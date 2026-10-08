#!/usr/bin/env python3
"""Alerts that matter reach a person, and the audit webhook is PROD (TD-209, LANE-A1).

Until 2026-10-07 every alert went to one webhook that wrote STG platform-api's
in-memory audit log and returned 200: Alertmanager counted it as delivered and nobody
was told, while BifrostLogicalBackupMissing fired for hours. LANE-A1 points that
default receiver at PROD platform-api and drops STG from the alert path. This check
walks the Alertmanager route tree the way Alertmanager does (first match, ``continue``)
and fails unless:

- Watchdog reaches a receiver outside the cluster (the relay's dead-man's switch);
- an alert with severity=critical, and every backup / WAL / NAS MinIO / cluster-state
  backup alert defined in k8s/monitoring PrometheusRules, reaches a receiver outside
  the cluster; ``BifrostClusterStateBackupFailed`` is checked even before its
  PrometheusRule lands (LANE-A2);
- those alerts still reach the in-cluster webhook too (nothing lost from the audit trail);
- every receiver outside the cluster has an egress rule in
  k8s/monitoring/alertmanager-webhook-network-policy.yaml (else Alertmanager cannot send);
- no receiver URL contains ``bifrost-platform-stg``;
- the default receiver's webhook is
  ``platform-api.bifrost-platform-prod.svc.cluster.local:8780/api/v1/ops-agent/alertmanager``;
- Alertmanager's egress policy allows monitoring → that PROD Service port and does not
  name the STG namespace;
- the webhook bearer the apply script writes is the PROD reporter token, not the
  operator token (the route accepts reporter or above and only writes diagnostics);
- no alert in k8s/monitoring/bifrost-maintainer-rules.yaml matches a paging route
  (maintainer liveness is an audit record; backup failures already page under
  the existing backup names);
- ``BifrostPostgresRecoveryDrillStale`` (k8s/monitoring/bifrost-postgres-recovery-drill-rules.yaml)
  is severity warning, its threshold is 100 days (8640000 seconds) or the
  last-pass ConfigMap is absent, and it does not match a paging route.

"Outside the cluster" means a webhook URL whose host is not ``*.svc.cluster.local``.

Static (default): reads scripts/k3s/values-kube-prometheus.yaml and the egress policy file.
Live (``--live``; needs KUBECONFIG, read-only): reads the running config from Secret
``monitoring/alertmanager-kube-prometheus-stack-alertmanager`` key ``alertmanager.yaml``.
The status API masks every webhook URL as ``<secret>``, so it cannot prove the target.
The Secret holds the same document with URLs in the clear and ``bearer_token_file``
paths (not the token). The live egress check reads NetworkPolicy
``alertmanager-webhook-egress``.

Usage: python3 scripts/check_alert_routing.py [--live]   (exit 1 on any problem)
"""

from __future__ import annotations

import base64
import hashlib
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
MAINTAINER_RULES = ROOT / "k8s/monitoring/bifrost-maintainer-rules.yaml"
DRILL_RULES = ROOT / "k8s/monitoring/bifrost-postgres-recovery-drill-rules.yaml"
DRILL_STALE_ALERT = "BifrostPostgresRecoveryDrillStale"
# 100 days. The rule uses `>` so an age of exactly this many seconds does not fire.
DRILL_STALE_SECONDS = 100 * 24 * 60 * 60
DRILL_CM = 'kube_configmap_created{namespace="data",configmap="pg-recovery-drill-last-pass"}'
PAGED = re.compile(
    r"Bifrost(PostgresBackup.*|PostgresWalArchiveStalled|LogicalBackup.*|MinIONas.*|ClusterStateBackup.*)"
)
# LANE-A2's rule file is not in this branch. The page matcher must already accept the name.
SYNTHETIC_PAGED = (("BifrostClusterStateBackupFailed", "warning"),)
WEBHOOK = "bifrost-ops-agent"
STG_MARK = "bifrost-platform-stg"
PROD_HOST = "platform-api.bifrost-platform-prod.svc.cluster.local"
PROD_PATH = "/api/v1/ops-agent/alertmanager"
PROD_NS = "bifrost-platform-prod"
AM_SECRET = "alertmanager-kube-prometheus-stack-alertmanager"
EGRESS_NAME = "alertmanager-webhook-egress"
TOKEN_SCRIPT = ROOT / "scripts/k3s/apply-platform-role-tokens.sh"
# The webhook bearer is the PROD reporter token. The operator printf must not come back.
WEBHOOK_TOKEN_FN = "webhook_token"
WEBHOOK_REPORTER_KEY = "PLATFORM_PROD_REPORTER_TOKEN"


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


def maintainer_rule_alerts() -> list[tuple[str, str]]:
    """Alerts whose only job is maintainer liveness. They must not page."""
    out = []
    for d in yaml.safe_load_all(MAINTAINER_RULES.read_text()):
        if d and d.get("kind") == "PrometheusRule":
            for g in d["spec"]["groups"]:
                for r in g.get("rules") or []:
                    if "alert" in r:
                        out.append((r["alert"], (r.get("labels") or {}).get("severity", "")))
    return out


def assert_maintainer_rules_unpaged(route: dict, outside_names: set[str], receivers: dict, problems: list[str]) -> None:
    """bifrost-maintainer-rules.yaml is an audit trail. A name that matches the
    backup pager, or a route that reaches a receiver outside the cluster, fails."""
    rel = MAINTAINER_RULES.relative_to(ROOT)
    alerts = maintainer_rule_alerts()
    if not alerts:
        problems.append(f"{rel}: no alerts found")
        return
    for name, sev in alerts:
        if PAGED.fullmatch(name):
            problems.append(f"{rel}: {name} matches the paging alertname route")
        got = [n for n in route_to(route, {"alertname": name, "severity": sev or "warning"}) if n]
        hit = [n for n in got if n in outside_names and n in receivers]
        if hit:
            problems.append(f"{rel}: {name} reaches a paging receiver {hit}")


def drill_stale(age_seconds: float | None) -> bool:
    """BifrostPostgresRecoveryDrillStale: the ConfigMap is missing, or older than 100 days."""
    if age_seconds is None:
        return True
    return age_seconds > DRILL_STALE_SECONDS


def drill_stale_rule() -> dict:
    docs = [
        doc for doc in yaml.safe_load_all(DRILL_RULES.read_text())
        if doc and doc.get("kind") == "PrometheusRule"
    ]
    if len(docs) != 1:
        raise ValueError(f"{DRILL_RULES.name}: expected one PrometheusRule")
    rules = []
    for group in docs[0]["spec"]["groups"]:
        for rule in group.get("rules") or []:
            if "alert" in rule:
                rules.append(rule)
    if len(rules) != 1:
        raise ValueError(f"{DRILL_RULES.name}: expected one alert, found {len(rules)}")
    return rules[0]


def assert_drill_stale_unpaged(route: dict, outside_names: set[str], receivers: dict, problems: list[str]) -> None:
    """The quarterly drill alert is an audit record. It must not page."""
    rel = DRILL_RULES.relative_to(ROOT)
    try:
        rule = drill_stale_rule()
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        problems.append(f"{rel}: {exc}")
        return
    name = rule.get("alert") or ""
    sev = (rule.get("labels") or {}).get("severity", "")
    expr = rule.get("expr") or ""
    if name != DRILL_STALE_ALERT:
        problems.append(f"{rel}: alert is {name or 'missing'}, want {DRILL_STALE_ALERT}")
    if sev != "warning":
        problems.append(f"{rel}: {name} severity is {sev or 'missing'}, want warning (audit, not a page)")
    if str(DRILL_STALE_SECONDS) not in expr:
        problems.append(f"{rel}: expr is not the {DRILL_STALE_SECONDS}-second (100-day) threshold")
    if "absent(" not in expr or DRILL_CM not in expr or ">" not in expr:
        problems.append(f"{rel}: expr must age {DRILL_CM} with '>' and alert when it is absent")
    if PAGED.fullmatch(name):
        problems.append(f"{rel}: {name} matches the paging alertname route")
    got = [n for n in route_to(route, {"alertname": name or DRILL_STALE_ALERT, "severity": sev or "warning"}) if n]
    hit = [n for n in got if n in outside_names and n in receivers]
    if hit:
        problems.append(f"{rel}: {name} reaches a paging receiver {hit}")


def kubectl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["kubectl", *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)


def webhook_urls(receiver: dict) -> list[str]:
    return [w.get("url") or "" for w in receiver.get("webhook_configs") or []]


def assert_webhook_targets(cfg: dict, problems: list[str], where: str) -> None:
    """No receiver URL may name STG; the default receiver must be the PROD audit webhook."""
    receivers = {r["name"]: r for r in cfg.get("receivers") or []}
    for name, rec in receivers.items():
        for url in webhook_urls(rec):
            if url == "<secret>":
                problems.append(f"{where}: receiver {name} URL is masked; cannot verify the target")
            if STG_MARK in url:
                problems.append(f"{where}: receiver {name} URL contains {STG_MARK}")
    default = (cfg.get("route") or {}).get("receiver")
    urls = webhook_urls(receivers.get(default) or {})
    ok = False
    hosts: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        hosts.append(parsed.hostname or url)
        if parsed.hostname == PROD_HOST and (parsed.port or 80) == 8780 and parsed.path == PROD_PATH:
            ok = True
    if not ok:
        problems.append(
            f"{where}: default receiver {default!r} is not {PROD_HOST}:8780{PROD_PATH} (hosts={hosts})"
        )


def policy_allows_prod(pol: dict) -> bool:
    for rule in (pol.get("spec") or {}).get("egress") or []:
        ports = {p.get("port") for p in rule.get("ports") or []}
        proto_ok = all(p.get("protocol", "TCP") == "TCP" for p in rule.get("ports") or [])
        if 8780 not in ports or not proto_ok:
            continue
        for peer in rule.get("to") or []:
            ns = ((peer.get("namespaceSelector") or {}).get("matchLabels") or {}).get(
                "kubernetes.io/metadata.name")
            app = ((peer.get("podSelector") or {}).get("matchLabels") or {}).get(
                "app.kubernetes.io/name")
            if ns == PROD_NS and app == "platform-api":
                return True
    return False


def assert_token_source(problems: list[str]) -> None:
    """The webhook bearer written for the next apply must be the PROD reporter token.
    The route accepts reporter or above and only writes diagnostics and audit, so
    Alertmanager must not hold PLATFORM_PROD_OPERATOR_TOKEN."""
    text = TOKEN_SCRIPT.read_text()
    rel = TOKEN_SCRIPT.relative_to(ROOT)
    if WEBHOOK_TOKEN_FN not in text or WEBHOOK_REPORTER_KEY not in text:
        problems.append(f"{rel}: webhook secret is not filled from {WEBHOOK_REPORTER_KEY}")
    if 'printf \'token=%s\\n\' "$(webhook_token)"' not in text:
        problems.append(f"{rel}: webhook secret is not written by webhook_token")
    for stale, label in (
        ('printf \'token=%s\\n\' "$(env_value PLATFORM_PROD_OPERATOR_TOKEN)"', "PLATFORM_PROD_OPERATOR_TOKEN"),
        ('printf \'token=%s\\n\' "$(env_value PLATFORM_STG_OPERATOR_TOKEN)"', "PLATFORM_STG_OPERATOR_TOKEN"),
    ):
        if stale in text:
            problems.append(f"{rel}: webhook secret is still filled from {label}")


def secret_sha256(namespace: str, name: str, key: str) -> str | None:
    r = kubectl("-n", namespace, "get", "secret", name, "-o", "json")
    if r.returncode != 0:
        return None
    try:
        encoded = json.loads(r.stdout)["data"][key]
    except (KeyError, TypeError, json.JSONDecodeError):
        return None
    return hashlib.sha256(base64.b64decode(encoded)).hexdigest()


def assert_live_bearer(problems: list[str]) -> None:
    """Compare digests only. Never print either secret."""
    webhook = secret_sha256("monitoring", "alertmanager-webhook-auth", "token")
    prod = secret_sha256(
        "bifrost-platform-prod", "bifrost-platform-reporter-token", "PLATFORM_PROD_REPORTER_TOKEN")
    if not webhook or not prod:
        problems.append("live: cannot read the webhook bearer or the PROD reporter token")
        return
    if webhook != prod:
        problems.append(
            "live: alertmanager-webhook-auth is not the PROD reporter token; "
            "the audit webhook would 401 once the route is reporter-or-above"
        )


def assert_egress_policy(pol: dict, raw: str, problems: list[str], where: str) -> None:
    if STG_MARK in raw:
        problems.append(f"{where}: egress policy still names {STG_MARK}")
    if not policy_allows_prod(pol):
        problems.append(
            f"{where}: egress policy does not allow {PROD_NS} platform-api TCP 8780"
        )


def load_config(live: bool) -> tuple[dict, str]:
    """Return (alertmanager config, raw text that was parsed). Live raw is the Secret
    document; it is never printed."""
    if not live:
        raw = VALUES.read_text()
        return yaml.safe_load(raw)["alertmanager"]["config"], raw
    r = kubectl("-n", "monitoring", "get", "secret", AM_SECRET, "-o", "json")
    if r.returncode != 0:
        print(f"kubectl: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    try:
        encoded = json.loads(r.stdout)["data"]["alertmanager.yaml"]
        raw = base64.b64decode(encoded).decode()
        cfg = yaml.safe_load(raw)
    except (KeyError, ValueError, TypeError) as e:
        print(f"alertmanager config secret: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(cfg, dict) or "route" not in cfg:
        print("alertmanager config secret: no route", file=sys.stderr)
        sys.exit(1)
    return cfg, raw


def load_policy(live: bool) -> tuple[dict, str]:
    if not live:
        raw = EGRESS.read_text()
        return yaml.safe_load(raw), raw
    r = kubectl("-n", "monitoring", "get", "networkpolicy", EGRESS_NAME, "-o", "yaml")
    if r.returncode != 0:
        print(f"kubectl: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(r.stdout), r.stdout


def self_test() -> None:
    """The new assertions must pass a PROD default and fail a STG URL."""
    prod_url = f"http://{PROD_HOST}:8780{PROD_PATH}"
    good = {
        "route": {
            "receiver": WEBHOOK,
            "routes": [
                {"receiver": "owner-ntfy", "matchers": [
                    'alertname=~"Bifrost(PostgresBackup.*|PostgresWalArchiveStalled|LogicalBackup.*|MinIONas.*|ClusterStateBackup.*)"'
                ], "continue": True},
                {"receiver": WEBHOOK},
            ],
        },
        "receivers": [
            {"name": WEBHOOK, "webhook_configs": [{"url": prod_url}]},
            {"name": "owner-ntfy", "webhook_configs": [
                {"url": "http://192.168.10.50:8783/api/v1/alerts/alertmanager"}]},
        ],
    }
    good_problems: list[str] = []
    assert_webhook_targets(good, good_problems, "self-test")
    if good_problems:
        raise SystemExit("self-test: PROD config was rejected: " + "; ".join(good_problems))
    reached = route_to(good["route"], {"alertname": "BifrostClusterStateBackupFailed", "severity": "warning"})
    if "owner-ntfy" not in reached or WEBHOOK not in reached:
        raise SystemExit(f"self-test: cluster-state backup route reached {reached}")
    if not PAGED.fullmatch("BifrostPostgresBackupFailed"):
        raise SystemExit("self-test: backup pager no longer matches BifrostPostgresBackup*")
    if PAGED.fullmatch("BifrostMaintainerBackupSweepStale"):
        raise SystemExit("self-test: maintainer liveness name matches the pager")
    maintainer_reached = route_to(good["route"], {"alertname": "BifrostMaintainerBackupSweepStale", "severity": "warning"})
    if "owner-ntfy" in maintainer_reached:
        raise SystemExit(f"self-test: maintainer liveness reached {maintainer_reached}")
    if DRILL_STALE_SECONDS != 8_640_000:
        raise SystemExit("self-test: 100 days is not 8640000 seconds")
    if not drill_stale(None) or not drill_stale(DRILL_STALE_SECONDS + 1):
        raise SystemExit("self-test: 100-day predicate did not fire for absent or stale")
    if drill_stale(0) or drill_stale(DRILL_STALE_SECONDS):
        raise SystemExit("self-test: 100-day predicate fired at or under 100 days")
    try:
        drill_rule = drill_stale_rule()
    except (OSError, ValueError, KeyError, yaml.YAMLError) as exc:
        raise SystemExit(f"self-test: drill rule: {exc}") from exc
    drill_expr = drill_rule.get("expr") or ""
    if str(DRILL_STALE_SECONDS) not in drill_expr or "absent(" not in drill_expr or DRILL_CM not in drill_expr:
        raise SystemExit("self-test: drill rule expr is not the 100-day or-absent form")
    if (drill_rule.get("labels") or {}).get("severity") != "warning":
        raise SystemExit("self-test: drill rule is not severity warning")
    if drill_rule.get("alert") != DRILL_STALE_ALERT:
        raise SystemExit("self-test: drill rule was renamed")
    if PAGED.fullmatch(DRILL_STALE_ALERT):
        raise SystemExit("self-test: recovery drill stale matches the pager")
    drill_reached = route_to(good["route"], {"alertname": DRILL_STALE_ALERT, "severity": "warning"})
    if "owner-ntfy" in drill_reached:
        raise SystemExit(f"self-test: recovery drill stale reached {drill_reached}")
    bad_problems: list[str] = []
    assert_webhook_targets({
        "route": {"receiver": WEBHOOK},
        "receivers": [{"name": WEBHOOK, "webhook_configs": [{
            "url": "http://platform-api.bifrost-platform-stg.svc.cluster.local:8780/api/v1/ops-agent/alertmanager"}]}],
    }, bad_problems, "self-test")
    if not any(STG_MARK in p for p in bad_problems) or not any(PROD_HOST in p for p in bad_problems):
        raise SystemExit(f"self-test: STG URL was not rejected ({bad_problems})")
    masked: list[str] = []
    assert_webhook_targets({
        "route": {"receiver": WEBHOOK},
        "receivers": [{"name": WEBHOOK, "webhook_configs": [{"url": "<secret>"}]}],
    }, masked, "self-test")
    if not any("masked" in p for p in masked):
        raise SystemExit("self-test: masked URL was not rejected")


def main() -> int:
    self_test()
    live = "--live" in sys.argv[1:]
    cfg, raw_cfg = load_config(live)
    receivers = {r["name"]: r for r in cfg.get("receivers") or []}
    outside_names = {n for n, r in receivers.items() if outside(r)}
    route = cfg["route"]
    problems: list[str] = []
    where = "live Alertmanager" if live else VALUES.name

    if STG_MARK in raw_cfg:
        problems.append(f"{where}: config still contains {STG_MARK}")
    assert_webhook_targets(cfg, problems, where)
    assert_token_source(problems)
    if live:
        assert_live_bearer(problems)

    def reach(labels):
        return [x for x in route_to(route, labels) if x]

    def paged(names):
        return [n for n in names if n in outside_names and n in receivers]

    hb = reach({"alertname": "Watchdog", "severity": "none"})
    if not paged(hb):
        problems.append(f"Watchdog reaches {hb}: no receiver outside the cluster (dead-man's switch)")

    assert_maintainer_rules_unpaged(route, outside_names, receivers, problems)
    assert_drill_stale_unpaged(route, outside_names, receivers, problems)

    cases = [("AnyCritical", "critical")] + [(a, s) for a, s in rule_alerts() if PAGED.fullmatch(a)]
    seen = {a for a, _ in cases}
    for name, sev in SYNTHETIC_PAGED:
        if name not in seen:
            cases.append((name, sev))
    for name, sev in cases:
        got = reach({"alertname": name, "severity": sev, "namespace": "data"})
        if not paged(got):
            problems.append(f"{name} (severity={sev}) reaches {got}: nobody is paged")
        if WEBHOOK not in got:
            problems.append(f"{name} (severity={sev}) no longer reaches {WEBHOOK}")

    pol, raw_pol = load_policy(live)
    pol_where = f"live {EGRESS_NAME}" if live else str(EGRESS.relative_to(ROOT))
    assert_egress_policy(pol, raw_pol, problems, pol_where)
    if not live:
        for n, r in receivers.items():
            for u in outside(r):
                if not egress_allows(u):
                    problems.append(f"receiver {n}: {u} has no egress rule in {EGRESS.relative_to(ROOT)}")

    if problems:
        print(f"FAIL ({where}):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"ok ({where}): Watchdog and {len(cases)} paged alert kinds reach a receiver outside the cluster; "
          f"default receiver is {PROD_HOST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
