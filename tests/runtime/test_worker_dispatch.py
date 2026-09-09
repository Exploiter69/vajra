from __future__ import annotations

from vajra.runtime.worker_dispatch import (
    InMemoryWorkerTransport,
    WorkerDispatcher,
)
from vajra.runtime.worker_protocol import WorkerJob


def make_job() -> WorkerJob:
    return WorkerJob(
        run_id="run-001",
        step_id="step-001",
        attempt_id="attempt-001",
        repository_revision="abc123",
        workspace_contract={"workspace_id": "ws-001"},
        context_bundle={"objective": "test"},
        allowed_capabilities=("execution.test",),
        budget={"max_commands": 1},
        deadline="2026-09-09T00:00:00+00:00",
        expected_output_schema={"type": "object"},
    )


def test_dispatch_delivers_job_to_worker_transport() -> None:
    transport = InMemoryWorkerTransport()
    dispatcher = WorkerDispatcher(transport)
    job = make_job()

    receipt = dispatcher.dispatch(job)

    assert transport.jobs == [job]
    assert receipt.run_id == "run-001"
    assert receipt.step_id == "step-001"
    assert receipt.attempt_id == "attempt-001"


def test_dispatch_does_not_mutate_worker_job() -> None:
    transport = InMemoryWorkerTransport()
    dispatcher = WorkerDispatcher(transport)
    job = make_job()

    dispatcher.dispatch(job)

    assert job.run_id == "run-001"
    assert job.step_id == "step-001"
    assert job.attempt_id == "attempt-001"


def test_dispatcher_does_not_accept_or_authorize_worker_results() -> None:
    transport = InMemoryWorkerTransport()
    dispatcher = WorkerDispatcher(transport)

    assert not hasattr(dispatcher, "accept")
    assert not hasattr(dispatcher, "execute")
