from vajra.runtime.worker_provider import HTTPWorkerProvider, WorkerProviderError


def test_worker_provider_accepts_healthy_matching_worker(monkeypatch):
    responses = {
        "http://worker/health": {
            "status": "ok",
            "worker": "kaggle-worker",
            "protocol": "vajra-worker-v1",
            "model": "qwen2.5-coder:32b",
        },
        "http://worker/capabilities": {
            "worker": "kaggle-worker",
            "capabilities": ["completion"],
        },
    }

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            import json
            return json.dumps(responses[self.url]).encode()

    from vajra.runtime import worker_provider

    original = worker_provider.urlopen

    def fake_urlopen(request, timeout):
        response = FakeResponse()
        response.url = request.full_url
        return response

    monkeypatch.setattr(worker_provider, "urlopen", fake_urlopen)
    endpoint = HTTPWorkerProvider(
        "http://worker/infer",
        expected_model="qwen2.5-coder:32b",
    ).ensure_ready()
    assert endpoint.worker_id == "kaggle-worker"
    assert endpoint.infer_url == "http://worker/infer"
    assert endpoint.capabilities == ("completion",)
    monkeypatch.setattr(worker_provider, "urlopen", original)


def test_worker_provider_rejects_unhealthy_worker(monkeypatch):
    from vajra.runtime import worker_provider

    def fake_urlopen(request, timeout):
        class Response:
            status = 503
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return b'{"status":"unhealthy"}'
        return Response()

    monkeypatch.setattr(worker_provider, "urlopen", fake_urlopen)
    try:
        HTTPWorkerProvider("http://worker/infer").ensure_ready()
    except WorkerProviderError as exc:
        assert "health check failed" in str(exc)
    else:
        raise AssertionError("unhealthy worker must be rejected")


def test_worker_provider_rejects_wrong_model(monkeypatch):
    from vajra.runtime import worker_provider

    responses = {
        "http://worker/health": {
            "status": "ok",
            "worker": "worker",
            "protocol": "vajra-worker-v1",
            "model": "wrong-model",
        },
        "http://worker/capabilities": {"worker": "worker", "capabilities": []},
    }

    def fake_urlopen(request, timeout):
        class Response:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                import json
                return json.dumps(responses[request.full_url]).encode()
        return Response()

    monkeypatch.setattr(worker_provider, "urlopen", fake_urlopen)
    try:
        HTTPWorkerProvider(
            "http://worker/infer",
            expected_model="qwen2.5-coder:32b",
        ).ensure_ready()
    except WorkerProviderError as exc:
        assert "model mismatch" in str(exc)
    else:
        raise AssertionError("wrong worker model must be rejected")
