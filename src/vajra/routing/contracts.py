from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Complexity(str, Enum):
    SIMPLE = "simple"
    MECHANICAL = "mechanical"
    COMPLEX = "complex"
    DIFFICULT = "difficult"


@dataclass(frozen=True)
class BudgetEnvelope:
    max_model_calls: int = 1
    max_worker_runtime_seconds: int = 300
    max_output_size: int = 1_000_000
    max_cost_units: int = 0

    def __post_init__(self) -> None:
        if any(v < 0 for v in (self.max_model_calls, self.max_worker_runtime_seconds, self.max_output_size, self.max_cost_units)):
            raise ValueError("budget values must be non-negative")


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model: str
    version: str
    adapter: str

    def __post_init__(self) -> None:
        for name in ("provider", "model", "version", "adapter"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")

    @property
    def canonical(self) -> str:
        return f"{self.provider}:{self.model}@{self.version}"


@dataclass(frozen=True)
class ModelUsage:
    model_calls: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    runtime_seconds: float = 0.0
    cost_units: int = 0

    def __post_init__(self) -> None:
        if self.model_calls < 0 or self.input_tokens < 0 or self.output_tokens < 0 or self.runtime_seconds < 0 or self.cost_units < 0:
            raise ValueError("usage values must be non-negative")


@dataclass(frozen=True)
class ModelRequest:
    request_id: str
    run_id: str
    step_id: str
    attempt_id: str
    task: str
    context: dict[str, Any] = field(default_factory=dict)
    tools: tuple[str, ...] = ()
    output_schema: dict[str, Any] = field(default_factory=dict)
    budget: BudgetEnvelope = field(default_factory=BudgetEnvelope)
    deadline: str = ""
    model: str | None = None
    strategy_id: str = "default"

    def __post_init__(self) -> None:
        for name in ("request_id", "run_id", "step_id", "attempt_id", "task", "deadline", "strategy_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True)
class RoutingEvidence:
    evidence_id: str
    request_id: str
    task: str
    complexity: Complexity
    candidates: tuple[str, ...]
    selected_worker: str
    selected_model: ModelIdentity
    reason: str
    budget_cost_units: int = 0

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or not self.request_id.strip() or not self.task.strip() or not self.reason.strip():
            raise ValueError("routing evidence identifiers and reason must not be empty")
        if not self.selected_worker.strip() or not self.candidates:
            raise ValueError("routing evidence must name a selected worker and candidates")


@dataclass(frozen=True)
class RoutingDecision:
    request_id: str
    complexity: Complexity
    worker_id: str
    model: ModelIdentity
    strategy_id: str
    evidence: RoutingEvidence


@dataclass(frozen=True)
class ModelResult:
    status: str
    structured_output: dict[str, Any] = field(default_factory=dict)
    raw_output_reference: str | None = None
    usage: ModelUsage = field(default_factory=ModelUsage)
    model_identity: ModelIdentity | None = None
    errors: tuple[str, ...] = ()
    evidence: tuple[RoutingEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.status.strip():
            raise ValueError("status must not be empty")
        if self.usage.model_calls and self.model_identity is None:
            raise ValueError("successful or attempted model usage must identify the model")


@dataclass(frozen=True)
class TaskProfile:
    task: str
    complexity: Complexity
    required_capabilities: frozenset[str] = frozenset()
    preferred_model: str | None = None
    strategy_id: str = "default"
    max_cost_units: int = 0

    def __post_init__(self) -> None:
        if not self.task.strip() or not self.strategy_id.strip():
            raise ValueError("task and strategy_id must not be empty")
        if self.max_cost_units < 0:
            raise ValueError("max_cost_units must be non-negative")
