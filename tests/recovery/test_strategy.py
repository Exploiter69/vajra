from __future__ import annotations

import pytest

from vajra.domain import EngineeringRun, RunState
from vajra.recovery.contracts import (
    Failure,
    FailureCategory,
    RecoveryAction,
)
from vajra.recovery.policy import RecoveryDecision
from vajra.recovery.strategy import (
    NewStrategyRecoveryHandler,
    StrategyChangeRequest,
)
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
        objective="change strategy after test failure",
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
        category=FailureCategory.TEST_FAILURE,
        message="tests failed",
    )


def make_decision() -> RecoveryDecision:
    return RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.TEST_FAILURE,
        action=RecoveryAction.NEW_STRATEGY,
        reason="change strategy after test failure",
    )


def test_new_strategy_delegates_selection_without_executing():
    manager = make_manager()
    calls = []

    def selector(failure, decision):
        calls.append((failure.failure_id, decision.action))
        return StrategyChangeRequest(
            strategy_id="strategy-2",
            reason="try a smaller implementation",
        )

    handler = NewStrategyRecoveryHandler(manager, selector)

    request = handler(make_failure(), make_decision())

    assert request.strategy_id == "strategy-2"
    assert request.reason == "try a smaller implementation"
    assert calls == [("failure-1", RecoveryAction.NEW_STRATEGY)]


def test_new_strategy_requires_recovering_run():
    manager = make_manager()
    manager.transition("run-1", RunState.QUEUED)

    handler = NewStrategyRecoveryHandler(
        manager,
        lambda failure, decision: StrategyChangeRequest(
            strategy_id="strategy-2",
            reason="alternate",
        ),
    )

    with pytest.raises(ValueError, match="Run is not recovering"):
        handler(make_failure(), make_decision())


def test_new_strategy_rejects_wrong_action():
    manager = make_manager()

    decision = RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.TEST_FAILURE,
        action=RecoveryAction.RETRY,
        reason="retry",
    )

    handler = NewStrategyRecoveryHandler(
        manager,
        lambda failure, decision: StrategyChangeRequest(
            strategy_id="strategy-2",
            reason="alternate",
        ),
    )

    with pytest.raises(ValueError, match="requires a NEW_STRATEGY decision"):
        handler(make_failure(), decision)


def test_new_strategy_rejects_mismatched_failure_identity():
    manager = make_manager()

    failure = Failure(
        failure_id="different-failure",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.TEST_FAILURE,
        message="tests failed",
    )

    handler = NewStrategyRecoveryHandler(
        manager,
        lambda failure, decision: StrategyChangeRequest(
            strategy_id="strategy-2",
            reason="alternate",
        ),
    )

    with pytest.raises(ValueError, match="does not match failure"):
        handler(failure, make_decision())


def test_new_strategy_rejects_empty_strategy():
    manager = make_manager()

    handler = NewStrategyRecoveryHandler(
        manager,
        lambda failure, decision: StrategyChangeRequest(
            strategy_id="",
            reason="alternate",
        ),
    )

    with pytest.raises(ValueError, match="strategy_id must not be empty"):
        handler(make_failure(), make_decision())


def test_new_strategy_rejects_empty_reason():
    manager = make_manager()

    handler = NewStrategyRecoveryHandler(
        manager,
        lambda failure, decision: StrategyChangeRequest(
            strategy_id="strategy-2",
            reason="",
        ),
    )

    with pytest.raises(ValueError, match="strategy reason must not be empty"):
        handler(make_failure(), make_decision())
