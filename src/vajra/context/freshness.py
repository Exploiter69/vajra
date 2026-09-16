from __future__ import annotations

from pathlib import Path

from vajra.control.reality import filesystem_digest

from .contracts import ContextBundle, Freshness


class ContextFreshness:
    """Checks whether a ContextBundle still describes the current workspace."""

    @staticmethod
    def check(bundle: ContextBundle, workspace: str | Path, revision: str | None = None) -> Freshness:
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            return Freshness.INVALID
        if revision is not None and revision != bundle.revision:
            return Freshness.STALE
        try:
            current = filesystem_digest(root)
        except ValueError:
            return Freshness.INVALID
        return Freshness.FRESH if current == bundle.filesystem_digest else Freshness.STALE

    @staticmethod
    def require_fresh(bundle: ContextBundle, workspace: str | Path, revision: str | None = None) -> None:
        status = ContextFreshness.check(bundle, workspace, revision)
        if status is not Freshness.FRESH:
            raise ValueError(f"ContextBundle is {status.value.lower()}")


__all__ = ["ContextFreshness"]
