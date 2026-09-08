from datetime import datetime, timezone

import pytest

from vajra.domain import Event
from vajra.runtime.event_store import InMemoryEventStore


def make_event(
    run_id: str = "run-1",
    sequence: int = 1,
    event_id: str = "event-1",
) -> Event:
    return Event(
        event_id=event_id,
        run_id=run_id,
        event_type="RUN_CREATED",
        timestamp=datetime.now(timezone.utc),
        sequence=sequence,
    )


def test_append_and_list_events() -> None:
    store = InMemoryEventStore()
    event = make_event()

    store.append(event)

    assert store.list_for_run("run-1") == (event,)


def test_next_sequence_starts_at_one() -> None:
    store = InMemoryEventStore()

    assert store.next_sequence("run-1") == 1


def test_next_sequence_increments() -> None:
    store = InMemoryEventStore()

    store.append(make_event(sequence=1))
    store.append(make_event(sequence=2, event_id="event-2"))

    assert store.next_sequence("run-1") == 3


def test_invalid_sequence_rejected() -> None:
    store = InMemoryEventStore()

    with pytest.raises(ValueError, match="Invalid event sequence"):
        store.append(make_event(sequence=2))


def test_events_are_scoped_to_run() -> None:
    store = InMemoryEventStore()

    store.append(make_event(run_id="run-1"))
    store.append(
        make_event(
            run_id="run-2",
            event_id="event-2",
        )
    )

    assert len(store.list_for_run("run-1")) == 1
    assert len(store.list_for_run("run-2")) == 1
