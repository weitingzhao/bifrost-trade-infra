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

It also reports a tier raised since the base commit (--base, default HEAD~1)
with the conditions Foundation set for that tier (R0D, 2026-11-23, shared
notes biz-align/r0d-promotion-conditions-2026-11-23.md): the one it can
judge from this repository is judged (a foundation repository is cloned by
a Tekton definition); the others are listed to check, not passed.

Origin: 2026-11-23, R0B (Foundation's design, the CI line writes the check).
It reports and passes: exit 0 whatever it finds. Making it fail the build is
adding a check to the judge (laws 29 and 33), the Owner's to decide; after a
week of reports Foundation takes the counts to him. --strict exits 1 on any
difference, for that day and for the tests.
"""
import argparse
import json
import re
import subprocess
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


RANK = {"retired": 0, "experiment": 1, "payload": 2, "shared": 3, "foundation": 4}
TEKTON = "k8s/cicd/tekton"
# What each tier asks of a repository raised to it (Foundation's R0D table);
# what this script cannot read from infra is named, to be checked.
CONDITIONS = {
    "payload": ["domain has an owner in the ownership table", "main's last ci-* Succeeded",
                "an STG deployment exists", "its trial period has not run out"],
    "shared": ["used by at least two other domains", "its public packages or events are registered",
               "released with a version that users pin", "no unexplained ci-* red in 7 days",
               "the Owner's card (a raise to shared)"],
    "foundation": ["the shared conditions", "the platform's release or approval path calls it",
                   "its rollback has been measured (law 91)", "the Owner's card (a raise to foundation)"],
}


def base_registry(root, base):
    """The registry's rows at base, or None when git cannot show it."""
    try:
        doc = subprocess.run(["git", "-C", str(root), "show", "%s:%s" % (base, REGISTRY)],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {r["name"]: r for r in (yaml.safe_load(doc) or {}).get("repositories") or []}


def tier_of(row):
    return row.get("tier", "experiment")


def cloned_by_tekton(root, name):
    """The Tekton definitions that name the repository, sorted."""
    return sorted(str(p.relative_to(root)) for p in (root / TEKTON).rglob("*.yaml")
                  if re.search(r"\b%s\b" % re.escape(name), p.read_text(errors="replace")))


def raises(root, before):
    """One report per repository whose tier went up since before (rows by name)."""
    out = []
    for row in registry(root):
        name, now = row["name"], tier_of(row)
        if name in before and "tier" not in before[name]:
            continue  # the first version had no tier: nothing to compare
        was = tier_of(before[name]) if name in before else "experiment"
        if RANK.get(now, 0) <= RANK.get(was, 0):
            continue
        lines = ["%s: tier raised %s -> %s (R0D conditions; reported, not failing)" % (name, was, now)]
        if now == "foundation":
            refs = cloned_by_tekton(root, name)
            lines.append("  judged: cloned by a Tekton definition: %s" % ("yes (%s)" % ", ".join(refs[:3]) if refs else "NO"))
        for cond in CONDITIONS.get(now, []):
            lines.append("  to check: " + cond)
        out.append("\n".join(lines))
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
        # A tier raised since the base is reported with its conditions; one kept is not.
        (root / TEKTON).mkdir(parents=True, exist_ok=True)
        (root / TEKTON / "p.yaml").write_text("repo: b\n")
        before = {r["name"]: r for r in yaml.safe_load((root / REGISTRY).read_text())["repositories"]}
        rows = yaml.safe_load((root / REGISTRY).read_text())
        rows["repositories"][1]["tier"] = "foundation"
        (root / REGISTRY).write_text(yaml.safe_dump(rows))
        got = raises(root, before)
        if len(got) != 1 or "b: tier raised payload -> foundation" not in got[0] or "yes (" not in got[0]:
            raise SystemExit(f"self-test: a raise reported {got}")
        if raises(root, {r["name"]: r for r in rows["repositories"]}):
            raise SystemExit("self-test: an unchanged tier was reported")
    print("repo registry: self-test passed")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--strict", action="store_true", help="exit 1 on any difference")
    ap.add_argument("--self-test", action="store_true", help="run the positive control and exit")
    ap.add_argument("--base", default="HEAD~1", help="the commit whose registry tier raises are measured from")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    diffs = differences(args.root)
    for d in diffs:
        print("repo registry: " + d)
    print(f"repo registry: {len(diffs)} difference(s)" + ("" if args.strict else " (reported, not failing: R0B)"))
    before = base_registry(args.root, args.base)
    if before is None:
        print(f"repo registry: no registry at {args.base}; tier raises not compared")
    else:
        for r in raises(args.root, before):
            print("repo registry: " + r)
    return 1 if (args.strict and diffs) else 0


if __name__ == "__main__":
    sys.exit(main())
