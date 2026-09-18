from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path("/kaggle/working")
JOB_PATH = ROOT / "worker_job.json"
RESULT_PATH = ROOT / "worker_result.json"
EMBEDDED_JOB_JSON: str | None = None
MODEL = os.environ.get("VAJRA_MODEL", "qwen2.5-coder:32b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
PROTOCOL = "vajra-worker-v1"


def run(command: tuple[str, ...]) -> None:
    subprocess.run(command, check=True, text=True)


def _ollama_executable() -> str | None:
    for candidate in (
        "ollama",
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
        "/opt/ollama/bin/ollama",
        str(ROOT / "ollama" / "bin" / "ollama"),
    ):
        probe = subprocess.run(
            ("bash", "-lc", f"command -v {candidate}" if candidate == "ollama" else f"test -x {candidate}"),
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return candidate if candidate != "ollama" else probe.stdout.strip()
    return None


def _install_ollama_user_local() -> str:
    target = ROOT / "ollama"
    archive = ROOT / "ollama-linux-amd64.tar.zst"
    target.mkdir(parents=True, exist_ok=True)
    run(
        (
            "bash",
            "-lc",
            "curl -fL https://ollama.com/download/ollama-linux-amd64.tar.zst "
            f"-o {archive}",
        )
    )
    run(("tar", "--zstd", "-xf", str(archive), "-C", str(target)))
    executable = target / "bin" / "ollama"
    if not executable.is_file():
        raise RuntimeError(f"Ollama archive did not contain {executable}")
    return str(executable)


def ensure_ollama() -> None:
    ollama = _ollama_executable()
    if ollama is None:
        ollama = _install_ollama_user_local()

    probe = subprocess.run((ollama, "list"), capture_output=True, text=True)
    if probe.returncode != 0:
        subprocess.Popen(
            (ollama, "serve"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if subprocess.run(
                (ollama, "list"), capture_output=True
            ).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Ollama did not become ready")

    listing = subprocess.run(
        (ollama, "list"), capture_output=True, text=True, check=True
    ).stdout
    if MODEL not in listing:
        run((ollama, "pull", MODEL))


def infer(prompt: str) -> tuple[str, dict]:
    payload = json.dumps(
        {"model": MODEL, "prompt": prompt, "stream": False, "format": "json"}
    ).encode("utf-8")
    request = Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=600) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data.get("response", "")), {
        "prompt_eval_count": int(data.get("prompt_eval_count") or 0),
        "eval_count": int(data.get("eval_count") or 0),
        "total_duration": int(data.get("total_duration") or 0),
    }


def main() -> int:
    if JOB_PATH.is_file():
        payload = json.loads(JOB_PATH.read_text(encoding="utf-8"))
    elif EMBEDDED_JOB_JSON is not None:
        payload = json.loads(EMBEDDED_JOB_JSON)
    else:
        raise FileNotFoundError(f"worker job not found: {JOB_PATH}")
    if payload.get("protocol_version") != PROTOCOL or payload.get("type") != "worker_job":
        raise ValueError("unsupported worker job envelope")
    job = payload.get("job")
    if not isinstance(job, dict):
        raise ValueError("worker job payload missing")

    prompt = job.get("context_bundle", {}).get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("worker job has no prompt")

    try:
        ensure_ollama()
        response, usage = infer(prompt)
        result = {
            "status": "completed",
            "correlation_id": job.get("correlation_id"),
            "structured_result": {"response": response},
            "artifacts": [],
            "logs": ["qwen inference completed through Ollama"],
            "usage": usage,
            "errors": [],
            "evidence_refs": [],
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "correlation_id": job.get("correlation_id"),
            "structured_result": {},
            "artifacts": [],
            "logs": [],
            "usage": {},
            "errors": [f"{type(exc).__name__}: {exc}"],
            "evidence_refs": [],
        }

    envelope = {"protocol_version": PROTOCOL, "type": "worker_result", "result": result}
    RESULT_PATH.write_text(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
