from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from vajra.domain import RunState
from vajra.recovery.contracts import Failure, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class WorkerChangeRequest:
    """
    Explicit request to change the worker used for a future attempt.

    Worker selection is supplied by the caller. Recovery does not acquire a
    lease, spawn a worker, or execute work.
    """

    worker_id: str
    reason: str


WorkerSelector = Callable[
    [Failure, RecoveryDecision],
    WorkerChangeRequest,
]


class ChangeWorkerRecoveryHandler:
    """
    Concrete CHANGE_WORKER recovery boundary.

    The handler validates recovery state and delegates worker selection to an
    explicitly supplied selector. It does not acquire a lease or execute the
    selected worker.
    """

    def __init__(
        self,
        run_manager: RunManager,
        selector: WorkerSelector,
    ) -> None:
        self._run_manager = run_manager
        self._selector = selector

    def __call__(
        self,
        failure: Failure,
        decision: RecoveryDecision,
    ) -> WorkerChangeRequest:
        if decision.action is not RecoveryAction.CHANGE_WORKER:
            raise ValueError(
                "ChangeWorkerRecoveryHandler requires a CHANGE_WORKER decision"
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

        request = self._selector(failure, decision)

        if not request.worker_id:
            raise ValueError("worker_id must not be empty")

        if not request.reason:
            raise ValueError("worker reason must not be empty")

        return request
