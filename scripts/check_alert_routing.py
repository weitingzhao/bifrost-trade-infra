#!/usr/bin/env python3
"""Alerts that matter reach a person, not only an in-cluster webhook (TD-209 ratchet).

Until 2026-10-07 every alert went to one webhook that wrote STG platform-api's
in-memory audit log and returned 200: Alertmanager counted it as delivered and nobody
was told, while BifrostLogicalBackupMissing fired for hours. This check walks the
Alertmanager route tree the way Alertmanager does (first match, ``continue``) and fails
unless:

- Watchdog reaches a receiver outside the cluster (the relay's dead-man's switch);
- an alert with severity=critical, and every backup / WAL / NAS MinIO alert defined in
  k8s/monitoring PrometheusRules, reaches a receiver outside the cluster;
- those alerts still reach the in-cluster webhook too (nothing lost from the audit trail);
- every receiver outside the cluster has an egress rule in
  k8s/monitoring/alertmanager-webhook-network-policy.yaml (else Alertmanager cannot send).

"Outside the cluster" means a webhook URL whose host is not ``*.svc.cluster.local``.

Static (default): reads scripts/k3s/values-kube-prometheus.yaml.
Live (``--live``; needs KUBECONFIG, read-only): walks the running Alertmanager's routes.
Its status API masks webhook URLs, so which receivers are outside the cluster is taken
from the values file, by receiver name.

Usage: python3 scripts/check_alert_routing.py [--live]   (exit 1 on any problem)
"""

from __future__ import annotations

import ipaddress
import json
import pathlib
import re
import subprocess
import sys
from urllib.parse import urlparse

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
VALUES = ROOT / "scripts/k3s/values-kube-prometheus.yaml"
EGRESS = ROOT / "k8s/monitoring/alertmanager-webhook-network-policy.yaml"
PAGED = re.compile(r"Bifrost(PostgresBackup.*|PostgresWalArchiveStalled|LogicalBackup.*|MinIONas.*)")
WEBHOOK = "bifrost-ops-agent"


def parse_matcher(m: str):
    k, op, v = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(=~|!~|!=|=)\s*"?(.*?)"?\s*$', m).groups()
    return k, op, v


def matches(route: dict, labels: dict) -> bool:
    conds = [parse_matcher(m) for m in route.get("matchers") or []]
    conds += [(k, "=", v) for k, v in (route.get("match") or {}).items()]
    conds += [(k, "=~", v) for k, v in (route.get("match_re") or {}).items()]
    for k, op, v in conds:
        got = labels.get(k, "")
        ok = {"=": got == v, "!=": got != v,
              "=~": re.fullmatch(v, got) is not None, "!~": re.fullmatch(v, got) is None}[op]
        if not ok:
            return False
    return True


def route_to(route: dict, labels: dict, inherited: str | None = None) -> list[str]:
    """Receivers an alert reaches from this (already matched) route; a route
    without a receiver inherits its parent's."""
    own = route.get("receiver", inherited)
    out: list[str] = []
    for child in route.get("routes") or []:
        if matches(child, labels):
            out += route_to(child, labels, own)
            if not child.get("continue"):
                return out
    return out or [own]


def outside(receiver: dict) -> list[str]:
    urls = [w.get("url", "") for w in receiver.get("webhook_configs") or []]
    return [u for u in urls if u and not (urlparse(u).hostname or "").endswith(".svc.cluster.local")]


def egress_allows(url: str) -> bool:
    p = urlparse(url)
    port = p.port or (443 if p.scheme == "https" else 80)
    pol = yaml.safe_load(EGRESS.read_text())
    for rule in pol["spec"].get("egress") or []:
        ports = {x.get("port") for x in rule.get("ports") or []}
        for peer in rule.get("to") or []:
            cidr = (peer.get("ipBlock") or {}).get("cidr")
            if cidr and port in ports:
                try:
                    if ipaddress.ip_address(p.hostname) in ipaddress.ip_network(cidr):
                        return True
                except ValueError:
                    pass
    return False


def rule_alerts() -> list[tuple[str, str]]:
    out = []
    for f in sorted((ROOT / "k8s/monitoring").glob("*.yaml")):
        for d in yaml.safe_load_all(f.read_text()):
            if d and d.get("kind") == "PrometheusRule":
                for g in d["spec"]["groups"]:
                    for r in g.get("rules") or []:
                        if "alert" in r:
                            out.append((r["alert"], (r.get("labels") or {}).get("severity", "")))
    return out


def load_config(live: bool) -> dict:
    if not live:
        return yaml.safe_load(VALUES.read_text())["alertmanager"]["config"]
    r = subprocess.run(["kubectl", "get", "--raw",
                        "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-alertmanager:9093/proxy/api/v2/status"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        print(f"kubectl: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(json.loads(r.stdout)["config"]["original"])


def main() -> int:
    live = "--live" in sys.argv[1:]
    cfg = load_config(live)
    static_receivers = {r["name"]: r for r in load_config(False).get("receivers") or []}
    outside_names = {n for n, r in static_receivers.items() if outside(r)}
    receivers = {r["name"]: r for r in cfg.get("receivers") or []}
    route = cfg["route"]
    problems: list[str] = []

    def reach(labels):
        return [x for x in route_to(route, labels) if x]

    def paged(names):
        return [n for n in names if n in outside_names and n in receivers]

    hb = reach({"alertname": "Watchdog", "severity": "none"})
    if not paged(hb):
        problems.append(f"Watchdog reaches {hb}: no receiver outside the cluster (dead-man's switch)")

    cases = [("AnyCritical", "critical")] + [(a, s) for a, s in rule_alerts() if PAGED.fullmatch(a)]
    for name, sev in cases:
        got = reach({"alertname": name, "severity": sev, "namespace": "data"})
        if not paged(got):
            problems.append(f"{name} (severity={sev}) reaches {got}: nobody is paged")
        if WEBHOOK not in got:
            problems.append(f"{name} (severity={sev}) no longer reaches {WEBHOOK}")

    if not live:
        for n, r in receivers.items():
            for u in outside(r):
                if not egress_allows(u):
                    problems.append(f"receiver {n}: {u} has no egress rule in {EGRESS.relative_to(ROOT)}")

    where = "live Alertmanager" if live else VALUES.name
    if problems:
        print(f"FAIL ({where}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"ok ({where}): Watchdog and {len(cases)} paged alert kinds reach a receiver outside the cluster")
    return 0


if __name__ == "__main__":
    sys.exit(main())
