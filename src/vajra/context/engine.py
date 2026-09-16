from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from vajra.control.reality import filesystem_digest

from .contracts import ContextBundle, ContextItem, Freshness, RepositoryIndex, SourceKind, TrustClass, stable_digest
from .index import RepositoryIndexer
from .retrieval import DeterministicRetriever, RetrievalQuery


INSTRUCTION_FILES = frozenset({
    "agents.md", "claude.md", "gemini.md", "copilot-instructions.md", ".cursorrules", ".cursorignore",
})


class ContextError(ValueError):
    pass


class ContextEngine:
    """Build bounded, provenance-tagged context from current workspace reality."""

    def __init__(self, indexer: RepositoryIndexer | None = None, retriever: DeterministicRetriever | None = None) -> None:
        self._indexer = indexer or RepositoryIndexer()
        self._retriever = retriever or DeterministicRetriever()
        self._cache: dict[tuple[str, str, str], RepositoryIndex] = {}
        self._lock = RLock()

    def index(self, workspace: str | Path, revision: str | None = None) -> RepositoryIndex:
        root = Path(workspace).expanduser().resolve()
        fs = filesystem_digest(root)
        revision_key = revision or "WORKTREE"
        key = (str(root), revision_key, fs)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            index = self._indexer.build(root, revision=revision)
            self._cache[key] = index
            for old_key in tuple(self._cache):
                if old_key[0] == str(root) and old_key != key:
                    del self._cache[old_key]
            return index

    def invalidate(self, workspace: str | Path) -> None:
        root = str(Path(workspace).expanduser().resolve())
        with self._lock:
            for key in tuple(self._cache):
                if key[0] == root:
                    del self._cache[key]

    def build_bundle(
        self,
        *,
        run_id: str,
        workspace_id: str,
        repository_id: str,
        objective: str,
        workspace: str | Path,
        revision: str | None = None,
        acceptance_criteria: tuple[str, ...] = (),
        current_reconciliation: dict[str, Any] | None = None,
        constraints: tuple[str, ...] = (),
        allowed_capabilities: tuple[str, ...] = (),
        budget: dict[str, Any] | None = None,
        limit: int = 12,
        max_bytes: int = 64 * 1024,
    ) -> ContextBundle:
        for name, value in (("run_id", run_id), ("workspace_id", workspace_id), ("repository_id", repository_id), ("objective", objective)):
            if not value or not value.strip():
                raise ContextError(f"{name} must not be empty")
        if limit < 1 or max_bytes < 1:
            raise ContextError("context bounds must be positive")

        root = Path(workspace).expanduser().resolve()
        current_fs = filesystem_digest(root)
        index = self.index(root, revision=revision)
        actual_revision = index.revision
        query = RetrievalQuery(objective, limit=limit)
        hits = self._retriever.search(index, query)
        by_path = {item.path: item for item in index.files}
        items: list[ContextItem] = []
        used = 0

        objective_item = ContextItem(
            item_id=stable_digest((run_id, "objective", objective)),
            source_kind=SourceKind.OBJECTIVE,
            trust=TrustClass.AUTHORITATIVE,
            locator=f"run:{run_id}:objective",
            content=objective,
            revision=actual_revision,
            digest=stable_digest(objective),
        )
        objective_size = len(objective.encode("utf-8"))
        if objective_size > max_bytes:
            raise ContextError("objective exceeds context byte bound")
        items.append(objective_item)
        used = objective_size

        relevant_files: list[str] = []
        relevant_symbols: set[str] = set()
        dependencies: set[str] = set()
        relevant_history: list[str] = []
        for hit in hits:
            if hit.path.startswith("@history:"):
                content = hit.path[len("@history:"):]
                relevant_history.append(content)
                item = ContextItem(
                    item_id=stable_digest((actual_revision, hit.path)),
                    source_kind=SourceKind.HISTORY,
                    trust=TrustClass.HISTORICAL,
                    locator=hit.path,
                    content=content,
                    revision=actual_revision,
                    digest=stable_digest(content),
                    metadata={"score": hit.score, "reasons": hit.reasons},
                )
            else:
                indexed = by_path[hit.path]
                candidate = root / indexed.path
                try:
                    content = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                lower_name = indexed.path.rsplit("/", 1)[-1].lower()
                if lower_name in INSTRUCTION_FILES or lower_name.startswith(".cursorrules"):
                    source_kind = SourceKind.INSTRUCTION
                    trust = TrustClass.UNTRUSTED_INSTRUCTION
                else:
                    source_kind = SourceKind.FILE
                    trust = TrustClass.REPOSITORY_CONTENT
                relevant_files.append(indexed.path)
                relevant_symbols.update(indexed.symbols)
                dependencies.update(indexed.dependencies)
                item = ContextItem(
                    item_id=stable_digest((actual_revision, indexed.path, indexed.digest)),
                    source_kind=source_kind,
                    trust=trust,
                    locator=indexed.path,
                    content=content,
                    revision=actual_revision,
                    digest=indexed.digest,
                    metadata={
                        "language": indexed.language,
                        "symbols": indexed.symbols,
                        "dependencies": indexed.dependencies,
                        "score": hit.score,
                        "reasons": hit.reasons,
                    },
                )
            encoded_size = len(item.content.encode("utf-8"))
            if used + encoded_size > max_bytes:
                continue
            items.append(item)
            used += encoded_size

        generated = datetime.now(timezone.utc)
        acceptance = tuple(acceptance_criteria)
        reconciliation = dict(current_reconciliation or {})
        bundle_budget = dict(budget or {})
        recent_changes = index.history[:8]
        summary = f"{len(index.files)} indexed files; {len(relevant_files)} retrieved files; revision {actual_revision}"
        bundle_id = stable_digest((run_id, workspace_id, repository_id, actual_revision, current_fs, index.digest, objective, acceptance, reconciliation, constraints, allowed_capabilities, bundle_budget, tuple(i.item_id for i in items)))
        digest = stable_digest({
            "bundle_id": bundle_id, "run_id": run_id, "workspace_id": workspace_id, "repository_id": repository_id,
            "revision": actual_revision, "filesystem_digest": current_fs, "index_digest": index.digest,
            "query": objective, "items": tuple(items), "acceptance_criteria": acceptance,
            "repository_summary": summary, "relevant_files": tuple(relevant_files),
            "relevant_symbols": tuple(sorted(relevant_symbols)), "dependencies": tuple(sorted(dependencies)),
            "recent_changes": recent_changes, "relevant_history": tuple(relevant_history),
            "current_reconciliation": reconciliation, "constraints": tuple(constraints),
            "allowed_capabilities": tuple(allowed_capabilities), "budget": bundle_budget,
        })
        return ContextBundle(
            bundle_id=bundle_id, run_id=run_id, workspace_id=workspace_id, repository_id=repository_id,
            revision=actual_revision, filesystem_digest=current_fs, index_digest=index.digest,
            query=objective, generated_at=generated, items=tuple(items), digest=digest,
            acceptance_criteria=acceptance, repository_summary=summary,
            relevant_files=tuple(relevant_files), relevant_symbols=tuple(sorted(relevant_symbols)),
            dependencies=tuple(sorted(dependencies)), recent_changes=recent_changes,
            relevant_history=tuple(relevant_history), current_reconciliation=reconciliation,
            constraints=tuple(constraints), allowed_capabilities=tuple(allowed_capabilities), budget=bundle_budget,
        )


__all__ = ["ContextEngine", "ContextError", "INSTRUCTION_FILES"]
