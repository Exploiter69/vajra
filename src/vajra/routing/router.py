from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .contracts import Complexity, ModelIdentity, RoutingDecision, RoutingEvidence, TaskProfile
from .workers import WorkerDescriptor, WorkerRegistry


class RoutingError(RuntimeError):
    """No worker satisfies the task, capability, or budget contract."""


@dataclass(frozen=True)
class _Score:
    worker: WorkerDescriptor
    model_match: int
    capability_count: int


class CapabilityRouter:
    """Deterministic capability-based worker selection.

    The router selects a resource; it never authorizes an operation or changes
    the Policy/Execution/Verification authority boundary.
    """

    def __init__(self, workers: WorkerRegistry) -> None:
        self._workers = workers

    def classify(self, task: str, complexity: Complexity | None = None) -> Complexity:
        if complexity is not None:
            return complexity
        text = task.lower()
        if any(word in text for word in ("debug", "race", "deadlock", "architecture", "root cause")):
            return Complexity.DIFFICULT
        if any(word in text for word in ("code", "refactor", "implement", "integration", "design")):
            return Complexity.COMPLEX
        if any(word in text for word in ("edit", "patch", "rename", "format", "mechanical")):
            return Complexity.MECHANICAL
        return Complexity.SIMPLE

    def select(self, profile: TaskProfile) -> RoutingDecision:
        return self._select(profile, request_id="pending")

    def select_for_request(self, request_id: str, profile: TaskProfile) -> RoutingDecision:
        return self._select(profile, request_id=request_id)

    def select_alternative(
        self,
        request_id: str,
        profile: TaskProfile,
        *,
        excluded_workers: frozenset[str] = frozenset(),
        excluded_models: frozenset[str] = frozenset(),
    ) -> RoutingDecision:
        return self._select(profile, request_id=request_id, excluded_workers=excluded_workers, excluded_models=excluded_models)

    def _select(
        self,
        profile: TaskProfile,
        *,
        request_id: str,
        excluded_workers: frozenset[str] = frozenset(),
        excluded_models: frozenset[str] = frozenset(),
    ) -> RoutingDecision:
        candidates = []
        for worker in self._workers.available():
            cap = worker.capabilities
            if worker.worker_id in excluded_workers or cap.model in excluded_models:
                continue
            if profile.required_capabilities - cap.supported_tasks:
                continue
            if profile.task not in cap.supported_tasks and "*" not in cap.supported_tasks:
                continue
            if profile.preferred_model and cap.model != profile.preferred_model:
                continue
            if worker.cost_units > profile.max_cost_units:
                continue
            candidates.append(worker)
        if not candidates:
            raise RoutingError(f"no available worker satisfies task/capability/budget contract: {profile.task}")

        scored = [
            _Score(
                worker=w,
                model_match=int(profile.preferred_model is not None and w.capabilities.model == profile.preferred_model),
                capability_count=len(profile.required_capabilities & w.capabilities.supported_tasks),
            )
            for w in candidates
        ]
        chosen = sorted(
            scored,
            key=lambda s: (-s.model_match, -s.capability_count, -s.worker.reliability, s.worker.latency_ms, s.worker.cost_units, s.worker.worker_id),
        )[0].worker
        cap = chosen.capabilities
        identity = ModelIdentity(
            provider=chosen.metadata.get("provider", chosen.worker_id),
            model=cap.model,
            version=cap.model_version,
            adapter=chosen.metadata.get("adapter", "worker"),
        )
        evidence = RoutingEvidence(
            evidence_id=str(uuid4()),
            request_id=request_id,
            task=profile.task,
            complexity=profile.complexity,
            candidates=tuple(w.worker_id for w in sorted(candidates, key=lambda w: w.worker_id)),
            selected_worker=chosen.worker_id,
            selected_model=identity,
            reason=f"complexity={profile.complexity.value}; capability-fit; budget<={profile.max_cost_units}",
            budget_cost_units=chosen.cost_units,
        )
        return RoutingDecision(request_id=request_id, complexity=profile.complexity, worker_id=chosen.worker_id, model=identity, strategy_id=profile.strategy_id, evidence=evidence)
