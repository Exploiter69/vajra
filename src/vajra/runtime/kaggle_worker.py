from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


@dataclass(frozen=True)
class KaggleWorkerAdapter:
    """
    Serialization boundary for the disposable Kaggle worker.

    The adapter does not execute inference, mutate Run state, manage leases,
    authorize operations, or perform retries. It only translates the existing
    VAJRA WorkerJob/WorkerResult contracts to and from a JSON wire format.
    """

    protocol_version: str = "vajra-worker-v1"

    def encode_job(self, job: WorkerJob) -> str:
        payload = {
            "protocol_version": self.protocol_version,
            "type": "worker_job",
            "job": {
                "run_id": job.run_id,
                "step_id": job.step_id,
                "attempt_id": job.attempt_id,
                "repository_revision": job.repository_revision,
                "workspace_contract": job.workspace_contract,
                "context_bundle": job.context_bundle,
                "allowed_capabilities": list(job.allowed_capabilities),
                "budget": job.budget,
                "deadline": job.deadline,
                "expected_output_schema": job.expected_output_schema,
                "correlation_id": job.correlation_id,
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def decode_job(self, encoded: str) -> WorkerJob:
        payload = json.loads(encoded)
        self._validate_envelope(payload, "worker_job")
        data = payload["job"]

        return WorkerJob(
            run_id=data["run_id"],
            step_id=data["step_id"],
            attempt_id=data["attempt_id"],
            repository_revision=data["repository_revision"],
            workspace_contract=data["workspace_contract"],
            context_bundle=data["context_bundle"],
            allowed_capabilities=tuple(data["allowed_capabilities"]),
            budget=data["budget"],
            deadline=data["deadline"],
            expected_output_schema=data["expected_output_schema"],
            correlation_id=data.get("correlation_id"),
        )

    def encode_result(self, result: WorkerResult) -> str:
        payload = {
            "protocol_version": self.protocol_version,
            "type": "worker_result",
            "result": {
                "status": result.status,
                "correlation_id": result.correlation_id,
                "structured_result": result.structured_result,
                "artifacts": [
                    {
                        "artifact_id": artifact.artifact_id,
                        "kind": artifact.kind,
                        "location": artifact.location,
                        "sha256": artifact.sha256,
                    }
                    for artifact in result.artifacts
                ],
                "logs": list(result.logs),
                "usage": result.usage,
                "errors": list(result.errors),
                "evidence_refs": [
                    {
                        "evidence_id": evidence.evidence_id,
                        "kind": evidence.kind,
                        "location": evidence.location,
                        "digest": evidence.digest,
                    }
                    for evidence in result.evidence_refs
                ],
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def decode_result(self, encoded: str) -> WorkerResult:
        payload = json.loads(encoded)
        self._validate_envelope(payload, "worker_result")
        data = payload["result"]

        from vajra.domain.models import ArtifactRef, EvidenceRef

        return WorkerResult(
            status=data["status"],
            correlation_id=data.get("correlation_id"),
            structured_result=data.get("structured_result"),
            artifacts=tuple(
                ArtifactRef(
                    artifact_id=artifact["artifact_id"],
                    kind=artifact["kind"],
                    location=artifact["location"],
                    sha256=artifact.get("sha256"),
                )
                for artifact in data.get("artifacts", ())
            ),
            logs=tuple(data.get("logs", ())),
            usage=data.get("usage", {}),
            errors=tuple(data.get("errors", ())),
            evidence_refs=tuple(
                EvidenceRef(
                    evidence_id=evidence["evidence_id"],
                    kind=evidence["kind"],
                    location=evidence["location"],
                    digest=evidence.get("digest"),
                )
                for evidence in data.get("evidence_refs", ())
            ),
        )

    def _validate_envelope(self, payload: dict[str, Any], expected_type: str) -> None:
        if payload.get("protocol_version") != self.protocol_version:
            raise ValueError("Unsupported Kaggle worker protocol version")
        if payload.get("type") != expected_type:
            raise ValueError(f"Expected {expected_type} envelope")
        if not isinstance(payload.get(expected_type.removeprefix("worker_")), dict):
            raise ValueError(f"Missing {expected_type} payload")
