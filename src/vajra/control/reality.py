from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vajra.control.contracts import (
    DivergenceClass,
    ReconciliationDisposition,
    ReconciliationReport,
    WorktreeContract,
)
from vajra.domain import EngineeringRun


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def stable_digest(value: Any) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def filesystem_digest(root: str | Path) -> str:
    path = Path(root).resolve()

    if not path.is_dir():
        raise ValueError(f"workspace does not exist: {path}")

    entries: list[dict[str, str]] = []

    for current, dirs, files in os.walk(path):
        dirs[:] = sorted(directory for directory in dirs if directory != ".git")

        for name in sorted(files):
            candidate = Path(current) / name

            try:
                stat = candidate.lstat()
            except OSError:
                continue

            relative = candidate.relative_to(path).as_posix()

            if candidate.is_symlink():
                entries.append(
                    {
                        "path": relative,
                        "kind": "symlink",
                        "target": os.readlink(candidate),
                    }
                )
                continue

            if not candidate.is_file():
                entries.append(
                    {
                        "path": relative,
                        "kind": "other",
                        "mode": str(stat.st_mode),
                        "size": str(stat.st_size),
                    }
                )
                continue

            digest = hashlib.sha256()

            try:
                with candidate.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
            except OSError:
                continue

            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "size": str(stat.st_size),
                    "digest": digest.hexdigest(),
                }
            )

    return stable_digest(entries)


class RealityObserver:
    """
    Produces a fresh ReconciliationReport from independently observed state.

    This class does not mutate the Run, workspace, Git repository, lease, or
    verification state. The caller supplies the authority-bound observations
    that it cannot safely infer itself.
    """

    def observe(
        self,
        *,
        run: EngineeringRun,
        worktree: WorktreeContract,
        git_revision: str,
        git_status: str,
        active_lease_state: str,
        verification_state: str,
        budget_state: str,
        checkpoint_ref: str | None = None,
        observed_external_state: dict[str, Any] | None = None,
        observed_at: datetime | None = None,
        expected_durable_state_digest: str | None = None,
    ) -> ReconciliationReport:
        workspace = Path(worktree.path).resolve()

        actual_filesystem_digest = filesystem_digest(workspace)
        actual_status_digest = hashlib.sha256(git_status.encode("utf-8")).hexdigest()

        canonical_digest = stable_digest(run)

        reasons: list[str] = []
        observations: list[
            tuple[int, DivergenceClass, ReconciliationDisposition, str]
        ] = []

        if expected_durable_state_digest is not None and canonical_digest != expected_durable_state_digest:
            observations.append(
                (
                    50,
                    DivergenceClass.RECOVERABLE,
                    ReconciliationDisposition.RECOVERABLE,
                    "WARNING",
                )
            )
            reasons.append("Durable VAJRA state differs from its reconciliation checkpoint")

        if git_revision != worktree.base_revision:
            observations.append(
                (
                    40,
                    DivergenceClass.REVERIFY,
                    ReconciliationDisposition.REVERIFY,
                    "WARNING",
                )
            )
            reasons.append("Git revision differs from worktree base revision")

        if actual_status_digest != worktree.git_status_digest:
            observations.append(
                (
                    30,
                    DivergenceClass.RECOVERABLE,
                    ReconciliationDisposition.RECOVERABLE,
                    "WARNING",
                )
            )
            reasons.append("Git status differs from creation state")

        if active_lease_state == "INVALID":
            observations.append(
                (
                    80,
                    DivergenceClass.OWNERSHIP_DIVERGENCE,
                    ReconciliationDisposition.WAITING_HUMAN,
                    "CRITICAL",
                )
            )
            reasons.append("Active lease is invalid")

        if verification_state == "FAILED":
            observations.append(
                (
                    70,
                    DivergenceClass.VERIFICATION_DIVERGENCE,
                    ReconciliationDisposition.REVERIFY,
                    "CRITICAL",
                )
            )
            reasons.append("Verification state is failed")

        if budget_state in {"EXHAUSTED", "EXPIRED"}:
            observations.append(
                (
                    100,
                    DivergenceClass.BUDGET_DIVERGENCE,
                    ReconciliationDisposition.ABORT,
                    "CRITICAL",
                )
            )
            reasons.append("Budget is exhausted or expired")

        if observations:
            _, divergence, disposition, severity = max(
                observations,
                key=lambda observation: observation[0],
            )
        else:
            divergence = DivergenceClass.NONE
            disposition = ReconciliationDisposition.CONSISTENT
            severity = "NORMAL"

        external = dict(observed_external_state or {})
        external["reasons"] = tuple(reasons)

        timestamp = observed_at or datetime.now(timezone.utc)

        return ReconciliationReport(
            report_id=stable_digest(
                {
                    "run_id": run.run_id,
                    "observed_at": timestamp,
                    "canonical": canonical_digest,
                    "workspace": worktree.workspace_id,
                    "git_revision": git_revision,
                    "filesystem": actual_filesystem_digest,
                }
            ),
            run_id=run.run_id,
            generated_at=timestamp,
            durable_state_digest=canonical_digest,
            workspace_id=worktree.workspace_id,
            workspace_state="PRESENT",
            git_revision=git_revision,
            git_status_digest=actual_status_digest,
            filesystem_digest=actual_filesystem_digest,
            checkpoint_ref=checkpoint_ref,
            active_lease_state=active_lease_state,
            verification_state=verification_state,
            budget_state=budget_state,
            observed_external_state=external,
            divergence_class=divergence,
            severity=severity,
            freshness="FRESH",
            disposition=disposition,
        )


__all__ = [
    "RealityObserver",
    "filesystem_digest",
    "stable_digest",
]
