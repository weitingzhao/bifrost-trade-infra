"""Bytes become typed events at one boundary. ``fold_total`` is a public entry.

JSON is decoded only here and in the publish shape check. Nothing in this
module reads the clock, a file, or the network. Callers hand in bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from model import (
    EVENT_VERSION,
    MAX_DEPTH,
    MAX_EVENTS,
    MAX_LINE_BYTES,
    MAX_LOG_BYTES,
    MAX_LOGS,
    MAX_OBSERVER_BYTES,
    MAX_TOTAL_BYTES,
    OBS_VALID_S,
    TWO53,
    UNREAD_NAMES,
    WORK_ID_RE,
    OBSERVER_NAME_RE,
)

_WORK = re.compile(WORK_ID_RE)
_OBS_NAME = re.compile(OBSERVER_NAME_RE)
_CLASS = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
_HEX64 = re.compile(r"[0-9a-f]{64}")

# Tests replace these. Each runs inside the matching guard.
PROBES = {"line": None, "fold": None, "publish": None, "fallback": None}


def _probe(name: str) -> None:
    fn = PROBES.get(name)
    if fn is not None:
        fn()


def class_name(exc: BaseException) -> str:
    name = type(exc).__name__
    if type(name) is str and _CLASS.fullmatch(name):
        return name
    return "Other"


def _in_range(number) -> bool:
    if type(number) is int:
        return -TWO53 <= number <= TWO53
    if type(number) is float:
        if number != number:
            return False
        return number != float("inf") and number != float("-inf") and -float(TWO53) <= number <= float(TWO53)
    return False


def at_or_0(now) -> int | float:
    if (type(now) is int or type(now) is float) and _in_range(now):
        if type(now) is float and now == 0:
            return 0
        return now
    return 0


def _bad_string(text: str) -> bool:
    if type(text) is not str:
        return True
    for ch in text:
        code = ord(ch)
        if 0xD800 <= code <= 0xDFFF:
            return True
        if code <= 0x1F or 0x7F <= code <= 0x9F:
            return True
        if code in (0x2028, 0x2029) or 0x202A <= code <= 0x202E or 0x2066 <= code <= 0x2069:
            return True
    return False


def _leaf_ok(value) -> bool:
    kind = type(value)
    if kind is str:
        return not _bad_string(value)
    if kind is int or kind is float:
        return _in_range(value)
    if kind is bool:
        return True
    return False


def exact_tree(value) -> bool:
    """Walk with an explicit stack. Depth over 8, or a cycle, is invalid."""
    if type(value) not in (dict, list):
        return _leaf_ok(value)
    stack = [(value, 1, None)]
    active: set[int] = set()
    while stack:
        node, depth, kids = stack[-1]
        if kids is None:
            if depth > MAX_DEPTH or id(node) in active:
                return False
            active.add(id(node))
            if type(node) is dict:
                built = []
                for key, child in node.items():
                    if type(key) is not str or _bad_string(key):
                        return False
                    built.append(child)
                kids = built
            elif type(node) is list:
                kids = list(node)
            else:
                return False
            stack[-1] = (node, depth, kids)
        if kids:
            child = kids.pop()
            if type(child) in (dict, list):
                stack.append((child, depth + 1, None))
            elif not _leaf_ok(child):
                return False
        else:
            active.discard(id(node))
            stack.pop()
    return True


def _pairs(pairs: list):
    obj = {}
    for key, val in pairs:
        if key in obj:
            raise ValueError("dup")
        obj[key] = val
    return obj


class _BadNumber(Exception):
    pass


def _keep_number(token: str):
    return ("N", token)


def _reject_constant(_name: str):
    raise ValueError("not json")


def _token_bad(token: str) -> bool:
    if token in ("-0", "-0.0"):
        return False
    if not any(char in token for char in ".eE"):
        if len(token) > 17:
            return True
        try:
            number = int(token)
        except ValueError:
            return True
        return number < -TWO53 or number > TWO53
    try:
        number = float(token)
    except ValueError:
        return True
    if number != number or number in (float("inf"), float("-inf")):
        return True
    return abs(number) > float(TWO53)


def _convert(value):
    if type(value) is tuple and len(value) == 2 and value[0] == "N":
        token = value[1]
        if _token_bad(token):
            raise _BadNumber()
        if not any(char in token for char in ".eE"):
            return int(token)
        number = float(token)
        return 0 if number == 0 else number
    if type(value) is dict:
        return {key: _convert(child) for key, child in value.items()}
    if type(value) is list:
        return [_convert(child) for child in value]
    return value


def _int_token(value):
    if type(value) is tuple and len(value) == 2 and value[0] == "N":
        token = value[1]
        if any(char in token for char in ".eE") or len(token) > 17:
            return None
        try:
            return int(token)
        except ValueError:
            return None
    return None


def loads_strict(text: str):
    """Strict JSON object value. Duplicate keys and non-JSON constants are errors."""
    return _convert(json.loads(
        text,
        object_pairs_hook=_pairs,
        parse_int=_keep_number,
        parse_float=_keep_number,
        parse_constant=_reject_constant,
    ))


def encode_strict(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _norm(value):
    if type(value) is float and value == 0:
        return 0
    if type(value) is dict:
        return {key: _norm(child) for key, child in value.items()}
    if type(value) is list:
        return [_norm(child) for child in value]
    return value


def prescan(body: bytes) -> str | None:
    """Depth limit on bytes, before decode. A cheap count of 8 or fewer skips the scan."""
    if body.count(b"[") + body.count(b"{") <= MAX_DEPTH:
        return None
    in_string = False
    escaped = False
    depth = 0
    for byte in body:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):
            depth += 1
            if depth > MAX_DEPTH:
                return "limit_depth"
        elif byte in (0x5D, 0x7D) and depth > 0:
            depth -= 1
    return None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Line:
    kind: str  # event, defect, break
    digest: str = ""
    event: dict | None = None
    reason: str = ""
    seq: int = 0


def read_line(line: bytes, number: int, prev: str) -> Line:
    """Rows 3–10 for one line. ``number`` is the 1-based line index."""
    _probe("line")
    if len(line) > MAX_LINE_BYTES:
        return Line("break", reason="limit_line", seq=number)
    space = line.find(b" ")
    if space != 64 or _HEX64.fullmatch(line[:space].decode("ascii", "replace")) is None:
        return Line("break", reason="bad_line", seq=number)
    digest = line[:space].decode("ascii")
    body = line[space + 1 :]
    if _sha(body) != digest:
        return Line("break", reason="bad_digest", seq=number, digest=digest)
    if prescan(body):
        return Line("break", reason="limit_depth", seq=number, digest=digest)
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return Line("break", reason="bad_utf8", seq=number, digest=digest)
    try:
        raw = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_int=_keep_number,
            parse_float=_keep_number,
            parse_constant=_reject_constant,
        )
    except ValueError as exc:
        why = "dup_key" if exc.args and exc.args[0] == "dup" else "bad_json"
        return Line("break", reason=why, seq=number, digest=digest)
    except (json.JSONDecodeError, TypeError):
        return Line("break", reason="bad_json", seq=number, digest=digest)
    if type(raw) is not dict:
        return Line("break", reason="not_object", seq=number, digest=digest)
    chain = _chain(raw, number, prev)
    if chain:
        return Line("break", reason=chain, seq=number, digest=digest)
    try:
        obj = _norm(_convert(raw))
    except _BadNumber:
        return Line("defect", reason="bad_number", seq=number, digest=digest)
    if _strings_bad(obj):
        return Line("defect", reason="limit_text", seq=number, digest=digest)
    return Line("event", digest=digest, event=obj, seq=number)


def _strings_bad(value) -> bool:
    if type(value) is str:
        return _bad_string(value)
    if type(value) is dict:
        return any(_bad_string(key) or _strings_bad(child) for key, child in value.items())
    if type(value) is list:
        return any(_strings_bad(child) for child in value)
    return False


def _chain(obj: dict, number: int, prev: str) -> str | None:
    if _int_token(obj.get("seq", None)) != number:
        return "bad_chain"
    previous = obj.get("prev_sha256", None)
    if type(previous) is not str or previous != prev:
        return "bad_chain"
    if _int_token(obj.get("v", None)) != EVENT_VERSION:
        return "bad_version"
    return None


@dataclass
class ReadLog:
    name: str
    events: list = field(default_factory=list)
    defects: list = field(default_factory=list)
    broken_line: int | None = None
    broken_why: str | None = None
    torn_tail: bool = False
    full: bool = False
    catches: int = 0
    internal: list = field(default_factory=list)
    nbytes: int = 0
    digests: list = field(default_factory=list)
    view: object = None


def read_log(name: str, data: bytes, *, observer: bool = False) -> ReadLog:
    """Split one file. A torn tail is not a line. The first failing row stops a chain."""
    from contextual import _apply, _contextual, _contextual_observer
    from validate import View, _backwards, parse_event

    out = ReadLog(name=name, nbytes=len(data) if type(data) is bytes else 0)
    view = View(work_id=None if observer else name)
    out.view = view
    if type(data) is not bytes:
        out.broken_line = 1
        out.broken_why = "bad_line"
        return out
    if data.endswith(b"\n") or data == b"":
        prefix = data
    else:
        cut = data.rfind(b"\n")
        prefix = b"" if cut < 0 else data[: cut + 1]
        out.torn_tail = True
    if not prefix:
        return out
    lines = prefix.split(b"\n")[:-1]
    prev = ""
    used = 0
    for index, line in enumerate(lines):
        number = index + 1
        if number > MAX_EVENTS or used + len(line) + 1 > MAX_LOG_BYTES:
            out.full = True
            break
        used += len(line) + 1
        try:
            parsed = read_line(line, number, prev)
        except Exception as exc:
            out.catches += 1
            out.internal.append({"stage": "read", "work_id": name, "line": number, "error_class": class_name(exc)})
            out.broken_line = number
            out.broken_why = "internal"
            break
        prev = parsed.digest or prev
        if parsed.kind != "break" and parsed.digest:
            out.digests.append(parsed.digest)
        if parsed.kind == "break":
            out.broken_line = number
            out.broken_why = parsed.reason
            if parsed.reason == "limit_log":
                out.full = True
            break
        if parsed.kind == "defect":
            bucket = out.defects
            bucket.append({"seq": number, "reason": parsed.reason, "file": name} if observer else {"seq": number, "reason": parsed.reason})
            continue
        try:
            event, reason = parse_event(parsed.event)
            if reason is None:
                reason = _contextual_observer(view, event) if observer else _contextual(view, event, len(view.valid))
            if reason is not None:
                item = {"seq": number, "reason": reason}
                if observer:
                    item["file"] = name
                out.defects.append(item)
                continue
            _apply(view, event, len(view.valid))
            out.events.append(event)
        except Exception as exc:
            out.catches += 1
            out.internal.append({"stage": "read", "work_id": name, "line": number, "error_class": class_name(exc)})
            out.broken_line = number
            out.broken_why = "internal"
            break
    if not observer:
        view.defects = [{"seq": item["seq"], "reason": item["reason"]} for item in out.defects]
    view.backwards = _backwards(view.valid)
    if len(lines) >= MAX_EVENTS or used >= MAX_LOG_BYTES:
        out.full = True
    return out


def _exact_pair_list(value, argument: str) -> str | None:
    if type(value) is not list:
        return argument
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            return argument
        name, data = item
        if type(name) is not str or type(data) is not bytes:
            return argument
    return None


def exact_types(logs, observer, now, logs_unread) -> str | None:
    if type(now) is not int and type(now) is not float:
        return "now"
    if type(logs_unread) is not int:
        return "logs_unread"
    return _exact_pair_list(logs, "logs") or _exact_pair_list(observer, "observer")


def bad_number(now) -> str | None:
    if not _in_range(now):
        return "now"
    return None


def bad_count(logs_unread) -> str | None:
    if logs_unread < 0:
        return "logs_unread"
    return None


def _byte_key(name: str) -> bytes:
    return name.encode("utf-8", "surrogatepass")


def select(logs: list, observer: list):
    """Table C. Names are matched in full before any decode. Duplicates are all refused."""
    obs_bad = 0
    obs_groups: dict[str, list] = {}
    for name, data in observer:
        if _OBS_NAME.fullmatch(name) is None:
            obs_bad += 1
            continue
        obs_groups.setdefault(name, []).append(data)
    obs_dup = 0
    obs_unique = []
    for name, items in obs_groups.items():
        if len(items) > 1:
            obs_dup += len(items)
            continue
        obs_unique.append((name, items[0]))
    obs_unique.sort(key=lambda item: _byte_key(item[0]), reverse=True)
    obs_kept = []
    obs_bytes = 0
    obs_past = []
    for name, data in obs_unique:
        size = len(data)
        if obs_bytes + size > MAX_OBSERVER_BYTES:
            obs_past.append(name)
            continue
        obs_bytes += size
        obs_kept.append((name, data))
    obs_kept.sort(key=lambda item: _byte_key(item[0]))
    files_unread = obs_bad + obs_dup + len(obs_past)

    work_bad = 0
    work_groups: dict[str, list] = {}
    for name, data in logs:
        if _WORK.fullmatch(name) is None:
            work_bad += 1
            continue
        work_groups.setdefault(name, []).append((name, data))
    work_dup_names = []
    work_unique = []
    for name in sorted(work_groups, key=_byte_key):
        items = work_groups[name]
        if len(items) > 1:
            work_dup_names.extend(item[0] for item in items)
            continue
        work_unique.append(items[0])
    work_unique.sort(key=lambda item: _byte_key(item[0]))
    kept = []
    total = obs_bytes
    past = []
    for name, data in work_unique:
        size = len(data)
        if len(kept) >= MAX_LOGS or total + size > MAX_TOTAL_BYTES:
            past.append(name)
            continue
        total += size
        kept.append((name, data))
    unread = work_bad + len(work_dup_names) + len(past)
    names = (work_dup_names + past)[:UNREAD_NAMES]
    return kept, obs_kept, unread, names, files_unread


def fallback(stage: str, reason: str, argument: str | None = None, error_class: str | None = None, at=0, n: int = 0) -> dict:
    _probe("fallback")
    failed = {"stage": stage, "reason": reason}
    if reason == "invalid_argument" and argument:
        failed["argument"] = argument
    if reason == "caught" and error_class:
        failed["error_class"] = error_class
    return {
        "at": at_or_0(at) if type(at) is int or type(at) is float else 0,
        "ball": {"holder": "unknown", "why": "recorder_failed"},
        "feed": [],
        "fold_complete": False,
        "full_at": "local_board",
        "incomplete": ["feed", "owner_all", "works"],
        "internal_errors": n,
        "observations_valid_s": OBS_VALID_S,
        "owner_all": [],
        "recorder_failed": failed,
        "works": [],
    }


def LAST_FOLD() -> dict:
    return {
        "at": 0,
        "ball": {"holder": "unknown", "why": "recorder_failed"},
        "feed": [],
        "fold_complete": False,
        "full_at": "local_board",
        "incomplete": ["feed", "owner_all", "works"],
        "internal_errors": 1,
        "observations_valid_s": 180,
        "owner_all": [],
        "recorder_failed": {"reason": "caught", "stage": "fold"},
        "works": [],
    }


LAST_PUBLISH = encode_strict({
    "at": 0,
    "ball": {"holder": "unknown", "why": "recorder_failed"},
    "feed": [],
    "fold_complete": False,
    "full_at": "local_board",
    "incomplete": ["feed", "owner_all", "works"],
    "internal_errors": 1,
    "observations_valid_s": 180,
    "owner_all": [],
    "recorder_failed": {"reason": "caught", "stage": "publish"},
    "works": [],
})


def fold_total(logs, observer, now, logs_unread=0) -> dict:
    """The only fold entry. Returns a document and does not raise Exception."""
    caught = 0
    try:
        bad = exact_types(logs, observer, now, logs_unread) or bad_number(now) or bad_count(logs_unread)
        if bad:
            return fallback("fold", "invalid_argument", argument=bad, at=at_or_0(now), n=0)
        kept, obs_kept, unread, names, files_unread = select(logs, observer)
        views = []
        internal = []
        for name, data in kept:
            loaded = read_log(name, data, observer=False)
            caught += loaded.catches
            internal.extend(loaded.internal)
            views.append(loaded)
        rounds_files = []
        for name, data in obs_kept:
            loaded = read_log(name, data, observer=True)
            caught += loaded.catches
            internal.extend(loaded.internal)
            rounds_files.append(loaded)
        _probe("fold")
        from fold import fold

        doc = fold(views, rounds_files, now, logs_unread + unread, names, files_unread)
        doc["internal_errors"] = caught
        if caught:
            doc["internal"] = internal[:5]
        encode_strict(doc)
        return doc
    except Exception as exc:
        try:
            return fallback("fold", "caught", error_class=class_name(exc), at=at_or_0(now), n=caught + 1)
        except Exception:
            return LAST_FOLD()


def round_trip(event: dict) -> str | None:
    """Read one sealed line. None when the reader returns the same event."""
    from events import dump_line

    line = dump_line(event)
    parsed = read_line(line[:-1] if line.endswith(b"\n") else line, int(event["seq"]), event["prev_sha256"])
    if parsed.kind != "event" or parsed.event != _norm(event):
        return parsed.reason or "bad_line"
    return None
