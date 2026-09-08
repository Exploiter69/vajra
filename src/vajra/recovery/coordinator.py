from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from vajra.domain import RunState
from vajra.recovery.contracts import Failure, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


RecoveryHandler = Callable[[Failure, RecoveryDecision], None]


@dataclass(frozen=True)
class RecoveryOutcome:
    """
    Result of one recovery-coordination decision.

    The coordinator reports what was dispatched. The handler owns the
    concrete recovery operation.
    """

    failure_id: str
    run_id: str
    step_id: str
    attempt_id: str
    action: RecoveryAction
    status: str


class RecoveryCoordinator:
    """
    Coordinates recovery without becoming an execution authority.

    Concrete recovery capabilities are supplied explicitly as handlers.
    The coordinator owns lifecycle sequencing and refuses unsupported
    recovery actions.
    """

    def __init__(
        self,
        run_manager: RunManager,
        handlers: dict[RecoveryAction, RecoveryHandler] | None = None,
    ) -> None:
        self._run_manager = run_manager
        self._handlers = dict(handlers or {})

    def register_handler(
        self,
        action: RecoveryAction,
        handler: RecoveryHandler,
    ) -> None:
        if action in self._handlers:
            raise ValueError(
                f"Recovery handler already registered: {action.value}"
            )

        self._handlers[action] = handler

    def coordinate(
        self,
        failure: Failure,
        decision: RecoveryDecision,
    ) -> RecoveryOutcome:
        self._validate_decision(failure, decision)

        run = self._run_manager.get_run(failure.run_id)

        if run.state is not RunState.RECOVERING:
            self._run_manager.recover_run(failure.run_id)

        handler = self._handlers.get(decision.action)

        if handler is None:
            raise RuntimeError(
                f"No recovery handler registered: {decision.action.value}"
            )

        handler(failure, decision)

        return RecoveryOutcome(
            failure_id=failure.failure_id,
            run_id=failure.run_id,
            step_id=failure.step_id,
            attempt_id=failure.attempt_id,
            action=decision.action,
            status="DISPATCHED",
        )

    @staticmethod
    def _validate_decision(
        failure: Failure,
        decision: RecoveryDecision,
    ) -> None:
        if failure.failure_id != decision.failure_id:
            raise ValueError(
                "Recovery decision does not match failure"
            )

        if failure.run_id != decision.run_id:
            raise ValueError(
                "Recovery decision run_id does not match failure"
            )

        if failure.step_id != decision.step_id:
            raise ValueError(
                "Recovery decision step_id does not match failure"
            )

        if failure.attempt_id != decision.attempt_id:
            raise ValueError(
                "Recovery decision attempt_id does not match failure"
            )
