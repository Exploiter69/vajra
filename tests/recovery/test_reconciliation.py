from datetime import datetime, timedelta, timezone

from vajra.domain import (
    Attempt,
    AttemptState,
    Checkpoint,
    EngineeringRun,
    RunState,
    Step,
    StepState,
)
from vajra.recovery.reconciliation import (
    RecoveryDisposition,
    RecoveryObservation,
    RecoveryReconciler,
)
from vajra.runtime.lease import WorkerLease


def make_run() -> EngineeringRun:
    attempt = Attempt(
        attempt_id="attempt-1",
        step_id="step-1",
        run_id="run-1",
        state=AttemptState.FAILED,
        worker_id="worker-1",
    )
    step = Step(
        step_id="step-1",
        run_id="run-1",
        name="test",
        state=StepState.RECOVERING,
        attempts=[attempt],
    )
    return EngineeringRun(
        run_id="run-1",
        created_at=datetime.now(timezone.utc),
        objective="recover",
        repository_id="repo-1",
        base_revision="base",
        acceptance_criteria=(),
        policy_id="policy",
        policy_version="v1",
        budget_id="budget-1",
        state=RunState.RECOVERING,
        steps=[step],
        current_step_id="step-1",
    )


def make_checkpoint() -> Checkpoint:
    return Checkpoint(
        checkpoint_id="checkpoint-1",
        run_id="run-1",
        step_id="step-1",
        event_position=3,
        git_revision="abc123",
        workspace_identity="workspace-1",
        policy_version="v1",
        state_digest="digest",
    )


def make_observation(**overrides) -> RecoveryObservation:
    values = {
        "run_state": RunState.RECOVERING,
        "event_position": 4,
        "git_revision": "abc123",
        "workspace_identity": "workspace-1",
    }
    values.update(overrides)
    return RecoveryObservation(**values)


def test_consistent_state_can_resume():
    result = RecoveryReconciler().assess(
        make_run(),
        make_checkpoint(),
        make_observation(),
    )

    assert result.disposition is RecoveryDisposition.RESUME


def test_git_divergence_requires_checkpoint_restore():
    result = RecoveryReconciler().assess(
        make_run(),
        make_checkpoint(),
        make_observation(git_revision="different"),
    )

    assert result.disposition is RecoveryDisposition.RESTORE_CHECKPOINT


def test_workspace_divergence_requires_checkpoint_restore():
    result = RecoveryReconciler().assess(
        make_run(),
        make_checkpoint(),
        make_observation(workspace_identity="different"),
    )

    assert result.disposition is RecoveryDisposition.RESTORE_CHECKPOINT


def test_missing_checkpoint_requires_human():
    result = RecoveryReconciler().assess(
        make_run(),
        None,
        make_observation(),
    )

    assert result.disposition is RecoveryDisposition.REQUEST_HUMAN


def test_run_state_mismatch_requires_human():
    result = RecoveryReconciler().assess(
        make_run(),
        make_checkpoint(),
        make_observation(run_state=RunState.EXECUTING),
    )

    assert result.disposition is RecoveryDisposition.REQUEST_HUMAN


def test_nonrecovering_run_requires_human():
    run = make_run()
    run.state = RunState.EXECUTING

    result = RecoveryReconciler().assess(
        run,
        make_checkpoint(),
        make_observation(run_state=RunState.EXECUTING),
    )

    assert result.disposition is RecoveryDisposition.REQUEST_HUMAN


def test_checkpoint_ahead_of_event_history_requires_human():
    result = RecoveryReconciler().assess(
        make_run(),
        make_checkpoint(),
        make_observation(event_position=2),
    )

    assert result.disposition is RecoveryDisposition.REQUEST_HUMAN


def test_lease_loss_requires_human():
    lease = WorkerLease(
        attempt_id="attempt-1",
        worker_id="worker-1",
        lease_id="lease-1",
        lease_expiry=datetime.now(timezone.utc) + timedelta(minutes=1),
        fencing_token=1,
    )

    result = RecoveryReconciler().assess(
        make_run(),
        make_checkpoint(),
        make_observation(
            lease=lease,
            lease_valid=False,
        ),
    )

    assert result.disposition is RecoveryDisposition.REQUEST_HUMAN


def test_unknown_lease_attempt_aborts():
    lease = WorkerLease(
        attempt_id="unknown-attempt",
        worker_id="worker-1",
        lease_id="lease-1",
        lease_expiry=datetime.now(timezone.utc) + timedelta(minutes=1),
        fencing_token=1,
    )

    result = RecoveryReconciler().assess(
        make_run(),
        make_checkpoint(),
        make_observation(
            lease=lease,
            lease_valid=True,
        ),
    )

    assert result.disposition is RecoveryDisposition.ABORT


def test_valid_lease_can_resume():
    lease = WorkerLease(
        attempt_id="attempt-1",
        worker_id="worker-1",
        lease_id="lease-1",
        lease_expiry=datetime.now(timezone.utc) + timedelta(minutes=1),
        fencing_token=1,
    )

    result = RecoveryReconciler().assess(
        make_run(),
        make_checkpoint(),
        make_observation(
            lease=lease,
            lease_valid=True,
        ),
    )

    assert result.disposition is RecoveryDisposition.RESUME


def test_observation_rejects_invalid_values():
    try:
        RecoveryObservation(
            run_state=RunState.RECOVERING,
            event_position=-1,
            git_revision="abc",
            workspace_identity="workspace",
        )
    except ValueError as exc:
        assert "event_position" in str(exc)
    else:
        raise AssertionError("Expected invalid event position to fail")
