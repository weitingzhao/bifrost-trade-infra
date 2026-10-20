"""t26_probe.compare: the page against the rows, a difference only where both page reads agree.

    python3 -m pytest -q scripts/agentrt/test_t26_probe.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import t26_probe as probe  # noqa: E402

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


def page(tasks: dict[str, str], live: list[dict]) -> dict:
    """A progress answer of mission M-7, in the shape GET /progress gives."""
    return {"work": {"missions": [{"mission_id": "M-7", "tasks": [{"task_id": k, "state": v} for k, v in tasks.items()]},
                                  {"mission_id": "M-8", "tasks": [{"task_id": "t_other", "state": "ready"}]}]},
            "live": [{"mission_id": "M-7", **a} for a in live]}


def host(polled_ago: float) -> list[dict]:
    return [{"host_id": "agent-06", "last_poll_at": (NOW - timedelta(seconds=polled_ago)).isoformat()}]


def test_consistent() -> None:
    p = page({"t1": "running", "t2": "ready"}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "working"}])
    rows = [{"task_id": "t1", "state": "running"}, {"task_id": "t2", "state": "ready"}]
    assert probe.compare(p, p, rows, [{"attempt_id": "a1", "state": "running"}, {"attempt_id": "a0", "state": "ended"}],
                         host(10), "M-7", NOW) == []


def test_a_task_state_that_differs_in_both_reads_counts() -> None:
    p = page({"t1": "running"}, [])
    assert probe.compare(p, p, [{"task_id": "t1", "state": "submitted"}], [], host(10), "M-7", NOW) == [
        {"check": "task_state", "task": "t1", "page": "running", "row": "submitted"}]


def test_a_task_that_moved_between_the_reads_does_not() -> None:
    before, after = page({"t1": "running"}, []), page({"t1": "submitted"}, [])
    assert probe.compare(before, after, [{"task_id": "t1", "state": "submitted"}], [], host(10), "M-7", NOW) == []


def test_live_attempts_both_ways() -> None:
    p = page({}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "working"}])
    rows = [{"attempt_id": "a1", "state": "ended"}, {"attempt_id": "a2", "state": "running"}]
    assert probe.compare(p, p, [], rows, host(10), "M-7", NOW) == [
        {"check": "live", "attempt": "a1", "page": "live", "row": "ended"},
        {"check": "live", "attempt": "a2", "page": "not live", "row": "running"}]


def test_another_missions_attempts_are_not_its() -> None:
    p = page({}, [])
    p["live"].append({"mission_id": "M-8", "attempt_id": "a9", "host_id": "agent-06", "status": "working"})
    assert probe.compare(p, p, [], [], host(10), "M-7", NOW) == []


def test_a_lost_host_shows_host_lost_and_only_then() -> None:
    working = page({}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "working"}])
    lost = page({}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "host_lost"}])
    rows = [{"attempt_id": "a1", "state": "running"}]
    assert [d["check"] for d in probe.compare(working, working, [], rows, host(300), "M-7", NOW)] == ["host_lost"]
    assert probe.compare(lost, lost, [], rows, host(300), "M-7", NOW) == []
    assert [d["check"] for d in probe.compare(lost, lost, [], rows, host(30), "M-7", NOW)] == ["host_lost"]
    # within the slack either way is no difference
    assert probe.compare(working, working, [], rows, host(200), "M-7", NOW) == []
    assert probe.compare(lost, lost, [], rows, host(160), "M-7", NOW) == []


def test_a_status_that_changed_between_the_reads_does_not_count() -> None:
    before = page({}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "working"}])
    after = page({}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "host_lost"}])
    assert probe.compare(before, after, [], [{"attempt_id": "a1", "state": "running"}], host(300), "M-7", NOW) == []


def test_times_with_nanoseconds_parse() -> None:
    assert probe.parse_time("2026-10-19T02:14:41.057074107Z") == datetime(2026, 10, 19, 2, 14, 41, 57074, tzinfo=timezone.utc)


def m(n: int, action: str | None) -> dict:
    return {"mission_id": f"M-{n}", "scope_json": {} if action is None else {"max_action": action}}


def test_the_goal_mission_is_the_first_that_may_act() -> None:
    # a brief and a chief answer come first; the goal is M-11; a later goal is not it
    assert probe.goal_mission([m(12, "branch"), m(9, "none"), m(11, "branch"), m(10, "none")]) == "M-11"


def test_no_goal_mission_yet() -> None:
    assert probe.goal_mission([m(9, "none"), m(10, None)]) is None
    assert probe.goal_mission([]) is None


def test_host_lost_seen_lists_hosts_and_ages_in_attempt_order() -> None:
    p = page({}, [{"attempt_id": "a2", "host_id": "agent-06", "status": "host_lost"},
                  {"attempt_id": "a1", "host_id": "agent-06", "status": "host_lost"}])
    assert probe.host_lost_seen(p, p, host(300), "M-7", NOW) == [
        {"attempt": "a1", "host": "agent-06", "poll_age_s": 300.0},
        {"attempt": "a2", "host": "agent-06", "poll_age_s": 300.0}]


def test_host_lost_seen_requires_host_lost_in_both_reads() -> None:
    lost = page({}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "host_lost"}])
    working = page({}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "working"}])
    absent = page({}, [])
    for other in (working, absent):
        assert probe.host_lost_seen(lost, other, host(300), "M-7", NOW) == []
        assert probe.host_lost_seen(other, lost, host(300), "M-7", NOW) == []


def test_host_lost_seen_excludes_another_missions_attempts() -> None:
    p = page({}, [{"mission_id": "M-8", "attempt_id": "a9", "host_id": "agent-06", "status": "host_lost"}])
    assert probe.host_lost_seen(p, p, host(300), "M-7", NOW) == []


def test_host_lost_seen_has_no_age_for_unknown_or_never_polled_hosts() -> None:
    p = page({}, [{"attempt_id": "a1", "host_id": "unknown", "status": "host_lost"},
                  {"attempt_id": "a2", "host_id": "agent-06", "status": "host_lost"}])
    for hosts in ([{"host_id": "agent-06"}], [{"host_id": "agent-06", "last_poll_at": None}]):
        assert probe.host_lost_seen(p, p, hosts, "M-7", NOW) == [
            {"attempt": "a1", "host": "unknown", "poll_age_s": None},
            {"attempt": "a2", "host": "agent-06", "poll_age_s": None}]


def test_tick_records_host_lost_without_changing_the_comparison() -> None:
    p = page({}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "host_lost"}])
    events = [{"event_type": "attempt_leased", "attempt_id": "a1"}]
    attempts = [{"attempt_id": "a1", "state": "running"}]

    class FakePlatform:
        def get(self, path: str, **query: str):
            return {"progress": p, "tasks": {"tasks": []}, "events": events,
                    "attempts/a1": attempts[0], "hosts": {"hosts": hosts}}[path]

    # A correctly lost host and a recently polled host are both recorded; only the latter differs.
    for polled_ago in (300, 30):
        hosts = [{"host_id": "agent-06",
                  "last_poll_at": (datetime.now(timezone.utc) - timedelta(seconds=polled_ago)).isoformat()}]
        line = probe.tick(FakePlatform(), "M-7")
        now = probe.parse_time(line["at"])
        differences = probe.compare(p, p, [], attempts, hosts, "M-7", now)
        assert line["differences"] == differences
        assert line["ok"] == (not differences)
        assert line["ok"] == (polled_ago == 300)
        assert line["host_lost"] == [
            {"attempt": "a1", "host": "agent-06",
             "poll_age_s": (now - probe.parse_time(hosts[0]["last_poll_at"])).total_seconds()}]


def test_tick_reads_every_page_of_the_missions_events() -> None:
    """Review 423 B2: an attempt leased past the first page of events is still read."""
    p = page({}, [{"attempt_id": "a1", "host_id": "agent-06", "status": "working"}])
    events = [{"seq": n, "event_type": "route_decided"} for n in range(1, 501)]
    events.append({"seq": 501, "event_type": "attempt_leased", "attempt_id": "a1"})
    hosts = [{"host_id": "agent-06", "last_poll_at": datetime.now(timezone.utc).isoformat()}]
    reads = []

    class FakePlatform:
        def get(self, path: str, **query: str):
            if path == "events":
                after = int(query.get("after_seq", "0"))
                reads.append(after)
                return [e for e in events if e["seq"] > after][:probe.EVENTS_PAGE]
            return {"progress": p, "tasks": {"tasks": []}, "attempts/a1": {"attempt_id": "a1", "state": "running"},
                    "hosts": {"hosts": hosts}}[path]

    line = probe.tick(FakePlatform(), "M-7")
    assert reads == [0, 500]
    assert line["attempts"] == 1
    assert line["ok"], line["differences"]
