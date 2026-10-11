"""Write commands. Each one appends an event or refuses, and does nothing else.

There is no run, no observe, and no read of a live approval or cluster.
A refusal writes nothing. The exit is about the bookkeeping, not about
whether a step may proceed.
"""

from __future__ import annotations

import time
from pathlib import Path

from estimate import usual_for
from events import append_bytes, dump_line, load_file, seal
from locks import LockBusy, hold
from model import BY
from repair import repair_torn_tail
from validate import refusal

import secrets


class RecorderError(Exception):
    def __init__(self, message: str, reason: str | None = None):
        super().__init__(message)
        self.reason = reason or "refused"
        self.message = message


def _work_dir(root: Path, work_id: str) -> Path:
    if not isinstance(work_id, str) or "/" in work_id or work_id in {"", ".", ".."}:
        raise RecorderError("work id is not a single name", "bad_value")
    return root / work_id


def _write(root: Path, work_id: str, fields_list: list[dict], by: str, command: str) -> list[dict]:
    if by not in BY:
        raise RecorderError("by is not an entry", "by_mismatch")
    directory = _work_dir(root, work_id)
    directory.mkdir(parents=True, exist_ok=True)
    at = time.time()
    try:
        with hold(directory, command):
            repair_torn_tail(directory, by=by, at=at)
            path = directory / "events.jsonl"
            log = load_file(path)
            if log.invalid_seq is not None:
                raise RecorderError(
                    f"log invalid at seq {log.invalid_seq}",
                    "log_invalid",
                )
            if log.full:
                raise RecorderError("log full", "log_full")
            pending = []
            events = list(log.events)
            digests = list(log.digests)
            for fields in fields_list:
                sealed = seal(fields, _view(events, digests), by, at)
                reason = refusal(events, sealed, work_id=work_id)
                if reason:
                    raise RecorderError(reason, reason)
                pending.append(sealed)
                events.append(sealed)
                digests.append(dump_line(sealed).split(b" ", 1)[0].decode("ascii"))
            blob = b"".join(dump_line(item) for item in pending)
            try:
                append_bytes(path, blob)
            except ValueError as exc:
                text = str(exc)
                if "full" in text:
                    raise RecorderError("log full", "log_full") from None
                raise RecorderError(text, "log_invalid") from None
            return pending
    except LockBusy as exc:
        raise RecorderError(str(exc), "lock_busy") from None


class _view:
    def __init__(self, events, digests):
        self.events = events
        self.digests = digests


def _new_id() -> str:
    return secrets.token_hex(4)


def open_work(root: Path, work_id: str, title: str, goal: str | None = None, work_ref: str | None = None) -> dict:
    fields = {"type": "work_opened", "work_id": work_id, "title": title}
    if goal is not None:
        fields["goal"] = goal
    if work_ref is not None:
        fields["work_ref"] = work_ref
    return _write(root, work_id, [fields], "coordinator", "open")[0]


def close_work(root: Path, work_id: str, claim: str) -> dict:
    return _write(root, work_id, [{"type": "work_closed", "claim": claim}], "coordinator", "close")[0]


def declare_step(
    root: Path,
    work_id: str,
    *,
    name: str,
    kind: str,
    who: str,
    watch: str,
    locator: dict | None = None,
    waiting_on: list | None = None,
    after: str | None = None,
    round: float | None = None,
    replaces: str | None = None,
    text: str | None = None,
) -> dict:
    fields = {
        "type": "step_declared",
        "step_id": _new_id(),
        "name": name,
        "kind": kind,
        "who": who,
        "watch": watch,
    }
    if locator is not None:
        fields["locator"] = locator
    if waiting_on:
        fields["waiting_on"] = list(waiting_on)
    if after is not None:
        fields["after"] = after
    if round is not None:
        fields["round"] = round
    usual = usual_for(root, kind) if watch in {"process", "none"} else None
    if usual is not None:
        fields["usual_s"], fields["usual_basis"] = usual
    batch = [fields]
    if replaces is not None:
        superseded = {"type": "step_superseded", "step_id": replaces, "by_step": fields["step_id"]}
        if text is not None:
            superseded["text"] = text
        batch.append(superseded)
    written = _write(root, work_id, batch, "coordinator", "declare")
    return written[0]


def withdraw_step(root: Path, work_id: str, step_id: str, text: str | None = None) -> dict:
    fields = {"type": "step_superseded", "step_id": step_id}
    if text is not None:
        fields["text"] = text
    return _write(root, work_id, [fields], "coordinator", "withdraw")[0]


def start_step(root: Path, work_id: str, step_id: str) -> dict:
    """Start a ``none`` step. A process step is started by the wrapper, not here."""
    return _write(
        root,
        work_id,
        [{"type": "step_started", "step_id": step_id, "run_id": _new_id()}],
        "coordinator",
        "start",
    )[0]


def finish_step(root: Path, work_id: str, step_id: str, reported: str, quote: str | None = None) -> dict:
    """Finish a ``none`` step. The process exit code is written by the wrapper."""
    log = load_file(_work_dir(root, work_id) / "events.jsonl")
    run_id = None
    for event in log.events:
        if event.get("type") == "step_started" and event.get("step_id") == step_id:
            run_id = event.get("run_id")
    if run_id is None:
        raise RecorderError("not_started", "not_started")
    fields = {
        "type": "step_finished",
        "step_id": step_id,
        "run_id": run_id,
        "reported": reported,
    }
    if quote is not None:
        fields["quote"] = quote
    return _write(root, work_id, [fields], "coordinator", "finish")[0]


def write_note(root: Path, work_id: str, text: str, step_id: str | None = None) -> dict:
    fields = {"type": "note", "text": text}
    if step_id is not None:
        fields["step_id"] = step_id
    return _write(root, work_id, [fields], "coordinator", "note")[0]


def owner_open(root: Path, work_id: str, title: str, **optional) -> dict:
    """Open a declared owner item. Binding a real approval or question is not this slice."""
    fields = {
        "type": "owner_wait_opened",
        "wait_id": _new_id(),
        "title": title,
        "ref": {"kind": "none", "id": optional.pop("ref_id", _new_id())},
        "can_act": optional.pop("can_act"),
    }
    for key, value in optional.items():
        if value is not None:
            fields[key] = value
    return _write(root, work_id, [fields], "coordinator", "owner-open")[0]


def owner_ready(root: Path, work_id: str, wait_id: str) -> dict:
    return _write(
        root,
        work_id,
        [{"type": "owner_wait_ready", "wait_id": wait_id}],
        "coordinator",
        "owner-ready",
    )[0]


def owner_close(root: Path, work_id: str, wait_id: str, how: str) -> dict:
    return _write(
        root,
        work_id,
        [{"type": "owner_wait_closed", "wait_id": wait_id, "how": how}],
        "coordinator",
        "owner-close",
    )[0]
