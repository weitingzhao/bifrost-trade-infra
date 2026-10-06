#!/usr/bin/env python3
"""Every API with a ServiceMonitor is seen by the API alert rules (TD-161 ratchet).

BifrostAPIHighErrorRate / BifrostAPIHighLatency read ``http_requests_total`` and
``http_request_duration_seconds_bucket`` in one namespace regex. Until 2026-10 the regex was
``bifrost-.*`` and research-api, market-data-api and flex-query-api exported no HTTP series, so
their 5xx went unalerted. This check keeps the two halves together:

Static (default; no cluster needed), on ``k8s/monitoring``:

- the two API rules and the runtime ratchet BifrostAPIWithoutHttpMetrics use one and the same
  namespace regex;
- every namespace scraped by a ServiceMonitor / PodMonitor whose component is an API
  (APP_COMPONENTS) matches that regex, and every monitor's component is classified, so a new
  API monitor cannot land outside the rules unnoticed.

Live (``--live``; needs KUBECONFIG, read-only via the apiserver proxy): runs the ratchet
alert's own expression and lists every scraped API target that exports no
``http_requests_total`` (platform-api is exempt in the expression until it exports them).

Usage: python3 scripts/check_http_metrics_coverage.py [--live]   (exit 1 on any problem)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MONITORING = ROOT / "k8s" / "monitoring"
RULES = MONITORING / "bifrost-alerting-rules.yaml"

API_RULES = (
    "BifrostAPIHighErrorRate",
    "BifrostAPIHighLatency",
    "BifrostAPIWithoutHttpMetrics",
)
#: Monitors that scrape an HTTP API Deployment; their namespaces must be inside the rules.
APP_COMPONENTS = frozenset({"api", "research", "plugin", "control-plane"})
#: Monitors that scrape exporters / infrastructure, not an API of ours.
INFRA_COMPONENTS = frozenset({"postgres", "redis", "minio", "logging", "gateway"})
PROMETHEUS = "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1"


def _rule_exprs() -> dict[str, str]:
    doc = yaml.safe_load(RULES.read_text())
    out: dict[str, str] = {}
    for group in doc["spec"]["groups"]:
        for rule in group["rules"]:
            if rule.get("alert") in API_RULES:
                out[rule["alert"]] = " ".join(str(rule["expr"]).split())
    return out


def check_static() -> list[str]:
    problems: list[str] = []
    exprs = _rule_exprs()
    for name in API_RULES:
        if name not in exprs:
            problems.append(f"{RULES.name}: rule {name} is missing")
    flat = {r for e in exprs.values() for r in re.findall(r'namespace=~"([^"]+)"', e)}
    if len(flat) != 1:
        problems.append(
            f"{RULES.name}: API rules use different namespace regexes: {sorted(flat)}"
        )
        return problems
    regex = re.compile(next(iter(flat)))

    for path in sorted(MONITORING.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc or doc.get("kind") not in ("ServiceMonitor", "PodMonitor"):
                continue
            name = doc["metadata"]["name"]
            component = (doc["metadata"].get("labels") or {}).get(
                "app.kubernetes.io/component"
            )
            if component in INFRA_COMPONENTS:
                continue
            if component not in APP_COMPONENTS:
                problems.append(
                    f"{path.name}: {doc['kind']} {name} has component {component!r}; classify it in "
                    "APP_COMPONENTS (an API the rules must see) or INFRA_COMPONENTS"
                )
                continue
            names = (doc["spec"].get("namespaceSelector") or {}).get("matchNames") or []
            if not names:
                problems.append(
                    f"{path.name}: {name} has no namespaceSelector.matchNames"
                )
            for ns in names:
                if not regex.fullmatch(ns):
                    problems.append(
                        f"{path.name}: {name} scrapes namespace {ns!r}, outside the API rules' "
                        f"namespace regex {regex.pattern!r}"
                    )
    return problems


def check_live() -> list[str]:
    expr = _rule_exprs()["BifrostAPIWithoutHttpMetrics"]
    url = f"{PROMETHEUS}/query?query={urllib.parse.quote(expr)}"
    proc = subprocess.run(
        ["kubectl", "get", "--raw", url], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return [f"Prometheus query failed: {proc.stderr.strip()}"]
    result = json.loads(proc.stdout)["data"]["result"]
    return [
        f"{r['metric'].get('namespace')}/{r['metric'].get('job')} is scraped but exports no "
        "http_requests_total"
        for r in result
    ]


def main(argv: list[str]) -> int:
    problems = check_static()
    if "--live" in argv and not problems:
        problems += check_live()
    for p in problems:
        print(f"FAIL {p}")
    if not problems:
        live = " and exports http_requests_total" if "--live" in argv else ""
        print(f"ok: every API monitor is inside the API rules{live}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
