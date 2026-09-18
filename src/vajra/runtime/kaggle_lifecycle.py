from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class KaggleLifecycleError(RuntimeError):
    """Kaggle kernel lifecycle command failed."""


@dataclass(frozen=True)
class KaggleKernelLauncher:
    """Start/stop a Kaggle kernel through the official CLI.

    This launcher only controls the Kaggle batch runtime. It never reports
    worker readiness; ManagedWorkerProvider must independently prove the
    configured HTTP endpoint before a lease is created.
    """

    kernel_path: Path
    timeout_seconds: int = 900
    executable: str = "kaggle"
    kernel_ref: str | None = None

    def start(self) -> None:
        command: list[str] = [
            self.executable,
            "kernels",
            "push",
            "-p",
            str(self.kernel_path),
            "--timeout",
            str(self.timeout_seconds),
        ]
        self._run(command)

    def stop(self) -> None:
        if not self.kernel_ref:
            return
        self._run(
            [
                self.executable,
                "kernels",
                "delete",
                self.kernel_ref,
                "--yes",
            ]
        )

    def status(self) -> str:
        if not self.kernel_ref:
            raise KaggleLifecycleError("kernel_ref is required for status")
        return self._run(
            [self.executable, "kernels", "status", self.kernel_ref],
            capture_output=True,
        )

    def _run(self, command: Sequence[str], *, capture_output: bool = False) -> str:
        try:
            completed = subprocess.run(
                tuple(command),
                check=True,
                text=True,
                capture_output=capture_output,
            )
        except FileNotFoundError as exc:
            raise KaggleLifecycleError(
                f"Kaggle CLI not found: {self.executable}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise KaggleLifecycleError(
                f"Kaggle CLI command failed ({exc.returncode}): {detail}"
            ) from exc
        return completed.stdout.strip() if capture_output else ""


__all__ = ["KaggleKernelLauncher", "KaggleLifecycleError"]
