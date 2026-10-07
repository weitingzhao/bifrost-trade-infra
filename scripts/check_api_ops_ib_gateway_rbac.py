#!/usr/bin/env python3
"""TD-104 ratchet: api-ops can get data/ib-gateway and nothing else in that Role.

    python3 scripts/check_api_ops_ib_gateway_rbac.py
    python3 scripts/check_api_ops_ib_gateway_rbac.py --self-test
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "k8s" / "data" / "api-ops-ib-gateway-rbac.yaml"

_REQUIRED_SUBJECTS = (
    ("api-ops", "bifrost-prod"),
    ("api-ops", "bifrost-stg"),
    ("api-ops", "bifrost-dev"),
)
_FORBIDDEN = ("list", "watch", "create", "update", "patch", "delete", "*")


def _docs(text: str) -> list[str]:
    parts = []
    buf: list[str] = []
    for line in text.splitlines():
        if line.strip() == "---":
            if buf:
                parts.append("\n".join(buf))
                buf = []
            continue
        buf.append(line)
    if buf:
        parts.append("\n".join(buf))
    return [part for part in parts if part.strip()]


def _kind(doc: str) -> str:
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.startswith("kind:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def _non_comment_lines(doc: str) -> list[str]:
    out = []
    for line in doc.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        out.append(line)
    return out


def check_manifest(text: str) -> list[str]:
    """Return human-readable errors. Empty means the manifest is the allowed Role."""
    errors: list[str] = []
    docs = _docs(text)
    kinds = [_kind(doc) for doc in docs]
    if kinds != ["Role", "RoleBinding"]:
        errors.append(f"expected Role then RoleBinding, got {kinds}")
        return errors
    role, binding = docs
    for label, doc in (("Role", role), ("RoleBinding", binding)):
        body = "\n".join(_non_comment_lines(doc))
        if "namespace: data" not in body:
            errors.append(f"{label} is not in namespace data")
        for word in _FORBIDDEN:
            if word in body:
                errors.append(f"{label} contains forbidden token {word!r}")
    role_body = "\n".join(_non_comment_lines(role))
    for needle in (
        'apiGroups: ["apps"]',
        'resources: ["deployments"]',
        'resourceNames: ["ib-gateway"]',
        'verbs: ["get"]',
    ):
        if needle not in role_body:
            errors.append(f"Role is missing {needle}")
    if role_body.count("resourceNames:") != 1:
        errors.append("Role must name exactly one resourceNames entry")
    binding_body = "\n".join(_non_comment_lines(binding))
    if "kind: Role" not in binding_body or "name: api-ops-ib-gateway-reader" not in binding_body:
        errors.append("RoleBinding does not point at api-ops-ib-gateway-reader")
    for name, namespace in _REQUIRED_SUBJECTS:
        block = f"name: {name}\n    namespace: {namespace}"
        if block not in binding_body:
            errors.append(f"RoleBinding is missing ServiceAccount {namespace}/{name}")
    if binding_body.count("kind: ServiceAccount") != len(_REQUIRED_SUBJECTS):
        errors.append("RoleBinding subject count is not the three api-ops accounts")
    return errors


def _self_test() -> int:
    ok = (MANIFEST.read_text(encoding="utf-8"))
    failed = 0
    if check_manifest(ok):
        print("self-test: real manifest should pass")
        failed += 1
    extra = ok.replace('verbs: ["get"]', 'verbs: ["get", "list"]')
    if not any("forbidden token 'list'" in err for err in check_manifest(extra)):
        print("self-test: adding list should fail")
        failed += 1
    dropped = ok.replace(
        "  - kind: ServiceAccount\n    name: api-ops\n    namespace: bifrost-dev\n",
        "",
    )
    if not any("bifrost-dev" in err for err in check_manifest(dropped)):
        print("self-test: dropping bifrost-dev should fail")
        failed += 1
    if failed:
        return 1
    print("self-test ok")
    return 0


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _self_test()
    errors = check_manifest(MANIFEST.read_text(encoding="utf-8"))
    if errors:
        for err in errors:
            print(err)
        return 1
    print(f"ok {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
