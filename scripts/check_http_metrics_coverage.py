#!/usr/bin/env python3
"""Every API with a ServiceMonitor is seen by the API alert rules (TD-161 ratchet).

BifrostAPIHighErrorRate / BifrostAPIHighLatency read ``http_requests_total`` and
``http_request_duration_seconds_bucket`` in one namespace regex. Until 2026-10 the regex was
``bifrost-.*`` and research-api, market-data-api and flex-query-api exported no HTTP series, so
their 5xx went unalerted. This check keeps the two halves together:

Static (default; no cluster needed), on ``k8s/monitoring``:

- the two API rules and the runtime ratchet BifrostAPIWithoutHttpMetrics use one and the same
  namespace regex;
- the ratchet exempts no target: its expression filters on nothing but that namespace regex
  (platform-api was the last exemption, until it exported the series — TD-195);
- the platform namespaces (PLATFORM_NAMESPACES) are inside that regex, and each is selected by
  some ServiceMonitor (TD-198: STG platform-api went unscraped, so it could fail with no alert);
- every namespace scraped by a ServiceMonitor / PodMonitor whose component is an API
  (APP_COMPONENTS) matches that regex, and every monitor's component is classified, so a new
  API monitor cannot land outside the rules unnoticed.

Live (``--live``; needs KUBECONFIG, read-only via the apiserver proxy): runs the ratchet
alert's own expression and lists every scraped API target that exports no
``http_requests_total``, and checks that every platform namespace has a platform-api target up.

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
#: platform-api's namespaces; its request series must reach the API rules like everyone's.
PLATFORM_NAMESPACES = ("bifrost-platform-prod", "bifrost-platform-stg")
#: A label matcher other than namespace in the ratchet's selectors is an exemption.
EXEMPTION = re.compile(r'\b(?!namespace\b)\w+\s*(?:!=|!~|=~|=)\s*"[^"]*"')
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

    for ns in PLATFORM_NAMESPACES:
        if not regex.fullmatch(ns):
            problems.append(
                f"{RULES.name}: platform namespace {ns!r} is outside the API rules' namespace "
                f"regex {regex.pattern!r}"
            )
    ratchet = exprs.get("BifrostAPIWithoutHttpMetrics", "")
    for selector in re.findall(r"\{([^}]*)\}", ratchet):
        for m in EXEMPTION.finditer(selector):
            problems.append(
                f"{RULES.name}: BifrostAPIWithoutHttpMetrics filters on {m.group(0).strip()!r}; "
                "the ratchet exempts no target (TD-195 removed the last one)"
            )

    scraped_by_service_monitor: set[str] = set()
    for path in sorted(MONITORING.glob("*.yaml")):
        for doc in yaml.safe_load_all(path.read_text()):
            if not doc or doc.get("kind") not in ("ServiceMonitor", "PodMonitor"):
                continue
            name = doc["metadata"]["name"]
            if doc["kind"] == "ServiceMonitor":
                scraped_by_service_monitor.update(
                    (doc["spec"].get("namespaceSelector") or {}).get("matchNames") or []
                )
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
    for ns in PLATFORM_NAMESPACES:
        if ns not in scraped_by_service_monitor:
            problems.append(
                f"{MONITORING.name}: platform namespace {ns!r} is selected by no ServiceMonitor, "
                "so its platform-api is never scraped (add it to bifrost-platform-api.yaml matchNames)"
            )
    return problems


def _query(expr: str) -> tuple[list[dict], str | None]:
    url = f"{PROMETHEUS}/query?query={urllib.parse.quote(expr)}"
    proc = subprocess.run(
        ["kubectl", "get", "--raw", url], capture_output=True, text=True
    )
    if proc.returncode != 0:
        return [], f"Prometheus query failed: {proc.stderr.strip()}"
    return json.loads(proc.stdout)["data"]["result"], None


def check_live() -> list[str]:
    result, err = _query(_rule_exprs()["BifrostAPIWithoutHttpMetrics"])
    if err:
        return [err]
    problems = [
        f"{r['metric'].get('namespace')}/{r['metric'].get('job')} is scraped but exports no "
        "http_requests_total"
        for r in result
    ]
    up, err = _query('count by (namespace) (up{job="platform-api"} == 1)')
    if err:
        return problems + [err]
    seen = {r["metric"].get("namespace") for r in up}
    problems += [
        f"{ns}: no platform-api target is up in Prometheus" for ns in PLATFORM_NAMESPACES if ns not in seen
    ]
    return problems


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
