from __future__ import annotations

from typing import Any

from vajra.domain.models import VerificationResult, VerificationStatus
from vajra.verification.contracts import VerificationRequest


class CommandVerifier:
    """
    Deterministic verifier for an observed command result.

    The verifier does not execute the command. It independently evaluates
    the observed result against an explicit acceptance condition.
    """

    VERSION = "command-verifier-v0"

    def verify(self, request: VerificationRequest) -> VerificationResult:
        parameters = request.parameters

        expected_exit_code = parameters.get("expected_exit_code")
        observed_exit_code = parameters.get("observed_exit_code")

        if not isinstance(expected_exit_code, int):
            return self._inconclusive(
                request,
                "expected_exit_code must be an integer",
            )

        if not isinstance(observed_exit_code, int):
            return self._inconclusive(
                request,
                "observed_exit_code must be an integer",
            )

        passed = observed_exit_code == expected_exit_code

        check = {
            "check": "exit_code",
            "expected": expected_exit_code,
            "observed": observed_exit_code,
            "passed": passed,
        }

        return VerificationResult(
            verification_id=request.verification_id,
            run_id=request.run_id,
            status=(
                VerificationStatus.PASSED
                if passed
                else VerificationStatus.FAILED
            ),
            checks=(check,),
            evidence_refs=request.evidence_refs,
            verifier_version=self.VERSION,
        )

    @staticmethod
    def _inconclusive(
        request: VerificationRequest,
        reason: str,
    ) -> VerificationResult:
        return VerificationResult(
            verification_id=request.verification_id,
            run_id=request.run_id,
            status=VerificationStatus.INCONCLUSIVE,
            checks=(
                {
                    "check": "exit_code",
                    "passed": False,
                    "reason": reason,
                },
            ),
            evidence_refs=request.evidence_refs,
            verifier_version=CommandVerifier.VERSION,
        )
