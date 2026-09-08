from __future__ import annotations

import pytest

from vajra.domain import EngineeringRun, FinalDisposition, RunState
from vajra.recovery.abort import AbortRecoveryHandler
from vajra.recovery.contracts import Failure, FailureCategory, RecoveryAction
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
        objective="abort recovery",
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
        category=FailureCategory.RESOURCE_EXHAUSTION,
        message="budget exhausted",
    )


def make_decision() -> RecoveryDecision:
    return RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.RESOURCE_EXHAUSTION,
        action=RecoveryAction.ABORT,
        reason="recovery budget exhausted",
    )


def test_aborts_run_and_sets_final_disposition() -> None:
    manager = make_manager()
    handler = AbortRecoveryHandler(manager)

    request = handler(make_failure(), make_decision())
    run = manager.get_run("run-1")

    assert request.failure_id == "failure-1"
    assert request.run_id == "run-1"
    assert request.step_id == "step-1"
    assert request.attempt_id == "attempt-1"
    assert request.reason == "recovery budget exhausted"
    assert run.state is RunState.ABORTED
    assert run.final_disposition is FinalDisposition.ABORTED


def test_records_abort_event() -> None:
    manager = make_manager()
    handler = AbortRecoveryHandler(manager)

    handler(make_failure(), make_decision())

    events = manager.events("run-1")

    assert events[-1].event_type == "RUN_ABORTED"
    assert events[-1].payload["reason"] == "recovery budget exhausted"


def test_requires_abort_action() -> None:
    manager = make_manager()
    handler = AbortRecoveryHandler(manager)

    decision = RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.RESOURCE_EXHAUSTION,
        action=RecoveryAction.RETRY,
        reason="retry",
    )

    with pytest.raises(ValueError, match="ABORT"):
        handler(make_failure(), decision)


def test_rejects_mismatched_failure() -> None:
    manager = make_manager()
    handler = AbortRecoveryHandler(manager)

    failure = Failure(
        failure_id="different",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.RESOURCE_EXHAUSTION,
        message="budget exhausted",
    )

    with pytest.raises(ValueError, match="does not match"):
        handler(failure, make_decision())


def test_requires_recovering_run() -> None:
    manager = make_manager()
    manager.transition("run-1", RunState.WAITING_HUMAN)
    handler = AbortRecoveryHandler(manager)

    with pytest.raises(ValueError, match="not recovering"):
        handler(make_failure(), make_decision())


def test_aborted_run_cannot_be_recovered_again() -> None:
    manager = make_manager()
    handler = AbortRecoveryHandler(manager)

    handler(make_failure(), make_decision())

    with pytest.raises(ValueError, match="not recovering"):
        handler(make_failure(), make_decision())
