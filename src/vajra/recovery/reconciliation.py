from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vajra.domain import Checkpoint, EngineeringRun, RunState
from vajra.runtime.lease import WorkerLease


class RecoveryDisposition(str, Enum):
    RESUME = "RESUME"
    RESTORE_CHECKPOINT = "RESTORE_CHECKPOINT"
    REQUEST_HUMAN = "REQUEST_HUMAN"
    ABORT = "ABORT"


@dataclass(frozen=True)
class RecoveryObservation:
    """
    Observed external/canonical state used during recovery reconciliation.

    Values are supplied by the appropriate authority boundary. Reconciliation
    never probes or mutates external state itself.
    """

    run_state: RunState
    event_position: int
    git_revision: str
    workspace_identity: str
    lease: WorkerLease | None = None
    lease_valid: bool | None = None

    def __post_init__(self) -> None:
        if self.event_position < 0:
            raise ValueError("event_position must not be negative")
        if not self.git_revision:
            raise ValueError("git_revision must not be empty")
        if not self.workspace_identity:
            raise ValueError("workspace_identity must not be empty")


@dataclass(frozen=True)
class RecoveryAssessment:
    disposition: RecoveryDisposition
    reasons: tuple[str, ...]


class RecoveryReconciler:
    """
    Deterministic recovery reconciliation.

    Canonical Run state, event position, checkpoint metadata, workspace/Git
    observations, and worker lease observations are compared before recovery
    continues. This class does not execute recovery actions.
    """

    def assess(
        self,
        run: EngineeringRun,
        checkpoint: Checkpoint | None,
        observation: RecoveryObservation,
    ) -> RecoveryAssessment:
        if observation.run_state is not run.state:
            return self._human(
                "Observed Run state differs from canonical Run state"
            )

        if run.state is not RunState.RECOVERING:
            return self._human(
                "Recovery reconciliation requires a RECOVERING Run"
            )

        if checkpoint is None:
            return self._human("No checkpoint is available for reconciliation")

        if checkpoint.run_id != run.run_id:
            return self._abort("Checkpoint belongs to a different Run")

        if checkpoint.event_position > observation.event_position:
            return self._human(
                "Checkpoint event position is ahead of observed event history"
            )

        if checkpoint.git_revision != observation.git_revision:
            return self._restore(
                "Observed Git revision differs from checkpoint revision"
            )

        if checkpoint.workspace_identity != observation.workspace_identity:
            return self._restore(
                "Observed workspace identity differs from checkpoint"
            )

        if observation.lease is not None and observation.lease_valid is False:
            return self._human("Worker lease is no longer valid")

        if (
            observation.lease is not None
            and observation.lease.attempt_id
            not in {
                attempt.attempt_id
                for step in run.steps
                for attempt in step.attempts
            }
        ):
            return self._abort("Observed lease references an unknown attempt")

        return RecoveryAssessment(
            disposition=RecoveryDisposition.RESUME,
            reasons=("Canonical and observed recovery state are consistent",),
        )

    @staticmethod
    def _restore(reason: str) -> RecoveryAssessment:
        return RecoveryAssessment(
            disposition=RecoveryDisposition.RESTORE_CHECKPOINT,
            reasons=(reason,),
        )

    @staticmethod
    def _human(reason: str) -> RecoveryAssessment:
        return RecoveryAssessment(
            disposition=RecoveryDisposition.REQUEST_HUMAN,
            reasons=(reason,),
        )

    @staticmethod
    def _abort(reason: str) -> RecoveryAssessment:
        return RecoveryAssessment(
            disposition=RecoveryDisposition.ABORT,
            reasons=(reason,),
        )


__all__ = [
    "RecoveryAssessment",
    "RecoveryDisposition",
    "RecoveryObservation",
    "RecoveryReconciler",
]
