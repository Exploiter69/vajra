from __future__ import annotations

from dataclasses import dataclass

from vajra.domain.models import VerificationResult, VerificationStatus


class AcceptanceStatus(str):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class AcceptanceResult:
    """
    Deterministic aggregate decision over verification results.

    This is an evaluation result only. It does not mutate or persist the
    EngineeringRun.
    """

    status: str
    checks: tuple[dict[str, object], ...] = ()
    verification_ids: tuple[str, ...] = ()


class AcceptanceEvaluator:
    """
    Determines whether a set of verification results establishes acceptance.

    Verification itself remains independent. This component only evaluates
    the canonical verification results that have already been produced.
    """

    def evaluate(
        self,
        results: tuple[VerificationResult, ...],
    ) -> AcceptanceResult:
        if not results:
            return AcceptanceResult(
                status=AcceptanceStatus.INCONCLUSIVE,
                checks=(
                    {
                        "check": "verification_results_present",
                        "passed": False,
                        "reason": "No verification results were provided",
                    },
                ),
            )

        verification_ids = tuple(result.verification_id for result in results)

        for result in results:
            if result.status is VerificationStatus.FAILED:
                return AcceptanceResult(
                    status=AcceptanceStatus.REJECTED,
                    checks=(
                        {
                            "check": "all_verifications_passed",
                            "passed": False,
                            "verification_id": result.verification_id,
                            "status": result.status.value,
                        },
                    ),
                    verification_ids=verification_ids,
                )

            if result.status is VerificationStatus.INCONCLUSIVE:
                return AcceptanceResult(
                    status=AcceptanceStatus.INCONCLUSIVE,
                    checks=(
                        {
                            "check": "all_verifications_conclusive",
                            "passed": False,
                            "verification_id": result.verification_id,
                            "status": result.status.value,
                        },
                    ),
                    verification_ids=verification_ids,
                )

            if result.status is VerificationStatus.PASSED and not result.evidence_refs:
                return AcceptanceResult(
                    status=AcceptanceStatus.INCONCLUSIVE,
                    checks=(
                        {
                            "check": "passed_verification_has_evidence",
                            "passed": False,
                            "verification_id": result.verification_id,
                            "reason": "Passed verification has no evidence references",
                        },
                    ),
                    verification_ids=verification_ids,
                )

        return AcceptanceResult(
            status=AcceptanceStatus.ACCEPTED,
            checks=(
                {
                    "check": "all_verifications_passed",
                    "passed": True,
                    "verification_count": len(results),
                },
            ),
            verification_ids=verification_ids,
        )
