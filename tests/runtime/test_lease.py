from datetime import datetime, timezone

import pytest

from vajra.runtime.lease import LeaseManager


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def test_acquire_creates_worker_lease_with_fencing_token():
    manager = LeaseManager()

    lease = manager.acquire(
        "attempt-001",
        "worker-001",
        "lease-001",
        60,
        now=NOW,
    )

    assert lease.attempt_id == "attempt-001"
    assert lease.worker_id == "worker-001"
    assert lease.lease_id == "lease-001"
    assert lease.lease_expiry == datetime(
        2026, 9, 8, 12, 1, tzinfo=timezone.utc
    )
    assert lease.fencing_token == 1


def test_valid_lease_is_accepted():
    manager = LeaseManager()
    lease = manager.acquire(
        "attempt-001",
        "worker-001",
        "lease-001",
        60,
        now=NOW,
    )

    validated = manager.validate(
        "attempt-001",
        "worker-001",
        "lease-001",
        lease.fencing_token,
        now=NOW,
    )

    assert validated == lease


def test_expired_lease_is_rejected():
    manager = LeaseManager()
    lease = manager.acquire(
        "attempt-001",
        "worker-001",
        "lease-001",
        60,
        now=NOW,
    )

    with pytest.raises(PermissionError, match="expired"):
        manager.validate(
            "attempt-001",
            "worker-001",
            "lease-001",
            lease.fencing_token,
            now=datetime(
                2026, 9, 8, 12, 1, tzinfo=timezone.utc
            ),
        )


def test_wrong_worker_cannot_use_lease():
    manager = LeaseManager()
    lease = manager.acquire(
        "attempt-001",
        "worker-001",
        "lease-001",
        60,
        now=NOW,
    )

    with pytest.raises(PermissionError, match="does not own"):
        manager.validate(
            "attempt-001",
            "worker-002",
            "lease-001",
            lease.fencing_token,
            now=NOW,
        )


def test_superseded_lease_has_stale_fencing_token():
    manager = LeaseManager()

    first = manager.acquire(
        "attempt-001",
        "worker-001",
        "lease-001",
        60,
        now=NOW,
    )

    second = manager.acquire(
        "attempt-001",
        "worker-002",
        "lease-002",
        60,
        now=NOW,
    )

    assert second.fencing_token > first.fencing_token

    with pytest.raises(PermissionError):
        manager.validate(
            "attempt-001",
            "worker-001",
            "lease-001",
            first.fencing_token,
            now=NOW,
        )


def test_superseded_lease_cannot_commit_even_before_expiry():
    manager = LeaseManager()

    first = manager.acquire(
        "attempt-001",
        "worker-001",
        "lease-001",
        600,
        now=NOW,
    )

    second = manager.acquire(
        "attempt-001",
        "worker-002",
        "lease-002",
        600,
        now=NOW,
    )

    with pytest.raises(PermissionError):
        manager.validate(
            "attempt-001",
            "worker-001",
            "lease-001",
            first.fencing_token,
            now=datetime(
                2026, 9, 8, 12, 5, tzinfo=timezone.utc
            ),
        )

    assert manager.validate(
        "attempt-001",
        "worker-002",
        "lease-002",
        second.fencing_token,
        now=datetime(
            2026, 9, 8, 12, 5, tzinfo=timezone.utc
        ),
    ) == second


def test_release_removes_active_lease():
    manager = LeaseManager()
    lease = manager.acquire(
        "attempt-001",
        "worker-001",
        "lease-001",
        60,
        now=NOW,
    )

    manager.release(
        "attempt-001",
        "worker-001",
        "lease-001",
        lease.fencing_token,
        now=NOW,
    )

    assert manager.get("attempt-001") is None


def test_invalid_lease_inputs_are_rejected():
    manager = LeaseManager()

    with pytest.raises(ValueError, match="attempt_id"):
        manager.acquire("", "worker", "lease", 60, now=NOW)

    with pytest.raises(ValueError, match="worker_id"):
        manager.acquire("attempt", "", "lease", 60, now=NOW)

    with pytest.raises(ValueError, match="lease_id"):
        manager.acquire("attempt", "worker", "", 60, now=NOW)

    with pytest.raises(ValueError, match="greater than zero"):
        manager.acquire("attempt", "worker", "lease", 0, now=NOW)


def test_naive_clock_is_rejected():
    manager = LeaseManager()

    with pytest.raises(ValueError, match="timezone-aware"):
        manager.acquire(
            "attempt-001",
            "worker-001",
            "lease-001",
            60,
            now=datetime(2026, 9, 8, 12, 0),
        )


def test_stale_worker_cannot_release_replacement_lease():
    manager = LeaseManager()

    first = manager.acquire(
        "attempt-001",
        "worker-001",
        "lease-001",
        600,
        now=NOW,
    )

    second = manager.acquire(
        "attempt-001",
        "worker-002",
        "lease-002",
        600,
        now=NOW,
    )

    with pytest.raises(PermissionError):
        manager.release(
            "attempt-001",
            "worker-001",
            "lease-001",
            first.fencing_token,
            now=NOW,
        )

    assert manager.get("attempt-001") == second
