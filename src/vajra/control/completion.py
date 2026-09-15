from __future__ import annotations

from dataclasses import dataclass

from .acceptance import AcceptanceEvaluation
from .contracts import PredicateResult


class CompletionDenied(ValueError):
    """Raised when a Run lacks the evidence required for completion."""


@dataclass(frozen=True)
class CompletionDecision:
    allowed: bool
    reason: str


class CompletionGate:
    """Pure completion boundary for the canonical Run lifecycle.

    Completion is allowed only when frozen acceptance evaluation is complete,
    the required artifact and verification evidence are present, and policy
    has explicitly approved the operation. This class never mutates a Run.
    """

    def authorize(
        self,
        acceptance: AcceptanceEvaluation,
        *,
        artifact_refs: tuple[str, ...],
        verification_refs: tuple[str, ...],
        policy_approved: bool,
    ) -> CompletionDecision:
        if acceptance.result is not PredicateResult.TRUE or not acceptance.complete:
            raise CompletionDenied("completion requires satisfied acceptance criteria")
        if not artifact_refs:
            raise CompletionDenied("completion requires artifact evidence")
        if not verification_refs:
            raise CompletionDenied("completion requires verification evidence")
        if not policy_approved:
            raise CompletionDenied("completion requires policy approval")
        return CompletionDecision(True, "completion prerequisites satisfied")
