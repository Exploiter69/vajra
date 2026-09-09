from __future__ import annotations

from typing import Protocol

from vajra.execution.contracts import ExecutionRequest, ExecutionResult
from vajra.sandbox.contracts import SandboxExecution, SandboxHandle, SandboxSpec


class SandboxBackend(Protocol):
    """Backend boundary for isolated autonomous execution."""

    def create(self, spec: SandboxSpec) -> SandboxHandle:
        """Create an isolated execution boundary."""
        ...

    def execute(
        self,
        sandbox: SandboxHandle,
        request: ExecutionRequest,
    ) -> ExecutionResult | SandboxExecution:
        """Execute an already-authorized operation inside the sandbox."""
        ...

    def destroy(self, sandbox: SandboxHandle) -> None:
        """Destroy the sandbox and release backend resources."""
        ...
