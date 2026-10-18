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


def test_run3_worker_failure_during_replan_is_durable_and_waits_for_human(tmp_path):
    from scripts.third_engineering_run import build_loop, prepare_workspace
    from vajra.runtime.run_manager import RunManager
    from vajra.runtime.sqlite_run_store import SQLiteRunStore

    class FailingReplanTransport(RecoveringFakeKaggleResultTransport):
        def execute(self, job: WorkerJob) -> WorkerResult:
            if self.calls == 0:
                return super().execute(job)
            self.calls += 1
            return WorkerResult(
                status="failed",
                correlation_id=job.correlation_id,
                errors=("HTTPError: HTTP Error 502: Bad Gateway",),
            )

    transport = FailingReplanTransport()

    class Gateway:
        def __init__(self):
            identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
            self.adapter = TransportWorkerModelAdapter(
                transport, identity, timeout_seconds=1
            )

        def invoke(self, request, model_identity):
            return self.adapter.invoke(request)

    workspace = tmp_path / "worker-failure-project"
    revision = prepare_workspace(workspace)
    identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
    database = tmp_path / "worker-failure.sqlite3"
    loop, manager, store = build_loop(
        workspace, revision, Gateway(), identity, "run3-worker-failure", database
    )

    result = loop.run("run3-worker-failure")
    run = manager.get_run("run3-worker-failure")

    assert transport.calls == 2
    assert result.completed is False
    assert result.waiting_human is True
    assert run.state.value == "WAITING_HUMAN"
    assert "HTTP Error 502" in result.reason
    assert "no completion" not in result.reason.lower()
    store.close()

    with SQLiteRunStore(database) as reopened:
        recovered_manager = RunManager(state_store=reopened, event_store=reopened)
        recovered = recovered_manager.get_run("run3-worker-failure")
        assert recovered.state.value == "WAITING_HUMAN"
        wait_events = [
            event for event in recovered_manager.events("run3-worker-failure")
            if event.event_type == "AUTONOMY_WAIT_HUMAN"
        ]
        assert wait_events
        assert "HTTP Error 502" in wait_events[-1].payload["reason"]
        assert wait_events[-1].payload["failed_phase"] == "recovery replanning"



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
    assert "needle=def add(a: int, b: int) -> int:" in reason
    assert "needle=def test_add_existing_behavior() -> None:" in reason
    store.close()



def _rebuild_run3_loop_after_restart(previous_loop, manager, store):
    from vajra.autonomy import AutonomousEngineeringLoop

    return AutonomousEngineeringLoop(
        run_manager=manager,
        state_store=store,
        event_store=store,
        context_engine=previous_loop._context,
        controller=previous_loop._controller,
        policy=previous_loop._policy,
        broker=previous_loop._broker,
        verifier=previous_loop._verifier,
        reasoning=previous_loop._reasoning,
        acceptance=previous_loop._acceptance,
        verification_plan=previous_loop._verification_plan,
        verification_environment=previous_loop._verification_environment,
        workspace=previous_loop._workspace,
        budget=previous_loop._budget,
        bounded_autonomy=previous_loop._bounded,
        max_cycles=previous_loop._max_cycles,
        lease_ttl_seconds=previous_loop._lease_ttl,
    )


def test_run3_restart_resumes_after_durable_worker_acceptance_without_replay(tmp_path):
    import pytest
    from scripts.third_engineering_run import build_loop, prepare_workspace
    from vajra.runtime.run_manager import RunManager
    from vajra.runtime.sqlite_run_store import SQLiteRunStore

    class CrashAfterAcceptance:
        def observe(self, *, phase, run_id, payload):
            if phase.value == "OBSERVE":
                raise RuntimeError("simulated process crash after worker acceptance")

    class Gateway:
        def __init__(self):
            identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
            self.adapter = TransportWorkerModelAdapter(
                FakeKaggleResultTransport(), identity, timeout_seconds=1
            )

        def invoke(self, request, model_identity):
            return self.adapter.invoke(request)

    workspace = tmp_path / "restart-after-acceptance"
    revision = prepare_workspace(workspace)
    identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
    database = tmp_path / "restart-after-acceptance.sqlite3"
    loop, manager, store = build_loop(
        workspace, revision, Gateway(), identity, "run3-restart-accepted", database
    )
    loop._observer = CrashAfterAcceptance()

    with pytest.raises(RuntimeError, match="simulated process crash"):
        loop.run("run3-restart-accepted")
    interrupted = manager.get_run("run3-restart-accepted")
    assert interrupted.state.value == "EXECUTING"
    assert len(interrupted.steps[0].attempts) == 1
    assert interrupted.steps[0].attempts[0].state.value == "SUCCEEDED"
    store.close()

    with SQLiteRunStore(database) as reopened:
        recovered_manager = RunManager(state_store=reopened, event_store=reopened)
        resumed = _rebuild_run3_loop_after_restart(loop, recovered_manager, reopened)
        result = resumed.run("run3-restart-accepted")
        recovered = recovered_manager.get_run("run3-restart-accepted")

        assert result.completed is True
        assert recovered.state.value == "COMPLETE"
        assert len(recovered.steps) == 2
        assert len(recovered.steps[0].attempts) == 1, "accepted intent must not be dispatched twice"
        assert len(recovered.steps[1].attempts) == 1


def test_run3_restart_waits_for_human_when_attempt_outcome_is_ambiguous(tmp_path):
    import pytest
    from scripts.third_engineering_run import build_loop, prepare_workspace
    from vajra.runtime.run_manager import RunManager
    from vajra.runtime.sqlite_run_store import SQLiteRunStore

    class CrashBeforeDispatch:
        def observe(self, *, phase, run_id, payload):
            if phase.value == "EXECUTE":
                raise RuntimeError("simulated process crash with a running attempt")

    class Gateway:
        def __init__(self):
            identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
            self.adapter = TransportWorkerModelAdapter(
                FakeKaggleResultTransport(), identity, timeout_seconds=1
            )

        def invoke(self, request, model_identity):
            return self.adapter.invoke(request)

    workspace = tmp_path / "restart-ambiguous-attempt"
    revision = prepare_workspace(workspace)
    identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
    database = tmp_path / "restart-ambiguous-attempt.sqlite3"
    loop, manager, store = build_loop(
        workspace, revision, Gateway(), identity, "run3-restart-ambiguous", database
    )
    loop._observer = CrashBeforeDispatch()

    with pytest.raises(RuntimeError, match="simulated process crash"):
        loop.run("run3-restart-ambiguous")
    interrupted = manager.get_run("run3-restart-ambiguous")
    assert interrupted.state.value == "EXECUTING"
    assert interrupted.steps[0].attempts[0].state.value == "RUNNING"
    store.close()

    with SQLiteRunStore(database) as reopened:
        recovered_manager = RunManager(state_store=reopened, event_store=reopened)
        resumed = _rebuild_run3_loop_after_restart(loop, recovered_manager, reopened)
        result = resumed.run("run3-restart-ambiguous")
        recovered = recovered_manager.get_run("run3-restart-ambiguous")

        assert result.waiting_human is True
        assert recovered.state.value == "WAITING_HUMAN"
        assert "outcome is ambiguous" in result.reason
        assert len(recovered.steps[0].attempts) == 1, "ambiguous attempt must never be auto-replayed"
