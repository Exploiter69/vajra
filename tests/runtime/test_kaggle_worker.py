from vajra.domain.models import ArtifactRef, EvidenceRef
from vajra.runtime.kaggle_worker import KaggleWorkerAdapter
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


def make_job() -> WorkerJob:
    return WorkerJob(
        run_id="run-001",
        step_id="step-001",
        attempt_id="attempt-001",
        repository_revision="abc123",
        workspace_contract={"mode": "isolated"},
        context_bundle={"objective": "fix tests"},
        allowed_capabilities=("workspace.read", "execution.test"),
        budget={"max_model_calls": 3},
        deadline="2030-01-01T00:00:00+00:00",
        expected_output_schema={"type": "object"},
        correlation_id="corr-001",
    )


def test_job_round_trip_preserves_worker_identity_and_correlation() -> None:
    adapter = KaggleWorkerAdapter()

    decoded = adapter.decode_job(adapter.encode_job(make_job()))

    assert decoded == make_job()
    assert decoded.run_id == "run-001"
    assert decoded.step_id == "step-001"
    assert decoded.attempt_id == "attempt-001"
    assert decoded.correlation_id == "corr-001"


def test_result_round_trip_preserves_structured_payload() -> None:
    adapter = KaggleWorkerAdapter()
    result = WorkerResult(
        status="SUCCEEDED",
        correlation_id="corr-001",
        structured_result={"summary": "tests pass"},
        logs=("pytest -q", "12 passed"),
        usage={"model_calls": 1},
        errors=(),
    )

    decoded = adapter.decode_result(adapter.encode_result(result))

    assert decoded.status == "SUCCEEDED"
    assert decoded.correlation_id == "corr-001"
    assert decoded.structured_result == {"summary": "tests pass"}
    assert decoded.logs == ("pytest -q", "12 passed")
    assert decoded.usage == {"model_calls": 1}


def test_result_round_trip_preserves_artifacts_and_evidence() -> None:
    adapter = KaggleWorkerAdapter()
    result = WorkerResult(
        status="SUCCEEDED",
        correlation_id="corr-001",
        structured_result={"summary": "tests pass"},
        artifacts=(
            ArtifactRef(
                artifact_id="artifact-001",
                kind="patch",
                location="workspace://patch.diff",
                sha256="abc123",
            ),
        ),
        evidence_refs=(
            EvidenceRef(
                evidence_id="evidence-001",
                kind="test-output",
                location="workspace://pytest.txt",
                digest="def456",
            ),
        ),
    )

    decoded = adapter.decode_result(adapter.encode_result(result))

    assert decoded.artifacts == result.artifacts
    assert decoded.evidence_refs == result.evidence_refs


def test_protocol_rejects_wrong_version() -> None:
    adapter = KaggleWorkerAdapter()
    encoded = adapter.encode_job(make_job()).replace(
        "vajra-worker-v1",
        "vajra-worker-v999",
    )

    try:
        adapter.decode_job(encoded)
    except ValueError as exc:
        assert "protocol version" in str(exc)
    else:
        raise AssertionError("wrong protocol version must be rejected")


def test_protocol_rejects_wrong_message_type() -> None:
    adapter = KaggleWorkerAdapter()
    encoded = adapter.encode_job(make_job()).replace(
        '"type":"worker_job"',
        '"type":"worker_result"',
    )

    try:
        adapter.decode_job(encoded)
    except ValueError as exc:
        assert "worker_job" in str(exc)
    else:
        raise AssertionError("wrong message type must be rejected")
