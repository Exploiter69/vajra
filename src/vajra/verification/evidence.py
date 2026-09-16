from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from vajra.domain.models import EvidenceRef, VerificationResult


@dataclass(frozen=True)
class VerificationEvidence:
    """Structured, content-addressed evidence for one verification observation."""

    evidence_ref: EvidenceRef
    check_id: str
    command: tuple[str, ...]
    status: str
    exit_code: int | None
    output_reference: str
    output_digest: str | None
    environment: dict[str, str]
    timestamp: str
    evidence_digest: str


class VerificationEvidenceBuilder:
    """Build verification evidence without executing or authorizing operations."""

    VERSION = "verification-evidence-v1"

    def build(
        self,
        result: VerificationResult,
        *,
        check_id: str,
        command: tuple[str, ...],
        exit_code: int | None,
        output_reference: str,
        output: str | bytes | None = None,
        environment: dict[str, str] | None = None,
        timestamp: str | None = None,
    ) -> VerificationEvidence:
        if not check_id:
            raise ValueError("check_id must not be empty")
        if not command or not all(isinstance(argument, str) and argument for argument in command):
            raise ValueError("command must contain non-empty strings")
        if not output_reference:
            raise ValueError("output_reference must not be empty")

        effective_environment = dict(environment or {})
        effective_timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        output_digest = None
        if output is not None:
            output_bytes = output if isinstance(output, bytes) else output.encode("utf-8")
            output_digest = hashlib.sha256(output_bytes).hexdigest()

        payload: dict[str, Any] = {
            "check_id": check_id,
            "command": list(command),
            "status": result.status.value,
            "exit_code": exit_code,
            "output_reference": output_reference,
            "output_digest": output_digest,
            "environment": effective_environment,
            "timestamp": effective_timestamp,
            "verification_id": result.verification_id,
            "run_id": result.run_id,
            "verifier_version": result.verifier_version,
            "checks": list(result.checks),
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        digest = hashlib.sha256(serialized).hexdigest()
        evidence_ref = EvidenceRef(
            evidence_id=f"{check_id}-evidence",
            kind="verification_result",
            location=output_reference,
            digest=digest,
        )
        return VerificationEvidence(
            evidence_ref=evidence_ref,
            check_id=check_id,
            command=command,
            status=result.status.value,
            exit_code=exit_code,
            output_reference=output_reference,
            output_digest=output_digest,
            environment=effective_environment,
            timestamp=effective_timestamp,
            evidence_digest=digest,
        )
