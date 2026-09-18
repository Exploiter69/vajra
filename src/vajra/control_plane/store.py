from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class QueueEntry:
    entry_id: str
    run_id: str
    state: str
    enqueued_at: str
    claimed_at: str | None = None


@dataclass(frozen=True)
class StoredSchedule:
    schedule_id: str
    due_at: str
    job_type: str
    payload: dict[str, Any]
    interval_seconds: int | None
    enabled: bool


class ControlPlaneStore:
    """Append-only, restart-replayable queue and scheduling journal.

    Canonical Run state remains owned by VAJRA's StateStore/RunManager.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = RLock()
        self._queue: dict[str, QueueEntry] = {}
        self._schedules: dict[str, StoredSchedule] = {}
        self._commands: list[dict[str, Any]] = []
        self._next_sequence = 1
        self._load()

    def enqueue(self, entry_id: str, run_id: str, *, enqueued_at: str | None = None) -> QueueEntry:
        with self._lock:
            existing = self._queue.get(entry_id)
            if existing is not None:
                return existing
            entry = QueueEntry(entry_id, run_id, "QUEUED", enqueued_at or _now())
            self._append(_queue_record(entry))
            return self._queue[entry_id]

    def ready(self) -> tuple[QueueEntry, ...]:
        with self._lock:
            return tuple(sorted(
                (e for e in self._queue.values() if e.state == "QUEUED"),
                key=lambda e: (e.enqueued_at, e.entry_id),
            ))

    def claim(self, entry_id: str) -> QueueEntry:
        with self._lock:
            e = self._queue.get(entry_id)
            if e is None:
                raise KeyError(f"Unknown queue entry: {entry_id}")
            if e.state == "DISPATCHING":
                return e
            if e.state != "QUEUED":
                raise RuntimeError(f"Queue entry is not claimable: {entry_id}")
            updated = QueueEntry(e.entry_id, e.run_id, "DISPATCHING", e.enqueued_at, _now())
            self._append(_queue_record(updated))
            return self._queue[entry_id]

    def finish(self, entry_id: str) -> QueueEntry:
        return self._set_queue_state(entry_id, "DISPATCHED")

    def requeue(self, entry_id: str) -> QueueEntry:
        return self._set_queue_state(entry_id, "QUEUED", clear_claim=True)

    def cancel_queue(self, entry_id: str) -> QueueEntry:
        return self._set_queue_state(entry_id, "CANCELLED")

    def recover_dispatching(self) -> tuple[QueueEntry, ...]:
        with self._lock:
            stale = tuple(e for e in self._queue.values() if e.state == "DISPATCHING")
            for e in stale:
                self._append(_queue_record(QueueEntry(e.entry_id, e.run_id, "QUEUED", e.enqueued_at)))
            return tuple(self._queue[e.entry_id] for e in stale)

    def add_schedule(self, schedule: StoredSchedule) -> StoredSchedule:
        with self._lock:
            existing = self._schedules.get(schedule.schedule_id)
            if existing is not None:
                return existing
            self._append(_schedule_record(schedule))
            return self._schedules[schedule.schedule_id]

    def schedules(self) -> tuple[StoredSchedule, ...]:
        with self._lock:
            return tuple(sorted(self._schedules.values(), key=lambda s: s.schedule_id))

    def due_schedules(self, now: datetime) -> tuple[StoredSchedule, ...]:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        current = now.astimezone(timezone.utc)
        with self._lock:
            return tuple(s for s in self._schedules.values()
                         if s.enabled and datetime.fromisoformat(s.due_at) <= current)

    def advance_schedule(self, schedule_id: str, *, next_due_at: str | None) -> StoredSchedule:
        with self._lock:
            s = self._schedules.get(schedule_id)
            if s is None:
                raise KeyError(f"Unknown schedule: {schedule_id}")
            updated = StoredSchedule(
                s.schedule_id, next_due_at or s.due_at, s.job_type,
                dict(s.payload), s.interval_seconds, bool(next_due_at) and s.enabled,
            )
            self._append(_schedule_record(updated))
            return self._schedules[schedule_id]

    def disable_schedule(self, schedule_id: str) -> StoredSchedule:
        with self._lock:
            s = self._schedules.get(schedule_id)
            if s is None:
                raise KeyError(f"Unknown schedule: {schedule_id}")
            updated = StoredSchedule(s.schedule_id, s.due_at, s.job_type, dict(s.payload), s.interval_seconds, False)
            self._append(_schedule_record(updated))
            return self._schedules[schedule_id]

    def record_command(self, command_id: str, command: str, run_id: str | None, result: str) -> None:
        with self._lock:
            self._append({"type": "command", "command_id": command_id, "command": command,
                          "run_id": run_id, "result": result, "recorded_at": _now()})

    def _set_queue_state(self, entry_id: str, state: str, *, clear_claim: bool = False) -> QueueEntry:
        with self._lock:
            e = self._queue.get(entry_id)
            if e is None:
                raise KeyError(f"Unknown queue entry: {entry_id}")
            if e.state == state and not clear_claim:
                return e
            updated = QueueEntry(e.entry_id, e.run_id, state, e.enqueued_at,
                                  None if clear_claim else e.claimed_at)
            self._append(_queue_record(updated))
            return self._queue[entry_id]

    def _append(self, record: dict[str, Any]) -> None:
        record = dict(record)
        record["sequence"] = self._next_sequence
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._apply(record)
        self._next_sequence += 1

    def _apply(self, record: dict[str, Any]) -> None:
        if record.get("type") == "queue":
            self._queue[record["entry_id"]] = QueueEntry(
                record["entry_id"], record["run_id"], record["state"],
                record["enqueued_at"], record.get("claimed_at"),
            )
        elif record.get("type") == "schedule":
            self._schedules[record["schedule_id"]] = StoredSchedule(
                record["schedule_id"], record["due_at"], record["job_type"],
                dict(record.get("payload") or {}), record.get("interval_seconds"),
                bool(record["enabled"]),
            )
        elif record.get("type") == "command":
            self._commands.append(record)

    def _load(self) -> None:
        if not self._path.exists():
            return
        expected = 1
        last = 0
        with self._path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid control-plane journal line {line_no}") from exc
                if record.get("sequence") != expected:
                    raise ValueError(
                        f"Invalid control-plane journal sequence at line {line_no}: "
                        f"expected {expected}, got {record.get('sequence')}"
                    )
                self._apply(record)
                last = expected
                expected += 1
        self._next_sequence = last + 1


def _queue_record(entry: QueueEntry) -> dict[str, Any]:
    return {"type": "queue", "entry_id": entry.entry_id, "run_id": entry.run_id,
            "state": entry.state, "enqueued_at": entry.enqueued_at, "claimed_at": entry.claimed_at}


def _schedule_record(s: StoredSchedule) -> dict[str, Any]:
    return {"type": "schedule", "schedule_id": s.schedule_id, "due_at": s.due_at,
            "job_type": s.job_type, "payload": s.payload, "interval_seconds": s.interval_seconds,
            "enabled": s.enabled}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
