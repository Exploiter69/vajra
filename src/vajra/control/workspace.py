from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic, sleep

from vajra.domain import Checkpoint

from .reality import filesystem_digest
from .worktree import WorktreeError, WorktreeInspection, WorktreeManager
from .contracts import WorktreeContract, stable_digest


@dataclass(frozen=True)
class WorkspaceRecord:
    workspace_id: str
    run_id: str
    repository_id: str
    repository: str
    base_revision: str
    path: str
    owner_token: str
    status: str = "ACTIVE"
    cleanup_state: str = "RETAINED"
    checkpoint_ref: str | None = None
    git_concurrency_key: str = ""
    record_digest: str = ""

    def __post_init__(self) -> None:
        for name in ("workspace_id", "run_id", "repository_id", "repository", "base_revision", "path", "owner_token"):
            if not getattr(self, name):
                raise ValueError(f"{name} must not be empty")
        expected = stable_digest({k: getattr(self, k) for k in self.__dataclass_fields__ if k != "record_digest"})
        if self.record_digest and self.record_digest != expected:
            raise ValueError("workspace record digest mismatch")


@dataclass(frozen=True)
class WorkspaceRecovery:
    record: WorkspaceRecord
    inspection: WorktreeInspection | None
    disposition: str
    reason: str


class GitSerialization:
    """Cross-process repository lock using the OS advisory file-lock primitive."""

    def __init__(self, lock_root: str | Path, repository_id: str, timeout_seconds: float = 30.0) -> None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds must not be negative")
        self.path = Path(lock_root).expanduser().resolve() / f"{stable_digest(repository_id)[:32]}.lock"
        self.timeout_seconds = timeout_seconds
        self._handle = None

    def __enter__(self) -> "GitSerialization":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        deadline = monotonic() + self.timeout_seconds
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._handle = handle
                return self
            except BlockingIOError:
                if monotonic() >= deadline:
                    handle.close()
                    raise TimeoutError(f"Git serialization lock timeout: {self.path}")
                sleep(0.05)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


class WorkspaceManager:
    """Durable registry around WorktreeManager for Run/workspace recovery."""

    def __init__(self, metadata_root: str | Path) -> None:
        self.metadata_root = Path(metadata_root).expanduser().resolve()
        self.metadata_root.mkdir(parents=True, exist_ok=True)
        self._worktrees = WorktreeManager(self.metadata_root / "worktrees")
        self._locks = self.metadata_root / "git-locks"

    def _record_path(self, workspace_id: str) -> Path:
        return self.metadata_root / "workspaces" / workspace_id / "record.json"

    def _write(self, record: WorkspaceRecord) -> None:
        path = self._record_path(record.workspace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(record)
        payload["record_digest"] = stable_digest({k: v for k, v in payload.items() if k != "record_digest"})
        path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    def load(self, workspace_id: str) -> WorkspaceRecord:
        path = self._record_path(workspace_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise WorktreeError(f"workspace record not found: {workspace_id}") from exc
        return WorkspaceRecord(**payload)

    @contextmanager
    def git_lock(self, repository_id: str):
        with GitSerialization(self._locks, repository_id):
            yield

    def create(
        self,
        *,
        run_id: str,
        repository_id: str,
        repository: str | Path,
        base_revision: str,
        workspace_id: str,
        path: str | Path,
    ) -> WorkspaceRecord:
        with self.git_lock(repository_id):
            contract = self._worktrees.create(
                run_id=run_id,
                repository_id=repository_id,
                repository=repository,
                base_revision=base_revision,
                workspace_id=workspace_id,
                path=path,
            )
            record = WorkspaceRecord(
                workspace_id=workspace_id,
                run_id=run_id,
                repository_id=repository_id,
                repository=str(Path(repository).expanduser().resolve()),
                base_revision=contract.base_revision,
                path=contract.path,
                owner_token=contract.owner_token,
                git_concurrency_key=repository_id,
            )
            self._write(record)
            return record

    def inspect(self, workspace_id: str) -> WorktreeInspection:
        record = self.load(workspace_id)
        contract = WorktreeContract(
            workspace_id=record.workspace_id,
            run_id=record.run_id,
            repository_id=record.repository_id,
            base_revision=record.base_revision,
            path=record.path,
            owner_token=record.owner_token,
            clean_at_creation=True,
            git_status_digest=stable_digest(""),
        )
        inspection = self._worktrees.inspect(contract)
        return inspection

    def attach_checkpoint(self, checkpoint: Checkpoint) -> WorkspaceRecord:
        record = self.load(checkpoint.workspace_identity)
        if record.run_id != checkpoint.run_id:
            raise WorktreeError("checkpoint run does not own workspace")
        updated = WorkspaceRecord(**{**asdict(record), "checkpoint_ref": checkpoint.checkpoint_id})
        self._write(updated)
        return self.load(record.workspace_id)

    def recover(self, workspace_id: str, expected_revision: str | None = None) -> WorkspaceRecovery:
        record = self.load(workspace_id)
        path = Path(record.path)
        if not path.is_dir():
            return WorkspaceRecovery(record, None, "MISSING", "workspace path is missing")
        try:
            inspection = self.inspect(workspace_id)
        except WorktreeError as exc:
            return WorkspaceRecovery(record, None, "INVALID", str(exc))
        if expected_revision and inspection.git_revision != expected_revision:
            return WorkspaceRecovery(record, inspection, "DIVERGED", "workspace revision differs from expected revision")
        if not inspection.clean:
            return WorkspaceRecovery(record, inspection, "DIRTY", "workspace contains uncommitted changes")
        return WorkspaceRecovery(record, inspection, "READY", "workspace can be safely reconciled")

    def cleanup(self, workspace_id: str, *, discard: bool = False) -> WorkspaceRecord:
        record = self.load(workspace_id)
        with self.git_lock(record.repository_id):
            inspection = self.inspect(workspace_id)
            if not inspection.clean and not discard:
                raise WorktreeError("refusing to clean dirty workspace without discard=True")
            contract = WorktreeContract(
                workspace_id=record.workspace_id,
                run_id=record.run_id,
                repository_id=record.repository_id,
                base_revision=record.base_revision,
                path=record.path,
                owner_token=record.owner_token,
                clean_at_creation=True,
                git_status_digest=stable_digest(""),
            )
            self._worktrees.remove(repository=record.repository, contract=contract, owner_token=record.owner_token)
            updated = WorkspaceRecord(**{**asdict(record), "status": "REMOVED", "cleanup_state": "DISCARDED" if discard else "CLEANED"})
            self._write(updated)
            return self.load(workspace_id)

    @staticmethod
    def workspace_digest(record: WorkspaceRecord) -> str:
        return filesystem_digest(record.path)


__all__ = ["GitSerialization", "WorkspaceManager", "WorkspaceRecord", "WorkspaceRecovery"]
