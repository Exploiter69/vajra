from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Event, RLock, Thread
from typing import Any, Callable
from uuid import uuid4

from vajra.control.transition_authority import TransitionActor
from vajra.domain import RunState

from .contracts import ControlCommand, ControlResult, ScheduleSpec
from .store import ControlPlaneStore, StoredSchedule


class ControlPlaneError(RuntimeError):
    """Raised when the always-on control plane cannot safely proceed."""


class ControlPlane:
    """Always-on daemon, durable queue, human controls, and scheduler."""

    ACTIVE_STATES = frozenset({
        RunState.ORIENTING, RunState.PLANNING, RunState.EXECUTING,
        RunState.VERIFYING, RunState.CANDIDATE, RunState.PROMOTION,
        RunState.RECOVERING,
    })

    def __init__(self, run_manager, store: ControlPlaneStore, *,
                 run_executor: Callable[[str], Any] | None = None,
                 poll_interval_seconds: float = 1.0) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._manager = run_manager
        self._store = store
        self._executor = run_executor
        self._poll = poll_interval_seconds
        self._stop = Event()
        self._wake = Event()
        self._thread: Thread | None = None
        self._lock = RLock()
        self._handlers: dict[str, Callable[[dict[str, Any]], str]] = {}
        self._store.recover_dispatching()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def register_job_handler(self, job_type: str, handler: Callable[[dict[str, Any]], str]) -> None:
        if not job_type.strip():
            raise ValueError("job_type must be nonempty")
        with self._lock:
            if job_type in self._handlers:
                raise ValueError(f"job handler already registered: {job_type}")
            self._handlers[job_type] = handler

    def submit(self, run_id: str) -> str:
        run = self._manager.get_run(run_id)
        if run.state is RunState.CREATED:
            self._manager.transition(run_id, RunState.QUEUED, TransitionActor.HUMAN, reason="queued by control plane")
        elif run.state is RunState.FAILED:
            self._manager.recover_run(run_id)
            self._manager.transition(run_id, RunState.QUEUED, TransitionActor.HUMAN, reason="retry queued by control plane")
        elif run.state is not RunState.QUEUED:
            raise ControlPlaneError(f"Run is not queueable from {run.state.value}: {run_id}")
        entry_id = f"queue-{uuid4()}"
        self._store.enqueue(entry_id, run_id)
        self._wake.set()
        return entry_id

    def control(self, run_id: str, command: ControlCommand, *, reason: str = "") -> ControlResult:
        command_id = f"command-{uuid4()}"
        try:
            run = self._manager.get_run(run_id)
            if command in {ControlCommand.PAUSE, ControlCommand.CANCEL}:
                if run.state is RunState.QUEUED:
                    for entry in self._store.ready():
                        if entry.run_id == run_id:
                            self._store.cancel_queue(entry.entry_id)
                    self._manager.transition(run_id, RunState.PAUSED, TransitionActor.HUMAN,
                                             reason=reason or f"human {command.value}")
                elif run.state in self.ACTIVE_STATES:
                    self._manager.transition(run_id, RunState.PAUSED, TransitionActor.HUMAN,
                                             reason=reason or f"human {command.value}")
                elif run.state is not RunState.PAUSED:
                    raise ControlPlaneError(f"Run cannot be {command.value}d from {run.state.value}")
            elif command is ControlCommand.RESUME:
                if run.state is not RunState.PAUSED:
                    raise ControlPlaneError(f"Run cannot be resumed from {run.state.value}")
                self._manager.transition(run_id, RunState.QUEUED, TransitionActor.HUMAN, reason=reason or "human resume")
                self.submit(run_id)
            elif command is ControlCommand.ABORT:
                if run.state not in {RunState.RECOVERING, RunState.WAITING_HUMAN, RunState.QUEUED, RunState.PAUSED}:
                    self._manager.recover_run(run_id)
                self._manager.abort_run(run_id, reason or "human abort", TransitionActor.HUMAN)
                for entry in self._store.ready():
                    if entry.run_id == run_id:
                        self._store.cancel_queue(entry.entry_id)
            elif command is ControlCommand.RETRY:
                if run.state is not RunState.FAILED:
                    raise ControlPlaneError(f"Run is not retryable from {run.state.value}")
                self._manager.recover_run(run_id)
                self._manager.transition(run_id, RunState.QUEUED, TransitionActor.HUMAN, reason=reason or "human retry")
                self.submit(run_id)
            elif command is ControlCommand.APPROVE:
                if run.state is not RunState.WAITING_HUMAN:
                    raise ControlPlaneError(f"Run is not awaiting approval: {run.state.value}")
                self._manager.transition(run_id, RunState.QUEUED, TransitionActor.HUMAN, reason=reason or "human approval")
                self.submit(run_id)
            elif command is ControlCommand.REJECT:
                if run.state not in {RunState.WAITING_HUMAN, RunState.CANDIDATE, RunState.PROMOTION}:
                    raise ControlPlaneError(f"Run is not rejectable from {run.state.value}")
                if run.state is not RunState.WAITING_HUMAN:
                    self._manager.transition(run_id, RunState.WAITING_HUMAN, TransitionActor.HUMAN, reason=reason or "human rejection review")
                self._manager.abort_run(run_id, reason or "human rejection", TransitionActor.HUMAN)
            else:
                raise ControlPlaneError(f"Unsupported command: {command}")
            final = self._manager.get_run(run_id)
            result = ControlResult(command_id, run_id, True, final.state.value, f"{command.value} accepted")
        except (KeyError, ValueError, RuntimeError, ControlPlaneError) as exc:
            result = ControlResult(command_id, run_id, False, None, str(exc))
        self._store.record_command(command_id, command.value, run_id, result.message)
        self._wake.set()
        return result

    def schedule(self, spec: ScheduleSpec) -> ScheduleSpec:
        due = datetime.fromisoformat(spec.due_at)
        if due.tzinfo is None:
            raise ValueError("schedule due_at must be timezone-aware")
        stored = self._store.add_schedule(StoredSchedule(
            spec.schedule_id, due.astimezone(timezone.utc).isoformat(),
            spec.job_type, dict(spec.payload), spec.interval_seconds, spec.enabled,
        ))
        self._wake.set()
        return ScheduleSpec(stored.schedule_id, stored.due_at, stored.job_type,
                            dict(stored.payload), stored.interval_seconds, stored.enabled)

    def cancel_schedule(self, schedule_id: str) -> None:
        self._store.disable_schedule(schedule_id)
        self._wake.set()

    def queue(self):
        return self._store.ready()

    def schedules(self):
        return self._store.schedules()

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            self._stop.clear()
            self._thread = Thread(target=self._serve, name="vajra-control-plane", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        if thread is not None and thread.is_alive():
            raise ControlPlaneError("control-plane daemon did not stop within timeout")
        self._thread = None

    def run_once(self, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        work = 0
        for schedule in self._store.due_schedules(now):
            handler = self._handlers.get(schedule.job_type)
            if handler is None:
                continue
            run_id = handler(dict(schedule.payload))
            if not run_id:
                raise ControlPlaneError(f"schedule handler returned empty run id: {schedule.job_type}")
            self.submit(run_id)
            if schedule.interval_seconds:
                next_due = datetime.fromisoformat(schedule.due_at) + timedelta(seconds=schedule.interval_seconds)
                while next_due <= now.astimezone(timezone.utc):
                    next_due += timedelta(seconds=schedule.interval_seconds)
                self._store.advance_schedule(schedule.schedule_id, next_due_at=next_due.isoformat())
            else:
                self._store.disable_schedule(schedule.schedule_id)
            work += 1

        if self._executor is not None:
            entry = next(iter(self._store.ready()), None)
            if entry is not None:
                self._store.claim(entry.entry_id)
                try:
                    self._executor(entry.run_id)
                except Exception:
                    self._store.requeue(entry.entry_id)
                    raise
                else:
                    self._store.finish(entry.entry_id)
                work += 1
        return work

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                self._wake.wait(self._poll)
                self._wake.clear()
                continue
            self._wake.wait(self._poll)
            self._wake.clear()
