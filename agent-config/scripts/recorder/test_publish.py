"""Published bytes, one fixture per reduction level, and the platform validator."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from model import (
    PLATFORM_HOST_RE,
    PLATFORM_MAX_ACTIONS,
    PLATFORM_MAX_FEED,
    PLATFORM_MAX_NEEDS_YOU,
    PLATFORM_MAX_OWNER_NOW,
    PLATFORM_MAX_PUT_BYTES,
    PLATFORM_MAX_RECENT,
    PLATFORM_MAX_STEPS,
    PLATFORM_MAX_WORKS,
    PLATFORM_STALE_S,
    PUBLISH_MAX_FEED,
    PUBLISH_MAX_OWNER_ALL,
    PUBLISH_TARGET_BYTES,
)
from harness import RUN, WAIT_D, WORK, LogBuilder, _chain
from publish import encoded, publish_total
from read import fold_total
from test_support import folded_for_test

ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT.parent / "bifrost-platform"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SUMMARY_KEYS = {
    "work_id", "title", "state_counts", "unknown_reasons", "unknown_reasons_omitted",
    "defects_count", "log_invalid_at", "log_invalid_why", "log_full", "torn_tail",
    "unrecorded_runs", "closed_claim",
}


def _blob(n: int) -> str:
    return "测" * n


def _step(state: str, note: str = "", command: str = "echo", quote: str = "") -> dict:
    step = {
        "step_id": "a1b2c3d4",
        "name": "n",
        "who": "C",
        "kind": "other",
        "watch": "process",
        "state": state,
        "command": command,
    }
    if note:
        step["note"] = note
    if quote:
        step["quote"] = quote
    return step


def _work(work_id: str, steps: list, closed: bool = False, last: int = 1) -> dict:
    work = {"work_id": work_id, "title": work_id, "source": "events", "steps": steps, "last_at": last, "defects": []}
    if closed:
        work["closed_claim"] = "stopped"
    return work


def _shell(works, feed=None, owner=None) -> dict:
    return {
        "at": 1,
        "observations_valid_s": 180,
        "fold_complete": True,
        "logs_unread": 0,
        "observer": {},
        "clock": {"reader_behind": False},
        "ball": {"holder": "nobody", "why": "queue_done", "since": 1},
        "owner_all": owner or [],
        "works": works,
        "feed": feed or [],
        "internal_errors": 0,
    }


def _through_door(doc: dict) -> dict:
    """Big reduction documents cannot be folded from a short valid log."""
    return json.loads(publish_total(folded_for_test(doc), "board"))


def _owner(title: str, text: str = "", commands=None) -> dict:
    item = {
        "source": "declared",
        "wait_id": "a2b2c3d4",
        "title": title,
        "can_act": "yes",
        "can_act_basis": "declared",
        "where": "terminal" if commands else "thread",
        "advice": text,
        "works": [{"work_id": "w1", "title": title, "holds_up": []}],
    }
    if commands:
        item["commands"] = commands
    return item


def _publish_logs(logs, now) -> dict:
    return json.loads(publish_total(fold_total(logs, [], now), "board"))


def _fat_logs(nworks, nsteps, mode, notes=0, defects=0, title="T", goal=None):
    """Real sealed logs. ``mode`` is done, running, or dead."""
    logs = []
    last = 1
    for work_index in range(nworks):
        name = f"w{work_index}"
        log = LogBuilder()
        opened = {"work_id": name, "title": title}
        if goal:
            opened["goal"] = goal
        log.add("work_opened", "coordinator", at=1, **opened)
        for step_index in range(nsteps):
            step = f"{step_index + 1:08x}"
            log.add("step_declared", "coordinator", step_id=step, name="n" * 80, kind="other", who="W" * 80, watch="process")
            log.add("step_started", "wrapper", step_id=step, run_id=RUN, command="c" * 200)
            if mode == "done":
                log.add("step_finished", "wrapper", step_id=step, run_id=RUN, exit={"code": 0}, quote="q" * 200)
            elif mode == "running":
                log.add("step_seen", "wrapper", step_id=step, run_id=RUN, sampled_at=log.at, alive=True, text="t" * 200, output_bytes=1)
            else:
                log.add("step_seen", "observer", step_id=step, run_id=RUN, sampled_at=log.at, alive=False, text="t" * 200)
        for _ in range(notes):
            log.add("note", "coordinator", text="f" * 200)
        if work_index == 0:
            for _ in range(defects):
                log.add("note", "coordinator", text="n", extra=1)
        if mode == "dead":
            log.add("work_closed", "coordinator", claim="stopped")
        last = max(last, log.at)
        logs.append((name, _chain(log.events)))
    return logs, last


def _colon_owners() -> tuple[list, int]:
    logs = []
    last = 1
    fields = {
        "advice": ":" * 200,
        "blocks_text": ":" * 200,
        "after_text": ":" * 200,
        "reply": ":" * 200,
        "reply_words": ":" * 200,
        "not_before_text": ":" * 200,
    }
    for work_index in range(2):
        name = f"w{work_index}"
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=name, title="T")
        for index in range(16):
            log.add(
                "owner_wait_opened", "coordinator", wait_id=f"{index + 1:08x}", title=":" * 80,
                ref={"kind": "none", "id": f"{index + 100:08x}"}, can_act="yes", **fields,
            )
        last = max(last, log.at)
        logs.append((name, _chain(log.events)))
    return logs, last


def levels() -> dict[str, dict]:
    """One published document per reduction level, from real folds at real sizes."""
    built = {}
    done, now = _fat_logs(30, 20, "done")
    built["level-1"] = _publish_logs(done, now)
    running, now = _fat_logs(13, 20, "running", notes=25, title="T" * 80, goal="g" * 200)
    built["level-2"] = _publish_logs(running, now)
    closed, now = _fat_logs(30, 20, "dead")
    built["level-3"] = _publish_logs(closed, now)
    running, now = _fat_logs(30, 20, "running")
    built["level-4"] = _publish_logs(running, now)
    running, now = _fat_logs(30, 20, "running", defects=5000)
    built["level-5"] = _publish_logs(running, now)
    owners, now = _colon_owners()
    built["level-6"] = _publish_logs(owners, now)
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add("step_declared", "coordinator", at=2, step_id="a1b2c3d4", name="n", who="C", kind="other", watch="none")
    log.add("step_started", "coordinator", at=3, step_id="a1b2c3d4", run_id="d1b2c3d4")
    built["level-0"] = json.loads(publish_total(fold_total([(WORK, _chain(log.events))], [], 3), "board"))
    log.add("owner_wait_opened", "coordinator", at=4, wait_id=WAIT_D, title="请看",
            ref={"kind": "none", "id": "c0ffee01"}, can_act="yes", where="terminal",
            commands=["echo a", "echo b", "echo c"])
    built["commands"] = json.loads(publish_total(fold_total([(WORK, _chain(log.events))], [], 4), "board"))
    built["redact-usage"] = json.loads(publish_total(
        fold_total([], [], 0), "board", {"usage": {"a": "pwd=x," * 17500}},
    ))
    built["redact-steps"] = _assignment_steps()
    return built


def _assignment_steps() -> dict:
    """Twelve works of running steps filled with ``pwd=x,`` up to each field cap."""
    blob = lambda n: ("pwd=x," * ((n // 6) + 1))[:n]
    logs = []
    for work_index in range(12):
        name = f"w{work_index}"
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=name, title="T")
        for step_index in range(20):
            step = f"{step_index + 1:08x}"
            log.add("step_declared", "coordinator", step_id=step, name=blob(80), kind="other", who=blob(80), watch="process")
            log.add("step_started", "wrapper", step_id=step, run_id=RUN, command=blob(200))
            log.add("step_seen", "wrapper", step_id=step, run_id=RUN, sampled_at=log.at, alive=True, text=blob(200))
        logs.append((name, _chain(log.events)))
    return _publish_logs(logs, 61)


def test_commands_are_not_published():
    log = LogBuilder()
    log.add("work_opened", "coordinator", at=1, work_id=WORK, title="T")
    log.add(
        "owner_wait_opened", "coordinator", wait_id=WAIT_D, title="请看",
        ref={"kind": "none", "id": "c0ffee01"}, can_act="yes", where="terminal",
        commands=["echo a", "echo b", "echo c"],
    )
    folded = fold_total([(WORK, _chain(log.events))], [], 1)
    local = folded.document()
    published = json.loads(publish_total(folded, "board"))
    item = published["owner_all"][0]
    assert "commands" not in item
    assert item["commands_at"] == "local_board"
    assert item["commands_count"] == 3
    assert published["full_at"] == "local_board"
    local_item = local["owner_all"][0]
    for key, value in local_item.items():
        if key == "commands":
            continue
        assert item[key] == value


def test_reduction_levels_and_commands():
    built = levels()
    for name, doc in built.items():
        if name == "commands":
            assert "reduced" not in doc
            item = doc["owner_all"][0]
            assert "commands" not in item
            assert item["commands_at"] == "local_board"
            assert item["commands_count"] == 3
            continue
        if not name.startswith("level-"):
            assert "recorder_failed" not in doc
            assert len(encoded(doc)) <= PUBLISH_TARGET_BYTES
            continue
        level = int(name.split("-")[1])
        assert doc.get("reduced", 0) == level
        assert len(encoded(doc)) <= PUBLISH_TARGET_BYTES
        if level >= 5:
            for work in doc["works"]:
                assert set(work) <= SUMMARY_KEYS
    assert len(built["level-6"]["owner_all"]) + built["level-6"]["owner_all_cut"] == 32


def test_limits_match_the_platform_source():
    if not PLATFORM.is_dir():
        raise AssertionError("没有跑")
    schema = (PLATFORM / "api/internal/agentprogress/schema.go").read_text(encoding="utf-8")
    document = (PLATFORM / "api/internal/agentprogress/document.go").read_text(encoding="utf-8")

    def grab(text, pattern):
        found = re.search(pattern, text)
        assert found, pattern
        return int(found.group(1))

    assert grab(schema, r"maxWorks\s*=\s*(\d+)") == PLATFORM_MAX_WORKS == 30
    assert grab(schema, r"maxSteps\s*=\s*(\d+)") == PLATFORM_MAX_STEPS == 20
    assert grab(schema, r"maxOwners\s*=\s*(\d+)") == PLATFORM_MAX_OWNER_NOW == 10
    assert grab(schema, r"maxActions\s*=\s*(\d+)") == PLATFORM_MAX_ACTIONS == 10
    assert grab(schema, r"maxFeed\s*=\s*(\d+)") == PLATFORM_MAX_FEED == 50
    assert grab(schema, r"maxRecent\s*=\s*(\d+)") == PLATFORM_MAX_RECENT == 30
    assert grab(schema, r"maxNeedsYou\s*=\s*(\d+)") == PLATFORM_MAX_NEEDS_YOU == 30
    assert grab(document, r"MaxDocumentBytes int64 = (\d+) << 10") == 256
    assert PLATFORM_MAX_PUT_BYTES == 256 << 10
    assert "StaleAfter = 5 * time.Minute" in document
    assert PLATFORM_STALE_S == 300
    assert PLATFORM_HOST_RE in document
    assert PUBLISH_MAX_FEED < PLATFORM_MAX_FEED
    assert PUBLISH_MAX_OWNER_ALL == 30
    assert PUBLISH_TARGET_BYTES == 204800


def test_fixtures_match_and_the_platform_accepts_them():
    if not PLATFORM.is_dir():
        raise AssertionError("没有跑")
    built = levels()
    for name, doc in built.items():
        path = FIXTURES / f"{name}.json"
        assert path.is_file(), name
        assert path.read_bytes() == encoded(doc)
    env = os.environ.copy()
    env["RECORDER_FIXTURES"] = str(FIXTURES)
    env["GOMAXPROCS"] = "2"
    proc = subprocess.run(
        ["go", "test", "-count=1", "-timeout=120s", "-run", "TestRecorderFixturesPassHandlePut", "./internal/agentprogress/"],
        cwd=PLATFORM / "api",
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_full_document_stays_inside_every_array_cap():
    works = []
    for index in range(31):
        steps = []
        for nth in range(21):
            step = _step("unknown", note="测" * 20)
            step["reason"] = "no_observation"
            step["step_id"] = f"{(index * 21 + nth) % 0xFFFFFFFF:08x}"
            steps.append(step)
        works.append(_work(f"w{index}", steps, closed=index >= 20, last=index))
    owners = []
    for index in range(40):
        item = _owner(f"o{index}", text="测")
        item["wait_id"] = f"{index:08x}"
        owners.append(item)
    feed = [{"at": index, "work": "w0", "step": "", "who": "C", "state": "note", "text": "测" * 80} for index in range(40)]
    published = _through_door(_shell(works, feed=feed, owner=owners))
    raw = encoded(published)
    assert len(raw) <= PUBLISH_TARGET_BYTES
    assert len(published["works"]) <= 30
    assert len(published["owner_all"]) <= 30
    assert len(published["feed"]) <= 25
    for work in published["works"]:
        if "steps" in work:
            assert len(work["steps"]) <= 20
    assert b"null" not in raw
    kept = len(published["owner_all"])
    assert kept + published.get("owner_all_cut", 0) == 40
    if published.get("reduced", 0) >= 5:
        for work in published["works"]:
            assert set(work) <= SUMMARY_KEYS


def test_reduction_metadata_is_inside_the_measured_bytes():
    works = []
    for index in range(30):
        steps = []
        for nth in range(20):
            step = _step("running", note="m" * 200, command="c" * 200)
            step["step_id"] = f"{index:04x}{nth:04x}"
            step["name"] = "n" * 80
            step["who"] = "w" * 80
            steps.append(step)
        work = _work(f"w{index:02d}", steps)
        work["title"] = "t" * 80
        if index == 0:
            work["defects"] = [{"seq": seq, "reason": "unknown_field"} for seq in range(3364)]
        works.append(work)
    published = _through_door(_shell(works))
    assert len(encoded(published)) <= PUBLISH_TARGET_BYTES


def test_a_host_with_a_trailing_newline_is_omitted():
    folded = fold_total([], [], 1)
    published = json.loads(publish_total(folded, "board\n"))
    assert "host" not in published
    assert "host" in published["incomplete"]
    assert json.loads(publish_total(folded, "board"))["host"] == "board"
    assert (FIXTURES / "host-newline.json").read_bytes() == encoded(published)


def test_closed_works_are_kept_by_close_time_not_last_event():
    def closed(work_id, closed_at, note_at=None):
        log = LogBuilder()
        log.add("work_opened", "coordinator", at=1, work_id=work_id, title=work_id)
        log.add("work_closed", "coordinator", at=closed_at, claim="stopped")
        if note_at is not None:
            log.add("note", "coordinator", at=note_at, text="later")
        return {"work_id": work_id, "events": log.events}

    folded = fold_total(
        [(item["work_id"], _chain(item["events"])) for item in (
            closed("w-early", 10, note_at=100),
            closed("w-late", 50),
        )],
        [],
        100,
    )
    published = json.loads(publish_total(folded, "board"))
    assert [work["work_id"] for work in published["works"]] == ["w-late", "w-early"]
    assert "_closed_at" not in encoded(published).decode("utf-8")


if __name__ == "__main__":
    FIXTURES.mkdir(exist_ok=True)
    for name, doc in levels().items():
        (FIXTURES / f"{name}.json").write_bytes(encoded(doc))
        print(name, doc.get("reduced", 0), len(encoded(doc)))
