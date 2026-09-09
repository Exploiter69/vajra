from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from vajra.domain import AttemptState, EngineeringRun, RunState
from vajra.recovery.classifier import FailureClassifier
from vajra.recovery.contracts import FailureObservation, RecoveryAction
from vajra.recovery.policy import RecoveryPolicy
from vajra.recovery.worker import (
    ChangeWorkerRecoveryHandler,
    WorkerChangeRequest,
)
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.oracle_retry import OracleRetryCoordinator, OracleRetryRequest
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore
from vajra.runtime.worker_acceptance import (
    WorkerExecutionIdentity,
    WorkerResultAcceptor,
)
from vajra.runtime.worker_dispatch import (
    InMemoryWorkerTransport,
    WorkerDispatcher,
)
from vajra.runtime.worker_lifecycle import (
    WorkerDisappearance,
    WorkerDisappearanceDetector,
)
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def make_manager() -> RunManager:
    manager = RunManager(
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
    )

    run = EngineeringRun(
        run_id="gate-c-run",
        created_at=NOW,
        objective="Gate C worker lifecycle",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("worker lifecycle survives loss",),
        policy_id="default",
        policy_version="1",
        budget_id="budget-1",
        state=RunState.CREATED,
    )

    manager.create_run(run)
    manager.transition("gate-c-run", RunState.QUEUED)
    manager.transition("gate-c-run", RunState.ORIENTING)
    manager.transition("gate-c-run", RunState.PLANNING)
    manager.transition("gate-c-run", RunState.EXECUTING)
    manager.add_step("gate-c-run", "step-1", "implementation")

    manager.start_attempt(
        "gate-c-run",
        "step-1",
        "attempt-1",
        "worker-1",
        "lease-1",
        lease_ttl_seconds=60,
        now=NOW,
    )

    return manager


def make_job(
    *,
    attempt_id: str,
    worker_id: str,
    correlation_id: str,
) -> WorkerJob:
    return WorkerJob(
        run_id="gate-c-run",
        step_id="step-1",
        attempt_id=attempt_id,
        repository_revision="abc123",
        workspace_contract={"workspace_id": "ws-gate-c"},
        context_bundle={"objective": "Gate C worker lifecycle"},
        allowed_capabilities=("execution.test",),
        budget={"max_commands": 2},
        deadline="2026-09-08T12:10:00+00:00",
        expected_output_schema={"type": "object"},
        correlation_id=correlation_id,
    )


def test_gate_c_oracle_worker_lifecycle():
    manager = make_manager()

    # Oracle dispatches the first attempt.
    transport = InMemoryWorkerTransport()
    dispatcher = WorkerDispatcher(transport)

    first_job = make_job(
        attempt_id="attempt-1",
        worker_id="worker-1",
        correlation_id="corr-attempt-1",
    )
    receipt = dispatcher.dispatch(first_job)

    assert receipt.attempt_id == "attempt-1"
    assert transport.jobs == [first_job]

    first_lease = manager.get_lease("attempt-1")
    assert first_lease is not None

    # Worker returns a structured result. Oracle validates and accepts it.
    acceptor = WorkerResultAcceptor(
        manager.lease_manager,
        manager._state_store,
        manager._event_store,
    )

    identity = WorkerExecutionIdentity(
        run_id="gate-c-run",
        step_id="step-1",
        attempt_id="attempt-1",
        worker_id="worker-1",
        lease_id="lease-1",
        fencing_token=first_lease.fencing_token,
        correlation_id="corr-attempt-1",
    )

    accepted = acceptor.accept(
        identity,
        WorkerResult(
            status="SUCCEEDED",
            correlation_id="corr-attempt-1",
            structured_result={"status": "ok"},
        ),
        now=NOW,
    )

    assert accepted.steps[0].attempts[0].state is AttemptState.SUCCEEDED

    accepted_events = manager.events("gate-c-run")
    result_event = accepted_events[-1]
    assert result_event.event_type == "WORKER_RESULT_ACCEPTED"
    assert result_event.correlation_id == "corr-attempt-1"

    # A second attempt is used to exercise the actual worker-loss/recovery path.
    manager.start_attempt(
        "gate-c-run",
        "step-1",
        "attempt-loss",
        "worker-old",
        "lease-old",
        lease_ttl_seconds=1,
        now=NOW,
    )

    loss_time = NOW + timedelta(seconds=2)

    WorkerDisappearanceDetector(manager).detect(
        WorkerDisappearance(
            run_id="gate-c-run",
            step_id="step-1",
            attempt_id="attempt-loss",
            worker_id="worker-old",
        ),
        now=loss_time,
    )

    run = manager.get_run("gate-c-run")
    assert run.state is RunState.RECOVERING

    failed_attempt = next(
        attempt
        for attempt in run.steps[0].attempts
        if attempt.attempt_id == "attempt-loss"
    )
    assert failed_attempt.state is AttemptState.FAILED

    # Failure classification and policy remain deterministic.
    observation = FailureObservation(
        failure_id="failure-worker-loss",
        run_id="gate-c-run",
        step_id="step-1",
        attempt_id="attempt-loss",
        source="worker",
        message="worker disappeared",
    )

    failure = FailureClassifier().classify(observation)
    decision = RecoveryPolicy().decide(failure)

    assert failure.category.value == "WORKER_LOSS"
    assert decision.action is RecoveryAction.CHANGE_WORKER

    # Oracle selects a replacement worker.
    selector_calls = []

    def selector(failure, decision):
        selector_calls.append((failure.failure_id, decision.action))
        return WorkerChangeRequest(
            worker_id="worker-new",
            reason="replace disappeared worker",
        )

    change_worker = ChangeWorkerRecoveryHandler(manager, selector)
    change_request = change_worker(failure, decision)

    assert change_request.worker_id == "worker-new"
    assert selector_calls == [
        ("failure-worker-loss", RecoveryAction.CHANGE_WORKER)
    ]

    # Oracle creates a new Attempt with a new lease/fencing identity.
    retry_decision = RecoveryPolicy().decide(
        failure.__class__(
            failure_id=failure.failure_id,
            run_id=failure.run_id,
            step_id=failure.step_id,
            attempt_id=failure.attempt_id,
            category=failure.category,
            message=failure.message,
            details=failure.details,
        )
    )
    retry_decision = retry_decision.__class__(
        failure_id=retry_decision.failure_id,
        run_id=retry_decision.run_id,
        step_id=retry_decision.step_id,
        attempt_id=retry_decision.attempt_id,
        category=retry_decision.category,
        action=RecoveryAction.RETRY,
        reason="Oracle retry with selected replacement worker",
    )

    replacement = OracleRetryCoordinator(manager).retry(
        failure,
        retry_decision,
        request=OracleRetryRequest(
            worker_id=change_request.worker_id,
            lease_id="lease-new",
            lease_ttl_seconds=60,
        ),
    )

    assert replacement.attempt_id != "attempt-loss"
    assert replacement.worker_id == "worker-new"
    assert replacement.lease_id == "lease-new"
    assert replacement.state is AttemptState.RUNNING

    old_lease = manager.get_lease("attempt-loss")
    new_lease = manager.get_lease(replacement.attempt_id)

    assert old_lease is not None
    assert old_lease.worker_id == "worker-old"
    assert old_lease.lease_id == "lease-old"
    assert old_lease.lease_expiry <= loss_time
    assert new_lease is not None
    assert new_lease.worker_id == "worker-new"
    assert new_lease.lease_id == "lease-new"
    assert new_lease.fencing_token != old_lease.fencing_token

    # Oracle dispatches the replacement attempt.
    second_job = make_job(
        attempt_id=replacement.attempt_id,
        worker_id="worker-new",
        correlation_id="corr-replacement",
    )
    dispatcher.dispatch(second_job)

    assert transport.jobs[-1] == second_job
    assert second_job.attempt_id == replacement.attempt_id

    # The disappeared worker is permanently fenced and cannot commit later.
    old_identity = WorkerExecutionIdentity(
        run_id="gate-c-run",
        step_id="step-1",
        attempt_id="attempt-loss",
        worker_id="worker-old",
        lease_id="lease-old",
        fencing_token=1,
    )

    with pytest.raises(PermissionError):
        acceptor.accept(
            old_identity,
            WorkerResult(status="SUCCEEDED"),
            now=loss_time,
        )

    final = manager.get_run("gate-c-run")

    old_attempt = next(
        attempt
        for attempt in final.steps[0].attempts
        if attempt.attempt_id == "attempt-loss"
    )

    new_attempt = next(
        attempt
        for attempt in final.steps[0].attempts
        if attempt.attempt_id == replacement.attempt_id
    )

    assert old_attempt.state is AttemptState.FAILED
    assert new_attempt.state is AttemptState.RUNNING
    assert final.state is RunState.RECOVERING
