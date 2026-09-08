from pathlib import Path

import pytest

from vajra.runtime.local_durable_runtime import (
    DurableRecord,
    LocalDurableRuntime,
)


def test_completed_execution_survives_new_runtime_instance(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    result = runtime.execute(
        "exec-1",
        lambda: "completed",
    )

    assert result.state == "COMPLETED"
    assert result.result == "completed"

    restarted = LocalDurableRuntime(journal)

    recovered = restarted.get_execution("exec-1")

    assert recovered is not None
    assert recovered.state == "COMPLETED"
    assert recovered.result == "completed"


def test_completed_execution_is_idempotent_after_restart(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"
    calls = 0

    runtime = LocalDurableRuntime(journal)

    def operation():
        nonlocal calls
        calls += 1
        return "result"

    runtime.execute("exec-1", operation)

    restarted = LocalDurableRuntime(journal)

    result = restarted.execute("exec-1", operation)

    assert result.state == "COMPLETED"
    assert result.result == "result"
    assert calls == 1


def test_failed_execution_is_persisted(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    with pytest.raises(RuntimeError, match="boom"):
        runtime.execute(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )

    restarted = LocalDurableRuntime(journal)

    record = restarted.get_execution("exec-1")

    assert record is not None
    assert record.state == "FAILED"
    assert record.error == "boom"


def test_incomplete_execution_is_recoverable_after_restart(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    runtime_record = runtime.start_execution("exec-1")

    assert runtime_record.state == "STARTED"

    restarted = LocalDurableRuntime(journal)

    recoverable = restarted.recoverable_executions()

    assert len(recoverable) == 1
    assert recoverable[0].execution_id == "exec-1"


def test_cancel_is_persisted_across_restart(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)
    runtime.cancel("exec-1")

    restarted = LocalDurableRuntime(journal)

    record = restarted.get_execution("exec-1")

    assert record is not None
    assert record.state == "CANCELLED"


def test_journal_sequences_are_monotonic(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    runtime.cancel("exec-1")
    runtime.cancel("exec-2")

    records = [
        line
        for line in journal.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert len(records) == 2

    sequences = [
        __import__("json").loads(line)["sequence"]
        for line in records
    ]

    assert sequences == [1, 2]


def test_started_execution_can_be_recovered_without_rerunning_completed_work(
    tmp_path: Path,
):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)
    runtime.start_execution("exec-1")

    calls = 0

    def recovery_operation():
        nonlocal calls
        calls += 1
        return "recovered"

    recovered = runtime.recover("exec-1", recovery_operation)

    assert recovered.state == "COMPLETED"
    assert recovered.result == "recovered"
    assert calls == 1

    restarted = LocalDurableRuntime(journal)

    persisted = restarted.get_execution("exec-1")

    assert persisted is not None
    assert persisted.state == "COMPLETED"
    assert persisted.result == "recovered"


def test_recovery_is_idempotent_after_completion(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)
    runtime.start_execution("exec-1")

    calls = 0

    def recovery_operation():
        nonlocal calls
        calls += 1
        return "recovered"

    first = runtime.recover("exec-1", recovery_operation)
    second = runtime.recover("exec-1", recovery_operation)

    assert first == second
    assert calls == 1


def test_failed_recovery_is_persisted(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)
    runtime.start_execution("exec-1")

    with pytest.raises(RuntimeError, match="recovery failed"):
        runtime.recover(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("recovery failed")),
        )

    restarted = LocalDurableRuntime(journal)

    record = restarted.get_execution("exec-1")

    assert record is not None
    assert record.state == "FAILED"
    assert record.error == "recovery failed"


def test_completed_execution_cannot_be_recovered_again(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    runtime.execute("exec-1", lambda: "done")

    calls = 0

    def recovery_operation():
        nonlocal calls
        calls += 1
        return "wrong"

    result = runtime.recover("exec-1", recovery_operation)

    assert result.state == "COMPLETED"
    assert result.result == "done"
    assert calls == 0


def test_cancelled_execution_cannot_be_recovered(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)
    runtime.cancel("exec-1")

    calls = 0

    def recovery_operation():
        nonlocal calls
        calls += 1
        return "wrong"

    result = runtime.recover("exec-1", recovery_operation)

    assert result.state == "CANCELLED"
    assert calls == 0


def test_unknown_execution_cannot_be_recovered(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    with pytest.raises(KeyError, match="Unknown execution"):
        runtime.recover("missing", lambda: "wrong")


def test_failed_execution_can_be_retried_with_durable_retry_state(
    tmp_path: Path,
):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    calls = 0

    def operation():
        nonlocal calls
        calls += 1

        if calls == 1:
            raise RuntimeError("transient failure")

        return "success"

    with pytest.raises(RuntimeError, match="transient failure"):
        runtime.execute("exec-1", operation)

    retried = runtime.retry("exec-1", operation)

    assert retried.state == "COMPLETED"
    assert retried.result == "success"
    assert calls == 2


def test_retry_count_survives_restart(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    with pytest.raises(RuntimeError, match="first failure"):
        runtime.execute(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("first failure")),
        )

    with pytest.raises(RuntimeError, match="second failure"):
        runtime.retry(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("second failure")),
        )

    restarted = LocalDurableRuntime(journal)

    record = restarted.get_execution("exec-1")

    assert record is not None
    assert record.state == "FAILED"
    assert record.retry_count == 1
    assert record.error == "second failure"


def test_retry_after_restart_continues_retry_count(
    tmp_path: Path,
):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    with pytest.raises(RuntimeError):
        runtime.execute(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("first failure")),
        )

    with pytest.raises(RuntimeError):
        runtime.retry(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("second failure")),
        )

    restarted = LocalDurableRuntime(journal)

    recovered = restarted.retry(
        "exec-1",
        lambda: "success-after-restart",
    )

    assert recovered.state == "COMPLETED"
    assert recovered.result == "success-after-restart"
    assert recovered.retry_count == 2


def test_retry_limit_is_enforced(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal, max_retries=1)

    with pytest.raises(RuntimeError, match="first failure"):
        runtime.execute(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("first failure")),
        )

    with pytest.raises(RuntimeError, match="second failure"):
        runtime.retry(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("second failure")),
        )

    record = runtime.get_execution("exec-1")
    assert record is not None
    assert record.state == "FAILED"
    assert record.retry_count == 1

    with pytest.raises(RuntimeError, match="Retry limit exhausted"):
        runtime.retry(
            "exec-1",
            lambda: "must-not-run",
        )


def test_retry_limit_survives_restart(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal, max_retries=1)

    with pytest.raises(RuntimeError):
        runtime.execute(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("first failure")),
        )

    with pytest.raises(RuntimeError):
        runtime.retry(
            "exec-1",
            lambda: (_ for _ in ()).throw(RuntimeError("second failure")),
        )

    restarted = LocalDurableRuntime(journal, max_retries=1)

    with pytest.raises(RuntimeError, match="Retry limit exhausted"):
        restarted.retry(
            "exec-1",
            lambda: "must-not-run",
        )


def test_negative_retry_limit_is_rejected(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    with pytest.raises(ValueError, match="max_retries must be >= 0"):
        LocalDurableRuntime(journal, max_retries=-1)


def test_completed_execution_is_idempotent_across_restart(
    tmp_path: Path,
):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        return "stable-result"

    first = runtime.execute("exec-1", operation)

    assert first.state == "COMPLETED"
    assert first.result == "stable-result"
    assert calls == 1

    restarted = LocalDurableRuntime(journal)

    second = restarted.execute(
        "exec-1",
        lambda: (_ for _ in ()).throw(
            AssertionError("idempotent execution must not rerun")
        ),
    )

    assert second.state == "COMPLETED"
    assert second.result == "stable-result"
    assert second.sequence == first.sequence


def test_cancelled_execution_is_idempotent_across_restart(
    tmp_path: Path,
):
    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    runtime.start_execution("exec-1")
    runtime.cancel("exec-1")

    first = runtime.get_execution("exec-1")

    assert first is not None
    assert first.state == "CANCELLED"

    restarted = LocalDurableRuntime(journal)

    second = restarted.execute(
        "exec-1",
        lambda: (_ for _ in ()).throw(
            AssertionError("cancelled execution must not run")
        ),
    )

    assert second.state == "CANCELLED"
    assert second.sequence == first.sequence


def test_timer_survives_restart_and_becomes_due(tmp_path: Path):
    from datetime import datetime, timezone, timedelta

    journal = tmp_path / "runtime.jsonl"

    due_at = datetime.now(timezone.utc) + timedelta(seconds=60)

    runtime = LocalDurableRuntime(journal)

    scheduled = runtime.schedule_timer("timer-1", due_at)

    assert scheduled.state == "SCHEDULED"
    assert scheduled.due_at == due_at.astimezone(timezone.utc).isoformat()

    restarted = LocalDurableRuntime(journal)

    timer = restarted.get_timer("timer-1")

    assert timer is not None
    assert timer.state == "SCHEDULED"
    assert timer.due_at == scheduled.due_at

    assert restarted.due_timers(
        due_at - timedelta(seconds=1)
    ) == ()

    due = restarted.due_timers(due_at)

    assert len(due) == 1
    assert due[0].timer_id == "timer-1"


def test_timer_consumption_is_durable_and_idempotent(
    tmp_path: Path,
):
    from datetime import datetime, timezone, timedelta

    journal = tmp_path / "runtime.jsonl"

    runtime = LocalDurableRuntime(journal)

    due_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    runtime.schedule_timer("timer-1", due_at)

    first = runtime.consume_timer("timer-1")

    assert first.state == "CONSUMED"

    second = runtime.consume_timer("timer-1")

    assert second.state == "CONSUMED"
    assert second.sequence == first.sequence

    restarted = LocalDurableRuntime(journal)

    persisted = restarted.get_timer("timer-1")

    assert persisted is not None
    assert persisted.state == "CONSUMED"
    assert restarted.due_timers(
        datetime.now(timezone.utc) + timedelta(seconds=1)
    ) == ()


def test_timer_requires_timezone_aware_due_at(tmp_path: Path):
    from datetime import datetime

    runtime = LocalDurableRuntime(tmp_path / "runtime.jsonl")

    with pytest.raises(ValueError, match="timezone-aware"):
        runtime.schedule_timer(
            "timer-1",
            datetime(2030, 1, 1),
        )


def test_duplicate_timer_schedule_is_idempotent(tmp_path: Path):
    from datetime import datetime, timezone, timedelta

    runtime = LocalDurableRuntime(tmp_path / "runtime.jsonl")

    due_at = datetime.now(timezone.utc) + timedelta(seconds=30)

    first = runtime.schedule_timer("timer-1", due_at)
    second = runtime.schedule_timer("timer-1", due_at)

    assert second == first
    assert second.sequence == first.sequence


def test_concurrent_execute_same_id_runs_operation_once(tmp_path: Path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    journal = tmp_path / "runtime.jsonl"
    runtime = LocalDurableRuntime(journal)

    operation_started = Event()
    release_operation = Event()
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        operation_started.set()
        assert release_operation.wait(timeout=2)
        return "shared-result"

    def invoke():
        return runtime.execute("exec-1", operation)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(invoke)

        assert operation_started.wait(timeout=2)

        second = pool.submit(invoke)

        # The second caller must be able to enter execute() while the
        # first operation is still running. It must wait for the
        # already-active execution rather than run the operation again.
        release_operation.set()

        results = [
            first.result(timeout=5),
            second.result(timeout=5),
        ]

    assert calls == 1
    assert all(result.state == "COMPLETED" for result in results)
    assert all(result.result == "shared-result" for result in results)
    assert results[0].sequence == results[1].sequence


def test_replay_rejects_sequence_gap(tmp_path: Path):
    import json

    journal = tmp_path / "runtime.jsonl"

    journal.write_text(
        json.dumps(
            {
                "execution_id": "exec-1",
                "state": "STARTED",
                "result": None,
                "error": None,
                "retry_count": 0,
                "sequence": 1,
            }
        )
        + "\n"
        + json.dumps(
            {
                "execution_id": "exec-1",
                "state": "COMPLETED",
                "result": "done",
                "error": None,
                "retry_count": 0,
                "sequence": 3,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sequence"):
        LocalDurableRuntime(journal)


def test_replay_rejects_duplicate_sequence(tmp_path: Path):
    import json

    journal = tmp_path / "runtime.jsonl"

    entry = {
        "execution_id": "exec-1",
        "state": "STARTED",
        "result": None,
        "error": None,
        "retry_count": 0,
        "sequence": 1,
    }

    journal.write_text(
        json.dumps(entry)
        + "\n"
        + json.dumps(
            {
                **entry,
                "state": "COMPLETED",
                "result": "done",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sequence"):
        LocalDurableRuntime(journal)


def test_replay_rejects_malformed_complete_record(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    journal.write_text(
        '{"execution_id":"exec-1","state":"STARTED","sequence":1}\n'
        '{"execution_id":"exec-1","state":"COMPLETED","sequence":2\n\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="journal"):
        LocalDurableRuntime(journal)


def test_replay_ignores_truncated_final_record(tmp_path: Path):
    import json

    journal = tmp_path / "runtime.jsonl"

    valid = {
        "execution_id": "exec-1",
        "state": "STARTED",
        "result": None,
        "error": None,
        "retry_count": 0,
        "sequence": 1,
    }

    truncated = (
        '{"execution_id":"exec-2","state":"STARTED",'
        '"result":null,"error":null,"retry_count":0,"sequence":2'
    )

    journal.write_text(
        json.dumps(valid) + "\n" + truncated,
        encoding="utf-8",
    )

    runtime = LocalDurableRuntime(journal)

    record = runtime.get_execution("exec-1")

    assert record is not None
    assert record.state == "STARTED"
    assert runtime.get_execution("exec-2") is None

    recovered = runtime.recover(
        "exec-1",
        lambda: "recovered",
    )

    assert recovered.state == "COMPLETED"
    assert recovered.result == "recovered"


def test_replay_preserves_last_durable_state_before_truncated_tail(
    tmp_path: Path,
):
    import json

    journal = tmp_path / "runtime.jsonl"

    durable_completed = {
        "execution_id": "exec-1",
        "state": "COMPLETED",
        "result": "durable-result",
        "error": None,
        "retry_count": 2,
        "sequence": 1,
    }

    truncated = (
        '{"execution_id":"exec-2","state":"STARTED",'
        '"result":null,"error":null,"retry_count":3,"sequence":2'
    )

    journal.write_text(
        json.dumps(durable_completed) + "\n" + truncated,
        encoding="utf-8",
    )

    runtime = LocalDurableRuntime(journal)

    record = runtime.get_execution("exec-1")

    assert record is not None
    assert record.state == "COMPLETED"
    assert record.result == "durable-result"
    assert record.retry_count == 2
    assert record.sequence == 1

    assert runtime.get_execution("exec-2") is None

    next_result = runtime.start_execution("exec-3")

    assert next_result.state == "STARTED"
    assert next_result.sequence == 2
