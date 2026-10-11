"""Lane files: atomic json, the lock, config argv, and the round budget."""
from __future__ import annotations

import json
import os
import random
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = "~/agent-work/lanes"
PHASES = ("implement", "verify", "review")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
PLACEHOLDER_RE = re.compile(r"\{(workspace|brief|round|report|id)\}")
ARGV_EXAMPLE = '["bash", "~/agent-work/verify-branch.sh", "{workspace}", "bifrost-platform"]'
REQUIRED = (
    "id", "work", "title", "repo_dirs", "branch", "brief", "round", "max_rounds",
    "state", "steps", "verdicts", "usage", "created_at", "updated_at",
)
STEP_BLOCK = "a lane step cannot change a lane"


class LaneError(Exception):
    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def atomic_write_json(path: Path, doc: dict) -> None:
    """Write JSON via a unique temp file in the same directory, then rename.

    The temp name carries the pid and a random suffix so two writers cannot
    share one file. A crash before the rename leaves the previous file in place.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}.{random.randrange(16 ** 8):08x}"
    tmp = path.with_name(f"{path.name}.{token}.tmp")
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
        command = cfg.get(key)
        if (
            not isinstance(command, list)
            or not command
            or any(type(part) is not str or part == "" for part in command)
        ):
            raise LaneError(
                f"config {key} must be a JSON array of strings, for example {ARGV_EXAMPLE}"
            )
    return cfg


def render_text(template: str, **values: object) -> str:
    """Substitute placeholders once. Values are not scanned again."""
    def sub(match: re.Match) -> str:
        key = match.group(1)
        if key in values:
            return str(values[key])
        return match.group(0)
    return PLACEHOLDER_RE.sub(sub, template)


def render_argv(argv: list[str], **values: object) -> list[str]:
    """Substitute inside each element. A value cannot become a new element.

    An element that begins with ``~/`` is expanded to the home directory.
    """
    rendered: list[str] = []
    for element in argv:
        text = render_text(element, **values)
        if text.startswith("~/"):
            text = str(Path(text).expanduser())
        rendered.append(text)
    return rendered


def root_path(text: str) -> Path:
    return Path(text).expanduser().resolve()


def check_id(lane_id: str) -> str:
    if not ID_RE.fullmatch(lane_id):
        raise LaneError("lane id must be one path segment")
    return lane_id


def lane_dir(root: Path, lane_id: str) -> Path:
    directory = root / check_id(lane_id)
    if not directory.is_dir():
        raise LaneError(f"no lane {lane_id}")
    return directory


def load_lane(directory: Path) -> dict:
    path = directory / "lane.json"
    if not path.is_file():
        raise LaneError(f"no lane {directory.name}")
    try:
        lane = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LaneError(f"unreadable lane.json: {exc}") from exc
    missing = [key for key in REQUIRED if key not in lane]
    if missing:
        raise LaneError(f"lane.json missing {', '.join(missing)}")
    return lane


def iter_lanes(root: Path) -> list[tuple[Path, dict]]:
    import sys
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
        for child in sorted(p for p in root.iterdir() if p.is_dir()):
            if (child / ".git").exists():
                out[child.name] = str(child)
    return out


def budget_limit(lane: dict) -> int:
    return int(lane["max_rounds"]) + len(lane.get("extensions") or [])


def within_budget(lane: dict) -> bool:
    return int(lane["round"]) <= budget_limit(lane)


def coordinator_extended(lane: dict) -> bool:
    return any(item.get("by") == "coordinator" for item in lane.get("extensions") or [])


def extension_lines(lane: dict) -> list[str]:
    return [
        f"budget extended once by {item['by']}: {item['reason']}"
        for item in (lane.get("extensions") or [])
    ]


def refuse_if_step() -> None:
    if os.environ.get("LANE_STEP"):
        raise LaneError(STEP_BLOCK)


@contextmanager
def lane_lock(directory: Path, lane_id: str):
    """Exclusive lock from before lane.json is read until the caller finishes writing."""
    import fcntl
    path = directory / "lock"
    fh = path.open("a+")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.seek(0)
            pid = fh.read().strip() or "unknown"
            raise LaneError(f"lane {lane_id} is being driven by pid {pid}", code=3) from exc
        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()}\n")
        fh.flush()
        os.fsync(fh.fileno())
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()
