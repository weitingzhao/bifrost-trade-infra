#!/usr/bin/env python3
"""Check the Trade gateway prefix map in the rendered overlays (TD-55, Owner option B).

One gateway prefix per API process. B1 adds ``/api/account`` (api-account's own prefix) next
to the alias prefixes, which keep answering until B2 removes them after 7 days of zero
traffic. For every env (dev, stg, prod) this renders ``kubectl kustomize k8s/overlays/<env>``
and checks, in both Trade IngressRoutes (hostname ``trade-gateway`` and NodePort
``trade-gateway-ip``) and for every Host rule of them:

- each prefix in PREFIXES has a route, to the Service and port listed there;
- that route strips exactly its own prefix (the stripPrefix Middleware it names);
- the Service selects the process listed there (alias Services select the real process).

So a prefix that would fall through to the SPA (200 HTML) or land on the wrong process
fails here, before a deliver. After B2 the alias rows move to RETIRED and the check
asserts they are gone.

Usage: python3 scripts/check_trade_gateway_routes.py   (exit 1 on any problem)
       python3 scripts/check_trade_gateway_routes.py --promql [WINDOW]   (default 7d)

``--promql`` prints the PromQL for B2: requests on the alias prefixes' routes in the last WINDOW.
Traefik has no per-router metric here, only ``traefik_service_requests_total`` per route
service, named ``<namespace>-<ingressroute>-<sha256(match)[:20]>@kubernetescrd``; the script
renders the overlays and hashes every alias route's match, so the list cannot go stale. A
series only exists after its first request, and ``increase()`` does not count the sample that
creates a series, so the query also keeps every series that exists now but did not exist
WINDOW ago. An empty result means zero traffic on every alias route.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENVS = ("dev", "stg", "prod")
GATEWAYS = ("trade-gateway", "trade-gateway-ip")

# prefix -> (Service, port, process the Service selects, role)
PREFIXES: dict[str, tuple[str, int, str, str]] = {
    "/api/monitor": ("api-monitor", 8765, "api-monitor", "process"),
    "/api/account": ("api-account", 8769, "api-account", "process"),
    "/api/market": ("api-market", 8772, "api-market", "process"),
    "/api/research": ("api-research", 8773, "api-research", "process"),
    # Aliases until B2 (Owner 2026-10-04): removed after 7 days of zero traffic.
    "/api/trading": ("api-trading", 8769, "api-account", "alias"),
    "/api/strategy": ("api-strategy", 8769, "api-account", "alias"),
    "/api/portfolio": ("api-portfolio", 8769, "api-account", "alias"),
    "/api/ops": ("api-ops", 8765, "api-monitor", "alias"),
    "/api/docs": ("api-docs", 8765, "api-monitor", "alias"),
}
# Prefixes that must have no route (B2 moves the alias rows here).
RETIRED: tuple[str, ...] = ()

_PREFIX_IN_MATCH = re.compile(r"(?:PathPrefix|Path)\(`(/api/[a-z-]+)[/`]")
_HOST_IN_MATCH = re.compile(r"Host\(`([^`]+)`\)")


def render(env: str) -> list[dict]:
    overlay = ROOT / "k8s" / "overlays" / env
    if shutil.which("kubectl"):
        cmd = ["kubectl", "kustomize", str(overlay)]
    elif shutil.which("kustomize"):
        cmd = ["kustomize", "build", str(overlay)]
    else:
        sys.exit("needs kubectl or kustomize on PATH")
    out = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=True).stdout
    return [d for d in yaml.safe_load_all(out) if d]


def check_env(env: str) -> list[str]:
    docs = render(env)
    by_kind: dict[str, dict[str, dict]] = {}
    for d in docs:
        by_kind.setdefault(d["kind"], {})[d["metadata"]["name"]] = d
    problems: list[str] = []
    services = by_kind.get("Service", {})
    middlewares = by_kind.get("Middleware", {})
    for gw in GATEWAYS:
        ir = by_kind.get("IngressRoute", {}).get(gw)
        if ir is None:
            problems.append(f"{env}: IngressRoute {gw} missing")
            continue
        # (host or "*", prefix) -> route
        seen: dict[tuple[str, str], dict] = {}
        hosts: set[str] = set()
        for route in ir["spec"]["routes"]:
            m = _PREFIX_IN_MATCH.search(route["match"])
            host_m = _HOST_IN_MATCH.search(route["match"])
            host = host_m.group(1) if host_m else "*"
            hosts.add(host)
            if m and m.group(1) in PREFIXES or m and m.group(1) in RETIRED:
                seen[(host, m.group(1))] = route
        for host in sorted(hosts):
            for prefix, (svc, port, process, role) in PREFIXES.items():
                where = f"{env}/{gw} host={host} {prefix}"
                route = seen.get((host, prefix))
                if route is None:
                    problems.append(f"{where}: no route ({role})")
                    continue
                backends = route.get("services") or []
                if [(b.get("name"), b.get("port")) for b in backends] != [(svc, port)]:
                    problems.append(f"{where}: routes to {backends}, want {svc}:{port}")
                strips = [
                    p
                    for mw in route.get("middlewares") or []
                    for p in ((middlewares.get(mw["name"]) or {}).get("spec", {}).get("stripPrefix") or {}).get(
                        "prefixes", []
                    )
                ]
                if strips != [prefix]:
                    problems.append(f"{where}: strips {strips}, want [{prefix!r}]")
                selector = ((services.get(svc) or {}).get("spec") or {}).get("selector") or {}
                if selector.get("app.kubernetes.io/name") != process:
                    problems.append(f"{where}: Service {svc} selects {selector}, want process {process}")
            for prefix in RETIRED:
                if (host, prefix) in seen:
                    problems.append(f"{env}/{gw} host={host} {prefix}: retired prefix still routed")
    return problems


def alias_route_services() -> list[tuple[str, str, str, str]]:
    """(traefik service name, env, gateway/host, prefix) of every alias route in every env."""
    out = []
    aliases = [p for p, row in PREFIXES.items() if row[3] == "alias"]
    for env in ENVS:
        for d in render(env):
            if d["kind"] != "IngressRoute" or d["metadata"]["name"] not in GATEWAYS:
                continue
            for route in d["spec"]["routes"]:
                m = _PREFIX_IN_MATCH.search(route["match"])
                if not m or m.group(1) not in aliases:
                    continue
                host_m = _HOST_IN_MATCH.search(route["match"])
                digest = hashlib.sha256(route["match"].encode()).hexdigest()[:20]
                name = f"{d['metadata']['namespace']}-{d['metadata']['name']}-{digest}@kubernetescrd"
                out.append((name, env, f"{d['metadata']['name']} {host_m.group(1) if host_m else '*'}", m.group(1)))
    return out


def promql(window: str) -> str:
    # One regex over namespace x gateway x hash. It matches exactly the alias routes: a hash is
    # sha256 of the full match, which carries the Host on the hostname gateway, so a hash from
    # one gateway or env never names a route of another.
    services = alias_route_services()
    hashes = sorted({n.rsplit("-", 1)[1].split("@")[0] for n, *_ in services})
    sel = (
        'traefik_service_requests_total{service=~"bifrost-(dev|stg|prod)-trade-gateway(-ip)?-('
        + "|".join(hashes)
        + ')@kubernetescrd"}'
    )
    return (
        f"sum by (service) (increase({sel}[{window}]) or ({sel} unless {sel} offset {window})) > 0"
    )


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--promql":
        window = sys.argv[2] if len(sys.argv) > 2 else "7d"
        for name, env, where, prefix in alias_route_services():
            print(f"# {name}  {env} {where} {prefix}")
        print(promql(window))
        return 0
    problems: list[str] = []
    for env in ENVS:
        found = check_env(env)
        problems += found
        print(f"{env}: {'ok' if not found else f'{len(found)} problem(s)'} ({len(PREFIXES)} prefixes)")
    for p in problems:
        print(f"  !! {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
