#!/usr/bin/env python3
"""Dispatch one lane: implement, verify, review. State lives in files.

A lane directory holds lane.json (rewritten atomically) and events.jsonl (one
state change per line: time, from, to, why). `run` starts the configured
command for the current step, waits, and stops when a person has to decide
(changes requested, over budget, stalled, passed, or failed).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = "~/agent-work/lanes"
PHASES = ("implement", "verify", "review")
DRIVING = {"ready", "implementing", "verifying", "reviewing"}
PHASE_OF = {"implementing": "implement", "verifying": "verify", "reviewing": "review"}
DEFAULT_WHO = {"implement": "Cursor", "verify": "verify-branch.sh", "review": "Codex"}
DEFAULT_USUAL = {"implement": 30, "verify": 8, "review": 10}
DEFAULT_PATTERN = {"implement": "cursor-agent", "verify": "verify-branch.sh", "review": "codex exec"}
VERIFY_RE = re.compile(r"^VERDICT: (pass|FAIL.*)$")
TOKENS_RE = re.compile(r"tokens used\s*\n?\s*([\d,]+)", re.I)
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
REQUIRED = (
    "id", "work", "title", "repo_dirs", "branch", "brief", "round", "max_rounds",
    "state", "steps", "verdicts", "usage", "created_at", "updated_at",
)


class LaneError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def atomic_write_json(path: Path, doc: dict) -> None:
    """Write JSON via a temp file in the same directory, then rename.

    A crash between the temp write and the rename leaves the previous file
    in place. The temp file stays behind so the new bytes are visible.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def append_event(directory: Path, old, new: str, why: str) -> None:
    rec = {"time": now_iso(), "from": old, "to": new, "why": why}
    with (directory / "events.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def commit_state(directory: Path, lane: dict, new: str, why: str) -> None:
    old = lane["state"]
    lane["state"] = new
    lane["updated_at"] = now_iso()
    atomic_write_json(directory / "lane.json", lane)
    if old != new:
        append_event(directory, old, new, why)


def config_path_default() -> Path:
    return Path(__file__).resolve().parent / "lane-config.json"


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise LaneError(f"missing config {path}")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LaneError(f"config is not json: {exc}") from exc
    for key in PHASES:
        if not isinstance(cfg.get(key), str) or not cfg[key].strip():
            raise LaneError(f"config missing command for {key}")
    return cfg


def render(template: str, **values: object) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def root_path(text: str) -> Path:
    return Path(text).expanduser().resolve()


def check_id(lane_id: str) -> str:
    if not ID_RE.fullmatch(lane_id):
        raise LaneError("lane id must be one path segment")
    return lane_id


def lane_paths(root: Path, lane_id: str) -> Path:
    directory = root / check_id(lane_id)
    if not (directory / "lane.json").is_file():
        raise LaneError(f"no lane {lane_id}")
    return directory


def load_lane(directory: Path) -> dict:
    try:
        lane = json.loads((directory / "lane.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LaneError(f"unreadable lane.json: {exc}") from exc
    missing = [key for key in REQUIRED if key not in lane]
    if missing:
        raise LaneError(f"lane.json missing {', '.join(missing)}")
    return lane


def iter_lanes(root: Path) -> list[tuple[Path, dict]]:
    found: list[tuple[Path, dict]] = []
    if not root.is_dir():
        return found
    for child in sorted(root.iterdir()):
        path = child / "lane.json"
        if not path.is_file():
            continue
        try:
            found.append((child, json.loads(path.read_text(encoding="utf-8"))))
        except json.JSONDecodeError:
            print(f"skipping unreadable {path}", file=sys.stderr)
    found.sort(key=lambda item: item[1].get("created_at") or "")
    return found


def repo_dirs(workspace: str) -> dict:
    root = Path(workspace).expanduser()
    out = {"workspace": str(root)}
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / ".git").exists():
                out[child.name] = str(child)
    return out


def artifact_paths(directory: Path, round_n: int, name: str) -> tuple[Path, Path, Path, Path]:
    folder = directory / f"round-{round_n}"
    return folder, folder / f"{name}.log", folder / f"{name}.done", folder / "review-report.txt"


def pid_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def log_age(path: Path, started: str) -> float:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        stamp = parse_time(started)
    return max(0.0, time.time() - stamp)


def poll_interval(stall_seconds: float) -> float:
    return min(1.0, max(0.05, stall_seconds / 20))


def wait_child(proc: subprocess.Popen, log_path: Path, started: str, stall_seconds: float) -> tuple[str, int | None]:
    """Return as soon as the child exits. Wake on the stall interval only while it is alive."""
    interval = poll_interval(stall_seconds)
    while True:
        try:
            return "exited", proc.wait(timeout=interval)
        except subprocess.TimeoutExpired:
            pass
        if not pid_alive(proc.pid):
            return "vanished", None
        if log_age(log_path, started) >= stall_seconds:
            return "stalled", None


def wait_pid(pid: int, log_path: Path, started: str, stall_seconds: float) -> tuple[str, int | None]:
    interval = poll_interval(stall_seconds)
    while True:
        if not pid_alive(pid):
            return "vanished", None
        if log_age(log_path, started) >= stall_seconds:
            return "stalled", None
        time.sleep(interval)


def open_step(lane: dict) -> dict | None:
    for step in reversed(lane["steps"]):
        if step.get("end") is None and step.get("pid"):
            return step
    return None


def last_verify_line(text: str) -> str | None:
    found = None
    for line in text.splitlines():
        stripped = line.strip()
        if VERIFY_RE.match(stripped):
            found = stripped
    return found


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def parse_usage(text: str) -> dict:
    usage: dict = {}
    result = None
    for line in text.splitlines():
        if '"type"' not in line or "result" not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            result = obj
    if isinstance(result, dict) and isinstance(result.get("usage"), dict):
        raw = result["usage"]
        for key in ("inputTokens", "outputTokens"):
            if isinstance(raw.get(key), int):
                usage[key] = raw[key]
    match = TOKENS_RE.search(text)
    if match:
        usage["tokens"] = int(match.group(1).replace(",", ""))
    return usage


def add_usage(lane: dict, step: dict, usage: dict) -> None:
    if not usage or step.get("usage"):
        return
    step["usage"] = usage
    total = lane.setdefault("usage", {})
    for key, value in usage.items():
        total[key] = total.get(key, 0) + value


def count_marks(text: str) -> dict:
    return {name: len(re.findall(rf"\b{name}\b", text)) for name in ("P1", "P2", "P3")}


def round_bucket(lane: dict) -> dict:
    verdicts = lane.setdefault("verdicts", {})
    rounds = verdicts.setdefault("rounds", [])
    for bucket in rounds:
        if bucket.get("round") == lane["round"]:
            return bucket
    bucket = {"round": lane["round"]}
    rounds.append(bucket)
    return bucket


def add_marks(lane: dict, marks: dict, **fields: object) -> None:
    verdicts = lane.setdefault("verdicts", {})
    bucket = round_bucket(lane)
    for name, count in marks.items():
        verdicts[name] = verdicts.get(name, 0) + count
        bucket[name] = count
    bucket.update(fields)


def write_done(path: Path, code: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"exit={code}\n", encoding="utf-8")


def placeholders(lane: dict, report: Path) -> dict:
    workspace = lane["repo_dirs"].get("workspace", "")
    return {
        "workspace": workspace,
        "brief": lane["brief"],
        "round": lane["round"],
        "report": str(report),
        "id": lane["id"],
    }


def meta(cfg: dict, name: str, lane: dict) -> tuple[str, int, str]:
    who = (cfg.get("who") or {}).get(name) or DEFAULT_WHO[name]
    usual = int((cfg.get("usual_min") or {}).get(name, DEFAULT_USUAL[name]))
    pattern = (cfg.get("pattern") or {}).get(name) or DEFAULT_PATTERN[name]
    workspace = lane["repo_dirs"].get("workspace", "")
    pattern = render(pattern, id=lane["id"], workspace=workspace, round=lane["round"], brief=lane["brief"], report="")
    return who, usual, pattern


def start_step(directory: Path, lane: dict, cfg: dict, name: str) -> tuple[dict, subprocess.Popen]:
    folder, log_path, done_path, report = artifact_paths(directory, lane["round"], name)
    folder.mkdir(parents=True, exist_ok=True)
    command = render(cfg[name], **placeholders(lane, report))
    who, _, _ = meta(cfg, name, lane)
    fh = log_path.open("ab", buffering=0)
    workspace = Path(str(lane["repo_dirs"].get("workspace", "")))
    cwd = str(workspace) if workspace.is_dir() else None
    try:
        proc = subprocess.Popen(
            ["sh", "-c", command],
            stdout=fh,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            start_new_session=True,
        )
    finally:
        fh.close()
    step = {
        "name": name,
        "round": lane["round"],
        "who": who,
        "start": now_iso(),
        "end": None,
        "pid": proc.pid,
        "exit": None,
        "log": str(log_path),
        "done": str(done_path),
    }
    lane["steps"].append(step)
    lane["updated_at"] = now_iso()
    atomic_write_json(directory / "lane.json", lane)
    return step, proc


def outcome_after_exit(lane: dict, step: dict, code: int, log_text: str, report_text: str) -> tuple[str, str]:
    name = step["name"]
    if name == "implement":
        if code != 0:
            return "failed", f"implement exited {code}"
        return "verifying", "implement exited 0"
    if name == "verify":
        verdict = last_verify_line(log_text)
        round_bucket(lane)["verify"] = verdict
        if verdict is None:
            return "failed", "verification produced no verdict"
        if verdict == "VERDICT: pass":
            return "reviewing", verdict
        return "failed", verdict
    line = report_text.splitlines()[0].strip() if report_text.strip() else ""
    marks = count_marks(report_text)
    if line == "VERDICT: safe to merge":
        add_marks(lane, marks, review="safe to merge")
        return "passed", line
    if line == "VERDICT: fix first":
        add_marks(lane, marks, review="fix first")
        return "changes_requested", line
    add_marks(lane, marks, review=None)
    return "failed", "review produced no verdict"


def finish_step(directory: Path, lane: dict, step: dict, code: int | None, why_state: str, why: str) -> None:
    step["end"] = now_iso()
    if code is not None:
        step["exit"] = code
        write_done(Path(step["done"]), code)
    elif why_state == "failed":
        write_done(Path(step["done"]), 1)
    commit_state(directory, lane, why_state, why)


def drive(directory: Path, lane: dict, cfg: dict, stall_seconds: float) -> dict:
    if lane["state"] not in DRIVING:
        return lane
    while lane["state"] in DRIVING:
        if lane["state"] == "ready":
            commit_state(directory, lane, "implementing", "run")
        name = PHASE_OF[lane["state"]]
        step = open_step(lane)
        if step is None:
            step, proc = start_step(directory, lane, cfg, name)
            kind, code = wait_child(proc, Path(step["log"]), step["start"], stall_seconds)
        else:
            kind, code = wait_pid(int(step["pid"]), Path(step["log"]), step["start"], stall_seconds)
        if kind == "stalled":
            commit_state(directory, lane, "stalled", f"no log growth for {stall_seconds:g}s")
            return lane
        if kind == "vanished":
            step["vanished"] = True
            finish_step(directory, lane, step, None, "failed", "process vanished without an exit record")
            return lane
        log_text = read_text(Path(step["log"]))
        add_usage(lane, step, parse_usage(log_text))
        _, _, _, report = artifact_paths(directory, step["round"], step["name"])
        report_text = read_text(report) if step["name"] == "review" else ""
        new_state, why = outcome_after_exit(lane, step, int(code), log_text, report_text)
        finish_step(directory, lane, step, int(code), new_state, why)
    return lane


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
    directory = lane_paths(root, args.id)
    cfg = load_config(Path(args.config))
    lane = drive(directory, load_lane(directory), cfg, args.stall_seconds)
    print(f"{lane['id']} {lane['state']} round={lane['round']}")
    return 0


def cmd_next_round(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    directory = lane_paths(root, args.id)
    lane = load_lane(directory)
    if lane["state"] != "changes_requested":
        raise LaneError(f"next-round needs changes_requested, not {lane['state']}")
    if not Path(args.brief).expanduser().is_file():
        raise LaneError(f"brief not found: {args.brief}")
    if lane["round"] >= lane["max_rounds"]:
        commit_state(directory, lane, "over_budget", "round budget exhausted")
        raise LaneError(
            f"refusing next round: round {lane['round']} of {lane['max_rounds']}",
            code=2,
        )
    lane["round"] += 1
    lane["brief"] = args.brief
    commit_state(directory, lane, "implementing", "next round")
    print(f"{lane['id']} implementing round={lane['round']}")
    return 0


def cmd_extend(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    directory = lane_paths(root, args.id)
    lane = load_lane(directory)
    if lane["state"] != "over_budget":
        raise LaneError(f"extend needs over_budget, not {lane['state']}")
    if not args.reason.strip() or not args.by.strip():
        raise LaneError("extend needs a reason and who allowed it")
    lane.setdefault("extensions", []).append({
        "by": args.by,
        "reason": args.reason,
        "at": now_iso(),
        "round": lane["round"],
    })
    lane["max_rounds"] = lane["round"] + 1
    commit_state(directory, lane, "changes_requested", f"extend by {args.by}: {args.reason}")
    print(f"{lane['id']} changes_requested max_rounds={lane['max_rounds']}")
    return 0


def cmd_abandon(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    directory = lane_paths(root, args.id)
    lane = load_lane(directory)
    if lane["state"] == "passed":
        raise LaneError("refusing to abandon a lane that passed")
    if not args.reason.strip():
        raise LaneError("abandon needs a reason")
    commit_state(directory, lane, "failed", f"abandon: {args.reason}")
    print(f"{lane['id']} failed")
    return 0


def current_step(lane: dict) -> dict | None:
    for step in reversed(lane["steps"]):
        if step.get("end") is None:
            return step
    return lane["steps"][-1] if lane["steps"] else None


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


def status_row(lane: dict) -> dict:
    step = current_step(lane)
    elapsed, growth = timing(lane, step)
    return {
        "id": lane["id"],
        "state": lane["state"],
        "round": lane["round"],
        "step": step["name"] if step else None,
        "elapsed": round(elapsed, 1),
        "log_growth": None if growth is None else round(growth, 1),
    }


def fmt_age(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.0f}s" if value >= 10 else f"{value:.1f}s"


def cmd_status(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    if args.id:
        rows = [status_row(load_lane(lane_paths(root, args.id)))]
    else:
        rows = [status_row(lane) for _, lane in iter_lanes(root)]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0
    for row in rows:
        step = row["step"] or "-"
        print(
            f"{row['id']} state={row['state']} round={row['round']} step={step} "
            f"elapsed={fmt_age(row['elapsed'])} log_growth={fmt_age(row['log_growth'])}"
        )
    return 0


def board_steps(directory: Path, lane: dict, cfg: dict) -> list[dict]:
    recorded = {(step["round"], step["name"]): step for step in lane["steps"]}
    out = []
    for number in range(1, int(lane["round"]) + 1):
        for name in PHASES:
            _, log_path, done_path, _ = artifact_paths(directory, number, name)
            rec = recorded.get((number, name))
            who, usual, pattern = meta(cfg, name, lane)
            out.append({
                "name": name,
                "who": rec.get("who") if rec else who,
                "progress": rec.get("log") if rec else str(log_path),
                "done": rec.get("done") if rec else str(done_path),
                "pattern": pattern,
                "usual_min": usual,
            })
    return out


def cmd_board(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    cfg = load_config(Path(args.config))
    works = []
    for directory, lane in iter_lanes(root):
        works.append({
            "title": lane["title"],
            "short": lane["id"],
            "goal": f"{', '.join(lane['work'])}: {lane['title']}",
            "round": lane["round"],
            "steps": board_steps(directory, lane, cfg),
        })
    print(json.dumps({"works": works}, indent=2, ensure_ascii=False))
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    root = root_path(args.root)
    waiting = []
    for _, lane in iter_lanes(root):
        if lane["state"] == "ready":
            why, needs = "ready to run", False
        elif lane["state"] == "changes_requested":
            why, needs = "changes requested", False
        else:
            continue
        waiting.append({"title": lane["title"], "why_waiting": why, "needs_owner": needs})
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
    status.set_defaults(func=cmd_status)

    nxt = sub.add_parser("next-round", help="start another round after changes were requested")
    nxt.add_argument("id")
    nxt.add_argument("--brief", required=True)
    nxt.set_defaults(func=cmd_next_round)

    extend = sub.add_parser("extend", help="allow exactly one more round past the budget")
    extend.add_argument("id")
    extend.add_argument("--reason", required=True)
    extend.add_argument("--by", required=True)
    extend.set_defaults(func=cmd_extend)

    abandon = sub.add_parser("abandon", help="stop a lane and record why")
    abandon.add_argument("id")
    abandon.add_argument("--reason", required=True)
    abandon.set_defaults(func=cmd_abandon)

    board = sub.add_parser("board", help="print the works/steps structure for the progress board")
    board.set_defaults(func=cmd_board)
    queue = sub.add_parser("queue", help="list lanes waiting to run or for another round")
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
