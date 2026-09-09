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


def make_cli_run(manager: RunManager, run_id: str = "run-1") -> None:
    main(
        [
            "run",
            "create",
            run_id,
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


def test_run_transition_controls_lifecycle() -> None:
    manager = RunManager()
    make_cli_run(manager)

    result = main(
        ["run", "transition", "run-1", "QUEUED"],
        manager=manager,
    )

    assert result == 0
    assert manager.get_run("run-1").state.value == "QUEUED"


def test_run_transition_rejects_invalid_lifecycle_transition() -> None:
    manager = RunManager()
    make_cli_run(manager)

    result = main(
        ["run", "transition", "run-1", "EXECUTING"],
        manager=manager,
    )

    assert result == 1
    assert manager.get_run("run-1").state.value == "CREATED"


def test_run_snapshot_reads_canonical_run() -> None:
    manager = RunManager()
    make_cli_run(manager)

    output = StringIO()
    with redirect_stdout(output):
        result = main(
            ["run", "snapshot", "run-1"],
            manager=manager,
        )

    assert result == 0
    text = output.getvalue()
    assert "run_id: run-1" in text
    assert "state: CREATED" in text
    assert "objective: Build artifact" in text


def test_run_abort_controls_recovering_run() -> None:
    manager = RunManager()
    make_cli_run(manager)

    manager.transition("run-1", __import__("vajra.domain", fromlist=["RunState"]).RunState.QUEUED)
    manager.transition("run-1", __import__("vajra.domain", fromlist=["RunState"]).RunState.ORIENTING)
    manager.transition("run-1", __import__("vajra.domain", fromlist=["RunState"]).RunState.RECOVERING)

    result = main(
        ["run", "abort", "run-1", "operator requested abort"],
        manager=manager,
    )

    assert result == 0
    run = manager.get_run("run-1")
    assert run.state.value == "ABORTED"


def test_run_abort_rejects_non_recovering_run() -> None:
    manager = RunManager()
    make_cli_run(manager)

    result = main(
        ["run", "abort", "run-1", "operator requested abort"],
        manager=manager,
    )

    assert result == 1
    assert manager.get_run("run-1").state.value == "CREATED"


def test_status_exposes_waiting_human_state() -> None:
    manager = RunManager()
    make_cli_run(manager)

    from vajra.domain import RunState

    manager.transition("run-1", RunState.QUEUED)
    manager.transition("run-1", RunState.ORIENTING)
    manager.transition("run-1", RunState.WAITING_HUMAN)

    output = StringIO()
    with redirect_stdout(output):
        result = main(
            ["run", "status", "run-1"],
            manager=manager,
        )

    assert result == 0
    text = output.getvalue()
    assert "state: WAITING_HUMAN" in text
    assert "final_disposition: -" in text


def test_human_waiting_run_can_be_aborted_explicitly() -> None:
    manager = RunManager()
    make_cli_run(manager)

    from vajra.domain import RunState

    manager.transition("run-1", RunState.QUEUED)
    manager.transition("run-1", RunState.ORIENTING)
    manager.transition("run-1", RunState.WAITING_HUMAN)

    result = main(
        ["run", "abort", "run-1", "human denied continuation"],
        manager=manager,
    )

    assert result == 0

    run = manager.get_run("run-1")
    assert run.state is RunState.ABORTED


def test_waiting_human_does_not_auto_approve() -> None:
    manager = RunManager()
    make_cli_run(manager)

    from vajra.domain import RunState

    manager.transition("run-1", RunState.QUEUED)
    manager.transition("run-1", RunState.ORIENTING)
    manager.transition("run-1", RunState.WAITING_HUMAN)

    output = StringIO()
    with redirect_stdout(output):
        result = main(
            ["run", "status", "run-1"],
            manager=manager,
        )

    assert result == 0
    assert manager.get_run("run-1").state is RunState.WAITING_HUMAN
    assert "state: WAITING_HUMAN" in output.getvalue()
