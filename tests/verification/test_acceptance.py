from vajra.domain.models import (
    EvidenceRef,
    VerificationResult,
    VerificationStatus,
)
from vajra.verification.acceptance import (
    AcceptanceEvaluator,
    AcceptanceStatus,
)


def make_result(
    verification_id: str,
    status: VerificationStatus,
    *,
    with_evidence: bool = True,
) -> VerificationResult:
    evidence_refs = ()

    if with_evidence:
        evidence_refs = (
            EvidenceRef(
                evidence_id=f"evidence-{verification_id}",
                kind="verification_result",
                location=f"memory://{verification_id}",
                digest="abc123",
            ),
        )

    return VerificationResult(
        verification_id=verification_id,
        run_id="run-1",
        status=status,
        checks=(
            {
                "check": "example",
                "passed": status is VerificationStatus.PASSED,
            },
        ),
        evidence_refs=evidence_refs,
        verifier_version="test-verifier-v0",
    )


def test_no_results_are_inconclusive() -> None:
    result = AcceptanceEvaluator().evaluate(())

    assert result.status == AcceptanceStatus.INCONCLUSIVE
    assert result.checks[0]["check"] == "verification_results_present"


def test_all_passed_with_evidence_are_accepted() -> None:
    result = AcceptanceEvaluator().evaluate(
        (
            make_result("verification-1", VerificationStatus.PASSED),
            make_result("verification-2", VerificationStatus.PASSED),
        )
    )

    assert result.status == AcceptanceStatus.ACCEPTED
    assert result.verification_ids == (
        "verification-1",
        "verification-2",
    )
    assert result.checks[0]["passed"] is True


def test_failed_verification_rejects_acceptance() -> None:
    result = AcceptanceEvaluator().evaluate(
        (
            make_result("verification-1", VerificationStatus.PASSED),
            make_result("verification-2", VerificationStatus.FAILED),
        )
    )

    assert result.status == AcceptanceStatus.REJECTED
    assert result.checks[0]["verification_id"] == "verification-2"


def test_inconclusive_verification_blocks_acceptance() -> None:
    result = AcceptanceEvaluator().evaluate(
        (
            make_result("verification-1", VerificationStatus.INCONCLUSIVE),
        )
    )

    assert result.status == AcceptanceStatus.INCONCLUSIVE
    assert result.checks[0]["verification_id"] == "verification-1"


def test_passed_verification_without_evidence_is_inconclusive() -> None:
    result = AcceptanceEvaluator().evaluate(
        (
            make_result(
                "verification-1",
                VerificationStatus.PASSED,
                with_evidence=False,
            ),
        )
    )

    assert result.status == AcceptanceStatus.INCONCLUSIVE
    assert result.checks[0]["check"] == "passed_verification_has_evidence"


def test_failed_result_takes_precedence_over_later_passed_result() -> None:
    result = AcceptanceEvaluator().evaluate(
        (
            make_result("verification-1", VerificationStatus.FAILED),
            make_result("verification-2", VerificationStatus.PASSED),
        )
    )

    assert result.status == AcceptanceStatus.REJECTED


def test_evaluation_does_not_mutate_results() -> None:
    verification = make_result(
        "verification-1",
        VerificationStatus.PASSED,
    )

    before = verification

    result = AcceptanceEvaluator().evaluate((verification,))

    assert result.status == AcceptanceStatus.ACCEPTED
    assert verification == before


def test_verification_ids_are_preserved() -> None:
    results = (
        make_result("verification-a", VerificationStatus.PASSED),
        make_result("verification-b", VerificationStatus.PASSED),
    )

    result = AcceptanceEvaluator().evaluate(results)

    assert result.verification_ids == (
        "verification-a",
        "verification-b",
    )
