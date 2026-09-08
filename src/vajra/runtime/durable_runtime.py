from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class DurableExecution(Generic[T]):
    execution_id: str
    result: T | None = None


class DurableRuntime(ABC):
    """
    VAJRA-owned durable execution boundary.

    Application code depends only on this contract. Concrete durable
    runtimes/adapters must provide the actual persistence, recovery,
    retry, idempotency, timer, and concurrency guarantees.
    """

    @abstractmethod
    def execute(
        self,
        execution_id: str,
        operation: Callable[[], T],
    ) -> DurableExecution[T]:
        """
        Execute a durable operation identified by execution_id.

        Implementations must provide idempotent recovery semantics.
        """
        raise NotImplementedError

    @abstractmethod
    def get_execution(
        self,
        execution_id: str,
    ) -> DurableExecution[object] | None:
        """Return persisted execution state, if known."""
        raise NotImplementedError

    @abstractmethod
    def cancel(self, execution_id: str) -> None:
        """Request cancellation of a durable execution."""
        raise NotImplementedError
