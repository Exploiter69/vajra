from datetime import datetime, timezone

import pytest

from vajra.domain import Checkpoint, Event
from vajra.recovery.checkpoint_store import (
    CheckpointManager,
    InMemoryCheckpointStore,
)
from vajra.runtime.event_store import InMemoryEventStore


def make_checkpoint(
    checkpoint_id: str = "checkpoint-1",
) -> Checkpoint:
    return Checkpoint(
        checkpoint_id=checkpoint_id,
        run_id="run-1",
        step_id="step-1",
        event_position=3,
        git_revision="abc123",
        workspace_identity="workspace-1",
        policy_version="policy-v1",
        state_digest="digest-1",
    )


def make_event(
    checkpoint: Checkpoint,
    *,
    event_type: str = "CHECKPOINT_CREATED",
) -> Event:
    return Event(
        event_id=f"event-{checkpoint.checkpoint_id}",
        run_id=checkpoint.run_id,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc),
        sequence=1,
        step_id=checkpoint.step_id,
        payload={
            "checkpoint_id": checkpoint.checkpoint_id,
            "event_position": checkpoint.event_position,
        },
    )


def test_creates_and_retrieves_checkpoint():
    store = InMemoryCheckpointStore()
    checkpoint = make_checkpoint()

    created = store.create(checkpoint)

    assert created == checkpoint
    assert store.get("checkpoint-1") == checkpoint


def test_rejects_duplicate_checkpoint_id():
    store = InMemoryCheckpointStore()
    store.create(make_checkpoint())

    with pytest.raises(ValueError, match="already exists"):
        store.create(make_checkpoint())


def test_missing_checkpoint_is_rejected():
    store = InMemoryCheckpointStore()

    with pytest.raises(KeyError, match="Checkpoint not found"):
        store.get("missing")


def test_lists_only_checkpoints_for_run():
    store = InMemoryCheckpointStore()
    store.create(make_checkpoint("checkpoint-1"))

    other = Checkpoint(
        checkpoint_id="checkpoint-2",
        run_id="run-2",
        step_id="step-1",
        event_position=4,
        git_revision="def456",
        workspace_identity="workspace-2",
        policy_version="policy-v1",
        state_digest="digest-2",
    )
    store.create(other)

    assert store.list_for_run("run-1") == (make_checkpoint("checkpoint-1"),)


def test_manager_persists_checkpoint_and_creation_event():
    checkpoint_store = InMemoryCheckpointStore()
    event_store = InMemoryEventStore()
    manager = CheckpointManager(checkpoint_store, event_store)

    created = manager.create_checkpoint(
        make_checkpoint(),
        event_factory=make_event,
    )

    assert created == make_checkpoint()
    events = event_store.list_for_run("run-1")
    assert len(events) == 1
    assert events[0].event_type == "CHECKPOINT_CREATED"
    assert events[0].payload["checkpoint_id"] == "checkpoint-1"


def test_manager_rejects_wrong_event_type_and_rolls_back():
    checkpoint_store = InMemoryCheckpointStore()
    event_store = InMemoryEventStore()
    manager = CheckpointManager(checkpoint_store, event_store)

    with pytest.raises(
        ValueError,
        match="CHECKPOINT_CREATED",
    ):
        manager.create_checkpoint(
            make_checkpoint(),
            event_factory=lambda checkpoint: make_event(
                checkpoint,
                event_type="WRONG_EVENT",
            ),
        )

    with pytest.raises(KeyError):
        checkpoint_store.get("checkpoint-1")

    assert event_store.list_for_run("run-1") == ()


def test_manager_rejects_event_for_different_run_and_rolls_back():
    checkpoint_store = InMemoryCheckpointStore()
    event_store = InMemoryEventStore()
    manager = CheckpointManager(checkpoint_store, event_store)

    def wrong_run_event(checkpoint):
        event = make_event(checkpoint)
        return Event(
            event_id=event.event_id,
            run_id="run-2",
            event_type=event.event_type,
            timestamp=event.timestamp,
            sequence=event.sequence,
            step_id=event.step_id,
            payload=event.payload,
        )

    with pytest.raises(ValueError, match="run_id"):
        manager.create_checkpoint(
            make_checkpoint(),
            event_factory=wrong_run_event,
        )

    with pytest.raises(KeyError):
        checkpoint_store.get("checkpoint-1")


def test_manager_rejects_event_for_different_step_and_rolls_back():
    checkpoint_store = InMemoryCheckpointStore()
    event_store = InMemoryEventStore()
    manager = CheckpointManager(checkpoint_store, event_store)

    def wrong_step_event(checkpoint):
        event = make_event(checkpoint)
        return Event(
            event_id=event.event_id,
            run_id=event.run_id,
            event_type=event.event_type,
            timestamp=event.timestamp,
            sequence=event.sequence,
            step_id="step-2",
            payload=event.payload,
        )

    with pytest.raises(ValueError, match="step_id"):
        manager.create_checkpoint(
            make_checkpoint(),
            event_factory=wrong_step_event,
        )

    with pytest.raises(KeyError):
        checkpoint_store.get("checkpoint-1")


def test_manager_rolls_back_when_event_store_fails():
    checkpoint_store = InMemoryCheckpointStore()

    class FailingEventStore(InMemoryEventStore):
        def append(self, event):
            raise RuntimeError("event persistence failed")

    event_store = FailingEventStore()
    manager = CheckpointManager(checkpoint_store, event_store)

    with pytest.raises(
        RuntimeError,
        match="event persistence failed",
    ):
        manager.create_checkpoint(
            make_checkpoint(),
            event_factory=make_event,
        )

    with pytest.raises(KeyError):
        checkpoint_store.get("checkpoint-1")
