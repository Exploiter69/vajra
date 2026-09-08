from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vajra.policy.contracts import Intent, PolicyDecision


class ExecutionStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ExecutionRequest:
    """
    An execution request carrying the exact Intent and its policy decision.

    The broker does not infer or reinterpret authorization.
    """

    intent: Intent
    policy_decision: PolicyDecision

    def __post_init__(self) -> None:
        if self.policy_decision.intent_id != self.intent.intent_id:
            raise ValueError(
                "Policy decision does not match execution intent"
            )


@dataclass(frozen=True)
class ExecutionResult:
    """
    Result reported by an execution backend.

    This is a report, not an authority grant.
    """

    status: ExecutionStatus
    operation: str
    output: dict[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.operation:
            raise ValueError("operation must not be empty")
