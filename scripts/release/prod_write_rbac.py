"""Kubernetes RBAC evaluation for the platform PROD write matrix.

RoleBinding to a ClusterRole is limited to the binding's namespace. ClusterRole
aggregationRule selectors contribute rules (inline rules on an aggregating
ClusterRole are ignored, as the controller would overwrite them). nonResourceURLs
are ignored. resourceNames do not limit create. A rule for a resource does not
grant its subresources, and a subresource rule does not grant the parent.
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

# Identities the plan's hand-written table names. A binding subject outside this
# set is reported; the matrix still includes its rows.
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


def subject_identity(subject: dict, binding_namespace: str) -> str | None:
    kind = str(subject.get("kind") or "")
    name = str(subject.get("name") or "")
    if not kind or not name:
        return None
    if kind == "ServiceAccount":
        ns = str(subject.get("namespace") or binding_namespace or "")
        return f"system:serviceaccount:{ns}:{name}"
    if kind == "User":
        return f"user:{name}"
    if kind == "Group":
        return f"group:{name}"
    return f"{kind}:{name}"


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
            # aggregationRule sits next to rules, not under spec.
            agg_rule = doc.get("aggregationRule") or (doc.get("spec") or {}).get("aggregationRule") or {}
            agg = agg_rule.get("clusterRoleSelectors") or []
            # A ClusterRole with aggregationRule is controller-managed: inline rules
            # are overwritten. Keep them only when there is no aggregationRule.
            inline = [] if agg else parse_rules(doc.get("rules"))
            clusterroles.append(
                ClusterRoleDef(
                    name=name,
                    labels={str(k): str(v) for k, v in (meta.get("labels") or {}).items()},
                    rules=inline,
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
                    kind=kind,
                    namespace=namespace,
                    role_kind=str(ref.get("kind") or ""),
                    role_name=str(ref.get("name") or ""),
                    subjects=[item for item in subjects if isinstance(item, dict)],
                )
            )
    return clusterroles, roles, bindings


def aggregated_rules(clusterroles: list[ClusterRoleDef]) -> dict[str, list[Rule]]:
    by_name = {item.name: item for item in clusterroles}
    memo: dict[str, list[Rule]] = {}

    def rules_for(name: str, stack: set[str]) -> list[Rule]:
        if name in memo:
            return memo[name]
        role = by_name.get(name)
        if role is None or name in stack:
            return []
        stack.add(name)
        if role.selectors:
            collected: list[Rule] = []
            seen: set[tuple] = set()
            for other in sorted(clusterroles, key=lambda item: item.name):
                if other.name == name:
                    continue
                if not any(selector_matches(sel, other.labels) for sel in role.selectors):
                    continue
                for rule in rules_for(other.name, stack):
                    if rule.key() in seen:
                        continue
                    seen.add(rule.key())
                    collected.append(rule)
            memo[name] = collected
        else:
            memo[name] = list(role.rules)
        stack.remove(name)
        return memo[name]

    return {name: rules_for(name, set()) for name in sorted(by_name)}


def effective_rules(docs: list[dict]) -> tuple[dict[str, list[ScopedRule]], list[str]]:
    """Return write rules per identity, and every binding subject."""
    clusterroles, roles, bindings = load_rbac(docs)
    aggregated = aggregated_rules(clusterroles)
    role_index = {(item.namespace, item.name): item.rules for item in roles}
    by_identity: dict[str, list[ScopedRule]] = {}
    subjects: set[str] = set()
    for binding in bindings:
        identities = []
        for subject in binding.subjects:
            identity = subject_identity(subject, binding.namespace)
            if identity:
                identities.append(identity)
                subjects.add(identity)
        if binding.role_kind == "ClusterRole":
            rules = aggregated.get(binding.role_name, [])
        elif binding.role_kind == "Role" and binding.kind == "RoleBinding":
            rules = role_index.get((binding.namespace, binding.role_name), [])
        else:
            continue
        scope = "*" if binding.kind == "ClusterRoleBinding" else binding.namespace
        for identity in identities:
            bucket = by_identity.setdefault(identity, [])
            for rule in rules:
                bucket.append(ScopedRule(rule=rule, scope=scope))
    return by_identity, sorted(subjects)


def resource_matches(rule_resources: tuple[str, ...], resource: str, subresource: str) -> bool:
    combined = f"{resource}/{subresource}" if subresource else resource
    for item in rule_resources:
        if item == "*" or item == combined:
            return True
        if subresource and item in (f"*/{subresource}", f"{resource}/*"):
            return True
    return False


def rule_allows(scoped: ScopedRule, verb: str, target: Target) -> bool:
    rule = scoped.rule
    if scoped.scope != "*" and scoped.scope != target.namespace:
        return False
    if target.namespace == "" and scoped.scope != "*":
        return False
    if verb not in rule.verbs and "*" not in rule.verbs:
        return False
    if target.api_group not in rule.api_groups and "*" not in rule.api_groups:
        return False
    if not resource_matches(rule.resources, target.resource, target.subresource):
        return False
    if verb != "create" and rule.resource_names and target.name not in rule.resource_names:
        return False
    return True


def allowed_verbs(rules: list[ScopedRule], target: Target) -> list[str]:
    return [verb for verb in WRITE_VERBS if any(rule_allows(rule, verb, target) for rule in rules)]
