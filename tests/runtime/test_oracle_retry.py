from __future__ import annotations

from datetime import datetime, timezone

import pytest

from vajra.domain import AttemptState, EngineeringRun, RunState
from vajra.recovery.contracts import Failure, FailureCategory, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.oracle_retry import OracleRetryCoordinator, OracleRetryRequest
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make_manager() -> RunManager:
    manager = RunManager(
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
    )

    run = EngineeringRun(
        run_id="run-1",
        created_at=NOW,
        objective="oracle retry",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="default",
        policy_version="1",
        budget_id="budget-1",
        state=RunState.CREATED,
    )

    manager.create_run(run)
    manager.transition("run-1", RunState.QUEUED)
    manager.transition("run-1", RunState.ORIENTING)
    manager.transition("run-1", RunState.PLANNING)
    manager.transition("run-1", RunState.EXECUTING)
    manager.add_step("run-1", "step-1", "implementation")

    manager.start_attempt(
        "run-1",
        "step-1",
        "attempt-1",
        "worker-1",
        "lease-1",
        lease_ttl_seconds=60,
        now=NOW,
    )

    manager.fail_attempt(
        "run-1",
        "step-1",
        "attempt-1",
        "worker disappeared",
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
        reason="retry with replacement worker",
    )


def test_oracle_retry_creates_new_attempt_and_lease() -> None:
    manager = make_manager()
    coordinator = OracleRetryCoordinator(manager)

    replacement = coordinator.retry(
        make_failure(),
        make_decision(),
        request=OracleRetryRequest(
            worker_id="worker-2",
            lease_id="lease-2",
            lease_ttl_seconds=60,
        ),
    )

    run = manager.get_run("run-1")
    attempts = run.steps[0].attempts

    assert replacement.attempt_id != "attempt-1"
    assert replacement.state is AttemptState.RUNNING
    assert replacement.worker_id == "worker-2"
    assert replacement.lease_id == "lease-2"

    assert attempts[0].attempt_id == "attempt-1"
    assert attempts[0].state is AttemptState.FAILED
    assert attempts[0].lease_id is None

    assert attempts[1].attempt_id == replacement.attempt_id
    assert manager.get_lease(replacement.attempt_id) is not None


def test_oracle_retry_requires_retry_decision() -> None:
    manager = make_manager()
    coordinator = OracleRetryCoordinator(manager)

    decision = RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.WORKER_LOSS,
        action=RecoveryAction.CHANGE_WORKER,
        reason="change worker",
    )

    with pytest.raises(ValueError, match="requires a RETRY decision"):
        coordinator.retry(
            make_failure(),
            decision,
            request=OracleRetryRequest(
                worker_id="worker-2",
                lease_id="lease-2",
            ),
        )


def test_oracle_retry_does_not_dispatch_or_execute() -> None:
    manager = make_manager()
    coordinator = OracleRetryCoordinator(manager)

    replacement = coordinator.retry(
        make_failure(),
        make_decision(),
        request=OracleRetryRequest(
            worker_id="worker-2",
            lease_id="lease-2",
        ),
    )

    assert replacement.worker_id == "worker-2"
    assert not hasattr(coordinator, "dispatch")
    assert not hasattr(coordinator, "execute")
