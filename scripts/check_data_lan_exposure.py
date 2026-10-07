#!/usr/bin/env python3
"""STG and PROD data-namespace pods are not reachable from the LAN (TD-205 ratchet).

Until 2026-10-07 redis-live-stg and redis-live-prod had LAN NodePorts (30380, 30382) and
NetworkPolicies admitting 192.168.10.0/24, 192.168.20.0/24 and the flannel.1 /32s that a
NodePort connection arrives from. Neither instance has a password, and PROD carries the
daemon's control stream, so any LAN device could stop the daemon. This check keeps them shut:

- no NodePort or LoadBalancer Service in ``data`` selects a pod whose name says stg or prod
  (``app.kubernetes.io/name`` containing ``-stg`` / ``-prod``), except the allowlist;
- no NetworkPolicy in ``data`` for such a pod admits an ``ipBlock`` (LAN ranges and the
  NodePort SNAT /32s are how the LAN got in), except the allowlist.

The allowlist names what is exposed on purpose and why.

Static (default): renders every kustomization under k8s/data.
Live (``--live``; needs KUBECONFIG, read-only): reads the Services and NetworkPolicies in
``data`` from the cluster, which is what matters for objects applied by hand.

Usage: python3 scripts/check_data_lan_exposure.py [--live]   (exit 1 on any problem)
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAMESPACE = "data"

# Exposed on purpose. Key: Service or NetworkPolicy name.
ALLOW = {
    # CNPG serves all four databases; every login role has a password (TD-85).
    "bifrost-postgres-lan": "Postgres LAN NodePort 30432, password-protected roles",
    "postgres-lan-ingress": "LAN ingress for the Postgres NodePort above",
}


def env_pod(name: str) -> bool:
    return "-stg" in name or "-prod" in name or name.endswith(("stg", "prod"))


def problems(objs: list[dict]) -> list[str]:
    out = []
    for o in objs:
        kind = o.get("kind")
        meta = o.get("metadata") or {}
        name = meta.get("name", "?")
        ns = meta.get("namespace") or NAMESPACE
        if ns != NAMESPACE or name in ALLOW:
            continue
        spec = o.get("spec") or {}
        if kind == "Service" and spec.get("type") in ("NodePort", "LoadBalancer"):
            target = (spec.get("selector") or {}).get("app.kubernetes.io/name", "")
            if env_pod(target):
                out.append(f"Service {name}: {spec.get('type')} selects {target} (stg/prod data pods stay off the LAN)")
        if kind == "NetworkPolicy":
            target = ((spec.get("podSelector") or {}).get("matchLabels") or {}).get("app.kubernetes.io/name", "")
            if not env_pod(target):
                continue
            for rule in spec.get("ingress") or []:
                for peer in rule.get("from") or []:
                    if "ipBlock" in peer:
                        out.append(f"NetworkPolicy {name}: {target} admits ipBlock {peer['ipBlock'].get('cidr')}")
    return out


def static_objects() -> list[dict]:
    objs: list[dict] = []
    for k in sorted((ROOT / "k8s" / "data").rglob("kustomization.yaml")):
        rendered = subprocess.run(["kubectl", "kustomize", str(k.parent)], capture_output=True, text=True)
        if rendered.returncode != 0:
            print(f"kustomize {k.parent.relative_to(ROOT)}: {rendered.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        objs += [d for d in yaml.safe_load_all(rendered.stdout) if d]
    # a parent kustomization renders its children again: keep one of each
    seen, unique = set(), []
    for o in objs:
        key = (o.get("kind"), (o.get("metadata") or {}).get("name"))
        if key not in seen:
            seen.add(key)
            unique.append(o)
    return unique


def live_objects() -> list[dict]:
    r = subprocess.run(["kubectl", "-n", NAMESPACE, "get", "svc,networkpolicy", "-o", "json"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        print(f"kubectl: {r.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return json.loads(r.stdout)["items"]


def main() -> int:
    live = "--live" in sys.argv[1:]
    found = problems(live_objects() if live else static_objects())
    where = "live data namespace" if live else "k8s/data manifests"
    if found:
        print(f"FAIL ({where}):")
        for p in found:
            print(f"  - {p}")
        return 1
    print(f"ok ({where}): no stg/prod data pod is reachable from the LAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
