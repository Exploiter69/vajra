from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vajra.domain.models import ArtifactRef, EvidenceRef


@dataclass(frozen=True)
class WorkerJob:
    """Bounded work assignment issued by VAJRA to a disposable worker."""

    run_id: str
    step_id: str
    attempt_id: str
    repository_revision: str
    workspace_contract: dict[str, Any]
    context_bundle: dict[str, Any]
    allowed_capabilities: tuple[str, ...]
    budget: dict[str, Any]
    deadline: str
    expected_output_schema: dict[str, Any]
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "step_id",
            "attempt_id",
            "repository_revision",
            "deadline",
        ):
            if not getattr(self, field_name):
                raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class WorkerResult:
    """Worker-reported outcome.

    Workers report results; they do not own or mutate canonical Run state.
    """

    status: str
    correlation_id: str | None = None
    structured_result: dict[str, Any] | None = None
    artifacts: tuple[ArtifactRef, ...] = ()
    logs: tuple[str, ...] = ()
    usage: dict[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if not self.status:
            raise ValueError("status must not be empty")
