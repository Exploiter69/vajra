from __future__ import annotations

import pytest

from vajra.domain import EngineeringRun, RunState
from vajra.recovery.contracts import (
    Failure,
    FailureCategory,
    RecoveryAction,
)
from vajra.recovery.policy import RecoveryDecision
from vajra.recovery.worker import (
    ChangeWorkerRecoveryHandler,
    WorkerChangeRequest,
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
        objective="change worker after worker loss",
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
        action=RecoveryAction.CHANGE_WORKER,
        reason="change worker after worker loss",
    )


def test_change_worker_delegates_selection_without_executing():
    manager = make_manager()
    calls = []

    def selector(failure, decision):
        calls.append((failure.failure_id, decision.action))
        return WorkerChangeRequest(
            worker_id="worker-2",
            reason="use replacement worker",
        )

    handler = ChangeWorkerRecoveryHandler(manager, selector)

    request = handler(make_failure(), make_decision())

    assert request.worker_id == "worker-2"
    assert request.reason == "use replacement worker"
    assert calls == [("failure-1", RecoveryAction.CHANGE_WORKER)]


def test_change_worker_requires_recovering_run():
    manager = make_manager()
    manager.transition("run-1", RunState.QUEUED)

    handler = ChangeWorkerRecoveryHandler(
        manager,
        lambda failure, decision: WorkerChangeRequest(
            worker_id="worker-2",
            reason="replacement",
        ),
    )

    with pytest.raises(ValueError, match="Run is not recovering"):
        handler(make_failure(), make_decision())


def test_change_worker_rejects_wrong_action():
    manager = make_manager()

    decision = RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.WORKER_LOSS,
        action=RecoveryAction.RETRY,
        reason="retry",
    )

    handler = ChangeWorkerRecoveryHandler(
        manager,
        lambda failure, decision: WorkerChangeRequest(
            worker_id="worker-2",
            reason="replacement",
        ),
    )

    with pytest.raises(ValueError, match="requires a CHANGE_WORKER decision"):
        handler(make_failure(), decision)


def test_change_worker_rejects_mismatched_failure_identity():
    manager = make_manager()

    failure = Failure(
        failure_id="different-failure",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.WORKER_LOSS,
        message="worker disappeared",
    )

    handler = ChangeWorkerRecoveryHandler(
        manager,
        lambda failure, decision: WorkerChangeRequest(
            worker_id="worker-2",
            reason="replacement",
        ),
    )

    with pytest.raises(ValueError, match="does not match failure"):
        handler(failure, make_decision())


def test_change_worker_rejects_empty_worker_id():
    manager = make_manager()

    handler = ChangeWorkerRecoveryHandler(
        manager,
        lambda failure, decision: WorkerChangeRequest(
            worker_id="",
            reason="replacement",
        ),
    )

    with pytest.raises(ValueError, match="worker_id must not be empty"):
        handler(make_failure(), make_decision())


def test_change_worker_rejects_empty_reason():
    manager = make_manager()

    handler = ChangeWorkerRecoveryHandler(
        manager,
        lambda failure, decision: WorkerChangeRequest(
            worker_id="worker-2",
            reason="",
        ),
    )

    with pytest.raises(ValueError, match="worker reason must not be empty"):
        handler(make_failure(), make_decision())
