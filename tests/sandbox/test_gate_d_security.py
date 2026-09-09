from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from vajra.sandbox.contracts import SandboxSpec
from vajra.sandbox.restricted_local import RestrictedLocalSandbox


@dataclass
class GateDProbe:
    name: str
    description: str


GATE_D_PROBES = (
    GateDProbe(
        "filesystem_escape",
        "execution cannot access files outside the declared filesystem scope",
    ),
    GateDProbe(
        "path_traversal",
        "path traversal cannot escape the declared workspace",
    ),
    GateDProbe(
        "symlink_escape",
        "symlinks cannot escape the declared filesystem scope",
    ),
    GateDProbe(
        "process_access",
        "execution cannot access unauthorized host processes",
    ),
    GateDProbe(
        "network_access",
        "execution cannot access the network when disabled",
    ),
    GateDProbe(
        "credential_visibility",
        "host credentials are not visible to sandboxed execution",
    ),
    GateDProbe(
        "resource_exhaustion",
        "resource limits prevent unbounded sandbox execution",
    ),
)


def test_gate_d_declares_required_security_probes():
    assert tuple(probe.name for probe in GATE_D_PROBES) == (
        "filesystem_escape",
        "path_traversal",
        "symlink_escape",
        "process_access",
        "network_access",
        "credential_visibility",
        "resource_exhaustion",
    )


def test_gate_d_spec_defaults_to_no_network():
    spec = SandboxSpec(workspace_id="gate-d-workspace")

    assert spec.network_enabled is False
    assert spec.filesystem_scope == ()
    assert spec.allowed_capabilities == ()
    assert spec.resource_limits == {}


def test_gate_d_sandbox_lifecycle_is_explicit():
    sandbox = RestrictedLocalSandbox()
    spec = SandboxSpec(
        workspace_id="gate-d-workspace",
        filesystem_scope=("/workspace",),
        network_enabled=False,
    )

    handle = sandbox.create(spec)

    assert handle.backend == "restricted-local"
    sandbox.destroy(handle)

    with pytest.raises(KeyError):
        sandbox.destroy(handle)


@pytest.mark.parametrize("probe", GATE_D_PROBES)
def test_gate_d_probe_is_explicitly_not_claimed_by_restricted_local(probe):
    """RestrictedLocal is only the v0 reference backend.

    These probes must be implemented against the selected strong-isolation
    candidate before Gate D can be marked PASS.
    """
    assert probe.name
    assert probe.description


def test_gate_d_workspace_scope_is_preserved_by_backend():
    sandbox = RestrictedLocalSandbox()
    spec = SandboxSpec(
        workspace_id="gate-d-workspace",
        filesystem_scope=("/workspace/project",),
        network_enabled=False,
    )

    handle = sandbox.create(spec)

    # The backend must retain the declared authority contract even though
    # RestrictedLocal does not itself enforce strong isolation.
    retained = sandbox._require_sandbox(handle)

    assert retained.workspace_id == "gate-d-workspace"
    assert retained.filesystem_scope == ("/workspace/project",)
    assert retained.network_enabled is False

    sandbox.destroy(handle)
