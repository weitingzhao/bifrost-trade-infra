#!/usr/bin/env python3
"""The Trade daemon's liveness chain stays wired end to end (TD-215 ratchet).

The PROD daemon's Lease holder is the only writer of raw_broker.account / raw_broker.positions.
Until 2026-10-07 nothing alerted when it stopped: no livenessProbe, no scrape, no rule. The chain
is five pieces in three places; this check fails when one of them goes missing.

Static (default; no cluster needed):

- k8s/base/worker/manifest.yaml: the daemon container declares port ``metrics`` (9108) and a
  livenessProbe that reads ``/health`` on it;
- k8s/monitoring: a PodMonitor selects the daemon pods (``app.kubernetes.io/name: daemon``) on
  port ``metrics`` in bifrost-prod and is listed in the kustomization;
- bifrost-alerting-rules.yaml: BifrostTradeDaemonRawBrokerStale, BifrostTradeDaemonHeartbeatStale
  and their absent() twin BifrostTradeDaemonMetricsAbsent exist, read the worker's metric names
  (WORKER_METRICS, defined in bifrost-trade-worker daemon/app/observability.py) in bifrost-prod,
  and the raw_broker rule is gated on a TWS session (bifrost_ib_gateway_slot_connected) so a
  logged-off TWS does not page every night.

Live (``--live``; KUBECONFIG, read-only via the apiserver proxy): a bifrost-prod daemon target is
up and the leader exports both timestamps.

Usage: python3 scripts/check_daemon_liveness.py [--live]   (exit 1 on any problem)
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "k8s" / "base" / "worker" / "manifest.yaml"
MONITORING = ROOT / "k8s" / "monitoring"
RULES = MONITORING / "bifrost-alerting-rules.yaml"

PORT_NAME, PORT = "metrics", 9108
HEARTBEAT = "bifrost_daemon_heartbeat_timestamp_seconds"
RAW_BROKER = "bifrost_daemon_raw_broker_last_write_timestamp_seconds"
WORKER_METRICS = (HEARTBEAT, RAW_BROKER)
#: rule -> metrics it must read (all in bifrost-prod)
RULE_READS = {
    "BifrostTradeDaemonRawBrokerStale": (RAW_BROKER,),
    "BifrostTradeDaemonHeartbeatStale": (HEARTBEAT,),
    "BifrostTradeDaemonMetricsAbsent": (HEARTBEAT, RAW_BROKER),
}
SESSION_GATE = "bifrost_ib_gateway_slot_connected"
PROMETHEUS = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1"


def _daemon_container() -> dict | None:
    for doc in yaml.safe_load_all(MANIFEST.read_text()):
        if doc and doc.get("kind") == "Deployment" and doc["metadata"]["name"] == "daemon":
            for c in doc["spec"]["template"]["spec"]["containers"]:
                if c["name"] == "daemon":
                    return c
    return None


def check_manifest() -> list[str]:
    c = _daemon_container()
    if c is None:
        return [f"{MANIFEST.name}: no Deployment daemon with a container daemon"]
    problems = []
    ports = {p.get("name"): p.get("containerPort") for p in c.get("ports") or []}
    if ports.get(PORT_NAME) != PORT:
        problems.append(f"{MANIFEST.name}: daemon container has no port {PORT_NAME}={PORT}")
    probe = c.get("livenessProbe")
    if not probe:
        problems.append(f"{MANIFEST.name}: daemon container has no livenessProbe")
    elif f":{PORT}/health" not in json.dumps(probe) and (
        (probe.get("httpGet") or {}).get("path") != "/health"
    ):
        problems.append(f"{MANIFEST.name}: the daemon livenessProbe does not read /health on {PORT}")
    return problems


def check_monitor() -> list[str]:
    found = []
    for path in sorted(MONITORING.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc or doc.get("kind") != "PodMonitor":
                continue
            spec = doc["spec"]
            if (spec.get("selector") or {}).get("matchLabels", {}).get("app.kubernetes.io/name") != "daemon":
                continue
            ns = (spec.get("namespaceSelector") or {}).get("matchNames") or []
            ports = [e.get("port") for e in spec.get("podMetricsEndpoints") or []]
            if "bifrost-prod" in ns and PORT_NAME in ports:
                found.append(path.name)
    if not found:
        return [f"{MONITORING.name}: no PodMonitor scrapes the daemon's {PORT_NAME} port in bifrost-prod"]
    listed = yaml.safe_load((MONITORING / "kustomization.yaml").read_text())["resources"]
    return [f"kustomization.yaml: {f} is not listed in resources" for f in found if f not in listed]


def check_rules() -> list[str]:
    doc = yaml.safe_load(RULES.read_text())
    exprs = {
        r["alert"]: " ".join(str(r["expr"]).split())
        for g in doc["spec"]["groups"]
        for r in g["rules"]
        if r.get("alert") in RULE_READS
    }
    problems = []
    for name, metrics in RULE_READS.items():
        expr = exprs.get(name)
        if expr is None:
            problems.append(f"{RULES.name}: rule {name} is missing")
            continue
        for m in metrics:
            if f'{m}{{namespace="bifrost-prod"}}' not in expr:
                problems.append(f'{RULES.name}: {name} does not read {m}{{namespace="bifrost-prod"}}')
    raw = exprs.get("BifrostTradeDaemonRawBrokerStale", "")
    if raw and SESSION_GATE not in raw:
        problems.append(
            f"{RULES.name}: BifrostTradeDaemonRawBrokerStale is not gated on {SESSION_GATE}; it would "
            "fire every night the TWS auto log off empties the plugin snapshot"
        )
    if "absent(" not in exprs.get("BifrostTradeDaemonMetricsAbsent", "absent("):
        problems.append(f"{RULES.name}: BifrostTradeDaemonMetricsAbsent has no absent()")
    return problems


def _query(expr: str) -> tuple[list[dict], str | None]:
    url = f"{PROMETHEUS}/query?query={urllib.parse.quote(expr)}"
    proc = subprocess.run(
        ["kubectl", "get", "--raw", url], capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    if proc.returncode != 0:
        return [], f"Prometheus query failed: {proc.stderr.strip()}"
    return json.loads(proc.stdout)["data"]["result"], None


def check_live() -> list[str]:
    problems = []
    for expr, what in (
        ('up{namespace="bifrost-prod",pod=~"daemon-.*"} == 1', "no bifrost-prod daemon target is up"),
        (f'{HEARTBEAT}{{namespace="bifrost-prod"}}', "the PROD leader exports no heartbeat timestamp"),
        (f'{RAW_BROKER}{{namespace="bifrost-prod"}}', "the PROD leader exports no raw_broker write timestamp"),
    ):
        rows, err = _query(expr)
        if err:
            return problems + [err]
        if not rows:
            problems.append(what)
    return problems


def main(argv: list[str]) -> int:
    problems = check_manifest() + check_monitor() + check_rules()
    if "--live" in argv and not problems:
        problems += check_live()
    for p in problems:
        print(f"FAIL {p}")
    if not problems:
        print("ok: daemon /health probe, scrape and liveness rules are wired" + (" and live" if "--live" in argv else ""))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
