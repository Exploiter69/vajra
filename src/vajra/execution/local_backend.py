from __future__ import annotations

from collections.abc import Callable
from typing import Any

from vajra.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)


OperationHandler = Callable[[ExecutionRequest], dict[str, Any]]


class LocalExecutionBackend:
    """
    Deterministic in-process execution backend.

    Operations must be explicitly registered with a handler. The backend
    performs no authorization and provides no implicit shell execution.
    """

    def __init__(
        self,
        handlers: dict[str, OperationHandler] | None = None,
    ) -> None:
        self._handlers: dict[str, OperationHandler] = dict(handlers or {})

    def register(
        self,
        operation: str,
        handler: OperationHandler,
    ) -> None:
        if not operation:
            raise ValueError("operation must not be empty")

        if operation in self._handlers:
            raise ValueError(f"Operation already registered: {operation}")

        self._handlers[operation] = handler

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        operation = request.intent.operation
        handler = self._handlers.get(operation)

        if handler is None:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                operation=operation,
                errors=(f"No execution handler registered: {operation}",),
            )

        try:
            output = handler(request)
        except Exception as exc:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                operation=operation,
                errors=(f"Execution handler failed: {exc}",),
            )

        return ExecutionResult(
            status=ExecutionStatus.ACCEPTED,
            operation=operation,
            output=output,
        )
