"""``publish_view(document, host) -> document`` inside the platform's limits.

Pure. The bytes are the compact UTF-8 JSON a publisher would send, host
already inside it, with no second parse. Commands are not in that JSON:
the item keeps ``commands_at`` and ``commands_count`` instead.
"""

from __future__ import annotations

import copy
import json
import math
import re

from model import (
    PLATFORM_HOST_RE,
    PLATFORM_MAX_FEED,
    PLATFORM_MAX_STEPS,
    PLATFORM_MAX_WORKS,
    PUBLISH_FEED_REDUCED,
    PUBLISH_MAX_FEED,
    PUBLISH_MAX_OWNER_ALL,
    PUBLISH_TARGET_BYTES,
    PUBLISH_UNFINISHED_KEEP,
    PUBLISH_UNKNOWN_REASONS,
    SENSITIVE_KEY_PARTS,
)

_HOST = re.compile(PLATFORM_HOST_RE)


def _host_decision(host) -> str:
    """'ok', 'omit', or 'bad'. Exact type before any comparison."""
    if host is None:
        return "omit"
    if type(host) is not str:
        return "bad"
    if host == "":
        return "omit"
    if _HOST.fullmatch(host):
        return "ok"
    return "bad"


_STEP_ORDER = {
    "unknown": 0,
    "dead": 1,
    "failed": 2,
    "quiet": 3,
    "slow": 4,
    "running": 5,
    "waiting": 6,
    "done": 7,
}
_ENDED = {"done", "failed"}
_SUMMARY_STATES = ("dead", "done", "failed", "quiet", "running", "slow", "unknown", "waiting")


def _publish_observer(doc: dict) -> None:
    """Table B row 10: the observer defect list is published as a count."""
    observer = doc.get("observer")
    if type(observer) is not dict or "defects" not in observer:
        return
    defects = observer.get("defects")
    observer["defects_count"] = len(defects) if type(defects) is list else 0
    observer.pop("defects", None)


def publish_view(document: dict, host: str | None = None, blocks=None) -> dict:
    doc = copy.deepcopy(document) if type(document) is dict else {"at": 0}
    _publish_observer(doc)
    doc = _drop_nulls(doc)
    _drop_sensitive(doc)
    block_missing = _merge_blocks(doc, blocks)
    host_kind = _host_decision(host)
    if host_kind == "ok":
        doc["host"] = host
    else:
        doc.pop("host", None)
    original_works = list(doc.get("works") or [])
    original_owner = list(doc.get("owner_all") or [])
    original_feed = list(doc.get("feed") or [])
    original_feed_len = len(original_feed)
    owner_ids = _owner_ids(original_owner)
    kept_works, omitted_works = _trim_works(original_works, owner_ids)
    for work in kept_works:
        _trim_steps(work)
    feed_cap = min(PUBLISH_MAX_FEED, PLATFORM_MAX_FEED)
    feed = original_feed[-feed_cap:] if len(original_feed) > feed_cap else list(original_feed)
    owner, structural_cut = _trim_owner(original_owner)
    owner = [_strip_commands(item) for item in owner]
    doc["works"] = kept_works
    doc["feed"] = feed
    doc["owner_all"] = owner
    doc["works_total"] = _works_total(original_works)
    incomplete = list(block_missing)
    if host_kind == "bad":
        incomplete.append("host")
    if omitted_works["open"] or omitted_works["closed"]:
        doc["omitted_works"] = omitted_works
        if omitted_works["open"]:
            incomplete.append("works")
    else:
        doc.pop("omitted_works", None)
    if structural_cut:
        doc["owner_all_cut"] = structural_cut
        incomplete.append("owner_all")
    else:
        doc.pop("owner_all_cut", None)
    if len(original_feed) > feed_cap:
        incomplete.append("feed")
    doc["incomplete"] = sorted(set(incomplete))
    if not doc["incomplete"]:
        doc.pop("incomplete")
    commands_stripped = any("commands" in item for item in original_owner)
    cut = _anything_cut(doc, original_works, original_owner, original_feed) or commands_stripped or bool(block_missing)
    level = _fit(doc, owner, original_feed_len, cut)
    if level:
        doc["reduced"] = level
        cut = True
    if doc.get("incomplete"):
        cut = True
    if original_feed_len > len(doc.get("feed") or []):
        doc["feed_cut"] = original_feed_len - len(doc.get("feed") or [])
        inc = list(doc.get("incomplete") or [])
        inc.append("feed")
        doc["incomplete"] = sorted(set(inc))
        cut = True
    if cut:
        doc["full_at"] = "local_board"
    else:
        doc.pop("full_at", None)
        doc.pop("reduced", None)
    from survive import apply_keep

    apply_keep(doc, level)
    return _public(doc)


def encoded(document: dict) -> bytes:
    """The bytes a publisher sends. Keys used only while reducing are left out."""
    return json.dumps(_public(document), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _stamp(doc: dict, level: int, original_feed_len: int, already_cut: bool) -> dict:
    """The document publish_view would return at this reduction level."""
    trial = copy.deepcopy(doc)
    cut = already_cut or bool(level)
    if level:
        trial["reduced"] = level
    current = len(trial.get("feed") or [])
    if original_feed_len > current:
        trial["feed_cut"] = original_feed_len - current
        inc = list(trial.get("incomplete") or [])
        inc.append("feed")
        trial["incomplete"] = sorted(set(inc))
        cut = True
    if cut:
        trial["full_at"] = "local_board"
    else:
        trial.pop("full_at", None)
        trial.pop("reduced", None)
    return trial


def _nbytes(doc: dict, level: int, original_feed_len: int, already_cut: bool) -> int:
    return len(encoded(_stamp(doc, level, original_feed_len, already_cut)))


def _fit(doc: dict, owner_items: list, original_feed_len: int, already_cut: bool) -> int:
    """Apply byte reductions in order. Return the level used, or 0.

    Each check measures the bytes after reduced, full_at, and feed_cut.
    """
    if _nbytes(doc, 0, original_feed_len, already_cut) <= PUBLISH_TARGET_BYTES:
        return 0
    if _shed_blocks(doc, original_feed_len, already_cut):
        already_cut = True
        if _nbytes(doc, 0, original_feed_len, already_cut) <= PUBLISH_TARGET_BYTES:
            return 0
    _level1(doc)
    if _nbytes(doc, 1, original_feed_len, already_cut) <= PUBLISH_TARGET_BYTES:
        return 1
    doc["feed"] = list(doc.get("feed") or [])[-PUBLISH_FEED_REDUCED:]
    if _nbytes(doc, 2, original_feed_len, already_cut) <= PUBLISH_TARGET_BYTES:
        return 2
    _level3(doc)
    if _nbytes(doc, 3, original_feed_len, already_cut) <= PUBLISH_TARGET_BYTES:
        return 3
    _level4(doc)
    if _nbytes(doc, 4, original_feed_len, already_cut) <= PUBLISH_TARGET_BYTES:
        return 4
    _level5(doc)
    if _nbytes(doc, 5, original_feed_len, already_cut) <= PUBLISH_TARGET_BYTES:
        return 5
    _level6(doc, owner_items, original_feed_len, already_cut)
    return 6


def _level1(doc: dict) -> None:
    for work in doc.get("works") or []:
        if _is_summary(work):
            continue
        for step in work.get("steps") or []:
            if step.get("state") in _ENDED:
                for key in ("note", "quote", "command"):
                    step.pop(key, None)


def _level3(doc: dict) -> None:
    works = []
    for work in doc.get("works") or []:
        if "closed_claim" in work and not _is_summary(work):
            works.append(_summary(work))
        else:
            works.append(work)
    doc["works"] = works


def _level4(doc: dict) -> None:
    for work in doc.get("works") or []:
        if _is_summary(work):
            continue
        all_steps = list(work.get("_all_steps") or work.get("steps") or [])
        unfinished = [step for step in all_steps if step.get("state") not in _ENDED]
        unfinished.sort(key=lambda step: _step_sort(step, 0))
        kept = []
        for step in unfinished[:PUBLISH_UNFINISHED_KEEP]:
            step = copy.deepcopy(step)
            step.pop("note", None)
            kept.append(step)
        work["steps"] = kept
        work["steps_total"] = len(all_steps)
        omitted = {state: 0 for state in _SUMMARY_STATES}
        for step in all_steps:
            state = step.get("state") if step.get("state") in omitted else "unknown"
            omitted[state] += 1
        for step in kept:
            state = step.get("state") if step.get("state") in omitted else "unknown"
            omitted[state] -= 1
        if any(omitted.values()):
            work["omitted"] = omitted
        else:
            work.pop("omitted", None)


def _level5(doc: dict) -> None:
    doc["works"] = [_summary(work) if not _is_summary(work) else work for work in doc.get("works") or []]


def _level6(doc: dict, items: list, original_feed_len: int, already_cut: bool) -> None:
    skeleton = copy.deepcopy(doc)
    skeleton["owner_all"] = []
    skeleton.pop("owner_all_cut", None)
    prior = doc.get("owner_all_cut") or 0
    # ``items`` is the structurally trimmed list. prior is how many the
    # fold had beyond that list. Level 6 drops more from the end of ``items``.
    kept = []
    for item in items:
        trial = copy.deepcopy(skeleton)
        trial["owner_all"] = kept + [item]
        dropped = len(items) - (len(kept) + 1)
        cut = prior + dropped
        if cut:
            trial["owner_all_cut"] = cut
            trial["incomplete"] = sorted(set([*(trial.get("incomplete") or []), "owner_all"]))
        if _nbytes(trial, 6, original_feed_len, already_cut) <= PUBLISH_TARGET_BYTES:
            kept.append(item)
        else:
            break
    dropped = len(items) - len(kept)
    doc["owner_all"] = kept
    cut = prior + dropped
    if cut:
        doc["owner_all_cut"] = cut
        doc["incomplete"] = sorted(set([*(doc.get("incomplete") or []), "owner_all"]))
    elif "owner_all_cut" in doc and not prior:
        doc.pop("owner_all_cut", None)


def _summary(work: dict) -> dict:
    counts = work.get("_state_counts") or _counts(work.get("_all_steps") or work.get("steps") or [], None)
    reasons = []
    seen = set()
    for step in work.get("_all_steps") or work.get("steps") or []:
        if step.get("state") != "unknown":
            continue
        reason = step.get("reason")
        if isinstance(reason, str) and reason not in seen:
            seen.add(reason)
            reasons.append(reason)
    listed = reasons[:PUBLISH_UNKNOWN_REASONS]
    out = {
        "work_id": work.get("work_id"),
        "title": work.get("title") or "",
        "state_counts": counts,
        "unknown_reasons": listed,
        "unknown_reasons_omitted": max(0, len(reasons) - len(listed)),
        "defects_count": len(work.get("defects") or []),
    }
    for key in ("log_invalid_at", "log_invalid_why", "log_full", "torn_tail", "unrecorded_runs", "closed_claim"):
        if key in work:
            out[key] = work[key]
    return out


def _is_summary(work: dict) -> bool:
    return "state_counts" in work and "steps" not in work


def _trim_works(works: list, owner_ids: set) -> tuple[list, dict]:
    decorated = []
    for index, work in enumerate(works):
        work = copy.deepcopy(work)
        work["_all_steps"] = list(work.get("steps") or [])
        work["_state_counts"] = _counts(work["_all_steps"], None)
        decorated.append(( _work_group(work, owner_ids), index, work))
    decorated.sort(key=lambda item: (*item[0], item[1]))
    ordered = [item[2] for item in decorated]
    kept = ordered[:PLATFORM_MAX_WORKS]
    omitted = {"open": 0, "closed": 0}
    for work in ordered[PLATFORM_MAX_WORKS:]:
        if "closed_claim" in work:
            omitted["closed"] += 1
        else:
            omitted["open"] += 1
    return kept, omitted


def _work_group(work: dict, owner_ids: set):
    last = work.get("last_at") or 0
    if "closed_claim" in work:
        closed_at = work.get("_closed_at")
        if not isinstance(closed_at, (int, float)) or isinstance(closed_at, bool):
            closed_at = last
        return (3, -closed_at, work.get("work_id") or "")
    states = {step.get("state") for step in work.get("steps") or []}
    if work.get("work_id") in owner_ids or states & {"unknown", "dead", "failed", "quiet"}:
        return (0, -last)
    if states & {"running", "slow"}:
        return (1, -last)
    return (2, -last)


def _trim_steps(work: dict) -> None:
    steps = list(work.get("steps") or [])
    work["steps_total"] = len(steps)
    if len(steps) <= PLATFORM_MAX_STEPS:
        return
    ranked = sorted(enumerate(steps), key=lambda pair: _step_sort(pair[1], pair[0]))
    kept_ids = {id(steps[index]) for index, _step in ranked[:PLATFORM_MAX_STEPS]}
    kept = [step for step in (steps[index] for index, _step in ranked[:PLATFORM_MAX_STEPS])]
    omitted = {state: 0 for state in _SUMMARY_STATES}
    for step in steps:
        if id(step) in kept_ids:
            continue
        state = step.get("state")
        if state not in omitted:
            state = "unknown"
        omitted[state] += 1
    work["steps"] = kept
    work["omitted"] = omitted


def _step_sort(step: dict, index: int):
    state = step.get("state")
    if state not in _STEP_ORDER:
        state = "unknown"
    superseded_ended = 1 if step.get("superseded_by") and step.get("state") in _ENDED else 0
    if state == "done":
        third = -(step.get("ended") or 0)
    else:
        third = index
    return (superseded_ended, _STEP_ORDER[state], third)


def _trim_owner(items: list) -> tuple[list, int]:
    if len(items) <= PUBLISH_MAX_OWNER_ALL:
        return list(items), 0
    return list(items[:PUBLISH_MAX_OWNER_ALL]), len(items) - PUBLISH_MAX_OWNER_ALL


def _strip_commands(item: dict) -> dict:
    if "commands" not in item:
        return item
    item = copy.deepcopy(item)
    count = len(item.pop("commands") or [])
    item["commands_at"] = "local_board"
    item["commands_count"] = count
    return item


def _counts(steps: list, omitted: dict | None) -> dict:
    counts = {state: 0 for state in _SUMMARY_STATES}
    for step in steps:
        state = step.get("state")
        if state not in counts:
            state = "unknown"
        counts[state] += 1
    for state, count in (omitted or {}).items():
        if state in counts:
            counts[state] += count
        else:
            counts["unknown"] += count
    return counts


def _works_total(works: list) -> dict:
    total = {"open": 0, "closed": 0}
    for work in works:
        if isinstance(work, dict) and "closed_claim" in work:
            total["closed"] += 1
        else:
            total["open"] += 1
    return total


def _owner_ids(items: list) -> set:
    found = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        for piece in item.get("works") or []:
            if isinstance(piece, dict) and piece.get("work_id"):
                found.add(piece["work_id"])
    return found


def _anything_cut(doc, works, owner, feed) -> bool:
    if len(works) > PLATFORM_MAX_WORKS or len(owner) > PUBLISH_MAX_OWNER_ALL or len(feed) > PUBLISH_MAX_FEED:
        return True
    for work in works:
        if len(work.get("steps") or []) > PLATFORM_MAX_STEPS:
            return True
    return False


def _drop_nulls(value):
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            if child is None:
                continue
            out[key] = _drop_nulls(child)
        return out
    if isinstance(value, list):
        return [_drop_nulls(child) for child in value if child is not None]
    if isinstance(value, float) and not math.isfinite(value):
        return 0
    return value


def _drop_sensitive(value) -> None:
    if isinstance(value, dict):
        for key in list(value):
            folded = str(key).lower()
            if any(part in folded for part in SENSITIVE_KEY_PARTS):
                value.pop(key)
                continue
            _drop_sensitive(value[key])
    elif isinstance(value, list):
        for child in value:
            _drop_sensitive(child)


def _public(value):
    if isinstance(value, dict):
        return {key: _public(child) for key, child in value.items() if not str(key).startswith("_")}
    if isinstance(value, list):
        return [_public(child) for child in value]
    return value


_BLOCK_ORDER = ("events", "recent", "usage", "graph", "queue", "roadmap", "coordinator")
_BLOCK_KEYS = set(_BLOCK_ORDER)


def _note(doc: dict, name: str) -> None:
    inc = list(doc.get("incomplete") or [])
    inc.append(name)
    doc["incomplete"] = sorted(set(inc))


def _shed_blocks(doc: dict, original_feed_len: int, already_cut: bool) -> bool:
    changed = False
    has_events = any(
        "events" in step
        for work in doc.get("works") or []
        for step in work.get("steps") or []
    )
    if has_events and _nbytes(doc, 0, original_feed_len, True) > PUBLISH_TARGET_BYTES:
        _strip_step_events(doc)
        _note(doc, "events")
        changed = True
    for key in ("recent", "usage", "graph", "queue", "roadmap", "coordinator"):
        if key in doc and _nbytes(doc, 0, original_feed_len, True) > PUBLISH_TARGET_BYTES:
            doc.pop(key, None)
            _note(doc, key)
            changed = True
    return changed


def _strip_step_events(doc: dict) -> bool:
    found = False
    for work in doc.get("works") or []:
        for step in work.get("steps") or []:
            if "events" in step:
                step.pop("events")
                found = True
    return found


def _merge_blocks(doc: dict, blocks) -> list:
    if blocks is None:
        return []
    if type(blocks) is not dict:
        return ["blocks"]
    from read import exact_tree

    if not exact_tree(blocks):
        return ["blocks"]
    missing = []
    for key in blocks:
        if type(key) is not str or key not in _BLOCK_KEYS:
            folded = key.lower() if type(key) is str else ""
            if any(part in folded for part in SENSITIVE_KEY_PARTS):
                missing.append("blocks")
            else:
                missing.append(key if type(key) is str else "blocks")
            continue
        value = blocks[key]
        if not exact_tree(value) or not _block_ok(key, value):
            missing.append(key)
            continue
        if key == "events":
            if not _attach_events(doc, value):
                missing.append("events")
        else:
            doc[key] = copy.deepcopy(value)
    return missing


def _block_ok(key: str, value) -> bool:
    if key == "recent":
        return type(value) is list and len(value) <= 30 and all(type(item) is str and len(item) <= 200 for item in value)
    if key == "coordinator":
        if type(value) is not dict or set(value) - {"at", "state", "note"}:
            return False
        if "at" in value and (type(value["at"]) is bool or type(value["at"]) not in (int, float)):
            return False
        if "state" in value and type(value["state"]) is not str:
            return False
        if "note" in value and type(value["note"]) is not str:
            return False
        return True
    if key == "graph":
        return type(value) is list and len(value) <= 60
    if key == "queue":
        return type(value) is list and len(value) <= 30
    if key in ("roadmap", "usage"):
        return type(value) is dict
    if key == "events":
        return type(value) is dict
    return False


def _attach_events(doc: dict, mapping: dict) -> bool:
    pending = []
    for key, rows in mapping.items():
        if type(key) is not str or key.count("/") != 1 or type(rows) is not list or len(rows) > 30:
            return False
        if not all(type(row) is dict for row in rows):
            return False
        work_id, _, step_id = key.partition("/")
        pending.append((work_id, step_id, rows))
    works = {work.get("work_id"): work for work in doc.get("works") or [] if type(work) is dict}
    attached = []
    for work_id, step_id, rows in pending:
        work = works.get(work_id)
        step = None
        if work is not None:
            for item in work.get("steps") or []:
                if item.get("step_id") == step_id and item.get("state") not in _ENDED:
                    step = item
                    break
        if step is None:
            return False
        attached.append((step, rows))
    for step, rows in attached:
        step["events"] = copy.deepcopy(rows)
    return True


def publish_total(folded, host=None, blocks=None) -> bytes:
    """The only publish entry. The first argument is a sealed fold result."""
    from read import LAST_PUBLISH, _is_folded, _probe, at_or_0, class_name, encode_strict, fallback

    caught = 0
    try:
        if not _is_folded(folded):
            return encode_strict(fallback("publish", "invalid_argument", argument="document", n=0))
        document = folded.document()
        caught = document["internal_errors"]
        _probe("publish")
        if "recorder_failed" in document:
            view = document
            if _host_decision(host) == "ok":
                view["host"] = host
            else:
                view.pop("host", None)
                if _host_decision(host) == "bad":
                    _note(view, "host")
        else:
            view = publish_view(document, host, blocks)
        data = encode_strict(view)
        if len(data) > PUBLISH_TARGET_BYTES:
            return encode_strict(fallback("publish", "too_large", at=document["at"], n=caught))
        if not shape_ok(data):
            return encode_strict(fallback("publish", "shape", at=document["at"], n=caught))
        return data
    except Exception as exc:
        try:
            at = 0
            if _is_folded(folded):
                held = folded.document()
                at = held["at"] if type(held) is dict and "at" in held else 0
            return encode_strict(fallback("publish", "caught", error_class=class_name(exc), at=at_or_0(at), n=caught + 1))
        except Exception:
            return LAST_PUBLISH


_WORK_NUM = {"round", "end"}
_WORK_STR = {"title", "short", "goal", "risk", "after"}
_WORK_BOOL = {"sure", "finished"}
_STEP_NUM = {"started", "ended", "last", "usual_min", "eta_start", "eta_end", "overdue"}
_STEP_STR = {"name", "who", "state", "label", "note", "doing"}
_STEP_BOOL = {"needs_owner"}
_FEED_STR = {"work", "step", "who", "state", "text"}


def shape_ok(data: bytes) -> bool:
    if type(data) is not bytes:
        return False
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return False
    if type(obj) is not dict or not _finite_number(obj.get("at")) or not _no_null(obj):
        return False
    if not _known(obj, "", {"at"}, {"verdict", "level", "host"}, {"sure"}):
        return False
    coordinator = obj.get("coordinator")
    if coordinator is not None:
        if type(coordinator) is not dict or not _known(coordinator, "coordinator", {"at"}, {"state", "note"}, set()):
            return False
    recent = obj.get("recent")
    if recent is not None and (type(recent) is not list or len(recent) > 30 or any(type(item) is not str for item in recent)):
        return False
    needs = obj.get("needs_you")
    if needs is not None and (type(needs) is not list or len(needs) > 30 or any(type(item) is not str for item in needs)):
        return False
    owner_now = obj.get("owner_now")
    if owner_now is not None and not _owner_now_ok(owner_now):
        return False
    owner_next = obj.get("owner_next")
    if owner_next is not None and type(owner_next) is not dict:
        return False
    graph = obj.get("graph")
    if graph is not None and (type(graph) is not list or len(graph) > 60):
        return False
    queue = obj.get("queue")
    if queue is not None and (type(queue) is not list or len(queue) > 30):
        return False
    works = obj.get("works")
    if works is not None:
        if type(works) is not list or len(works) > 30:
            return False
        for work in works:
            if type(work) is not dict or not _known(work, "work", _WORK_NUM, _WORK_STR, _WORK_BOOL):
                return False
            if "next" in work and type(work["next"]) is not dict:
                return False
            steps = work.get("steps")
            if steps is None:
                continue
            if type(steps) is not list or len(steps) > 20:
                return False
            for step in steps:
                if type(step) is not dict or not _known(step, "step", _STEP_NUM, _STEP_STR, _STEP_BOOL):
                    return False
                events = step.get("events")
                if events is not None and (type(events) is not list or len(events) > 30 or any(type(item) is not dict for item in events)):
                    return False
    feed = obj.get("feed")
    if feed is not None:
        if type(feed) is not list or len(feed) > 50:
            return False
        for row in feed:
            if type(row) is not dict or not _finite_number(row.get("at")) or not _known(row, "feed", {"at"}, _FEED_STR, set()):
                return False
    return True


def _owner_now_ok(items) -> bool:
    if type(items) is not list or len(items) > 10:
        return False
    for item in items:
        if type(item) is not dict:
            return False
        actions = item.get("actions")
        if actions is None:
            continue
        if type(actions) is not list or len(actions) > 10 or any(type(action) is not dict for action in actions):
            return False
    return True


def _finite_number(value) -> bool:
    if type(value) is bool or (type(value) is not int and type(value) is not float):
        return False
    if type(value) is float and (value != value or value in (float("inf"), float("-inf"))):
        return False
    return True


def _no_null(value) -> bool:
    if value is None:
        return False
    if type(value) is dict:
        return all(_no_null(child) for child in value.values())
    if type(value) is list:
        return all(_no_null(child) for child in value)
    return type(value) in (str, int, float, bool)


def _known(node: dict, _kind: str, numbers: set, strings: set, flags: set) -> bool:
    for key, value in node.items():
        if key in numbers and not _finite_number(value):
            return False
        if key in strings and type(value) is not str:
            return False
        if key in flags and type(value) is not bool:
            return False
    return True
