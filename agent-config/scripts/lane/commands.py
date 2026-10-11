"""State-changing commands. Every one walks the same six gates, then the table."""

from __future__ import annotations

import json
import os
import re
import secrets
from pathlib import Path

from errors import LaneError
from events import load_file, sha256_bytes
from fsutil import canonical_json, fsync_dir, publish
from locks import hold, read_snapshot
from query import (
    IN_PROGRESS,
    NEGATIVE,
    abandoned_event,
    baseline_set,
    created,
    may_open_round,
    resolve_start_set,
    round_events,
)
from recorder import (
    append_resolution,
    flush_verdict,
    now_iso,
    write_initial_log,
)
from repair import repair_torn_tail
from state import inspect_lane
from table import GATES, RUN_STUB, consult

_ = GATES  # the gate order below follows this table

ID_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA_OK = re.compile(r"^[0-9a-f]{40}$")
CLOSING = ("failed", "cancelled", "evidence-lost")


def default_root() -> Path:
    return Path.home() / "agent-work" / "lanes"


def gate_lane_exec() -> None:
    # Set at all, including to the empty string. Absence is the only negative.
    if "LANE_EXEC" in os.environ:
        raise LaneError(GATES[0]["refusal"])


def _require_id(lane_id: str) -> None:
    if not ID_OK.fullmatch(lane_id or ""):
        raise LaneError(f"lane id {lane_id!r} is not allowed")


def parse_repo(spec: str) -> tuple[str, dict]:
    parts = spec.split(":")
    if len(parts) < 5:
        raise LaneError("repo must be NAME:change|context:REF:SHA:TREE")
    name, role = parts[0], parts[1]
    tree = parts[-1]
    sha = parts[-2]
    ref = ":".join(parts[2:-2])
    if role not in ("change", "context"):
        raise LaneError(f"repo role must be change or context, not {role}")
    if not SHA_OK.fullmatch(sha):
        raise LaneError(f"commit id must be 40 hex digits: {sha}")
    if not SHA_OK.fullmatch(tree):
        raise LaneError(f"tree id must be 40 hex digits: {tree}")
    if not name or "/" in name or name in (".", ".."):
        raise LaneError(f"repo name {name!r} is not allowed")
    return name, {"role": role, "target_ref": ref, "target_sha": sha, "tree": tree}


def collect_repos(specs: list[str]) -> dict:
    """CLI repository list. A repeated name is refused, not overwritten."""
    repos: dict = {}
    for spec in specs:
        name, meta = parse_repo(spec)
        if name in repos:
            raise LaneError(f"duplicate repository {name}")
        repos[name] = meta
    return repos


def _require_baseline(repos: dict) -> None:
    if not isinstance(repos, dict) or not repos:
        raise LaneError("at least one repo is required")
    for name, meta in repos.items():
        if not isinstance(meta, dict):
            raise LaneError(f"repository {name} needs a commit and a tree")
        sha = meta.get("target_sha")
        tree = meta.get("tree")
        if not isinstance(sha, str) or not SHA_OK.fullmatch(sha):
            raise LaneError(f"commit id must be 40 hex digits: {sha}")
        if not isinstance(tree, str) or not SHA_OK.fullmatch(tree):
            raise LaneError(f"tree id must be 40 hex digits: {tree}")


def _file_sha(path: str | None) -> str | None:
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        return None
    return sha256_bytes(file.read_bytes())


def changed_file(events: list[dict]) -> str | None:
    info = created(events) or {}
    if info.get("config_path") and _file_sha(info.get("config_path")) != info.get("config_sha256"):
        return info["config_path"]
    for path, digest in (info.get("pinned_files") or {}).items():
        if _file_sha(path) != digest:
            return path
    opened = round_events(events)
    if opened and opened[-1].get("brief_path"):
        if _file_sha(opened[-1]["brief_path"]) != opened[-1].get("brief_sha256"):
            return opened[-1]["brief_path"]
    return None


def _ctx(view: dict, lane_id: str, command: str, extra: dict) -> dict:
    attempt = extra.get("attempt") or view.get("problem_attempt") or ""
    info = (view.get("attempts") or {}).get(attempt) if attempt else None
    known = info is not None
    if command not in ("resolve", "confirm-ended"):
        known = True
    return {
        "lane_id": lane_id,
        "round": view.get("round") or 1,
        "step": (info or {}).get("step") or view.get("step") or extra.get("step") or "implement",
        "attempt": attempt,
        "result": view.get("verdict_result"),
        "verdict_result": view.get("verdict_result"),
        "pending_result": view.get("pending_result"),
        "opened": view.get("opened") or 0,
        "budget": view.get("budget_max") or 2,
        "has_verdict": bool(view.get("has_verdict")),
        "file_changed": extra.get("file_changed"),
        "kind": extra.get("kind"),
        "known_attempt": known,
        "is_problem": bool(attempt) and attempt == view.get("problem_attempt"),
        "recorded": bool(info and info.get("recorded")),
        "exit_code": None if not info else info.get("exit_code"),
        "exit_signal": None if not info else info.get("exit_signal"),
        "resolved_kind": None if not info else info.get("resolved_kind"),
        "has_recorded_exit": bool(info and info.get("recorded")),
        "confirmed": bool(info and info.get("confirmed")),
    }


def enter(root: Path, lane_id: str, command: str, action, extra: dict | None = None, *, held: bool = False, lane_dir: Path | None = None):
    """One entry for every state-changing command, including ``new`` and ``record``.

    Gate 1 runs before argument checks. The lock, the log, the verdict flush
    and the transition table follow, in that order. ``may_open_round`` is the
    budget check for ``new`` and ``next-round``.
    """
    gate_lane_exec()
    extra = dict(extra or {})
    if command == "new":
        _require_id(lane_id)
        dest = root / lane_id
        budget = int(extra.get("budget") if extra.get("budget") is not None else 2)
        decision = consult(
            None if not dest.exists() else "ready",
            "new",
            {"lane_id": lane_id, "opened": 0, "budget": budget, "round": 1},
        )
        if not decision.allowed:
            raise LaneError(decision.message)
        if not may_open_round(0, budget):
            raise LaneError(f"over budget: 0/{budget}; the Owner decides")
        return action(dest, None, extra)
    _require_id(lane_id)
    if lane_dir is None:
        lane_dir = root / lane_id

    def run():
        repair_torn_tail(lane_dir)
        log = load_file(lane_dir / "events.jsonl")
        if log.invalid_seq is not None:
            if command == "abandon":
                return _abandon_corrupt(lane_dir, log, extra)
            raise LaneError(f"event log invalid at seq {log.invalid_seq}; a person must inspect it")
        flush_verdict(lane_dir)
        view = inspect_lane(lane_dir, driver=False)
        extra["file_changed"] = changed_file(load_file(lane_dir / "events.jsonl").events)
        ctx = _ctx(view, lane_id, command, extra)
        ctx["has_closing"] = bool(view.get("has_closing"))
        decision = consult(view["state"], command, ctx)
        if not decision.allowed:
            raise LaneError(decision.message)
        if command == "next-round" and not may_open_round(int(view["opened"] or 0), int(view["budget_max"] or 0)):
            raise LaneError(f"over budget: {view['opened']}/{view['budget_max']}; the Owner decides")
        return action(lane_dir, view, ctx)

    if not lane_dir.is_dir() or not (lane_dir / "events.jsonl").is_file():
        if lane_dir.is_dir():
            raise LaneError("incomplete lane directory")
        raise LaneError(f"lane {lane_id} does not exist")
    if held:
        return run()
    with hold(lane_dir, lane_id, command):
        return run()


def mutate(root: Path, lane_id: str, command: str, action, extra: dict | None = None):
    return enter(root, lane_id, command, action, extra)


def _abandon_corrupt(lane_dir: Path, log, extra: dict) -> None:
    if abandoned_event(log.events) is not None or (lane_dir / "abandoned.json").is_file():
        raise LaneError(f"lane {lane_dir.name} was abandoned")
    body = {
        "operator": extra.get("operator"),
        "reason": extra.get("reason"),
        "at": now_iso(),
        "last_seq": log.last_valid_seq or 0,
        "last_sha256": log.digests[-1] if log.digests else None,
    }
    publish(lane_dir / "abandoned.json", (canonical_json(body) + "\n").encode("utf-8"))


def cmd_new(root: Path, lane_id: str, *, title: str, brief: str, repos: dict, max_rounds: int = 2, config: str | None = None, pins: list[str] | None = None) -> None:
    def action(lane_dir, _view, _ctx):
        if max_rounds < 1:
            raise LaneError("max_rounds must be at least 1")
        if not title:
            raise LaneError("title is required")
        _require_baseline(repos)
        brief_path = Path(brief)
        if not brief_path.is_file():
            raise LaneError(f"brief not found: {brief}")
        if not root.is_dir():
            raise LaneError(f"lane root does not exist: {root}")
        pinned = {}
        for pin in pins or []:
            digest = _file_sha(pin)
            if digest is None:
                raise LaneError(f"pinned file not found: {pin}")
            pinned[pin] = digest
        config_sha = _file_sha(config) if config else None
        if config and config_sha is None:
            raise LaneError(f"config not found: {config}")
        brief_bytes = brief_path.read_bytes()
        copy_name = f"brief-{secrets.token_hex(4)}.md"
        params = {
            "lane_id": lane_id,
            "title": title,
            "max_rounds": max_rounds,
            "repos": repos,
            "config_path": config,
            "config_sha256": config_sha,
            "pinned_files": pinned,
            "brief_path": brief,
            "brief_sha256": sha256_bytes(brief_bytes),
            "brief_copy": f"r1/{copy_name}",
            "inputs": [],
            "created_at": now_iso(),
        }
        os.mkdir(lane_dir)
        round_dir = lane_dir / "r1"
        round_dir.mkdir()
        publish(round_dir / copy_name, brief_bytes)
        fsync_dir(round_dir)
        publish(lane_dir / "lane.json", (canonical_json(params) + "\n").encode("utf-8"))
        write_initial_log(
            lane_dir,
            params,
            {
                "round": 1,
                "brief_path": brief,
                "brief_sha256": params["brief_sha256"],
                "brief_copy": params["brief_copy"],
                "start": "baseline",
                "start_set": baseline_set(repos),
            },
        )
        fsync_dir(lane_dir)
        fsync_dir(root)

    enter(root, lane_id, "new", action, {"budget": max_rounds})


def cmd_run(root: Path, lane_id: str) -> None:
    def action(lane_dir, view, ctx):
        raise LaneError(RUN_STUB)

    mutate(root, lane_id, "run", action)


def cmd_next_round(root: Path, lane_id: str, *, brief: str, start: str = "pinned") -> None:
    def action(lane_dir, view, ctx):
        if start not in ("baseline", "pinned"):
            raise LaneError("start must be baseline or pinned")
        brief_path = Path(brief)
        if not brief_path.is_file():
            raise LaneError(f"brief not found: {brief}")
        if not may_open_round(int(view["opened"] or 0), int(view["budget_max"] or 0)):
            raise LaneError(f"over budget: {view['opened']}/{view['budget_max']}; the Owner decides")
        rnd = int(view["opened"]) + 1
        events = load_file(lane_dir / "events.jsonl").events
        targets = (created(events) or {}).get("repos") or {}
        start_set = resolve_start_set(events, rnd, targets, start)
        round_dir = lane_dir / f"r{rnd}"
        round_dir.mkdir(exist_ok=True)
        data = brief_path.read_bytes()
        copy_name = f"brief-{secrets.token_hex(4)}.md"
        publish(round_dir / copy_name, data)
        fsync_dir(round_dir)
        fsync_dir(lane_dir)
        from events import append_obj

        append_obj(
            lane_dir,
            {
                "type": "round_opened",
                "round": rnd,
                "brief_path": brief,
                "brief_sha256": sha256_bytes(data),
                "brief_copy": f"r{rnd}/{copy_name}",
                "start": start,
                "start_set": start_set,
            },
        )

    mutate(root, lane_id, "next-round", action)


def cmd_resolve(root: Path, lane_id: str, *, attempt: str, kind: str, operator: str, reason: str, evidence: str, code: int | None = None) -> None:
    def action(lane_dir, view, ctx):
        if kind == "passed":
            raise LaneError("unknown kind passed")
        if not operator or not reason or not evidence or not attempt:
            raise LaneError("resolve requires --attempt, --kind, --operator, --reason and --evidence")
        info = view["attempts"][attempt]
        append_resolution(
            lane_dir,
            rnd=int(info["round"]),
            step=info["step"],
            attempt=attempt,
            kind=kind,
            operator=operator,
            reason=reason,
            evidence=evidence,
        )
        if kind in CLOSING:
            flush_verdict(lane_dir)

    mutate(
        root,
        lane_id,
        "resolve",
        action,
        {"attempt": attempt, "kind": kind, "operator": operator, "reason": reason, "evidence": evidence, "code": code},
    )


def cmd_confirm(root: Path, lane_id: str, *, attempt: str, operator: str, how: str) -> None:
    def action(lane_dir, view, ctx):
        if not attempt or not operator or not how:
            raise LaneError("confirm-ended requires --attempt, --operator and --how")
        from events import append_obj

        append_obj(
            lane_dir,
            {"type": "execution_confirmed", "attempt_id": attempt, "operator": operator, "how": how},
        )

    mutate(root, lane_id, "confirm-ended", action, {"attempt": attempt, "operator": operator, "how": how})


def cmd_abandon(root: Path, lane_id: str, *, operator: str, reason: str) -> None:
    def action(lane_dir, view, ctx):
        if not operator or not reason:
            raise LaneError("abandon requires --operator and --reason")
        from events import append_obj

        append_obj(lane_dir, {"type": "abandoned", "operator": operator, "reason": reason})

    mutate(root, lane_id, "abandon", action, {"operator": operator, "reason": reason})


def cmd_status(root: Path, lane_id: str, *, now=None, gap=None) -> dict:
    _require_id(lane_id)
    lane_dir = root / lane_id
    if not lane_dir.is_dir():
        raise LaneError(f"lane {lane_id} does not exist")
    if not (lane_dir / "events.jsonl").is_file():
        return {
            "lane_id": lane_id,
            "state": "incomplete",
            "display": "incomplete lane directory",
            "reason": None,
            "round": None,
            "opened": 0,
            "budget_max": None,
            "title": "",
            "unconfirmed": [],
            "overdue": False,
            "driver": False,
            "needs": None,
        }
    snap = read_snapshot(lane_dir, gap=gap)
    if not snap.stable:
        return {
            "lane_id": lane_id,
            "state": "changing",
            "display": "changing",
            "reason": None,
            "round": None,
            "opened": 0,
            "budget_max": None,
            "title": "",
            "unconfirmed": [],
            "overdue": False,
            "driver": False,
            "marker": None,
            "busy": None,
        }
    from events import load_bytes

    log = load_bytes(snap.data)
    view = inspect_lane(lane_dir, driver=snap.driver, now=now, log=log)
    view["lane_id"] = lane_id
    if snap.lock_held and snap.lock_label:
        view["busy"] = snap.lock_label.get("command")
    return view


def queue_row(view: dict) -> dict | None:
    state = view.get("state")
    if state in (None, "incomplete"):
        return None
    unconfirmed = list(view.get("unconfirmed") or [])
    if view.get("driver") and view.get("attempt"):
        unconfirmed = [item for item in unconfirmed if item != view["attempt"]]
    why: list[str] = []
    needs: set[str] = set()
    if state == "over_budget":
        why.append("over budget")
        needs.add("owner")
    elif state in ("unknown", "start_ambiguous"):
        why.append(view.get("reason") or state)
        needs.add("person")
    elif state == "verdict_pending":
        why.append("verdict pending")
        needs.add("coordinator")
    elif state in NEGATIVE:
        why.append("round closed")
        needs.add("coordinator")
    elif state == "ready":
        why.append("ready")
        needs.add("coordinator")
    elif state == "abandoned":
        why.append("abandoned")
    elif state == "changing":
        why.append("changing")
        needs.add("person")
    if view.get("overdue"):
        why.append("overdue")
        needs.add("person")
    for attempt in unconfirmed:
        why.append(f"execution not confirmed ended: {attempt}")
        needs.add("person")
    if state == "passed" and "person" not in needs and "owner" not in needs:
        return None
    if state in IN_PROGRESS and not view.get("overdue") and "person" not in needs and "owner" not in needs:
        return None
    if not why:
        return None
    rank = next((name for name in ("owner", "person", "coordinator") if name in needs), None)
    return {
        "id": view.get("lane_id"),
        "title": view.get("title") or "",
        "state": state,
        "round": view.get("round"),
        "budget": f"{view.get('opened')}/{view.get('budget_max')}",
        "why_waiting": why,
        "needs": rank,
        "since": view.get("since"),
    }


def cmd_queue(root: Path) -> tuple[list[dict], int]:
    rows = []
    if root.is_dir():
        for child in sorted(path for path in root.iterdir() if path.is_dir()):
            if not (child / "events.jsonl").is_file():
                continue
            rows.append(queue_row(cmd_status(root, child.name)))
    rows = [row for row in rows if row]
    code = 1 if any(row.get("needs") in ("person", "owner") for row in rows) else 0
    return rows, code


def cmd_pass_set(root: Path, lane_id: str) -> dict:
    view = cmd_status(root, lane_id)
    if view["state"] == "changing":
        raise LaneError("changing")
    if view["state"] == "incomplete":
        raise LaneError("incomplete lane directory")
    if view["state"] != "passed":
        raise LaneError(f"pass-set requires passed, lane is {view['state']}")
    if view.get("evidence_problems"):
        raise LaneError("evidence changed after the verdict")
    repos = {}
    sha_set = view.get("sha_set") or {}
    targets = view.get("targets") or {}
    for name, meta in sha_set.items():
        target = targets.get(name) or {}
        repos[name] = {
            "commit": meta.get("commit"),
            "tree": meta.get("tree"),
            "target_ref": target.get("target_ref"),
            "target_sha": target.get("target_sha"),
        }
    return {
        "lane_id": lane_id,
        "round": view.get("round"),
        "verdict_seq": view.get("verdict_seq"),
        "config_sha256": view.get("config_sha256"),
        "repos": repos,
        "manifests": view.get("manifest_shas") or {},
        "events_head": view.get("events_head"),
    }


def format_status(view: dict) -> str:
    lines = [f"state: {view.get('display') or view.get('state')}"]
    if view.get("reason"):
        lines.append(f"reason: {view['reason']}")
    if view.get("marker"):
        lines.append(f"marker: {view['marker']}")
    if view.get("busy"):
        lines.append(f"busy: {view['busy']}")
    if view.get("overdue"):
        lines.append("overdue: true")
    lines.append(f"round: {view.get('round')}")
    if view.get("budget_max") is not None:
        lines.append(f"budget: {view.get('opened')}/{view.get('budget_max')}")
    if view.get("next_step"):
        lines.append(f"next: {view['next_step']}")
    for note in view.get("notes") or []:
        lines.append(f"note: {note}")
    return "\n".join(lines)


def dumps(obj: object) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"
