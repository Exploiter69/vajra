from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from vajra.context.contracts import ContextBundle
from vajra.policy.contracts import Intent


class LoopPhase(str, Enum):
    OBJECTIVE = "OBJECTIVE"
    ORIENT = "ORIENT"
    CONTEXT = "CONTEXT"
    PLAN = "PLAN"
    INTENT = "INTENT"
    POLICY = "POLICY"
    EXECUTE = "EXECUTE"
    OBSERVE = "OBSERVE"
    VERIFY = "VERIFY"
    MEASURE_PROGRESS = "MEASURE_PROGRESS"
    DECIDE_NEXT_STEP = "DECIDE_NEXT_STEP"
    COMPLETE = "COMPLETE"
    WAIT_HUMAN = "WAIT_HUMAN"
    STOP = "STOP"


@dataclass(frozen=True)
class PlannedIntent:
    intent_id: str
    operation: str
    parameters: dict[str, Any] = field(default_factory=dict)
    requested_capabilities: tuple[str, ...] = ()
    reason: str = ""
    strategy_id: str = ""

    def __post_init__(self) -> None:
        for name in ("intent_id", "operation"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if not self.reason.strip():
            raise ValueError("reason must not be empty")

    def to_intent(self, *, run_id: str, step_id: str, attempt_id: str) -> Intent:
        return Intent(
            intent_id=self.intent_id,
            run_id=run_id,
            step_id=step_id,
            attempt_id=attempt_id,
            operation=self.operation,
            parameters=dict(self.parameters),
            requested_capabilities=self.requested_capabilities,
            reason=self.reason,
        )


@dataclass(frozen=True)
class EngineeringPlan:
    plan_id: str
    context_digest: str
    intents: tuple[PlannedIntent, ...]
    strategy_id: str = ""

    def __post_init__(self) -> None:
        if not self.plan_id.strip() or not self.context_digest.strip():
            raise ValueError("plan_id and context_digest must not be empty")
        if not self.intents:
            raise ValueError("engineering plan must contain at least one intent")


@dataclass(frozen=True)
class ProgressMeasurement:
    before_digest: str
    after_digest: str
    verification_passed: int
    verification_failed: int
    verification_inconclusive: int
    artifact_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return self.before_digest != self.after_digest

    @property
    def verification_improved(self) -> bool:
        return self.verification_passed > 0 and self.verification_failed == 0

    @property
    def useful(self) -> bool:
        return self.changed or self.verification_improved


@dataclass(frozen=True)
class LoopResult:
    run_id: str
    phase: LoopPhase
    cycles: int
    completed: bool
    waiting_human: bool
    stopped: bool
    reason: str
    progress: tuple[ProgressMeasurement, ...] = ()


class ReasoningProvider(Protocol):
    """Model boundary: reasoning proposes; it never executes or verifies."""

    def orient(self, context: ContextBundle) -> str: ...

    def plan(self, context: ContextBundle, orientation: str) -> EngineeringPlan: ...

    def replan(
        self,
        context: ContextBundle,
        previous_plan: EngineeringPlan,
        failure_reason: str,
    ) -> EngineeringPlan: ...


class LoopObserver(Protocol):
    def observe(self, *, phase: LoopPhase, run_id: str, payload: dict[str, Any]) -> None: ...


class NullLoopObserver:
    def observe(self, *, phase: LoopPhase, run_id: str, payload: dict[str, Any]) -> None:
        return None
