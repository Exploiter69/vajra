from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from vajra.domain.models import EvidenceRef, VerificationResult


@dataclass(frozen=True)
class VerificationEvidence:
    """
    Structured evidence produced from one verification result.

    The evidence is deterministic for the supplied verification observation
    except for the explicitly supplied timestamp and environment.
    """

    evidence_ref: EvidenceRef
    check_id: str
    command: tuple[str, ...]
    status: str
    exit_code: int | None
    output_reference: str
    environment: dict[str, str]
    timestamp: str
    evidence_digest: str


class VerificationEvidenceBuilder:
    """
    Builds structured, content-addressed verification evidence.

    This component does not execute commands, authorize operations, or
    persist evidence.
    """

    VERSION = "verification-evidence-v0"

    def build(
        self,
        result: VerificationResult,
        *,
        check_id: str,
        command: tuple[str, ...],
        exit_code: int | None,
        output_reference: str,
        environment: dict[str, str] | None = None,
        timestamp: str | None = None,
    ) -> VerificationEvidence:
        if not check_id:
            raise ValueError("check_id must not be empty")

        if not command or not all(
            isinstance(argument, str) and argument
            for argument in command
        ):
            raise ValueError("command must contain non-empty strings")

        if not output_reference:
            raise ValueError("output_reference must not be empty")

        effective_environment = dict(environment or {})

        effective_timestamp = timestamp or datetime.now(
            timezone.utc
        ).isoformat()

        payload: dict[str, Any] = {
            "check_id": check_id,
            "command": list(command),
            "status": result.status.value,
            "exit_code": exit_code,
            "output_reference": output_reference,
            "environment": effective_environment,
            "timestamp": effective_timestamp,
            "verification_id": result.verification_id,
            "run_id": result.run_id,
            "verifier_version": result.verifier_version,
            "checks": list(result.checks),
        }

        serialized = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")

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
            environment=effective_environment,
            timestamp=effective_timestamp,
            evidence_digest=digest,
        )
