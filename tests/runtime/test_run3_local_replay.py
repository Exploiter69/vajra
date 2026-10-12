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
                    "content": "def add(a: int, b: int) -> int:\n    return a + b\n\ndef multiply(a: int, b: int) -> int:\n    return a * b\n",
                    "reason": "implement multiply",
                },
                {
                    "intent_id": "b",
                    "operation": "WRITE_FILE",
                    "path": "test_calculator.py",
                    "content": "from calculator import add, multiply\n\n\ndef test_add_existing_behavior() -> None:\n    assert add(2, 3) == 5\n\ndef test_multiply():\n    assert multiply(6, 7) == 42\n",
                    "reason": "regression test",
                },
            ],
        }
        return WorkerResult(
            status="completed",
            correlation_id=job.correlation_id,
            structured_result={"response": json.dumps(payload)},
        )


class RecoveringFakeKaggleResultTransport(FakeKaggleResultTransport):
    """First proposal regresses the old API; the replan repairs it."""

    def __init__(self):
        self.calls = 0

    def execute(self, job: WorkerJob) -> WorkerResult:
        self.calls += 1
        result = super().execute(job)
        payload = json.loads(result.structured_result["response"])
        if self.calls != 1:
            payload["strategy_id"] = "recovery-2"
            result.structured_result["response"] = json.dumps(payload)
            return result
        for intent in payload["intents"]:
            if intent["path"] == "calculator.py":
                intent["content"] = intent["content"].replace(
                    "def add(a: int, b: int) -> int:", "def add(a, b):"
                )
            elif intent["path"] == "test_calculator.py":
                intent["content"] = intent["content"].replace(
                    "def test_add_existing_behavior() -> None:", "def test_add():"
                )
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


def test_run3_local_replay_completes_real_control_plane(tmp_path):
    from scripts.third_engineering_run import build_loop, prepare_workspace

    class Gateway:
        def __init__(self):
            identity = ModelIdentity(
                "kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch"
            )
            self.adapter = TransportWorkerModelAdapter(
                FakeKaggleResultTransport(), identity, timeout_seconds=1
            )

        def invoke(self, request, model_identity):
            return self.adapter.invoke(request)

    workspace = tmp_path / "project"
    revision = prepare_workspace(workspace)
    identity = ModelIdentity(
        "kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch"
    )
    database = tmp_path / "run3.sqlite3"
    loop, manager, store = build_loop(
        workspace, revision, Gateway(), identity, "run3-local-replay", database
    )

    result = loop.run("run3-local-replay")
    run = manager.get_run("run3-local-replay")

    assert result.completed is True
    assert run.state.value == "COMPLETE"
    assert "def add" in (workspace / "calculator.py").read_text()
    assert "def multiply" in (workspace / "calculator.py").read_text()
    assert "add(2, 3) == 5" in (workspace / "test_calculator.py").read_text()
    assert "multiply(6, 7) == 42" in (workspace / "test_calculator.py").read_text()
    assert len(run.steps) == 2
    assert len(run.verification_results) == 6
    assert run.artifacts
    expected_events = manager.events("run3-local-replay")
    store.close()

    from vajra.runtime.run_manager import RunManager
    from vajra.runtime.sqlite_run_store import SQLiteRunStore

    with SQLiteRunStore(database) as reopened:
        recovered_manager = RunManager(state_store=reopened, event_store=reopened)
        recovered = recovered_manager.get_run("run3-local-replay")
        assert recovered.state.value == "COMPLETE"
        assert len(recovered.verification_results) == 6
        assert recovered.artifacts == run.artifacts
        assert recovered_manager.events("run3-local-replay") == expected_events



def test_run3_recovery_replans_with_specific_verification_failures(tmp_path):
    from scripts.third_engineering_run import build_loop, prepare_workspace

    transport = RecoveringFakeKaggleResultTransport()

    class Gateway:
        def __init__(self):
            identity = ModelIdentity(
                "kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch"
            )
            self.adapter = TransportWorkerModelAdapter(
                transport, identity, timeout_seconds=1
            )

        def invoke(self, request, model_identity):
            return self.adapter.invoke(request)

    workspace = tmp_path / "recovery-project"
    revision = prepare_workspace(workspace)
    identity = ModelIdentity(
        "kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch"
    )
    database = tmp_path / "recovery.sqlite3"
    loop, manager, store = build_loop(
        workspace, revision, Gateway(), identity, "run3-recovery-replay", database
    )

    result = loop.run("run3-recovery-replay")
    run = manager.get_run("run3-recovery-replay")

    assert transport.calls >= 2, "the rejected first proposal must trigger a replan"
    assert result.completed is True
    assert run.state.value == "COMPLETE"
    assert "def add(a: int, b: int) -> int:" in (workspace / "calculator.py").read_text()
    assert "def test_add_existing_behavior() -> None:" in (workspace / "test_calculator.py").read_text()
    replan_events = [
        event for event in manager.events("run3-recovery-replay")
        if event.event_type == "AUTONOMY_PLAN" and event.payload.get("replan")
    ]
    assert replan_events
    reason = replan_events[0].payload["recovery_reason"]
    assert "typed add API" in reason
    assert "existing addition regression test" in reason
    store.close()
