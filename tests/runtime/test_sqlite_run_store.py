from datetime import datetime, timezone

import pytest

from vajra.domain import EngineeringRun, RunState
from vajra.control.transition_authority import TransitionActor
from vajra.runtime.run_manager import RunManager
from vajra.runtime.sqlite_run_store import SQLiteRunStore


def make_run() -> EngineeringRun:
    return EngineeringRun(
        run_id="sqlite-run",
        objective="survive process restart",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="default",
        policy_version="1",
        budget_id="default",
        created_by="test",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_run_and_event_history_survive_store_reopen(tmp_path):
    path = tmp_path / "vajra.sqlite3"
    store = SQLiteRunStore(path)
    manager = RunManager(state_store=store, event_store=store)

    manager.create_run(make_run())
    manager.transition("sqlite-run", RunState.QUEUED, TransitionActor.SYSTEM)
    manager.add_step("sqlite-run", "step-1", "persist nested state")
    manager.start_attempt(
        "sqlite-run", "step-1", "attempt-1", "worker-1", "lease-1"
    )
    expected_events = manager.events("sqlite-run")
    store.close()

    reopened = SQLiteRunStore(path)
    recovered_manager = RunManager(state_store=reopened, event_store=reopened)

    recovered = recovered_manager.get_run("sqlite-run")
    assert recovered.state is RunState.QUEUED
    assert recovered.steps[0].step_id == "step-1"
    assert recovered.steps[0].attempts[0].attempt_id == "attempt-1"
    assert recovered.steps[0].attempts[0].lease_id == "lease-1"
    assert recovered_manager.events("sqlite-run") == expected_events
    assert [event.sequence for event in recovered_manager.events("sqlite-run")] == [
        1, 2, 3, 4
    ]
    reopened.close()


def test_state_and_event_roll_back_together_when_event_append_fails(tmp_path):
    class FailingStore(SQLiteRunStore):
        def append(self, event):
            if event.event_type != "RUN_CREATED":
                raise RuntimeError("event persistence failed")
            return super().append(event)

    store = FailingStore(tmp_path / "atomic.sqlite3")
    manager = RunManager(state_store=store, event_store=store)
    manager.create_run(make_run())
    initial_events = manager.events("sqlite-run")

    with pytest.raises(RuntimeError, match="event persistence failed"):
        manager.transition("sqlite-run", RunState.QUEUED, TransitionActor.SYSTEM)

    assert manager.get_run("sqlite-run").state is RunState.CREATED
    assert manager.events("sqlite-run") == initial_events
    store.close()


def test_duplicate_run_is_rejected_after_reopen(tmp_path):
    path = tmp_path / "duplicate.sqlite3"
    first = SQLiteRunStore(path)
    first.create_run(make_run())
    first.close()

    second = SQLiteRunStore(path)
    with pytest.raises(ValueError, match="Run already exists"):
        second.create_run(make_run())
    second.close()
