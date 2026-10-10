#!/usr/bin/env python3
"""Prometheus and Alertmanager keep their data across an eviction (TD-289).

Static (default): scripts/k3s/values-kube-prometheus.yaml gives both a
volumeClaimTemplate with a storage class, and Prometheus a retentionSize below
its claim. Without storageSpec the operator uses an emptyDir, which a node drain
deletes (2026-10-10: 10 days of metric history).

--live: the running Prometheus and Alertmanager pods mount their data volume
from a PersistentVolumeClaim, and the claim is Bound.

Grafana is not checked: it has no persistence on purpose (dashboards from
ConfigMaps, anonymous viewers); the values file says so.

Usage: python3 scripts/check_monitoring_persistence.py [--live]
Reads only. Exit 1 on any problem.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
VALUES = ROOT / "scripts" / "k3s" / "values-kube-prometheus.yaml"
NAMESPACE = "monitoring"
# pod name -> the volume that holds its data
PODS = {
    "prometheus-kube-prometheus-stack-prometheus-0": "prometheus-kube-prometheus-stack-prometheus-db",
    "alertmanager-kube-prometheus-stack-alertmanager-0": "alertmanager-kube-prometheus-stack-alertmanager-db",
}
UNITS = {"KB": 1e3, "MB": 1e6, "GB": 1e9, "TB": 1e12, "Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40}


def size_bytes(text: object) -> float | None:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGT]B|[KMGT]i)\s*", str(text or ""))
    return float(m.group(1)) * UNITS[m.group(2)] if m else None


def claim_spec(holder: dict | None) -> dict:
    return (((holder or {}).get("volumeClaimTemplate") or {}).get("spec")) or {}


def static_problems(values: dict) -> list[str]:
    problems: list[str] = []
    prom = ((values.get("prometheus") or {}).get("prometheusSpec")) or {}
    alert = ((values.get("alertmanager") or {}).get("alertmanagerSpec")) or {}
    prom_claim = claim_spec(prom.get("storageSpec"))
    alert_claim = claim_spec(alert.get("storage"))
    if not prom_claim.get("storageClassName"):
        problems.append("prometheusSpec.storageSpec has no volumeClaimTemplate with a storageClassName (emptyDir: an eviction erases the history)")
    if not alert_claim.get("storageClassName"):
        problems.append("alertmanagerSpec.storage has no volumeClaimTemplate with a storageClassName (emptyDir: an eviction erases the silences)")
    if prom_claim.get("storageClassName"):
        claim = size_bytes(((prom_claim.get("resources") or {}).get("requests") or {}).get("storage"))
        cap = size_bytes(prom.get("retentionSize"))
        if cap is None:
            problems.append("prometheusSpec.retentionSize is not set (the claim size is not enforced on NFS; this is the cap)")
        elif claim is not None and cap >= claim:
            problems.append("prometheusSpec.retentionSize is not below the claim size")
    return problems


def live_pod_problems(pod: dict, data_volume: str, claims: dict[str, str]) -> list[str]:
    name = pod["metadata"]["name"]
    volume = next((v for v in pod["spec"].get("volumes") or [] if v.get("name") == data_volume), None)
    if volume is None:
        return [f"{name}: no volume named {data_volume}"]
    claim = (volume.get("persistentVolumeClaim") or {}).get("claimName")
    if not claim:
        kind = next((k for k in volume if k != "name"), "?")
        return [f"{name}: {data_volume} is {kind}, not a PersistentVolumeClaim"]
    phase = claims.get(claim)
    if phase != "Bound":
        return [f"{name}: claim {claim} is {phase or 'missing'}, not Bound"]
    return []


def kubectl_json(*args: str) -> dict:
    out = subprocess.run(["kubectl", "-n", NAMESPACE, *args, "-o", "json"], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def live_problems() -> list[str]:
    claims = {c["metadata"]["name"]: (c.get("status") or {}).get("phase", "") for c in kubectl_json("get", "pvc")["items"]}
    problems: list[str] = []
    for pod_name, data_volume in PODS.items():
        try:
            pod = kubectl_json("get", "pod", pod_name)
        except subprocess.CalledProcessError as exc:
            problems.append(f"{pod_name}: cannot read the pod ({exc.stderr.strip()[:120]})")
            continue
        problems += live_pod_problems(pod, data_volume, claims)
    return problems


def main() -> int:
    problems = static_problems(yaml.safe_load(VALUES.read_text()) or {})
    live = "--live" in sys.argv[1:]
    if live:
        problems += live_problems()
    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        return 1
    print("ok: Prometheus and Alertmanager values carry a volume claim" + (" and the running pods mount it" if live else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
