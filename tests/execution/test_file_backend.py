from pathlib import Path

from vajra.execution import ExecutionRequest, ExecutionStatus
from vajra.execution.contracts import Intent
from vajra.execution.file_backend import WorkspaceFileBackend
from vajra.policy.contracts import PolicyDecision, PolicyDecisionType


def make_request(
    operation: str,
    workspace: Path,
    **parameters,
) -> ExecutionRequest:
    intent = Intent(
        intent_id="intent-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation=operation,
        parameters={
            "workspace": str(workspace),
            **parameters,
        },
        requested_capabilities=("workspace.read", "workspace.write"),
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


def test_write_and_read_file(tmp_path: Path) -> None:
    backend = WorkspaceFileBackend()

    write_result = backend.execute(
        make_request(
            "write_file",
            tmp_path,
            path="src/example.py",
            content="print('hello')\n",
        )
    )

    assert write_result.status is ExecutionStatus.ACCEPTED
    assert (tmp_path / "src/example.py").read_text() == "print('hello')\n"

    read_result = backend.execute(
        make_request(
            "read_file",
            tmp_path,
            path="src/example.py",
        )
    )

    assert read_result.status is ExecutionStatus.ACCEPTED
    assert read_result.output["content"] == "print('hello')\n"


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    backend = WorkspaceFileBackend()

    result = backend.execute(
        make_request(
            "read_file",
            tmp_path,
            path="../outside.txt",
        )
    )

    assert result.status is ExecutionStatus.REJECTED
    assert "escapes" in result.errors[0]


def test_absolute_path_outside_workspace_is_rejected(
    tmp_path: Path,
) -> None:
    backend = WorkspaceFileBackend()

    outside = tmp_path.parent / "outside.txt"

    result = backend.execute(
        make_request(
            "read_file",
            tmp_path,
            path=str(outside),
        )
    )

    assert result.status is ExecutionStatus.REJECTED
    assert "escapes" in result.errors[0]


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    backend = WorkspaceFileBackend()

    result = backend.execute(
        make_request(
            "read_file",
            tmp_path,
            path="missing.txt",
        )
    )

    assert result.status is ExecutionStatus.REJECTED
    assert "does not exist" in result.errors[0]


def test_non_string_content_is_rejected(tmp_path: Path) -> None:
    backend = WorkspaceFileBackend()

    result = backend.execute(
        make_request(
            "write_file",
            tmp_path,
            path="example.txt",
            content=123,
        )
    )

    assert result.status is ExecutionStatus.REJECTED
    assert "content must be a string" in result.errors[0]


def test_unsupported_operation_is_rejected(tmp_path: Path) -> None:
    backend = WorkspaceFileBackend()

    result = backend.execute(
        make_request(
            "delete_file",
            tmp_path,
            path="example.txt",
        )
    )

    assert result.status is ExecutionStatus.REJECTED
    assert "Unsupported file operation" in result.errors[0]
