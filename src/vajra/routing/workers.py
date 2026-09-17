from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkerCapabilities:
    accelerator: str | None = None
    vram_gib: float = 0.0
    system_ram_gib: float = 0.0
    model: str = ""
    model_version: str = ""
    context_limit: int = 0
    supported_tasks: frozenset[str] = frozenset()
    sandbox_type: str = ""
    network_policy: str = "none"

    def __post_init__(self) -> None:
        if self.vram_gib < 0 or self.system_ram_gib < 0 or self.context_limit < 0:
            raise ValueError("worker resource values must be non-negative")
        if not self.model.strip() or not self.model_version.strip():
            raise ValueError("worker model and model_version must not be empty")
        if not self.sandbox_type.strip() or not self.network_policy.strip():
            raise ValueError("sandbox_type and network_policy must not be empty")


@dataclass(frozen=True)
class WorkerDescriptor:
    worker_id: str
    capabilities: WorkerCapabilities
    reliability: float = 1.0
    latency_ms: int = 0
    cost_units: int = 0
    available: bool = True
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.worker_id.strip():
            raise ValueError("worker_id must not be empty")
        if not 0.0 <= self.reliability <= 1.0:
            raise ValueError("reliability must be between 0 and 1")
        if self.latency_ms < 0 or self.cost_units < 0:
            raise ValueError("latency and cost must be non-negative")


class WorkerRegistry:
    """In-memory capability registry; canonical run state remains elsewhere."""

    def __init__(self, workers: tuple[WorkerDescriptor, ...] = ()) -> None:
        self._workers: dict[str, WorkerDescriptor] = {}
        for worker in workers:
            self.register(worker)

    def register(self, worker: WorkerDescriptor) -> None:
        if worker.worker_id in self._workers:
            raise ValueError(f"worker already registered: {worker.worker_id}")
        self._workers[worker.worker_id] = worker

    def replace(self, worker: WorkerDescriptor) -> None:
        self._workers[worker.worker_id] = worker

    def get(self, worker_id: str) -> WorkerDescriptor:
        try:
            return self._workers[worker_id]
        except KeyError as exc:
            raise KeyError(f"unknown worker: {worker_id}") from exc

    def available(self) -> tuple[WorkerDescriptor, ...]:
        return tuple(sorted((w for w in self._workers.values() if w.available), key=lambda w: w.worker_id))
