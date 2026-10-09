#!/usr/bin/env python3
"""The spine mounted by platform STG and PROD matches bifrost-platform's copy (TD-109).

Argo CD applies k8s/overlays/platform-{stg,prod} with prune and selfHeal, so the
ConfigMap cannot be generated only at deliver time: a file that is not in git is
reverted or pruned. The copies stay in git, sync_platform_k8s_config.sh refreshes
ops-context.yaml into both overlays, and this check fails when they drift.

Compares bytes, and prints the decisions[id → status] diff so a stale D10 is obvious.

Also checks trust-overrides.yaml (W-32 B2): platform-api reads it from
/app/config on every request, and a missing file silently drops every override
(a demotion such as L0 is lost). Both overlay copies must equal the platform
file and both configMapGenerators must list it.

Also checks running-images.yaml (W-33) the same way: the Releases page reads
which workloads to version from that file, and a missing ConfigMap entry makes
Research and plugin versions disappear.
`--self-test` checks the decision parser without the repos.

Usage:
  PLATFORM_ROOT=../bifrost-platform python3 scripts/check_ops_context_parity.py
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

INFRA = pathlib.Path(__file__).resolve().parent.parent
COPIES = (
    INFRA / "k8s" / "overlays" / "platform-stg" / "config" / "ops-context.yaml",
    INFRA / "k8s" / "overlays" / "platform-prod" / "config" / "ops-context.yaml",
)


TRUST_COPIES = (
    INFRA / "k8s" / "overlays" / "platform-stg" / "config" / "trust-overrides.yaml",
    INFRA / "k8s" / "overlays" / "platform-prod" / "config" / "trust-overrides.yaml",
)
OVERLAY_KUSTOMIZATIONS = (
    INFRA / "k8s" / "overlays" / "platform-stg" / "kustomization.yaml",
    INFRA / "k8s" / "overlays" / "platform-prod" / "kustomization.yaml",
)
RUNNING_COPIES = (
    INFRA / "k8s" / "overlays" / "platform-stg" / "config" / "running-images.yaml",
    INFRA / "k8s" / "overlays" / "platform-prod" / "config" / "running-images.yaml",
)


def check_trust_overrides(source: pathlib.Path) -> list[str]:
    """Overlay copies equal the platform file and every generator ships it."""
    if not source.is_file():
        return [f"missing source {source}"]
    problems: list[str] = []
    src_bytes = source.read_bytes()
    for copy in TRUST_COPIES:
        if not copy.is_file():
            problems.append(f"missing copy {copy.relative_to(INFRA)}")
        elif copy.read_bytes() != src_bytes:
            problems.append(f"{copy.relative_to(INFRA)} is not byte-identical to {source}")
    for kust in OVERLAY_KUSTOMIZATIONS:
        if "- config/trust-overrides.yaml" not in kust.read_text():
            problems.append(f"{kust.relative_to(INFRA)} configMapGenerator does not list config/trust-overrides.yaml")
    return problems


def check_running_images(source: pathlib.Path) -> list[str]:
    """Overlay copies equal the platform file and every generator ships it."""
    if not source.is_file():
        return [f"missing source {source}"]
    problems: list[str] = []
    src_bytes = source.read_bytes()
    for copy in RUNNING_COPIES:
        if not copy.is_file():
            problems.append(f"missing copy {copy.relative_to(INFRA)}")
        elif copy.read_bytes() != src_bytes:
            problems.append(f"{copy.relative_to(INFRA)} is not byte-identical to {source}")
    for kust in OVERLAY_KUSTOMIZATIONS:
        if "- config/running-images.yaml" not in kust.read_text():
            problems.append(f"{kust.relative_to(INFRA)} configMapGenerator does not list config/running-images.yaml")
    return problems


def decisions(text: str) -> dict[str, str]:
    """id → status inside the top-level decisions: block. Milestones are ignored."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^decisions:\s*$", line):
            start = i + 1
            break
    if start is None:
        return {}
    block: list[str] = []
    for line in lines[start:]:
        if line and not line[0].isspace() and not line.startswith("#"):
            break
        block.append(line)
    out: dict[str, str] = {}
    current: str | None = None
    for line in block:
        id_match = re.match(r"^\s*- id:\s*(\S+)\s*$", line)
        if id_match:
            current = id_match.group(1)
            out.setdefault(current, "")
            continue
        if current is None:
            continue
        status_match = re.match(r"^\s*status:\s*(\S+)\s*$", line)
        if status_match and out[current] == "":
            out[current] = status_match.group(1)
    return out


def decision_diff(source: dict[str, str], copy: dict[str, str]) -> list[str]:
    problems: list[str] = []
    for did in sorted(set(source) - set(copy)):
        problems.append(f"missing decision {did}")
    for did in sorted(set(copy) - set(source)):
        problems.append(f"extra decision {did}")
    for did in sorted(set(source) & set(copy)):
        if source[did] != copy[did]:
            problems.append(f"{did} status {copy[did]!r} != source {source[did]!r}")
    return problems


def check_files(source: pathlib.Path, copies: tuple[pathlib.Path, ...]) -> list[str]:
    problems: list[str] = []
    if not source.is_file():
        return [f"missing source {source}"]
    src_bytes = source.read_bytes()
    src_decisions = decisions(src_bytes.decode())
    if "D10" not in src_decisions:
        problems.append(f"{source} has no decisions[id=D10]")
    for copy in copies:
        if not copy.is_file():
            problems.append(f"missing copy {copy}")
            continue
        if copy.read_bytes() != src_bytes:
            problems.append(f"{copy.relative_to(INFRA)} is not byte-identical to {source}")
            problems.extend(
                f"{copy.relative_to(INFRA)}: {item}"
                for item in decision_diff(src_decisions, decisions(copy.read_text()))
            )
    return problems


def self_test() -> int:
    text = """
milestones:
  - id: not-a-decision
    status: OPEN
decisions:
  - id: D10
    status: BLOCKED
  - id: D11
    status: SIGNED
tracks:
  build: {}
"""
    got = decisions(text)
    if got != {"D10": "BLOCKED", "D11": "SIGNED"}:
        print(f"self-test: parser got {got}", file=sys.stderr)
        return 1
    if decision_diff(got, got):
        print("self-test: identical maps should diff clean", file=sys.stderr)
        return 1
    drifted = decision_diff(got, {"D10": "UNLOCKED", "D11": "SIGNED"})
    if not any("D10" in item for item in drifted):
        print(f"self-test: D10 drift not reported: {drifted}", file=sys.stderr)
        return 1
    missing = decision_diff(got, {"D11": "SIGNED"})
    if not any("missing decision D10" in item for item in missing):
        print(f"self-test: missing D10 not reported: {missing}", file=sys.stderr)
        return 1
    print("self-test ok")
    return 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    platform = pathlib.Path(os.environ.get("PLATFORM_ROOT", INFRA.parent / "bifrost-platform"))
    source = platform / "config" / "ops-context.yaml"
    problems = check_files(source, COPIES)
    problems += check_trust_overrides(platform / "config" / "trust-overrides.yaml")
    problems += check_running_images(platform / "config" / "running-images.yaml")
    if problems:
        print(f"ops-context parity failed against {source}:", file=sys.stderr)
        for item in problems:
            print(f"  {item}", file=sys.stderr)
        return 1
    ids = decisions(source.read_text())
    print(f"ok: {len(ids)} decisions match {source} (D10={ids.get('D10')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
