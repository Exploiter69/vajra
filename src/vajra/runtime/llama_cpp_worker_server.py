from __future__ import annotations

import hmac
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

from vajra.runtime.kaggle_worker import KaggleWorkerAdapter
from vajra.runtime.worker_protocol import WorkerJob, WorkerResult

HOST = os.environ.get("VAJRA_WORKER_HOST", "127.0.0.1")
PORT = int(os.environ.get("VAJRA_WORKER_PORT", "8787"))
LLAMA_API = os.environ.get("VAJRA_LLAMA_URL", "http://127.0.0.1:8000").rstrip("/")
MODEL = os.environ.get("VAJRA_WORKER_MODEL", "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M")
WORKER_ID = os.environ.get("VAJRA_WORKER_ID", "kaggle-t4-llama-cpp-01")
adapter = KaggleWorkerAdapter()


def is_authorized(supplied: str, expected_token: str) -> bool:
    return len(expected_token) >= 32 and hmac.compare_digest(
        supplied, f"Bearer {expected_token}"
    )

def llama_ready() -> bool:
    try:
        req = Request(f"{LLAMA_API}/health", method="GET")
        with urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False

def infer(job: WorkerJob) -> WorkerResult:
    started = time.time()
    prompt = job.context_bundle.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return WorkerResult(status="failed", correlation_id=job.correlation_id,
                            errors=("context_bundle.prompt is required",))
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": int(job.budget.get("max_output_tokens", 128)),
        "stream": False,
    }).encode()
    req = Request(
        f"{LLAMA_API}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        timeout = int(job.budget.get("timeout_seconds", 300))
        with urlopen(req, timeout=timeout) as r:
            result = json.loads(r.read().decode())
        choice = (result.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content", "")
        usage = result.get("usage") or {}
        return WorkerResult(
            status="completed",
            correlation_id=job.correlation_id,
            structured_result={"response": content, "model": MODEL},
            logs=(f"model={MODEL}", f"elapsed_seconds={time.time()-started:.3f}"),
            usage={
                "prompt_eval_count": usage.get("prompt_tokens"),
                "eval_count": usage.get("completion_tokens"),
            },
        )
    except Exception as exc:
        return WorkerResult(
            status="failed",
            correlation_id=job.correlation_id,
            errors=(f"{type(exc).__name__}: {exc}",),
            logs=(f"model={MODEL}", f"elapsed_seconds={time.time()-started:.3f}"),
        )

class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_job(self) -> WorkerJob:
        return adapter.decode_job(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())

    def do_GET(self) -> None:
        if self.path == "/health":
            healthy = llama_ready()
            self._send(200 if healthy else 503, {
                "status": "ok" if healthy else "unhealthy",
                "worker": WORKER_ID, "protocol": adapter.protocol_version,
                "model": MODEL, "runtime": "llama.cpp",
            })
            return
        if self.path == "/capabilities":
            self._send(200, {
                "worker": WORKER_ID, "protocol": adapter.protocol_version,
                "runtime": "llama.cpp", "model": MODEL,
                "capabilities": ["completion"],
            })
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/infer":
            self._send(404, {"error": "not_found"})
            return
        expected_token = os.environ.get("VAJRA_WORKER_TOKEN", "")
        if len(expected_token) < 32:
            self._send(503, {"error": "worker_auth_not_configured"})
            return
        if not is_authorized(self.headers.get("Authorization", ""), expected_token):
            self._send(401, {"error": "unauthorized"})
            return
        try:
            result = infer(self._read_job())
            self._send(200 if result.status == "completed" else 502,
                        json.loads(adapter.encode_result(result)))
        except Exception as exc:
            self._send(400, {"error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, *_args) -> None:
        pass

def serve() -> None:
    if len(os.environ.get("VAJRA_WORKER_TOKEN", "")) < 32:
        raise RuntimeError("VAJRA_WORKER_TOKEN must be configured with at least 32 characters")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"VAJRA llama.cpp worker listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    serve()
