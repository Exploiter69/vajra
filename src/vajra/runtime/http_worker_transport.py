from __future__ import annotations

import ipaddress
import json
import os
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from vajra.runtime.kaggle_worker import KaggleWorkerAdapter
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


@dataclass(frozen=True)
class HTTPWorkerTransport:
    """HTTP transport from the VAJRA control plane to a worker server."""

    endpoint: str
    timeout_seconds: int = 180

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("worker endpoint must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("worker endpoint must not embed credentials in the URL")
        object.__setattr__(self, "_adapter", KaggleWorkerAdapter())

    def _headers(self) -> dict[str, str]:
        parsed = urlparse(self.endpoint)
        try:
            loopback = parsed.hostname == "localhost" or ipaddress.ip_address(
                parsed.hostname or ""
            ).is_loopback
        except ValueError:
            loopback = False

        token = os.environ.get("VAJRA_WORKER_TOKEN", "").strip()
        if not loopback and parsed.scheme != "https":
            raise RuntimeError("remote worker endpoints must use HTTPS")
        if not loopback and not token:
            raise RuntimeError(
                "VAJRA_WORKER_TOKEN is required for remote worker endpoints"
            )

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def dispatch(self, job: WorkerJob) -> None:
        """Deliver a WorkerJob to the remote worker.

        This transport only delivers the job. Result acceptance remains
        the responsibility of the Oracle/control-plane acceptance boundary.
        """

        payload = self._adapter.encode_job(job).encode("utf-8")

        request = Request(
            self.endpoint,
            data=payload,
            headers=self._headers(),
            method="POST",
        )

        with urlopen(request, timeout=self.timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(
                    f"Worker returned HTTP status {response.status}"
                )

            # Read the response so the HTTP exchange is fully consumed.
            response.read()

    def execute(self, job: WorkerJob) -> WorkerResult:
        """Send a job and decode the returned WorkerResult.

        This convenience method is intentionally separate from dispatch().
        It does not mutate canonical Run state or authorize/accept results.
        """

        payload = self._adapter.encode_job(job).encode("utf-8")

        request = Request(
            self.endpoint,
            data=payload,
            headers=self._headers(),
            method="POST",
        )

        with urlopen(request, timeout=self.timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(
                    f"Worker returned HTTP status {response.status}"
                )

            encoded_result = response.read().decode("utf-8")

        return self._adapter.decode_result(encoded_result)
