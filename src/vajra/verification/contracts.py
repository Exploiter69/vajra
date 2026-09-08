from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from vajra.domain.models import EvidenceRef, VerificationResult


@dataclass(frozen=True)
class VerificationRequest:
    """
    Immutable description of an independent verification operation.
    """

    verification_id: str
    run_id: str
    step_id: str
    attempt_id: str
    operation: str
    parameters: dict[str, Any]
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "verification_id",
            "run_id",
            "step_id",
            "attempt_id",
            "operation",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")


class Verifier(Protocol):
    """
    Independent verification boundary.

    A verifier determines whether an engineering condition is satisfied.
    Execution success alone is not verification evidence.
    """

    def verify(self, request: VerificationRequest) -> VerificationResult:
        ...
