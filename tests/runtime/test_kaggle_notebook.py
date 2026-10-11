from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_canonical_kaggle_notebook_is_valid_and_authenticated() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    notebook_path = repo_root / "infra/kaggle/vajra_qwen3_coder_t4x2.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))

    cells = notebook["cells"]
    assert len(cells) >= 5
    markdown = "".join(cells[0]["source"])
    boot = "".join(cells[1]["source"])
    worker = "".join(cells[2]["source"])
    smoke = "".join(cells[3]["source"])
    tunnel = "".join(cells[4]["source"])

    assert "f2cc7282ce0042641df55e0e563b75e824e2b647" in markdown
    assert "cmake --build" in boot
    assert "CMAKE_CUDA_ARCHITECTURES=75" in boot
    assert "VAJRA_WORKER_TOKEN" in worker
    assert "Authorization" in smoke
    assert "payload['protocol_version']" in smoke
    assert "trycloudflare.com" in tunnel

    for index, cell in enumerate(cells[1:], start=1):
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        lines = source.splitlines()
        if lines and lines[0].startswith("%%bash"):
            source = "\n".join(lines[1:]) + "\n"
        result = subprocess.run(
            ["bash", "-n"],
            input=source,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"Kaggle notebook cell {index} has invalid shell syntax: "
            f"{result.stderr}"
        )
