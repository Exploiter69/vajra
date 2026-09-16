from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from vajra.domain.models import VerificationResult, VerificationStatus
from vajra.verification.command import CommandVerifier
from vajra.verification.contracts import VerificationRequest
from vajra.verification.environment import VerificationEnvironment, VerificationExecutor
from vajra.verification.plan import CriterionKind, FrozenVerificationPlan


@dataclass(frozen=True)
class IndependentVerificationReport:
    verification_results: tuple[VerificationResult, ...]
    output: tuple[str, ...]


class IndependentVerifier:
    """Execute only a frozen verification plan, never worker-supplied checks."""

    VERSION = "independent-verifier-v1"

    def __init__(self, executor: VerificationExecutor) -> None:
        self._executor = executor

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
        outputs: list[str] = []
        for check in plan.checks:
            parameters = dict(check.parameters)
            if check.kind is not CriterionKind.COMMAND_EXIT:
                result = self._unsupported_check(check.check_id, run_id, f"check kind {check.kind.value} requires a dedicated verifier")
                results.append(result)
                outputs.append("")
                continue
            command = parameters["command"]
            expected = parameters["expected_exit_code"]
            exit_code, output = self._executor.execute(command, environment)
            outputs.append(output)
            request = VerificationRequest(
                verification_id=check.check_id,
                run_id=run_id,
                step_id=step_id,
                attempt_id=attempt_id,
                operation="frozen-verification-check",
                parameters={
                    "expected_exit_code": expected,
                    "observed_exit_code": exit_code,
                    "plan_id": plan.plan_id,
                    "plan_digest": plan.integrity_digest,
                },
            )
            results.append(CommandVerifier().verify(request))
        return IndependentVerificationReport(tuple(results), tuple(outputs))

    @staticmethod
    def _unsupported_check(check_id: str, run_id: str, reason: str) -> VerificationResult:
        return VerificationResult(
            verification_id=check_id,
            run_id=run_id,
            status=VerificationStatus.INCONCLUSIVE,
            checks=({"check": "supported_verifier", "passed": False, "reason": reason},),
            verifier_version=IndependentVerifier.VERSION,
        )


class SubprocessVerificationExecutor:
    """Pristine local executor; network-disabled runs require a sandbox executor."""

    def __init__(self, *, max_output_bytes: int = 1_048_576) -> None:
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        self.max_output_bytes = max_output_bytes

    def execute(self, command: Sequence[str], environment: VerificationEnvironment) -> tuple[int, str]:
        if not command or not all(isinstance(arg, str) and arg for arg in command):
            raise ValueError("verification command must contain non-empty strings")
        if not environment.network_enabled:
            raise RuntimeError("network-disabled verification must use an isolated sandbox executor")
        import subprocess

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
