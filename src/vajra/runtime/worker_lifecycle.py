from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from vajra.domain import AttemptState, EngineeringRun, RunState
from vajra.runtime.run_manager import RunManager


@dataclass(frozen=True)
class WorkerDisappearance:
    run_id: str
    step_id: str
    attempt_id: str
    worker_id: str
    reason: str = "worker disappeared"


class WorkerDisappearanceDetector:
    """
    Oracle-side detection boundary for disposable worker loss.

    Worker liveness is inferred from the VAJRA-owned lease authority. The
    detector mutates canonical Run state only through RunManager.
    """

    def __init__(self, manager: RunManager) -> None:
        self._manager = manager

    def detect(
        self,
        disappearance: WorkerDisappearance,
        *,
        now: datetime | None = None,
    ) -> EngineeringRun:
        current_time = now or datetime.now(timezone.utc)

        run = self._manager.get_run(disappearance.run_id)

        step = next(
            (
                step
                for step in run.steps
                if step.step_id == disappearance.step_id
            ),
            None,
        )
        if step is None:
            raise KeyError(f"Step not found: {disappearance.step_id}")

        attempt = next(
            (
                attempt
                for attempt in step.attempts
                if attempt.attempt_id == disappearance.attempt_id
            ),
            None,
        )
        if attempt is None:
            raise KeyError(f"Attempt not found: {disappearance.attempt_id}")

        if attempt.state is not AttemptState.RUNNING:
            raise ValueError(
                f"Attempt is not running: {attempt.attempt_id}"
            )

        if attempt.worker_id != disappearance.worker_id:
            raise PermissionError("Worker does not match attempt owner")

        lease = self._manager.get_lease(disappearance.attempt_id)

        lease_lost = (
            lease is None
            or current_time >= lease.lease_expiry
        )

        if not lease_lost:
            raise ValueError(
                f"Worker lease is still active: {disappearance.attempt_id}"
            )

        self._manager.fail_attempt(
            disappearance.run_id,
            disappearance.step_id,
            disappearance.attempt_id,
            disappearance.reason,
        )

        return self._manager.recover_run(disappearance.run_id)


__all__ = [
    "WorkerDisappearance",
    "WorkerDisappearanceDetector",
]


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
