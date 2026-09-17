from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from enum import Enum


class ChaosTarget(str, Enum):
    CONTROLLER = "controller"
    WORKER = "worker"
    MODEL = "model"
    PROCESS = "process"
    NETWORK = "network"
    SANDBOX = "sandbox"
    MACHINE_SIMULATION = "machine_simulation"


class FaultMode(str, Enum):
    KILL = "kill"
    FAIL = "fail"
    DISCONNECT = "disconnect"
    CORRUPT = "corrupt"
    EXPIRE = "expire"


@dataclass(frozen=True)
class ChaosEvent:
    sequence: int
    target: ChaosTarget
    mode: FaultMode
    seed: int

    @property
    def event_id(self) -> str:
        payload = f"{self.sequence}|{self.target.value}|{self.mode.value}|{self.seed}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChaosPlan:
    seed: int = 11
    ticks: int = 100
    injection_probability: float = 0.15
    targets: tuple[ChaosTarget, ...] = tuple(ChaosTarget)
    modes: tuple[FaultMode, ...] = tuple(FaultMode)

    def __post_init__(self) -> None:
        if self.ticks <= 0:
            raise ValueError("ticks must be positive")
        if not 0.0 <= self.injection_probability <= 1.0:
            raise ValueError("injection_probability must be between 0 and 1")
        if not self.targets:
            raise ValueError("targets must not be empty")
        if not self.modes:
            raise ValueError("modes must not be empty")

    def events(self) -> tuple[ChaosEvent, ...]:
        rng = random.Random(self.seed)
        events: list[ChaosEvent] = []
        for tick in range(1, self.ticks + 1):
            if rng.random() <= self.injection_probability:
                target = self.targets[rng.randrange(len(self.targets))]
                mode = self.modes[rng.randrange(len(self.modes))]
                events.append(ChaosEvent(tick, target, mode, self.seed))
        return tuple(events)


class FaultInjector:
    """Deterministic fault schedule; it never mutates VAJRA state itself."""

    def __init__(self, plan: ChaosPlan) -> None:
        self._events = {event.sequence: event for event in plan.events()}

    def event_at(self, tick: int) -> ChaosEvent | None:
        if tick <= 0:
            raise ValueError("tick must be positive")
        return self._events.get(tick)

    def all_events(self) -> tuple[ChaosEvent, ...]:
        return tuple(self._events.values())


@dataclass(frozen=True)
class RetryStormDecision:
    run_id: str
    step_id: str
    failure_signature: str
    attempts: int
    terminate: bool
    reason: str


class RetryStormGuard:
    """Hard deterministic bound for repeated identical failures."""

    def __init__(self, *, max_retries: int = 3) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1")
        self._max_retries = max_retries
        self._counts: dict[tuple[str, str, str], int] = {}

    def observe(
        self,
        *,
        run_id: str,
        step_id: str,
        failure_signature: str,
    ) -> RetryStormDecision:
        if not run_id or not step_id or not failure_signature:
            raise ValueError("run_id, step_id and failure_signature are required")
        key = (run_id, step_id, failure_signature)
        attempts = self._counts.get(key, 0) + 1
        self._counts[key] = attempts
        terminate = attempts >= self._max_retries
        return RetryStormDecision(
            run_id=run_id,
            step_id=step_id,
            failure_signature=failure_signature,
            attempts=attempts,
            terminate=terminate,
            reason=(
                "retry storm threshold reached"
                if terminate
                else "retry remains bounded"
            ),
        )


@dataclass(frozen=True)
class SoakSample:
    elapsed_seconds: float
    memory_bytes: int
    disk_bytes: int
    event_count: int
    context_items: int
    worker_leaks: int
    stale_leases: int
    retry_count: int
    verification_failures: int
    provider_failures: int
    clock_anomalies: int

    def __post_init__(self) -> None:
        if self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must not be negative")
        for name in (
            "memory_bytes",
            "disk_bytes",
            "event_count",
            "context_items",
            "worker_leaks",
            "stale_leases",
            "retry_count",
            "verification_failures",
            "provider_failures",
            "clock_anomalies",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True)
class SoakMetrics:
    samples: tuple[SoakSample, ...]

    @property
    def first(self) -> SoakSample:
        if not self.samples:
            raise ValueError("no soak samples")
        return self.samples[0]

    @property
    def last(self) -> SoakSample:
        if not self.samples:
            raise ValueError("no soak samples")
        return self.samples[-1]

    @property
    def memory_growth_bytes(self) -> int:
        return self.last.memory_bytes - self.first.memory_bytes

    @property
    def disk_growth_bytes(self) -> int:
        return self.last.disk_bytes - self.first.disk_bytes

    @property
    def event_growth(self) -> int:
        return self.last.event_count - self.first.event_count

    @property
    def context_growth(self) -> int:
        return self.last.context_items - self.first.context_items

    @property
    def retry_growth(self) -> int:
        return self.last.retry_count - self.first.retry_count

    def violations(
        self,
        *,
        max_memory_growth_bytes: int | None = None,
        max_disk_growth_bytes: int | None = None,
        max_worker_leaks: int = 0,
        max_stale_leases: int = 0,
        max_clock_anomalies: int = 0,
    ) -> tuple[str, ...]:
        violations: list[str] = []
        if (
            max_memory_growth_bytes is not None
            and self.memory_growth_bytes > max_memory_growth_bytes
        ):
            violations.append("memory_growth")
        if (
            max_disk_growth_bytes is not None
            and self.disk_growth_bytes > max_disk_growth_bytes
        ):
            violations.append("disk_growth")
        if self.last.worker_leaks > max_worker_leaks:
            violations.append("worker_leaks")
        if self.last.stale_leases > max_stale_leases:
            violations.append("stale_leases")
        if self.last.clock_anomalies > max_clock_anomalies:
            violations.append("clock_anomalies")
        return tuple(violations)

    @property
    def passed(self) -> bool:
        return not self.violations()


@dataclass(frozen=True)
class LongRunProfile:
    name: str
    duration_seconds: int

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("name must not be empty")
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")


LONG_RUN_PROFILES: tuple[LongRunProfile, ...] = (
    LongRunProfile("1h", 60 * 60),
    LongRunProfile("12h", 12 * 60 * 60),
    LongRunProfile("3d", 3 * 24 * 60 * 60),
    LongRunProfile("7d", 7 * 24 * 60 * 60),
    LongRunProfile("30d", 30 * 24 * 60 * 60),
)


__all__ = [
    "ChaosEvent",
    "ChaosPlan",
    "ChaosTarget",
    "FaultInjector",
    "FaultMode",
    "LongRunProfile",
    "LONG_RUN_PROFILES",
    "RetryStormDecision",
    "RetryStormGuard",
    "SoakMetrics",
    "SoakSample",
]
