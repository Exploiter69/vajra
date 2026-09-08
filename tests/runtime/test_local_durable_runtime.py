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
