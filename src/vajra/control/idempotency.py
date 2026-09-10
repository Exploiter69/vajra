from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .contracts import OperationIdentity
from .reality import stable_digest


class IdempotencyError(ValueError):
    """Base error for idempotency violations."""


class IdempotencyConflict(IdempotencyError):
    """Raised when one idempotency key is reused for a different effect."""


class IdempotencyDisposition(str, Enum):
    NEW = "NEW"
    REPLAY = "REPLAY"


@dataclass(frozen=True)
class EffectIdentity:
    effect_digest: str
    operation_id: str
    idempotency_key: str
    target_resource: str
    fencing_token: int

    def __post_init__(self) -> None:
        for name in (
            "effect_digest",
            "operation_id",
            "idempotency_key",
            "target_resource",
        ):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")

        if self.fencing_token < 0:
            raise ValueError("fencing_token must not be negative")


@dataclass(frozen=True)
class IdempotencyDecision:
    disposition: IdempotencyDisposition
    effect: EffectIdentity
    existing_effect: EffectIdentity | None = None


class IdempotencyRegistry:
    """
    Resource-local logical idempotency registry.

    The registry does not execute operations. It establishes whether an
    operation/effect identity is new, a safe replay, or a conflicting reuse
    of an idempotency key.

    A production durable implementation must persist this registry at the
    resource/effect authority. This in-memory implementation establishes the
    control contract and semantics for Phase 7.3.
    """

    def __init__(self) -> None:
        self._effects: dict[str, EffectIdentity] = {}

    @staticmethod
    def effect_identity(
        operation: OperationIdentity,
        effect: Any,
    ) -> EffectIdentity:
        digest = stable_digest(
            {
                "operation_id": operation.operation_id,
                "run_id": operation.run_id,
                "step_id": operation.step_id,
                "attempt_id": operation.attempt_id,
                "intent_id": operation.intent_id,
                "operation_type": operation.operation_type,
                "parameters_digest": operation.parameters_digest,
                "target_resource": operation.target_resource,
                "fencing_token": operation.fencing_token,
                "effect": effect,
            }
        )

        return EffectIdentity(
            effect_digest=digest,
            operation_id=operation.operation_id,
            idempotency_key=operation.idempotency_key,
            target_resource=operation.target_resource,
            fencing_token=operation.fencing_token,
        )

    def check(
        self,
        operation: OperationIdentity,
        effect: Any,
    ) -> IdempotencyDecision:
        candidate = self.effect_identity(operation, effect)
        existing = self._effects.get(operation.idempotency_key)

        if existing is None:
            self._effects[operation.idempotency_key] = candidate
            return IdempotencyDecision(
                disposition=IdempotencyDisposition.NEW,
                effect=candidate,
            )

        if existing.effect_digest != candidate.effect_digest:
            raise IdempotencyConflict(
                "idempotency key is already bound to a different effect"
            )

        return IdempotencyDecision(
            disposition=IdempotencyDisposition.REPLAY,
            effect=candidate,
            existing_effect=existing,
        )

    def contains(self, idempotency_key: str) -> bool:
        return idempotency_key in self._effects
