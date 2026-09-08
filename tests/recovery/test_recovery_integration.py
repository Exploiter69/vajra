from datetime import datetime, timezone
from uuid import uuid4

from vajra.domain import (
    Attempt,
    AttemptState,
    Checkpoint,
    EngineeringRun,
    RunState,
    Step,
    StepState,
)
from vajra.recovery.contracts import FailureCategory, FailureObservation, RecoveryAction
from vajra.recovery.policy import RecoveryPolicy
from vajra.recovery.classifier import FailureClassifier
from vajra.recovery.reconciliation import (
    RecoveryDisposition,
    RecoveryObservation,
    RecoveryReconciler,
)
from vajra.recovery.actions import RetryRecoveryHandler, RetryRequest
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore


def make_run() -> EngineeringRun:
    return EngineeringRun(
        run_id="run-integration",
        created_at=datetime.now(timezone.utc),
        objective="integration recovery",
        repository_id="repo-1",
        base_revision="base",
        acceptance_criteria=(),
        policy_id="policy",
        policy_version="v1",
        budget_id="budget",
        state=RunState.CREATED,
    )


def test_worker_loss_flows_through_recovery_to_reconciliation():
    state_store = InMemoryStateStore()
    event_store = InMemoryEventStore()
    manager = RunManager(state_store, event_store)

    run = make_run()
    manager.create_run(run)

    manager.transition(run.run_id, RunState.QUEUED)
    manager.transition(run.run_id, RunState.ORIENTING)
    manager.transition(run.run_id, RunState.PLANNING)
    manager.transition(run.run_id, RunState.EXECUTING)

    manager.add_step(
        run.run_id,
        "step-1",
        "implementation",
    )

    manager.start_attempt(
        run.run_id,
        "step-1",
        "attempt-1",
        "worker-1",
        "lease-1",
    )

    manager.fail_attempt(
        run.run_id,
        "step-1",
        "attempt-1",
        "worker disappeared",
    )

    recovered = manager.recover_run(run.run_id)
    assert recovered.state is RunState.RECOVERING

    failure = FailureClassifier().classify(
        FailureObservation(
            failure_id="failure-1",
            run_id=run.run_id,
            step_id="step-1",
            attempt_id="attempt-1",
            source="worker",
            message="worker disappeared",
        )
    )

    assert failure.category is FailureCategory.WORKER_LOSS

    decision = RecoveryPolicy().decide(failure)
    assert decision.action is RecoveryAction.CHANGE_WORKER

    checkpoint = Checkpoint(
        checkpoint_id="checkpoint-1",
        run_id=run.run_id,
        step_id="step-1",
        event_position=len(manager.events(run.run_id)),
        git_revision="abc123",
        workspace_identity="workspace-1",
        policy_version="v1",
        state_digest="digest",
    )

    assessment = RecoveryReconciler().assess(
        manager.get_run(run.run_id),
        checkpoint,
        RecoveryObservation(
            run_state=RunState.RECOVERING,
            event_position=checkpoint.event_position,
            git_revision="abc123",
            workspace_identity="workspace-1",
            lease=None,
        ),
    )

    assert assessment.disposition is RecoveryDisposition.RESUME
    assert assessment.reasons


def test_failed_attempt_can_be_retried_after_recovery():
    state_store = InMemoryStateStore()
    event_store = InMemoryEventStore()
    manager = RunManager(state_store, event_store)

    run = make_run()
    manager.create_run(run)

    manager.transition(run.run_id, RunState.QUEUED)
    manager.transition(run.run_id, RunState.ORIENTING)
    manager.transition(run.run_id, RunState.PLANNING)
    manager.transition(run.run_id, RunState.EXECUTING)

    manager.add_step(
        run.run_id,
        "step-1",
        "implementation",
    )

    manager.start_attempt(
        run.run_id,
        "step-1",
        "attempt-1",
        "worker-1",
        "lease-1",
    )

    manager.fail_attempt(
        run.run_id,
        "step-1",
        "attempt-1",
        "command failed",
    )

    manager.recover_run(run.run_id)

    failure = FailureClassifier().classify(
        FailureObservation(
            failure_id="failure-1",
            run_id=run.run_id,
            step_id="step-1",
            attempt_id="attempt-1",
            source="command",
            message="command failed",
        )
    )

    decision = RecoveryPolicy().decide(failure)

    assert decision.action is RecoveryAction.RETRY

    handler = RetryRecoveryHandler(manager)

    replacement = handler(
        failure,
        decision,
        request=RetryRequest(
            worker_id="worker-2",
            lease_id="lease-2",
        ),
    )

    assert replacement.attempt_id != "attempt-1"
    assert replacement.worker_id == "worker-2"
    assert replacement.state is AttemptState.RUNNING

    current = manager.get_run(run.run_id)
    step = current.steps[0]

    assert len(step.attempts) == 2
    assert step.attempts[0].state is AttemptState.FAILED
    assert step.attempts[1].state is AttemptState.RUNNING
    assert current.state is RunState.RECOVERING
