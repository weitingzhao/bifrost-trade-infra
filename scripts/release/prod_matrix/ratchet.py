"""Repository ratchet over k8s/. Line-for-line baseline. It does not classify."""

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

import yaml

from canon import SCHEMA_VERSION, MatrixExit, dump_line, sha256_hex
from schema import read_declared, validate_document

_KINDS_BINDING = {"RoleBinding", "ClusterRoleBinding"}
_KINDS_ROLE = {"Role", "ClusterRole"}
_KINDS_ADMISSION = {
    "ValidatingAdmissionPolicy",
    "ValidatingAdmissionPolicyBinding",
    "MutatingAdmissionPolicy",
    "MutatingAdmissionPolicyBinding",
    "ValidatingWebhookConfiguration",
    "MutatingWebhookConfiguration",
}
_LIST_KEYS = ("apiGroups", "nonResourceURLs", "resourceNames", "resources", "verbs")
_VOLATILE_META = ("resourceVersion", "uid", "creationTimestamp", "managedFields", "generation")
_WEBHOOK_KINDS = {"ValidatingWebhookConfiguration", "MutatingWebhookConfiguration"}


def _meta(doc: dict) -> dict:
    meta = doc.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _labels(meta: dict) -> dict:
    labels = meta.get("labels") or {}
    if not isinstance(labels, dict):
        return {}
    return {str(key): "" if value is None else str(value) for key, value in labels.items()}


def _rules(rules) -> list:
    if not isinstance(rules, list):
        return []
    normalized = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        item = {}
        for key, value in rule.items():
            if key in _LIST_KEYS and isinstance(value, list):
                item[key] = sorted("" if part is None else str(part) for part in value)
            else:
                item[key] = value
        normalized.append(item)
    return normalized


def _row(category: str, namespace: str, kind: str, name: str, source: str, **extra) -> dict:
    row = {
        "category": category,
        "name": name,
        "namespace": namespace or "",
        "schema_version": SCHEMA_VERSION,
        "source": source,
        "type": kind,
    }
    row.update(extra)
    return row


def _subject(subject: dict, default_namespace: str) -> str:
    kind = str(subject.get("kind") or "")
    name = str(subject.get("name") or "")
    namespace = str(subject.get("namespace") or "")
    if kind == "ServiceAccount":
        return f"ServiceAccount/{namespace or default_namespace}/{name}"
    return f"{kind}/{name}"


def _binding(doc: dict, source: str) -> dict:
    meta = _meta(doc)
    namespace = str(meta.get("namespace") or "")
    role_ref = doc.get("roleRef") or {}
    subjects = doc.get("subjects") or []
    rendered = []
    if isinstance(subjects, list):
        for subject in subjects:
            if isinstance(subject, dict):
                rendered.append(_subject(subject, namespace))
    return _row(
        "binding",
        namespace,
        str(doc.get("kind") or ""),
        str(meta.get("name") or ""),
        source,
        role_ref=f"{role_ref.get('kind') or ''}/{role_ref.get('name') or ''}",
        subjects=sorted(rendered),
    )


def _role(doc: dict, source: str) -> dict:
    meta = _meta(doc)
    aggregation = doc.get("aggregationRule")
    return _row(
        "role",
        str(meta.get("namespace") or ""),
        str(doc.get("kind") or ""),
        str(meta.get("name") or ""),
        source,
        aggregation_rule=aggregation if isinstance(aggregation, dict) else None,
        labels=_labels(meta),
        rules=_rules((doc.get("rules") or [])),
    )


def _crd_rows(doc: dict, source: str) -> list[dict]:
    meta = _meta(doc)
    spec = doc.get("spec") or {}
    group = str(spec.get("group") or "")
    plural = str((spec.get("names") or {}).get("plural") or meta.get("name") or "")
    subs: set[str] = set()
    for version in spec.get("versions") or []:
        if isinstance(version, dict) and isinstance(version.get("subresources"), dict):
            subs.update(str(name) for name in version["subresources"])
    names = [""] + sorted(subs)
    rows = []
    crd_name = str(meta.get("name") or plural)
    for sub in names:
        label = f"{crd_name}/{sub}" if sub else crd_name
        rows.append(
            _row(
                "expanded-resource",
                "",
                "CustomResourceDefinition",
                label,
                source,
                resources=[f"{group}/{plural}/{sub}"],
            )
        )
    return rows


def _service_account(doc: dict) -> str:
    spec = doc.get("spec") or {}
    if doc.get("kind") == "Task":
        return str(spec.get("serviceAccountName") or "")
    parts = []
    for task in spec.get("tasks") or []:
        if isinstance(task, dict):
            parts.append(f"{task.get('name')}={task.get('serviceAccountName') or ''}")
    return ",".join(parts)


def _task(doc: dict, source: str) -> dict:
    meta = _meta(doc)
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
    return _row(
        "task",
        str(meta.get("namespace") or ""),
        str(doc.get("kind") or ""),
        str(meta.get("name") or ""),
        source,
        content_sha256=sha256_hex(spec),
        service_account=_service_account(doc),
    )


def _strip(doc: dict) -> dict:
    cleaned = copy.deepcopy(doc)
    meta = cleaned.get("metadata")
    if isinstance(meta, dict):
        for key in _VOLATILE_META:
            meta.pop(key, None)
    cleaned.pop("status", None)
    return cleaned


def _effective(doc: dict):
    """Fields that take effect, per kind. Unlisted kinds keep the object minus volatile metadata and status."""
    kind = str(doc.get("kind") or "")
    if kind in _WEBHOOK_KINDS:
        return doc.get("webhooks") or []
    if kind in _KINDS_ROLE:
        return doc.get("rules") or []
    if kind in _KINDS_BINDING:
        return {"roleRef": doc.get("roleRef"), "subjects": doc.get("subjects")}
    if kind == "ConfigMap":
        data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        binary = doc.get("binaryData") if isinstance(doc.get("binaryData"), dict) else {}
        return sorted(set(data) | set(binary))
    if isinstance(doc.get("spec"), dict):
        return doc["spec"]
    return _strip(doc)


def _configmap(doc: dict, source: str) -> dict:
    meta = _meta(doc)
    return _row(
        "configmap",
        str(meta.get("namespace") or ""),
        "ConfigMap",
        str(meta.get("name") or ""),
        source,
        data_keys=_effective(doc),
    )


def _manifest(doc: dict, source: str) -> dict:
    meta = _meta(doc)
    return _row(
        "manifest",
        str(meta.get("namespace") or ""),
        str(doc.get("kind") or ""),
        str(meta.get("name") or ""),
        source,
        content_sha256=sha256_hex(_effective(doc)),
    )


def _admission(doc: dict, source: str) -> dict:
    meta = _meta(doc)
    spec = doc.get("spec") if isinstance(doc.get("spec"), dict) else {}
    extra = {"spec_sha256": sha256_hex(_effective(doc))}
    actions = spec.get("validationActions")
    if isinstance(actions, list):
        extra["validation_actions"] = sorted(str(item) for item in actions)
    return _row(
        "admission",
        str(meta.get("namespace") or ""),
        str(doc.get("kind") or ""),
        str(meta.get("name") or ""),
        source,
        **extra,
    )


def _namespace(doc: dict, source: str) -> dict:
    meta = _meta(doc)
    name = str(meta.get("name") or "")
    return _row("namespace-label", name, "Namespace", name, source, labels=_labels(meta))


def _fixed_rows(path: Path) -> list[dict]:
    document = read_declared(path, "prod_fixed_identities.json")
    rows = []
    for row in document["rows"]:
        rows.append(
            _row("fixed-identity", "", str(row.get("record") or ""), str(row.get("id") or ""), path.name, record=row)
        )
    return rows


def _missing_inputs() -> list[dict]:
    specs = (
        ("side-effecting-tasks", "slice-B", "not provided"),
        ("discovery-inventory", "measurement", "not provided"),
        ("credential-holders", "owner", "not provided"),
    )
    rows = []
    for name, provider, reason in specs:
        rows.append(
            _row(
                "missing-input",
                "",
                "missing-input",
                name,
                "",
                input=name,
                provider=provider,
                reason=reason,
            )
        )
    return rows


def scan(root: Path, fixed_path: Path) -> list[dict]:
    rows: list[dict] = []
    files = sorted(path for path in root.rglob("*") if path.suffix.lower() in {".yaml", ".yml"} and path.is_file())
    for path in files:
        source = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
            docs = list(yaml.safe_load_all(text))
        except (OSError, yaml.YAMLError) as exc:
            raise MatrixExit(2, f"{source}: {exc}") from None
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            kind = str(doc.get("kind") or "")
            if kind in _KINDS_BINDING:
                rows.append(_binding(doc, source))
            elif kind in _KINDS_ROLE:
                rows.append(_role(doc, source))
            elif kind == "CustomResourceDefinition":
                rows.extend(_crd_rows(doc, source))
            elif kind in {"Task", "Pipeline"}:
                rows.append(_task(doc, source))
            elif kind in _KINDS_ADMISSION:
                rows.append(_admission(doc, source))
            elif kind == "Namespace":
                rows.append(_namespace(doc, source))
            elif kind == "ConfigMap":
                rows.append(_configmap(doc, source))
            elif kind:
                rows.append(_manifest(doc, source))
    rows.extend(_fixed_rows(fixed_path))
    rows.extend(_missing_inputs())
    rows.sort(key=lambda row: (row["category"], row["namespace"], row["type"], row["name"], row.get("source", "")))
    return rows


def lines_of(rows: list[dict]) -> list[str]:
    return [dump_line(row) for row in rows]


def read_baseline(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MatrixExit(2, f"baseline unreadable: {exc}") from None
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise MatrixExit(2, "baseline unreadable: empty")
    for index, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MatrixExit(2, f"baseline: line {index}: invalid JSON ({exc})") from None
        validate_document("prod_write_baseline.jsonl", value)
    return lines


def _describe(prefix: str, line: str) -> str:
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return f"{prefix} {line}"
    return f"{prefix} {row['category']} {row['namespace']} {row['type']} {row['name']}"


def diff(tree: list[str], baseline: list[str]) -> list[str]:
    """Equal as sequences. A different order or a repeated row is its own failure."""
    if tree == baseline:
        return []
    tree_counts = Counter(tree)
    base_counts = Counter(baseline)
    if tree_counts == base_counts:
        return ["顺序不同"]
    if set(tree_counts) == set(base_counts):
        return ["重复一行"]
    messages = []
    for line, count in tree_counts.items():
        if count > base_counts.get(line, 0):
            messages.append(_describe("多出一行", line))
    for line, count in base_counts.items():
        if count > tree_counts.get(line, 0):
            messages.append(_describe("少一行", line))
    return messages
