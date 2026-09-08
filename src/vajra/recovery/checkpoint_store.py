from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from threading import RLock

from vajra.domain import Checkpoint, Event
from vajra.runtime.event_store import EventStore


class CheckpointStore(ABC):
    """
    Persistence boundary for durable Engineering Run checkpoints.
    """

    @abstractmethod
    def create(self, checkpoint: Checkpoint) -> Checkpoint:
        raise NotImplementedError

    @abstractmethod
    def get(self, checkpoint_id: str) -> Checkpoint:
        raise NotImplementedError

    @abstractmethod
    def list_for_run(self, run_id: str) -> tuple[Checkpoint, ...]:
        raise NotImplementedError


class InMemoryCheckpointStore(CheckpointStore):
    """
    Test/development checkpoint store.

    Production durability is supplied by the durable runtime/backend.
    """

    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}
        self._lock = RLock()

    def create(self, checkpoint: Checkpoint) -> Checkpoint:
        with self._lock:
            if checkpoint.checkpoint_id in self._checkpoints:
                raise ValueError(
                    f"Checkpoint already exists: {checkpoint.checkpoint_id}"
                )

            stored = deepcopy(checkpoint)
            self._checkpoints[checkpoint.checkpoint_id] = stored
            return deepcopy(stored)

    def get(self, checkpoint_id: str) -> Checkpoint:
        with self._lock:
            try:
                return deepcopy(self._checkpoints[checkpoint_id])
            except KeyError:
                raise KeyError(
                    f"Checkpoint not found: {checkpoint_id}"
                ) from None

    def list_for_run(self, run_id: str) -> tuple[Checkpoint, ...]:
        with self._lock:
            return tuple(
                deepcopy(checkpoint)
                for checkpoint in self._checkpoints.values()
                if checkpoint.run_id == run_id
            )

    def delete(self, checkpoint_id: str) -> None:
        with self._lock:
            self._checkpoints.pop(checkpoint_id, None)


class CheckpointManager:
    """
    Coordinates durable checkpoint creation with event history.

    The manager records the checkpoint itself and its CHECKPOINT_CREATED event
    as one logical operation. It does not create Git/workspace snapshots or
    restore external state.
    """

    def __init__(
        self,
        checkpoint_store: CheckpointStore,
        event_store: EventStore,
    ) -> None:
        self._checkpoint_store = checkpoint_store
        self._event_store = event_store
        self._lock = RLock()

    def create_checkpoint(
        self,
        checkpoint: Checkpoint,
        *,
        event_factory,
    ) -> Checkpoint:
        """
        Persist one checkpoint and append its durable creation event.

        event_factory receives the checkpoint and must return the canonical
        Event to append. Keeping event construction outside this manager
        avoids duplicating RunManager's event-ID/timestamp policy.
        """
        with self._lock:
            created = self._checkpoint_store.create(checkpoint)

            try:
                event = event_factory(created)

                if not isinstance(event, Event):
                    raise TypeError(
                        "event_factory must return an Event"
                    )

                if event.run_id != created.run_id:
                    raise ValueError(
                        "Checkpoint event run_id does not match checkpoint"
                    )

                if event.event_type != "CHECKPOINT_CREATED":
                    raise ValueError(
                        "Checkpoint event must be CHECKPOINT_CREATED"
                    )

                if event.step_id != created.step_id:
                    raise ValueError(
                        "Checkpoint event step_id does not match checkpoint"
                    )

                self._event_store.append(event)
                return created

            except Exception:
                delete = getattr(self._checkpoint_store, "delete", None)
                if delete is not None:
                    delete(created.checkpoint_id)
                raise


__all__ = [
    "CheckpointManager",
    "CheckpointStore",
    "InMemoryCheckpointStore",
]
