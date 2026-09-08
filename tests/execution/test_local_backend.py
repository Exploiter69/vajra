import pytest

from vajra.execution import (
    ExecutionBroker,
    ExecutionRequest,
    ExecutionStatus,
)
from vajra.execution.contracts import Intent
from vajra.execution.local_backend import LocalExecutionBackend
from vajra.policy.contracts import (
    PolicyDecision,
    PolicyDecisionType,
)


def make_request(operation: str = "test_operation") -> ExecutionRequest:
    intent = Intent(
        intent_id="intent-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation=operation,
        parameters={"value": 42},
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


def test_registered_handler_executes() -> None:
    backend = LocalExecutionBackend(
        {"test_operation": lambda request: {"value": request.intent.parameters["value"]}}
    )

    result = backend.execute(make_request())

    assert result.status is ExecutionStatus.ACCEPTED
    assert result.operation == "test_operation"
    assert result.output == {"value": 42}


def test_unregistered_operation_is_rejected() -> None:
    backend = LocalExecutionBackend()

    result = backend.execute(make_request())

    assert result.status is ExecutionStatus.REJECTED
    assert "No execution handler" in result.errors[0]


def test_handler_failure_becomes_execution_result() -> None:
    def fail(request):
        raise RuntimeError("boom")

    backend = LocalExecutionBackend({"test_operation": fail})

    result = backend.execute(make_request())

    assert result.status is ExecutionStatus.REJECTED
    assert result.errors == ("Execution handler failed: boom",)


def test_duplicate_registration_is_rejected() -> None:
    backend = LocalExecutionBackend({"test_operation": lambda request: {}})

    with pytest.raises(ValueError, match="already registered"):
        backend.register("test_operation", lambda request: {})


def test_broker_dispatches_authorized_request_to_local_backend() -> None:
    seen = {}

    def handler(request):
        seen["operation"] = request.intent.operation
        seen["parameters"] = request.intent.parameters
        return {"executed": True}

    backend = LocalExecutionBackend({"test_operation": handler})
    broker = ExecutionBroker(backend)

    result = broker.execute(make_request())

    assert result.status is ExecutionStatus.ACCEPTED
    assert result.output == {"executed": True}
    assert seen == {
        "operation": "test_operation",
        "parameters": {"value": 42},
    }


def test_broker_blocks_unauthorized_request_before_local_backend() -> None:
    calls = []

    def handler(request):
        calls.append(request)
        return {"executed": True}

    backend = LocalExecutionBackend({"test_operation": handler})
    broker = ExecutionBroker(backend)

    request = make_request()
    denied = request.policy_decision.__class__(
        intent_id="intent-1",
        decision=PolicyDecisionType.DENY,
        policy_id="test-policy",
        policy_version="1",
        reason="denied",
    )

    denied_request = ExecutionRequest(
        intent=request.intent,
        policy_decision=denied,
    )

    result = broker.execute(denied_request)

    assert result.status is ExecutionStatus.REJECTED
    assert calls == []
