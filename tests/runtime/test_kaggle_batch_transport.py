from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from vajra.runtime.kaggle_batch_transport import KaggleBatchWorkerError, KaggleBatchWorkerTransport
from vajra.runtime.kaggle_worker import KaggleWorkerAdapter
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


def job(correlation_id: str = "corr-1") -> WorkerJob:
    return WorkerJob(
        run_id="run",
        step_id="step",
        attempt_id="attempt",
        repository_revision="rev",
        workspace_contract={},
        context_bundle={"prompt": "return JSON"},
        allowed_capabilities=(),
        budget={},
        deadline=(datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
        expected_output_schema={"type": "object"},
        correlation_id=correlation_id,
    )


def template(tmp_path):
    path = tmp_path / "template"
    path.mkdir()
    (path / "kernel-metadata.json").write_text(
        json.dumps({"id": "placeholder", "code_file": "worker.py"}), encoding="utf-8"
    )
    (path / "worker.py").write_text("EMBEDDED_JOB_JSON: str | None = None\nprint('worker')\n", encoding="utf-8")
    return path


def encoded_result(correlation_id="corr-1"):
    return KaggleWorkerAdapter().encode_result(
        WorkerResult(
            status="completed",
            correlation_id=correlation_id,
            structured_result={"response": "{\"ok\":true}"},
        )
    )


def test_batch_transport_pushes_polls_downloads_and_decodes(monkeypatch, tmp_path):
    calls = []
    uploaded_worker_source = None

    class FakeLauncher:
        def __init__(self, kernel_path, **kwargs):
            self.kernel_path = kernel_path
            calls.append(("init", kernel_path, kwargs))

        def start(self):
            nonlocal uploaded_worker_source
            uploaded_worker_source = (self.kernel_path / "worker.py").read_text(encoding="utf-8")
            calls.append(("start",))

        def status(self):
            calls.append(("status",))
            return "running" if len([x for x in calls if x[0] == "status"]) == 1 else "complete"

        def output(self, destination, **kwargs):
            calls.append(("output",))
            destination.mkdir(parents=True)
            (destination / "worker_result.json").write_text(encoded_result(), encoding="utf-8")

    monkeypatch.setattr("vajra.runtime.kaggle_batch_transport.KaggleKernelLauncher", FakeLauncher)
    transport = KaggleBatchWorkerTransport(template(tmp_path), "owner/kernel", poll_interval_seconds=0.001)
    result = transport.execute(job())

    assert result.status == "completed"
    assert result.correlation_id == "corr-1"
    assert uploaded_worker_source is not None
    assert "EMBEDDED_JOB_JSON: str | None = '" in uploaded_worker_source
    assert "return JSON" in uploaded_worker_source
    assert [x[0] for x in calls] == ["init", "start", "status", "status", "output"]


def test_batch_transport_rejects_failed_kernel(monkeypatch, tmp_path):
    class FakeLauncher:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            pass
        def status(self):
            return "failed"
        def output(self, destination, **kwargs):
            raise AssertionError("output must not run")

    monkeypatch.setattr("vajra.runtime.kaggle_batch_transport.KaggleKernelLauncher", FakeLauncher)
    with pytest.raises(KaggleBatchWorkerError, match="kernel failed"):
        KaggleBatchWorkerTransport(template(tmp_path), "owner/kernel").execute(job())


def test_batch_transport_rejects_missing_result(monkeypatch, tmp_path):
    class FakeLauncher:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            pass
        def status(self):
            return "complete"
        def output(self, destination, **kwargs):
            destination.mkdir(parents=True)

    monkeypatch.setattr("vajra.runtime.kaggle_batch_transport.KaggleKernelLauncher", FakeLauncher)
    with pytest.raises(KaggleBatchWorkerError, match="worker_result.json"):
        KaggleBatchWorkerTransport(template(tmp_path), "owner/kernel").execute(job())


def test_batch_transport_rejects_wrong_correlation(monkeypatch, tmp_path):
    class FakeLauncher:
        def __init__(self, *args, **kwargs):
            pass
        def start(self):
            pass
        def status(self):
            return "complete"
        def output(self, destination, **kwargs):
            destination.mkdir(parents=True)
            (destination / "worker_result.json").write_text(
                encoded_result("wrong"), encoding="utf-8"
            )

    monkeypatch.setattr("vajra.runtime.kaggle_batch_transport.KaggleKernelLauncher", FakeLauncher)
    with pytest.raises(KaggleBatchWorkerError, match="correlation_id"):
        KaggleBatchWorkerTransport(template(tmp_path), "owner/kernel").execute(job())


def test_batch_transport_rejects_expired_job(tmp_path):
    expired = WorkerJob(
        run_id="run", step_id="step", attempt_id="attempt", repository_revision="rev",
        workspace_contract={}, context_bundle={"prompt": "x"}, allowed_capabilities=(),
        budget={}, deadline=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        expected_output_schema={}, correlation_id="corr-1",
    )
    transport = KaggleBatchWorkerTransport(template(tmp_path), "owner/kernel")
    with pytest.raises(KaggleBatchWorkerError, match="deadline"):
        transport.execute(expired)
