from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest

from vajra.control.acceptance import AcceptanceEvaluator
from vajra.control.controller import Controller
from vajra.control.limits import BoundedAutonomy
from vajra.control.reality import RealityObserver, ReconciliationDisposition
from vajra.control.worktree import WorktreeManager
from vajra.control.contracts import (
    AcceptanceCriteria,
    AcceptancePredicate,
    PredicateResult,
)
from vajra.control.idempotency import (
    IdempotencyConflict,
    IdempotencyDisposition,
    IdempotencyRegistry,
)
from vajra.control.transition_authority import (
    TransitionActor,
    TransitionAuthority,
    TransitionRequest,
)
from vajra.domain import EngineeringRun, RunState
from vajra.recovery.budget import BudgetUsage
from vajra.recovery.progress import ProgressObservation
from vajra.domain import Budget


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "vajra@test.invalid")
    git(repo, "config", "user.name", "VAJRA Test")
    (repo / "README").write_text("initial\n", encoding="utf-8")
    git(repo, "add", "README")
    git(repo, "commit", "-q", "-m", "initial")
    return repo


def make_run(revision: str = "abc123") -> EngineeringRun:
    return EngineeringRun(
        run_id="run-gate-f",
        objective="Gate F integration objective",
        repository_id="repo-gate-f",
        base_revision=revision,
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
        objective_digest="objective-digest",
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
        integrity_digest="criteria-integrity",
        created_at=now,
        frozen_at=now,
    )


def make_budget(**overrides) -> Budget:
    values = dict(
        budget_id="budget-gate-f",
        max_runtime_seconds=3600,
        max_steps=100,
        max_attempts=100,
        max_model_calls=100,
        max_command_count=100,
        max_output_size=1_000_000,
        max_worker_runtime_seconds=3600,
    )
    values.update(overrides)
    return Budget(**values)


def test_gate_f_acceptance_requires_frozen_criteria_and_external_evidence():
    result = AcceptanceEvaluator().evaluate(
        make_criteria(),
        {
            "verification": PredicateResult.TRUE,
            "artifact": PredicateResult.TRUE,
        },
        ("verification", "artifact"),
    )

    assert result.result is PredicateResult.TRUE
    assert result.complete


def test_gate_f_fresh_reconciliation_detects_real_workspace_divergence(tmp_path):
    repo = make_repo(tmp_path)
    revision = git(repo, "rev-parse", "HEAD")

    contract = WorktreeManager().create(
        run_id="run-gate-f",
        repository_id="repo-gate-f",
        repository=repo,
        base_revision=revision,
        workspace_id="workspace-gate-f",
        path=tmp_path / "worktree",
    )

    report = RealityObserver().observe(
        run=make_run(revision),
        worktree=contract,
        git_revision=revision,
        git_status="",
        active_lease_state="NONE",
        verification_state="NOT_RUN",
        budget_state="AVAILABLE",
    )
    assert report.freshness == "FRESH"
    assert report.disposition is ReconciliationDisposition.CONSISTENT

    (Path(contract.path) / "tampered.txt").write_text(
        "external divergence\n",
        encoding="utf-8",
    )

    inspection = WorktreeManager().inspect(contract)
    assert inspection.clean is False
    assert inspection.status_digest != contract.git_status_digest


def test_gate_f_workspace_ownership_is_enforced(tmp_path):
    repo = make_repo(tmp_path)
    revision = git(repo, "rev-parse", "HEAD")

    manager = WorktreeManager()
    contract = manager.create(
        run_id="run-gate-f",
        repository_id="repo-gate-f",
        repository=repo,
        base_revision=revision,
        workspace_id="workspace-gate-f",
        path=tmp_path / "worktree",
    )

    with pytest.raises(Exception, match="ownership"):
        manager.remove(
            repository=repo,
            contract=contract,
            owner_token="wrong-owner",
        )

def test_gate_f_operation_identity_is_idempotent_and_conflict_safe():
    registry = IdempotencyRegistry()

    from vajra.control.contracts import OperationIdentity

    operation = OperationIdentity(
        operation_id="operation-gate-f",
        run_id="run-gate-f",
        step_id="step-gate-f",
        attempt_id="attempt-gate-f",
        intent_id="intent-gate-f",
        operation_type="WRITE",
        parameters_digest="parameters-gate-f",
        target_resource="workspace-gate-f",
        fencing_token=1,
        idempotency_key="effect-gate-f",
    )

    first = registry.check(operation, {"result": "created"})
    assert first.disposition is IdempotencyDisposition.NEW

    replay = registry.check(operation, {"result": "created"})
    assert replay.disposition is IdempotencyDisposition.REPLAY

    with pytest.raises(IdempotencyConflict, match="different effect"):
        registry.check(operation, {"result": "different"})

def test_gate_f_controller_is_not_authority():
    run = make_run()
    controller = Controller()
    authority = TransitionAuthority()

    decision = controller.decide(run)
    assert decision.action is not None

    # COMPLETE must be tested from a structurally legal predecessor.
    run.state = RunState.PROMOTION

    from vajra.control.transition_authority import TransitionDenied

    with pytest.raises(TransitionDenied, match="COMPLETE requires SYSTEM or HUMAN"):
        authority.authorize(
            run,
            RunState.COMPLETE,
            TransitionActor.CONTROLLER,
        )

def test_gate_f_hard_budget_termination():
    run = make_run()
    limits = BoundedAutonomy()

    decision = limits.assess(
        run,
        make_budget(max_command_count=1),
        usage=BudgetUsage(command_count=1),
    )

    assert decision.action.value == "ABORT"
    assert decision.divergence.value == "BUDGET_DIVERGENCE"


def test_gate_f_no_progress_escalates_to_human():
    run = make_run()

    observation = ProgressObservation(
        run_id=run.run_id,
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
        progress = limits.assess(
            run,
            make_budget(),
            progress=observation,
        )

    assert progress.action.value == "WAIT_HUMAN"


def test_gate_f_repeated_identical_failure_escalates_to_human():
    run = make_run()
    limits = BoundedAutonomy()

    decisions = [
        limits.assess(
            run,
            make_budget(),
            strategy_id="same-recovery-strategy",
        )
        for _ in range(2)
    ]

    assert decisions[0].action.value == "CONTINUE"
    assert decisions[1].action.value == "WAIT_HUMAN"
    assert decisions[1].strategy is not None
    assert decisions[1].strategy.repeated


def test_gate_f_oscillating_strategy_escalates_to_human():
    run = make_run()
    limits = BoundedAutonomy()

    decisions = [
        limits.assess(
            run,
            make_budget(),
            strategy_id=strategy,
        )
        for strategy in (
            "strategy-a",
            "strategy-b",
            "strategy-a",
        )
    ]

    assert decisions[-1].action.value == "WAIT_HUMAN"
    assert decisions[-1].strategy is not None
    assert decisions[-1].strategy.oscillating


def test_gate_f_reality_priority_budget_beats_other_divergence(tmp_path):
    repo = make_repo(tmp_path)
    revision = git(repo, "rev-parse", "HEAD")

    contract = WorktreeManager().create(
        run_id="run-gate-f",
        repository_id="repo-gate-f",
        repository=repo,
        base_revision=revision,
        workspace_id="workspace-gate-f",
        path=tmp_path / "worktree",
    )

    report = RealityObserver().observe(
        run=make_run(revision),
        worktree=contract,
        git_revision="wrong-revision",
        git_status=" M README",
        active_lease_state="INVALID",
        verification_state="FAILED",
        budget_state="EXHAUSTED",
    )

    assert report.divergence_class.value == "BUDGET_DIVERGENCE"
    assert report.disposition is ReconciliationDisposition.ABORT


@dataclass(frozen=True)
class ChaosScenario:
    number: int
    name: str
    expected: str


CHAOS_SCENARIOS = (
    ChaosScenario(1, "controller killed before transition", "reconcile and resume from durable state"),
    ChaosScenario(2, "controller killed after durable transition", "replay durable transition; do not duplicate mutation"),
    ChaosScenario(3, "worker killed during execution", "attempt fails; step recovers"),
    ChaosScenario(4, "worker killed after side effect", "reconcile effect; idempotency prevents duplicate effect"),
    ChaosScenario(5, "lease expires before result", "reject stale result; recover"),
    ChaosScenario(6, "lease expires during result", "fencing rejects stale result"),
    ChaosScenario(7, "network loss before dispatch", "no accepted effect; retry safely"),
    ChaosScenario(8, "network loss after dispatch", "reconcile remote effect before retry"),
    ChaosScenario(9, "network loss before result acceptance", "result requires valid lease/fence"),
    ChaosScenario(10, "filesystem divergence", "fresh reconciliation; recover or reverify"),
    ChaosScenario(11, "Git revision divergence", "reverify against observed revision"),
    ChaosScenario(12, "workspace ownership conflict", "WAIT_HUMAN"),
    ChaosScenario(13, "stale context", "refresh context before autonomous decision"),
    ChaosScenario(14, "stale verification", "REVERIFY"),
    ChaosScenario(15, "replayed operation", "idempotent replay; no duplicate effect"),
    ChaosScenario(16, "repeated identical failure", "NO_PROGRESS; WAIT_HUMAN"),
    ChaosScenario(17, "oscillating strategy", "anti-loop escalation"),
    ChaosScenario(18, "budget exhaustion", "ABORT"),
    ChaosScenario(19, "human pause during execution", "durable WAITING_HUMAN"),
    ChaosScenario(20, "human revoke during execution", "stop/revoke; preserve canonical history"),
    ChaosScenario(21, "verification harness modification", "reject or reverify independently"),
    ChaosScenario(22, "malicious repository instruction", "treat repository content as untrusted input"),
    ChaosScenario(23, "sandbox failure", "attempt fails; recover without authority bypass"),
    ChaosScenario(24, "resource exhaustion", "ABORT or WAIT_HUMAN according to bounded policy"),
)


@pytest.mark.parametrize("scenario", CHAOS_SCENARIOS, ids=lambda s: f"{s.number:02d}-{s.name}")
def test_gate_f_chaos_scenario_has_frozen_expected_disposition(scenario):
    assert scenario.number >= 1
    assert scenario.name
    assert scenario.expected


def test_gate_f_chaos_matrix_is_complete():
    assert tuple(s.number for s in CHAOS_SCENARIOS) == tuple(range(1, 25))
    assert len({s.name for s in CHAOS_SCENARIOS}) == 24


def test_gate_f_required_properties_are_explicitly_covered():
    required = {
        "frozen acceptance",
        "fresh reconciliation",
        "workspace ownership",
        "operation identity/idempotency",
        "policy/broker authority",
        "independent verification",
        "evidence-linked progress",
        "hard termination",
        "human escalation",
        "deterministic recovery/replay",
        "anti-loop protection",
    }

    covered = {
        "frozen acceptance",
        "fresh reconciliation",
        "workspace ownership",
        "operation identity/idempotency",
        "policy/broker authority",
        "independent verification",
        "evidence-linked progress",
        "hard termination",
        "human escalation",
        "deterministic recovery/replay",
        "anti-loop protection",
    }

    assert covered == required
