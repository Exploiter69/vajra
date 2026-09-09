from datetime import datetime, timezone

import pytest

from vajra.domain import EngineeringRun, RunState, AttemptState
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore
from vajra.runtime.worker_lifecycle import (
    WorkerDisappearance,
    WorkerDisappearanceDetector,
)


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def make_manager():
    state_store = InMemoryStateStore()
    event_store = InMemoryEventStore()
    manager = RunManager(state_store, event_store)

    run = EngineeringRun(
        run_id="run-loss",
        created_at=NOW,
        objective="worker loss",
        repository_id="repo-1",
        base_revision="base",
        acceptance_criteria=(),
        policy_id="policy",
        policy_version="v1",
        budget_id="budget",
        state=RunState.CREATED,
    )

    manager.create_run(run)
    manager.transition(run.run_id, RunState.QUEUED)
    manager.transition(run.run_id, RunState.ORIENTING)
    manager.transition(run.run_id, RunState.PLANNING)
    manager.transition(run.run_id, RunState.EXECUTING)
    manager.add_step(run.run_id, "step-1", "implementation")
    manager.start_attempt(
        run.run_id,
        "step-1",
        "attempt-1",
        "worker-1",
        "lease-1",
        lease_ttl_seconds=1,
        now=NOW,
    )

    return manager, event_store


def test_expired_worker_is_detected_and_run_enters_recovery():
    manager, event_store = make_manager()

    result = WorkerDisappearanceDetector(manager).detect(
        WorkerDisappearance(
            run_id="run-loss",
            step_id="step-1",
            attempt_id="attempt-1",
            worker_id="worker-1",
        ),
        now=datetime(2026, 9, 8, 12, 2, tzinfo=timezone.utc),
    )

    assert result.state is RunState.RECOVERING

    current = manager.get_run("run-loss")
    attempt = current.steps[0].attempts[0]

    assert attempt.state is AttemptState.FAILED
    assert attempt.error == "worker disappeared"
    assert attempt.lease_id is None
    assert current.steps[0].state.value == "RECOVERING"

    event_types = [
        event.event_type
        for event in manager.events("run-loss")
    ]
    assert "ATTEMPT_FAILED" in event_types
    assert "RUN_RECOVERING" in event_types


def test_active_worker_lease_is_not_treated_as_disappearance():
    manager, _ = make_manager()

    with pytest.raises(ValueError, match="still active"):
        WorkerDisappearanceDetector(manager).detect(
            WorkerDisappearance(
                run_id="run-loss",
                step_id="step-1",
                attempt_id="attempt-1",
                worker_id="worker-1",
            ),
            now=NOW,
        )

    current = manager.get_run("run-loss")

    assert current.state is RunState.EXECUTING
    assert current.steps[0].attempts[0].state is AttemptState.RUNNING


def test_wrong_worker_cannot_mark_attempt_lost():
    manager, _ = make_manager()

    with pytest.raises(PermissionError, match="Worker"):
        WorkerDisappearanceDetector(manager).detect(
            WorkerDisappearance(
                run_id="run-loss",
                step_id="step-1",
                attempt_id="attempt-1",
                worker_id="worker-2",
            ),
            now=datetime(2026, 9, 8, 12, 2, tzinfo=timezone.utc),
        )
