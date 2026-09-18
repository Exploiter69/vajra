from __future__ import annotations

from dataclasses import dataclass

import pytest

from vajra.runtime.worker_lifecycle import ManagedWorkerProvider, WorkerLifecycleError
from vajra.runtime.worker_provider import WorkerEndpoint


@dataclass
class FakeProvider:
    endpoint: WorkerEndpoint | None = None
    failures_before_ready: int = 0

    def ensure_ready(self) -> WorkerEndpoint:
        if self.failures_before_ready:
            self.failures_before_ready -= 1
            raise RuntimeError("not ready")
        if self.endpoint is None:
            raise RuntimeError("missing endpoint")
        return self.endpoint


def endpoint() -> WorkerEndpoint:
    return WorkerEndpoint(
        infer_url="http://worker/infer",
        health_url="http://worker/health",
        worker_id="worker-1",
        protocol="vajra-worker-v1",
        model="qwen2.5-coder:32b",
        capabilities=("completion",),
    )


def test_managed_provider_starts_and_waits_for_readiness() -> None:
    calls: list[str] = []
    provider = FakeProvider(endpoint=endpoint(), failures_before_ready=2)
    manager = ManagedWorkerProvider(
        provider,
        start=lambda: calls.append("start"),
        readiness_timeout_seconds=1,
        poll_interval_seconds=0.001,
    )
    ready = manager.ensure_ready()
    assert ready == endpoint()
    assert calls == ["start"]
    assert manager.lease is not None


def test_managed_provider_releases_once() -> None:
    calls: list[str] = []
    provider = FakeProvider(endpoint=endpoint())
    manager = ManagedWorkerProvider(
        provider,
        start=lambda: calls.append("start"),
        stop=lambda value: calls.append(f"stop:{value.worker_id}"),
    )
    manager.ensure_ready()
    manager.release()
    manager.release()
    assert calls == ["start", "stop:worker-1"]


def test_managed_provider_reports_start_failure() -> None:
    manager = ManagedWorkerProvider(
        FakeProvider(),
        start=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(WorkerLifecycleError, match="worker start failed"):
        manager.ensure_ready()


def test_managed_provider_reports_readiness_timeout() -> None:
    manager = ManagedWorkerProvider(
        FakeProvider(),
        start=lambda: None,
        readiness_timeout_seconds=0.01,
        poll_interval_seconds=0.001,
    )
    with pytest.raises(WorkerLifecycleError, match="did not become ready"):
        manager.ensure_ready()
