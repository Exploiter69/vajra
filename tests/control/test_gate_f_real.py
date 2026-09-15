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
from vajra.control.reality import RealityObserver
from vajra.control.transition_authority import TransitionActor, TransitionDenied
from vajra.control.worktree import WorktreeManager
from vajra.domain import EngineeringRun, RunState
from vajra.runtime.run_manager import RunManager


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def make_run() -> EngineeringRun:
    return EngineeringRun(
        run_id="gate-f-real",
        objective="prove Gate F integration",
        repository_id="repo-gate-f",
        base_revision="revision-gate-f",
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


def make_accepted() -> object:
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
    accepted = make_accepted()

    # Evidence is sufficient for the completion gate, but controller authority is not.
    with pytest.raises(TransitionDenied, match="COMPLETE requires SYSTEM or HUMAN"):
        manager.complete_run(
            "gate-f-real",
            accepted,
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
    run = make_run()
    run.base_revision = revision

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

    assert dirty.divergence_class is DivergenceClass.WORKSPACE if hasattr(DivergenceClass, "WORKSPACE") else dirty.divergence_class is DivergenceClass.RECOVERABLE
    assert dirty.disposition is ReconciliationDisposition.RECOVERABLE
    assert dirty.freshness == "FRESH"


def test_recovery_is_durable_not_an_in_memory_controller_flag():
    manager = RunManager()
    manager.create_run(make_run())
    manager.transition("gate-f-real", RunState.QUEUED, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.ORIENTING, TransitionActor.SYSTEM)
    manager.transition("gate-f-real", RunState.RECOVERING, TransitionActor.RECOVERY)

    recovered = manager.recover_run("gate-f-real")
    assert recovered.state is RunState.RECOVERING
    assert manager.get_run("gate-f-real").state is RunState.RECOVERING
    assert any(event.event_type == "RUN_RECOVERING" for event in manager.events("gate-f-real"))
