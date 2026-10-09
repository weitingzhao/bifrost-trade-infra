#!/usr/bin/env python3
"""Render every apply_manifest allow-listed path at origin/main and report refusals (TD-275).

The LANE-W33C allow-list was checked path by path but not kind by kind, so the
plugins' k8s/base (a Namespace and PodDisruptionBudgets) could never be planned.
This renders each (repo, prefix) in actuation-policy.yaml from the sibling
checkouts in the workspace and applies the same rules as apply-manifest-check.sh:

- a Namespace is fine (the check drops it when it already exists with the same
  labels; whether it exists is a live question this offline check does not ask)
- any other cluster-scoped object is refused
- a namespace outside apply.namespaces is refused
- a kind outside apply.resources (or apply.cicd_resources in the delivery
  namespace) is refused

Refusals listed in ON_PURPOSE are expected: those objects go through
owner_run_command. Anything else exits 1.

Usage: python3 scripts/check_apply_paths.py   (BIFROST_WORKSPACE overrides the workspace root)
Needs: git, kubectl (kustomize), PyYAML. Reads only; fetches nothing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

INFRA = Path(__file__).resolve().parent.parent
POLICY = INFRA / "k8s" / "cicd" / "tekton" / "apply-manifest" / "actuation-policy.yaml"
RBAC_KINDS = {"Role", "RoleBinding", "ClusterRole", "ClusterRoleBinding"}
# Files refused on purpose by path: (repo, path prefix) -> why.
PATH_ON_PURPOSE = {
    ("bifrost-platform-plugin", "k8s/external-names/"):
        "per-environment ExternalName aliases with no namespace field, applied once with -n; owner_run_command",
}


def on_purpose(kind: str, namespace: str, delivery_ns: str, cicd_kinds: set[str]) -> str | None:
    """Why this refusal is expected, or None."""
    if kind in RBAC_KINDS:
        return "RBAC goes through owner_run_command"
    if kind in ("PipelineRun", "TaskRun"):
        return "runs start through start_pipeline_run, not apply"
    if namespace == delivery_ns and kind not in cicd_kinds:
        return "the applier writes only Tekton definitions in the delivery namespace"
    return None


def render(repo_dir: Path, prefix: str) -> tuple[list[dict], str | None]:
    top = prefix.split("/", 1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        arc = subprocess.run(
            f"git -C '{repo_dir}' archive origin/main '{top}' | tar -x -C '{tmp}'",
            shell=True, capture_output=True, text=True,
        )
        target = Path(tmp) / prefix
        if arc.returncode != 0 or not target.exists():
            return [], "not on origin/main"
        docs: list[dict] = []
        if target.is_file():
            docs += [d for d in yaml.safe_load_all(target.read_text()) if d]
            return docs, None
        kdirs = sorted({p.parent for p in target.rglob("kustomization.yaml")})
        # A base another kustomization pulls in gets its namespace from that
        # overlay; it is applied through the overlay, so render only the tops.
        referenced: set[Path] = set()
        for kd in kdirs:
            spec = yaml.safe_load((kd / "kustomization.yaml").read_text()) or {}
            for ref in (spec.get("resources") or []) + (spec.get("bases") or []) + (spec.get("components") or []):
                if isinstance(ref, str) and "://" not in ref:
                    referenced.add((kd / ref).resolve())
        tops = [kd for kd in kdirs if kd.resolve() not in referenced]
        for kd in tops:
            out = subprocess.run(["kubectl", "kustomize", str(kd)], capture_output=True, text=True)
            if out.returncode != 0:
                return [], f"kustomize {kd.relative_to(tmp)} failed: {out.stderr.strip()[:200]}"
            docs += [d for d in yaml.safe_load_all(out.stdout) if d]
        for f in sorted(target.rglob("*.y*ml")):
            if f.name == "kustomization.yaml" or any(k == f.parent or k in f.parents for k in kdirs):
                continue
            try:
                found = [d for d in yaml.safe_load_all(f.read_text()) if d and isinstance(d, dict) and d.get("kind")]
            except yaml.YAMLError:
                continue
            for d in found:
                d["__src__"] = str(f.relative_to(tmp))
            docs += found
        return docs, None


def main() -> int:
    policy = yaml.safe_load(POLICY.read_text())
    apply = policy["apply"]
    delivery_ns = policy["delivery"]["namespace"]
    namespaces = set(apply["namespaces"])
    kinds = {r["kind"] for r in apply["resources"]}
    cicd_kinds = {r["kind"] for r in apply["cicd_resources"]}
    workspace = Path(os.environ.get("BIFROST_WORKSPACE", INFRA.parent))

    unexpected = 0
    for repo in apply["repos"]:
        repo_dir = workspace / repo["name"]
        for prefix in repo["prefixes"]:
            label = f"{repo['name']}:{prefix}"
            if not (repo_dir / ".git").exists():
                print(f"SKIP {label}: no checkout at {repo_dir}")
                continue
            docs, err = render(repo_dir, prefix)
            if err:
                print(f"FAIL {label}: {err}")
                unexpected += 1
                continue
            expected: dict[str, int] = {}
            for d in docs:
                kind = d.get("kind", "")
                ns = (d.get("metadata") or {}).get("namespace") or ""
                name = (d.get("metadata") or {}).get("name", "")
                if kind == "Namespace" and not ns:
                    continue
                if not ns:
                    reason = "cluster-scoped"
                elif ns not in namespaces:
                    reason = f"namespace {ns} not allowed"
                elif kind not in (cicd_kinds if ns == delivery_ns else kinds):
                    reason = f"kind not allowed in {ns}"
                else:
                    continue
                why = on_purpose(kind, ns, delivery_ns, cicd_kinds)
                src = d.get("__src__", "")
                for (prepo, pprefix), pwhy in PATH_ON_PURPOSE.items():
                    if repo["name"] == prepo and src.startswith(pprefix):
                        why = pwhy
                if why:
                    expected[f"{kind} ({why})"] = expected.get(f"{kind} ({why})", 0) + 1
                    continue
                print(f"FAIL {label}: {kind}/{name} in {ns or '<cluster>'}: {reason}")
                unexpected += 1
            note = "; ".join(f"{k} x{v}" for k, v in sorted(expected.items()))
            print(f"ok   {label}: {len(docs)} objects" + (f"; refused on purpose: {note}" if note else ""))
    if unexpected:
        print(f"{unexpected} unexpected refusal(s)", file=sys.stderr)
        return 1
    print("check-apply-paths: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
