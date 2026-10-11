"""Permissions a subject can obtain, as a monotone fixed point.

Each new rule records its path (``via impersonate …``, ``via bind …``,
``via escalate``, ``via create <resource> as <sa>``, ``via serviceaccounts/token``).
A rule already held is not added again, so a cycle stops.

Creating a pod-template workload, PipelineRun or TaskRun borrows every
ServiceAccount in that namespace unless a proven restrict-serviceaccount
effect names the only ones allowed. An unproven effect does not narrow.
"""

from __future__ import annotations

from prod_write_admission import matching_policies
from prod_write_rbac import (
    BindingDef,
    Rule,
    ScopedRule,
    Target,
    aggregated_rules,
    load_rbac,
    resource_matches,
    sa_namespace,
    subject_identity,
)


_GROUP = "rbac.authorization.k8s.io"
_WORKLOADS = {
    "pods": ("", "v1"),
    "jobs": ("batch", "v1"),
    "cronjobs": ("batch", "v1"),
    "deployments": ("apps", "v1"),
    "statefulsets": ("apps", "v1"),
    "daemonsets": ("apps", "v1"),
    "replicasets": ("apps", "v1"),
    "pipelineruns": ("tekton.dev", "v1"),
    "taskruns": ("tekton.dev", "v1"),
}
_STAR = Rule(api_groups=("*",), resources=("*",), verbs=("*",), resource_names=())


def _held(rules: list[ScopedRule], rule: Rule, scope: str, path: str) -> bool:
    return any(item.rule.key() == rule.key() and item.scope == scope and item.path == path for item in rules)


def _scopes(rules: list[ScopedRule], verb: str, resource: str, api_group: str, subresource: str = "") -> list[str]:
    found = []
    for scoped in rules:
        if scoped.path:
            continue
        rule = scoped.rule
        if verb not in rule.verbs and "*" not in rule.verbs:
            continue
        if api_group not in rule.api_groups and "*" not in rule.api_groups:
            continue
        if not resource_matches(rule.resources, resource, subresource):
            continue
        found.append(scoped.scope)
    return found


def _write_scopes(rules, resource: str) -> list[str]:
    found = []
    for verb in ("create", "update", "patch"):
        found.extend(_scopes(rules, verb, resource, _GROUP))
    return found


def _names_for(rules: list[ScopedRule], verb: str, resource: str) -> set[str] | None:
    """None when any matching rule is not limited by resourceNames."""
    limited: set[str] = set()
    saw = False
    for scoped in rules:
        if scoped.path:
            continue
        rule = scoped.rule
        if verb not in rule.verbs and "*" not in rule.verbs:
            continue
        if not resource_matches(rule.resources, resource, ""):
            continue
        if _GROUP not in rule.api_groups and "*" not in rule.api_groups:
            continue
        saw = True
        if not rule.resource_names:
            return None
        limited.update(rule.resource_names)
    return limited if saw else set()


def _bound(identity: str, bindings: list[BindingDef], kind: str) -> set[str]:
    names = set()
    for binding in bindings:
        if binding.role_kind != kind:
            continue
        for subject in binding.subjects:
            if subject_identity(subject, binding.namespace) == identity:
                names.add(binding.role_name)
    return names


def _allowlist(effects, hits, identity: str, namespace: str, resource: str) -> set[str] | None:
    allow: set[str] | None = None
    proven = {hit.name for hit in hits if hit.proven}
    for effect in effects:
        if effect.get("effect") != "restrict-serviceaccount":
            continue
        if effect.get("policy") not in proven:
            continue
        if effect.get("identity") not in (identity, "*"):
            continue
        resources = [str(item) for item in (effect.get("resources") or [])]
        if resource not in resources:
            continue
        names = {str(item) for item in (effect.get("service_accounts") or [])}
        also = effect.get("also") or {}
        if isinstance(also, dict):
            names.update(str(item) for item in (also.get(namespace) or []))
        allow = names if allow is None else allow & names
    return allow


def expand(by_identity, docs, policies, policy_bindings, effects, ns_labels, ns_known, from_dump: bool) -> list[str]:
    clusterroles, roles, bindings = load_rbac(docs)
    cluster_rules = aggregated_rules(clusterroles, from_dump=from_dump)
    role_rules = {(item.namespace, item.name): item.rules for item in roles}
    namespaces = set(ns_known)
    for identity in by_identity:
        namespace = sa_namespace(identity)
        if namespace:
            namespaces.add(namespace)
    for binding in bindings:
        if binding.namespace:
            namespaces.add(binding.namespace)
    surfaces: list[str] = []
    changed = True
    while changed:
        changed = False
        for identity in list(by_identity):
            snapshot = list(by_identity[identity])
            additions = []
            additions.extend(_impersonate(identity, snapshot, by_identity, surfaces))
            additions.extend(_bind(snapshot, cluster_rules, role_rules, surfaces))
            additions.extend(_escalate(identity, snapshot, bindings))
            additions.extend(
                _workloads(
                    identity, snapshot, by_identity, namespaces, policies, policy_bindings, effects, ns_labels, ns_known, surfaces
                )
            )
            for rule in additions:
                if _held(by_identity[identity], rule.rule, rule.scope, rule.path):
                    continue
                by_identity[identity].append(rule)
                changed = True
    return sorted(set(surfaces))


def _impersonate(identity, rules, by_identity, surfaces) -> list[ScopedRule]:
    added = []
    known = sorted(by_identity)
    for scoped in rules:
        if scoped.path:
            continue
        rule = scoped.rule
        if "impersonate" not in rule.verbs and "*" not in rule.verbs:
            continue
        resources = set(rule.resources)
        if not resources & {"*", "users", "groups", "serviceaccounts"}:
            continue
        targets, extra = _impersonation_targets(rule, scoped.scope, known)
        surfaces.extend(extra)
        for target in targets:
            if target == identity:
                continue
            for victim in by_identity.get(target, []):
                added.append(ScopedRule(victim.rule, victim.scope, f"via impersonate {target}"))
    return added


def _impersonation_targets(rule: Rule, scope: str, known: list[str]) -> tuple[list[str], list[str]]:
    resources = set(rule.resources)
    star = "*" in resources
    names = set(rule.resource_names)
    found: list[str] = []
    surfaces: list[str] = []

    def take(resource: str, prefix: str, label: str) -> None:
        if not star and resource not in resources:
            return
        pool = [item for item in known if item.startswith(prefix)]
        if resource == "serviceaccounts" and scope != "*":
            pool = [item for item in pool if sa_namespace(item) == scope]
        if not names:
            found.extend(pool)
            surfaces.append(f"unknown-surface: impersonate {label} without resourceNames")
            return
        if resource == "serviceaccounts":
            for name in sorted(names):
                if "/" in name:
                    namespace, _, short = name.partition("/")
                    found.append(f"system:serviceaccount:{namespace}:{short}")
                elif scope != "*":
                    found.append(f"system:serviceaccount:{scope}:{name}")
                else:
                    found.extend(item for item in pool if item.rsplit(":", 1)[-1] == name)
                    surfaces.append(f"unknown-surface: impersonate serviceaccount {name} in every namespace")
        else:
            found.extend(f"{prefix}{name}" for name in sorted(names))

    take("users", "user:", "users")
    take("groups", "group:", "groups")
    take("serviceaccounts", "system:serviceaccount:", "serviceaccounts")
    return found, surfaces


def _bind(rules, cluster_rules, role_rules, surfaces) -> list[ScopedRule]:
    added = []
    if _scopes(rules, "bind", "clusterroles", _GROUP) and _write_scopes(rules, "clusterrolebindings"):
        names = _names_for(rules, "bind", "clusterroles")
        picked = sorted(cluster_rules) if names is None else sorted(names & set(cluster_rules))
        if names is None:
            surfaces.append("unknown-surface: bind clusterroles without resourceNames")
        for name in picked:
            for rule in cluster_rules.get(name, []):
                added.append(ScopedRule(rule, "*", f"via bind clusterrole/{name}"))
    if _scopes(rules, "bind", "roles", _GROUP) and _write_scopes(rules, "rolebindings"):
        names = _names_for(rules, "bind", "roles")
        if names is None:
            surfaces.append("unknown-surface: bind roles without resourceNames")
        scopes = _scopes(rules, "bind", "roles", _GROUP)
        namespaces = sorted({ns for ns, _name in role_rules}) if "*" in scopes else sorted(set(scopes))
        for namespace in namespaces:
            for (role_ns, role_name), body in role_rules.items():
                if role_ns != namespace:
                    continue
                if names is not None and role_name not in names:
                    continue
                for rule in body:
                    added.append(ScopedRule(rule, namespace, f"via bind role/{namespace}/{role_name}"))
    return added


def _escalate(identity, rules, bindings) -> list[ScopedRule]:
    added = []
    for resource, kind in (("clusterroles", "ClusterRole"), ("roles", "Role")):
        if not _scopes(rules, "escalate", resource, _GROUP):
            continue
        if not _write_scopes(rules, resource):
            continue
        bound = _bound(identity, bindings, kind)
        if not bound and not _scopes(rules, "bind", resource, _GROUP):
            continue
        scope = "*" if kind == "ClusterRole" else "*"
        if kind == "Role":
            role_scopes = _write_scopes(rules, resource)
            scope = "*" if "*" in role_scopes else (role_scopes[0] if role_scopes else "*")
        added.append(ScopedRule(_STAR, scope, "via escalate"))
    return added


def _workloads(identity, rules, by_identity, namespaces, policies, policy_bindings, effects, ns_labels, ns_known, surfaces):
    added = []
    sas = [item for item in by_identity if item.startswith("system:serviceaccount:")]
    for resource, (api_group, version) in _WORKLOADS.items():
        for scope in _scopes(rules, "create", resource, api_group):
            spaces = sorted(namespaces) if scope == "*" else [scope]
            if scope == "*" and not spaces:
                surfaces.append(f"unknown-surface: create {resource} in namespaces that were not read")
            for namespace in spaces:
                if not namespace:
                    continue
                target = Target("borrow", namespace, api_group, resource, "", "", ("serviceAccountName",), "", version)
                hits = matching_policies(policies, policy_bindings, target, ["create"], identity, ns_labels, ns_known)
                allow = _allowlist(effects, hits, identity, namespace, resource)
                if allow is None:
                    chosen = [sa for sa in sas if sa_namespace(sa) == namespace and sa != identity]
                    surfaces.append(f"unknown-surface: serviceaccounts in {namespace}")
                else:
                    chosen = [f"system:serviceaccount:{namespace}:{name}" for name in sorted(allow)]
                    chosen = [sa for sa in chosen if sa != identity]
                for sa in chosen:
                    path = f"via create {resource} as {sa}"
                    for victim in by_identity.get(sa, []):
                        added.append(ScopedRule(victim.rule, victim.scope, path))
    for scoped in rules:
        if scoped.path:
            continue
        if "create" not in scoped.rule.verbs and "*" not in scoped.rule.verbs:
            continue
        if not resource_matches(scoped.rule.resources, "serviceaccounts", "token"):
            continue
        spaces = sorted(namespaces) if scoped.scope == "*" else [scoped.scope]
        if scoped.scope == "*" and not spaces:
            surfaces.append("unknown-surface: serviceaccounts/token in namespaces that were not read")
        for namespace in spaces:
            if not namespace:
                continue
            if scoped.rule.resource_names:
                picked = [f"system:serviceaccount:{namespace}:{name}" for name in scoped.rule.resource_names]
            else:
                picked = [sa for sa in sas if sa_namespace(sa) == namespace]
                surfaces.append(f"unknown-surface: serviceaccounts/token in {namespace}")
            for sa in picked:
                if sa == identity:
                    continue
                for victim in by_identity.get(sa, []):
                    added.append(ScopedRule(victim.rule, victim.scope, f"via serviceaccounts/token {sa}"))
    return added
