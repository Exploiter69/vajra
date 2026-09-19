from __future__ import annotations

from datetime import datetime, timezone

import pytest

from vajra.control.transition_authority import (
    TransitionActor,
    TransitionAuthority,
    TransitionDenied,
    TransitionRequest,
)
from vajra.domain import EngineeringRun, RunState


def make_run(state: RunState = RunState.CREATED) -> EngineeringRun:
    now = datetime.now(timezone.utc)
    return EngineeringRun(
        run_id="run-authority",
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


def test_authorizes_structurally_valid_transition() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.CREATED)

    decision = authority.authorize(
        run,
        RunState.QUEUED,
        TransitionActor.CONTROLLER,
        reason="dispatch run",
    )

    assert decision.allowed is True
    assert decision.request.run_id == run.run_id
    assert decision.request.from_state is RunState.CREATED
    assert decision.request.to_state is RunState.QUEUED
    assert decision.request.actor is TransitionActor.CONTROLLER


def test_rejects_invalid_domain_transition() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.CREATED)

    with pytest.raises(TransitionDenied, match="invalid Run transition"):
        authority.authorize(
            run,
            RunState.COMPLETE,
            TransitionActor.SYSTEM,
        )


def test_controller_cannot_complete_run() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.PROMOTION)

    with pytest.raises(TransitionDenied, match="COMPLETE"):
        authority.authorize(
            run,
            RunState.COMPLETE,
            TransitionActor.CONTROLLER,
        )


def test_system_can_complete_run() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.PROMOTION)

    authority.assert_authorized(
        run,
        RunState.COMPLETE,
        TransitionActor.SYSTEM,
        reason="independent verification satisfied",
    )


def test_human_can_complete_run() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.PROMOTION)

    authority.assert_authorized(
        run,
        RunState.COMPLETE,
        TransitionActor.HUMAN,
    )


def test_controller_can_request_recovery() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.EXECUTING)

    authority.assert_authorized(
        run,
        RunState.RECOVERING,
        TransitionActor.CONTROLLER,
        reason="worker failure",
    )


def test_recovery_actor_can_abort() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.RECOVERING)

    authority.assert_authorized(
        run,
        RunState.ABORTED,
        TransitionActor.RECOVERY,
        reason="recovery exhausted",
    )


@pytest.mark.parametrize(
    "terminal_state",
    [
        RunState.COMPLETE,
        RunState.ABORTED,
        RunState.EXPIRED,
    ],
)
def test_terminal_states_are_not_reopened(
    terminal_state: RunState,
) -> None:
    authority = TransitionAuthority()
    run = make_run(terminal_state)

    with pytest.raises(TransitionDenied):
        authority.authorize(
            run,
            RunState.QUEUED,
            TransitionActor.SYSTEM,
        )


def test_authority_does_not_mutate_run() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.CREATED)

    before = run.state
    authority.authorize(
        run,
        RunState.QUEUED,
        TransitionActor.CONTROLLER,
    )

    assert run.state is before


def test_request_requires_run_id() -> None:
    with pytest.raises(Exception):
        TransitionRequest(
            run_id="",
            from_state=RunState.CREATED,
            to_state=RunState.QUEUED,
            actor=TransitionActor.SYSTEM,
        )


def test_controller_can_recover_candidate_after_failed_acceptance() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.CANDIDATE)

    authority.assert_authorized(
        run,
        RunState.RECOVERING,
        TransitionActor.CONTROLLER,
        reason="acceptance evaluation failed",
    )


def test_controller_can_escalate_verification_to_human() -> None:
    authority = TransitionAuthority()
    run = make_run(RunState.VERIFYING)

    authority.assert_authorized(
        run,
        RunState.WAITING_HUMAN,
        TransitionActor.CONTROLLER,
        reason="strategy loop threshold reached",
    )
