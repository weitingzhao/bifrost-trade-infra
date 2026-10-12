"""Round-3 coverage the row file does not already name.

Table B at every reduction level, the five Table C permutations, the
pre-scan fixtures, family 乙 hostile objects, and family 丁 injections.
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from events import dump_line, sha256_bytes
from harness import _chain
from publish import publish_total
from read import PROBES, fold_total, prescan, read_line
from test_rows import _level_sources

_SOURCES = None


def _fresh(level: int) -> dict:
    global _SOURCES
    if _SOURCES is None:
        _SOURCES = _level_sources()
    return copy.deepcopy(_SOURCES[level])


def _publish(level: int, mutate) -> dict:
    doc = _fresh(level)
    doc["internal_errors"] = 0
    mutate(doc)
    raw = publish_total(doc, "board")
    published = json.loads(raw)
    assert "recorder_failed" not in published
    assert published.get("reduced", 0) == level
    return published


def _work_blob(published: dict) -> str:
    return json.dumps(published["works"], ensure_ascii=False)


@pytest.mark.parametrize("level", range(7), ids=lambda n: f"level_{n}")
def test_table_b_row_01_logs_unread(level):
    def plant(doc):
        doc["logs_unread"] = 3
        doc["logs_unread_names"] = ["z"]
        doc["fold_complete"] = False

    published = _publish(level, plant)
    assert published["logs_unread"] == 3
    assert published["logs_unread_names"] == ["z"]
    assert published["fold_complete"] is False


@pytest.mark.parametrize("level", range(7), ids=lambda n: f"level_{n}")
def test_table_b_row_02_log_invalid_at(level):
    def plant(doc):
        doc["fold_complete"] = False
        for work in doc["works"]:
            work["log_invalid_at"] = 4
            work["log_invalid_why"] = "bad_chain"

    published = _publish(level, plant)
    for work in published["works"]:
        assert work["log_invalid_at"] == 4
        assert work["log_invalid_why"] == "bad_chain"


@pytest.mark.parametrize("level", range(7), ids=lambda n: f"level_{n}")
def test_table_b_row_06_log_full(level):
    def plant(doc):
        for work in doc["works"]:
            work["log_full"] = True

    published = _publish(level, plant)
    for work in published["works"]:
        assert work["log_full"] is True


@pytest.mark.parametrize("level", range(7), ids=lambda n: f"level_{n}")
def test_table_b_row_07_defects(level):
    defects = [{"seq": 1, "reason": "unknown_field"}]

    def plant(doc):
        for work in doc["works"]:
            work["defects"] = defects

    published = _publish(level, plant)
    for work in published["works"]:
        if "defects" in work:
            assert work["defects"] == defects
        else:
            assert work["defects_count"] == 1


@pytest.mark.parametrize("level", range(7), ids=lambda n: f"level_{n}")
def test_table_b_row_08_unknown_step(level):
    def plant(doc):
        for work in doc["works"]:
            step = work["steps"][0]
            step["state"] = "unknown"
            step["reason"] = "no_observation"
            step["last_seen"] = {"alive": True, "at": 1}

    published = _publish(level, plant)
    for work in published["works"]:
        if "steps" in work:
            step = next(item for item in work["steps"] if item.get("state") == "unknown")
            assert step["reason"] == "no_observation"
            assert step["last_seen"]["at"] == 1
        else:
            assert work["state_counts"]["unknown"] >= 1
            assert "no_observation" in work["unknown_reasons"]


@pytest.mark.parametrize("level", range(7), ids=lambda n: f"level_{n}")
def test_table_b_row_09_owner_unknown(level):
    def plant(doc):
        if not doc["owner_all"]:
            doc["owner_all"] = [{
                "source": "record",
                "can_act": "yes",
                "ref": {"kind": "approval", "id": "appr_0123456789abcdef"},
                "works": [],
            }]
        item = doc["owner_all"][0]
        item["can_act"] = "unknown"
        item["reason"] = "not_confirmed"
        item["last_seen"] = {"ref_state": "pending", "at": 1}

    published = _publish(level, plant)
    kept = [item for item in published["owner_all"] if item.get("can_act") == "unknown"]
    if kept:
        assert kept[0]["reason"] == "not_confirmed"
        assert kept[0]["last_seen"]["at"] == 1
    else:
        assert published.get("owner_all_cut", 0) >= 1


@pytest.mark.parametrize("level", range(7), ids=lambda n: f"level_{n}")
def test_table_b_row_10_observer_and_clock(level):
    def plant(doc):
        doc["observer"] = {
            "defects": [{"file": "2026-10-11-0001.jsonl", "seq": 1, "reason": "bad_value"}],
            "log_invalid_at": {"file": "2026-10-11-0001.jsonl", "line": 2, "why": "bad_json"},
            "files_unread": 2,
        }
        doc["clock"] = {"reader_behind": True}

    published = _publish(level, plant)
    assert published["observer"]["files_unread"] == 2
    assert published["observer"]["log_invalid_at"]["why"] == "bad_json"
    assert published["observer"]["defects_count"] == 1
    assert "defects" not in published["observer"]
    assert published["clock"]["reader_behind"] is True


@pytest.mark.parametrize("level", range(7), ids=lambda n: f"level_{n}")
def test_table_b_row_11_internal_errors(level):
    def plant(doc):
        doc["internal_errors"] = 2
        doc["internal"] = [{"stage": "read", "work_id": "w1", "line": 1, "error_class": "RecursionError"}]

    published = _publish(level, plant)
    assert published["internal_errors"] == 2
    assert published["internal"][0]["error_class"] == "RecursionError"


@pytest.mark.parametrize("level", range(7), ids=lambda n: f"level_{n}")
def test_table_b_row_12_conservation(level):
    doc = _fresh(level)
    doc["internal_errors"] = 0
    owners = len(doc["owner_all"])
    feed = len(doc["feed"])
    step_counts = {
        work["work_id"]: len(work.get("steps") or [])
        for work in doc["works"]
    }
    raw = publish_total(doc, "board")
    published = json.loads(raw)
    assert published.get("reduced", 0) == level
    omitted = published.get("omitted_works") or {"open": 0, "closed": 0}
    listed_closed = sum(1 for work in published["works"] if "closed_claim" in work)
    listed_open = len(published["works"]) - listed_closed
    total = published["works_total"]
    assert listed_open + omitted.get("open", 0) == total["open"]
    assert listed_closed + omitted.get("closed", 0) == total["closed"]
    assert len(published.get("owner_all") or []) + (published.get("owner_all_cut") or 0) == owners
    assert len(published.get("feed") or []) + (published.get("feed_cut") or 0) == feed
    for work in published["works"]:
        if "steps_total" in work and "steps" in work:
            dropped = sum((work.get("omitted") or {}).values())
            assert len(work["steps"]) + dropped == work["steps_total"] == step_counts[work["work_id"]]
        if "state_counts" in work:
            assert sum(work["state_counts"].values()) == step_counts[work["work_id"]]


@pytest.mark.parametrize("level", [0, 1, 2, 4, 6], ids=lambda n: f"level_{n}")
def test_table_b_row_13_gap_follows_the_step(level):
    def plant(doc):
        for work in doc["works"]:
            work["steps"][0]["gap"] = True

    published = _publish(level, plant)
    for work in published["works"]:
        if "steps" in work:
            assert any(step.get("gap") is True for step in work["steps"])


def test_table_b_row_04_recorder_failed_is_not_reduced():
    doc = fold_total([], [], True)
    raw = publish_total(doc)
    published = json.loads(raw)
    assert "reduced" not in published
    assert published["recorder_failed"]["reason"] == "invalid_argument"
    assert published["ball"] == {"holder": "unknown", "why": "recorder_failed"}
    assert published["works"] == []
    assert published["fold_complete"] is False


def _same(left, right) -> None:
    assert json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def test_table_c_perm_01_two_hundred_one_logs_either_order():
    logs = [(f"n{index:03d}", b"") for index in range(201)]
    forward = fold_total(logs, [], 1)
    backward = fold_total(list(reversed(logs)), [], 1)
    _same(forward, backward)
    assert forward["logs_unread"] == 1
    assert forward["fold_complete"] is False


def test_table_c_perm_02_two_hundred_one_logs_plus_caller_unread_either_order():
    logs = [(f"n{index:03d}", b"") for index in range(201)]
    forward = fold_total(logs, [], 1, 3)
    backward = fold_total(list(reversed(logs)), [], 1, 3)
    _same(forward, backward)
    assert forward["logs_unread"] == 4


def test_table_c_perm_03_duplicate_work_names_either_order():
    first = _chain([{"type": "note", "at": 1, "by": "coordinator", "text": "a"}])
    second = _chain([{"type": "note", "at": 1, "by": "coordinator", "text": "b"}])
    left = [("w1", first), ("w1", second)]
    forward = fold_total(left, [], 1)
    backward = fold_total(list(reversed(left)), [], 1)
    _same(forward, backward)
    assert forward["logs_unread"] == 2
    assert forward["works"] == []


def test_table_c_perm_04_duplicate_observer_names_either_order():
    name = "2026-10-11-0001.jsonl"
    confirmed = _chain([{
        "type": "observer_round", "at": 1, "by": "observer", "round_id": "ab12cd34",
        "started_at": 1, "ended_at": 1, "confirmed": ["step:w1/a1b2c3d4"], "failed": [],
    }])
    failed = _chain([{
        "type": "observer_round", "at": 1, "by": "observer", "round_id": "ab12cd34",
        "started_at": 1, "ended_at": 1, "confirmed": [],
        "failed": [{"key": "step:w1/a1b2c3d4", "error": "timeout"}],
    }])
    pair = [(name, confirmed), (name, failed)]
    forward = fold_total([], pair, 1)
    backward = fold_total([], list(reversed(pair)), 1)
    _same(forward, backward)
    assert forward["observer"]["files_unread"] == 2


def test_table_c_perm_05_lone_surrogate_name_either_order():
    bad = "w\ud800"
    logs = [(bad, b""), ("ok", b"")]
    forward = fold_total(logs, [], 1)
    backward = fold_total(list(reversed(logs)), [], 1)
    _same(forward, backward)
    assert forward["logs_unread"] == 1
    assert [work["work_id"] for work in forward["works"]] == ["ok"]


def _sealed(body: bytes) -> bytes:
    return sha256_bytes(body).encode("ascii") + b" " + body


def test_prescan_exactly_8_levels_is_readable():
    body = ('{"at":1,"by":"coordinator","prev_sha256":"","seq":1,"text":"n","type":"note","v":2,"x":'
            + "[" * 7 + "]" * 7 + "}").encode()
    assert body.count(b"[") + body.count(b"{") == 8
    assert prescan(body) is None
    parsed = read_line(_sealed(body), 1, "")
    assert parsed.kind != "break" or parsed.reason != "limit_depth"


def test_prescan_exactly_9_levels_is_limit_depth():
    body = ('{"at":1,"by":"coordinator","prev_sha256":"","seq":1,"text":"n","type":"note","v":2,"x":'
            + "[" * 8 + "]" * 8 + "}").encode()
    assert prescan(body) == "limit_depth"
    parsed = read_line(_sealed(body), 1, "")
    assert parsed.kind == "break" and parsed.reason == "limit_depth"


def test_prescan_brackets_inside_strings_are_not_depth():
    body = b'{"at":1,"by":"coordinator","prev_sha256":"","seq":1,"text":"' + b"[" * 20 + b'","type":"note","v":2}'
    assert prescan(body) is None
    parsed = read_line(_sealed(body), 1, "")
    assert parsed.reason != "limit_depth"


def test_prescan_escape_parity_does_not_end_the_string():
    body = b'{"at":1,"by":"coordinator","prev_sha256":"","seq":1,"text":"\\"' + b"[" * 20 + b'","type":"note","v":2}'
    assert prescan(body) is None


def test_prescan_unterminated_string_is_bad_json_not_a_catch():
    body = b'{"at":1,"by":"coordinator","prev_sha256":"","seq":1,"text":"' + b"[" * 20
    assert prescan(body) is None
    parsed = read_line(_sealed(body), 1, "")
    assert parsed.kind == "break" and parsed.reason == "bad_json"


def test_prescan_invalid_utf8_around_brackets_is_bad_utf8():
    body = b'{"at":1,"text":"' + b"\xff" + b"[" * 20 + b'"}'
    assert prescan(body) is None
    parsed = read_line(_sealed(body), 1, "")
    assert parsed.kind == "break" and parsed.reason == "bad_utf8"


class _Hostile:
    def __eq__(self, other):
        raise AssertionError("eq")

    def __hash__(self):
        raise AssertionError("hash")

    def __iter__(self):
        raise AssertionError("iter")

    def __len__(self):
        raise AssertionError("len")

    def __str__(self):
        raise AssertionError("str")

    def __bool__(self):
        raise AssertionError("bool")


def test_family_yi_hostile_logs_calls_nothing():
    doc = fold_total(_Hostile(), [], 1)
    assert doc["recorder_failed"]["reason"] == "invalid_argument"
    assert doc["recorder_failed"]["argument"] == "logs"
    assert doc["internal_errors"] == 0


def test_family_yi_hostile_now_calls_nothing():
    doc = fold_total([], [], _Hostile())
    assert doc["recorder_failed"] == {"stage": "fold", "reason": "invalid_argument", "argument": "now"}
    assert doc["internal_errors"] == 0


class _Boom(Exception):
    pass


def _note() -> bytes:
    return dump_line({
        "type": "note", "v": 2, "seq": 1, "prev_sha256": "", "at": 1, "by": "coordinator", "text": "n",
    })


def _arm(name, exc):
    def boom():
        raise exc
    PROBES[name] = boom


def _clear():
    for key in PROBES:
        PROBES[key] = None


def test_family_ding_line_recursion_error():
    _arm("line", RecursionError("x"))
    try:
        doc = fold_total([("w1", _note())], [], 1)
    finally:
        _clear()
    assert "recorder_failed" not in doc
    assert doc["internal_errors"] == 1
    assert doc["works"][0]["log_invalid_why"] == "internal"


def test_family_ding_line_memory_error():
    _arm("line", MemoryError("x"))
    try:
        doc = fold_total([("w1", _note())], [], 1)
    finally:
        _clear()
    assert doc["internal_errors"] == 1
    assert doc["works"][0]["log_invalid_why"] == "internal"


def test_family_ding_line_custom_exception():
    _arm("line", _Boom())
    try:
        doc = fold_total([("w1", _note())], [], 1)
    finally:
        _clear()
    assert doc["internal_errors"] == 1
    assert doc["internal"][0]["error_class"] == "_Boom"


def test_family_ding_fold_recursion_error():
    _arm("fold", RecursionError("x"))
    try:
        doc = fold_total([], [], 1)
    finally:
        _clear()
    assert doc["recorder_failed"]["reason"] == "caught"
    assert doc["recorder_failed"]["error_class"] == "RecursionError"
    assert doc["internal_errors"] == 1


def test_family_ding_fold_memory_error():
    _arm("fold", MemoryError())
    try:
        doc = fold_total([], [], 1)
    finally:
        _clear()
    assert doc["recorder_failed"]["error_class"] == "MemoryError"


def test_family_ding_fold_custom_exception():
    _arm("fold", _Boom())
    try:
        doc = fold_total([], [], 1)
    finally:
        _clear()
    assert doc["recorder_failed"]["error_class"] == "_Boom"


def test_family_ding_publish_recursion_error():
    doc = fold_total([], [], 1)
    _arm("publish", RecursionError("x"))
    try:
        raw = publish_total(doc, "board")
    finally:
        _clear()
    published = json.loads(raw)
    assert published["recorder_failed"]["stage"] == "publish"
    assert published["recorder_failed"]["error_class"] == "RecursionError"


def test_family_ding_publish_memory_error():
    doc = fold_total([], [], 1)
    _arm("publish", MemoryError())
    try:
        raw = publish_total(doc, "board")
    finally:
        _clear()
    assert b'"error_class":"MemoryError"' in raw


def test_family_ding_publish_custom_exception():
    doc = fold_total([], [], 1)
    _arm("publish", _Boom())
    try:
        raw = publish_total(doc, "board")
    finally:
        _clear()
    assert b'"error_class":"_Boom"' in raw


def test_family_ding_fallback_recursion_error():
    _arm("fallback", RecursionError("x"))
    try:
        doc = fold_total([], [], True)
    finally:
        _clear()
    assert doc["recorder_failed"]["reason"] == "caught"
    assert doc["internal_errors"] == 1
    assert "argument" not in doc["recorder_failed"]


def test_family_ding_fallback_memory_error():
    _arm("fallback", MemoryError())
    try:
        doc = fold_total([], [], True)
    finally:
        _clear()
    assert doc["internal_errors"] == 1
    assert doc["recorder_failed"]["stage"] == "fold"


def test_family_ding_fallback_custom_exception():
    _arm("fallback", _Boom())
    try:
        raw = publish_total({"at": 0}, "board")
    finally:
        _clear()
    published = json.loads(raw)
    assert published["recorder_failed"]["stage"] == "publish"
    assert published["internal_errors"] == 1


def test_family_ding_keyboard_interrupt_from_line():
    _arm("line", KeyboardInterrupt())
    try:
        with pytest.raises(KeyboardInterrupt):
            fold_total([("w1", _note())], [], 1)
    finally:
        _clear()


def test_family_ding_keyboard_interrupt_from_publish():
    doc = fold_total([], [], 1)
    _arm("publish", KeyboardInterrupt())
    try:
        with pytest.raises(KeyboardInterrupt):
            publish_total(doc, "board")
    finally:
        _clear()


def test_family_ding_keyboard_interrupt_from_fallback():
    _arm("fallback", KeyboardInterrupt())
    try:
        with pytest.raises(KeyboardInterrupt):
            fold_total([], [], True)
    finally:
        _clear()


def test_static_json_loads_stays_in_read_and_publish():
    root = Path(__file__).resolve().parent
    allowed = {"read.py", "publish.py"}
    for path in root.glob("*.py"):
        if path.name.startswith("test_"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "loads" and isinstance(node.func.value, ast.Name) and node.func.value.id == "json":
                    assert path.name in allowed
    for path in root.glob("*.py"):
        assert sum(1 for _ in path.open(encoding="utf-8")) <= 800
