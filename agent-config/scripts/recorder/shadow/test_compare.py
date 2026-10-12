"""Compare against a board and logs the real recorder commands wrote."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

SHADOW = Path(__file__).resolve().parent / "shadow.py"
RECORDER = Path(__file__).resolve().parents[1]


def _run(root: Path, *args, check=True) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(SHADOW), "--root", str(root), *args],
        capture_output=True,
        text=True,
        env=env,
    )
    if check and proc.returncode != 0:
        raise AssertionError((proc.returncode, proc.stdout, proc.stderr))
    return proc


def _mark(root: Path, title: str, rec_args: list[str], step=None, owner=None) -> dict:
    args = ["mark", "--title", title]
    if step is not None:
        args.extend(["--step", step])
    if owner is not None:
        args.extend(["--owner", owner])
    args.append("--")
    args.extend(rec_args)
    proc = _run(root, *args)
    return json.loads(proc.stdout)


def _board(path: Path, steps: list[dict], owners: list[dict] | None = None, title="活") -> None:
    document = {"works": [{"title": title, "steps": steps}], "owner_all": owners or []}
    path.write_text(json.dumps(document), encoding="utf-8")


def _map_owner(root: Path, name: str, wait_id: str, work: str = "w1", title: str = "活") -> None:
    path = root / "map.json"
    mapping = json.loads(path.read_text(encoding="utf-8"))
    owners = mapping.setdefault("owners", [])
    for item in owners:
        if item.get("name") == name and item.get("title") == title:
            item["wait_id"] = wait_id
            item["work_id"] = work
            break
    else:
        owners.append({"title": title, "name": name, "work_id": work, "wait_id": wait_id})
    path.write_text(json.dumps(mapping), encoding="utf-8")


def _diffs(root: Path) -> list[dict]:
    path = root / "diff.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _by(root: Path, field: str, step=None, owner=None) -> list[dict]:
    rows = []
    for item in _diffs(root):
        if item["field"] != field:
            continue
        if step is not None and item.get("step") != step:
            continue
        if owner is not None and item.get("owner") != owner:
            continue
        rows.append(item)
    return rows


def _declare(root: Path, name: str, work="w1") -> dict:
    return _mark(
        root,
        "活",
        ["declare", "--work", work, "--name", name, "--kind", "other", "--who", "Cursor", "--watch", "none"],
        step=name,
    )


def _start(root: Path, name: str, step_id: str, work="w1") -> dict:
    return _mark(root, "活", ["start", "--work", work, "--step", step_id], step=name)


def _finish(root: Path, name: str, step_id: str, reported: str, work="w1") -> dict:
    return _mark(
        root,
        "活",
        ["finish", "--work", work, "--step", step_id, "--reported", reported],
        step=name,
    )


def _step(name: str, state: str, started=None, ended=None, needs_owner=False) -> dict:
    item = {"name": name, "state": state}
    if started is not None:
        item["started"] = started
    if ended is not None:
        item["ended"] = ended
    if needs_owner:
        item["needs_owner"] = True
    return item


def test_state_classes(tmp_path):
    root = tmp_path / "root"
    _mark(root, "活", ["open", "--work", "w1", "--title", "活"])
    waiting = _declare(root, "未开始")
    running = _declare(root, "在跑")
    started = _start(root, "在跑", running["step_id"])
    slow = _declare(root, "慢")
    slow_at = _start(root, "慢", slow["step_id"])["at"]
    quiet = _declare(root, "静")
    quiet_at = _start(root, "静", quiet["step_id"])["at"]
    done = _declare(root, "成功")
    done_start = _start(root, "成功", done["step_id"])["at"]
    done_end = _finish(root, "成功", done["step_id"], "finished")["at"]
    failed = _declare(root, "失败")
    failed_start = _start(root, "失败", failed["step_id"])["at"]
    failed_end = _finish(root, "失败", failed["step_id"], "failed")["at"]
    dead = _declare(root, "看板死")
    dead_start = _start(root, "看板死", dead["step_id"])["at"]
    dead_end = _finish(root, "看板死", dead["step_id"], "finished")["at"]
    owned = _declare(root, "等他")
    mismatch = _declare(root, "说成失败")
    mismatch_start = _start(root, "说成失败", mismatch["step_id"])["at"]
    mismatch_end = _finish(root, "说成失败", mismatch["step_id"], "finished")["at"]
    assert waiting["type"] == "step_declared"
    board = tmp_path / "status.json"
    _board(
        board,
        [
            _step("未开始", "waiting"),
            _step("在跑", "running", started=started["at"]),
            _step("慢", "slow", started=slow_at),
            _step("静", "quiet", started=quiet_at),
            _step("成功", "done", started=done_start, ended=done_end),
            _step("失败", "failed", started=failed_start, ended=failed_end),
            _step("看板死", "dead", started=dead_start, ended=dead_end),
            _step("等他", "waiting", needs_owner=True),
            _step("说成失败", "failed", started=mismatch_start, ended=mismatch_end),
        ],
    )
    proc = _run(root, "compare", "--board", str(board))
    assert proc.stdout.strip() == "steps=9 owners=0 differences=3"
    assert _by(root, "state", step="未开始") == []
    assert _by(root, "state", step="在跑") == []
    assert _by(root, "state", step="慢") == []
    assert _by(root, "state", step="静") == []
    assert _by(root, "state", step="成功") == []
    assert _by(root, "state", step="失败") == []
    dead_diff = _by(root, "state", step="看板死")
    assert len(dead_diff) == 1
    assert dead_diff[0]["board"] == "running_process_gone"
    assert dead_diff[0]["recorder"] == "finished_ok"
    assert dead_diff[0]["facts"] == {"marker": None, "process": False}
    owned_diff = _by(root, "state", step="等他")
    assert owned_diff[0]["board"] == "waiting_owner"
    assert owned_diff[0]["recorder"] == "not_started"
    said = _by(root, "state", step="说成失败")
    assert said[0]["board"] == "finished_failed"
    assert said[0]["recorder"] == "finished_ok"


def test_time_tolerance_both_edges(tmp_path):
    root = tmp_path / "root"
    _mark(root, "活", ["open", "--work", "w1", "--title", "活"])
    high = _declare(root, "上沿")
    high_at = _start(root, "上沿", high["step_id"])["at"]
    low = _declare(root, "下沿")
    low_at = _start(root, "下沿", low["step_id"])["at"]
    outside = _declare(root, "超出")
    outside_at = _start(root, "超出", outside["step_id"])["at"]
    end_in = _declare(root, "结束沿")
    end_in_start = _start(root, "结束沿", end_in["step_id"])["at"]
    end_in_at = _finish(root, "结束沿", end_in["step_id"], "finished")["at"]
    end_out = _declare(root, "结束外")
    end_out_start = _start(root, "结束外", end_out["step_id"])["at"]
    end_out_at = _finish(root, "结束外", end_out["step_id"], "finished")["at"]
    board = tmp_path / "status.json"
    _board(
        board,
        [
            _step("上沿", "running", started=high_at + 60),
            _step("下沿", "running", started=low_at - 60),
            _step("超出", "running", started=outside_at + 61),
            _step("结束沿", "done", started=end_in_start, ended=end_in_at + 60),
            _step("结束外", "done", started=end_out_start, ended=end_out_at + 61),
        ],
    )
    _run(root, "compare", "--board", str(board))
    assert _by(root, "started", step="上沿") == []
    assert _by(root, "started", step="下沿") == []
    assert _by(root, "ended", step="结束沿") == []
    over = _by(root, "started", step="超出")
    assert len(over) == 1
    assert over[0]["board"] == outside_at + 61
    assert over[0]["recorder"] == outside_at
    ended = _by(root, "ended", step="结束外")
    assert len(ended) == 1
    assert ended[0]["board"] == end_out_at + 61
    assert ended[0]["recorder"] == end_out_at


def test_owner_items_and_since(tmp_path):
    # The command line cannot record owner-open. The events below are placed
    # with owner_open only so the fold has open items to try ``since`` on.
    # shadow.py itself writes through the command line only.
    from commands import owner_open

    root = tmp_path / "root"
    _mark(root, "活", ["open", "--work", "w1", "--title", "活"])
    refused = _run(
        root,
        "mark",
        "--title",
        "活",
        "--owner",
        "两边都有",
        "--",
        "owner-open",
        "--work",
        "w1",
        "--title",
        "两边都有",
        "--can-act",
        "yes",
        check=False,
    )
    assert refused.returncode == 1
    assert refused.stderr.strip() == "unknown command"
    assert refused.stdout == ""
    both = owner_open(root, "w1", "两边都有", can_act="yes")
    only_rec = owner_open(root, "w1", "只在记录器", can_act="yes")
    closed = owner_open(root, "w1", "只在看板", can_act="yes")
    no_since = owner_open(root, "w1", "没有起算", can_act="yes")
    for event, name in (
        (both, "两边都有"),
        (only_rec, "只在记录器"),
        (closed, "只在看板"),
        (no_since, "没有起算"),
    ):
        _map_owner(root, name, event["wait_id"])
    _mark(
        root,
        "活",
        ["owner-close", "--work", "w1", "--wait", closed["wait_id"], "--how", "done"],
        owner="只在看板",
    )
    board = tmp_path / "status.json"
    _board(
        board,
        [],
        owners=[
            {"name": "两边都有", "since": both["at"], "now": True},
            {"name": "只在看板", "since": closed["at"], "now": True},
            {"name": "没有起算", "now": True},
        ],
    )
    proc = _run(root, "compare", "--board", str(board))
    assert proc.stdout.splitlines() == [
        "owner items not comparable: the recorder cannot record them (TD-319 item 5)",
        "since of owner items not comparable (TD-319 item 6)",
        "steps=0 owners=4 differences=0",
    ]
    assert _by(root, "open") == []
    assert _by(root, "since") == []
    assert _diffs(root) == []
    assert only_rec["wait_id"] != no_since["wait_id"]
    assert both["at"] != closed["at"]


def test_owner_line_when_the_fold_has_no_items(tmp_path):
    root = tmp_path / "root"
    _mark(root, "活", ["open", "--work", "w1", "--title", "活"])
    board = tmp_path / "status.json"
    _board(board, [], owners=[{"name": "请看", "since": 1, "now": True}])
    proc = _run(root, "compare", "--board", str(board))
    assert proc.stdout.splitlines() == [
        "owner items not comparable: the recorder cannot record them (TD-319 item 5)",
        "steps=0 owners=0 differences=0",
    ]
    assert _diffs(root) == []


def test_step_mapped_on_one_side_only(tmp_path):
    root = tmp_path / "root"
    _mark(root, "活", ["open", "--work", "w1", "--title", "活"])
    gone = _declare(root, "撤了")
    _mark(root, "活", ["withdraw", "--work", "w1", "--step", gone["step_id"]], step="撤了")
    kept = _declare(root, "记录器有")
    _start(root, "记录器有", kept["step_id"])
    board = tmp_path / "status.json"
    _board(board, [_step("撤了", "waiting")])
    _run(root, "compare", "--board", str(board))
    left = _by(root, "presence", step="撤了")
    assert left[0]["board"] is True
    assert left[0]["recorder"] is False
    right = _by(root, "presence", step="记录器有")
    assert right[0]["board"] is False
    assert right[0]["recorder"] is True
    assert _by(root, "state") == []


def test_differences_are_appended(tmp_path):
    root = tmp_path / "root"
    _mark(root, "活", ["open", "--work", "w1", "--title", "活"])
    declared = _declare(root, "未开始")
    board = tmp_path / "status.json"
    _board(board, [_step("未开始", "failed")])
    _run(root, "compare", "--board", str(board))
    _run(root, "compare", "--board", str(board))
    rows = _diffs(root)
    assert [row["id"] for row in rows] == ["d1", "d2"]
    assert rows[0]["step"] == "未开始"
    assert declared["step_id"]


def test_unreadable_input_exits_2(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    missing = _run(root, "compare", "--board", str(tmp_path / "nope.json"), check=False)
    assert missing.returncode == 2
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    broken = _run(root, "compare", "--board", str(bad), check=False)
    assert broken.returncode == 2
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    ok = _run(root, "compare", "--board", str(empty))
    assert ok.returncode == 0
    assert ok.stdout.strip() == "steps=0 owners=0 differences=0"


def test_report_four_numbers(tmp_path):
    root = tmp_path / "root"
    _mark(root, "活", ["open", "--work", "w1", "--title", "活"])
    _declare(root, "未开始")
    board = tmp_path / "status.json"
    _board(board, [_step("未开始", "failed"), _step("没有这一步", "running")])
    # The second step is not mapped, so only the failed class is a difference.
    _run(root, "compare", "--board", str(board))
    day = json.loads((root / "compares.jsonl").read_text(encoding="utf-8"))["day"]
    (root / "triage.json").write_text(json.dumps({"d1": "脚本错"}), encoding="utf-8")
    proc = _run(root, "report", "--day", day)
    assert proc.stdout.strip() == "comparisons=1 differences=1 脚本错=1 看板错=0 两边的模型不同=0 unexplained=0"
    (root / "triage.json").write_text("{}", encoding="utf-8")
    again = _run(root, "report", "--day", day)
    assert "unexplained=1" in again.stdout
    bad = _run(root, "report", "--day", "yesterday", check=False)
    assert bad.returncode == 2


def test_nothing_is_written_outside_root(tmp_path):
    base = tmp_path / "sandbox"
    root = base / "root"
    outside = base / "outside"
    home = base / "home"
    outside.mkdir(parents=True)
    home.mkdir()
    sentinel = outside / "sentinel"
    sentinel.write_text("keep", encoding="utf-8")
    before = _snapshot(RECORDER)
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["HOME"] = str(home)
    _mark(root, "活", ["open", "--work", "w1", "--title", "活"])
    declared = _declare(root, "一步")
    _start(root, "一步", declared["step_id"])
    _finish(root, "一步", declared["step_id"], "finished")
    from commands import owner_open

    opened = owner_open(root, "w1", "请看", can_act="yes")
    _mark(
        root,
        "活",
        ["owner-close", "--work", "w1", "--wait", opened["wait_id"], "--how", "done"],
        owner="请看",
    )
    board = base / "status.json"
    _board(board, [_step("一步", "done")], owners=[{"name": "请看", "now": True}])
    _run(root, "compare", "--board", str(board))
    proc = subprocess.run(
        [
            sys.executable,
            str(SHADOW),
            "--root",
            str(root),
            "start-step",
            "--title",
            "活",
            "--step",
            "影子",
            "--pattern",
            "sj-not-a-job",
            "--done",
            str(root / "missing.done"),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    _reap(root)
    assert proc.returncode in (0, 2)
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert list(home.iterdir()) == []
    for path in base.rglob("*"):
        if path.is_relative_to(root) or path in (sentinel, board, outside, home):
            continue
        raise AssertionError(path)
    assert _snapshot(RECORDER) == before


def _reap(root: Path) -> None:
    path = root / "map.json"
    if not path.is_file():
        return
    for step in json.loads(path.read_text(encoding="utf-8")).get("steps") or []:
        pid = step.get("pid")
        if type(pid) is int:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        done = step.get("done")
        if type(done) is str and done:
            _signal_matching(done)


def _signal_matching(text: str) -> None:
    proc = subprocess.run(["pgrep", "-f", text], capture_output=True, text=True)
    me = {os.getpid(), os.getppid()}
    for line in proc.stdout.splitlines():
        if not line.strip().isdigit():
            continue
        pid = int(line.strip())
        if pid in me:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def _snapshot(directory: Path) -> set[str]:
    found = set()
    for path in directory.rglob("*"):
        if "__pycache__" in path.parts or path.name.endswith(".pyc"):
            continue
        if path.is_file():
            found.add(str(path.relative_to(directory)))
    return found
