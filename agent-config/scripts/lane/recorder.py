"""Recording primitives: durable directories, intent, manifest, and events.

These functions do not spawn a step. ``run`` in round 1 never calls them.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from events import append_obj, dump_line, sha256_bytes
from evidence import manifest_digest, parse_review_report, parse_verify_stdout, publish_json_doc
from fsutil import fsync_dir, publish
from query import STEPS
from repair import repair_torn_tail
from locks import hold


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_attempt_id(when: datetime | None = None) -> str:
    moment = when or datetime.now(timezone.utc)
    return moment.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)


def _locked(lane_dir: Path, command: str, fn, holding_lock: bool):
    if holding_lock:
        return fn()
    with hold(lane_dir, lane_dir.name, command):
        repair_torn_tail(lane_dir)
        return fn()


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
    write_verdict: bool = True,
    also_start: bool = True,
    limit_seconds: int = 3600,
    started_at: str | None = None,
    holding_lock: bool = False,
    attempt_id: str | None = None,
) -> dict:
    def body() -> dict:
        repair_torn_tail(lane_dir)
        return _record_attempt(
            lane_dir,
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
            write_verdict=write_verdict,
            also_start=also_start,
            limit_seconds=limit_seconds,
            started_at=started_at,
            attempt_id=attempt_id,
        )

    return _locked(lane_dir, "record", body, holding_lock)


def _record_attempt(lane_dir: Path, **kw) -> dict:
    from state import inspect_lane

    view = inspect_lane(lane_dir, driver=False)
    rnd = int(view["round"])
    lane_id = view["lane_id"] or lane_dir.name
    step = kw["step"]
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
        "brief": {
            "path": info.get("brief_path"),
            "sha256": info.get("brief_sha256"),
        },
        "config_sha256": info.get("config_sha256"),
        "pinned_files": info.get("pinned_files") or {},
        "repos": info.get("repos") or {},
        "consumed": kw["consumed"] or {},
        "pre_checks": {},
        "toolchain": {},
        "limit_seconds": kw["limit_seconds"],
        "env_names": ["PATH", "LC_ALL"],
        "driver_pid": os.getpid(),
    }
    intent_sha = publish_json_doc(root / "rec" / "intent.json", intent)
    append_obj(lane_dir, {"type": "step_intent", "exec": exec_body, "intent_sha256": intent_sha})
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
        }
    stdout = kw["stdout"]
    stderr = kw["stderr"]
    (root / "out" / "stdout").write_bytes(stdout)
    (root / "out" / "stderr").write_bytes(stderr)
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
            (root / "out" / "report").write_bytes(report)
            parsed = parse_review_report(report)
            outputs["report"] = {"present": True, "length": len(report), "sha256": sha256_bytes(report)}
            fields = parsed
    bundles = dict(kw["bundles"] or {})
    for repo, blob in (kw["bundle_bytes"] or {}).items():
        dest = root / "rec" / f"{repo}.bundle"
        dest.write_bytes(blob)
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

    def body() -> dict:
        repair_torn_tail(lane_dir)
        from state import inspect_lane

        view = inspect_lane(lane_dir, driver=False)
        rnd = int(view["round"])
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
        intent = {"exec": exec_body, "argv": ["lane-step", step], "limit_seconds": 3600}
        intent_sha = publish_json_doc(root / "rec" / "intent.json", intent)
        append_obj(lane_dir, {"type": "step_intent", "exec": exec_body, "intent_sha256": intent_sha})
        return exec_body

    return _locked(lane_dir, "record", body, holding_lock)


def mark_started(lane_dir: Path, exec_body: dict, *, started_at: str | None = None, limit_seconds: int = 3600, holding_lock: bool = False) -> None:
    def body() -> None:
        repair_torn_tail(lane_dir)
        append_obj(
            lane_dir,
            {
                "type": "step_started",
                "exec": exec_body,
                "pid": os.getpid(),
                "lstart": started_at or now_iso(),
                "started_at": started_at or now_iso(),
                "limit_seconds": limit_seconds,
            },
        )

    _locked(lane_dir, "record", body, holding_lock)


def manifest_sha(obj: dict) -> str:
    return manifest_digest(obj)
