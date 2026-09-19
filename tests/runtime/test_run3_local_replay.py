from __future__ import annotations

import json

from vajra.routing.contracts import BudgetEnvelope, ModelIdentity, ModelRequest
from vajra.runtime.remote_model import TransportWorkerModelAdapter
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


class FakeKaggleResultTransport:
    def execute(self, job: WorkerJob) -> WorkerResult:
        payload = {
            "orientation": "Implement multiply and its regression test.",
            "plan_id": "p",
            "strategy_id": "qwen-run-3",
            "intents": [
                {
                    "intent_id": "a",
                    "operation": "WRITE_FILE",
                    "path": "calculator.py",
                    "content": "def multiply(a,b):\n    return a*b\n",
                    "reason": "implement multiply",
                },
                {
                    "intent_id": "b",
                    "operation": "WRITE_FILE",
                    "path": "test_calculator.py",
                    "content": "def test_multiply():\n    assert multiply(6, 7) == 42\n",
                    "reason": "regression test",
                },
            ],
        }
        return WorkerResult(
            status="completed",
            correlation_id=job.correlation_id,
            structured_result={"response": json.dumps(payload)},
        )


def test_run3_local_replay_preserves_kaggle_wire_shape():
    identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
    adapter = TransportWorkerModelAdapter(
        FakeKaggleResultTransport(), identity, timeout_seconds=1
    )

    request = ModelRequest(
        request_id="request-1",
        run_id="run-1",
        step_id="model-orientation-plan",
        attempt_id="attempt-1",
        task="objective",
        context={"revision": "rev", "context_digest": "digest"},
        output_schema={"type": "object"},
        budget=BudgetEnvelope(
            max_model_calls=1,
            max_worker_runtime_seconds=900,
            max_output_size=4800,
            max_cost_units=0,
        ),
        deadline="2099-01-01T00:00:00+00:00",
        model=identity.canonical,
        strategy_id="qwen-orientation-plan",
    )

    result = adapter.invoke(request)

    assert result.status == "SUCCEEDED"
    assert result.structured_output["response"]
    payload = json.loads(result.structured_output["response"])
    assert payload["orientation"]
    assert [intent["path"] for intent in payload["intents"]] == [
        "calculator.py",
        "test_calculator.py",
    ]
