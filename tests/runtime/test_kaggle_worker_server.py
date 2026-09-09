from __future__ import annotations

from vajra.runtime.kaggle_worker_server import infer
from vajra.runtime.worker_protocol import WorkerJob


def make_job(**context):
    return WorkerJob(
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        repository_revision="abc123",
        workspace_contract={},
        context_bundle={"prompt": "hello", **context},
        allowed_capabilities=("completion",),
        budget={"max_output_tokens": 16, "timeout_seconds": 5},
        deadline="2030-01-01T00:00:00Z",
        expected_output_schema={"type": "object"},
        correlation_id="corr-1",
    )


def test_missing_prompt_returns_failed_result():
    job = make_job()
    job = WorkerJob(
        run_id=job.run_id,
        step_id=job.step_id,
        attempt_id=job.attempt_id,
        repository_revision=job.repository_revision,
        workspace_contract=job.workspace_contract,
        context_bundle={},
        allowed_capabilities=job.allowed_capabilities,
        budget=job.budget,
        deadline=job.deadline,
        expected_output_schema=job.expected_output_schema,
        correlation_id=job.correlation_id,
    )

    result = infer(job)

    assert result.status == "failed"
    assert result.correlation_id == "corr-1"
    assert result.errors


def test_infer_preserves_job_correlation(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return (
                b'{"response":"hello","total_duration":10,'
                b'"load_duration":2,"prompt_eval_count":3,'
                b'"eval_count":4}'
            )

    monkeypatch.setattr(
        "vajra.runtime.kaggle_worker_server.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = infer(make_job())

    assert result.status == "completed"
    assert result.correlation_id == "corr-1"
    assert result.structured_result["response"] == "hello"
    assert result.structured_result["model"] == "qwen2.5-coder:32b"
    assert result.usage["eval_count"] == 4
    assert not result.errors


def test_infer_failure_preserves_job_correlation(monkeypatch):
    def fail(*args, **kwargs):
        raise TimeoutError("ollama timeout")

    monkeypatch.setattr(
        "vajra.runtime.kaggle_worker_server.urlopen",
        fail,
    )

    result = infer(make_job())

    assert result.status == "failed"
    assert result.correlation_id == "corr-1"
    assert "TimeoutError" in result.errors[0]
