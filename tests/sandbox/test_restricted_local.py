from __future__ import annotations

import pytest

from vajra.sandbox.contracts import SandboxSpec
from vajra.sandbox.restricted_local import RestrictedLocalSandbox


def test_create_returns_live_restricted_local_sandbox():
    backend = RestrictedLocalSandbox()

    handle = backend.create(
        SandboxSpec(workspace_id="ws-1")
    )

    assert handle.backend == "restricted-local"
    assert handle.sandbox_id


def test_destroy_removes_sandbox():
    backend = RestrictedLocalSandbox()
    handle = backend.create(SandboxSpec(workspace_id="ws-1"))

    backend.destroy(handle)

    with pytest.raises(KeyError):
        backend.destroy(handle)


def test_wrong_backend_handle_is_rejected():
    backend = RestrictedLocalSandbox()
    handle = backend.create(SandboxSpec(workspace_id="ws-1"))

    from vajra.sandbox.contracts import SandboxHandle

    wrong = SandboxHandle(
        sandbox_id=handle.sandbox_id,
        backend="firecracker",
    )

    with pytest.raises(ValueError):
        backend.execute(wrong, None)  # type: ignore[arg-type]
