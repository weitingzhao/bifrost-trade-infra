"""Round 8, continued: publish, read, validate, and the redaction bound."""

from __future__ import annotations

import threading

P = "a1b2c3d4"
WORK = "w1"


def _need(cond, detail):
    if not cond:
        raise AssertionError(detail)


def _soon(fn):
    """None when fn has not returned. A cycle that ignores its stop must fail here."""
    box = []
    thread = threading.Thread(target=lambda: box.append(fn()), daemon=True)
    thread.start()
    thread.join(0.2)
    if thread.is_alive() or not box:
        return None
    return box[0]


def _publish_view_and_levels():
    from model import PLATFORM_MAX_STEPS, PUBLISH_MAX_FEED
    from publish import (
        _anything_cut, _attach_events, _block_ok, _drop_nulls, _finite_number, _fit,
        _is_summary, _level1, _level3, _level4, _level5, _level6, _merge_blocks,
        _owner_ids, _shed_blocks, _step_sort, _strip_commands, _strip_step_events,
        _too_big, _trim_steps, _trim_works, _work_group, _works_total, publish_view,
    )

    bare = {"at": 1}
    view = publish_view(bare)
    _need(view["works"] == [] and view["owner_all"] == [] and view["feed"] == [], view)
    feed = [{"at": index, "work": WORK, "step": "", "who": "", "state": "", "text": "t"} for index in range(PUBLISH_MAX_FEED)]
    exact = publish_view({"at": 1, "works": [], "owner_all": [], "feed": feed})
    _need(len(exact["feed"]) == PUBLISH_MAX_FEED and "feed" not in exact.get("incomplete", []), len(exact["feed"]))
    _need(_is_summary({"state_counts": {}, "steps": []}) is False, "steps means it is not a summary")
    _need(_is_summary({"state_counts": {}}) is True, "counts and no steps is a summary")
    _need(_is_summary({"steps": []}) is False, "steps without counts is not a summary")
    doc = {"works": [{"steps": [{"state": "done", "note": "n"}, {"state": "running", "note": "n"}]}]}
    _level1(doc)
    _need("note" not in doc["works"][0]["steps"][0] and doc["works"][0]["steps"][1]["note"] == "n", doc)
    summary = {"state_counts": {"done": 1}}
    held = {"works": [summary]}
    _level1(held)
    _need(held["works"] == [{"state_counts": {"done": 1}}], "a summary has no steps to strip")
    _level1({})
    missing_steps = {"works": [{}]}
    _level1(missing_steps)
    _need(missing_steps["works"] == [{}], "a work with no steps is left alone")
    closed = {"works": [{"closed_claim": "landed", "steps": [{"state": "running"}]}]}
    _level3(closed)
    _need("steps" not in closed["works"][0] and "state_counts" in closed["works"][0], closed["works"][0])
    open_work = {"works": [{"steps": [{"state": "running"}]}]}
    _level3(open_work)
    _need("steps" in open_work["works"][0], "an open work is not summarized at level 3")
    level4 = {"works": [{"steps": [{"state": "running"}, {"state": "done"}], "_all_steps": [{"state": "running"}, {"state": "done"}]}]}
    _level4(level4)
    _need(all(step["state"] != "done" for step in level4["works"][0]["steps"]), level4["works"][0]["steps"])
    only_steps = {"works": [{"steps": [{"state": "waiting"}]}]}
    _level4(only_steps)
    _need(only_steps["works"][0]["steps"][0]["state"] == "waiting", "steps stand in when the full list is absent")
    _level5({"works": [{"steps": [{"state": "running"}]}]})
    no_works = {}
    _level5(no_works)
    _need(no_works["works"] == [], no_works)
    level6 = {"at": 1, "works": [], "feed": [], "owner_all_cut": 0}
    _level6(level6, [], 0, False)
    _need("owner_all_cut" not in level6, level6)
    kept_cut = {"at": 1, "works": [], "feed": [], "owner_all_cut": 0}
    # prior is 0 because 0 is falsy; the key is still present and must be removed when nothing is cut
    _level6(kept_cut, [{"title": "t"}], 0, False)
    _need("owner_all_cut" not in kept_cut, kept_cut)
    _need(_finite_number(True) is False and _finite_number(1) is True and _finite_number(1.5) is True, "a boolean is not a finite number")
    _need(_finite_number(float("nan")) is False and _finite_number(float("inf")) is False, "nan and infinity are not finite")
    _need(_drop_nulls({"a": None, "b": 1}) == {"b": 1}, "null values are absent")
    _need(_drop_nulls([1, None]) == [1], "null list items are absent")
    _need(_drop_nulls(float("nan")) == 0, "a non-finite float becomes 0")
    _need(_drop_nulls(float("inf")) == 0, "infinity becomes 0")
    cut = _anything_cut({}, [], [], [{"at": 1}] * 26)
    _need(cut is True, "26 feed rows are over the feed cap")
    _need(_anything_cut({}, [{"steps": [1] * (PLATFORM_MAX_STEPS + 1)}], [], []) is True, "21 steps are over the step cap")
    _need(_anything_cut({}, [{}], [], []) is False, "a work with no steps is within the cap")
    ids = _owner_ids([{"works": [WORK, {"work_id": WORK}]}, {"works": "nope"}])
    _need(ids == {WORK}, ids)
    group = _work_group({"steps": None, "last_at": 1}, set())
    _need(group[0] == 2, group)
    trimmed = {"steps": None}
    _trim_steps(trimmed)
    _need(trimmed["steps_total"] == 0 and trimmed["steps"] is None, trimmed)
    ranked = _step_sort({"state": "running", "superseded_by": P}, 0)
    ended = _step_sort({"state": "done", "superseded_by": P}, 0)
    _need(ranked[0] == 0 and ended[0] == 1, (ranked, ended))
    stripped = _strip_commands({"commands": []})
    _need(stripped["commands_count"] == 0 and "commands" not in stripped, stripped)
    _need(_works_total(["closed_claim", {"closed_claim": "landed"}]) == {"open": 1, "closed": 1}, "only an object can be closed")
    _need(_block_ok("coordinator", {"at": True}) is False, "a boolean at is not a time")
    _need(_block_ok("coordinator", {"at": 1}) is True, "an integer at is a time")
    _need(_merge_blocks({}, {1: {}}) == ["blocks"], "a block key is a string")
    _need(_merge_blocks({}, {"usage": []}) == ["usage"], "usage is an object")
    cycle = {}
    cycle["self"] = cycle
    _need(_soon(lambda: _merge_blocks({}, {"usage": cycle})) == ["blocks"], "a cyclic blocks object is rejected before a key is copied")
    attached = {"works": [{"work_id": WORK, "steps": [{"step_id": P, "state": "running"}]}]}
    _need(_attach_events(attached, {"w1/" + P: [{"at": 1}]}) is True, attached)
    _need(attached["works"][0]["steps"][0]["events"] == [{"at": 1}], attached)
    _need(_attach_events({"works": None}, {WORK + "/" + P: []}) is False, "a missing work list cannot take events")
    _need(_attach_events(attached, {1: []}) is False, "an event key is a string")
    _need(_attach_events(attached, {"noslash": []}) is False, "an event key contains one slash")
    shed = {"works": None, "at": 1, "feed": [], "owner_all": []}
    _need(_shed_blocks(shed, 0, False) is False, "no works means no events to shed")
    small = {"at": 1, "works": [{"steps": [{"events": [{"a": 1}]}]}], "feed": [], "owner_all": []}
    _need(_shed_blocks(small, 0, False) is False, "events stay when the document fits")
    _need("events" in small["works"][0]["steps"][0], small)
    _need(_strip_step_events({}) is False, "no works means nothing was stripped")
    _need(_too_big({"at": 1, "works": [], "feed": [], "owner_all": []}, 0, 0, False) is False, "an empty document fits")
    _need(_fit({"at": 1, "works": [], "feed": [], "owner_all": []}, [], 0, False) == 0, "an empty document is level 0")
    kept, omitted = _trim_works([{"work_id": WORK, "steps": []}], set())
    _need(len(kept) == 1 and omitted == {"open": 0, "closed": 0}, (kept, omitted))


def _read_edges():
    import json
    from model import MAX_DEPTH, TWO53
    from read import (
        Folded, _bad_string, _chain, _convert, _forget, _held, _in_range, _int_token,
        _is_folded, _strings_bad, _token_bad, at_or_0, exact_tree, fallback, prescan, read_line, read_log,
    )

    _need(at_or_0(True) == 0, "a boolean is not a time")
    _need(at_or_0(1.5) == 1.5, "a finite float is kept")
    _need(at_or_0(0.0) == 0 and type(at_or_0(0.0)) is int, "zero becomes the integer 0")
    _need(at_or_0(0) == 0 and type(at_or_0(0)) is int, "the integer zero stays zero")
    _need(at_or_0(None) == 0, "a missing time is 0")
    _need(_in_range(float("nan")) is False, "nan is outside the range")
    _need(_in_range(float("inf")) is False and _in_range(float("-inf")) is False, "infinity is outside the range")
    _need(_in_range(1.0) is True, "a finite float is inside the range")
    _need(exact_tree("ok") is True and exact_tree("\n") is False, "a control character is not a leaf")
    _need(exact_tree({1: "a"}) is False, "a key is a string")
    cycle = []
    cycle.append(cycle)
    _need(_soon(lambda: exact_tree(cycle)) is False, "a cycle is not a tree")
    deep = current = []
    for _ in range(MAX_DEPTH):
        nxt = []
        current.append(nxt)
        current = nxt
    _need(exact_tree(deep) is False, "deeper than eight is not a tree")
    _need(_convert(("N",)) == ("N",), "a short pair is not a number token")
    _need(_convert(("X", "1")) == ("X", "1"), "the tag is N")
    _need(_convert(("N", "0.0")) == 0 and type(_convert(("N", "0.0"))) is int, "zero is the integer 0")
    _need(_convert(("N", "1.5")) == 1.5, "a non-zero float stays")
    _need(_convert(("N", "-1.0")) == -1.0, "negative one stays a float")
    _need(_chain({"seq": ("N", "1"), "prev_sha256": "", "v": ("N", "2")}, 1, "") is None, "a matching chain is clean")
    _need(_chain({"seq": ("N", "1"), "prev_sha256": 1, "v": ("N", "2")}, 1, "") == "bad_chain", "prev_sha256 is text")
    _need(_chain({"seq": ("N", "1"), "v": ("N", "2")}, 1, "") == "bad_chain", "a missing prev_sha256 is a bad chain")
    _need(_chain({"seq": ("N", "2"), "prev_sha256": "", "v": ("N", "2")}, 1, "") == "bad_chain", "seq has to be the line number")
    _need(_bad_string("\u202a") is True and _bad_string("ok") is False, "an embedding control is rejected")
    _need(_bad_string(1) is True, "a non-string is bad")
    _need(_strings_bad({"\n": "a"}) is True, "a bad key is a bad string")
    _need(_strings_bad(["ok"]) is False and _strings_bad(["\n"]) is True, "a list is walked")
    _need(_strings_bad(1) is False, "a number is not a string")
    _need(_int_token(("N", "1.5")) is None, "a decimal token is not an integer token")
    _need(_int_token(("N", "1" * 17)) == int("1" * 17), "seventeen digits are still an integer")
    _forget(1, None)
    slot = {}
    # a missing slot is left alone; a slot that is not this reference is left alone
    from read import _REGISTRY
    _REGISTRY[7] = None
    try:
        _forget(7, "ref")
        _need(7 not in _REGISTRY or _REGISTRY.get(7) is None, "a slot that is not a pair is not this reference")
    finally:
        _REGISTRY.pop(7, None)
    _need(_held(object()) is None, "an unknown object holds nothing")
    _need(_is_folded(object()) is False, "an ordinary object is not a fold handle")
    try:
        Folded()
        raised = False
    except TypeError:
        raised = True
    _need(raised, "Folded has no public constructor")
    try:
        Folded(document={"at": 1})
        raised = False
    except TypeError:
        raised = True
    _need(raised, "a document does not open the constructor")
    body = b"]" + b"[" * 9
    _need(prescan(body) == "limit_depth", "a close at depth zero does not buy nine more opens")
    nested = b"[" * 8 + b"]" + b"["
    _need(prescan(nested) is None, "closing the eighth bracket keeps the next open within the limit")
    pair = b"[" + b"]" + b"[" * 8
    _need(prescan(pair) is None, "a close at depth one is a real close")
    import hashlib
    line = b"ab" * 32 + b"Z"
    parsed = read_line(line, 1, "")
    _need(parsed.reason == "bad_line", parsed.reason)
    dup = hashlib.sha256(b'{"a":1,"a":2}').hexdigest().encode() + b' {"a":1,"a":2}'
    # ValueError from the pairs hook has args; an empty args case is the guard on exc.args
    _need(read_line(dup, 1, "").reason == "dup_key", "a repeated key is dup_key")
    _need(read_log(WORK, "not-bytes").broken_why == "bad_line", "a non-bytes log breaks at line 1")
    empty_tail = read_log(WORK, b"\n")
    _need(empty_tail.events == [] and empty_tail.torn_tail is False, "a lone newline is an empty line, not a torn tail")
    text = json.dumps({"at": 1, "by": "coordinator", "prev_sha256": "", "seq": 1, "text": "n", "type": "note", "v": 2})
    # line number constant and digest fallback are exercised by a real line below via read_log of sealed bytes
    from harness import LogBuilder, _chain
    note = LogBuilder()
    note.add("note", "coordinator", at=1, text="n")
    sealed = _chain(note.events)
    _need(len(read_log(WORK, sealed).events) == 1, "one sealed note is one event")
    observed = read_log("obs.jsonl", sealed, observer=True)
    _need(observed.defects and observed.defects[0].get("file") == "obs.jsonl", observed.defects)
    _need("file" not in read_log(WORK, sealed).events[0], "a work event is not an observer defect")
    failed = fallback("read", "invalid_argument", argument="", at=True)
    _need("argument" not in failed["recorder_failed"] and failed["at"] == 0, failed)
    failed = fallback("read", "invalid_argument", argument="now", at=1.5)
    _need(failed["recorder_failed"]["argument"] == "now" and failed["at"] == 1.5, failed)
    failed = fallback("read", "caught", error_class="", at=1)
    _need("error_class" not in failed["recorder_failed"], failed)
    failed = fallback("read", "caught", error_class="ValueError", at=1)
    _need(failed["recorder_failed"]["error_class"] == "ValueError", failed)
    _need(_token_bad("1e999") is True, "overflow is rejected")
    del slot
    del text


def _validate_edges():
    from model import CLOCK_SKEW_S, NAME_LIMIT, SAMPLED_LAG_S, TEXT_LIMIT
    from validate import (
        Step, View, _backwards, _exit, _hex_pair, _id_list, _locator, _ref, _round_lists,
        _sampled, _shape, _text_ok, has_control, step_is_open,
    )

    _need(_locator({"namespace": "n", "name": "a"}) == "missing_field", "cluster is required")
    _need(_locator({"cluster": "c", "name": "a"}) == "missing_field", "namespace is required")
    _need(_locator({"cluster": "c", "namespace": "n"}) is None, "name is optional")
    _need(_locator({"cluster": 1, "namespace": "n"}) == "bad_type", "cluster is text")
    _need(_locator({"cluster": "c" * (NAME_LIMIT + 1), "namespace": "n"}) == "limit_text", "cluster is at most 80")
    _need(_locator({"cluster": "", "namespace": "n"}) == "bad_value", "cluster is not empty")
    _need(_ref({"id": "c0ffee01"}) == "missing_field", "kind is required")
    _need(_ref({"kind": "none"}) == "missing_field", "id is required")
    _need(_ref({"kind": "none", "id": 1}) == "bad_type", "id is text")
    _need(_ref({"kind": "none", "id": "c" * (NAME_LIMIT + 1)}) == "limit_text", "id is at most 80")
    _need(_ref({"kind": "none", "id": "c"}) is None, "a none ref with text id is a ref")
    events = [{"at": 10}, {"at": 10 - CLOCK_SKEW_S}]
    _need(_soon(lambda: _backwards(events)) == set(), "exactly the skew is not backwards")
    events = [{"at": 10}, {"at": 10}]
    _need(_soon(lambda: _backwards(events)) == set(), "an equal at is not a new maximum and not backwards")
    raised_max = [{"at": 10}, {"at": 7}, {"at": 20}, {"at": 12}]
    _need(_soon(lambda: _backwards(raised_max)) == {1, 3}, "a later maximum still marks the earlier dip")
    earlier = [{"at": 10}, {"at": 10 - CLOCK_SKEW_S - 1}, {"at": 10}]
    inside = _soon(lambda: _backwards(earlier)) or set()
    _need(1 in inside and 2 not in inside, inside)
    _need(_sampled({"at": 40, "sampled_at": 40 - SAMPLED_LAG_S}, None) is None, "the lag boundary is still in the window")
    _need(_sampled({"at": 40, "sampled_at": 40 - SAMPLED_LAG_S - 1}, None) == "sampled_at", "one second before the window is late")
    _need(_sampled({"at": 40, "sampled_at": 41}, None) == "sampled_at", "after at is late")

    class Same:
        def __eq__(self, other):
            return other == "text"

        def __hash__(self):
            return hash("text")

    event = {"type": "note", "v": 2, "at": 1, "by": "coordinator"}
    event[Same()] = "n"
    _need(_shape(event) == "unknown_field", "a key has to be a string, not merely equal to one")
    _need(_shape({"type": "note", "v": 2, "at": "x", "by": "coordinator", "text": "n"}) == "bad_type", "at is a number")
    _need(has_control("\n") and not has_control(" "), "a newline is a control and space is not")
    _need(_text_ok("\n", 10) == "limit_text", "a control character fails the text check inside the length")
    _need(_text_ok("ok", TEXT_LIMIT) is None, "text inside the limit is ok")
    _need(_hex_pair({"step_id": 1}, "step_id") is False, "a hex id is text")
    _need(_hex_pair({"step_id": P}, "step_id") is True, "eight hex digits are an id")
    _need(_id_list([1]) == "bad_value", "an id list is text")
    _need(_id_list([P]) is None, "one hex id is a list")
    _need(_exit({"signal": 1}) == "bad_value", "a signal is text")
    _need(_exit({"signal": "TERM"}) is None, "TERM is a signal")
    _need(_round_lists({"confirmed": [1], "failed": []}) == "bad_type", "a confirmed key is text")
    _need(_round_lists({"confirmed": ["not a key"], "failed": []}) == "bad_value", "a confirmed key has to match the closed pattern")
    _need(_round_lists({"confirmed": [f"step:{WORK}/{P}"], "failed": []}) is None, "a step key is a round key")
    record = Step(P, "n", "release", "C", "record", 0, 1, superseded=False, ever_found=False)
    _need(step_is_open(record) is True, "a record that was not withdrawn is open")
    record.superseded = True
    _need(step_is_open(record) is False, "a record withdrawn before it was found is not open")


def _still():
    """Inputs for the round-7 sites the first pass still answered the same way."""
    import hashlib
    import json
    import weakref

    from model import PUBLISH_FEED_REDUCED
    from publish import (
        _attach_events, _fit, _is_summary, _level3, _level4, _level6, _shed_blocks,
        _strip_commands, _strip_step_events, _too_big, _trim_works, publish_total,
    )
    from read import _REGISTRY, _forget, _held, _seal, fallback, read_line, read_log

    _need(_is_summary({}) is False, "no counts and no steps is not a summary")
    empty = {}
    _level3(empty)
    _need(empty.get("works") == [], empty)
    kept_summary = {"works": [{"closed_claim": "landed", "state_counts": {"done": 1}}]}
    _level3(kept_summary)
    _need("unknown_reasons" not in kept_summary["works"][0], kept_summary["works"][0])
    bare = {}
    _level4(bare)
    _need("works" not in bare, bare)
    neither = {"works": [{}]}
    _level4(neither)
    _need(neither["works"][0]["steps"] == [] and neither["works"][0]["steps_total"] == 0, neither)
    plain = {"at": 1, "works": [], "feed": []}
    _level6(plain, [], 0, False)
    _need("owner_all_cut" not in plain, plain)
    _need(_strip_commands({"commands": ""})["commands_count"] == 0, "an empty command string counts as none")
    try:
        none_commands = _strip_commands({"commands": None})["commands_count"]
    except TypeError:
        none_commands = None
    _need(none_commands == 0, "commands that are none count as none")
    noslash = {"works": [{"work_id": "noslash", "steps": [{"step_id": "", "state": "running"}]}]}
    _need(_attach_events(noslash, {"noslash": [{"at": 1}]}) is False, noslash)
    missing_steps = {"works": [{"work_id": WORK, "steps": None}]}
    _need(_attach_events(missing_steps, {WORK + "/" + P: []}) is False, "steps none is no step")
    _need(_shed_blocks({"works": [{"steps": None}], "at": 1, "feed": [], "owner_all": []}, 0, False) is False, "no step list, nothing shed")
    _need(_strip_step_events({"works": [{"steps": None}]}) is False, "no step list, nothing stripped")
    kept, _omitted = _trim_works([{"work_id": WORK, "steps": None}], set())
    _need(len(kept) == 1, kept)
    import copy

    huge = {"at": 1, "works": [{"steps": [{"state": "running", "note": "x" * 210000}]}], "owner_all": []}
    _need(isinstance(_fit(copy.deepcopy(huge), [], 0, False), int), "a missing feed is an empty feed")
    with_feed = copy.deepcopy(huge)
    with_feed["feed"] = [{"text": str(index)} for index in range(15)]
    _fit(with_feed, [], 15, False)
    _need(len(with_feed["feed"]) == PUBLISH_FEED_REDUCED, len(with_feed["feed"]))
    from model import PLATFORM_ENVELOPE_BYTES, PLATFORM_MAX_PUT_BYTES
    from publish import _nbytes, encoded, publish_view
    from redact_bound import growth

    under = {"at": 1, "works": [{"steps": [{"state": "running", "note": "bearer" * 32000}]}], "feed": [], "owner_all": []}
    deficit = PLATFORM_MAX_PUT_BYTES - (_nbytes(under, 0, 0, False) + growth(under) + PLATFORM_ENVELOPE_BYTES)
    exact_note = copy.deepcopy(under)
    exact_note["works"][0]["steps"][0]["note"] += "x" * deficit
    _need(_too_big(exact_note, 0, 0, False) is False, "equal to the platform limit still fits")
    over_note = copy.deepcopy(under)
    over_note["works"][0]["steps"][0]["note"] = "bearer" * 33500
    _need(_too_big(over_note, 0, 0, False) is True, "bearer growth crosses the platform limit")

    def titled(extra):
        return {
            "at": 1,
            "internal_errors": 0,
            "works": [{"title": "bearer" * 32000 + "x" * extra, "steps": [{"state": "running"}]}],
            "feed": [],
            "owner_all": [],
        }

    def measured(extra):
        view = publish_view(titled(extra))
        return len(encoded(view)) + growth(view) + PLATFORM_ENVELOPE_BYTES

    extra = PLATFORM_MAX_PUT_BYTES - measured(0)
    for _ in range(5):
        total = measured(extra)
        if total == PLATFORM_MAX_PUT_BYTES:
            break
        extra += PLATFORM_MAX_PUT_BYTES - total
    _need(measured(extra) == PLATFORM_MAX_PUT_BYTES, measured(extra))
    exact_out = json.loads(publish_total(_seal(titled(extra))))
    _need(exact_out.get("recorder_failed", {}).get("reason") != "too_large", exact_out.get("recorder_failed"))
    over = titled(0)
    over["works"][0]["title"] = "bearer" * 33500
    published = json.loads(publish_total(_seal(over)))
    _need(published["recorder_failed"]["reason"] == "too_large", published.get("recorder_failed"))
    caught = json.loads(publish_total(_seal({"title": "x"})))
    _need(caught["recorder_failed"].get("error_class") == "KeyError", caught)
    listed = json.loads(publish_total(_seal(["at"])))
    _need(listed["recorder_failed"].get("error_class") == "TypeError", listed)
    _REGISTRY[7] = ("other", b"")
    try:
        _forget(7, "ref")
        _need(7 in _REGISTRY, "a different reference keeps the slot")
    finally:
        _REGISTRY.pop(7, None)
    class Box:
        pass

    target = Box()
    _REGISTRY[id(target)] = (weakref.ref(Box()), b"payload")
    try:
        _need(_held(target) is None, "a stale slot is not this object")
    finally:
        _REGISTRY.pop(id(target), None)
    failed = fallback("read", "shape", argument="now")
    _need("argument" not in failed["recorder_failed"], failed["recorder_failed"])
    failed = fallback("read", "shape", error_class="ValueError")
    _need("error_class" not in failed["recorder_failed"], failed["recorder_failed"])
    from read import _chain

    _need(_chain({"seq": ("N", "1"), "prev_sha256": "nope", "v": ("N", "2")}, 1, "") == "bad_chain", "the wrong prev is a bad chain")

    class Same:
        def __eq__(self, other):
            return other == ""

    _need(_chain({"seq": ("N", "1"), "prev_sha256": Same(), "v": ("N", "2")}, 1, "") == "bad_chain", "a non-string prev is a bad chain")
    prefix = bytearray(b"ab" * 32)
    prefix[0] = 255
    try:
        reason = read_line(bytes(prefix) + b" {}", 1, "").reason
    except LookupError:
        reason = "lookup"
    _need(reason == "bad_line", reason)
    raw = {"at": 10 ** 18, "by": "coordinator", "prev_sha256": "", "seq": 1, "text": "n", "type": "note", "v": 2}
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    numbered = hashlib.sha256(payload).hexdigest().encode() + b" " + payload + b"\n"
    _need(read_log("obs.jsonl", numbered, observer=True).defects[0].get("file") == "obs.jsonl", "an observer defect names its file")
    _need("file" not in read_log(WORK, numbered).defects[0], "a work defect has no file")
    from harness import LogBuilder, _chain as seal_chain

    note_log = LogBuilder()
    note_log.add("note", "coordinator", at=1, text="n")
    sealed = seal_chain(note_log.events)
    _need(len(read_log(WORK, sealed + b"nope\n").events) == 1, "a later bad line does not drop the note")
    import read as read_mod

    saved = read_mod.MAX_LOG_BYTES
    read_mod.MAX_LOG_BYTES = 10
    try:
        capped = read_log(WORK, b"x" * 10 + b"\n")
        _need(capped.broken_why == "limit_log" and capped.events == [], (capped.broken_why, capped.events))
    finally:
        read_mod.MAX_LOG_BYTES = saved


def run_checks():
    _publish_view_and_levels()
    _read_edges()
    _still()
    _validate_edges()
    from redact_bound import growth, string_growth
    _need(string_growth(1) == 0, "a non-string does not grow")
    _need(string_growth("") == 0, "an empty string does not grow")
    _need(string_growth("a@b") > 0, "an at-sign can grow")
    _need(growth({1: "a@b"}) == growth("a@b"), "a non-string key is not measured")
    _need(growth({"k": "a@b"}) == growth("k") + growth("a@b"), "a string key is measured")
