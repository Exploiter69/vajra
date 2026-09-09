from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from vajra.domain import (
    Attempt,
    AttemptState,
    EngineeringRun,
    FinalDisposition,
    Event,
    RunState,
    Step,
    StepState,
    transition_run,
)

from vajra.runtime.event_store import EventStore, InMemoryEventStore
from vajra.runtime.lease import LeaseManager, WorkerLease
from vajra.runtime.state_store import InMemoryStateStore, StateStore


@dataclass(frozen=True)
class RunSnapshot:
    run: EngineeringRun


class RunManager:
    """
    Application-level owner of Engineering Run lifecycle.

    Canonical state persistence is delegated to StateStore.
    Append-only lifecycle history is delegated to EventStore.

    This layer deliberately does not execute commands, call models, or
    communicate with workers.

    Lifecycle mutations are rollback-safe against persistence failures in
    the current application/in-memory boundary. Durable atomicity belongs
    to the future DurableRuntime implementation.
    """

    def __init__(
        self,
        state_store: StateStore | None = None,
        event_store: EventStore | None = None,
    ) -> None:
        self._state_store = state_store or InMemoryStateStore()
        self._event_store = event_store or InMemoryEventStore()
        self._lock = RLock()
        self._lease_manager = LeaseManager()

    def create_run(self, run: EngineeringRun) -> EngineeringRun:
        with self._lock:
            result = self._state_store.create_run(run)

            try:
                self._record_event(
                    run_id=run.run_id,
                    event_type="RUN_CREATED",
                )
            except Exception:
                self._remove_created_run(run.run_id)
                raise

            return result

    def get_run(self, run_id: str) -> EngineeringRun:
        with self._lock:
            return self._state_store.get_run(run_id)

    def transition(self, run_id: str, target: RunState) -> EngineeringRun:
        with self._lock:
            run = self.get_run(run_id)
            previous = deepcopy(run)

            previous_state = run.state
            transition_run(run, target)

            try:
                result = self._state_store.save_run(run)

                self._record_event(
                    run_id=run_id,
                    event_type="RUN_STATE_CHANGED",
                    payload={
                        "from": previous_state.value,
                        "to": target.value,
                    },
                )

                return result
            except Exception:
                self._state_store.save_run(previous)
                raise

    def abort_run(self, run_id: str, reason: str) -> EngineeringRun:
        with self._lock:
            run = self.get_run(run_id)
            previous = deepcopy(run)

            if run.state not in {RunState.RECOVERING, RunState.WAITING_HUMAN}:
                raise ValueError(
                    f"Run cannot be aborted from state {run.state.value}: {run_id}"
                )

            transition_run(run, RunState.ABORTED)
            run.final_disposition = FinalDisposition.ABORTED

            try:
                result = self._state_store.save_run(run)

                self._record_event(
                    run_id=run_id,
                    event_type="RUN_ABORTED",
                    payload={"reason": reason},
                )

                return result
            except Exception:
                self._state_store.save_run(previous)
                raise

    def add_step(self, run_id: str, step_id: str, name: str) -> Step:
        with self._lock:
            run = self.get_run(run_id)
            previous = deepcopy(run)

            if any(step.step_id == step_id for step in run.steps):
                raise ValueError(f"Step already exists: {step_id}")

            step = Step(
                step_id=step_id,
                run_id=run_id,
                name=name,
            )

            run.steps.append(step)
            run.current_step_id = step_id

            try:
                self._state_store.save_run(run)

                self._record_event(
                    run_id=run_id,
                    event_type="STEP_CREATED",
                    step_id=step_id,
                    payload={"name": name},
                )

                return step
            except Exception:
                self._state_store.save_run(previous)
                raise

    def start_attempt(
        self,
        run_id: str,
        step_id: str,
        attempt_id: str,
        worker_id: str,
        lease_id: str,
        *,
        lease_ttl_seconds: int = 60,
        now: datetime | None = None,
    ) -> Attempt:
        with self._lock:
            run = self.get_run(run_id)
            previous = deepcopy(run)
            step = self._get_step(run, step_id)

            if any(
                attempt.attempt_id == attempt_id
                for attempt in step.attempts
            ):
                raise ValueError(f"Attempt already exists: {attempt_id}")

            lease = self._lease_manager.acquire(
                attempt_id,
                worker_id,
                lease_id,
                lease_ttl_seconds,
                now=now,
            )

            attempt = Attempt(
                attempt_id=attempt_id,
                step_id=step_id,
                run_id=run_id,
                state=AttemptState.RUNNING,
                worker_id=worker_id,
                lease_id=lease.lease_id,
                lease_expiry=lease.lease_expiry,
            )

            step.attempts.append(attempt)
            step.state = StepState.RUNNING

            try:
                self._state_store.save_run(run)

                self._record_event(
                    run_id=run_id,
                    event_type="ATTEMPT_STARTED",
                    step_id=step_id,
                    attempt_id=attempt_id,
                    worker_id=worker_id,
                    payload={
                        "lease_id": lease.lease_id,
                        "fencing_token": lease.fencing_token,
                        "lease_expiry": lease.lease_expiry.isoformat(),
                    },
                )

                return attempt
            except Exception:
                self._state_store.save_run(previous)
                self._lease_manager.release(
                    attempt_id,
                    worker_id,
                    lease.lease_id,
                    lease.fencing_token,
                    now=now,
                )
                raise

    def get_lease(self, attempt_id: str) -> WorkerLease | None:
        with self._lock:
            return self._lease_manager.get(attempt_id)

    def fail_attempt(
        self,
        run_id: str,
        step_id: str,
        attempt_id: str,
        error: str,
    ) -> Attempt:
        with self._lock:
            run = self.get_run(run_id)
            previous = deepcopy(run)
            step = self._get_step(run, step_id)
            attempt = self._get_attempt(step, attempt_id)

            if attempt.state is not AttemptState.RUNNING:
                raise ValueError(
                    f"Attempt is not running: {attempt.attempt_id}"
                )

            attempt.state = AttemptState.FAILED
            attempt.error = error
            attempt.lease_id = None
            attempt.lease_expiry = None

            step.state = StepState.RECOVERING

            try:
                self._state_store.save_run(run)

                self._record_event(
                    run_id=run_id,
                    event_type="ATTEMPT_FAILED",
                    step_id=step_id,
                    attempt_id=attempt_id,
                    worker_id=attempt.worker_id,
                    payload={"error": error},
                )

                return attempt
            except Exception:
                self._state_store.save_run(previous)
                raise

    def recover_run(self, run_id: str) -> EngineeringRun:
        with self._lock:
            run = self.get_run(run_id)

            if run.state is not RunState.RECOVERING:
                previous = deepcopy(run)
                previous_state = run.state
                transition_run(run, RunState.RECOVERING)

                try:
                    self._state_store.save_run(run)

                    self._record_event(
                        run_id=run_id,
                        event_type="RUN_RECOVERING",
                        payload={
                            "from": previous_state.value,
                            "to": RunState.RECOVERING.value,
                        },
                    )

                    return run
                except Exception:
                    self._state_store.save_run(previous)
                    raise

            self._state_store.save_run(run)
            return run

    def snapshot(self, run_id: str) -> RunSnapshot:
        with self._lock:
            return RunSnapshot(run=deepcopy(self.get_run(run_id)))

    def events(self, run_id: str) -> tuple[Event, ...]:
        with self._lock:
            return self._event_store.list_for_run(run_id)

    def _record_event(
        self,
        run_id: str,
        event_type: str,
        *,
        step_id: str | None = None,
        attempt_id: str | None = None,
        worker_id: str | None = None,
        correlation_id: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> Event:
        event = Event(
            event_id=str(uuid4()),
            run_id=run_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            sequence=self._event_store.next_sequence(run_id),
            step_id=step_id,
            attempt_id=attempt_id,
            worker_id=worker_id,
            correlation_id=correlation_id,
            payload=payload or {},
        )

        return self._event_store.append(event)

    def _remove_created_run(self, run_id: str) -> None:
        if isinstance(self._state_store, InMemoryStateStore):
            self._state_store._runs.pop(run_id, None)

    @staticmethod
    def _get_step(run: EngineeringRun, step_id: str) -> Step:
        for step in run.steps:
            if step.step_id == step_id:
                return step

        raise KeyError(f"Step not found: {step_id}")

    @staticmethod
    def _get_attempt(step: Step, attempt_id: str) -> Attempt:
        for attempt in step.attempts:
            if attempt.attempt_id == attempt_id:
                return attempt

        raise KeyError(f"Attempt not found: {attempt_id}")
