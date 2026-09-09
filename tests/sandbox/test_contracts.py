from __future__ import annotations

import pytest

from vajra.sandbox.contracts import (
    SandboxExecution,
    SandboxHandle,
    SandboxSpec,
)


def test_sandbox_spec_requires_workspace():
    with pytest.raises(ValueError):
        SandboxSpec(workspace_id="")


def test_sandbox_spec_preserves_boundary():
    spec = SandboxSpec(
        workspace_id="ws-1",
        filesystem_scope=("/workspace",),
        network_enabled=False,
        allowed_capabilities=("execution.test",),
        resource_limits={"cpu_seconds": 30},
    )

    assert spec.workspace_id == "ws-1"
    assert spec.filesystem_scope == ("/workspace",)
    assert spec.network_enabled is False
    assert spec.allowed_capabilities == ("execution.test",)
    assert spec.resource_limits == {"cpu_seconds": 30}


def test_sandbox_handle_requires_identity():
    with pytest.raises(ValueError):
        SandboxHandle(sandbox_id="", backend="restricted-local")

    with pytest.raises(ValueError):
        SandboxHandle(sandbox_id="sb-1", backend="")


def test_sandbox_execution_requires_identity_and_status():
    with pytest.raises(ValueError):
        SandboxExecution(sandbox_id="", status="READY")

    with pytest.raises(ValueError):
        SandboxExecution(sandbox_id="sb-1", status="")


def test_sandbox_execution_is_backend_neutral():
    execution = SandboxExecution(
        sandbox_id="sb-1",
        status="completed",
        output={"result": "ok"},
    )

    assert execution.sandbox_id == "sb-1"
    assert execution.status == "completed"
    assert execution.output == {"result": "ok"}
