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

from vajra.control.completion import CompletionGate
from vajra.control.transition_authority import (
    TransitionActor,
    TransitionAuthority,
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
        self._transition_authority = TransitionAuthority()
        self._completion_gate = CompletionGate()

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

    def transition(
        self,
        run_id: str,
        target: RunState,
        actor: TransitionActor,
        *,
        reason: str = "",
    ) -> EngineeringRun:
        with self._lock:
            run = self.get_run(run_id)
            previous = deepcopy(run)

            self._transition_authority.assert_authorized(
                run,
                target,
                actor,
                reason=reason,
            )

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

    def complete_run(
        self,
        run_id: str,
        acceptance,
        *,
        artifact_refs: tuple[str, ...],
        verification_refs: tuple[str, ...],
        policy_approved: bool,
        actor: TransitionActor,
        reason: str = "",
    ) -> EngineeringRun:
        """Complete a Run only after the evidence-bound completion gate passes."""
        with self._lock:
            self._completion_gate.authorize(
                acceptance,
                artifact_refs=artifact_refs,
                verification_refs=verification_refs,
                policy_approved=policy_approved,
            )

            run = self.get_run(run_id)
            previous = deepcopy(run)
            self._transition_authority.assert_authorized(
                run,
                RunState.COMPLETE,
                actor,
                reason=reason or "completion prerequisites satisfied",
            )

            transition_run(run, RunState.COMPLETE)
            # FinalDisposition uses SUCCESS as the canonical completed outcome.
            run.final_disposition = FinalDisposition.SUCCESS

            try:
                result = self._state_store.save_run(run)
                self._record_event(
                    run_id=run_id,
                    event_type="RUN_COMPLETED",
                    payload={
                        "acceptance_criteria_id": acceptance.criteria_id,
                        "acceptance_criteria_version": acceptance.criteria_version,
                        "artifact_refs": list(artifact_refs),
                        "verification_refs": list(verification_refs),
                    },
                )
                return result
            except Exception:
                self._state_store.save_run(previous)
                raise

    def abort_run(
        self,
        run_id: str,
        reason: str,
        actor: TransitionActor,
    ) -> EngineeringRun:
        with self._lock:
            run = self.get_run(run_id)
            previous = deepcopy(run)

            if run.state not in {RunState.RECOVERING, RunState.WAITING_HUMAN}:
                raise ValueError(
                    f"Run cannot be aborted from state {run.state.value}: {run_id}"
                )

            self._transition_authority.assert_authorized(
                run,
                RunState.ABORTED,
                actor,
                reason=reason,
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

    def recover_run(self, run_id: str) -> EngineeringRun:
        with self._lock:
            run = self.get_run(run_id)
            previous = deepcopy(run)

            if run.state not in {
                RunState.FAILED,
                RunState.EXECUTING,
                RunState.VERIFYING,
                RunState.CANDIDATE,
                RunState.PROMOTION,
            }:
                return run

            self._transition_authority.assert_authorized(
                run,
                RunState.RECOVERING,
                TransitionActor.RECOVERY,
                reason="recovery requested",
            )
            transition_run(run, RunState.RECOVERING)

            try:
                result = self._state_store.save_run(run)
                self._record_event(
                    run_id=run_id,
                    event_type="RUN_RECOVERING",
                )
                return result
            except Exception:
                self._state_store.save_run(previous)
                raise

    def events(self, run_id: str) -> list[Event]:
        with self._lock:
            return list(self._event_store.list_events(run_id))

    def snapshot(self, run_id: str) -> RunSnapshot:
        return RunSnapshot(run=deepcopy(self.get_run(run_id)))

    def lease_manager(self) -> LeaseManager:
        return self._lease_manager

    def _record_event(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: dict | None = None,
    ) -> Event:
        event = Event(
            event_id=str(uuid4()),
            run_id=run_id,
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            sequence=self._event_store.next_sequence(run_id),
            payload=payload or {},
        )
        self._event_store.append(event)
        return event

    def _remove_created_run(self, run_id: str) -> None:
        remove = getattr(self._state_store, "delete_run", None)
        if remove is None:
            return
        remove(run_id)
