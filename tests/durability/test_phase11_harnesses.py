from __future__ import annotations

from pathlib import Path

from vajra.durability import ChaosTarget, SoakConfig, SoakCounters, SoakRunner
from vajra.durability.kill_harness import KillHarness


def test_kill_harness_recovers_after_real_sigkill_for_every_phase11_target(
    tmp_path: Path,
):
    results = KillHarness(tmp_path).run_all()

    assert {result.target for result in results} == set(ChaosTarget)
    assert all(result.exit_code == -9 for result in results)
    assert all(result.durable_before_kill for result in results)
    assert all(result.recovered_after_restart for result in results)


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
