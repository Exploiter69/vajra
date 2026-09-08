import pytest

from vajra.domain.models import EvidenceRef
from vajra.verification.contracts import VerificationRequest


def make_request() -> VerificationRequest:
    return VerificationRequest(
        verification_id="verification-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="tests",
        parameters={"command": ["pytest", "-q"]},
    )


def test_verification_request_is_created() -> None:
    request = make_request()

    assert request.verification_id == "verification-1"
    assert request.run_id == "run-1"
    assert request.operation == "tests"
    assert request.evidence_refs == ()


def test_verification_request_accepts_evidence_refs() -> None:
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
        parameters={},
        evidence_refs=(evidence,),
    )

    assert request.evidence_refs == (evidence,)


@pytest.mark.parametrize(
    "field_name",
    [
        "verification_id",
        "run_id",
        "step_id",
        "attempt_id",
        "operation",
    ],
)
def test_identity_fields_must_not_be_empty(field_name: str) -> None:
    values = {
        "verification_id": "verification-1",
        "run_id": "run-1",
        "step_id": "step-1",
        "attempt_id": "attempt-1",
        "operation": "tests",
    }
    values[field_name] = ""

    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        VerificationRequest(
            parameters={},
            **values,
        )


def test_request_is_immutable() -> None:
    request = make_request()

    with pytest.raises(AttributeError):
        request.operation = "build"  # type: ignore[misc]


def test_parameters_are_preserved() -> None:
    request = VerificationRequest(
        verification_id="verification-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="tests",
        parameters={"expected_exit_code": 0},
    )

    assert request.parameters["expected_exit_code"] == 0
