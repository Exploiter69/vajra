from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class PredicateResult(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    INCONCLUSIVE = "INCONCLUSIVE"


class DivergenceClass(str, Enum):
    NONE = "NONE"
    RECOVERABLE = "RECOVERABLE"
    REVERIFY = "REVERIFY"
    STATE_DIVERGENCE = "STATE_DIVERGENCE"
    OWNERSHIP_DIVERGENCE = "OWNERSHIP_DIVERGENCE"
    VERIFICATION_DIVERGENCE = "VERIFICATION_DIVERGENCE"
    BUDGET_DIVERGENCE = "BUDGET_DIVERGENCE"
    UNKNOWN = "UNKNOWN"


class ReconciliationDisposition(str, Enum):
    CONSISTENT = "CONSISTENT"
    RECOVERABLE = "RECOVERABLE"
    REVERIFY = "REVERIFY"
    RECOVERING = "RECOVERING"
    WAITING_HUMAN = "WAITING_HUMAN"
    ABORT = "ABORT"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_nonempty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class AcceptancePredicate:
    predicate_id: str
    version: str
    description: str
    required_evidence_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty(self.predicate_id, "predicate_id")
        _require_nonempty(self.version, "version")
        _require_nonempty(self.description, "description")


@dataclass(frozen=True)
class AcceptanceCriteria:
    criteria_id: str
    version: str
    objective_digest: str
    predicates: tuple[AcceptancePredicate, ...]
    required_evidence: tuple[str, ...] = ()
    verification_plan_ref: str | None = None
    integrity_digest: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    frozen_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_nonempty(self.criteria_id, "criteria_id")
        _require_nonempty(self.version, "version")
        _require_nonempty(self.objective_digest, "objective_digest")
        if not self.predicates:
            raise ValueError("acceptance criteria must contain at least one predicate")

    @property
    def frozen(self) -> bool:
        return self.frozen_at is not None


@dataclass(frozen=True)
class ProgressPredicate:
    predicate_id: str
    version: str
    description: str
    required_evidence_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_nonempty(self.predicate_id, "predicate_id")
        _require_nonempty(self.version, "version")
        _require_nonempty(self.description, "description")


@dataclass(frozen=True)
class CompletionPredicate:
    predicate_id: str
    version: str
    description: str

    def __post_init__(self) -> None:
        _require_nonempty(self.predicate_id, "predicate_id")
        _require_nonempty(self.version, "version")
        _require_nonempty(self.description, "description")


@dataclass(frozen=True)
class OperationIdentity:
    operation_id: str
    run_id: str
    step_id: str
    attempt_id: str
    intent_id: str
    operation_type: str
    parameters_digest: str
    target_resource: str
    fencing_token: int
    idempotency_key: str

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "run_id",
            "step_id",
            "attempt_id",
            "intent_id",
            "operation_type",
            "parameters_digest",
            "target_resource",
            "idempotency_key",
        ):
            _require_nonempty(getattr(self, name), name)
        if self.fencing_token < 0:
            raise ValueError("fencing_token must not be negative")


@dataclass(frozen=True)
class EvidenceLink:
    evidence_id: str
    intent_id: str
    operation_id: str
    artifact_digest: str
    verification_id: str
    evidence_digest: str

    def __post_init__(self) -> None:
        for name in (
            "evidence_id",
            "intent_id",
            "operation_id",
            "artifact_digest",
            "verification_id",
            "evidence_digest",
        ):
            _require_nonempty(getattr(self, name), name)


@dataclass(frozen=True)
class ProgressRecord:
    progress_id: str
    run_id: str
    step_id: str
    attempt_id: str
    intent_id: str
    operation_identity: OperationIdentity
    pre_state_digest: str
    post_state_digest: str
    artifact_refs: tuple[str, ...]
    verification_refs: tuple[str, ...]
    predicate_id: str
    predicate_version: str
    predicate_result: PredicateResult
    novelty_fingerprint: str
    failure_signature: str | None = None
    evidence_links: tuple[EvidenceLink, ...] = ()
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        for name in (
            "progress_id",
            "run_id",
            "step_id",
            "attempt_id",
            "intent_id",
            "pre_state_digest",
            "post_state_digest",
            "predicate_id",
            "predicate_version",
            "novelty_fingerprint",
        ):
            _require_nonempty(getattr(self, name), name)
        if self.operation_identity.intent_id != self.intent_id:
            raise ValueError("operation identity intent_id does not match progress intent_id")


@dataclass(frozen=True)
class ReconciliationReport:
    report_id: str
    run_id: str
    generated_at: datetime
    durable_state_digest: str
    workspace_id: str
    workspace_state: str
    git_revision: str
    git_status_digest: str
    filesystem_digest: str
    checkpoint_ref: str | None
    active_lease_state: str
    verification_state: str
    budget_state: str
    observed_external_state: dict[str, Any]
    divergence_class: DivergenceClass
    severity: str
    freshness: str
    disposition: ReconciliationDisposition

    def __post_init__(self) -> None:
        for name in (
            "report_id",
            "run_id",
            "durable_state_digest",
            "workspace_id",
            "workspace_state",
            "git_revision",
            "git_status_digest",
            "filesystem_digest",
            "active_lease_state",
            "verification_state",
            "budget_state",
            "severity",
            "freshness",
        ):
            _require_nonempty(getattr(self, name), name)

        if self.divergence_class is DivergenceClass.NONE and self.disposition is not ReconciliationDisposition.CONSISTENT:
            raise ValueError("NONE divergence requires CONSISTENT disposition")
        if self.divergence_class is not DivergenceClass.NONE and self.disposition is ReconciliationDisposition.CONSISTENT:
            raise ValueError("non-NONE divergence cannot have CONSISTENT disposition")


@dataclass(frozen=True)
class WorktreeContract:
    workspace_id: str
    run_id: str
    repository_id: str
    base_revision: str
    path: str
    owner_token: str
    clean_at_creation: bool
    git_status_digest: str

    def __post_init__(self) -> None:
        for name in (
            "workspace_id",
            "run_id",
            "repository_id",
            "base_revision",
            "path",
            "owner_token",
            "git_status_digest",
        ):
            _require_nonempty(getattr(self, name), name)

        if not self.clean_at_creation:
            raise ValueError("worktree must be clean at creation")


__all__ = [
    "AcceptanceCriteria",
    "AcceptancePredicate",
    "CompletionPredicate",
    "DivergenceClass",
    "EvidenceLink",
    "OperationIdentity",
    "PredicateResult",
    "ProgressPredicate",
    "ProgressRecord",
    "ReconciliationDisposition",
    "ReconciliationReport",
    "WorktreeContract",
]
