"""Chain, torn tail, the lock, and the full-log refusal.

The fold of a broken or full log, and two writers going through the
commands, are covered with the fold tests.
"""

from __future__ import annotations

import os
from pathlib import Path

from events import MAX_BYTES, MAX_EVENTS, Log, append_sealed, dump_line, load_bytes, load_file, seal
from fsutil import write_all
from locks import LockBusy, hold
from repair import repair_torn_tail

WORK = "w1"
P = "a1b2c3d4"
RUN = "d1b2c3d4"


def _note_line(seq: int, prev: str, text: str = "n") -> tuple[bytes, str]:
    obj = {
        "type": "note",
        "v": 2,
        "seq": seq,
        "prev_sha256": prev,
        "at": seq,
        "by": "coordinator",
        "text": text,
    }
    line = dump_line(obj)
    return line, line.split(b" ", 1)[0].decode("ascii")


def save_log(directory: Path, specs: list[tuple]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    log = Log()
    lines = []
    for by, at, fields in specs:
        sealed = seal(dict(fields), log, by, at)
        line = dump_line(sealed)
        log.events.append(sealed)
        log.digests.append(line.split(b" ", 1)[0].decode("ascii"))
        lines.append(line)
    (directory / "events.jsonl").write_bytes(b"".join(lines))


def _chain(n: int, text: str = "n") -> bytes:
    prev = ""
    lines = []
    for seq in range(1, n + 1):
        line, prev = _note_line(seq, prev, text)
        lines.append(line)
    return b"".join(lines)


def test_links_run_from_the_empty_prefix(tmp_path):
    blob = _chain(4)
    log = load_bytes(blob)
    assert log.invalid_seq is None
    assert [event["seq"] for event in log.events] == [1, 2, 3, 4]
    assert log.events[0]["prev_sha256"] == ""
    assert log.events[1]["prev_sha256"] == log.digests[0]


def test_middle_byte_is_not_truncated_and_append_is_refused(tmp_path):
    specs = [
        ("coordinator", 1, {"type": "work_opened", "work_id": WORK, "title": "T"}),
        ("coordinator", 2, {"type": "step_declared", "step_id": P, "name": "done", "kind": "other", "who": "C", "watch": "none"}),
        ("coordinator", 3, {"type": "step_started", "step_id": P, "run_id": RUN}),
        ("coordinator", 4, {"type": "step_finished", "step_id": P, "run_id": RUN, "reported": "finished"}),
        ("coordinator", 5, {"type": "step_declared", "step_id": "b9b9b9b9", "name": "open", "kind": "other", "who": "C", "watch": "none"}),
        ("coordinator", 6, {"type": "step_started", "step_id": "b9b9b9b9", "run_id": "c9c9c9c9"}),
        ("coordinator", 7, {"type": "note", "text": "tail"}),
    ]
    directory = tmp_path / WORK
    save_log(directory, specs)
    path = directory / "events.jsonl"
    raw = bytearray(path.read_bytes())
    # Corrupt the note, the last complete line, by flipping one byte of its body.
    # A line in the middle is the started-open step's line: flip a byte there.
    lines = bytes(raw).split(b"\n")
    target = lines[5]
    flipped = bytearray(target)
    flipped[70] ^= 0x01
    lines[5] = bytes(flipped)
    path.write_bytes(b"\n".join(lines))
    before = path.read_bytes()
    loaded = load_file(path)
    assert loaded.invalid_seq is not None
    try:
        append_sealed(path, {"type": "note", "v": 2, "seq": 99, "prev_sha256": "", "at": 9, "by": "coordinator", "text": "no"})
    except ValueError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("append was accepted")
    assert path.read_bytes() == before


def test_closed_prefix_stays_closed_when_the_tail_breaks(tmp_path):
    specs = [
        ("coordinator", 1, {"type": "work_opened", "work_id": WORK, "title": "T"}),
        ("coordinator", 2, {"type": "work_closed", "claim": "stopped"}),
        ("coordinator", 3, {"type": "note", "text": "after"}),
    ]
    directory = tmp_path / WORK
    save_log(directory, specs)
    path = directory / "events.jsonl"
    lines = path.read_bytes().split(b"\n")
    bad = bytearray(lines[2])
    bad[80] ^= 0x01
    lines[2] = bytes(bad)
    path.write_bytes(b"\n".join(lines))
    loaded = load_file(path)
    assert loaded.invalid_seq is not None
    assert loaded.events[1]["type"] == "work_closed"


def test_torn_tail_is_saved_once_and_recorded(tmp_path):
    directory = tmp_path / WORK
    save_log(directory, [("coordinator", 1, {"type": "work_opened", "work_id": WORK, "title": "T"})])
    path = directory / "events.jsonl"
    path.write_bytes(path.read_bytes() + b'{"torn":')
    first = repair_torn_tail(directory, at=2)
    assert first is not None
    saved = directory / f"events.torn-{first}"
    assert saved.read_bytes() == b'{"torn":'
    assert path.read_bytes().endswith(b"\n")
    log = load_file(path)
    assert log.invalid_seq is None
    assert log.events[-1]["type"] == "tail_repaired"
    assert log.events[-1]["repair_id"] == first
    again = repair_torn_tail(directory, at=3)
    assert again is None
    assert len([event for event in load_file(path).events if event["type"] == "tail_repaired"]) == 1


def test_repair_records_a_torn_file_left_after_the_truncate(tmp_path):
    directory = tmp_path / WORK
    save_log(directory, [("coordinator", 1, {"type": "note", "text": "ok"})])
    torn = b'{"half":'
    from repair import repair_id
    from fsutil import publish

    rid = repair_id(path_size(directory / "events.jsonl"), torn)
    publish(directory / f"events.torn-{rid}", torn)
    assert repair_torn_tail(directory, at=4) is None
    kinds = [event["type"] for event in load_file(directory / "events.jsonl").events]
    assert kinds[-1] == "tail_repaired"


def path_size(path: Path) -> int:
    return path.stat().st_size


def test_zero_write_is_an_error(tmp_path, monkeypatch):
    path = tmp_path / "out"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o644)

    def zero(_fd, _data):
        return 0

    monkeypatch.setattr(os, "write", zero)
    try:
        try:
            write_all(fd, b"abc")
        except OSError as exc:
            assert "0" in str(exc)
        else:
            raise AssertionError("zero write was accepted")
    finally:
        os.close(fd)


def test_a_held_lock_is_busy(tmp_path):
    directory = tmp_path / WORK
    directory.mkdir()
    with hold(directory, "test-hold"):
        try:
            with hold(directory, "other", timeout=0):
                raise AssertionError("second hold was taken")
        except LockBusy as exc:
            assert "lock busy" in str(exc)
            assert "test-hold" in str(exc)


def test_twenty_thousand_events_refuse_another(tmp_path):
    blob = _chain(MAX_EVENTS)
    path = tmp_path / "events.jsonl"
    path.write_bytes(blob)
    log = load_bytes(blob)
    assert log.full
    try:
        append_sealed(
            path,
            {
                "type": "note",
                "v": 2,
                "seq": MAX_EVENTS + 1,
                "prev_sha256": log.digests[-1],
                "at": 1,
                "by": "coordinator",
                "text": "more",
            },
        )
    except ValueError as exc:
        assert "full" in str(exc)
    else:
        raise AssertionError("full log accepted an append")


def test_sixteen_mebibytes_refuses_another(tmp_path):
    prev = ""
    line, prev = _note_line(1, prev, "x" * (MAX_BYTES + 10))
    path = tmp_path / "events.jsonl"
    path.write_bytes(line)
    loaded = load_bytes(line)
    assert loaded.full is False
    assert loaded.invalid_seq == 1
    try:
        append_sealed(
            path,
            {
                "type": "note",
                "v": 2,
                "seq": 2,
                "prev_sha256": prev,
                "at": 2,
                "by": "coordinator",
                "text": "more",
            },
        )
    except ValueError as exc:
        assert "invalid" in str(exc)
    else:
        raise AssertionError("oversized log accepted an append")
