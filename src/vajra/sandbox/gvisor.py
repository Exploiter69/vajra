from __future__ import annotations

import os
import signal
import selectors
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from vajra.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from vajra.sandbox.contracts import SandboxHandle, SandboxSpec
from vajra.hardening import HardeningViolation, SecurityPolicy


class GVisorSandbox:
    """Docker-backed sandbox using the gVisor runsc runtime."""

    def __init__(
        self,
        image: str = "alpine:latest",
        runtime: str = "runsc",
        docker: str = "docker",
        security_policy: SecurityPolicy | None = None,
    ) -> None:
        self._image = image
        self._runtime = runtime
        self._docker = docker
        self._security = security_policy or SecurityPolicy()
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

        try:
            workspace_path = self._security.validate_workspace(workspace)
            self._security.validate_command(command, network_enabled=spec.network_enabled)
        except HardeningViolation as exc:
            return self._rejected(operation, str(exc))

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

        supported_limits = set(resource_flags) | {"timeout_seconds", "output_bytes"}
        unknown_limits = set(spec.resource_limits) - supported_limits
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

        timeout = spec.resource_limits.get("timeout_seconds")
        output_limit = spec.resource_limits.get("output_bytes")
        if timeout is not None and (isinstance(timeout, bool) or float(timeout) < 0):
            return self._rejected(operation, "timeout_seconds must be non-negative")
        if output_limit is not None and (isinstance(output_limit, bool) or int(output_limit) < 0):
            return self._rejected(operation, "output_bytes must be non-negative")

        try:
            completed = self._run_limited(
                docker_command,
                timeout=float(timeout) if timeout is not None else None,
                output_limit=int(output_limit) if output_limit is not None else None,
            )
        except OSError as exc:
            return self._rejected(operation, f"gVisor execution failed: {exc}")

        output = {
            "command": list(command),
            "return_code": completed["return_code"],
            "stdout": completed["stdout"],
            "stderr": completed["stderr"],
            "workspace": str(workspace_path),
            "runtime": self._runtime,
            "image": self._image,
            "timed_out": completed["timed_out"],
            "output_bytes": completed["output_bytes"],
        }

        if completed["timed_out"]:
            return self._rejected(operation, "worker runtime limit exceeded", output)
        if completed["output_exceeded"]:
            return self._rejected(operation, "output byte limit exceeded", output)

        if completed["return_code"] != 0:
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

    def _run_limited(self, command: list[str], *, timeout: float | None, output_limit: int | None) -> dict[str, object]:
        started = time.monotonic()
        process = subprocess.Popen(
            command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdout is not None and process.stderr is not None
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        timed_out = False
        output_exceeded = False
        total = 0
        try:
            while selector.get_map() or process.poll() is None:
                remaining = None if timeout is None else max(0.0, timeout - (time.monotonic() - started))
                if remaining == 0.0:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGKILL)
                    remaining = 0.2
                for key, _ in selector.select(remaining if remaining is not None else 0.2):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    total += len(chunk)
                    if output_limit is not None and total > output_limit:
                        output_exceeded = True
                        os.killpg(process.pid, signal.SIGKILL)
                        continue
                    buffers[key.data].extend(chunk)
                if process.poll() is not None and not selector.get_map():
                    break
            process.wait(timeout=1)
        finally:
            selector.close()
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=1)
        return {
            "return_code": process.returncode,
            "stdout": bytes(buffers["stdout"]).decode("utf-8", errors="replace"),
            "stderr": bytes(buffers["stderr"]).decode("utf-8", errors="replace"),
            "timed_out": timed_out,
            "output_exceeded": output_exceeded,
            "output_bytes": total,
        }

    @staticmethod
    def _rejected(operation: str, error: str) -> ExecutionResult:
        return ExecutionResult(
            status=ExecutionStatus.REJECTED,
            operation=operation,
            errors=(error,),
        )
