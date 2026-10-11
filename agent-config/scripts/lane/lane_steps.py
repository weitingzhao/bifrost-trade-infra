"""One attempt of implement, verify, or review, and how its result is judged.

A step runs only while the `run` that started it is still alive. A later `run`
does not attach to that child. It ends the recorded process group and fails
the lane. The exit code is the value `proc.wait()` returns. `done` is written
afterwards for the board and is never read back to decide.
"""
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
    LaneError,
    atomic_write_json,
    commit_state,
    now_iso,
    render_argv,
    render_text,
    within_budget,
)

DRIVING = {"ready", "implementing", "verifying", "reviewing"}
PHASE_OF = {"implementing": "implement", "verifying": "verify", "reviewing": "review"}
PHASE_STATE = {"implement": "implementing", "verify": "verifying", "review": "reviewing"}
DEFAULT_WHO = {"implement": "Cursor", "verify": "verify-branch.sh", "review": "Codex"}
DEFAULT_USUAL = {"implement": 30, "verify": 8, "review": 10}
DEFAULT_PATTERN = {"implement": "cursor-agent", "verify": "verify-branch.sh", "review": "codex exec"}
TOKENS_RE = re.compile(r"tokens used\s*\n?\s*([\d,]+)", re.I)
PASS_LINE = "VERDICT: pass"
REVIEW_OK = ("VERDICT: safe to merge", "VERDICT: fix first")
END_LINE = "END OF REPORT"
REVIEW_HEADS = "review needs a passing verify for the current heads"
RUNNER = Path(__file__).resolve().parent / "lane_runner.py"
GROUP_WAIT_SECONDS = 5.0
REGISTER_SECONDS = 5.0
REQUEST_NAME = "stop-request.json"


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


def _pgid(value: object) -> int | None:
    if type(value) is not int or value <= 1:
        return None
    return value


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_group_gone(pgid: int, seconds: float, reap) -> bool:
    deadline = time.time() + seconds
    while True:
        if reap is not None:
            reap()
        if not group_alive(pgid):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.05)


def end_group(pgid: object, wait_s: float = GROUP_WAIT_SECONDS, *, reap=None) -> bool:
    """TERM the group, poll, then KILL and poll again. True when the group is gone.

    The leader being dead already is not a reason to skip the group: a
    grandchild may still be in it. ``reap``, when given, collects the leader
    zombie; otherwise ``killpg`` still reports the group as alive. ``reaped``
    is false when members survive KILL.
    """
    number = _pgid(pgid)
    if number is None:
        return True
    try:
        os.killpg(number, signal.SIGTERM)
    except ProcessLookupError:
        if reap is not None:
            reap()
        return True
    except PermissionError:
        pass
    if _wait_group_gone(number, wait_s, reap):
        return True
    try:
        os.killpg(number, signal.SIGKILL)
    except ProcessLookupError:
        if reap is not None:
            reap()
        return True
    except PermissionError:
        pass
    return _wait_group_gone(number, wait_s, reap)


def log_age(path: Path, started: str) -> float:
    try:
        stamp = path.stat().st_mtime
    except OSError:
        from lane_state import parse_time
        stamp = parse_time(started)
    return max(0.0, time.time() - stamp)


def poll_interval(stall_seconds: float) -> float:
    """Seconds between stop-request checks. Never more than one second."""
    return min(1.0, max(0.05, stall_seconds / 20))


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_report(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_json(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


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


def _nested_untracked(line: str, nested: set[str]) -> bool:
    """An untracked direct child work tree is judged on its own, not as parent dirt."""
    if not nested or not line.startswith("??") or len(line) < 4:
        return False
    path = line[3:].strip().strip('"').rstrip("/")
    return path.split("/", 1)[0] in nested


def repo_rows(workspace: Path) -> list[tuple[str, str | None, str]]:
    repos = git_repos(workspace)
    nested = {name for name, path in repos if path.resolve() != workspace.resolve()}
    rows: list[tuple[str, str | None, str]] = []
    for name, repo in repos:
        skip = nested if repo.resolve() == workspace.resolve() else set()
        head = _git(repo, "rev-parse", "HEAD")
        status = _git(repo, "status", "--porcelain")
        sha = head.stdout.strip() if head.returncode == 0 and head.stdout.strip() else None
        if status.returncode != 0:
            text = "error"
        else:
            kept = [line for line in status.stdout.splitlines() if not _nested_untracked(line, skip)]
            text = "\n".join(kept)
        rows.append((name, sha, text))
    return rows


def read_heads(workspace: Path) -> dict[str, str]:
    return {name: sha for name, sha, _text in repo_rows(workspace) if sha}


def dirty_name(workspace: Path) -> str | None:
    for name, sha, text in repo_rows(workspace):
        if not sha or text.strip():
            return name
    return None


def changed_name(workspace: Path, recorded: dict | None) -> str | None:
    recorded = recorded or {}
    seen: set[str] = set()
    for name, sha, text in repo_rows(workspace):
        seen.add(name)
        if not sha or text.strip() or recorded.get(name) != sha:
            return name
    for name in recorded:
        if name not in seen:
            return name
    return None


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


def pgid_of(step: dict | None) -> int | None:
    if not step:
        return None
    started = step.get("started")
    if started:
        doc = read_json(Path(started))
        if doc:
            number = _pgid(doc.get("pgid"))
            if number is not None:
                return number
    for key in ("pgid", "pid"):
        number = _pgid(step.get(key))
        if number is not None:
            return number
    return None


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


def persist(directory: Path, lane: dict) -> None:
    lane["updated_at"] = now_iso()
    atomic_write_json(directory / "lane.json", lane)


def request_path(directory: Path) -> Path:
    return directory / REQUEST_NAME


def read_request(directory: Path) -> dict | None:
    doc = read_json(request_path(directory))
    if not doc or doc.get("what") not in ("stop", "abandon"):
        return None
    return doc


def discard_request(directory: Path) -> None:
    try:
        request_path(directory).unlink()
    except FileNotFoundError:
        pass


def close_step(
    directory: Path, lane: dict, step: dict, new_state: str, why: str,
    code: int | None, **extra,
) -> None:
    step["end"] = now_iso()
    step["state"] = "finished"
    if code is not None:
        step["exit"] = code
    commit_state(directory, lane, new_state, why, **extra)


def apply_request(directory: Path, lane: dict, request: dict, *, reap=None) -> None:
    """End the open step's group and record stop or abandon. Caller holds the lock."""
    if lane["state"] == "passed":
        verb = "stop" if request.get("what") == "stop" else "abandon"
        raise LaneError(f"refusing to {verb} a lane that passed")
    step = open_step(lane)
    pgid = pgid_of(step)
    reaped = end_group(pgid, reap=reap) if pgid else True
    if step is not None:
        step["reaped"] = reaped
        if request.get("what") == "stop":
            step["stopped_by"] = request.get("by")
        else:
            step["terminated"] = {"by": "abandon", "reaped": reaped, "at": now_iso()}
    lane["last_interrupt"] = {
        "what": request.get("what"),
        "by": request.get("by") or "",
        "reason": request.get("reason") or "",
        "at": request.get("at"),
    }
    if request.get("what") == "abandon":
        lane["abandoned"] = True
        why = f"abandon: {request.get('reason') or ''}"
        if pgid:
            why += "; terminated the process group"
    else:
        why = f"stopped by {request.get('by')}"
    if step is not None:
        close_step(directory, lane, step, "failed", why, None, reaped=reaped)
    else:
        commit_state(directory, lane, "failed", why, reaped=reaped)
    discard_request(directory)


def gate(lane: dict, name: str) -> tuple[str | None, dict | None]:
    workspace = workspace_of(lane)
    if name == "verify":
        dirty = dirty_name(workspace)
        if dirty:
            return f"uncommitted or untracked files in {dirty} before verify", None
        return None, read_heads(workspace)
    if name == "review":
        current = read_heads(workspace)
        entry = passing_verify(lane)
        if entry is None or entry.get("heads") != current:
            return REVIEW_HEADS, None
        dirty = dirty_name(workspace)
        if dirty:
            return f"the work tree of {dirty} changed during review", None
        return None, current
    return None, None


def judge(
    name: str, code: int, log_text: str, report_text: str, changed: str | None,
) -> tuple[str, str, str | None]:
    if name == "implement":
        if code != 0:
            return "failed", f"implement exited {code}", None
        return "verifying", "implement exited 0", None
    if name == "verify":
        last = last_nonempty(log_text)
        shown = last if last and last.startswith("VERDICT:") else None
        if code != 0:
            return "failed", f"verify exited {code}", shown
        if changed:
            return "failed", f"the work tree of {changed} changed during verify", shown
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
    if changed:
        return "failed", f"the work tree of {changed} changed during review", shown
    if first in REVIEW_OK and last == END_LINE:
        if first == "VERDICT: safe to merge":
            return "passed", first, first
        return "changes_requested", first, first
    return "failed", "review produced no verdict", shown


def write_done(path: Path, code: int) -> None:
    atomic_write_json(path, {"exit": code, "ended_at": now_iso()})


def apply_exit(directory: Path, lane: dict, step: dict, code: int) -> None:
    name = step["name"]
    log_text = read_text(Path(step["log"])) if step.get("log") else ""
    err_text = read_text(Path(step["stderr"])) if step.get("stderr") else ""
    add_usage(lane, step, parse_usage(log_text + "\n" + err_text))
    report_text = read_report(Path(step["report"])) if name == "review" and step.get("report") else ""
    changed = None
    fresh: dict[str, str] = {}
    if name in ("verify", "review"):
        workspace = workspace_of(lane)
        fresh = read_heads(workspace)
        changed = changed_name(workspace, step.get("heads") if isinstance(step.get("heads"), dict) else {})
    new_state, why, shown = judge(name, code, log_text, report_text, changed)
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
    write_done(Path(step["done"]), code)
    close_step(directory, lane, step, new_state, why, code)


def note_quiet(directory: Path, lane: dict, step: dict, stall_seconds: float, last_size: int, last_growth: float):
    size = file_size(Path(step["log"]))
    now = time.time()
    if size != last_size:
        if step.get("stalled_since"):
            step.pop("stalled_since", None)
            persist(directory, lane)
        return size, now
    if now - last_growth >= stall_seconds and not step.get("stalled_since"):
        step["stalled_since"] = now_iso()
        persist(directory, lane)
    return last_size, last_growth


def collect(proc: subprocess.Popen) -> int | None:
    try:
        return int(proc.wait(timeout=2))
    except subprocess.TimeoutExpired:
        return None


def wait_started(directory: Path, proc: subprocess.Popen, path: Path, timeout: float):
    """Return the started.json object, ``"request"``, or None on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if read_request(directory):
            return "request"
        doc = read_json(path)
        if doc and _pgid(doc.get("pid")) and _pgid(doc.get("pgid")):
            return doc
        if proc.poll() is not None:
            return None
        time.sleep(0.02)
    return None


def launch(directory: Path, lane: dict, cfg: dict, name: str, heads: dict | None, stall_seconds: float) -> None:
    number, attempt = allocate_attempt(directory, int(lane["round"]), name)
    stdout_path = attempt / "stdout.log"
    stderr_path = attempt / "stderr.log"
    done_path = attempt / "done"
    report_path = attempt / "report"
    started_path = attempt / "started.json"
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
        "pgid": None,
        "exit": None,
        "log": str(stdout_path),
        "stderr": str(stderr_path),
        "done": str(done_path),
        "report": str(report_path),
        "started": str(started_path),
        "heads": heads,
    }
    lane["steps"].append(step)
    persist(directory, lane)
    argv = render_argv(list(cfg[name]), **placeholders(lane, report_path))
    env = os.environ.copy()
    env["LANE_STEP"] = f"{lane['id']}/{name}"
    workspace = workspace_of(lane)
    cwd = str(workspace) if workspace.is_dir() else None
    out = stdout_path.open("wb", buffering=0)
    err = stderr_path.open("wb", buffering=0)
    try:
        proc = subprocess.Popen(
            [sys.executable, str(RUNNER), str(started_path), "--", *argv],
            stdout=out,
            stderr=err,
            cwd=cwd,
            env=env,
            start_new_session=True,
            shell=False,
        )
    except OSError:
        close_step(directory, lane, step, "failed", "the step did not register", None, reaped=True)
        return
    finally:
        out.close()
        err.close()
    step["pid"] = proc.pid
    step["pgid"] = proc.pid
    persist(directory, lane)
    found = wait_started(directory, proc, started_path, REGISTER_SECONDS)
    pending = read_request(directory)
    if found == "request" or pending:
        apply_request(
            directory, lane,
            pending or read_request(directory) or {"what": "stop", "by": "unknown"},
            reap=proc.poll,
        )
        collect(proc)
        return
    if not isinstance(found, dict):
        reaped = end_group(proc.pid, reap=proc.poll)
        collect(proc)
        step["reaped"] = reaped
        close_step(directory, lane, step, "failed", "the step did not register", None, reaped=reaped)
        return
    step["pid"] = found["pid"]
    step["pgid"] = found["pgid"]
    step["state"] = "running"
    persist(directory, lane)
    wait_child(directory, lane, step, proc, stall_seconds)


def wait_child(directory: Path, lane: dict, step: dict, proc: subprocess.Popen, stall_seconds: float) -> None:
    interval = poll_interval(stall_seconds)
    log_path = Path(step["log"])
    try:
        last_size = file_size(log_path)
        last_growth = log_path.stat().st_mtime
    except OSError:
        last_size = 0
        last_growth = time.time()
    while True:
        req = read_request(directory)
        if req:
            apply_request(directory, lane, req, reap=proc.poll)
            collect(proc)
            return
        try:
            code = proc.wait(timeout=interval)
        except subprocess.TimeoutExpired:
            last_size, last_growth = note_quiet(
                directory, lane, step, stall_seconds, last_size, last_growth,
            )
            continue
        req = read_request(directory)
        if req:
            apply_request(directory, lane, req, reap=proc.poll)
            return
        apply_exit(directory, lane, step, int(code))
        return


def close_orphan(directory: Path, lane: dict, step: dict) -> None:
    pgid = pgid_of(step)
    reaped = end_group(pgid) if pgid else True
    step["reaped"] = reaped
    why = f"the driver died during {step.get('name') or 'step'}"
    close_step(directory, lane, step, "failed", why, None, reaped=reaped)


def retry_block(lane: dict) -> str | None:
    if lane.get("abandoned"):
        return "refusing to retry an abandoned lane"
    if lane["state"] == "changes_requested":
        return "a review fix first goes through next-round"
    if lane["state"] != "failed":
        return f"retry needs a failed lane, not {lane['state']}"
    if not lane.get("steps"):
        return "retry needs a failed step"
    step = lane["steps"][-1]
    if step.get("name") != "verify":
        return None
    for entry in reversed(lane.get("verdicts", {}).get("entries") or []):
        if (
            entry.get("step") == "verify"
            and entry.get("round") == step.get("round")
            and entry.get("attempt") == step.get("attempt")
        ):
            verdict = entry.get("verdict")
            if (
                entry.get("exit") == 0
                and isinstance(verdict, str)
                and verdict.startswith("VERDICT:")
                and verdict != PASS_LINE
            ):
                return "a verify FAIL goes through next-round"
            return None
    return None


def drive(directory: Path, lane: dict, cfg: dict, stall_seconds: float) -> dict:
    if lane["state"] not in DRIVING:
        return lane
    while lane["state"] in DRIVING:
        pending = read_request(directory)
        if pending:
            apply_request(directory, lane, pending)
            return lane
        if lane["state"] == "ready":
            if not within_budget(lane):
                commit_state(directory, lane, "over_budget", "round budget exhausted")
                return lane
            commit_state(directory, lane, "implementing", "run")
            continue
        step = open_step(lane)
        if step is not None:
            close_orphan(directory, lane, step)
            return lane
        name = PHASE_OF.get(lane["state"])
        if name is None:
            commit_state(directory, lane, "failed", "the driver died during the step")
            return lane
        if name == "implement" and not within_budget(lane):
            commit_state(directory, lane, "over_budget", "round budget exhausted")
            return lane
        why, heads = gate(lane, name)
        if why:
            commit_state(directory, lane, "failed", why)
            return lane
        launch(directory, lane, cfg, name, heads, stall_seconds)
    return lane
