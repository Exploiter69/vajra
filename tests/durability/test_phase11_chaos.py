from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from vajra.control.contracts import stable_digest
from vajra.control.transition_authority import TransitionActor
from vajra.domain import EngineeringRun, RunState
from vajra.durability import (
    ChaosPlan,
    ChaosTarget,
    FaultInjector,
    FaultMode,
    RetryStormGuard,
    SoakMetrics,
    SoakSample,
)
from vajra.runtime.local_durable_runtime import LocalDurableRuntime
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.worker_acceptance import WorkerExecutionIdentity, WorkerResultAcceptor
from vajra.runtime.worker_protocol import WorkerResult


def test_kill_plan_is_reproducible_and_covers_all_roadmap_targets():
    plan = ChaosPlan(seed=2026, ticks=500, injection_probability=1.0)
    first = plan.events()
    second = plan.events()

    assert first == second
    assert {event.target for event in first} == set(ChaosTarget)
    assert {event.mode for event in first} == set(FaultMode)
    assert all(event.event_id for event in first)


@pytest.mark.parametrize("target", tuple(ChaosTarget))
def test_fault_injector_can_schedule_every_kill_target(target):
    plan = ChaosPlan(
        seed=7,
        ticks=1,
        injection_probability=1.0,
        targets=(target,),
        modes=(FaultMode.KILL,),
    )
    event = FaultInjector(plan).event_at(1)
    assert event is not None
    assert event.target is target
    assert event.mode is FaultMode.KILL


def test_retry_storm_hard_stops_identical_failure():
    guard = RetryStormGuard(max_retries=3)
    decisions = [
        guard.observe(
            run_id="run",
            step_id="step",
            failure_signature="same-error",
        )
        for _ in range(4)
    ]

    assert [decision.attempts for decision in decisions] == [1, 2, 3, 4]
    assert decisions[0].terminate is False
    assert decisions[1].terminate is False
    assert decisions[2].terminate is True
    assert decisions[3].terminate is True


def test_retry_storm_keys_are_isolated():
    guard = RetryStormGuard(max_retries=2)
    first = guard.observe(
        run_id="run",
        step_id="step",
        failure_signature="a",
    )
    second = guard.observe(
        run_id="run",
        step_id="step",
        failure_signature="b",
    )

    assert first.attempts == second.attempts == 1
    assert not first.terminate
    assert not second.terminate


def test_soak_metrics_measure_all_roadmap_signals():
    metrics = SoakMetrics(
        (
            SoakSample(
                0,
                100,
                200,
                10,
                5,
                0,
                0,
                2,
                0,
                0,
                0,
            ),
            SoakSample(
                60,
                130,
                240,
                25,
                8,
                0,
                0,
                5,
                2,
                1,
                0,
            ),
        )
    )

    assert metrics.memory_growth_bytes == 30
    assert metrics.disk_growth_bytes == 40
    assert metrics.event_growth == 15
    assert metrics.context_growth == 3
    assert metrics.retry_growth == 3
    assert metrics.last.verification_failures == 2
    assert metrics.last.provider_failures == 1
    assert metrics.violations() == ()


def test_soak_metrics_detect_unbounded_resource_or_lease_growth():
    metrics = SoakMetrics(
        (
            SoakSample(0, 100, 100, 1, 1, 0, 0, 0, 0, 0, 0),
            SoakSample(1, 200, 300, 2, 2, 1, 2, 1, 0, 0, 1),
        )
    )

    assert metrics.violations(
        max_memory_growth_bytes=50,
        max_disk_growth_bytes=100,
        max_worker_leaks=0,
        max_stale_leases=0,
        max_clock_anomalies=0,
    ) == (
        "memory_growth",
        "disk_growth",
        "worker_leaks",
        "stale_leases",
        "clock_anomalies",
    )


def test_soak_samples_reject_negative_observations():
    with pytest.raises(ValueError, match="memory_bytes"):
        SoakSample(0, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0)


def test_long_run_profiles_match_roadmap():
    from vajra.durability.chaos import LONG_RUN_PROFILES

    assert [(profile.name, profile.duration_seconds) for profile in LONG_RUN_PROFILES] == [
        ("1h", 3600),
        ("12h", 43200),
        ("3d", 259200),
        ("7d", 604800),
        ("30d", 2592000),
    ]


def test_durable_execution_survives_real_process_kill(tmp_path: Path):
    journal = tmp_path / "kill.jsonl"
    child = tmp_path / "kill_child.py"
    child.write_text(
        """
from vajra.runtime.local_durable_runtime import LocalDurableRuntime
runtime = LocalDurableRuntime(r'{journal}')
runtime.start_execution('killed-execution')
raise SystemExit(137)
""".format(journal=str(journal)),
        encoding="utf-8",
    )

    repo_root = Path(__file__).parents[2]
    result = subprocess.run(
        [sys.executable, str(child)],
        cwd=repo_root,
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(repo_root / "src"),
        },
        check=False,
    )
    assert result.returncode == 137

    restarted = LocalDurableRuntime(journal)
    recoverable = restarted.recoverable_executions()
    assert len(recoverable) == 1
    assert recoverable[0].execution_id == "killed-execution"

    recovered = restarted.recover(
        "killed-execution",
        lambda: "recovered-after-process-kill",
    )
    assert recovered.state == "COMPLETED"
    assert recovered.result == "recovered-after-process-kill"


def test_completed_execution_remains_idempotent_after_kill_and_restart(
    tmp_path: Path,
):
    journal = tmp_path / "idempotent.jsonl"
    calls = 0
    runtime = LocalDurableRuntime(journal)

    def operation():
        nonlocal calls
        calls += 1
        return "stable"

    runtime.execute("execution", operation)
    restarted = LocalDurableRuntime(journal)
    result = restarted.execute("execution", operation)

    assert result.state == "COMPLETED"
    assert calls == 1


def test_durable_timer_survives_restart():
    from datetime import timedelta

    journal = Path("/tmp") / "vajra-phase11-timer.jsonl"
    journal.unlink(missing_ok=True)
    due = datetime.now(timezone.utc) + timedelta(seconds=1)

    runtime = LocalDurableRuntime(journal)
    runtime.schedule_timer("timer", due)
    restarted = LocalDurableRuntime(journal)

    assert restarted.get_timer("timer") is not None
    assert restarted.due_timers(due - timedelta(seconds=1)) == ()


def test_state_divergence_is_detectable_from_canonical_reality_digest(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    state = {"git": "A", "filesystem": "B", "verification": "PASS"}
    baseline = stable_digest(json.dumps(state, sort_keys=True))

    state["filesystem"] = "C"
    divergent = stable_digest(json.dumps(state, sort_keys=True))

    assert baseline != divergent


def _make_run() -> EngineeringRun:
    return EngineeringRun(
        run_id="lease-chaos",
        objective="phase 11 lease chaos",
        repository_id="repo",
        base_revision="base",
        acceptance_criteria=("criteria",),
        policy_id="policy",
        policy_version="1",
        budget_id="budget",
        created_by="test",
    )


def test_lease_expiry_race_cannot_allow_stale_worker_to_overwrite():
    state = InMemoryStateStore()
    events = InMemoryEventStore()
    manager = RunManager(state_store=state, event_store=events)
    manager.create_run(_make_run())
    manager.add_step("lease-chaos", "step", "lease chaos")
    for target in (
        RunState.QUEUED,
        RunState.ORIENTING,
        RunState.PLANNING,
        RunState.EXECUTING,
    ):
        manager.transition("lease-chaos", target, TransitionActor.SYSTEM)

    now = datetime.now(timezone.utc)
    first = manager.start_attempt(
        "lease-chaos",
        "step",
        "attempt",
        "worker-a",
        "lease-a",
        lease_ttl_seconds=60,
        now=now,
    )
    old = manager.get_lease(first.attempt_id)
    assert old is not None

    manager.lease_manager.acquire(
        "attempt",
        "worker-b",
        "lease-b",
        60,
        now=now,
    )

    acceptor = WorkerResultAcceptor(
        manager.lease_manager,
        state,
        events,
    )
    identity = WorkerExecutionIdentity(
        run_id="lease-chaos",
        step_id="step",
        attempt_id="attempt",
        worker_id="worker-a",
        lease_id="lease-a",
        fencing_token=old.fencing_token,
    )

    with pytest.raises(PermissionError, match="does not own"):
        acceptor.accept(
            identity,
            WorkerResult(status="SUCCEEDED"),
            now=now,
        )


def test_terminal_run_has_no_autonomous_write_path():
    manager = RunManager()
    manager.create_run(_make_run())
    manager.transition("lease-chaos", RunState.QUEUED, TransitionActor.SYSTEM)
    manager.transition("lease-chaos", RunState.ORIENTING, TransitionActor.SYSTEM)
    manager.transition("lease-chaos", RunState.PLANNING, TransitionActor.SYSTEM)
    manager.transition("lease-chaos", RunState.EXECUTING, TransitionActor.SYSTEM)
    manager.transition("lease-chaos", RunState.VERIFYING, TransitionActor.SYSTEM)
    manager.transition("lease-chaos", RunState.CANDIDATE, TransitionActor.SYSTEM)
    manager.transition("lease-chaos", RunState.PROMOTION, TransitionActor.SYSTEM)

    with __import__("pytest").raises(ValueError):
        manager.abort_run("lease-chaos", "chaos abort", TransitionActor.SYSTEM)

    run = manager.get_run("lease-chaos")
    assert run.state is RunState.PROMOTION
