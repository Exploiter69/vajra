from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SelfImprovementError(ValueError):
    pass


class ProposalState(str, Enum):
    PROPOSED = "PROPOSED"
    ISOLATED = "ISOLATED"
    TESTED = "TESTED"
    VERIFIED = "VERIFIED"
    SECURITY_VERIFIED = "SECURITY_VERIFIED"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    APPROVED = "APPROVED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class ImprovementArea(str, Enum):
    ROUTING_HEURISTICS = "routing_heuristics"
    RECOVERY_HEURISTICS = "recovery_heuristics"
    CONTEXT_RANKING = "context_ranking"
    FAILURE_CLASSIFICATION = "failure_classification"
    MEMORY_STRATEGIES = "memory_strategies"
    SCHEDULING_HEURISTICS = "scheduling_heuristics"
    WORKER_SELECTION = "worker_selection"


class ProtectedSurface(str, Enum):
    POLICY_AUTHORITY = "policy_authority"
    SECURITY_BOUNDARY = "security_boundary"
    SANDBOX_PRIMITIVES = "sandbox_primitives"
    VERIFICATION_AUTHORITY = "verification_authority"
    WORKER_FENCING = "worker_fencing"
    CANONICAL_STATE = "canonical_state"
    HUMAN_OVERRIDE = "human_override"
    AUDIT_EVENT_INTEGRITY = "audit_event_integrity"
    EXECUTION_BROKER_BOUNDARY = "execution_broker_boundary"


@dataclass(frozen=True)
class ImprovementProposal:
    proposal_id: str
    objective: str
    area: ImprovementArea
    base_revision: str
    proposed_revision: str
    changed_paths: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.proposal_id,
                self.objective,
                self.base_revision,
                self.proposed_revision,
                self.rationale,
            )
        ):
            raise SelfImprovementError("proposal identity, revisions, objective, and rationale are required")
        if not self.changed_paths:
            raise SelfImprovementError("self-improvement proposal must declare changed paths")
        if self.base_revision == self.proposed_revision:
            raise SelfImprovementError("self-improvement proposal must change revision")


@dataclass(frozen=True)
class PromotionDecision:
    proposal_id: str
    approver: str
    approval_token: str

    def __post_init__(self) -> None:
        if not all((self.proposal_id.strip(), self.approver.strip(), self.approval_token.strip())):
            raise SelfImprovementError("promotion requires proposal, approver, and approval token")
