from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone

from vajra.domain import AttemptState, EngineeringRun
from vajra.runtime.event_store import EventStore, InMemoryEventStore
from vajra.runtime.lease import LeaseManager
from vajra.runtime.state_store import InMemoryStateStore, StateStore
from vajra.runtime.worker_protocol import WorkerResult


@dataclass(frozen=True)
class WorkerExecutionIdentity:
    run_id: str
    step_id: str
    attempt_id: str
    worker_id: str
    lease_id: str
    fencing_token: int


class WorkerResultAcceptor:
    """
    Canonical acceptance boundary for disposable worker results.

    A WorkerResult is only a report. It becomes authoritative only after
    VAJRA validates the worker execution identity against the active lease
    and fencing authority.

    This reference implementation uses the existing StateStore/EventStore
    abstractions. Distributed durability belongs to the future worker
    infrastructure.
    """

    def __init__(
        self,
        lease_manager: LeaseManager,
        state_store: StateStore | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        self._lease_manager = lease_manager
        self._state_store = state_store or InMemoryStateStore()
        self._event_store = event_store or InMemoryEventStore()

    def accept(
        self,
        identity: WorkerExecutionIdentity,
        result: WorkerResult,
        *,
        now: datetime | None = None,
    ) -> EngineeringRun:
        self._lease_manager.validate(
            identity.attempt_id,
            identity.worker_id,
            identity.lease_id,
            identity.fencing_token,
            now=now,
        )

        run = self._state_store.get_run(identity.run_id)
        previous = deepcopy(run)

        step = self._get_step(run, identity.step_id)
        attempt = self._get_attempt(step, identity.attempt_id)

        if attempt.state is not AttemptState.RUNNING:
            raise ValueError(
                f"Attempt is not running: {attempt.attempt_id}"
            )

        if attempt.worker_id != identity.worker_id:
            raise PermissionError("Worker does not match attempt owner")

        if attempt.lease_id != identity.lease_id:
            raise PermissionError("Lease does not match attempt")

        if result.status.upper() in {"SUCCEEDED", "SUCCESS", "COMPLETED"}:
            attempt.state = AttemptState.SUCCEEDED
            event_type = "WORKER_RESULT_ACCEPTED"
        elif result.status.upper() in {"FAILED", "FAILURE"}:
            attempt.state = AttemptState.FAILED
            attempt.error = "; ".join(result.errors) or "Worker reported failure"
            event_type = "WORKER_RESULT_FAILED"
        else:
            raise ValueError(f"Unsupported worker result status: {result.status}")

        attempt.finished_at = now or datetime.now(timezone.utc)
        attempt.lease_id = None
        attempt.lease_expiry = None

        run.artifacts.extend(result.artifacts)

        try:
            self._state_store.save_run(run)

            self._event_store.append(
                self._make_event(
                    run=run,
                    event_type=event_type,
                    identity=identity,
                    result=result,
                )
            )
        except Exception:
            self._state_store.save_run(previous)
            raise

        # Canonical state and event history are now authoritative. Lease
        # cleanup is deliberately outside the rollback boundary: a cleanup
        # failure must never undo an already-persisted worker result.
        # Canonical state and event history are already authoritative.
        # Lease cleanup is outside that rollback boundary. If cleanup fails,
        # preserve the accepted result and surface the operational failure so
        # recovery can reconcile the lease.
        self._lease_manager.release(
            identity.attempt_id,
            identity.worker_id,
            identity.lease_id,
            identity.fencing_token,
            now=now,
        )

        return run

    def _make_event(
        self,
        *,
        run: EngineeringRun,
        event_type: str,
        identity: WorkerExecutionIdentity,
        result: WorkerResult,
    ):
        from uuid import uuid4
        from vajra.domain import Event

        return Event(
            event_id=str(uuid4()),
            run_id=run.run_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            sequence=self._event_store.next_sequence(run.run_id),
            step_id=identity.step_id,
            attempt_id=identity.attempt_id,
            worker_id=identity.worker_id,
            payload={
                "status": result.status,
                "structured_result": result.structured_result,
                "logs": list(result.logs),
                "usage": result.usage,
                "errors": list(result.errors),
                "evidence_refs": [
                    {
                        "evidence_id": ref.evidence_id,
                        "kind": ref.kind,
                        "location": ref.location,
                        "digest": ref.digest,
                    }
                    for ref in result.evidence_refs
                ],
            },
        )

    @staticmethod
    def _get_step(run: EngineeringRun, step_id: str):
        for step in run.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(f"Step not found: {step_id}")

    @staticmethod
    def _get_attempt(step, attempt_id: str):
        for attempt in step.attempts:
            if attempt.attempt_id == attempt_id:
                return attempt
        raise KeyError(f"Attempt not found: {attempt_id}")
