"""Shared by the S1-5 collector tests: a local fake platform and a fake claude. Not a test file.

Nothing here reaches a real platform or runs a real CLI. Environments for the
scripts under test are built from nothing, so the session these tests run in
(its CLAUDE_PID, sidebar id, tokens) never reaches them.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT_HOST = HERE.parent
INFRA = AGENT_HOST.parents[1]
HEARTBEAT = INFRA / "agent-config" / "scripts" / "thread-heartbeat.js"
AUDIT = INFRA / "agent-config" / "scripts" / "collector-audit.js"
COLLECTOR = "COLLECTOR_TEST_TOKEN"


class Platform:
    """platform-api's heartbeat route and the external-work routes, one work per registration key."""

    def __init__(self):
        self.calls = []
        self.works = {}
        self.refuse_registration = 0
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle(self_):
                try:
                    super().handle()
                except ConnectionError:
                    pass

            def serve(self_):
                raw = self_.rfile.read(int(self_.headers.get("Content-Length", "0")))
                with outer.lock:
                    code, reply = outer.answer(self_.command, self_.path, raw, dict(self_.headers))
                body = json.dumps(reply).encode()
                self_.send_response(code)
                self_.send_header("Content-Type", "application/json")
                self_.send_header("Content-Length", str(len(body)))
                self_.end_headers()
                self_.wfile.write(body)

            do_GET = do_PUT = do_POST = serve

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def answer(self, method, path, raw, headers):
        body = json.loads(raw) if raw and path != "" and not path.startswith("/api/v1/agentrt/artifacts/") else None
        kept = {k: headers.get(k, "") for k in ("Authorization", "X-Bifrost-Session", "Content-Type", "X-Artifact-Kind")}
        self.calls.append({"method": method, "path": path, "raw": raw, "body": body, "auth": headers.get("Authorization", ""), "headers": kept})
        if path == "/api/v1/agent/threads/heartbeat":
            return 202, {"ok": True, "thread_key": "ab" * 32}
        if path.startswith("/api/v1/agentrt/artifacts/"):
            return 200, {"artifact_id": path.rsplit("/", 1)[-1]}
        if method == "POST" and path == "/api/v1/agentrt/external-work":
            if self.refuse_registration:
                self.refuse_registration -= 1
                return 400, {"error": "node rejected"}
            key = body["idempotency_key"]
            work = self.works.setdefault(key, {"id": "ew_" + str(len(self.works) + 1), "seq": 0, "state": "Registered", "events": {}, "registration": body})
            return 200, self.reply(work)
        for work in self.works.values():
            route = "/api/v1/agentrt/external-work/" + work["id"]
            if path == route and method == "GET":
                return 200, self.reply(work)
            if path == route + "/events" and method == "POST":
                seq = body["seq"]
                if seq in work["events"]:
                    return (200, self.reply(work)) if work["events"][seq] == body else (409, {"error": "conflict"})
                if seq != work["seq"] + 1 or work["state"] in ("Submitted", "Cancelled"):
                    return 409, {"error": "conflict"}
                work["seq"], work["events"][seq] = seq, body
                work["state"] = {"started": "Running", "submitted": "Submitted", "cancelled": "Cancelled"}.get(body["type"], work["state"])
                return 200, self.reply(work)
        return 404, {"error": "not found"}

    @staticmethod
    def reply(work):
        return {"external_work_id": work["id"], "event_id": work["seq"], "seq": work["seq"], "state": work["state"], "registered_at": "2026-11-04T00:00:00.000Z"}

    def beats(self):
        return [c["body"] for c in self.calls if c["path"] == "/api/v1/agent/threads/heartbeat"]

    def events(self):
        return [c["body"] for c in self.calls if c["path"].endswith("/events")]

    def wait(self, predicate, seconds=15.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            with self.lock:
                if predicate(self):
                    return True
            time.sleep(0.05)
        return predicate(self)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def clean_env(home: Path, url: str, **extra) -> dict:
    env = {"PATH": os.environ["PATH"], "BIFROST_HOME_OVERRIDE": str(home), "HOME": str(home), "PLATFORM_HEARTBEAT_URL": url}
    for key, value in extra.items():
        if value is not None:
            env[key] = str(value)
    return env


def collector_env(home: Path, url: str, **extra) -> dict:
    return clean_env(home, url, PLATFORM_COLLECTOR_TOKEN=COLLECTOR, BIFROST_HOST_ID="h1", **extra)


FAKE_CLAUDE = r'''#!{python}
"""A fake claude: it runs the wired hooks as the CLI would, with CLAUDE_PID its own pid."""
import json, os, subprocess, sys, time
plan = json.loads(os.environ["FAKE_CLAUDE_PLAN"])
record = {{"pid": os.getpid(), "argv": sys.argv[1:], "env": {{k: os.environ.get(k, "") for k in ("BIFROST_LAUNCH_ID", "BIFROST_PLAN_ROOT", "BIFROST_PLAN_NODE", "BIFROST_WORK_DESCRIPTION", "CLAUDE_CODE_HOST_SESSION_ID")}}}}
open(os.environ["FAKE_CLAUDE_RECORD"], "w").write(json.dumps(record))
for step in plan:
    env = dict(os.environ, CLAUDE_PID=str(step.get("pid") or os.getpid()))
    payload = {{"session_id": step["session"], "hook_event_name": step["event"], **step.get("extra", {{}})}}
    subprocess.run(["node", {heartbeat!r}, "hook", "claude"], input=json.dumps(payload), text=True, env=env, timeout=10)
    time.sleep(step.get("sleep", 0.4))
'''


def fake_claude(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / "claude"
    path.write_text(FAKE_CLAUDE.format(python=sys.executable, heartbeat=str(HEARTBEAT)))
    path.chmod(0o755)
    return path
