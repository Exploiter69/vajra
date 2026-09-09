from io import StringIO
from contextlib import redirect_stdout

from vajra.cli import build_parser
from vajra.cli.main import main
from vajra.runtime import RunManager


def test_cli_exposes_vajra_program() -> None:
    parser = build_parser()

    assert parser.prog == "vajra"


def test_cli_exposes_run_commands() -> None:
    parser = build_parser()

    args = parser.parse_args(["run", "list"])
    assert args.command == "run"
    assert args.run_command == "list"


def test_cli_status_requires_run_id() -> None:
    parser = build_parser()

    args = parser.parse_args(["run", "status", "run-1"])

    assert args.command == "run"
    assert args.run_command == "status"
    assert args.run_id == "run-1"


def test_run_create_persists_through_run_manager() -> None:
    manager = RunManager()

    output = StringIO()
    with redirect_stdout(output):
        result = main(
            [
                "run",
                "create",
                "run-1",
                "Build artifact",
                "--repository-id",
                "repo-1",
                "--base-revision",
                "abc123",
                "--acceptance",
                "tests pass",
                "--policy-id",
                "default",
                "--policy-version",
                "1",
                "--budget-id",
                "budget-1",
            ],
            manager=manager,
        )

    assert result == 0
    run = manager.get_run("run-1")
    assert run.objective == "Build artifact"
    assert run.state.value == "CREATED"
    assert "run_id: run-1" in output.getvalue()


def test_run_status_reads_from_run_manager() -> None:
    manager = RunManager()

    main(
        [
            "run",
            "create",
            "run-1",
            "Build artifact",
            "--repository-id",
            "repo-1",
            "--base-revision",
            "abc123",
            "--acceptance",
            "tests pass",
            "--policy-id",
            "default",
            "--policy-version",
            "1",
            "--budget-id",
            "budget-1",
        ],
        manager=manager,
    )

    output = StringIO()
    with redirect_stdout(output):
        result = main(
            ["run", "status", "run-1"],
            manager=manager,
        )

    assert result == 0
    text = output.getvalue()
    assert "run_id: run-1" in text
    assert "state: CREATED" in text
    assert "objective: Build artifact" in text
    assert "steps: 0" in text


def test_run_events_reads_event_history() -> None:
    manager = RunManager()

    main(
        [
            "run",
            "create",
            "run-1",
            "Build artifact",
            "--repository-id",
            "repo-1",
            "--base-revision",
            "abc123",
            "--acceptance",
            "tests pass",
            "--policy-id",
            "default",
            "--policy-version",
            "1",
            "--budget-id",
            "budget-1",
        ],
        manager=manager,
    )

    output = StringIO()
    with redirect_stdout(output):
        result = main(
            ["run", "events", "run-1"],
            manager=manager,
        )

    assert result == 0
    assert "1 " in output.getvalue()
    assert "RUN_CREATED" in output.getvalue()


def test_status_missing_run_returns_clean_error() -> None:
    manager = RunManager()

    output = StringIO()

    with redirect_stdout(output):
        result = main(["run", "status", "missing"], manager=manager)

    assert result == 1


def test_events_missing_run_returns_clean_error() -> None:
    manager = RunManager()

    output = StringIO()

    with redirect_stdout(output):
        result = main(["run", "events", "missing"], manager=manager)

    assert result == 1


def test_duplicate_run_returns_clean_error() -> None:
    manager = RunManager()

    arguments = [
        "run",
        "create",
        "run-1",
        "Build artifact",
        "--repository-id",
        "repo-1",
        "--base-revision",
        "abc123",
        "--acceptance",
        "tests pass",
        "--policy-id",
        "default",
        "--policy-version",
        "1",
        "--budget-id",
        "budget-1",
    ]

    assert main(arguments, manager=manager) == 0

    result = main(arguments, manager=manager)

    assert result == 1
