from __future__ import annotations

import argparse
import subprocess
import sys
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


class ProjectFileBackend:
    """Bounded backend for Run #2: only creates/updates project files."""

    def execute(self, request):
        if request.intent.operation != "WRITE_FILE":
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                operation=request.intent.operation,
                errors=("run-2 backend only permits WRITE_FILE",),
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
class RealProjectReasoner:
    workspace: Path
    plan_calls: int = 0

    def orient(self, context):
        return "inspect the small Python project and implement the requested calculator feature with a regression test"

    def plan(self, context, orientation):
        self.plan_calls += 1
        suffix = self.plan_calls
        return EngineeringPlan(
            plan_id=f"run-2-plan-{suffix}",
            context_digest=context.digest,
            intents=(
                PlannedIntent(
                    intent_id=f"calculator-implementation-{suffix}",
                    operation="WRITE_FILE",
                    parameters={
                        "path": "calculator.py",
                        "content": (
                            '"""Tiny calculator module managed by the VAJRA Run #2 fixture."""\n\n'
                            "def add(a: int, b: int) -> int:\n"
                            '    """Return the sum of two integers."""\n'
                            "    return a + b\n\n"
                            "def multiply(a: int, b: int) -> int:\n"
                            '    """Return the product of two integers."""\n'
                            "    return a * b\n"
                        ),
                        "workspace": str(self.workspace),
                    },
                    reason="implement the requested multiply feature",
                    strategy_id=f"calculator-feature-v{suffix}",
                ),
                PlannedIntent(
                    intent_id=f"calculator-test-{suffix}",
                    operation="WRITE_FILE",
                    parameters={
                        "path": "test_calculator.py",
                        "content": (
                            "from calculator import add, multiply\n\n"
                            "def test_add_existing_behavior() -> None:\n"
                            "    assert add(2, 3) == 5\n\n"
                            "def test_multiply_new_behavior() -> None:\n"
                            "    assert multiply(6, 7) == 42\n"
                        ),
                        "workspace": str(self.workspace),
                    },
                    reason="add a regression test proving the new behavior",
                    strategy_id=f"calculator-feature-v{suffix}",
                ),
            ),
            strategy_id=f"calculator-feature-v{suffix}",
        )

    def replan(self, context, previous_plan, failure_reason):
        return self.plan(context, "replan after verification feedback")


def _git(*args: str, cwd: Path) -> str:
    return subprocess.check_output(("git", "-C", str(cwd), *args), text=True).strip()


def prepare_workspace(workspace: Path) -> str:
    workspace.mkdir(parents=True, exist_ok=True)
    if not (workspace / ".git").exists():
        subprocess.run(("git", "init", "-q", str(workspace)), check=True)
        (workspace / "calculator.py").write_text(
            '"""Tiny calculator module: intentionally missing multiply()."""\n\n'
            "def add(a: int, b: int) -> int:\n"
            '    """Return the sum of two integers."""\n'
            "    return a + b\n",
            encoding="utf-8",
        )
        (workspace / "test_calculator.py").write_text(
            "from calculator import add\n\n"
            "def test_add_existing_behavior() -> None:\n"
            "    assert add(2, 3) == 5\n",
            encoding="utf-8",
        )
        (workspace / "README.md").write_text(
            "# VAJRA Run #2 fixture\n\n"
            "Disposable Python project used to validate a real code change.\n",
            encoding="utf-8",
        )
        subprocess.run(("git", "-C", str(workspace), "add", "."), check=True)
        subprocess.run(
            (
                "git", "-C", str(workspace),
                "-c", "user.name=VAJRA",
                "-c", "user.email=vajra@example.invalid",
                "commit", "-qm", "base calculator project",
            ),
            check=True,
        )
    return _git("rev-parse", "HEAD", cwd=workspace)


def build_loop(workspace: Path, revision: str, run_id: str):
    state = InMemoryStateStore()
    events = InMemoryEventStore()
    manager = RunManager(state_store=state, event_store=events)

    objective = "Add multiply(a, b) to calculator.py and add a regression test proving multiply(6, 7) == 42."
    run = EngineeringRun(
        run_id=run_id,
        objective=objective,
        repository_id="vajra-run-2-repo",
        base_revision=revision,
        acceptance_criteria=("multiply exists and its regression test passes",),
        policy_id="vajra-run-2-policy",
        policy_version="1",
        budget_id="vajra-run-2-budget",
        created_by="human",
    )
    manager.create_run(run)

    criteria = AcceptanceCriteria(
        criteria_id="vajra-run-2-criteria",
        version="1",
        objective_digest=stable_digest(objective),
        predicates=(
            AcceptancePredicate("implementation", "1", "multiply implementation exists"),
            AcceptancePredicate("regression", "1", "multiply regression test exists"),
            AcceptancePredicate("tests", "1", "project tests pass"),
        ),
        required_evidence=("verification_result",),
        verification_plan_ref="vajra-run-2-criteria",
        created_at=datetime.now(timezone.utc),
        frozen_at=datetime.now(timezone.utc),
    )
    verification_plan = AcceptanceCriteriaCompiler().compile(
        objective,
        criteria,
        (
            {
                "predicate_id": "implementation",
                "kind": "FILE_CONTAINS",
                "path": "calculator.py",
                "needle": "def multiply",
            },
            {
                "predicate_id": "regression",
                "kind": "FILE_CONTAINS",
                "path": "test_calculator.py",
                "needle": "multiply(6, 7) == 42",
            },
            {
                "predicate_id": "tests",
                "kind": "COMMAND_EXIT",
                "command": (sys.executable, "-m", "pytest", "-q"),
                "expected_exit_code": 0,
            },
        ),
    )

    policy = PolicyEvaluator(
        "vajra-run-2-policy",
        "1",
        (
            PolicyRule("write", "WRITE_FILE", PolicyDecisionType.ALLOW, "bounded project file change"),
            PolicyRule("promote", "PROMOTE_RUN", PolicyDecisionType.ALLOW, "independent tests passed"),
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
            broker=ExecutionBroker(ProjectFileBackend()),
            verifier=IndependentVerifier(SubprocessVerificationExecutor()),
            reasoning=RealProjectReasoner(workspace),
            acceptance=criteria,
            verification_plan=verification_plan,
            verification_environment=VerificationEnvironment(
                workspace=workspace.resolve(),
                network_enabled=True,
                sandbox_id=None,
                environment=(
                    ("PYTHONPATH", str(workspace.resolve())),
                    ("PYTHONDONTWRITEBYTECODE", "1"),
                ),
            ),
            workspace=WorkspaceRuntime(
                workspace.resolve(),
                "vajra-run-2-workspace",
                "vajra-run-2-repo",
                revision,
            ),
            budget=Budget("vajra-run-2-budget", 300, 20, 20, 20, 40, 2_000_000, 300),
            bounded_autonomy=BoundedAutonomy(),
            max_cycles=32,
        ),
        manager,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run VAJRA Engineering Run #2 against a disposable real Python project.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.home() / "vajra-run-2-project",
        help="disposable project path (default: ~/vajra-run-2-project)",
    )
    parser.add_argument(
        "--run-id",
        default="second-engineering-run",
        help="durable Engineering Run identifier",
    )
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    revision = prepare_workspace(workspace)
    loop, manager = build_loop(workspace, revision, args.run_id)

    print("=== VAJRA ENGINEERING RUN #2 ===")
    print(f"workspace: {workspace}")
    print(f"base_revision: {revision}")
    print(f"run_id: {args.run_id}")
    print("objective: add multiply() and prove it with pytest")
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
    print(f"git_status: {_git('status', '--porcelain', cwd=workspace) or 'clean'}")
    print(f"project: {workspace}")

    if not result.completed:
        print(f"reason: {result.reason}")
        return 1

    assert (workspace / "calculator.py").read_text(encoding="utf-8").find("def multiply") >= 0
    assert (workspace / "test_calculator.py").read_text(encoding="utf-8").find("multiply(6, 7) == 42") >= 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
