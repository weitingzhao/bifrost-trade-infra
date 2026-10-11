"""Single declaration of every data file, bundle part, and output row.

Validators and the README field table are generated from FIELDS. schema_version
is the integer 1. A missing required field, an unknown field, or a wrong type
exits 2 and names the file and the field.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from canon import SCHEMA_VERSION, MatrixExit

# (name, type, required, allowed)
# type: str, int, bool, date, json, list, object
# list and object may be "list:<item>" or "object:<nested>"
# allowed: a set of values, or None

_CONTEXT = (
    ("kind", "str", True, {"serviceaccount", "serviceaccount-unbound", "user", "node", "group-member", "anonymous", "fixed-risk"}),
    ("user", "str", True, None),
    ("groups", "list:str", True, None),
    ("uid", "object:uid", True, None),
    ("extra", "object:extra", True, None),
    ("source", "str", True, None),
)

_UID = (
    ("state", "str", True, {"known", "unknown"}),
    ("value", "str", False, None),
)

_EXTRA = (
    ("state", "str", True, {"known", "unknown"}),
    ("value", "object:extra-map", False, None),
)

_SCOPE = (("match", "str", True, {"all"}),)

_QUESTION = (
    ("identity_scope", "object:scope", True, None),
    ("group", "str", True, None),
    ("version", "str", True, None),
    ("resource", "str", True, None),
    ("subresource", "str", True, None),
    ("namespace", "str", True, None),
    ("scope", "str", True, {"namespaced", "cluster"}),
    ("name", "str", True, None),
    ("verb", "str", True, None),
)

_NONTARGET = (
    ("group", "str", True, None),
    ("resource", "str", True, None),
    ("subresource", "str", True, None),
    ("namespace", "str", True, None),
    ("scope", "str", True, {"namespaced", "cluster"}),
    ("reason", "str", True, None),
)

_EXCEPTION = (
    ("class", "str", True, {"trust-root", "field"}),
    ("identity", "object:context", True, None),
    ("group", "str", True, None),
    ("resource", "str", True, None),
    ("subresource", "str", True, None),
    ("namespace", "str", True, None),
    ("scope", "str", True, {"namespaced", "cluster"}),
    ("name", "str", True, None),
    ("verb", "str", True, None),
    ("request_family", "str", True, {"authz"}),
    ("field", "str", True, None),
    ("check", "str", True, None),
    ("expires", "date", True, None),
    ("removes", "str", True, None),
    ("reason", "str", True, None),
)

_KIND = {"serviceaccount", "serviceaccount-unbound", "user", "node", "group-member", "anonymous", "fixed-risk"}

# Conditional fields use a 5th item: the sibling that makes them required when true.
_FIXED_IDENTITY = (
    ("id", "str", True, None),
    ("record", "str", True, {"identity"}),
    ("kind", "str", True, _KIND),
    ("user", "str", True, None),
    ("groups", "list:str", True, None),
    ("uid", "object:uid", True, None),
    ("extra", "object:extra", True, None),
    ("source", "str", True, None),
    ("ask", "bool", True, None),
)

_FIXED_RISK = (
    ("id", "str", True, None),
    ("record", "str", True, {"risk"}),
    ("kind", "str", True, _KIND),
    ("source", "str", True, None),
    ("ask", "bool", True, None),
    ("reason", "str", True, None),
)

_FIXED_AUTH = (
    ("id", "str", True, None),
    ("record", "str", True, {"auth-chain"}),
    ("confirmed", "bool", True, None),
    ("by", "str", False, None, "confirmed"),
    ("at", "str", False, None, "confirmed"),
    ("evidence", "str", False, None, "confirmed"),
)

_REQUEST_PARAMS = (
    ("limit", "str", False, None),
    ("continue", "str", False, None),
)

_ATTEMPT_REQUEST = (
    ("method", "str", True, {"GET", "POST"}),
    ("path", "str", True, None),
    ("params", "object:request-params", True, None),
    ("body", "json", False, None),
)

_ATTEMPT_RESULT = (
    ("status_code", "int", True, None),
    ("ok", "bool", True, None),
    ("body", "json", True, None),
    ("body_sha256", "str", True, None),
)

_ATTEMPT = (
    ("attempt", "int", True, None),
    ("kind", "str", True, {"read", "review"}),
    ("request", "object:attempt-request", True, None),
    ("request_hash", "str", True, None),
    ("retry_of", "int", False, None),
    ("started_at", "str", True, None),
    ("finished_at", "str", True, None),
    ("result", "object:attempt-result", True, None),
)

_RESOURCE_ATTRS = (
    ("group", "str", True, None),
    ("version", "str", True, None),
    ("resource", "str", True, None),
    ("subresource", "str", True, None),
    ("namespace", "str", True, None),
    ("name", "str", True, None),
    ("verb", "str", True, None),
)

_SAR_SPEC = (
    ("user", "str", True, None),
    ("groups", "list:str", True, None),
    ("uid", "str", False, None),
    ("extra", "json", False, None),
    ("resourceAttributes", "object:resource-attributes", True, None),
)

_SAR_REQUEST = (
    ("apiVersion", "str", True, {"authorization.k8s.io/v1"}),
    ("kind", "str", True, {"SubjectAccessReview"}),
    ("spec", "object:sar-spec", True, None),
)

_BASELINE = (
    ("schema_version", "int", True, {1}),
    ("category", "str", True, {
        "binding",
        "role",
        "expanded-resource",
        "task",
        "admission",
        "namespace-label",
        "fixed-identity",
        "missing-input",
        "configmap",
        "manifest",
    }),
    ("namespace", "str", True, None),
    ("type", "str", True, None),
    ("name", "str", True, None),
    ("role_ref", "str", False, None),
    ("subjects", "list:str", False, None),
    ("labels", "json", False, None),
    ("aggregation_rule", "json", False, None),
    ("rules", "json", False, None),
    ("resources", "list:str", False, None),
    ("content_sha256", "str", False, None),
    ("data_keys", "list:str", False, None),
    ("service_account", "str", False, None),
    ("validation_actions", "list:str", False, None),
    ("spec_sha256", "str", False, None),
    ("reason", "str", False, None),
    ("input", "str", False, None),
    ("provider", "str", False, None),
    ("record", "json", False, None),
    ("source", "str", False, None),
)

_OUTPUT = (
    ("kind", "str", True, {"unclassified", "named-exception", "unknown-surface"}),
    ("reason", "str", True, None),
    ("row_key", "str", False, None),
    ("subject", "object:context", False, None),
    ("executor", "object:context", False, None),
    ("group", "str", False, None),
    ("version", "str", False, None),
    ("resource", "str", False, None),
    ("subresource", "str", False, None),
    ("namespace", "str", False, None),
    ("scope", "str", False, {"namespaced", "cluster"}),
    ("name", "str", False, None),
    ("verb", "str", False, None),
    ("request_family", "str", False, {"authz"}),
    ("only", "str", False, None),
    ("exception_class", "str", False, {"trust-root", "field"}),
)

# file id, filename, root field list, nested object lists
FIELDS: dict[str, dict[str, Any]] = {
    "prod_targets.json": {
        "root": (
            ("schema_version", "int", True, {1}),
            ("questions", "list:question", True, None),
        ),
        "nested": {"question": _QUESTION, "scope": _SCOPE},
    },
    "prod_nontargets.json": {
        "root": (
            ("schema_version", "int", True, {1}),
            ("entries", "list:nontarget", True, None),
        ),
        "nested": {"nontarget": _NONTARGET},
    },
    "prod_write_exceptions.json": {
        "root": (
            ("schema_version", "int", True, {1}),
            ("exceptions", "list:exception", True, None),
        ),
        "nested": {"exception": _EXCEPTION, "context": _CONTEXT, "uid": _UID, "extra": _EXTRA},
    },
    "prod_fixed_identities.json": {
        "root": (
            ("schema_version", "int", True, {1}),
            ("rows", "list:fixed-row", True, None),
        ),
        "nested": {
            "fixed-identity": _FIXED_IDENTITY,
            "fixed-risk": _FIXED_RISK,
            "fixed-auth-chain": _FIXED_AUTH,
            "uid": _UID,
            "extra": _EXTRA,
        },
    },
    "prod_write_baseline.jsonl": {
        "root": _BASELINE,
        "nested": {},
        "jsonl": True,
    },
    "bundle": {
        "root": (
            ("schema_version", "int", True, {1}),
            ("started_at", "str", True, None),
            ("finished_at", "str", True, None),
            ("caller", "object:context", True, None),
            ("tool_version", "str", True, None),
            ("attempts", "list:attempt", True, None),
        ),
        "nested": {
            "context": _CONTEXT,
            "uid": _UID,
            "extra": _EXTRA,
            "attempt": _ATTEMPT,
            "attempt-request": _ATTEMPT_REQUEST,
            "request-params": _REQUEST_PARAMS,
            "attempt-result": _ATTEMPT_RESULT,
            "sar-request": _SAR_REQUEST,
            "sar-spec": _SAR_SPEC,
            "resource-attributes": _RESOURCE_ATTRS,
        },
    },
    "output-row": {
        "root": _OUTPUT,
        "nested": {"context": _CONTEXT, "uid": _UID, "extra": _EXTRA},
    },
}

REQUIRED_FIXED_IDS = (
    "member-of-system-masters",
    "k3s-admin-credentials",
    "node-root",
    "anonymous",
    "auth-chain",
)


def _fail(filename: str, field: str, message: str) -> None:
    raise MatrixExit(2, f"{filename}: {field}: {message}")


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _check_value(filename: str, field: str, declared: str, value: Any, allowed: set | None) -> None:
    base = declared.split(":", 1)[0]
    if base == "json":
        return
    if base == "str":
        if not isinstance(value, str):
            _fail(filename, field, f"type {_type_name(value)}, expected str")
    elif base == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            _fail(filename, field, f"type {_type_name(value)}, expected int")
    elif base == "bool":
        if not isinstance(value, bool):
            _fail(filename, field, f"type {_type_name(value)}, expected bool")
    elif base == "date":
        if not isinstance(value, str):
            _fail(filename, field, f"type {_type_name(value)}, expected date")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            _fail(filename, field, f"invalid date {value!r}")
    elif base == "list":
        if not isinstance(value, list):
            _fail(filename, field, f"type {_type_name(value)}, expected list")
    elif base == "object":
        if not isinstance(value, dict):
            _fail(filename, field, f"type {_type_name(value)}, expected object")
    else:
        _fail(filename, field, f"unknown declared type {declared}")
    if allowed is not None and base in {"str", "int"} and value not in allowed:
        _fail(filename, field, f"value {value!r} not in {sorted(allowed)}")


def _nested(spec: dict[str, Any], name: str) -> tuple:
    table = spec.get("nested") or {}
    if name not in table:
        raise KeyError(name)
    return table[name]


def _parts(field: tuple) -> tuple:
    name, declared, required, allowed = field[:4]
    when = field[4] if len(field) > 4 else None
    return name, declared, required, allowed, when


def validate_object(filename: str, spec: dict[str, Any], obj_name: str, fields: tuple, value: Any) -> None:
    if not isinstance(value, dict):
        _fail(filename, obj_name, f"type {_type_name(value)}, expected object")
    declared = {item[0] for item in fields}
    for key in value:
        if key not in declared:
            _fail(filename, key, "unknown field")
    for field in fields:
        name, declared_type, required, allowed, when = _parts(field)
        needed = required or (when is not None and value.get(when) is True)
        if name not in value:
            if needed:
                message = "required when confirmed is true" if when else "missing required field"
                _fail(filename, name, message)
            continue
        if when is not None and value.get(when) is True and (not isinstance(value[name], str) or not value[name]):
            _fail(filename, name, "required when confirmed is true")
        _check_value(filename, name, declared_type, value[name], allowed)
        if declared_type.startswith("object:"):
            nested_name = declared_type.split(":", 1)[1]
            if nested_name == "extra-map":
                _validate_extra_map(filename, name, value[name])
            else:
                validate_object(filename, spec, name, _nested(spec, nested_name), value[name])
        elif declared_type.startswith("list:"):
            item_type = declared_type.split(":", 1)[1]
            for index, item in enumerate(value[name]):
                item_field = f"{name}[{index}]"
                if item_type == "str":
                    if not isinstance(item, str):
                        _fail(filename, item_field, f"type {_type_name(item)}, expected str")
                elif item_type == "fixed-row":
                    _validate_fixed_variant(filename, spec, item_field, item)
                elif item_type.startswith("object") or item_type in spec.get("nested", {}):
                    validate_object(filename, spec, item_field, _nested(spec, item_type), item)
                else:
                    _fail(filename, item_field, f"unknown item type {item_type}")
    if obj_name in {"uid", "extra"} or fields is _UID or fields is _EXTRA:
        _validate_state_value(filename, obj_name, value)


_FIXED_VARIANTS = {
    "identity": "fixed-identity",
    "risk": "fixed-risk",
    "auth-chain": "fixed-auth-chain",
}


def _validate_fixed_variant(filename: str, spec: dict[str, Any], field: str, row: Any) -> None:
    if not isinstance(row, dict):
        _fail(filename, field, f"type {_type_name(row)}, expected object")
    variant = _FIXED_VARIANTS.get(row.get("record"))
    if variant is None:
        _fail(filename, f"{field}.record", "unknown fixed record")
    validate_object(filename, spec, field, _nested(spec, variant), row)


def _validate_state_value(filename: str, field: str, value: dict) -> None:
    state = value.get("state")
    if state == "unknown" and "value" in value:
        _fail(filename, field, "unknown state must omit value")
    if state == "known" and "value" not in value:
        _fail(filename, field, "known state requires value")


def _validate_extra_map(filename: str, field: str, value: Any) -> None:
    if not isinstance(value, dict):
        _fail(filename, field, f"type {_type_name(value)}, expected object")
    for key, item in value.items():
        if not isinstance(key, str):
            _fail(filename, field, "extra key must be a string")
        if not isinstance(item, list) or not all(isinstance(part, str) for part in item):
            _fail(filename, f"{field}.{key}", "extra value must be a list of strings")


def validate_document(filename: str, value: Any) -> None:
    spec = FIELDS[filename]
    validate_object(filename, spec, filename, spec["root"], value)
    if filename == "prod_targets.json":
        _reject_star(filename, value)
    if filename == "prod_nontargets.json":
        for index, entry in enumerate(value["entries"]):
            if entry["resource"] == "*" or "*" in entry["resource"]:
                _fail(filename, f"entries[{index}].resource", "resource must not be a wildcard")
            if entry["namespace"] != "*" and "*" in entry["namespace"]:
                _fail(filename, f"entries[{index}].namespace", "namespace wildcard must be exactly *")
    if filename == "prod_write_exceptions.json":
        _reject_star(filename, value)
    if filename == "prod_fixed_identities.json":
        _validate_fixed_rows(filename, value)
    if filename == "bundle":
        _validate_states(filename, value["caller"])
        _validate_attempts(filename, spec, value["attempts"])


def _reject_star(filename: str, value: Any, field: str = "") -> None:
    """Wildcards are not stored. The one all-resource question is generated."""
    if isinstance(value, str) and "*" in value:
        _fail(filename, field or "value", "wildcard is not allowed")
    elif isinstance(value, dict):
        for key, item in value.items():
            _reject_star(filename, item, key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_star(filename, item, f"{field}[{index}]")


def _validate_attempts(filename: str, spec: dict[str, Any], attempts: list) -> None:
    """Review requests are our own SubjectAccessReview. Response bodies stay verbatim JSON."""
    for index, attempt in enumerate(attempts):
        if attempt.get("kind") != "review":
            continue
        body = attempt["request"].get("body")
        field = f"attempts[{index}].request.body"
        if not isinstance(body, dict):
            _fail(filename, field, "missing required field")
        validate_object(filename, spec, field, _nested(spec, "sar-request"), body)


def _validate_states(filename: str, context: dict) -> None:
    _validate_state_value(filename, "uid", context["uid"])
    _validate_state_value(filename, "extra", context["extra"])
    if context["extra"]["state"] == "known":
        _validate_extra_map(filename, "extra.value", context["extra"]["value"])


def _validate_fixed_rows(filename: str, doc: dict) -> None:
    seen = []
    for index, row in enumerate(doc["rows"]):
        field = f"rows[{index}]"
        seen.append(row["id"])
        record = row["record"]
        if record == "auth-chain" and row.get("confirmed") is True:
            try:
                datetime.strptime(row["at"], "%Y-%m-%dT%H:%M:%SZ")
            except (KeyError, ValueError):
                _fail(filename, f"{field}.at", "expected UTC time YYYY-MM-DDTHH:MM:SSZ")
        elif record == "risk" and row.get("ask") is not False:
            _fail(filename, f"{field}.ask", "risk rows are not asked")
    missing = [item for item in REQUIRED_FIXED_IDS if item not in seen]
    if missing:
        _fail(filename, "rows", "missing fixed identity " + ", ".join(missing))
    _check_known_contexts(filename, doc["rows"])


def _check_known_contexts(filename: str, rows: list[dict]) -> None:
    by_id = {row["id"]: row for row in rows}
    member = by_id["member-of-system-masters"]
    if member.get("user") != "prod-matrix:member-of:system:masters":
        _fail(filename, "member-of-system-masters.user", "must be the placeholder member")
    groups = member.get("groups") or []
    if "system:masters" not in groups or "system:authenticated" not in groups:
        _fail(filename, "member-of-system-masters.groups", "must include system:masters and system:authenticated")
    anon = by_id["anonymous"]
    if anon.get("user") != "system:anonymous" or anon.get("groups") != ["system:unauthenticated"]:
        _fail(filename, "anonymous", "user system:anonymous, group system:unauthenticated")
    uid = anon.get("uid") or {}
    extra = anon.get("extra") or {}
    if uid.get("state") != "known" or uid.get("value") != "":
        _fail(filename, "anonymous.uid", "known and empty")
    if extra.get("state") != "known" or extra.get("value") != {}:
        _fail(filename, "anonymous.extra", "known and empty")


def read_declared(path, key: str) -> Any:
    name = key if key in FIELDS else path.name
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MatrixExit(2, f"{name}: unreadable") from None
    except json.JSONDecodeError as exc:
        raise MatrixExit(2, f"{name}: invalid JSON ({exc})") from None
    validate_document(key, value)
    return value


def load_json(path, filename: str | None = None) -> Any:
    name = filename or path.name
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text)
    except FileNotFoundError:
        raise MatrixExit(2, f"{name}: unreadable") from None
    except json.JSONDecodeError as exc:
        raise MatrixExit(2, f"{name}: invalid JSON ({exc})") from None
    if name.endswith(".jsonl") or name == "prod_write_baseline.jsonl":
        raise MatrixExit(2, f"{name}: baseline is JSON lines, not one JSON value")
    validate_document(name if name in FIELDS else _file_key(name), value)
    return value


def _file_key(name: str) -> str:
    if name in FIELDS:
        return name
    raise MatrixExit(2, f"{name}: unknown file")


def load_json_file(path) -> Any:
    key = path.name if path.name in FIELDS else "bundle"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise MatrixExit(2, f"{path.name}: unreadable") from None
    except json.JSONDecodeError as exc:
        raise MatrixExit(2, f"{path.name}: invalid JSON ({exc})") from None
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        if isinstance(value, dict) and "schema_version" in value and value.get("schema_version") != SCHEMA_VERSION:
            raise MatrixExit(2, f"{path.name}: schema_version: unrecognized version")
    validate_document(key if path.name in FIELDS or key == "bundle" else path.name, value if path.name in FIELDS else value)
    if path.name not in FIELDS:
        validate_document("bundle", value)
    return value


def iter_field_rows() -> list[tuple[str, str, str, str, str, str]]:
    """Rows of (file, location, field, type, required, allowed) for the README table."""
    rows: list[tuple[str, str, str, str, str, str]] = []
    seen_nested: set[tuple[str, str]] = set()

    def add_fields(filename: str, location: str, fields: tuple) -> None:
        for field in fields:
            name, declared, required, allowed, _when = _parts(field)
            allowed_text = ""
            if isinstance(allowed, set):
                allowed_text = ", ".join(str(item) for item in sorted(allowed, key=str))
            rows.append((filename, location, name, declared, "yes" if required else "no", allowed_text))

    for filename, spec in FIELDS.items():
        add_fields(filename, "root", spec["root"])
        for nested_name, fields in spec.get("nested", {}).items():
            key = (filename, nested_name)
            if key in seen_nested:
                continue
            seen_nested.add(key)
            add_fields(filename, nested_name, fields)
    return rows


def field_table_markdown() -> str:
    lines = [
        "| 文件 | 位置 | 字段 | 类型 | 必填 | 允许值 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for file, location, name, declared, required, allowed in iter_field_rows():
        lines.append(f"| {file} | {location} | {name} | {declared} | {required} | {allowed} |")
    return "\n".join(lines) + "\n"


def table_in_readme(text: str) -> str:
    start = "<!-- field-table:start -->"
    end = "<!-- field-table:end -->"
    if start not in text or end not in text:
        raise MatrixExit(2, "README.md: field table markers missing")
    body = text.split(start, 1)[1].split(end, 1)[0]
    return body.strip() + "\n"
