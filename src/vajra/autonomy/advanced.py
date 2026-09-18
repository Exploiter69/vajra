from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import RLock
from time import monotonic
from typing import Any, Callable


class AdvancedAutonomyError(RuntimeError):
    pass


class StageState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    VERIFYING = "VERIFYING"
    COMPLETE = "COMPLETE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class WorkerSpecialization(str, Enum):
    CODING = "coding"
    TESTING = "testing"
    SECURITY = "security"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"


@dataclass(frozen=True)
class RepositoryAuthority:
    repository_id: str
    workspace_id: str
    base_revision: str
    allowed_operations: frozenset[str]

    def __post_init__(self) -> None:
        if not self.repository_id.strip() or not self.workspace_id.strip() or not self.base_revision.strip():
            raise ValueError("repository authority identifiers must not be empty")
        if not self.allowed_operations:
            raise ValueError("repository authority must allow at least one operation")


@dataclass(frozen=True)
class CrossRepositoryOperation:
    operation_id: str
    intent_id: str
    repository_ids: tuple[str, ...]
    reason: str
    operations: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.operation_id.strip() or not self.intent_id.strip() or not self.reason.strip():
            raise ValueError("cross-repository operation identity and reason are required")
        if not self.repository_ids:
            raise ValueError("cross-repository operation must name repositories")
        if not self.operations:
            raise ValueError("cross-repository operation must name requested operations")


@dataclass(frozen=True)
class AdvancedStage:
    stage_id: str
    name: str
    objective: str
    depends_on: tuple[str, ...] = ()
    worker_roles: tuple[WorkerSpecialization, ...] = ()
    required_operations: frozenset[str] = frozenset()
    verification_required: bool = True

    def __post_init__(self) -> None:
        if not self.stage_id.strip() or not self.name.strip() or not self.objective.strip():
            raise ValueError("stage identity and objective are required")


@dataclass(frozen=True)
class MultiStepObjective:
    objective_id: str
    objective: str
    stages: tuple[AdvancedStage, ...]
    repositories: tuple[RepositoryAuthority, ...]

    def __post_init__(self) -> None:
        if not self.objective_id.strip() or not self.objective.strip() or not self.stages:
            raise ValueError("objective must have identity, text, and at least one stage")
        _validate_dag(self.stages)
        repo_ids = {r.repository_id for r in self.repositories}
        if not repo_ids:
            raise ValueError("multi-step objective must declare repository authority")
        for stage in self.stages:
            if not stage.required_operations.issubset(set().union(*(r.allowed_operations for r in self.repositories))):
                raise ValueError(f"stage {stage.stage_id} requests an unauthorized operation")


@dataclass(frozen=True)
class SpecializedWorker:
    worker_id: str
    role: WorkerSpecialization
    capabilities: frozenset[str] = frozenset()
    available: bool = True

    def __post_init__(self) -> None:
        if not self.worker_id.strip():
            raise ValueError("worker_id must not be empty")


class SpecializedWorkerRegistry:
    """Role registry; selection is singular and policy remains authoritative."""

    def __init__(self, workers: tuple[SpecializedWorker, ...] = ()) -> None:
        self._workers: dict[str, SpecializedWorker] = {}
        for worker in workers:
            self.register(worker)

    def register(self, worker: SpecializedWorker) -> None:
        if worker.worker_id in self._workers:
            raise ValueError(f"worker already registered: {worker.worker_id}")
        self._workers[worker.worker_id] = worker

    def select(self, role: WorkerSpecialization, capabilities: frozenset[str] = frozenset()) -> SpecializedWorker:
        candidates = [w for w in self._workers.values() if w.available and w.role is role and capabilities.issubset(w.capabilities)]
        if not candidates:
            raise AdvancedAutonomyError(f"no available specialized worker for role {role.value}")
        return sorted(candidates, key=lambda w: w.worker_id)[0]


@dataclass(frozen=True)
class LongHorizonLimits:
    max_stages: int = 64
    max_replans: int = 32
    max_model_calls: int = 256
    max_attempts: int = 256
    max_wall_clock_seconds: int = 7 * 24 * 3600

    def __post_init__(self) -> None:
        if any(v <= 0 for v in (self.max_stages, self.max_replans, self.max_model_calls, self.max_attempts, self.max_wall_clock_seconds)):
            raise ValueError("long-horizon limits must be positive")


@dataclass(frozen=True)
class StageCheckpoint:
    objective_id: str
    stage_id: str
    state: StageState
    sequence: int
    recorded_at: str
    evidence_refs: tuple[str, ...] = ()
    worker_id: str | None = None
    reason: str = ""


class AdvancedRunStore:
    """Durable append-only stage journal for resumable long-horizon objectives."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = RLock()
        self._sequence = 1
        self._state: dict[tuple[str, str], StageCheckpoint] = {}
        self._load()

    def record(self, checkpoint: StageCheckpoint) -> StageCheckpoint:
        with self._lock:
            key = (checkpoint.objective_id, checkpoint.stage_id)
            existing = self._state.get(key)
            if existing and checkpoint.sequence <= existing.sequence:
                raise AdvancedAutonomyError("checkpoint sequence must increase")
            self._append({
                "objective_id": checkpoint.objective_id, "stage_id": checkpoint.stage_id,
                "state": checkpoint.state.value, "sequence": checkpoint.sequence,
                "recorded_at": checkpoint.recorded_at, "evidence_refs": list(checkpoint.evidence_refs),
                "worker_id": checkpoint.worker_id, "reason": checkpoint.reason,
            })
            return self._state[key]

    def latest(self, objective_id: str) -> tuple[StageCheckpoint, ...]:
        with self._lock:
            return tuple(sorted((v for (oid, _), v in self._state.items() if oid == objective_id), key=lambda x: x.stage_id))

    def _append(self, record: dict[str, Any]) -> None:
        record["journal_sequence"] = self._sequence
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._apply(record)
        self._sequence += 1

    def _apply(self, record: dict[str, Any]) -> None:
        checkpoint = StageCheckpoint(
            record["objective_id"], record["stage_id"], StageState(record["state"]),
            int(record["sequence"]), record["recorded_at"], tuple(record.get("evidence_refs", ())),
            record.get("worker_id"), record.get("reason", ""),
        )
        self._state[(checkpoint.objective_id, checkpoint.stage_id)] = checkpoint

    def _load(self) -> None:
        if not self._path.exists():
            return
        expected = 1
        with self._path.open("r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if record.get("journal_sequence") != expected:
                    raise AdvancedAutonomyError(f"invalid advanced journal sequence at line {line_no}")
                self._apply(record)
                expected += 1
        self._sequence = expected


class AdvancedAutonomyEngine:
    """Coordinates multi-step objectives without becoming an execution authority.

    The supplied execute/verify callbacks must themselves cross VAJRA's normal
    policy, execution-broker, and independent-verification boundaries.
    """

    VERSION = "advanced-autonomy-v1"

    def __init__(self, *, store: AdvancedRunStore, limits: LongHorizonLimits | None = None) -> None:
        self.store = store
        self.limits = limits or LongHorizonLimits()

    def validate(self, objective: MultiStepObjective) -> None:
        if len(objective.stages) > self.limits.max_stages:
            raise AdvancedAutonomyError("objective exceeds maximum stage count")

    def next_stages(self, objective: MultiStepObjective) -> tuple[AdvancedStage, ...]:
        self.validate(objective)
        completed = {
            checkpoint.stage_id
            for checkpoint in self.store.latest(objective.objective_id)
            if checkpoint.state is StageState.COMPLETE
        }
        return tuple(
            stage for stage in _topological_order(objective.stages)
            if stage.stage_id not in completed
            and set(stage.depends_on).issubset(completed)
        )

    def authorize_operation(
        self,
        objective: MultiStepObjective,
        operation: CrossRepositoryOperation,
    ) -> None:
        self.validate(objective)
        authorities = {repo.repository_id: repo for repo in objective.repositories}
        requested_repositories = set(operation.repository_ids)
        if len(requested_repositories) != len(operation.repository_ids):
            raise AdvancedAutonomyError("cross-repository operation contains duplicate repositories")
        if not requested_repositories.issubset(authorities):
            raise AdvancedAutonomyError("cross-repository operation names unauthorized repositories")
        unauthorized = {
            repo_id
            for repo_id in operation.repository_ids
            if not operation.operations.issubset(authorities[repo_id].allowed_operations)
        }
        if unauthorized:
            raise AdvancedAutonomyError(
                f"unauthorized operations for repositories: {sorted(unauthorized)}"
            )

    def execute(
        self,
        objective: MultiStepObjective,
        *,
        execute_stage: Callable[[AdvancedStage, Any], Any],
        verify_stage: Callable[[AdvancedStage, Any], tuple[bool, tuple[str, ...]]],
        worker_registry: SpecializedWorkerRegistry | None = None,
        worker_capabilities: frozenset[str] = frozenset(),
    ) -> tuple[StageCheckpoint, ...]:
        self.validate(objective)
        started = monotonic()
        attempts = 0
        model_calls = 0
        latest = {c.stage_id: c for c in self.store.latest(objective.objective_id)}
        while True:
            if monotonic() - started >= self.limits.max_wall_clock_seconds:
                raise AdvancedAutonomyError("long-horizon wall-clock bound exceeded")
            ready = self.next_stages(objective)
            if not ready:
                if len(latest) == len(objective.stages) and all(
                    c.state is StageState.COMPLETE for c in latest.values()
                ):
                    return self.store.latest(objective.objective_id)
                raise AdvancedAutonomyError("no ready stage; objective is blocked")
            for stage in ready:
                attempts += 1
                if attempts > self.limits.max_attempts:
                    raise AdvancedAutonomyError("long-horizon attempt bound exceeded")
                worker = None
                if len(stage.worker_roles) > 1:
                    raise AdvancedAutonomyError(
                        f"stage {stage.stage_id} requires multiple worker roles"
                    )
                if stage.worker_roles:
                    if worker_registry is None:
                        raise AdvancedAutonomyError(
                            f"stage {stage.stage_id} requires a specialized worker"
                        )
                    worker = worker_registry.select(stage.worker_roles[0], worker_capabilities)
                running = _checkpoint(
                    objective.objective_id, stage, StageState.RUNNING,
                    _next_sequence(latest), worker
                )
                self.store.record(running)
                latest[stage.stage_id] = running
                try:
                    result = execute_stage(stage, worker)
                    model_calls += 1
                    if model_calls > self.limits.max_model_calls:
                        raise AdvancedAutonomyError("long-horizon model-call bound exceeded")
                    verifying = _checkpoint(
                        objective.objective_id, stage, StageState.VERIFYING,
                        _next_sequence(latest), worker
                    )
                    self.store.record(verifying)
                    latest[stage.stage_id] = verifying
                    verified, evidence = verify_stage(stage, result)
                    if not verified or not evidence:
                        failed = _checkpoint(
                            objective.objective_id, stage, StageState.FAILED,
                            _next_sequence(latest), worker,
                            reason="independent verification failed",
                        )
                        self.store.record(failed)
                        latest[stage.stage_id] = failed
                        raise AdvancedAutonomyError(
                            f"stage {stage.stage_id} verification failed"
                        )
                    complete = _checkpoint(
                        objective.objective_id, stage, StageState.COMPLETE,
                        _next_sequence(latest), worker,
                        evidence_refs=tuple(evidence),
                    )
                    self.store.record(complete)
                    latest[stage.stage_id] = complete
                except AdvancedAutonomyError:
                    raise
                except Exception as exc:
                    failed = _checkpoint(
                        objective.objective_id, stage, StageState.FAILED,
                        _next_sequence(latest), worker,
                        reason=f"execution failed: {exc}",
                    )
                    self.store.record(failed)
                    latest[stage.stage_id] = failed
                    raise AdvancedAutonomyError(
                        f"stage {stage.stage_id} execution failed"
                    ) from exc
            if len(latest) == len(objective.stages) and all(
                c.state is StageState.COMPLETE for c in latest.values()
            ):
                return self.store.latest(objective.objective_id)


def _topological_order(stages: tuple[AdvancedStage, ...]) -> tuple[AdvancedStage, ...]:
    by_id = {stage.stage_id: stage for stage in stages}
    remaining = set(by_id)
    completed: set[str] = set()
    ordered: list[AdvancedStage] = []
    while remaining:
        ready = sorted(
            (sid for sid in remaining if set(by_id[sid].depends_on).issubset(completed)),
            key=str,
        )
        if not ready:
            raise AdvancedAutonomyError("stage dependency graph contains a cycle")
        for sid in ready:
            ordered.append(by_id[sid])
            completed.add(sid)
            remaining.remove(sid)
    return tuple(ordered)


def _next_sequence(latest: dict[str, StageCheckpoint]) -> int:
    return max((checkpoint.sequence for checkpoint in latest.values()), default=0) + 1


def _checkpoint(
    objective_id: str,
    stage: AdvancedStage,
    state: StageState,
    sequence: int,
    worker: SpecializedWorker | None,
    *,
    evidence_refs: tuple[str, ...] = (),
    reason: str = "",
) -> StageCheckpoint:
    return StageCheckpoint(
        objective_id=objective_id,
        stage_id=stage.stage_id,
        state=state,
        sequence=sequence,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        evidence_refs=evidence_refs,
        worker_id=worker.worker_id if worker else None,
        reason=reason,
    )

def _validate_dag(stages: tuple[AdvancedStage, ...]) -> None:
    ids = [stage.stage_id for stage in stages]
    if len(ids) != len(set(ids)):
        raise ValueError("stage IDs must be unique")
    known = set(ids)
    for stage in stages:
        if any(dep not in known for dep in stage.depends_on):
            raise ValueError(f"stage {stage.stage_id!r} has an unknown dependency")
        if stage.stage_id in stage.depends_on:
            raise ValueError(f"stage {stage.stage_id!r} cannot depend on itself")
    remaining = set(ids)
    done: set[str] = set()
    while remaining:
        ready = {sid for sid in remaining if set(next(s for s in stages if s.stage_id == sid).depends_on).issubset(done)}
        if not ready:
            raise ValueError("stage dependency graph contains a cycle")
        done.update(ready)
        remaining -= ready
