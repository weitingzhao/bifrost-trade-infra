#!/usr/bin/env python3
"""Loki gates for releases that wait on "no caller left" (TD-24, TD-51). Read-only.

The api logs every caller of a thing that is about to go; a release that removes it
waits until Loki shows none. This script asks Loki (through the apiserver service proxy,
no port-forward) and answers PASS / FAIL / INCONCLUSIVE with the evidence:

  td24-unknown-fields   "unknown request fields: <METHOD> <route> ignored [<names>]"
                        (api 0.3.x .. 0.8.4, bifrost_api.common.request_bodies). Owner rule:
                        a week with zero lines -> switch the bodies to extra="forbid".
                        Also counts the POST / PUT requests that reached those routes
                        (a week with no write proves nothing about the routes not written).
  td51-query-aliases    "deprecated query params: <METHOD> <path> <old>-><new> ... client=
                        forwarded_for= user_agent=" (api 0.6.6 .. 0.8.4,
                        bifrost_api.common.query_vocab). --group td51 (the TD-51 spellings,
                        api 0.8.3), r1 (strategy_instance_id(s), api 0.8.4, decision D4-A)
                        or all.
  td51-retired          "retired query params: <METHOD> <path> <old> (use <new>) ... client=
                        forwarded_for= user_agent=" (api 0.10.0 on: the TD-51 spellings are a
                        422 retired_query_param, bifrost_api.common.query_vocab). Lines from the
                        release probes (user_agent=bifrost-release-check/...) are not callers:
                        they are counted apart, as proof the line still reaches Loki.

Every run also reports, for the same window and envs: lines per env and 6-hour bucket from
the api pods (a bucket with none is a hole in the evidence), the api's other WARNING lines
(the pipe is alive) and promtail's dropped entries (Prometheus).

  python3 scripts/release/loki_gate.py td24-unknown-fields --since 2026-10-02T00:00:00Z
  python3 scripts/release/loki_gate.py td51-query-aliases --since 2026-10-05T13:30:00Z \\
      --until 2026-10-06T12:00:00Z --group td51
  python3 scripts/release/loki_gate.py td51-retired            # the last 24 h, after api 0.10.0

Every gate's line filter is checked against a line of the api version that emits it before a
run (GATE_FIXTURES, also `self-test`): a needle that no longer matches what the api logs would
read as a clean zero.

Exit: 0 PASS, 1 FAIL (lines found; each one is listed with its caller), 3 INCONCLUSIVE
(a hole in the logs, or promtail dropped entries: the hours and promtail pods are listed,
for a human to judge against the requests listed), 2 Loki / Prometheus unavailable.
Loki keeps 30 days and its earliest data is 2026-09-28 17:45 UTC. A 503 "no endpoints
available for service loki" means loki-0 is not Ready: wait and rerun, do not retry in a loop.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

LOKI = "/api/v1/namespaces/monitoring/services/loki:3100/proxy/loki/api/v1"
PROM = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1"
ENV_NS = {"dev": "bifrost-dev", "stg": "bifrost-stg", "prod": "bifrost-prod"}
API_APPS = "api-(account|market|monitor|research)"
BUCKET_S = 6 * 3600
FETCH_CHUNK_S = 24 * 3600
FETCH_LIMIT = 500

TD51_NAMES = ("since_ts", "until_ts", "opened_at_from", "opened_at_until", "trade_date_from", "trade_date_to",
              "expiration", "right")
R1_NAMES = ("strategy_instance_id", "strategy_instance_ids")
RELEASE_PROBE_UA = "bifrost-release-check"  # release_checks.USER_AGENT is bifrost-release-check/1

# The routes whose body was a LenientBody (api 0.3.x .. 0.8.4). {id} is any path segment.
TD24_ROUTES = (
    ("POST", "/watchlist"),
    ("POST", "/position-categories"),
    ("PUT", "/position-categories/tag"),
    ("PUT", "/position-categories/symbol-order"),
    ("PUT", "/instrument-classes/{id}"),
    ("POST", "/strategies/templates"),
    ("PUT", "/strategies/templates/{id}/legs"),
    ("PUT", "/strategies/templates/{id}/params"),
    ("PUT", "/strategies/templates/{id}/characteristics"),
    ("POST", "/strategies/structures"),
    ("PUT", "/strategies/structures/{id}"),
    ("POST", "/strategies/gate-safety"),
    ("PUT", "/strategies/gate-safety/{id}"),
    ("POST", "/gate-sets"),
    ("PUT", "/gate-sets/{id}"),
    ("POST", "/strategies/saved-searches"),
    ("POST", "/preferences/saved-searches"),
    ("POST", "/executions"),
    ("PUT", "/executions/{id}"),
    ("POST", "/executions/option-stock-links"),
    ("POST", "/executions/option-stock-links/query"),
)


class Unavailable(Exception):
    pass


# --- transport ---------------------------------------------------------------------------


def kube_get(path: str) -> Any:
    env = dict(os.environ)
    env.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/bifrost-k3s.yaml"))
    proc = subprocess.run(["kubectl", "get", "--raw", path], capture_output=True, text=True, env=env,
                          stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise Unavailable(proc.stderr.strip() or f"kubectl exit {proc.returncode}")
    try:
        body = json.loads(proc.stdout)
    except ValueError as e:
        raise Unavailable(f"not JSON from {path.split('?')[0]}: {e}") from e
    if body.get("status") != "success":
        raise Unavailable(f"{path.split('?')[0]}: {body.get('error') or body}")
    return body["data"]


def loki_instant(logql: str, at: datetime) -> List[Dict[str, Any]]:
    q = urllib.parse.urlencode({"query": logql, "time": str(_ns(at))})
    return kube_get(f"{LOKI}/query?{q}")["result"]


def loki_range(logql: str, start: datetime, end: datetime, *, step: Optional[int] = None,
               limit: int = FETCH_LIMIT) -> List[Dict[str, Any]]:
    params = {"query": logql, "start": str(_ns(start)), "end": str(_ns(end)), "limit": str(limit),
              "direction": "forward"}
    if step:
        params["step"] = str(step)
    return kube_get(f"{LOKI}/query_range?{urllib.parse.urlencode(params)}")["result"]


def prom_instant(promql: str, at: datetime) -> List[Dict[str, Any]]:
    q = urllib.parse.urlencode({"query": promql, "time": f"{at.timestamp():.0f}"})
    return kube_get(f"{PROM}/query?{q}")["result"]


def _ns(t: datetime) -> int:
    return int(t.timestamp() * 1e9)


# --- line parsing (pure; exercised by --self-test) ----------------------------------------

_TD24_RE = re.compile(r"unknown request fields: (?P<method>\S+) (?P<route>\S+) ignored \[(?P<names>.*)\]\s*$")
_TD51_RE = re.compile(
    r"deprecated query params: (?P<method>\S+) (?P<path>\S+) (?P<used>.*?) client=(?P<client>\S+)"
    r" forwarded_for=(?P<fwd>\S+) user_agent=(?P<ua>.*)$"
)
_TD51_RETIRED_RE = re.compile(
    r"retired query params: (?P<method>\S+) (?P<path>\S+) (?P<used>.*?) client=(?P<client>\S+)"
    r" forwarded_for=(?P<fwd>\S+) user_agent=(?P<ua>.*)$"
)
_ACCESS_RE = re.compile(r'uvicorn\.access:(?P<client>[0-9a-fA-F.:]+):\d+ - "(?P<method>[A-Z]+) (?P<path>[^ ?"]+)'
                        r'[^"]*" (?P<status>\d{3})')


def parse_td24(line: str) -> Optional[Dict[str, Any]]:
    m = _TD24_RE.search(line)
    if not m:
        return None
    names = [n.strip().strip("'\"") for n in m.group("names").split(",") if n.strip()]
    return {"method": m.group("method"), "route": m.group("route"), "names": names}


def parse_td51(line: str) -> Optional[Dict[str, Any]]:
    m = _TD51_RE.search(line)
    if not m:
        return None
    used = re.findall(r"(\w+)->(\w+)( \(ignored\))?", m.group("used"))
    return {
        "method": m.group("method"),
        "path": m.group("path"),
        "old": sorted({old for old, _new, _ign in used}),
        "client": m.group("client"),
        "forwarded_for": m.group("fwd"),
        "user_agent": m.group("ua").strip(),
    }


def parse_td51_retired(line: str) -> Optional[Dict[str, Any]]:
    m = _TD51_RETIRED_RE.search(line)
    if not m:
        return None
    used = re.findall(r"(\w+) \(use (\w+)\)", m.group("used"))
    return {
        "method": m.group("method"),
        "path": m.group("path"),
        "old": sorted({old for old, _new in used}),
        "client": m.group("client"),
        "forwarded_for": m.group("fwd"),
        "user_agent": m.group("ua").strip(),
    }


def td51_group_regex(group: str) -> str:
    names = {"td51": TD51_NAMES, "r1": R1_NAMES, "all": TD51_NAMES + R1_NAMES}[group]
    return "deprecated query params: .*(^| )(" + "|".join(names) + ")->"


# --- what each gate reads (pure) ------------------------------------------------------------

Filter = Tuple[str, str]  # (LogQL line-filter operator, operand)


def gate_filters(check: str, group: str = "td51") -> List[Filter]:
    """The LogQL line filters that select a gate's lines."""
    if check == "td24-unknown-fields":
        return [("|=", "unknown request fields: ")]
    if check == "td51-query-aliases":
        return [("|~", td51_group_regex(group))]
    if check == "td51-retired":
        return [("|=", "retired query params: "), ("!=", RELEASE_PROBE_UA)]
    raise ValueError(f"no line filter for gate {check}")


def probe_filters(check: str) -> Optional[List[Filter]]:
    """The release probes' own lines for a gate, when it excludes them (a positive control)."""
    if check == "td51-retired":
        return [("|=", "retired query params: "), ("|=", RELEASE_PROBE_UA)]
    return None


def logql_filters(filters: List[Filter]) -> str:
    return " ".join(f'{op} "{_logql_quote(v)}"' for op, v in filters)


def _logql_quote(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"')


def filters_match(filters: List[Filter], line: str) -> bool:
    """What Loki would answer for one line (|= != substring, |~ !~ regex)."""
    for op, v in filters:
        hit = (v in line) if op in ("|=", "!=") else bool(re.search(v, line))
        if hit != (op in ("|=", "|~")):
            return False
    return True


PARSERS = {"td24-unknown-fields": parse_td24, "td51-query-aliases": parse_td51, "td51-retired": parse_td51_retired}
CHECKS = tuple(PARSERS)

# Per gate: lines the api version that emits it writes, copied from its logger call
# (bifrost_api.common.request_bodies, .query_vocab). A gate whose filter stops matching the
# line its api writes reads every caller as zero; self_test() fails before any run does.
GATE_FIXTURES: Dict[str, List[Tuple[str, str]]] = {
    "td24-unknown-fields": [
        ("api 0.3.x..0.8.4", "WARNING:bifrost_api.common.request_bodies:unknown request fields: PUT "
                             "/strategies/templates/{strategy_template_id}/legs ignored ['legs[].leg_uid', 'x']"),
    ],
    "td51-query-aliases": [
        ("api 0.6.6..0.9.0", "WARNING:bifrost_api.common.query_vocab:deprecated query params: GET /executions "
                             "since_ts->from_ts client=10.42.8.39 forwarded_for=10.42.0.204 user_agent=python-httpx/0.28.1"),
    ],
    "td51-retired": [
        ("api 0.10.0", "WARNING:bifrost_api.common.query_vocab:retired query params: GET /transactions "
                       "since_ts (use from_ts) until_ts (use to_ts) client=10.42.8.39 forwarded_for=- "
                       "user_agent=python-httpx/0.28.1"),
        ("api 0.10.0", "WARNING:bifrost_api.common.query_vocab:retired query params: GET /research/greeks "
                       "right (use option_right) client=10.42.8.39 forwarded_for=10.42.0.204 "
                       "user_agent=Mozilla/5.0 (Macintosh)"),
    ],
}
PROBE_FIXTURES: Dict[str, str] = {
    "td51-retired": ("WARNING:bifrost_api.common.query_vocab:retired query params: GET /executions since_ts "
                     "(use from_ts) client=10.42.8.39 forwarded_for=10.42.0.1 user_agent=bifrost-release-check/1"),
}


def check_gate_fixtures() -> None:
    """Every gate has a fixture line of the api that emits it, and its filter and parser read it."""
    for check in CHECKS:
        fixtures = GATE_FIXTURES.get(check)
        assert fixtures, f"{check}: no fixture line (GATE_FIXTURES)"
        for version, line in fixtures:
            assert filters_match(gate_filters(check), line), f"{check}: filter misses the {version} line"
            assert PARSERS[check](line), f"{check}: parser misses the {version} line"
        probe = probe_filters(check)
        if probe:
            assert filters_match(probe, PROBE_FIXTURES[check]), f"{check}: probe filter misses the probe line"
            assert not filters_match(gate_filters(check), PROBE_FIXTURES[check]), f"{check}: counts the release probe"
    # The gates do not read each other's lines: api 0.10.0 refuses what 0.9.0 renamed.
    for check in CHECKS:
        for other in CHECKS:
            if other != check:
                for version, line in GATE_FIXTURES[other]:
                    assert not filters_match(gate_filters(check), line), f"{check} reads the {other} {version} line"


def route_regex(template: str) -> "re.Pattern[str]":
    return re.compile("^" + re.escape(template).replace(re.escape("{id}"), "[^/]+") + "$")


_TD24_ROUTE_RES = [(m, route_regex(t), t) for m, t in TD24_ROUTES]


def td24_route_of(method: str, path: str) -> Optional[str]:
    for m, rx, template in _TD24_ROUTE_RES:
        if m == method and rx.match(urllib.parse.unquote(path)):
            return template
    return None


def pod_ips() -> Dict[str, str]:
    """Running pods by IP, so forwarded_for names its pod. svclb-traefik-* in that field means the
    request came from outside the cluster through a node's LoadBalancer port (the Mac, the LAN)."""
    env = dict(os.environ)
    env.setdefault("KUBECONFIG", os.path.expanduser("~/.kube/bifrost-k3s.yaml"))
    proc = subprocess.run(["kubectl", "get", "pods", "-A", "--field-selector=status.phase=Running", "-o", "json"],
                          capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        return {}
    out: Dict[str, str] = {}
    for p in json.loads(proc.stdout).get("items", []):
        ip = p.get("status", {}).get("podIP")
        if ip and not p.get("spec", {}).get("hostNetwork"):
            out[ip] = f"{p['metadata']['namespace']}/{p['metadata']['name']}"
    return out


def caller_kind(user_agent: str) -> str:
    ua = user_agent.lower()
    if "bifrost-release-check" in ua or ua.startswith(("curl/", "python-urllib/")):
        return "agent / manual check"
    if "mozilla/" in ua:
        return "browser"
    if "python-httpx" in ua or "python-requests" in ua:
        return "service (python)"
    return "unknown"


# --- the evidence common to every check ---------------------------------------------------


def ns_selector(envs: Iterable[str]) -> str:
    return "|".join(ENV_NS[e] for e in envs)


def coverage(envs: List[str], start: datetime, end: datetime) -> Tuple[List[str], Dict[str, int]]:
    """Holes: (env, 6 h bucket) with no api line at all, one instant query per bucket.
    Also the api lines per env over the window."""
    holes: List[str] = []
    totals: Dict[str, int] = {e: 0 for e in envs}
    sel = f'{{namespace=~"{ns_selector(envs)}", app=~"{API_APPS}"}}'
    for b_start, b_end in _chunks(start, end, BUCKET_S):
        secs = max(1, int((b_end - b_start).total_seconds()))
        seen = {r["metric"].get("namespace"): int(float(r["value"][1]))
                for r in loki_instant(f"sum by (namespace) (count_over_time({sel} [{secs}s]))", b_end)}
        for env in envs:
            n = seen.get(ENV_NS[env], 0)
            totals[env] += n
            if n == 0:
                holes.append(f"{env} {b_start:%m-%d %H:%M}-{b_end:%H:%M}Z")
    return holes, totals


def promtail_drops(start: datetime, end: datetime) -> Tuple[Optional[float], List[str]]:
    """Entries promtail could not push in the window, and the hours (and promtail pod) they fell in."""
    secs = max(60, int((end - start).total_seconds()))
    try:
        res = prom_instant(f"sum(increase(promtail_dropped_entries_total[{secs}s]))", end)
        total = float(res[0]["value"][1]) if res else 0.0
        hours: List[str] = []
        if total > 0:
            q = urllib.parse.urlencode({
                "query": "sum by (instance) (increase(promtail_dropped_entries_total[1h]))",
                "start": f"{start.timestamp() + 3600:.0f}", "end": f"{end.timestamp():.0f}", "step": "3600"})
            for r in kube_get(f"{PROM}/query_range?{q}")["result"]:
                for t, v in r["values"]:
                    if float(v) >= 0.5:
                        t0 = datetime.fromtimestamp(float(t) - 3600, tz=timezone.utc)
                        hours.append(f"{t0:%m-%d %H:%M}-{t0 + timedelta(hours=1):%H:%M}Z "
                                     f"promtail {r['metric'].get('instance', '?')}: {float(v):.0f}")
    except Unavailable:
        return None, []
    return total, sorted(hours)


def count_by_env(envs: List[str], needle_logql: str, start: datetime, end: datetime) -> Dict[str, int]:
    out: Dict[str, int] = {e: 0 for e in envs}
    sel = f'{{namespace=~"{ns_selector(envs)}", app=~"{API_APPS}"}} {needle_logql}'
    for chunk_start, chunk_end in _chunks(start, end, 7 * 86400):
        secs = int((chunk_end - chunk_start).total_seconds())
        for r in loki_instant(f"sum by (namespace) (count_over_time({sel} [{secs}s]))", chunk_end):
            env = next((e for e, ns in ENV_NS.items() if ns == r["metric"].get("namespace")), None)
            if env in out:
                out[env] += int(float(r["value"][1]))
    return out


def fetch_lines(envs: List[str], needle_logql: str, start: datetime, end: datetime) -> List[Tuple[datetime, Dict[str, str], str]]:
    sel = f'{{namespace=~"{ns_selector(envs)}", app=~"{API_APPS}"}} {needle_logql}'
    rows: List[Tuple[datetime, Dict[str, str], str]] = []
    for chunk_start, chunk_end in _chunks(start, end, FETCH_CHUNK_S):
        for r in loki_range(sel, chunk_start, chunk_end):
            for ts, line in r["values"]:
                rows.append((datetime.fromtimestamp(int(ts) / 1e9, tz=timezone.utc), r["stream"], line))
    rows.sort(key=lambda x: x[0])
    return rows


def _chunks(start: datetime, end: datetime, size_s: int) -> Iterable[Tuple[datetime, datetime]]:
    t = start
    while t < end:
        nxt = min(end, t + timedelta(seconds=size_s))
        yield t, nxt
        t = nxt


# --- checks -------------------------------------------------------------------------------


def check_td24(envs: List[str], start: datetime, end: datetime) -> Tuple[int, Dict[str, Any]]:
    needle = logql_filters(gate_filters("td24-unknown-fields"))
    hits = count_by_env(envs, needle, start, end)
    report: Dict[str, Any] = {"lines": hits, "callers": []}
    if sum(hits.values()):
        for t, stream, line in fetch_lines(envs, needle, start, end):
            p = parse_td24(line) or {"raw": line[:300]}
            p.update(time=f"{t:%Y-%m-%d %H:%M:%S}Z", env=stream.get("namespace"), pod=stream.get("pod"))
            p["access_log_near"] = _access_near(stream, t, p.get("method"))
            report["callers"].append(p)
    # Requests that reached a body route (a 403 is the write guard, before the body is read).
    writes: Dict[Tuple[str, str, str, str], int] = defaultdict(int)
    sel = (f'{{namespace=~"{ns_selector(envs)}", app=~"api-(account|market)"}} |= "uvicorn.access" '
           f'|~ "\\"(POST|PUT) "')
    for t, stream, line in fetch_lines_all(sel, start, end):
        m = _ACCESS_RE.search(line)
        if not m:
            continue
        route = td24_route_of(m.group("method"), m.group("path"))
        if route:
            env = next((e for e, ns in ENV_NS.items() if ns == stream.get("namespace")), "?")
            writes[(env, m.group("method"), route, m.group("status")[0] + "xx")] += 1
    report["requests"] = {" ".join(k): v for k, v in sorted(writes.items())}
    return sum(hits.values()), report


def fetch_lines_all(selector: str, start: datetime, end: datetime) -> Iterable[Tuple[datetime, Dict[str, str], str]]:
    """Every line of a selector, paging forward past the per-query limit."""
    t = start
    while t < end:
        res = loki_range(selector, t, end, limit=5000)
        batch = [(int(ts), r["stream"], line) for r in res for ts, line in r["values"]]
        if not batch:
            return
        batch.sort(key=lambda x: x[0])
        for ts, stream, line in batch:
            yield datetime.fromtimestamp(ts / 1e9, tz=timezone.utc), stream, line
        if len(batch) < 5000:
            return
        t = datetime.fromtimestamp(batch[-1][0] / 1e9 + 1e-6, tz=timezone.utc)


def _access_near(stream: Dict[str, str], t: datetime, method: Optional[str]) -> List[str]:
    """The access-log lines of the same pod within 3 s (the field log has no caller)."""
    pod = stream.get("pod")
    if not pod:
        return []
    sel = f'{{namespace="{stream.get("namespace")}", pod="{pod}"}} |= "uvicorn.access" |= "\\"{method or ""} "'
    try:
        res = loki_range(sel, t - timedelta(seconds=3), t + timedelta(seconds=3), limit=20)
    except Unavailable:
        return []
    return sorted(line[:200] for r in res for _ts, line in r["values"])


def check_td51(envs: List[str], start: datetime, end: datetime, group: str) -> Tuple[int, Dict[str, Any]]:
    needle = logql_filters(gate_filters("td51-query-aliases", group))
    hits = count_by_env(envs, needle, start, end)
    report: Dict[str, Any] = {"group": group, "lines": hits, "callers": []}
    if sum(hits.values()):
        report["callers"] = _callers(envs, needle, start, end, parse_td51)
    return sum(hits.values()), report


def check_td51_retired(envs: List[str], start: datetime, end: datetime) -> Tuple[int, Dict[str, Any]]:
    """api 0.10.0 on: a caller still sending a TD-51 spelling got a 422 and left this line."""
    needle = logql_filters(gate_filters("td51-retired"))
    hits = count_by_env(envs, needle, start, end)
    probes = count_by_env(envs, logql_filters(probe_filters("td51-retired") or []), start, end)
    report: Dict[str, Any] = {"lines": hits, "release_probe_lines": probes, "callers": []}
    if sum(hits.values()):
        report["callers"] = _callers(envs, needle, start, end, parse_td51_retired)
    return sum(hits.values()), report


def _callers(envs: List[str], needle: str, start: datetime, end: datetime, parse: Any) -> List[Dict[str, Any]]:
    agg: Dict[Tuple[str, ...], Dict[str, Any]] = {}
    for t, stream, line in fetch_lines(envs, needle, start, end):
        p = parse(line)
        if not p:
            continue
        key = (stream.get("namespace", "?"), p["method"], p["path"], ",".join(p["old"]),
               p["client"], p["forwarded_for"], p["user_agent"])
        row = agg.setdefault(key, {"env": key[0], "request": f"{p['method']} {p['path']}", "old": p["old"],
                                   "client": p["client"], "forwarded_for": p["forwarded_for"], "user_agent": p["user_agent"],
                                   "kind": caller_kind(p["user_agent"]), "count": 0,
                                   "first": f"{t:%m-%d %H:%M:%S}Z"})
        row["count"] += 1
        row["last"] = f"{t:%m-%d %H:%M:%S}Z"
    ips = pod_ips()
    for row in agg.values():
        row["client_pod"] = ips.get(row["client"], "-")  # traefik when it came through the gateway
        pod = ips.get(row["forwarded_for"], "")
        row["forwarded_for_pod"] = pod or "-"
        if "svclb-traefik" in pod:
            row["from"] = "outside the cluster, through a node's LoadBalancer port (Mac / LAN)"
    return list(agg.values())


# --- main ---------------------------------------------------------------------------------


def _when(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def self_test() -> None:
    line = ("WARNING:bifrost_api.common.request_bodies:unknown request fields: PUT "
            "/strategies/templates/{strategy_template_id}/legs ignored ['legs[].leg_uid', 'x']")
    assert parse_td24(line) == {"method": "PUT", "route": "/strategies/templates/{strategy_template_id}/legs",
                                "names": ["legs[].leg_uid", "x"]}
    line = ("WARNING:bifrost_api.common.query_vocab:deprecated query params: GET /executions since_ts->from_ts "
            "strategy_instance_id->trade_id (ignored) client=10.42.8.39 forwarded_for=10.42.0.204 "
            "user_agent=python-httpx/0.28.1")
    p = parse_td51(line)
    assert p and p["old"] == ["since_ts", "strategy_instance_id"] and p["user_agent"] == "python-httpx/0.28.1"
    assert re.search(td51_group_regex("td51"), line) and re.search(td51_group_regex("r1"), line)
    assert not re.search(td51_group_regex("td51"), "deprecated query params: GET /trades strategy_instance_ids->trade_ids")
    assert not re.search(td51_group_regex("td51"), "deprecated query params: GET /x option_right->y")
    assert re.search(td51_group_regex("td51"), "deprecated query params: GET /research/greeks right->option_right")
    assert td24_route_of("PUT", "/instrument-classes/ZZQ%7CSTK%7C%7C%7C") == "/instrument-classes/{id}"
    assert td24_route_of("PUT", "/executions/-101") == "/executions/{id}"
    assert td24_route_of("POST", "/executions/option-stock-links/query") == "/executions/option-stock-links/query"
    assert td24_route_of("POST", "/executions/fetch") is None
    m = _ACCESS_RE.search('INFO:uvicorn.access:10.42.9.4:36126 - "PUT /executions/-7 HTTP/1.1" 200')
    assert m and m.group("path") == "/executions/-7" and m.group("status") == "200"
    assert caller_kind("curl/8.9.1") == "agent / manual check" and caller_kind("Mozilla/5.0 (Mac)") == "browser"
    p = parse_td51_retired(GATE_FIXTURES["td51-retired"][0][1])
    assert p and p["old"] == ["since_ts", "until_ts"] and p["forwarded_for"] == "-" and p["path"] == "/transactions"
    p = parse_td51_retired(GATE_FIXTURES["td51-retired"][1][1])
    assert p and p["old"] == ["right"] and p["user_agent"] == "Mozilla/5.0 (Macintosh)"
    assert logql_filters(gate_filters("td51-retired")) == '|= "retired query params: " != "bifrost-release-check"'
    assert logql_filters([("|~", 'a"b\\d')]) == '|~ "a\\"b\\\\d"'
    check_gate_fixtures()
    print("self-test ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("check", choices=[*CHECKS, "self-test"])
    ap.add_argument("--since", help="ISO time, UTC (default: td24 2026-10-02T00:00Z, td51 24 h ago)")
    ap.add_argument("--until", help="ISO time, UTC (default: now)")
    ap.add_argument("--envs", default="dev,stg,prod")
    ap.add_argument("--group", choices=["td51", "r1", "all"], default="td51", help="td51-query-aliases only")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    a = ap.parse_args()
    if a.check == "self-test":
        self_test()
        return 0
    check_gate_fixtures()  # a filter that misses what the api logs would read as a clean zero
    envs = [e.strip() for e in a.envs.split(",") if e.strip()]
    for e in envs:
        if e not in ENV_NS:
            ap.error(f"unknown env {e}")
    end = _when(a.until) if a.until else datetime.now(timezone.utc)
    if a.since:
        start = _when(a.since)
    elif a.check == "td24-unknown-fields":
        start = datetime(2026, 10, 2, tzinfo=timezone.utc)
    else:
        start = end - timedelta(hours=24)
    try:
        if a.check == "td24-unknown-fields":
            found, report = check_td24(envs, start, end)
        elif a.check == "td51-retired":
            found, report = check_td51_retired(envs, start, end)
        else:
            found, report = check_td51(envs, start, end, a.group)
        holes, totals = coverage(envs, start, end)
        alive = count_by_env(envs, '|= "WARNING:bifrost_api."', start, end)
    except Unavailable as e:
        print(f"UNAVAILABLE: {e}", file=sys.stderr)
        return 2
    drops, drop_hours = promtail_drops(start, end)
    report.update(window=f"{start:%Y-%m-%d %H:%M}Z .. {end:%Y-%m-%d %H:%M}Z", envs=envs, api_lines=totals,
                  api_warning_lines=alive, holes=holes, promtail_dropped=drops, promtail_drop_hours=drop_hours)
    if found:
        verdict, code = "FAIL", 1
    elif holes or drops is None or drops > 0:
        verdict, code = "INCONCLUSIVE", 3
    else:
        verdict, code = "PASS", 0
    report["verdict"] = verdict
    if a.json:
        print(json.dumps(report, indent=2, default=str))
        return code
    print(f"{a.check}{' (' + a.group + ')' if a.check == 'td51-query-aliases' else ''}  {report['window']}")
    print(f"  lines found:          {report['lines']}")
    if "release_probe_lines" in report:
        print(f"  release probe lines:  {report['release_probe_lines']}   (bifrost-release-check, not callers)")
    print(f"  api lines per env:    {totals}   (holes, 6 h buckets with none: {len(holes)})")
    for h in holes[:20]:
        print(f"    hole {h}")
    print(f"  api WARNING lines:    {alive}   (the pipe is alive when > 0)")
    print(f"  promtail dropped:     {'unknown (Prometheus unavailable)' if drops is None else int(drops)}"
          + ("   (all nodes and namespaces; a dropped entry may or may not be an api line)" if drops else ""))
    for h in drop_hours:
        print(f"    {h}")
    if "requests" in report:
        print("  POST / PUT that reached a body route (env method route status: count):")
        for k, v in report["requests"].items():
            print(f"    {k}: {v}")
        if not report["requests"]:
            print("    none")
    for c in report["callers"]:
        print(f"  caller: {json.dumps(c, default=str)}")
    print(verdict)
    return code


if __name__ == "__main__":
    sys.exit(main())
