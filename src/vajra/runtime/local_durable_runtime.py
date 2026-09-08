from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Callable, TypeVar


T = TypeVar("T")


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
                    raise RuntimeError(
                        f"Execution requires recovery: {execution_id}"
                    )

            self._append(
                DurableRecord(
                    execution_id=execution_id,
                    state="STARTED",
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

        with self._path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue

                entry = json.loads(line)

                record = DurableRecord(
                    execution_id=entry["execution_id"],
                    state=entry["state"],
                    result=entry.get("result"),
                    error=entry.get("error"),
                    retry_count=entry.get("retry_count", 0),
                    sequence=entry["sequence"],
                )

                self._records[record.execution_id] = record
                self._next_sequence = max(
                    self._next_sequence,
                    record.sequence + 1,
                )
