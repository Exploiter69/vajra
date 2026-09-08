from __future__ import annotations

from typing import Protocol

from vajra.execution.contracts import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from vajra.policy.contracts import PolicyDecisionType


class ExecutionBackend(Protocol):
    """
    Backend interface used by the Execution Broker.

    Backends perform operations; the broker remains responsible for
    authorization.
    """

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        ...


class ExecutionBroker:
    """
    VAJRA execution authority boundary.

    The broker will only dispatch an Intent whose policy decision authorizes
    execution. It never grants authorization itself.
    """

    def __init__(self, backend: ExecutionBackend) -> None:
        self._backend = backend

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        decision = request.policy_decision.decision

        if decision not in {
            PolicyDecisionType.ALLOW,
            PolicyDecisionType.MODIFY,
        }:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                operation=request.intent.operation,
                errors=(
                    f"Execution not authorized: {decision.value}",
                ),
            )

        effective_request = request

        if decision is PolicyDecisionType.MODIFY:
            modified_parameters = request.policy_decision.modified_parameters
            assert modified_parameters is not None

            modified_intent = type(request.intent)(
                intent_id=request.intent.intent_id,
                run_id=request.intent.run_id,
                step_id=request.intent.step_id,
                attempt_id=request.intent.attempt_id,
                operation=request.intent.operation,
                parameters=modified_parameters,
                requested_capabilities=request.intent.requested_capabilities,
                reason=request.intent.reason,
            )

            effective_request = ExecutionRequest(
                intent=modified_intent,
                policy_decision=request.policy_decision,
            )

        return self._backend.execute(effective_request)
