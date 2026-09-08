from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from vajra.domain import RunState
from vajra.recovery.contracts import Failure, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class ModelChangeRequest:
    """
    Explicit request to change the model used for a future attempt.

    Model selection is supplied by the caller. Recovery does not perform
    inference, contact a provider, or mutate execution state.
    """

    model_id: str
    reason: str


ModelSelector = Callable[
    [Failure, RecoveryDecision],
    ModelChangeRequest,
]


class ChangeModelRecoveryHandler:
    """
    Concrete CHANGE_MODEL recovery boundary.

    The handler validates recovery state and delegates model selection to an
    explicitly supplied selector. It does not execute the selected model.
    """

    def __init__(
        self,
        run_manager: RunManager,
        selector: ModelSelector,
    ) -> None:
        self._run_manager = run_manager
        self._selector = selector

    def __call__(
        self,
        failure: Failure,
        decision: RecoveryDecision,
    ) -> ModelChangeRequest:
        if decision.action is not RecoveryAction.CHANGE_MODEL:
            raise ValueError(
                "ChangeModelRecoveryHandler requires a CHANGE_MODEL decision"
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

        if not request.model_id:
            raise ValueError("model_id must not be empty")

        if not request.reason:
            raise ValueError("model reason must not be empty")

        return request
