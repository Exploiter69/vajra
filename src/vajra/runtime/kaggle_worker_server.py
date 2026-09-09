from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

from vajra.runtime.kaggle_worker import KaggleWorkerAdapter
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult


HOST = "127.0.0.1"
PORT = 8787
OLLAMA_API = "http://127.0.0.1:11434"
MODEL = "qwen2.5-coder:32b"

adapter = KaggleWorkerAdapter()


def ollama_health() -> bool:
    try:
        request = Request(OLLAMA_API, method="GET")
        with urlopen(request, timeout=5) as response:
            return (
                response.status == 200
                and response.read().decode().strip()
                == "Ollama is running"
            )
    except Exception:
        return False


def infer(job: WorkerJob) -> WorkerResult:
    started = time.time()

    prompt = job.context_bundle.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return WorkerResult(
            status="failed",
            correlation_id=job.correlation_id,
            errors=("context_bundle.prompt is required",),
            logs=("worker rejected job: missing prompt",),
        )

    options = {
        "temperature": 0,
        "num_predict": int(job.budget.get("max_output_tokens", 128)),
    }

    payload = json.dumps(
        {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
    ).encode()

    request = Request(
        f"{OLLAMA_API}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        timeout = int(job.budget.get("timeout_seconds", 300))

        with urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode())

        elapsed = time.time() - started

        return WorkerResult(
            status="completed",
            correlation_id=job.correlation_id,
            structured_result={
                "response": result.get("response", ""),
                "model": MODEL,
            },
            logs=(
                f"model={MODEL}",
                f"elapsed_seconds={elapsed:.3f}",
            ),
            usage={
                "total_duration_ns": result.get("total_duration"),
                "load_duration_ns": result.get("load_duration"),
                "prompt_eval_count": result.get("prompt_eval_count"),
                "eval_count": result.get("eval_count"),
            },
        )

    except Exception as exc:
        return WorkerResult(
            status="failed",
            correlation_id=job.correlation_id,
            errors=(f"{type(exc).__name__}: {exc}",),
            logs=(
                f"model={MODEL}",
                f"elapsed_seconds={time.time() - started:.3f}",
            ),
        )


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", "0"))
        return self.rfile.read(length).decode()

    def do_GET(self) -> None:
        if self.path == "/health":
            healthy = ollama_health()
            self._send(
                200 if healthy else 503,
                {
                    "status": "ok" if healthy else "unhealthy",
                    "worker": "vajra-kaggle-worker",
                    "protocol": adapter.protocol_version,
                    "model": MODEL,
                },
            )
            return

        if self.path == "/capabilities":
            self._send(
                200,
                {
                    "worker": "vajra-kaggle-worker",
                    "protocol": adapter.protocol_version,
                    "runtime": "ollama",
                    "model": MODEL,
                    "capabilities": ["completion"],
                },
            )
            return

        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/infer":
            self._send(404, {"error": "not_found"})
            return

        try:
            encoded_job = self._read_body()
            job = adapter.decode_job(encoded_job)
            result = infer(job)
            self._send(
                200 if result.status == "completed" else 502,
                json.loads(adapter.encode_result(result)),
            )
        except Exception as exc:
            self._send(
                400,
                {
                    "protocol_version": adapter.protocol_version,
                    "type": "worker_result",
                    "result": {
                        "status": "failed",
                        "correlation_id": None,
                        "structured_result": None,
                        "artifacts": [],
                        "logs": [],
                        "usage": {},
                        "errors": [f"{type(exc).__name__}: {exc}"],
                        "evidence_refs": [],
                    },
                },
            )

    def log_message(self, *_args) -> None:
        pass


def serve() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"VAJRA Kaggle worker listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    serve()
