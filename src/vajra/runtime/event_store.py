from __future__ import annotations

from abc import ABC, abstractmethod
from threading import RLock

from vajra.domain import Event


class EventStore(ABC):
    """
    Persistence boundary for append-only VAJRA event history.
    """

    @abstractmethod
    def append(self, event: Event) -> Event:
        raise NotImplementedError

    @abstractmethod
    def list_for_run(self, run_id: str) -> tuple[Event, ...]:
        raise NotImplementedError

    @abstractmethod
    def next_sequence(self, run_id: str) -> int:
        raise NotImplementedError


class InMemoryEventStore(EventStore):
    """
    Non-durable EventStore for tests/development.

    Production durability will be supplied by the durable runtime/state
    backend. This class must never be treated as canonical persistence.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[Event]] = {}
        self._lock = RLock()

    def append(self, event: Event) -> Event:
        with self._lock:
            events = self._events.setdefault(event.run_id, [])

            expected = len(events) + 1
            if event.sequence != expected:
                raise ValueError(
                    f"Invalid event sequence for run {event.run_id}: "
                    f"expected {expected}, got {event.sequence}"
                )

            events.append(event)
            return event

    def list_for_run(self, run_id: str) -> tuple[Event, ...]:
        with self._lock:
            return tuple(self._events.get(run_id, ()))

    def next_sequence(self, run_id: str) -> int:
        with self._lock:
            return len(self._events.get(run_id, ())) + 1
