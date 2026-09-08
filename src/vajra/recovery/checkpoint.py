from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from vajra.domain import Checkpoint, RunState
from vajra.recovery.contracts import Failure, RecoveryAction
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class CheckpointRestoreRequest:
    """
    Explicit request to restore a run to a known checkpoint.

    The actual workspace/Git restoration is supplied by the caller.
    Recovery does not execute Git commands or mutate external state.
    """

    checkpoint_id: str
    reason: str


CheckpointRestorer = Callable[
    [Failure, RecoveryDecision, Checkpoint],
    CheckpointRestoreRequest,
]


class RestoreCheckpointRecoveryHandler:
    """
    Concrete RESTORE_CHECKPOINT recovery boundary.

    The handler validates checkpoint ownership and recovery state, then
    delegates the actual restoration operation to an explicitly supplied
    restorer.
    """

    def __init__(
        self,
        run_manager: RunManager,
        checkpoint_lookup: Callable[[str], Checkpoint | None],
        restorer: CheckpointRestorer,
    ) -> None:
        self._run_manager = run_manager
        self._checkpoint_lookup = checkpoint_lookup
        self._restorer = restorer

    def __call__(
        self,
        failure: Failure,
        decision: RecoveryDecision,
    ) -> CheckpointRestoreRequest:
        if decision.action is not RecoveryAction.RESTORE_CHECKPOINT:
            raise ValueError(
                "RestoreCheckpointRecoveryHandler requires "
                "a RESTORE_CHECKPOINT decision"
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

        checkpoint_id = self._checkpoint_id(failure)

        checkpoint = self._checkpoint_lookup(checkpoint_id)

        if checkpoint is None:
            raise ValueError(
                f"Checkpoint not found: {checkpoint_id}"
            )

        if checkpoint.run_id != failure.run_id:
            raise ValueError(
                "Checkpoint run_id does not match failure"
            )

        if checkpoint.step_id != failure.step_id:
            raise ValueError(
                "Checkpoint step_id does not match failure"
            )

        if checkpoint.event_position < 0:
            raise ValueError("Checkpoint event_position must not be negative")

        if not checkpoint.git_revision:
            raise ValueError("Checkpoint git_revision must not be empty")

        if not checkpoint.workspace_identity:
            raise ValueError(
                "Checkpoint workspace_identity must not be empty"
            )

        if not checkpoint.policy_version:
            raise ValueError(
                "Checkpoint policy_version must not be empty"
            )

        if not checkpoint.state_digest:
            raise ValueError(
                "Checkpoint state_digest must not be empty"
            )

        request = self._restorer(failure, decision, checkpoint)

        if request.checkpoint_id != checkpoint.checkpoint_id:
            raise ValueError(
                "Restorer returned a different checkpoint_id"
            )

        if not request.reason:
            raise ValueError("Restore reason must not be empty")

        return request

    @staticmethod
    def _checkpoint_id(failure: Failure) -> str:
        if not failure.details:
            raise ValueError(
                "RESTORE_CHECKPOINT requires checkpoint_id in failure details"
            )

        checkpoint_id = failure.details.get("checkpoint_id")

        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise ValueError(
                "RESTORE_CHECKPOINT requires a non-empty checkpoint_id"
            )

        return checkpoint_id
