#!/usr/bin/env python3
"""Dispatch one lane: implement, verify, review. State lives in files.

A lane directory holds lane.json (rewritten atomically) and events.jsonl (one
state change per line: time, from, to, why). `run` starts the configured
command for the current step, waits, and stops when a person has to decide
(changes requested, over budget, stalled, passed, or failed).

What this does NOT protect against: a process running as the same Unix user
can still edit the lane directory. It stops accidents and a coordinator
quietly extending; the real boundary needs the agents to run as another user
or in a sandbox (ADR §12).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from lane_state import (
    DEFAULT_ROOT,
    PHASES,
    LaneError,
    append_event,
    atomic_write_json,
    budget_limit,
    check_id,
    commit_state,
    config_path_default,
    coordinator_extended,
    extension_lines,
    lane_dir,
    lane_lock,
    load_config,
    load_lane,
    now_iso,
    parse_time,
    refuse_if_step,
    repo_dirs,
    root_path,
    iter_lanes,
)
from lane_steps import (
    current_step,
    drive,
    log_age,
    meta,
    open_step,
    process_gone,
    same_process,
    terminate_group,
)

QUEUE_WHY = {
    "ready": "ready to run",
    "changes_requested": "changes requested",
    "over_budget": "over the round budget",
    "stalled": "stalled; a person has to decide",
    "failed": "failed; a person has to decide",
}


def cmd_new(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    lane_id = check_id(args.id)
    directory = root / lane_id
    if directory.exists():
        raise LaneError(f"lane {lane_id} already exists")
    work = [part.strip() for part in args.work.split(",") if part.strip()]
    if not work:
        raise LaneError("work is empty")
    if args.max_rounds < 1:
        raise LaneError("max-rounds must be at least 1")
    brief = args.brief
    if not Path(brief).expanduser().is_file():
        raise LaneError(f"brief not found: {brief}")
    stamp = now_iso()
    lane = {
        "id": lane_id,
        "work": work,
        "title": args.title,
        "repo_dirs": repo_dirs(args.workspace),
        "branch": args.branch,
        "brief": brief,
        "round": 1,
        "max_rounds": args.max_rounds,
        "state": "ready",
        "steps": [],
        "verdicts": {},
        "usage": {},
        "created_at": stamp,
        "updated_at": stamp,
    }
    directory.mkdir(parents=True)
    atomic_write_json(directory / "lane.json", lane)
    append_event(directory, None, "ready", "new")
    print(f"{lane_id} ready")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    if args.stall_seconds <= 0:
        raise LaneError("stall-seconds must be positive")
    root = root_path(args.root)
    directory = lane_dir(root, args.id)
    cfg = load_config(Path(args.config))
    with lane_lock(directory, args.id):
        lane = drive(directory, load_lane(directory), cfg, args.stall_seconds)
    print(f"{lane['id']} {lane['state']} round={lane['round']}")
    return 0


def cmd_next_round(args: argparse.Namespace) -> int:
    refuse_if_step()
    if not Path(args.brief).expanduser().is_file():
        raise LaneError(f"brief not found: {args.brief}")
    root = root_path(args.root)
    directory = lane_dir(root, args.id)
    with lane_lock(directory, args.id):
        lane = load_lane(directory)
        if lane["state"] != "changes_requested":
            raise LaneError(f"next-round needs changes_requested, not {lane['state']}")
        if int(lane["round"]) >= budget_limit(lane):
            commit_state(directory, lane, "over_budget", "round budget exhausted")
            raise LaneError(
                f"refusing next round: round {lane['round']} of {budget_limit(lane)}",
                code=2,
            )
        lane["round"] += 1
        lane["brief"] = args.brief
        commit_state(directory, lane, "implementing", "next round")
    print(f"{lane['id']} implementing round={lane['round']}")
    return 0


def _confirm_owner(lane_id: str) -> None:
    if not sys.stdin.isatty():
        raise LaneError("owner extension needs a terminal")
    print("Type the lane id to confirm an owner extension: ", end="", flush=True)
    typed = sys.stdin.readline()
    if typed.strip() != lane_id:
        raise LaneError("owner extension was not confirmed")


def cmd_extend(args: argparse.Namespace) -> int:
    refuse_if_step()
    who = args.by.strip()
    if who not in ("coordinator", "owner"):
        raise LaneError("extend --by accepts only coordinator or owner")
    if not args.reason.strip():
        raise LaneError("extend needs a reason and who allowed it")
    root = root_path(args.root)
    directory = lane_dir(root, args.id)
    with lane_lock(directory, args.id):
        lane = load_lane(directory)
        if lane["state"] != "over_budget":
            raise LaneError(f"extend needs over_budget, not {lane['state']}")
        if who == "coordinator" and coordinator_extended(lane):
            raise LaneError("the coordinator has used its one extension; the Owner decides")
        if who == "owner":
            _confirm_owner(lane["id"])
        lane.setdefault("extensions", []).append({
            "by": who,
            "reason": args.reason,
            "at": now_iso(),
            "round": lane["round"],
        })
        commit_state(directory, lane, "changes_requested", f"extend by {who}: {args.reason}")
    print(f"{lane['id']} changes_requested budget={budget_limit(lane)}")
    return 0


def _end_group(step: dict | None, who: str) -> None:
    if not step or not same_process(step):
        return
    signals = terminate_group(step["pid"])
    step["terminated"] = {"by": who, "signals": signals, "at": now_iso()}
    step["end"] = now_iso()
    step["state"] = "finished"


def cmd_abandon(args: argparse.Namespace) -> int:
    refuse_if_step()
    if not args.reason.strip():
        raise LaneError("abandon needs a reason")
    root = root_path(args.root)
    directory = lane_dir(root, args.id)
    with lane_lock(directory, args.id):
        lane = load_lane(directory)
        if lane["state"] == "passed":
            raise LaneError("refusing to abandon a lane that passed")
        step = open_step(lane)
        killed = bool(step and same_process(step))
        _end_group(step, "abandon")
        lane["abandoned"] = True
        why = f"abandon: {args.reason}"
        if killed:
            why += "; terminated the process group"
        commit_state(directory, lane, "failed", why)
    print(f"{lane['id']} failed")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    who = args.by.strip()
    if not who:
        raise LaneError("stop needs --by")
    root = root_path(args.root)
    directory = lane_dir(root, args.id)
    with lane_lock(directory, args.id):
        lane = load_lane(directory)
        if lane["state"] == "passed":
            raise LaneError("refusing to stop a lane that passed")
        _end_group(open_step(lane), who)
        commit_state(directory, lane, "failed", f"stopped by {who}")
    print(f"{lane['id']} failed")
    return 0


def timing(lane: dict, step: dict | None) -> tuple[float, float | None]:
    now = time.time()
    if step and step.get("start"):
        start = parse_time(step["start"])
        end = parse_time(step["end"]) if step.get("end") else now
        elapsed = max(0.0, end - start)
        growth = log_age(Path(step["log"]), step["start"]) if step.get("log") else None
        return elapsed, growth
    created = parse_time(lane["created_at"]) if lane.get("created_at") else now
    return max(0.0, now - created), None


def short_heads(heads: dict | None) -> str:
    if not heads:
        return "-"
    return ",".join(f"{name}:{sha[:7]}" for name, sha in sorted(heads.items()))


def status_row(lane: dict) -> dict:
    step = current_step(lane)
    elapsed, growth = timing(lane, step)
    gone = process_gone(step)
    notes = extension_lines(lane)
    row = {
        "id": lane["id"],
        "state": "running (process gone)" if gone else lane["state"],
        "round": lane["round"],
        "step": step["name"] if step else None,
        "elapsed": round(elapsed, 1),
        "log_growth": None if growth is None else round(growth, 1),
        "process_gone": gone,
        "verified_heads": lane.get("verified_heads"),
        "heads": short_heads(lane.get("verified_heads")) if "verified_heads" in lane else None,
        "budget": "; ".join(notes) if notes else None,
    }
    return row


def fmt_age(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}s" if value >= 10 else f"{value:.1f}s"


def cmd_status(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    if args.id:
        rows = [status_row(load_lane(lane_dir(root, args.id)))]
    else:
        rows = [status_row(lane) for _, lane in iter_lanes(root)]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            step = row["step"] or "-"
            line = (
                f"{row['id']} state={row['state']} round={row['round']} step={step} "
                f"elapsed={fmt_age(row['elapsed'])} log_growth={fmt_age(row['log_growth'])}"
            )
            if row["heads"] is not None:
                line += f" heads={row['heads']}"
            if row["budget"]:
                line += f"; {row['budget']}"
            print(line)
    if args.check and any(row["process_gone"] for row in rows):
        return 1
    return 0


def board_steps(directory: Path, lane: dict, cfg: dict) -> list[dict]:
    recorded: dict[tuple, dict] = {}
    for step in lane["steps"]:
        recorded[(step["round"], step["name"])] = step
    out = []
    for number in range(1, int(lane["round"]) + 1):
        for name in PHASES:
            attempt = directory / f"round-{number}" / f"{name}-1"
            rec = recorded.get((number, name))
            who, usual, pattern = meta(cfg, name, lane)
            out.append({
                "name": name,
                "who": rec.get("who") if rec else who,
                "progress": rec.get("log") if rec else str(attempt / "log"),
                "done": rec.get("done") if rec else str(attempt / "done"),
                "pattern": pattern,
                "usual_min": usual,
            })
    return out


def cmd_board(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    cfg = load_config(Path(args.config))
    works = []
    for directory, lane in iter_lanes(root):
        work = {
            "title": lane["title"],
            "short": lane["id"],
            "goal": f"{', '.join(lane['work'])}: {lane['title']}",
            "round": lane["round"],
            "steps": board_steps(directory, lane, cfg),
        }
        notes = extension_lines(lane)
        if notes:
            work["budget"] = "; ".join(notes)
        works.append(work)
    print(json.dumps({"works": works}, indent=2, ensure_ascii=False))
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    waiting = []
    for _, lane in iter_lanes(root):
        if lane.get("abandoned") or lane["state"] not in QUEUE_WHY:
            continue
        why = QUEUE_WHY[lane["state"]]
        notes = extension_lines(lane)
        if notes:
            why = why + "; " + "; ".join(notes)
        waiting.append({
            "title": lane["title"],
            "why_waiting": why,
            "needs_owner": lane["state"] == "over_budget" and coordinator_extended(lane),
        })
    print(json.dumps(waiting, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lane.py",
        description="Run implement, verify and review as a file-backed state machine.",
    )
    parser.add_argument("--root", default=DEFAULT_ROOT, help="lanes directory (default %(default)s)")
    parser.add_argument("--config", default=str(config_path_default()), help="command template json")
    sub = parser.add_subparsers(dest="cmd", required=True)

    new = sub.add_parser("new", help="create a lane in the ready state")
    new.add_argument("--id", required=True)
    new.add_argument("--work", required=True, help="W-n or W-n,W-m")
    new.add_argument("--title", required=True)
    new.add_argument("--workspace", required=True)
    new.add_argument("--branch", required=True)
    new.add_argument("--brief", required=True)
    new.add_argument("--max-rounds", type=int, default=2)
    new.set_defaults(func=cmd_new)

    run = sub.add_parser("run", help="drive the lane until it needs a decision")
    run.add_argument("id")
    run.add_argument("--stall-seconds", type=float, default=600)
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="one line per lane")
    status.add_argument("id", nargs="?")
    status.add_argument("--json", action="store_true")
    status.add_argument("--check", action="store_true", help="exit 1 when a running step's process is gone")
    status.set_defaults(func=cmd_status)

    nxt = sub.add_parser("next-round", help="start another round after changes were requested")
    nxt.add_argument("id")
    nxt.add_argument("--brief", required=True)
    nxt.set_defaults(func=cmd_next_round)

    extend = sub.add_parser("extend", help="allow exactly one more round past the budget")
    extend.add_argument("id")
    extend.add_argument("--reason", required=True)
    extend.add_argument("--by", required=True, help="coordinator (once per lane) or owner (a terminal)")
    extend.set_defaults(func=cmd_extend)

    abandon = sub.add_parser("abandon", help="stop a lane and record why")
    abandon.add_argument("id")
    abandon.add_argument("--reason", required=True)
    abandon.set_defaults(func=cmd_abandon)

    stop = sub.add_parser("stop", help="end the step's process group and mark the lane failed")
    stop.add_argument("id")
    stop.add_argument("--by", required=True)
    stop.set_defaults(func=cmd_stop)

    board = sub.add_parser("board", help="print the works/steps structure for the progress board")
    board.set_defaults(func=cmd_board)
    queue = sub.add_parser("queue", help="list lanes that are waiting and not running")
    queue.set_defaults(func=cmd_queue)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except LaneError as exc:
        print(exc, file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
