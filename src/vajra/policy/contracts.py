from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    MODIFY = "MODIFY"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


@dataclass(frozen=True)
class Intent:
    """
    A proposed operation.

    Intent is a request for authority, not an instruction that has already
    been authorized or executed.
    """

    intent_id: str
    run_id: str
    step_id: str
    attempt_id: str
    operation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    requested_capabilities: tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        for field_name in (
            "intent_id",
            "run_id",
            "step_id",
            "attempt_id",
            "operation",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class PolicyDecision:
    """
    The authoritative policy evaluation result for an Intent.

    A decision records what policy decided. It does not execute the Intent.
    """

    intent_id: str
    decision: PolicyDecisionType
    policy_id: str
    policy_version: str
    reason: str
    modified_parameters: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "intent_id",
            "policy_id",
            "policy_version",
            "reason",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")

        if (
            self.decision is PolicyDecisionType.MODIFY
            and self.modified_parameters is None
        ):
            raise ValueError(
                "MODIFY decision requires modified_parameters"
            )

        if (
            self.decision is not PolicyDecisionType.MODIFY
            and self.modified_parameters is not None
        ):
            raise ValueError(
                "modified_parameters is only valid for MODIFY decisions"
            )
