from __future__ import annotations

import subprocess
from pathlib import Path

from vajra.control.contracts import WorktreeContract
from vajra.control.reality import RealityObserver, filesystem_digest
from vajra.durability import (
    ChaosTarget,
    KillHarness,
    SoakConfig,
    SoakCounters,
    SoakRunner,
    recovery_action_for,
)
from vajra.domain import EngineeringRun
from vajra.runtime.local_durable_runtime import LocalDurableRuntime


def test_kill_harness_recovers_after_real_sigkill_for_every_phase11_target(
    tmp_path: Path,
):
    results = KillHarness(tmp_path).run_all()

    assert {result.target for result in results} == set(ChaosTarget)
    assert all(result.exit_code == -9 for result in results)
    assert all(result.durable_before_kill for result in results)
    assert all(result.recovered_after_restart for result in results)
    assert all(result.recovery_action == recovery_action_for(result.target) for result in results)


def test_each_failure_domain_has_explicit_recovery_semantics():
    expected = {
        ChaosTarget.CONTROLLER: "restart_component_and_reconcile",
        ChaosTarget.WORKER: "restart_component_and_reconcile",
        ChaosTarget.MODEL: "retry_reasoning_with_fresh_context",
        ChaosTarget.PROCESS: "restart_process_and_recover",
        ChaosTarget.NETWORK: "reconnect_and_reconcile_external_state",
        ChaosTarget.SANDBOX: "discard_sandbox_and_reconcile_workspace",
        ChaosTarget.MACHINE_SIMULATION: "restore_from_durable_state_and_reconcile",
    }

    assert {target: recovery_action_for(target) for target in ChaosTarget} == expected


def test_soak_runner_uses_real_duration_contract_without_sleeping_in_unit_test(
    tmp_path: Path,
):
    clock = [0.0]
    counter = [0]

    def monotonic() -> float:
        return clock[0]

    def sleep(seconds: float) -> None:
        clock[0] += seconds

    def workload() -> None:
        counter[0] += 1

    def counters() -> SoakCounters:
        return SoakCounters(event_count=counter[0], context_items=1)

    metrics = SoakRunner(
        SoakConfig(10.0, 2.0, tmp_path),
        counter_provider=counters,
        workload=workload,
        monotonic=monotonic,
        sleep=sleep,
    ).run()

    assert metrics.last.elapsed_seconds == 10.0
    assert metrics.last.event_count > metrics.first.event_count
    assert metrics.last.context_items == 1
    assert metrics.samples


def test_soak_runner_rejects_negative_runtime_counters(tmp_path: Path):
    def counters() -> SoakCounters:
        return SoakCounters(worker_leaks=-1)

    runner = SoakRunner(
        SoakConfig(1.0, 1.0, tmp_path),
        counter_provider=counters,
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
    )

    try:
        runner.run()
    except ValueError as exc:
        assert "negative" in str(exc)
    else:
        raise AssertionError("negative soak counters must be rejected")


def _run(*args: str, cwd: Path) -> str:
    return subprocess.check_output(("git", *args), cwd=cwd, text=True).strip()


def test_reality_observer_detects_actual_git_and_filesystem_divergence(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "tracked.txt").write_text("A\n", encoding="utf-8")
    subprocess.run(("git", "init", "-q"), cwd=workspace, check=True)
    subprocess.run(("git", "add", "tracked.txt"), cwd=workspace, check=True)
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=VAJRA",
            "-c",
            "user.email=vajra@example.invalid",
            "commit",
            "-qm",
            "base",
        ),
        cwd=workspace,
        check=True,
    )
    revision = _run("rev-parse", "HEAD", cwd=workspace)
    status = _run("status", "--porcelain", cwd=workspace)
    base_digest = filesystem_digest(workspace)

    run = EngineeringRun(
        run_id="phase11-reality",
        objective="detect reality divergence",
        repository_id="repo",
        base_revision=revision,
        acceptance_criteria=("tracked.txt remains present",),
        policy_id="policy",
        policy_version="1",
        budget_id="budget",
        created_by="test",
    )
    contract = WorktreeContract(
        "workspace-1",
        "phase11-reality",
        "repo",
        revision,
        str(workspace),
        True,
        status_digest=__import__("hashlib").sha256(status.encode()).hexdigest(),
    )

    clean = RealityObserver().observe(
        run=run,
        worktree=contract,
        git_revision=revision,
        git_status=status,
        active_lease_state="VALID",
        verification_state="PASS",
        budget_state="AVAILABLE",
    )
    assert clean.divergence_class.value == "NONE"
    assert clean.filesystem_digest == base_digest

    (workspace / "tracked.txt").write_text("B\n", encoding="utf-8")
    divergent_status = _run("status", "--porcelain", cwd=workspace)
    divergent = RealityObserver().observe(
        run=run,
        worktree=contract,
        git_revision=revision,
        git_status=divergent_status,
        active_lease_state="VALID",
        verification_state="PASS",
        budget_state="AVAILABLE",
    )
    assert divergent.filesystem_digest != clean.filesystem_digest
    assert divergent.git_status_digest != clean.git_status_digest
    assert divergent.divergence_class.value == "RECOVERABLE"


def test_local_durable_runtime_retry_storm_terminates_at_runtime_boundary(tmp_path: Path):
    runtime = LocalDurableRuntime(tmp_path / "retry.jsonl", max_retries=2)
    runtime.execute("storm", lambda: (_ for _ in ()).throw(RuntimeError("same failure"))) if False else None

    try:
        runtime.execute("storm", lambda: (_ for _ in ()).throw(RuntimeError("same failure")))
    except RuntimeError:
        pass
    else:
        raise AssertionError("initial failure must be recorded")

    for _ in range(2):
        try:
            runtime.retry("storm", lambda: (_ for _ in ()).throw(RuntimeError("same failure")))
        except RuntimeError:
            pass
        else:
            raise AssertionError("retry failure must remain a failure")

    try:
        runtime.retry("storm", lambda: None)
    except RuntimeError as exc:
        assert "Retry limit exhausted" in str(exc)
    else:
        raise AssertionError("runtime retry boundary must hard-stop the storm")
