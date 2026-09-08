from vajra.execution.backend import ExecutionBackend


def test_execution_backend_defines_execute_contract() -> None:
    assert hasattr(ExecutionBackend, "execute")
