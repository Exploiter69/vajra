from pathlib import Path
import subprocess

import pytest

from vajra.control import GitSerialization, WorkspaceManager, WorkspaceRecord, WorktreeError
from vajra.domain import Checkpoint, EvidenceRef


def git(path: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=path, capture_output=True, text=True, check=True)
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


def test_workspace_lifecycle_and_recovery(repository: Path, tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "state")
    revision = git(repository, "rev-parse", "HEAD")
    record = manager.create(run_id="run-1", repository_id="repo-1", repository=repository,
                            base_revision=revision, workspace_id="ws-1", path=tmp_path / "ws-1")
    assert record.status == "OWNED"
    recovery = manager.recover("ws-1", expected_revision=revision)
    assert recovery.disposition == "READY"
    assert manager.workspace_digest(record)

    checkpoint = Checkpoint(
        checkpoint_id="cp-1", run_id="run-1", step_id="step-1", event_position=1,
        git_revision=revision, workspace_identity="ws-1", policy_version="p1",
        state_digest="state", evidence_refs=[EvidenceRef("e1", "test", "loc")],
    )
    updated = manager.attach_checkpoint(checkpoint)
    assert updated.checkpoint_ref == "cp-1"

    with manager.use("ws-1", run_id="run-1", owner_token=record.owner_token) as path:
        assert path == Path(record.path)
        assert manager.load("ws-1").status == "IN_USE"
    assert manager.load("ws-1").status == "OWNED"

    released = manager.release("ws-1", run_id="run-1", owner_token=record.owner_token)
    assert released.status == "RELEASED"
    with pytest.raises(WorktreeError, match="released"):
        with manager.use("ws-1", run_id="run-1", owner_token=record.owner_token):
            pass

    cleaned = manager.cleanup("ws-1")
    assert cleaned.status == "REMOVED"
    assert not Path(record.path).exists()


def test_dirty_workspace_requires_explicit_discard(repository: Path, tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "state")
    revision = git(repository, "rev-parse", "HEAD")
    record = manager.create(run_id="run-1", repository_id="repo-1", repository=repository,
                            base_revision=revision, workspace_id="ws-1", path=tmp_path / "ws-1")
    Path(record.path, "dirty.txt").write_text("do not discard", encoding="utf-8")
    assert manager.recover("ws-1").disposition == "DIRTY"
    with pytest.raises(WorktreeError, match="dirty workspace"):
        manager.cleanup("ws-1")
    manager.cleanup("ws-1", discard=True)


def test_wrong_expected_revision_is_not_ready(repository: Path, tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "state")
    revision = git(repository, "rev-parse", "HEAD")
    record = manager.create(run_id="run-1", repository_id="repo-1", repository=repository,
                            base_revision=revision, workspace_id="ws-1", path=tmp_path / "ws-1")
    result = manager.recover("ws-1", expected_revision="0" * 40)
    assert result.disposition == "DIVERGED"
    manager.cleanup("ws-1")


def test_record_digest_rejects_tampering() -> None:
    fields = dict(workspace_id="ws", run_id="run", repository_id="repo", repository="/repo",
                  base_revision="abc", path="/ws", owner_token="token", status="ACTIVE",
                  cleanup_state="RETAINED", checkpoint_ref=None, git_concurrency_key="repo")
    good = WorkspaceRecord(record_digest="", **fields)
    import dataclasses
    payload = dataclasses.asdict(good)
    payload["record_digest"] = "bad"
    with pytest.raises(ValueError, match="digest"):
        WorkspaceRecord(**payload)


def test_git_serialization_rejects_contended_lock(tmp_path: Path) -> None:
    first = GitSerialization(tmp_path / "locks", "repo", timeout_seconds=0)
    with first:
        second = GitSerialization(tmp_path / "locks", "repo", timeout_seconds=0)
        with pytest.raises(TimeoutError, match="serialization lock timeout"):
            with second:
                pass
