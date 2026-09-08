from __future__ import annotations

from .models import EngineeringRun, RunState


ALLOWED_TRANSITIONS: dict[RunState, frozenset[RunState]] = {
    RunState.CREATED: frozenset({RunState.QUEUED, RunState.ABORTED}),
    RunState.QUEUED: frozenset({RunState.ORIENTING, RunState.PAUSED, RunState.ABORTED}),
    RunState.ORIENTING: frozenset({RunState.PLANNING, RunState.RECOVERING, RunState.WAITING_HUMAN}),
    RunState.PLANNING: frozenset({RunState.EXECUTING, RunState.RECOVERING, RunState.WAITING_HUMAN}),
    RunState.EXECUTING: frozenset({
        RunState.VERIFYING,
        RunState.RECOVERING,
        RunState.WAITING_HUMAN,
        RunState.FAILED,
    }),
    RunState.VERIFYING: frozenset({
        RunState.CANDIDATE,
        RunState.RECOVERING,
        RunState.FAILED,
    }),
    RunState.CANDIDATE: frozenset({RunState.PROMOTION, RunState.FAILED, RunState.WAITING_HUMAN}),
    RunState.PROMOTION: frozenset({RunState.COMPLETE, RunState.FAILED, RunState.WAITING_HUMAN}),

    RunState.RECOVERING: frozenset({
        RunState.QUEUED,
        RunState.ORIENTING,
        RunState.PLANNING,
        RunState.EXECUTING,
        RunState.VERIFYING,
        RunState.FAILED,
        RunState.WAITING_HUMAN,
        RunState.ABORTED,
    }),
    RunState.PAUSED: frozenset({RunState.QUEUED, RunState.ABORTED}),
    RunState.WAITING_HUMAN: frozenset({
        RunState.QUEUED,
        RunState.ORIENTING,
        RunState.PLANNING,
        RunState.EXECUTING,
        RunState.FAILED,
        RunState.ABORTED,
    }),
    RunState.FAILED: frozenset({RunState.RECOVERING, RunState.ABORTED}),
    RunState.ABORTED: frozenset(),
    RunState.EXPIRED: frozenset(),
    RunState.COMPLETE: frozenset(),
}


def transition_run(run: EngineeringRun, target: RunState) -> None:
    allowed = ALLOWED_TRANSITIONS[run.state]

    if target not in allowed:
        raise ValueError(
            f"invalid Run transition: {run.state.value} -> {target.value}"
        )

    run.state = target
    run.updated_at = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
