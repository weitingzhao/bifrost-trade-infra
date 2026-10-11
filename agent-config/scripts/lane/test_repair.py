"""T47 (B1, B2, B8-B10) and T55."""

from __future__ import annotations

from commands import cmd_abandon, cmd_new, cmd_next_round, cmd_status
from errors import LaneError
from events import load_file
from fsutil import publish
from repair import repair_id, repair_torn_tail
from support import implement_ok, make_lane
import pytest


def _torn_names(lane) -> list[str]:
    return sorted(
        path.name
        for path in lane.dir.iterdir()
        if path.is_file() and path.name.startswith("events.torn-") and ".tmp-" not in path.name
    )


def _repairs(lane) -> list[dict]:
    return [event for event in lane.events() if event["type"] == "tail_repaired"]


def test_t47_boundaries_b1_b2_b8_b9_b10(tmp_path):
    root = tmp_path / "lanes"
    root.mkdir()
    (root / "L").mkdir()
    shown = cmd_status(root, "L")
    assert shown["display"] == "incomplete lane directory"
    brief = tmp_path / "brief.md"
    brief.write_text("task\n")
    with pytest.raises(LaneError, match="lane L exists"):
        cmd_new(root, "L", title="Title", brief=str(brief), repos={"repo": {"role": "change", "target_ref": "main", "target_sha": "a" * 40}})

    lane = make_lane(tmp_path, "B2")
    implement_ok(lane, exit_code=9)
    before = lane.status()
    (lane.dir / "r2").mkdir()
    publish(lane.dir / "r2" / "brief-deadbeef.md", b"not opened\n")
    assert lane.status()["state"] == before["state"] == "step_failed"
    assert lane.status()["opened"] == before["opened"]
    assert lane.status()["round"] == 1
    cmd_next_round(lane.root, lane.lane_id, brief=str(lane.brief))
    assert lane.status()["state"] == "ready"
    assert lane.status()["round"] == 2

    continued = make_lane(tmp_path, "B8a", max_rounds=3)
    implement_ok(continued, write_verdict=False)
    assert continued.status()["state"] == "ready"
    assert continued.status()["next_step"] == "verify"
    terminal = make_lane(tmp_path, "B8b", max_rounds=3)
    implement_ok(terminal, exit_code=9, write_verdict=False)
    assert terminal.status()["display"] == "verdict_pending (step_failed)"

    torn = make_lane(tmp_path, "B9")
    intact = torn.status()["state"]
    path = torn.dir / "events.jsonl"
    path.write_bytes(path.read_bytes() + b"torn-tail")
    assert torn.status()["state"] == intact
    cmd_abandon(torn.root, torn.lane_id, operator="ada", reason="repair")
    assert len(_torn_names(torn)) == 1
    assert len(_repairs(torn)) == 1
    seqs = [event["seq"] for event in torn.events()]
    assert seqs == list(range(1, len(seqs) + 1))
    assert load_file(path).invalid_seq is None

    # B10: one of the four crash points; T55 covers all four.
    crash = make_lane(tmp_path, "B10")
    blob = (crash.dir / "events.jsonl").read_bytes()
    offset = len(blob)
    piece = b"half"
    (crash.dir / f"events.torn-{repair_id(offset, piece)}").write_bytes(piece)
    (crash.dir / "events.jsonl").write_bytes(blob + piece)
    repair_torn_tail(crash.dir)
    repair_torn_tail(crash.dir)
    assert len(_torn_names(crash)) == 1
    assert len(_repairs(crash)) == 1


def test_t55_repair_is_idempotent_at_every_crash_point(tmp_path):
    lane = make_lane(tmp_path, "P1")
    path = lane.dir / "events.jsonl"
    original = path.read_bytes()
    torn = b"not-a-line"
    offset = len(original)
    rid = repair_id(offset, torn)
    (lane.dir / f".events.torn-{rid}.tmp-deadbeef").write_bytes(b"wrong-temp")
    path.write_bytes(original + torn)
    repair_torn_tail(lane.dir)
    assert _torn_names(lane) == [f"events.torn-{rid}"]
    assert (lane.dir / f"events.torn-{rid}").read_bytes() == torn
    assert [event["repair_id"] for event in _repairs(lane)] == [rid]
    assert (lane.dir / f".events.torn-{rid}.tmp-deadbeef").read_bytes() == b"wrong-temp"

    renamed = make_lane(tmp_path, "P2")
    raw = (renamed.dir / "events.jsonl").read_bytes()
    rid2 = repair_id(len(raw), torn)
    (renamed.dir / f"events.torn-{rid2}").write_bytes(torn)
    (renamed.dir / "events.jsonl").write_bytes(raw + torn)
    repair_torn_tail(renamed.dir)
    assert _torn_names(renamed) == [f"events.torn-{rid2}"]
    assert len(_repairs(renamed)) == 1

    truncated = make_lane(tmp_path, "P3")
    raw = (truncated.dir / "events.jsonl").read_bytes()
    rid3 = repair_id(len(raw), torn)
    (truncated.dir / f"events.torn-{rid3}").write_bytes(torn)
    repair_torn_tail(truncated.dir)
    assert len(_repairs(truncated)) == 1
    repair_torn_tail(truncated.dir)
    assert _torn_names(truncated) == [f"events.torn-{rid3}"]
    assert len(_repairs(truncated)) == 1

    done = make_lane(tmp_path, "P4")
    raw = (done.dir / "events.jsonl").read_bytes()
    (done.dir / "events.jsonl").write_bytes(raw + torn)
    repair_torn_tail(done.dir)
    repair_torn_tail(done.dir)
    assert len(_torn_names(done)) == 1
    assert len(_repairs(done)) == 1
    assert load_file(done.dir / "events.jsonl").invalid_seq is None

    again = make_lane(tmp_path, "P5")
    base = (again.dir / "events.jsonl").read_bytes()
    first = b"original-tear"
    first_id = repair_id(len(base), first)
    (again.dir / f"events.torn-{first_id}").write_bytes(first)
    partial = b"tail_repaired-half"
    (again.dir / "events.jsonl").write_bytes(base + partial)
    repair_torn_tail(again.dir)
    names = _torn_names(again)
    assert len(names) == 2
    events = _repairs(again)
    assert len(events) == 2
    by_id = {event["repair_id"]: event for event in events}
    assert by_id[first_id]["bytes"] == len(first)
    second_id = repair_id(len(base), partial)
    assert (again.dir / f"events.torn-{second_id}").read_bytes() == partial
    assert by_id[second_id]["sha256"]
    assert load_file(again.dir / "events.jsonl").invalid_seq is None

    bad = make_lane(tmp_path, "P6")
    target = bad.dir / "events.jsonl"
    blob = bytearray(target.read_bytes())
    cut = blob.rfind(b"\n", 0, len(blob) - 1) + 1
    blob[cut + 1] = ord("0") if blob[cut + 1] != ord("0") else ord("1")
    target.write_bytes(bytes(blob))
    before = target.read_bytes()
    repair_torn_tail(bad.dir)
    assert target.read_bytes() == before
    status = bad.status()
    assert status["state"] == "unknown"
    assert status["reason"].startswith("event log invalid at seq ")


def test_publish_writes_every_byte(tmp_path, monkeypatch):
    import os

    import fsutil

    real = os.write

    def one_byte(fd, data):
        return real(fd, bytes(data[:1]))

    monkeypatch.setattr(fsutil.os, "write", one_byte)
    dest = tmp_path / "events.torn-piece"
    fsutil.publish(dest, b"abcdef")
    assert dest.read_bytes() == b"abcdef"
    fsutil.write_bytes(tmp_path / "stdout", b"xyz")
    assert (tmp_path / "stdout").read_bytes() == b"xyz"


def test_publish_rejects_a_zero_write(tmp_path, monkeypatch):
    import fsutil

    monkeypatch.setattr(fsutil.os, "write", lambda fd, data: 0)
    with pytest.raises(OSError, match="returned 0"):
        fsutil.publish(tmp_path / "events.torn-piece", b"abcdef")
    assert not (tmp_path / "events.torn-piece").exists()
