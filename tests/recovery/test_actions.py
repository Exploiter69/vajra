from __future__ import annotations

from datetime import datetime, timezone

import pytest

from vajra.domain import (
    Budget,
    EngineeringRun,
    RunState,
)
from vajra.recovery.actions import RetryRecoveryHandler, RetryRequest
from vajra.recovery.contracts import (
    Failure,
    FailureCategory,
    RecoveryAction,
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
        objective="retry failed work",
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

    manager.add_step(
        "run-1",
        "step-1",
        "implementation",
    )

    manager.start_attempt(
        "run-1",
        "step-1",
        "attempt-1",
        "worker-old",
        "lease-old",
    )

    manager.fail_attempt(
        "run-1",
        "step-1",
        "attempt-1",
        "worker failure",
    )

    manager.recover_run("run-1")

    return manager


def make_failure() -> Failure:
    return Failure(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.WORKER_LOSS,
        message="worker disappeared",
    )


def make_decision() -> RecoveryDecision:
    return RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.WORKER_LOSS,
        action=RecoveryAction.RETRY,
        reason="retry transient worker failure",
    )


def test_retry_creates_new_attempt_with_new_worker_and_lease():
    manager = make_manager()
    handler = RetryRecoveryHandler(manager)

    replacement = handler(
        make_failure(),
        make_decision(),
        request=RetryRequest(
            worker_id="worker-new",
            lease_id="lease-new",
        ),
    )

    assert replacement.attempt_id != "attempt-1"
    assert replacement.worker_id == "worker-new"
    assert replacement.lease_id == "lease-new"

    run = manager.get_run("run-1")
    step = run.steps[0]

    assert len(step.attempts) == 2
    assert step.attempts[0].attempt_id == "attempt-1"
    assert step.attempts[0].state.value == "FAILED"
    assert step.attempts[1].attempt_id == replacement.attempt_id


def test_retry_requires_recovering_run():
    manager = make_manager()
    manager.transition("run-1", RunState.QUEUED)

    handler = RetryRecoveryHandler(manager)

    with pytest.raises(ValueError, match="Run is not recovering"):
        handler(
            make_failure(),
            make_decision(),
            request=RetryRequest(
                worker_id="worker-new",
                lease_id="lease-new",
            ),
        )


def test_retry_rejects_non_retry_decision():
    manager = make_manager()
    handler = RetryRecoveryHandler(manager)

    decision = RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.WORKER_LOSS,
        action=RecoveryAction.CHANGE_WORKER,
        reason="worker replacement",
    )

    with pytest.raises(ValueError, match="requires a RETRY decision"):
        handler(
            make_failure(),
            decision,
            request=RetryRequest(
                worker_id="worker-new",
                lease_id="lease-new",
            ),
        )


def test_retry_rejects_missing_step():
    manager = make_manager()
    handler = RetryRecoveryHandler(manager)

    failure = Failure(
        failure_id="failure-1",
        run_id="run-1",
        step_id="missing-step",
        attempt_id="attempt-1",
        category=FailureCategory.WORKER_LOSS,
        message="worker disappeared",
    )

    decision = RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="missing-step",
        attempt_id="attempt-1",
        category=FailureCategory.WORKER_LOSS,
        action=RecoveryAction.RETRY,
        reason="retry transient worker failure",
    )

    with pytest.raises(KeyError, match="Unknown step"):
        handler(
            failure,
            decision,
            request=RetryRequest(
                worker_id="worker-new",
                lease_id="lease-new",
            ),
        )


def test_retry_rejects_non_failed_attempt():
    manager = make_manager()

    # Move the run back through recovery and create a new running attempt.
    manager.start_attempt(
        "run-1",
        "step-1",
        "attempt-running",
        "worker-running",
        "lease-running",
    )

    handler = RetryRecoveryHandler(manager)

    failure = Failure(
        failure_id="failure-2",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-running",
        category=FailureCategory.WORKER_LOSS,
        message="worker disappeared",
    )

    decision = RecoveryDecision(
        failure_id="failure-2",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-running",
        category=FailureCategory.WORKER_LOSS,
        action=RecoveryAction.RETRY,
        reason="retry transient worker failure",
    )

    with pytest.raises(ValueError, match="Attempt is not failed"):
        handler(
            failure,
            decision,
            request=RetryRequest(
                worker_id="worker-new",
                lease_id="lease-new",
            ),
        )
