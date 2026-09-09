from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.request import Request, urlopen

from vajra.runtime.kaggle_worker import KaggleWorkerAdapter
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


@dataclass(frozen=True)
class HTTPWorkerTransport:
    """HTTP transport from the VAJRA control plane to a worker server."""

    endpoint: str
    timeout_seconds: int = 180

    def __post_init__(self) -> None:
        object.__setattr__(self, "_adapter", KaggleWorkerAdapter())

    def dispatch(self, job: WorkerJob) -> None:
        """Deliver a WorkerJob to the remote worker.

        This transport only delivers the job. Result acceptance remains
        the responsibility of the Oracle/control-plane acceptance boundary.
        """

        payload = self._adapter.encode_job(job).encode("utf-8")

        request = Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
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
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urlopen(request, timeout=self.timeout_seconds) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(
                    f"Worker returned HTTP status {response.status}"
                )

            encoded_result = response.read().decode("utf-8")

        return self._adapter.decode_result(encoded_result)
