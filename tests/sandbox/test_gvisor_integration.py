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


def test_gvisor_applies_resource_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    class Completed:
        returncode = 0
        stdout = "resource-limit-test"
        stderr = ""

    def fake_run(command: list[str], **kwargs: object) -> Completed:
        captured.extend(command)
        assert kwargs["shell"] is False
        return Completed()

    monkeypatch.setattr(
        "vajra.sandbox.gvisor.subprocess.run",
        fake_run,
    )

    sandbox = GVisorSandbox()
    handle = sandbox.create(
        SandboxSpec(
            workspace_id="gate-d-resource-workspace",
            filesystem_scope=("/workspace",),
            network_enabled=False,
            resource_limits={
                "memory": "32m",
                "memory_swap": "32m",
                "cpus": "1.0",
                "pids_limit": 64,
            },
        )
    )

    intent = Intent(
        intent_id="gate-d-resource-test",
        run_id="gate-d-run",
        step_id="gate-d-step",
        attempt_id="gate-d-attempt",
        operation="run_command",
        parameters={
            "workspace": str(tmp_path),
            "command": ["sh", "-c", "echo resource-limit-test"],
        },
        requested_capabilities=("execution.test",),
    )

    decision = PolicyDecision(
        intent_id=intent.intent_id,
        policy_id="gate-d",
        policy_version="1",
        decision=PolicyDecisionType.ALLOW,
        reason="Gate D resource-limit wiring test",
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

    assert "--memory" in captured
    assert "32m" in captured
    assert "--memory-swap" in captured
    assert "--cpus" in captured
    assert "1.0" in captured
    assert "--pids-limit" in captured
    assert "64" in captured
