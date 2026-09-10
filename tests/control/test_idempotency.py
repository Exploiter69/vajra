import pytest

from vajra.control.contracts import OperationIdentity
from vajra.control.idempotency import (
    IdempotencyConflict,
    IdempotencyDisposition,
    IdempotencyRegistry,
)


def operation(
    *,
    idempotency_key: str = "idem-1",
    operation_id: str = "operation-1",
    parameters_digest: str = "params-1",
    fencing_token: int = 1,
    target_resource: str = "file.txt",
) -> OperationIdentity:
    return OperationIdentity(
        operation_id=operation_id,
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        intent_id="intent-1",
        operation_type="write",
        parameters_digest=parameters_digest,
        target_resource=target_resource,
        fencing_token=fencing_token,
        idempotency_key=idempotency_key,
    )


def test_first_effect_is_new():
    registry = IdempotencyRegistry()

    decision = registry.check(operation(), {"content": "hello"})

    assert decision.disposition is IdempotencyDisposition.NEW
    assert registry.contains("idem-1")


def test_same_operation_and_effect_is_replay():
    registry = IdempotencyRegistry()

    first = registry.check(operation(), {"content": "hello"})
    second = registry.check(operation(), {"content": "hello"})

    assert first.disposition is IdempotencyDisposition.NEW
    assert second.disposition is IdempotencyDisposition.REPLAY
    assert second.existing_effect == first.effect
    assert second.effect.effect_digest == first.effect.effect_digest


def test_same_key_with_different_effect_is_conflict():
    registry = IdempotencyRegistry()

    registry.check(operation(), {"content": "hello"})

    with pytest.raises(IdempotencyConflict):
        registry.check(operation(), {"content": "different"})


def test_same_key_with_different_parameters_is_conflict():
    registry = IdempotencyRegistry()

    registry.check(operation(parameters_digest="params-1"), {"content": "hello"})

    with pytest.raises(IdempotencyConflict):
        registry.check(
            operation(parameters_digest="params-2"),
            {"content": "hello"},
        )


def test_same_key_with_different_target_is_conflict():
    registry = IdempotencyRegistry()

    registry.check(
        operation(target_resource="file-a.txt"),
        {"content": "hello"},
    )

    with pytest.raises(IdempotencyConflict):
        registry.check(
            operation(target_resource="file-b.txt"),
            {"content": "hello"},
        )


def test_fencing_token_is_part_of_effect_identity():
    registry = IdempotencyRegistry()

    registry.check(
        operation(fencing_token=1),
        {"content": "hello"},
    )

    with pytest.raises(IdempotencyConflict):
        registry.check(
            operation(fencing_token=2),
            {"content": "hello"},
        )


def test_effect_identity_is_deterministic():
    registry = IdempotencyRegistry()

    first = registry.effect_identity(
        operation(),
        {"b": 2, "a": 1},
    )
    second = registry.effect_identity(
        operation(),
        {"a": 1, "b": 2},
    )

    assert first.effect_digest == second.effect_digest


def test_registry_does_not_execute_operations():
    registry = IdempotencyRegistry()
    called = False

    def dangerous_operation():
        nonlocal called
        called = True

    decision = registry.check(
        operation(),
        {"description": "effect only"},
    )

    assert decision.disposition is IdempotencyDisposition.NEW
    assert not called
