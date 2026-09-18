from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Callable

from .contracts import (
    ImprovementProposal,
    PromotionDecision,
    ProposalState,
    ProtectedSurface,
    SelfImprovementError,
)


class SelfImprovementStore:
    """Append-only durable proposal lifecycle journal."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = RLock()
        self._sequence = 1
        self._state: dict[str, tuple[ProposalState, int]] = {}
        self._load()

    def record(self, proposal_id: str, state: ProposalState, sequence: int) -> None:
        with self._lock:
            current = self._state.get(proposal_id)
            if current and sequence <= current[1]:
                raise SelfImprovementError("proposal journal sequence must increase")
            record = {
                "proposal_id": proposal_id,
                "state": state.value,
                "sequence": sequence,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._state[proposal_id] = (state, sequence)
            self._sequence += 1

    def state(self, proposal_id: str) -> ProposalState | None:
        current = self._state.get(proposal_id)
        return current[0] if current else None

    def _load(self) -> None:
        if not self._path.exists():
            return
        expected = 1
        with self._path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("sequence") != expected:
                    raise SelfImprovementError(f"invalid self-improvement journal at line {line_no}")
                self._state[record["proposal_id"]] = (
                    ProposalState(record["state"]),
                    record["sequence"],
                )
                expected += 1
        self._sequence = expected


@dataclass(frozen=True)
class SelfImprovementEngine:
    store: SelfImprovementStore

    # These paths are authority/security surfaces. A proposal touching one is
    # rejected before any isolated branch/test/verification work is authorized.
    PROTECTED_PREFIXES = (
        "src/vajra/policy/",
        "src/vajra/security/",
        "src/vajra/sandbox/",
        "src/vajra/verification/",
        "src/vajra/execution/broker.py",
        "src/vajra/runtime/",
        "src/vajra/domain/",
        "src/vajra/hardening/",
        "src/vajra/autonomy/",
        "src/vajra/control_plane/",
        "src/vajra/self_improvement/",
    )

    PROTECTED_NAMES = frozenset({
        "src/vajra/control/transition.py",
        "src/vajra/control/completion.py",
        "src/vajra/worker/protocol.py",
    })

    ALLOWED_AREAS = frozenset({
        "routing_heuristics",
        "recovery_heuristics",
        "context_ranking",
        "failure_classification",
        "memory_strategies",
        "scheduling_heuristics",
        "worker_selection",
    })

    def propose(self, proposal: ImprovementProposal) -> None:
        self._validate_scope(proposal)
        if self.store.state(proposal.proposal_id) is not None:
            raise SelfImprovementError("proposal already exists")
        self.store.record(proposal.proposal_id, ProposalState.PROPOSED, 1)

    def isolate(
        self,
        proposal: ImprovementProposal,
        create_branch: Callable[[str, str], None],
    ) -> None:
        self._require(proposal, ProposalState.PROPOSED)
        self._validate_scope(proposal)
        branch = f"vajra-improvement/{proposal.proposal_id}"
        create_branch(branch, proposal.base_revision)
        self.store.record(proposal.proposal_id, ProposalState.ISOLATED, 2)

    def test(
        self,
        proposal: ImprovementProposal,
        run_tests: Callable[[str], bool],
    ) -> None:
        self._require(proposal, ProposalState.ISOLATED)
        if not run_tests(proposal.proposed_revision):
            raise SelfImprovementError("self-improvement tests failed")
        self.store.record(proposal.proposal_id, ProposalState.TESTED, 3)

    def verify(
        self,
        proposal: ImprovementProposal,
        verify_revision: Callable[[str], bool],
    ) -> None:
        self._require(proposal, ProposalState.TESTED)
        if not verify_revision(proposal.proposed_revision):
            raise SelfImprovementError("independent verification failed")
        self.store.record(proposal.proposal_id, ProposalState.VERIFIED, 4)

    def security_verify(
        self,
        proposal: ImprovementProposal,
        verify_security: Callable[[str], bool],
    ) -> None:
        self._require(proposal, ProposalState.VERIFIED)
        if not verify_security(proposal.proposed_revision):
            raise SelfImprovementError("security verification failed")
        self.store.record(proposal.proposal_id, ProposalState.SECURITY_VERIFIED, 5)

    def request_human_approval(self, proposal: ImprovementProposal) -> None:
        self._require(proposal, ProposalState.SECURITY_VERIFIED)
        self.store.record(proposal.proposal_id, ProposalState.AWAITING_HUMAN, 6)

    def promote(
        self,
        proposal: ImprovementProposal,
        decision: PromotionDecision,
        promote_revision: Callable[[str], None],
    ) -> None:
        self._require(proposal, ProposalState.AWAITING_HUMAN)
        if decision.proposal_id != proposal.proposal_id:
            raise SelfImprovementError("promotion decision does not match proposal")
        # The engine only accepts an explicit human decision object. It has no
        # path to manufacture approval or invoke promotion autonomously.
        promote_revision(proposal.proposed_revision)
        self.store.record(proposal.proposal_id, ProposalState.APPROVED, 7)
        self.store.record(proposal.proposal_id, ProposalState.PROMOTED, 8)

    def reject(self, proposal: ImprovementProposal) -> None:
        state = self.store.state(proposal.proposal_id)
        if state is None or state is ProposalState.PROMOTED:
            raise SelfImprovementError("proposal cannot be rejected in its current state")
        self.store.record(proposal.proposal_id, ProposalState.REJECTED, 9)

    def _validate_scope(self, proposal: ImprovementProposal) -> None:
        if proposal.area.value not in self.ALLOWED_AREAS:
            raise SelfImprovementError("proposal area is not eligible for controlled self-improvement")
        for raw_path in proposal.changed_paths:
            path = raw_path.replace("\\", "/").lstrip("./")
            if path.startswith("/") or ".." in path.split("/"):
                raise SelfImprovementError("proposal contains unsafe path")
            if path in self.PROTECTED_NAMES or any(path.startswith(prefix) for prefix in self.PROTECTED_PREFIXES):
                raise SelfImprovementError(
                    f"proposal attempts to modify protected authority surface: {path}"
                )

    def _require(self, proposal: ImprovementProposal, expected: ProposalState) -> None:
        if self.store.state(proposal.proposal_id) is not expected:
            raise SelfImprovementError(
                f"proposal must be in {expected.value} state"
            )
