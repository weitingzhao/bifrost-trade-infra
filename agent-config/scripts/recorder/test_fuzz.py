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
from model import SCHEMAS, SENSITIVE_KEY_PARTS
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


def _placeholders(typ: str) -> dict:
    required = SCHEMAS[typ]["required"]
    fields = {"type": typ, "v": 2, "seq": 2, "prev_sha256": "", "at": 2, "by": "coordinator"}
    for name in required:
        if name in {"step_id", "run_id", "wait_id", "round_id", "work_id"}:
            fields[name] = "a1b2c3d4"
        elif name in {"text", "title", "name", "who", "command", "quote"}:
            fields[name] = "n"
        elif name in {"kind", "watch", "how", "ref_state", "can_act"}:
            fields[name] = "none"
        elif name in {"sampled_at", "started_at", "ended_at", "bytes", "number"}:
            fields[name] = 1
        elif name in {"found", "alive", "truncated"}:
            fields[name] = False
        elif name == "ref":
            fields[name] = {"kind": "none", "id": "c0ffee01"}
        elif name == "locator":
            fields[name] = {"name": "run-1"}
        elif name in {"confirmed", "failed"}:
            fields[name] = []
        else:
            fields[name] = "n"
    return fields


def _field_rows():
    rows = []
    for typ in sorted(SCHEMAS):
        for name in sorted(SCHEMAS[typ]["required"] | SCHEMAS[typ]["optional"]):
            rows.append((typ, name))
    return rows


_FIELDS = _field_rows()


def _family_c(rng: random.Random, index: int):
    """Walk every schema field. A legal leaf on an open work is 甲; anything else is 丙."""
    if index % 5 == 0:
        built = LogBuilder()
        title = "t" + str(index % 50)
        built.add("work_opened", "coordinator", at=1, work_id=WORK, title=title)
        if index % 10 == 0:
            built.events[0]["at"] = -0.0
        return ("甲", [("w1", _chain(built.events))], [], 1, 0, "board", None)
    typ, name = _FIELDS[index % len(_FIELDS)]
    leaf = rng.choice(_HOSTILE + (_DEEP,))
    opened = LogBuilder()
    opened.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    event = _placeholders(typ)
    event[name] = leaf
    try:
        body = json.dumps(event, ensure_ascii=False, allow_nan=True).encode("utf-8", "surrogatepass")
    except (ValueError, UnicodeError):
        body = b'{"type":"note","text":"\\ud800"}'
    blob = _chain(opened.events) + _seal(body)
    return ("丙", [("w1", blob)], [], 1, 0, "board", None)


class _Trap:
    def __init__(self):
        self.calls = 0

    def _hit(self, *args, **kwargs):
        self.calls += 1
        return False

    __eq__ = __lt__ = __len__ = __iter__ = __bool__ = __str__ = __repr__ = __hash__ = _hit


def _family_d(rng: random.Random, index: int):
    """Hostile Python arguments. Methods of the trap are never called."""
    trap = _Trap()
    nonempty = [("w1", _open())]
    logs = nonempty if index % 2 else []
    slot = index % 6
    if slot == 0:
        return ("乙", "now", logs, [], trap, 0, "board", None, trap)
    if slot == 1:
        return ("乙", "now", logs, [], rng.choice([10**400, math.nan, math.inf, True]), 0, "board", None, None)
    if slot == 2:
        return ("乙", "logs_unread", logs, [], 1, rng.choice([-1, True]), "board", None, None)
    if slot == 3:
        return ("乙", "logs", trap, [], 1, 0, "board", None, trap)
    if slot == 4:
        return ("乙", "logs", [trap], [], 1, 0, "board", None, trap)
    return ("乙", "observer", logs, [trap], 1, 0, "board", None, trap)


def _family_e(rng: random.Random, index: int):
    logs = [("w1", _open())]
    if index % 2 == 0:
        host = rng.choice(["bad\nhost", "h" * 65, "bad\ud800x", "has space"])
        return ("丙", logs, [], 1, 0, host, None)
    leaf = rng.choice(_HOSTILE)
    blocks = rng.choice([
        {"recent": [leaf]},
        _DEEP,
        {"password": "x"},
        {"token": {"a": 1}},
        {"coordinator": leaf},
        ["not", "a", "dict"],
        {"unknown_block": "x"},
    ])
    return ("丙", logs, [], 1, 0, "board", blocks)


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
    for case in _cases("C"):
        _run_case(case)


def test_fuzz_d_python_arguments():
    for case in _cases("D"):
        _run_case(case)


def test_fuzz_e_host_and_blocks():
    for case in _cases("E"):
        _run_case(case)


def test_fuzz_samples():
    """Three generated samples of each family, escaped."""
    for family in "ABCDE":
        for nth, case in enumerate(_cases(family, 3)):
            shown = repr(case[1] if case[0] != "乙" else case[2])
            print(f"fuzz {family}#{nth} {case[0]} {shown[:180]}")


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
