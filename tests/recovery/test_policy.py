import pytest

from vajra.recovery import (
    Failure,
    FailureCategory,
    RecoveryAction,
)
from vajra.recovery.policy import RecoveryPolicy


@pytest.mark.parametrize(
    ("category", "expected_action"),
    [
        (FailureCategory.MODEL_FAILURE, RecoveryAction.CHANGE_MODEL),
        (FailureCategory.TOOL_FAILURE, RecoveryAction.RETRY),
        (FailureCategory.COMMAND_FAILURE, RecoveryAction.RETRY),
        (FailureCategory.TEST_FAILURE, RecoveryAction.NEW_STRATEGY),
        (FailureCategory.POLICY_DENIAL, RecoveryAction.REQUEST_HUMAN),
        (FailureCategory.RESOURCE_EXHAUSTION, RecoveryAction.ABORT),
        (FailureCategory.TIMEOUT, RecoveryAction.RETRY),
        (FailureCategory.WORKER_LOSS, RecoveryAction.CHANGE_WORKER),
        (FailureCategory.NETWORK_FAILURE, RecoveryAction.RETRY),
        (
            FailureCategory.STATE_DIVERGENCE,
            RecoveryAction.RESTORE_CHECKPOINT,
        ),
        (FailureCategory.SANDBOX_FAILURE, RecoveryAction.RETRY),
        (FailureCategory.NO_PROGRESS, RecoveryAction.REQUEST_HUMAN),
        (FailureCategory.UNKNOWN, RecoveryAction.REQUEST_HUMAN),
    ],
)
def test_v0_failure_categories_have_explicit_recovery_actions(
    category: FailureCategory,
    expected_action: RecoveryAction,
) -> None:
    failure = Failure(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=category,
        message="failure observed",
    )

    decision = RecoveryPolicy().decide(failure)

    assert decision.action is expected_action
    assert decision.category is category


def test_policy_preserves_failure_identity() -> None:
    failure = Failure(
        failure_id="failure-42",
        run_id="run-42",
        step_id="step-42",
        attempt_id="attempt-42",
        category=FailureCategory.WORKER_LOSS,
        message="worker disappeared",
    )

    decision = RecoveryPolicy().decide(failure)

    assert decision.failure_id == failure.failure_id
    assert decision.run_id == failure.run_id
    assert decision.step_id == failure.step_id
    assert decision.attempt_id == failure.attempt_id


def test_policy_is_deterministic() -> None:
    failure = Failure(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.TEST_FAILURE,
        message="tests failed",
    )

    policy = RecoveryPolicy()

    assert policy.decide(failure) == policy.decide(failure)


def test_unknown_failure_requires_human() -> None:
    failure = Failure(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.UNKNOWN,
        message="unclassified failure",
    )

    decision = RecoveryPolicy().decide(failure)

    assert decision.action is RecoveryAction.REQUEST_HUMAN


@pytest.mark.parametrize(
    "field_name",
    [
        "failure_id",
        "run_id",
        "step_id",
        "attempt_id",
        "reason",
    ],
)
def test_recovery_decision_requires_identity_and_reason(
    field_name: str,
) -> None:
    values = {
        "failure_id": "failure-1",
        "run_id": "run-1",
        "step_id": "step-1",
        "attempt_id": "attempt-1",
        "category": FailureCategory.COMMAND_FAILURE,
        "action": RecoveryAction.RETRY,
        "reason": "retry command",
    }
    values[field_name] = ""

    from vajra.recovery.policy import RecoveryDecision

    with pytest.raises(ValueError):
        RecoveryDecision(**values)


def test_policy_reason_identifies_mapping() -> None:
    failure = Failure(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.NO_PROGRESS,
        message="same failure repeated",
    )

    decision = RecoveryPolicy().decide(failure)

    assert "NO_PROGRESS" in decision.reason
    assert "REQUEST_HUMAN" in decision.reason
