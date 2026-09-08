from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from vajra.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)


class WorkspaceGitBackend:
    """
    Controlled Git backend for local workspace operations.

    Only explicitly supported, non-destructive operations are executed.
    No shell is used and no remote/destructive operation is implicit.
    """

    _ALLOWED_OPERATIONS = {
        "git_status",
        "git_diff",
        "git_log",
        "git_revision",
    }

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        operation = request.intent.operation

        if operation not in self._ALLOWED_OPERATIONS:
            return self._rejected(
                operation,
                f"Unsupported Git operation: {operation}",
            )

        parameters = request.intent.parameters
        workspace = parameters.get("workspace")

        if not isinstance(workspace, str) or not workspace:
            return self._rejected(
                operation,
                "workspace must be a non-empty string",
            )

        workspace_path = Path(workspace).resolve()

        if not workspace_path.is_dir():
            return self._rejected(
                operation,
                f"workspace does not exist: {workspace_path}",
            )

        commands: dict[str, list[str]] = {
            "git_status": ["git", "status", "--short"],
            "git_diff": ["git", "diff", "--no-ext-diff"],
            "git_log": ["git", "log", "-n", "10", "--oneline"],
            "git_revision": ["git", "rev-parse", "HEAD"],
        }

        try:
            completed = subprocess.run(
                commands[operation],
                cwd=workspace_path,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return self._rejected(
                operation,
                f"Git execution failed: {exc}",
            )

        output: dict[str, Any] = {
            "command": commands[operation],
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "workspace": str(workspace_path),
        }

        if completed.returncode != 0:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                operation=operation,
                output=output,
                errors=(
                    f"Git exited with return code {completed.returncode}",
                ),
            )

        return ExecutionResult(
            status=ExecutionStatus.ACCEPTED,
            operation=operation,
            output=output,
        )

    @staticmethod
    def _rejected(operation: str, error: str) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.REJECTED,
            operation=operation,
            errors=(error,),
        )
