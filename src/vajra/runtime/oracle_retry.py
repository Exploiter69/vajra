from __future__ import annotations

from dataclasses import dataclass

from vajra.domain import Attempt
from vajra.recovery.actions import RetryRecoveryHandler, RetryRequest
from vajra.recovery.contracts import Failure, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class OracleRetryRequest:
    """Oracle-authorized inputs for creating a replacement attempt."""

    worker_id: str
    lease_id: str
    lease_ttl_seconds: int = 60


class OracleRetryCoordinator:
    """
    Oracle-side retry integration.

    The coordinator creates a new Attempt through the existing recovery
    handler. It does not execute work or dispatch a WorkerJob.
    """

    def __init__(self, run_manager: RunManager) -> None:
        self._handler = RetryRecoveryHandler(run_manager)

    def retry(
        self,
        failure: Failure,
        decision: RecoveryDecision,
        *,
        request: OracleRetryRequest,
    ) -> Attempt:
        if decision.action is not RecoveryAction.RETRY:
            raise ValueError(
                "OracleRetryCoordinator requires a RETRY decision"
            )

        return self._handler(
            failure,
            decision,
            request=RetryRequest(
                worker_id=request.worker_id,
                lease_id=request.lease_id,
                lease_ttl_seconds=request.lease_ttl_seconds,
            ),
        )
