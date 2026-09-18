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


# Managed lifecycle coverage
from dataclasses import dataclass

from vajra.runtime.worker_lifecycle import ManagedWorkerProvider, WorkerLifecycleError, WorkerLease
from vajra.runtime.worker_provider import WorkerEndpoint


def test_managed_provider_starts_waits_and_leases_ready_worker():
    endpoint = WorkerEndpoint(
        infer_url="http://worker/infer", health_url="http://worker/health",
        worker_id="worker-managed", protocol="vajra-worker-v1",
        model="test-model", capabilities=("completion",),
    )
    calls = {"start": 0, "ready": 0}

    class Provider:
        def ensure_ready(self):
            calls["ready"] += 1
            if calls["ready"] < 2:
                raise RuntimeError("not ready")
            return endpoint

    managed = ManagedWorkerProvider(
        Provider(), start=lambda: calls.__setitem__("start", calls["start"] + 1),
        readiness_timeout_seconds=0.2, poll_interval_seconds=0.001,
    )
    assert managed.ensure_ready() == endpoint
    assert calls["start"] == 1
    assert managed.lease is not None
    assert managed.lease.endpoint == endpoint


def test_managed_provider_release_clears_lease_and_calls_stop():
    endpoint = WorkerEndpoint(
        infer_url="http://worker/infer", health_url="http://worker/health",
        worker_id="worker-managed", protocol="vajra-worker-v1",
        model="test-model", capabilities=("completion",),
    )
    stopped = []
    provider = type("P", (), {"ensure_ready": lambda self: endpoint})()
    managed = ManagedWorkerProvider(
        provider, start=lambda: None, stop=lambda ep: stopped.append(ep.worker_id),
        readiness_timeout_seconds=0.1, poll_interval_seconds=0.001,
    )
    managed.ensure_ready()
    managed.release()
    assert managed.lease is None
    assert stopped == ["worker-managed"]


def test_managed_provider_wraps_start_failure():
    provider = type("P", (), {"ensure_ready": lambda self: None})()
    managed = ManagedWorkerProvider(
        provider, start=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        readiness_timeout_seconds=0.1, poll_interval_seconds=0.001,
    )
    with pytest.raises(WorkerLifecycleError, match="worker start failed"):
        managed.ensure_ready()
