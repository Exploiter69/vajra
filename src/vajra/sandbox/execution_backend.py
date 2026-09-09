from __future__ import annotations

from vajra.execution.backend import ExecutionBackend
from vajra.execution.contracts import ExecutionRequest, ExecutionResult
from vajra.sandbox.contracts import SandboxSpec
from vajra.sandbox.restricted_local import RestrictedLocalSandbox


class SandboxedExecutionBackend:
    """ExecutionBackend adapter that places authorized execution inside a sandbox."""

    def __init__(
        self,
        backend: ExecutionBackend,
        spec: SandboxSpec,
        sandbox: RestrictedLocalSandbox | None = None,
    ) -> None:
        self._backend = backend
        self._spec = spec
        self._sandbox = sandbox or RestrictedLocalSandbox(
            execution_backend=backend,
        )

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        handle = self._sandbox.create(self._spec)
        try:
            return self._sandbox.execute(
                handle,
                request,
            )
        finally:
            self._sandbox.destroy(handle)
