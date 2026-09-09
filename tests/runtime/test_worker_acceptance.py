from datetime import datetime, timedelta, timezone

import pytest

from vajra.domain import (
    AttemptState,
    EngineeringRun,
    RunState,
)
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.lease import LeaseManager
from vajra.runtime.state_store import InMemoryStateStore
from vajra.runtime.worker_acceptance import (
    WorkerExecutionIdentity,
    WorkerResultAcceptor,
)
from vajra.runtime.worker_protocol import WorkerResult


def make_run() -> EngineeringRun:
    return EngineeringRun(
        run_id="run-1",
        objective="test",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="policy-1",
        policy_version="1",
        budget_id="budget-1",
    )


def setup():
    state_store = InMemoryStateStore()
    event_store = InMemoryEventStore()
    lease_manager = LeaseManager()
    run = make_run()
    state_store.create_run(run)

    from vajra.runtime.run_manager import RunManager

    manager = RunManager(state_store, event_store)
    manager.add_step("run-1", "step-1", "coding")
    manager.start_attempt(
        "run-1",
        "step-1",
        "attempt-1",
        "worker-1",
        "lease-1",
    )

    lease = lease_manager.acquire(
        "attempt-1",
        "worker-1",
        "lease-1",
        ttl_seconds=60,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    acceptor = WorkerResultAcceptor(
        lease_manager,
        state_store,
        event_store,
    )

    identity = WorkerExecutionIdentity(
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        worker_id="worker-1",
        lease_id="lease-1",
        fencing_token=lease.fencing_token,
    )

    return (
        state_store,
        event_store,
        lease_manager,
        acceptor,
        identity,
    )


def test_accept_successful_worker_result():
    state_store, event_store, lease_manager, acceptor, identity = setup()

    result = acceptor.accept(
        identity,
        WorkerResult(status="SUCCEEDED", correlation_id="corr-001"),
        now=datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
    )

    attempt = result.steps[0].attempts[0]

    assert attempt.state is AttemptState.SUCCEEDED
    assert attempt.lease_id is None
    assert lease_manager.get("attempt-1") is None
    assert event_store.list_for_run("run-1")[-1].event_type == (
        "WORKER_RESULT_ACCEPTED"
    )


def test_accept_failed_worker_result():
    state_store, event_store, lease_manager, acceptor, identity = setup()

    result = acceptor.accept(
        identity,
        WorkerResult(status="FAILED", errors=("compiler failed",)),
        now=datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
    )

    attempt = result.steps[0].attempts[0]

    assert attempt.state is AttemptState.FAILED
    assert attempt.error == "compiler failed"
    assert attempt.lease_id is None
    assert event_store.list_for_run("run-1")[-1].event_type == (
        "WORKER_RESULT_FAILED"
    )


def test_mismatched_worker_result_correlation_cannot_mutate_state():
    (
        state_store,
        event_store,
        lease_manager,
        acceptor,
        identity,
    ) = setup()

    before = state_store.get_run("run-1")
    before_events = event_store.list_for_run("run-1")

    identity = WorkerExecutionIdentity(
        run_id=identity.run_id,
        step_id=identity.step_id,
        attempt_id=identity.attempt_id,
        worker_id=identity.worker_id,
        lease_id=identity.lease_id,
        fencing_token=identity.fencing_token,
        correlation_id="corr-001",
    )

    with pytest.raises(
        PermissionError,
        match="correlation",
    ):
        acceptor.accept(
            identity,
            WorkerResult(
                status="SUCCEEDED",
                correlation_id="corr-002",
            ),
            now=datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc),
        )

    after = state_store.get_run("run-1")

    assert after.steps[0].attempts[0].state is AttemptState.RUNNING
    assert after.steps[0].attempts[0].lease_id == before.steps[0].attempts[0].lease_id
    assert event_store.list_for_run("run-1") == before_events
    assert after.artifacts == before.artifacts
    assert event_store.list_for_run("run-1") == event_store.list_for_run("run-1")


def test_stale_worker_result_cannot_mutate_canonical_state():
    (
        state_store,
        event_store,
        lease_manager,
        acceptor,
        identity,
    ) = setup()

    replacement = lease_manager.acquire(
        "attempt-1",
        "worker-2",
        "lease-2",
        ttl_seconds=60,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    before = state_store.get_run("run-1")

    with pytest.raises(PermissionError):
        acceptor.accept(
            identity,
            WorkerResult(status="SUCCEEDED"),
            now=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        )

    after = state_store.get_run("run-1")

    assert after.steps[0].attempts[0].state is AttemptState.RUNNING
    assert after.steps[0].attempts[0].lease_id == "lease-1"
    assert after.artifacts == before.artifacts
    assert event_store.list_for_run("run-1") == (
        event_store.list_for_run("run-1")
    )
    assert lease_manager.get("attempt-1") == replacement


def test_expired_worker_result_cannot_mutate_canonical_state():
    (
        state_store,
        event_store,
        lease_manager,
        acceptor,
        identity,
    ) = setup()

    before = state_store.get_run("run-1")

    with pytest.raises(PermissionError):
        acceptor.accept(
            identity,
            WorkerResult(status="SUCCEEDED"),
            now=datetime(2026, 1, 1, 0, 1, 1, tzinfo=timezone.utc),
        )

    after = state_store.get_run("run-1")

    assert after.steps[0].attempts[0].state is AttemptState.RUNNING
    assert after.artifacts == before.artifacts
    assert len(event_store.list_for_run("run-1")) == 2


def test_wrong_worker_result_cannot_mutate_canonical_state():
    (
        state_store,
        event_store,
        lease_manager,
        acceptor,
        identity,
    ) = setup()

    bad_identity = WorkerExecutionIdentity(
        run_id=identity.run_id,
        step_id=identity.step_id,
        attempt_id=identity.attempt_id,
        worker_id="worker-2",
        lease_id=identity.lease_id,
        fencing_token=identity.fencing_token,
    )

    before = state_store.get_run("run-1")

    with pytest.raises(PermissionError):
        acceptor.accept(
            bad_identity,
            WorkerResult(status="SUCCEEDED"),
        )

    after = state_store.get_run("run-1")

    assert after.steps[0].attempts[0].state is AttemptState.RUNNING
    assert after.artifacts == before.artifacts


def test_unsupported_result_does_not_mutate_canonical_state():
    (
        state_store,
        event_store,
        lease_manager,
        acceptor,
        identity,
    ) = setup()

    before = state_store.get_run("run-1")

    with pytest.raises(ValueError):
        acceptor.accept(
            identity,
            WorkerResult(status="UNKNOWN"),
                now=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        )

    after = state_store.get_run("run-1")

    assert after.steps[0].attempts[0].state is AttemptState.RUNNING
    assert after.steps[0].attempts[0].lease_id == "lease-1"
    assert after.artifacts == before.artifacts
    assert lease_manager.get("attempt-1") is not None


class FailingStateStore(InMemoryStateStore):
    def __init__(self):
        super().__init__()
        self.fail_next_save = True

    def save_run(self, run):
        if self.fail_next_save:
            self.fail_next_save = False
            raise RuntimeError("state persistence failed")
        return super().save_run(run)


class FailingEventStore(InMemoryEventStore):
    def __init__(self):
        super().__init__()
        self.fail_next_append = False

    def append(self, event):
        if self.fail_next_append:
            self.fail_next_append = False
            raise RuntimeError("event persistence failed")
        return super().append(event)


def test_state_persistence_failure_rolls_back_and_preserves_lease():
    (
        state_store,
        event_store,
        lease_manager,
        _acceptor,
        identity,
    ) = setup()

    failing_store = FailingStateStore()
    failing_store.create_run(state_store.get_run("run-1"))

    acceptor = WorkerResultAcceptor(
        lease_manager,
        failing_store,
        event_store,
    )

    before_events = event_store.list_for_run("run-1")

    with pytest.raises(RuntimeError, match="state persistence failed"):
        acceptor.accept(
            identity,
            WorkerResult(status="SUCCEEDED"),
            now=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        )

    after = failing_store.get_run("run-1")

    assert after.steps[0].attempts[0].state is AttemptState.RUNNING
    assert after.steps[0].attempts[0].lease_id == "lease-1"
    assert event_store.list_for_run("run-1") == before_events
    assert lease_manager.get("attempt-1") is not None


def test_event_persistence_failure_rolls_back_state_and_preserves_lease():
    (
        state_store,
        _event_store,
        lease_manager,
        _acceptor,
        identity,
    ) = setup()

    failing_events = FailingEventStore()
    for event in _event_store.list_for_run("run-1"):
        InMemoryEventStore.append(failing_events, event)
    failing_events.fail_next_append = True

    acceptor = WorkerResultAcceptor(
        lease_manager,
        state_store,
        failing_events,
    )

    before = state_store.get_run("run-1")

    with pytest.raises(RuntimeError, match="event persistence failed"):
        acceptor.accept(
            identity,
            WorkerResult(status="SUCCEEDED"),
            now=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        )

    after = state_store.get_run("run-1")

    assert after.steps[0].attempts[0].state is AttemptState.RUNNING
    assert after.steps[0].attempts[0].lease_id == "lease-1"
    assert after.artifacts == before.artifacts
    assert len(failing_events.list_for_run("run-1")) == 2
    assert lease_manager.get("attempt-1") is not None


def test_lease_release_failure_does_not_roll_back_accepted_result():
    (
        state_store,
        event_store,
        lease_manager,
        _acceptor,
        identity,
    ) = setup()

    class FailingReleaseLeaseManager(LeaseManager):
        def release(
            self,
            attempt_id,
            worker_id,
            lease_id,
            fencing_token,
            *,
            now=None,
        ):
            raise RuntimeError("lease cleanup failed")

    replacement_manager = FailingReleaseLeaseManager()

    lease = replacement_manager.acquire(
        "attempt-1",
        "worker-1",
        "lease-1",
        ttl_seconds=60,
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    acceptor = WorkerResultAcceptor(
        replacement_manager,
        state_store,
        event_store,
    )

    with pytest.raises(RuntimeError, match="lease cleanup failed"):
        acceptor.accept(
            identity,
            WorkerResult(status="SUCCEEDED"),
            now=datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
        )

    result = state_store.get_run("run-1")
    attempt = result.steps[0].attempts[0]

    assert attempt.state is AttemptState.SUCCEEDED
    assert attempt.lease_id is None
    assert event_store.list_for_run("run-1")[-1].event_type == (
        "WORKER_RESULT_ACCEPTED"
    )
    assert replacement_manager.get("attempt-1") == lease
