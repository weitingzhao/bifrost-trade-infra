"""Shadow week beside the hand-maintained board.

``start-step`` launches ``proxy.py`` under the recorder's ``run``.
``mark`` passes a bookkeeping command through and records the mapping.
``compare`` is the only reader of the folded document. ``report`` prints
the four numbers for one day.

State stays under ``--root`` (default ``~/agent-work/shadow-recorder``):
``map.json``, ``diff.jsonl``, ``compares.jsonl``. The coordinator keeps
``triage.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

_HERE = Path(__file__).resolve().parent
_RECORDER = _HERE.parent
if str(_RECORDER) not in sys.path:
    sys.path.insert(0, str(_RECORDER))

import proxy  # noqa: E402

REC = _RECORDER / "rec.py"
PROXY = _HERE / "proxy.py"
TOLERANCE_S = 60
TRIAGE_CLASSES = ("脚本错", "看板错", "两边的模型不同")

# Board state → class. ``needs_owner`` on a waiting step is waiting_owner.
_BOARD = {
    "waiting": "not_started",
    "running": "running",
    "slow": "running",
    "quiet": "running",
    "dead": "running_process_gone",
    "done": "finished_ok",
    "failed": "finished_failed",
}
_RECORDER_STATE = {
    "waiting": "not_started",
    "running": "running",
    "slow": "running",
    "quiet": "running",
    "dead": "running_process_gone",
    "done": "finished_ok",
    "failed": "finished_failed",
    "unknown": "unknown",
}


class InputError(Exception):
    pass


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path.home() / "agent-work" / "shadow-recorder"
    if argv[:1] == ["--root"]:
        if len(argv) < 3:
            print("need a path after --root", file=sys.stderr)
            return 2
        root = Path(argv[1])
        argv = argv[2:]
    if not argv:
        print("need start-step, mark, compare, or report", file=sys.stderr)
        return 2
    command, rest = argv[0], argv[1:]
    try:
        if command == "start-step":
            return cmd_start_step(root, rest)
        if command == "mark":
            return cmd_mark(root, rest)
        if command == "compare":
            return cmd_compare(root, rest)
        if command == "report":
            return cmd_report(root, rest)
    except InputError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"unknown command {command}", file=sys.stderr)
    return 2


def cmd_start_step(root: Path, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="shadow.py start-step")
    parser.add_argument("--title", required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--done", required=True)
    parser.add_argument("--kind", default="other")
    parser.add_argument("--who", default="shadow")
    parser.add_argument("--poll", type=float, default=2)
    args = parser.parse_args(argv)
    if args.poll <= 0:
        print("poll must be greater than 0", file=sys.stderr)
        return 2
    root.mkdir(parents=True, exist_ok=True)
    mapping = _load_map(root)
    work_id = _work_id(mapping, args.title)
    if not (root / work_id / "events.jsonl").is_file():
        opened = _rec(root, ["open", "--work", work_id, "--title", args.title])
        if opened.returncode != 0:
            sys.stderr.write(opened.stderr)
            return opened.returncode
        _remember_work(mapping, args.title, work_id)
        _save_map(root, mapping)
    spawn = root / "_spawn"
    spawn.mkdir(parents=True, exist_ok=True)
    log_path = spawn / f"{os.getpid()}-{time.time_ns()}.log"
    command = [
        sys.executable,
        str(REC),
        "--root",
        str(root),
        "run",
        "--work",
        work_id,
        "--kind",
        args.kind,
        "--who",
        args.who,
        "--name",
        args.step,
        "--",
        sys.executable,
        str(PROXY),
        "--pattern",
        args.pattern,
        "--done",
        args.done,
        "--poll",
        str(args.poll),
    ]
    log_file = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        command,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=str(root),
        env=_env(),
    )
    try:
        code = proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        code = None
    log_file.close()
    text = log_path.read_text(encoding="utf-8", errors="replace")
    step_id, run_id = _ids_from_text(text)
    _remember_step(
        mapping,
        args.title,
        args.step,
        work_id,
        step_id,
        pattern=args.pattern,
        done=args.done,
        pid=None if code is not None else proc.pid,
        run_id=run_id,
        run_exit=code,
    )
    _save_map(root, mapping)
    if code is None:
        print(f"pid={proc.pid}")
        return 0
    sys.stderr.write(text)
    return code if code else 1


def cmd_mark(root: Path, argv: list[str]) -> int:
    if "--" not in argv:
        print("mark needs -- before the recorder command", file=sys.stderr)
        return 2
    split = argv.index("--")
    parser = argparse.ArgumentParser(prog="shadow.py mark")
    parser.add_argument("--title", required=True)
    parser.add_argument("--step")
    parser.add_argument("--owner")
    args = parser.parse_args(argv[:split])
    rec_args = argv[split + 1 :]
    if not rec_args:
        print("mark needs a recorder command after --", file=sys.stderr)
        return 2
    if "--root" in rec_args:
        print("the recorder root is the shadow --root", file=sys.stderr)
        return 2
    root.mkdir(parents=True, exist_ok=True)
    proc = _rec(root, rec_args)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        return proc.returncode
    event = _one_event(proc.stdout)
    mapping = _load_map(root)
    work_id = event.get("work_id") or _flag(rec_args, "--work")
    if event.get("type") == "work_opened" and work_id:
        _remember_work(mapping, args.title, work_id)
    if args.step and event.get("step_id"):
        _remember_step(mapping, args.title, args.step, work_id, event["step_id"])
    if args.owner and event.get("wait_id"):
        _remember_owner(mapping, args.title, args.owner, work_id, event["wait_id"])
    _save_map(root, mapping)
    return 0


def cmd_compare(root: Path, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="shadow.py compare")
    parser.add_argument("--board", required=True)
    args = parser.parse_args(argv)
    board = _read_json(Path(args.board), "board")
    if type(board) is not dict:
        raise InputError("board is not a JSON object")
    mapping = _load_map(root) if (root / "map.json").exists() else _empty_map()
    document = _fold(root)
    now = time.time()
    diffs = []
    steps = mapping.get("steps") or []
    owners = mapping.get("owners") or []
    for entry in steps:
        if type(entry) is not dict:
            continue
        diffs.extend(_compare_step(board, document, entry))
    for entry in owners:
        if type(entry) is not dict:
            continue
        diffs.extend(_compare_owner(board, document, entry))
    _append_diffs(root, diffs, now)
    _append_jsonl(
        root / "compares.jsonl",
        {"at": now, "day": _day(now), "differences": len(diffs)},
    )
    print(f"steps={len(steps)} owners={len(owners)} differences={len(diffs)}")
    return 0


def cmd_report(root: Path, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="shadow.py report")
    parser.add_argument("--day", required=True)
    args = parser.parse_args(argv)
    if len(args.day) != 10 or args.day[4] != "-" or args.day[7] != "-":
        raise InputError("day must be YYYY-MM-DD")
    compares = _read_jsonl(root / "compares.jsonl")
    diffs = _read_jsonl(root / "diff.jsonl")
    triage = _read_triage(root / "triage.json")
    day_compares = [row for row in compares if row.get("day") == args.day]
    day_diffs = [row for row in diffs if row.get("day") == args.day]
    counts = {name: 0 for name in TRIAGE_CLASSES}
    unexplained = 0
    for row in day_diffs:
        klass = triage.get(row.get("id"))
        if klass in counts:
            counts[klass] += 1
        else:
            unexplained += 1
    print(
        f"comparisons={len(day_compares)} differences={len(day_diffs)} "
        f"脚本错={counts['脚本错']} 看板错={counts['看板错']} "
        f"两边的模型不同={counts['两边的模型不同']} unexplained={unexplained}"
    )
    return 0


def _compare_step(board: dict, document: dict, entry: dict) -> list[dict]:
    title = entry.get("title")
    name = entry.get("name")
    board_step = _board_step(board, title, name)
    rec_step = _rec_step(document, entry.get("work_id"), entry.get("step_id"))
    facts = _facts(entry)
    if board_step is None or rec_step is None:
        return [
            _diff(
                title,
                name,
                None,
                "presence",
                board_step is not None,
                rec_step is not None,
                facts,
            )
        ]
    found = []
    board_class = _board_class(board_step)
    rec_class = _rec_class(rec_step)
    if board_class != rec_class:
        found.append(_diff(title, name, None, "state", board_class, rec_class, facts))
    if _time_differs(board_step.get("started"), rec_step.get("started")):
        found.append(
            _diff(title, name, None, "started", board_step.get("started"), rec_step.get("started"), facts)
        )
    if _time_differs(board_step.get("ended"), rec_step.get("ended")):
        found.append(
            _diff(title, name, None, "ended", board_step.get("ended"), rec_step.get("ended"), facts)
        )
    return found


def _compare_owner(board: dict, document: dict, entry: dict) -> list[dict]:
    name = entry.get("name")
    title = entry.get("title")
    board_item = _board_owner(board, name)
    rec_item = _rec_owner(document, entry.get("wait_id"))
    board_open = _is_open(board_item)
    rec_open = rec_item is not None
    facts = {"marker": None, "process": False}
    found = []
    if board_open != rec_open:
        found.append(_diff(title, None, name, "open", board_open, rec_open, facts))
    if board_open and rec_open:
        board_since = board_item.get("since") if board_item else None
        rec_since = rec_item.get("since") if rec_item else None
        if _time_differs(board_since, rec_since):
            found.append(_diff(title, None, name, "since", board_since, rec_since, facts))
    return found


def _board_class(step: dict) -> str:
    state = step.get("state")
    if step.get("needs_owner") is True and state in (None, "waiting"):
        return "waiting_owner"
    return _BOARD.get(state, "unknown")


def _rec_class(step: dict) -> str:
    return _RECORDER_STATE.get(step.get("state"), "unknown")


def _time_differs(left, right) -> bool:
    if left is None and right is None:
        return False
    if type(left) not in (int, float) or type(right) not in (int, float):
        return True
    if type(left) is bool or type(right) is bool:
        return True
    return abs(left - right) > TOLERANCE_S


def _is_open(item) -> bool:
    if type(item) is not dict:
        return False
    return item.get("now", True) is not False


def _facts(entry: dict) -> dict:
    marker = None
    done = entry.get("done")
    if done:
        try:
            marker = Path(done).read_text(encoding="utf-8", errors="replace")
        except OSError:
            marker = None
    pattern = entry.get("pattern")
    process = proxy.matching(pattern) if pattern else False
    return {"marker": marker, "process": process}


def _diff(title, step, owner, field, board, recorder, facts) -> dict:
    return {
        "title": title,
        "step": step,
        "owner": owner,
        "field": field,
        "board": board,
        "recorder": recorder,
        "facts": facts,
    }


def _fold(root: Path) -> dict:
    logs = []
    if root.is_dir():
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            if not child.is_dir() or child.name.startswith(".") or child.name.startswith("_"):
                continue
            path = child / "events.jsonl"
            if not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise InputError(f"cannot read {path}") from exc
            logs.append((child.name, data))
    import read

    now = time.time()
    return read.fold_total(logs, [], now, 0).document()


def _board_step(board: dict, title, name):
    work = _board_work(board, title)
    if work is None:
        return None
    steps = work.get("steps")
    if type(steps) is not list:
        return None
    for step in steps:
        if type(step) is dict and step.get("name") == name:
            return step
    return None


def _board_work(board: dict, title):
    works = board.get("works")
    if type(works) is not list:
        return None
    for work in works:
        if type(work) is dict and work.get("title") == title:
            return work
    return None


def _board_owner(board: dict, name):
    items = board.get("owner_all")
    if type(items) is not list:
        return None
    for item in items:
        if type(item) is dict and item.get("name") == name:
            return item
    return None


def _rec_step(document: dict, work_id, step_id):
    if not step_id:
        return None
    for work in document.get("works") or []:
        if work.get("work_id") != work_id:
            continue
        for step in work.get("steps") or []:
            if step.get("step_id") == step_id:
                return step
    return None


def _rec_owner(document: dict, wait_id):
    if not wait_id:
        return None
    for item in document.get("owner_all") or []:
        if item.get("wait_id") == wait_id:
            return item
    return None


def _append_diffs(root: Path, diffs: list[dict], now: float) -> None:
    path = root / "diff.jsonl"
    existing = _read_jsonl(path)
    number = _next_id(existing)
    day = _day(now)
    for item in diffs:
        item["id"] = f"d{number}"
        item["at"] = now
        item["day"] = day
        number += 1
        _append_jsonl(path, item)


def _next_id(rows: list[dict]) -> int:
    highest = 0
    for row in rows:
        ident = row.get("id")
        if type(ident) is str and ident.startswith("d") and ident[1:].isdigit():
            highest = max(highest, int(ident[1:]))
    return highest + 1


def _read_triage(path: Path) -> dict:
    if not path.exists():
        return {}
    data = _read_json(path, "triage")
    if type(data) is not dict:
        raise InputError("triage is not a JSON object")
    return data


def _read_json(path: Path, label: str):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {label}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise InputError(f"cannot read {label}") from exc


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {path.name}") from exc
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise InputError(f"cannot read {path.name}") from exc
        if type(item) is not dict:
            raise InputError(f"cannot read {path.name}")
        rows.append(item)
    return rows


def _append_jsonl(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def _empty_map() -> dict:
    return {"works": [], "steps": [], "owners": []}


def _load_map(root: Path) -> dict:
    path = root / "map.json"
    if not path.exists():
        return _empty_map()
    data = _read_json(path, "map")
    if type(data) is not dict:
        raise InputError("map is not a JSON object")
    data.setdefault("works", [])
    data.setdefault("steps", [])
    data.setdefault("owners", [])
    return data


def _save_map(root: Path, mapping: dict) -> None:
    path = root / "map.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(blob, encoding="utf-8")
    os.replace(tmp, path)


def _work_id(mapping: dict, title: str) -> str:
    for item in mapping.get("works") or []:
        if item.get("title") == title and item.get("work_id"):
            return item["work_id"]
    digest = hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]
    return "s" + digest


def _remember_work(mapping: dict, title: str, work_id: str) -> None:
    for item in mapping["works"]:
        if item.get("title") == title:
            item["work_id"] = work_id
            return
    mapping["works"].append({"title": title, "work_id": work_id})


def _remember_step(
    mapping: dict,
    title: str,
    name: str,
    work_id,
    step_id,
    pattern=None,
    done=None,
    pid=None,
    run_id=None,
    run_exit=None,
) -> None:
    for item in mapping["steps"]:
        if item.get("title") == title and item.get("name") == name:
            item["work_id"] = work_id
            if step_id:
                item["step_id"] = step_id
            if pattern is not None:
                item["pattern"] = pattern
            if done is not None:
                item["done"] = done
            if pid is not None:
                item["pid"] = pid
            if run_id:
                item["run_id"] = run_id
            if run_exit is not None:
                item["run_exit"] = run_exit
            return
    mapping["steps"].append(
        {
            "title": title,
            "name": name,
            "work_id": work_id,
            "step_id": step_id,
            "pattern": pattern,
            "done": done,
            "pid": pid,
            "run_id": run_id,
            "run_exit": run_exit,
        }
    )


def _remember_owner(mapping: dict, title: str, name: str, work_id, wait_id: str) -> None:
    for item in mapping["owners"]:
        if item.get("title") == title and item.get("name") == name:
            item["work_id"] = work_id
            item["wait_id"] = wait_id
            return
    mapping["owners"].append(
        {"title": title, "name": name, "work_id": work_id, "wait_id": wait_id}
    )


def _ids_from_text(text: str) -> tuple[str | None, str | None]:
    step_id = None
    run_id = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if event.get("step_id"):
            step_id = event["step_id"]
        if event.get("run_id"):
            run_id = event["run_id"]
    return step_id, run_id


def _one_event(text: str) -> dict:
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        event = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise InputError("recorder did not print an event") from exc
    if type(event) is not dict:
        raise InputError("recorder did not print an event")
    return event


def _flag(argv: list[str], name: str):
    if name not in argv:
        return None
    index = argv.index(name)
    if index + 1 >= len(argv):
        return None
    return argv[index + 1]


def _rec(root: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REC), "--root", str(root), *args],
        capture_output=True,
        text=True,
        env=_env(),
        cwd=str(root),
    )


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _day(at: float) -> str:
    return datetime.fromtimestamp(at).strftime("%Y-%m-%d")


if __name__ == "__main__":
    sys.exit(main())
