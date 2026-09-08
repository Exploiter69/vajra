from typing import Callable

import pytest

from vajra.runtime.durable_runtime import (
    DurableExecution,
    DurableRuntime,
)


class ContractRuntime(DurableRuntime):
    def __init__(self):
        self.executions = {}
        self.cancelled = set()

    def execute(
        self,
        execution_id: str,
        operation: Callable[[], object],
    ) -> DurableExecution[object]:
        if execution_id in self.executions:
            return self.executions[execution_id]

        result = operation()
        execution = DurableExecution(
            execution_id=execution_id,
            result=result,
        )
        self.executions[execution_id] = execution
        return execution

    def get_execution(self, execution_id: str):
        return self.executions.get(execution_id)

    def cancel(self, execution_id: str) -> None:
        self.cancelled.add(execution_id)


def test_durable_runtime_contract_can_execute_and_retrieve():
    runtime = ContractRuntime()

    execution = runtime.execute(
        "exec-1",
        lambda: "completed",
    )

    assert execution.execution_id == "exec-1"
    assert execution.result == "completed"
    assert runtime.get_execution("exec-1") == execution


def test_durable_runtime_contract_preserves_idempotent_execution():
    runtime = ContractRuntime()
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        return "result"

    first = runtime.execute("exec-1", operation)
    second = runtime.execute("exec-1", operation)

    assert first == second
    assert calls == 1


def test_durable_runtime_contract_supports_cancellation():
    runtime = ContractRuntime()

    runtime.cancel("exec-1")

    assert "exec-1" in runtime.cancelled


def test_durable_execution_requires_execution_id():
    with pytest.raises(TypeError):
        DurableExecution()
