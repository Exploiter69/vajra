import pytest

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
        reason="Implement requested change",
    )


def test_intent_is_frozen_and_contains_proposed_operation():
    intent = make_intent()

    assert intent.operation == "write_file"
    assert intent.parameters["path"] == "src/example.py"
    assert intent.requested_capabilities == ("workspace.write",)

    with pytest.raises(AttributeError):
        intent.operation = "delete_file"


@pytest.mark.parametrize(
    "decision",
    [
        PolicyDecisionType.ALLOW,
        PolicyDecisionType.DENY,
        PolicyDecisionType.HUMAN_REQUIRED,
    ],
)
def test_non_modify_decisions_do_not_require_modified_parameters(decision):
    result = PolicyDecision(
        intent_id="intent-1",
        decision=decision,
        policy_id="engineering-safe",
        policy_version="1",
        reason="Policy evaluation",
    )

    assert result.decision is decision
    assert result.modified_parameters is None


def test_modify_requires_modified_parameters():
    result = PolicyDecision(
        intent_id="intent-1",
        decision=PolicyDecisionType.MODIFY,
        policy_id="engineering-safe",
        policy_version="1",
        reason="Restrict operation to workspace",
        modified_parameters={"path": "workspace/src/example.py"},
    )

    assert result.modified_parameters == {
        "path": "workspace/src/example.py"
    }


def test_modify_without_parameters_is_rejected():
    with pytest.raises(ValueError, match="modified_parameters"):
        PolicyDecision(
            intent_id="intent-1",
            decision=PolicyDecisionType.MODIFY,
            policy_id="engineering-safe",
            policy_version="1",
            reason="Must modify request",
        )


def test_non_modify_with_modified_parameters_is_rejected():
    with pytest.raises(ValueError, match="only valid"):
        PolicyDecision(
            intent_id="intent-1",
            decision=PolicyDecisionType.ALLOW,
            policy_id="engineering-safe",
            policy_version="1",
            reason="Allowed",
            modified_parameters={"path": "src/example.py"},
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "intent_id",
        "run_id",
        "step_id",
        "attempt_id",
        "operation",
    ],
)
def test_intent_requires_identity_fields(field_name):
    values = {
        "intent_id": "intent-1",
        "run_id": "run-1",
        "step_id": "step-1",
        "attempt_id": "attempt-1",
        "operation": "write_file",
    }
    values[field_name] = ""

    with pytest.raises(ValueError, match="must not be empty"):
        Intent(**values)
