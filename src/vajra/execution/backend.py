from __future__ import annotations

from typing import Protocol

from vajra.execution.contracts import ExecutionRequest, ExecutionResult


class ExecutionBackend(Protocol):
    """
    Backend boundary for performing an already-authorized operation.

    The backend does not decide whether an operation is permitted.
    Authorization has already been established by the Policy Authority
    and enforced by the Execution Broker.
    """

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Perform the authorized execution request and return its result."""
        ...
