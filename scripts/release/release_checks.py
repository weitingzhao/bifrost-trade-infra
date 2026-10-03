#!/usr/bin/env python3
"""Release checks over HTTP (TD-84), used by release_tool.py: snapshots of the Trade API,
their diff, /health core identity, probes. GETs only."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Pattern, Tuple

GATEWAYS = {
    "stg": "http://192.168.10.73:30880",
    "prod": "http://192.168.10.73:30881",
    "dev": "http://192.168.10.73:30882",
}
# The domains whose /health reports core_version / core_sha (account is served by trading;
# /api/account/health returns the frontend's HTML, not the api).
CORE_HEALTH_DOMAINS = ("monitor", "trading", "market", "research")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
USER_AGENT = "bifrost-release-check/1"
MISSING = object()


def die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def gateway(env: str) -> str:
    if env not in GATEWAYS:
        die(f"unknown env '{env}' (dev, stg, prod)")
    return os.environ.get(f"BIFROST_GATEWAY_{env.upper()}", GATEWAYS[env]).rstrip("/")


# ── HTTP snapshots ───────────────────────────────────────────────────────────


def http_get(url: str, tries: int = 4, timeout: float = 180) -> Tuple[int, Dict[str, str], bytes]:
    last: Optional[Exception] = None
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()
        except Exception as e:  # network, timeout
            last = e
            if attempt < tries - 1:
                print(f"retry {url}: {e}", file=sys.stderr)
                time.sleep(10)
    raise RuntimeError(f"GET {url} failed: {last}")


def get_json(url: str) -> Any:
    status, _, body = http_get(url)
    if status != 200:
        raise RuntimeError(f"GET {url} -> {status}: {body[:200]!r}")
    return json.loads(body)


def discover_accounts(base: str, executions: List[Dict[str, Any]]) -> List[str]:
    found = {str(r["account_id"]) for r in executions if r.get("account_id")}
    try:
        status = get_json(base + "/api/monitor/status")
        for acct in ((status.get("portfolio") or {}).get("accounts")) or []:
            if acct.get("account_id"):
                found.add(str(acct["account_id"]))
    except Exception as e:  # the executions alone still name the accounts with fills
        print(f"warning: /api/monitor/status unreadable ({e}); accounts from executions only", file=sys.stderr)
    return sorted(found)


def cmd_snapshot(args: argparse.Namespace) -> int:
    base = gateway(args.env)
    rows: List[Dict[str, Any]] = []
    url = base + "/api/trading/executions?limit=0"
    body = get_json(url)
    rows.extend(body.get("items", body.get("executions", [])))
    while body.get("next_cursor"):
        body = get_json(f"{url}&cursor={urllib.request.quote(str(body['next_cursor']))}")
        rows.extend(body.get("items", []))
    total = body.get("total")
    if isinstance(total, int) and total != len(rows):
        die(f"executions: total {total} but read {len(rows)}", 1)
    execs = {
        str(r.get("account_executions_id")): {
            "ck": r.get("contract_key"),
            "side": r.get("side"),
            "q": r.get("quantity"),
        }
        for r in rows
    }
    accounts = args.accounts.split(",") if args.accounts else discover_accounts(base, rows)
    perf = get_json(base + "/api/trading/performance")
    model = {
        a: get_json(base + f"/api/portfolio/portfolio/model-analysis?account_id={urllib.request.quote(a)}")
        for a in accounts
    }
    health = {}
    for d in CORE_HEALTH_DOMAINS:
        try:
            h = get_json(f"{base}/api/{d}/health")
            health[d] = {"core_sha": h.get("core_sha"), "core_version": h.get("core_version")}
        except Exception as e:  # recorded, not fatal: the snapshot is about the data
            health[d] = {"error": str(e)}
    snap = {
        "meta": {
            "env": args.env,
            "gateway": base,
            "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "accounts": accounts,
            "executions": len(execs),
            "health": health,
        },
        "execs": execs,
        "perf": perf,
        "model": model,
    }
    with open(args.output, "w") as fh:
        json.dump(snap, fh, sort_keys=True)
    cores = sorted({f"{h.get('core_version')}@{str(h.get('core_sha'))[:12]}" for h in health.values()})
    print(f"{args.env}: {len(execs)} executions, {len(accounts)} accounts, core {', '.join(cores)} -> {args.output}")
    return 0


# ── diff ─────────────────────────────────────────────────────────────────────


def norm(path: str) -> str:
    """perf.calendar[3].x and perf.transactions[account_transactions_id=790].x -> [*]."""
    return re.sub(r"\[[^\]]*\]", "[*]", path)


ROW_KEYS_AFTER_IDS = ("period_start_ts", "period_label", "contract_key", "symbol")


def row_key(x: List[Any], y: List[Any]) -> Optional[str]:
    """A field that identifies the rows of two lists of objects, so a reordered or grown
    list is compared row by row instead of by position: the most specific *_id field
    whose values are present and unique in both lists, else a period / symbol field."""
    rows = x + y
    if not rows or not all(isinstance(r, dict) for r in rows):
        return None
    common = set(rows[0]).intersection(*rows[1:])

    def unique(k: str) -> bool:
        for lst in (x, y):
            vals = [r.get(k) for r in lst]
            if any(v is None or isinstance(v, (dict, list)) for v in vals) or len(set(vals)) != len(vals):
                return False
        return True

    ids = sorted((k for k in common if k == "id" or k.endswith("_id")), key=lambda k: (-len(k), k))
    for k in [*ids, *ROW_KEYS_AFTER_IDS]:
        if k in common and unique(k):
            return k
    return None


def walk(x: Any, y: Any, path: str, out: List[Tuple[str, str, Any, Any]]) -> None:
    if x is MISSING:
        out.append(("added", path, None, y))
    elif y is MISSING:
        out.append(("removed", path, x, None))
    elif isinstance(x, dict) and isinstance(y, dict):
        for k in sorted(set(x) | set(y), key=str):
            walk(x.get(k, MISSING), y.get(k, MISSING), f"{path}.{k}", out)
    elif isinstance(x, list) and isinstance(y, list) and x != y and (key := row_key(x, y)):
        bx = {r[key]: r for r in x}
        by = {r[key]: r for r in y}
        for k in sorted(set(bx) | set(by), key=str):
            walk(bx.get(k, MISSING), by.get(k, MISSING), f"{path}[{key}={k}]", out)
    elif isinstance(x, list) and isinstance(y, list):
        if len(x) != len(y):
            out.append(("length", path, len(x), len(y)))
            return
        for i, (p, q) in enumerate(zip(x, y, strict=True)):
            walk(p, q, f"{path}[{i}]", out)
    elif (
        isinstance(x, (int, float))
        and isinstance(y, (int, float))
        and not isinstance(x, bool)
        and not isinstance(y, bool)
    ):
        if abs(x - y) > 1e-6 * max(1.0, abs(x)):
            out.append(("changed", path, x, y))
    elif x != y:
        out.append(("changed", path, x, y))


def allow_pattern(p: str) -> Pattern[str]:
    """`*` matches anything; `[*]` is the literal list-row marker the diff prints."""
    parts = [re.escape(s).replace(r"\*", ".*") for s in p.split("[*]")]
    return re.compile("^" + r"\[\*\]".join(parts) + "$")


def load_allow(files: List[str]) -> List[Pattern[str]]:
    patterns: List[Pattern[str]] = []
    for f in files:
        with open(f) as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if line:
                    patterns.append(allow_pattern(line))
    return patterns


def short(v: Any) -> str:
    s = json.dumps(v, sort_keys=True, default=str)
    return s if len(s) <= 60 else s[:57] + "..."


def diff_snapshots(a: Dict[str, Any], b: Dict[str, Any], allow: List[Pattern[str]]) -> Dict[str, Any]:
    report: Dict[str, Any] = {"sections": {}, "unexpected": 0, "allowed": 0}
    ea, eb = a.get("execs", {}), b.get("execs", {})
    records: List[Tuple[str, str, Any, Any]] = []
    for k in sorted(set(ea) - set(eb)):
        records.append(("removed", f"execs.{k}", ea[k], None))
    for k in sorted(set(eb) - set(ea)):
        records.append(("added", f"execs.{k}", None, eb[k]))
    for k in sorted(set(ea) & set(eb)):
        walk(ea[k], eb[k], f"execs.{k}", records)
    sections = {"execs": records}
    for part in ("perf", "model"):
        recs: List[Tuple[str, str, Any, Any]] = []
        walk(a.get(part, MISSING), b.get(part, MISSING), part, recs)
        sections[part] = recs

    for part, recs in sections.items():
        groups: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for kind, path, x, y in recs:
            if part == "execs":
                # execs.<id>.<field> -> execs.*.<field>; execs.<id> -> execs.*
                key_path = re.sub(r"^execs\.[^.]+", "execs.*", path)
            else:
                key_path = norm(path)
            allowed = kind == "added" or any(p.match(key_path) or p.match(path) for p in allow)
            g = groups.setdefault(
                (kind, key_path), {"kind": kind, "path": key_path, "count": 0, "allowed": allowed, "examples": []}
            )
            g["count"] += 1
            if len(g["examples"]) < 2:
                g["examples"].append([path, x, y])
        kinds = {g["kind"] for g in groups.values()}
        if not groups:
            verdict = "identical"
        elif kinds == {"added"}:
            verdict = "only added keys"
        else:
            verdict = "changed values"
        unexpected = [g for g in groups.values() if not g["allowed"]]
        report["sections"][part] = {
            "verdict": verdict,
            "differences": len(recs),
            "unexpected": sum(g["count"] for g in unexpected),
            "groups": sorted(groups.values(), key=lambda g: (g["allowed"], g["kind"], g["path"])),
        }
        report["unexpected"] += sum(g["count"] for g in unexpected)
        report["allowed"] += sum(g["count"] for g in groups.values() if g["allowed"] and g["kind"] != "added")
    report["executions"] = {
        "before": len(ea),
        "after": len(eb),
        "added": len(set(eb) - set(ea)),
        "removed": len(set(ea) - set(eb)),
    }
    return report


def print_diff(report: Dict[str, Any]) -> None:
    e = report["executions"]
    print(f"executions: {e['before']} -> {e['after']} (added {e['added']}, removed {e['removed']})")
    for part, sec in report["sections"].items():
        flag = "" if not sec["unexpected"] else f"  <-- {sec['unexpected']} UNEXPECTED"
        print(f"{part}: {sec['verdict']} ({sec['differences']} differences){flag}")
        for g in sec["groups"]:
            mark = "ok " if g["allowed"] else "!! "
            label = "allowed" if g["allowed"] and g["kind"] != "added" else g["kind"]
            print(
                f"   {mark}{g['kind']:<7} x{g['count']:<5} {g['path']}" + ("" if label == g["kind"] else f"  ({label})")
            )
            for path, x, y in g["examples"]:
                print(f"         {path}: {short(x)} -> {short(y)}")
    verdict = "PASS" if not report["unexpected"] else "FAIL"
    print(f"diff: {verdict} — {report['unexpected']} unexpected, {report['allowed']} allowed changes")


def cmd_diff(args: argparse.Namespace) -> int:
    with open(args.before) as fh:
        a = json.load(fh)
    with open(args.after) as fh:
        b = json.load(fh)
    report = diff_snapshots(a, b, load_allow(args.allow or []))
    print_diff(report)
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({k: v for k, v in report.items()}, fh, default=str, indent=1)
    return 1 if report["unexpected"] else 0


# ── /health core identity and probes ─────────────────────────────────────────


def core_version_at(repo: Optional[str], sha: str) -> Optional[str]:
    if not repo or not os.path.isdir(repo):
        return None
    proc = subprocess.run(["git", "-C", repo, "show", f"{sha}:pyproject.toml"], capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    m = re.search(r'^version\s*=\s*"([^"]+)"', proc.stdout, re.M)
    return m.group(1) if m else None


def cmd_health(args: argparse.Namespace) -> int:
    base = gateway(args.env)
    expect_sha = args.expect_sha.strip()
    if not SHA_RE.match(expect_sha):
        die(f"--expect-sha must be 40 hex, got {expect_sha!r}")
    expect_ver = core_version_at(args.core_repo, expect_sha)
    seen: Dict[str, Dict[str, Any]] = {}
    failures = 0
    for d in CORE_HEALTH_DOMAINS:
        try:
            h = get_json(f"{base}/api/{d}/health")
        except Exception as e:
            print(f"  !! {d:<9} {e}")
            failures += 1
            continue
        sha, ver = h.get("core_sha"), h.get("core_version")
        seen[d] = {"core_sha": sha, "core_version": ver, "status": h.get("status")}
        ok = sha == expect_sha and (ver == expect_ver if expect_ver else ver not in (None, "", "unknown"))
        failures += 0 if ok else 1
        print(f"  {'ok' if ok else '!!'} {d:<9} core_version={ver} core_sha={sha}")
    versions = {v["core_version"] for v in seen.values()}
    if len(versions) > 1:
        print(f"  !! domains disagree on core_version: {sorted(map(str, versions))}")
        failures += 1
    if expect_ver:
        print(f"  expected core {expect_ver} @ {expect_sha}")
    else:
        print(
            f"  expected core_sha {expect_sha}; version not cross-checked "
            f"(commit not in {args.core_repo or 'a local core checkout'} — set BIFROST_CORE_REPO or fetch)"
        )
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(
                {"expect_sha": expect_sha, "expect_version": expect_ver, "domains": seen, "failures": failures},
                fh,
                indent=1,
            )
    print(f"health: {'PASS' if not failures else 'FAIL'}")
    return 1 if failures else 0


def cmd_probes(args: argparse.Namespace) -> int:
    base = gateway(args.env)
    failures = ran = 0
    for f in args.file:
        with open(f) as fh:
            probes = json.load(fh).get("probes", [])
        for p in probes:
            if not p.get("enabled", True) or (p.get("envs") and args.env not in p["envs"]):
                continue
            ran += 1
            problems = []
            try:
                status, headers, body = http_get(base + p["path"], tries=2, timeout=60)
            except Exception as e:
                print(f"  !! {p.get('name', p['path'])}: {e}")
                failures += 1
                continue
            if status != p.get("status", 200):
                problems.append(f"status {status} != {p.get('status', 200)}")
            if p.get("json"):
                try:
                    json.loads(body)
                except ValueError:
                    problems.append(f"not JSON ({headers.get('content-type')})")
            for name, want in (p.get("headers") or {}).items():
                got = headers.get(name.lower())
                if got is None or (want is not None and got != want):
                    problems.append(f"header {name}={got!r}, want {want!r}")
            for name in p.get("absent_headers") or []:
                if name.lower() in headers:
                    problems.append(f"header {name} present ({headers[name.lower()]!r})")
            if p.get("contains") and p["contains"].encode() not in body:
                problems.append(f"body lacks {p['contains']!r}")
            failures += 1 if problems else 0
            print(
                f"  {'!!' if problems else 'ok'} {p.get('name', p['path'])}"
                + (f": {'; '.join(problems)}" if problems else "")
            )
    print(f"probes: {'PASS' if not failures else 'FAIL'} ({ran} run, {failures} failed)")
    return 1 if failures else 0


def cmd_core_sha(args: argparse.Namespace) -> int:
    h = get_json(f"{gateway(args.env)}/api/monitor/health")
    sha = str(h.get("core_sha") or "")
    if not SHA_RE.match(sha):
        die(f"{args.env} /api/monitor/health core_sha is {sha!r}", 1)
    print(sha)
    return 0
