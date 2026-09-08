from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from vajra.domain import Budget, EngineeringRun, RunState
from vajra.recovery.budget import (
    BudgetEnforcer,
    BudgetUsage,
)
from vajra.recovery.contracts import FailureCategory


def make_run(
    *,
    run_id: str = "run-1",
    created_at: datetime | None = None,
    current_step_id: str | None = "step-1",
) -> EngineeringRun:
    return EngineeringRun(
        run_id=run_id,
        objective="test objective",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="policy-1",
        policy_version="1",
        budget_id="budget-1",
        state=RunState.EXECUTING,
        current_step_id=current_step_id,
        created_at=created_at or datetime.now(timezone.utc),
    )


def make_budget(**overrides: int) -> Budget:
    values = {
        "max_runtime_seconds": 100,
        "max_steps": 10,
        "max_attempts": 10,
        "max_model_calls": 10,
        "max_command_count": 10,
        "max_output_size": 1000,
        "max_worker_runtime_seconds": 100,
    }
    values.update(overrides)

    return Budget(
        budget_id="budget-1",
        **values,
    )


def add_attempt(run: EngineeringRun) -> None:
    from vajra.domain import Attempt, AttemptState, Step, StepState

    step = Step(
        step_id="step-1",
        run_id=run.run_id,
        name="work",
        state=StepState.RUNNING,
    )
    step.attempts.append(
        Attempt(
            attempt_id="attempt-1",
            step_id="step-1",
            run_id=run.run_id,
            state=AttemptState.RUNNING,
        )
    )
    run.steps.append(step)


def test_budget_passes_when_usage_is_below_limits() -> None:
    run = make_run()
    budget = make_budget()

    assessment = BudgetEnforcer().assess(
        run,
        budget,
        BudgetUsage(
            model_calls=2,
            command_count=3,
            output_size=100,
            worker_runtime_seconds=5,
        ),
    )

    assert not assessment.exhausted
    assert assessment.violations == ()


@pytest.mark.parametrize(
    ("field", "value", "resource"),
    [
        ("model_calls", 10, "model_calls"),
        ("command_count", 10, "command_count"),
        ("output_size", 1000, "output_size"),
        ("worker_runtime_seconds", 100, "worker_runtime_seconds"),
    ],
)
def test_usage_limit_is_exhausted(
    field: str,
    value: int,
    resource: str,
) -> None:
    run = make_run()
    budget = make_budget()

    usage = BudgetUsage(**{field: value})

    assessment = BudgetEnforcer().assess(
        run,
        budget,
        usage,
    )

    assert assessment.exhausted
    assert [(v.resource, v.observed) for v in assessment.violations] == [
        (resource, value)
    ]


def test_step_limit_is_derived_from_run_state() -> None:
    run = make_run()
    budget = make_budget(max_steps=1)

    from vajra.domain import Step

    run.steps.append(
        Step(
            step_id="step-1",
            run_id=run.run_id,
            name="work",
        )
    )

    assessment = BudgetEnforcer().assess(run, budget)

    assert assessment.exhausted
    assert assessment.violations[0].resource == "steps"


def test_attempt_limit_is_derived_from_run_state() -> None:
    run = make_run()
    budget = make_budget(max_attempts=1)
    add_attempt(run)

    assessment = BudgetEnforcer().assess(run, budget)

    assert assessment.exhausted
    assert assessment.violations[0].resource == "attempts"


def test_runtime_limit_uses_run_creation_time() -> None:
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    now = created + timedelta(seconds=100)

    run = make_run(created_at=created)
    budget = make_budget(max_runtime_seconds=100)

    assessment = BudgetEnforcer().assess(
        run,
        budget,
        now=now,
    )

    assert assessment.exhausted
    assert assessment.violations[0].resource == "runtime_seconds"
    assert assessment.violations[0].observed == 100


def test_multiple_limits_are_reported_together() -> None:
    run = make_run()
    budget = make_budget(
        max_model_calls=1,
        max_command_count=1,
        max_output_size=1,
    )

    assessment = BudgetEnforcer().assess(
        run,
        budget,
        BudgetUsage(
            model_calls=2,
            command_count=2,
            output_size=2,
        ),
    )

    assert assessment.exhausted
    assert [v.resource for v in assessment.violations] == [
        "model_calls",
        "command_count",
        "output_size",
    ]


def test_failure_is_resource_exhaustion() -> None:
    run = make_run()
    budget = make_budget(max_command_count=1)

    failure = BudgetEnforcer().failure(
        run,
        budget,
        BudgetUsage(command_count=1),
        failure_id="failure-1",
    )

    assert failure is not None
    assert failure.category is FailureCategory.RESOURCE_EXHAUSTION
    assert failure.failure_id == "failure-1"
    assert failure.run_id == run.run_id
    assert failure.details is not None
    assert failure.details["violations"][0]["resource"] == "command_count"


def test_failure_is_not_emitted_when_budget_is_available() -> None:
    run = make_run()
    budget = make_budget()

    failure = BudgetEnforcer().failure(
        run,
        budget,
        BudgetUsage(),
        failure_id="failure-1",
    )

    assert failure is None


def test_failure_uses_current_attempt_when_available() -> None:
    run = make_run()
    budget = make_budget(max_attempts=1)
    add_attempt(run)

    failure = BudgetEnforcer().failure(
        run,
        budget,
        failure_id="failure-1",
    )

    assert failure is not None
    assert failure.attempt_id == "attempt-1"


def test_budget_id_mismatch_is_rejected() -> None:
    run = make_run()
    budget = Budget(
        budget_id="other-budget",
        max_runtime_seconds=100,
        max_steps=10,
        max_attempts=10,
        max_model_calls=10,
        max_command_count=10,
        max_output_size=1000,
        max_worker_runtime_seconds=100,
    )

    with pytest.raises(ValueError, match="does not belong"):
        BudgetEnforcer().assess(run, budget)


def test_negative_usage_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        BudgetUsage(command_count=-1)
