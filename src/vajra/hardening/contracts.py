from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from threading import RLock
from typing import Any


class HardeningViolation(RuntimeError):
    """Raised when a production-hardening invariant cannot be established."""


@dataclass(frozen=True)
class ResourceLimits:
    cpu_seconds: float | None = None
    memory_bytes: int | None = None
    disk_bytes: int | None = None
    network_bytes: int | None = None
    process_count: int | None = None
    output_bytes: int | None = None
    model_calls: int | None = None
    worker_runtime_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or value < 0):
                raise ValueError(f"{name} must be non-negative")


@dataclass
class ResourceUsage:
    cpu_seconds: float = 0.0
    memory_bytes: int = 0
    disk_bytes: int = 0
    network_bytes: int = 0
    process_count: int = 0
    output_bytes: int = 0
    model_calls: int = 0
    worker_runtime_seconds: float = 0.0

    def consume(self, **values: float | int) -> None:
        for name, value in values.items():
            if name not in self.__dataclass_fields__:
                raise ValueError(f"unknown resource: {name}")
            if value < 0:
                raise ValueError(f"{name} increment must be non-negative")
            setattr(self, name, getattr(self, name) + value)


@dataclass(frozen=True)
class ResourceDecision:
    allowed: bool
    resource: str | None
    limit: float | int | None
    observed: float | int
    reason: str


class ResourceGovernor:
    """Deterministic fail-closed accounting for every Phase 15 resource."""

    def __init__(self, limits: ResourceLimits, usage: ResourceUsage | None = None) -> None:
        self.limits = limits
        self.usage = usage or ResourceUsage()
        self._lock = RLock()

    def charge(self, **values: float | int) -> ResourceDecision:
        with self._lock:
            return self._charge_locked(**values)

    def _charge_locked(self, **values: float | int) -> ResourceDecision:
        for name, value in values.items():
            if name not in self.usage.__dataclass_fields__:
                return ResourceDecision(False, name, None, 0, f"unknown resource: {name}")
            if value < 0:
                return ResourceDecision(False, name, None, getattr(self.usage, name), "negative charge")
            limit = getattr(self.limits, name)
            projected = getattr(self.usage, name) + value
            if limit is not None and projected > limit:
                return ResourceDecision(
                    False, name, limit, projected, f"{name} limit exceeded"
                )
        self.usage.consume(**values)
        return ResourceDecision(True, None, None, 0, "resource charge accepted")

    def check(self) -> ResourceDecision:
        with self._lock:
            for name in self.usage.__dataclass_fields__:
                limit = getattr(self.limits, name)
                observed = getattr(self.usage, name)
                if limit is not None and observed > limit:
                    return ResourceDecision(False, name, limit, observed, f"{name} limit exceeded")
            return ResourceDecision(True, None, None, 0, "resource usage within limits")


class AuditEventType(str, Enum):
    SECURITY = "SECURITY"
    RESOURCE = "RESOURCE"
    EXECUTION = "EXECUTION"
    WORKER = "WORKER"
    VERIFICATION = "VERIFICATION"
    RECOVERY = "RECOVERY"
    CONTROL = "CONTROL"


@dataclass(frozen=True)
class AuditRecord:
    audit_id: str
    event_type: AuditEventType
    timestamp: str
    run_id: str
    step_id: str | None = None
    attempt_id: str | None = None
    worker_id: str | None = None
    model_id: str | None = None
    operation: str | None = None
    outcome: str = ""
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    record_digest: str = ""

    def __post_init__(self) -> None:
        if not self.audit_id or not self.run_id or not self.timestamp:
            raise ValueError("audit identity fields must not be empty")
        expected = hashlib.sha256(json.dumps({
            "audit_id": self.audit_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "model_id": self.model_id,
            "operation": self.operation,
            "outcome": self.outcome,
            "reason": self.reason,
            "payload": self.payload,
        }, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        if self.record_digest and self.record_digest != expected:
            raise ValueError("audit record digest mismatch")

    def with_digest(self) -> "AuditRecord":
        payload = {
            "audit_id": self.audit_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "attempt_id": self.attempt_id,
            "worker_id": self.worker_id,
            "model_id": self.model_id,
            "operation": self.operation,
            "outcome": self.outcome,
            "reason": self.reason,
            "payload": self.payload,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        return AuditRecord(record_digest=digest, **{k: v for k, v in payload.items() if k != "event_type"}, event_type=self.event_type)
