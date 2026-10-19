#!/usr/bin/env python3
"""T26 criterion 5 (design v5 §5.4; W-31 2.4 slice 6): every few minutes, compare what the
progress page says of one mission with the rows it is computed from, and count every difference.

    python3 scripts/agentrt/t26_probe.py --env prod --mission M-17 --hours 9 --out ~/agent-work/t26/probe.jsonl

Each tick reads GET /api/v1/agentrt/progress, then the rows (GET /tasks?mission=, GET /attempts/{id} for
every attempt the mission's events lease, GET /hosts), then the progress page again. A difference counts
only where both progress reads agree with each other and differ from the rows read between them (a task
that moved in between is not a difference). Three checks:

  1. each task of the mission: its state on the page is the task row's state;
  2. the page's live attempts of the mission are exactly the attempt rows leased, running or stale;
  3. a live attempt whose host last polled more than HostLostAfter (3 min) + slack ago shows host_lost,
     and one whose host polled within HostLostAfter - slack does not.

One JSON line a tick: {"at", "ok", "differences": [...]}; at the end a summary line. It writes nothing to
the platform and prints no credential (the operator token comes from bifrost-trade-infra/.env).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASES = {"prod": "http://192.168.10.100:30876", "stg": "http://192.168.10.73:30878"}
TOKEN_KEYS = {"prod": "PLATFORM_PROD_OPERATOR_TOKEN", "stg": "PLATFORM_STG_OPERATOR_TOKEN"}
LIVE = {"leased", "running", "stale"}
HOST_LOST_AFTER_S = 180  # store.HostLostAfter
SLACK_S = 45


def parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    s = re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00"))
    return datetime.fromisoformat(s)


def mission_view(progress: dict, mission: str) -> tuple[dict[str, str], dict[str, dict]]:
    """The page's task states and live attempts of the mission."""
    tasks: dict[str, str] = {}
    for m in progress.get("work", {}).get("missions", []) or []:
        if m.get("mission_id") == mission:
            for t in m.get("tasks", []) or []:
                tasks[t["task_id"]] = t.get("state", "")
    live = {a["attempt_id"]: a for a in progress.get("live", []) or [] if a.get("mission_id") == mission}
    return tasks, live


def compare(before: dict, after: dict, task_rows: list[dict], attempt_rows: list[dict], hosts: list[dict],
            mission: str, now: datetime) -> list[dict]:
    """The differences between the page (read before and after) and the rows read between."""
    out: list[dict] = []
    tb, lb = mission_view(before, mission)
    ta, la = mission_view(after, mission)
    for row in task_rows:
        tid = row["task_id"]
        if tid in tb and tid in ta and tb[tid] == ta[tid] and tb[tid] != row.get("state"):
            out.append({"check": "task_state", "task": tid, "page": tb[tid], "row": row.get("state")})
    rows_live = {a["attempt_id"]: a for a in attempt_rows if a.get("state") in LIVE}
    rows_by_id = {a["attempt_id"]: a for a in attempt_rows}
    for aid in sorted(set(lb) | set(la) | set(rows_live)):
        on_page = aid in lb and aid in la
        off_page = aid not in lb and aid not in la
        if on_page and aid not in rows_live:
            out.append({"check": "live", "attempt": aid, "page": "live", "row": rows_by_id.get(aid, {}).get("state", "absent")})
        if off_page and aid in rows_live:
            out.append({"check": "live", "attempt": aid, "page": "not live", "row": rows_live[aid]["state"]})
    polled = {h["host_id"]: parse_time(h.get("last_poll_at")) for h in hosts}
    for aid in sorted(set(lb) & set(la)):
        a_before, a_after = lb[aid], la[aid]
        if a_before.get("status") != a_after.get("status"):
            continue
        last = polled.get(a_after.get("host_id", ""))
        age = None if last is None else (now - last).total_seconds()
        status = a_after.get("status")
        if (age is None or age > HOST_LOST_AFTER_S + SLACK_S) and status != "host_lost":
            out.append({"check": "host_lost", "attempt": aid, "host": a_after.get("host_id"), "poll_age_s": age, "page": status})
        if age is not None and age < HOST_LOST_AFTER_S - SLACK_S and status == "host_lost":
            out.append({"check": "host_lost", "attempt": aid, "host": a_after.get("host_id"), "poll_age_s": age, "page": status})
    return out


def token(env: str) -> str:
    dotenv = Path(__file__).resolve().parents[2] / ".env"
    m = re.search(r"^" + TOKEN_KEYS[env] + r"=(.*)$", dotenv.read_text(), re.M)
    if not m or not m.group(1).strip().strip('"'):
        sys.exit(f"t26_probe: no {TOKEN_KEYS[env]} in {dotenv}")
    return m.group(1).strip().strip('"')


class Platform:
    def __init__(self, env: str):
        self.base, self.token = BASES[env], token(env)

    def get(self, path: str, **query: str):
        url = self.base + "/api/v1/agentrt/" + path + ("?" + urllib.parse.urlencode(query) if query else "")
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.token})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)


def tick(p: Platform, mission: str) -> dict:
    now = datetime.now(timezone.utc)
    before = p.get("progress")
    tasks = p.get("tasks", mission=mission)
    events = p.get("events", stream="mission:" + mission)
    attempts = [p.get("attempts/" + urllib.parse.quote(e["attempt_id"]))
                for e in events if e.get("event_type") == "attempt_leased" and e.get("attempt_id")]
    hosts = p.get("hosts").get("hosts", [])
    after = p.get("progress")
    diffs = compare(before, after, tasks.get("tasks", []), attempts, hosts, mission, now)
    return {"at": now.isoformat(), "ok": not diffs, "differences": diffs, "tasks": len(tasks.get("tasks", [])),
            "attempts": len(attempts), "truncated": bool(tasks.get("truncated"))}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=sorted(BASES), required=True)
    ap.add_argument("--mission", required=True)
    ap.add_argument("--every", type=int, default=300, help="seconds between ticks")
    ap.add_argument("--hours", type=float, default=9.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if not re.fullmatch(r"M-[0-9]+", a.mission):
        sys.exit("t26_probe: --mission is M-<n>")
    p, out = Platform(a.env), Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    end, ticks, bad, failed = time.time() + a.hours * 3600, 0, 0, 0
    while time.time() < end:
        try:
            line = tick(p, a.mission)
            ticks += 1
            bad += 0 if line["ok"] else 1
        except Exception as exc:  # a tick that cannot read is recorded, not a difference
            failed += 1
            line = {"at": datetime.now(timezone.utc).isoformat(), "error": f"{type(exc).__name__}: {exc}"[:300]}
        with out.open("a") as f:
            f.write(json.dumps(line) + "\n")
        time.sleep(a.every)
    with out.open("a") as f:
        f.write(json.dumps({"summary": True, "ticks": ticks, "ticks_with_differences": bad, "ticks_unread": failed}) + "\n")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
