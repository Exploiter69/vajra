import pytest

from vajra.domain import EngineeringRun, RunState
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore


class FailingEventStore(InMemoryEventStore):
    def append(self, event):
        if event.event_type != "RUN_CREATED":
            raise RuntimeError("event persistence failed")
        return super().append(event)


class FailingStateStore(InMemoryStateStore):
    def __init__(self):
        super().__init__()
        self.fail_save = False

    def save_run(self, run):
        if self.fail_save:
            raise RuntimeError("state persistence failed")
        return super().save_run(run)


def make_run() -> EngineeringRun:
    return EngineeringRun(
        run_id="atomicity-run",
        objective="test atomicity",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("pytest",),
        policy_id="default",
        policy_version="1",
        budget_id="default",
    )


def test_transition_does_not_hide_event_persistence_failure():
    state_store = InMemoryStateStore()
    manager = RunManager(
        state_store=state_store,
        event_store=FailingEventStore(),
    )

    run = make_run()
    manager.create_run(run)

    with pytest.raises(RuntimeError, match="event persistence failed"):
        manager.transition("atomicity-run", RunState.QUEUED)

    # State must roll back when the lifecycle event cannot be persisted.
    assert manager.get_run("atomicity-run").state is RunState.CREATED


def test_state_persistence_failure_prevents_event_creation():
    state_store = FailingStateStore()
    event_store = InMemoryEventStore()
    manager = RunManager(
        state_store=state_store,
        event_store=event_store,
    )

    run = make_run()
    manager.create_run(run)

    state_store.fail_save = True

    with pytest.raises(RuntimeError, match="state persistence failed"):
        manager.transition("atomicity-run", RunState.QUEUED)

    assert event_store.list_for_run("atomicity-run") == (
        event_store.list_for_run("atomicity-run")[0],
    )
    assert manager.get_run("atomicity-run").state is RunState.QUEUED
