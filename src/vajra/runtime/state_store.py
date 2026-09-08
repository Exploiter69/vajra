from __future__ import annotations

from abc import ABC, abstractmethod
from threading import RLock

from vajra.domain import EngineeringRun


class StateStore(ABC):
    """
    Persistence boundary for canonical VAJRA Engineering Run state.

    RunManager depends on this abstraction and must not know whether state
    is stored in memory, a durable runtime, or another persistent backend.
    """

    @abstractmethod
    def create_run(self, run: EngineeringRun) -> EngineeringRun:
        raise NotImplementedError

    @abstractmethod
    def get_run(self, run_id: str) -> EngineeringRun:
        raise NotImplementedError

    @abstractmethod
    def save_run(self, run: EngineeringRun) -> EngineeringRun:
        raise NotImplementedError


class InMemoryStateStore(StateStore):
    """
    Test/development StateStore.

    This implementation is intentionally non-durable and must never be
    treated as VAJRA's production canonical persistence mechanism.
    """

    def __init__(self) -> None:
        self._runs: dict[str, EngineeringRun] = {}
        self._lock = RLock()

    def create_run(self, run: EngineeringRun) -> EngineeringRun:
        with self._lock:
            if run.run_id in self._runs:
                raise ValueError(f"Run already exists: {run.run_id}")

            self._runs[run.run_id] = run
            return run

    def get_run(self, run_id: str) -> EngineeringRun:
        with self._lock:
            try:
                return self._runs[run_id]
            except KeyError:
                raise KeyError(f"Run not found: {run_id}") from None

    def save_run(self, run: EngineeringRun) -> EngineeringRun:
        with self._lock:
            if run.run_id not in self._runs:
                raise KeyError(f"Run not found: {run.run_id}")

            self._runs[run.run_id] = run
            return run
