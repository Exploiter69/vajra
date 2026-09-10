from pathlib import Path
import subprocess

from vajra.control.reality import filesystem_digest
from vajra.control import (
    RealityObserver,
    ReconciliationDisposition,
    WorktreeManager,
)
from vajra.domain import EngineeringRun


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "vajra@test.invalid")
    git(repo, "config", "user.name", "VAJRA Test")
    (repo / "README").write_text("initial\n", encoding="utf-8")
    git(repo, "add", "README")
    git(repo, "commit", "-q", "-m", "initial")
    return repo


def make_run(revision: str) -> EngineeringRun:
    return EngineeringRun(
        run_id="run-1",
        objective="test objective",
        repository_id="repo-1",
        base_revision=revision,
        acceptance_criteria=("criteria-1",),
        policy_id="policy-1",
        policy_version="1",
        budget_id="budget-1",
    )


def test_reality_observer_reports_consistent_state(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    revision = git(repo, "rev-parse", "HEAD")

    contract = WorktreeManager().create(
        run_id="run-1",
        repository_id="repo-1",
        repository=repo,
        base_revision=revision,
        workspace_id="ws-1",
        path=tmp_path / "worktree",
    )

    report = RealityObserver().observe(
        run=make_run(revision),
        worktree=contract,
        git_revision=revision,
        git_status="",
        active_lease_state="NONE",
        verification_state="NOT_RUN",
        budget_state="AVAILABLE",
    )

    assert report.divergence_class.value == "NONE"
    assert report.disposition is ReconciliationDisposition.CONSISTENT
    assert report.freshness == "FRESH"
    assert len(report.durable_state_digest) == 64
    assert len(report.filesystem_digest) == 64


def test_reality_observer_detects_budget_exhaustion(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    revision = git(repo, "rev-parse", "HEAD")

    contract = WorktreeManager().create(
        run_id="run-1",
        repository_id="repo-1",
        repository=repo,
        base_revision=revision,
        workspace_id="ws-1",
        path=tmp_path / "worktree",
    )

    report = RealityObserver().observe(
        run=make_run(revision),
        worktree=contract,
        git_revision=revision,
        git_status="",
        active_lease_state="NONE",
        verification_state="NOT_RUN",
        budget_state="EXHAUSTED",
    )

    assert report.disposition is ReconciliationDisposition.ABORT


def test_filesystem_digest_tracks_file_content(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "file.txt"
    target.write_text("aaaa\n", encoding="utf-8")

    before = filesystem_digest(workspace)

    target.write_text("bbbb\n", encoding="utf-8")

    after = filesystem_digest(workspace)

    assert before != after


def test_filesystem_digest_tracks_symlink_target(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a\n", encoding="utf-8")
    (workspace / "b.txt").write_text("b\n", encoding="utf-8")
    link = workspace / "link"
    link.symlink_to("a.txt")

    before = filesystem_digest(workspace)

    link.unlink()
    link.symlink_to("b.txt")

    after = filesystem_digest(workspace)

    assert before != after


def test_reality_observer_uses_highest_priority_divergence(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    revision = git(repo, "rev-parse", "HEAD")

    contract = WorktreeManager().create(
        run_id="run-1",
        repository_id="repo-1",
        repository=repo,
        base_revision=revision,
        workspace_id="ws-1",
        path=tmp_path / "worktree",
    )

    report = RealityObserver().observe(
        run=make_run(revision),
        worktree=contract,
        git_revision="different-revision",
        git_status=" M README",
        active_lease_state="INVALID",
        verification_state="FAILED",
        budget_state="EXHAUSTED",
    )

    assert report.divergence_class.value == "BUDGET_DIVERGENCE"
    assert report.disposition is ReconciliationDisposition.ABORT
    assert len(report.observed_external_state["reasons"]) == 5
