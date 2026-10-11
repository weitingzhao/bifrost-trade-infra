"""Match ValidatingAdmissionPolicies without evaluating CEL.

A row is refused only when a reviewed effect names that exact field and the
policy is proven to apply. Proven means every one of these was read off the
objects: validationActions contains Deny, failurePolicy is Fail, every
matchCondition evaluates true for the identity, there is no objectSelector,
no parameter the program cannot resolve, and the namespace selector matches
labels actually read. Anything else that still overlaps the request is
``gated (uncertain: <why>)`` and stays unclassified.

Admission resource wildcards are not the RBAC matcher. ``*`` matches resources
but not subresources; ``pods/*`` and ``*/exec`` match subresources only;
resourceNames apply to CREATE as well as other operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from prod_write_rbac import Target, selector_matches


_EQ = re.compile(r"""request\.userInfo\.username\s*==\s*['"]([^'"]+)['"]""")
_IN = re.compile(r"""request\.userInfo\.username\s+in\s+\[(.*)\]""", re.S)

_OPERATION = {
    "create": "CREATE",
    "update": "UPDATE",
    "patch": "UPDATE",
    "delete": "DELETE",
    "deletecollection": "DELETE",
    "get": "CONNECT",
}


@dataclass(frozen=True)
class PolicyHit:
    name: str
    verbs: tuple[str, ...]
    cel: str
    proven: bool
    uncertain: str = ""


@dataclass
class Policy:
    name: str
    match: dict
    conditions: list[dict]
    cel: str
    failure_policy: str = ""
    param_kind: str = ""


@dataclass
class PolicyBinding:
    name: str
    policy_name: str
    match: dict
    actions: tuple[str, ...] = field(default_factory=tuple)
    param_ref: str = ""


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
            param = spec.get("paramKind") or {}
            param_kind = ""
            if isinstance(param, dict) and (param.get("kind") or param.get("apiVersion")):
                param_kind = str(param.get("kind") or "param")
            policies[name] = Policy(
                name=name,
                match=spec.get("matchConstraints") or {},
                conditions=[item for item in (spec.get("matchConditions") or []) if isinstance(item, dict)],
                cel=validation_text(spec),
                failure_policy=str(spec.get("failurePolicy") or ""),
                param_kind=param_kind,
            )
        elif kind == "ValidatingAdmissionPolicyBinding" and name:
            actions = spec.get("validationActions") or []
            param_ref = spec.get("paramRef") or {}
            bindings.append(
                PolicyBinding(
                    name=name,
                    policy_name=str(spec.get("policyName") or ""),
                    match=spec.get("matchResources") or {},
                    actions=tuple(str(item) for item in actions),
                    param_ref="yes" if isinstance(param_ref, dict) and param_ref else "",
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
        read = {str(k): str(v) for k, v in (meta.get("labels") or {}).items()}
        # The apiserver stamps this label. It is known once the object was read.
        read.setdefault("kubernetes.io/metadata.name", name)
        labels[name] = read
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


def condition_state(conditions: list[dict], identity: str) -> str:
    """'yes' when every condition is true, 'no' when one is false, else 'unknown'."""
    state = "yes"
    for condition in conditions:
        allow = username_allowlist(str(condition.get("expression") or ""))
        if allow is None:
            state = "unknown"
            continue
        if identity not in allow:
            return "no"
    return state


def admission_resource_matches(rule_resources: tuple[str, ...], resource: str, subresource: str) -> bool:
    """ValidatingAdmissionPolicy resource wildcards. Not the RBAC helper.

    ``*`` matches every resource and not its subresources. ``*/*`` matches
    both. ``pods`` matches pods only. ``pods/*`` and ``*/exec`` match
    subresources only.
    """
    for item in rule_resources:
        if item in ("*", "*/*") and not subresource:
            return item == "*" or item == "*/*"
        if item == "*/*":
            return True
        if item == "*" and not subresource:
            return True
        if not subresource and item == resource:
            return True
        if subresource and item in (f"{resource}/{subresource}", f"{resource}/*", f"*/{subresource}"):
            return True
    return False


def _namespace_state(selector: dict | None, namespace: str, labels: dict[str, str], known: set[str]) -> str:
    """'yes', 'no', or an uncertainty reason."""
    if not selector:
        return "yes"
    if namespace == "":
        return "no"
    # kubernetes.io/metadata.name is the namespace name. Other labels count
    # only when the Namespace object was read.
    read = {"kubernetes.io/metadata.name": namespace}
    if namespace in known:
        read.update(labels)
    needed = set((selector.get("matchLabels") or {}))
    for expr in selector.get("matchExpressions") or []:
        needed.add(str(expr.get("key") or ""))
    if not needed <= set(read):
        return "namespace labels not read"
    if _selector_unknown(selector):
        return "namespace selector operator not read"
    if selector_matches(selector, read):
        return "yes"
    return "no"


def _selector_unknown(selector: dict) -> bool:
    known = {"In", "NotIn", "Exists", "DoesNotExist"}
    for expr in selector.get("matchExpressions") or []:
        if str(expr.get("operator") or "") not in known:
            return True
    return False


def _operation_ok(rule: dict, verb: str) -> bool:
    operation = _OPERATION.get(verb)
    if operation is None:
        return False
    operations = [str(item) for item in (rule.get("operations") or [])]
    return "*" in operations or operation in operations


def _listed(rule: dict, key: str) -> list[str]:
    return [str(item) for item in (rule.get(key) or [])]


def one_resource_rule(rule: dict, target: Target, verb: str) -> bool:
    if not _operation_ok(rule, verb):
        return False
    groups = _listed(rule, "apiGroups")
    if not groups or (target.api_group not in groups and "*" not in groups):
        return False
    versions = _listed(rule, "apiVersions")
    if target.api_version and (not versions or (target.api_version not in versions and "*" not in versions)):
        return False
    scope = str(rule.get("scope") or "*")
    if scope == "Cluster" and target.namespace != "":
        return False
    if scope == "Namespaced" and target.namespace == "":
        return False
    resources = tuple(_listed(rule, "resources"))
    if not resources or not admission_resource_matches(resources, target.resource, target.subresource):
        return False
    names = _listed(rule, "resourceNames")
    if names and (not target.name or target.name not in names):
        return False
    return True


def _rules_hit(rules: list | None, target: Target, verb: str, empty_means: bool) -> bool:
    if not rules:
        return empty_means
    return any(isinstance(rule, dict) and one_resource_rule(rule, target, verb) for rule in rules)


def _match_state(block: dict | None, target: Target, verb: str, ns_labels: dict[str, dict[str, str]], ns_known: set[str]) -> str:
    """'yes', 'no', or a reason the match cannot be proven."""
    if not block:
        return "yes"
    reasons = []
    if block.get("objectSelector"):
        reasons.append("objectSelector")
    namespace = target.namespace
    labels = ns_labels.get(namespace, {})
    ns_state = _namespace_state(block.get("namespaceSelector"), namespace, labels, ns_known)
    if ns_state == "no":
        return "no"
    if ns_state != "yes":
        reasons.append(ns_state)
    if not _rules_hit(block.get("resourceRules"), target, verb, empty_means=True):
        return "no"
    if _rules_hit(block.get("excludeResourceRules"), target, verb, empty_means=False):
        return "no"
    if reasons:
        return "; ".join(reasons)
    return "yes"


def _uncertain_reasons(policy: Policy, binding: PolicyBinding, identity: str) -> list[str]:
    reasons = []
    if "Deny" not in binding.actions:
        reasons.append("validationActions has no Deny")
    if policy.failure_policy != "Fail":
        reasons.append("failurePolicy is not Fail")
    if policy.param_kind or binding.param_ref:
        reasons.append("paramRef")
    state = condition_state(policy.conditions, identity)
    if state == "unknown":
        reasons.append("matchCondition")
    return reasons


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
    for binding in sorted(bindings, key=lambda item: (item.policy_name, item.name)):
        policy = policies.get(binding.policy_name)
        if policy is None:
            continue
        if condition_state(policy.conditions, identity) == "no":
            continue
        matched: list[str] = []
        uncertain: list[str] = []
        for verb in verbs:
            policy_state = _match_state(policy.match, target, verb, ns_labels, ns_known)
            binding_state = _match_state(binding.match, target, verb, ns_labels, ns_known)
            if policy_state == "no" or binding_state == "no":
                continue
            matched.append(verb)
            for state in (policy_state, binding_state):
                if state != "yes":
                    uncertain.append(state)
        if not matched:
            continue
        reasons = _uncertain_reasons(policy, binding, identity) + uncertain
        # Warn or Audit alone does not gate. A missing Deny is uncertain above
        # and is not a proven refusal; drop a binding that is only Warn/Audit
        # when Deny is absent and the actions are non-empty of those.
        if binding.actions and "Deny" not in binding.actions and set(binding.actions) <= {"Warn", "Audit"}:
            continue
        proven = not reasons
        why = "" if proven else "; ".join(dict.fromkeys(reasons))
        hits.append(PolicyHit(name=policy.name, verbs=tuple(matched), cel=policy.cel, proven=proven, uncertain=why))
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
        proven = current.proven and hit.proven
        why = "; ".join(part for part in (current.uncertain, hit.uncertain) if part)
        by_name[hit.name] = PolicyHit(name=hit.name, verbs=verbs, cel=cel, proven=proven, uncertain="" if proven else why)
    return [by_name[name] for name in sorted(by_name)]


def hits_for_verb(hits: list[PolicyHit], verb: str) -> list[PolicyHit]:
    return [hit for hit in hits if verb in hit.verbs]


def effect_refuses(effects: list[dict], policy_names: list[str], identity: str, field: str) -> bool:
    for effect in effects:
        if effect.get("effect") != "refuse":
            continue
        if effect.get("policy") not in policy_names:
            continue
        if str(effect.get("field") or "") != field:
            continue
        if effect.get("identity") not in (identity, "*"):
            continue
        return True
    return False


def validate_effects(effects: list[dict]) -> list[str]:
    problems = []
    for index, effect in enumerate(effects, start=1):
        kind = str(effect.get("effect") or "")
        if kind == "refuse":
            required = ("policy", "identity", "field", "effect", "note")
        elif kind == "restrict-serviceaccount":
            required = ("policy", "identity", "effect", "resources", "service_accounts", "note")
        else:
            problems.append(f"invalid-effect: entry {index} effect must be refuse or restrict-serviceaccount")
            continue
        missing = [key for key in required if not effect.get(key) and effect.get(key) != 0]
        missing = [key for key in required if effect.get(key) in (None, "", [])]
        if missing:
            problems.append(f"invalid-effect: entry {index} missing {', '.join(missing)}")
            continue
        field_name = str(effect.get("field") or "")
        if kind == "refuse" and (not field_name or "*" in field_name):
            problems.append(f"invalid-effect: entry {index} field must be an exact field")
    return problems
