#!/usr/bin/env python3
"""Run the reusable VAJRA Kaggle worker as one foreground notebook-owned process.

The notebook cell stays alive while this supervisor owns Ollama and the VAJRA
HTTP worker. An existing model is reused; a missing model is pulled exactly
once. This is intentionally runtime-scoped: Kaggle may destroy the runtime.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request


MODEL = os.environ.get("VAJRA_WORKER_MODEL", "qwen2.5-coder:32b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
WORKER_HOST = os.environ.get("VAJRA_WORKER_HOST", "127.0.0.1")
WORKER_PORT = os.environ.get("VAJRA_WORKER_PORT", "8787")
OLLAMA_URL = f"http://{OLLAMA_HOST}"
OLLAMA_MODELS = os.environ.get("OLLAMA_MODELS", "/root/.ollama/models")
WORKER_ID = os.environ.get("VAJRA_WORKER_ID", "kaggle-t4-persistent-01")

ollama_process: subprocess.Popen[str] | None = None
worker_process: subprocess.Popen[str] | None = None
stopping = False


def get_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode())


def ollama_ready() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=3) as response:
            return (
                response.status == 200
                and response.read().decode().strip() == "Ollama is running"
            )
    except Exception:
        return False


def model_present() -> bool:
    try:
        payload = get_json(f"{OLLAMA_URL}/api/tags")
        return any(item.get("name") == MODEL for item in payload.get("models", []))
    except Exception:
        return False


def worker_ready() -> bool:
    try:
        payload = get_json(
            f"http://{WORKER_HOST}:{WORKER_PORT}/health",
            timeout=3,
        )
        return (
            payload.get("status") == "ok"
            and payload.get("model") == MODEL
            and payload.get("model_available") is True
            and payload.get("ollama") is True
        )
    except Exception:
        return False


def install_ollama() -> str:
    target = "/kaggle/working/ollama"
    binary = f"{target}/bin/ollama"
    if os.path.isfile(binary) and os.access(binary, os.X_OK):
        return binary

    print("Ollama: not installed — installing once into /kaggle/working/ollama", flush=True)
    installer = "/tmp/ollama-install.sh"
    subprocess.run(
        ["bash", "-lc", f"curl -fsSL https://ollama.com/install.sh -o {installer} && sh {installer}"],
        check=True,
    )
    candidates = [binary, "/usr/local/bin/ollama", shutil.which("ollama")]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("Ollama installation completed but no executable was found.")

def find_ollama() -> str:
    configured = os.environ.get("VAJRA_OLLAMA_BIN")
    candidates = [
        configured,
        shutil.which("ollama"),
        "/kaggle/working/ollama/bin/ollama",
        "/usr/local/bin/ollama",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return install_ollama()


def start_ollama(ollama: str) -> None:
    global ollama_process
    if ollama_ready():
        print("Ollama: already running", flush=True)
        return

    env = os.environ.copy()
    env["OLLAMA_HOST"] = OLLAMA_HOST
    env["OLLAMA_MODELS"] = OLLAMA_MODELS

    print(f"Ollama: starting {ollama}", flush=True)
    ollama_process = subprocess.Popen(
        [ollama, "serve"],
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if ollama_ready():
            print(f"Ollama: READY pid={ollama_process.pid}", flush=True)
            return
        if ollama_process.poll() is not None:
            raise RuntimeError(
                f"Ollama exited during startup with code {ollama_process.returncode}"
            )
        time.sleep(1)

    raise TimeoutError("Ollama did not become ready within 90 seconds")


def ensure_model(ollama: str) -> None:
    if model_present():
        print(f"Model: {MODEL} already present — SKIP PULL", flush=True)
        return

    print(f"Model: {MODEL} absent — pulling ONCE", flush=True)
    env = os.environ.copy()
    env["OLLAMA_HOST"] = OLLAMA_HOST
    env["OLLAMA_MODELS"] = OLLAMA_MODELS
    subprocess.run([ollama, "pull", MODEL], env=env, check=True)
    if not model_present():
        raise RuntimeError(f"Model pull completed but {MODEL} is not visible")
    print(f"Model: {MODEL} READY", flush=True)


def start_worker() -> None:
    global worker_process
    if worker_ready():
        print("VAJRA worker: already running", flush=True)
        return

    env = os.environ.copy()
    env["VAJRA_WORKER_HOST"] = WORKER_HOST
    env["VAJRA_WORKER_PORT"] = WORKER_PORT
    env["VAJRA_WORKER_MODEL"] = MODEL
    env["VAJRA_OLLAMA_URL"] = OLLAMA_URL
    env["VAJRA_WORKER_ID"] = WORKER_ID

    print(
        f"VAJRA worker: starting http://{WORKER_HOST}:{WORKER_PORT}",
        flush=True,
    )
    worker_process = subprocess.Popen(
        [sys.executable, "-m", "vajra.runtime.kaggle_worker_server"],
        env=env,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if worker_ready():
            print(
                f"VAJRA worker: READY id={WORKER_ID} model={MODEL}",
                flush=True,
            )
            return
        if worker_process.poll() is not None:
            raise RuntimeError(
                f"VAJRA worker exited during startup with code {worker_process.returncode}"
            )
        time.sleep(1)

    raise TimeoutError("VAJRA worker did not become ready within 30 seconds")


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def shutdown(*_args: object) -> None:
    global stopping
    if stopping:
        return
    stopping = True
    print("\n=== VAJRA WORKER STOPPING ===", flush=True)
    stop_process(worker_process)
    stop_process(ollama_process)
    print("VAJRA worker stopped.", flush=True)


def main() -> int:
    global ollama_process, worker_process

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("=== VAJRA PERSISTENT WORKER ===", flush=True)
    print(f"model: {MODEL}", flush=True)
    print(f"ollama: {OLLAMA_URL}", flush=True)
    print(f"worker: http://{WORKER_HOST}:{WORKER_PORT}", flush=True)
    print(f"worker_id: {WORKER_ID}", flush=True)
    print(f"model_store: {OLLAMA_MODELS}", flush=True)
    print(flush=True)

    ollama = find_ollama()
    start_ollama(ollama)
    ensure_model(ollama)
    start_worker()

    print("\n=== VAJRA WORKER READY ===", flush=True)
    print("Keep this notebook cell running.", flush=True)
    print("No model pull will occur while the existing model is present.", flush=True)
    print(flush=True)

    try:
        while not stopping:
            if ollama_process is not None and ollama_process.poll() is not None:
                print("Ollama exited; restarting...", flush=True)
                ollama_process = None
                start_ollama(ollama)

            if not worker_ready():
                if worker_process is not None and worker_process.poll() is not None:
                    print("VAJRA worker exited; restarting...", flush=True)
                    worker_process = None
                start_worker()

            time.sleep(10)
    finally:
        shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
