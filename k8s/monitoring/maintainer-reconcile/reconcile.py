#!/usr/bin/env python3
"""Nightly maintainer reconcile (LANE-E1). Read-only against the inventory sources.

Compares agent-config/MAINTAINERS.yaml (mounted beside this file) with:

- CronJobs and CNPG ScheduledBackups, via the Kubernetes API
- Dagster schedule and sensor names, via the research webserver GraphQL
- platform loop ids whose detected_by is an alert, via
  bifrost_maintainer_last_success_timestamp_seconds
- launchd/.50 and launchd/.52, via each mini's operator plane
  GET /api/v1/agent/launchd (viewer token)

Drift greater than zero deletes ConfigMap monitoring/maintainer-reconcile-clean
so kube_configmap_created goes absent. A clean pass deletes and recreates that
ConfigMap so its creation time is this run. The job exits 0 after it has
recorded the result. It exits 1 only when it could not observe the cluster.

Usage:
  python3 reconcile.py --self-test
  python3 reconcile.py
"""

from __future__ import annotations

import json
import os
import pathlib
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

CLEAN_CM = "maintainer-reconcile-clean"
CLEAN_NS = "monitoring"
DAGSTER_QUERY = """
query Workspace {
  workspaceOrError {
    __typename
    ... on Workspace {
      locationEntries {
        locationOrLoadError {
          __typename
          ... on RepositoryLocation {
            repositories {
              schedules { name }
              sensors { name }
            }
          }
        }
      }
    }
    ... on PythonError { message }
  }
}
"""


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_inventory(text: str) -> list[dict]:
    items: list[dict] = []
    cur: dict | None = None
    in_members = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("maintainers:"):
            continue
        if raw.startswith("  - "):
            if cur is not None:
                items.append(cur)
            cur = {}
            in_members = False
            key, _, value = raw[4:].partition(":")
            cur[key.strip()] = unquote(value)
            continue
        if raw.startswith("      - ") and cur is not None and in_members:
            cur.setdefault("members", []).append(unquote(raw[8:]))
            continue
        if cur is None or not raw.startswith("    "):
            continue
        key, _, value = raw[4:].partition(":")
        if value.strip() == "":
            in_members = True
            cur[key.strip()] = []
        else:
            in_members = False
            cur[key.strip()] = unquote(value)
    if cur is not None:
        items.append(cur)
    return items


def names(items: list[dict], prefix: str) -> set[str]:
    return {i["id"] for i in items if str(i.get("id", "")).startswith(prefix)}


def members(items: list[dict], prefix: str) -> set[str]:
    out: set[str] = set()
    for item in items:
        if str(item.get("id", "")).startswith(prefix):
            out.update(item.get("members") or [])
    return out


def platform_expected(items: list[dict]) -> set[str]:
    """Loops that claim an alert must have a success series. none: does not."""
    out = set()
    for item in items:
        ident = str(item.get("id", ""))
        if not ident.startswith("platform/"):
            continue
        detected = str(item.get("detected_by", ""))
        if detected.startswith("none:"):
            continue
        out.add(ident)
    return out


def drift_lines(items: list[dict], live: dict) -> list[str]:
    lines: list[str] = []

    def pair(label: str, want: set[str], got: set[str]) -> None:
        for name in sorted(got - want):
            lines.append(f"{label} live only: {name}")
        for name in sorted(want - got):
            lines.append(f"{label} inventory only: {name}")

    pair("cronjob", names(items, "cronjob/"), set(live.get("cronjobs") or []))
    pair("scheduledbackup", names(items, "scheduledbackup/"), set(live.get("scheduledbackups") or []))
    pair("dagster schedule", members(items, "dagster/schedules/"), set(live.get("schedules") or []))
    pair("dagster sensor", members(items, "dagster/sensors/"), set(live.get("sensors") or []))

    launchd = live.get("launchd") or {}
    want_launchd = {i["id"] for i in items if str(i.get("id", "")).startswith("launchd/")}
    got_launchd: set[str] = set()
    running: dict[str, bool] = {}
    for tag, info in launchd.items():
        err = (info or {}).get("error") or ""
        if err:
            lines.append(f"launchd {tag} unread: {err}")
            continue
        for label, svc in (info.get("services") or {}).items():
            ident = f"launchd/{tag}/{label}"
            got_launchd.add(ident)
            running[ident] = bool((svc or {}).get("running"))
    if not any((info or {}).get("error") for info in launchd.values()):
        pair("launchd", want_launchd, got_launchd)
    for item in items:
        ident = str(item.get("id", ""))
        if not ident.startswith("launchd/"):
            continue
        if not str(item.get("schedule", "")).startswith("keep-alive"):
            continue
        if ident in running and not running[ident]:
            lines.append(f"launchd not running: {ident}")

    series = set(live.get("series") or [])
    expected = platform_expected(items)
    for ident in sorted(expected - series):
        lines.append(f"platform series missing: {ident}")
    known = set(expected)
    for item in items:
        ident = str(item.get("id", ""))
        if ident.startswith("platform/"):
            known.add(ident)
    for label in sorted(series):
        if label in known:
            continue
        if any(label.startswith(parent + "/") for parent in known):
            continue
        lines.append(f"platform series extra: {label}")
    return lines


def kube_request(method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
    token = pathlib.Path("/var/run/secrets/kubernetes.io/serviceaccount/token").read_text(encoding="utf-8").strip()
    ctx = ssl.create_default_context(cafile="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request("https://kubernetes.default.svc" + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def object_names(kind_path: str, prefix: str) -> set[str]:
    status, raw = kube_request("GET", kind_path)
    if status != 200:
        raise SystemExit(f"kubernetes {kind_path} HTTP {status}: {raw[:300]!r}")
    data = json.loads(raw)
    out = set()
    for item in data.get("items") or []:
        meta = item.get("metadata") or {}
        ns, name = meta.get("namespace"), meta.get("name")
        if ns and name:
            out.add(f"{prefix}/{ns}/{name}")
    return out


def dagster_names() -> tuple[set[str], set[str]]:
    url = os.environ.get(
        "DAGSTER_URL", "http://dagster-webserver.research.svc.cluster.local:3000/graphql"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps({"query": DAGSTER_QUERY}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    ws = (data.get("data") or {}).get("workspaceOrError") or {}
    if ws.get("__typename") != "Workspace":
        raise SystemExit(f"Dagster workspace: {ws.get('message') or ws.get('__typename')}")
    schedules: set[str] = set()
    sensors: set[str] = set()
    for entry in ws.get("locationEntries") or []:
        loc = entry.get("locationOrLoadError") or {}
        if loc.get("__typename") != "RepositoryLocation":
            continue
        for repo in loc.get("repositories") or []:
            for sch in repo.get("schedules") or []:
                schedules.add(sch["name"])
            for sen in repo.get("sensors") or []:
                sensors.add(sen["name"])
    if not schedules:
        raise SystemExit("Dagster GraphQL returned no schedules")
    return schedules, sensors


def prometheus_series() -> set[str]:
    base = os.environ.get(
        "PROMETHEUS_URL", "http://kube-prometheus-stack-prometheus.monitoring.svc:9090"
    ).rstrip("/")
    # A rollout clears the in-memory gauges; look back as far as the longest
    # stale threshold in bifrost-maintainer-rules.yaml (cert-expiry, 14d).
    query = urllib.parse.urlencode(
        {"query": "last_over_time(bifrost_maintainer_last_success_timestamp_seconds[14d])"}
    )
    with urllib.request.urlopen(f"{base}/api/v1/query?{query}", timeout=60) as resp:
        data = json.loads(resp.read().decode())
    if data.get("status") != "success":
        raise SystemExit(f"prometheus query: {data.get('status')}")
    out = set()
    for series in (data.get("data") or {}).get("result") or []:
        label = ((series.get("metric") or {}).get("maintainer") or "").strip()
        if label:
            out.add(label)
    return out


def launchd_from(base: str, token: str) -> dict:
    url = base.rstrip("/") + "/api/v1/agent/launchd"
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001 — one unread mini is drift, not a crash
        return {"error": str(exc), "services": {}}
    services = {}
    for svc in payload.get("services") or []:
        label = str(svc.get("label") or "")
        if label.startswith("com.bifrost."):
            services[label] = {"running": bool(svc.get("running"))}
    return {"error": "", "services": services}


def record(clean: bool, summary: str) -> None:
    path = f"/api/v1/namespaces/{CLEAN_NS}/configmaps/{CLEAN_CM}"
    status, _ = kube_request("DELETE", path)
    if status not in (200, 202, 404):
        raise SystemExit(f"delete {CLEAN_CM} HTTP {status}")
    if not clean:
        print(f"recorded drift; {CLEAN_CM} removed")
        return
    body = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": CLEAN_CM,
            "namespace": CLEAN_NS,
            "labels": {"app.kubernetes.io/name": "maintainer-reconcile"},
        },
        "data": {"drift": "0", "summary": summary[:400]},
    }
    status, raw = kube_request("POST", f"/api/v1/namespaces/{CLEAN_NS}/configmaps", body)
    if status not in (200, 201):
        raise SystemExit(f"create {CLEAN_CM} HTTP {status}: {raw[:300]!r}")
    print(f"recorded clean {CLEAN_CM}")


def live_main() -> int:
    here = pathlib.Path(__file__).resolve().parent
    inventory_path = pathlib.Path(os.environ.get("INVENTORY_PATH", str(here / "MAINTAINERS.yaml")))
    items = parse_inventory(inventory_path.read_text(encoding="utf-8"))
    token = os.environ.get("OPERATOR_PLANE_TOKEN", "").strip()
    planes = (
        (".50", os.environ.get("OPERATOR_PLANE_50", "http://192.168.10.50:8783")),
        (".52", os.environ.get("OPERATOR_PLANE_52", "http://192.168.10.52:8783")),
    )
    if not token:
        launchd = {tag: {"error": "OPERATOR_PLANE_TOKEN unset", "services": {}} for tag, _ in planes}
    else:
        launchd = {tag: launchd_from(url, token) for tag, url in planes}
    schedules, sensors = dagster_names()
    live = {
        "cronjobs": object_names("/apis/batch/v1/cronjobs", "cronjob"),
        "scheduledbackups": object_names(
            "/apis/postgresql.cnpg.io/v1/scheduledbackups", "scheduledbackup"
        ),
        "schedules": schedules,
        "sensors": sensors,
        "series": prometheus_series(),
        "launchd": launchd,
    }
    lines = drift_lines(items, live)
    for line in lines:
        print(line)
    summary = "drift 0" if not lines else f"drift {len(lines)}: " + "; ".join(lines[:8])
    print(summary)
    record(not lines, summary)
    return 0


def self_test() -> None:
    text = """
maintainers:
  - id: cronjob/data/backup-retry
    schedule: "*/15 4-9 * * * UTC"
    detected_by: BifrostPostgresBackupRetryStale
  - id: scheduledbackup/data/bifrost-postgres-daily
    schedule: "0 0 3 * * * UTC"
    detected_by: BifrostPostgresBackupMissing
  - id: dagster/schedules/market-trim
    schedule: "15 2 * * * UTC"
    detected_by: BifrostDagsterScheduleMissedTick
    members:
      - market_trim_schedule
  - id: platform/prod/ib-autorepair
    schedule: "every 30s"
    detected_by: BifrostMaintainerIBAutoRepairStale
  - id: platform/stg/data-clone-scheduler
    schedule: "every 1h"
    detected_by: "none: loop off"
  - id: platform/prod/patrol-autopilot
    schedule: "scan every 30s"
    detected_by: BifrostMaintainerPatrolScanStale
    members:
      - ops-autopilot
  - id: launchd/.50/com.bifrost.operator-plane
    schedule: "keep-alive"
    detected_by: "none: no prometheus series"
  - id: launchd/.50/com.bifrost.peer-watchdog
    schedule: "every 60s"
    detected_by: "none: interval job"
"""
    items = parse_inventory(text)
    clean = {
        "cronjobs": {"cronjob/data/backup-retry"},
        "scheduledbackups": {"scheduledbackup/data/bifrost-postgres-daily"},
        "schedules": {"market_trim_schedule"},
        "sensors": set(),
        "series": {
            "platform/prod/ib-autorepair",
            "platform/prod/patrol-autopilot",
            "platform/prod/patrol-autopilot/ops-autopilot",
        },
        "launchd": {
            ".50": {
                "error": "",
                "services": {
                    "com.bifrost.operator-plane": {"running": True},
                    "com.bifrost.peer-watchdog": {"running": False},
                },
            }
        },
    }
    if drift_lines(items, clean):
        raise SystemExit("self-test: clean fixture drifted: " + "; ".join(drift_lines(items, clean)))
    missing = dict(clean)
    missing["series"] = {"platform/prod/patrol-autopilot"}
    got = drift_lines(items, missing)
    if not any("ib-autorepair" in line for line in got):
        raise SystemExit(f"self-test: missing series not reported: {got}")
    if any("data-clone" in line for line in got):
        raise SystemExit(f"self-test: none: loop was required: {got}")
    stopped = dict(clean)
    stopped["launchd"] = {
        ".50": {
            "error": "",
            "services": {
                "com.bifrost.operator-plane": {"running": False},
                "com.bifrost.peer-watchdog": {"running": False},
            },
        }
    }
    got = drift_lines(items, stopped)
    if not any("not running" in line and "operator-plane" in line for line in got):
        raise SystemExit(f"self-test: stopped keep-alive not reported: {got}")
    if any("peer-watchdog" in line and "not running" in line for line in got):
        raise SystemExit(f"self-test: interval job treated as keep-alive: {got}")
    extra = dict(clean)
    extra["schedules"] = {"market_trim_schedule", "not_in_inventory"}
    if not any("not_in_inventory" in line for line in drift_lines(items, extra)):
        raise SystemExit("self-test: extra schedule not reported")
    here = pathlib.Path(__file__).resolve()
    root = here.parents[3]
    src = root / "agent-config" / "MAINTAINERS.yaml"
    copy = here.with_name("MAINTAINERS.yaml")
    if src.is_file() and copy.is_file() and src.read_bytes() != copy.read_bytes():
        raise SystemExit("self-test: MAINTAINERS.yaml copy drifted from agent-config")
    print("self-test ok")


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        self_test()
        return 0
    if sys.argv[1:]:
        print("usage: reconcile.py [--self-test]", file=sys.stderr)
        return 2
    return live_main()


if __name__ == "__main__":
    sys.exit(main())
