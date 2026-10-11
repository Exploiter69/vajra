from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Iterator

from vajra.domain import (
    ArtifactRef,
    Attempt,
    AttemptState,
    EngineeringRun,
    Event,
    EvidenceRef,
    FinalDisposition,
    RunState,
    Step,
    StepState,
    VerificationResult,
    VerificationStatus,
)
from vajra.runtime.event_store import EventStore
from vajra.runtime.state_store import StateStore


def _json_default(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported durable value: {type(value).__name__}")


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _run_to_json(run: EngineeringRun) -> str:
    return json.dumps(
        {
            "run_id": run.run_id,
            "objective": run.objective,
            "repository_id": run.repository_id,
            "base_revision": run.base_revision,
            "acceptance_criteria": list(run.acceptance_criteria),
            "policy_id": run.policy_id,
            "policy_version": run.policy_version,
            "budget_id": run.budget_id,
            "state": run.state.value,
            "created_by": run.created_by,
            "workspace_id": run.workspace_id,
            "current_step_id": run.current_step_id,
            "final_disposition": (
                run.final_disposition.value if run.final_disposition else None
            ),
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
            "steps": [
                {
                    "step_id": step.step_id,
                    "run_id": step.run_id,
                    "name": step.name,
                    "state": step.state.value,
                    "attempts": [
                        {
                            "attempt_id": attempt.attempt_id,
                            "step_id": attempt.step_id,
                            "run_id": attempt.run_id,
                            "state": attempt.state.value,
                            "worker_id": attempt.worker_id,
                            "lease_id": attempt.lease_id,
                            "lease_expiry": attempt.lease_expiry.isoformat() if attempt.lease_expiry else None,
                            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
                            "finished_at": attempt.finished_at.isoformat() if attempt.finished_at else None,
                            "error": attempt.error,
                        }
                        for attempt in step.attempts
                    ],
                }
                for step in run.steps
            ],
            "artifacts": [
                {
                    "artifact_id": item.artifact_id,
                    "kind": item.kind,
                    "location": item.location,
                    "sha256": item.sha256,
                }
                for item in run.artifacts
            ],
            "verification_results": [
                {
                    "verification_id": item.verification_id,
                    "run_id": item.run_id,
                    "status": item.status.value,
                    "checks": list(item.checks),
                    "evidence_refs": [
                        {
                            "evidence_id": evidence.evidence_id,
                            "kind": evidence.kind,
                            "location": evidence.location,
                            "digest": evidence.digest,
                        }
                        for evidence in item.evidence_refs
                    ],
                    "verifier_version": item.verifier_version,
                }
                for item in run.verification_results
            ],
        },
        sort_keys=True,
        default=_json_default,
    )


def _run_from_json(payload: str) -> EngineeringRun:
    data = json.loads(payload)
    steps = [
        Step(
            step_id=item["step_id"],
            run_id=item["run_id"],
            name=item["name"],
            state=StepState(item["state"]),
            attempts=[
                Attempt(
                    attempt_id=attempt["attempt_id"],
                    step_id=attempt["step_id"],
                    run_id=attempt["run_id"],
                    state=AttemptState(attempt["state"]),
                    worker_id=attempt["worker_id"],
                    lease_id=attempt["lease_id"],
                    lease_expiry=_datetime(attempt["lease_expiry"]),
                    started_at=_datetime(attempt["started_at"]),
                    finished_at=_datetime(attempt["finished_at"]),
                    error=attempt["error"],
                )
                for attempt in item["attempts"]
            ],
        )
        for item in data["steps"]
    ]
    artifacts = [ArtifactRef(**item) for item in data["artifacts"]]
    verification_results = [
        VerificationResult(
            verification_id=item["verification_id"],
            run_id=item["run_id"],
            status=VerificationStatus(item["status"]),
            checks=tuple(item["checks"]),
            evidence_refs=tuple(EvidenceRef(**ref) for ref in item["evidence_refs"]),
            verifier_version=item["verifier_version"],
        )
        for item in data["verification_results"]
    ]
    return EngineeringRun(
        run_id=data["run_id"],
        objective=data["objective"],
        repository_id=data["repository_id"],
        base_revision=data["base_revision"],
        acceptance_criteria=tuple(data["acceptance_criteria"]),
        policy_id=data["policy_id"],
        policy_version=data["policy_version"],
        budget_id=data["budget_id"],
        state=RunState(data["state"]),
        created_by=data["created_by"],
        workspace_id=data["workspace_id"],
        current_step_id=data["current_step_id"],
        final_disposition=(
            FinalDisposition(data["final_disposition"])
            if data["final_disposition"] else None
        ),
        created_at=datetime.fromisoformat(data["created_at"]),
        updated_at=datetime.fromisoformat(data["updated_at"]),
        steps=steps,
        artifacts=artifacts,
        verification_results=verification_results,
    )


def _event_to_json(event: Event) -> str:
    return json.dumps(
        {
            "event_id": event.event_id,
            "run_id": event.run_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "sequence": event.sequence,
            "step_id": event.step_id,
            "attempt_id": event.attempt_id,
            "worker_id": event.worker_id,
            "correlation_id": event.correlation_id,
            "payload": event.payload,
        },
        sort_keys=True,
        default=_json_default,
    )


def _event_from_json(payload: str) -> Event:
    data = json.loads(payload)
    data["timestamp"] = datetime.fromisoformat(data["timestamp"])
    return Event(**data)


class SQLiteRunStore(StateStore, EventStore):
    """Local canonical run and event store using one transactional SQLite DB.

    Pass the same instance as both RunManager's state_store and event_store.
    RunManager's transaction boundary then commits state and lifecycle event
    together. SQLite is from the Python standard library; no service is needed.
    """

    def __init__(self, database_path: str | Path) -> None:
        self._path = str(database_path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._transaction_depth = 0
        self._connection = sqlite3.connect(
            self._path, timeout=30, check_same_thread=False
        )
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                payload TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence),
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            );
            """
        )
        self._connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Atomically commit/rollback run state and events for one operation."""
        with self._lock:
            outermost = self._transaction_depth == 0
            if outermost:
                self._connection.execute("BEGIN IMMEDIATE")
            self._transaction_depth += 1
            try:
                yield
            except Exception:
                self._transaction_depth -= 1
                if outermost:
                    self._connection.rollback()
                raise
            else:
                self._transaction_depth -= 1
                if outermost:
                    self._connection.commit()

    def _commit_if_standalone(self) -> None:
        if self._transaction_depth == 0:
            self._connection.commit()

    def create_run(self, run: EngineeringRun) -> EngineeringRun:
        with self._lock:
            try:
                self._connection.execute(
                    "INSERT INTO runs(run_id, payload) VALUES (?, ?)",
                    (run.run_id, _run_to_json(run)),
                )
            except sqlite3.IntegrityError as exc:
                if self._connection.execute(
                    "SELECT 1 FROM runs WHERE run_id = ?", (run.run_id,)
                ).fetchone():
                    raise ValueError(f"Run already exists: {run.run_id}") from exc
                raise
            self._commit_if_standalone()
            return _run_from_json(_run_to_json(run))

    def get_run(self, run_id: str) -> EngineeringRun:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Run not found: {run_id}")
            return _run_from_json(row[0])

    def save_run(self, run: EngineeringRun) -> EngineeringRun:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE runs SET payload = ? WHERE run_id = ?",
                (_run_to_json(run), run.run_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Run not found: {run.run_id}")
            self._commit_if_standalone()
            return _run_from_json(_run_to_json(run))

    def append(self, event: Event) -> Event:
        with self._lock:
            expected = self.next_sequence(event.run_id)
            if event.sequence != expected:
                raise ValueError(
                    f"Invalid event sequence for run {event.run_id}: "
                    f"expected {expected}, got {event.sequence}"
                )
            self._connection.execute(
                "INSERT INTO events(run_id, sequence, event_id, payload) "
                "VALUES (?, ?, ?, ?)",
                (event.run_id, event.sequence, event.event_id, _event_to_json(event)),
            )
            self._commit_if_standalone()
            return _event_from_json(_event_to_json(event))

    def list_for_run(self, run_id: str) -> tuple[Event, ...]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM events WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()
            return tuple(_event_from_json(row[0]) for row in rows)

    def next_sequence(self, run_id: str) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            return int(row[0])

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteRunStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
