from __future__ import annotations

from dataclasses import dataclass

from vajra.domain import RunState
from vajra.recovery.contracts import Failure, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class HumanApprovalRequest:
    """Durable description of a decision that requires human authority."""

    failure_id: str
    run_id: str
    step_id: str
    attempt_id: str
    reason: str


class RequestHumanRecoveryHandler:
    """
    Concrete REQUEST_HUMAN recovery boundary.

    The handler places the run into WAITING_HUMAN and returns an explicit
    approval request. It does not approve the request or execute any action.
    """

    def __init__(self, run_manager: RunManager) -> None:
        self._run_manager = run_manager

    def __call__(
        self,
        failure: Failure,
        decision: RecoveryDecision,
    ) -> HumanApprovalRequest:
        if decision.action is not RecoveryAction.REQUEST_HUMAN:
            raise ValueError(
                "RequestHumanRecoveryHandler requires a REQUEST_HUMAN decision"
            )

        if (
            failure.failure_id != decision.failure_id
            or failure.run_id != decision.run_id
            or failure.step_id != decision.step_id
            or failure.attempt_id != decision.attempt_id
        ):
            raise ValueError("Recovery decision does not match failure")

        run = self._run_manager.get_run(failure.run_id)

        if run.state is not RunState.RECOVERING:
            raise ValueError(
                f"Run is not recovering: {failure.run_id}"
            )

        self._run_manager.transition(
            failure.run_id,
            RunState.WAITING_HUMAN,
        )

        return HumanApprovalRequest(
            failure_id=failure.failure_id,
            run_id=failure.run_id,
            step_id=failure.step_id,
            attempt_id=failure.attempt_id,
            reason=decision.reason,
        )
