from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping


class MemoryKind(str, Enum):
    FAILURE = "FAILURE"
    REPOSITORY = "REPOSITORY"
    CONTEXT = "CONTEXT"


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class MemoryRecord:
    """Immutable informational memory; never an authority source."""
    memory_id: str
    kind: MemoryKind
    content: Mapping[str, Any]
    created_at: str
    run_id: str | None = None
    step_id: str | None = None
    attempt_id: str | None = None
    repository_id: str | None = None
    source_revision: str | None = None
    source_digest: str | None = None
    source_refs: tuple[str, ...] = ()
    provenance: str = "HISTORICAL_MEMORY"
    supersedes: str | None = None
    tags: tuple[str, ...] = ()
    record_digest: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not self.memory_id or not self.created_at:
            raise ValueError("memory_id and created_at are required")
        if not self.content:
            raise ValueError("memory content cannot be empty")
        if self.provenance != "HISTORICAL_MEMORY":
            raise ValueError("engineering memory is informational and must remain historical")
        expected = _digest(self.to_payload(include_digest=False))
        if self.record_digest and self.record_digest != expected:
            raise ValueError("memory record digest mismatch")
        object.__setattr__(self, "record_digest", expected)

    def to_payload(self, *, include_digest: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "memory_id": self.memory_id, "kind": self.kind.value, "content": dict(self.content),
            "created_at": self.created_at, "run_id": self.run_id, "step_id": self.step_id,
            "attempt_id": self.attempt_id, "repository_id": self.repository_id,
            "source_revision": self.source_revision, "source_digest": self.source_digest,
            "source_refs": list(self.source_refs), "provenance": self.provenance,
            "supersedes": self.supersedes, "tags": list(self.tags),
        }
        if include_digest:
            payload["record_digest"] = self.record_digest
        return payload

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "MemoryRecord":
        return cls(
            memory_id=str(payload["memory_id"]), kind=MemoryKind(str(payload["kind"])),
            content=dict(payload["content"]), created_at=str(payload["created_at"]),
            run_id=payload.get("run_id"), step_id=payload.get("step_id"), attempt_id=payload.get("attempt_id"),
            repository_id=payload.get("repository_id"), source_revision=payload.get("source_revision"),
            source_digest=payload.get("source_digest"), source_refs=tuple(payload.get("source_refs", ())),
            provenance=str(payload.get("provenance", "HISTORICAL_MEMORY")), supersedes=payload.get("supersedes"),
            tags=tuple(payload.get("tags", ())), record_digest=str(payload.get("record_digest", "")),
        )


@dataclass(frozen=True)
class MemoryQuery:
    kind: MemoryKind | None = None
    repository_id: str | None = None
    run_id: str | None = None
    tags: tuple[str, ...] = ()
    text: str | None = None
    limit: int = 20

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 500:
            raise ValueError("limit must be between 1 and 500")


@dataclass(frozen=True)
class MemoryConflict:
    memory_id: str
    reason: str
    historical_revision: str | None
    current_revision: str | None
    disposition: str = "CURRENT_TRUTH_WINS"
