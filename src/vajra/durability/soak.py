from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from .chaos import SoakMetrics, SoakSample


@dataclass(frozen=True)
class SoakCounters:
    """Application counters supplied by the runtime under observation."""

    event_count: int = 0
    context_items: int = 0
    worker_leaks: int = 0
    stale_leases: int = 0
    retry_count: int = 0
    verification_failures: int = 0
    provider_failures: int = 0
    clock_anomalies: int = 0


CounterProvider = Callable[[], SoakCounters]
Workload = Callable[[], None]


def _rss_bytes() -> int:
    """Return Linux process RSS without requiring psutil."""
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (FileNotFoundError, OSError, ValueError):
        pass
    return 0


@dataclass(frozen=True)
class SoakConfig:
    duration_seconds: float
    sample_interval_seconds: float = 60.0
    workspace: Path | None = None

    def __post_init__(self) -> None:
        if self.duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if self.sample_interval_seconds <= 0:
            raise ValueError("sample_interval_seconds must be positive")


class SoakRunner:
    """Run a real elapsed-time soak and record the Phase 11 signals.

    This runner deliberately uses a monotonic wall clock. A short accelerated
    run is useful for testing the runner itself, but is never equivalent to the
    configured real duration of a 1h/12h/3d/7d/30d profile.
    """

    def __init__(
        self,
        config: SoakConfig,
        *,
        counter_provider: CounterProvider | None = None,
        workload: Workload | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._counters = counter_provider or (lambda: SoakCounters())
        self._workload = workload or (lambda: None)
        self._monotonic = monotonic
        self._sleep = sleep

    def run(self) -> SoakMetrics:
        start = self._monotonic()
        samples: list[SoakSample] = []
        self._sample(samples, start, start)
        deadline = start + self.config.duration_seconds
        next_sample = start + self.config.sample_interval_seconds

        while True:
            now = self._monotonic()
            if now >= deadline:
                break
            self._workload()
            now = self._monotonic()
            if now >= next_sample or now >= deadline:
                self._sample(samples, start, now)
                while next_sample <= now:
                    next_sample += self.config.sample_interval_seconds
            else:
                self._sleep(min(next_sample - now, deadline - now))

        final_now = self._monotonic()
        if samples[-1].elapsed_seconds != max(0.0, final_now - start):
            self._sample(samples, start, final_now)
        return SoakMetrics(tuple(samples))

    def run_and_write(self, evidence_path: str | Path) -> SoakMetrics:
        """Run the configured real-time campaign and atomically publish JSON evidence."""
        metrics = self.run()
        destination = Path(evidence_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "duration_seconds_configured": self.config.duration_seconds,
            "sample_interval_seconds": self.config.sample_interval_seconds,
            "samples": [asdict(sample) for sample in metrics.samples],
            "completed_elapsed_seconds": metrics.last.elapsed_seconds,
        }
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)
        return metrics

    def _sample(self, samples: list[SoakSample], start: float, now: float) -> None:
        counters = self._counters()
        if any(value < 0 for value in counters.__dict__.values()):
            raise ValueError("soak counters must not be negative")
        disk_bytes = _directory_size(self.config.workspace) if self.config.workspace else 0
        samples.append(
            SoakSample(
                elapsed_seconds=max(0.0, now - start),
                memory_bytes=_rss_bytes(),
                disk_bytes=disk_bytes,
                event_count=counters.event_count,
                context_items=counters.context_items,
                worker_leaks=counters.worker_leaks,
                stale_leases=counters.stale_leases,
                retry_count=counters.retry_count,
                verification_failures=counters.verification_failures,
                provider_failures=counters.provider_failures,
                clock_anomalies=counters.clock_anomalies,
            )
        )


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


__all__ = ["SoakConfig", "SoakCounters", "SoakRunner"]
