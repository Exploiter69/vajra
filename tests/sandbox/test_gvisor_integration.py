from __future__ import annotations

from pathlib import Path

import pytest

from vajra.execution.contracts import ExecutionRequest, ExecutionStatus
from vajra.policy.contracts import (
    Intent,
    PolicyDecision,
    PolicyDecisionType,
)
from vajra.sandbox.contracts import SandboxSpec
from vajra.sandbox.gvisor import GVisorSandbox


def test_gvisor_executes_authorized_command(tmp_path: Path) -> None:
    sandbox = GVisorSandbox()

    handle = sandbox.create(
        SandboxSpec(
            workspace_id="gate-d-workspace",
            filesystem_scope=("/workspace",),
            network_enabled=False,
        )
    )

    intent = Intent(
        intent_id="gate-d-gvisor-test",
        run_id="gate-d-run",
        step_id="gate-d-step",
        attempt_id="gate-d-attempt",
        operation="run_command",
        parameters={
            "workspace": str(tmp_path),
            "command": ["sh", "-c", "echo VAJRA_GVISOR_TEST_OK"],
        },
        requested_capabilities=("execution.test",),
    )

    decision = PolicyDecision(
        intent_id=intent.intent_id,
        policy_id="gate-d",
        policy_version="1",
        decision=PolicyDecisionType.ALLOW,
        reason="Gate D integration test",
    )

    result = sandbox.execute(
        handle,
        ExecutionRequest(
            intent=intent,
            policy_decision=decision,
        ),
    )

    sandbox.destroy(handle)

    assert result.status is ExecutionStatus.ACCEPTED
    assert result.output["runtime"] == "runsc"
    assert "VAJRA_GVISOR_TEST_OK" in result.output["stdout"]


@pytest.mark.parametrize(
    "command",
    [
        ["sh", "-c", "test ! -e /host-secret.txt"],
        ["sh", "-c", "test ! -e /proc/1/root/host-secret.txt"],
    ],
)
def test_gvisor_does_not_expose_host_paths(
    tmp_path: Path,
    command: list[str],
) -> None:
    host_secret = tmp_path.parent / "gate-d-host-secret.txt"
    host_secret.write_text("VAJRA-GATE-D-HOST-SECRET\n")

    sandbox = GVisorSandbox()
    handle = sandbox.create(
        SandboxSpec(
            workspace_id="gate-d-workspace",
            filesystem_scope=("/workspace",),
            network_enabled=False,
        )
    )

    intent = Intent(
        intent_id="gate-d-host-path-test",
        run_id="gate-d-run",
        step_id="gate-d-step",
        attempt_id="gate-d-attempt",
        operation="run_command",
        parameters={
            "workspace": str(tmp_path),
            "command": command,
        },
        requested_capabilities=("execution.test",),
    )

    decision = PolicyDecision(
        intent_id=intent.intent_id,
        policy_id="gate-d",
        policy_version="1",
        decision=PolicyDecisionType.ALLOW,
        reason="Gate D isolation test",
    )

    result = sandbox.execute(
        handle,
        ExecutionRequest(
            intent=intent,
            policy_decision=decision,
        ),
    )

    sandbox.destroy(handle)
    host_secret.unlink()

    assert result.status is ExecutionStatus.ACCEPTED
