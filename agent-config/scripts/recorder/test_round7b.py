"""More round-7 checks. Split so no recorder module exceeds 800 lines."""
from test_round7 import (
    APPR, M, P, R, RUN, SHA, WAIT, WAIT2, WORK,
    _chain, _need,
)

def _direct_edges():
    """Boundaries the field table does not reach: numbers, lines, and kept markers."""
    import hashlib
    from model import MAX_DEPTH, MAX_LINE_BYTES
    from read import _int_token, _norm, prescan, read_line
    from survive import apply_keep

    _need(_int_token(1) is None, "an integer token is a pair")
    _need(_int_token(("N", "3", "x")) is None, "the pair has two slots")
    _need(_int_token(("X", "3")) is None, "the tag is N")
    _need(_int_token(("N", "1" * 18)) is None, "18 digits are not an integer token")
    _need(_int_token(("N", "1" * 17)) == int("1" * 17), "17 digits are still an integer token")
    _need(_int_token(("N", "1" * 16)) == int("1" * 16), "16 digits are an integer token")
    _need(_int_token(("N", "zz")) is None, "a non-digit token is not an integer")
    _need(_norm(0.0) == 0 and type(_norm(0.0)) is int, "-0 and 0 become the integer 0")
    _need(_norm(-0.0) == 0 and type(_norm(-0.0)) is int, "negative zero becomes the integer 0")
    _need(_norm(1.5) == 1.5, "a non-zero float stays a float")
    _need(_norm({"a": 0.0}) == {"a": 0}, "zero inside an object is normalized")
    _need(_norm([0.0]) == [0], "zero inside a list is normalized")
    _need(_norm(1) == 1, "an integer stays")
    braces = b"{" * (MAX_DEPTH + 1)
    _need(prescan(b"{" * MAX_DEPTH) is None, "eight braces are still shallow")
    _need(prescan(braces) == "limit_depth", "nine braces are too deep")
    exact = b"a" * MAX_LINE_BYTES
    _need(read_line(exact, 1, "").reason != "limit_line", "a line of the maximum length is not over the limit")
    over = b"a" * (MAX_LINE_BYTES + 1)
    _need(read_line(over, 1, "").reason == "limit_line", "one byte over the limit stops the line")

    def sealed(body: bytes):
        digest = hashlib.sha256(body).hexdigest().encode()
        return read_line(digest + b" " + body, 1, "")

    _need(sealed(b'{"a":1,"a":2}').reason == "dup_key", "a repeated key is dup_key")
    _need(sealed(b"[1]").reason == "not_object", "a line has to be an object")
    bad_hex = b"g" * 64 + b" {}"
    _need(read_line(bad_hex, 1, "").reason == "bad_line", "the digest is 64 hex characters")

    doc = {"works": [{"state_counts": ["no"], "steps": [{"state": "running"}]}], "owner_all": [{"can_act": "not_yet"}]}
    apply_keep(doc, 7)
    _need(doc["owner_all"][0]["can_act"] == "not_yet", "only an unknown owner item is rewritten")
    _need(doc["works"][0]["steps"][0]["state"] == "running", "only an unknown step is rewritten")
    _need("gap" not in doc["works"][0], "a zero gap flag does not mark a gap")
    bare = {}
    apply_keep(bare, 7)
    _need(bare == {}, "a document without works is unchanged")
    counted = {"works": [{"state_counts": {"waiting": 1}, "steps": []}]}
    apply_keep(counted, 7)
    _need(counted["works"][0]["state_counts"] == {"waiting": 1}, "a count with no unknown stays")


def _ball_rules():
    """Section 4 holder times, and which steps still block a close."""
    from fold import _watched_step
    from ownerball import _effect, _ended_at, _in_flight_since, _not_yet_since, _owner_since, _running_since
    from publish import _owner_ids, _shed_blocks
    from survive import apply_keep
    from validate import Step, View, Wait, step_is_open

    view = View(work_id=WORK)
    view.valid = [{"type": "work_opened", "at": 3}]
    flight = Wait(WAIT, "a", {"kind": "none", "id": "c0"}, 0, 10)
    flight.seen = [{"ref_state": "approved", "sampled_at": 4}, {"ref_state": "running", "sampled_at": 8}]
    later = Wait(WAIT2, "b", {"kind": "none", "id": "c1"}, 1, 20)
    later.yes_at = 6
    view.waits = {WAIT: flight, WAIT2: later}
    merged = {
        ("none", WORK, WAIT): {"status": "in_flight"},
        ("none", WORK, WAIT2): {"status": "yes", "declared": True},
    }
    _need(_in_flight_since(view, merged) == 4, "in flight starts at the first approved sample")
    _need(_owner_since(view, merged) == 6, "a declared yes uses yes_at")
    later_status = {("none", WORK, WAIT2): {"status": "not_yet"}}
    _need(_not_yet_since(view, later_status) == 20, "not yet starts when that wait opened")
    record = Step(R, "r", "release", "C", "record", 0, 1)
    record.record_obs = [{"condition": "True", "started_at": 1}, {"found": True, "started_at": 9}]
    view.steps = {R: record}
    _need(_running_since(view, [{"step_id": R}]) == 9, "a terminal record observation is not the running start")
    record.finished = {"at": 12}
    _need(_ended_at(record) == 12, "a finish event supplies the end")
    record.finished = {}
    record.record_obs = [{"ended_at": 6}]
    _need(_ended_at(record) == 6, "otherwise the record observation does")
    _need(_ended_at(None) is None, "a missing step has no end")
    record.usual_s = 5
    _need(_effect(view, [R]) == 5, "the first held step's usual time is the effect")
    _need(_effect(view, []) is None and _effect(view, ["missing"]) is None, "no hold has no effect")
    withdrawn = Step(R, "r", "release", "C", "record", 0, 1, superseded=True)
    _need(step_is_open(withdrawn) is False, "a record withdrawn before it was found is not open")
    withdrawn.ever_found = True
    _need(step_is_open(withdrawn) is True, "a found record stays open until it ends")
    process = Step(P, "n", "implement", "C", "process", 0, 1, superseded=True)
    _need(step_is_open(process) is False, "a process withdrawn before it started is not open")
    process.started = True
    process.dead = True
    _need(step_is_open(process) is False, "dead is not open")
    process.dead = False
    _need(step_is_open(process) is True, "a started process is open")
    process.ended = True
    _need(step_is_open(process) is False, "an ended step is not open")
    dead = Step(P, "n", "implement", "wrapper", "process", 0, 1, started=True, started_at=5)
    dead.dead = True
    dead.seen = [{"alive": False, "sampled_at": 9}]
    public, row = _watched_step(dead, view, 10)
    _need(row == "dead" and public["started"] == 5 and public["since"] == 9, (row, public))
    waiting = Step(P, "n", "implement", "C", "process", 0, 1)
    waiting.declared_by = "wrapper"
    public, row = _watched_step(waiting, view, 10)
    _need(row == "unknown" and public.get("reason") == "start_not_recorded", (row, public))
    waiting.declared_by = "coordinator"
    public, row = _watched_step(waiting, view, 10)
    _need(row == "waiting", row)
    _need(_owner_ids([{"works": [{"work_id": WORK}]}, "x", {}]) == {WORK}, "owner ids come from work pieces")
    _need(_owner_ids([{"works": [{"work_id": ""}]}]) == set(), "an empty work id is not an owner id")
    huge = {"at": 1, "works": [{"steps": [{"events": ["x" * 300000]}]}]}
    _shed_blocks(huge, 0, False)
    _need("events" not in huge["works"][0]["steps"][0], "events are the first block shed when the document is over the limit")
    apply_keep({"works": [{}]}, 7)
    _need(True, "a work without steps is left alone")


def _small_rules():
    """Bounds and defaults that sit under the tables: one value on each side."""
    from model import terminal_state
    from ownerball import _open_merged, _substantive
    from model import PUBLISH_MAX_OWNER_ALL
    from publish import _counts, _known, _owner_now_ok, _summary, _trim_owner, _works_total
    from read import _in_range, class_name
    from validate import MAX_COMMANDS, View, Wait, _commands, has_control, is_number

    counted = _summary({"_state_counts": {"unknown": 2}, "steps": [{"state": "running"}]})
    _need(counted["state_counts"] == {"unknown": 2}, "a stored count is kept")
    fresh = _summary({"steps": [{"state": "running"}, {"state": "unknown", "reason": "clock"}, {"state": "unknown", "reason": 1}]})
    _need(fresh["unknown_reasons"] == ["clock"], fresh)
    _need(fresh["state_counts"]["running"] == 1 and fresh["state_counts"]["unknown"] == 2, fresh["state_counts"])
    both = _summary({"_all_steps": [{"state": "running"}], "steps": [{"state": "waiting"}]})
    _need(both["state_counts"]["running"] == 1 and both["state_counts"]["waiting"] == 0, "the full step list is counted")
    _need(_summary({"defects": [1, 2]})["defects_count"] == 2, "defects are counted")
    _need(_summary({})["defects_count"] == 0, "no defects is zero")
    _need(_counts([{"state": "running"}, {"state": "nope"}], None)["unknown"] == 1, "an unlisted state counts as unknown")
    _need(_counts([], {"running": 2})["running"] == 2, "omitted counts are added")
    _need(_known({"sure": True}, "", set(), set(), {"sure"}) is True, "a flag is a boolean")
    _need(_known({"sure": 1}, "", set(), set(), {"sure"}) is False, "a flag is not an integer")
    view = View(work_id=WORK)
    view.valid = [{"type": "work_opened", "at": 3}, {"type": "note", "at": 9}, {"type": "tail_repaired", "at": 8}]
    view.waits = {
        WAIT: Wait(WAIT, "a", {"kind": "none", "id": "c"}, 0, 1),
        WAIT2: Wait(WAIT2, "b", {"kind": "none", "id": "d"}, 1, 2),
    }
    merged = {("none", WORK, WAIT): {"status": "in_flight"}, ("none", WORK, WAIT2): {"status": "closed"}}
    _need([item["status"] for item in _open_merged(view, merged)] == ["in_flight"], "closed is not an open merged status")
    _need(_substantive(view) == 3, "a note and a tail repair are not the substantive time")
    _need(terminal_state("approval", "executed") is True, "executed ends an approval")
    _need(terminal_state("approval", "pending") is False, "pending does not")
    _need(terminal_state("question", "answered") is True and terminal_state("question", "open") is False, "answered ends a question")
    _need(_commands(["a"] * MAX_COMMANDS) is None, "five commands are allowed")
    _need(_commands(["a"] * (MAX_COMMANDS + 1)) == "bad_value", "six commands are not")
    _need(_commands([1]) == "bad_type", "a command is text")
    _need(has_control("\x1f") and not has_control(" "), "unit separator is a control and space is not")
    _need(is_number(1) and not is_number(True) and not is_number(float("inf")), "a number is finite and not a boolean")
    _need(_in_range(float("inf")) is False and _in_range(float("-inf")) is False and _in_range(1.0) is True, "infinity is outside the range")
    _need(class_name(ValueError("x")) == "ValueError", "an ordinary exception keeps its class name")
    _need(_owner_now_ok([{"actions": ({"a": 1},)}]) is False, "actions are a list")
    _need(_owner_now_ok([{"actions": [1]}]) is False, "an action is an object")
    cap = list(range(PUBLISH_MAX_OWNER_ALL))
    _need(_trim_owner(cap) == (cap, 0), "the owner cap itself is kept")
    _need(_trim_owner(cap + ["x"])[1] == 1, "one past the owner cap is cut")
    _need(_works_total([{"closed_claim": "landed"}, "x"]) == {"open": 1, "closed": 1}, "only an object with a claim is closed")
