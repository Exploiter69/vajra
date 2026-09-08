from __future__ import annotations

from pathlib import Path

from vajra.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)


class WorkspaceFileBackend:
    """
    Bounded filesystem backend for VAJRA workspace operations.

    All paths are resolved relative to the workspace declared in the
    execution request. Path traversal outside that workspace is rejected.
    """

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        operation = request.intent.operation
        parameters = request.intent.parameters

        workspace = parameters.get("workspace")
        relative_path = parameters.get("path")

        if not isinstance(workspace, str) or not workspace:
            return self._rejected(operation, "workspace must be a non-empty string")

        if not isinstance(relative_path, str) or not relative_path:
            return self._rejected(operation, "path must be a non-empty string")

        workspace_path = Path(workspace).resolve()
        target_path = (workspace_path / relative_path).resolve()

        try:
            target_path.relative_to(workspace_path)
        except ValueError:
            return self._rejected(
                operation,
                "path escapes the declared workspace",
            )

        try:
            if operation == "read_file":
                return self._read_file(operation, target_path)

            if operation == "write_file":
                return self._write_file(
                    operation,
                    target_path,
                    parameters.get("content"),
                )

            return self._rejected(
                operation,
                f"Unsupported file operation: {operation}",
            )
        except OSError as exc:
            return self._rejected(
                operation,
                f"Filesystem operation failed: {exc}",
            )

    def _read_file(
        self,
        operation: str,
        target_path: Path,
    ) -> ExecutionResult:
        if not target_path.is_file():
            return self._rejected(
                operation,
                f"File does not exist: {target_path}",
            )

        return ExecutionResult(
            status=ExecutionStatus.ACCEPTED,
            operation=operation,
            output={
                "path": str(target_path),
                "content": target_path.read_text(),
            },
        )

    def _write_file(
        self,
        operation: str,
        target_path: Path,
        content: object,
    ) -> ExecutionResult:
        if not isinstance(content, str):
            return self._rejected(
                operation,
                "content must be a string",
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content)

        return ExecutionResult(
            status=ExecutionStatus.ACCEPTED,
            operation=operation,
            output={
                "path": str(target_path),
                "bytes_written": len(content.encode()),
            },
        )

    @staticmethod
    def _rejected(operation: str, error: str) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.REJECTED,
            operation=operation,
            errors=(error,),
        )
