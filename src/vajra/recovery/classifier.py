from __future__ import annotations

from vajra.recovery.contracts import (
    Failure,
    FailureCategory,
    FailureObservation,
)


class FailureClassifier:
    """
    Deterministic failure classifier.

    Classification is informational only. It does not schedule retries,
    mutate a Run, or invoke external systems.
    """

    def classify(self, observation: FailureObservation) -> Failure:
        category = self._classify_category(observation)

        return Failure(
            failure_id=observation.failure_id,
            run_id=observation.run_id,
            step_id=observation.step_id,
            attempt_id=observation.attempt_id,
            category=category,
            message=observation.message,
            details=observation.details,
        )

    @staticmethod
    def _classify_category(
        observation: FailureObservation,
    ) -> FailureCategory:
        source = observation.source.strip().lower()

        source_mapping = {
            "model": FailureCategory.MODEL_FAILURE,
            "tool": FailureCategory.TOOL_FAILURE,
            "command": FailureCategory.COMMAND_FAILURE,
            "test": FailureCategory.TEST_FAILURE,
            "policy": FailureCategory.POLICY_DENIAL,
            "resource": FailureCategory.RESOURCE_EXHAUSTION,
            "timeout": FailureCategory.TIMEOUT,
            "worker": FailureCategory.WORKER_LOSS,
            "network": FailureCategory.NETWORK_FAILURE,
            "state": FailureCategory.STATE_DIVERGENCE,
            "sandbox": FailureCategory.SANDBOX_FAILURE,
            "no_progress": FailureCategory.NO_PROGRESS,
        }

        return source_mapping.get(source, FailureCategory.UNKNOWN)
