#!/usr/bin/env python3
"""Record a Claude session's external work without launching any subprocess.

Use register, heartbeat, submit or abandon. Authentication comes exclusively
from BIFROST_DISPATCH_TOKEN. Each run keeps its own state directory.
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import re
import sys
import urllib.parse
from pathlib import Path

# Keep the existing wrapper's transport, atomic writes and pending-event
# protocol in one place. Importing it never invokes dispatch or supervise.
_spec = importlib.util.spec_from_file_location(
    "dispatch_codex", Path(__file__).with_name("dispatch-codex.py")
)
dispatch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dispatch)

SCHEMA = "claude-work/v1"
DESCRIPTION_FIELDS = {
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


def no_credentials(value, token: str) -> None:
    if token in json.dumps(value, ensure_ascii=False):
        raise ValueError("dispatch credential must not appear in work metadata")


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate description field")
        result[key] = value
    return result


def registration_state(options, token: str):
    url = options.url.rstrip("/")
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.path
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("url must be an HTTP(S) origin without credentials or query")
    if not re.fullmatch(r"local_[A-Za-z0-9_-]+", options.session):
        raise ValueError("session must be the reporter-owned local_ session ID")
    if not options.run_key.strip() or len(options.run_key) > 200:
        raise ValueError("run-key must contain 1 to 200 characters")
    description = Path(options.description).read_bytes()
    body = json.loads(description, object_pairs_hook=unique_fields)
    if not isinstance(body, dict) or set(body) != DESCRIPTION_FIELDS:
        raise ValueError(
            "description must contain exactly the external-work schema fields"
        )
    if body["executor"] != "claude" or body["provider"] != "anthropic":
        raise ValueError("description requires executor claude and provider anthropic")
    no_credentials(body, token)
    state = {
        "schema": SCHEMA,
        "url": url,
        "session": options.session,
        "registration": {
            "idempotency_key": "register:" + options.run_key,
            "root": options.root,
            "plan_node_id": options.node,
            "source_run_key": options.run_key,
            "artifact_id": dispatch.digest(description),
        },
        "seq": 0,
    }
    no_credentials(state, token)
    return state, description


def submission(options):
    commits = options.commit_sha
    if len(commits) > 100 or any(
        not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", sha) for sha in commits
    ):
        raise ValueError("commit-sha must be a full lowercase SHA; at most 100 commits")
    report = Path(options.report).resolve()
    return {
        "exit_code": options.exit_code,
        "report_path_digest": dispatch.digest(str(report).encode()),
        "report_digest": dispatch.digest(report.read_bytes()),
        "commit_shas": commits,
    }


def check_reply(reply, token: str):
    if (
        not isinstance(reply, dict)
        or not isinstance(reply.get("external_work_id"), str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", reply["external_work_id"])
        or type(reply.get("seq")) is not int
        or reply["seq"] < 0
        or reply.get("state") not in ("Registered", "Running", "Submitted", "Cancelled")
    ):
        raise RuntimeError("invalid external-work response from platform")
    no_credentials(reply, token)
    return reply


class WorkClient(dispatch.Client):
    def request(self, method, path, body=None, *, raw=False):
        reply = super().request(method, path, body, raw=raw)
        if path.startswith("/external-work"):
            # Validate before EventJournal consumes a response or writes seq.
            check_reply(reply, self.headers["Authorization"].removeprefix("Bearer "))
        return reply


def run(options):
    token = os.environ.get("BIFROST_DISPATCH_TOKEN", "")
    if not token:
        raise ValueError("BIFROST_DISPATCH_TOKEN is required")
    directory = Path(options.state_dir)
    path = directory / "state.json"
    if options.command != "register" and not path.is_file():
        raise ValueError("no registered work in state-dir; run register first")
    candidate, description = (
        registration_state(options, token)
        if options.command == "register"
        else (None, None)
    )
    result = submission(options) if options.command == "submit" else None
    if result:
        no_credentials(result, token)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "wrapper.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another command owns this run; retry later") from None
        if path.exists():
            state = json.loads(path.read_text())
            if state.get("schema") != SCHEMA:
                raise ValueError("state-dir is not a Claude work registration")
            if candidate and any(
                state[key] != candidate[key]
                for key in (
                    "url",
                    "session",
                    "registration",
                )
            ):
                raise ValueError(
                    "state-dir already belongs to different content; use the original invocation"
                )
        else:
            state = candidate
            dispatch.atomic(path, state)
        no_credentials(state, token)
        if result and "submission" in state and state["submission"] != result:
            raise ValueError(
                "submitted report or result changed; restore the original submission"
            )

        client = WorkClient(state["url"], state["session"], token)
        registration = state["registration"]
        if "id" not in state:
            if options.command != "register":
                raise ValueError(
                    "registration incomplete; repeat the original register command"
                )
            client.request(
                "PUT",
                "/artifacts/" + registration["artifact_id"],
                description,
                raw=True,
            )
            reply = check_reply(
                client.request("POST", "/external-work", registration), token
            )
            state["id"] = reply["external_work_id"]
            dispatch.atomic(path, state)

        journal = dispatch.EventJournal(
            client, path, state, registration["source_run_key"]
        )
        # Replay before GET: the last POST may have committed while its reply
        # was lost. Reusing its key and sequence is the server's recovery contract.
        pending_type = state.get("pending", {}).get("type")
        journal.deliver_pending()
        current = check_reply(client.request("GET", journal.route), token)
        if current["external_work_id"] != state["id"]:
            raise RuntimeError("platform returned a different external work ID")
        state["seq"] = current["seq"]
        dispatch.atomic(path, state)
        status = current["state"]

        if options.command == "register":
            if status == "Registered":
                current = journal.event("started")
        elif options.command == "heartbeat":
            if status != "Running":
                raise ValueError(
                    "heartbeat requires Running work; run register first or stop the heartbeat loop"
                )
            if pending_type != "heartbeat":
                current = journal.event("heartbeat")
        elif options.command == "submit":
            if status == "Submitted" and state.get("submission") == result:
                return current
            if status != "Running":
                raise ValueError("submit requires Running work")
            state["submission"] = result
            # EventJournal atomically persists this result with the pending event.
            current = journal.event("submitted", **result)
        elif options.command == "abandon":
            if status == "Submitted":
                raise ValueError("submitted work cannot be abandoned")
            if status != "Cancelled":
                current = journal.event("cancelled")
        return check_reply(current, token)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse normally echoes unknown arguments (possibly a pasted token).
        self.print_usage(sys.stderr)
        self.exit(
            2,
            "invalid arguments; use --help (credentials belong only in BIFROST_DISPATCH_TOKEN)\n",
        )


def main(argv=None) -> int:
    parser = Parser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register", allow_abbrev=False)
    for name in (
        "url",
        "session",
        "run-key",
        "root",
        "node",
        "description",
        "state-dir",
    ):
        register.add_argument("--" + name, required=True)
    for name in ("heartbeat", "submit", "abandon"):
        command = commands.add_parser(name, allow_abbrev=False)
        command.add_argument("--state-dir", required=True)
        if name == "submit":
            command.add_argument("--report", required=True)
            command.add_argument("--exit-code", type=int, default=0)
            command.add_argument("--commit-sha", action="append", default=[])
    options = parser.parse_args(argv)
    try:
        reply = run(options)
        print(
            json.dumps(
                {key: reply[key] for key in ("external_work_id", "state", "seq")}
            )
        )
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        message = str(exc)
        token = os.environ.get("BIFROST_DISPATCH_TOKEN", "")
        if token:
            message = message.replace(token, "[redacted]")
        print(f"claude work failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
