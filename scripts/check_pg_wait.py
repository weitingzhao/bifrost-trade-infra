#!/usr/bin/env python3
"""Every Job / CronJob that talks to Postgres waits for it first (debt TD-210).

A new pod reaches the CNPG pods only after the k3s policy controller has
programmed the NetworkPolicy for its IP, a few seconds after the pod starts.
A Job that connects in its first second gets "Connection refused". On
2026-10-06 that failed the nightly logical backup on 6 of 7 targets, on both
attempts, while the last target dumped fine 2 s later.

A Job or CronJob is a Postgres client here when its pod template
  - sets PGHOST in any container env, or names bifrost-postgres-rw in an env value, or
  - carries labels that a NetworkPolicy selecting the CNPG pods
    (spec.podSelector on cnpg.io/cluster) admits through an ingress podSelector.
Such a pod must have an initContainer named ``wait-pg``, or the Job / CronJob
must declare its own retry with the annotation ``bifrost.io/pg-wait: <reason>``.

Usage: python3 scripts/check_pg_wait.py [DIR ...]   (default: k8s/; exit 1 on any problem)
       python3 scripts/check_pg_wait.py --self-test
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CNPG_LABEL = "cnpg.io/cluster"
INIT_NAME = "wait-pg"
DECLARED_RETRY = "bifrost.io/pg-wait"
PG_HOST_MARKERS = ("bifrost-postgres-rw",)


def load_docs(paths: list[Path]) -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    for base in paths:
        files = [base] if base.is_file() else sorted(
            p for p in base.rglob("*") if p.suffix in (".yaml", ".yml")
        )
        for f in files:
            try:
                docs = list(yaml.safe_load_all(f.read_text()))
            except yaml.YAMLError:
                continue  # not a manifest this check can read (templates, values files)
            out.extend((f, d) for d in docs if isinstance(d, dict))
    return out


def pod_template(doc: dict) -> tuple[dict, dict] | None:
    """Return (pod metadata, pod spec) of a Job or CronJob, else None."""
    kind = doc.get("kind")
    spec = doc.get("spec") or {}
    if kind == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec")) or {}
    elif kind != "Job":
        return None
    tpl = spec.get("template") or {}
    pod = tpl.get("spec") or {}
    if not pod.get("containers"):
        return None  # a patch without containers; the base it patches is checked
    return tpl.get("metadata") or {}, pod


def postgres_sources(docs: list[tuple[Path, dict]]) -> list[dict]:
    """matchLabels of every ingress podSelector into the CNPG pods."""
    sources: list[dict] = []
    for _, d in docs:
        if d.get("kind") != "NetworkPolicy":
            continue
        spec = d.get("spec") or {}
        if CNPG_LABEL not in ((spec.get("podSelector") or {}).get("matchLabels") or {}):
            continue
        for rule in spec.get("ingress") or []:
            for peer in rule.get("from") or []:
                labels = (peer.get("podSelector") or {}).get("matchLabels")
                if labels and CNPG_LABEL not in labels:
                    sources.append(labels)
    return sources


def is_pg_client(meta: dict, pod: dict, sources: list[dict]) -> str | None:
    for c in pod.get("containers") or []:
        for e in c.get("env") or []:
            if e.get("name") == "PGHOST":
                return f"container {c.get('name')} sets PGHOST"
            if any(m in str(e.get("value", "")) for m in PG_HOST_MARKERS):
                return f"container {c.get('name')} env {e.get('name')} names the Postgres service"
    labels = meta.get("labels") or {}
    for src in sources:
        if all(labels.get(k) == v for k, v in src.items()):
            return f"labels {src} are admitted by a Postgres ingress NetworkPolicy"
    return None


def check(paths: list[Path]) -> list[str]:
    docs = load_docs(paths)
    sources = postgres_sources(docs)
    problems: list[str] = []
    for f, d in docs:
        got = pod_template(d)
        if got is None:
            continue
        meta, pod = got
        why = is_pg_client(meta, pod, sources)
        if why is None:
            continue
        if any(c.get("name") == INIT_NAME for c in pod.get("initContainers") or []):
            continue
        if ((d.get("metadata") or {}).get("annotations") or {}).get(DECLARED_RETRY):
            continue
        name = (d.get("metadata") or {}).get("name")
        try:
            where = f.relative_to(ROOT)
        except ValueError:
            where = f
        problems.append(
            f"{where}: {d['kind']}/{name} is a Postgres client ({why}) but has no "
            f"initContainer '{INIT_NAME}' and no '{DECLARED_RETRY}' annotation"
        )
    return problems


SELF_TEST = """
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: {name: np}
spec:
  podSelector: {matchLabels: {cnpg.io/cluster: bifrost-postgres}}
  ingress:
    - from:
        - podSelector: {matchLabels: {app.kubernetes.io/name: dumper}}
---
apiVersion: batch/v1
kind: CronJob
metadata: {name: bad-label}
spec:
  jobTemplate:
    spec:
      template:
        metadata: {labels: {app.kubernetes.io/name: dumper}}
        spec: {containers: [{name: c, image: x}]}
---
apiVersion: batch/v1
kind: Job
metadata: {name: bad-env}
spec:
  template:
    spec: {containers: [{name: c, image: x, env: [{name: PGHOST, value: h}]}]}
---
apiVersion: batch/v1
kind: Job
metadata: {name: good-init}
spec:
  template:
    spec:
      initContainers: [{name: wait-pg, image: x}]
      containers: [{name: c, image: x, env: [{name: PGHOST, value: h}]}]
---
apiVersion: batch/v1
kind: Job
metadata: {name: good-declared, annotations: {bifrost.io/pg-wait: "client retries 60 s"}}
spec:
  template:
    spec: {containers: [{name: c, image: x, env: [{name: DB, value: bifrost-postgres-rw.data}]}]}
---
apiVersion: batch/v1
kind: Job
metadata: {name: not-a-client}
spec:
  template:
    spec: {containers: [{name: c, image: x}]}
"""


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "m.yaml"
        p.write_text(SELF_TEST)
        got = sorted(line.split(": ", 1)[1].split(" ", 1)[0] for line in check([p]))
    want = ["CronJob/bad-label", "Job/bad-env"]
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
        print(f"{len(problems)} Postgres client Job(s) without a wait (TD-210)")
        return 1
    print("pg-wait: every Postgres client Job / CronJob waits for the server")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
