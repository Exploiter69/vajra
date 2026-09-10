from __future__ import annotations

from datetime import datetime, timezone

import pytest

from vajra.control.contracts import (
    DivergenceClass,
    ReconciliationDisposition,
)
from vajra.control.controller import (
    Controller,
    ControllerAction,
)
from vajra.domain import EngineeringRun, RunState


def make_run(state: RunState) -> EngineeringRun:
    now = datetime.now(timezone.utc)
    return EngineeringRun(
        run_id="controller-run",
        created_at=now,
        updated_at=now,
        objective="test objective",
        repository_id="repo-001",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="policy-1",
        policy_version="1",
        budget_id="budget-1",
        state=state,
    )


@pytest.mark.parametrize(
    ("state", "action", "target"),
    [
        (RunState.CREATED, ControllerAction.NOOP, RunState.QUEUED),
        (RunState.QUEUED, ControllerAction.ORIENT, RunState.ORIENTING),
        (RunState.ORIENTING, ControllerAction.PLAN, RunState.PLANNING),
        (RunState.PLANNING, ControllerAction.EXECUTE, RunState.EXECUTING),
        (RunState.EXECUTING, ControllerAction.VERIFY, RunState.VERIFYING),
        (RunState.VERIFYING, ControllerAction.NOOP, RunState.CANDIDATE),
        (RunState.CANDIDATE, ControllerAction.NOOP, RunState.PROMOTION),
    ],
)
def test_controller_progression(
    state: RunState,
    action: ControllerAction,
    target: RunState,
) -> None:
    controller = Controller()
    decision = controller.decide(make_run(state))

    assert decision.action is action
    assert decision.target_state is target


def test_controller_cannot_complete_run() -> None:
    controller = Controller()
    decision = controller.decide(make_run(RunState.PROMOTION))

    assert decision.action is ControllerAction.NOOP
    assert decision.target_state is None


def test_controller_does_not_mutate_run() -> None:
    controller = Controller()
    run = make_run(RunState.CREATED)

    controller.decide(run)

    assert run.state is RunState.CREATED


def test_budget_divergence_aborts() -> None:
    controller = Controller()

    decision = controller.decide(
        make_run(RunState.EXECUTING),
        divergence=DivergenceClass.BUDGET_DIVERGENCE,
    )

    assert decision.action is ControllerAction.ABORT
    assert decision.target_state is RunState.ABORTED


def test_ownership_divergence_waits_for_human() -> None:
    controller = Controller()

    decision = controller.decide(
        make_run(RunState.EXECUTING),
        divergence=DivergenceClass.OWNERSHIP_DIVERGENCE,
    )

    assert decision.action is ControllerAction.WAIT_HUMAN
    assert decision.target_state is RunState.WAITING_HUMAN


def test_verification_divergence_requires_verification() -> None:
    controller = Controller()

    decision = controller.decide(
        make_run(RunState.EXECUTING),
        divergence=DivergenceClass.VERIFICATION_DIVERGENCE,
    )

    assert decision.action is ControllerAction.VERIFY
    assert decision.target_state is RunState.VERIFYING


def test_reconciliation_recovery_is_not_normal_progression() -> None:
    controller = Controller()

    decision = controller.decide(
        make_run(RunState.EXECUTING),
        reconciliation=ReconciliationDisposition.RECOVERABLE,
    )

    assert decision.action is ControllerAction.RECOVER
    assert decision.target_state is RunState.RECOVERING


def test_controller_decision_must_respect_transition_authority() -> None:
    controller = Controller()

    decision = controller.decide(make_run(RunState.PROMOTION))

    controller.authorize_decision(
        make_run(RunState.PROMOTION),
        decision,
    )


def test_terminal_runs_are_noop() -> None:
    controller = Controller()

    for state in (
        RunState.COMPLETE,
        RunState.ABORTED,
        RunState.EXPIRED,
    ):
        decision = controller.decide(make_run(state))
        assert decision.action is ControllerAction.NOOP
        assert decision.target_state is None


def test_invalid_run_id_is_rejected() -> None:
    controller = Controller()
    run = make_run(RunState.CREATED)
    run.run_id = ""

    with pytest.raises(ValueError):
        controller.decide(run)
