from __future__ import annotations

from dataclasses import dataclass

from vajra.recovery.contracts import Failure, FailureCategory, RecoveryAction


@dataclass(frozen=True)
class RecoveryDecision:
    """
    Immutable recovery-policy decision.

    This object recommends an action. It does not execute the action,
    consume a retry budget, mutate Run state, or restore a checkpoint.
    """

    failure_id: str
    run_id: str
    step_id: str
    attempt_id: str
    category: FailureCategory
    action: RecoveryAction
    reason: str

    def __post_init__(self) -> None:
        for field_name in (
            "failure_id",
            "run_id",
            "step_id",
            "attempt_id",
            "reason",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")


class RecoveryPolicy:
    """
    Deterministic v0 recovery policy.

    The policy maps classified failures to bounded recovery actions.
    It is deliberately separate from the durable runtime and recovery
    coordinator.
    """

    _DEFAULT_ACTIONS: dict[FailureCategory, RecoveryAction] = {
        FailureCategory.MODEL_FAILURE: RecoveryAction.CHANGE_MODEL,
        FailureCategory.TOOL_FAILURE: RecoveryAction.RETRY,
        FailureCategory.COMMAND_FAILURE: RecoveryAction.RETRY,
        FailureCategory.TEST_FAILURE: RecoveryAction.NEW_STRATEGY,
        FailureCategory.POLICY_DENIAL: RecoveryAction.REQUEST_HUMAN,
        FailureCategory.RESOURCE_EXHAUSTION: RecoveryAction.ABORT,
        FailureCategory.TIMEOUT: RecoveryAction.RETRY,
        FailureCategory.WORKER_LOSS: RecoveryAction.CHANGE_WORKER,
        FailureCategory.NETWORK_FAILURE: RecoveryAction.RETRY,
        FailureCategory.STATE_DIVERGENCE: RecoveryAction.RESTORE_CHECKPOINT,
        FailureCategory.SANDBOX_FAILURE: RecoveryAction.RETRY,
        FailureCategory.NO_PROGRESS: RecoveryAction.REQUEST_HUMAN,
        FailureCategory.UNKNOWN: RecoveryAction.REQUEST_HUMAN,
    }

    def decide(self, failure: Failure) -> RecoveryDecision:
        action = self._DEFAULT_ACTIONS[failure.category]

        return RecoveryDecision(
            failure_id=failure.failure_id,
            run_id=failure.run_id,
            step_id=failure.step_id,
            attempt_id=failure.attempt_id,
            category=failure.category,
            action=action,
            reason=self._reason(failure.category, action),
        )

    @staticmethod
    def _reason(
        category: FailureCategory,
        action: RecoveryAction,
    ) -> str:
        return (
            f"v0 recovery policy maps {category.value} "
            f"to {action.value}"
        )
