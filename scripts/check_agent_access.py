#!/usr/bin/env python3
"""Static and live checks for the Mac Agent's read-only identity (LANE-W33D).

Static (default): render k8s/agent-access and refuse Secret reads, write verbs,
and exec / port-forward outside the allowed scope.

--live uses the current kubeconfig (default ~/.kube/bifrost-k3s.yaml) after the
Owner has swapped in the bifrost-agent file. It does not print credential values.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCESS = ROOT / "k8s" / "agent-access"
AGENT = "system:serviceaccount:bifrost-access:bifrost-agent"
PROM = "prometheus-kube-prometheus-stack-prometheus-0"
EXEC_NS = ("research", "plugin-market-data", "plugin-flex-query")
WRITE_VERBS = {"create", "update", "patch", "delete", "deletecollection", "*"}
READ_VERBS = {"get", "list", "watch"}
INFRA_KEYS = (
    "OPS_ADMIN_TOKEN",
    "REDIS_IB_PASSWORD",
    "BIFROST_PG_PASSWORD_PREVIOUS",
    "BIFROST_PG_PASSWORD_NEXT",
)
PLATFORM_KEYS = ("UNIFI_HOST", "UNIFI_USER", "UNIFI_PASS", "UNIFI_API_KEY")
# redis-ib users that can write ib:* (ib:operator:cmd, D10). REDIS_IB_PLATFORM_PASS stays.
PLUGIN_KEYS = ("REDIS_IB_GATEWAY_PASS", "REDIS_IB_TRADE_PROD_PASS")
NODES = (
    "192.168.10.73",
    "192.168.10.70",
    "192.168.10.75",
    "192.168.10.77",
    "192.168.10.79",
    "192.168.10.60",
)


def _yaml_docs(text: str) -> list[dict]:
    try:
        import yaml  # type: ignore
    except ImportError:
        proc = subprocess.run(
            [
                "python3.12",
                "-c",
                "import json,sys,yaml\n"
                "docs=[d for d in yaml.safe_load_all(sys.stdin.read()) if d]\n"
                "json.dump(docs, sys.stdout)\n",
            ],
            input=text,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise SystemExit(f"cannot parse rendered YAML: {proc.stderr.strip()}")
        return json.loads(proc.stdout)
    return [doc for doc in yaml.safe_load_all(text) if doc]


def render() -> list[dict]:
    proc = subprocess.run(
        ["kubectl", "kustomize", str(ACCESS)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or "kubectl kustomize failed")
    return _yaml_docs(proc.stdout)


def _names(rule: dict, field: str) -> list[str]:
    return [str(item) for item in (rule.get(field) or [])]


def static_problems(docs: list[dict]) -> list[str]:
    problems: list[str] = []
    kinds = {(doc.get("kind"), (doc.get("metadata") or {}).get("name"), (doc.get("metadata") or {}).get("namespace")) for doc in docs}
    if ("Namespace", "bifrost-access", None) not in kinds and ("Namespace", "bifrost-access", "") not in kinds:
        # kustomize keeps namespace unset on the Namespace object itself
        found = any(doc.get("kind") == "Namespace" and (doc.get("metadata") or {}).get("name") == "bifrost-access" for doc in docs)
        if not found:
            problems.append("missing Namespace bifrost-access")
    need = [
        ("ServiceAccount", "bifrost-agent", "bifrost-access"),
        ("Secret", "bifrost-agent-token", "bifrost-access"),
        ("ClusterRole", "bifrost-agent-read", None),
        ("ClusterRoleBinding", "bifrost-agent-view", None),
        ("ClusterRoleBinding", "bifrost-agent-read", None),
    ]
    for kind, name, ns in need:
        matched = [
            doc for doc in docs
            if doc.get("kind") == kind and (doc.get("metadata") or {}).get("name") == name
            and (ns is None or (doc.get("metadata") or {}).get("namespace") == ns)
        ]
        if not matched:
            problems.append(f"missing {kind} {name}")
    for doc in docs:
        if doc.get("kind") == "Secret":
            if doc.get("type") != "kubernetes.io/service-account-token":
                problems.append("Secret is not a service-account token")
            if doc.get("data") or doc.get("stringData"):
                problems.append("token Secret must not carry data in git")
        meta = doc.get("metadata") or {}
        kind = doc.get("kind")
        name = meta.get("name")
        ns = meta.get("namespace")
        for rule in doc.get("rules") or []:
            resources = _names(rule, "resources")
            verbs = set(_names(rule, "verbs"))
            resource_names = _names(rule, "resourceNames")
            if any(item == "secrets" or item.endswith("/secrets") for item in resources) or "*" in resources:
                if "secrets" in resources or "*" in resources:
                    problems.append(f"{kind} {name} grants secrets or all resources")
            if "*" in verbs:
                problems.append(f"{kind} {name} grants all verbs")
            for verb in verbs & WRITE_VERBS:
                allowed = False
                if (
                    kind == "Role"
                    and name == "bifrost-agent-exec"
                    and ns in EXEC_NS
                    and verb == "create"
                    and resources == ["pods/exec"]
                    and not resource_names
                ):
                    allowed = True
                if (
                    kind == "Role"
                    and name == "bifrost-agent-portforward"
                    and ns == "monitoring"
                    and verb in {"get", "create"}
                    and resources == ["pods/portforward"]
                    and resource_names == [PROM]
                ):
                    allowed = True
                if not allowed:
                    problems.append(f"write verb {verb} on {resources} in {kind} {ns}/{name}")
            if "pods/exec" in resources:
                if not (kind == "Role" and name == "bifrost-agent-exec" and ns in EXEC_NS):
                    problems.append(f"pods/exec outside the three namespaces: {ns}/{name}")
                if verbs - {"create"}:
                    problems.append(f"pods/exec verbs {sorted(verbs)} in {ns}")
            if "pods/portforward" in resources:
                if not (kind == "Role" and name == "bifrost-agent-portforward" and ns == "monitoring"):
                    problems.append(f"pods/portforward outside monitoring: {ns}/{name}")
                if resource_names != [PROM]:
                    problems.append(f"port-forward resourceNames {resource_names}")
                if verbs - {"get", "create"}:
                    problems.append(f"port-forward verbs {sorted(verbs)}")
            if verbs and not verbs <= (READ_VERBS | WRITE_VERBS):
                problems.append(f"unexpected verbs {sorted(verbs)} in {kind} {name}")
        if kind == "ClusterRoleBinding":
            ref = doc.get("roleRef") or {}
            if name == "bifrost-agent-view" and ref.get("name") != "view":
                problems.append("view binding does not point at view")
            if name == "bifrost-agent-read" and ref.get("name") != "bifrost-agent-read":
                problems.append("read binding does not point at bifrost-agent-read")
            subjects = doc.get("subjects") or []
            if subjects != [{"kind": "ServiceAccount", "name": "bifrost-agent", "namespace": "bifrost-access"}]:
                problems.append(f"binding {name} subject is not bifrost-agent")
    exec_ns = {
        (doc.get("metadata") or {}).get("namespace")
        for doc in docs
        if doc.get("kind") == "Role" and (doc.get("metadata") or {}).get("name") == "bifrost-agent-exec"
    }
    if exec_ns != set(EXEC_NS):
        problems.append(f"exec namespaces {sorted(exec_ns)}")
    return problems


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True)


def _can(verb: str, resource: str, extra: list[str]) -> str:
    kube = os.environ.get("KUBECONFIG") or str(Path.home() / ".kube" / "bifrost-k3s.yaml")
    proc = _run(["kubectl", "--kubeconfig", kube, "auth", "can-i", verb, resource, *extra])
    text = (proc.stdout or proc.stderr).strip().splitlines()
    return text[-1].strip() if text else f"exit {proc.returncode}"


def _key_names(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        names.add(line.split("=", 1)[0].strip())
    return names


def live_problems() -> list[str]:
    problems: list[str] = []
    kube = os.environ.get("KUBECONFIG") or str(Path.home() / ".kube" / "bifrost-k3s.yaml")
    who = _run(["kubectl", "--kubeconfig", kube, "auth", "whoami", "-o", "json"])
    if who.returncode != 0:
        problems.append("kubectl auth whoami failed")
    else:
        try:
            doc = json.loads(who.stdout)
        except json.JSONDecodeError:
            problems.append("whoami was not JSON")
            doc = {}
        user = ((doc.get("status") or {}).get("userInfo") or {}).get("username")
        if user != AGENT:
            problems.append(f"whoami is {user}")
    expect = [
        ("yes", "list", "pods", ["-A"]),
        ("yes", "get", "pods", ["--subresource=log", "-n", "research"]),
        ("yes", "create", "pods/exec", ["-n", "research"]),
        ("yes", "create", f"pods/portforward/{PROM}", ["-n", "monitoring"]),
        ("no", "get", "secrets", ["-A"]),
        ("no", "create", "pipelineruns.tekton.dev", ["-n", "cicd"]),
        ("no", "create", "pods/exec", ["-n", "data"]),
        ("no", "create", "pods/exec", ["-n", "bifrost-prod"]),
        ("no", "create", "pods/portforward/not-prometheus", ["-n", "monitoring"]),
        ("no", "delete", "pods", ["-n", "research"]),
        ("no", "patch", "deployments", ["-n", "bifrost-prod"]),
        ("no", "create", "namespaces", []),
    ]
    for want, verb, resource, extra in expect:
        got = _can(verb, resource, extra)
        if got != want:
            problems.append(f"can-i {verb} {resource} {' '.join(extra)} got {got} want {want}")
    for host in NODES:
        proc = _run([
            "ssh", "-F", "/dev/null", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=yes", f"vision@{host}", "true",
        ])
        if proc.returncode == 0:
            problems.append(f"ssh via agent succeeded for {host}")
    infra_env = ROOT / ".env"
    platform_env = ROOT.parent / "bifrost-platform" / ".env"
    for key in INFRA_KEYS:
        if key in _key_names(infra_env):
            problems.append(f"infra .env still has {key}")
    for key in PLATFORM_KEYS:
        if key in _key_names(platform_env):
            problems.append(f"platform .env still has {key}")
    plugin_env = ROOT.parent / "bifrost-platform-plugin" / ".env"
    for key in PLUGIN_KEYS:
        if key in _key_names(plugin_env):
            problems.append(f"plugin .env still has {key}")
    secrets = ROOT / "k8s" / "base" / "secrets"
    if secrets.is_dir():
        for path in secrets.iterdir():
            if not path.is_file():
                continue
            name = path.name
            if name.endswith(".example") or name.endswith(".example.yaml") or "example" in name:
                continue
            problems.append(f"secret file still in the checkout: {name}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    docs = render()
    problems = static_problems(docs)
    print(f"static: {len(docs)} objects, {len(problems)} problems")
    if args.live:
        live = live_problems()
        print(f"live: {len(live)} problems")
        problems.extend(live)
    for item in problems:
        print(f"FAIL {item}", file=sys.stderr)
    if problems:
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
