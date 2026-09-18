from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from vajra.memory import EngineeringMemory, JsonlMemoryStore, MemoryKind, MemoryQuery


def test_memory_is_durable_and_digest_bound(tmp_path):
    path = tmp_path / "memory.jsonl"
    memory = EngineeringMemory(JsonlMemoryStore(path))
    record = memory.remember_failure(run_id="run-1", step_id="step-1", attempt_id="attempt-1",
        failure_signature="pytest-timeout", category="TIMEOUT", outcome="retry",
        source_refs=("attempt:attempt-1", "evidence:e-1"), repository_id="repo", source_revision="abc")
    assert record.provenance == "HISTORICAL_MEMORY"
    assert record.record_digest
    assert JsonlMemoryStore(path).get(record.memory_id) == record


def test_memory_requires_provenance(tmp_path):
    memory = EngineeringMemory(JsonlMemoryStore(tmp_path / "memory.jsonl"))
    with pytest.raises(ValueError, match="source references"):
        memory.remember_failure(run_id="r", step_id=None, attempt_id=None, failure_signature="x",
                                category="FAILURE", outcome="stop", source_refs=())


def test_repository_memory_is_stale_when_current_revision_changes(tmp_path):
    memory = EngineeringMemory(JsonlMemoryStore(tmp_path / "memory.jsonl"))
    record = memory.remember_repository(repository_id="repo", revision="old", source_digest="digest-old",
        architecture=("layered",), decisions=("broker is authority",), source_refs=("git:old",))
    result = memory.validate_repository(record.memory_id, current_revision="new", current_digest="digest-new")
    assert not result.current
    assert result.reason == "STALE"
    assert result.conflict is not None
    assert result.conflict.disposition == "CURRENT_TRUTH_WINS"


def test_current_revision_matching_memory_is_valid(tmp_path):
    memory = EngineeringMemory(JsonlMemoryStore(tmp_path / "memory.jsonl"))
    record = memory.remember_repository(repository_id="repo", revision="abc", source_digest="digest",
        conventions=("ruff",), verification=("pytest",), source_refs=("git:abc",))
    assert memory.validate_repository(record.memory_id, current_revision="abc", current_digest="digest").current


def test_context_memory_validates_digest_and_revision(tmp_path):
    memory = EngineeringMemory(JsonlMemoryStore(tmp_path / "memory.jsonl"))
    record = memory.remember_context(repository_id="repo", revision="abc", context_digest="ctx-1",
        items=({"path": "src/a.py", "trust": "HISTORICAL_MEMORY"},), source_refs=("context:ctx-1",))
    assert memory.validate_context(record.memory_id, current_revision="abc", current_context_digest="ctx-1").current
    assert not memory.validate_context(record.memory_id, current_revision="abc", current_context_digest="ctx-2").current


def test_query_is_deterministic_and_filters(tmp_path):
    store = JsonlMemoryStore(tmp_path / "memory.jsonl")
    memory = EngineeringMemory(store, now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    first = memory.remember_failure(run_id="r1", step_id="s", attempt_id="a1", failure_signature="same-error",
        category="TEST_FAILURE", outcome="retry", source_refs=("a:a1",), tags=("tests",))
    second = memory.remember_failure(run_id="r2", step_id="s", attempt_id="a2", failure_signature="different-error",
        category="TIMEOUT", outcome="human", source_refs=("a:a2",), tags=("runtime",))
    rows = memory.search(MemoryQuery(kind=MemoryKind.FAILURE, tags=("tests",), text="same-error"))
    assert rows == (first,)
    assert second.memory_id != first.memory_id


def test_superseded_memory_is_hidden_by_default(tmp_path):
    memory = EngineeringMemory(JsonlMemoryStore(tmp_path / "memory.jsonl"), now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))
    old = memory.remember_repository(repository_id="repo", revision="abc", source_digest="d1",
        decisions=("old",), source_refs=("git:abc",))
    new = memory.remember_repository(repository_id="repo", revision="def", source_digest="d2",
        decisions=("new",), source_refs=("git:def",), supersedes=old.memory_id)
    assert memory.search(MemoryQuery(kind=MemoryKind.REPOSITORY)) == (new,)
    assert len(memory.search(MemoryQuery(kind=MemoryKind.REPOSITORY, include_superseded=True))) == 2


def test_memory_journal_rejects_tampering(tmp_path):
    path = tmp_path / "memory.jsonl"
    memory = EngineeringMemory(JsonlMemoryStore(path))
    memory.remember_failure(run_id="r", step_id="s", attempt_id="a", failure_signature="x",
        category="TEST_FAILURE", outcome="retry", source_refs=("a:a",))
    payload = json.loads(path.read_text())
    payload["content"]["outcome"] = "complete"
    path.write_text(json.dumps(payload) + "\n")
    with pytest.raises(ValueError, match="digest mismatch"):
        JsonlMemoryStore(path)
