from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from vajra.domain import Attempt, RunState
from vajra.recovery.contracts import Failure, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class RetryRequest:
    """Explicit inputs required to create a replacement attempt."""

    worker_id: str
    lease_id: str
    lease_ttl_seconds: int = 60


class RetryRecoveryHandler:
    """
    Concrete RETRY recovery action.

    Recovery creates a new Attempt rather than mutating or reusing the failed
    Attempt. Worker selection and lease identity are supplied explicitly;
    recovery does not become a worker-selection authority.
    """

    def __init__(self, run_manager: RunManager) -> None:
        self._run_manager = run_manager

    def __call__(
        self,
        failure: Failure,
        decision: RecoveryDecision,
        *,
        request: RetryRequest,
    ) -> Attempt:
        if decision.action is not RecoveryAction.RETRY:
            raise ValueError(
                "RetryRecoveryHandler requires a RETRY decision"
            )

        if failure.failure_id != decision.failure_id:
            raise ValueError("Recovery decision does not match failure")

        run = self._run_manager.get_run(failure.run_id)

        if run.state is not RunState.RECOVERING:
            raise ValueError(
                f"Run is not recovering: {failure.run_id}"
            )

        step = next(
            (
                candidate
                for candidate in run.steps
                if candidate.step_id == failure.step_id
            ),
            None,
        )
        if step is None:
            raise KeyError(f"Unknown step: {failure.step_id}")

        attempt = next(
            (
                candidate
                for candidate in step.attempts
                if candidate.attempt_id == failure.attempt_id
            ),
            None,
        )
        if attempt is None:
            raise KeyError(f"Unknown attempt: {failure.attempt_id}")

        if attempt.state.value != "FAILED":
            raise ValueError(
                f"Attempt is not failed: {failure.attempt_id}"
            )

        new_attempt_id = str(uuid4())

        return self._run_manager.start_attempt(
            failure.run_id,
            failure.step_id,
            new_attempt_id,
            request.worker_id,
            request.lease_id,
            lease_ttl_seconds=request.lease_ttl_seconds,
        )
