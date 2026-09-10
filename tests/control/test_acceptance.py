from datetime import datetime, timezone

import pytest

from vajra.control.acceptance import AcceptanceError, AcceptanceEvaluator
from vajra.control.contracts import (
    AcceptanceCriteria,
    AcceptancePredicate,
    PredicateResult,
)


def criteria() -> AcceptanceCriteria:
    return AcceptanceCriteria(
        criteria_id="criteria-1",
        version="1",
        objective_digest="objective-digest",
        predicates=(
            AcceptancePredicate(
                predicate_id="tests-pass",
                version="1",
                description="required tests pass",
                required_evidence_kinds=("verification",),
            ),
            AcceptancePredicate(
                predicate_id="artifact-present",
                version="1",
                description="required artifact exists",
                required_evidence_kinds=("artifact",),
            ),
        ),
        required_evidence=("verification", "artifact"),
        verification_plan_ref="plan-1",
        integrity_digest="criteria-integrity",
        created_at=datetime.now(timezone.utc),
        frozen_at=datetime.now(timezone.utc),
    )


def test_acceptance_requires_frozen_criteria():
    c = criteria()
    unfrozen = AcceptanceCriteria(
        **{**c.__dict__, "frozen_at": None}
    )

    with pytest.raises(AcceptanceError):
        AcceptanceEvaluator().evaluate(
            unfrozen,
            {},
            (),
        )


def test_acceptance_is_true_only_when_all_predicates_and_evidence_exist():
    result = AcceptanceEvaluator().evaluate(
        criteria(),
        {
            "tests-pass": PredicateResult.TRUE,
            "artifact-present": PredicateResult.TRUE,
        },
        ("verification", "artifact"),
    )

    assert result.result is PredicateResult.TRUE
    assert result.complete
    assert result.satisfied_predicates == ("artifact-present", "tests-pass")


def test_missing_evidence_makes_acceptance_inconclusive():
    result = AcceptanceEvaluator().evaluate(
        criteria(),
        {
            "tests-pass": PredicateResult.TRUE,
            "artifact-present": PredicateResult.TRUE,
        },
        ("verification",),
    )

    assert result.result is PredicateResult.INCONCLUSIVE
    assert not result.complete
    assert result.missing_evidence == ("artifact",)


def test_failed_predicate_wins_over_missing_evidence():
    result = AcceptanceEvaluator().evaluate(
        criteria(),
        {
            "tests-pass": PredicateResult.FALSE,
            "artifact-present": PredicateResult.TRUE,
        },
        (),
    )

    assert result.result is PredicateResult.FALSE
    assert result.failed_predicates == ("tests-pass",)
