#!/usr/bin/env python3
"""Validate a live VAJRA HTTP worker and exercise two real requests."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from vajra.routing.contracts import BudgetEnvelope, ModelIdentity, ModelRequest
from vajra.runtime.remote_model import RemoteWorkerModelAdapter
from vajra.runtime.worker_provider import HTTPWorkerProvider


ENDPOINT = os.environ.get("VAJRA_KAGGLE_WORKER_URL")
MODEL = os.environ.get("VAJRA_WORKER_MODEL", "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M")


def main() -> int:
    if not ENDPOINT:
        print("VAJRA_KAGGLE_WORKER_URL is required", file=sys.stderr)
        return 2

    provider = HTTPWorkerProvider(
        ENDPOINT,
        expected_model=MODEL,
        timeout_seconds=10,
    )
    endpoint = provider.ensure_ready()

    print("=== PERSISTENT WORKER PREFLIGHT ===")
    print(f"worker: {endpoint.worker_id}")
    print(f"protocol: {endpoint.protocol}")
    print(f"model: {endpoint.model}")
    print(f"capabilities: {', '.join(endpoint.capabilities)}")
    print("health: READY")

    adapter = RemoteWorkerModelAdapter(
        ENDPOINT,
        ModelIdentity("kaggle", MODEL, "ollama", "http-worker"),
        timeout_seconds=180,
    )

    for index, prompt in enumerate(
        (
            "Return exactly: VAJRA_PERSISTENT_WORKER_OK_1",
            "Return exactly: VAJRA_PERSISTENT_WORKER_OK_2",
        ),
        start=1,
    ):
        request = ModelRequest(
            request_id=f"persistent-worker-smoke-{index}",
            run_id="persistent-worker-smoke",
            step_id=f"step-{index}",
            attempt_id=f"attempt-{index}",
            task=prompt,
            context={"revision": "smoke"},
            deadline=datetime.now(timezone.utc).replace(
                microsecond=0
            ).isoformat(),
            output_schema={"type": "object"},
            budget=BudgetEnvelope(max_output_size=512, max_worker_runtime_seconds=180),
        )
        result = adapter.invoke(request)
        print(f"request_{index}: {result.status}")
        print(f"response_{index}: {result.structured_output.get('response', '')}")
        if result.status != "SUCCEEDED":
            print(f"errors_{index}: {result.errors}", file=sys.stderr)
            return 1

    print("reuse: VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
