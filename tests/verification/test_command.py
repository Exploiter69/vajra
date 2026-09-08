from pathlib import Path

from vajra.domain.models import VerificationStatus
from vajra.verification.command import CommandVerifier
from vajra.verification.contracts import VerificationRequest


def make_request(
    *,
    expected_exit_code: object = 0,
    observed_exit_code: object = 0,
) -> VerificationRequest:
    return VerificationRequest(
        verification_id="verification-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="tests",
        parameters={
            "expected_exit_code": expected_exit_code,
            "observed_exit_code": observed_exit_code,
        },
    )


def test_matching_exit_code_passes() -> None:
    result = CommandVerifier().verify(make_request())

    assert result.status is VerificationStatus.PASSED
    assert result.verification_id == "verification-1"
    assert result.run_id == "run-1"
    assert result.verifier_version == "command-verifier-v0"
    assert result.checks[0] == {
        "check": "exit_code",
        "expected": 0,
        "observed": 0,
        "passed": True,
    }


def test_mismatched_exit_code_fails() -> None:
    result = CommandVerifier().verify(
        make_request(
            expected_exit_code=0,
            observed_exit_code=3,
        )
    )

    assert result.status is VerificationStatus.FAILED
    assert result.checks[0]["expected"] == 0
    assert result.checks[0]["observed"] == 3
    assert result.checks[0]["passed"] is False


def test_missing_expected_exit_code_is_inconclusive() -> None:
    result = CommandVerifier().verify(
        make_request(expected_exit_code=None)
    )

    assert result.status is VerificationStatus.INCONCLUSIVE
    assert "expected_exit_code" in result.checks[0]["reason"]


def test_missing_observed_exit_code_is_inconclusive() -> None:
    result = CommandVerifier().verify(
        make_request(observed_exit_code=None)
    )

    assert result.status is VerificationStatus.INCONCLUSIVE
    assert "observed_exit_code" in result.checks[0]["reason"]


def test_evidence_refs_are_preserved() -> None:
    from vajra.domain.models import EvidenceRef

    evidence = EvidenceRef(
        evidence_id="evidence-1",
        kind="execution_result",
        location="memory://evidence-1",
        digest="abc123",
    )

    request = VerificationRequest(
        verification_id="verification-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="tests",
        parameters={
            "expected_exit_code": 0,
            "observed_exit_code": 0,
        },
        evidence_refs=(evidence,),
    )

    result = CommandVerifier().verify(request)

    assert result.evidence_refs == (evidence,)


def test_verifier_does_not_execute_a_command(tmp_path: Path) -> None:
    marker = tmp_path / "marker"

    request = VerificationRequest(
        verification_id="verification-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="tests",
        parameters={
            "expected_exit_code": 0,
            "observed_exit_code": 0,
            "command": [
                "python",
                "-c",
                f"open({str(marker)!r}, 'w').write('executed')",
            ],
        },
    )

    result = CommandVerifier().verify(request)

    assert result.status is VerificationStatus.PASSED
    assert not marker.exists()
