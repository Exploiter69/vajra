from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

from vajra.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from vajra.sandbox.contracts import SandboxHandle, SandboxSpec


class GVisorSandbox:
    """Docker-backed sandbox using the gVisor runsc runtime."""

    def __init__(
        self,
        image: str = "alpine:latest",
        runtime: str = "runsc",
        docker: str = "docker",
    ) -> None:
        self._image = image
        self._runtime = runtime
        self._docker = docker
        self._sandboxes: dict[str, SandboxSpec] = {}

    def create(self, spec: SandboxSpec) -> SandboxHandle:
        sandbox_id = str(uuid4())
        self._sandboxes[sandbox_id] = spec
        return SandboxHandle(
            sandbox_id=sandbox_id,
            backend="gvisor",
        )

    def execute(
        self,
        sandbox: SandboxHandle,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        spec = self._require_sandbox(sandbox)
        operation = request.intent.operation
        parameters = request.intent.parameters

        workspace = parameters.get("workspace")
        command = parameters.get("command")

        if not isinstance(workspace, str) or not workspace:
            return self._rejected(operation, "workspace must be a non-empty string")

        if not isinstance(command, (list, tuple)) or not command:
            return self._rejected(
                operation,
                "command must be a non-empty argument sequence",
            )

        if not all(
            isinstance(argument, str) and argument
            for argument in command
        ):
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

        docker_command = [
            self._docker,
            "run",
            "--rm",
            "--runtime",
            self._runtime,
        ]

        if not spec.network_enabled:
            docker_command.extend(["--network", "none"])

        resource_flags = {
            "memory": "--memory",
            "memory_swap": "--memory-swap",
            "cpus": "--cpus",
            "pids_limit": "--pids-limit",
        }

        unknown_limits = set(spec.resource_limits) - set(resource_flags)
        if unknown_limits:
            return self._rejected(
                operation,
                "Unsupported resource limits: "
                + ", ".join(sorted(unknown_limits)),
            )

        for name, flag in resource_flags.items():
            if name in spec.resource_limits:
                value = spec.resource_limits[name]
                if not isinstance(value, (str, int, float)) or isinstance(value, bool):
                    return self._rejected(
                        operation,
                        f"resource limit must be scalar: {name}",
                    )
                docker_command.extend([flag, str(value)])

        docker_command.extend([
            "-v",
            f"{workspace_path}:/workspace:rw",
            "-w",
            "/workspace",
            self._image,
        ])
        docker_command.extend(command)

        try:
            completed = subprocess.run(
                docker_command,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            return self._rejected(
                operation,
                f"gVisor execution failed: {exc}",
            )

        output = {
            "command": list(command),
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "workspace": str(workspace_path),
            "runtime": self._runtime,
            "image": self._image,
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

    def destroy(self, sandbox: SandboxHandle) -> None:
        self._require_sandbox(sandbox)
        del self._sandboxes[sandbox.sandbox_id]

    def _require_sandbox(self, sandbox: SandboxHandle) -> SandboxSpec:
        if sandbox.backend != "gvisor":
            raise ValueError("Sandbox handle does not belong to this backend")

        try:
            return self._sandboxes[sandbox.sandbox_id]
        except KeyError as exc:
            raise KeyError(
                f"Unknown sandbox: {sandbox.sandbox_id}"
            ) from exc

    @staticmethod
    def _rejected(operation: str, error: str) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.REJECTED,
            operation=operation,
            errors=(error,),
        )
