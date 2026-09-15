from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest

from vajra.control.acceptance import AcceptanceEvaluator
from vajra.control.completion import CompletionDenied
from vajra.control.contracts import (
    AcceptanceCriteria,
    AcceptancePredicate,
    PredicateResult,
    DivergenceClass,
    ReconciliationDisposition,
)
from vajra.control.controller import Controller, ControllerAction
from vajra.control.idempotency import IdempotencyDisposition, IdempotencyRegistry
from vajra.control.limits import BoundedAutonomy, LimitAction
from vajra.control.reality import RealityObserver
from vajra.control.transition_authority import TransitionActor, TransitionDenied
from vajra.control.worktree import WorktreeManager
from vajra.domain import Budget, EngineeringRun, RunState
from vajra.recovery.budget import BudgetUsage
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore
from vajra.runtime.worker_acceptance import WorkerExecutionIdentity, WorkerResultAcceptor
from vajra.runtime.worker_protocol import WorkerResult


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def make_run(base_revision: str = "revision-gate-f") -> EngineeringRun:
    return EngineeringRun(
        run_id="gate-f-real",
        objective="prove Gate F integration",
        repository_id="repo-gate-f",
        base_revision=base_revision,
        acceptance_criteria=("criteria-gate-f",),
        policy_id="policy-gate-f",
        policy_version="1",
        budget_id="budget-gate-f",
        created_by="human",
    )


def make_criteria() -> AcceptanceCriteria:
    now = datetime.now(timezone.utc)
    return AcceptanceCriteria(
        criteria_id="criteria-gate-f",
        version="1",
        objective_digest="objective-gate-f",
        predicates=(
            AcceptancePredicate(
                predicate_id="verification",
                version="1",
                description="independent verification passes",
                required_evidence_kinds=("verification",),
            ),
            AcceptancePredicate(
                predicate_id="artifact",
                version="1",
                description="required artifact exists",
                required_evidence_kinds=("artifact",),
            ),
        ),
        required_evidence=("verification", "artifact"),
        verification_plan_ref="verification-plan-gate-f",
        integrity_digest="criteria-integrity-gate-f",
        created_at=now,
        frozen_at=now,
    )


def make_accepted():
    return AcceptanceEvaluator().evaluate(
        make_criteria(),
        {
            "verification": PredicateResult.TRUE,
            "artifact": PredicateResult.TRUE,
        },
        ("verification", "artifact"),
    )


def advance_to_promotion(manager: RunManager) -> None:
    manager.transition("gate-f-real", RunState.QUEUED, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.ORIENTING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.PLANNING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.EXECUTING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.VERIFYING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.CANDIDATE, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.PROMOTION, TransitionActor.SYSTEM)


def test_controller_proposal_reaches_canonical_run_manager():
    manager = RunManager()
    manager.create_run(make_run())
    controller = Controller()

    decision = controller.decide(manager.get_run("gate-f-real"))
    assert decision.action is ControllerAction.NOOP
    assert decision.target_state is RunState.QUEUED

    controller.authorize_decision(manager.get_run("gate-f-real"), decision)
    manager.transition(
        "gate-f-real",
        decision.target_state,
        TransitionActor.CONTROLLER,
        reason=decision.reason,
    )

    assert manager.get_run("gate-f-real").state is RunState.QUEUED
    assert manager.events("gate-f-real")[-1].event_type == "RUN_STATE_CHANGED"


def test_unauthorized_transition_changes_nothing():
    manager = RunManager()
    manager.create_run(make_run())
    advance_to_promotion(manager)
    before = manager.snapshot("gate-f-real")
    event_count = len(manager.events("gate-f-real"))

    with pytest.raises(TransitionDenied):
        manager.transition(
            "gate-f-real",
            RunState.COMPLETE,
            TransitionActor.CONTROLLER,
            reason="model says done",
        )

    after = manager.snapshot("gate-f-real")
    assert after.run.state is before.run.state is RunState.PROMOTION
    assert len(manager.events("gate-f-real")) == event_count


def test_completion_requires_acceptance_artifact_verification_and_policy():
    manager = RunManager()
    manager.create_run(make_run())
    advance_to_promotion(manager)
    accepted = make_accepted()

    with pytest.raises(CompletionDenied, match="policy approval"):
        manager.complete_run(
            "gate-f-real",
            accepted,
            artifact_refs=("artifact-1",),
            verification_refs=("verification-1",),
            policy_approved=False,
            actor=TransitionActor.SYSTEM,
        )

    with pytest.raises(CompletionDenied, match="artifact evidence"):
        manager.complete_run(
            "gate-f-real",
            accepted,
            artifact_refs=(),
            verification_refs=("verification-1",),
            policy_approved=True,
            actor=TransitionActor.SYSTEM,
        )

    with pytest.raises(CompletionDenied, match="satisfied acceptance"):
        manager.complete_run(
            "gate-f-real",
            AcceptanceEvaluator().evaluate(
                make_criteria(),
                {"verification": PredicateResult.FALSE, "artifact": PredicateResult.TRUE},
                ("verification", "artifact"),
            ),
            artifact_refs=("artifact-1",),
            verification_refs=("verification-1",),
            policy_approved=True,
            actor=TransitionActor.SYSTEM,
        )


def test_completion_is_canonical_and_evidence_bound():
    manager = RunManager()
    manager.create_run(make_run())
    advance_to_promotion(manager)

    result = manager.complete_run(
        "gate-f-real",
        make_accepted(),
        artifact_refs=("artifact-1",),
        verification_refs=("verification-1",),
        policy_approved=True,
        actor=TransitionActor.SYSTEM,
        reason="verified candidate",
    )

    assert result.state is RunState.COMPLETE
    assert manager.get_run("gate-f-real").state is RunState.COMPLETE
    event = manager.events("gate-f-real")[-1]
    assert event.event_type == "RUN_COMPLETED"
    assert event.payload["artifact_refs"] == ["artifact-1"]
    assert event.payload["verification_refs"] == ["verification-1"]


def test_controller_cannot_complete_even_when_completion_evidence_exists():
    manager = RunManager()
    manager.create_run(make_run())
    advance_to_promotion(manager)

    with pytest.raises(TransitionDenied, match="COMPLETE requires SYSTEM or HUMAN"):
        manager.complete_run(
            "gate-f-real",
            make_accepted(),
            artifact_refs=("artifact-1",),
            verification_refs=("verification-1",),
            policy_approved=True,
            actor=TransitionActor.CONTROLLER,
        )

    assert manager.get_run("gate-f-real").state is RunState.PROMOTION


def test_fresh_reality_reconciliation_observes_actual_workspace_divergence(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "vajra@test.invalid")
    git(repo, "config", "user.name", "VAJRA Test")
    (repo / "README").write_text("initial\n", encoding="utf-8")
    git(repo, "add", "README")
    git(repo, "commit", "-q", "-m", "initial")
    revision = git(repo, "rev-parse", "HEAD")

    worktree = WorktreeManager().create(
        run_id="gate-f-real",
        repository_id="repo-gate-f",
        repository=repo,
        base_revision=revision,
        workspace_id="workspace-gate-f",
        path=tmp_path / "worktree",
    )
    run = make_run(revision)

    observer = RealityObserver()
    clean = observer.observe(
        run=run,
        worktree=worktree,
        git_revision=revision,
        git_status="",
        active_lease_state="NONE",
        verification_state="PASSED",
        budget_state="AVAILABLE",
    )
    assert clean.disposition is ReconciliationDisposition.CONSISTENT

    (Path(worktree.path) / "tampered.txt").write_text("divergence\n", encoding="utf-8")
    status = git(Path(worktree.path), "status", "--porcelain=v1")
    dirty = observer.observe(
        run=run,
        worktree=worktree,
        git_revision=revision,
        git_status=status,
        active_lease_state="NONE",
        verification_state="PASSED",
        budget_state="AVAILABLE",
    )

    assert dirty.divergence_class is DivergenceClass.RECOVERABLE
    assert dirty.disposition is ReconciliationDisposition.RECOVERABLE
    assert dirty.freshness == "FRESH"


def test_idempotent_replay_allows_only_one_effect():
    from vajra.control.contracts import OperationIdentity

    registry = IdempotencyRegistry()
    operation = OperationIdentity(
        operation_id="operation-gate-f-real",
        run_id="gate-f-real",
        step_id="step-gate-f",
        attempt_id="attempt-gate-f",
        intent_id="intent-gate-f",
        operation_type="WRITE",
        parameters_digest="parameters-gate-f",
        target_resource="resource-gate-f",
        fencing_token=1,
        idempotency_key="effect-gate-f-real",
    )
    effects = []

    def apply_effect() -> None:
        effects.append("created")

    for _ in range(2):
        decision = registry.check(operation, {"effect": "created"})
        if decision.disposition is IdempotencyDisposition.NEW:
            apply_effect()

    assert effects == ["created"]
    assert registry.contains(operation.idempotency_key)


def test_budget_exhaustion_becomes_durable_abort():
    manager = RunManager()
    manager.create_run(make_run())
    manager.transition("gate-f-real", RunState.QUEUED, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.ORIENTING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.PLANNING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.EXECUTING, TransitionActor.SYSTEM)

    budget = Budget(
        budget_id="budget-gate-f",
        max_runtime_seconds=3600,
        max_steps=100,
        max_attempts=100,
        max_model_calls=100,
        max_command_count=1,
        max_output_size=1_000_000,
        max_worker_runtime_seconds=3600,
    )
    decision = BoundedAutonomy().assess(
        manager.get_run("gate-f-real"),
        budget,
        usage=BudgetUsage(command_count=1),
    )
    assert decision.action is LimitAction.ABORT

    manager.transition("gate-f-real", RunState.RECOVERING, TransitionActor.RECOVERY)
    manager.abort_run("gate-f-real", decision.reason, TransitionActor.RECOVERY)
    assert manager.get_run("gate-f-real").state is RunState.ABORTED
    assert manager.events("gate-f-real")[-1].event_type == "RUN_ABORTED"


def test_no_progress_becomes_durable_waiting_human():
    from vajra.recovery.progress import ProgressObservation

    manager = RunManager()
    manager.create_run(make_run())
    manager.transition("gate-f-real", RunState.QUEUED, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.ORIENTING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.PLANNING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.EXECUTING, TransitionActor.SYSTEM)

    observation = ProgressObservation(
        run_id="gate-f-real",
        step_id="step-gate-f",
        attempt_id="attempt-gate-f",
        state_digest="same-state",
        git_revision="same-revision",
        patch_digest="same-patch",
        test_signature="same-tests",
        error_signature="same-error",
    )
    limits = BoundedAutonomy()
    for _ in range(3):
        decision = limits.assess(
            manager.get_run("gate-f-real"),
            Budget(
                budget_id="budget-gate-f",
                max_runtime_seconds=3600,
                max_steps=100,
                max_attempts=100,
                max_model_calls=100,
                max_command_count=100,
                max_output_size=1_000_000,
                max_worker_runtime_seconds=3600,
            ),
            progress=observation,
        )
    assert decision.action is LimitAction.WAIT_HUMAN
    manager.transition("gate-f-real", RunState.WAITING_HUMAN, TransitionActor.CONTROLLER)
    assert manager.get_run("gate-f-real").state is RunState.WAITING_HUMAN


def test_stale_worker_result_cannot_change_canonical_state():
    state_store = InMemoryStateStore()
    event_store = InMemoryEventStore()
    manager = RunManager(state_store=state_store, event_store=event_store)
    manager.create_run(make_run())
    manager.add_step("gate-f-real", "step-gate-f", "worker step")
    manager.transition("gate-f-real", RunState.QUEUED, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.ORIENTING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.PLANNING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.EXECUTING, TransitionActor.SYSTEM)

    now = datetime.now(timezone.utc)
    attempt = manager.start_attempt(
        "gate-f-real",
        "step-gate-f",
        "attempt-gate-f",
        "worker-a",
        "lease-a",
        lease_ttl_seconds=60,
        now=now,
    )
    lease = manager.get_lease(attempt.attempt_id)
    assert lease is not None

    manager.lease_manager.acquire(
        "attempt-gate-f",
        "worker-b",
        "lease-b",
        60,
        now=now,
    )
    acceptor = WorkerResultAcceptor(manager.lease_manager, state_store, event_store)
    identity = WorkerExecutionIdentity(
        run_id="gate-f-real",
        step_id="step-gate-f",
        attempt_id="attempt-gate-f",
        worker_id="worker-a",
        lease_id="lease-a",
        fencing_token=lease.fencing_token,
    )

    with pytest.raises(PermissionError, match="does not own"):
        acceptor.accept(identity, WorkerResult(status="SUCCEEDED"), now=now)

    assert manager.get_run("gate-f-real").steps[0].attempts[0].state.value == "RUNNING"
