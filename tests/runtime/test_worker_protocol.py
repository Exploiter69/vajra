import pytest

from vajra.domain.models import ArtifactRef, EvidenceRef
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


def make_job() -> WorkerJob:
    return WorkerJob(
        run_id="run-001",
        step_id="step-001",
        attempt_id="attempt-001",
        repository_revision="abc123",
        workspace_contract={"workspace_id": "ws-001"},
        context_bundle={"objective": "implement feature"},
        allowed_capabilities=("git", "shell", "test"),
        budget={"max_commands": 10},
        deadline="2026-09-08T13:00:00+00:00",
        expected_output_schema={"type": "object"},
    )


def test_worker_job_contains_bounded_execution_context():
    job = make_job()

    assert job.run_id == "run-001"
    assert job.step_id == "step-001"
    assert job.attempt_id == "attempt-001"
    assert job.repository_revision == "abc123"
    assert job.workspace_contract["workspace_id"] == "ws-001"
    assert job.context_bundle["objective"] == "implement feature"
    assert job.allowed_capabilities == ("git", "shell", "test")
    assert job.budget["max_commands"] == 10
    assert job.deadline.endswith("+00:00")
    assert job.expected_output_schema["type"] == "object"


def test_worker_job_requires_execution_identity():
    with pytest.raises(ValueError, match="run_id"):
        WorkerJob(
            run_id="",
            step_id="step-001",
            attempt_id="attempt-001",
            repository_revision="abc123",
            workspace_contract={},
            context_bundle={},
            allowed_capabilities=(),
            budget={},
            deadline="deadline",
            expected_output_schema={},
        )


def test_worker_result_contains_reported_outcome():
    artifact = ArtifactRef(
        artifact_id="artifact-001",
        kind="patch",
        location="workspace/patch.diff",
    )
    evidence = EvidenceRef(
        evidence_id="evidence-001",
        kind="test",
        location="tests/result.json",
    )

    result = WorkerResult(
        status="SUCCEEDED",
        structured_result={"summary": "implemented"},
        artifacts=(artifact,),
        logs=("pytest passed",),
        usage={"commands": 3},
        evidence_refs=(evidence,),
    )

    assert result.status == "SUCCEEDED"
    assert result.structured_result == {"summary": "implemented"}
    assert result.artifacts == (artifact,)
    assert result.logs == ("pytest passed",)
    assert result.usage["commands"] == 3
    assert result.evidence_refs == (evidence,)


def test_worker_result_requires_status():
    with pytest.raises(ValueError, match="status"):
        WorkerResult(status="")


def test_worker_result_does_not_contain_canonical_run_state():
    result = WorkerResult(
        status="FAILED",
        errors=("worker failure",),
    )

    assert not hasattr(result, "state")
    assert not hasattr(result, "run_state")
    assert not hasattr(result, "step_state")
    assert not hasattr(result, "attempt_state")
