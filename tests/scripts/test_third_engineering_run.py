from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from third_engineering_run import git, prepare_workspace, validate_generated_sources  # noqa: E402


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



def test_git_helper_preserves_leading_porcelain_status_column(tmp_path):
    workspace = tmp_path / "porcelain-workspace"
    workspace.mkdir()
    prepare_workspace(workspace)
    (workspace / "calculator.py").write_text(
        (workspace / "calculator.py").read_text(encoding="utf-8")
        + "\n# changed\n",
        encoding="utf-8",
    )

    status = git("status", "--porcelain", cwd=workspace)

    assert status.startswith(" M calculator.py")
    status_lines = status.splitlines()
    changed_paths = {line[3:] for line in status_lines if len(line) >= 4}
    assert changed_paths == {"calculator.py"}



def test_generated_source_validator_accepts_feature_without_regressing_existing_api():
    calculator = (
        '"""Calculator module."""\n\n'
        "def add(a: int, b: int) -> int:\n    return a + b\n\n"
        "def multiply(a, b):\n    return a * b\n"
    )
    tests = (
        "from calculator import add, multiply\n\n"
        "def test_add_existing_behavior() -> None:\n    assert add(2, 3) == 5\n\n"
        "def test_multiply_regression():\n    assert multiply(6, 7) == 42\n"
    )

    assert validate_generated_sources(calculator, tests) == ()


def test_generated_source_validator_rejects_existing_api_and_test_replacement():
    calculator = "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n"
    tests = (
        "from calculator import add, multiply\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n"
        "def test_multiply():\n    assert multiply(6, 7) == 42\n"
    )

    assert validate_generated_sources(calculator, tests) == (
        "typed add API",
        "existing add test",
    )
