from __future__ import annotations

from vajra.recovery.contracts import FailureCategory
from vajra.recovery.progress import (
    NoProgressDetector,
    ProgressObservation,
)


def make_observation(
    *,
    attempt_id: str = "attempt-1",
    state_digest: str | None = "state-a",
    git_revision: str | None = "revision-a",
    patch_digest: str | None = "patch-a",
    test_signature: str | None = "tests-a",
    error_signature: str | None = "error-a",
) -> ProgressObservation:
    return ProgressObservation(
        run_id="run-1",
        step_id="step-1",
        attempt_id=attempt_id,
        state_digest=state_digest,
        git_revision=git_revision,
        patch_digest=patch_digest,
        test_signature=test_signature,
        error_signature=error_signature,
    )


def test_identical_observations_have_same_fingerprint() -> None:
    first = make_observation()
    second = make_observation()

    assert (
        NoProgressDetector.fingerprint(first)
        == NoProgressDetector.fingerprint(second)
    )


def test_changed_observation_has_different_fingerprint() -> None:
    first = make_observation()
    second = make_observation(patch_digest="patch-b")

    assert (
        NoProgressDetector.fingerprint(first)
        != NoProgressDetector.fingerprint(second)
    )


def test_detector_counts_repeated_observations() -> None:
    detector = NoProgressDetector(repetition_threshold=3)
    observation = make_observation()

    first = detector.observe(observation)
    second = detector.observe(observation)

    assert first.repetition_count == 1
    assert not first.no_progress
    assert second.repetition_count == 2
    assert not second.no_progress


def test_detector_marks_no_progress_at_threshold() -> None:
    detector = NoProgressDetector(repetition_threshold=3)
    observation = make_observation()

    detector.observe(observation)
    detector.observe(observation)
    assessment = detector.observe(observation)

    assert assessment.repetition_count == 3
    assert assessment.no_progress


def test_failure_is_emitted_only_at_threshold() -> None:
    detector = NoProgressDetector(repetition_threshold=2)
    observation = make_observation()

    assert detector.failure(
        observation,
        failure_id="failure-1",
        message="No progress detected",
    ) is None

    failure = detector.failure(
        observation,
        failure_id="failure-2",
        message="No progress detected",
    )

    assert failure is not None
    assert failure.category is FailureCategory.NO_PROGRESS
    assert failure.details is not None
    assert failure.details["repetition_count"] == 2
    assert failure.details["threshold"] == 2


def test_different_attempts_do_not_share_progress_count() -> None:
    detector = NoProgressDetector(repetition_threshold=2)

    first = make_observation(attempt_id="attempt-1")
    second = make_observation(attempt_id="attempt-2")

    assert not detector.observe(first).no_progress
    assert not detector.observe(second).no_progress


def test_reset_forgets_run_step_observations() -> None:
    detector = NoProgressDetector(repetition_threshold=2)
    observation = make_observation()

    detector.observe(observation)
    detector.reset(run_id="run-1", step_id="step-1")

    assessment = detector.observe(observation)

    assert assessment.repetition_count == 1
    assert not assessment.no_progress


def test_invalid_threshold_is_rejected() -> None:
    try:
        NoProgressDetector(repetition_threshold=1)
    except ValueError as exc:
        assert "at least 2" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
