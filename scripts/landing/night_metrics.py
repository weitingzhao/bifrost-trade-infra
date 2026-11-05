#!/usr/bin/env python3
"""R5:5.7-6 S0b compute: one night's metrics from a night_fetch.py snapshot.

Reads only the snapshot (no cluster, database or network), so the tests run on
fixtures. Every number comes with the run names, landing ops, card numbers or
task ids behind it. A source the snapshot lacks gives Unknown, never 0.

Frozen definitions (a change is a new VERSION and a re-run of the baseline):
- Window: night = 23:00-09:00 US Central, handover = 09:00-12:00, keyed by
  the date the night starts. A thing counts in the segment holding its start
  time; durations are clipped to the segment.
- Run kind (design 2.3): a name starting with landing- is a landing; else a
  revision on main's first-parent chain is a main push; else a branch.
- Outcome: Succeeded is green, failed is red, cancelled has no verdict and is
  left out, still running is unknown.
- Main state, proxy clock: at time t, the outcome of the newest revision (in
  first-parent order) with a main run created by t, from its latest such run,
  as if the verdict were known when the run was created.
- Main state, terminal clock: the same over runs completed by t; a verdict
  takes effect at completionTime.
- Owner push: the first main run of a revision whose base..revision range on
  the first-parent chain has no commit with a Landed-By trailer.
- Delivery: a hand-in task created by seat:coordinator in the night segment.
  On main = its first landed event. Wait = landed - created when it landed
  before the handover end, otherwise its age at the handover end (open).
  Percentiles are nearest-rank: defined at n = 1, never a value between two
  deliveries.
"""
import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

VERSION = "night-metrics/1"
SNAPSHOT = "night-metrics-snapshot/1"
NO_VERDICT = ("Cancelled", "CancelledRunFinally", "StoppedRunFinally", "PipelineRunCancelled")
CLOSING_WHY = ("declined", "denied")
CLOSED_STATES = ("cancelled", "rejected")
MIN_DELIVERIES = 3
ENDS = {"parked": ("unparked", "landed", "failed", "discarded", "main_intent"),
        "awaiting_grant": ("landing_grant", "landed", "failed", "discarded", "main_intent")}
IDLE = {"unknown": "no system record of when the coordinator thread had work but did nothing",
        "criterion": "manual: a gap over 30 min between two coordinator tool calls while at least "
                     "one step needed nobody else (a finished change not handed in, a review that "
                     "could start, a design that could advance)"}


def central_offset(day):
    """UTC offset in hours of US Central on day, after 02:00 local (all window edges are)."""
    march, november = date(day.year, 3, 8), date(day.year, 11, 1)
    dst_from = march + timedelta(days=(6 - march.weekday()) % 7)
    dst_to = november + timedelta(days=(6 - november.weekday()) % 7)
    return -5 if dst_from <= day < dst_to else -6


def local_utc(day, hour):
    return datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc) - timedelta(hours=central_offset(day))


def night_windows(night):
    start = date.fromisoformat(night)
    after = start + timedelta(days=1)
    return {"night": (local_utc(start, 23), local_utc(after, 9)),
            "handover": (local_utc(after, 9), local_utc(after, 12))}


def moment_of(value):
    if not value:
        return None
    text = re.sub(r"(\.\d{6})\d+", r"\1", str(value).replace("Z", "+00:00"))
    moment = datetime.fromisoformat(text)
    return moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def iso_z(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None


def within(moment, seg):
    return moment is not None and seg[0] <= moment < seg[1]


def run_outcome(run):
    if run["status"] == "True":
        return "green"
    if run["status"] == "False":
        return "none" if run["reason"] in NO_VERDICT else "red"
    return "running"


def classify_runs(runs, commits):
    pos = {c["sha"]: i for i, c in enumerate(commits)}
    rows = []
    for run in runs:
        rev = run["params"].get("revision") or ""
        kind = "landing" if run["name"].startswith("landing-") else ("main" if rev in pos else "branch")
        rows.append(dict(run, kind=kind, rev=rev, outcome=run_outcome(run), t_created=moment_of(run["created"]),
                         t_completed=moment_of(run["completed"])))
    return rows, pos


def state_at(runs, pos, moment, clock):
    """(state, run name) of main at moment under the proxy or the terminal clock."""
    best, key = None, None
    for run in runs:
        if run["kind"] != "main" or run["outcome"] == "none":
            continue
        when = run["t_created"] if clock == "proxy" else run["t_completed"]
        if when is None or when > moment:
            continue
        rank = (-pos[run["rev"]], when)
        if key is None or rank > key:
            best, key = run, rank
    if best is None:
        return "unknown", None
    return ("unknown" if best["outcome"] == "running" else best["outcome"]), best["name"]


def main_timeline(runs, pos, seg, clock):
    field = "t_created" if clock == "proxy" else "t_completed"
    points = sorted({seg[0]} | {r[field] for r in runs if r["kind"] == "main" and r[field]
                                and seg[0] < r[field] < seg[1]})
    spans = []
    for i, point in enumerate(points):
        upto = points[i + 1] if i + 1 < len(points) else seg[1]
        state, name = state_at(runs, pos, point, clock)
        if spans and spans[-1]["state"] == state:
            spans[-1]["to"] = upto
        else:
            spans.append({"from": point, "to": upto, "state": state, "runs": []})
        if name and name not in spans[-1]["runs"]:
            spans[-1]["runs"].append(name)
    total = {s: sum((x["to"] - x["from"]).total_seconds() for x in spans if x["state"] == s)
             for s in ("red", "unknown")}
    return {"red_s": total["red"], "unknown_s": total["unknown"],
            "spans": [dict(x, **{"from": iso_z(x["from"]), "to": iso_z(x["to"])}) for x in spans]}


def seg_main_runs(runs, seg):
    picked = [r for r in runs if r["kind"] == "main" and within(r["t_created"], seg)]
    return {"count": len(picked), "red": sum(r["outcome"] == "red" for r in picked),
            "running": sum(r["outcome"] == "running" for r in picked),
            "runs": [{"run": r["name"], "rev": r["rev"][:10], "outcome": r["outcome"], "created": r["created"]}
                     for r in picked]}


def push_range(run, pos, commits, prior):
    top = pos[run["rev"]]
    for base, how in ((run["params"].get("base") or "", "base"), (prior or "", "previous main run")):
        if base in pos and pos[base] > top:
            return commits[top:pos[base]], base[:10], how
    return commits[top:top + 1], None, "unknown"


def seg_owner_pushes(runs, pos, commits, seg, night):
    seen, prior, rows = set(), None, []
    for run in sorted((r for r in runs if r["kind"] == "main"), key=lambda r: r["t_created"]):
        if run["rev"] in seen:
            continue
        seen.add(run["rev"])
        if within(run["t_created"], seg):
            span, base, how = push_range(run, pos, commits, prior)
            landed = [c for c in span if c["landed_by"]]
            state, base_run = state_at([r for r in runs if r["name"] != run["name"]], pos, run["t_created"], "terminal")
            waiting = [{"sha": c["sha"][:10], "committed": c["committed"],
                        "wait_s": (run["t_created"] - moment_of(c["committed"])).total_seconds()}
                       for c in span if not c["landed_by"] and within(moment_of(c["committed"]), night)]
            rows.append({"run": run["name"], "rev": run["rev"][:10], "base": base, "range_from": how,
                         "commits": len(span), "by": "landing" if landed else "owner",
                         "mixed": 0 < len(landed) < len(span), "outcome": run["outcome"],
                         "base_state": state, "base_run": base_run, "night_commits": waiting})
        if prior is None or pos[run["rev"]] < pos.get(prior, len(pos)):
            prior = run["rev"]
    owner = [r for r in rows if r["by"] == "owner"]
    rule_a = [r["run"] for r in owner if r["base_state"] == "red" and r["outcome"] == "green"]
    rule_b = [r["run"] for r in owner if r["base_state"] == "red"]
    return {"count": len(owner), "pushes": rows, "repair_rule_a": rule_a, "repair_rule_b": rule_b,
            "night_commits_waiting": sum(len(r["night_commits"]) for r in owner)}


def fail_head(run):
    lines = (run.get("fail") or {}).get("lines") or []
    return lines[0] if lines else None


def attribute(run, runs):
    mine, base = fail_head(run), run["params"].get("base") or ""
    found = {"first_line": mine, "fail_step": (run.get("fail") or {}).get("step"),
             "log_source": (run.get("fail") or {}).get("source", "not fetched")}
    done = [r for r in runs if r["kind"] == "main" and r["rev"] == base and r["outcome"] in ("red", "green")
            and r["t_completed"] and r["t_completed"] <= run["t_created"]]
    if not done:
        return found | {"vs_base": "base_unknown"}
    last = max(done, key=lambda r: r["t_completed"])
    found |= {"base_run": last["name"], "base_outcome": last["outcome"], "base_first_line": fail_head(last)}
    if last["outcome"] == "green":
        return found | {"vs_base": "base_green"}
    if mine is None or found["base_first_line"] is None:
        return found | {"vs_base": "base_red_line_unknown"}
    return found | {"vs_base": "same_first_line_as_base" if mine == found["base_first_line"] else "differs_from_base"}


def op_events(events):
    """op -> [(at, kind, why, repo)] in event order, for every body part that names an op."""
    out = {}
    for event in events:
        for key, part in event["body"].items():
            if isinstance(part, dict) and part.get("op"):
                kind = part.get("kind") if key == "landing" else key
                out.setdefault(part["op"], []).append((moment_of(event["at"]), kind, part.get("why"),
                                                       event["stream"].split(":", 1)[1]))
    return out


def seg_landings(runs, events, seg, repo="bifrost-trade-infra"):
    run_op = {}
    for event in events:
        part = event["body"].get("landing") or {}
        if part.get("kind") == "ci_seen" and part.get("run"):
            run_op[part["run"]] = part.get("op")
    rows = []
    for run in (r for r in runs if r["kind"] == "landing" and within(r["t_created"], seg)):
        row = {"run": run["name"], "op": run_op.get(run["name"]), "rev": run["rev"][:10],
               "base": (run["params"].get("base") or "")[:10], "outcome": run["outcome"]}
        rows.append(row | attribute(run, runs) if run["outcome"] == "red" else row)
    ended = [{"op": op, "kind": kind, "why": why, "at": iso_z(at)} for op, seq in op_events(events).items()
             for at, kind, why, where in seq if where == repo and kind in ("landed", "failed", "discarded")
             and within(at, seg)]
    return {"count": len(rows), "failed": sum(r["outcome"] == "red" for r in rows), "runs": rows,
            "ops": sorted({r["op"] for r in rows if r["op"]}), "ops_ended": ended}


def seg_cards(events, questions, seg):
    prepared = {e["body"]["landing_card_prepared"].get("prep"): e["body"]["landing_card_prepared"]
                for e in events if "landing_card_prepared" in e["body"]}
    by_id = {q["id"]: q for q in questions or []}
    rows = []
    for event in events:
        card = event["body"].get("landing_card")
        if not card or not within(moment_of(event["at"]), seg):
            continue
        prep, asked = prepared.get(card.get("prep")) or {}, by_id.get(card.get("question_id")) or {}
        rows.append({"question": card.get("question_id"), "number": asked.get("number"),
                     "repo": event["stream"].split(":", 1)[1], "op": prep.get("op"), "kind": prep.get("kind"),
                     "at": iso_z(moment_of(event["at"])), "answered_at": asked.get("answered_at"),
                     "answer": asked.get("answer_option")})
    return {"count": len(rows), "cards": rows, "numbers_known": questions is not None}


def seg_other_cards(questions, approvals, seg):
    asked = None if questions is None else [
        {"number": q["number"], "id": q["id"], "task": q.get("task_id"), "title": (q.get("title") or "")[:70],
         "created_at": q["created_at"], "answered_at": q.get("answered_at")}
        for q in questions if within(moment_of(q["created_at"]), seg)]
    requested = None if approvals is None else [
        {"number": a["number"], "action": a["action"], "tier": a.get("tier"), "created_at": a["created_at"],
         "decided_at": a.get("decided_at")} for a in approvals if within(moment_of(a["created_at"]), seg)]
    return {"questions": asked if asked is not None else {"unknown": "question list not given"},
            "approvals": requested if requested is not None else {"unknown": "approval list not given"}}


def episodes(by_op, opener, horizon):
    rows = []
    for op, seq in by_op.items():
        start = None
        for at, kind, why, repo in seq:
            if start is None and kind == opener:
                start, cause = at, why
            elif start is not None and kind in ENDS[opener]:
                rows.append({"op": op, "repo": repo, "why": cause, "from": start, "to": at})
                start = None
        if start is not None:
            rows.append({"op": op, "repo": repo, "why": cause, "from": start, "to": None, "horizon": horizon})
    return rows


def clip(rows, seg):
    picked = []
    for row in rows:
        end = row["to"] or row["horizon"]
        lo, hi = max(row["from"], seg[0]), min(end, seg[1])
        if hi > lo:
            picked.append({"op": row["op"], "repo": row["repo"], "why": row["why"], "from": iso_z(row["from"]),
                           "to": iso_z(row["to"]), "clipped_s": (hi - lo).total_seconds(),
                           "open_at_end": row["to"] is None or row["to"] > seg[1]})
    return {"count": len(picked), "seconds": sum(p["clipped_s"] for p in picked), "episodes": picked}


def nearest_rank(values, share):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)] if ordered else None


def task_status(task, by_op, end):
    mine = [x for op, seq in by_op.items() if op.startswith(f"land:{task['task_id']}:") for x in seq]
    landed = min((at for at, kind, _, _ in mine if kind == "landed"), default=None)
    closed = min((at for at, kind, why, _ in mine if kind == "failed" and why in CLOSING_WHY), default=None)
    if task["state"] in CLOSED_STATES and moment_of(task["updated_at"]) < end:
        closed = min(filter(None, (closed, moment_of(task["updated_at"]))))
    if landed and landed < end:
        return "landed", landed, closed
    return ("closed_unlanded" if closed and closed < end else "open"), landed, closed


def deliveries(snap, by_op, wins, horizon):
    tasks, checks = snap["db"]["tasks"], snap["db"]["verifications"]
    night, end = wins["night"], wins["handover"][1]
    grants, parks = episodes(by_op, "awaiting_grant", horizon), episodes(by_op, "parked", horizon)
    items, backlog = [], []
    for task in tasks:
        created = moment_of(task["created_at"])
        if created >= end:
            continue
        status, landed, closed = task_status(task, by_op, end)
        if status == "open":
            backlog.append({"task": task["task_id"], "repo": task["repo"], "created_at": task["created_at"],
                            "night_delivery": within(created, night), "age_s": (end - created).total_seconds()})
        if not within(created, night):
            continue
        own = (created, end)
        mine = [v for v in checks if v["task_id"] == task["task_id"] and moment_of(v["created_at"]) < end]
        first = {m: next((v for v in mine if v["method"] == m), None) for m in ("review", "deterministic")}
        items.append({"task": task["task_id"], "repo": task["repo"], "title": (task["title"] or "")[:70],
                      "created_at": task["created_at"], "status": status, "landed_at": iso_z(landed),
                      "closed_at": iso_z(closed), "open": status != "landed",
                      "wait_s": ((landed if status == "landed" else end) - created).total_seconds(),
                      "grant_wait_s": clip([g for g in grants if g["op"].startswith(f"land:{task['task_id']}:")],
                                           own)["seconds"],
                      "parked_s": clip([p for p in parks if p["op"].startswith(f"land:{task['task_id']}:")],
                                       own)["seconds"],
                      "first_review": first["review"] and {"id": first["review"]["verification_id"],
                                                           "verdict": first["review"]["verdict"]},
                      "first_check": first["deterministic"] and first["deterministic"]["verdict"]})
    waits = [i["wait_s"] for i in items]
    reviewed = [i for i in items if i["first_review"]]
    return {"n": len(items), "min_sample_ok": len(items) >= MIN_DELIVERIES,
            "landed_by_handover_end": sum(i["status"] == "landed" for i in items),
            "completion": (sum(i["status"] == "landed" for i in items) / len(items)) if items else None,
            "wait_s": {"p50": nearest_rank(waits, 0.5), "p90": nearest_rank(waits, 0.9),
                       "max": max(waits) if waits else None, "open_counted_at_age": sum(i["open"] for i in items)},
            "review_first_pass": {"rate": (sum(i["first_review"]["verdict"] == "pass" for i in reviewed)
                                           / len(reviewed)) if reviewed else None,
                                  "reviewed": len(reviewed), "without_review": len(items) - len(reviewed)},
            "items": items, "backlog_at_end": backlog,
            "backlog_night_deliveries": sum(b["night_delivery"] for b in backlog)}


def compute_all(snap, night):
    wins, horizon, src = night_windows(night), moment_of(snap["fetched_at"]), snap["sources"]
    gone = lambda *keys: {"unknown": "snapshot lacks " + ", ".join(f"{k} ({src.get(k)})" for k in keys)}
    runs = pos = None
    if snap.get("runs") is not None and snap.get("git") is not None:
        runs, pos = classify_runs(snap["runs"], snap["git"]["commits"])
    db = snap.get("db")
    by_op = op_events(db["events"]) if db is not None else None
    earliest = min((r["t_created"] for r in runs or [] if r["t_created"]), default=None)
    out = {"version": VERSION, "night": night, "windows": {k: [iso_z(a), iso_z(b)] for k, (a, b) in wins.items()},
           "coverage": {"fetched_at": snap["fetched_at"], "since": snap["since"], "sources": src,
                        "earliest_run": iso_z(earliest),
                        "runs_cover_night_start": bool(earliest and earliest <= wins["night"][0]),
                        "window_closed": horizon >= wins["handover"][1]},
           "segments": {}, "idle": IDLE}
    for name, seg in wins.items():
        part = {}
        if runs is None:
            part["main_ci"] = part["main_red"] = part["owner_pushes"] = part["landings"] = gone("runs", "git")
        else:
            part["main_ci"] = seg_main_runs(runs, seg)
            part["main_red"] = {c: main_timeline(runs, pos, seg, c) for c in ("proxy", "terminal")}
            part["owner_pushes"] = seg_owner_pushes(runs, pos, snap["git"]["commits"], seg, wins["night"])
            part["landings"] = seg_landings(runs, db["events"], seg) if db else gone("db")
        part["landing_cards"] = seg_cards(db["events"], snap.get("questions"), seg) if db else gone("db")
        part["suspensions"] = {"base_only": {"unknown": "S5 not built: no base_only state exists yet"},
                               "parked": clip(episodes(by_op, "parked", horizon), seg) if db else gone("db"),
                               "grant_waits": clip(episodes(by_op, "awaiting_grant", horizon), seg)
                               if db else gone("db")}
        part["other_cards"] = seg_other_cards(snap.get("questions"), snap.get("approvals"), seg)
        out["segments"][name] = part
    out["deliveries"] = deliveries(snap, by_op, wins, horizon) if db else gone("db")
    return out


def hours(seconds):
    return "Unknown" if seconds is None else f"{seconds / 3600:.2f} h"


def cell(items):
    text = "; ".join(str(i) for i in items) if isinstance(items, list) else str(items)
    return text.replace("|", "\\|").replace("\n", " ") or "-"


def summary_rows(part):
    """(metric, value, identifiers) rows of one segment; an unknown metric shows its reason."""
    def known(key, value, ids):
        got = part[key]
        return (key, "Unknown", got["unknown"]) if "unknown" in got else (key, value(got), ids(got))
    rows = [known("main_ci", lambda g: f"{g['count']} runs, {g['red']} red, {g['running']} running",
                  lambda g: [f"{r['run']} {r['rev']} {r['outcome']}" for r in g["runs"]])]
    for clock in ("proxy", "terminal"):
        rows.append(known("main_red", lambda g, c=clock: f"{c}: {hours(g[c]['red_s'])}"
                          + (f" (+{hours(g[c]['unknown_s'])} unknown)" if g[c]["unknown_s"] else ""),
                          lambda g, c=clock: [f"{s['from']}..{s['to']} {'/'.join(s['runs'])}"
                                              for s in g[c]["spans"] if s["state"] != "green"]))
    rows += [known("landings", lambda g: f"{g['count']} CI, {g['failed']} failed",
                   lambda g: [f"{r['run']} {r['op']} {r['outcome']}"
                              + (f" {r['vs_base']} [{r.get('first_line')}]" if r["outcome"] == "red" else "")
                              for r in g["runs"]] + [f"ended {e['op']} {e['kind']}/{e['why']}" for e in g["ops_ended"]]),
             known("landing_cards", lambda g: str(g["count"]),
                   lambda g: [f"#{c['number']} {c['question']} {c['op']} answered {c['answered_at']}"
                              for c in g["cards"]]),
             known("owner_pushes", lambda g: f"{g['count']} (repair rule A {len(g['repair_rule_a'])}, "
                                             f"rule B {len(g['repair_rule_b'])}; night commits waiting "
                                             f"{g['night_commits_waiting']})",
                   lambda g: [f"{p['run']} {p['rev']} base={p['base']} {p['by']} {p['outcome']} "
                              f"on-{p['base_state']} commits={p['commits']}" for p in g["pushes"]])]
    sus = part["suspensions"]
    rows.append(("suspensions.base_only", "Unknown", sus["base_only"]["unknown"]))
    for key in ("parked", "grant_waits"):
        got = sus[key]
        rows.append((f"suspensions.{key}", "Unknown", got["unknown"]) if "unknown" in got else
                    (f"suspensions.{key}", f"{got['count']} episodes, {hours(got['seconds'])}",
                     [f"{e['op']} {e['why'] or ''} {e['from']}..{e['to']}" for e in got["episodes"]]))
    for key, got in part["other_cards"].items():
        rows.append((f"other_cards.{key}", "Unknown" if isinstance(got, dict) else str(len(got)),
                     got.get("unknown") if isinstance(got, dict) else [f"#{c['number']}" for c in got]))
    return rows


def render_md(res):
    lines = [f"# {res['version']}, night of {res['night']}", "",
             f"Windows (UTC): night {res['windows']['night']}, handover {res['windows']['handover']}.",
             f"Coverage: {json.dumps(res['coverage'], sort_keys=True)}", ""]
    for name, part in res["segments"].items():
        lines += [f"## {name}", "", "| metric | value | identifiers |", "|---|---|---|"]
        lines += [f"| {cell(m)} | {cell(v)} | {cell(i)} |" for m, v, i in summary_rows(part)]
        lines.append("")
    dl = res["deliveries"]
    lines += ["## deliveries (night) and backlog at handover end", ""]
    if "unknown" in dl:
        lines.append(f"Unknown: {dl['unknown']}")
    else:
        w = dl["wait_s"]
        lines += [f"n={dl['n']} (minimum sample {MIN_DELIVERIES}: {'met' if dl['min_sample_ok'] else 'NOT met'}), "
                  f"landed by handover end {dl['landed_by_handover_end']}, completion {dl['completion']}, "
                  f"wait p50 {hours(w['p50'])} p90 {hours(w['p90'])} max {hours(w['max'])} "
                  f"(open counted at age: {w['open_counted_at_age']}), review first pass "
                  f"{dl['review_first_pass']}", "", "| task | repo | created | status | wait | grant wait "
                  "| parked | first review |", "|---|---|---|---|---|---|---|---|"]
        lines += [f"| {i['task']} | {i['repo']} | {i['created_at'][:19]} | {i['status']} | {hours(i['wait_s'])} "
                  f"| {hours(i['grant_wait_s'])} | {hours(i['parked_s'])} | {cell(i['first_review'])} |"
                  for i in dl["items"]]
        lines += ["", f"Backlog at handover end: {len(dl['backlog_at_end'])} open hand-ins "
                      f"({dl['backlog_night_deliveries']} delivered at night): "
                      + cell([f"{b['task']} {b['repo']} age {hours(b['age_s'])}" for b in dl["backlog_at_end"]])]
    lines += ["", f"Idle with work: Unknown ({res['idle']['unknown']}); {res['idle']['criterion']}", ""]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", required=True, help="night_fetch.py output")
    ap.add_argument("--night", required=True, help="date the night starts, YYYY-MM-DD (US Central)")
    ap.add_argument("--json", help="also write the full result here")
    args = ap.parse_args(argv)
    snap = json.loads(Path(args.snapshot).read_text())
    if snap.get("schema") != SNAPSHOT:
        print(f"FAIL snapshot schema {snap.get('schema')!r} is not {SNAPSHOT}", file=sys.stderr)
        return 2
    res = compute_all(snap, args.night)
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(render_md(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
