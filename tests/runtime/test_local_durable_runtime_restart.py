import json
import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path


def test_execution_survives_physical_process_kill(tmp_path: Path):
    journal = tmp_path / "runtime.jsonl"

    child_code = textwrap.dedent(
        """
        import sys
        import time

        from vajra.runtime.local_durable_runtime import LocalDurableRuntime

        journal = sys.argv[1]
        runtime = LocalDurableRuntime(journal)

        runtime.start_execution("physical-kill-1")

        print("STARTED", flush=True)
        time.sleep(60)
        """
    )

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child_code,
            str(journal),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
        },
    )

    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "STARTED"

        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=5)

        assert process.returncode == -signal.SIGKILL

        from vajra.runtime.local_durable_runtime import LocalDurableRuntime

        restarted = LocalDurableRuntime(journal)

        recoverable = restarted.recoverable_executions()

        assert len(recoverable) == 1
        assert recoverable[0].execution_id == "physical-kill-1"
        assert recoverable[0].state == "STARTED"

    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_execution_recovers_and_completes_after_physical_process_kill(
    tmp_path: Path,
):
    journal = tmp_path / "runtime.jsonl"

    child_code = textwrap.dedent(
        """
        import sys
        import time

        from vajra.runtime.local_durable_runtime import LocalDurableRuntime

        journal = sys.argv[1]
        runtime = LocalDurableRuntime(journal)

        runtime.start_execution("physical-recovery-1")

        print("STARTED", flush=True)
        time.sleep(60)
        """
    )

    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            child_code,
            str(journal),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).parents[2] / "src"),
        },
    )

    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "STARTED"

        os.kill(process.pid, signal.SIGKILL)
        process.wait(timeout=5)

        assert process.returncode == -signal.SIGKILL

        restarted = __import__(
            "vajra.runtime.local_durable_runtime",
            fromlist=["LocalDurableRuntime"],
        ).LocalDurableRuntime(journal)

        recoverable = restarted.recoverable_executions()

        assert len(recoverable) == 1
        assert recoverable[0].execution_id == "physical-recovery-1"

        recovered = restarted.recover(
            "physical-recovery-1",
            lambda: "recovered-after-kill",
        )

        assert recovered.state == "COMPLETED"
        assert recovered.result == "recovered-after-kill"

        final_runtime = __import__(
            "vajra.runtime.local_durable_runtime",
            fromlist=["LocalDurableRuntime"],
        ).LocalDurableRuntime(journal)

        persisted = final_runtime.get_execution("physical-recovery-1")

        assert persisted is not None
        assert persisted.state == "COMPLETED"
        assert persisted.result == "recovered-after-kill"

    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
