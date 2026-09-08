from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock


@dataclass(frozen=True)
class WorkerLease:
    """Authority granted to a worker for one attempt."""

    attempt_id: str
    worker_id: str
    lease_id: str
    lease_expiry: datetime
    fencing_token: int


class LeaseManager:
    """VAJRA-owned in-process lease/fencing authority.

    This is a reference implementation for v0. Distributed persistence and
    cross-process coordination belong to the durable worker infrastructure.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._leases: dict[str, WorkerLease] = {}
        self._next_fencing_token = 1

    def acquire(
        self,
        attempt_id: str,
        worker_id: str,
        lease_id: str,
        ttl_seconds: int,
        *,
        now: datetime | None = None,
    ) -> WorkerLease:
        if not attempt_id:
            raise ValueError("attempt_id must not be empty")
        if not worker_id:
            raise ValueError("worker_id must not be empty")
        if not lease_id:
            raise ValueError("lease_id must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")

        current_time = self._normalize_now(now)

        with self._lock:
            lease = WorkerLease(
                attempt_id=attempt_id,
                worker_id=worker_id,
                lease_id=lease_id,
                lease_expiry=current_time + timedelta(seconds=ttl_seconds),
                fencing_token=self._next_fencing_token,
            )
            self._next_fencing_token += 1
            self._leases[attempt_id] = lease
            return lease

    def get(self, attempt_id: str) -> WorkerLease | None:
        with self._lock:
            return self._leases.get(attempt_id)

    def validate(
        self,
        attempt_id: str,
        worker_id: str,
        lease_id: str,
        fencing_token: int,
        *,
        now: datetime | None = None,
    ) -> WorkerLease:
        current_time = self._normalize_now(now)

        with self._lock:
            lease = self._leases.get(attempt_id)

            if lease is None:
                raise PermissionError(
                    f"No active lease for attempt: {attempt_id}"
                )

            if lease.worker_id != worker_id:
                raise PermissionError("Worker does not own the active lease")

            if lease.lease_id != lease_id:
                raise PermissionError("Lease identity is stale")

            if lease.fencing_token != fencing_token:
                raise PermissionError("Fencing token is stale")

            if current_time >= lease.lease_expiry:
                raise PermissionError("Worker lease has expired")

            return lease

    def release(
        self,
        attempt_id: str,
        worker_id: str,
        lease_id: str,
        fencing_token: int,
        *,
        now: datetime | None = None,
    ) -> None:
        self.validate(
            attempt_id,
            worker_id,
            lease_id,
            fencing_token,
            now=now,
        )

        with self._lock:
            self._leases.pop(attempt_id, None)

    @staticmethod
    def _normalize_now(now: datetime | None) -> datetime:
        value = now or datetime.now(timezone.utc)

        if value.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        return value.astimezone(timezone.utc)
