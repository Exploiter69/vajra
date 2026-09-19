from __future__ import annotations

import json
from pathlib import Path

from vajra.domain import ArtifactRef
from vajra.routing.contracts import ModelIdentity, ModelResult, ModelUsage
from vajra.runtime.remote_model import TransportWorkerModelAdapter
from vajra.runtime.worker_protocol import WorkerResult
from vajra.runtime.remote_reasoner import GatewayReasoner
from vajra.runtime.worker_protocol import WorkerJob

from third_engineering_run import build_loop, prepare_workspace


class ReplayTransport:
    """Local replay of the exact WorkerResult shape returned by Kaggle/Qwen."""

    def execute(self, job: WorkerJob) -> WorkerResult:
        plan = {
            "orientation": "Implement multiply and add its regression test.",
            "plan_id": "replay-plan-1",
            "strategy_id": "qwen-run-3",
            "intents": [
                {
                    "intent_id": "write-calculator",
                    "operation": "WRITE_FILE",
                    "path": "calculator.py",
                    "content": (
                        '"""Tiny calculator module."""\n\n'
                        "def add(a: int, b: int) -> int:\n"
                        "    return a + b\n\n"
                        "def multiply(a: int, b: int) -> int:\n"
                        "    return a * b\n"
                    ),
                    "reason": "implement multiply",
                },
                {
                    "intent_id": "write-test-calculator",
                    "operation": "WRITE_FILE",
                    "path": "test_calculator.py",
                    "content": (
                        "from calculator import add, multiply\n\n"
                        "def test_add_existing_behavior() -> None:\n"
                        "    assert add(2, 3) == 5\n\n"
                        "def test_multiply_regression() -> None:\n"
                        "    assert multiply(6, 7) == 42\n"
                    ),
                    "reason": "add regression coverage",
                },
            ],
        }
        return WorkerResult(
            status="completed",
            correlation_id=job.correlation_id,
            structured_result={"response": json.dumps(plan)},
            usage={"prompt_eval_count": 1, "eval_count": 1},
        )


class ReplayGateway:
    def __init__(self) -> None:
        self._identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
        self._adapter = TransportWorkerModelAdapter(ReplayTransport(), self._identity, timeout_seconds=1)

    def invoke(self, request, model_identity):
        return self._adapter.invoke(request)


def main() -> int:
    workspace = Path.home() / "vajra-run-3-replay-project"
    if workspace.exists():
        import shutil
        shutil.rmtree(workspace)

    revision = prepare_workspace(workspace)
    identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "kaggle-batch")
    gateway = ReplayGateway()
    loop, manager = build_loop(workspace, revision, gateway, identity, "third-engineering-run-replay")

    print("=== VAJRA ENGINEERING RUN #3 — LOCAL REPLAY ===")
    print("Kaggle transport: REPLAYED")
    print("Qwen response: REPLAYED")
    print("Control plane: REAL")
    print("Execution broker: REAL")
    print("Independent verifier: REAL")
    print()
    result = loop.run("third-engineering-run-replay")
    run = manager.get_run("third-engineering-run-replay")
    print(f"result: {'COMPLETE' if result.completed else run.state.value}")
    print(f"cycles: {result.cycles}")
    print(f"steps: {len(run.steps)}")
    print(f"attempts: {sum(len(s.attempts) for s in run.steps)}")
    print(f"verification_results: {len(run.verification_results)}")
    print(f"artifacts: {len(run.artifacts)}")
    print(f"events: {len(manager.events('third-engineering-run-replay'))}")
    print(f"git_status: {__import__('subprocess').check_output(('git', '-C', str(workspace), 'status', '--porcelain'), text=True).strip() or 'clean'}")
    if not result.completed:
        print(f"reason: {result.reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
