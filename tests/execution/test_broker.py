from vajra.execution import (
    ExecutionBroker,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from vajra.policy import Intent, PolicyDecision, PolicyDecisionType


class RecordingBackend:
    def __init__(self) -> None:
        self.requests: list[ExecutionRequest] = []

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.requests.append(request)
        return ExecutionResult(
            status=ExecutionStatus.ACCEPTED,
            operation=request.intent.operation,
        )


def make_intent(
    *,
    operation: str = "write_file",
    parameters: dict | None = None,
) -> Intent:
    return Intent(
        intent_id="intent-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation=operation,
        parameters=parameters or {"path": "src/example.py"},
        requested_capabilities=("workspace.write",),
    )


def make_request(
    decision: PolicyDecisionType,
    *,
    modified_parameters: dict | None = None,
) -> ExecutionRequest:
    intent = make_intent()

    policy_decision = PolicyDecision(
        intent_id=intent.intent_id,
        decision=decision,
        policy_id="engineering-v0",
        policy_version="1",
        reason="test",
        modified_parameters=modified_parameters,
    )

    return ExecutionRequest(
        intent=intent,
        policy_decision=policy_decision,
    )


def test_allow_is_dispatched_to_backend():
    backend = RecordingBackend()
    broker = ExecutionBroker(backend)

    result = broker.execute(make_request(PolicyDecisionType.ALLOW))

    assert result.status is ExecutionStatus.ACCEPTED
    assert len(backend.requests) == 1
    assert backend.requests[0].intent.parameters == {
        "path": "src/example.py"
    }


def test_modify_dispatches_modified_parameters():
    backend = RecordingBackend()
    broker = ExecutionBroker(backend)

    result = broker.execute(
        make_request(
            PolicyDecisionType.MODIFY,
            modified_parameters={
                "path": "workspace/src/example.py"
            },
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert len(backend.requests) == 1
    assert backend.requests[0].intent.parameters == {
        "path": "workspace/src/example.py"
    }


def test_deny_never_reaches_backend():
    backend = RecordingBackend()
    broker = ExecutionBroker(backend)

    result = broker.execute(make_request(PolicyDecisionType.DENY))

    assert result.status is ExecutionStatus.REJECTED
    assert backend.requests == []
    assert "DENY" in result.errors[0]


def test_human_required_never_reaches_backend():
    backend = RecordingBackend()
    broker = ExecutionBroker(backend)

    result = broker.execute(
        make_request(PolicyDecisionType.HUMAN_REQUIRED)
    )

    assert result.status is ExecutionStatus.REJECTED
    assert backend.requests == []
    assert "HUMAN_REQUIRED" in result.errors[0]


def test_backend_is_only_called_after_authorization():
    called = False

    class Backend:
        def execute(self, request):
            nonlocal called
            called = True
            return ExecutionResult(
                status=ExecutionStatus.ACCEPTED,
                operation=request.intent.operation,
            )

    broker = ExecutionBroker(Backend())

    result = broker.execute(
        make_request(PolicyDecisionType.DENY)
    )

    assert result.status is ExecutionStatus.REJECTED
    assert called is False


def test_broker_preserves_run_step_and_attempt_identity():
    backend = RecordingBackend()
    broker = ExecutionBroker(backend)

    broker.execute(make_request(PolicyDecisionType.ALLOW))

    request = backend.requests[0]

    assert request.intent.run_id == "run-1"
    assert request.intent.step_id == "step-1"
    assert request.intent.attempt_id == "attempt-1"


def test_modify_preserves_intent_identity():
    backend = RecordingBackend()
    broker = ExecutionBroker(backend)

    broker.execute(
        make_request(
            PolicyDecisionType.MODIFY,
            modified_parameters={"path": "workspace/example.py"},
        )
    )

    request = backend.requests[0]

    assert request.intent.intent_id == "intent-1"
    assert request.intent.run_id == "run-1"
    assert request.intent.step_id == "step-1"
    assert request.intent.attempt_id == "attempt-1"
