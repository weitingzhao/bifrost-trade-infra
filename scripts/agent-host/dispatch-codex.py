#!/usr/bin/env python3
"""Register, observe and submit a codex exec run; never assert completion.

Run with --run-key, --session, --root, --node, --description JSON,
--report PATH, --state-dir DIR, --url URL, then -- CODEX_EXEC_ARGUMENTS.
Authentication is read from BIFROST_DISPATCH_TOKEN (never persisted or sent
as payload). Re-run the same invocation after a crash to observe the same
child and replay a durable pending event. A lost child is never relaunched
implicitly: its run remains Unconfirmed until explicitly reconciled.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def atomic(path: Path, value: dict) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        os.chmod(tmp, 0o600)
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Client:
    def __init__(self, url: str, session: str, token: str):
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "url must be an HTTP(S) origin without credentials or query"
            )
        self.base = url.rstrip("/") + "/api/v1/agentrt"
        self.headers = {
            "Authorization": "Bearer " + token,
            "X-Bifrost-Session": session,
        }

        # Never forward the bearer token to a redirect target.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method: str, path: str, body=None, *, raw=False):
        data = (
            body if raw else (json.dumps(body).encode() if body is not None else None)
        )
        headers = {**self.headers, "Content-Type": "application/json"}
        if raw:
            headers["X-Artifact-Kind"] = "other"
        req = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(req, timeout=10) as reply:
                return json.load(reply)
        except urllib.error.HTTPError as exc:
            # A response can echo data; do not print it or the request headers.
            raise RuntimeError(
                f"platform refused {method} with HTTP {exc.code}"
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise RuntimeError("platform unavailable") from None


def git(repo: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def child_active(directory: Path) -> bool:
    with (directory / "child.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def supervise(directory: Path, lock_fd: int, repo: str, args: list[str]) -> int:
    # The lock is acquired by the parent and inherited across exec. No
    # resumed wrapper can race the launch before this durable receipt.
    try:
        atomic(directory / "child.json", {"pid": os.getpid()})
        try:
            code = subprocess.call(["codex", "exec", *args], cwd=repo)
        except OSError:
            code = 127
        atomic(directory / "exit.json", {"exit_code": code})
        return code
    finally:
        os.close(lock_fd)


def launch(directory: Path, args: list[str], repo: str) -> subprocess.Popen:
    with (directory / "child.lock").open("a") as child_lock:
        fcntl.flock(child_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        env = dict(os.environ)
        env.pop("BIFROST_DISPATCH_TOKEN", None)
        return subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--supervise",
                str(directory),
                str(child_lock.fileno()),
                repo,
                *args,
            ],
            pass_fds=(child_lock.fileno(),),
            start_new_session=True,
            env=env,
        )


def dispatch(options, args: list[str], *, interval=30.0, poll=0.2) -> int:
    token = os.environ.get("BIFROST_DISPATCH_TOKEN", "")
    if not token:
        raise ValueError("BIFROST_DISPATCH_TOKEN is required")
    client = Client(options.url, options.session, token)
    run_dir = (
        Path(options.state_dir)
        / hashlib.sha256(
            (options.session + "\0" + options.run_key).encode()
        ).hexdigest()
    )
    run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (run_dir / "wrapper.lock").open("a") as wrapper_lock:
        try:
            fcntl.flock(wrapper_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another wrapper owns this run") from None
        path = run_dir / "state.json"
        description = Path(options.description).read_bytes()
        # Closed server schema is the payload allowlist. Command arguments,
        # environment, credentials and report contents are never uploaded.
        parsed = json.loads(description)
        allowed = {
            "v",
            "kind",
            "task",
            "executor",
            "provider",
            "repo",
            "branch",
            "acceptance_refs",
            "estimate_minutes",
        }
        if set(parsed) != allowed:
            raise ValueError(
                "description must contain exactly the external-work schema fields"
            )
        registration = {
            "idempotency_key": "register:" + options.run_key,
            "root": options.root,
            "plan_node_id": options.node,
            "source_run_key": options.run_key,
            "artifact_id": digest(description),
        }
        report = str(Path(options.report).resolve())
        repo = str(Path(options.repo).resolve())
        if path.exists():
            state = json.loads(path.read_text())
            if (
                state["registration"] != registration
                or state["report"] != report
                or state["repo"] != repo
            ):
                raise ValueError("run key already belongs to different content")
        else:
            state = {
                "registration": registration,
                "report": report,
                "repo": repo,
                "base_commit": git(repo, "rev-parse", "HEAD"),
                "seq": 0,
            }
            atomic(path, state)
        client.request(
            "PUT", "/artifacts/" + registration["artifact_id"], description, raw=True
        )
        out = client.request("POST", "/external-work", registration)
        state["id"] = out["external_work_id"]
        atomic(path, state)
        route = "/external-work/" + urllib.parse.quote(state["id"], safe="")

        def deliver_pending():
            if "pending" not in state:
                return
            result = client.request("POST", route + "/events", state["pending"])
            state["seq"] = result["seq"]
            state.pop("pending")
            atomic(path, state)

        def event(kind, **fields):
            deliver_pending()
            seq = state["seq"] + 1
            state["pending"] = {
                "idempotency_key": f"{options.run_key}:{seq}",
                "seq": seq,
                "type": kind,
                **fields,
            }
            atomic(path, state)
            deliver_pending()

        deliver_pending()
        current = client.request("GET", route)
        state["seq"] = current["seq"]
        atomic(path, state)
        if current["state"] in ("Submitted", "Cancelled"):
            return int(state.get("exit_code", 0))
        if current["state"] == "Registered":
            event("started")
        child = None
        if not (run_dir / "exit.json").exists() and not child_active(run_dir):
            if state.get("launch_attempted") or (run_dir / "child.json").exists():
                raise RuntimeError(
                    "child disappeared without an exit receipt; run stays Unconfirmed; reconcile this run, do not relaunch"
                )
            # Persist intent before spawning: a crash before the supervisor's
            # receipt must not permit an implicit second launch on resume.
            state["launch_attempted"] = True
            atomic(path, state)
            child = launch(run_dir, args, repo)
        next_heartbeat = time.monotonic() + interval
        while not (run_dir / "exit.json").exists():
            if (
                (
                    (child is not None and child.poll() is not None)
                    or not child_active(run_dir)
                )
                and not (run_dir / "exit.json").exists()
            ):
                raise RuntimeError(
                    "child disappeared without an exit receipt; run stays Unconfirmed"
                )
            # Heartbeats require a durable startup acknowledgement. A stuck
            # or dead supervisor before child.json is not confirmed running.
            if (run_dir / "child.json").exists() and time.monotonic() >= next_heartbeat:
                try:
                    event("heartbeat")
                except RuntimeError as exc:
                    print(str(exc), file=sys.stderr)
                next_heartbeat = time.monotonic() + interval
            time.sleep(poll)
        if child is not None:
            child.wait()
        receipt = json.loads((run_dir / "exit.json").read_text())
        state["exit_code"] = receipt["exit_code"]
        atomic(path, state)
        result = {
            "exit_code": receipt["exit_code"],
            "report_path_digest": digest(report.encode()),
            "commit_shas": [],
        }
        if Path(report).is_file():
            result["report_digest"] = digest(Path(report).read_bytes())
        if state["base_commit"]:
            result["commit_shas"] = git(
                repo, "rev-list", "--max-count=100", state["base_commit"] + "..HEAD"
            ).splitlines()
        event("submitted", **result)
        return receipt["exit_code"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "url",
        "session",
        "run-key",
        "root",
        "node",
        "description",
        "report",
        "state-dir",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    args = options.args[1:] if options.args[:1] == ["--"] else options.args
    try:
        return dispatch(options, args)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"dispatch failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--supervise":
        sys.exit(
            supervise(Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5:])
        )
    sys.exit(main())
