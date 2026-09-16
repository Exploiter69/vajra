from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from vajra.verification.integrity import IntegrityReport


class AntiGamingStatus(str, Enum):
    CLEAR = "CLEAR"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class AntiGamingFinding:
    rule: str
    detail: str
    severity: str = "HIGH"


@dataclass(frozen=True)
class AntiGamingReport:
    status: AntiGamingStatus
    findings: tuple[AntiGamingFinding, ...]

    @property
    def blocked(self) -> bool:
        return self.status is AntiGamingStatus.BLOCK


class AntiGamingGuard:
    """Turn integrity/evidence anomalies into a fail-closed verification gate."""

    def inspect_integrity(self, report: IntegrityReport) -> AntiGamingReport:
        if report.valid:
            return AntiGamingReport(AntiGamingStatus.CLEAR, ())
        findings = tuple(
            AntiGamingFinding(v.rule, f"{v.path}: {v.detail}")
            for v in report.violations
        )
        return AntiGamingReport(AntiGamingStatus.BLOCK, findings)

    def inspect_verification_claim(
        self,
        *,
        status: str,
        evidence_present: bool,
        verifier_version: str,
        expected_verifier_version: str,
        artifact_digest_matches: bool,
    ) -> AntiGamingReport:
        findings: list[AntiGamingFinding] = []
        if status == "PASSED" and not evidence_present:
            findings.append(AntiGamingFinding("missing_evidence", "a passed verification has no evidence"))
        if not verifier_version or verifier_version != expected_verifier_version:
            findings.append(AntiGamingFinding("verifier_identity", "verification was not produced by the expected verifier version"))
        if not artifact_digest_matches:
            findings.append(AntiGamingFinding("artifact_binding", "verification evidence is not bound to the current artifact"))
        if status not in {"PASSED", "FAILED", "INCONCLUSIVE"}:
            findings.append(AntiGamingFinding("unknown_status", "verification status is not a canonical value"))
        return AntiGamingReport(
            AntiGamingStatus.BLOCK if findings else AntiGamingStatus.CLEAR,
            tuple(findings),
        )
