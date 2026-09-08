from __future__ import annotations

import subprocess
from pathlib import Path

from vajra.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)


class WorkspaceProcessBackend:
    """
    Controlled process backend for workspace-local engineering commands.

    Commands are supplied as an argv sequence, never as a shell command.
    Execution is rooted in the declared workspace.
    """

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        operation = request.intent.operation
        parameters = request.intent.parameters

        workspace = parameters.get("workspace")
        command = parameters.get("command")

        if not isinstance(workspace, str) or not workspace:
            return self._rejected(
                operation,
                "workspace must be a non-empty string",
            )

        if not isinstance(command, (list, tuple)) or not command:
            return self._rejected(
                operation,
                "command must be a non-empty argument sequence",
            )

        if not all(isinstance(argument, str) and argument for argument in command):
            return self._rejected(
                operation,
                "command arguments must be non-empty strings",
            )

        workspace_path = Path(workspace).resolve()

        if not workspace_path.is_dir():
            return self._rejected(
                operation,
                f"workspace does not exist: {workspace_path}",
            )

        try:
            completed = subprocess.run(
                list(command),
                cwd=workspace_path,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return self._rejected(
                operation,
                f"Process execution failed: {exc}",
            )

        output = {
            "command": list(command),
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
                    f"Process exited with return code {completed.returncode}",
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
