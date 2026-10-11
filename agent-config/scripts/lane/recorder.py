"""Recording primitives: durable directories, intent, manifest, and events.

These functions do not spawn a step. ``run`` in round 1 never calls them.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from errors import LaneError
from events import append_obj, dump_line, load_file, sha256_bytes
from evidence import (
    attempt_dir,
    manifest_digest,
    parse_review_report,
    parse_verify_stdout,
    publish_json_doc,
)
from fsutil import fsync_dir, publish, write_bytes
from query import STEPS, closing_resolutions, events_for_step, exec_of, round_events, verdict_event


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_attempt_id(when: datetime | None = None) -> str:
    moment = when or datetime.now(timezone.utc)
    return moment.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)


def write_initial_log(lane_dir: Path, created_fields: dict, opened_fields: dict) -> None:
    first = dict(created_fields)
    first.setdefault("at", now_iso())
    first["type"] = "lane_created"
    first["seq"] = 1
    first["prev_sha256"] = ""
    line1 = dump_line(first)
    second = dict(opened_fields)
    second.setdefault("at", first["at"])
    second["type"] = "round_opened"
    second["seq"] = 2
    second["prev_sha256"] = line1[:64].decode("ascii")
    line2 = dump_line(second)
    publish(lane_dir / "events.jsonl", line1 + line2)


def make_attempt(lane_dir: Path, rnd: int, step: str, attempt: str) -> Path:
    root = lane_dir / f"r{rnd}" / f"{step}-{attempt}"
    os.mkdir(root)
    (root / "rec").mkdir()
    (root / "out").mkdir()
    (root / "work").mkdir()
    fsync_dir(root)
    fsync_dir(root.parent)
    return root


def _as_bytes(value: bytes | str | None) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def record_attempt(
    lane_dir: Path,
    *,
    step: str,
    stdout: bytes | str = b"",
    stderr: bytes | str = b"",
    report: bytes | str | None = None,
    exit_code: int | None = 0,
    signal: int | None = None,
    termination: str = "exited",
    checks: dict | None = None,
    pinned: dict | None = None,
    bundles: dict | None = None,
    bundle_bytes: dict | None = None,
    consumed: dict | None = None,
    notes: list | None = None,
    not_started: dict | None = None,
    pre_checks: dict | None = None,
    write_verdict: bool = True,
    also_start: bool = True,
    limit_seconds: int = 3600,
    started_at: str | None = None,
    holding_lock: bool = False,
    attempt_id: str | None = None,
) -> dict:
    from commands import enter

    def action(locked_dir, _view, _ctx):
        return _record_attempt(
            locked_dir,
            step=step,
            stdout=_as_bytes(stdout) or b"",
            stderr=_as_bytes(stderr) or b"",
            report=_as_bytes(report),
            exit_code=exit_code,
            signal=signal,
            termination=termination,
            checks=checks,
            pinned=pinned,
            bundles=bundles,
            bundle_bytes=bundle_bytes,
            consumed=consumed,
            notes=notes,
            not_started=not_started,
            pre_checks=pre_checks,
            write_verdict=write_verdict,
            also_start=also_start,
            limit_seconds=limit_seconds,
            started_at=started_at,
            attempt_id=attempt_id,
        )

    # Gate 1 (LANE_EXEC) runs inside enter, before the lock and before repair.
    return enter(lane_dir.parent, lane_dir.name, "record", action, held=holding_lock, lane_dir=lane_dir)


def _record_attempt(lane_dir: Path, **kw) -> dict:
    from state import inspect_lane

    events = load_file(lane_dir / "events.jsonl").events
    view = inspect_lane(lane_dir, driver=False)
    rnd = int(view["round"])
    lane_id = view["lane_id"] or lane_dir.name
    step = kw["step"]
    grouped = events_for_step(events, rnd, step)
    intents = grouped["step_intent"]
    records = grouped["step_recorded"]
    _refuse_closed(events, rnd)
    if records:
        existing = exec_of(records[0]).get("attempt_id")
        raise LaneError(f"{step} already has attempt {existing} in round {rnd}")
    if intents:
        open_id = exec_of(intents[0]).get("attempt_id")
        if kw["attempt_id"] != open_id:
            if kw["attempt_id"] is None:
                raise LaneError(f"{step} already has attempt {open_id} in round {rnd}")
            raise LaneError(f"attempt {kw['attempt_id']} is not the open intent of {step}")
        return _finish_open(lane_dir, intents[0], kw)
    _refuse_order(view, step)
    attempt = kw["attempt_id"] or new_attempt_id()
    exec_body = {
        "lane_id": lane_id,
        "round": rnd,
        "step": step,
        "step_index": STEPS.index(step),
        "attempt_id": attempt,
    }
    root = make_attempt(lane_dir, rnd, step, attempt)
    info = _created_fields(lane_dir)
    intent = {
        "exec": exec_body,
        "step_order": list(STEPS),
        "argv": ["lane-step", step],
        "cwd": "work",
        "brief": _brief_ref(lane_dir, rnd, events),
        "config_sha256": info.get("config_sha256"),
        "pinned_files": info.get("pinned_files") or {},
        "repos": info.get("repos") or {},
        "consumed": kw["consumed"] or {},
        "pre_checks": kw["pre_checks"] if isinstance(kw.get("pre_checks"), dict) else {},
        "toolchain": {},
        "limit_seconds": kw["limit_seconds"],
        "env_names": ["PATH", "LC_ALL"],
        "driver_pid": os.getpid(),
    }
    intent_sha = publish_json_doc(root / "rec" / "intent.json", intent)
    append_obj(
        lane_dir,
        {
            "type": "step_intent",
            "exec": exec_body,
            "intent_sha256": intent_sha,
            "consumed": kw["consumed"] or {},
        },
    )
    not_started = kw["not_started"]
    if kw["also_start"] and not_started is None:
        append_obj(
            lane_dir,
            {
                "type": "step_started",
                "exec": exec_body,
                "pid": os.getpid(),
                "lstart": kw["started_at"] or now_iso(),
                "started_at": kw["started_at"] or now_iso(),
                "limit_seconds": kw["limit_seconds"],
            },
        )
    manifest = _manifest(root, exec_body, intent_sha, kw)
    manifest_sha = publish_json_doc(root / "rec" / "manifest.json", manifest)
    _append_recorded(lane_dir, exec_body, manifest, manifest_sha)
    if kw["write_verdict"]:
        flush_verdict(lane_dir)
    return exec_body


def _created_fields(lane_dir: Path) -> dict:
    from events import load_file
    from query import created

    event = created(load_file(lane_dir / "events.jsonl").events) or {}
    return event


def _manifest(root: Path, exec_body: dict, intent_sha: str, kw: dict) -> dict:
    consumed = kw["consumed"] or {}
    if kw["not_started"] is not None:
        return {
            "exec": exec_body,
            "intent_sha256": intent_sha,
            "not_started": kw["not_started"],
            "exit": None,
            "termination": None,
            "started_at": None,
            "ended_at": None,
            "outputs": {},
            "checks": None,
            "fields": None,
            "consumed": consumed,
            "pre_checks": kw.get("pre_checks") if isinstance(kw.get("pre_checks"), dict) else {},
        }
    stdout = kw["stdout"]
    stderr = kw["stderr"]
    # Artifacts are durable before the manifest is built or published.
    write_bytes(root / "out" / "stdout", stdout)
    write_bytes(root / "out" / "stderr", stderr)
    outputs = {
        "stdout": {"length": len(stdout), "sha256": sha256_bytes(stdout)},
        "stderr": {"length": len(stderr), "sha256": sha256_bytes(stderr)},
    }
    step = exec_body["step"]
    fields: dict = {}
    if step == "verify":
        fields["stdout_last_line"] = parse_verify_stdout(stdout)
    report = kw["report"]
    if step == "review":
        if report is None:
            outputs["report"] = {"present": False}
            fields = {"report_first_line": "", "report_last_line": "", "p1": 0, "p2": 0, "p3": 0}
        else:
            write_bytes(root / "out" / "report", report)
            parsed = parse_review_report(report)
            outputs["report"] = {"present": True, "length": len(report), "sha256": sha256_bytes(report)}
            fields = parsed
    bundles = dict(kw["bundles"] or {})
    for repo, blob in (kw["bundle_bytes"] or {}).items():
        dest = root / "rec" / f"{repo}.bundle"
        write_bytes(dest, blob)
        bundles[repo] = {"length": len(blob), "sha256": sha256_bytes(blob)}
    signal = kw["signal"]
    exit_body = {"code": None, "signal": signal} if signal is not None else {"code": kw["exit_code"], "signal": None}
    manifest = {
        "exec": exec_body,
        "intent_sha256": intent_sha,
        "not_started": None,
        "exit": exit_body,
        "termination": kw["termination"],
        "started_at": kw["started_at"] or now_iso(),
        "ended_at": now_iso(),
        "outputs": outputs,
        "checks": kw["checks"] if kw["checks"] is not None else {},
        "fields": fields,
        "consumed": consumed,
        "pre_checks": kw.get("pre_checks") if isinstance(kw.get("pre_checks"), dict) else {},
    }
    if step == "implement":
        manifest["pinned"] = kw["pinned"] or {}
        manifest["bundles"] = bundles
        manifest["notes"] = list(kw["notes"] or [])
    return manifest


def flush_verdict(lane_dir: Path) -> dict | None:
    from state import inspect_lane

    view = inspect_lane(lane_dir, driver=False)
    if view["state"] != "verdict_pending":
        return None
    return append_obj(
        lane_dir,
        {
            "type": "verdict",
            "round": view["round"],
            "result": view["decide_result"],
            "reason": view["decide_reason"],
            "sha_set": view["sha_set"],
            "manifests": view["manifest_shas"],
        },
    )


def append_resolution(lane_dir: Path, *, rnd: int, step: str, attempt: str, kind: str, operator: str, reason: str, evidence: str) -> dict:
    return append_obj(
        lane_dir,
        {
            "type": "resolution",
            "round": rnd,
            "step": step,
            "attempt_id": attempt,
            "kind": kind,
            "operator": operator,
            "reason": reason,
            "evidence": evidence,
        },
    )


def open_intent_only(lane_dir: Path, *, step: str = "implement", holding_lock: bool = False) -> dict:
    """Publish an intent and append step_intent, then stop. The directory is an open attempt."""

    from commands import enter

    def action(locked_dir, _view, _ctx):
        return _open_intent(locked_dir, step)

    return enter(lane_dir.parent, lane_dir.name, "record", action, held=holding_lock, lane_dir=lane_dir)


def _open_intent(lane_dir: Path, step: str) -> dict:
    from state import inspect_lane

    events = load_file(lane_dir / "events.jsonl").events
    view = inspect_lane(lane_dir, driver=False)
    rnd = int(view["round"])
    _refuse_closed(events, rnd)
    grouped = events_for_step(events, rnd, step)
    if grouped["step_intent"] or grouped["step_recorded"]:
        existing = exec_of((grouped["step_intent"] or grouped["step_recorded"])[0]).get("attempt_id")
        raise LaneError(f"{step} already has attempt {existing} in round {rnd}")
    _refuse_order(view, step)
    lane_id = view["lane_id"] or lane_dir.name
    attempt = new_attempt_id()
    exec_body = {
        "lane_id": lane_id,
        "round": rnd,
        "step": step,
        "step_index": STEPS.index(step),
        "attempt_id": attempt,
    }
    root = make_attempt(lane_dir, rnd, step, attempt)
    info = _created_fields(lane_dir)
    intent = {
        "exec": exec_body,
        "step_order": list(STEPS),
        "argv": ["lane-step", step],
        "cwd": "work",
        "brief": _brief_ref(lane_dir, rnd, events),
        "config_sha256": info.get("config_sha256"),
        "pinned_files": info.get("pinned_files") or {},
        "repos": info.get("repos") or {},
        "consumed": {},
        "pre_checks": {},
        "limit_seconds": 3600,
    }
    intent_sha = publish_json_doc(root / "rec" / "intent.json", intent)
    append_obj(
        lane_dir,
        {"type": "step_intent", "exec": exec_body, "intent_sha256": intent_sha, "consumed": {}},
    )
    return exec_body


def mark_started(lane_dir: Path, exec_body: dict, *, started_at: str | None = None, limit_seconds: int = 3600, holding_lock: bool = False) -> None:
    from commands import enter

    def action(locked_dir, _view, _ctx):
        append_obj(
            locked_dir,
            {
                "type": "step_started",
                "exec": exec_body,
                "pid": os.getpid(),
                "lstart": started_at or now_iso(),
                "started_at": started_at or now_iso(),
                "limit_seconds": limit_seconds,
            },
        )

    enter(lane_dir.parent, lane_dir.name, "record", action, held=holding_lock, lane_dir=lane_dir)


def _refuse_closed(events: list[dict], rnd: int) -> None:
    if verdict_event(events, rnd) is not None:
        raise LaneError(f"round {rnd} already has a verdict")
    if closing_resolutions(events, rnd):
        raise LaneError(f"round {rnd} has a closing resolution")


def _refuse_order(view: dict, step: str) -> None:
    if view.get("state") == "ready" and view.get("next_step") == step:
        return
    raise LaneError(f"{step} is out of order in round {view.get('round')}")


def _brief_ref(lane_dir: Path, rnd: int, events: list[dict]) -> dict:
    opened = [event for event in round_events(events) if int(event.get("round", -1)) == rnd]
    event = opened[-1] if opened else {}
    rel = event.get("brief_copy")
    path = lane_dir / rel if rel else None
    if path is None or not path.is_file():
        matches = sorted((lane_dir / f"r{rnd}").glob("brief-*.md"))
        path = matches[-1] if matches else None
        rel = f"r{rnd}/{path.name}" if path is not None else event.get("brief_path")
    data = path.read_bytes() if path is not None and path.is_file() else b""
    return {"path": rel, "length": len(data), "sha256": sha256_bytes(data)}


def _finish_open(lane_dir: Path, intent_event: dict, kw: dict) -> dict:
    exec_body = dict(intent_event["exec"])
    root = attempt_dir(lane_dir, exec_body)
    intent_sha = intent_event["intent_sha256"]
    events = load_file(lane_dir / "events.jsonl").events
    started = events_for_step(events, int(exec_body["round"]), exec_body["step"])["step_started"]
    if kw["also_start"] and kw["not_started"] is None and not started:
        append_obj(
            lane_dir,
            {
                "type": "step_started",
                "exec": exec_body,
                "pid": os.getpid(),
                "lstart": kw["started_at"] or now_iso(),
                "started_at": kw["started_at"] or now_iso(),
                "limit_seconds": kw["limit_seconds"],
            },
        )
    manifest = _manifest(root, exec_body, intent_sha, kw)
    manifest_sha = publish_json_doc(root / "rec" / "manifest.json", manifest)
    _append_recorded(lane_dir, exec_body, manifest, manifest_sha)
    if kw["write_verdict"]:
        flush_verdict(lane_dir)
    return exec_body


def _append_recorded(lane_dir: Path, exec_body: dict, manifest: dict, manifest_sha: str) -> None:
    step = exec_body["step"]
    recorded = {
        "type": "step_recorded",
        "exec": exec_body,
        "manifest_sha256": manifest_sha,
        "not_started": manifest.get("not_started"),
        "exit": manifest.get("exit"),
        "consumed": manifest.get("consumed") or {},
    }
    if step == "implement":
        recorded["pinned"] = manifest.get("pinned") or {}
        recorded["bundles"] = manifest.get("bundles") or {}
    if step == "review":
        recorded["rejects"] = manifest.get("fields", {}).get("report_first_line") == "VERDICT: fix first" and bool(
            (manifest.get("outputs") or {}).get("report", {}).get("present")
        )
        recorded["sha_set"] = manifest.get("consumed") or {}
    append_obj(lane_dir, recorded)


def manifest_sha(obj: dict) -> str:
    return manifest_digest(obj)
