from __future__ import annotations

import json

from vajra.runtime.http_worker_transport import HTTPWorkerTransport
from vajra.runtime.worker_protocol import WorkerJob


def make_job() -> WorkerJob:
    return WorkerJob(
        run_id="run-001",
        step_id="step-001",
        attempt_id="attempt-001",
        repository_revision="abc123",
        workspace_contract={},
        context_bundle={"prompt": "hello"},
        allowed_capabilities=("completion",),
        budget={"max_output_tokens": 16},
        deadline="2099-01-01T00:00:00+00:00",
        expected_output_schema={"type": "object"},
        correlation_id="corr-001",
    )


def test_http_transport_dispatch_posts_worker_job(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ignored": true}'

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        "vajra.runtime.http_worker_transport.urlopen",
        fake_urlopen,
    )

    transport = HTTPWorkerTransport(
        "http://127.0.0.1:8787/infer",
        timeout_seconds=42,
    )

    transport.dispatch(make_job())

    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))

    assert request.full_url == "http://127.0.0.1:8787/infer"
    assert request.get_header("Content-type") == "application/json"
    assert captured["timeout"] == 42

    assert payload["protocol_version"] == "vajra-worker-v1"
    assert payload["type"] == "worker_job"
    assert payload["job"]["run_id"] == "run-001"
    assert payload["job"]["attempt_id"] == "attempt-001"
    assert payload["job"]["correlation_id"] == "corr-001"


def test_http_transport_execute_decodes_worker_result(monkeypatch):
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {
                    "protocol_version": "vajra-worker-v1",
                    "type": "worker_result",
                    "result": {
                        "status": "completed",
                        "correlation_id": "corr-001",
                        "structured_result": {
                            "response": "hello",
                        },
                        "artifacts": [],
                        "logs": [],
                        "usage": {},
                        "errors": [],
                        "evidence_refs": [],
                    },
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        "vajra.runtime.http_worker_transport.urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = HTTPWorkerTransport(
        "http://worker/infer",
    ).execute(make_job())

    assert result.status == "completed"
    assert result.correlation_id == "corr-001"
    assert result.structured_result == {"response": "hello"}
