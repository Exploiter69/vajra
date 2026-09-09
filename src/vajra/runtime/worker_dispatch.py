from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


class WorkerTransport(Protocol):
    """Transport boundary between VAJRA control plane and disposable workers."""

    def dispatch(self, job: WorkerJob) -> None:
        """Deliver a bounded job to a disposable worker."""


@dataclass(frozen=True)
class DispatchReceipt:
    """Evidence that the control plane handed a job to its worker transport."""

    run_id: str
    step_id: str
    attempt_id: str


class WorkerDispatcher:
    """Oracle-side worker dispatch authority.

    The dispatcher transports WorkerJob objects only. It does not execute
    worker code, mutate canonical Run state, or accept worker results.
    """

    def __init__(self, transport: WorkerTransport) -> None:
        self._transport = transport

    def dispatch(self, job: WorkerJob) -> DispatchReceipt:
        self._transport.dispatch(job)

        return DispatchReceipt(
            run_id=job.run_id,
            step_id=job.step_id,
            attempt_id=job.attempt_id,
        )


class InMemoryWorkerTransport:
    """Deterministic transport used by tests and local lifecycle simulation."""

    def __init__(self) -> None:
        self.jobs: list[WorkerJob] = []
        self.results: list[WorkerResult] = []

    def dispatch(self, job: WorkerJob) -> None:
        self.jobs.append(job)
