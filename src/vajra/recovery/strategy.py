from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from vajra.domain import RunState
from vajra.recovery.contracts import Failure, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class StrategyChangeRequest:
    """
    Explicit request for a new execution strategy.

    Strategy selection is supplied by the caller. Recovery does not perform
    model reasoning or invent a strategy.
    """

    strategy_id: str
    reason: str


StrategySelector = Callable[
    [Failure, RecoveryDecision],
    StrategyChangeRequest,
]


class NewStrategyRecoveryHandler:
    """
    Concrete NEW_STRATEGY recovery boundary.

    The handler validates recovery state and delegates strategy selection to
    an explicitly supplied selector. It does not execute the new strategy.
    """

    def __init__(
        self,
        run_manager: RunManager,
        selector: StrategySelector,
    ) -> None:
        self._run_manager = run_manager
        self._selector = selector

    def __call__(
        self,
        failure: Failure,
        decision: RecoveryDecision,
    ) -> StrategyChangeRequest:
        if decision.action is not RecoveryAction.NEW_STRATEGY:
            raise ValueError(
                "NewStrategyRecoveryHandler requires a NEW_STRATEGY decision"
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

        if not request.strategy_id:
            raise ValueError("strategy_id must not be empty")

        if not request.reason:
            raise ValueError("strategy reason must not be empty")

        return request
