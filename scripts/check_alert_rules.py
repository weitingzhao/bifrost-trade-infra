#!/usr/bin/env python3
"""PrometheusRule unit tests with promtool (W-38).

Each k8s/monitoring/rule-tests/*.test.yaml is a promtool rule test. Its
rule_files name PrometheusRule files in k8s/monitoring; this script extracts
spec.groups from each into a plain rule file of the same name in a temporary
directory, copies the test next to it, and runs `promtool check rules` and
`promtool test rules` there. A rule file under test must also be listed in
k8s/monitoring/kustomization.yaml, so the rule that passes is the one applied.

promtool: $PROMTOOL, else `promtool` on PATH, else the Prometheus image through
docker ($PROMTOOL_IMAGE; the default is the version the cluster ran on
2026-10-10). Nothing is installed.

Usage: python3 scripts/check_alert_rules.py   (exit 1 on any problem)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MONITORING = ROOT / "k8s" / "monitoring"
TESTS = MONITORING / "rule-tests"
KUSTOMIZATION = MONITORING / "kustomization.yaml"
DEFAULT_IMAGE = "quay.io/prometheus/prometheus:v3.13.2-distroless"


def promtool_cmd(workdir: Path) -> list[str]:
    explicit = os.environ.get("PROMTOOL")
    if explicit:
        return [explicit]
    found = shutil.which("promtool")
    if found:
        return [found]
    if not shutil.which("docker"):
        raise SystemExit("promtool not found: set PROMTOOL, put promtool on PATH, or start docker")
    image = os.environ.get("PROMTOOL_IMAGE", DEFAULT_IMAGE)
    return ["docker", "run", "--rm", "-v", f"{workdir}:/w", "-w", "/w", "--entrypoint", "/bin/promtool", image]


def rule_groups(path: Path) -> dict:
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d and d.get("kind") == "PrometheusRule"]
    if len(docs) != 1:
        raise ValueError(f"{path.relative_to(ROOT)}: expected one PrometheusRule, found {len(docs)}")
    return {"groups": docs[0]["spec"]["groups"]}


def kustomize_resources() -> set[str]:
    doc = yaml.safe_load(KUSTOMIZATION.read_text()) or {}
    return {str(r) for r in doc.get("resources") or []}


def main() -> int:
    tests = sorted(TESTS.glob("*.test.yaml"))
    if not tests:
        print(f"FAIL: no rule tests in {TESTS.relative_to(ROOT)}")
        return 1
    problems: list[str] = []
    listed = kustomize_resources()
    with tempfile.TemporaryDirectory(prefix="alert-rules-") as tmp:
        work = Path(tmp)
        rule_names: set[str] = set()
        for test in tests:
            doc = yaml.safe_load(test.read_text()) or {}
            names = [str(n) for n in doc.get("rule_files") or []]
            if not names:
                problems.append(f"{test.relative_to(ROOT)}: no rule_files")
            for name in names:
                if "/" in name:
                    problems.append(f"{test.relative_to(ROOT)}: rule_files entry {name} must be a file name in k8s/monitoring")
                    continue
                src = MONITORING / name
                if not src.is_file():
                    problems.append(f"{test.relative_to(ROOT)}: {name} is not in k8s/monitoring")
                    continue
                if name not in listed:
                    problems.append(f"{KUSTOMIZATION.relative_to(ROOT)} does not list {name}; the tested rule would not be applied")
                try:
                    (work / name).write_text(yaml.safe_dump(rule_groups(src), sort_keys=False))
                except (ValueError, KeyError, yaml.YAMLError) as exc:
                    problems.append(str(exc))
                    continue
                rule_names.add(name)
            shutil.copy(test, work / test.name)
        if problems:
            for p in problems:
                print(f"FAIL: {p}")
            return 1
        cmd = promtool_cmd(work)
        for args in (["check", "rules", *sorted(rule_names)], ["test", "rules", *[t.name for t in tests]]):
            res = subprocess.run([*cmd, *args], cwd=work, capture_output=True, text=True)
            out = (res.stdout + res.stderr).strip()
            if res.returncode != 0:
                print(out)
                print(f"FAIL: promtool {' '.join(args[:2])} exited {res.returncode}")
                return 1
    print(f"ok: {len(rule_names)} rule file(s), {len(tests)} promtool test file(s) pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
