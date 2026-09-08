import pytest

from vajra.execution import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from vajra.policy import Intent, PolicyDecision, PolicyDecisionType


def make_intent() -> Intent:
    return Intent(
        intent_id="intent-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="write_file",
        parameters={"path": "src/example.py"},
        requested_capabilities=("workspace.write",),
    )


def make_decision(
    decision: PolicyDecisionType = PolicyDecisionType.ALLOW,
    *,
    intent_id: str = "intent-1",
) -> PolicyDecision:
    return PolicyDecision(
        intent_id=intent_id,
        decision=decision,
        policy_id="engineering-v0",
        policy_version="1",
        reason="Policy decision",
        modified_parameters=(
            {"path": "workspace/src/example.py"}
            if decision is PolicyDecisionType.MODIFY
            else None
        ),
    )


def test_execution_request_preserves_exact_intent_and_decision():
    intent = make_intent()
    decision = make_decision()

    request = ExecutionRequest(
        intent=intent,
        policy_decision=decision,
    )

    assert request.intent is intent
    assert request.policy_decision is decision


@pytest.mark.parametrize(
    "decision",
    [
        PolicyDecisionType.ALLOW,
        PolicyDecisionType.DENY,
        PolicyDecisionType.MODIFY,
        PolicyDecisionType.HUMAN_REQUIRED,
    ],
)
def test_execution_request_accepts_all_policy_decision_types(decision):
    request = ExecutionRequest(
        intent=make_intent(),
        policy_decision=make_decision(decision),
    )

    assert request.policy_decision.decision is decision


def test_execution_request_rejects_decision_for_different_intent():
    with pytest.raises(ValueError, match="does not match"):
        ExecutionRequest(
            intent=make_intent(),
            policy_decision=make_decision(intent_id="different-intent"),
        )


def test_execution_result_preserves_backend_report():
    result = ExecutionResult(
        status=ExecutionStatus.ACCEPTED,
        operation="write_file",
        output={"path": "src/example.py"},
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert result.operation == "write_file"
    assert result.output == {"path": "src/example.py"}


def test_execution_result_can_report_errors():
    result = ExecutionResult(
        status=ExecutionStatus.REJECTED,
        operation="write_file",
        errors=("backend rejected operation",),
    )

    assert result.status is ExecutionStatus.REJECTED
    assert result.errors == ("backend rejected operation",)


def test_execution_result_requires_operation():
    with pytest.raises(ValueError, match="must not be empty"):
        ExecutionResult(
            status=ExecutionStatus.REJECTED,
            operation="",
        )


def test_execution_request_is_frozen():
    request = ExecutionRequest(
        intent=make_intent(),
        policy_decision=make_decision(),
    )

    with pytest.raises(AttributeError):
        request.intent = make_intent()
