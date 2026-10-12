"""Whether one event counts, given only the earlier events in the same log.

An event that fails is absent: later events do not see it. The reason is a
defect code. This does not read the clock, the observer log, or a file.
The same rules run at append time and inside the fold.
"""

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field

from model import (
    APPROVAL_TERMINAL,
    BY,
    CLOCK_SKEW_S,
    CLOSE_HOW,
    COMMAND_LIMIT,
    CONDITIONS,
    ENVELOPE,
    MAX_COMMANDS,
    MAX_OPEN_WAITS,
    MAX_STEPS,
    NAME_LIMIT,
    OBSERVER_ERRORS,
    QUESTION_TERMINAL,
    REPORTED,
    ROUND_ITEM_LIMIT,
    SAMPLED_LAG_S,
    SCHEMAS,
    TEXT_LIMIT,
    USUAL_BASIS,
    WHERE,
    CLAIMS,
    CAN_ACT,
    OUTPUT_LARGE_BYTES,
    ref_state_ok,
    terminal_state,
    watch_matches,
)

_HEX8 = re.compile(r"^[0-9a-f]{8}$")
_APPROVAL = re.compile(r"^appr_[0-9a-f]{16}$")
_QUESTION = re.compile(r"^q_[0-9a-f]{16}$")
_WORK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def has_control(text: str) -> bool:
    """Control characters, line separators, and the bidi override U+202E.

    The design names controls and U+2028 / U+2029. U+202E is rejected as well:
    a string containing it is not a value any field accepts.
    """
    for ch in text:
        code = ord(ch)
        if code < 32 or code == 127 or code in (0x2028, 0x2029, 0x202E):
            return True
    return False


class Event:
    """One event after ``parse_event``. Fields are already typed.

    Downstream code does not see the raw dictionary. Item access reads the
    copy made at the boundary.
    """

    __slots__ = ("_fields",)

    def __init__(self, fields: dict):
        self._fields = fields

    def __getitem__(self, key):
        return self._fields[key]

    def get(self, key, default=None):
        return self._fields.get(key, default)

    def __contains__(self, key):
        return key in self._fields

    def keys(self):
        return self._fields.keys()


def _closed(value, allowed) -> str | None:
    """Set membership only after the value is known to be a string."""
    if not isinstance(value, str):
        return "bad_type"
    if value not in allowed:
        return "bad_value"
    return None


@dataclass
class Step:
    step_id: str
    name: str
    kind: str
    who: str
    watch: str
    index: int
    declared_at: float
    declared_by: str = "coordinator"
    declared_seq: int = 0
    locator: dict | None = None
    waiting_on: list = field(default_factory=list)
    after: str | None = None
    usual_s: float | None = None
    usual_basis: str | None = None
    round: float | None = None
    started: bool = False
    started_at: float | None = None
    start_index: int | None = None
    run_id: str | None = None
    command: str | None = None
    superseded: bool = False
    by_step: str | None = None
    superseded_text: str | None = None
    ever_found: bool = False
    found_uid: str | None = None
    ended: bool = False
    dead: bool = False
    seen: list = field(default_factory=list)
    record_obs: list = field(default_factory=list)
    finished: dict | None = None
    last_output: int | None = None
    last_sampled: float | None = None
    last_seen_index: int | None = None
    output_large: bool = False
    note: str | None = None
    quote: str | None = None


@dataclass
class Wait:
    wait_id: str
    title: str
    ref: dict
    index: int
    opened_at: float
    can_act: str | None = None
    where: str | None = None
    reply: str | None = None
    reply_needed: bool | None = None
    reply_words: str | None = None
    commands: list | None = None
    deadline: float | None = None
    no_deadline: bool = False
    blocks_nothing: bool = False
    not_before_text: str | None = None
    advice: str | None = None
    blocks_text: str | None = None
    after_text: str | None = None
    after: str | None = None
    seen: list = field(default_factory=list)
    ever_seen: bool = False
    settled: bool = False
    settled_how: str | None = None
    settled_at: float | None = None
    terminal_state: str | None = None
    yes_at: float | None = None


@dataclass
class View:
    """What the valid events in one log say. Invalid events are listed and ignored."""

    work_id: str | None = None
    title: str | None = None
    goal: str | None = None
    work_ref: str | None = None
    opened: bool = False
    closed: bool = False
    closed_claim: str | None = None
    closed_at: float | None = None
    steps: dict = field(default_factory=dict)
    step_order: list = field(default_factory=list)
    waits: dict = field(default_factory=dict)
    wait_order: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    rounds: list = field(default_factory=list)
    valid: list = field(default_factory=list)
    defects: list = field(default_factory=list)
    max_at: float | None = None
    backwards: set = field(default_factory=set)


def step_is_open(step: Step) -> bool:
    """Open for a close check. Does not use the clock or the observer log.

    ``dead`` is not open and not ended. A withdrawn step that never started
    (or, for a record, was never found) is not in the list and is not open.
    """
    if step.ended:
        return False
    if step.watch == "record":
        if step.superseded and not step.ever_found:
            return False
        return True
    if step.superseded and not step.started:
        return False
    if step.dead:
        return False
    return True


def wait_is_unsettled(wait: Wait) -> bool:
    return not wait.settled


def _seq_of(event, index: int):
    if isinstance(event, (dict, Event)):
        seq = event.get("seq")
        if is_int(seq):
            return seq
    return index + 1


def parse_event(raw):
    """Turn one raw value into a typed event, or a defect code.

    Every field, nested fields included, is type-checked here. Nothing after
    this function looks up, compares, or does arithmetic on a raw dictionary.
    """
    if not isinstance(raw, dict):
        return None, "bad_type"
    reason = _shape(raw)
    if reason is not None:
        return None, reason
    return Event(copy.deepcopy(raw)), None


def _text_ok(value: str, limit: int) -> str | None:
    if has_control(value) or len(value) > limit:
        return "limit_text"
    return None


def _shape(event: dict) -> str | None:
    """Type of every field first. No set lookup, comparison, or arithmetic before that."""
    if not isinstance(event, dict):
        return "bad_type"
    kind = event.get("type")
    if not isinstance(kind, str) or kind not in SCHEMAS:
        return "unknown_type"
    schema = SCHEMAS[kind]
    allowed = ENVELOPE | schema["required"] | schema["optional"]
    for key in event:
        if not isinstance(key, str) or key not in allowed:
            return "unknown_field"
    for key in ("type", "v", "at", "by", *schema["required"]):
        if key not in event:
            return "missing_field"
    version = event.get("v")
    if type(version) is not int:
        return "bad_type"
    if version != 2:
        return "bad_value"
    if not is_number(event.get("at")):
        return "bad_type"
    by_reason = _closed(event.get("by"), BY)
    if by_reason:
        return by_reason
    if "seq" in event and not is_int(event["seq"]):
        return "bad_type"
    if "prev_sha256" in event:
        prev = event["prev_sha256"]
        if not isinstance(prev, str):
            return "bad_type"
        if prev != "" and _SHA.fullmatch(prev) is None:
            return "bad_value"
    return _fields(kind, event)


def _fields(kind: str, event: dict) -> str | None:
    if kind == "work_opened":
        if not isinstance(event["work_id"], str) or _WORK.match(event["work_id"]) is None:
            return "bad_value"
        return _strings(event, {"title": NAME_LIMIT, "goal": TEXT_LIMIT, "work_ref": NAME_LIMIT})
    if kind == "work_closed":
        return _closed(event.get("claim"), CLAIMS)
    if kind == "step_declared":
        if not _HEX8.match(event["step_id"]) if isinstance(event["step_id"], str) else True:
            return "bad_value"
        err = _strings(event, {"name": NAME_LIMIT, "who": NAME_LIMIT})
        if err:
            return err
        reason = _closed(event.get("kind"), {"implement", "verify", "review", "merge", "other", "release", "ci"})
        if reason:
            return reason
        reason = _closed(event.get("watch"), {"process", "none", "record"})
        if reason:
            return reason
        if "usual_s" in event and (not is_number(event["usual_s"]) or event["usual_s"] < 0):
            return "bad_value"
        if "usual_basis" in event:
            reason = _closed(event.get("usual_basis"), USUAL_BASIS)
            if reason:
                return reason
        if "round" in event and not is_number(event["round"]):
            return "bad_type"
        if "after" in event and not isinstance(event["after"], str):
            return "bad_type"
        if "after" in event and not _HEX8.match(event["after"]):
            return "bad_value"
        if "waiting_on" in event:
            err = _id_list(event["waiting_on"])
            if err:
                return err
        if "locator" in event:
            err = _locator(event["locator"])
            if err:
                return err
        if "replaces" in event and (not isinstance(event["replaces"], str) or not _HEX8.match(event["replaces"])):
            return "bad_value"
        if "replaces_text" in event and "replaces" not in event:
            return "bad_value"
        return _strings(event, {"replaces_text": TEXT_LIMIT})
    if kind == "step_superseded":
        if not isinstance(event["step_id"], str) or not _HEX8.match(event["step_id"]):
            return "bad_value"
        return _strings(event, {"text": TEXT_LIMIT})
    if kind == "step_started":
        if not _hex_pair(event, "step_id", "run_id"):
            return "bad_value"
        if "command" in event:
            err = _strings(event, {"command": TEXT_LIMIT})
            if err:
                return err
        if "pid" in event and not is_int(event["pid"]):
            return "bad_type"
        return None
    if kind == "step_seen":
        if not _hex_pair(event, "step_id", "run_id"):
            return "bad_value"
        if not is_number(event["sampled_at"]) or not isinstance(event["alive"], bool):
            return "bad_type"
        if "output_bytes" in event and (not is_int(event["output_bytes"]) or event["output_bytes"] < 0):
            return "bad_value"
        return _strings(event, {"text": TEXT_LIMIT})
    if kind == "step_finished":
        if not _hex_pair(event, "step_id", "run_id"):
            return "bad_value"
        if "reported" in event:
            reason = _closed(event.get("reported"), REPORTED)
            if reason:
                return reason
        if "exit" in event:
            err = _exit(event["exit"])
            if err:
                return err
        return _strings(event, {"quote": TEXT_LIMIT})
    if kind == "record_seen":
        if not isinstance(event["step_id"], str) or not _HEX8.match(event["step_id"]):
            return "bad_value"
        if not is_number(event["sampled_at"]) or not isinstance(event["found"], bool):
            return "bad_type"
        if "uid" in event and not isinstance(event["uid"], str):
            return "bad_type"
        if "uid" in event and _text_ok(event["uid"], NAME_LIMIT):
            return "limit_text"
        for key in ("started_at", "ended_at"):
            if key in event and not is_number(event[key]):
                return "bad_type"
        if "condition" in event:
            reason = _closed(event.get("condition"), CONDITIONS)
            if reason:
                return reason
        return _strings(event, {"reason_quote": TEXT_LIMIT})
    if kind == "owner_wait_opened":
        if not isinstance(event["wait_id"], str) or not _HEX8.match(event["wait_id"]):
            return "bad_value"
        err = _strings(event, {
            "title": NAME_LIMIT,
            "reply": TEXT_LIMIT,
            "reply_words": TEXT_LIMIT,
            "not_before_text": TEXT_LIMIT,
            "advice": TEXT_LIMIT,
            "blocks_text": TEXT_LIMIT,
            "after_text": TEXT_LIMIT,
        })
        if err:
            return err
        err = _ref(event.get("ref"))
        if err:
            return err
        if "can_act" in event:
            reason = _closed(event.get("can_act"), CAN_ACT)
            if reason:
                return reason
        if "where" in event:
            reason = _closed(event.get("where"), WHERE)
            if reason:
                return reason
        if "after" in event and (not isinstance(event["after"], str) or not _HEX8.match(event["after"])):
            return "bad_value"
        if "deadline" in event and not is_number(event["deadline"]):
            return "bad_type"
        if "no_deadline" in event and event["no_deadline"] is not True:
            return "bad_value"
        if "blocks_nothing" in event and event["blocks_nothing"] is not True:
            return "bad_value"
        if "reply_needed" in event and event["reply_needed"] is not False:
            return "bad_value"
        if "commands" in event:
            err = _commands(event["commands"])
            if err:
                return err
        if "replaces" in event and (not isinstance(event["replaces"], str) or not _HEX8.match(event["replaces"])):
            return "bad_value"
        return None
    if kind == "owner_wait_seen":
        if not isinstance(event["wait_id"], str) or not _HEX8.match(event["wait_id"]):
            return "bad_value"
        if not is_number(event["sampled_at"]) or not isinstance(event["ref_state"], str):
            return "bad_type"
        if _text_ok(event["ref_state"], NAME_LIMIT):
            return "limit_text"
        if "expires_at" in event and not is_number(event["expires_at"]):
            return "bad_type"
        if "number" in event and not is_int(event["number"]):
            return "bad_type"
        return None
    if kind == "owner_wait_ready":
        if not isinstance(event["wait_id"], str) or not _HEX8.match(event["wait_id"]):
            return "bad_value"
        return None
    if kind == "owner_wait_closed":
        if not isinstance(event["wait_id"], str) or not _HEX8.match(event["wait_id"]):
            return "bad_value"
        reason = _closed(event.get("how"), CLOSE_HOW)
        if reason:
            return reason
        return None
    if kind == "note":
        err = _strings(event, {"text": TEXT_LIMIT})
        if err:
            return err
        if "step_id" in event and (not isinstance(event["step_id"], str) or not _HEX8.match(event["step_id"])):
            return "bad_value"
        return None
    if kind == "observer_round":
        if not isinstance(event["round_id"], str) or not _HEX8.match(event["round_id"]):
            return "bad_value"
        if not is_number(event["started_at"]) or not is_number(event["ended_at"]):
            return "bad_type"
        if not isinstance(event["confirmed"], list) or not isinstance(event["failed"], list):
            return "bad_type"
        if "truncated" in event and event["truncated"] is not True:
            return "bad_value"
        return _round_lists(event)
    if kind == "tail_repaired":
        if not isinstance(event["repair_id"], str) or _text_ok(event["repair_id"], NAME_LIMIT):
            return "bad_value"
        if not is_int(event["bytes"]) or event["bytes"] < 0:
            return "bad_value"
        if not isinstance(event["sha256"], str) or _SHA.match(event["sha256"]) is None:
            return "bad_value"
        return None
    return "unknown_type"


def _strings(event: dict, limits: dict[str, int]) -> str | None:
    for key, limit in limits.items():
        if key not in event:
            continue
        if not isinstance(event[key], str):
            return "bad_type"
        if _text_ok(event[key], limit):
            return "limit_text"
    return None


def _hex_pair(event: dict, *keys: str) -> bool:
    for key in keys:
        value = event.get(key)
        if not isinstance(value, str) or _HEX8.match(value) is None:
            return False
    return True


def _id_list(value) -> str | None:
    if not isinstance(value, list):
        return "bad_type"
    seen = set()
    for item in value:
        if not isinstance(item, str) or _HEX8.match(item) is None:
            return "bad_value"
        if item in seen:
            return "bad_value"
        seen.add(item)
    return None


def _locator(value) -> str | None:
    if not isinstance(value, dict):
        return "bad_type"
    allowed = {"cluster", "namespace", "name"}
    if any(key not in allowed for key in value) or "cluster" not in value or "namespace" not in value:
        return "bad_value" if any(key not in allowed for key in value) else "missing_field"
    for key in ("cluster", "namespace", "name"):
        if key not in value:
            continue
        if not isinstance(value[key], str):
            return "bad_type"
        if _text_ok(value[key], NAME_LIMIT):
            return "limit_text"
        if value[key] == "":
            return "bad_value"
    return None


def _exit(value) -> str | None:
    if not isinstance(value, dict):
        return "bad_type"
    if set(value) - {"code", "signal"}:
        return "unknown_field"
    if "code" in value and value["code"] is None:
        return "bad_type"
    if "signal" in value and value["signal"] is None:
        return "bad_type"
    code = value.get("code", None)
    signal = value.get("signal", None)
    code_set = code is not None
    signal_set = signal is not None and signal != ""
    if code_set == signal_set:
        return "bad_exit"
    if code_set and not is_int(code):
        return "bad_type"
    if signal_set and (not isinstance(signal, str) or _text_ok(signal, NAME_LIMIT)):
        return "bad_value"
    return None


def _ref(value) -> str | None:
    if not isinstance(value, dict):
        return "bad_type"
    if set(value) - {"kind", "id"} or "kind" not in value or "id" not in value:
        return "missing_field" if "kind" not in value or "id" not in value else "unknown_field"
    kind = value["kind"]
    ident = value["id"]
    if not isinstance(kind, str) or not isinstance(ident, str):
        return "bad_type"
    if kind not in {"approval", "question", "none"}:
        return "bad_value"
    if _text_ok(ident, NAME_LIMIT):
        return "limit_text"
    if kind == "approval" and _APPROVAL.match(ident) is None:
        return "ref_format"
    if kind == "question" and _QUESTION.match(ident) is None:
        return "ref_format"
    return None


def _commands(value) -> str | None:
    if not isinstance(value, list):
        return "bad_type"
    if len(value) > MAX_COMMANDS:
        return "bad_value"
    for item in value:
        if not isinstance(item, str):
            return "bad_type"
        if _text_ok(item, COMMAND_LIMIT):
            return "limit_text"
    return None


def _round_lists(event: dict) -> str | None:
    confirmed = event["confirmed"]
    failed = event["failed"]
    unrecorded = event.get("unrecorded", [])
    if not isinstance(unrecorded, list):
        return "bad_type"
    for item in confirmed:
        if not isinstance(item, str):
            return "bad_type"
        if _text_ok(item, TEXT_LIMIT) or _OBS_KEY.fullmatch(item) is None:
            return "bad_value" if _OBS_KEY.fullmatch(item) is None else "limit_text"
    for item in failed:
        if not isinstance(item, dict):
            return "bad_type"
        if set(item) - {"key", "error"} or "key" not in item or "error" not in item:
            return "missing_field" if "key" not in item or "error" not in item else "unknown_field"
        if not isinstance(item["key"], str) or not isinstance(item["error"], str):
            return "bad_type"
        if _OBS_KEY.fullmatch(item["key"]) is None:
            return "bad_value"
    for item in unrecorded:
        reason = _unrecorded_item(item)
        if reason:
            return reason
    return None


_OBS_KEY = re.compile(
    r"^(?:approval:appr_[0-9a-f]{16}|question:q_[0-9a-f]{16}|step:[A-Za-z0-9][A-Za-z0-9._-]{0,79}/[0-9a-f]{8})$"
)


def _unrecorded_item(item) -> str | None:
    if not isinstance(item, dict):
        return "bad_type"
    if set(item) - {"work_id", "step_id", "run_id"}:
        return "unknown_field"
    if "work_id" not in item or "step_id" not in item or "run_id" not in item:
        return "missing_field"
    if not isinstance(item["work_id"], str) or not isinstance(item["step_id"], str) or not isinstance(item["run_id"], str):
        return "bad_type"
    if _WORK.fullmatch(item["work_id"]) is None or not _HEX8.fullmatch(item["step_id"]) or not _HEX8.fullmatch(item["run_id"]):
        return "bad_value"
    return None


def _sampled(event: dict, previous: float | None) -> str | None:
    at = event["at"]
    sampled = event["sampled_at"]
    if sampled > at or sampled < at - SAMPLED_LAG_S:
        return "sampled_at"
    if previous is not None and sampled < previous:
        return "sampled_at"
    return None


def _open_items(view: View) -> bool:
    for step in view.steps.values():
        if step_is_open(step):
            return True
    for wait in view.waits.values():
        if wait_is_unsettled(wait):
            return True
    return False


def _unsettled_count(view: View) -> int:
    return sum(1 for wait in view.waits.values() if wait_is_unsettled(wait))


def _ref_key(ref: dict) -> tuple:
    return (ref.get("kind"), ref.get("id"))


def classify(events: list, *, work_id: str | None = None, observer: bool = False) -> View:
    from contextual import _apply, _contextual, _contextual_observer
    """Split ``events`` into the valid prefix's meaningful events and defects.

    ``work_id`` is the directory name. A ``work_opened`` for a different id
    is a defect. ``observer`` is the observer log: only ``observer_round`` counts.
    """
    view = View(work_id=work_id)
    for index, raw in enumerate(events or []):
        parsed, reason = parse_event(raw)
        if reason is None:
            reason = _contextual_observer(view, parsed) if observer else _contextual(view, parsed, index)
        if reason is not None:
            view.defects.append({"seq": _seq_of(raw, index), "reason": reason})
            continue
        _apply(view, parsed, len(view.valid))
    view.backwards = _backwards(view.valid)
    return view


def _backwards(events: list) -> set[int]:
    """Indexes of valid events that sit in a clock-backwards interval."""
    inside: set[int] = set()
    max_at = None
    index = 0
    total = len(events)
    while index < total:
        at = events[index]["at"]
        if max_at is not None and at < max_at - CLOCK_SKEW_S:
            threshold = max_at
            while index < total and events[index]["at"] < threshold:
                inside.add(index)
                index += 1
            continue
        if max_at is None or at > max_at:
            max_at = at
        index += 1
    return inside


def refusal(events: list, event: dict, *, work_id: str | None = None) -> str | None:
    from contextual import _contextual
    """The defect code a new event would get, or None when it would be written."""
    view = classify(events, work_id=work_id)
    parsed, reason = parse_event(event)
    if reason is None:
        reason = _contextual(view, parsed, len(events))
    return reason
