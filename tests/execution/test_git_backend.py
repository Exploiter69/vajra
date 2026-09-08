import subprocess
from pathlib import Path

from vajra.execution import ExecutionRequest, ExecutionStatus
from vajra.execution.contracts import Intent
from vajra.execution.git_backend import WorkspaceGitBackend
from vajra.policy.contracts import PolicyDecision, PolicyDecisionType


def make_request(
    workspace: Path,
    operation: str,
) -> ExecutionRequest:
    intent = Intent(
        intent_id="intent-git-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation=operation,
        parameters={"workspace": str(workspace)},
        requested_capabilities=("git.read",),
        reason="test",
    )

    decision = PolicyDecision(
        intent_id="intent-git-1",
        decision=PolicyDecisionType.ALLOW,
        policy_id="test-policy",
        policy_version="1",
        reason="allowed",
    )

    return ExecutionRequest(
        intent=intent,
        policy_decision=decision,
    )


def initialize_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "vajra@test.local"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "VAJRA Test"],
        cwd=path,
        check=True,
    )
    (path / "README.md").write_text("VAJRA\n")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )


def test_git_status(tmp_path: Path) -> None:
    initialize_repo(tmp_path)
    (tmp_path / "README.md").write_text("changed\n")

    result = WorkspaceGitBackend().execute(
        make_request(tmp_path, "git_status")
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert "README.md" in result.output["stdout"]


def test_git_diff(tmp_path: Path) -> None:
    initialize_repo(tmp_path)
    (tmp_path / "README.md").write_text("changed\n")

    result = WorkspaceGitBackend().execute(
        make_request(tmp_path, "git_diff")
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert "-VAJRA" in result.output["stdout"]
    assert "+changed" in result.output["stdout"]


def test_git_log(tmp_path: Path) -> None:
    initialize_repo(tmp_path)

    result = WorkspaceGitBackend().execute(
        make_request(tmp_path, "git_log")
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert "initial" in result.output["stdout"]


def test_git_revision(tmp_path: Path) -> None:
    initialize_repo(tmp_path)

    result = WorkspaceGitBackend().execute(
        make_request(tmp_path, "git_revision")
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert len(result.output["stdout"].strip()) == 40


def test_unsupported_git_operation_is_rejected(tmp_path: Path) -> None:
    initialize_repo(tmp_path)

    result = WorkspaceGitBackend().execute(
        make_request(tmp_path, "git_push")
    )

    assert result.status is ExecutionStatus.REJECTED
    assert "Unsupported Git operation" in result.errors[0]


def test_missing_workspace_is_rejected(tmp_path: Path) -> None:
    result = WorkspaceGitBackend().execute(
        make_request(tmp_path / "missing", "git_status")
    )

    assert result.status is ExecutionStatus.REJECTED
    assert "workspace does not exist" in result.errors[0]


def test_non_git_workspace_returns_failure(tmp_path: Path) -> None:
    result = WorkspaceGitBackend().execute(
        make_request(tmp_path, "git_revision")
    )

    assert result.status is ExecutionStatus.REJECTED
    assert result.output["return_code"] != 0
