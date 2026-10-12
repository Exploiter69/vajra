from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from third_engineering_run import prepare_workspace  # noqa: E402


def test_prepare_workspace_refuses_nonempty_directory_without_mutating_it(tmp_path):
    workspace = tmp_path / "existing"
    workspace.mkdir()
    sentinel = workspace / "important.txt"
    sentinel.write_text("keep me\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        prepare_workspace(workspace)

    assert sentinel.read_text(encoding="utf-8") == "keep me\n"
    assert not (workspace / ".git").exists()


def test_prepare_workspace_seeds_an_empty_directory(tmp_path):
    workspace = tmp_path / "new-workspace"
    workspace.mkdir()

    revision = prepare_workspace(workspace)

    assert revision
    assert (workspace / "calculator.py").is_file()
    assert (workspace / "test_calculator.py").is_file()
    assert "def add" in (workspace / "calculator.py").read_text(encoding="utf-8")
    assert "add(2, 3) == 5" in (workspace / "test_calculator.py").read_text(encoding="utf-8")
