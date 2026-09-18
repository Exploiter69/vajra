from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from vajra.runtime.worker_provider import WorkerEndpoint, WorkerProvider


class WorkerLifecycleError(RuntimeError):
    """A worker could not be started, made ready, or released safely."""


@dataclass(frozen=True)
class WorkerLease:
    endpoint: WorkerEndpoint
    lease_id: str

    def __post_init__(self) -> None:
        if not self.lease_id.strip():
            raise ValueError("lease_id must not be empty")


class ManagedWorkerProvider(WorkerProvider):
    """Provider-neutral lifecycle coordinator.

    Provider-specific start/stop mechanics are injected. VAJRA owns lifecycle
    state and readiness; the provider owns only runtime mechanics.
    """

    def __init__(
        self,
        provider: WorkerProvider,
        *,
        start: Callable[[], None],
        stop: Callable[[WorkerEndpoint], None] | None = None,
        readiness_timeout_seconds: float = 120.0,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        if readiness_timeout_seconds <= 0:
            raise ValueError("readiness_timeout_seconds must be positive")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._provider = provider
        self._start = start
        self._stop = stop
        self._timeout = readiness_timeout_seconds
        self._poll = poll_interval_seconds
        self._lease: WorkerLease | None = None

    @property
    def lease(self) -> WorkerLease | None:
        return self._lease

    def ensure_ready(self) -> WorkerEndpoint:
        if self._lease is not None:
            try:
                current = self._provider.ensure_ready()
            except Exception:
                self._lease = None
            else:
                self._lease = WorkerLease(current, self._lease.lease_id)
                return current

        try:
            self._start()
        except Exception as exc:
            raise WorkerLifecycleError(
                f"worker start failed: {type(exc).__name__}: {exc}"
            ) from exc

        deadline = time.monotonic() + self._timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                endpoint = self._provider.ensure_ready()
            except Exception as exc:
                last_error = exc
                time.sleep(min(self._poll, max(0.0, deadline - time.monotonic())))
                continue
            lease_id = f"{endpoint.worker_id}:{time.monotonic_ns()}"
            self._lease = WorkerLease(endpoint, lease_id)
            return endpoint

        detail = f": {last_error}" if last_error else ""
        raise WorkerLifecycleError(
            f"worker did not become ready within {self._timeout:.1f}s{detail}"
        )

    def release(self) -> None:
        lease = self._lease
        self._lease = None
        if lease is None or self._stop is None:
            return
        try:
            self._stop(lease.endpoint)
        except Exception as exc:
            raise WorkerLifecycleError(
                f"worker release failed: {type(exc).__name__}: {exc}"
            ) from exc


__all__ = ["ManagedWorkerProvider", "WorkerLease", "WorkerLifecycleError"]
