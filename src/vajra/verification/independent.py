from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from vajra.domain.models import EvidenceRef, VerificationResult, VerificationStatus
from vajra.verification.command import CommandVerifier
from vajra.verification.contracts import VerificationRequest
from vajra.verification.environment import VerificationEnvironment, VerificationExecutor
from vajra.verification.evidence import VerificationEvidence, VerificationEvidenceBuilder
from vajra.verification.plan import CriterionKind, FrozenVerificationPlan


@dataclass(frozen=True)
class IndependentVerificationReport:
    verification_results: tuple[VerificationResult, ...]
    evidence: tuple[VerificationEvidence, ...]
    output: tuple[str, ...]


class IndependentVerifier:
    """Execute only a frozen verification plan, never worker-supplied checks."""

    VERSION = "independent-verifier-v1"

    def __init__(self, executor: VerificationExecutor) -> None:
        self._executor = executor
        self._evidence = VerificationEvidenceBuilder()

    def verify(
        self,
        plan: FrozenVerificationPlan,
        *,
        run_id: str,
        step_id: str,
        attempt_id: str,
        environment: VerificationEnvironment,
    ) -> IndependentVerificationReport:
        results: list[VerificationResult] = []
        evidence: list[VerificationEvidence] = []
        outputs: list[str] = []
        for check in plan.checks:
            parameters = dict(check.parameters)
            command: tuple[str, ...]
            output: str
            exit_code: int

            if check.kind is CriterionKind.COMMAND_EXIT:
                command = tuple(parameters["command"])
                exit_code, output = self._executor.execute(command, environment)
                expected = parameters["expected_exit_code"]
                result = self._command_result(check.check_id, run_id, step_id, attempt_id, expected, exit_code, plan)
            elif check.kind is CriterionKind.FILE_EXISTS:
                relative = str(parameters["path"])
                path = self._safe_path(environment.workspace, relative)
                exists = path.is_file()
                command = ("filesystem", "exists", relative)
                exit_code = 0 if exists else 1
                output = f"{relative}: {'present' if exists else 'missing'}"
                result = self._observation_result(check.check_id, run_id, "file_exists", relative, exists)
            elif check.kind is CriterionKind.FILE_CONTAINS:
                relative = str(parameters["path"])
                needle = str(parameters["needle"])
                path = self._safe_path(environment.workspace, relative)
                if not path.is_file():
                    found = False
                    output = f"{relative}: missing"
                else:
                    found = needle in path.read_text(encoding="utf-8")
                    output = f"{relative}: {'matched' if found else 'not matched'}"
                command = ("filesystem", "contains", relative, needle)
                exit_code = 0 if found else 1
                result = self._observation_result(check.check_id, run_id, "file_contains", relative, found, needle=needle)
            elif check.kind is CriterionKind.GIT_CLEAN:
                command = ("git", "status", "--porcelain", "--untracked-files=all")
                exit_code, output = self._executor.execute(command, environment)
                clean = exit_code == 0 and not output.strip()
                result = self._observation_result(check.check_id, run_id, "git_clean", "workspace", clean, observed_output=output)
            else:
                command = ("unsupported", check.kind.value)
                exit_code = 1
                output = ""
                result = self._unsupported_check(check.check_id, run_id, f"unsupported criterion kind: {check.kind.value}")

            outputs.append(output)
            sealed = self._evidence.build(
                result,
                check_id=check.check_id,
                command=command,
                exit_code=exit_code,
                output_reference=f"memory://verification/{check.check_id}",
                output=output,
                environment=environment.env_dict(),
            )
            evidence.append(sealed)
            results.append(
                VerificationResult(
                    verification_id=result.verification_id,
                    run_id=result.run_id,
                    status=result.status,
                    checks=result.checks,
                    evidence_refs=(sealed.evidence_ref,),
                    verifier_version=result.verifier_version,
                )
            )
        return IndependentVerificationReport(tuple(results), tuple(evidence), tuple(outputs))

    @staticmethod
    def _command_result(check_id: str, run_id: str, step_id: str, attempt_id: str, expected: int, observed: int, plan: FrozenVerificationPlan) -> VerificationResult:
        request = VerificationRequest(
            verification_id=check_id,
            run_id=run_id,
            step_id=step_id,
            attempt_id=attempt_id,
            operation="frozen-verification-check",
            parameters={
                "expected_exit_code": expected,
                "observed_exit_code": observed,
                "plan_id": plan.plan_id,
                "plan_digest": plan.integrity_digest,
            },
        )
        return CommandVerifier().verify(request)

    @staticmethod
    def _observation_result(check_id: str, run_id: str, check: str, subject: str, passed: bool, **extra: str) -> VerificationResult:
        details = {"check": check, "subject": subject, "passed": passed, **extra}
        return VerificationResult(
            verification_id=check_id,
            run_id=run_id,
            status=VerificationStatus.PASSED if passed else VerificationStatus.FAILED,
            checks=(details,),
            verifier_version=IndependentVerifier.VERSION,
        )

    @staticmethod
    def _unsupported_check(check_id: str, run_id: str, reason: str) -> VerificationResult:
        return VerificationResult(
            verification_id=check_id,
            run_id=run_id,
            status=VerificationStatus.INCONCLUSIVE,
            checks=({"check": "supported_verifier", "passed": False, "reason": reason},),
            verifier_version=IndependentVerifier.VERSION,
        )

    @staticmethod
    def _safe_path(root: Path, relative: str) -> Path:
        path = (root / relative).resolve()
        root = root.resolve()
        if path != root and root not in path.parents:
            raise ValueError(f"unsafe verification path: {relative}")
        return path


class SubprocessVerificationExecutor:
    """Pristine local executor; network-disabled runs require an isolated sandbox."""

    def __init__(self, *, max_output_bytes: int = 1_048_576) -> None:
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        self.max_output_bytes = max_output_bytes

    def execute(self, command: Sequence[str], environment: VerificationEnvironment) -> tuple[int, str]:
        if not command or not all(isinstance(arg, str) and arg for arg in command):
            raise ValueError("verification command must contain non-empty strings")
        if not environment.network_enabled:
            raise RuntimeError("network-disabled verification must use an isolated sandbox executor")
        completed = subprocess.run(
            tuple(command),
            cwd=environment.workspace,
            env=environment.env_dict(),
            capture_output=True,
            text=True,
            timeout=environment.timeout_seconds,
            check=False,
        )
        output = (completed.stdout + completed.stderr).encode("utf-8", errors="replace")[: self.max_output_bytes].decode("utf-8", errors="replace")
        return completed.returncode, output
