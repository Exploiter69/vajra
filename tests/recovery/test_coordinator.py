import pytest

from vajra.domain import EngineeringRun, RunState
from vajra.recovery import Failure, FailureCategory, RecoveryAction
from vajra.recovery.coordinator import RecoveryCoordinator
from vajra.recovery.policy import RecoveryDecision
from vajra.runtime.run_manager import RunManager


def make_run(
    run_id: str = "run-1",
    state: RunState = RunState.EXECUTING,
) -> EngineeringRun:
    return EngineeringRun(
        run_id=run_id,
        created_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        updated_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
        objective="test objective",
        repository_id="repo-1",
        base_revision="abc123",
        acceptance_criteria=("tests pass",),
        policy_id="engineering-v0",
        policy_version="1",
        budget_id="budget-1",
        state=state,
        steps=[],
        artifacts=[],
        verification_results=[],
        final_disposition=None,
        workspace_id="workspace-1",
        current_step_id=None,
    )


def make_failure(
    failure_id: str = "failure-1",
    run_id: str = "run-1",
) -> Failure:
    return Failure(
        failure_id=failure_id,
        run_id=run_id,
        step_id="step-1",
        attempt_id="attempt-1",
        category=FailureCategory.COMMAND_FAILURE,
        message="command failed",
    )


def make_decision(
    failure: Failure,
    action: RecoveryAction = RecoveryAction.RETRY,
) -> RecoveryDecision:
    return RecoveryDecision(
        failure_id=failure.failure_id,
        run_id=failure.run_id,
        step_id=failure.step_id,
        attempt_id=failure.attempt_id,
        category=failure.category,
        action=action,
        reason="test recovery",
    )


def test_coordinator_dispatches_registered_handler() -> None:
    manager = RunManager()
    manager.create_run(make_run())

    failure = make_failure()
    decision = make_decision(failure)

    calls = []

    def handler(received_failure, received_decision):
        calls.append((received_failure, received_decision))

    coordinator = RecoveryCoordinator(
        manager,
        {RecoveryAction.RETRY: handler},
    )

    outcome = coordinator.coordinate(failure, decision)

    assert outcome.status == "DISPATCHED"
    assert outcome.action is RecoveryAction.RETRY
    assert calls == [(failure, decision)]
    assert manager.get_run("run-1").state is RunState.RECOVERING


def test_coordinator_does_not_execute_without_handler() -> None:
    manager = RunManager()
    manager.create_run(make_run())

    failure = make_failure()
    decision = make_decision(failure)

    coordinator = RecoveryCoordinator(manager)

    with pytest.raises(RuntimeError, match="No recovery handler registered"):
        coordinator.coordinate(failure, decision)

    assert manager.get_run("run-1").state is RunState.RECOVERING


def test_recovering_run_does_not_transition_again() -> None:
    manager = RunManager()
    manager.create_run(make_run(state=RunState.RECOVERING))

    failure = make_failure()
    decision = make_decision(failure)

    calls = []

    coordinator = RecoveryCoordinator(
        manager,
        {RecoveryAction.RETRY: lambda f, d: calls.append(True)},
    )

    outcome = coordinator.coordinate(failure, decision)

    assert outcome.status == "DISPATCHED"
    assert calls == [True]
    assert manager.get_run("run-1").state is RunState.RECOVERING


def test_failed_run_enters_recovery() -> None:
    manager = RunManager()
    manager.create_run(make_run(state=RunState.FAILED))

    failure = make_failure()
    decision = make_decision(failure)

    coordinator = RecoveryCoordinator(
        manager,
        {RecoveryAction.RETRY: lambda f, d: None},
    )

    coordinator.coordinate(failure, decision)

    assert manager.get_run("run-1").state is RunState.RECOVERING


@pytest.mark.parametrize(
    "action",
    list(RecoveryAction),
)
def test_every_v0_action_can_be_explicitly_registered(
    action: RecoveryAction,
) -> None:
    manager = RunManager()
    manager.create_run(make_run())

    failure = make_failure()
    decision = make_decision(failure, action)

    calls = []

    coordinator = RecoveryCoordinator(
        manager,
        {action: lambda f, d: calls.append(d.action)},
    )

    outcome = coordinator.coordinate(failure, decision)

    assert outcome.action is action
    assert calls == [action]


def test_mismatched_failure_id_is_rejected() -> None:
    manager = RunManager()
    manager.create_run(make_run())

    failure = make_failure()
    decision = make_decision(failure)

    mismatched = Failure(
        failure_id="different",
        run_id=failure.run_id,
        step_id=failure.step_id,
        attempt_id=failure.attempt_id,
        category=failure.category,
        message=failure.message,
    )

    coordinator = RecoveryCoordinator(
        manager,
        {RecoveryAction.RETRY: lambda f, d: None},
    )

    with pytest.raises(ValueError, match="failure"):
        coordinator.coordinate(mismatched, decision)


def test_mismatched_run_id_is_rejected() -> None:
    manager = RunManager()
    manager.create_run(make_run())

    failure = make_failure()
    decision = make_decision(failure)

    mismatched = Failure(
        failure_id=failure.failure_id,
        run_id="different-run",
        step_id=failure.step_id,
        attempt_id=failure.attempt_id,
        category=failure.category,
        message=failure.message,
    )

    coordinator = RecoveryCoordinator(
        manager,
        {RecoveryAction.RETRY: lambda f, d: None},
    )

    with pytest.raises(ValueError, match="run_id"):
        coordinator.coordinate(mismatched, decision)


def test_mismatched_step_id_is_rejected() -> None:
    manager = RunManager()
    manager.create_run(make_run())

    failure = make_failure()
    decision = make_decision(failure)

    mismatched = Failure(
        failure_id=failure.failure_id,
        run_id=failure.run_id,
        step_id="different-step",
        attempt_id=failure.attempt_id,
        category=failure.category,
        message=failure.message,
    )

    coordinator = RecoveryCoordinator(
        manager,
        {RecoveryAction.RETRY: lambda f, d: None},
    )

    with pytest.raises(ValueError, match="step_id"):
        coordinator.coordinate(mismatched, decision)


def test_mismatched_attempt_id_is_rejected() -> None:
    manager = RunManager()
    manager.create_run(make_run())

    failure = make_failure()
    decision = make_decision(failure)

    mismatched = Failure(
        failure_id=failure.failure_id,
        run_id=failure.run_id,
        step_id=failure.step_id,
        attempt_id="different-attempt",
        category=failure.category,
        message=failure.message,
    )

    coordinator = RecoveryCoordinator(
        manager,
        {RecoveryAction.RETRY: lambda f, d: None},
    )

    with pytest.raises(ValueError, match="attempt_id"):
        coordinator.coordinate(mismatched, decision)
