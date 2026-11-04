"""The single writer of a collector's Claude external work (R5:5.5-12 S1-5, §2.3, §2.4).

One (vendor, session, epoch) is one external work. Its directory is
~/.cache/bifrost/external-work/<vendor>/<session>/<epoch>/ (state.json,
description.json, wrapper.lock); the process holding wrapper.lock is its only
writer. The hooks start one writer per event (`register-claude-work.py
event`), detached; `register-claude-work.py bind` registers a session after
the fact. Every call first makes sure the work is registered and started,
then applies its own event, so calls that arrive out of order converge:

  start       registered and started
  heartbeat   + heartbeat (only while Running)
  submit      + submitted, with no results (the hook knows none, §2.3)
  cancel      cancelled, for an epoch a resume left without an end

Registration names the identity (vendor, session, epoch) and the run key
<vendor>:<session>:<epoch>; every event names the identity too (§1.4). The
collector token is the only credential; it is never written anywhere.
A refusal (HTTP 4xx) at registration is kept as `failed`, which the hooks
report as client_bind refused / register_failed; anything else is retried by
the next call with the same request bodies.
"""

from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = _load("collector_auth", "collector_auth.py")
dispatch = _load("dispatch_codex", "dispatch-codex.py")

SCHEMA = "collector-work/v1"
EVENTS = ("start", "heartbeat", "submit", "cancel")
DESCRIPTION_FIELDS = {"v", "kind", "task", "executor", "provider", "repo", "branch", "acceptance_refs", "estimate_minutes"}
TERMINAL = ("Submitted", "Cancelled")
LOCK_WAIT = 10.0
TERMINAL_FILE = "terminal.json"
RETRY_SECONDS = (2.0, 5.0)


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def check_description(raw: bytes, executor="claude", provider="anthropic") -> dict:
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate description field")
            out[key] = value
        return out

    body = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(body, dict) or set(body) != DESCRIPTION_FIELDS:
        raise ValueError("description must contain exactly the external-work schema fields")
    if body["executor"] != executor or body["provider"] != provider:
        raise ValueError(f"description requires executor {executor} and provider {provider}")
    return body


def check_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path.strip("/") or parsed.username or parsed.query or parsed.fragment:
        raise ValueError("url must be an HTTP(S) origin without credentials or query")
    return url.rstrip("/")


def read_launch(launch_id: str):
    """The launch record when it is a linked launch, else None."""
    try:
        directory = auth.launch_dir(launch_id)
        launch = json.loads((directory / "launch.json").read_text())
        description = (directory / "description.json").read_bytes()
    except (ValueError, OSError, json.JSONDecodeError):
        return None
    if launch.get("mode") != "linked" or launch.get("description_digest") != dispatch.digest(description):
        return None
    return launch, description


def new_state(url, vendor, session, epoch, root, node, description: bytes, sidebar=""):
    identity = {"vendor": vendor, "session": session, "epoch": epoch}
    run_key = f"{vendor}:{session}:{epoch}"
    registration = {
        "idempotency_key": "register:" + run_key,
        "root": root,
        "plan_node_id": node,
        "source_run_key": run_key,
        "artifact_id": dispatch.digest(description),
        **identity,
    }
    if sidebar and auth.ID_RE.fullmatch(sidebar):
        registration["sidebar"] = sidebar
    return {"schema": SCHEMA, "url": check_url(url), "identity": identity, "registration": registration, "seq": 0}


def check_reply(reply):
    if (
        not isinstance(reply, dict)
        or not isinstance(reply.get("external_work_id"), str)
        or type(reply.get("seq")) is not int
        or reply.get("state") not in ("Registered", "Running", "Submitted", "Cancelled")
    ):
        raise RuntimeError("invalid external-work response from platform")
    return reply


class Locked:
    """flock with a bounded wait: the writer is detached, so it may wait for the one before it."""

    def __init__(self, path: Path, wait: float):
        self.path, self.wait = path, wait

    def __enter__(self):
        self.stream = self.path.open("a")
        end = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= end:
                    self.stream.close()
                    raise RuntimeError("another writer holds this work") from None
                time.sleep(0.05)

    def __exit__(self, *exc):
        self.stream.close()


def note_terminal(directory: Path, event: str) -> None:
    """Keep a work's end (submit) or cancel before any lock or request; the first one kept stands.

    Written as a temporary file linked into place, so it is whole or absent, and
    an existing one is never replaced. The hooks write the same file (collector-launch.js).
    """
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = directory / TERMINAL_FILE
    if target.exists():
        return
    tmp = directory / f".{TERMINAL_FILE}.{os.getpid()}.tmp"
    tmp.write_text(json.dumps({"event": event, "at": now_text()}))
    tmp.chmod(0o600)
    try:
        os.link(tmp, target)
    except FileExistsError:
        pass
    finally:
        tmp.unlink(missing_ok=True)


def read_terminal(directory: Path):
    try:
        event = json.loads((directory / TERMINAL_FILE).read_text()).get("event")
    except (OSError, ValueError, AttributeError):
        return None
    return event if event in ("submit", "cancel") else None


def _register(state, path, directory, client):
    registration = state["registration"]
    # Marked before the POST: a lost reply may still have registered the work.
    state["registration_sent"] = True
    dispatch.atomic(path, state)
    description = (directory / "description.json").read_bytes()
    try:
        client.request("PUT", "/artifacts/" + registration["artifact_id"], description, raw=True)
        reply = check_reply(client.request("POST", "/external-work", registration))
    except RuntimeError as exc:
        if " HTTP 4" in str(exc):
            state["failed"] = {"why": str(exc)[:120], "at": now_text()}
            dispatch.atomic(path, state)
        raise
    state["id"] = reply["external_work_id"]
    state.pop("failed", None)
    if reply.get("registered_at"):
        state["registered_at"] = reply["registered_at"]
    dispatch.atomic(path, state)


def _deliver(state, path, directory, event, token, retry_failed=False):
    """Bring the work to what is kept for it: registered and started, then its end or cancel
    once one is kept (terminal.json), else this call's heartbeat. A cancelled epoch never
    becomes Running: nothing is registered for it unless a registration may already exist."""
    client = dispatch.Client(state["url"], state["identity"]["session"], token)
    terminal = read_terminal(directory)
    if "id" not in state:
        if terminal == "cancel" and not state.get("registration_sent"):
            return None
        if state.get("failed") and not retry_failed:
            return None
        _register(state, path, directory, client)
    journal = dispatch.EventJournal(client, path, state, state["registration"]["source_run_key"], state["identity"])
    journal.deliver_pending()
    current = check_reply(client.request("GET", journal.route))
    for _ in range(2):  # once more if an end was kept while this call ran
        state["seq"], state["status"] = current["seq"], current["state"]
        dispatch.atomic(path, state)
        status = current["state"]
        if status in TERMINAL:
            return current
        if terminal == "cancel":
            current = check_reply(journal.event("cancelled"))
        else:
            if status == "Registered":
                current = check_reply(journal.event("started"))
            if terminal == "submit":
                current = check_reply(journal.event("submitted"))
            elif event == "heartbeat" and current["state"] == "Running":
                current = check_reply(journal.event("heartbeat"))
                event = "start"
        state["seq"], state["status"] = current["seq"], current["state"]
        dispatch.atomic(path, state)
        later = read_terminal(directory)
        if later == terminal:
            return current
        terminal = later
    return current


def run_event(event, vendor, session, epoch, url="", launch_id="", *, wait=LOCK_WAIT, tries=None):
    """One hook event for one external work. Returns the work's reply, or None when there is nothing to write.

    An end or a cancel is kept before anything else, and its delivery is tried a few times;
    whatever is still undelivered is delivered by the next call for this work, bind included."""
    if event not in EVENTS:
        raise ValueError("event is start, heartbeat, submit or cancel")
    token = auth.collector_token()
    if not token:
        raise ValueError("collector mode is off: no collector token")
    directory = auth.epoch_dir(vendor, session, epoch)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if event in ("submit", "cancel"):
        note_terminal(directory, event)
    tries = tries or (3 if event in ("submit", "cancel") else 1)
    for attempt in range(tries):
        try:
            return _run_once(event, vendor, session, epoch, url, launch_id, directory, token, wait)
        except RuntimeError:
            if attempt + 1 >= tries:
                raise
            time.sleep(RETRY_SECONDS[attempt])


def _run_once(event, vendor, session, epoch, url, launch_id, directory, token, wait):
    path = directory / "state.json"
    with Locked(directory / "wrapper.lock", wait):
        if path.exists():
            state = json.loads(path.read_text())
            if state.get("schema") != SCHEMA:
                raise ValueError("not a collector work directory")
        else:
            found = read_launch(launch_id) if launch_id and read_terminal(directory) != "cancel" else None
            if not found:
                return None
            launch, description = found
            state = new_state(url, vendor, session, epoch, launch["root"], launch["node"], description, launch.get("sidebar", ""))
            state["launch_id"] = launch_id
            (directory / "description.json").write_bytes(description)
            (directory / "description.json").chmod(0o600)
            dispatch.atomic(path, state)
        return _deliver(state, path, directory, event, token)


def bind(vendor, session, epoch, root, node, description_file, url, sidebar="", *, wait=LOCK_WAIT):
    """Register a session after the fact (§2.4). Repeating it with the same inputs writes nothing new."""
    token = auth.collector_token()
    if not token:
        raise ValueError("collector mode is off: no collector token")
    description = Path(description_file).read_bytes()
    check_description(description)
    candidate = new_state(url, vendor, session, epoch, root, node, description, sidebar)
    directory = auth.epoch_dir(vendor, session, epoch)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "state.json"
    with Locked(directory / "wrapper.lock", wait):
        if path.exists():
            state = json.loads(path.read_text())
            if state.get("schema") != SCHEMA or any(state.get(k) != candidate[k] for k in ("url", "identity", "registration")):
                raise ValueError("this session epoch is already bound to other content; it is not bound again")
        else:
            state = candidate
            (directory / "description.json").write_bytes(description)
            (directory / "description.json").chmod(0o600)
            dispatch.atomic(path, state)
        return _deliver(state, path, directory, "start", token, retry_failed=True)
