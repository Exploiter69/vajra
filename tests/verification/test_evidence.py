from vajra.domain.models import VerificationStatus
from vajra.verification.evidence import VerificationEvidenceBuilder
from vajra.verification.command import CommandVerifier
from vajra.verification.contracts import VerificationRequest


def make_result():
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
    )

    return CommandVerifier().verify(request)


def test_structured_evidence_contains_required_fields() -> None:
    result = make_result()

    evidence = VerificationEvidenceBuilder().build(
        result,
        check_id="check-tests",
        command=("pytest", "-q"),
        exit_code=0,
        output_reference="memory://output-1",
        environment={"python": "3.14"},
        timestamp="2026-01-01T00:00:00+00:00",
    )

    assert evidence.check_id == "check-tests"
    assert evidence.command == ("pytest", "-q")
    assert evidence.status == VerificationStatus.PASSED.value
    assert evidence.exit_code == 0
    assert evidence.output_reference == "memory://output-1"
    assert evidence.environment == {"python": "3.14"}
    assert evidence.timestamp == "2026-01-01T00:00:00+00:00"
    assert evidence.evidence_digest
    assert len(evidence.evidence_digest) == 64


def test_evidence_ref_contains_digest() -> None:
    evidence = VerificationEvidenceBuilder().build(
        make_result(),
        check_id="check-tests",
        command=("pytest", "-q"),
        exit_code=0,
        output_reference="memory://output-1",
        timestamp="2026-01-01T00:00:00+00:00",
    )

    assert evidence.evidence_ref.kind == "verification_result"
    assert evidence.evidence_ref.location == "memory://output-1"
    assert evidence.evidence_ref.digest == evidence.evidence_digest


def test_same_inputs_produce_same_digest() -> None:
    result = make_result()
    builder = VerificationEvidenceBuilder()

    first = builder.build(
        result,
        check_id="check-tests",
        command=("pytest", "-q"),
        exit_code=0,
        output_reference="memory://output-1",
        environment={"python": "3.14"},
        timestamp="2026-01-01T00:00:00+00:00",
    )

    second = builder.build(
        result,
        check_id="check-tests",
        command=("pytest", "-q"),
        exit_code=0,
        output_reference="memory://output-1",
        environment={"python": "3.14"},
        timestamp="2026-01-01T00:00:00+00:00",
    )

    assert first == second


def test_changed_observation_changes_digest() -> None:
    result = make_result()
    builder = VerificationEvidenceBuilder()

    first = builder.build(
        result,
        check_id="check-tests",
        command=("pytest", "-q"),
        exit_code=0,
        output_reference="memory://output-1",
        timestamp="2026-01-01T00:00:00+00:00",
    )

    second = builder.build(
        result,
        check_id="check-tests",
        command=("pytest", "-q"),
        exit_code=1,
        output_reference="memory://output-1",
        timestamp="2026-01-01T00:00:00+00:00",
    )

    assert first.evidence_digest != second.evidence_digest


def test_empty_check_id_is_rejected() -> None:
    builder = VerificationEvidenceBuilder()

    try:
        builder.build(
            make_result(),
            check_id="",
            command=("pytest", "-q"),
            exit_code=0,
            output_reference="memory://output-1",
        )
    except ValueError as exc:
        assert str(exc) == "check_id must not be empty"
    else:
        raise AssertionError("Expected ValueError")


def test_empty_command_is_rejected() -> None:
    builder = VerificationEvidenceBuilder()

    try:
        builder.build(
            make_result(),
            check_id="check-tests",
            command=(),
            exit_code=0,
            output_reference="memory://output-1",
        )
    except ValueError as exc:
        assert str(exc) == "command must contain non-empty strings"
    else:
        raise AssertionError("Expected ValueError")


def test_empty_output_reference_is_rejected() -> None:
    builder = VerificationEvidenceBuilder()

    try:
        builder.build(
            make_result(),
            check_id="check-tests",
            command=("pytest", "-q"),
            exit_code=0,
            output_reference="",
        )
    except ValueError as exc:
        assert str(exc) == "output_reference must not be empty"
    else:
        raise AssertionError("Expected ValueError")


def test_environment_is_copied() -> None:
    environment = {"python": "3.14"}

    evidence = VerificationEvidenceBuilder().build(
        make_result(),
        check_id="check-tests",
        command=("pytest", "-q"),
        exit_code=0,
        output_reference="memory://output-1",
        environment=environment,
        timestamp="2026-01-01T00:00:00+00:00",
    )

    environment["python"] = "changed"

    assert evidence.environment == {"python": "3.14"}


def test_result_is_not_mutated() -> None:
    result = make_result()
    before = result

    VerificationEvidenceBuilder().build(
        result,
        check_id="check-tests",
        command=("pytest", "-q"),
        exit_code=0,
        output_reference="memory://output-1",
    )

    assert result == before
