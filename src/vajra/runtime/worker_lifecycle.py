from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from vajra.domain import AttemptState, EngineeringRun, RunState
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class WorkerDisappearance:
    run_id: str
    step_id: str
    attempt_id: str
    worker_id: str
    reason: str = "worker disappeared"


class WorkerDisappearanceDetector:
    """
    Oracle-side detection boundary for disposable worker loss.

    Worker liveness is inferred from the VAJRA-owned lease authority. The
    detector mutates canonical Run state only through RunManager.
    """

    def __init__(self, manager: RunManager) -> None:
        self._manager = manager

    def detect(
        self,
        disappearance: WorkerDisappearance,
        *,
        now: datetime | None = None,
    ) -> EngineeringRun:
        current_time = now or datetime.now(timezone.utc)

        run = self._manager.get_run(disappearance.run_id)

        step = next(
            (
                step
                for step in run.steps
                if step.step_id == disappearance.step_id
            ),
            None,
        )
        if step is None:
            raise KeyError(f"Step not found: {disappearance.step_id}")

        attempt = next(
            (
                attempt
                for attempt in step.attempts
                if attempt.attempt_id == disappearance.attempt_id
            ),
            None,
        )
        if attempt is None:
            raise KeyError(f"Attempt not found: {disappearance.attempt_id}")

        if attempt.state is not AttemptState.RUNNING:
            raise ValueError(
                f"Attempt is not running: {attempt.attempt_id}"
            )

        if attempt.worker_id != disappearance.worker_id:
            raise PermissionError("Worker does not match attempt owner")

        lease = self._manager.get_lease(disappearance.attempt_id)

        lease_lost = (
            lease is None
            or current_time >= lease.lease_expiry
        )

        if not lease_lost:
            raise ValueError(
                f"Worker lease is still active: {disappearance.attempt_id}"
            )

        self._manager.fail_attempt(
            disappearance.run_id,
            disappearance.step_id,
            disappearance.attempt_id,
            disappearance.reason,
        )

        return self._manager.recover_run(disappearance.run_id)


__all__ = [
    "WorkerDisappearance",
    "WorkerDisappearanceDetector",
]
