from pathlib import Path

import pytest

from vajra.self_improvement import (
    ImprovementArea,
    ImprovementProposal,
    PromotionDecision,
    ProposalState,
    SelfImprovementEngine,
    SelfImprovementError,
    SelfImprovementStore,
)


def proposal(paths=("src/vajra/routing/router.py",)):
    return ImprovementProposal(
        "p1",
        "improve routing",
        ImprovementArea.ROUTING_HEURISTICS,
        "base",
        "candidate",
        paths,
        "reduce unnecessary model switches",
    )


def test_proposal_is_scoped_and_durable(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    engine.propose(proposal())
    assert engine.store.state("p1") is ProposalState.PROPOSED
    resumed = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    assert resumed.store.state("p1") is ProposalState.PROPOSED


def test_protected_authority_surfaces_are_immutable(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    for path in (
        "src/vajra/policy/authority.py",
        "src/vajra/security/foo.py",
        "src/vajra/sandbox/backend.py",
        "src/vajra/verification/contracts.py",
        "src/vajra/execution/broker.py",
        "src/vajra/runtime/run_manager.py",
        "src/vajra/domain/models.py",
        "src/vajra/hardening/security.py",
    ):
        with pytest.raises(SelfImprovementError, match="protected"):
            engine.propose(proposal((path,)))


def test_unsafe_paths_are_rejected(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    for path in ("../outside.py", "/absolute.py", "src/vajra/../policy/x.py"):
        with pytest.raises(SelfImprovementError):
            engine.propose(proposal((path,)))


def test_full_lifecycle_requires_isolation_verification_security_and_human(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    events = []
    p = proposal()
    engine.propose(p)
    engine.isolate(p, lambda branch, base: events.append(("branch", branch, base)))
    engine.test(p, lambda revision: events.append(("test", revision)) or True)
    engine.verify(p, lambda revision: events.append(("verify", revision)) or True)
    engine.security_verify(p, lambda revision: events.append(("security", revision)) or True)
    engine.request_human_approval(p)
    engine.promote(p, PromotionDecision("p1", "human", "explicit-approval"), lambda rev: events.append(("promote", rev)))
    assert engine.store.state("p1") is ProposalState.PROMOTED
    assert [item[0] for item in events] == ["branch", "test", "verify", "security", "promote"]


def test_tests_or_verification_failure_cannot_promote(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    p = proposal()
    engine.propose(p)
    engine.isolate(p, lambda *_: None)
    with pytest.raises(SelfImprovementError):
        engine.test(p, lambda _: False)
    assert engine.store.state("p1") is ProposalState.ISOLATED
    with pytest.raises(SelfImprovementError):
        engine.promote(p, PromotionDecision("p1", "human", "approval"), lambda _: None)


def test_independent_verification_failure_cannot_promote(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    p = proposal()
    engine.propose(p)
    engine.isolate(p, lambda *_: None)
    engine.test(p, lambda _: True)
    with pytest.raises(SelfImprovementError):
        engine.verify(p, lambda _: False)
    assert engine.store.state("p1") is ProposalState.TESTED


def test_security_failure_cannot_promote(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    p = proposal()
    engine.propose(p)
    engine.isolate(p, lambda *_: None)
    engine.test(p, lambda _: True)
    engine.verify(p, lambda _: True)
    with pytest.raises(SelfImprovementError):
        engine.security_verify(p, lambda _: False)
    assert engine.store.state("p1") is ProposalState.VERIFIED


def test_promotion_requires_matching_explicit_human_decision(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    p = proposal()
    engine.propose(p)
    engine.isolate(p, lambda *_: None)
    engine.test(p, lambda _: True)
    engine.verify(p, lambda _: True)
    engine.security_verify(p, lambda _: True)
    engine.request_human_approval(p)
    with pytest.raises(SelfImprovementError):
        engine.promote(p, PromotionDecision("other", "human", "approval"), lambda _: None)
    assert engine.store.state("p1") is ProposalState.AWAITING_HUMAN


def test_rejection_is_durable(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    p = proposal()
    engine.propose(p)
    engine.reject(p)
    resumed = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    assert resumed.store.state("p1") is ProposalState.REJECTED


def test_runtime_control_and_self_improvement_surfaces_are_protected(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    for path in (
        "src/vajra/autonomy/advanced.py",
        "src/vajra/control_plane/plane.py",
        "src/vajra/self_improvement/engine.py",
        "src/vajra/runtime/lease.py",
    ):
        with pytest.raises(SelfImprovementError, match="protected"):
            engine.propose(proposal((path,)))


def test_promotion_callback_is_not_reached_without_human_gate(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    p = proposal()
    engine.propose(p)
    engine.isolate(p, lambda *_: None)
    engine.test(p, lambda _: True)
    engine.verify(p, lambda _: True)
    engine.security_verify(p, lambda _: True)
    reached = []
    with pytest.raises(SelfImprovementError):
        engine.promote(p, PromotionDecision("p1", "human", "approval"), lambda _: reached.append(True))
    assert reached == []
    assert engine.store.state("p1") is ProposalState.SECURITY_VERIFIED


def test_proposal_cannot_be_redefined_or_promoted_twice(tmp_path: Path):
    engine = SelfImprovementEngine(SelfImprovementStore(tmp_path / "journal.jsonl"))
    p = proposal()
    engine.propose(p)
    with pytest.raises(SelfImprovementError):
        engine.propose(p)
    engine.isolate(p, lambda *_: None)
    engine.test(p, lambda _: True)
    engine.verify(p, lambda _: True)
    engine.security_verify(p, lambda _: True)
    engine.request_human_approval(p)
    engine.promote(p, PromotionDecision("p1", "human", "approval"), lambda _: None)
    with pytest.raises(SelfImprovementError):
        engine.promote(p, PromotionDecision("p1", "human", "approval"), lambda _: None)


def test_journal_tampering_is_detected(tmp_path: Path):
    path = tmp_path / "journal.jsonl"
    engine = SelfImprovementEngine(SelfImprovementStore(path))
    engine.propose(proposal())
    path.write_text(path.read_text(encoding="utf-8") + '{" + "\"sequence\"" + ":99," + "\"proposal_id\"" + ":\"evil\"," + "\"state\"" + ":\"PROPOSED\"}\\n", encoding="utf-8")
    with pytest.raises(SelfImprovementError, match="journal"):
        SelfImprovementStore(path)
