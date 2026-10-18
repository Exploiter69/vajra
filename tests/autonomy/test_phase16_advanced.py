from __future__ import annotations

from pathlib import Path

import pytest

from vajra.autonomy import (
    AdvancedAutonomyEngine,
    AdvancedAutonomyError,
    AdvancedRunStore,
    AdvancedStage,
    CrossRepositoryOperation,
    LongHorizonLimits,
    MultiStepObjective,
    RepositoryAuthority,
    SpecializedWorker,
    SpecializedWorkerRegistry,
    StageCheckpoint,
    StageState,
    WorkerSpecialization,
)


def repo(repo_id: str, ops=frozenset({"inspect", "modify", "test", "integrate", "security", "document"})):
    return RepositoryAuthority(repo_id, f"ws-{repo_id}", "base", ops)


def test_multistep_plan_validates_dependencies_and_next_stage(tmp_path: Path):
    objective = MultiStepObjective(
        "o1", "ship oauth",
        (
            AdvancedStage("inspect", "Inspect", "inspect architecture", worker_roles=(WorkerSpecialization.RESEARCH,)),
            AdvancedStage("design", "Design", "design", depends_on=("inspect",)),
            AdvancedStage("implement", "Implement", "implement", depends_on=("design",), required_operations=frozenset({"modify"})),
            AdvancedStage("test", "Tests", "tests", depends_on=("implement",), required_operations=frozenset({"test"})),
            AdvancedStage("integration", "Integration", "integration", depends_on=("test",), required_operations=frozenset({"integrate"})),
            AdvancedStage("security", "Security", "security", depends_on=("integration",), required_operations=frozenset({"security"})),
            AdvancedStage("docs", "Docs", "documentation", depends_on=("security",), required_operations=frozenset({"document"})),
            AdvancedStage("verify", "Verify", "final verification", depends_on=("docs",)),
        ),
        (repo("main"),),
    )
    engine = AdvancedAutonomyEngine(store=AdvancedRunStore(tmp_path / "advanced.jsonl"))
    assert [s.stage_id for s in engine.next_stages(objective)] == ["inspect"]


def test_stage_cycles_and_unknown_dependencies_are_rejected():
    with pytest.raises(ValueError):
        MultiStepObjective("o", "x", (AdvancedStage("a", "a", "a", depends_on=("b",)),), (repo("r"),))
    with pytest.raises(ValueError):
        MultiStepObjective("o", "x", (AdvancedStage("a", "a", "a", depends_on=("a",)),), (repo("r"),))


def test_specialized_workers_are_singular_and_deterministic():
    registry = SpecializedWorkerRegistry((
        SpecializedWorker("testing-b", WorkerSpecialization.TESTING, frozenset({"pytest"})),
        SpecializedWorker("testing-a", WorkerSpecialization.TESTING, frozenset({"pytest"})),
        SpecializedWorker("coding", WorkerSpecialization.CODING),
    ))
    assert registry.select(WorkerSpecialization.TESTING, frozenset({"pytest"})).worker_id == "testing-a"
    with pytest.raises(AdvancedAutonomyError):
        registry.select(WorkerSpecialization.SECURITY)


def test_cross_repository_authority_is_explicit(tmp_path: Path):
    objective = MultiStepObjective(
        "o", "cross repo",
        (AdvancedStage("s", "s", "s"),),
        (repo("a"), repo("b")),
    )
    engine = AdvancedAutonomyEngine(store=AdvancedRunStore(tmp_path / "authority.jsonl"))
    engine.authorize_operation(objective, CrossRepositoryOperation("op", "intent", ("a", "b"), "coordinated change", frozenset({"modify"})))
    with pytest.raises(AdvancedAutonomyError):
        engine.authorize_operation(objective, CrossRepositoryOperation("bad", "intent", ("a", "c"), "unauthorized", frozenset({"modify"})))


def test_execution_is_verified_and_durablely_resumable(tmp_path: Path):
    store = AdvancedRunStore(tmp_path / "advanced.jsonl")
    engine = AdvancedAutonomyEngine(store=store)
    objective = MultiStepObjective(
        "o", "two stage",
        (
            AdvancedStage("a", "A", "first"),
            AdvancedStage("b", "B", "second", depends_on=("a",)),
        ),
        (repo("r"),),
    )
    calls = []
    def execute(stage, worker):
        calls.append(("execute", stage.stage_id))
        return stage.stage_id
    def verify(stage, result):
        calls.append(("verify", stage.stage_id, result))
        return True, (f"evidence-{stage.stage_id}",)
    checkpoints = engine.execute(objective, execute_stage=execute, verify_stage=verify)
    assert checkpoints[-1].state is StageState.COMPLETE
    assert calls == [("execute", "a"), ("verify", "a", "a"), ("execute", "b"), ("verify", "b", "b")]

    resumed = AdvancedAutonomyEngine(store=AdvancedRunStore(tmp_path / "advanced.jsonl"))
    assert resumed.next_stages(objective) == ()


def test_failed_verification_never_marks_stage_complete(tmp_path: Path):
    engine = AdvancedAutonomyEngine(store=AdvancedRunStore(tmp_path / "advanced.jsonl"), limits=LongHorizonLimits(max_replans=1))
    objective = MultiStepObjective("o", "fail", (AdvancedStage("a", "A", "a"),), (repo("r"),))
    with pytest.raises(AdvancedAutonomyError):
        engine.execute(objective, execute_stage=lambda s, w: None, verify_stage=lambda s, r: (False, ()))
    states = engine.store.latest("o")
    assert states[-1].state is StageState.FAILED
    assert all(c.state is not StageState.COMPLETE for c in states)


def test_stage_bound_is_hard(tmp_path: Path):
    objective = MultiStepObjective("o", "many", tuple(AdvancedStage(str(i), str(i), str(i)) for i in range(2)), (repo("r"),))
    engine = AdvancedAutonomyEngine(store=AdvancedRunStore(tmp_path / "advanced.jsonl"), limits=LongHorizonLimits(max_stages=1))
    with pytest.raises(AdvancedAutonomyError, match="stage count"):
        engine.next_stages(objective)


def test_cross_repository_operation_must_be_authorized_per_repository(tmp_path: Path):
    objective = MultiStepObjective("o2", "cross repo", (AdvancedStage("s", "s", "s"),), (repo("a", frozenset({"inspect", "modify"})), repo("b", frozenset({"inspect"}))))
    engine = AdvancedAutonomyEngine(store=AdvancedRunStore(tmp_path / "authority.jsonl"))
    with pytest.raises(AdvancedAutonomyError, match="unauthorized operations"):
        engine.authorize_operation(objective, CrossRepositoryOperation("op", "intent", ("a", "b"), "bad scope", frozenset({"modify"})))


def test_execution_uses_dependency_order_even_when_declared_out_of_order(tmp_path: Path):
    objective = MultiStepObjective(
        "ordered", "ordered work",
        (
            AdvancedStage("b", "B", "second", depends_on=("a",)),
            AdvancedStage("a", "A", "first"),
        ),
        (repo("r"),),
    )
    engine = AdvancedAutonomyEngine(store=AdvancedRunStore(tmp_path / "ordered.jsonl"))
    seen = []
    engine.execute(
        objective,
        execute_stage=lambda stage, worker: seen.append(stage.stage_id) or stage.stage_id,
        verify_stage=lambda stage, result: (True, (f"e-{stage.stage_id}",)),
    )
    assert seen == ["a", "b"]

@pytest.mark.parametrize("ambiguous_state", (StageState.RUNNING, StageState.VERIFYING))
def test_restart_refuses_to_replay_ambiguous_stage(tmp_path: Path, ambiguous_state: StageState):
    journal = tmp_path / "ambiguous-stage.jsonl"
    store = AdvancedRunStore(journal)
    objective = MultiStepObjective(
        "ambiguous", "recover safely",
        (AdvancedStage("stage-a", "Stage A", "perform an operation"),),
        (repo("r"),),
    )
    store.record(StageCheckpoint(
        objective_id="ambiguous",
        stage_id="stage-a",
        state=ambiguous_state,
        sequence=1,
        recorded_at="2026-10-18T00:00:00+00:00",
    ))

    # Reopen the journal to exercise the actual restart path.
    restarted = AdvancedAutonomyEngine(store=AdvancedRunStore(journal))
    calls = []
    with pytest.raises(AdvancedAutonomyError, match="human reconciliation required"):
        restarted.execute(
            objective,
            execute_stage=lambda stage, worker: calls.append(("execute", stage.stage_id)),
            verify_stage=lambda stage, result: calls.append(("verify", stage.stage_id)) or (True, ("evidence",)),
        )

    assert calls == [], "ambiguous in-flight stages must not be replayed automatically"



def test_attempt_and_execution_budgets_survive_engine_restart(tmp_path: Path):
    journal = tmp_path / "durable-budget.jsonl"
    objective = MultiStepObjective(
        "budgeted", "bounded work",
        (AdvancedStage("a", "A", "first"), AdvancedStage("b", "B", "second", depends_on=("a",))),
        (repo("r"),),
    )
    limits = LongHorizonLimits(max_attempts=1, max_model_calls=10)
    first = AdvancedAutonomyEngine(store=AdvancedRunStore(journal), limits=limits)
    calls = []
    with pytest.raises(AdvancedAutonomyError, match="attempt bound"):
        first.execute(
            objective,
            execute_stage=lambda stage, worker: calls.append(stage.stage_id) or stage.stage_id,
            verify_stage=lambda stage, result: (True, (f"e-{stage.stage_id}",)),
        )
    assert calls == ["a"]
    persisted = AdvancedRunStore(journal).budget("budgeted")
    assert persisted["attempts"] == 1
    assert persisted["model_calls"] == 1
    with pytest.raises(AdvancedAutonomyError, match="limits differ"):
        AdvancedAutonomyEngine(
            store=AdvancedRunStore(journal),
            limits=LongHorizonLimits(max_attempts=2, max_model_calls=10),
        ).execute(
            objective,
            execute_stage=lambda stage, worker: pytest.fail("changed limits must be rejected"),
            verify_stage=lambda stage, result: (True, ("evidence",)),
        )


def test_model_call_budget_is_reserved_before_execution_callback(tmp_path: Path):
    journal = tmp_path / "model-budget.jsonl"
    objective = MultiStepObjective("model-budget", "bounded model work", (AdvancedStage("a", "A", "first"),), (repo("r"),))
    engine = AdvancedAutonomyEngine(
        store=AdvancedRunStore(journal),
        limits=LongHorizonLimits(max_model_calls=1),
    )
    # Exhaust the durable execution-call budget before any stage callback runs.
    store = engine.store
    store.reserve_stage_execution("model-budget", engine.limits)
    calls = []
    with pytest.raises(AdvancedAutonomyError, match="model-call bound"):
        engine.execute(
            objective,
            execute_stage=lambda stage, worker: calls.append(stage.stage_id),
            verify_stage=lambda stage, result: (True, ("evidence",)),
        )
    assert calls == []
