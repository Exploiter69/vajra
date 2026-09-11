from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from vajra.control.contracts import DivergenceClass
from vajra.control.limits import BoundedAutonomy, LimitAction
from vajra.domain import Budget, EngineeringRun, RunState
from vajra.recovery.budget import BudgetUsage
from vajra.recovery.progress import ProgressObservation


def make_run() -> EngineeringRun:
    now = datetime.now(timezone.utc)
    return EngineeringRun(
        run_id="limits-run",
        created_at=now,
        updated_at=now,
        objective="test objective",
        repository_id="repo-001",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="policy-1",
        policy_version="1",
        budget_id="budget-1",
        state=RunState.EXECUTING,
    )


def make_budget(**overrides: int) -> Budget:
    values = {
        "budget_id": "budget-1",
        "max_runtime_seconds": 300,
        "max_steps": 10,
        "max_attempts": 20,
        "max_model_calls": 20,
        "max_command_count": 100,
        "max_output_size": 10000,
        "max_worker_runtime_seconds": 300,
    }
    values.update(overrides)
    return Budget(**values)


def make_progress() -> ProgressObservation:
    return ProgressObservation(
        run_id="limits-run",
        step_id="step-1",
        attempt_id="attempt-1",
        state_digest="state-a",
        git_revision="abc123",
        patch_digest="patch-a",
        test_signature="tests-a",
        error_signature=None,
    )


def test_continuation_is_allowed_within_limits() -> None:
    decision = BoundedAutonomy().assess(
        make_run(),
        make_budget(),
        BudgetUsage(),
        progress=make_progress(),
    )

    assert decision.action is LimitAction.CONTINUE
    assert decision.divergence is DivergenceClass.NONE
    assert decision.progress is not None
    assert decision.progress.repetition_count == 1


def test_budget_exhaustion_is_hard_abort() -> None:
    decision = BoundedAutonomy().assess(
        make_run(),
        make_budget(max_model_calls=1),
        BudgetUsage(model_calls=1),
        progress=make_progress(),
    )

    assert decision.action is LimitAction.ABORT
    assert decision.divergence is DivergenceClass.BUDGET_DIVERGENCE
    assert decision.budget.exhausted


def test_budget_wins_over_no_progress() -> None:
    controller = BoundedAutonomy()

    for _ in range(3):
        decision = controller.assess(
            make_run(),
            make_budget(max_model_calls=1),
            BudgetUsage(model_calls=1),
            progress=make_progress(),
        )

    assert decision.action is LimitAction.ABORT
    assert decision.divergence is DivergenceClass.BUDGET_DIVERGENCE


def test_repeated_progress_observation_escalates() -> None:
    controller = BoundedAutonomy()

    decisions = [
        controller.assess(
            make_run(),
            make_budget(),
            progress=make_progress(),
        )
        for _ in range(3)
    ]

    assert decisions[0].action is LimitAction.CONTINUE
    assert decisions[1].action is LimitAction.CONTINUE
    assert decisions[2].action is LimitAction.WAIT_HUMAN
    assert decisions[2].progress is not None
    assert decisions[2].progress.no_progress


def test_progress_is_optional() -> None:
    decision = BoundedAutonomy().assess(
        make_run(),
        make_budget(),
    )

    assert decision.action is LimitAction.CONTINUE
    assert decision.progress is None


def test_budget_belongs_to_run() -> None:
    with pytest.raises(ValueError):
        BoundedAutonomy().assess(
            make_run(),
            Budget(
                budget_id="wrong-budget",
                max_runtime_seconds=300,
                max_steps=10,
                max_attempts=20,
                max_model_calls=20,
                max_command_count=100,
                max_output_size=10000,
                max_worker_runtime_seconds=300,
            ),
        )


def test_strategy_loop_escalates_to_human() -> None:
    controller = BoundedAutonomy()

    decisions = [
        controller.assess(
            make_run(),
            make_budget(),
            strategy_id="strategy-a",
        )
        for _ in range(2)
    ]

    assert decisions[0].action is LimitAction.CONTINUE
    assert decisions[1].action is LimitAction.WAIT_HUMAN
    assert decisions[1].strategy is not None
    assert decisions[1].strategy.repeated


def test_strategy_oscillation_escalates_to_human() -> None:
    controller = BoundedAutonomy()

    decisions = [
        controller.assess(
            make_run(),
            make_budget(),
            strategy_id=strategy,
        )
        for strategy in ("strategy-a", "strategy-b", "strategy-a")
    ]

    assert decisions[-1].action is LimitAction.WAIT_HUMAN
    assert decisions[-1].strategy is not None
    assert decisions[-1].strategy.oscillating


def test_budget_beats_strategy_loop() -> None:
    controller = BoundedAutonomy()

    for _ in range(2):
        decision = controller.assess(
            make_run(),
            make_budget(max_model_calls=1),
            BudgetUsage(model_calls=1),
            strategy_id="strategy-a",
        )

    assert decision.action is LimitAction.ABORT
    assert decision.divergence is DivergenceClass.BUDGET_DIVERGENCE
