from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from .contracts import AcceptanceCriteria, PredicateResult


class AcceptanceError(ValueError):
    """Raised when acceptance evaluation cannot be performed safely."""


@dataclass(frozen=True)
class AcceptanceEvaluation:
    criteria_id: str
    criteria_version: str
    objective_digest: str
    result: PredicateResult
    satisfied_predicates: tuple[str, ...]
    failed_predicates: tuple[str, ...]
    inconclusive_predicates: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    evaluated_at: datetime

    @property
    def complete(self) -> bool:
        return self.result is PredicateResult.TRUE


class AcceptanceEvaluator:
    """
    Evaluates frozen acceptance criteria from externally supplied predicate
    results and evidence kinds.

    This component evaluates evidence; it does not manufacture evidence and
    does not mutate Run state.
    """

    def evaluate(
        self,
        criteria: AcceptanceCriteria,
        predicate_results: dict[str, PredicateResult],
        available_evidence_kinds: Iterable[str],
        *,
        evaluated_at: datetime | None = None,
    ) -> AcceptanceEvaluation:
        if not criteria.frozen:
            raise AcceptanceError("acceptance criteria must be frozen")

        available = set(available_evidence_kinds)

        missing_evidence = tuple(
            sorted(
                {
                    kind
                    for kind in criteria.required_evidence
                    if kind not in available
                }
            )
        )

        satisfied: list[str] = []
        failed: list[str] = []
        inconclusive: list[str] = []

        for predicate in criteria.predicates:
            result = predicate_results.get(
                predicate.predicate_id,
                PredicateResult.INCONCLUSIVE,
            )

            if result is PredicateResult.TRUE:
                satisfied.append(predicate.predicate_id)
            elif result is PredicateResult.FALSE:
                failed.append(predicate.predicate_id)
            else:
                inconclusive.append(predicate.predicate_id)

        if failed:
            result = PredicateResult.FALSE
        elif missing_evidence or inconclusive:
            result = PredicateResult.INCONCLUSIVE
        elif len(satisfied) == len(criteria.predicates):
            result = PredicateResult.TRUE
        else:
            result = PredicateResult.INCONCLUSIVE

        return AcceptanceEvaluation(
            criteria_id=criteria.criteria_id,
            criteria_version=criteria.version,
            objective_digest=criteria.objective_digest,
            result=result,
            satisfied_predicates=tuple(sorted(satisfied)),
            failed_predicates=tuple(sorted(failed)),
            inconclusive_predicates=tuple(sorted(inconclusive)),
            missing_evidence=missing_evidence,
            evaluated_at=evaluated_at or datetime.now(timezone.utc),
        )
