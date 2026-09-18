from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.request import Request, urlopen


class WorkerProviderError(RuntimeError):
    """Worker cannot be discovered or made ready."""


@dataclass(frozen=True)
class WorkerEndpoint:
    """A ready worker endpoint plus immutable capability metadata."""

    infer_url: str
    health_url: str
    worker_id: str
    protocol: str
    model: str
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("infer_url", "health_url", "worker_id", "protocol", "model"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")


class WorkerProvider:
    """Provider-neutral lifecycle boundary owned outside model reasoning."""

    def ensure_ready(self) -> WorkerEndpoint:
        raise NotImplementedError


@dataclass(frozen=True)
class HTTPWorkerProvider(WorkerProvider):
    """Readiness adapter for an already-running HTTP worker.

    It deliberately does not automate a provider UI or manufacture a remote
    session. A provider-specific implementation may do so later.
    """

    infer_url: str
    health_url: str | None = None
    timeout_seconds: int = 5
    expected_model: str | None = None
    expected_protocol: str = "vajra-worker-v1"

    def ensure_ready(self) -> WorkerEndpoint:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        health_url = self.health_url or self._derive_health_url()
        try:
            payload = self._get_json(health_url)
        except Exception as exc:
            raise WorkerProviderError(
                f"worker health check failed for {health_url}: {type(exc).__name__}: {exc}"
            ) from exc

        if payload.get("status") != "ok":
            raise WorkerProviderError(f"worker is not healthy: {payload!r}")
        protocol = str(payload.get("protocol", ""))
        if protocol != self.expected_protocol:
            raise WorkerProviderError(
                f"worker protocol mismatch: expected {self.expected_protocol}, got {protocol!r}"
            )
        model = str(payload.get("model", ""))
        if self.expected_model and model != self.expected_model:
            raise WorkerProviderError(
                f"worker model mismatch: expected {self.expected_model}, got {model!r}"
            )

        capabilities = self._capabilities(self._get_json(self._derive_capabilities_url()))
        worker_id = str(payload.get("worker") or capabilities.get("worker") or "remote-worker")
        advertised = capabilities.get("capabilities", ())
        if not isinstance(advertised, list):
            advertised = ()
        return WorkerEndpoint(
            infer_url=self.infer_url,
            health_url=health_url,
            worker_id=worker_id,
            protocol=protocol,
            model=model,
            capabilities=tuple(str(item) for item in advertised),
        )

    def _derive_health_url(self) -> str:
        return self.infer_url.rsplit("/", 1)[0] + "/health"

    def _derive_capabilities_url(self) -> str:
        return self.infer_url.rsplit("/", 1)[0] + "/capabilities"

    def _get_json(self, url: str) -> dict:
        request = Request(url, method="GET")
        with urlopen(request, timeout=self.timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP status {response.status}")
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("worker endpoint returned a non-object JSON payload")
        return value

    @staticmethod
    def _capabilities(payload: dict) -> dict:
        return payload


__all__ = ["HTTPWorkerProvider", "WorkerEndpoint", "WorkerProvider", "WorkerProviderError"]
