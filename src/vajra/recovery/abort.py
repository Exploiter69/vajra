from __future__ import annotations

from dataclasses import dataclass

from vajra.domain import FinalDisposition, RunState
from vajra.recovery.contracts import Failure, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class AbortRecoveryRequest:
    """Record describing a recovery decision that permanently aborts a run."""

    failure_id: str
    run_id: str
    step_id: str
    attempt_id: str
    reason: str


class AbortRecoveryHandler:
    """
    Concrete ABORT recovery boundary.

    The handler delegates canonical lifecycle mutation to RunManager. It does
    not execute external work or attempt any further recovery.
    """

    def __init__(self, run_manager: RunManager) -> None:
        self._run_manager = run_manager

    def __call__(
        self,
        failure: Failure,
        decision: RecoveryDecision,
    ) -> AbortRecoveryRequest:
        if decision.action is not RecoveryAction.ABORT:
            raise ValueError(
                "AbortRecoveryHandler requires an ABORT decision"
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

        self._run_manager.abort_run(
            failure.run_id,
            decision.reason,
        )

        aborted = self._run_manager.get_run(failure.run_id)

        if aborted.state is not RunState.ABORTED:
            raise RuntimeError("Run was not aborted")

        if aborted.final_disposition is not FinalDisposition.ABORTED:
            raise RuntimeError(
                "Aborted run does not have ABORTED final disposition"
            )

        return AbortRecoveryRequest(
            failure_id=failure.failure_id,
            run_id=failure.run_id,
            step_id=failure.step_id,
            attempt_id=failure.attempt_id,
            reason=decision.reason,
        )
