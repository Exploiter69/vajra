from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vajra.autonomy import AutonomousEngineeringLoop, EngineeringPlan, PlannedIntent, WorkspaceRuntime
from vajra.context import ContextEngine
from vajra.control.contracts import AcceptanceCriteria, AcceptancePredicate, stable_digest
from vajra.control.controller import Controller
from vajra.control.limits import BoundedAutonomy
from vajra.domain import Budget, EngineeringRun
from vajra.execution.broker import ExecutionBroker
from vajra.execution.contracts import ExecutionResult, ExecutionStatus
from vajra.policy.contracts import PolicyDecisionType
from vajra.policy.evaluator import PolicyEvaluator, PolicyRule
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore
from vajra.verification.environment import VerificationEnvironment
from vajra.verification.independent import IndependentVerifier, SubprocessVerificationExecutor
from vajra.verification.plan import AcceptanceCriteriaCompiler


class LocalFileBackend:
    """Minimal first-run backend: executes only the WRITE_FILE operation."""

    def execute(self, request):
        if request.intent.operation != "WRITE_FILE":
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                operation=request.intent.operation,
                errors=("first-run backend only permits WRITE_FILE",),
            )
        path = request.intent.parameters["path"]
        content = request.intent.parameters["content"]
        target = Path(request.intent.parameters["workspace"]) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ExecutionResult(
            status=ExecutionStatus.ACCEPTED,
            operation=request.intent.operation,
        )


@dataclass
class FirstRunReasoner:
    workspace: Path
    plan_calls: int = 0

    def orient(self, context):
        return "inspect the disposable repository and create the requested health artifact"

    def plan(self, context, orientation):
        self.plan_calls += 1
        return EngineeringPlan(
            plan_id=f"first-run-plan-{self.plan_calls}",
            context_digest=context.digest,
            intents=(
                PlannedIntent(
                    intent_id=f"write-health-{self.plan_calls}",
                    operation="WRITE_FILE",
                    parameters={
                        "path": "result.txt",
                        "content": "done\\n",
                        "workspace": str(self.workspace),
                    },
                    reason="create the bounded first-run artifact",
                    strategy_id=f"first-run-write-v{self.plan_calls}",
                ),
            ),
            strategy_id=f"first-run-write-v{self.plan_calls}",
        )

    def replan(self, context, previous_plan, failure_reason):
        return self.plan(context, "replan after recovery")


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(
        ("git", "-C", str(cwd), *args),
        text=True,
    ).strip()


def prepare_workspace(workspace: Path) -> str:
    workspace.mkdir(parents=True, exist_ok=True)
    if not (workspace / ".git").exists():
        subprocess.run(("git", "init", "-q", str(workspace)), check=True)
        (workspace / "README.md").write_text(
            "# VAJRA first Engineering Run\\n\\nDisposable validation repository.\\n",
            encoding="utf-8",
        )
        subprocess.run(("git", "-C", str(workspace), "add", "README.md"), check=True)
        subprocess.run(
            (
                "git", "-C", str(workspace),
                "-c", "user.name=VAJRA",
                "-c", "user.email=vajra@example.invalid",
                "commit", "-qm", "first-run base",
            ),
            check=True,
        )
    return _git("rev-parse", "HEAD", cwd=workspace)


def build_loop(workspace: Path, revision: str, run_id: str):
    state = InMemoryStateStore()
    events = InMemoryEventStore()
    manager = RunManager(state_store=state, event_store=events)

    objective = 'Create result.txt containing exactly "done" and prove it exists.'
    run = EngineeringRun(
        run_id=run_id,
        objective=objective,
        repository_id="vajra-first-run-repo",
        base_revision=revision,
        acceptance_criteria=("result.txt exists",),
        policy_id="vajra-first-run-policy",
        policy_version="1",
        budget_id="vajra-first-run-budget",
        created_by="human",
    )
    manager.create_run(run)

    criteria = AcceptanceCriteria(
        criteria_id="vajra-first-run-criteria",
        version="1",
        objective_digest=stable_digest(objective),
        predicates=(
            AcceptancePredicate("result", "1", "result file exists"),
        ),
        required_evidence=("verification_result",),
        verification_plan_ref="vajra-first-run-criteria",
        created_at=datetime.now(timezone.utc),
        frozen_at=datetime.now(timezone.utc),
    )
    verification_plan = AcceptanceCriteriaCompiler().compile(
        objective,
        criteria,
        (
            {
                "predicate_id": "result",
                "kind": "FILE_EXISTS",
                "path": "result.txt",
            },
        ),
    )

    policy = PolicyEvaluator(
        "vajra-first-run-policy",
        "1",
        (
            PolicyRule("write", "WRITE_FILE", PolicyDecisionType.ALLOW, "first-run write"),
            PolicyRule("promote", "PROMOTE_RUN", PolicyDecisionType.ALLOW, "verified first-run promotion"),
        ),
    )

    return (
        AutonomousEngineeringLoop(
            run_manager=manager,
            state_store=state,
            event_store=events,
            context_engine=ContextEngine(),
            controller=Controller(),
            policy=policy,
            broker=ExecutionBroker(LocalFileBackend()),
            verifier=IndependentVerifier(SubprocessVerificationExecutor()),
            reasoning=FirstRunReasoner(workspace),
            acceptance=criteria,
            verification_plan=verification_plan,
            verification_environment=VerificationEnvironment(
                workspace=workspace.resolve(),
                network_enabled=False,
                sandbox_id="first-run-local",
            ),
            workspace=WorkspaceRuntime(
                workspace.resolve(),
                "vajra-first-run-workspace",
                "vajra-first-run-repo",
                revision,
            ),
            budget=Budget("vajra-first-run-budget", 300, 10, 10, 10, 20, 1_000_000, 300),
            bounded_autonomy=BoundedAutonomy(),
            max_cycles=20,
        ),
        manager,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run VAJRA Engineering Run #1 in a disposable repository.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.home() / "vajra-first-run",
        help="disposable repository path (default: ~/vajra-first-run)",
    )
    parser.add_argument(
        "--run-id",
        default="first-engineering-run",
        help="durable Engineering Run identifier",
    )
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    revision = prepare_workspace(workspace)
    loop, manager = build_loop(workspace, revision, args.run_id)

    print("=== VAJRA ENGINEERING RUN #1 ===")
    print(f"workspace: {workspace}")
    print(f"base_revision: {revision}")
    print(f"run_id: {args.run_id}")
    print()

    result = loop.run(args.run_id)
    run = manager.get_run(args.run_id)

    print(f"result: {'COMPLETE' if result.completed else run.state.value}")
    print(f"cycles: {result.cycles}")
    print(f"steps: {len(run.steps)}")
    print(f"attempts: {sum(len(step.attempts) for step in run.steps)}")
    print(f"verification_results: {len(run.verification_results)}")
    print(f"artifacts: {len(run.artifacts)}")
    print(f"events: {len(manager.events(args.run_id))}")
    print(f"result_file: {workspace / 'result.txt'}")

    if not result.completed:
        print(f"reason: {result.reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
