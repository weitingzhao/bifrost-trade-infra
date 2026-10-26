import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "dispatch-codex.py"
spec = importlib.util.spec_from_file_location("dispatch_codex", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


@pytest.fixture
def world(tmp_path, monkeypatch):
    calls = []
    data = {
        "seq": 0,
        "state": "Registered",
        "reject_register": False,
        "fail_submit": 0,
        "events": {},
        "registrations": 0,
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            parsed = json.loads(body) if body else None
            calls.append((self.command, self.path, parsed, dict(self.headers)))
            code = 200
            reply = {
                "external_work_id": "ew_test",
                "event_id": 1,
                "seq": data["seq"],
                "state": data["state"],
            }
            if self.command == "POST" and self.path.endswith("/external-work"):
                data["registrations"] += 1
                if data["reject_register"]:
                    code = 503
            elif self.path.endswith("/events"):
                if parsed["type"] == "submitted" and data["fail_submit"]:
                    data["fail_submit"] -= 1
                    code = 503
                elif parsed["seq"] in data["events"]:
                    if data["events"][parsed["seq"]] != parsed:
                        code = 409
                elif parsed["seq"] != data["seq"] + 1:
                    code = 409
                else:
                    data["seq"] = parsed["seq"]
                    data["events"][parsed["seq"]] = parsed
                    data["state"] = {
                        "started": "Running",
                        "submitted": "Submitted",
                        "cancelled": "Cancelled",
                    }.get(parsed["type"], data["state"])
                reply.update(seq=data["seq"], state=data["state"])
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(reply).encode())

        do_GET = handle_request
        do_PUT = handle_request
        do_POST = handle_request

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    description = tmp_path / "description.json"
    description.write_text(
        json.dumps(
            {
                "v": 1,
                "kind": "agentrt.external_work/v1",
                "task": "实现摘要",
                "executor": "codex",
                "provider": "openai",
                "repo": "platform",
                "branch": "test",
                "acceptance_refs": ["PV1"],
                "estimate_minutes": [1, 2],
            }
        )
    )
    marker = tmp_path / "launches"
    report = tmp_path / "REPORT.md"
    binary = tmp_path / "codex"
    binary.write_text(
        "#!"
        + sys.executable
        + "\nimport os, time\n"
        + f'with open({str(marker)!r}, "a") as f: f.write("launch\\n")\n'
        + 'assert "BIFROST_DISPATCH_TOKEN" not in os.environ\n'
        + 'time.sleep(float(os.environ.get("FAKE_DURATION", ".15")))\n'
        + f'open({str(report)!r}, "w").write("PRIVATE REPORT CONTENT")\n'
    )
    binary.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("BIFROST_DISPATCH_TOKEN", "PRIVATE_TOKEN")
    monkeypatch.setenv("PRIVATE_ENV", "PRIVATE_ENV_VALUE")
    options = SimpleNamespace(
        url=f"http://127.0.0.1:{server.server_port}",
        session="test",
        run_key="run-594",
        root="R4",
        node="R4:4.5-1",
        description=str(description),
        report=str(report),
        state_dir=str(tmp_path / "state"),
        repo=str(tmp_path),
    )
    yield options, calls, data, marker
    server.shutdown()
    server.server_close()
    thread.join()


def test_register_before_start_heartbeat_submit_and_privacy(world):
    options, calls, data, marker = world
    assert mod.dispatch(options, ["PRIVATE_COMMAND"], interval=0.03, poll=0.01) == 0
    assert marker.read_text().splitlines() == ["launch"]
    events = list(data["events"].values())
    assert events[0]["type"] == "started"
    assert any(e["type"] == "heartbeat" for e in events)
    assert events[-1]["type"] == "submitted"
    assert events[-1]["report_digest"].startswith("sha256:")
    assert events[-1]["report_path_digest"].startswith("sha256:")
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    payload = json.dumps([(method, path, body) for method, path, body, _ in calls])
    for secret in [
        "PRIVATE_COMMAND",
        "PRIVATE_ENV_VALUE",
        "PRIVATE_TOKEN",
        "PRIVATE REPORT CONTENT",
        options.report,
    ]:
        assert secret not in payload
    assert all(headers["X-Bifrost-Session"] == "test" for _, _, _, headers in calls)
    assert mod.dispatch(options, ["PRIVATE_COMMAND"], interval=0.03, poll=0.01) == 0
    assert marker.read_text().splitlines() == ["launch"]


def test_registration_failure_never_starts(world):
    options, _, data, marker = world
    data["reject_register"] = True
    with pytest.raises(RuntimeError, match="503"):
        mod.dispatch(options, [])
    assert not marker.exists()
    assert not data["events"]


def test_submit_failure_replays_same_durable_event(world):
    options, calls, data, marker = world
    data["fail_submit"] = 1
    with pytest.raises(RuntimeError, match="503"):
        mod.dispatch(options, [], interval=0.03, poll=0.01)
    assert mod.dispatch(options, [], interval=0.03, poll=0.01) == 0
    submitted = [
        body
        for _, path, body, _ in calls
        if path.endswith("/events") and body["type"] == "submitted"
    ]
    assert submitted[0] == submitted[1]
    assert marker.read_text().splitlines() == ["launch"]


def test_crash_resume_same_child(world, monkeypatch):
    options, _, data, marker = world
    monkeypatch.setenv("FAKE_DURATION", "1")
    command = [sys.executable, str(SCRIPT)]
    for name, value in vars(options).items():
        command.extend(["--" + name.replace("_", "-"), value])
    command.extend(["--", "PRIVATE_COMMAND"])
    first = subprocess.Popen(command)
    try:
        until = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < until:
            time.sleep(0.01)
        assert marker.exists()
        first.kill()
        first.wait(timeout=2)
        assert mod.dispatch(options, ["PRIVATE_COMMAND"], interval=0.03, poll=0.01) == 0
        assert marker.read_text().splitlines() == ["launch"]
        assert data["state"] == "Submitted"
    finally:
        if first.poll() is None:
            first.kill()
        first.wait(timeout=2)


def test_changed_registration_refused_locally(world):
    options, _, _, marker = world
    assert mod.dispatch(options, [], interval=0.03, poll=0.01) == 0
    options.node = "another-step"
    with pytest.raises(ValueError, match="different content"):
        mod.dispatch(options, [])
    assert marker.read_text().splitlines() == ["launch"]
