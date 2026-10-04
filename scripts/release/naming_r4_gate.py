#!/usr/bin/env python3
"""Naming R4 release gate (decision pack 2026-10-03, D4-A): are the old names still in use?

R4 deletes what R1–R3 kept for one version: the replaced routes (/strategies/instances …), the
old query names (strategy_instance_id / strategy_instance_ids), the old body names, Research's
alias MCP tools (trade.strategy.instances / gate_safety) and the journal ref type ``inst``.
The gate is zero hits for >= 4 days after R3's PROD release (2026-10-04 04:31 UTC). This script
measures, read-only:

  Loki (via the apiserver service proxy, no port-forward), per env namespace bifrost-<env>:
    - "replaced route hit: <METHOD> <path> (route <template>) use <successor> … user_agent=…"
    - "deprecated query params: <METHOD> <path> <old>-><new> … user_agent=…"
      (naming names vs the TD-51 vocabulary aliases, reported apart)
    - "deprecated route hit" (TD-40's list; empty since api 0.8.0, reported for completeness)
  Loki, namespace research: any line naming trade.strategy.instances / trade.strategy.gate_safety.
  Golden Source (read-only psql, default_transaction_read_only=on):
    - research.ai_action_log rows whose tool_calls name an old tool (Copilot's own calls)
    - journal.note refs stored with type 'inst' (the frontend fallback R4 deletes needs 0)

Old *body* field names (strategy_instance_id / instance_allocations in execution bodies) are not
logged by any api version: there is nothing to count in Loki. The callers are known from code
(frontend, Research, platform on main send the new names since R2); the report says so.

Usage (from bifrost-trade-infra, KUBECONFIG=~/.kube/bifrost-k3s.yaml):
  python3 scripts/release/naming_r4_gate.py                       # since R3 PROD, all envs, GS checks
  python3 scripts/release/naming_r4_gate.py --quiet-days 4        # verdict window (default 4)
  python3 scripts/release/naming_r4_gate.py --since 2026-10-04T04:31:00Z --json out.json
  python3 scripts/release/naming_r4_gate.py --no-gs               # Loki only

Exit code: 0 = gate open (no naming hit in the last --quiet-days in any env, research clean,
journal 'inst' = 0, quiet window fully inside the measured window); 1 = gate closed; 2 = could
not measure (Loki down, psql failed). Callers whose user agent is an agent's check (curl,
python-*, bifrost-release-check) are listed like any other: the integrator decides.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

R3_PROD_LIVE = "2026-10-04T04:31:00Z"
ENVS = ("dev", "stg", "prod")
LOKI = "/api/v1/namespaces/monitoring/services/loki:3100/proxy/loki/api/v1"
CHUNK_LIMIT = 4000  # lines per Loki call; a full chunk is split in two (Loki is a small single instance)
NAMING_QUERY_NAMES = frozenset({"strategy_instance_id", "strategy_instance_ids"})
OLD_TOOLS = ("trade.strategy.instances", "trade.strategy.gate_safety")

LINE_FILTER = 'replaced route hit|deprecated query params|deprecated route hit'
REPLACED_RE = re.compile(
    r"replaced route hit: (?P<method>\S+) (?P<path>\S+) \(route (?P<template>[^)]*)\) use (?P<successor>.+?) "
    r"client=(?P<client>\S+) forwarded_for=(?P<fwd>\S+) user_agent=(?P<ua>.*)$"
)
QUERY_RE = re.compile(
    r"deprecated query params: (?P<method>\S+) (?P<path>\S+) (?P<pairs>.*?) "
    r"client=(?P<client>\S+) forwarded_for=(?P<fwd>\S+) user_agent=(?P<ua>.*)$"
)
DEPRECATED_RE = re.compile(
    r"deprecated route hit: (?P<method>\S+) (?P<path>\S+) \(route (?P<template>[^)]*)\) "
    r"client=(?P<client>\S+) forwarded_for=(?P<fwd>\S+) user_agent=(?P<ua>.*)$"
)


class MeasureError(RuntimeError):
    pass


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def kubectl_raw(path: str) -> Dict[str, Any]:
    proc = subprocess.run(["kubectl", "get", "--raw", path], capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise MeasureError(f"kubectl get --raw failed: {proc.stderr.strip()[:300]}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise MeasureError(f"Loki answered non-JSON: {proc.stdout[:200]!r}") from e


def loki_lines(logql: str, start: datetime, end: datetime, depth: int = 0) -> List[Tuple[datetime, Dict[str, str], str]]:
    """Every line of ``logql`` in [start, end); splits a window whose answer is full."""
    q = urllib.parse.quote(logql)
    s_ns, e_ns = int(start.timestamp() * 1e9), int(end.timestamp() * 1e9)
    path = f"{LOKI}/query_range?query={q}&start={s_ns}&end={e_ns}&limit={CHUNK_LIMIT}&direction=forward"
    for attempt in range(3):
        try:
            data = kubectl_raw(path)
            break
        except MeasureError as e:
            if attempt == 2 or "no endpoints available" not in str(e):
                raise
            time.sleep(30)  # loki-0 NotReady: wait, do not hammer it
    out: List[Tuple[datetime, Dict[str, str], str]] = []
    for stream in data.get("data", {}).get("result", []):
        labels = stream.get("stream", {})
        for ts, line in stream.get("values", []):
            out.append((datetime.fromtimestamp(int(ts) / 1e9, tz=timezone.utc), labels, line))
    if len(out) >= CHUNK_LIMIT:
        if depth > 12 or (end - start) < timedelta(seconds=2):
            raise MeasureError(f"more than {CHUNK_LIMIT} lines in {iso(start)}..{iso(end)}: narrow the filter")
        mid = start + (end - start) / 2
        return loki_lines(logql, start, mid, depth + 1) + loki_lines(logql, mid, end, depth + 1)
    return out


def windows(start: datetime, end: datetime, hours: int) -> List[Tuple[datetime, datetime]]:
    out, cur = [], start
    while cur < end:
        nxt = min(cur + timedelta(hours=hours), end)
        out.append((cur, nxt))
        cur = nxt
    return out


def classify(line: str) -> Optional[Dict[str, Any]]:
    m = REPLACED_RE.search(line)
    if m:
        return {"kind": "replaced_route", "naming": True, "route": f"{m['method']} {m['template']}",
                "detail": f"use {m['successor']}", "fwd": m["fwd"], "ua": m["ua"].strip(), "client": m["client"]}
    m = QUERY_RE.search(line)
    if m:
        pairs = m["pairs"].split()
        olds = {p.split("->", 1)[0] for p in pairs if "->" in p}
        return {"kind": "query_alias", "naming": bool(olds & NAMING_QUERY_NAMES),
                "route": f"{m['method']} {m['path']}", "detail": " ".join(pairs), "fwd": m["fwd"],
                "ua": m["ua"].strip(), "client": m["client"]}
    m = DEPRECATED_RE.search(line)
    if m:
        return {"kind": "deprecated_route", "naming": False, "route": f"{m['method']} {m['template']}",
                "detail": "", "fwd": m["fwd"], "ua": m["ua"].strip(), "client": m["client"]}
    return None


def measure_env(env: str, start: datetime, end: datetime, chunk_hours: int) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    logql = f'{{namespace="bifrost-{env}"}} |~ "{LINE_FILTER}"'
    for a, b in windows(start, end, chunk_hours):
        for ts, labels, line in loki_lines(logql, a, b):
            c = classify(line)
            if c is None:
                continue
            c.update({"env": env, "ts": ts, "app": labels.get("app", labels.get("container", "?"))})
            hits.append(c)
    return hits


def measure_research(start: datetime, end: datetime, chunk_hours: int) -> List[Dict[str, Any]]:
    hits: List[Dict[str, Any]] = []
    logql = '{namespace="research"} |~ "trade\\\\.strategy\\\\.(instances|gate_safety)"'
    for a, b in windows(start, end, chunk_hours):
        for ts, labels, line in loki_lines(logql, a, b):
            hits.append({"ts": ts, "app": labels.get("app", labels.get("container", "?")), "line": line[:300]})
    return hits


def psql_ro(db: str, sql: str) -> str:
    cmd = ["kubectl", "-n", "data", "exec", "-i", "bifrost-postgres-1", "-c", "postgres", "--",
           "psql", "-U", "postgres", "-d", db, "-X", "-At", "-v", "ON_ERROR_STOP=1",
           "-c", "SET default_transaction_read_only=on;", "-c", sql]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise MeasureError(f"psql {db} failed: {proc.stderr.strip()[:300]}")
    return "\n".join(l for l in proc.stdout.splitlines() if l and l != "SET")


def measure_gs(since: datetime) -> Dict[str, Any]:
    names = " OR ".join(f"tool_calls::text LIKE '%{t}%'" for t in OLD_TOOLS)
    tools = psql_ro(
        "bifrost_golden_source",
        "SELECT count(*) FILTER (WHERE created_at >= '" + iso(since) + "'), count(*), "
        "coalesce(max(created_at)::text, '-') FROM research.ai_action_log WHERE " + names + ";",
    ).split("|")
    inst = psql_ro(
        "bifrost_golden_source",
        "SELECT count(*), count(DISTINCT n.id) FROM journal.note n, jsonb_array_elements(n.refs) r "
        "WHERE r->>'type' = 'inst';",
    ).split("|")
    return {
        "ai_action_log_old_tools_since": int(tools[0]),
        "ai_action_log_old_tools_ever": int(tools[1]),
        "ai_action_log_old_tools_last": tools[2],
        "journal_inst_refs": int(inst[0]),
        "journal_inst_notes": int(inst[1]),
    }


def summarize(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, ...], Dict[str, Any]] = defaultdict(lambda: {"n": 0, "first": None, "last": None})
    for h in hits:
        key = (h["env"], h["kind"], "naming" if h["naming"] else "other", h["route"], h["detail"], h["fwd"], h["ua"])
        g = groups[key]
        g["n"] += 1
        g["first"] = h["ts"] if g["first"] is None or h["ts"] < g["first"] else g["first"]
        g["last"] = h["ts"] if g["last"] is None or h["ts"] > g["last"] else g["last"]
    rows = []
    for (env, kind, scope, route, detail, fwd, ua), g in groups.items():
        rows.append({"env": env, "kind": kind, "scope": scope, "route": route, "detail": detail,
                     "forwarded_for": fwd, "user_agent": ua, "count": g["n"],
                     "first": iso(g["first"]), "last": iso(g["last"])})
    return sorted(rows, key=lambda r: (ENVS.index(r["env"]), r["scope"], r["kind"], r["route"], r["last"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since", default=R3_PROD_LIVE, help="start (UTC ISO), default R3 PROD live")
    ap.add_argument("--until", default=None, help="end (UTC ISO), default now")
    ap.add_argument("--envs", nargs="+", default=list(ENVS), choices=ENVS)
    ap.add_argument("--quiet-days", type=float, default=4.0, help="zero-hit window the gate needs (D4-A: 4)")
    ap.add_argument("--chunk-hours", type=int, default=6)
    ap.add_argument("--no-gs", action="store_true", help="skip the Golden Source read-only checks")
    ap.add_argument("--json", default=None, help="also write the full result here")
    args = ap.parse_args()

    if not os.environ.get("KUBECONFIG"):
        os.environ["KUBECONFIG"] = os.path.expanduser("~/.kube/bifrost-k3s.yaml")
    since = parse_ts(args.since)
    until = parse_ts(args.until) if args.until else datetime.now(timezone.utc)
    quiet_from = until - timedelta(days=args.quiet_days)

    try:
        hits: List[Dict[str, Any]] = []
        for env in args.envs:
            hits.extend(measure_env(env, since, until, args.chunk_hours))
        research = measure_research(since, until, args.chunk_hours)
        gs = None if args.no_gs else measure_gs(since)
    except MeasureError as e:
        print(f"could not measure: {e}", file=sys.stderr)
        return 2

    rows = summarize(hits)
    print(f"Naming R4 gate — window {iso(since)} .. {iso(until)}; quiet window from {iso(quiet_from)}")
    print(f"{'env':4} {'scope':6} {'kind':16} {'count':>5}  {'first':20} {'last':20}  route / detail / caller")
    for r in rows:
        print(f"{r['env']:4} {r['scope']:6} {r['kind']:16} {r['count']:>5}  {r['first']:20} {r['last']:20}  "
              f"{r['route']}  {r['detail']}  fwd={r['forwarded_for']} ua={r['user_agent'][:70]}")
    if not rows:
        print("(no replaced-route / deprecated-query / deprecated-route lines)")

    verdict: Dict[str, Any] = {}
    for env in args.envs:
        naming = [h for h in hits if h["env"] == env and h["naming"]]
        last = max((h["ts"] for h in naming), default=None)
        verdict[env] = {
            "naming_hits": len(naming),
            "naming_last": iso(last) if last else None,
            "naming_hits_in_quiet_window": sum(1 for h in naming if h["ts"] >= quiet_from),
            "other_alias_hits": sum(1 for h in hits if h["env"] == env and not h["naming"]),
        }
    print("\nper env:")
    for env, v in verdict.items():
        print(f"  {env}: naming hits {v['naming_hits']} (last {v['naming_last'] or '-'}), "
              f"in the last {args.quiet_days:g} days {v['naming_hits_in_quiet_window']}; "
              f"TD-51 / TD-40 alias hits {v['other_alias_hits']}")
    print(f"research log lines naming an old MCP tool: {len(research)}"
          + (f" (last {iso(max(h['ts'] for h in research))})" if research else ""))
    if gs is not None:
        print(f"research.ai_action_log rows naming an old tool: {gs['ai_action_log_old_tools_since']} since "
              f"{iso(since)} ({gs['ai_action_log_old_tools_ever']} ever, last {gs['ai_action_log_old_tools_last']})")
        print(f"journal.note refs stored as 'inst': {gs['journal_inst_refs']} in {gs['journal_inst_notes']} notes")
    print("old body field names (strategy_instance_id / instance_allocations in execution bodies): not logged by "
          "any api version — callers checked in code (see the R4 db-step file)")

    window_ok = since <= quiet_from
    open_ = (
        window_ok
        and all(v["naming_hits_in_quiet_window"] == 0 for v in verdict.values())
        and not [h for h in research if h["ts"] >= quiet_from]
        and (gs is None or (gs["journal_inst_refs"] == 0
                            and (gs["ai_action_log_old_tools_last"] == "-"
                                 or parse_ts(gs["ai_action_log_old_tools_last"].replace(" ", "T")) < quiet_from)))
    )
    if not window_ok:
        print(f"\nGATE CLOSED: the measured window starts {iso(since)}, after the quiet window's start "
              f"{iso(quiet_from)} (earliest open: {iso(since + timedelta(days=args.quiet_days))})")
    else:
        print("\nGATE " + ("OPEN" if open_ else "CLOSED") + f" (zero naming hits needed since {iso(quiet_from)})")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({"since": iso(since), "until": iso(until), "quiet_from": iso(quiet_from), "rows": rows,
                       "verdict": verdict, "research_lines": [{**h, "ts": iso(h["ts"])} for h in research],
                       "golden_source": gs, "gate_open": open_}, f, indent=2)
    return 0 if open_ else 1


if __name__ == "__main__":
    sys.exit(main())
