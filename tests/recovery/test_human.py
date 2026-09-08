from __future__ import annotations

import pytest

from vajra.domain import EngineeringRun, RunState
from vajra.recovery.contracts import Failure, FailureCategory, RecoveryAction
from vajra.recovery.human import RequestHumanRecoveryHandler
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore
from vajra.runtime.event_store import InMemoryEventStore


def make_manager() -> RunManager:
    manager = RunManager(
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
    )

    run = EngineeringRun(
        run_id="run-1",
        objective="human escalation",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="default",
        policy_version="v1",
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
        category=FailureCategory.POLICY_DENIAL,
        message="human authority required",
    )


def make_decision() -> RecoveryDecision:
    return RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.POLICY_DENIAL,
        action=RecoveryAction.REQUEST_HUMAN,
        reason="human authority is required",
    )


def test_requests_human_and_waits() -> None:
    manager = make_manager()
    handler = RequestHumanRecoveryHandler(manager)

    request = handler(make_failure(), make_decision())

    assert request.failure_id == "failure-1"
    assert request.run_id == "run-1"
    assert request.step_id == "step-1"
    assert request.attempt_id == "attempt-1"
    assert request.reason == "human authority is required"
    assert manager.get_run("run-1").state is RunState.WAITING_HUMAN


def test_requires_request_human_action() -> None:
    manager = make_manager()
    handler = RequestHumanRecoveryHandler(manager)

    decision = RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.POLICY_DENIAL,
        action=RecoveryAction.RETRY,
        reason="retry",
    )

    with pytest.raises(ValueError, match="REQUEST_HUMAN"):
        handler(make_failure(), decision)


def test_rejects_mismatched_failure() -> None:
    manager = make_manager()
    handler = RequestHumanRecoveryHandler(manager)

    failure = Failure(
        failure_id="different",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.POLICY_DENIAL,
        message="human authority required",
    )

    with pytest.raises(ValueError, match="does not match"):
        handler(failure, make_decision())


def test_requires_recovering_run() -> None:
    manager = make_manager()
    manager.transition("run-1", RunState.WAITING_HUMAN)
    handler = RequestHumanRecoveryHandler(manager)

    with pytest.raises(ValueError, match="not recovering"):
        handler(make_failure(), make_decision())


def test_does_not_auto_approve() -> None:
    manager = make_manager()
    handler = RequestHumanRecoveryHandler(manager)

    request = handler(make_failure(), make_decision())

    assert request.reason
    assert manager.get_run("run-1").state is RunState.WAITING_HUMAN
    assert manager.get_run("run-1").final_disposition is None
