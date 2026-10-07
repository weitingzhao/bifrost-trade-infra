#!/usr/bin/env python3
"""A redis-server in a manifest says what it persists and where its memory stops (debt TD-238).

redis-live-{stg,prod} and redis-dev ran --appendonly yes with no volume, so AOF and RDB
went to the container's writable layer and were lost on any recreate while reading as
durable; and --maxmemory-policy noeviction with no --maxmemory never applied, so the
only memory bound was an OOMKill at the container limit.

For every container whose command / args run redis-server:
  1. Without a volumeMount at /data it is ephemeral and must say so: no
     `--appendonly yes`, and `--save ""` (redis 7 snapshots by default).
  2. It sets `--maxmemory` above 0 (noeviction is also redis' default policy), and
     below the container's memory limit when it has one.

Usage: python3 scripts/check_redis_config.py [DIR ...]   (default: k8s/; exit 1 on any problem)
       python3 scripts/check_redis_config.py --self-test
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = "/data"
REDIS_UNITS = {"": 1, "b": 1, "k": 1000, "kb": 1024, "m": 1000**2, "mb": 1024**2, "g": 1000**3, "gb": 1024**3}
K8S_UNITS = {"": 1, "k": 1000, "M": 1000**2, "G": 1000**3, "Ki": 1024, "Mi": 1024**2, "Gi": 1024**3}


def load_docs(paths: list[Path]) -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    for base in paths:
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.suffix in (".yaml", ".yml"))
        for f in files:
            try:
                docs = list(yaml.safe_load_all(f.read_text()))
            except yaml.YAMLError:
                continue
            out.extend((f, d) for d in docs if isinstance(d, dict))
    return out


def pod_spec(doc: dict) -> dict | None:
    kind = doc.get("kind")
    spec = doc.get("spec") or {}
    if kind == "Pod":
        return spec
    if kind == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec")) or {}
    elif kind not in ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job"):
        return None
    return (spec.get("template") or {}).get("spec")


def redis_flags(container: dict) -> dict[str, str] | None:
    argv = [str(a) for a in (container.get("command") or []) + (container.get("args") or [])]
    if not any(a == "redis-server" or a.endswith("/redis-server") for a in argv):
        return None
    flags: dict[str, str] = {}
    i = argv.index(next(a for a in argv if a == "redis-server" or a.endswith("/redis-server"))) + 1
    while i < len(argv):
        if argv[i].startswith("--"):
            value = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith("--") else ""
            flags[argv[i][2:].lower()] = value
            i += 2 if i + 1 < len(argv) and not argv[i + 1].startswith("--") else 1
        else:
            i += 1
    return flags


def parse_size(value: str, units: dict[str, int]) -> int | None:
    m = re.fullmatch(r"\s*(\d+)\s*([A-Za-z]*)\s*", value or "")
    if not m:
        return None
    unit = m.group(2) if units is K8S_UNITS else m.group(2).lower()
    return int(m.group(1)) * units[unit] if unit in units else None


def check(paths: list[Path]) -> list[str]:
    problems: list[str] = []
    for f, d in load_docs(paths):
        pod = pod_spec(d)
        if not pod:
            continue
        name = f"{d.get('kind')}/{(d.get('metadata') or {}).get('name')}"
        try:
            where = f.relative_to(ROOT)
        except ValueError:
            where = f
        for c in pod.get("containers") or []:
            flags = redis_flags(c)
            if flags is None:
                continue
            at = f"{where}: {name} container {c.get('name')}"
            persistent = any(m.get("mountPath", "").rstrip("/") == DATA_DIR for m in c.get("volumeMounts") or [])
            if not persistent:
                if flags.get("appendonly", "no").lower() == "yes":
                    problems.append(f"{at} runs --appendonly yes with no volumeMount at {DATA_DIR}")
                if flags.get("save") != "":
                    problems.append(f"{at} has no volumeMount at {DATA_DIR} but does not set --save \"\"")
            maxmemory = parse_size(flags.get("maxmemory", ""), REDIS_UNITS)
            if not maxmemory:
                policy = flags.get("maxmemory-policy", "noeviction")
                problems.append(f"{at} runs maxmemory-policy {policy} without a --maxmemory above 0")
                continue
            limit = parse_size(str(((c.get("resources") or {}).get("limits") or {}).get("memory", "")), K8S_UNITS)
            if limit and maxmemory >= limit:
                problems.append(f"{at} sets --maxmemory {flags['maxmemory']} at or above its memory limit")
    return problems


SELF_TEST = """
apiVersion: apps/v1
kind: Deployment
metadata: {name: good-ephemeral}
spec:
  template:
    spec:
      containers:
        - name: redis
          command: [redis-server, --appendonly, "no", --save, "", --maxmemory, 400mb, --maxmemory-policy, noeviction]
          resources: {limits: {memory: 512Mi}}
        - name: exporter
          args: [--web.listen-address=0.0.0.0:9121]
---
apiVersion: apps/v1
kind: StatefulSet
metadata: {name: good-persistent}
spec:
  template:
    spec:
      containers:
        - name: redis
          command: [redis-server]
          args: [--appendonly, "yes", --maxmemory, 1gb]
          volumeMounts: [{name: data, mountPath: /data}]
          resources: {limits: {memory: 2Gi}}
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: bad-aof}
spec:
  template:
    spec:
      containers:
        - name: redis
          command: [redis-server, --appendonly, "yes", --save, "", --maxmemory, 100mb]
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: bad-save}
spec:
  template:
    spec:
      containers:
        - name: redis
          command: [redis-server, --maxmemory, 100mb]
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: bad-nomax}
spec:
  template:
    spec:
      containers:
        - name: redis
          command: [redis-server, --save, "", --maxmemory-policy, noeviction]
---
apiVersion: apps/v1
kind: Deployment
metadata: {name: bad-overlimit}
spec:
  template:
    spec:
      containers:
        - name: redis
          command: [redis-server, --save, "", --maxmemory, 1gb]
          resources: {limits: {memory: 512Mi}}
"""


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "m.yaml"
        p.write_text(SELF_TEST)
        got = sorted(line.split(": ", 1)[1].split(" ", 1)[0] for line in check([p]))
    want = ["Deployment/bad-aof", "Deployment/bad-nomax", "Deployment/bad-overlimit", "Deployment/bad-save"]
    if got != want:
        print(f"self-test FAILED: flagged {got}, want {want}")
        return 1
    print("self-test ok")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--self-test"]:
        return self_test()
    paths = [Path(a).resolve() for a in argv] or [ROOT / "k8s"]
    problems = check(paths)
    for p in problems:
        print(p)
    if problems:
        print(f"{len(problems)} redis-server config problem(s) (TD-238)")
        return 1
    print("redis-config: every redis-server is ephemeral or has /data, and sets maxmemory below its limit")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
