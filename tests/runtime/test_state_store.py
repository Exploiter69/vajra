from datetime import datetime, timezone

import pytest

from vajra.domain import EngineeringRun
from vajra.runtime.state_store import InMemoryStateStore


def make_run(run_id: str = "run-1") -> EngineeringRun:
    return EngineeringRun(
        run_id=run_id,
        objective="test objective",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="default",
        policy_version="1",
        budget_id="default",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_create_and_get_run() -> None:
    store = InMemoryStateStore()
    run = make_run()

    store.create_run(run)

    assert store.get_run("run-1") is run


def test_duplicate_run_rejected() -> None:
    store = InMemoryStateStore()
    run = make_run()

    store.create_run(run)

    with pytest.raises(ValueError, match="Run already exists"):
        store.create_run(run)


def test_save_existing_run() -> None:
    store = InMemoryStateStore()
    run = make_run()

    store.create_run(run)
    run.objective = "updated objective"
    store.save_run(run)

    assert store.get_run("run-1").objective == "updated objective"


def test_save_missing_run_rejected() -> None:
    store = InMemoryStateStore()
    run = make_run()

    with pytest.raises(KeyError, match="Run not found"):
        store.save_run(run)
