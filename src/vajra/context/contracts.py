from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TrustClass(str, Enum):
    AUTHORITATIVE = "AUTHORITATIVE"
    VERIFIED_EVIDENCE = "VERIFIED_EVIDENCE"
    REPOSITORY_CONTENT = "REPOSITORY_CONTENT"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    WORKER_OUTPUT = "WORKER_OUTPUT"
    EXTERNAL_CONTENT = "EXTERNAL_CONTENT"
    HISTORICAL = "HISTORICAL"
    UNTRUSTED_INSTRUCTION = "UNTRUSTED_INSTRUCTION"
    GENERATED_SUMMARY = "GENERATED_SUMMARY"
    LOSSY_COMPRESSION = "LOSSY_COMPRESSION"
    UNKNOWN = "UNKNOWN"


class SourceKind(str, Enum):
    OBJECTIVE = "OBJECTIVE"
    ACCEPTANCE = "ACCEPTANCE"
    FILE = "FILE"
    SYMBOL = "SYMBOL"
    REFERENCE = "REFERENCE"
    DEPENDENCY = "DEPENDENCY"
    HISTORY = "HISTORY"
    EVIDENCE = "EVIDENCE"
    WORKSPACE_METADATA = "WORKSPACE_METADATA"
    RECONCILIATION = "RECONCILIATION"
    CONSTRAINT = "CONSTRAINT"
    CAPABILITY = "CAPABILITY"
    BUDGET = "BUDGET"
    INSTRUCTION = "INSTRUCTION"


class Freshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    INVALID = "INVALID"


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return _canonical({k: getattr(value, k) for k in value.__dataclass_fields__})
    return value


def stable_digest(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class ContextItem:
    item_id: str
    source_kind: SourceKind
    trust: TrustClass
    locator: str
    content: str
    revision: str
    digest: str
    freshness: Freshness = Freshness.FRESH
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("item_id", "locator", "content", "revision", "digest"):
            if not getattr(self, name):
                raise ValueError(f"{name} must not be empty")
        if self.trust is TrustClass.AUTHORITATIVE and self.source_kind not in {
            SourceKind.OBJECTIVE,
            SourceKind.ACCEPTANCE,
            SourceKind.EVIDENCE,
            SourceKind.WORKSPACE_METADATA,
            SourceKind.RECONCILIATION,
            SourceKind.CONSTRAINT,
            SourceKind.CAPABILITY,
            SourceKind.BUDGET,
        }:
            raise ValueError("repository/model content cannot be authoritative context")


@dataclass(frozen=True)
class ContextBundle:
    bundle_id: str
    run_id: str
    workspace_id: str
    repository_id: str
    revision: str
    filesystem_digest: str
    index_digest: str
    query: str
    generated_at: datetime
    items: tuple[ContextItem, ...]
    digest: str
    acceptance_criteria: tuple[str, ...] = ()
    repository_summary: str = ""
    relevant_files: tuple[str, ...] = ()
    relevant_symbols: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    recent_changes: tuple[str, ...] = ()
    relevant_history: tuple[str, ...] = ()
    current_reconciliation: dict[str, Any] = field(default_factory=dict)
    constraints: tuple[str, ...] = ()
    allowed_capabilities: tuple[str, ...] = ()
    budget: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("bundle_id", "run_id", "workspace_id", "repository_id", "revision", "filesystem_digest", "index_digest", "query", "digest"):
            if not getattr(self, name):
                raise ValueError(f"{name} must not be empty")
        if any(item.freshness is not Freshness.FRESH for item in self.items):
            raise ValueError("a ContextBundle cannot contain stale or invalid items")
        expected = stable_digest({
            "bundle_id": self.bundle_id,
            "run_id": self.run_id,
            "workspace_id": self.workspace_id,
            "repository_id": self.repository_id,
            "revision": self.revision,
            "filesystem_digest": self.filesystem_digest,
            "index_digest": self.index_digest,
            "query": self.query,
            "items": self.items,
            "acceptance_criteria": self.acceptance_criteria,
            "repository_summary": self.repository_summary,
            "relevant_files": self.relevant_files,
            "relevant_symbols": self.relevant_symbols,
            "dependencies": self.dependencies,
            "recent_changes": self.recent_changes,
            "relevant_history": self.relevant_history,
            "current_reconciliation": self.current_reconciliation,
            "constraints": self.constraints,
            "allowed_capabilities": self.allowed_capabilities,
            "budget": self.budget,
        })
        if self.digest != expected:
            raise ValueError("ContextBundle digest mismatch")


@dataclass(frozen=True)
class IndexFile:
    path: str
    digest: str
    size: int
    language: str
    symbols: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepositoryIndex:
    root: str
    revision: str
    filesystem_digest: str
    files: tuple[IndexFile, ...]
    history: tuple[str, ...]
    digest: str

    def __post_init__(self) -> None:
        expected = stable_digest({
            "root": self.root,
            "revision": self.revision,
            "filesystem_digest": self.filesystem_digest,
            "files": self.files,
            "history": self.history,
        })
        if self.digest != expected:
            raise ValueError("RepositoryIndex digest mismatch")


@dataclass(frozen=True)
class RetrievalHit:
    path: str
    score: int
    reasons: tuple[str, ...]


__all__ = [
    "ContextItem", "ContextBundle", "Freshness", "IndexFile", "RepositoryIndex",
    "RetrievalHit", "SourceKind", "TrustClass", "stable_digest",
]
