from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import RLock
from time import monotonic\nfrom time import monotonic
from typing import Any, Callable

from .contracts import EngineeringPlan


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

    def __post_init__(self) -> None:
        if not self.operation_id.strip() or not self.intent_id.strip() or not self.reason.strip():
            raise ValueError("cross-repository operation identity and reason are required")
        if not self.repository_ids:
            raise ValueError("cross-repository operation must name repositories")


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

    def authorize_operation(self, objective: MultiStepObjective, operation: CrossRepositoryOperation) -> None:\n        authorities = {r.repository_id: r for r in objective.repositories}\n        missing = set(operation.repository_ids) - set(authorities)\n        if missing:\n            raise AdvancedAutonomyError(f\"cross-repository operation names unauthorized repositories: {sorted(missing)}\")\n        if len(operation.repository_ids) > 1 and len(set(operation.repository_ids)) != len(operation.repository_ids):\n            raise AdvancedAutonomyError(\"cross-repository operation contains duplicate repository identities\")\n\n    def authorize_operation(self, objective: MultiStepObjective, operation: CrossRepositoryOperation) -> None:
        authorities = {r.repository_id: r for r in objective.repositories}
        missing = set(operation.repository_ids) - set(authorities)
        if missing:
            raise AdvancedAutonomyError(f"cross-repository operation names unauthorized repositories: {sorted(missing)}")
        if len(operation.repository_ids) > 1 and len(set(operation.repository_ids)) != len(operation.repository_ids):
            raise AdvancedAutonomyError("cross-repository operation contains duplicate repository identities")

    def next_stages(self, objective: MultiStepObjective) -> tuple[AdvancedStage, ...]:
        self.validate(objective)
        checkpoints = {c.stage_id: c for c in self.store.latest(objective.objective_id)}
        completed = {sid for sid, c in checkpoints.items() if c.state is StageState.COMPLETE}
        ready = []
        for stage in objective.stages:
            if stage.stage_id in completed:
                continue
            if all(dep in completed for dep in stage.depends_on):
                ready.append(stage)
        return tuple(ready)

    def execute(
        self,
        objective: MultiStepObjective,
        *,
        execute_stage: Callable[[AdvancedStage, SpecializedWorker | None], Any],
        verify_stage: Callable[[AdvancedStage, Any], tuple[bool, tuple[str, ...]]],
        workers: SpecializedWorkerRegistry | None = None,
    ) -> tuple[StageCheckpoint, ...]:
        self.validate(objective)
        completed = {c.stage_id for c in self.store.latest(objective.objective_id) if c.state is StageState.COMPLETE}
        sequence = max((c.sequence for c in self.store.latest(objective.objective_id)), default=0) + 1
        replans = 0
        attempts = 0
        started = monotonic()
        for stage in objective.stages:
            if monotonic() - started > self.limits.max_wall_clock_seconds:
                raise AdvancedAutonomyError("long-horizon wall-clock bound exhausted")
            attempts += 1
            if attempts > self.limits.max_attempts:
                raise AdvancedAutonomyError("long-horizon attempt bound exhausted")
            if stage.stage_id in completed:
                continue
            if not all(dep in completed for dep in stage.depends_on):
                raise AdvancedAutonomyError(f"stage dependency not complete: {stage.stage_id}")
            worker = workers.select(stage.worker_roles[0]) if workers and stage.worker_roles else None
            self._record(objective.objective_id, stage.stage_id, StageState.RUNNING, sequence, worker.worker_id if worker else None, "stage started")
            sequence += 1
            try:
                result = execute_stage(stage, worker)
            except Exception as exc:
                self._record(objective.objective_id, stage.stage_id, StageState.FAILED, sequence, worker.worker_id if worker else None, str(exc))
                raise
            sequence += 1
            if stage.verification_required:
                self._record(objective.objective_id, stage.stage_id, StageState.VERIFYING, sequence, worker.worker_id if worker else None, "independent stage verification required")
                sequence += 1
                passed, evidence = verify_stage(stage, result)
                if not passed:
                    replans += 1
                    if replans > self.limits.max_replans:
                        self._record(objective.objective_id, stage.stage_id, StageState.BLOCKED, sequence, worker.worker_id if worker else None, "replan bound exhausted")
                        raise AdvancedAutonomyError("long-horizon replan bound exhausted")
                    self._record(objective.objective_id, stage.stage_id, StageState.FAILED, sequence, worker.worker_id if worker else None, "stage verification failed")
                    raise AdvancedAutonomyError(f"stage verification failed: {stage.stage_id}")
            else:
                evidence = ()
            self._record(objective.objective_id, stage.stage_id, StageState.COMPLETE, sequence, worker.worker_id if worker else None, "stage verified and complete", evidence)
            sequence += 1
            completed.add(stage.stage_id)
        if len(completed) != len(objective.stages):
            raise AdvancedAutonomyError("objective remains incomplete")
        return self.store.latest(objective.objective_id)

    def _record(self, objective_id: str, stage_id: str, state: StageState, sequence: int, worker_id: str | None, reason: str, evidence: tuple[str, ...] = ()) -> None:
        self.store.record(StageCheckpoint(objective_id, stage_id, state, sequence, datetime.now(timezone.utc).isoformat(), evidence, worker_id, reason))


def _validate_dag(stages: tuple[AdvancedStage, ...]) -> None:
    ids = [s.stage_id for s in stages]
    if len(ids) != len(set(ids)):
        raise ValueError("stage IDs must be unique")
    known = set(ids)
    for stage in stages:
        if stage.stage_id in stage.depends_on or not set(stage.depends_on).issubset(known):
            raise ValueError(f"invalid stage dependency for {stage.stage_id}")
    visiting: set[str] = set()
    visited: set[str] = set()
    graph = {s.stage_id: s.depends_on for s in stages}

    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("stage dependency graph contains a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in ids:
        visit(node)
