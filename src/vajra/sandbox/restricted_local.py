from __future__ import annotations

from uuid import uuid4

from vajra.execution.contracts import ExecutionRequest, ExecutionResult
from vajra.execution.local_backend import LocalExecutionBackend
from vajra.sandbox.contracts import SandboxHandle, SandboxSpec


class RestrictedLocalSandbox:
    """Reference sandbox backend with bounded local workspace execution.

    This backend is intentionally not presented as a strong security boundary.
    It provides the v0 sandbox abstraction using the existing local execution
    backend and an explicit SandboxSpec.
    """

    def __init__(
        self,
        execution_backend: LocalExecutionBackend | None = None,
    ) -> None:
        self._sandboxes: dict[str, SandboxSpec] = {}
        self._execution = execution_backend or LocalExecutionBackend()

    def create(self, spec: SandboxSpec) -> SandboxHandle:
        sandbox_id = str(uuid4())
        self._sandboxes[sandbox_id] = spec
        return SandboxHandle(
            sandbox_id=sandbox_id,
            backend="restricted-local",
        )

    def execute(
        self,
        sandbox: SandboxHandle,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        self._require_sandbox(sandbox)
        return self._execution.execute(request)

    def destroy(self, sandbox: SandboxHandle) -> None:
        self._require_sandbox(sandbox)
        del self._sandboxes[sandbox.sandbox_id]

    def _require_sandbox(self, sandbox: SandboxHandle) -> SandboxSpec:
        if sandbox.backend != "restricted-local":
            raise ValueError("Sandbox handle does not belong to this backend")

        try:
            return self._sandboxes[sandbox.sandbox_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown sandbox: {sandbox.sandbox_id}"
            ) from exc
