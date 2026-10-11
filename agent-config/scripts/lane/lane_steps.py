"""One attempt of implement, verify, or review, and how its result is judged."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from lane_state import (
    atomic_write_json,
    commit_state,
    now_iso,
    render_argv,
    render_text,
    within_budget,
)

DRIVING = {"ready", "implementing", "verifying", "reviewing"}
PHASE_OF = {"implementing": "implement", "verifying": "verify", "reviewing": "review"}
DEFAULT_WHO = {"implement": "Cursor", "verify": "verify-branch.sh", "review": "Codex"}
DEFAULT_USUAL = {"implement": 30, "verify": 8, "review": 10}
DEFAULT_PATTERN = {"implement": "cursor-agent", "verify": "verify-branch.sh", "review": "codex exec"}
TOKENS_RE = re.compile(r"tokens used\s*\n?\s*([\d,]+)", re.I)
PASS_LINE = "VERDICT: pass"
REVIEW_OK = ("VERDICT: safe to merge", "VERDICT: fix first")
END_LINE = "END OF REPORT"
MOVED_VERIFY = "the branch moved during verification"
MOVED_REVIEW = "the branch moved during review"
REVIEW_HEADS = "review needs a passing verify for the current heads"
START_ABORTED = "stopped while starting; check for a stray process"
VANISHED = "process vanished without an exit record"
RUNNER = Path(__file__).resolve().parent / "lane_runner.py"
TERM_WAIT_SECONDS = 5.0


def pid_alive(pid: object) -> bool:
    if type(pid) is not int or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_lstart(pid: int) -> str:
    proc = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True, text=True,
    )
    return proc.stdout.strip()


def same_process(step: dict) -> bool:
    pid = step.get("pid")
    if not pid_alive(pid):
        return False
    return process_lstart(pid) == (step.get("lstart") or "")


def terminate_group(pid: int, wait_s: float = TERM_WAIT_SECONDS) -> list[str]:
    """TERM the process group, wait, then KILL. Returns the signals that were sent."""
    if type(pid) is not int or pid <= 1:
        return []
    sent: list[str] = []
    try:
        os.killpg(pid, signal.SIGTERM)
        sent.append("TERM")
    except ProcessLookupError:
        return sent
    except PermissionError:
        try:
            os.kill(pid, signal.SIGTERM)
            sent.append("TERM")
        except ProcessLookupError:
            return sent
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if not pid_alive(pid):
            return sent
        time.sleep(0.05)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return sent
    except PermissionError:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return sent
    sent.append("KILL")
    kill_deadline = time.time() + 1
    while time.time() < kill_deadline and pid_alive(pid):
        time.sleep(0.05)
    return sent


def log_age(path: Path, started: str) -> float:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        from lane_state import parse_time
        stamp = parse_time(started)
    return max(0.0, time.time() - stamp)


def poll_interval(stall_seconds: float) -> float:
    return min(1.0, max(0.05, stall_seconds / 20))


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_report(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_done(path: Path) -> int | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(doc, dict) and type(doc.get("exit")) is int:
        return doc["exit"]
    return None


def last_nonempty(text: str) -> str | None:
    found = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            found = stripped
    return found


def nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def git_repos(workspace: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []
    if not workspace.is_dir():
        return found
    if (workspace / ".git").exists():
        found.append((workspace.name, workspace))
    for child in sorted(p for p in workspace.iterdir() if p.is_dir()):
        if (child / ".git").exists():
            found.append((child.name, child))
    return found


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, env=git_env(),
    )


def first_dirty(workspace: Path) -> str | None:
    for name, repo in git_repos(workspace):
        status = _git(repo, "status", "--porcelain", "--untracked-files=no")
        if status.returncode != 0 or status.stdout.strip():
            return name
        head = _git(repo, "rev-parse", "HEAD")
        if head.returncode != 0 or not head.stdout.strip():
            return name
    return None


def read_heads(workspace: Path) -> dict[str, str]:
    heads: dict[str, str] = {}
    for name, repo in git_repos(workspace):
        head = _git(repo, "rev-parse", "HEAD")
        if head.returncode == 0 and head.stdout.strip():
            heads[name] = head.stdout.strip()
    return heads


def workspace_of(lane: dict) -> Path:
    return Path(str(lane.get("repo_dirs", {}).get("workspace", "")))


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
            if type(raw.get(key)) is int:
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


def record_verdict(lane: dict, step: dict, verdict: str | None, exit_code: int) -> None:
    entry = {
        "round": step.get("round"),
        "step": step.get("name"),
        "attempt": step.get("attempt"),
        "verdict": verdict,
        "heads": step.get("heads"),
        "exit": exit_code,
        "at": now_iso(),
    }
    lane.setdefault("verdicts", {}).setdefault("entries", []).append(entry)


def passing_verify(lane: dict) -> dict | None:
    found = None
    for entry in lane.get("verdicts", {}).get("entries") or []:
        if (
            entry.get("round") == lane.get("round")
            and entry.get("step") == "verify"
            and entry.get("verdict") == PASS_LINE
            and entry.get("exit") == 0
        ):
            found = entry
    return found


def open_step(lane: dict) -> dict | None:
    for step in reversed(lane["steps"]):
        if step.get("end") is None:
            return step
    return None


def current_step(lane: dict) -> dict | None:
    for step in reversed(lane["steps"]):
        if step.get("end") is None:
            return step
    return lane["steps"][-1] if lane["steps"] else None


def process_gone(step: dict | None) -> bool:
    if not step or step.get("end") is not None or step.get("state") != "running":
        return False
    done = step.get("done")
    if done and read_done(Path(done)) is not None:
        return False
    if not pid_alive(step.get("pid")):
        return True
    return process_lstart(step["pid"]) != (step.get("lstart") or "")


def meta(cfg: dict, name: str, lane: dict) -> tuple[str, int, str]:
    who = (cfg.get("who") or {}).get(name) or DEFAULT_WHO[name]
    usual = int((cfg.get("usual_min") or {}).get(name, DEFAULT_USUAL[name]))
    pattern = (cfg.get("pattern") or {}).get(name) or DEFAULT_PATTERN[name]
    values = placeholders(lane, "")
    return who, usual, render_text(pattern, **values)


def placeholders(lane: dict, report: Path | str) -> dict:
    return {
        "workspace": lane.get("repo_dirs", {}).get("workspace", ""),
        "brief": lane.get("brief", ""),
        "round": lane.get("round"),
        "report": str(report),
        "id": lane.get("id", ""),
    }


def allocate_attempt(directory: Path, round_n: int, name: str) -> tuple[int, Path]:
    folder = directory / f"round-{round_n}"
    folder.mkdir(parents=True, exist_ok=True)
    number = 1
    while True:
        attempt = folder / f"{name}-{number}"
        try:
            attempt.mkdir()
        except FileExistsError:
            number += 1
            continue
        return number, attempt


def capture_lstart(pid: int) -> str:
    for _ in range(10):
        if not pid_alive(pid):
            return ""
        stamp = process_lstart(pid)
        if stamp:
            return stamp
        time.sleep(0.02)
    return process_lstart(pid) if pid_alive(pid) else ""


def start_step(directory: Path, lane: dict, cfg: dict, name: str, heads: dict | None) -> tuple[dict, subprocess.Popen]:
    number, attempt = allocate_attempt(directory, int(lane["round"]), name)
    log_path = attempt / "log"
    done_path = attempt / "done"
    report_path = attempt / "report"
    who, _, _ = meta(cfg, name, lane)
    step = {
        "name": name,
        "round": lane["round"],
        "attempt": number,
        "state": "starting",
        "who": who,
        "start": now_iso(),
        "end": None,
        "pid": None,
        "lstart": None,
        "exit": None,
        "log": str(log_path),
        "done": str(done_path),
        "report": str(report_path),
        "heads": heads,
    }
    lane["steps"].append(step)
    lane["updated_at"] = now_iso()
    atomic_write_json(directory / "lane.json", lane)
    argv = render_argv(list(cfg[name]), **placeholders(lane, report_path))
    env = os.environ.copy()
    env["LANE_STEP"] = f"{lane['id']}/{name}"
    workspace = workspace_of(lane)
    cwd = str(workspace) if workspace.is_dir() else None
    fh = log_path.open("wb", buffering=0)
    try:
        proc = subprocess.Popen(
            [sys.executable, str(RUNNER), str(done_path), "--", *argv],
            stdout=fh,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            env=env,
            start_new_session=True,
            shell=False,
        )
    finally:
        fh.close()
    step["pid"] = proc.pid
    step["lstart"] = capture_lstart(proc.pid)
    step["state"] = "running"
    lane["updated_at"] = now_iso()
    atomic_write_json(directory / "lane.json", lane)
    return step, proc


def wait_child(proc: subprocess.Popen, step: dict, stall_seconds: float) -> tuple[str, int | None]:
    interval = poll_interval(stall_seconds)
    log_path = Path(step["log"])
    while True:
        try:
            rc = proc.wait(timeout=interval)
        except subprocess.TimeoutExpired:
            if log_age(log_path, step["start"]) >= stall_seconds:
                return "stalled", None
            continue
        code = read_done(Path(step["done"]))
        if code is None:
            return "vanished", None
        return "exited", code if code is not None else rc


def wait_pid(step: dict, stall_seconds: float) -> tuple[str, int | None]:
    interval = poll_interval(stall_seconds)
    log_path = Path(step["log"])
    pid = step.get("pid")
    while True:
        code = read_done(Path(step["done"]))
        if code is not None:
            return "exited", code
        if not pid_alive(pid) or process_lstart(pid) != (step.get("lstart") or ""):
            code = read_done(Path(step["done"]))
            if code is not None:
                return "exited", code
            return "vanished", None
        if log_age(log_path, step["start"]) >= stall_seconds:
            return "stalled", None
        time.sleep(interval)


def classify(step: dict) -> tuple[str, int | None]:
    code = read_done(Path(step["done"])) if step.get("done") else None
    if code is not None:
        return "exited", code
    if step.get("state") == "starting" and not step.get("pid"):
        return "aborted", None
    if same_process(step):
        return "alive", None
    return "vanished", None


def resume_step(step: dict, stall_seconds: float) -> tuple[str, int | None]:
    kind, code = classify(step)
    if kind == "alive":
        return wait_pid(step, stall_seconds)
    return kind, code


def gate(lane: dict, name: str) -> tuple[str | None, dict | None]:
    workspace = workspace_of(lane)
    if name == "verify":
        dirty = first_dirty(workspace)
        if dirty:
            return f"uncommitted changes in {dirty}", None
        return None, read_heads(workspace)
    if name == "review":
        current = read_heads(workspace)
        entry = passing_verify(lane)
        if entry is None or entry.get("heads") != current:
            return REVIEW_HEADS, None
        return None, current
    return None, None


def judge(name: str, code: int, log_text: str, report_text: str, heads_moved: bool) -> tuple[str, str, str | None]:
    if name == "implement":
        if code != 0:
            return "failed", f"implement exited {code}", None
        return "verifying", "implement exited 0", None
    if name == "verify":
        last = last_nonempty(log_text)
        shown = last if last and last.startswith("VERDICT:") else None
        if code != 0:
            return "failed", f"verify exited {code}", shown
        if heads_moved:
            return "failed", MOVED_VERIFY, shown
        if last == PASS_LINE:
            return "reviewing", last, last
        if shown:
            return "failed", shown, shown
        return "failed", "verification produced no verdict", None
    lines = nonempty_lines(report_text)
    first = lines[0] if lines else ""
    last = lines[-1] if lines else ""
    shown = first if first.startswith("VERDICT:") else None
    if code != 0:
        return "failed", f"review exited {code}", shown
    if heads_moved:
        return "failed", MOVED_REVIEW, shown
    if first in REVIEW_OK and last == END_LINE:
        if first == "VERDICT: safe to merge":
            return "passed", first, first
        return "changes_requested", first, first
    return "failed", "review produced no verdict", shown


def close_step(directory: Path, lane: dict, step: dict, new_state: str, why: str, code: int | None) -> None:
    step["end"] = now_iso()
    step["state"] = "finished"
    if code is not None:
        step["exit"] = code
    commit_state(directory, lane, new_state, why)


def apply_exit(directory: Path, lane: dict, step: dict, code: int) -> None:
    name = step["name"]
    log_text = read_text(Path(step["log"])) if step.get("log") else ""
    add_usage(lane, step, parse_usage(log_text))
    report_text = read_report(Path(step["report"])) if name == "review" and step.get("report") else ""
    heads_moved = False
    fresh: dict[str, str] = {}
    if name in ("verify", "review"):
        fresh = read_heads(workspace_of(lane))
        bound = step.get("heads")
        if not isinstance(bound, dict):
            bound = {}
        heads_moved = fresh != bound
    new_state, why, shown = judge(name, code, log_text, report_text, heads_moved)
    if name == "verify":
        round_bucket(lane)["verify"] = shown
        record_verdict(lane, step, shown, code)
    elif name == "review":
        if code == 0:
            label = None
            if new_state == "passed":
                label = "safe to merge"
            elif new_state == "changes_requested":
                label = "fix first"
            add_marks(lane, count_marks(report_text), review=label)
        record_verdict(lane, step, shown, code)
    if new_state == "passed":
        lane["verified_heads"] = fresh
    close_step(directory, lane, step, new_state, why, code)


def drive(directory: Path, lane: dict, cfg: dict, stall_seconds: float) -> dict:
    if lane["state"] not in DRIVING and lane["state"] != "stalled":
        return lane
    while lane["state"] in DRIVING or lane["state"] == "stalled":
        if lane["state"] == "ready":
            if not within_budget(lane):
                commit_state(directory, lane, "over_budget", "round budget exhausted")
                return lane
            commit_state(directory, lane, "implementing", "run")
        step = open_step(lane)
        if step is None:
            name = PHASE_OF.get(lane["state"])
            if name is None:
                commit_state(directory, lane, "failed", "stalled without a step")
                return lane
            if name == "implement" and not within_budget(lane):
                commit_state(directory, lane, "over_budget", "round budget exhausted")
                return lane
            why, heads = gate(lane, name)
            if why:
                commit_state(directory, lane, "failed", why)
                return lane
            step, proc = start_step(directory, lane, cfg, name, heads)
            kind, code = wait_child(proc, step, stall_seconds)
        else:
            kind, code = resume_step(step, stall_seconds)
        if kind == "stalled":
            commit_state(directory, lane, "stalled", f"no log growth for {stall_seconds:g}s")
            return lane
        if kind == "vanished":
            step["vanished"] = True
            close_step(directory, lane, step, "failed", VANISHED, None)
            return lane
        if kind == "aborted":
            close_step(directory, lane, step, "failed", START_ABORTED, None)
            return lane
        apply_exit(directory, lane, step, int(code))
    return lane
