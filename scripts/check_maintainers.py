#!/usr/bin/env python3
"""Maintainer inventory (agent-config/MAINTAINERS.yaml) vs the repo and, with --live, vs reality.

A maintainer is anything that runs by itself and reads or writes the system or
its data. The static check (default) requires every entry to have the ADR §7
fields, and every detected_by alert name to exist in a PrometheusRule file in
this repo. ``none: <reason>`` is the explicit absence of such an alert.

``--live`` is read-only. It reconciles the entries whose ids the inventory
treats as discovered objects:

- ``cronjob/<namespace>/<name>`` against ``kubectl get cronjobs -A``
- ``scheduledbackup/<namespace>/<name>`` against CNPG ScheduledBackups
- ``dagster/schedules/…`` and ``dagster/sensors/…`` member names against the
  Dagster GraphQL workspace inside ``research/dagster-webserver``
- ``launchd/.50/…`` and ``launchd/.52/…`` against ``launchctl list`` union the
  ``~/Library/LaunchAgents/com.bifrost.*`` plists on the two Mac minis

An extra or a missing object in those sources exits 1.

Platform loops, plugin timers, and Mac Pro bdev / Claude tasks are in the
inventory but are not part of this script's --live reconcile. Platform loops
whose detected_by is an alert, and the launchd rows, are reconciled in-cluster
by CronJob monitoring/maintainer-reconcile.

Usage: python3 scripts/check_maintainers.py [--live]
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "agent-config" / "MAINTAINERS.yaml"
REQUIRED = ("id", "what", "runs_on", "schedule", "env", "max_tier", "detected_by", "status")
ENVS = {"prod", "shared", "dev-only"}
TIERS = {"A", "B", "C", "D"}
STATUSES = {"active", "retiring"}
MINIS = (("192.168.10.50", ".50"), ("192.168.10.52", ".52"))
ALERT_RE = re.compile(r"^[ \t]*-[ \t]*alert:[ \t]*([A-Za-z_][A-Za-z0-9_]*)\s*$", re.M)
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
              schedules { name scheduleState { status } }
              sensors { name sensorState { status } }
            }
          }
        }
      }
    }
    ... on PythonError { message }
  }
}
"""


def fail(msg: str) -> None:
    print(f"check-maintainers: {msg}", file=sys.stderr)
    raise SystemExit(1)


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_inventory(text: str) -> list[dict]:
    """The subset this file is written in: a maintainers list of flat maps."""
    items: list[dict] = []
    cur: dict | None = None
    in_members = False
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("maintainers:"):
            continue
        if raw.startswith("  - "):
            if cur is not None:
                items.append(cur)
            cur = {}
            in_members = False
            key, value = _kv(raw[4:], n)
            cur[key] = value
            continue
        if raw.startswith("      - "):
            if cur is None or not in_members:
                fail(f"{INVENTORY.name}:{n}: list item outside members")
            cur.setdefault("members", []).append(unquote(raw[8:]))
            continue
        if not raw.startswith("    ") or cur is None:
            fail(f"{INVENTORY.name}:{n}: unexpected line")
        body = raw[4:]
        key, value = _kv(body, n)
        if value == "":
            in_members = True
            cur[key] = []
        else:
            in_members = False
            cur[key] = value
    if cur is not None:
        items.append(cur)
    if not items:
        fail(f"{INVENTORY.name}: no maintainers")
    return items


def _kv(body: str, n: int) -> tuple[str, str]:
    if ":" not in body:
        fail(f"{INVENTORY.name}:{n}: expected key: value")
    key, value = body.split(":", 1)
    key = key.strip()
    if not key:
        fail(f"{INVENTORY.name}:{n}: empty key")
    return key, unquote(value)


def prometheus_alerts() -> set[str]:
    found: set[str] = set()
    for path in ROOT.rglob("*"):
        if path.suffix not in {".yaml", ".yml"} or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if "kind: PrometheusRule" not in text:
            continue
        found.update(ALERT_RE.findall(text))
    if not found:
        fail("no PrometheusRule alerts found in the repo")
    return found


def static_check(items: list[dict]) -> None:
    alerts = prometheus_alerts()
    seen: set[str] = set()
    schedule_members: set[str] = set()
    sensor_members: set[str] = set()
    for item in items:
        missing = [k for k in REQUIRED if not str(item.get(k, "")).strip()]
        if missing:
            fail(f"{item.get('id', '?')}: missing {', '.join(missing)}")
        ident = item["id"]
        if ident in seen:
            fail(f"duplicate id {ident}")
        seen.add(ident)
        if item["env"] not in ENVS:
            fail(f"{ident}: env {item['env']!r} is not prod, shared, or dev-only")
        if item["max_tier"] not in TIERS:
            fail(f"{ident}: max_tier {item['max_tier']!r} is not A–D")
        if item["status"] not in STATUSES:
            fail(f"{ident}: status {item['status']!r} is not active or retiring")
        detected = item["detected_by"]
        if detected.startswith("none:"):
            if not detected[5:].strip():
                fail(f"{ident}: detected_by none: needs a reason")
        elif detected not in alerts:
            fail(f"{ident}: alert {detected} is not in a PrometheusRule file")
        members = item.get("members")
        if members is not None:
            if not isinstance(members, list) or not members or not all(isinstance(m, str) and m for m in members):
                fail(f"{ident}: members must be a non-empty list of names")
        if ident.startswith("dagster/schedules/"):
            if not members:
                fail(f"{ident}: a Dagster schedule group needs members")
            for name in members:
                if name in schedule_members:
                    fail(f"schedule {name} is in more than one group")
                schedule_members.add(name)
        elif ident.startswith("dagster/sensors/"):
            if not members:
                fail(f"{ident}: a Dagster sensor group needs members")
            for name in members:
                if name in sensor_members:
                    fail(f"sensor {name} is in more than one group")
                sensor_members.add(name)
        elif ident.startswith(("cronjob/", "scheduledbackup/", "launchd/")):
            parts = ident.split("/")
            if len(parts) != 3 or not all(parts):
                fail(f"{ident}: expected kind/scope/name")


def run(cmd: list[str], timeout: int = 90) -> str:
    env = os.environ.copy()
    env.setdefault("KUBECONFIG", str(pathlib.Path.home() / ".kube" / "bifrost-k3s.yaml"))
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        fail(f"{cmd[0]} failed: {exc}")
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        fail(f"{' '.join(cmd[:4])} exited {proc.returncode}: {err[:500]}")
    return proc.stdout


def names_from(kind: str) -> set[str]:
    raw = run(["kubectl", "get", kind, "-A", "-o", "json"])
    data = json.loads(raw)
    out = set()
    prefix = "cronjob" if kind == "cronjobs" else "scheduledbackup"
    for item in data.get("items", []):
        meta = item.get("metadata") or {}
        ns, name = meta.get("namespace"), meta.get("name")
        if ns and name:
            out.add(f"{prefix}/{ns}/{name}")
    return out


def dagster_names() -> tuple[set[str], set[str]]:
    encoded = base64.b64encode(DAGSTER_QUERY.encode()).decode()
    code = (
        "import base64,json,urllib.request;"
        f"q=base64.b64decode('{encoded}').decode();"
        "req=urllib.request.Request('http://127.0.0.1:3000/graphql',"
        "data=json.dumps({'query':q}).encode(),"
        "headers={'Content-Type':'application/json'});"
        "print(urllib.request.urlopen(req, timeout=60).read().decode())"
    )
    raw = run(["kubectl", "-n", "research", "exec", "deploy/dagster-webserver", "--", "python3", "-c", code])
    data = json.loads(raw)
    ws = (data.get("data") or {}).get("workspaceOrError") or {}
    if ws.get("__typename") != "Workspace":
        fail(f"Dagster workspace: {ws.get('message') or ws.get('__typename')}")
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
        fail("Dagster GraphQL returned no schedules")
    return schedules, sensors


def launchd_names() -> set[str]:
    key = pathlib.Path.home() / ".ssh" / "id_ed25519"
    found: set[str] = set()
    remote = (
        "launchctl list | awk 'NR>1 {print $NF}';"
        "echo ---;"
        "ls -1 \"$HOME/Library/LaunchAgents\"/com.bifrost.*.plist 2>/dev/null || true"
    )
    for host, tag in MINIS:
        raw = run([
            "ssh", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10",
            "-i", str(key), f"vision@{host}", remote,
        ], timeout=30)
        labels, _, plists = raw.partition("---")
        for line in labels.splitlines():
            name = line.strip()
            if name.startswith("com.bifrost."):
                found.add(f"launchd/{tag}/{name}")
        for line in plists.splitlines():
            base = pathlib.PurePosixPath(line.strip()).name
            if base.startswith("com.bifrost.") and base.endswith(".plist"):
                found.add(f"launchd/{tag}/{base[: -len('.plist')]}")
    return found


def live_check(items: list[dict]) -> None:
    want_cron = {i["id"] for i in items if i["id"].startswith("cronjob/")}
    want_backup = {i["id"] for i in items if i["id"].startswith("scheduledbackup/")}
    want_schedules = {m for i in items if i["id"].startswith("dagster/schedules/") for m in i.get("members") or []}
    want_sensors = {m for i in items if i["id"].startswith("dagster/sensors/") for m in i.get("members") or []}
    want_launchd = {i["id"] for i in items if i["id"].startswith("launchd/")}
    got_cron = names_from("cronjobs")
    got_backup = names_from("scheduledbackups.postgresql.cnpg.io")
    got_schedules, got_sensors = dagster_names()
    got_launchd = launchd_names()
    pairs = (
        ("cronjobs", want_cron, got_cron),
        ("scheduledbackups", want_backup, got_backup),
        ("dagster schedules", want_schedules, got_schedules),
        ("dagster sensors", want_sensors, got_sensors),
        ("launchd", want_launchd, got_launchd),
    )
    drifted = False
    for label, want, got in pairs:
        missing = sorted(got - want)
        extra = sorted(want - got)
        if missing or extra:
            drifted = True
            print(f"drift {label}:", file=sys.stderr)
            for name in missing:
                print(f"  live only: {name}", file=sys.stderr)
            for name in extra:
                print(f"  inventory only: {name}", file=sys.stderr)
    if drifted:
        raise SystemExit(1)
    print(
        "live drift 0 "
        f"(cronjobs={len(got_cron)} scheduledbackups={len(got_backup)} "
        f"schedules={len(got_schedules)} sensors={len(got_sensors)} launchd={len(got_launchd)})"
    )


def inventory_copy() -> None:
    copy = ROOT / "k8s" / "monitoring" / "maintainer-reconcile" / "MAINTAINERS.yaml"
    if not copy.is_file():
        fail(f"missing {copy.relative_to(ROOT)}")
    if copy.read_bytes() != INVENTORY.read_bytes():
        fail(f"{copy.relative_to(ROOT)} is not a byte copy of {INVENTORY.relative_to(ROOT)}")


def main() -> None:
    live = "--live" in sys.argv[1:]
    if any(a not in {"--live"} for a in sys.argv[1:]):
        fail("usage: python3 scripts/check_maintainers.py [--live]")
    items = parse_inventory(INVENTORY.read_text(encoding="utf-8"))
    static_check(items)
    inventory_copy()
    none = sum(1 for i in items if str(i["detected_by"]).startswith("none:"))
    print(f"ok {len(items)} maintainers; static; no-alert {none}")
    if live:
        live_check(items)


if __name__ == "__main__":
    main()
