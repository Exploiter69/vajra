from datetime import datetime, timezone

import pytest

from vajra.domain import (
    EngineeringRun,
    RunState,
    transition_run,
)


def make_run() -> EngineeringRun:
    return EngineeringRun(
        run_id="run-001",
        objective="Implement a verified feature",
        repository_id="repo-001",
        base_revision="abc123",
        acceptance_criteria=("tests pass", "build succeeds"),
        policy_id="default",
        policy_version="1",
        budget_id="budget-001",
        created_by="human",
    )


def test_run_starts_created():
    run = make_run()

    assert run.state is RunState.CREATED
    assert run.run_id == "run-001"
    assert run.objective == "Implement a verified feature"


def test_valid_lifecycle_transition():
    run = make_run()

    transition_run(run, RunState.QUEUED)
    transition_run(run, RunState.ORIENTING)
    transition_run(run, RunState.PLANNING)
    transition_run(run, RunState.EXECUTING)
    transition_run(run, RunState.VERIFYING)
    transition_run(run, RunState.CANDIDATE)
    transition_run(run, RunState.PROMOTION)
    transition_run(run, RunState.COMPLETE)

    assert run.state is RunState.COMPLETE
    assert run.updated_at.tzinfo == timezone.utc


def test_invalid_transition_is_rejected():
    run = make_run()

    with pytest.raises(ValueError, match="invalid Run transition"):
        transition_run(run, RunState.COMPLETE)


def test_terminal_run_cannot_transition():
    run = make_run()
    transition_run(run, RunState.QUEUED)
    transition_run(run, RunState.ORIENTING)
    transition_run(run, RunState.PLANNING)
    transition_run(run, RunState.EXECUTING)
    transition_run(run, RunState.VERIFYING)
    transition_run(run, RunState.CANDIDATE)
    transition_run(run, RunState.PROMOTION)
    transition_run(run, RunState.COMPLETE)

    with pytest.raises(ValueError):
        transition_run(run, RunState.RECOVERING)
