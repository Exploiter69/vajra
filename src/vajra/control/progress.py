from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .contracts import PredicateResult, ProgressRecord


class ProgressError(ValueError):
    """Raised when a progress record violates control invariants."""


@dataclass(frozen=True)
class ProgressAssessment:
    record: ProgressRecord
    novel: bool
    accepted: bool
    reason: str


class ProgressTracker:
    """
    Validates and classifies durable progress observations.

    Progress is evidence-backed state change. A successful operation alone is
    not considered progress.
    """

    def __init__(self) -> None:
        self._novelty: dict[tuple[str, str], str] = {}

    def record(self, progress: ProgressRecord) -> ProgressAssessment:
        if not progress.run_id:
            raise ProgressError("run_id is required")
        if not progress.step_id:
            raise ProgressError("step_id is required")
        if not progress.attempt_id:
            raise ProgressError("attempt_id is required")
        if not progress.intent_id:
            raise ProgressError("intent_id is required")
        if not progress.pre_state_digest:
            raise ProgressError("pre_state_digest is required")
        if not progress.post_state_digest:
            raise ProgressError("post_state_digest is required")
        if not progress.novelty_fingerprint:
            raise ProgressError("novelty_fingerprint is required")
        if not progress.evidence_links:
            raise ProgressError("progress requires evidence links")

        key = (progress.step_id, progress.predicate_id)
        previous = self._novelty.get(key)
        novel = previous != progress.novelty_fingerprint

        if previous is None:
            self._novelty[key] = progress.novelty_fingerprint
        elif novel:
            self._novelty[key] = progress.novelty_fingerprint

        accepted = (
            progress.predicate_result is PredicateResult.TRUE
            and novel
            and bool(progress.evidence_links)
        )

        if not novel:
            reason = "duplicate novelty fingerprint"
        elif progress.predicate_result is PredicateResult.FALSE:
            reason = "progress predicate failed"
        elif progress.predicate_result is PredicateResult.INCONCLUSIVE:
            reason = "progress predicate inconclusive"
        elif not progress.evidence_links:
            reason = "missing evidence"
        else:
            reason = "novel evidence-backed progress"

        return ProgressAssessment(
            record=progress,
            novel=novel,
            accepted=accepted,
            reason=reason,
        )

    @staticmethod
    def changed_state(progress: ProgressRecord) -> bool:
        return progress.pre_state_digest != progress.post_state_digest
