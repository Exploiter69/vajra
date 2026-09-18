from __future__ import annotations

import hashlib
import json
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path

from vajra.control.contracts import WorktreeContract
from vajra.hardening import SecurityPolicy


class WorktreeError(RuntimeError):
    """Raised when a VAJRA worktree invariant cannot be established."""


@dataclass(frozen=True)
class WorktreeInspection:
    workspace_id: str
    path: str
    base_revision: str
    git_revision: str
    clean: bool
    status_digest: str


class WorktreeManager:
    """
    Owns the lifecycle boundary for a VAJRA Engineering Run worktree.

    Git itself remains the authority for repository state. This manager only
    creates and validates isolated worktrees; it does not execute engineering
    operations inside them.
    """

    def __init__(self, metadata_root: str | Path | None = None, *, security_policy: SecurityPolicy | None = None) -> None:
        self._security = security_policy or SecurityPolicy()
        self._metadata_root = (
            Path(metadata_root).expanduser().resolve()
            if metadata_root is not None
            else None
        )

    @staticmethod
    def _git(repository: Path, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=repository,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise WorktreeError(f"Git execution failed: {exc}") from exc

        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise WorktreeError(
                f"git {' '.join(args)} failed: {detail}"
            )

        return result.stdout.strip()

    @classmethod
    def _revision(cls, repository: Path, revision: str) -> str:
        return cls._git(repository, "rev-parse", "--verify", f"{revision}^{{commit}}")

    @classmethod
    def _status(cls, path: Path) -> str:
        return cls._git(path, "status", "--porcelain=v1")

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def create(
        self,
        *,
        run_id: str,
        repository_id: str,
        repository: str | Path,
        base_revision: str,
        workspace_id: str,
        path: str | Path,
    ) -> WorktreeContract:
        if not run_id:
            raise ValueError("run_id must not be empty")
        if not repository_id:
            raise ValueError("repository_id must not be empty")
        if not workspace_id:
            raise ValueError("workspace_id must not be empty")

        repository_path = Path(repository).expanduser().resolve()
        workspace_path = Path(path).expanduser().resolve()

        if not repository_path.is_dir():
            raise WorktreeError(f"repository does not exist: {repository_path}")
        try:
            self._security.assert_repository_safe(repository_path)
        except Exception as exc:
            raise WorktreeError(str(exc)) from exc

        if workspace_path.exists():
            raise WorktreeError(
                f"worktree path already exists: {workspace_path}"
            )

        resolved_revision = self._revision(repository_path, base_revision)

        workspace_path.parent.mkdir(parents=True, exist_ok=True)

        self._git(
            repository_path,
            "worktree",
            "add",
            "--detach",
            str(workspace_path),
            resolved_revision,
        )

        metadata_dir: Path | None = None

        try:
            status = self._status(workspace_path)
            if status:
                raise WorktreeError(
                    "new worktree is not clean at creation"
                )

            owner_token = secrets.token_hex(32)
            status_digest = self._digest(status)

            contract = WorktreeContract(
                workspace_id=workspace_id,
                run_id=run_id,
                repository_id=repository_id,
                base_revision=resolved_revision,
                path=str(workspace_path),
                owner_token=owner_token,
                clean_at_creation=True,
                git_status_digest=status_digest,
            )

            if self._metadata_root is not None:
                metadata_dir = self._metadata_root / workspace_id
                metadata_dir.mkdir(parents=True, exist_ok=True)
                metadata = {
                    "workspace_id": workspace_id,
                    "run_id": run_id,
                    "repository_id": repository_id,
                    "base_revision": resolved_revision,
                    "path": str(workspace_path),
                    "owner_token": owner_token,
                    "git_status_digest": status_digest,
                }
                (metadata_dir / "contract.json").write_text(
                    json.dumps(metadata, sort_keys=True, indent=2),
                    encoding="utf-8",
                )

            return contract
        except Exception:
            try:
                self._git(
                    repository_path,
                    "worktree",
                    "remove",
                    "--force",
                    str(workspace_path),
                )
            finally:
                if metadata_dir is not None:
                    metadata_file = metadata_dir / "contract.json"
                    try:
                        metadata_file.unlink(missing_ok=True)
                        metadata_dir.rmdir()
                    except OSError:
                        pass
            raise

    def inspect(self, contract: WorktreeContract) -> WorktreeInspection:
        path = Path(contract.path).resolve()

        if not path.is_dir():
            raise WorktreeError(f"worktree does not exist: {path}")

        revision = self._git(path, "rev-parse", "HEAD")
        status = self._status(path)

        return WorktreeInspection(
            workspace_id=contract.workspace_id,
            path=str(path),
            base_revision=contract.base_revision,
            git_revision=revision,
            clean=not bool(status),
            status_digest=self._digest(status),
        )

    def remove(
        self,
        *,
        repository: str | Path,
        contract: WorktreeContract,
        owner_token: str,
    ) -> None:
        if owner_token != contract.owner_token:
            raise WorktreeError("worktree ownership token mismatch")

        repository_path = Path(repository).expanduser().resolve()
        workspace_path = Path(contract.path).expanduser().resolve()

        if not workspace_path.exists():
            return

        self._git(
            repository_path,
            "worktree",
            "remove",
            "--force",
            str(workspace_path),
        )

        if workspace_path.exists():
            raise WorktreeError(
                f"Git reported successful removal but path remains: {workspace_path}"
            )

        if self._metadata_root is not None:
            metadata_dir = self._metadata_root / contract.workspace_id
            metadata_file = metadata_dir / "contract.json"
            try:
                metadata_file.unlink(missing_ok=True)
                metadata_dir.rmdir()
            except OSError:
                pass
