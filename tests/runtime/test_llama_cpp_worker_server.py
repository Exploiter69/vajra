from __future__ import annotations

import json

from vajra.runtime.llama_cpp_worker_server import MODEL, infer
from vajra.runtime.worker_protocol import WorkerJob


def make_job() -> WorkerJob:
    return WorkerJob(
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        repository_revision="abc123",
        workspace_contract={"mode": "proposal-only"},
        context_bundle={"prompt": "hello"},
        allowed_capabilities=(),
        budget={"max_output_tokens": 16, "timeout_seconds": 5},
        deadline="2030-01-01T00:00:00Z",
        expected_output_schema={"type": "string"},
        correlation_id="corr-llama-1",
    )


def test_infer_preserves_correlation_and_model(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [{"message": {"content": "hello"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 4},
                }
            ).encode()

    monkeypatch.setattr(
        "vajra.runtime.llama_cpp_worker_server.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = infer(make_job())

    assert result.status == "completed"
    assert result.correlation_id == "corr-llama-1"
    assert result.structured_result == {"response": "hello", "model": MODEL}
    assert result.usage["prompt_eval_count"] == 3
    assert result.usage["eval_count"] == 4


def test_infer_rejects_missing_prompt():
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
    assert result.correlation_id == "corr-llama-1"
    assert result.errors
