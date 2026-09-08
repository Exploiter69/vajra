from __future__ import annotations

import pytest

from vajra.domain import Checkpoint, EngineeringRun, RunState
from vajra.recovery.checkpoint import (
    CheckpointRestoreRequest,
    RestoreCheckpointRecoveryHandler,
)
from vajra.recovery.contracts import (
    Failure,
    FailureCategory,
    RecoveryAction,
)
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.event_store import InMemoryEventStore
from vajra.runtime.run_manager import RunManager
from vajra.runtime.state_store import InMemoryStateStore


def make_manager() -> RunManager:
    manager = RunManager(
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
    )

    run = EngineeringRun(
        run_id="run-1",
        objective="restore checkpoint",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="default",
        policy_version="v1",
        budget_id="budget-1",
    )

    manager.create_run(run)
    manager.transition("run-1", RunState.QUEUED)
    manager.transition("run-1", RunState.ORIENTING)
    manager.recover_run("run-1")

    return manager


def make_failure() -> Failure:
    return Failure(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.STATE_DIVERGENCE,
        message="workspace diverged",
        details={"checkpoint_id": "checkpoint-1"},
    )


def make_decision() -> RecoveryDecision:
    return RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.STATE_DIVERGENCE,
        action=RecoveryAction.RESTORE_CHECKPOINT,
        reason="restore known-good state",
    )


def make_checkpoint() -> Checkpoint:
    return Checkpoint(
        checkpoint_id="checkpoint-1",
        run_id="run-1",
        step_id="step-1",
        event_position=4,
        git_revision="abc123",
        workspace_identity="workspace-1",
        policy_version="v1",
        state_digest="digest-1",
    )


def test_delegates_checkpoint_restore():
    manager = make_manager()
    checkpoint = make_checkpoint()
    calls = []

    def restorer(failure, decision, supplied):
        calls.append((failure, decision, supplied))
        return CheckpointRestoreRequest(
            checkpoint_id=supplied.checkpoint_id,
            reason="restoration delegated",
        )

    handler = RestoreCheckpointRecoveryHandler(
        manager,
        lambda checkpoint_id: (
            checkpoint if checkpoint_id == "checkpoint-1" else None
        ),
        restorer,
    )

    result = handler(make_failure(), make_decision())

    assert result.checkpoint_id == checkpoint.checkpoint_id
    assert result.reason == "restoration delegated"
    assert len(calls) == 1
    assert calls[0][2] == checkpoint
    assert manager.get_run("run-1").state is RunState.RECOVERING


def test_requires_recovering_run():
    manager = make_manager()
    manager.transition("run-1", RunState.QUEUED)

    checkpoint = make_checkpoint()

    handler = RestoreCheckpointRecoveryHandler(
        manager,
        lambda _: checkpoint,
        lambda failure, decision, supplied: CheckpointRestoreRequest(
            checkpoint_id=supplied.checkpoint_id,
            reason="restore",
        ),
    )

    with pytest.raises(ValueError, match="not recovering"):
        handler(make_failure(), make_decision())

    assert manager.get_run("run-1").state is RunState.QUEUED


def test_rejects_wrong_action():
    manager = make_manager()
    checkpoint = make_checkpoint()

    handler = RestoreCheckpointRecoveryHandler(
        manager,
        lambda _: checkpoint,
        lambda failure, decision, supplied: CheckpointRestoreRequest(
            checkpoint_id=supplied.checkpoint_id,
            reason="restore",
        ),
    )

    decision = RecoveryDecision(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.STATE_DIVERGENCE,
        action=RecoveryAction.RETRY,
        reason="retry",
    )

    with pytest.raises(ValueError, match="requires a RESTORE_CHECKPOINT"):
        handler(make_failure(), decision)


def test_rejects_checkpoint_from_different_run():
    manager = make_manager()

    checkpoint = Checkpoint(
        checkpoint_id="checkpoint-1",
        run_id="run-other",
        step_id="step-1",
        event_position=4,
        git_revision="abc123",
        workspace_identity="workspace-1",
        policy_version="v1",
        state_digest="digest-1",
    )

    handler = RestoreCheckpointRecoveryHandler(
        manager,
        lambda _: checkpoint,
        lambda failure, decision, supplied: CheckpointRestoreRequest(
            checkpoint_id=supplied.checkpoint_id,
            reason="restore",
        ),
    )

    with pytest.raises(ValueError, match="run_id"):
        handler(make_failure(), make_decision())


def test_rejects_missing_checkpoint():
    manager = make_manager()

    handler = RestoreCheckpointRecoveryHandler(
        manager,
        lambda _: None,
        lambda failure, decision, supplied: CheckpointRestoreRequest(
            checkpoint_id=supplied.checkpoint_id,
            reason="restore",
        ),
    )

    with pytest.raises(ValueError, match="Checkpoint not found"):
        handler(make_failure(), make_decision())


def test_requires_checkpoint_identity_in_failure():
    manager = make_manager()

    handler = RestoreCheckpointRecoveryHandler(
        manager,
        lambda _: make_checkpoint(),
        lambda failure, decision, supplied: CheckpointRestoreRequest(
            checkpoint_id=supplied.checkpoint_id,
            reason="restore",
        ),
    )

    failure = Failure(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.STATE_DIVERGENCE,
        message="workspace diverged",
    )

    with pytest.raises(ValueError, match="checkpoint_id"):
        handler(failure, make_decision())


def test_rejects_invalid_checkpoint_metadata():
    manager = make_manager()

    checkpoint = Checkpoint(
        checkpoint_id="checkpoint-1",
        run_id="run-1",
        step_id="step-1",
        event_position=-1,
        git_revision="abc123",
        workspace_identity="workspace-1",
        policy_version="v1",
        state_digest="digest-1",
    )

    handler = RestoreCheckpointRecoveryHandler(
        manager,
        lambda _: checkpoint,
        lambda failure, decision, supplied: CheckpointRestoreRequest(
            checkpoint_id=supplied.checkpoint_id,
            reason="restore",
        ),
    )

    with pytest.raises(ValueError, match="event_position"):
        handler(make_failure(), make_decision())


def test_rejects_bad_restorer_result():
    manager = make_manager()
    checkpoint = make_checkpoint()

    handler = RestoreCheckpointRecoveryHandler(
        manager,
        lambda _: checkpoint,
        lambda failure, decision, supplied: CheckpointRestoreRequest(
            checkpoint_id="wrong-checkpoint",
            reason="restore",
        ),
    )

    with pytest.raises(ValueError, match="different checkpoint_id"):
        handler(make_failure(), make_decision())
