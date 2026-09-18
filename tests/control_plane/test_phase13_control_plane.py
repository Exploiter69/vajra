from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from vajra.control_plane import ControlPlane, ControlPlaneHTTPServer, ControlPlaneStore, ControlCommand, ScheduleSpec
from vajra.domain import EngineeringRun, RunState
from vajra.runtime import RunManager


def make_run(run_id: str = "run-1") -> EngineeringRun:
    now = datetime.now(timezone.utc)
    return EngineeringRun(
        run_id=run_id,
        objective="phase13 test",
        repository_id="repo",
        base_revision="HEAD",
        acceptance_criteria=("tests pass",),
        policy_id="policy",
        policy_version="1",
        budget_id="budget",
        created_by="test",
        created_at=now,
        updated_at=now,
    )


def make_plane(tmp_path: Path, executor=None):
    manager = RunManager()
    store = ControlPlaneStore(tmp_path / "control.jsonl")
    plane = ControlPlane(manager, store, run_executor=executor, poll_interval_seconds=0.01)
    return manager, store, plane


def test_queue_survives_restart_and_reclaims_dispatching(tmp_path: Path):
    store = ControlPlaneStore(tmp_path / "control.jsonl")
    store.enqueue("q1", "run-1")
    store.claim("q1")

    restarted = ControlPlaneStore(tmp_path / "control.jsonl")
    restarted.recover_dispatching()
    recovered = restarted.ready()

    assert len(recovered) == 1
    assert recovered[0].entry_id == "q1"
    assert recovered[0].state == "QUEUED"


def test_submit_and_fifo_dispatch(tmp_path: Path):
    seen: list[str] = []
    manager, store, plane = make_plane(tmp_path, seen.append)
    manager.create_run(make_run())

    entry = plane.submit("run-1")
    assert manager.get_run("run-1").state is RunState.QUEUED
    assert entry in {e.entry_id for e in plane.queue()}

    assert plane.run_once() == 1
    assert seen == ["run-1"]
    assert plane.queue() == ()
    assert json.loads((tmp_path / "control.jsonl").read_text().splitlines()[-1])["state"] == "DISPATCHED"


def test_dispatch_failure_requeues(tmp_path: Path):
    def fail(_: str) -> None:
        raise RuntimeError("worker unavailable")

    manager, _, plane = make_plane(tmp_path, fail)
    manager.create_run(make_run())
    plane.submit("run-1")

    with pytest.raises(RuntimeError, match="worker unavailable"):
        plane.run_once()

    assert [e.run_id for e in plane.queue()] == ["run-1"]


@pytest.mark.parametrize(
    ("command", "initial", "expected"),
    [
        (ControlCommand.PAUSE, RunState.QUEUED, RunState.PAUSED),
        (ControlCommand.CANCEL, RunState.QUEUED, RunState.PAUSED),
        (ControlCommand.ABORT, RunState.QUEUED, RunState.ABORTED),
    ],
)
def test_human_queue_controls(tmp_path: Path, command, initial, expected):
    manager, _, plane = make_plane(tmp_path)
    manager.create_run(make_run())
    plane.submit("run-1")
    assert manager.get_run("run-1").state is initial

    result = plane.control("run-1", command)
    assert result.accepted
    assert manager.get_run("run-1").state is expected


def test_pause_and_resume_active_run(tmp_path: Path):
    manager, _, plane = make_plane(tmp_path)
    manager.create_run(make_run())
    manager.transition("run-1", RunState.QUEUED, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    manager.transition("run-1", RunState.ORIENTING, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)

    assert plane.control("run-1", ControlCommand.PAUSE).accepted
    assert manager.get_run("run-1").state is RunState.PAUSED

    assert plane.control("run-1", ControlCommand.RESUME).accepted
    assert manager.get_run("run-1").state is RunState.QUEUED
    assert len(plane.queue()) == 1


def test_retry_failed_run(tmp_path: Path):
    manager, _, plane = make_plane(tmp_path)
    manager.create_run(make_run())
    manager.transition("run-1", RunState.QUEUED, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    manager.transition("run-1", RunState.ORIENTING, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    manager.transition("run-1", RunState.PLANNING, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    manager.transition("run-1", RunState.EXECUTING, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    manager.transition("run-1", RunState.FAILED, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)

    result = plane.control("run-1", ControlCommand.RETRY)
    assert result.accepted
    assert manager.get_run("run-1").state is RunState.QUEUED
    assert len(plane.queue()) == 1


def test_approval_and_rejection_are_human_authority(tmp_path: Path):
    manager, _, plane = make_plane(tmp_path)
    manager.create_run(make_run())
    manager.transition("run-1", RunState.QUEUED, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    manager.transition("run-1", RunState.ORIENTING, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    manager.transition("run-1", RunState.WAITING_HUMAN, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)

    approved = plane.control("run-1", ControlCommand.APPROVE)
    assert approved.accepted
    assert manager.get_run("run-1").state is RunState.QUEUED
    assert len(plane.queue()) == 1

    manager2, _, plane2 = make_plane(tmp_path / "reject")
    manager2.create_run(make_run("run-2"))
    manager2.transition("run-2", RunState.QUEUED, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    manager2.transition("run-2", RunState.ORIENTING, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    manager2.transition("run-2", RunState.WAITING_HUMAN, __import__("vajra.control", fromlist=["TransitionActor"]).TransitionActor.HUMAN)
    rejected = plane2.control("run-2", ControlCommand.REJECT)
    assert rejected.accepted
    assert manager2.get_run("run-2").state is RunState.ABORTED


def test_one_shot_and_periodic_schedules_are_durable(tmp_path: Path):
    created: list[str] = []
    manager, store, plane = make_plane(tmp_path, lambda run_id: created.append(run_id))
    manager.create_run(make_run())

    due = datetime.now(timezone.utc) - timedelta(seconds=1)
    plane.register_job_handler("existing", lambda payload: payload["run_id"])
    plane.schedule(ScheduleSpec("once", due.isoformat(), "existing", {"run_id": "run-1"}))
    assert plane.run_once(due + timedelta(seconds=1)) == 2
    assert created == ["run-1"]
    assert not store.schedules()[0].enabled

    counter = {"n": 0}
    plane.register_job_handler("new-run", lambda _: (counter.__setitem__("n", counter["n"] + 1) or "run-1"))
    plane.schedule(ScheduleSpec("periodic", due.isoformat(), "new-run", {}, interval_seconds=60))
    plane.run_once(due + timedelta(seconds=1))
    periodic = next(s for s in store.schedules() if s.schedule_id == "periodic")
    assert periodic.enabled
    assert datetime.fromisoformat(periodic.due_at) > due + timedelta(seconds=1)


def test_daemon_starts_and_stops(tmp_path: Path):
    manager, _, plane = make_plane(tmp_path, lambda _: None)
    manager.create_run(make_run())
    plane.submit("run-1")
    plane.start()
    deadline = time.monotonic() + 1
    while plane.queue() and time.monotonic() < deadline:
        time.sleep(0.01)
    plane.stop()
    assert not plane.running
    assert plane.queue() == ()


def test_localhost_api_is_control_surface_only(tmp_path: Path):
    manager, _, plane = make_plane(tmp_path)
    manager.create_run(make_run())
    server = ControlPlaneHTTPServer(plane, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://{server.host}:{server.port}/health", timeout=2) as response:
            health = json.loads(response.read())
        assert health["ok"] is True

        request = Request(
            f"http://{server.host}:{server.port}/runs/run-1/submit",
            data=json.dumps({}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            assert response.status == 202
        assert manager.get_run("run-1").state is RunState.QUEUED

        with urlopen(f"http://{server.host}:{server.port}/runs/run-1/pause", timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["accepted"] is True
        assert manager.get_run("run-1").state is RunState.PAUSED
    finally:
        server.shutdown()
        thread.join(timeout=2)
