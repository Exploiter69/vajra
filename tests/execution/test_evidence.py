from vajra.domain.models import EvidenceRef
from vajra.execution.contracts import ExecutionResult, ExecutionStatus
from vajra.execution.evidence import ExecutionEvidenceNormalizer


def make_result(
    *,
    status: ExecutionStatus = ExecutionStatus.ACCEPTED,
    output: dict | None = None,
    errors: tuple[str, ...] = (),
) -> ExecutionResult:
    return ExecutionResult(
        status=status,
        operation="run_tests",
        output=output or {"return_code": 0, "stdout": "ok\n"},
        errors=errors,
    )


def test_normalizes_execution_result() -> None:
    normalized = ExecutionEvidenceNormalizer().normalize(
        make_result(),
        evidence_id="evidence-1",
        location="memory://evidence-1",
    )

    assert isinstance(normalized.evidence_ref, EvidenceRef)
    assert normalized.evidence_ref.evidence_id == "evidence-1"
    assert normalized.evidence_ref.kind == "execution_result"
    assert normalized.evidence_ref.location == "memory://evidence-1"
    assert normalized.evidence_ref.digest
    assert normalized.status == "ACCEPTED"
    assert normalized.operation == "run_tests"


def test_payload_preserves_output() -> None:
    result = make_result(
        output={"return_code": 0, "stdout": "172 passed\n"},
    )

    normalized = ExecutionEvidenceNormalizer().normalize(
        result,
        evidence_id="evidence-2",
        location="memory://evidence-2",
    )

    assert normalized.payload["output"] == {
        "return_code": 0,
        "stdout": "172 passed\n",
    }


def test_payload_preserves_errors() -> None:
    result = make_result(
        status=ExecutionStatus.REJECTED,
        output={"return_code": 3},
        errors=("Process exited with return code 3",),
    )

    normalized = ExecutionEvidenceNormalizer().normalize(
        result,
        evidence_id="evidence-3",
        location="memory://evidence-3",
    )

    assert normalized.payload["errors"] == [
        "Process exited with return code 3",
    ]
    assert normalized.status == "REJECTED"


def test_same_result_produces_same_digest() -> None:
    normalizer = ExecutionEvidenceNormalizer()
    result = make_result()

    first = normalizer.normalize(
        result,
        evidence_id="evidence-a",
        location="memory://a",
    )
    second = normalizer.normalize(
        result,
        evidence_id="evidence-b",
        location="memory://b",
    )

    assert first.evidence_ref.digest == second.evidence_ref.digest


def test_different_result_produces_different_digest() -> None:
    normalizer = ExecutionEvidenceNormalizer()

    first = normalizer.normalize(
        make_result(output={"return_code": 0}),
        evidence_id="evidence-a",
        location="memory://a",
    )
    second = normalizer.normalize(
        make_result(output={"return_code": 1}),
        evidence_id="evidence-b",
        location="memory://b",
    )

    assert first.evidence_ref.digest != second.evidence_ref.digest


def test_empty_evidence_id_is_rejected() -> None:
    try:
        ExecutionEvidenceNormalizer().normalize(
            make_result(),
            evidence_id="",
            location="memory://evidence",
        )
    except ValueError as exc:
        assert str(exc) == "evidence_id must not be empty"
    else:
        raise AssertionError("Expected ValueError")


def test_empty_location_is_rejected() -> None:
    try:
        ExecutionEvidenceNormalizer().normalize(
            make_result(),
            evidence_id="evidence-1",
            location="",
        )
    except ValueError as exc:
        assert str(exc) == "location must not be empty"
    else:
        raise AssertionError("Expected ValueError")
