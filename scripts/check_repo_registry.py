#!/usr/bin/env python3
"""Hold the other lists of repositories to the registry (R0B, structural elasticity).

k8s/cicd/repositories.yaml is the one list of the organisation's repositories
(Foundation owns it). Four other places list repositories, each for its own
purpose; this compares each with the registry entry by entry:

  public: true          <-> agent-config/gitea-primary.txt
  public: true          <-> the read-primaries.py arguments in
                            k8s/cicd/github-sync/cronjob-reconcile.yaml (GitHub follows)
  ready: true           <-> the keys of LANDING_REPOS in k8s/cicd/tekton/pipeline-land.yaml
  tier is not retired   <-> the repository table of agent-config/AGENT_FACTS.md section 2

Origin: 2026-11-23, R0B (Foundation's design, the CI line writes the check).
It reports and passes: exit 0 whatever it finds. Making it fail the build is
adding a check to the judge (laws 29 and 33), the Owner's to decide; after a
week of reports Foundation takes the counts to him. --strict exits 1 on any
difference, for that day and for the tests.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "k8s/cicd/repositories.yaml"
PRIMARY = "agent-config/gitea-primary.txt"
RECONCILE = "k8s/cicd/github-sync/cronjob-reconcile.yaml"
LAND = "k8s/cicd/tekton/pipeline-land.yaml"
FACTS = "agent-config/AGENT_FACTS.md"


def registry(root):
    doc = yaml.safe_load((root / REGISTRY).read_text())
    rows = doc.get("repositories") or []
    names = [r["name"] for r in rows]
    if len(names) != len(set(names)):
        raise SystemExit(f"{REGISTRY}: a repository is listed twice")
    return rows


def primary(root):
    out = set()
    for line in (root / PRIMARY).read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.add(line)
    return out


def reconcile(root):
    """The repositories after read-primaries.py and its output directory."""
    doc = yaml.safe_load((root / RECONCILE).read_text())
    found = None

    def walk(node):
        nonlocal found
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            if any(isinstance(x, str) and x.endswith("read-primaries.py") for x in node):
                i = next(i for i, x in enumerate(node) if isinstance(x, str) and x.endswith("read-primaries.py"))
                found = set(node[i + 2:])
            for v in node:
                walk(v)

    walk(doc)
    if found is None:
        raise SystemExit(f"{RECONCILE}: no read-primaries.py command found")
    return found


def landing(root):
    text = (root / LAND).read_text()
    m = re.search(r"- name: LANDING_REPOS\n\s+value: \|\n((?:\s+.*\n)+?)\s+- name:", text)
    if not m:
        raise SystemExit(f"{LAND}: LANDING_REPOS not found")
    return set(json.loads(m.group(1)))


def facts(root):
    """The backticked repository names of the active table in section 2,
    leaving out a row marked archived."""
    text = (root / FACTS).read_text()
    m = re.search(r"^## 2\..*?\n(.*?)^## 3\.", text, re.S | re.M)
    if not m:
        raise SystemExit(f"{FACTS}: section 2 not found")
    out = set()
    for line in m.group(1).splitlines():
        cell = re.match(r"\|\s*`([a-z0-9-]+)`\s*\|", line)
        if cell and "已归档" not in line and "archived" not in line.lower():
            out.add(cell.group(1))
    return out


def active(row):
    """A repository in use: tier is not retired (the registry's fields since
    infra 30f731b6, aligned with the map line's reading); the first version's
    state: active is still read."""
    if "tier" in row:
        return row.get("tier") != "retired"
    return row.get("state") == "active"


def differences(root):
    rows = registry(root)
    want_active = {r["name"] for r in rows if active(r)}
    want_public = {r["name"] for r in rows if r.get("public") and active(r)}
    want_landing = {r["name"] for r in rows if (r.get("ready") or r.get("landing")) and active(r)}
    out = []
    for where, have, want, what in (
        (PRIMARY, primary(root), want_public, "public"),
        (RECONCILE, reconcile(root), want_public, "public"),
        (LAND + " LANDING_REPOS", landing(root), want_landing, "landing"),
        (FACTS + " section 2", facts(root), want_active, "active"),
    ):
        for name in sorted(want - have):
            out.append(f"{where}: lacks {name} (the registry says {what})")
        for name in sorted(have - want):
            out.append(f"{where}: lists {name}, which the registry does not mark {what}")
    return out


def self_test():
    """Positive control on a small fixture: consistent lists give no
    difference; one repository dropped from gitea-primary.txt gives exactly
    that one, and --strict then exits 1 while the report still exits 0."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel in (REGISTRY, PRIMARY, RECONCILE, LAND, FACTS):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / REGISTRY).write_text(yaml.safe_dump({"repositories": [
            {"name": "a", "tier": "foundation", "public": True, "ready": True},
            {"name": "b", "tier": "payload", "public": True, "ready": False},
            {"name": "c", "tier": "retired", "public": False, "ready": False},
        ]}))
        (root / PRIMARY).write_text("# comment\na\nb\n")
        (root / RECONCILE).write_text(yaml.safe_dump({"spec": {"containers": [
            {"command": ["python3", "/scripts/read-primaries.py", "/work/primaries", "a", "b"]}]}}))
        (root / LAND).write_text('            - name: LANDING_REPOS\n              value: |\n                {"a": {}}\n            - name: OTHER\n')
        (root / FACTS).write_text("## 2. list\n\n| Repo |\n|---|\n| `a` | x |\n| `b` | x |\n| `c` | **已归档** |\n\n## 3. next\n")
        if differences(root):
            raise SystemExit(f"self-test: consistent fixture reported {differences(root)}")
        (root / PRIMARY).write_text("a\n")
        got = differences(root)
        if got != [f"{PRIMARY}: lacks b (the registry says public)"]:
            raise SystemExit(f"self-test: one drop reported {got}")
        if main(["--root", str(root), "--strict"]) != 1 or main(["--root", str(root)]) != 0:
            raise SystemExit("self-test: --strict must exit 1 and the report 0")
    print("repo registry: self-test passed")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--strict", action="store_true", help="exit 1 on any difference")
    ap.add_argument("--self-test", action="store_true", help="run the positive control and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    diffs = differences(args.root)
    for d in diffs:
        print("repo registry: " + d)
    print(f"repo registry: {len(diffs)} difference(s)" + ("" if args.strict else " (reported, not failing: R0B)"))
    return 1 if (args.strict and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
