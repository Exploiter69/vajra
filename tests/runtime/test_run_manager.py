import pytest

from vajra.domain import (
    EngineeringRun,
    AttemptState,
    RunState,
    StepState,
)
from vajra.runtime import RunManager


def make_run(run_id: str = "run-001") -> EngineeringRun:
    return EngineeringRun(
        run_id=run_id,
        objective="Build a verified artifact",
        repository_id="repo-001",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="default",
        policy_version="1",
        budget_id="budget-001",
        created_by="human",
    )


def test_create_and_retrieve_run():
    manager = RunManager()
    run = make_run()

    manager.create_run(run)

    assert manager.get_run("run-001") is run


def test_duplicate_run_is_rejected():
    manager = RunManager()
    manager.create_run(make_run())

    with pytest.raises(ValueError, match="Run already exists"):
        manager.create_run(make_run())


def test_step_belongs_to_run():
    manager = RunManager()
    manager.create_run(make_run())

    step = manager.add_step(
        "run-001",
        "step-001",
        "Inspect repository",
    )

    assert step.run_id == "run-001"
    assert manager.get_run("run-001").current_step_id == "step-001"


def test_attempt_belongs_to_step_and_worker():
    manager = RunManager()
    manager.create_run(make_run())
    manager.add_step("run-001", "step-001", "Execute work")

    attempt = manager.start_attempt(
        "run-001",
        "step-001",
        "attempt-001",
        "worker-001",
        "lease-001",
    )

    run = manager.get_run("run-001")

    assert attempt.run_id == run.run_id
    assert attempt.step_id == "step-001"
    assert attempt.worker_id == "worker-001"
    assert attempt.lease_id == "lease-001"
    assert attempt.state is AttemptState.RUNNING
    assert run.steps[0].state is StepState.RUNNING


def test_worker_failure_preserves_run_and_marks_step_recovering():
    manager = RunManager()
    manager.create_run(make_run())
    manager.add_step("run-001", "step-001", "Execute work")

    manager.start_attempt(
        "run-001",
        "step-001",
        "attempt-001",
        "worker-001",
        "lease-001",
    )

    failed = manager.fail_attempt(
        "run-001",
        "step-001",
        "attempt-001",
        "worker disappeared",
    )

    run = manager.get_run("run-001")

    assert failed.state is AttemptState.FAILED
    assert failed.error == "worker disappeared"
    assert failed.lease_id is None

    assert run.run_id == "run-001"
    assert run.state is RunState.CREATED
    assert run.steps[0].state is StepState.RECOVERING


def test_recovery_moves_run_to_recovering():
    manager = RunManager()
    manager.create_run(make_run())

    manager.transition("run-001", RunState.QUEUED)
    manager.transition("run-001", RunState.ORIENTING)

    manager.recover_run("run-001")

    assert manager.get_run("run-001").state is RunState.RECOVERING


def test_missing_entities_are_rejected():
    manager = RunManager()

    with pytest.raises(KeyError, match="Run not found"):
        manager.get_run("missing")

    manager.create_run(make_run())

    with pytest.raises(KeyError, match="Step not found"):
        manager.start_attempt(
            "run-001",
            "missing-step",
            "attempt-001",
            "worker-001",
            "lease-001",
        )


def test_lifecycle_events_are_recorded() -> None:
    from vajra.runtime.event_store import InMemoryEventStore
    from vajra.runtime.run_manager import RunManager

    event_store = InMemoryEventStore()
    manager = RunManager(event_store=event_store)

    run = make_run("run-events")
    manager.create_run(run)
    manager.transition("run-events", RunState.QUEUED)
    manager.transition("run-events", RunState.ORIENTING)
    manager.transition("run-events", RunState.PLANNING)
    manager.transition("run-events", RunState.EXECUTING)

    step = manager.add_step("run-events", "step-1", "inspect")
    manager.start_attempt(
        "run-events",
        step.step_id,
        "attempt-1",
        "worker-1",
        "lease-1",
    )
    manager.fail_attempt(
        "run-events",
        step.step_id,
        "attempt-1",
        "worker disappeared",
    )
    manager.recover_run("run-events")

    events = manager.events("run-events")

    assert [event.sequence for event in events] == list(range(1, 10))
    assert [event.event_type for event in events] == [
        "RUN_CREATED",
        "RUN_STATE_CHANGED",
        "RUN_STATE_CHANGED",
        "RUN_STATE_CHANGED",
        "RUN_STATE_CHANGED",
        "STEP_CREATED",
        "ATTEMPT_STARTED",
        "ATTEMPT_FAILED",
        "RUN_RECOVERING",
    ]


def test_event_contains_lifecycle_correlation_data() -> None:
    from vajra.runtime.event_store import InMemoryEventStore
    from vajra.runtime.run_manager import RunManager

    event_store = InMemoryEventStore()
    manager = RunManager(event_store=event_store)

    run = make_run("run-correlation")
    manager.create_run(run)
    step = manager.add_step("run-correlation", "step-1", "execute")
    manager.start_attempt(
        "run-correlation",
        step.step_id,
        "attempt-1",
        "worker-1",
        "lease-1",
    )

    events = manager.events("run-correlation")

    attempt_event = events[-1]

    assert attempt_event.step_id == "step-1"
    assert attempt_event.attempt_id == "attempt-1"
    assert attempt_event.worker_id == "worker-1"
    assert attempt_event.payload["lease_id"] == "lease-1"


def test_start_attempt_creates_and_persists_worker_lease():
    from datetime import datetime, timezone

    manager = RunManager()
    run = manager.create_run(make_run())
    manager.add_step(run.run_id, "step-1", "implementation")

    attempt = manager.start_attempt(
        run.run_id,
        "step-1",
        "attempt-1",
        "worker-1",
        "lease-1",
        lease_ttl_seconds=60,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    lease = manager.get_lease("attempt-1")

    assert attempt.worker_id == "worker-1"
    assert attempt.lease_id == "lease-1"
    assert attempt.lease_expiry == lease.lease_expiry
    assert lease.worker_id == "worker-1"
    assert lease.lease_id == "lease-1"
    assert lease.fencing_token == 1


def test_start_attempt_records_fencing_information():
    from datetime import datetime, timezone

    manager = RunManager()
    run = manager.create_run(make_run())
    manager.add_step(run.run_id, "step-1", "implementation")

    manager.start_attempt(
        run.run_id,
        "step-1",
        "attempt-1",
        "worker-1",
        "lease-1",
        lease_ttl_seconds=30,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    event = manager.events(run.run_id)[-1]

    assert event.event_type == "ATTEMPT_STARTED"
    assert event.payload["lease_id"] == "lease-1"
    assert event.payload["fencing_token"] == 1
    assert event.payload["lease_expiry"] == (
        "2026-01-01T00:00:30+00:00"
    )


def test_start_attempt_rejects_invalid_lease_ttl():
    from datetime import datetime, timezone

    manager = RunManager()
    run = manager.create_run(make_run())
    manager.add_step(run.run_id, "step-1", "implementation")

    with pytest.raises(ValueError, match="ttl_seconds"):
        manager.start_attempt(
            run.run_id,
            "step-1",
            "attempt-1",
            "worker-1",
            "lease-1",
            lease_ttl_seconds=0,
            now=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
