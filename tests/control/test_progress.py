from datetime import datetime, timezone

from vajra.control.contracts import (
    EvidenceLink,
    OperationIdentity,
    PredicateResult,
    ProgressRecord,
)
from vajra.policy.contracts import Intent
from vajra.control.progress import ProgressTracker


def progress(
    fingerprint: str = "novel-1",
    result: PredicateResult = PredicateResult.TRUE,
) -> ProgressRecord:
    intent = Intent(
        intent_id="intent-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation="write",
    )
    operation = OperationIdentity(
        operation_id="operation-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        intent_id="intent-1",
        operation_type="write",
        parameters_digest="params",
        target_resource="file.txt",
        fencing_token=1,
        idempotency_key="idem-1",
    )
    return ProgressRecord(
        progress_id="progress-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        intent_id=intent.intent_id,
        operation_identity=operation,
        pre_state_digest="before",
        post_state_digest="after",
        artifact_refs=("artifact-1",),
        verification_refs=("verification-1",),
        predicate_id="progress-1",
        predicate_version="1",
        predicate_result=result,
        novelty_fingerprint=fingerprint,
        failure_signature=None,
        evidence_links=(
            EvidenceLink(
                evidence_id="evidence-1",
                intent_id=intent.intent_id,
                operation_id=operation.operation_id,
                artifact_digest="artifact-digest",
                verification_id="verification-1",
                evidence_digest="evidence-digest",
            ),
        ),
        created_at=datetime.now(timezone.utc),
    )


def test_novel_evidence_backed_progress_is_accepted():
    assessment = ProgressTracker().record(progress())

    assert assessment.novel
    assert assessment.accepted
    assert assessment.reason == "novel evidence-backed progress"


def test_duplicate_novelty_is_not_accepted():
    tracker = ProgressTracker()

    first = tracker.record(progress())
    second = tracker.record(progress())

    assert first.accepted
    assert not second.novel
    assert not second.accepted


def test_changed_state_is_detected():
    assert ProgressTracker.changed_state(progress())


def test_failed_progress_predicate_is_not_accepted():
    assessment = ProgressTracker().record(
        progress(result=PredicateResult.FALSE)
    )

    assert assessment.novel
    assert not assessment.accepted
    assert assessment.reason == "progress predicate failed"
