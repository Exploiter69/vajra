from pathlib import Path
import subprocess

import pytest

from vajra.control import WorktreeError, WorktreeManager


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()

    git(repo, "init", "-q")
    git(repo, "config", "user.email", "vajra@test.invalid")
    git(repo, "config", "user.name", "VAJRA Test")

    (repo / "README").write_text("initial\n", encoding="utf-8")
    git(repo, "add", "README")
    git(repo, "commit", "-q", "-m", "initial")
    return repo


def test_create_produces_clean_detached_worktree(repository: Path, tmp_path: Path) -> None:
    revision = git(repository, "rev-parse", "HEAD")
    path = tmp_path / "worktree"

    manager = WorktreeManager(tmp_path / "metadata")
    contract = manager.create(
        run_id="run-1",
        repository_id="repo-1",
        repository=repository,
        base_revision=revision,
        workspace_id="ws-1",
        path=path,
    )

    assert Path(contract.path) == path.resolve()
    assert contract.base_revision == revision
    assert contract.clean_at_creation is True
    assert git(path, "status", "--porcelain=v1") == ""
    assert git(path, "rev-parse", "HEAD") == revision


def test_create_rejects_existing_path(repository: Path, tmp_path: Path) -> None:
    path = tmp_path / "existing"
    path.mkdir()

    manager = WorktreeManager()

    with pytest.raises(WorktreeError, match="already exists"):
        manager.create(
            run_id="run-1",
            repository_id="repo-1",
            repository=repository,
            base_revision=git(repository, "rev-parse", "HEAD"),
            workspace_id="ws-1",
            path=path,
        )


def test_inspect_detects_workspace_change(repository: Path, tmp_path: Path) -> None:
    manager = WorktreeManager()
    contract = manager.create(
        run_id="run-1",
        repository_id="repo-1",
        repository=repository,
        base_revision=git(repository, "rev-parse", "HEAD"),
        workspace_id="ws-1",
        path=tmp_path / "worktree",
    )

    (Path(contract.path) / "change.txt").write_text("changed\n", encoding="utf-8")
    inspection = manager.inspect(contract)

    assert inspection.clean is False
    assert inspection.status_digest != contract.git_status_digest


def test_remove_requires_owner(repository: Path, tmp_path: Path) -> None:
    manager = WorktreeManager()
    contract = manager.create(
        run_id="run-1",
        repository_id="repo-1",
        repository=repository,
        base_revision=git(repository, "rev-parse", "HEAD"),
        workspace_id="ws-1",
        path=tmp_path / "worktree",
    )

    with pytest.raises(WorktreeError, match="ownership"):
        manager.remove(
            repository=repository,
            contract=contract,
            owner_token="wrong",
        )

    manager.remove(
        repository=repository,
        contract=contract,
        owner_token=contract.owner_token,
    )

    assert not Path(contract.path).exists()
