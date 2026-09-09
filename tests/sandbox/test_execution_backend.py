from __future__ import annotations

from vajra.execution.broker import ExecutionBroker
from vajra.execution.contracts import ExecutionRequest, ExecutionResult, ExecutionStatus
from vajra.policy.contracts import (
    Intent,
    PolicyDecision,
    PolicyDecisionType,
)
from vajra.sandbox.contracts import SandboxSpec
from vajra.sandbox.execution_backend import SandboxedExecutionBackend


class RecordingBackend:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls += 1
        return ExecutionResult(
            status=ExecutionStatus.ACCEPTED,
            operation=request.intent.operation,
            output={"executed": True},
        )


def make_request(
    *,
    intent_id: str,
    operation: str,
    decision: PolicyDecisionType,
    capabilities: tuple[str, ...] = (),
) -> ExecutionRequest:
    intent = Intent(
        intent_id=intent_id,
        run_id="run-1",
        step_id="step-1",
        attempt_id="attempt-1",
        operation=operation,
        parameters={},
        requested_capabilities=capabilities,
    )

    policy = PolicyDecision(
        intent_id=intent_id,
        decision=decision,
        policy_id="policy-1",
        policy_version="1",
        reason="test",
    )

    return ExecutionRequest(
        intent=intent,
        policy_decision=policy,
    )


def test_broker_authorizes_before_sandbox_execution():
    backend = RecordingBackend()
    sandbox_backend = SandboxedExecutionBackend(
        backend,
        SandboxSpec(
            workspace_id="ws-1",
            filesystem_scope=("/workspace",),
            network_enabled=False,
            allowed_capabilities=("execution.test",),
        ),
    )
    broker = ExecutionBroker(sandbox_backend)

    result = broker.execute(
        make_request(
            intent_id="intent-1",
            operation="run_tests",
            decision=PolicyDecisionType.ALLOW,
            capabilities=("execution.test",),
        )
    )

    assert result.status is ExecutionStatus.ACCEPTED
    assert result.output == {"executed": True}
    assert backend.calls == 1


def test_denied_request_never_reaches_sandbox_backend():
    backend = RecordingBackend()
    sandbox_backend = SandboxedExecutionBackend(
        backend,
        SandboxSpec(workspace_id="ws-1"),
    )
    broker = ExecutionBroker(sandbox_backend)

    result = broker.execute(
        make_request(
            intent_id="intent-2",
            operation="dangerous",
            decision=PolicyDecisionType.DENY,
        )
    )

    assert result.status is ExecutionStatus.REJECTED
    assert backend.calls == 0
