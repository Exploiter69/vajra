from __future__ import annotations

import re
from dataclasses import dataclass

from .contracts import RepositoryIndex, RetrievalHit


class RetrievalMode:
    PATH = "path"
    EXACT = "exact"
    LEXICAL = "lexical"
    SYMBOL = "symbol"
    DEPENDENCY = "dependency"
    HISTORY = "history"


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    modes: tuple[str, ...] = (
        RetrievalMode.EXACT,
        RetrievalMode.PATH,
        RetrievalMode.LEXICAL,
        RetrievalMode.SYMBOL,
        RetrievalMode.DEPENDENCY,
        RetrievalMode.HISTORY,
    )
    limit: int = 12

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("retrieval query must not be empty")
        if self.limit < 1:
            raise ValueError("retrieval limit must be positive")


class DeterministicRetriever:
    """Rank repository evidence without embeddings or nondeterministic services."""

    @staticmethod
    def _tokens(text: str) -> tuple[str, ...]:
        return tuple(dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_./:-]*", text.lower())))

    def search(self, index: RepositoryIndex, query: RetrievalQuery) -> tuple[RetrievalHit, ...]:
        tokens = self._tokens(query.text)
        scores: dict[str, tuple[int, set[str]]] = {}
        by_path = {item.path: item for item in index.files}
        for item in index.files:
            score = 0
            reasons: set[str] = set()
            path_lower = item.path.lower()
            symbols = {s.lower() for s in item.symbols}
            references = {r.lower() for r in item.references}
            dependencies = {d.lower() for d in item.dependencies}
            for token in tokens:
                if RetrievalMode.EXACT in query.modes and token == path_lower:
                    score += 100
                    reasons.add("exact-path")
                if RetrievalMode.PATH in query.modes and token in path_lower:
                    score += 30
                    reasons.add("path")
                if RetrievalMode.SYMBOL in query.modes and token in symbols:
                    score += 80
                    reasons.add("symbol")
                if RetrievalMode.LEXICAL in query.modes and token in references:
                    score += 20
                    reasons.add("reference")
                if RetrievalMode.DEPENDENCY in query.modes and any(token in dep.lower() for dep in dependencies):
                    score += 25
                    reasons.add("dependency")
            if score:
                scores[item.path] = (score, reasons)
        if RetrievalMode.HISTORY in query.modes:
            for entry in index.history:
                lower = entry.lower()
                if any(token in lower for token in tokens):
                    # History is represented as a synthetic locator, keeping file ranking stable.
                    key = f"@history:{entry}"
                    scores[key] = (15, {"history"})
        ranked = sorted(scores.items(), key=lambda pair: (-pair[1][0], pair[0]))[: query.limit]
        return tuple(RetrievalHit(path=path, score=score, reasons=tuple(sorted(reasons))) for path, (score, reasons) in ranked)


__all__ = ["DeterministicRetriever", "RetrievalMode", "RetrievalQuery"]
