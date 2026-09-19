from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from vajra.autonomy import AutonomousEngineeringLoop, WorkspaceRuntime
from vajra.context import ContextEngine
from vajra.control.contracts import AcceptanceCriteria, AcceptancePredicate, stable_digest
from vajra.control.controller import Controller
from vajra.control.limits import BoundedAutonomy
from vajra.domain import Budget, EngineeringRun
from vajra.execution.broker import ExecutionBroker
from vajra.execution.contracts import ExecutionResult, ExecutionStatus
from vajra.policy.contracts import PolicyDecisionType
from vajra.policy.evaluator import PolicyEvaluator, PolicyRule
from vajra.routing.contracts import ModelIdentity
from vajra.runtime.remote_model import build_remote_gateway, build_kaggle_batch_gateway
from vajra.runtime.worker_provider import HTTPWorkerProvider, WorkerProviderError
from vajra.runtime.remote_reasoner import GatewayReasoner
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore
from vajra.verification.environment import VerificationEnvironment
from vajra.verification.independent import IndependentVerifier, SubprocessVerificationExecutor
from vajra.verification.plan import AcceptanceCriteriaCompiler


class ProjectFileBackend:
    def execute(self, request):
        if request.intent.operation != "WRITE_FILE":
            return ExecutionResult(status=ExecutionStatus.REJECTED, operation=request.intent.operation,
                                   errors=("run-3 backend only permits WRITE_FILE",))
        path = request.intent.parameters["path"]
        if path not in {"calculator.py", "test_calculator.py"}:
            return ExecutionResult(status=ExecutionStatus.REJECTED, operation=request.intent.operation,
                                   errors=("run-3 backend rejected path",))
        target = Path(request.intent.parameters["workspace"]) / path
        target.write_text(request.intent.parameters["content"], encoding="utf-8")
        return ExecutionResult(status=ExecutionStatus.ACCEPTED, operation=request.intent.operation)


def git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(("git", "-C", str(cwd), *args), text=True).strip()


def prepare_workspace(workspace: Path) -> str:
    workspace.mkdir(parents=True, exist_ok=True)
    subprocess.run(("git", "init", "-q", str(workspace)), check=True)
    (workspace / "calculator.py").write_text(
        '"""Tiny calculator module: intentionally missing multiply()."""\n\n'
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8")
    (workspace / "test_calculator.py").write_text(
        "from calculator import add\n\n"
        "def test_add_existing_behavior() -> None:\n    assert add(2, 3) == 5\n",
        encoding="utf-8")
    subprocess.run(("git", "-C", str(workspace), "add", "."), check=True)
    subprocess.run(("git", "-C", str(workspace), "-c", "user.name=VAJRA",
                     "-c", "user.email=vajra@example.invalid", "commit", "-qm",
                     "base calculator project"), check=True)
    return git("rev-parse", "HEAD", cwd=workspace)


def build_loop(workspace: Path, revision: str, gateway: object, model_identity: ModelIdentity, run_id: str):
    state, events = InMemoryStateStore(), InMemoryEventStore()
    manager = RunManager(state_store=state, event_store=events)
    objective = "Add multiply(a, b) to calculator.py and add a regression test proving multiply(6, 7) == 42."
    run = EngineeringRun(
        run_id=run_id, objective=objective, repository_id="vajra-run-3-repo",
        base_revision=revision, acceptance_criteria=("multiply exists and its regression test passes",),
        policy_id="vajra-run-3-policy", policy_version="1", budget_id="vajra-run-3-budget", created_by="human")
    manager.create_run(run)

    criteria = AcceptanceCriteria(
        criteria_id="vajra-run-3-criteria", version="1", objective_digest=stable_digest(objective),
        predicates=(
            AcceptancePredicate("implementation", "1", "multiply implementation exists"),
            AcceptancePredicate("regression", "1", "multiply regression test exists"),
            AcceptancePredicate("tests", "1", "project tests pass"),
        ),
        required_evidence=("verification_result",), verification_plan_ref="vajra-run-3-criteria",
        created_at=datetime.now(timezone.utc), frozen_at=datetime.now(timezone.utc))
    plan = AcceptanceCriteriaCompiler().compile(
        objective, criteria,
        ({"predicate_id": "implementation", "kind": "FILE_CONTAINS", "path": "calculator.py", "needle": "def multiply"},
         {"predicate_id": "regression", "kind": "FILE_CONTAINS", "path": "test_calculator.py", "needle": "multiply(6, 7) == 42"},
         {"predicate_id": "tests", "kind": "COMMAND_EXIT", "command": (sys.executable, "-m", "pytest", "-q"), "expected_exit_code": 0}))

    policy = PolicyEvaluator("vajra-run-3-policy", "1", (
        PolicyRule("write", "WRITE_FILE", PolicyDecisionType.ALLOW, "bounded project file change"),
        PolicyRule("promote", "PROMOTE_RUN", PolicyDecisionType.ALLOW, "independent tests passed")))
    loop = AutonomousEngineeringLoop(
        run_manager=manager, state_store=state, event_store=events, context_engine=ContextEngine(),
        controller=Controller(), policy=policy, broker=ExecutionBroker(ProjectFileBackend()),
        verifier=IndependentVerifier(SubprocessVerificationExecutor()),
        reasoning=GatewayReasoner(gateway, model_identity.canonical, single_call_plan=True),
        acceptance=criteria, verification_plan=plan,
        verification_environment=VerificationEnvironment(
            workspace=workspace.resolve(), network_enabled=True, sandbox_id=None,
            environment=(("PYTHONPATH", str(workspace.resolve())), ("PYTHONDONTWRITEBYTECODE", "1"))),
        workspace=WorkspaceRuntime(workspace.resolve(), "vajra-run-3-workspace", "vajra-run-3-repo", revision),
        budget=Budget("vajra-run-3-budget", 2400, 20, 20, 20, 40, 4_000_000, 2400),
        bounded_autonomy=BoundedAutonomy(), max_cycles=32)
    return loop, manager


def main() -> int:
    parser = argparse.ArgumentParser(description="VAJRA Run #3: real Qwen proposal through ModelGateway.")
    parser.add_argument("--workspace", type=Path, default=Path.home() / "vajra-run-3-project")
    parser.add_argument("--run-id", default="third-engineering-run")
    parser.add_argument("--endpoint", default=os.environ.get("VAJRA_KAGGLE_WORKER_URL", "http://127.0.0.1:8787/infer"))
    parser.add_argument("--kaggle-batch", action="store_true", default=os.environ.get("VAJRA_KAGGLE_MODE") == "batch")
    parser.add_argument("--kernel-template", type=Path, default=Path(os.environ.get("VAJRA_KAGGLE_KERNEL_TEMPLATE", "infra/kaggle/burst_worker")))
    parser.add_argument("--kernel-ref", default=os.environ.get("VAJRA_KAGGLE_KERNEL_REF", ""))
    args = parser.parse_args()

    identity = ModelIdentity("kaggle", "qwen2.5-coder:32b", "ollama", "http-worker")
    endpoint = None
    if args.kaggle_batch:
        template = args.kernel_template.expanduser().resolve()
        if not template.is_dir():
            print(f"worker_not_ready: Kaggle kernel template not found: {template}")
            print("No project mutation or model call was attempted.")
            return 2
        if not args.kernel_ref.strip():
            print("worker_not_ready: --kernel-ref or VAJRA_KAGGLE_KERNEL_REF is required for batch mode")
            print("No project mutation or model call was attempted.")
            return 2
        gateway = build_kaggle_batch_gateway(template, args.kernel_ref)
        mode = "kaggle-batch"
    else:
        provider = HTTPWorkerProvider(infer_url=args.endpoint, expected_model=identity.model)
        try:
            endpoint = provider.ensure_ready()
        except WorkerProviderError as exc:
            print(f"worker_not_ready: {exc}")
            print("No project mutation or model call was attempted.")
            print("Start the configured worker session and expose its /health, /capabilities, and /infer endpoints, then rerun.")
            return 2
        gateway = build_remote_gateway(endpoint.infer_url, identity)
        mode = "http"

    workspace = args.workspace.expanduser().resolve()
    revision = prepare_workspace(workspace)
    loop, manager = build_loop(workspace, revision, gateway, identity, args.run_id)

    print("=== VAJRA ENGINEERING RUN #3 ===")
    print(f"workspace: {workspace}")
    print(f"base_revision: {revision}")
    print(f"run_id: {args.run_id}")
    print(f"model: {identity.canonical}")
    print(f"mode: {mode}")
    if endpoint is not None:
        print(f"endpoint: {endpoint.infer_url}")
        print(f"worker: {endpoint.worker_id}")
        print(f"protocol: {endpoint.protocol}")
        print(f"capabilities: {', '.join(endpoint.capabilities) or 'none advertised'}")
    else:
        print(f"kernel_ref: {args.kernel_ref}")

    print("authority: model proposes; VAJRA policy/broker/verifier decide")
    print()
    result = loop.run(args.run_id)
    run = manager.get_run(args.run_id)
    print(f"result: {'COMPLETE' if result.completed else run.state.value}")
    print(f"cycles: {result.cycles}")
    print(f"steps: {len(run.steps)}")
    print(f"attempts: {sum(len(s.attempts) for s in run.steps)}")
    print(f"verification_results: {len(run.verification_results)}")
    print(f"artifacts: {len(run.artifacts)}")
    print(f"events: {len(manager.events(args.run_id))}")
    print(f"git_status: {git('status', '--porcelain', cwd=workspace) or 'clean'}")
    if not result.completed:
        print(f"reason: {result.reason}")
        return 1
    assert "def multiply" in (workspace / "calculator.py").read_text(encoding="utf-8")
    assert "multiply(6, 7) == 42" in (workspace / "test_calculator.py").read_text(encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
