from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Callable, Mapping

from .contracts import MemoryConflict, MemoryKind, MemoryQuery, MemoryRecord
from .store import MemoryStore


def _id(kind: MemoryKind, content: Mapping[str, Any], *, identity: Mapping[str, Any]) -> str:
    raw = json.dumps({"kind": kind.value, "content": dict(content), "identity": dict(identity)}, sort_keys=True, separators=(",", ":"))
    return f"mem-{sha256(raw.encode("utf-8")).hexdigest()[:24]}"


@dataclass(frozen=True)
class MemoryValidation:
    memory: MemoryRecord
    current: bool
    reason: str
    conflict: MemoryConflict | None = None


class EngineeringMemory:
    """Phase 14 memory facade: useful history, never runtime authority."""

    def __init__(self, store: MemoryStore, now: Callable[[], datetime] | None = None) -> None:
        self._store = store
        self._now = now or (lambda: datetime.now(timezone.utc))

    def remember_failure(self, *, run_id: str, step_id: str | None, attempt_id: str | None,
                         failure_signature: str, category: str, outcome: str, source_refs: tuple[str, ...],
                         repository_id: str | None = None, source_revision: str | None = None,
                         tags: tuple[str, ...] = (), supersedes: str | None = None) -> MemoryRecord:
        content = {"failure_signature": failure_signature, "category": category, "outcome": outcome}
        return self._remember(MemoryKind.FAILURE, content, run_id=run_id, step_id=step_id, attempt_id=attempt_id,
                              repository_id=repository_id, source_revision=source_revision, source_refs=source_refs,
                              tags=tags, supersedes=supersedes)

    def remember_repository(self, *, repository_id: str, revision: str, source_digest: str,
                            architecture: tuple[str, ...] = (), conventions: tuple[str, ...] = (),
                            decisions: tuple[str, ...] = (), verification: tuple[str, ...] = (),
                            source_refs: tuple[str, ...] = (), tags: tuple[str, ...] = (),
                            supersedes: str | None = None) -> MemoryRecord:
        content = {"architecture": list(architecture), "conventions": list(conventions),
                   "decisions": list(decisions), "verification": list(verification)}
        return self._remember(MemoryKind.REPOSITORY, content, repository_id=repository_id,
                              source_revision=revision, source_digest=source_digest, source_refs=source_refs,
                              tags=tags, supersedes=supersedes)

    def remember_context(self, *, repository_id: str | None, revision: str | None, context_digest: str,
                         items: tuple[Mapping[str, Any], ...], source_refs: tuple[str, ...],
                         run_id: str | None = None, tags: tuple[str, ...] = (),
                         supersedes: str | None = None) -> MemoryRecord:
        content = {"context_digest": context_digest, "items": [dict(item) for item in items]}
        return self._remember(MemoryKind.CONTEXT, content, run_id=run_id, repository_id=repository_id,
                              source_revision=revision, source_digest=context_digest, source_refs=source_refs,
                              tags=tags, supersedes=supersedes)

    def _remember(self, kind: MemoryKind, content: Mapping[str, Any], *, run_id: str | None = None,
                  step_id: str | None = None, attempt_id: str | None = None, repository_id: str | None = None,
                  source_revision: str | None = None, source_digest: str | None = None,
                  source_refs: tuple[str, ...] = (), tags: tuple[str, ...] = (), supersedes: str | None = None) -> MemoryRecord:
        if not source_refs:
            raise ValueError("memory requires provenance source references")
        created = self._now().astimezone(timezone.utc).isoformat()
        identity = {"run_id": run_id, "step_id": step_id, "attempt_id": attempt_id,
                    "repository_id": repository_id, "source_revision": source_revision,
                    "source_digest": source_digest, "source_refs": source_refs, "supersedes": supersedes}
        record = MemoryRecord(memory_id=_id(kind, content, identity=identity), kind=kind, content=dict(content),
                              created_at=created, run_id=run_id, step_id=step_id, attempt_id=attempt_id,
                              repository_id=repository_id, source_revision=source_revision, source_digest=source_digest,
                              source_refs=source_refs, tags=tags, supersedes=supersedes)
        self._store.append(record)
        return record

    def search(self, query: MemoryQuery) -> tuple[MemoryRecord, ...]:
        return self._store.query(query)

    def validate_repository(self, memory_id: str, *, current_revision: str, current_digest: str | None = None) -> MemoryValidation:
        memory = self._store.get(memory_id)
        if memory is None:
            raise KeyError(memory_id)
        if memory.kind is not MemoryKind.REPOSITORY:
            raise ValueError("repository validation requires repository memory")
        if memory.source_revision != current_revision or (current_digest is not None and memory.source_digest != current_digest):
            conflict = MemoryConflict(memory.memory_id, "repository current state changed", memory.source_revision, current_revision)
            return MemoryValidation(memory, False, "STALE", conflict)
        return MemoryValidation(memory, True, "CURRENT_REVISION_MATCH")

    def validate_context(self, memory_id: str, *, current_revision: str | None, current_context_digest: str) -> MemoryValidation:
        memory = self._store.get(memory_id)
        if memory is None:
            raise KeyError(memory_id)
        if memory.kind is not MemoryKind.CONTEXT:
            raise ValueError("context validation requires context memory")
        if memory.source_revision != current_revision or memory.source_digest != current_context_digest:
            conflict = MemoryConflict(memory.memory_id, "current context changed", memory.source_revision, current_revision)
            return MemoryValidation(memory, False, "STALE", conflict)
        return MemoryValidation(memory, True, "CURRENT_CONTEXT_MATCH")

    def conflicts_with_current(self, memory: MemoryRecord, *, current_revision: str | None,
                               current_digest: str | None = None) -> MemoryConflict | None:
        if memory.source_revision is None or current_revision is None:
            return None
        if memory.source_revision != current_revision or (current_digest is not None and memory.source_digest != current_digest):
            return MemoryConflict(memory.memory_id, "historical memory conflicts with current authoritative state",
                                  memory.source_revision, current_revision)
        return None
