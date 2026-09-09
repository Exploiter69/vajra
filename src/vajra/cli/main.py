from __future__ import annotations

import argparse
from datetime import datetime, timezone

from vajra.domain import EngineeringRun, RunState
from vajra.runtime import RunManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vajra",
        description="VAJRA durable autonomous engineering runtime",
    )

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser(
        "run",
        help="inspect and control Engineering Runs",
    )
    run_subparsers = run_parser.add_subparsers(dest="run_command")

    run_subparsers.add_parser("list", help="list Engineering Runs")

    create_parser = run_subparsers.add_parser(
        "create",
        help="create an Engineering Run",
    )
    create_parser.add_argument("run_id")
    create_parser.add_argument("objective")
    create_parser.add_argument("--repository-id", required=True)
    create_parser.add_argument("--base-revision", required=True)
    create_parser.add_argument(
        "--acceptance",
        action="append",
        required=True,
        dest="acceptance_criteria",
    )
    create_parser.add_argument("--policy-id", required=True)
    create_parser.add_argument("--policy-version", required=True)
    create_parser.add_argument("--budget-id", required=True)
    create_parser.add_argument("--created-by", default="human")

    status_parser = run_subparsers.add_parser(
        "status",
        help="show an Engineering Run",
    )
    status_parser.add_argument("run_id")

    events_parser = run_subparsers.add_parser(
        "events",
        help="show Engineering Run event history",
    )
    events_parser.add_argument("run_id")

    transition_parser = run_subparsers.add_parser(
        "transition",
        help="transition an Engineering Run",
    )
    transition_parser.add_argument("run_id")
    transition_parser.add_argument(
        "state",
        choices=[state.value for state in RunState],
    )

    abort_parser = run_subparsers.add_parser(
        "abort",
        help="abort an Engineering Run",
    )
    abort_parser.add_argument("run_id")
    abort_parser.add_argument("reason")

    snapshot_parser = run_subparsers.add_parser(
        "snapshot",
        help="show an Engineering Run snapshot",
    )
    snapshot_parser.add_argument("run_id")

    return parser


def _create_run(manager: RunManager, args: argparse.Namespace) -> int:
    run = EngineeringRun(
        run_id=args.run_id,
        objective=args.objective,
        repository_id=args.repository_id,
        base_revision=args.base_revision,
        acceptance_criteria=tuple(args.acceptance_criteria),
        policy_id=args.policy_id,
        policy_version=args.policy_version,
        budget_id=args.budget_id,
        created_by=args.created_by,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    created = manager.create_run(run)

    print(f"run_id: {created.run_id}")
    print(f"state: {created.state.value}")
    return 0


def _status(manager: RunManager, args: argparse.Namespace) -> int:
    run = manager.get_run(args.run_id)

    print(f"run_id: {run.run_id}")
    print(f"state: {run.state.value}")
    print(f"objective: {run.objective}")
    print(f"repository_id: {run.repository_id}")
    print(f"base_revision: {run.base_revision}")
    print(f"policy: {run.policy_id}@{run.policy_version}")
    print(f"budget_id: {run.budget_id}")
    print(f"created_by: {run.created_by}")
    print(f"current_step_id: {run.current_step_id or '-'}")
    print(f"steps: {len(run.steps)}")

    attempts = sum(len(step.attempts) for step in run.steps)
    print(f"attempts: {attempts}")

    return 0


def _events(manager: RunManager, args: argparse.Namespace) -> int:
    manager.get_run(args.run_id)
    events = manager.events(args.run_id)

    for event in events:
        timestamp = event.timestamp.isoformat()
        print(
            f"{event.sequence} "
            f"{timestamp} "
            f"{event.event_type}"
        )

    return 0


def _transition(manager: RunManager, args: argparse.Namespace) -> int:
    target = RunState(args.state)
    run = manager.transition(args.run_id, target)

    print(f"run_id: {run.run_id}")
    print(f"state: {run.state.value}")
    return 0


def _abort(manager: RunManager, args: argparse.Namespace) -> int:
    run = manager.abort_run(args.run_id, args.reason)

    print(f"run_id: {run.run_id}")
    print(f"state: {run.state.value}")
    print(f"final_disposition: {run.final_disposition.value}")
    return 0


def _snapshot(manager: RunManager, args: argparse.Namespace) -> int:
    snapshot = manager.snapshot(args.run_id)
    run = snapshot.run

    print(f"run_id: {run.run_id}")
    print(f"state: {run.state.value}")
    print(f"objective: {run.objective}")
    print(f"steps: {len(run.steps)}")
    print(f"attempts: {sum(len(step.attempts) for step in run.steps)}")

    return 0


def main(
    argv: list[str] | None = None,
    *,
    manager: RunManager | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    manager = manager or RunManager()

    try:
        if args.command == "run":
            if args.run_command == "create":
                return _create_run(manager, args)

            if args.run_command == "status":
                return _status(manager, args)

            if args.run_command == "events":
                return _events(manager, args)

            if args.run_command == "transition":
                return _transition(manager, args)

            if args.run_command == "abort":
                return _abort(manager, args)

            if args.run_command == "snapshot":
                return _snapshot(manager, args)

        return 0
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
