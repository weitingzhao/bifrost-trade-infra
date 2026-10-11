"""T52 and T56."""

from __future__ import annotations

import os
import threading

import pytest

from commands import cmd_next_round, cmd_run
from errors import LaneError
from events import append_obj
from locks import acquire, release
from recorder import mark_started, open_intent_only
from support import implement_ok, make_lane, review_ok, verify_ok


def _hold(paths, ready, stop):
    fds = [acquire(path, command) for path, command in paths]
    ready.set()
    stop.wait(15)
    for fd in reversed(fds):
        release(fd)


def test_t52_gates_keep_their_order(tmp_path, monkeypatch):
    lane = make_lane(tmp_path, max_rounds=3)
    implement_ok(lane)
    verify_ok(lane)
    review_ok(lane)
    assert lane.status()["state"] == "passed"
    path = lane.dir / "events.jsonl"
    original = path.read_bytes()
    blob = bytearray(original)
    cut = blob.find(b"\n") + 1
    blob[cut + 4] = ord("0") if blob[cut + 4] != ord("0") else ord("1")
    path.write_bytes(bytes(blob))
    monkeypatch.setenv("LANE_EXEC", "1")

    def attempt():
        cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))

    with pytest.raises(LaneError, match="a lane step cannot change a lane"):
        attempt()
    monkeypatch.delenv("LANE_EXEC")
    started = threading.Event()
    stop = threading.Event()
    thread = threading.Thread(
        target=_hold,
        args=([(lane.dir / "lock", "run"), (lane.dir / "run.lock", "run")], started, stop),
    )
    thread.start()
    assert started.wait(5)
    try:
        with pytest.raises(LaneError, match=f"lane {lane.lane_id} is being driven by pid {os.getpid()}") as caught:
            attempt()
        assert caught.value.exit_code == 3
    finally:
        stop.set()
        thread.join(5)
    with pytest.raises(LaneError, match=r"event log invalid at seq \d+; a person must inspect it"):
        attempt()
    path.write_bytes(original)
    with pytest.raises(LaneError, match=f"lane {lane.lane_id} passed in round 1; it is closed"):
        attempt()


def test_t56_reader_snapshot(tmp_path):
    pending = make_lane(tmp_path, "flush", max_rounds=3)
    implement_ok(pending, exit_code=9, write_verdict=False)
    calls = {"n": 0}

    def flush_once():
        if calls["n"]:
            return
        calls["n"] += 1
        with pytest.raises(LaneError):
            cmd_run(pending.root, pending.lane_id)

    shown = pending.status(gap=flush_once)
    assert shown["state"] == "step_failed"
    assert shown["state"] != "unknown"

    moving = make_lane(tmp_path, "move")

    def always():
        append_obj(moving.dir, {"type": "note", "text": "tick"})

    assert moving.status(gap=always)["state"] == "changing"

    held = make_lane(tmp_path, "held")
    mark_started(held.dir, open_intent_only(held.dir))
    started = threading.Event()
    stop = threading.Event()
    thread = threading.Thread(target=_hold, args=([(held.dir / "lock", "resolve")], started, stop))
    thread.start()
    assert started.wait(5)
    try:
        status = held.status()
    finally:
        stop.set()
        thread.join(5)
    assert status["state"] == "unknown"
    assert status["busy"] == "resolve"
    assert status["state"] != "implementing"

    stale = make_lane(tmp_path, "stale")
    (stale.dir / "lock").write_text('{"command":"run","pid":1,"since":"2000-01-01T00:00:00Z"}\n')
    (stale.dir / "run.lock").write_text('{"command":"run","pid":1,"since":"2000-01-01T00:00:00Z"}\n')
    quiet = stale.status()
    assert quiet["driver"] is False
    assert quiet["state"] == "ready"

    driven = make_lane(tmp_path, "driven", max_rounds=3)
    implement_ok(driven, exit_code=9, write_verdict=False)
    started = threading.Event()
    stop = threading.Event()
    thread = threading.Thread(target=_hold, args=([(driven.dir / "run.lock", "run")], started, stop))
    thread.start()
    assert started.wait(5)
    try:
        status = driven.status()
    finally:
        stop.set()
        thread.join(5)
    assert status["display"] == "implementing"
    assert not str(status["display"]).startswith("verdict_pending")
