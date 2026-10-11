"""Kubernetes RBAC evaluation for the platform PROD write matrix.

RoleBinding to a ClusterRole is limited to the binding's namespace. Aggregation
is a monotone fixed point, so a cycle cannot drop rules. In a dump, rules
already stored on an aggregated ClusterRole are kept. nonResourceURLs are
ignored. A resource rule does not grant a subresource, and the reverse.

resourceNames do not limit create. On a target declared without a name, a
named rule still grants the write and the row carries those names.
"""

from __future__ import annotations

from dataclasses import dataclass, field


WRITE_VERBS = (
    "bind",
    "create",
    "delete",
    "deletecollection",
    "escalate",
    "impersonate",
    "patch",
    "update",
)

# GET on these subresources runs a command or attaches a stream. It is a write.
EXEC_SUBRESOURCES = frozenset({"exec", "attach", "portforward", "ephemeralcontainers"})

PLAN_TABLE = frozenset(
    {
        "system:serviceaccount:bifrost-platform-prod:bifrost-platform",
        "system:serviceaccount:cicd:tekton-trigger",
        "system:serviceaccount:cicd:tekton-deliver",
        "owner-admin",
        "owner_run_command",
        "anyone-who-reaches-the-registry",
        "anyone-who-can-push-main",
    }
)


@dataclass(frozen=True)
class Rule:
    api_groups: tuple[str, ...]
    resources: tuple[str, ...]
    verbs: tuple[str, ...]
    resource_names: tuple[str, ...]

    def key(self) -> tuple:
        return (self.api_groups, self.resources, self.verbs, self.resource_names)


@dataclass(frozen=True)
class ScopedRule:
    rule: Rule
    scope: str  # "*" cluster-wide, otherwise one namespace
    path: str = ""


@dataclass(frozen=True)
class Grant:
    verbs: tuple[str, ...]
    only: tuple[str, ...]
    path: str


@dataclass
class ClusterRoleDef:
    name: str
    labels: dict[str, str]
    rules: list[Rule]
    selectors: list[dict] = field(default_factory=list)


@dataclass
class RoleDef:
    name: str
    namespace: str
    rules: list[Rule]


@dataclass
class BindingDef:
    name: str
    kind: str
    namespace: str
    role_kind: str
    role_name: str
    subjects: list[dict]


@dataclass(frozen=True)
class Target:
    id: str
    namespace: str
    api_group: str
    resource: str
    name: str
    subresource: str
    fields: tuple[str, ...]
    why: str
    api_version: str = ""


def candidate_verbs(target: Target) -> tuple[str, ...]:
    if target.subresource in EXEC_SUBRESOURCES:
        return WRITE_VERBS + ("get",)
    return WRITE_VERBS


def subject_identity(subject: dict, binding_namespace: str) -> str | None:
    kind = str(subject.get("kind") or "")
    name = str(subject.get("name") or "")
    if not kind or not name:
        return None
    if kind == "ServiceAccount":
        ns = str(subject.get("namespace") or binding_namespace or "")
        return f"system:serviceaccount:{ns}:{name}"
    if kind == "User":
        if name in ("system:anonymous", "anonymous"):
            return "system:anonymous"
        return f"user:{name}"
    if kind == "Group":
        return f"group:{name}"
    return f"{kind}:{name}"


def sa_namespace(identity: str) -> str | None:
    prefix = "system:serviceaccount:"
    if not identity.startswith(prefix):
        return None
    rest = identity[len(prefix):]
    namespace, sep, name = rest.partition(":")
    if not sep or not name:
        return None
    return namespace


def _tuple(value, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def parse_rule(raw: dict) -> Rule | None:
    resources = _tuple(raw.get("resources"))
    if not resources:
        return None
    return Rule(
        api_groups=_tuple(raw.get("apiGroups"), ("",)),
        resources=resources,
        verbs=_tuple(raw.get("verbs")),
        resource_names=_tuple(raw.get("resourceNames")),
    )


def parse_rules(raw_rules: list | None) -> list[Rule]:
    rules: list[Rule] = []
    for raw in raw_rules or []:
        if not isinstance(raw, dict):
            continue
        rule = parse_rule(raw)
        if rule is not None and rule.verbs:
            rules.append(rule)
    return rules


def selector_matches(selector: dict | None, labels: dict[str, str]) -> bool:
    if not selector:
        return True
    for key, value in (selector.get("matchLabels") or {}).items():
        if labels.get(key) != str(value):
            return False
    known = {"In", "NotIn", "Exists", "DoesNotExist"}
    for expr in selector.get("matchExpressions") or []:
        key = str(expr.get("key") or "")
        op = str(expr.get("operator") or "")
        values = [str(item) for item in (expr.get("values") or [])]
        present = key in labels
        if op not in known:
            return False
        if op == "In" and labels.get(key) not in values:
            return False
        if op == "NotIn" and present and labels.get(key) in values:
            return False
        if op == "Exists" and not present:
            return False
        if op == "DoesNotExist" and present:
            return False
    return True


def _meta(doc: dict) -> dict:
    meta = doc.get("metadata") or {}
    return meta if isinstance(meta, dict) else {}


def load_rbac(docs: list[dict]) -> tuple[list[ClusterRoleDef], list[RoleDef], list[BindingDef]]:
    clusterroles: list[ClusterRoleDef] = []
    roles: list[RoleDef] = []
    bindings: list[BindingDef] = []
    for doc in docs:
        kind = str(doc.get("kind") or "")
        meta = _meta(doc)
        name = str(meta.get("name") or "")
        namespace = str(meta.get("namespace") or "")
        if kind == "ClusterRole" and name:
            agg_rule = doc.get("aggregationRule") or (doc.get("spec") or {}).get("aggregationRule") or {}
            agg = agg_rule.get("clusterRoleSelectors") or []
            parsed = parse_rules(doc.get("rules"))
            clusterroles.append(
                ClusterRoleDef(
                    name=name,
                    labels={str(k): str(v) for k, v in (meta.get("labels") or {}).items()},
                    rules=parsed,
                    selectors=[item for item in agg if isinstance(item, dict)],
                )
            )
        elif kind == "Role" and name:
            roles.append(RoleDef(name=name, namespace=namespace, rules=parse_rules(doc.get("rules"))))
        elif kind in ("RoleBinding", "ClusterRoleBinding"):
            ref = doc.get("roleRef") or {}
            subjects = doc.get("subjects") or []
            bindings.append(
                BindingDef(
                    name=name or f"{kind}/{namespace}",
                    kind=kind,
                    namespace=namespace,
                    role_kind=str(ref.get("kind") or ""),
                    role_name=str(ref.get("name") or ""),
                    subjects=[item for item in subjects if isinstance(item, dict)],
                )
            )
    return clusterroles, roles, bindings


def aggregated_rules(clusterroles: list[ClusterRoleDef], from_dump: bool = False) -> dict[str, list[Rule]]:
    """Monotone fixed point. Cycles keep rules that flow in from outside the cycle.

    A dump keeps rules already materialised on an aggregated ClusterRole and
    still unions anything the selectors add. A repository aggregated role
    starts empty: the controller overwrites inline rules.
    """
    current: dict[str, list[Rule]] = {}
    for role in clusterroles:
        if role.selectors and from_dump:
            current[role.name] = list(role.rules)
        elif role.selectors:
            current[role.name] = []
        else:
            current[role.name] = list(role.rules)
    changed = True
    while changed:
        changed = False
        for role in clusterroles:
            if not role.selectors:
                continue
            have = {rule.key() for rule in current[role.name]}
            for other in clusterroles:
                if other.name == role.name:
                    continue
                if not any(selector_matches(sel, other.labels) for sel in role.selectors):
                    continue
                for rule in current[other.name]:
                    if rule.key() in have:
                        continue
                    current[role.name].append(rule)
                    have.add(rule.key())
                    changed = True
    return current


def service_account_identities(docs: list[dict], subjects: set[str]) -> set[str]:
    found = {identity for identity in subjects if identity.startswith("system:serviceaccount:")}
    for doc in docs:
        if str(doc.get("kind") or "") != "ServiceAccount":
            continue
        meta = _meta(doc)
        name = str(meta.get("name") or "")
        namespace = str(meta.get("namespace") or "")
        if name and namespace:
            found.add(f"system:serviceaccount:{namespace}:{name}")
    return found


def _append_unique(bucket: list[ScopedRule], rule: ScopedRule, seen: set[tuple]) -> None:
    mark = (rule.rule.key(), rule.scope, rule.path)
    if mark in seen:
        return
    seen.add(mark)
    bucket.append(rule)


def effective_rules(docs: list[dict], from_dump: bool = False) -> tuple[dict[str, list[ScopedRule]], list[str], list[str]]:
    """Write rules per identity, every subject, and unresolved roleRef messages.

    A missing roleRef is not an empty rule set. The message is
    ``unresolved roleRef: <binding> -> <role>``.
    """
    clusterroles, roles, bindings = load_rbac(docs)
    aggregated = aggregated_rules(clusterroles, from_dump=from_dump)
    role_index = {(item.namespace, item.name): item.rules for item in roles}
    by_identity: dict[str, list[ScopedRule]] = {}
    seen: dict[str, set[tuple]] = {}
    subjects: set[str] = set()
    unresolved: list[str] = []
    for binding in bindings:
        identities = []
        for subject in binding.subjects:
            identity = subject_identity(subject, binding.namespace)
            if not identity:
                continue
            identities.append(identity)
            subjects.add(identity)
        if binding.role_kind == "ClusterRole":
            if binding.role_name not in aggregated:
                unresolved.append(f"unresolved roleRef: {binding.name} -> {binding.role_name}")
                continue
            rules = aggregated[binding.role_name]
        elif binding.role_kind == "Role" and binding.kind == "RoleBinding":
            key = (binding.namespace, binding.role_name)
            if key not in role_index:
                unresolved.append(f"unresolved roleRef: {binding.name} -> {binding.role_name}")
                continue
            rules = role_index[key]
        else:
            unresolved.append(f"unresolved roleRef: {binding.name} -> {binding.role_name}")
            continue
        scope = "*" if binding.kind == "ClusterRoleBinding" else binding.namespace
        for identity in identities:
            bucket = by_identity.setdefault(identity, [])
            marks = seen.setdefault(identity, set())
            for rule in rules:
                _append_unique(bucket, ScopedRule(rule=rule, scope=scope), marks)
    for sa in service_account_identities(docs, subjects):
        subjects.add(sa)
        by_identity.setdefault(sa, [])
        namespace = sa_namespace(sa) or ""
        groups = (
            "group:system:serviceaccounts",
            f"group:system:serviceaccounts:{namespace}",
            "group:system:authenticated",
        )
        marks = seen.setdefault(sa, set())
        for group in groups:
            for rule in by_identity.get(group, []):
                _append_unique(by_identity[sa], rule, marks)
    anon_rules = list(by_identity.get("group:system:unauthenticated", []))
    if anon_rules:
        bucket = by_identity.setdefault("system:anonymous", [])
        marks = seen.setdefault("system:anonymous", set())
        for rule in anon_rules:
            _append_unique(bucket, rule, marks)
        subjects.add("system:anonymous")
    return by_identity, sorted(subjects), unresolved


def resource_matches(rule_resources: tuple[str, ...], resource: str, subresource: str) -> bool:
    """RBAC resource match. ``*`` matches a resource and its subresources.

    ``resource/*`` is not an RBAC wildcard (admission treats it as one). A
    parent rule does not match a subresource, and a subresource rule does not
    match the parent.
    """
    combined = f"{resource}/{subresource}" if subresource else resource
    for item in rule_resources:
        if item == "*":
            return True
        if item == combined:
            return True
        if subresource and item == f"*/{subresource}":
            return True
    return False


def _rule_matches(scoped: ScopedRule, verb: str, target: Target) -> bool:
    rule = scoped.rule
    if scoped.scope != "*" and scoped.scope != target.namespace:
        return False
    if target.namespace == "" and scoped.scope != "*":
        return False
    if verb not in rule.verbs and "*" not in rule.verbs:
        return False
    if target.api_group not in rule.api_groups and "*" not in rule.api_groups:
        return False
    return resource_matches(rule.resources, target.resource, target.subresource)


def allowed_grants(rules: list[ScopedRule], target: Target) -> list[Grant]:
    """Verbs the rules grant, with resourceNames kept on unnamed targets.

    ``only`` is empty when some matching rule is not name-limited. Otherwise
    it is the union of the names. create ignores resourceNames.
    """
    verbs = candidate_verbs(target)
    per_path: dict[str, dict[str, set[str] | None]] = {}
    for scoped in rules:
        for verb in verbs:
            if not _rule_matches(scoped, verb, target):
                continue
            names = scoped.rule.resource_names
            slot = per_path.setdefault(scoped.path, {})
            if verb == "create" or not names or (target.name and target.name in names):
                slot[verb] = None
            elif not target.name:
                current = slot.get(verb, set())
                if current is None:
                    continue
                slot[verb] = set(current) | set(names)
    grants: list[Grant] = []
    for path in sorted(per_path):
        groups: dict[tuple[str, ...], list[str]] = {}
        for verb, only in per_path[path].items():
            key = () if only is None else tuple(sorted(only))
            groups.setdefault(key, []).append(verb)
        for only, group in sorted(groups.items()):
            ordered = tuple(verb for verb in verbs if verb in group)
            grants.append(Grant(verbs=ordered, only=only, path=path))
    return grants


def allowed_verbs(rules: list[ScopedRule], target: Target) -> list[str]:
    found = []
    for grant in allowed_grants(rules, target):
        for verb in grant.verbs:
            if verb not in found:
                found.append(verb)
    return found


def rule_allows(scoped: ScopedRule, verb: str, target: Target) -> bool:
    return verb in allowed_verbs([scoped], target)
