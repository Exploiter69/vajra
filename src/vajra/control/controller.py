from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vajra.domain import EngineeringRun, RunState

from .contracts import (
    DivergenceClass,
    ReconciliationDisposition,
)
from .transition_authority import (
    TransitionActor,
    TransitionAuthority,
    TransitionDenied,
)


class ControllerError(ValueError):
    """Base error for controller violations."""


class ControllerAction(str, Enum):
    NOOP = "NOOP"
    ORIENT = "ORIENT"
    PLAN = "PLAN"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    RECOVER = "RECOVER"
    WAIT_HUMAN = "WAIT_HUMAN"
    ABORT = "ABORT"


@dataclass(frozen=True)
class ControllerDecision:
    run_id: str
    action: ControllerAction
    reason: str
    target_state: RunState | None = None


class Controller:
    """
    Bounded orchestration decision boundary.

    The controller decides what should happen next. It does not:
      - mutate Runs directly
      - execute commands
      - call models
      - authorize policy
      - perform verification
      - manufacture evidence
      - declare completion

    Transition authority remains the sole authority for state-transition
    authorization.
    """

    def __init__(
        self,
        transition_authority: TransitionAuthority | None = None,
    ) -> None:
        self._transition_authority = (
            transition_authority or TransitionAuthority()
        )

    def decide(
        self,
        run: EngineeringRun,
        *,
        divergence: DivergenceClass = DivergenceClass.NONE,
        reconciliation: ReconciliationDisposition = (
            ReconciliationDisposition.CONSISTENT
        ),
    ) -> ControllerDecision:
        if not run.run_id.strip():
            raise ControllerError("run_id must be nonempty")

        # External reality takes precedence over optimistic continuation.
        if divergence is DivergenceClass.BUDGET_DIVERGENCE:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.ABORT,
                reason="budget divergence requires termination",
                target_state=RunState.ABORTED,
            )

        if divergence is DivergenceClass.OWNERSHIP_DIVERGENCE:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.WAIT_HUMAN,
                reason="ownership divergence requires human authority",
                target_state=RunState.WAITING_HUMAN,
            )

        if divergence is DivergenceClass.VERIFICATION_DIVERGENCE:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.VERIFY,
                reason="verification reality diverged; re-verification required",
                target_state=RunState.VERIFYING,
            )

        if reconciliation is ReconciliationDisposition.WAITING_HUMAN:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.WAIT_HUMAN,
                reason="reconciliation requires human authority",
                target_state=RunState.WAITING_HUMAN,
            )

        if reconciliation is ReconciliationDisposition.ABORT:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.ABORT,
                reason="reconciliation requires termination",
                target_state=RunState.ABORTED,
            )

        if reconciliation in {
            ReconciliationDisposition.REVERIFY,
            ReconciliationDisposition.RECOVERABLE,
            ReconciliationDisposition.RECOVERING,
        }:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.RECOVER,
                reason="reality requires recovery/reverification",
                target_state=RunState.RECOVERING,
            )

        if run.state is RunState.CREATED:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.NOOP,
                reason="run must be queued before controller work begins",
                target_state=RunState.QUEUED,
            )

        if run.state is RunState.QUEUED:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.ORIENT,
                reason="queued run requires orientation",
                target_state=RunState.ORIENTING,
            )

        if run.state is RunState.ORIENTING:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.PLAN,
                reason="orientation complete; planning is next",
                target_state=RunState.PLANNING,
            )

        if run.state is RunState.PLANNING:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.EXECUTE,
                reason="planning complete; execution is next",
                target_state=RunState.EXECUTING,
            )

        if run.state is RunState.EXECUTING:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.VERIFY,
                reason="execution requires external verification",
                target_state=RunState.VERIFYING,
            )

        if run.state is RunState.VERIFYING:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.NOOP,
                reason="verification must determine whether candidate criteria are satisfied",
                target_state=RunState.CANDIDATE,
            )

        if run.state is RunState.CANDIDATE:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.NOOP,
                reason="candidate requires promotion authority",
                target_state=RunState.PROMOTION,
            )

        if run.state is RunState.PROMOTION:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.NOOP,
                reason="controller cannot declare completion",
                target_state=None,
            )

        if run.state is RunState.RECOVERING:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.RECOVER,
                reason="run remains in recovery",
                target_state=None,
            )

        if run.state is RunState.WAITING_HUMAN:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.WAIT_HUMAN,
                reason="waiting for human authority",
                target_state=None,
            )

        if run.state in {
            RunState.FAILED,
            RunState.PAUSED,
        }:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.NOOP,
                reason=f"run requires an explicit external recovery/resume action from {run.state.value}",
                target_state=None,
            )

        if run.state in {
            RunState.COMPLETE,
            RunState.ABORTED,
            RunState.EXPIRED,
        }:
            return ControllerDecision(
                run_id=run.run_id,
                action=ControllerAction.NOOP,
                reason=f"terminal run state: {run.state.value}",
                target_state=None,
            )

        raise ControllerError(f"unsupported Run state: {run.state}")

    def authorize_decision(
        self,
        run: EngineeringRun,
        decision: ControllerDecision,
    ) -> None:
        """
        Validate a controller-requested transition through canonical
        TransitionAuthority.

        This method still does not mutate the Run.
        """
        if decision.target_state is None:
            return

        self._transition_authority.assert_authorized(
            run,
            decision.target_state,
            TransitionActor.CONTROLLER,
            reason=decision.reason,
        )
