from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
from pathlib import Path
import threading
from typing import Iterable

from .contracts import MemoryQuery, MemoryRecord


class MemoryStore(ABC):
    @abstractmethod
    def append(self, record: MemoryRecord) -> None: ...
    @abstractmethod
    def get(self, memory_id: str) -> MemoryRecord | None: ...
    @abstractmethod
    def query(self, query: MemoryQuery) -> tuple[MemoryRecord, ...]: ...
    @abstractmethod
    def all(self) -> tuple[MemoryRecord, ...]: ...


class JsonlMemoryStore(MemoryStore):
    """Dependency-free append-only persistent memory store with fsync."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._records: dict[str, MemoryRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = MemoryRecord.from_payload(json.loads(line))
                except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise ValueError(f"invalid memory journal record at line {line_no}") from exc
                if record.memory_id in self._records:
                    raise ValueError(f"duplicate memory id: {record.memory_id}")
                if record.supersedes == record.memory_id:
                    raise ValueError(f"memory record cannot supersede itself: {record.memory_id}")
                self._records[record.memory_id] = record

    def append(self, record: MemoryRecord) -> None:
        with self._lock:
            if record.supersedes is not None and record.supersedes not in self._records:
                raise ValueError(f"superseded memory does not exist: {record.supersedes}")
            existing = self._records.get(record.memory_id)
            if existing is not None:
                if existing.record_digest == record.record_digest:
                    return
                raise ValueError(f"memory id already exists with different content: {record.memory_id}")
            line = json.dumps(record.to_payload(), sort_keys=True, separators=(",", ":")) + "\n"
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            self._records[record.memory_id] = record

    def get(self, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            return self._records.get(memory_id)

    def all(self) -> tuple[MemoryRecord, ...]:
        with self._lock:
            return tuple(self._records.values())

    def query(self, query: MemoryQuery) -> tuple[MemoryRecord, ...]:
        terms = tuple(t.lower() for t in (query.text or "").split() if t)
        with self._lock:
            records: Iterable[MemoryRecord] = tuple(self._records.values())
            if not query.include_superseded:
                superseded = {r.supersedes for r in records if r.supersedes}
                records = [r for r in records if r.memory_id not in superseded]
            records = [r for r in records if query.kind is None or r.kind is query.kind]
            records = [r for r in records if query.repository_id is None or r.repository_id == query.repository_id]
            records = [r for r in records if query.run_id is None or r.run_id == query.run_id]
            records = [r for r in records if not query.tags or set(query.tags).issubset(r.tags)]
            if terms:
                records = [r for r in records if all(term in json.dumps(r.content, sort_keys=True).lower() for term in terms)]
            return tuple(sorted(records, key=lambda r: (r.created_at, r.memory_id), reverse=True)[:query.limit])
