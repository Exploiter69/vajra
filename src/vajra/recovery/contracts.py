from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class FailureCategory(str, Enum):
    MODEL_FAILURE = "MODEL_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    COMMAND_FAILURE = "COMMAND_FAILURE"
    TEST_FAILURE = "TEST_FAILURE"
    POLICY_DENIAL = "POLICY_DENIAL"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    TIMEOUT = "TIMEOUT"
    WORKER_LOSS = "WORKER_LOSS"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    STATE_DIVERGENCE = "STATE_DIVERGENCE"
    SANDBOX_FAILURE = "SANDBOX_FAILURE"
    NO_PROGRESS = "NO_PROGRESS"
    UNKNOWN = "UNKNOWN"


class RecoveryAction(str, Enum):
    RETRY = "RETRY"
    NEW_STRATEGY = "NEW_STRATEGY"
    CHANGE_MODEL = "CHANGE_MODEL"
    CHANGE_WORKER = "CHANGE_WORKER"
    RESTORE_CHECKPOINT = "RESTORE_CHECKPOINT"
    REQUEST_HUMAN = "REQUEST_HUMAN"
    ABORT = "ABORT"


@dataclass(frozen=True)
class Failure:
    """
    Immutable representation of an observed engineering failure.

    Classification is based on this observation. The Failure object itself
    does not perform recovery or mutate canonical Run state.
    """

    failure_id: str
    run_id: str
    step_id: str
    attempt_id: str
    category: FailureCategory
    message: str
    details: dict[str, object] | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "failure_id",
            "run_id",
            "step_id",
            "attempt_id",
            "message",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class FailureObservation:
    """
    Transient observation used to classify a failure.

    This intentionally does not contain a preselected recovery action.
    """

    failure_id: str
    run_id: str
    step_id: str
    attempt_id: str
    source: str
    message: str
    details: dict[str, object] | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "failure_id",
            "run_id",
            "step_id",
            "attempt_id",
            "source",
            "message",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")
