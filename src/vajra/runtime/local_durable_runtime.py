from __future__ import annotations

import json
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from threading import Condition, RLock
from typing import Callable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class DurableTimer:
    timer_id: str
    due_at: str
    state: str = "SCHEDULED"
    sequence: int = 0


@dataclass(frozen=True)
class DurableRecord:
    execution_id: str
    state: str
    result: object | None = None
    error: str | None = None
    retry_count: int = 0
    sequence: int = 0


class LocalDurableRuntime:
    """
    Minimal restart-capable durable execution journal.

    This is a development/reference implementation for validating VAJRA's
    DurableRuntime semantics. It is not the production runtime and must not
    be treated as equivalent to a distributed durable execution system.

    The journal is append-only. Runtime state is reconstructed by replaying
    records after process restart.
    """

    def __init__(
        self,
        journal_path: str | Path,
        max_retries: int = 3,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")

        self._path = Path(journal_path)
        self._max_retries = max_retries
        self._lock = RLock()
        self._records: dict[str, DurableRecord] = {}
        self._timers: dict[str, DurableTimer] = {}
        self._active_executions: set[str] = set()
        self._conditions: dict[str, Condition] = {}
        self._next_sequence = 1
        self._load()

    def execute(
        self,
        execution_id: str,
        operation: Callable[[], T],
    ) -> DurableRecord:
        with self._lock:
            existing = self._records.get(execution_id)

            if existing is not None:
                if existing.state == "COMPLETED":
                    return existing

                if existing.state == "CANCELLED":
                    return existing

                if existing.state == "STARTED":
                    if execution_id not in self._active_executions:
                        raise RuntimeError(
                            f"Execution requires recovery: {execution_id}"
                        )

                    condition = self._conditions.setdefault(
                        execution_id,
                        Condition(self._lock),
                    )

                    while True:
                        current = self._records[execution_id]

                        if current.state != "STARTED":
                            if current.state == "COMPLETED":
                                return current

                            if current.state == "CANCELLED":
                                return current

                            raise RuntimeError(
                                current.error
                                or f"Execution failed: {execution_id}"
                            )

                        condition.wait()

                    # Unreachable; terminal states return above.

            self._append(
                DurableRecord(
                    execution_id=execution_id,
                    state="STARTED",
                )
            )

            self._active_executions.add(execution_id)
            self._conditions.setdefault(
                execution_id,
                Condition(self._lock),
            )

        try:
            result = operation()
        except Exception as exc:
            with self._lock:
                self._append(
                    DurableRecord(
                        execution_id=execution_id,
                        state="FAILED",
                        error=str(exc),
                    )
                )
                self._active_executions.discard(execution_id)
                self._conditions[execution_id].notify_all()
            raise

        with self._lock:
            self._append(
                DurableRecord(
                    execution_id=execution_id,
                    state="COMPLETED",
                    result=result,
                )
            )
            self._active_executions.discard(execution_id)
            self._conditions[execution_id].notify_all()
            return self._records[execution_id]

    def get_execution(
        self,
        execution_id: str,
    ) -> DurableRecord | None:
        with self._lock:
            return self._records.get(execution_id)

    def cancel(self, execution_id: str) -> None:
        with self._lock:
            existing = self._records.get(execution_id)

            if existing is not None and existing.state == "COMPLETED":
                return

            self._append(
                DurableRecord(
                    execution_id=execution_id,
                    state="CANCELLED",
                )
            )

    def schedule_timer(
        self,
        timer_id: str,
        due_at: datetime,
    ) -> DurableTimer:
        """Persist a timer without creating an in-process scheduler."""
        if due_at.tzinfo is None:
            raise ValueError("due_at must be timezone-aware")

        with self._lock:
            existing = self._timers.get(timer_id)
            if existing is not None:
                return existing

            normalized = due_at.astimezone(timezone.utc).isoformat()

            timer = DurableTimer(
                timer_id=timer_id,
                due_at=normalized,
            )
            self._append_timer(timer)
            return self._timers[timer_id]

    def get_timer(self, timer_id: str) -> DurableTimer | None:
        with self._lock:
            return self._timers.get(timer_id)

    def due_timers(
        self,
        now: datetime | None = None,
    ) -> tuple[DurableTimer, ...]:
        if now is None:
            now = datetime.now(timezone.utc)

        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        current = now.astimezone(timezone.utc)

        with self._lock:
            return tuple(
                timer
                for timer in self._timers.values()
                if timer.state == "SCHEDULED"
                and datetime.fromisoformat(timer.due_at) <= current
            )

    def consume_timer(self, timer_id: str) -> DurableTimer:
        with self._lock:
            existing = self._timers.get(timer_id)

            if existing is None:
                raise KeyError(f"Unknown timer: {timer_id}")

            if existing.state == "CONSUMED":
                return existing

            if existing.state != "SCHEDULED":
                raise RuntimeError(
                    f"Timer is not consumable: {timer_id}"
                )

            consumed = DurableTimer(
                timer_id=existing.timer_id,
                due_at=existing.due_at,
                state="CONSUMED",
            )
            self._append_timer(consumed)
            return self._timers[timer_id]

    def _append_timer(self, timer: DurableTimer) -> None:
        sequence = self._next_sequence

        entry = {
            "type": "timer",
            "timer_id": timer.timer_id,
            "due_at": timer.due_at,
            "state": timer.state,
            "sequence": sequence,
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)

        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()

        persisted = DurableTimer(
            timer_id=timer.timer_id,
            due_at=timer.due_at,
            state=timer.state,
            sequence=sequence,
        )

        self._timers[timer.timer_id] = persisted
        self._next_sequence += 1

    def recoverable_executions(self) -> tuple[DurableRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in self._records.values()
                if record.state == "STARTED"
            )

    def retry(
        self,
        execution_id: str,
        operation: Callable[[], T],
    ) -> DurableRecord:
        with self._lock:
            existing = self._records.get(execution_id)

            if existing is None:
                raise KeyError(f"Unknown execution: {execution_id}")

            if existing.state == "COMPLETED":
                return existing

            if existing.state == "CANCELLED":
                return existing

            if existing.state != "FAILED":
                raise RuntimeError(
                    f"Execution is not retryable: {execution_id}"
                )

            if existing.retry_count >= self._max_retries:
                raise RuntimeError(
                    f"Retry limit exhausted: {execution_id}"
                )

            retry_count = existing.retry_count + 1

            self._append(
                DurableRecord(
                    execution_id=execution_id,
                    state="STARTED",
                    retry_count=retry_count,
                )
            )

            try:
                result = operation()
            except Exception as exc:
                self._append(
                    DurableRecord(
                        execution_id=execution_id,
                        state="FAILED",
                        error=str(exc),
                        retry_count=retry_count,
                    )
                )
                raise

            self._append(
                DurableRecord(
                    execution_id=execution_id,
                    state="COMPLETED",
                    result=result,
                    retry_count=retry_count,
                )
            )
            return self._records[execution_id]

    def recover(
        self,
        execution_id: str,
        operation: Callable[[], T],
    ) -> DurableRecord:
        with self._lock:
            existing = self._records.get(execution_id)

            if existing is None:
                raise KeyError(f"Unknown execution: {execution_id}")

            if existing.state == "COMPLETED":
                return existing

            if existing.state == "CANCELLED":
                return existing

            if existing.state != "STARTED":
                raise RuntimeError(
                    f"Execution is not recoverable: {execution_id}"
                )

            try:
                result = operation()
            except Exception as exc:
                self._append(
                    DurableRecord(
                        execution_id=execution_id,
                        state="FAILED",
                        error=str(exc),
                    )
                )
                raise

            record = DurableRecord(
                execution_id=execution_id,
                state="COMPLETED",
                result=result,
            )
            self._append(record)
            return self._records[execution_id]

    def start_execution(self, execution_id: str) -> DurableRecord:
        """Persist the durable STARTED boundary without running the operation.

        This exists for lifecycle/recovery tests and controlled runtime
        integration points. It does not execute user work.
        """
        with self._lock:
            existing = self._records.get(execution_id)

            if existing is not None:
                return existing

            self._append(
                DurableRecord(
                    execution_id=execution_id,
                    state="STARTED",
                )
            )
            return self._records[execution_id]

    def _append(self, record: DurableRecord) -> None:
        sequence = self._next_sequence

        entry = {
            "execution_id": record.execution_id,
            "state": record.state,
            "result": record.result,
            "error": record.error,
            "retry_count": record.retry_count,
            "sequence": sequence,
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)

        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()

        persisted = DurableRecord(
            execution_id=record.execution_id,
            state=record.state,
            result=record.result,
            error=record.error,
            retry_count=record.retry_count,
            sequence=sequence,
        )

        self._records[record.execution_id] = persisted
        self._next_sequence += 1

    def _load(self) -> None:
        if not self._path.exists():
            return

        expected_sequence = 1
        last_sequence = 0

        with self._path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()

        for index, line in enumerate(lines):
            if not line.strip():
                continue

            is_final_line = index == len(lines) - 1
            has_newline = line.endswith("\n")

            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                if is_final_line and not has_newline:
                    # A process may crash while appending the final JSONL
                    # record. An incomplete final record is not durable and
                    # is therefore ignored during replay.
                    break

                raise ValueError(
                    f"Invalid journal record at line {index + 1}: {exc}"
                ) from exc

            sequence = entry.get("sequence")

            if not isinstance(sequence, int) or sequence < 1:
                raise ValueError(
                    f"Invalid journal sequence at line {index + 1}: "
                    f"{sequence!r}"
                )

            if sequence != expected_sequence:
                raise ValueError(
                    f"Invalid journal sequence at line {index + 1}: "
                    f"expected {expected_sequence}, got {sequence}"
                )

            if entry.get("type") == "timer":
                try:
                    timer = DurableTimer(
                        timer_id=entry["timer_id"],
                        due_at=entry["due_at"],
                        state=entry["state"],
                        sequence=sequence,
                    )
                except (KeyError, TypeError) as exc:
                    raise ValueError(
                        f"Invalid journal timer at line {index + 1}"
                    ) from exc

                self._timers[timer.timer_id] = timer

            else:
                try:
                    record = DurableRecord(
                        execution_id=entry["execution_id"],
                        state=entry["state"],
                        result=entry.get("result"),
                        error=entry.get("error"),
                        retry_count=entry.get("retry_count", 0),
                        sequence=sequence,
                    )
                except (KeyError, TypeError) as exc:
                    raise ValueError(
                        f"Invalid journal record at line {index + 1}"
                    ) from exc

                self._records[record.execution_id] = record

            last_sequence = sequence
            expected_sequence += 1

        self._next_sequence = last_sequence + 1
