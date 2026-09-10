from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vajra.domain import EngineeringRun, RunState
from vajra.domain.transitions import ALLOWED_TRANSITIONS


class TransitionAuthorityError(ValueError):
    """Base error for transition-authority violations."""


class TransitionDenied(TransitionAuthorityError):
    """Raised when an otherwise structurally possible transition is not authorized."""


class TransitionActor(str, Enum):
    SYSTEM = "SYSTEM"
    CONTROLLER = "CONTROLLER"
    RECOVERY = "RECOVERY"
    HUMAN = "HUMAN"


@dataclass(frozen=True)
class TransitionRequest:
    run_id: str
    from_state: RunState
    to_state: RunState
    actor: TransitionActor
    reason: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("run_id", self.run_id),
            ("reason", self.reason),
        ):
            if not value.strip() and name != "reason":
                raise TransitionAuthorityError(f"{name} must be nonempty")

        if not isinstance(self.actor, TransitionActor):
            raise TransitionAuthorityError("actor must be a TransitionActor")


@dataclass(frozen=True)
class TransitionDecision:
    request: TransitionRequest
    allowed: bool
    reason: str


class TransitionAuthority:
    """
    Pure canonical Run transition authority.

    This layer decides whether a transition may occur.
    It does not mutate Runs, persist state, emit events, execute commands,
    call models, or communicate with workers.

    Structural transition legality remains owned by domain.transitions.
    """

    def authorize(
        self,
        run: EngineeringRun,
        target: RunState,
        actor: TransitionActor,
        *,
        reason: str = "",
    ) -> TransitionDecision:
        request = TransitionRequest(
            run_id=run.run_id,
            from_state=run.state,
            to_state=target,
            actor=actor,
            reason=reason,
        )

        if target not in ALLOWED_TRANSITIONS[run.state]:
            raise TransitionDenied(
                f"invalid Run transition: "
                f"{run.state.value} -> {target.value}"
            )

        if run.state in {RunState.COMPLETE, RunState.ABORTED, RunState.EXPIRED}:
            raise TransitionDenied(
                f"terminal Run state cannot transition: {run.state.value}"
            )

        if target is RunState.COMPLETE:
            if actor not in {TransitionActor.SYSTEM, TransitionActor.HUMAN}:
                raise TransitionDenied(
                    "COMPLETE requires SYSTEM or HUMAN authority"
                )

        if target is RunState.ABORTED:
            if actor not in {TransitionActor.SYSTEM, TransitionActor.HUMAN, TransitionActor.RECOVERY}:
                raise TransitionDenied(
                    "ABORTED requires SYSTEM, HUMAN, or RECOVERY authority"
                )

        if target is RunState.RECOVERING:
            if actor not in {TransitionActor.SYSTEM, TransitionActor.RECOVERY, TransitionActor.CONTROLLER}:
                raise TransitionDenied(
                    "RECOVERING requires SYSTEM, RECOVERY, or CONTROLLER authority"
                )

        return TransitionDecision(
            request=request,
            allowed=True,
            reason=reason or "transition authorized",
        )

    def assert_authorized(
        self,
        run: EngineeringRun,
        target: RunState,
        actor: TransitionActor,
        *,
        reason: str = "",
    ) -> None:
        self.authorize(
            run,
            target,
            actor,
            reason=reason,
        )
