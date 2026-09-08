from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from vajra.domain.models import EvidenceRef
from vajra.execution.contracts import ExecutionResult


@dataclass(frozen=True)
class ExecutionEvidence:
    """
    Normalized evidence derived from one execution result.

    This object is intentionally not a persistence mechanism. The caller
    decides where and when the evidence is durably recorded.
    """

    evidence_ref: EvidenceRef
    status: str
    operation: str
    payload: dict[str, object]


class ExecutionEvidenceNormalizer:
    """
    Converts transient execution results into deterministic evidence.

    Evidence identity is content-derived so repeated normalization of the
    same result produces the same digest.
    """

    def normalize(
        self,
        result: ExecutionResult,
        *,
        evidence_id: str,
        location: str,
    ) -> ExecutionEvidence:
        if not evidence_id:
            raise ValueError("evidence_id must not be empty")

        if not location:
            raise ValueError("location must not be empty")

        payload: dict[str, object] = {
            "operation": result.operation,
            "status": result.status.value,
            "output": result.output,
            "errors": list(result.errors),
        }

        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")

        digest = hashlib.sha256(serialized).hexdigest()

        evidence_ref = EvidenceRef(
            evidence_id=evidence_id,
            kind="execution_result",
            location=location,
            digest=digest,
        )

        return ExecutionEvidence(
            evidence_ref=evidence_ref,
            status=result.status.value,
            operation=result.operation,
            payload=payload,
        )
