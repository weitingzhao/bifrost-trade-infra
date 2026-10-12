"""Five fuzz families. Default counts are a tenth; RECORDER_FULL=1 is the table.

Seed is ``20261011:<family>`` unless RECORDER_FUZZ_SEED overrides it.
RECORDER_FUZZ_N still scales the full sizes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random

from harness import WORK, LogBuilder, _chain
from model import SENSITIVE_KEY_PARTS
from publish import publish_total, shape_ok
from read import fold_total

# Both columns the coverage table promises.
COVERAGE = {
    "A": {"default": 400, "full": 4000, "row": "丙 arbitrary bytes"},
    "B": {"default": 500, "full": 5000, "row": "丙 sealed arbitrary JSON"},
    "C": {"default": 800, "full": 8000, "row": "甲 legal leaf, 丙 hostile leaf"},
    "D": {"default": 150, "full": 1500, "row": "乙 hostile arguments"},
    "E": {"default": 150, "full": 1500, "row": "丙 host and blocks"},
}
_FULL = {key: value["full"] for key, value in COVERAGE.items()}
_RATIO = 20000

_HOSTILE = (
    10**400,
    1e309,
    float("nan"),
    -0.0,
    1.0,
    True,
    None,
    "\ud800",
    "\u202e",
    "x" * 10000,
    {"k": 1},
)
_DEEP = [0]
for _ in range(12):
    _DEEP = [_DEEP]


def _count(family: str) -> int:
    raw = os.environ.get("RECORDER_FUZZ_N")
    if raw:
        return max(1, _FULL[family] * int(raw) // _RATIO)
    if os.environ.get("RECORDER_FULL") == "1":
        return _FULL[family]
    return COVERAGE[family]["default"]


def _rng(family: str) -> random.Random:
    seed = os.environ.get("RECORDER_FUZZ_SEED", "20261011")
    return random.Random(f"{seed}:{family}")


def _seal(body: bytes) -> bytes:
    digest = hashlib.sha256(body).hexdigest().encode("ascii")
    return digest + b" " + body + b"\n"


def _open() -> bytes:
    built = LogBuilder()
    built.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    return _chain(built.events)


def _publish(logs, observer, now, logs_unread=0, host="board", blocks=None):
    folded = fold_total(logs, observer, now, logs_unread)
    raw = publish_total(folded, host, blocks)
    assert type(raw) is bytes
    assert shape_ok(raw)
    doc = json.loads(raw)
    assert type(doc) is dict
    return doc


def _degraded(doc: dict) -> bool:
    if doc.get("log_invalid_at") or doc.get("torn_tail") or doc.get("log_full"):
        return True
    observer = doc.get("observer") or {}
    if observer.get("log_invalid_at") or observer.get("defects_count") or observer.get("files_unread"):
        return True
    if doc.get("incomplete"):
        return True
    for work in doc.get("works") or []:
        if work.get("log_invalid_at") or work.get("torn_tail") or work.get("log_full"):
            return True
        if work.get("defects") or work.get("defects_count") or work.get("unrecorded_runs"):
            return True
    return False


def _forbid(doc: dict) -> None:
    """No forbidden conclusion on a degraded document."""
    assert doc["ball"]["holder"] != "nobody"
    assert not (doc.get("owner_all") == [] and doc.get("fold_complete") is True and doc["ball"]["holder"] == "nobody")
    if doc.get("owner_all_cut"):
        assert "owner_all" in (doc.get("incomplete") or [])
    if doc.get("fold_complete") is True:
        assert doc["ball"]["why"] != "fold_incomplete"


def _assert_bing(doc: dict) -> None:
    assert "recorder_failed" not in doc
    assert doc["internal_errors"] == 0
    assert _degraded(doc)
    _forbid(doc)


def _assert_jia(doc: dict) -> None:
    assert "recorder_failed" not in doc
    assert doc["internal_errors"] == 0
    assert doc["fold_complete"] is True
    assert not _degraded(doc)


def _assert_yi(doc: dict, argument: str) -> None:
    assert doc["recorder_failed"]["reason"] == "invalid_argument"
    assert doc["recorder_failed"]["argument"] == argument
    assert doc["internal_errors"] == 0
    assert doc["ball"]["holder"] == "unknown"
    assert doc["fold_complete"] is False


def _family_a(rng: random.Random):
    """Arbitrary bytes: newlines, a digest prefix, an overlong line, deep brackets, a torn tail."""
    kind = rng.randrange(5)
    if kind == 0:
        blob = bytes(rng.getrandbits(8) for _ in range(rng.randrange(1, 80)))
        if b"\n" not in blob:
            blob += b"\n"
    elif kind == 1:
        blob = b"a" * 64 + b" " + bytes(rng.getrandbits(8) for _ in range(rng.randrange(1, 40))) + b"\n"
    elif kind == 2:
        blob = b"z" * 131073 + b"\n"
    elif kind == 3:
        blob = b"[" * 30 + b"]" * 30 + b"\n"
    else:
        blob = _seal(b'{"type":"note"}')[:-1]
    return ("丙", [("w1", blob)], [], 1, 0, "board", None)


def _json_value(rng: random.Random):
    kind = rng.randrange(6)
    if kind == 0:
        return _DEEP
    if kind == 1:
        return rng.choice(["1e309", "-0", "1.0", "NaN", "1e2"])
    if kind == 2:
        return "\\ud800"
    if kind == 3:
        return "".join(chr(rng.randrange(0, 32)) for _ in range(4))
    if kind == 4:
        return None
    return {"a": 1, "nested": [True, False, None]}


def _family_b(rng: random.Random):
    """A correctly sealed line whose body is not an event."""
    kind = rng.randrange(3)
    if kind == 0:
        body = json.dumps(_json_value(rng), ensure_ascii=False).encode("utf-8", "surrogatepass")
    elif kind == 1:
        body = b'{"a":1,"a":2}'
    else:
        body = json.dumps({"fuzz": _json_value(rng)}, ensure_ascii=False).encode("utf-8", "surrogateescape")
    return ("丙", [("w1", _seal(body))], [], 1, 0, "board", None)


def _family_c(rng: random.Random, index: int):
    from test_fuzz_leaves import leaf_case
    if index % 5 == 0:
        built = LogBuilder()
        built.add("work_opened", "coordinator", at=1, work_id=WORK, title="t" + str(index))
        return ("甲", [("w1", _chain(built.events))], [], 1, 0, "board", None)
    return leaf_case(index - index // 5 - 1)[0]


class _Trap:
    def __init__(self):
        self.calls = 0

    def _hit(self, *args, **kwargs):
        self.calls += 1
        return False

    __eq__ = __lt__ = __len__ = __iter__ = __bool__ = __str__ = __repr__ = __hash__ = _hit


# Built-in subclasses exercise the exact-type boundary, including nested
# tuple, name and bytes subclasses. Trap methods may never be evaluated.
class _Int(_Trap, int):
    pass


class _Float(_Trap, float):
    pass


class _Str(_Trap, str):
    pass


class _Bytes(_Trap, bytes):
    pass


class _List(_Trap, list):
    pass


class _Tuple(_Trap, tuple):
    pass


class _Dict(_Trap, dict):
    pass


def _subclass(cls, value):
    obj = cls.__new__(cls, value)
    obj.calls = 0
    return obj


def _family_d(rng: random.Random, index: int):
    trap = _Trap()
    logs = [("w1", _open())] if (index // 25) % 2 else []
    observer, now, unread = [], 1, 0
    slot = index % 25
    argument = "now"
    if slot < 6:
        now = (trap, _subclass(_Int, 1), _subclass(_Float, 1.), 10**400, math.nan, math.inf)[slot]
        trap = now if isinstance(now, _Trap) else None
    elif slot < 10:
        argument = "logs_unread"
        unread = (True, -1, _subclass(_Int, 1), trap)[slot - 6]
        trap = unread if isinstance(unread, _Trap) else None
    elif slot < 17:
        argument = "logs"
        if slot == 10:
            logs = _subclass(_List, [])
            trap = logs
        elif slot == 11:
            logs = (item for item in [trap])
        elif slot == 12:
            logs = []
            logs.append(logs)
        elif slot == 13:
            item = _subclass(_Tuple, ("w1", b""))
            logs, trap = [item], item
        elif slot == 14:
            name = _subclass(_Str, "w1")
            logs, trap = [(name, b"")], name
        elif slot == 15:
            blob = _subclass(_Bytes, b"")
            logs, trap = [("w1", blob)], blob
        else:
            logs = [("w1", trap)]
    elif slot < 23:
        argument = "observer"
        if slot == 17:
            observer = _subclass(_List, [])
            trap = observer
        elif slot == 18:
            observer = (item for item in [trap])
        elif slot == 19:
            observer = []
            observer.append(observer)
        elif slot == 20:
            observer = [trap]
        elif slot == 21:
            observer = [("2026-10-11-0001.jsonl", trap)]
        else:
            name = _subclass(_Str, "2026-10-11-0001.jsonl")
            observer, trap = [(name, b"")], name
    elif slot == 23:
        now = True
        trap = None
    else:
        argument = "logs"
        logs = _subclass(_Dict, {})
        trap = logs
    return ("乙", argument, logs, observer, now, unread, "board", None, trap)


def _e_spec(index):
    cycle = {}
    cycle["self"] = cycle
    cases = [
        ("bad\nhost", None, ["host"]),
        ("h" * 65, None, ["host"]),
        (_subclass(_Str, "board"), None, ["host"]),
        (_Trap(), None, ["host"]),
        ("board", {"recent": [True]}, ["recent"]),
        ("board", _DEEP, ["blocks"]),
        ("board", {"password": "x"}, ["blocks"]),
        ("board", {"coordinator": True}, ["coordinator"]),
        ("board", ["not", "a", "dict"], ["blocks"]),
        ("board", {"unknown_block": "x"}, ["blocks"]),
        ("board", cycle, ["blocks"]),
        ("board", _subclass(_Dict, {}), ["blocks"]),
        ("board", {"recent": _subclass(_List, [])}, ["blocks"]),
        ("board", {"recent": [_subclass(_Str, "x")]}, ["blocks"]),
        ("board", (item for item in [1]), ["blocks"]),
        ("board", {"events": {"w1": {"badstep": []}}}, ["events"]),
    ]
    return cases[index % len(cases)]


def _family_e(rng: random.Random, index: int):
    host, blocks, _expected = _e_spec(index)
    return ("丙", [("w1", _open())], [], 1, 0, host, blocks)


def _run_case(case) -> dict:
    kind = case[0]
    if kind == "乙":
        _kind, argument, logs, observer, now, unread, host, blocks, trap = case
        doc = _publish(logs, observer, now, unread, host, blocks)
        _assert_yi(doc, argument)
        if trap is not None:
            assert trap.calls == 0
        return doc
    _kind, logs, observer, now, unread, host, blocks = case
    doc = _publish(logs, observer, now, unread, host, blocks)
    if kind == "甲":
        _assert_jia(doc)
    else:
        _assert_bing(doc)
        if blocks is not None:
            keys = []

            def walk(value):
                if type(value) is dict:
                    for key, child in value.items():
                        keys.append(str(key).lower())
                        walk(child)
                elif type(value) is list:
                    for child in value:
                        walk(child)

            walk(doc)
            for part in SENSITIVE_KEY_PARTS:
                assert all(part not in key for key in keys)
    return doc


def _cases(family: str, limit: int | None = None):
    rng = _rng(family)
    n = _count(family) if limit is None else limit
    for index in range(n):
        if family == "A":
            yield _family_a(rng)
        elif family == "B":
            yield _family_b(rng)
        elif family == "C":
            yield _family_c(rng, index)
        elif family == "D":
            yield _family_d(rng, index)
        else:
            yield _family_e(rng, index)


def test_coverage_table_has_both_columns():
    assert COVERAGE["A"]["full"] == 4000
    assert COVERAGE["C"]["default"] == 800
    assert sum(_FULL.values()) == 20000
    assert (36**4 - 1) // 35 == 47989
    assert (36**3 - 1) // 35 == 1333


def test_fuzz_a_arbitrary_bytes():
    for case in _cases("A"):
        _run_case(case)


def test_fuzz_b_sealed_json():
    for case in _cases("B"):
        _run_case(case)


def test_fuzz_c_hostile_leaves():
    from test_fuzz_leaves import leaf_case, assert_leaf_document
    for index, case in enumerate(_cases("C")):
        doc = _run_case(case)
        if index % 5:
            _case, expected, _kind, _path = leaf_case(index - index // 5 - 1)
            folded = fold_total(case[1], case[2], case[3], case[4]).document()
            assert_leaf_document(folded, expected, bool(case[2]))
            if case[2]:
                assert doc["observer"]["defects_count"] == 1


def test_fuzz_d_python_arguments():
    for case in _cases("D"):
        _run_case(case)


def test_fuzz_e_host_and_blocks():
    for index, case in enumerate(_cases("E")):
        doc = _run_case(case)
        assert doc["incomplete"] == _e_spec(index)[2]
        for value in (case[5], case[6]):
            if isinstance(value, _Trap):
                assert value.calls == 0


def _sample(value, seen=None):
    seen = set() if seen is None else seen
    if type(value) in (str, bytes, int, float, bool, type(None)):
        return repr(value)[:180]
    for cls, base in ((_Int, int), (_Float, float), (_Str, str), (_Bytes, bytes)):
        if type(value) is cls:
            return f"<{cls.__name__}:{base.__repr__(value)}>"
    if id(value) in seen:
        return "<cycle>"
    seen.add(id(value))
    if type(value) in (list, tuple):
        return "[" + ", ".join(_sample(child, seen) for child in value)[:180] + "]"
    if type(value) is dict:
        return "{" + ", ".join(_sample(key, seen) + ":" + _sample(child, seen) for key, child in value.items())[:180] + "}"
    return f"<{type(value).__name__}>"


def test_fuzz_samples():
    """Three generated samples of each family, escaped."""
    for family in "ABCDE":
        samples = list(_cases(family, 11)) if family == "E" else list(_cases(family, 3))
        if family == "E":
            samples = [samples[index] for index in (0, 4, 10)]
        for nth, case in enumerate(samples):
            if case[0] == "乙":
                _kind, argument, logs, observer, now, unread, host, blocks, trap = case
            else:
                _kind, logs, observer, now, unread, host, blocks = case
                argument = "leaves" if family == "C" else ""
                if family == "C" and nth % 5:
                    from test_fuzz_leaves import leaf_case
                    _case, expected, event_kind, path = leaf_case(nth - nth // 5 - 1)
                    data = (observer or logs)[0][1]
                    leaf = json.loads(data.splitlines()[-1].split(b" ", 1)[1])
                    for key in path:
                        leaf = leaf[key]
                    argument = f"{event_kind}{path!r}={_sample(leaf)} expected={expected}"
            print(f"fuzz {family}#{nth} {case[0]} argument={argument} now={_sample(now)} unread={_sample(unread)} host={_sample(host)} blocks={_sample(blocks)} logs={_sample(logs)} observer={_sample(observer)}")


def test_fuzz_sample_two_hundred_pass_handleput(tmp_path):
    """Two hundred fixed-seed outputs, plus the fallback fixtures, go through HandlePut."""
    import subprocess
    from test_publish import FIXTURES, PLATFORM

    if not PLATFORM.is_dir():
        raise AssertionError("没有跑")
    written = 0
    for family in "ABCDE":
        for index, case in enumerate(_cases(family, 40)):
            kind = case[0]
            if kind == "乙":
                _k, _arg, logs, observer, now, unread, host, blocks, _trap = case
            else:
                _k, logs, observer, now, unread, host, blocks = case
            raw = publish_total(fold_total(logs, observer, now, unread), host if type(host) is str else None, blocks)
            (tmp_path / f"{family}-{index:02d}.json").write_bytes(raw)
            written += 1
    assert written == 200
    for name in (
        "fallback-argument.json",
        "fallback-fold-caught.json",
        "fallback-publish-caught.json",
        "fallback-last-resort.json",
    ):
        (tmp_path / name).write_bytes((FIXTURES / name).read_bytes())
    env = os.environ.copy()
    env["RECORDER_FIXTURES"] = str(tmp_path)
    env["GOMAXPROCS"] = "2"
    proc = subprocess.run(
        ["go", "test", "-count=1", "-timeout=120s", "-run", "TestRecorderFixturesPassHandlePut", "./internal/agentprogress/"],
        cwd=PLATFORM / "api",
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
