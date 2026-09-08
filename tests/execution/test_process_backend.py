from pathlib import Path

from vajra.execution import ExecutionRequest, ExecutionStatus
from vajra.execution.contracts import Intent
from vajra.execution.process_backend import WorkspaceProcessBackend
from vajra.policy.contracts import PolicyDecision, PolicyDecisionType


def make_request(
    workspace: Path,
    command,
    operation: str = "run_tests",
) -> ExecutionRequest:
    intent = Intent(
        intent_id="intent-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation=operation,
        parameters={
            "workspace": str(workspace),
            "command": command,
        },
        requested_capabilities=("execution.test",),
        reason="test",
    )

    decision = PolicyDecision(
        intent_id="intent-1",
        decision=PolicyDecisionType.ALLOW,
        policy_id="test-policy",
        policy_version="1",
        reason="allowed",
    )

    return ExecutionRequest(
        intent=intent,
        policy_decision=decision,
    )


def test_successful_process_executes_in_workspace(tmp_path: Path) -> None:
    backend = WorkspaceProcessBackend()

    result = backend.execute(
        make_request(
            tmp_path,
            ["python", "-c", "print('hello')"],
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert result.output["return_code"] == 0
    assert result.output["stdout"] == "hello\n"
    assert result.output["workspace"] == str(tmp_path.resolve())


def test_failed_process_returns_rejected_result(tmp_path: Path) -> None:
    backend = WorkspaceProcessBackend()

    result = backend.execute(
        make_request(
            tmp_path,
            ["python", "-c", "import sys; print('bad'); sys.exit(3)"],
        )
    )

    assert result.status is ExecutionStatus.REJECTED
    assert result.output["return_code"] == 3
    assert result.output["stdout"] == "bad\n"
    assert "return code 3" in result.errors[0]


def test_empty_command_is_rejected(tmp_path: Path) -> None:
    backend = WorkspaceProcessBackend()

    result = backend.execute(make_request(tmp_path, []))

    assert result.status is ExecutionStatus.REJECTED
    assert "non-empty argument sequence" in result.errors[0]


def test_non_string_argument_is_rejected(tmp_path: Path) -> None:
    backend = WorkspaceProcessBackend()

    result = backend.execute(
        make_request(tmp_path, ["python", 123]),
    )

    assert result.status is ExecutionStatus.REJECTED
    assert "non-empty strings" in result.errors[0]


def test_missing_workspace_is_rejected(tmp_path: Path) -> None:
    backend = WorkspaceProcessBackend()

    result = backend.execute(
        make_request(tmp_path / "missing", ["python", "--version"]),
    )

    assert result.status is ExecutionStatus.REJECTED
    assert "workspace does not exist" in result.errors[0]


def test_shell_syntax_is_not_interpreted(tmp_path: Path) -> None:
    backend = WorkspaceProcessBackend()

    result = backend.execute(
        make_request(
            tmp_path,
            ["python", "-c", "print('a && echo injected')"],
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert result.output["stdout"] == "a && echo injected\n"


def test_working_directory_is_workspace(tmp_path: Path) -> None:
    backend = WorkspaceProcessBackend()

    result = backend.execute(
        make_request(
            tmp_path,
            ["python", "-c", "import os; print(os.getcwd())"],
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert result.output["stdout"].strip() == str(tmp_path.resolve())
