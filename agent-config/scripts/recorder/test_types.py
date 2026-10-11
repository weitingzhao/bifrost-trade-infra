"""Every field of every event, replaced by a value of the wrong shape.

The walk follows the model's field tables (envelope, schema, nested objects,
list items). It does not list the fields by hand. A mutant that is not a
legal value of that field is absent and leaves a defect. Fold does not raise.
"""

from __future__ import annotations

import copy
import json

from events import dump_line, load_bytes
from fold import fold
from harness import APPR, N, P, R, RUN, WAIT_A, WAIT_D, WORK, fold_one
from model import ENVELOPE, LIST_FIELDS, NESTED_FIELDS, SCHEMAS
from model import CAN_ACT_OUT, ENDED_HOW, HOLDERS, LABELS, REASONS, STATES, WHYS
from publish import encoded, publish_view
from validate import is_int

_MUTANTS = (
    [],
    {},
    None,
    True,
    0,
    -1,
    1e309,
    "",
    "x" * 10000,
    "a\u202eb",
    [[]],
)

# Never a legal inhabitant. ``[]`` can be an empty list field. ``true``, ``0``,
# ``-1`` and ``""`` can be a bool, a number, or a short string.
_NEVER_LEGAL = ({}, None, 1e309, "x" * 10000, "a\u202eb", [[]])

# A shape-legal body for each event. Context for it is ``_base``.
_BODIES = {
    "work_opened": {"work_id": "w9", "title": "T", "goal": "g", "work_ref": "W-9"},
    "work_closed": {"claim": "stopped"},
    "step_declared": {
        "step_id": "abcd1234",
        "name": "m",
        "kind": "other",
        "who": "C",
        "watch": "none",
        "round": 1,
        "after": P,
        "usual_s": 10,
        "usual_basis": "declared",
        "waiting_on": [WAIT_D],
        "locator": {"cluster": "prod", "namespace": "cicd", "name": "run-9"},
    },
    "step_superseded": {"step_id": P, "by_step": N, "text": "old"},
    "step_started": {"step_id": N, "run_id": "aaaaaaaa", "command": "echo"},
    "step_seen": {
        "step_id": P,
        "run_id": RUN,
        "sampled_at": 50,
        "alive": True,
        "output_bytes": 4,
        "text": "line",
    },
    "step_finished": {"step_id": P, "run_id": RUN, "exit": {"code": 0}, "quote": "ok"},
    "record_seen": {
        "step_id": R,
        "sampled_at": 50,
        "found": True,
        "uid": "uid-1",
        "started_at": 40,
        "ended_at": 45,
        "condition": "Unknown",
        "reason_quote": "because",
    },
    "owner_wait_opened": {
        "wait_id": "bbbbbbbb",
        "title": "请看",
        "ref": {"kind": "none", "id": "c0ffee0a"},
        "can_act": "not_yet",
        "where": "thread",
        "reply": "回一句",
        "reply_words": "好",
        "advice": "先看",
        "blocks_text": "卡住",
        "after_text": "然后",
        "not_before_text": "之前",
        "after": P,
        "commands": ["echo hi"],
    },
    "owner_wait_seen": {
        "wait_id": WAIT_A,
        "sampled_at": 50,
        "ref_state": "pending",
        "expires_at": 90,
        "number": 7,
    },
    "owner_wait_ready": {"wait_id": WAIT_D},
    "owner_wait_closed": {"wait_id": WAIT_D, "how": "done"},
    "note": {"text": "n", "step_id": P},
    "observer_round": {
        "round_id": "ab12cd34",
        "started_at": 40,
        "ended_at": 50,
        "confirmed": [f"approval:{APPR}"],
        "failed": [{"key": f"step:{WORK}/{R}", "error": "timeout"}],
        "truncated": True,
    },
    "tail_repaired": {"repair_id": "0-0123456789abcdef", "bytes": 1, "sha256": "ab" * 32},
}


def _paths(kind: str) -> list[tuple]:
    found = [(key,) for key in sorted(ENVELOPE)]
    schema = SCHEMAS[kind]
    for key in sorted(schema["required"] | schema["optional"]):
        found.append((key,))
        nested = NESTED_FIELDS.get(key)
        if nested:
            for child in nested:
                found.append((key, child))
        item = LIST_FIELDS.get(key)
        if item == "str":
            found.append((key, 0))
        elif item:
            for child in NESTED_FIELDS[item]:
                found.append((key, 0, child))
    return found


def _set(event: dict, path: tuple, value):
    cursor = event
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


def _base():
    from harness import LogBuilder

    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", at=2, step_id=P, name="实现", kind="other", who="C", watch="process")
    log.add("step_started", "wrapper", at=3, step_id=P, run_id=RUN, command="echo")
    log.add("step_declared", "coordinator", at=4, step_id=N, name="手工", kind="other", who="C", watch="none")
    log.add(
        "step_declared", "coordinator", at=5, step_id=R, name="发布", kind="release", who="C",
        watch="record", locator={"cluster": "prod", "namespace": "cicd", "name": "run-1"},
    )
    log.add(
        "owner_wait_opened", "coordinator", at=6, wait_id=WAIT_D, title="请看",
        ref={"kind": "none", "id": "c0ffee01"}, can_act="not_yet",
    )
    log.add(
        "owner_wait_opened", "coordinator", at=7, wait_id=WAIT_A, title="请批",
        ref={"kind": "approval", "id": APPR},
    )
    return log.events


def _seal(events: list[dict]) -> list[dict]:
    """Rewrite the chain so the mutated body is a consistent sealed line."""
    blob = b"".join(dump_line(event) for event in events)
    loaded = load_bytes(blob)
    if loaded.invalid_seq is not None:
        return events
    return loaded.events


def _invariants(doc) -> None:
    """V1 and the vocabulary half of V9–V12, on one document."""
    published = publish_view(doc, "board")
    assert len(encoded(published)) <= 204800
    assert doc["ball"]["holder"] in HOLDERS
    assert doc["ball"]["why"] in WHYS
    forbidden = {"needs_you", "owner_now", "owner_items", "owner_next", "needs_owner"}
    assert forbidden.isdisjoint(doc)
    for work in doc["works"]:
        if "closed_claim" in work:
            for step in work["steps"]:
                assert step["state"] not in {"waiting", "running", "slow", "quiet", "unknown"}
        for step in work["steps"]:
            assert step["state"] in STATES
            if "reason" in step:
                assert step["reason"] in REASONS
            if "label" in step:
                assert step["label"] in LABELS
            if "ended_how" in step:
                assert step["ended_how"] in ENDED_HOW
    for item in doc["owner_all"]:
        if "can_act" in item:
            assert item["can_act"] in CAN_ACT_OUT
        if "reason" in item:
            assert item["reason"] in REASONS
    if doc["ball"]["holder"] == "nobody":
        assert all("closed_claim" in work for work in doc["works"])


def _without(doc) -> str:
    copied = json.loads(json.dumps(doc))
    for work in copied["works"]:
        work.pop("defects", None)
    return json.dumps(copied, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_sealed_note_with_by_list_is_a_defect(tmp_path):
    """The review's P1: a sealed note whose ``by`` is a list used to raise."""
    base = _base()
    note = {
        "type": "note",
        "v": 1,
        "seq": len(base) + 1,
        "prev_sha256": "",
        "at": 50,
        "by": [],
        "text": "n",
    }
    events = _seal(base + [note])
    # ``by`` is not a hash, so the chain of seq/prev still loads when the
    # digest matches the body. Fold must return the note as a defect.
    note_events = events if any(item.get("by") == [] for item in events if isinstance(item, dict)) else base + [note]
    doc = fold_one(note_events, 50)
    reasons = [item["reason"] for item in doc["works"][0]["defects"] if item["seq"] == note["seq"]]
    assert reasons
    assert "note" not in json.dumps(doc["feed"])
    bare = fold_one(base, 50)
    assert _without(doc) == _without(bare)
    publish_view(doc, "board")


def test_every_field_type_mutant_is_absent():
    base = _base()
    total = 0
    absent = 0
    legal = []
    for kind in SCHEMAS:
        prototype = {
            "type": kind,
            "v": 1,
            "seq": len(base) + 1,
            "prev_sha256": "",
            "at": 50,
            "by": "observer" if kind in {"record_seen", "owner_wait_seen", "observer_round"} else "coordinator",
        }
        if kind == "step_seen":
            prototype["by"] = "wrapper"
        if kind == "step_started" and _BODIES[kind].get("command"):
            prototype["by"] = "wrapper"
        if kind == "step_finished" and "exit" in _BODIES[kind]:
            prototype["by"] = "wrapper"
        prototype.update(_BODIES[kind])
        for path in _paths(kind):
            for mutant in _MUTANTS:
                total += 1
                event = copy.deepcopy(prototype)
                _set(event, path, mutant)
                sealed = _seal(base + [event])
                nows = (50, 250, 2050)
                seq = event["seq"] if is_int(event.get("seq")) else len(base) + 1
                forced = mutant in _NEVER_LEGAL or (isinstance(mutant, str) and len(mutant) > 200)
                for now in nows:
                    doc = fold_one(sealed, now)
                    _invariants(doc)
                    bare = fold_one(base, now)
                    defect = any(item["seq"] == seq for item in doc["works"][0]["defects"])
                    if defect:
                        assert _without(doc) == _without(bare)
                    else:
                        assert not forced, (kind, path)
                if defect:
                    absent += 1
                else:
                    shown = mutant if not isinstance(mutant, str) else ("empty" if mutant == "" else "text")
                    legal.append((kind, path, shown))
    assert absent + len(legal) == total == _expected_mutants()
    # 1908 mutants are defects. 72 are legal inhabitants of that field
    # (0, -1, the empty string, true, or an empty list). Lists, objects,
    # null, a non-finite number, a 10,000-character string, U+202E and a
    # nested list are never among the 72.
    assert absent == 1908
    assert legal == _LEGAL_MUTANTS


def _expected_mutants() -> int:
    return sum(len(_paths(kind)) for kind in SCHEMAS) * len(_MUTANTS)


_LEGAL_MUTANTS = [
    ("step_declared", ("at",), 0),
    ("step_declared", ("at",), -1),
    ("step_declared", ("prev_sha256",), "empty"),
    ("step_declared", ("seq",), 0),
    ("step_declared", ("seq",), -1),
    ("step_declared", ("name",), "empty"),
    ("step_declared", ("round",), 0),
    ("step_declared", ("round",), -1),
    ("step_declared", ("usual_s",), 0),
    ("step_declared", ("waiting_on",), []),
    ("step_declared", ("who",), "empty"),
    ("step_superseded", ("at",), 0),
    ("step_superseded", ("at",), -1),
    ("step_superseded", ("prev_sha256",), "empty"),
    ("step_superseded", ("seq",), 0),
    ("step_superseded", ("seq",), -1),
    ("step_superseded", ("text",), "empty"),
    ("step_seen", ("prev_sha256",), "empty"),
    ("step_seen", ("seq",), 0),
    ("step_seen", ("seq",), -1),
    ("step_seen", ("alive",), True),
    ("step_seen", ("output_bytes",), 0),
    ("step_seen", ("text",), "empty"),
    ("step_finished", ("at",), 0),
    ("step_finished", ("at",), -1),
    ("step_finished", ("prev_sha256",), "empty"),
    ("step_finished", ("seq",), 0),
    ("step_finished", ("seq",), -1),
    ("step_finished", ("exit", "code"), 0),
    ("step_finished", ("exit", "code"), -1),
    ("step_finished", ("exit", "signal"), "empty"),
    ("step_finished", ("quote",), "empty"),
    ("record_seen", ("prev_sha256",), "empty"),
    ("record_seen", ("seq",), 0),
    ("record_seen", ("seq",), -1),
    ("record_seen", ("ended_at",), 0),
    ("record_seen", ("ended_at",), -1),
    ("record_seen", ("found",), True),
    ("record_seen", ("reason_quote",), "empty"),
    ("record_seen", ("started_at",), 0),
    ("record_seen", ("started_at",), -1),
    ("record_seen", ("uid",), "empty"),
    ("owner_wait_seen", ("prev_sha256",), "empty"),
    ("owner_wait_seen", ("seq",), 0),
    ("owner_wait_seen", ("seq",), -1),
    ("owner_wait_seen", ("expires_at",), 0),
    ("owner_wait_seen", ("expires_at",), -1),
    ("owner_wait_seen", ("number",), 0),
    ("owner_wait_seen", ("number",), -1),
    ("owner_wait_ready", ("at",), 0),
    ("owner_wait_ready", ("at",), -1),
    ("owner_wait_ready", ("prev_sha256",), "empty"),
    ("owner_wait_ready", ("seq",), 0),
    ("owner_wait_ready", ("seq",), -1),
    ("owner_wait_closed", ("at",), 0),
    ("owner_wait_closed", ("at",), -1),
    ("owner_wait_closed", ("prev_sha256",), "empty"),
    ("owner_wait_closed", ("seq",), 0),
    ("owner_wait_closed", ("seq",), -1),
    ("note", ("at",), 0),
    ("note", ("at",), -1),
    ("note", ("prev_sha256",), "empty"),
    ("note", ("seq",), 0),
    ("note", ("seq",), -1),
    ("note", ("text",), "empty"),
    ("tail_repaired", ("at",), 0),
    ("tail_repaired", ("at",), -1),
    ("tail_repaired", ("prev_sha256",), "empty"),
    ("tail_repaired", ("seq",), 0),
    ("tail_repaired", ("seq",), -1),
    ("tail_repaired", ("bytes",), 0),
    ("tail_repaired", ("repair_id",), "empty"),
]
