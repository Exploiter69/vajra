from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
from threading import RLock
from typing import Iterable

from .contracts import AuditRecord


class AuditStore:
    """Append-only, fsync-backed observability journal."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._records: list[AuditRecord] = []
        self._load()

    def append(self, record: AuditRecord) -> AuditRecord:
        with self._lock:
            record = record.with_digest()
            if self._records and record.audit_id == self._records[-1].audit_id:
                return record
            payload = asdict(record)
            payload["event_type"] = record.event_type.value
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._records.append(record)
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


__all__ = ["AuditStore", "Observability"]
