from __future__ import annotations

from dataclasses import dataclass

import pytest

from vajra.runtime.kaggle_lifecycle import KaggleKernelLauncher, KaggleLifecycleError


@dataclass
class Completed:
    stdout: str = ""
    stderr: str = ""


def test_kaggle_launcher_pushes_with_timeout(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        return Completed()

    monkeypatch.setattr("vajra.runtime.kaggle_lifecycle.subprocess.run", fake_run)
    launcher = KaggleKernelLauncher(tmp_path / "kernel", timeout_seconds=600)
    launcher.start()

    assert calls == [
        (
            "kaggle",
            "kernels",
            "push",
            "-p",
            str(tmp_path / "kernel"),
            "--timeout",
            "600",
        )
    ]


def test_kaggle_launcher_status_is_explicit(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        return Completed(stdout="running")

    monkeypatch.setattr("vajra.runtime.kaggle_lifecycle.subprocess.run", fake_run)
    launcher = KaggleKernelLauncher(
        tmp_path / "kernel", kernel_ref="owner/worker", timeout_seconds=600
    )

    assert launcher.status() == "running"
    assert calls[-1] == ("kaggle", "kernels", "status", "owner/worker")


def test_kaggle_launcher_does_not_delete_without_explicit_kernel_ref(
    monkeypatch, tmp_path
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **kwargs):
        calls.append(tuple(command))
        return Completed()

    monkeypatch.setattr("vajra.runtime.kaggle_lifecycle.subprocess.run", fake_run)
    KaggleKernelLauncher(tmp_path / "kernel").stop()

    assert calls == []


def test_kaggle_launcher_reports_cli_failure(monkeypatch, tmp_path) -> None:
    def fake_run(command, **kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr("vajra.runtime.kaggle_lifecycle.subprocess.run", fake_run)

    with pytest.raises(KaggleLifecycleError, match="CLI not found"):
        KaggleKernelLauncher(tmp_path / "kernel").start()


def test_kaggle_managed_provider_composes_launcher_and_http_readiness(monkeypatch):
    from vajra.runtime.kaggle_lifecycle import KaggleManagedWorkerProvider
    from vajra.runtime.worker_provider import WorkerEndpoint

    endpoint = WorkerEndpoint(
        infer_url="http://worker/infer",
        health_url="http://worker/health",
        worker_id="kaggle-worker",
        protocol="vajra-worker-v1",
        model="qwen2.5-coder:32b",
        capabilities=("completion",),
    )
    calls = []

    class Provider:
        def ensure_ready(self):
            calls.append("ready")
            return endpoint

    class Launcher:
        def start(self):
            calls.append("start")

        def stop(self):
            calls.append("stop")

    managed = KaggleManagedWorkerProvider(
        Launcher(),
        Provider(),
        readiness_timeout_seconds=0.1,
        poll_interval_seconds=0.001,
    )
    assert managed.endpoint() == endpoint
    assert calls == ["start", "ready"]
    managed.release()
    assert calls == ["start", "ready", "stop"]
