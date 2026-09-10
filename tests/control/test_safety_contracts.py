from datetime import datetime, timezone

import pytest

from vajra.control.contracts import (
    AcceptanceCriteria,
    AcceptancePredicate,
    CompletionPredicate,
    DivergenceClass,
    EvidenceLink,
    OperationIdentity,
    PredicateResult,
    ProgressPredicate,
    ProgressRecord,
    ReconciliationDisposition,
    ReconciliationReport,
    WorktreeContract,
)


@pytest.fixture
def operation() -> OperationIdentity:
    return OperationIdentity(
        operation_id="op-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        intent_id="intent-1",
        operation_type="write_file",
        parameters_digest="sha256:params",
        target_resource="workspace:file.py",
        fencing_token=7,
        idempotency_key="idem-1",
    )


def test_acceptance_predicate_requires_identity_and_description() -> None:
    predicate = AcceptancePredicate("accept-1", "1", "tests pass")
    assert predicate.predicate_id == "accept-1"

    with pytest.raises(ValueError):
        AcceptancePredicate("", "1", "tests pass")

    with pytest.raises(ValueError):
        AcceptancePredicate("accept-1", "", "tests pass")

    with pytest.raises(ValueError):
        AcceptancePredicate("accept-1", "1", "")


def test_acceptance_criteria_requires_predicate() -> None:
    with pytest.raises(ValueError):
        AcceptanceCriteria("criteria-1", "1", "sha256:objective", ())


def test_acceptance_criteria_reports_frozen_state() -> None:
    criteria = AcceptanceCriteria(
        "criteria-1",
        "1",
        "sha256:objective",
        (AcceptancePredicate("accept-1", "1", "tests pass"),),
    )
    assert not criteria.frozen
    frozen = AcceptanceCriteria(
        "criteria-1",
        "1",
        "sha256:objective",
        (AcceptancePredicate("accept-1", "1", "tests pass"),),
        frozen_at=datetime.now(timezone.utc),
    )
    assert frozen.frozen


def test_progress_and_completion_predicates_require_identity() -> None:
    progress = ProgressPredicate("progress-1", "1", "artifact changes")
    completion = CompletionPredicate("complete-1", "1", "all acceptance predicates true")
    assert progress.version == "1"
    assert completion.description.startswith("all")

    with pytest.raises(ValueError):
        CompletionPredicate("", "1", "complete")


def test_operation_identity_rejects_negative_fencing_token() -> None:
    with pytest.raises(ValueError):
        OperationIdentity(
            "op-1", "run-1", "step-1", "attempt-1", "intent-1",
            "write", "sha256:p", "workspace:file", -1, "idem-1"
        )


def test_operation_identity_requires_all_authority_fields() -> None:
    with pytest.raises(ValueError):
        OperationIdentity(
            "op-1", "run-1", "step-1", "attempt-1", "intent-1",
            "", "sha256:p", "workspace:file", 1, "idem-1"
        )


def test_evidence_link_requires_complete_chain() -> None:
    link = EvidenceLink(
        "evidence-1",
        "intent-1",
        "op-1",
        "sha256:artifact",
        "verification-1",
        "sha256:evidence",
    )
    assert link.operation_id == "op-1"

    with pytest.raises(ValueError):
        EvidenceLink("", "intent-1", "op-1", "a", "v", "e")


def test_progress_record_binds_operation_to_intent(operation: OperationIdentity) -> None:
    record = ProgressRecord(
        "progress-1",
        "run-1",
        "step-1",
        "attempt-1",
        "intent-1",
        operation,
        "sha256:before",
        "sha256:after",
        ("artifact-1",),
        ("verification-1",),
        "progress-1",
        "1",
        PredicateResult.TRUE,
        "novelty-1",
    )
    assert record.predicate_result is PredicateResult.TRUE


def test_progress_record_rejects_mismatched_intent(operation: OperationIdentity) -> None:
    with pytest.raises(ValueError):
        ProgressRecord(
            "progress-1", "run-1", "step-1", "attempt-1", "different-intent",
            operation, "before", "after", (), (), "predicate", "1",
            PredicateResult.INCONCLUSIVE, "novelty"
        )


def test_progress_record_accepts_evidence_links(operation: OperationIdentity) -> None:
    record = ProgressRecord(
        "progress-1", "run-1", "step-1", "attempt-1", "intent-1", operation,
        "before", "after", ("artifact-1",), ("verification-1",),
        "predicate", "1", PredicateResult.TRUE, "novelty",
        evidence_links=(EvidenceLink("e-1", "intent-1", "op-1", "artifact", "v-1", "evidence"),),
    )
    assert len(record.evidence_links) == 1


def test_reconciliation_report_consistent_requires_no_divergence() -> None:
    report = ReconciliationReport(
        "report-1", "run-1", datetime.now(timezone.utc), "state", "workspace-1",
        "CLEAN", "abc123", "git-status", "filesystem", None, "NONE",
        "VERIFIED", "WITHIN_BUDGET", {}, DivergenceClass.NONE, "NONE", "fresh",
        ReconciliationDisposition.CONSISTENT,
    )
    assert report.disposition is ReconciliationDisposition.CONSISTENT


def test_reconciliation_report_rejects_divergence_marked_consistent() -> None:
    with pytest.raises(ValueError):
        ReconciliationReport(
            "report-1", "run-1", datetime.now(timezone.utc), "state", "workspace-1",
            "DIRTY", "abc123", "git-status", "filesystem", None, "NONE",
            "VERIFIED", "WITHIN_BUDGET", {}, DivergenceClass.STATE_DIVERGENCE,
            "HIGH", "fresh", ReconciliationDisposition.CONSISTENT,
        )


def test_reconciliation_report_requires_consistent_for_none_divergence() -> None:
    with pytest.raises(ValueError):
        ReconciliationReport(
            "report-1", "run-1", datetime.now(timezone.utc), "state", "workspace-1",
            "CLEAN", "abc123", "git-status", "filesystem", None, "NONE",
            "VERIFIED", "WITHIN_BUDGET", {}, DivergenceClass.NONE,
            "NONE", "fresh", ReconciliationDisposition.REVERIFY,
        )


def test_worktree_contract_requires_clean_creation() -> None:
    contract = WorktreeContract(
        "workspace-1", "run-1", "repo-1", "abc123", "/tmp/worktree",
        "owner-1", True, "sha256:status",
    )
    assert contract.clean_at_creation

    with pytest.raises(ValueError):
        WorktreeContract(
            "workspace-1", "run-1", "repo-1", "abc123", "/tmp/worktree",
            "owner-1", False, "sha256:status",
        )


def test_frozen_dataclasses_prevent_mutation(operation: OperationIdentity) -> None:
    with pytest.raises(AttributeError):
        operation.operation_id = "changed"  # type: ignore[misc]


def test_enum_values_are_stable() -> None:
    assert PredicateResult.TRUE.value == "TRUE"
    assert DivergenceClass.STATE_DIVERGENCE.value == "STATE_DIVERGENCE"
    assert ReconciliationDisposition.WAITING_HUMAN.value == "WAITING_HUMAN"
