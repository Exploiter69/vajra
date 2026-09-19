from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from vajra.runtime.kaggle_lifecycle import KaggleKernelLauncher, KaggleLifecycleError
from vajra.runtime.kaggle_worker import KaggleWorkerAdapter
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


class KaggleBatchWorkerError(RuntimeError):
    """A headless Kaggle batch worker could not complete safely."""


@dataclass(frozen=True)
class KaggleBatchWorkerTransport:
    """Execute one WorkerJob through a disposable Kaggle batch kernel.

    The transport owns delivery and result retrieval only. It never mutates
    canonical Run state and never authorizes, verifies, or promotes a result.
    """

    kernel_template: Path
    kernel_ref: str
    executable: str = "kaggle"
    timeout_seconds: int = 900
    poll_interval_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not self.kernel_ref.strip():
            raise ValueError("kernel_ref must not be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")

    def execute(self, job: WorkerJob) -> WorkerResult:
        deadline = self._deadline(job)
        adapter = KaggleWorkerAdapter()

        if time.monotonic() >= deadline:
            raise KaggleBatchWorkerError("worker job deadline already expired")

        with tempfile.TemporaryDirectory(prefix="vajra-kaggle-") as temp:
            kernel_dir = Path(temp) / "kernel"
            shutil.copytree(self.kernel_template, kernel_dir)
            metadata_path = kernel_dir / "kernel-metadata.json"
            if not metadata_path.is_file():
                raise KaggleBatchWorkerError("kernel template has no kernel-metadata.json")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["id"] = self.kernel_ref
            metadata_path.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            job_json = adapter.encode_job(job)
            (kernel_dir / "worker_job.json").write_text(job_json, encoding="utf-8")
            worker_path = kernel_dir / "worker.py"
            worker_source = worker_path.read_text(encoding="utf-8")
            marker = "EMBEDDED_JOB_JSON: str | None = None"
            if marker not in worker_source:
                raise KaggleBatchWorkerError(
                    "kernel template worker.py has no embedded-job marker"
                )
            worker_source = worker_source.replace(
                marker,
                f"EMBEDDED_JOB_JSON: str | None = {job_json!r}",
                1,
            )
            worker_path.write_text(worker_source, encoding="utf-8")

            launcher = KaggleKernelLauncher(
                kernel_dir,
                timeout_seconds=self.timeout_seconds,
                executable=self.executable,
                kernel_ref=self.kernel_ref,
            )
            try:
                launcher.start()
                self._wait_for_completion(launcher, deadline)
                output_dir = Path(temp) / "output"
                launcher.output(output_dir, file_pattern="worker_result.json")
                result_path = output_dir / "worker_result.json"
                if not result_path.is_file():
                    raise KaggleBatchWorkerError(
                        "Kaggle output did not contain worker_result.json"
                    )
                result = adapter.decode_result(result_path.read_text(encoding="utf-8"))
            except KaggleLifecycleError as exc:
                raise KaggleBatchWorkerError(str(exc)) from exc

        if result.correlation_id != job.correlation_id:
            raise KaggleBatchWorkerError(
                "worker result correlation_id does not match dispatched job"
            )
        return result

    def dispatch(self, job: WorkerJob) -> None:
        """Compatibility with WorkerTransport; batch execution is synchronous."""
        self.execute(job)

    @staticmethod
    def _deadline(job: WorkerJob) -> float:
        try:
            parsed = datetime.fromisoformat(job.deadline.replace("Z", "+00:00"))
        except ValueError as exc:
            raise KaggleBatchWorkerError("invalid WorkerJob deadline") from exc
        return time.monotonic() + (parsed - datetime.now(timezone.utc)).total_seconds()

    def _wait_for_completion(
        self, launcher: KaggleKernelLauncher, deadline: float
    ) -> None:
        while time.monotonic() < deadline:
            status = launcher.status().lower()
            if any(token in status for token in ("error", "failed", "cancelled")):
                raise KaggleBatchWorkerError(f"Kaggle kernel failed: {status}")
            if any(token in status for token in ("complete", "finished", "success")):
                return
            time.sleep(min(self.poll_interval_seconds, max(0.0, deadline - time.monotonic())))
        raise KaggleBatchWorkerError("Kaggle batch worker deadline expired")
