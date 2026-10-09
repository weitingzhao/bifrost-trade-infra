#!/usr/bin/env python3
"""Generate k8s/platform-rbac/{10-stg,20-prod}.yaml (TD-204) from one namespace list.

STG observes, PROD maintains (Owner 2026-10-07). The ClusterRoles live in
00-clusterroles.yaml; this writes the ServiceAccount and bindings per env.
Usage: python3 scripts/gen_platform_rbac.py   (then kubectl apply -k k8s/platform-rbac)
"""
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "k8s" / "platform-rbac"
# Namespaces the platform reads logs in and (PROD) acts on.
BIFROST_NS = ["bifrost-dev", "bifrost-stg", "bifrost-prod", "bifrost-platform-stg", "bifrost-platform-prod",
              "data", "research", "plugin-market-data", "plugin-flex-query", "cicd", "monitoring"]


def sa(env):
    return (f"apiVersion: v1\nkind: ServiceAccount\nmetadata:\n  name: bifrost-platform\n"
            f"  namespace: bifrost-platform-{env}\n  labels: {{app.kubernetes.io/part-of: bifrost-platform}}\n")


def subj(env):
    return f"[{{kind: ServiceAccount, name: bifrost-platform, namespace: bifrost-platform-{env}}}]"


def crb(env, role):
    return (f"apiVersion: rbac.authorization.k8s.io/v1\nkind: ClusterRoleBinding\nmetadata:\n  name: {role}-{env}\n"
            f"  labels: {{app.kubernetes.io/part-of: bifrost-platform}}\n"
            f"roleRef: {{apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: {role}}}\nsubjects: {subj(env)}\n")


def rb(env, role, ns):
    return (f"apiVersion: rbac.authorization.k8s.io/v1\nkind: RoleBinding\nmetadata:\n  name: {role}-{env}\n"
            f"  namespace: {ns}\n  labels: {{app.kubernetes.io/part-of: bifrost-platform}}\n"
            f"roleRef: {{apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: {role}}}\nsubjects: {subj(env)}\n")


POLICY = OUT.parent / "cicd" / "tekton" / "apply-manifest" / "actuation-policy.yaml"


def parse_policy(text):
    """Enough of actuation-policy.yaml to generate bindings. No PyYAML."""
    stack = []
    maps = {}
    lists = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = tuple(key for _, key in stack)
        if line.startswith("- "):
            item = line[2:].strip()
            if ":" in item and not item.startswith('"'):
                key, _, val = item.partition(":")
                lists.setdefault(path, []).append({key.strip(): unquote(val)})
            else:
                lists.setdefault(path, []).append(unquote(item))
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val == "":
            stack.append((indent, key))
            continue
        parent = maps.setdefault(path, {})
        parent[key] = unquote(val)
        if lists.get(path) and isinstance(lists[path][-1], dict) and key not in lists[path][-1]:
            lists[path][-1][key] = unquote(val)
    return maps, lists


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def policy_names():
    text = POLICY.read_text()
    maps, lists = parse_policy(text)
    job_ns = set(maps.get(("jobs", "namespaces"), {}))
    job_ns |= set(maps.get(("probe", "namespaces"), {}))
    deny = set(lists.get(("jobs", "deny"), [])) | set(lists.get(("probe", "deny"), []))
    job_ns -= deny
    apply_ns = set(maps.get(("apply", "namespaces"), {}))
    resources = [item for item in lists.get(("apply", "resources"), []) if isinstance(item, dict)]
    cicd_resources = [item for item in lists.get(("apply", "cicd_resources"), []) if isinstance(item, dict)]
    delivery_ns = maps.get(("delivery",), {}).get("namespace", "")
    return sorted(job_ns), sorted(apply_ns), resources, cicd_resources, delivery_ns


def rule_block(items):
    grouped = {}
    for item in items:
        grouped.setdefault(item.get("group", ""), []).append(item["resource"])
    lines = []
    for group, resources in grouped.items():
        quoted = ", ".join(resources)
        lines.append(
            f"  - apiGroups: [\"{group}\"]\n"
            f"    resources: [{quoted}]\n"
            f"    verbs: [get, list, create, patch, update]\n"
        )
    return "".join(lines)


def applier_file(apply_ns, resources, cicd_resources, delivery_ns):
    others = [ns for ns in apply_ns if ns != delivery_ns]
    subject = "[{kind: ServiceAccount, name: bifrost-applier, namespace: cicd}]"
    docs = []
    docs.append(
        "apiVersion: v1\nkind: ServiceAccount\nmetadata:\n"
        "  name: bifrost-applier\n  namespace: cicd\n"
        "  labels: {app.kubernetes.io/part-of: bifrost-platform}\n"
    )
    docs.append(
        "apiVersion: rbac.authorization.k8s.io/v1\nkind: ClusterRole\nmetadata:\n"
        "  name: bifrost-applier\n  labels: {app.kubernetes.io/part-of: bifrost-platform}\nrules:\n"
        + rule_block(resources)
    )
    docs.append(
        "apiVersion: rbac.authorization.k8s.io/v1\nkind: ClusterRole\nmetadata:\n"
        "  name: bifrost-applier-cicd\n  labels: {app.kubernetes.io/part-of: bifrost-platform}\nrules:\n"
        + rule_block(cicd_resources)
    )
    docs.append(
        "apiVersion: rbac.authorization.k8s.io/v1\nkind: Role\nmetadata:\n"
        "  name: bifrost-applier-read\n  namespace: cicd\n"
        "  labels: {app.kubernetes.io/part-of: bifrost-platform}\n"
        "rules:\n"
        "  - apiGroups: [\"\"]\n    resources: [secrets]\n"
        "    resourceNames: [gitea-git-credentials]\n    verbs: [get]\n"
        "  - apiGroups: [\"\"]\n    resources: [configmaps]\n"
        "    resourceNames: [bifrost-actuation-policy, bifrost-apply-manifest-check]\n"
        "    verbs: [get]\n"
    )
    for ns in others:
        docs.append(
            "apiVersion: rbac.authorization.k8s.io/v1\nkind: RoleBinding\nmetadata:\n"
            f"  name: bifrost-applier\n  namespace: {ns}\n"
            "  labels: {app.kubernetes.io/part-of: bifrost-platform}\n"
            "roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: bifrost-applier}\n"
            f"subjects: {subject}\n"
        )
    docs.append(
        "apiVersion: rbac.authorization.k8s.io/v1\nkind: RoleBinding\nmetadata:\n"
        f"  name: bifrost-applier-cicd\n  namespace: {delivery_ns}\n"
        "  labels: {app.kubernetes.io/part-of: bifrost-platform}\n"
        "roleRef: {apiGroup: rbac.authorization.k8s.io, kind: ClusterRole, name: bifrost-applier-cicd}\n"
        f"subjects: {subject}\n"
    )
    docs.append(
        "apiVersion: rbac.authorization.k8s.io/v1\nkind: RoleBinding\nmetadata:\n"
        "  name: bifrost-applier-read\n  namespace: cicd\n"
        "  labels: {app.kubernetes.io/part-of: bifrost-platform}\n"
        "roleRef: {apiGroup: rbac.authorization.k8s.io, kind: Role, name: bifrost-applier-read}\n"
        f"subjects: {subject}\n"
    )
    head = ("# Applier identity for bifrost-apply-manifest. Generated by\n"
            "# scripts/gen_platform_rbac.py from actuation-policy.yaml; do not edit by hand.\n"
            "# No Secrets except the named Gitea credential, no RBAC, no cluster scope,\n"
            "# and no binding in a denied namespace.\n")
    return head + "---\n" + "---\n".join(docs)


def env_file(env, prod, job_ns):
    own = f"bifrost-platform-{env}"
    docs = [sa(env), crb(env, "bifrost-platform-observer")]
    docs += [rb(env, "bifrost-platform-logs", n) for n in BIFROST_NS]
    docs += [rb(env, "bifrost-platform-state", own), rb(env, "bifrost-platform-state", "cicd"),
             rb(env, "bifrost-platform-gitea-creds", "cicd")]
    if prod:
        docs += [rb(env, "bifrost-platform-workload-actuator", n) for n in BIFROST_NS]
        docs += [crb(env, "bifrost-platform-node-actuator"), crb(env, "bifrost-platform-node-drain"),
                 rb(env, "bifrost-platform-data-actuator", "data"),
                 rb(env, "bifrost-platform-delivery", "cicd")]
        docs += [rb(env, "bifrost-platform-job-actuator", n) for n in job_ns]
    what = "observe and maintain" if prod else "observe only (Owner 2026-10-07: STG observes, PROD maintains)"
    head = (f"# {env.upper()}: {what}. Generated by\n"
            "# scripts/gen_platform_rbac.py from one namespace list; do not edit by hand.\n")
    return head + "---\n" + "---\n".join(docs)


if __name__ == "__main__":
    job_ns, apply_ns, resources, cicd_resources, delivery_ns = policy_names()
    if not job_ns or not resources or not delivery_ns:
        raise SystemExit(f"actuation policy parse failed: {POLICY}")
    (OUT / "10-stg.yaml").write_text(env_file("stg", False, job_ns))
    (OUT / "20-prod.yaml").write_text(env_file("prod", True, job_ns))
    (OUT / "30-applier.yaml").write_text(applier_file(apply_ns, resources, cicd_resources, delivery_ns))
    print("wrote", OUT / "10-stg.yaml", OUT / "20-prod.yaml", OUT / "30-applier.yaml")
