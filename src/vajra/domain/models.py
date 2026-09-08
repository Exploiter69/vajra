from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RunState(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    ORIENTING = "ORIENTING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    CANDIDATE = "CANDIDATE"
    PROMOTION = "PROMOTION"
    COMPLETE = "COMPLETE"

    RECOVERING = "RECOVERING"
    PAUSED = "PAUSED"
    WAITING_HUMAN = "WAITING_HUMAN"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"


class StepState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RECOVERING = "RECOVERING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class AttemptState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class VerificationStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"


class FinalDisposition(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class Budget:
    budget_id: str
    max_runtime_seconds: int
    max_steps: int
    max_attempts: int
    max_model_calls: int
    max_command_count: int
    max_output_size: int
    max_worker_runtime_seconds: int


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    location: str
    sha256: str | None = None


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    kind: str
    location: str
    digest: str | None = None


@dataclass
class Attempt:
    attempt_id: str
    step_id: str
    run_id: str
    state: AttemptState = AttemptState.CREATED
    worker_id: str | None = None
    lease_id: str | None = None
    lease_expiry: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


@dataclass
class Step:
    step_id: str
    run_id: str
    name: str
    state: StepState = StepState.PENDING
    attempts: list[Attempt] = field(default_factory=list)


@dataclass
class Checkpoint:
    checkpoint_id: str
    run_id: str
    step_id: str
    event_position: int
    git_revision: str
    workspace_identity: str
    policy_version: str
    state_digest: str
    evidence_refs: list[EvidenceRef] = field(default_factory=list)


@dataclass(frozen=True)
class VerificationResult:
    verification_id: str
    run_id: str
    status: VerificationStatus
    checks: tuple[dict[str, Any], ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()
    verifier_version: str = ""


@dataclass(frozen=True)
class Event:
    event_id: str
    run_id: str
    event_type: str
    timestamp: datetime
    sequence: int
    step_id: str | None = None
    attempt_id: str | None = None
    worker_id: str | None = None
    correlation_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineeringRun:
    run_id: str
    objective: str
    repository_id: str
    base_revision: str
    acceptance_criteria: tuple[str, ...]
    policy_id: str
    policy_version: str
    budget_id: str
    state: RunState = RunState.CREATED
    created_by: str = ""
    workspace_id: str | None = None
    current_step_id: str | None = None
    final_disposition: FinalDisposition | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    steps: list[Step] = field(default_factory=list)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    verification_results: list[VerificationResult] = field(default_factory=list)
