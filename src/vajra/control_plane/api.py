from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from .contracts import ControlCommand, ScheduleSpec


class ControlPlaneHTTPServer:
    """Localhost-by-default JSON control surface.

    The API delegates every Run mutation to ControlPlane/RunManager. It never
    stores canonical Run state and is therefore replaceable by Telegram or
    another UI without architectural changes.
    """

    def __init__(self, plane, *, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.plane = plane
        self.server = ThreadingHTTPServer((host, port), self._handler())
        self.host, self.port = self.server.server_address

    def _handler(self):
        plane = self.plane

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status: int, payload: object) -> None:
                data = json.dumps(payload, sort_keys=True).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                path = urlparse(self.path).path
                if path == "/health":
                    self._send(200, {"ok": True, "running": plane.running})
                    return
                if path == "/queue":
                    self._send(200, [e.__dict__ for e in plane.queue()])
                    return
                if path == "/schedules":
                    self._send(200, [e.__dict__ for e in plane.schedules()])
                    return
                if path.startswith("/runs/"):
                    run_id = unquote(path[len("/runs/"):])
                    try:
                        run = plane._manager.get_run(run_id)
                    except KeyError:
                        self._send(404, {"error": "run not found"})
                        return
                    self._send(200, {"run_id": run.run_id, "state": run.state.value, "objective": run.objective})
                    return
                self._send(404, {"error": "not found"})

            def do_POST(self) -> None:
                path = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
                try:
                    if len(path) == 2 and path[0] == "runs" and path[1] == "submit":
                        self._send(202, {"entry_id": plane.submit(self._body()["run_id"])})
                        return
                    if len(path) == 3 and path[0] == "runs" and path[2] in {c.value for c in ControlCommand}:
                        result = plane.control(path[1], ControlCommand(path[2]))
                        self._send(200 if result.accepted else 409, result.__dict__)
                        return
                    if path == ["schedules"]:
                        self._send(201, plane.schedule(ScheduleSpec(**self._body())).__dict__)
                        return
                except (ValueError, KeyError, RuntimeError) as exc:
                    self._send(400, {"error": str(exc)})
                    return
                self._send(404, {"error": "not found"})

            def do_DELETE(self) -> None:
                path = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
                if len(path) == 2 and path[0] == "schedules":
                    try:
                        plane.cancel_schedule(path[1])
                        self._send(204, {})
                    except KeyError as exc:
                        self._send(404, {"error": str(exc)})
                    return
                self._send(404, {"error": "not found"})

            def _body(self) -> dict:
                length = int(self.headers.get("Content-Length", "0"))
                return json.loads(self.rfile.read(length) or b"{}")

            def log_message(self, format, *args) -> None:
                return

        return Handler

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
