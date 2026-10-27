import fcntl
import http.client
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).parents[1] / "register-claude-work.py"
spec = importlib.util.spec_from_file_location("register_claude_work", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
TOKEN = "PRIVATE_REPORTER_TOKEN"


@pytest.fixture
def world(tmp_path, monkeypatch):
    calls = []
    data = {
        "seq": 0,
        "state": "Registered",
        "registered": False,
        "events": {},
        "reject": None,
        "fail_event": None,
        "lose_reply": None,
        "lose_registration": False,
        "redirect": False,
    }

    def reply():
        return {
            "external_work_id": "ew_claude",
            "event_id": 1,
            "seq": data["seq"],
            "state": data["state"],
        }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def handle_request(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            parsed = json.loads(body) if body else None
            calls.append((self.command, self.path, parsed, dict(self.headers)))
            code, response = 200, reply()
            if data["redirect"]:
                code = 307
            elif data["reject"] == self.command:
                code, response = 403, {"error": "echo " + TOKEN}
            elif self.command == "POST" and self.path.endswith("/external-work"):
                data["registered"] = True
                if data["lose_registration"]:
                    data["lose_registration"] = False
                    code = 503  # Applied, but the client cannot know that.
            elif self.path.endswith("/events"):
                assert data["registered"]
                kind = parsed["type"]
                if data["fail_event"] == kind:
                    data["fail_event"] = None
                    code = 503
                elif parsed["seq"] in data["events"]:
                    if data["events"][parsed["seq"]] != parsed:
                        code = 409
                elif parsed["seq"] != data["seq"] + 1:
                    code = 409
                elif data["state"] in ("Submitted", "Cancelled"):
                    code = 409
                else:
                    data["seq"] = parsed["seq"]
                    data["events"][parsed["seq"]] = parsed
                    data["state"] = {
                        "started": "Running",
                        "submitted": "Submitted",
                        "cancelled": "Cancelled",
                    }.get(kind, data["state"])
                    if data["lose_reply"] == kind:
                        data["lose_reply"] = None
                        code = 503
                response = reply()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            if code == 307:
                self.send_header("Location", "/redirect-target")
            self.end_headers()
            if data.get("malformed_event") and self.path.endswith("/events"):
                response["seq"] = TOKEN
            self.wfile.write(json.dumps(response).encode())

        do_GET = handle_request
        do_PUT = handle_request
        do_POST = handle_request

    if os.environ.get("BIFROST_TEST_HTTP") == "memory":
        # Explicit sandbox test mode: serialize HTTP through the same handler
        # and urllib error/redirect chain, with no socket or listening process.
        server, thread = None, None
        port = 18780

        def memory_http_open(self, request):
            assert request.host == f"127.0.0.1:{port}"
            body = request.data or b""
            headers = {key.title(): value for key, value in request.header_items()}
            headers["Content-Length"] = str(len(body))
            wire = f"{request.get_method()} {request.selector} HTTP/1.1\r\n"
            wire += "".join(f"{key}: {value}\r\n" for key, value in headers.items())
            incoming = io.BytesIO(wire.encode() + b"\r\n" + body)
            outgoing = io.BytesIO()
            connection = SimpleNamespace(
                makefile=lambda *args: incoming,
                sendall=outgoing.write,
            )
            Handler(connection, ("127.0.0.1", 0), None)
            response = http.client.HTTPResponse(
                SimpleNamespace(
                    makefile=lambda *args: io.BytesIO(outgoing.getvalue()),
                )
            )
            response.begin()
            response.url, response.msg = request.full_url, response.reason
            return response

        monkeypatch.setattr(urllib.request.HTTPHandler, "http_open", memory_http_open)
    else:
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_port
    description = tmp_path / "desc.json"
    description.write_text(
        json.dumps(
            {
                "v": 1,
                "kind": "agentrt.external_work/v1",
                "task": "登记 Claude 工作",
                "executor": "claude",
                "provider": "anthropic",
                "repo": "bifrost-trade-infra",
                "branch": "w31/td446-claude-work",
                "acceptance_refs": ["TD-446"],
                "estimate_minutes": [20, 60],
            },
            ensure_ascii=False,
        )
    )
    report = tmp_path / "REPORT.md"
    report.write_text("PRIVATE REPORT CONTENT\nEND OF REPORT\n")
    options = SimpleNamespace(
        command="register",
        url=f"http://127.0.0.1:{port}",
        session="local_accccb4e-dispatch",
        run_key="claude-work-test",
        root="R4",
        node="R4:4.9-9",
        description=str(description),
        state_dir=str(tmp_path / "state"),
        report=str(report),
        exit_code=0,
        commit_sha=[],
    )
    monkeypatch.setenv("BIFROST_DISPATCH_TOKEN", TOKEN)

    def forbid_child(*args, **kwargs):
        pytest.fail("Claude work CLI must never launch any subprocess (including git)")

    monkeypatch.setattr(subprocess, "Popen", forbid_child)
    monkeypatch.setattr(os, "system", forbid_child)
    yield SimpleNamespace(options=options, calls=calls, data=data)
    if server:
        server.shutdown()
        server.server_close()
        thread.join()


def state(world):
    return json.loads((Path(world.options.state_dir) / "state.json").read_text())


def invoke(world, command, *extra):
    args = [command, "--state-dir", world.options.state_dir]
    if command == "register":
        for name in ("url", "session", "run_key", "root", "node", "description"):
            args += ["--" + name.replace("_", "-"), getattr(world.options, name)]
    elif command == "submit":
        args += ["--report", world.options.report]
    return mod.main(args + list(extra))


def event_attempts(world, kind):
    return [
        body
        for _, path, body, _ in world.calls
        if path.endswith("/events") and body["type"] == kind
    ]


def test_register_started_idempotent_heartbeat_submit_and_privacy(world, capsys):
    assert invoke(world, "register") == 0
    assert [method for method, _, _, _ in world.calls] == ["PUT", "POST", "GET", "POST"]
    assert world.calls[0][2] == json.loads(Path(world.options.description).read_text())
    assert world.data["state"] == "Running"
    assert invoke(world, "register") == 0
    assert len([c for c in world.calls if c[1].endswith("/external-work")]) == 1
    assert len(event_attempts(world, "started")) == 1
    assert invoke(world, "heartbeat") == 0
    assert len(event_attempts(world, "heartbeat")) == 1
    sha = "a" * 40
    assert invoke(world, "submit", "--exit-code", "7", "--commit-sha", sha) == 0
    result = event_attempts(world, "submitted")[0]
    assert result == {
        "idempotency_key": "claude-work-test:3",
        "seq": 3,
        "type": "submitted",
        "exit_code": 7,
        "commit_shas": [sha],
        "report_path_digest": mod.dispatch.digest(
            str(Path(world.options.report).resolve()).encode()
        ),
        "report_digest": mod.dispatch.digest(Path(world.options.report).read_bytes()),
    }
    assert invoke(world, "submit", "--exit-code", "7", "--commit-sha", sha) == 0
    assert len(event_attempts(world, "submitted")) == 1
    assert invoke(world, "register") == 0
    assert world.data["state"] == "Submitted"
    assert not state(world).get("pending")
    assert all(
        h["X-Bifrost-Session"] == world.options.session for _, _, _, h in world.calls
    )
    assert all(h["Authorization"] == "Bearer " + TOKEN for _, _, _, h in world.calls)
    payload = json.dumps(
        [(method, path, body) for method, path, body, _ in world.calls]
    )
    output = capsys.readouterr()
    for secret in (TOKEN, "PRIVATE REPORT CONTENT", world.options.report):
        assert secret not in payload
        assert secret not in output.out + output.err
    for path in Path(world.options.state_dir).iterdir():
        assert TOKEN not in path.read_text()
    assert (
        Path(world.options.state_dir) / "state.json"
    ).stat().st_mode & 0o777 == 0o600
    assert Path(world.options.state_dir).stat().st_mode & 0o777 == 0o700
    assert TOKEN not in " ".join(sys.argv)


@pytest.mark.parametrize(
    "kind,command",
    [
        ("started", "register"),
        ("heartbeat", "heartbeat"),
        ("submitted", "submit"),
        ("cancelled", "abandon"),
    ],
)
@pytest.mark.parametrize("failure", ["fail_event", "lose_reply"])
def test_pending_replay_uses_identical_payload_even_if_server_applied_it(
    world, kind, command, failure
):
    if kind != "started":
        assert invoke(world, "register") == 0
    world.data[failure] = kind
    assert invoke(world, command) == 1
    pending = state(world)["pending"]
    assert pending["type"] == kind
    assert invoke(world, command) == 0
    assert event_attempts(world, kind) == [pending, pending]
    assert "pending" not in state(world)


def test_lost_registration_reply_retries_same_identity(world):
    world.data["lose_registration"] = True
    assert invoke(world, "register") == 1
    assert "id" not in state(world)
    assert not world.data["events"]
    assert invoke(world, "heartbeat") == 1
    assert invoke(world, "register") == 0
    attempts = [
        body for _, path, body, _ in world.calls if path.endswith("/external-work")
    ]
    assert attempts[0] == attempts[1]
    assert len(event_attempts(world, "started")) == 1


@pytest.mark.parametrize("method", ["PUT", "POST", "GET"])
def test_rejection_fails_closed_and_never_echoes_response(world, method, capsys):
    world.data["reject"] = method
    assert invoke(world, "register") == 1
    assert not world.data["events"]
    output = capsys.readouterr()
    assert "platform refused " + method + " with HTTP 403" in output.err
    assert TOKEN not in output.out + output.err
    world.data["reject"] = None
    assert invoke(world, "register") == 0


def test_redirect_refused_without_forwarding_authorization(world, capsys):
    world.data["redirect"] = True
    assert invoke(world, "register") == 1
    assert len(world.calls) == 1
    assert "HTTP 307" in capsys.readouterr().err
    assert not world.data["registered"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("session", "local_another"),
        ("run_key", "another"),
        ("node", "R4:other"),
        ("root", "R5"),
        ("url", "http://127.0.0.1:1"),
    ],
)
def test_state_dir_cannot_be_reused_for_different_work(world, field, value, capsys):
    assert invoke(world, "register") == 0
    before = len(world.calls)
    setattr(world.options, field, value)
    assert invoke(world, "register") == 1
    assert len(world.calls) == before
    assert "different content" in capsys.readouterr().err


def test_changed_description_and_submission_refused_before_network(world):
    assert invoke(world, "register") == 0
    desc = Path(world.options.description)
    desc.write_text(desc.read_text() + "\n")
    before = len(world.calls)
    assert invoke(world, "register") == 1
    assert len(world.calls) == before
    world.data["fail_event"] = "submitted"
    assert invoke(world, "submit") == 1
    pending = state(world)["pending"]
    Path(world.options.report).write_text("changed report")
    before = len(world.calls)
    assert invoke(world, "submit") == 1
    assert len(world.calls) == before
    assert state(world)["pending"] == pending


def test_abandon_is_explicit_idempotent_and_does_not_submit(world):
    assert invoke(world, "register") == 0
    assert invoke(world, "abandon") == 0
    assert invoke(world, "abandon") == 0
    assert world.data["state"] == "Cancelled"
    assert len(event_attempts(world, "cancelled")) == 1
    assert not event_attempts(world, "submitted")
    assert invoke(world, "heartbeat") == 1
    assert invoke(world, "submit") == 1


def test_lock_prevents_parallel_commands(world):
    assert invoke(world, "register") == 0
    before = len(world.calls)
    with (Path(world.options.state_dir) / "wrapper.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert invoke(world, "heartbeat") == 1
    assert len(world.calls) == before


def test_token_only_from_env_and_no_credential_argument_echo(
    world, monkeypatch, capsys
):
    monkeypatch.delenv("BIFROST_DISPATCH_TOKEN")
    assert invoke(world, "register") == 1
    assert not Path(world.options.state_dir).exists()
    with pytest.raises(SystemExit) as err:
        invoke(world, "register", "--token", TOKEN)
    assert err.value.code == 2
    assert not world.calls
    output = capsys.readouterr()
    assert "BIFROST_DISPATCH_TOKEN is required" in output.err
    assert TOKEN not in output.out + output.err


@pytest.mark.parametrize(
    "field,value",
    [("executor", "codex"), ("provider", "openai"), ("token", TOKEN), ("task", TOKEN)],
)
def test_invalid_or_credential_bearing_description_never_uploaded(
    world, field, value, capsys
):
    description = Path(world.options.description)
    body = json.loads(description.read_text())
    body[field] = value
    description.write_text(json.dumps(body))
    assert invoke(world, "register") == 1
    assert not world.calls
    assert not Path(world.options.state_dir).exists()
    output = capsys.readouterr()
    assert TOKEN not in output.out + output.err


def test_unknown_state_and_missing_report_fail_without_network(world):
    assert invoke(world, "heartbeat") == 1
    assert not world.calls
    assert invoke(world, "register") == 0
    Path(world.options.report).unlink()
    before = len(world.calls)
    assert invoke(world, "submit") == 1
    assert len(world.calls) == before


def test_invalid_commit_refused_before_network(world):
    assert invoke(world, "register") == 0
    before = len(world.calls)
    assert invoke(world, "submit", "--commit-sha", "abc123") == 1
    assert len(world.calls) == before


def test_invalid_event_reply_preserves_pending_and_never_persists_echoed_token(
    world, capsys
):
    world.data["malformed_event"] = True
    assert invoke(world, "register") == 1
    pending = state(world)["pending"]
    assert TOKEN not in json.dumps(state(world))
    output = capsys.readouterr()
    assert "invalid external-work response" in output.err
    assert TOKEN not in output.out + output.err
    world.data["malformed_event"] = False
    assert invoke(world, "register") == 0
    assert event_attempts(world, "started") == [pending, pending]
