from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vajra.autonomy import AutonomousEngineeringLoop, EngineeringPlan, PlannedIntent, WorkspaceRuntime
from vajra.context import ContextEngine
from vajra.control.acceptance import AcceptanceEvaluator
from vajra.control.controller import Controller
from vajra.control.contracts import AcceptanceCriteria, AcceptancePredicate, stable_digest
from vajra.control.limits import BoundedAutonomy
from vajra.domain import Budget
from vajra.execution.broker import ExecutionBroker
from vajra.execution.contracts import ExecutionResult, ExecutionStatus
from vajra.policy.contracts import PolicyDecisionType
from vajra.policy.evaluator import PolicyEvaluator, PolicyRule
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore
from vajra.verification.environment import VerificationEnvironment
from vajra.verification.independent import IndependentVerifier
from vajra.verification.plan import AcceptanceCriteriaCompiler
from vajra.verification.independent import SubprocessVerificationExecutor


class FileBackend:
    def execute(self, request):
        path = request.intent.parameters["path"]
        content = request.intent.parameters["content"]
        target = Path(request.intent.parameters["workspace"]) / path
        target.write_text(content, encoding="utf-8")
        return ExecutionResult(status=ExecutionStatus.ACCEPTED, operation=request.intent.operation)


@dataclass
class Reasoner:
    plan_calls: int = 0
    replan_calls: int = 0

    def orient(self, context):
        assert context.items[0].source_kind.value == "OBJECTIVE"
        return "inspect the repository and create the requested file"

    def plan(self, context, orientation):
        self.plan_calls += 1
        return EngineeringPlan(
            plan_id=f"plan-{self.plan_calls}",
            context_digest=context.digest,
            intents=(
                PlannedIntent(
                    intent_id=f"write-{self.plan_calls}",
                    operation="WRITE_FILE",
                    parameters={"path": "result.txt", "content": "done\n", "workspace": str(TEST_WORKSPACE)},
                    reason="create the objective artifact",
                    strategy_id=f"write-v{self.plan_calls}",
                ),
            ),
            strategy_id=f"write-v{self.plan_calls}",
        )

    def replan(self, context, previous_plan, failure_reason):
        self.replan_calls += 1
        return self.plan(context, "replan")


TEST_WORKSPACE = "/tmp/vajra-phase10-loop"


def make_run(objective: str, base_revision: str):
    from vajra.domain import EngineeringRun

    return EngineeringRun(
        run_id="phase10-run",
        objective=objective,
        repository_id="phase10-repo",
        base_revision=base_revision,
        acceptance_criteria=("result.txt exists",),
        policy_id="phase10-policy",
        policy_version="1",
        budget_id="phase10-budget",
        created_by="test",
    )


def build_loop(tmp_path):
    global TEST_WORKSPACE
    workspace = tmp_path / "repo"
    workspace.mkdir()
    subprocess.run(("git", "init", "-q", str(workspace)), check=True)
    (workspace / "README.md").write_text("phase10\n", encoding="utf-8")
    subprocess.run(("git", "-C", str(workspace), "add", "README.md"), check=True)
    subprocess.run(("git", "-C", str(workspace), "-c", "user.name=VAJRA", "-c", "user.email=vajra@example.invalid", "commit", "-qm", "base"), check=True)
    revision = subprocess.check_output(("git", "-C", str(workspace), "rev-parse", "HEAD"), text=True).strip()
    TEST_WORKSPACE = str(workspace)

    state = InMemoryStateStore()
    events = InMemoryEventStore()
    manager = RunManager(state_store=state, event_store=events)
    run = make_run("create result.txt", revision)
    manager.create_run(run)

    objective_digest = stable_digest(run.objective)
    criteria = AcceptanceCriteria(
        criteria_id="phase10-criteria",
        version="1",
        objective_digest=objective_digest,
        predicates=(AcceptancePredicate("result", "1", "result file exists"),),
        required_evidence=("verification_result",),
        verification_plan_ref="phase10-criteria",
        created_at=datetime.now(timezone.utc),
        frozen_at=datetime.now(timezone.utc),
    )
    plan = AcceptanceCriteriaCompiler().compile(
        run.objective,
        criteria,
        ({"predicate_id": "result", "kind": "FILE_EXISTS", "path": "result.txt"},),
    )

    policy = PolicyEvaluator(
        "phase10-policy",
        "1",
        (
            PolicyRule("write", "WRITE_FILE", PolicyDecisionType.ALLOW, "test write"),
            PolicyRule("promote", "PROMOTE_RUN", PolicyDecisionType.ALLOW, "verified promotion"),
        ),
    )
    verifier = IndependentVerifier(SubprocessVerificationExecutor())
    environment = VerificationEnvironment(workspace=workspace.resolve(), network_enabled=False, sandbox_id="test-sandbox")
    loop = AutonomousEngineeringLoop(
        run_manager=manager,
        state_store=state,
        event_store=events,
        context_engine=ContextEngine(),
        controller=Controller(),
        policy=policy,
        broker=ExecutionBroker(FileBackend()),
        verifier=verifier,
        reasoning=Reasoner(),
        acceptance=criteria,
        verification_plan=plan,
        verification_environment=environment,
        workspace=WorkspaceRuntime(workspace.resolve(), "ws-phase10", "phase10-repo", revision),
        budget=Budget("phase10-budget", 300, 10, 10, 10, 20, 1_000_000, 300),
        bounded_autonomy=BoundedAutonomy(),
        max_cycles=20,
    )
    return loop, manager, workspace


def test_phase10_completes_end_to_end(tmp_path):
    loop, manager, workspace = build_loop(tmp_path)
    result = loop.run("phase10-run")

    assert result.completed is True
    assert manager.get_run("phase10-run").state.value == "COMPLETE"
    assert (workspace / "result.txt").read_text(encoding="utf-8") == "done\n"
    assert manager.get_run("phase10-run").verification_results
    assert manager.get_run("phase10-run").artifacts
    assert any(event.event_type == "RUN_COMPLETED" for event in manager.events("phase10-run"))


def test_phase10_model_cannot_bypass_policy(tmp_path):
    loop, manager, _ = build_loop(tmp_path)
    loop._policy = PolicyEvaluator("phase10-policy", "1", ())

    result = loop.run("phase10-run")

    assert result.waiting_human is True
    assert manager.get_run("phase10-run").state.value == "WAITING_HUMAN"


def test_phase10_plan_is_bound_to_fresh_context(tmp_path):
    loop, manager, _ = build_loop(tmp_path)

    class StaleReasoner(Reasoner):
        def plan(self, context, orientation):
            return EngineeringPlan("stale", "wrong-context", (PlannedIntent("x", "WRITE_FILE", reason="x"),))

    loop._reasoning = StaleReasoner()
    try:
        loop.run("phase10-run")
    except Exception as exc:
        assert "stale or different context" in str(exc)
    else:
        raise AssertionError("stale plan was accepted")


def test_phase10_completion_requires_verification_evidence(tmp_path):
    loop, manager, workspace = build_loop(tmp_path)
    run = manager.get_run("phase10-run")
    assert run.state.value == "CREATED"
    assert not run.verification_results
    assert not run.artifacts
    assert not (workspace / "result.txt").exists()


def test_phase10_respects_hard_cycle_bound(tmp_path):
    loop, manager, _ = build_loop(tmp_path)
    loop._max_cycles = 1

    result = loop.run("phase10-run")

    assert result.stopped is True
    assert result.completed is False
    assert manager.get_run("phase10-run").state.value in {"QUEUED", "CREATED"}


def test_phase10_records_full_control_plane_trace(tmp_path):
    loop, manager, _ = build_loop(tmp_path)
    result = loop.run("phase10-run")
    assert result.completed
    event_types = {event.event_type for event in manager.events("phase10-run")}
    for expected in {
        "AUTONOMY_OBJECTIVE",
        "AUTONOMY_ORIENT",
        "AUTONOMY_PLAN",
        "AUTONOMY_INTENT",
        "AUTONOMY_POLICY",
        "AUTONOMY_EXECUTE",
        "AUTONOMY_OBSERVE",
        "AUTONOMY_VERIFY",
        "AUTONOMY_MEASURE_PROGRESS",
        "AUTONOMY_DECIDE_NEXT_STEP",
        "RUN_COMPLETED",
    }:
        assert expected in event_types
