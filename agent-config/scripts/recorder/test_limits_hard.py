"""Limits written as numbers, so raising the constant fails the test."""

from __future__ import annotations

import hashlib

from harness import WORK, LogBuilder, _chain, fold_one
from model import MAX_EVENTS
from read import read_log


def test_line_of_131073_bytes_is_limit_line():
    loaded = read_log(WORK, b"a" * 131073 + b"\n")
    assert loaded.broken_why == "limit_line"


def test_sixteen_mebibytes_is_limit_log():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    for index in range(170):
        log.add("note", "coordinator", text="n" * 100000)
    from harness import _chain

    loaded = read_log(WORK, _chain(log.events))
    assert loaded.broken_why == "limit_log"
    assert loaded.broken_line is not None
    assert loaded.full is False


def test_twenty_thousand_and_one_lines_is_limit_log():
    log = LogBuilder()
    for _ in range(MAX_EVENTS + 1):
        log.add("note", "coordinator", at=1, text="n")
    loaded = read_log(WORK, _chain(log.events))
    assert loaded.broken_line == MAX_EVENTS + 1
    assert loaded.broken_why == "limit_log"
    assert loaded.full is False


def test_a_title_of_81_codepoints_is_limit_text():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="n" * 81)
    doc = fold_one(log.events, 1)
    assert doc["works"][0]["defects"][0]["reason"] == "limit_text"


def test_a_note_of_201_codepoints_is_limit_text():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("note", "coordinator", at=2, text="n" * 201)
    doc = fold_one(log.events, 2)
    assert any(item["reason"] == "limit_text" for item in doc["works"][0]["defects"])


def test_a_command_of_401_codepoints_is_limit_text():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add(
        "owner_wait_opened", "coordinator", wait_id="f1b2c3d4", title="请看",
        ref={"kind": "none", "id": "c0ffee01"}, can_act="yes", where="terminal",
        commands=["c" * 401],
    )
    doc = fold_one(log.events, 2)
    assert any(item["reason"] == "limit_text" for item in doc["works"][0]["defects"])


def test_two_hundred_one_steps_is_too_many():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    for index in range(201):
        log.add(
            "step_declared", "coordinator",
            step_id=f"{index:08x}", name="n", kind="other", who="C", watch="none",
        )
    doc = fold_one(log.events, 1)
    assert any(item["reason"] == "too_many_steps" for item in doc["works"][0]["defects"])


def test_twenty_one_open_waits_is_too_many():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    for index in range(21):
        log.add(
            "owner_wait_opened", "coordinator",
            wait_id=f"{index:08x}", title="请看",
            ref={"kind": "none", "id": f"{index:08x}"}, can_act="yes",
        )
    doc = fold_one(log.events, 1)
    assert any(item["reason"] == "too_many_waits" for item in doc["works"][0]["defects"])


def test_depth_nine_is_limit_depth():
    nested = "[" * 9 + "]" * 9
    body = '{"type":"note","v":2,"seq":1,"prev_sha256":"","at":1,"by":"coordinator","text":"n","extra":' + nested + "}"
    line = (hashlib.sha256(body.encode()).hexdigest() + " " + body + "\n").encode()
    loaded = read_log(WORK, line)
    assert loaded.broken_why == "limit_depth"
