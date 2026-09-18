from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
from threading import RLock
from typing import Iterable

from .contracts import AuditEventType, AuditRecord


class AuditStore:
    """Append-only, fsync-backed observability journal."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._records: list[AuditRecord] = []
        self._ids: set[str] = set()
        self._load()

    def append(self, record: AuditRecord) -> AuditRecord:
        with self._lock:
            record = record.with_digest()
            if record.audit_id in self._ids:
                existing = next(r for r in self._records if r.audit_id == record.audit_id)
                if existing.record_digest == record.record_digest:
                    return existing
                raise ValueError(f"audit id already exists with different content: {record.audit_id}")
            payload = asdict(record)
            payload["event_type"] = record.event_type.value
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._records.append(record)
            self._ids.add(record.audit_id)
            return record

    def list_for_run(self, run_id: str) -> tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(r for r in self._records if r.run_id == run_id)

    def all(self) -> tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(self._records)

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    from .contracts import AuditEventType
                    payload["event_type"] = AuditEventType(payload["event_type"])
                    record = AuditRecord(**payload)
                except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"invalid audit record at line {line_no}") from exc
                self._records.append(record)



class AuditLoopObserver:
    """Bridges autonomous loop observations into the hardening audit journal."""

    def __init__(self, store: AuditStore, *, clock=None) -> None:
        self.store = store
        self._clock = clock

    def observe(self, *, phase, run_id: str, payload: dict[str, object]) -> None:
        from datetime import datetime, timezone
        timestamp = self._clock() if self._clock is not None else datetime.now(timezone.utc)
        event_type = AuditEventType.VERIFICATION if phase.value == "VERIFY" else AuditEventType.EXECUTION
        index = len(self.store.list_for_run(run_id))
        record = AuditRecord(
            audit_id=f"{run_id}:{phase.value}:{index}",
            event_type=event_type,
            timestamp=timestamp.isoformat(),
            run_id=run_id,
            step_id=str(payload["step_id"]) if payload.get("step_id") else None,
            attempt_id=str(payload["attempt_id"]) if payload.get("attempt_id") else None,
            worker_id=str(payload["worker_id"]) if payload.get("worker_id") else None,
            model_id=str(payload["model_id"]) if payload.get("model_id") else None,
            operation=str(payload["operation"]) if payload.get("operation") else None,
            outcome=str(payload.get("outcome", "")),
            reason=str(payload.get("reason", "")),
            payload={"phase": phase.value, **payload},
        )
        self.store.append(record)


class Observability:
    """Queryable view over durable audit events, without owning Run state."""

    def __init__(self, store: AuditStore) -> None:
        self.store = store

    def run_timeline(self, run_id: str) -> tuple[AuditRecord, ...]:
        return self.store.list_for_run(run_id)

    def explain(self, run_id: str) -> dict[str, object]:
        events = self.store.list_for_run(run_id)
        return {
            "run_id": run_id,
            "event_count": len(events),
            "steps": sorted({e.step_id for e in events if e.step_id}),
            "attempts": sorted({e.attempt_id for e in events if e.attempt_id}),
            "workers": sorted({e.worker_id for e in events if e.worker_id}),
            "models": sorted({e.model_id for e in events if e.model_id}),
            "intents": sorted({e.payload.get("intent_id") for e in events if e.payload.get("intent_id")}),
            "executions": sorted({e.operation for e in events if e.operation}),
            "failures": [e.reason for e in events if e.event_type.value == "RECOVERY" or e.outcome == "FAILED"],
            "recoveries": [e.reason for e in events if e.event_type.value == "RECOVERY"],
            "verification": [e.payload for e in events if e.event_type.value == "VERIFICATION"],
            "evidence": [e.payload.get("evidence_refs", ()) for e in events if e.payload.get("evidence_refs")],
        }


__all__ = ["AuditLoopObserver", "AuditStore", "Observability"]
