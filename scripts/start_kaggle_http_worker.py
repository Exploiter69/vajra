#!/usr/bin/env python3
"""Start a reusable VAJRA Ollama worker without re-pulling an existing model."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request


MODEL = os.environ.get("VAJRA_WORKER_MODEL", "qwen2.5-coder:32b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1:11434")
WORKER_HOST = os.environ.get("VAJRA_WORKER_HOST", "127.0.0.1")
WORKER_PORT = os.environ.get("VAJRA_WORKER_PORT", "8787")
OLLAMA_URL = f"http://{OLLAMA_HOST}"


def ollama_ready() -> bool:
    try:
        with urllib.request.urlopen(OLLAMA_URL, timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def model_present() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode())
        return any(item.get("name") == MODEL for item in payload.get("models", []))
    except Exception:
        return False


def main() -> int:
    ollama = shutil.which("ollama")
    if ollama is None:
        raise SystemExit(
            "ollama is not installed in this runtime. Bootstrap it once, then rerun."
        )

    if not ollama_ready():
        env = os.environ.copy()
        env["OLLAMA_HOST"] = OLLAMA_HOST
        subprocess.Popen(
            [ollama, "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        for _ in range(60):
            if ollama_ready():
                break
            time.sleep(1)
        else:
            raise SystemExit("Ollama did not become ready within 60 seconds.")

    if not model_present():
        print(f"Model {MODEL} is absent; pulling it once.")
        subprocess.run([ollama, "pull", MODEL], check=True)
    else:
        print(f"Model {MODEL} already present; skipping pull.")

    env = os.environ.copy()
    env["VAJRA_WORKER_HOST"] = WORKER_HOST
    env["VAJRA_WORKER_PORT"] = WORKER_PORT
    env["VAJRA_WORKER_MODEL"] = MODEL
    env["VAJRA_OLLAMA_URL"] = OLLAMA_URL
    print(f"Starting VAJRA worker on http://{WORKER_HOST}:{WORKER_PORT}")
    os.execvpe("python", ["python", "-m", "vajra.runtime.kaggle_worker_server"], env)


if __name__ == "__main__":
    raise SystemExit(main())
