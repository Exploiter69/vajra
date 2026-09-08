from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from vajra.recovery.contracts import Failure, FailureCategory


@dataclass(frozen=True)
class ProgressObservation:
    """
    Deterministic observation of engineering progress.

    Fields describe externally observable state. The detector does not inspect
    or mutate the workspace itself; callers supply the observations.
    """

    run_id: str
    step_id: str
    attempt_id: str
    state_digest: str | None = None
    git_revision: str | None = None
    patch_digest: str | None = None
    test_signature: str | None = None
    error_signature: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "step_id",
            "attempt_id",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class ProgressFingerprint:
    """
    Stable fingerprint of one externally supplied progress observation.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("fingerprint must not be empty")


@dataclass(frozen=True)
class ProgressAssessment:
    """
    Result of comparing one observation with prior observations.
    """

    fingerprint: ProgressFingerprint
    repetition_count: int
    no_progress: bool


class NoProgressDetector:
    """
    Deterministic detector for repeated engineering state.

    The detector only records supplied fingerprints in memory. It does not
    execute commands, inspect Git, mutate Run state, or choose recovery.
    """

    def __init__(self, repetition_threshold: int = 3) -> None:
        if repetition_threshold < 2:
            raise ValueError("repetition_threshold must be at least 2")

        self._threshold = repetition_threshold
        self._counts: dict[tuple[str, str, str], int] = {}

    @staticmethod
    def fingerprint(
        observation: ProgressObservation,
    ) -> ProgressFingerprint:
        payload = {
            "run_id": observation.run_id,
            "step_id": observation.step_id,
            "attempt_id": observation.attempt_id,
            "state_digest": observation.state_digest,
            "git_revision": observation.git_revision,
            "patch_digest": observation.patch_digest,
            "test_signature": observation.test_signature,
            "error_signature": observation.error_signature,
        }

        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return ProgressFingerprint(
            hashlib.sha256(serialized).hexdigest()
        )

    def observe(
        self,
        observation: ProgressObservation,
    ) -> ProgressAssessment:
        fingerprint = self.fingerprint(observation)
        key = (
            observation.run_id,
            observation.step_id,
            fingerprint.value,
        )

        count = self._counts.get(key, 0) + 1
        self._counts[key] = count

        return ProgressAssessment(
            fingerprint=fingerprint,
            repetition_count=count,
            no_progress=count >= self._threshold,
        )

    def failure(
        self,
        observation: ProgressObservation,
        *,
        failure_id: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> Failure | None:
        assessment = self.observe(observation)

        if not assessment.no_progress:
            return None

        effective_details = dict(details or {})
        effective_details.update(
            {
                "fingerprint": assessment.fingerprint.value,
                "repetition_count": assessment.repetition_count,
                "threshold": self._threshold,
            }
        )

        return Failure(
            failure_id=failure_id,
            run_id=observation.run_id,
            step_id=observation.step_id,
            attempt_id=observation.attempt_id,
            category=FailureCategory.NO_PROGRESS,
            message=message,
            details=effective_details,
        )

    def reset(
        self,
        *,
        run_id: str,
        step_id: str,
    ) -> None:
        """
        Forget observations for one run/step.

        Callers should reset when a genuinely new engineering state is
        established, such as a new strategy or restored checkpoint.
        """
        keys = [
            key
            for key in self._counts
            if key[0] == run_id and key[1] == step_id
        ]

        for key in keys:
            del self._counts[key]
