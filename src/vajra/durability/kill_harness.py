from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass
from multiprocessing import Process
from pathlib import Path

from vajra.runtime.local_durable_runtime import LocalDurableRuntime

from .chaos import ChaosTarget


@dataclass(frozen=True)
class KillResult:
    target: ChaosTarget
    exit_code: int
    durable_before_kill: bool
    recovered_after_restart: bool


def _durable_child(journal: str, execution_id: str) -> None:
    runtime = LocalDurableRuntime(journal)
    runtime.start_execution(execution_id)
    while True:
        time.sleep(60)


class KillHarness:
    """Exercise every Phase 11 kill domain through a real process boundary.

    Controller, worker, model, network, sandbox and machine failures are
    represented as failure-domain labels around the same disposable child.
    This proves the common durable boundary and restart/recovery behavior; it
    does not claim that the physical implementation of each external domain
    has been independently killed on the host.
    """

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)

    def run_target(self, target: ChaosTarget) -> KillResult:
        journal = self.workspace / f"{target.value}.jsonl"
        execution_id = f"phase11-{target.value}"
        child = Process(target=_durable_child, args=(str(journal), execution_id))
        child.start()
        child.join(timeout=0.5)
        if not child.is_alive():
            raise RuntimeError(f"kill target exited before injection: {target.value}")

        before = LocalDurableRuntime(journal).get_execution(execution_id)
        durable_before_kill = before is not None and before.state == "STARTED"
        os.kill(child.pid, signal.SIGKILL)
        child.join(timeout=2.0)
        if child.is_alive():
            child.kill()
            child.join(timeout=2.0)

        restarted = LocalDurableRuntime(journal)
        recoverable = restarted.recoverable_executions()
        recovered = any(record.execution_id == execution_id for record in recoverable)
        return KillResult(
            target=target,
            exit_code=child.exitcode if child.exitcode is not None else -1,
            durable_before_kill=durable_before_kill,
            recovered_after_restart=recovered,
        )

    def run_all(self) -> tuple[KillResult, ...]:
        return tuple(self.run_target(target) for target in ChaosTarget)


__all__ = ["KillHarness", "KillResult"]
