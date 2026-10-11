"""Match ValidatingAdmissionPolicies to a PROD write without evaluating CEL.

A policy matches on namespace selector, resource rules (policy constraints
intersected with the binding), exclude rules, and literal username
matchConditions. Any other matchCondition is recorded and does not exclude an
identity. Validation expressions are kept as text. They never flip a row to
refused; only admission_effects.yaml can do that, and only for a policy that
matched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from prod_write_rbac import Target, selector_matches


_EQ = re.compile(r"""request\.userInfo\.username\s*==\s*['"]([^'"]+)['"]""")
_IN = re.compile(r"""request\.userInfo\.username\s+in\s+\[(.*)\]""", re.S)

# Admission reviews PATCH as UPDATE and deletecollection as DELETE.
_OPERATION = {
    "create": "CREATE",
    "update": "UPDATE",
    "patch": "UPDATE",
    "delete": "DELETE",
    "deletecollection": "DELETE",
}


@dataclass(frozen=True)
class PolicyHit:
    name: str
    verbs: tuple[str, ...]
    cel: str


@dataclass
class Policy:
    name: str
    match: dict
    conditions: list[dict]
    cel: str
    param_kind: str = ""


@dataclass
class PolicyBinding:
    name: str
    policy_name: str
    match: dict
    actions: tuple[str, ...] = field(default_factory=tuple)


def _meta_name(doc: dict) -> str:
    return str((doc.get("metadata") or {}).get("name") or "")


def validation_text(spec: dict) -> str:
    messages = []
    for item in spec.get("validations") or []:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "").strip()
        expression = str(item.get("expression") or "").strip()
        messages.append(message or expression[:240])
    return " | ".join(messages)


def index_policies(docs: list[dict]) -> tuple[dict[str, Policy], list[PolicyBinding]]:
    policies: dict[str, Policy] = {}
    bindings: list[PolicyBinding] = []
    for doc in docs:
        kind = str(doc.get("kind") or "")
        name = _meta_name(doc)
        spec = doc.get("spec") or {}
        if kind == "ValidatingAdmissionPolicy" and name:
            policies[name] = Policy(
                name=name,
                match=spec.get("matchConstraints") or {},
                conditions=[item for item in (spec.get("matchConditions") or []) if isinstance(item, dict)],
                cel=validation_text(spec),
            )
        elif kind == "ValidatingAdmissionPolicyBinding" and name:
            actions = spec.get("validationActions") or []
            bindings.append(
                PolicyBinding(
                    name=name,
                    policy_name=str(spec.get("policyName") or ""),
                    match=spec.get("matchResources") or {},
                    actions=tuple(str(item) for item in actions),
                )
            )
    return policies, bindings


def namespace_index(docs: list[dict]) -> tuple[dict[str, dict[str, str]], set[str]]:
    labels: dict[str, dict[str, str]] = {}
    known: set[str] = set()
    for doc in docs:
        if str(doc.get("kind") or "") != "Namespace":
            continue
        meta = doc.get("metadata") or {}
        name = str(meta.get("name") or "")
        if not name:
            continue
        known.add(name)
        labels[name] = {str(k): str(v) for k, v in (meta.get("labels") or {}).items()}
    return labels, known


def username_allowlist(expression: str) -> set[str] | None:
    """Literal username equality or `in` list. None means the CEL is not that shape."""
    text = (expression or "").strip()
    matched = re.fullmatch(_EQ, text)
    if matched:
        return {matched.group(1)}
    matched = re.fullmatch(_IN, text)
    if not matched:
        return None
    body = matched.group(1)
    if re.search(r"[&|!=<>]", body):
        return None
    names = re.findall(r"""['"]([^'"]+)['"]""", body)
    return set(names) if names else None


def identity_selected(conditions: list[dict], identity: str) -> bool:
    """True when no recognised condition excludes this identity.

    An expression that is not a literal username test does not exclude anyone:
    the row stays gated rather than being treated as refused or as unguarded.
    """
    for condition in conditions:
        allow = username_allowlist(str(condition.get("expression") or ""))
        if allow is not None and identity not in allow:
            return False
    return True


def _namespace_selected(selector: dict | None, namespace: str, labels: dict[str, str], complete: bool) -> bool:
    if not selector:
        return True
    if namespace == "":
        return False
    known = dict(labels)
    known.setdefault("kubernetes.io/metadata.name", namespace)
    if complete:
        return selector_matches(selector, known)
    needed = set((selector.get("matchLabels") or {}))
    for expr in selector.get("matchExpressions") or []:
        needed.add(str(expr.get("key") or ""))
    if needed <= set(known):
        return selector_matches(selector, known)
    return True


def _rule_resources(rule: dict) -> tuple[str, ...]:
    resources = rule.get("resources") or []
    return tuple(str(item) for item in resources)


def _operation_ok(rule: dict, verb: str) -> bool:
    operation = _OPERATION.get(verb)
    if operation is None:
        return False
    operations = [str(item) for item in (rule.get("operations") or [])]
    return "*" in operations or operation in operations


def _group_ok(rule: dict, api_group: str) -> bool:
    groups = [str(item) for item in (rule.get("apiGroups") or [])]
    return not groups or "*" in groups or api_group in groups


def _version_ok(rule: dict, api_version: str) -> bool:
    if not api_version:
        return True
    versions = [str(item) for item in (rule.get("apiVersions") or [])]
    return not versions or "*" in versions or api_version in versions


def _name_ok(rule: dict, name: str) -> bool:
    names = [str(item) for item in (rule.get("resourceNames") or [])]
    if not names or not name:
        return not names or name in names
    return name in names


def one_resource_rule(rule: dict, target: Target, verb: str) -> bool:
    if not _operation_ok(rule, verb) or not _group_ok(rule, target.api_group):
        return False
    if not _version_ok(rule, target.api_version):
        return False
    from prod_write_rbac import resource_matches

    if not resource_matches(_rule_resources(rule), target.resource, target.subresource):
        return False
    return _name_ok(rule, target.name)


def _rules_hit(rules: list | None, target: Target, verb: str, empty_means: bool) -> bool:
    if not rules:
        return empty_means
    return any(isinstance(rule, dict) and one_resource_rule(rule, target, verb) for rule in rules)


def _match_block(block: dict | None, target: Target, verb: str, ns_labels: dict[str, dict[str, str]], ns_known: set[str]) -> bool:
    if not block:
        return True
    namespace = target.namespace
    labels = ns_labels.get(namespace, {})
    if not _namespace_selected(block.get("namespaceSelector"), namespace, labels, namespace in ns_known):
        return False
    if not _rules_hit(block.get("resourceRules"), target, verb, empty_means=True):
        return False
    if _rules_hit(block.get("excludeResourceRules"), target, verb, empty_means=False):
        return False
    return True


def matching_policies(
    policies: dict[str, Policy],
    bindings: list[PolicyBinding],
    target: Target,
    verbs: list[str],
    identity: str,
    ns_labels: dict[str, dict[str, str]],
    ns_known: set[str],
) -> list[PolicyHit]:
    hits: list[PolicyHit] = []
    for binding in sorted(bindings, key=lambda item: item.policy_name):
        policy = policies.get(binding.policy_name)
        if policy is None or not identity_selected(policy.conditions, identity):
            continue
        matched = [
            verb
            for verb in verbs
            if _match_block(policy.match, target, verb, ns_labels, ns_known)
            and _match_block(binding.match, target, verb, ns_labels, ns_known)
        ]
        if not matched:
            continue
        # Warn-only bindings do not gate the write. Deny, or an empty action list, does.
        if binding.actions and "Deny" not in binding.actions:
            continue
        hits.append(PolicyHit(name=policy.name, verbs=tuple(matched), cel=policy.cel))
    return _merge(hits)


def _merge(hits: list[PolicyHit]) -> list[PolicyHit]:
    by_name: dict[str, PolicyHit] = {}
    for hit in hits:
        current = by_name.get(hit.name)
        if current is None:
            by_name[hit.name] = hit
            continue
        verbs = tuple(sorted(set(current.verbs) | set(hit.verbs)))
        cel = current.cel or hit.cel
        by_name[hit.name] = PolicyHit(name=hit.name, verbs=verbs, cel=cel)
    return [by_name[name] for name in sorted(by_name)]


def hits_for_verb(hits: list[PolicyHit], verb: str) -> list[PolicyHit]:
    return [hit for hit in hits if verb in hit.verbs]


def effect_refuses(effects: list[dict], policy_names: list[str], identity: str, field: str) -> bool:
    for effect in effects:
        if effect.get("effect") != "refuse":
            continue
        if effect.get("policy") not in policy_names:
            continue
        if effect.get("field") not in (field, "*"):
            continue
        if effect.get("identity") not in (identity, "*"):
            continue
        return True
    return False


def validate_effects(effects: list[dict]) -> list[str]:
    required = ("policy", "identity", "field", "effect", "note")
    problems = []
    for index, effect in enumerate(effects, start=1):
        missing = [key for key in required if not str(effect.get(key) or "").strip()]
        if missing:
            problems.append(f"invalid-effect: entry {index} missing {', '.join(missing)}")
            continue
        if effect.get("effect") != "refuse":
            problems.append(f"invalid-effect: entry {index} effect must be refuse")
    return problems
