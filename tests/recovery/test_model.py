from __future__ import annotations

import pytest

from vajra.domain import EngineeringRun, RunState
from vajra.recovery.contracts import (
    Failure,
    FailureCategory,
    RecoveryAction,
)
from vajra.recovery.model import (
    ChangeModelRecoveryHandler,
    ModelChangeRequest,
)
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore


def make_manager() -> RunManager:
    manager = RunManager(
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
    )

    run = EngineeringRun(
        run_id="run-1",
        objective="change model after model failure",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="default",
        policy_version="1",
        budget_id="budget-1",
    )

    manager.create_run(run)
    manager.transition("run-1", RunState.QUEUED)
    manager.transition("run-1", RunState.ORIENTING)
    manager.recover_run("run-1")

    return manager


def make_failure() -> Failure:
    return Failure(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.MODEL_FAILURE,
        message="model failed",
    )


def make_decision() -> RecoveryDecision:
    return RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.MODEL_FAILURE,
        action=RecoveryAction.CHANGE_MODEL,
        reason="change model after model failure",
    )


def test_change_model_delegates_selection_without_executing():
    manager = make_manager()
    calls = []

    def selector(failure, decision):
        calls.append((failure.failure_id, decision.action))
        return ModelChangeRequest(
            model_id="model-2",
            reason="use alternate model",
        )

    handler = ChangeModelRecoveryHandler(manager, selector)

    request = handler(make_failure(), make_decision())

    assert request.model_id == "model-2"
    assert request.reason == "use alternate model"
    assert calls == [("failure-1", RecoveryAction.CHANGE_MODEL)]


def test_change_model_requires_recovering_run():
    manager = make_manager()
    manager.transition("run-1", RunState.QUEUED)

    handler = ChangeModelRecoveryHandler(
        manager,
        lambda failure, decision: ModelChangeRequest(
            model_id="model-2",
            reason="alternate",
        ),
    )

    with pytest.raises(ValueError, match="Run is not recovering"):
        handler(make_failure(), make_decision())


def test_change_model_rejects_wrong_action():
    manager = make_manager()

    decision = RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.MODEL_FAILURE,
        action=RecoveryAction.RETRY,
        reason="retry",
    )

    handler = ChangeModelRecoveryHandler(
        manager,
        lambda failure, decision: ModelChangeRequest(
            model_id="model-2",
            reason="alternate",
        ),
    )

    with pytest.raises(ValueError, match="requires a CHANGE_MODEL decision"):
        handler(make_failure(), decision)


def test_change_model_rejects_mismatched_failure_identity():
    manager = make_manager()

    failure = Failure(
        failure_id="different-failure",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.MODEL_FAILURE,
        message="model failed",
    )

    handler = ChangeModelRecoveryHandler(
        manager,
        lambda failure, decision: ModelChangeRequest(
            model_id="model-2",
            reason="alternate",
        ),
    )

    with pytest.raises(ValueError, match="does not match failure"):
        handler(failure, make_decision())


def test_change_model_rejects_empty_model_id():
    manager = make_manager()

    handler = ChangeModelRecoveryHandler(
        manager,
        lambda failure, decision: ModelChangeRequest(
            model_id="",
            reason="alternate",
        ),
    )

    with pytest.raises(ValueError, match="model_id must not be empty"):
        handler(make_failure(), make_decision())


def test_change_model_rejects_empty_reason():
    manager = make_manager()

    handler = ChangeModelRecoveryHandler(
        manager,
        lambda failure, decision: ModelChangeRequest(
            model_id="model-2",
            reason="",
        ),
    )

    with pytest.raises(ValueError, match="model reason must not be empty"):
        handler(make_failure(), make_decision())
