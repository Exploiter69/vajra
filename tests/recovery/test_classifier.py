import pytest

from vajra.recovery import (
    FailureCategory,
    FailureClassifier,
    FailureObservation,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("model", FailureCategory.MODEL_FAILURE),
        ("tool", FailureCategory.TOOL_FAILURE),
        ("command", FailureCategory.COMMAND_FAILURE),
        ("test", FailureCategory.TEST_FAILURE),
        ("policy", FailureCategory.POLICY_DENIAL),
        ("resource", FailureCategory.RESOURCE_EXHAUSTION),
        ("timeout", FailureCategory.TIMEOUT),
        ("worker", FailureCategory.WORKER_LOSS),
        ("network", FailureCategory.NETWORK_FAILURE),
        ("state", FailureCategory.STATE_DIVERGENCE),
        ("sandbox", FailureCategory.SANDBOX_FAILURE),
        ("no_progress", FailureCategory.NO_PROGRESS),
    ],
)
def test_classifier_maps_v0_failure_categories(
    source: str,
    expected: FailureCategory,
) -> None:
    observation = FailureObservation(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        source=source,
        message="failure observed",
    )

    failure = FailureClassifier().classify(observation)

    assert failure.category is expected


def test_unknown_source_becomes_unknown() -> None:
    observation = FailureObservation(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        source="something-new",
        message="unrecognized failure",
    )

    failure = FailureClassifier().classify(observation)

    assert failure.category is FailureCategory.UNKNOWN


@pytest.mark.parametrize(
    "field_name",
    [
        "failure_id",
        "run_id",
        "step_id",
        "attempt_id",
        "source",
        "message",
    ],
)
def test_observation_requires_identity_and_source(
    field_name: str,
) -> None:
    values = {
        "failure_id": "failure-1",
        "run_id": "run-1",
        "step_id": "step-1",
        "attempt_id": "attempt-1",
        "source": "command",
        "message": "failure",
    }
    values[field_name] = ""

    with pytest.raises(ValueError):
        FailureObservation(**values)


def test_failure_preserves_observation_details() -> None:
    details = {"return_code": 1}

    observation = FailureObservation(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        source="command",
        message="command failed",
        details=details,
    )

    failure = FailureClassifier().classify(observation)

    assert failure.details == details
    assert failure.failure_id == "failure-1"
    assert failure.run_id == "run-1"
    assert failure.step_id == "step-1"
    assert failure.attempt_id == "attempt-1"
    assert failure.message == "command failed"


def test_classifier_is_deterministic() -> None:
    observation = FailureObservation(
        failure_id="failure-1",
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        source="TEST",
        message="tests failed",
    )

    classifier = FailureClassifier()

    assert classifier.classify(observation) == classifier.classify(observation)
