"""Section 3 identities. Contexts are copied from the table, not invented."""

from __future__ import annotations

from typing import Any

from attempts import (
    last_reads,
    pages_for,
    parse_items,
    parse_resources,
    version_paths,
)
from canon import MatrixExit


def _uid_known(value: str) -> dict:
    return {"state": "known", "value": value}


def _uid_unknown() -> dict:
    return {"state": "unknown"}


def _extra_known(value: dict | None = None) -> dict:
    return {"state": "known", "value": value or {}}


def _extra_unknown() -> dict:
    return {"state": "unknown"}


def context(kind: str, user: str, groups: list[str], uid: dict, extra: dict, source: str) -> dict:
    return {
        "kind": kind,
        "user": user,
        "groups": sorted(set(groups)),
        "uid": uid,
        "extra": extra,
        "source": source,
    }


def group_member(group: str, source: str) -> dict:
    if group == "system:unauthenticated":
        groups = [group]
    else:
        groups = [group, "system:authenticated"]
    return context(
        "group-member",
        f"prod-matrix:member-of:{group}",
        groups,
        _uid_unknown(),
        _extra_unknown(),
        source,
    )


def service_account(namespace: str, name: str, uid: str | None, source: str, bound_only: bool) -> dict:
    groups = ["system:authenticated", "system:serviceaccounts", f"system:serviceaccounts:{namespace}"]
    uid_field = _uid_unknown() if uid is None else _uid_known(uid)
    kind = "serviceaccount-unbound" if bound_only else "serviceaccount"
    return context(kind, f"system:serviceaccount:{namespace}:{name}", groups, uid_field, _extra_unknown(), source)


def user_context(name: str, source: str) -> dict:
    return context("user", name, ["system:authenticated"], _uid_unknown(), _extra_unknown(), source)


def node_context(name: str, source: str) -> dict:
    return context(
        "node",
        f"system:node:{name}",
        ["system:authenticated", "system:nodes"],
        _uid_unknown(),
        _extra_unknown(),
        source,
    )


def fixed_identity(row: dict) -> tuple[dict, bool]:
    if row["record"] == "identity":
        ctx = context(row["kind"], row["user"], list(row["groups"]), row["uid"], row["extra"], row["source"])
        return ctx, bool(row["ask"])
    if row["record"] == "risk":
        ctx = context("fixed-risk", "", [], _uid_unknown(), _extra_unknown(), row["source"])
        return ctx, False
    raise MatrixExit(2, f"prod_fixed_identities.json: {row.get('id')}: not an identity row")


def discovery_paths_from(api: Any, apis: Any) -> list[str]:
    """Every served version named by root discovery. A malformed element is exit 2."""
    try:
        return version_paths(api, apis)
    except MatrixExit:
        raise
    except (AttributeError, TypeError, KeyError):
        raise MatrixExit(2, "bundle: root discovery failed") from None


def _chain_body(attempt: dict) -> Any:
    if not attempt["result"].get("ok"):
        raise MatrixExit(2, f"bundle: root discovery {attempt['request']['path']} failed")
    body = attempt["result"]["body"]
    if not isinstance(body, dict):
        raise MatrixExit(2, f"bundle: root discovery {attempt['request']['path']} failed")
    return body


def assert_discovery_complete(reads: dict[str, list[dict]]) -> list[str]:
    """Root discovery must have succeeded, and every version it names must be present and ok."""
    api = reads.get("/api")
    apis = reads.get("/apis")
    if not api:
        raise MatrixExit(2, "bundle: root discovery /api failed")
    if not apis:
        raise MatrixExit(2, "bundle: root discovery /apis failed")
    api_body = _chain_body(api[0])
    apis_body = _chain_body(apis[0])
    expected = discovery_paths_from(api_body, apis_body)
    if not expected:
        raise MatrixExit(2, "bundle: root discovery failed")
    for path in expected:
        group = reads.get(path)
        if not group or not group[0]["result"].get("ok"):
            raise MatrixExit(2, f"bundle: missing discovery {path}")
    return expected


def _items(reads: dict[str, list[dict]], path: str) -> list[dict]:
    found: list[dict] = []
    for attempt in pages_for(reads.get(path, []), path):
        found.extend(parse_items(attempt["result"]["body"], attempt))
    return found


def namespaces_of(reads: dict[str, list[dict]]) -> list[str]:
    names = []
    for item in _items(reads, "/api/v1/namespaces"):
        names.append(str(item["metadata"]["name"]))
    if not names:
        raise MatrixExit(2, "bundle: missing a namespace")
    return sorted(set(names))


def _group_version(path: str, body: dict) -> tuple[str, str]:
    group_version = body.get("groupVersion")
    if not isinstance(group_version, str) or not group_version:
        if path.startswith("/api/"):
            return "", path.rsplit("/", 1)[-1]
        raise MatrixExit(2, f"bundle: {path}: groupVersion is missing")
    if "/" in group_version:
        group, version = group_version.split("/", 1)
        return group, version
    return "", group_version


def discovery_resources(reads: dict[str, list[dict]], expected: list[str]) -> list[dict]:
    found: list[dict] = []
    for path in expected:
        for attempt in pages_for(reads.get(path, []), path):
            body = attempt["result"]["body"]
            if not isinstance(body, dict):
                raise MatrixExit(2, f"bundle: {path}: body is not an object")
            group, version = _group_version(path, body)
            for resource in parse_resources(body, path):
                found.append(
                    {
                        "group": group,
                        "version": version,
                        "resource": resource["parent"],
                        "subresource": resource["subresource"],
                        "namespaced": resource["namespaced"],
                        "named_subresource": "/" in resource["name"],
                        "verbs": resource["verbs"],
                    }
                )
    if not found:
        raise MatrixExit(2, "bundle: missing a subresource")
    return found


def inventory(attempts: list[dict], *, require_discovery: bool = True, chosen: dict[str, dict] | None = None) -> dict[str, Any]:
    """Reads come from attempt chains. chosen skips a second chain walk when replay already has one."""
    from attempts import chains

    reads = last_reads(chosen if chosen is not None else chains(attempts))
    expected = assert_discovery_complete(reads) if require_discovery else []
    namespaces = namespaces_of(reads)
    serviceaccounts = _items(reads, "/api/v1/serviceaccounts")
    nodes = _items(reads, "/api/v1/nodes")
    rolebindings = _items(reads, "/apis/rbac.authorization.k8s.io/v1/rolebindings")
    clusterrolebindings = _items(reads, "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings")
    _items(reads, "/apis/rbac.authorization.k8s.io/v1/roles")
    _items(reads, "/apis/rbac.authorization.k8s.io/v1/clusterroles")
    referenced: set[str] = set()
    for item in serviceaccounts + rolebindings:
        namespace = str((item.get("metadata") or {}).get("namespace") or "")
        if namespace:
            referenced.add(namespace)
        for subject in item.get("subjects") or []:
            if isinstance(subject, dict) and subject.get("namespace"):
                referenced.add(str(subject["namespace"]))
    missing = sorted(name for name in referenced if name not in namespaces)
    if missing:
        raise MatrixExit(2, "bundle: missing a namespace: " + ", ".join(missing))
    return {
        "namespaces": namespaces,
        "serviceaccounts": serviceaccounts,
        "nodes": nodes,
        "rolebindings": rolebindings,
        "clusterrolebindings": clusterrolebindings,
        "resources": discovery_resources(reads, expected) if require_discovery else [],
    }


def assert_target_namespaces(namespaces: list[str], questions: list[dict], fixed_rows: list[dict]) -> None:
    """Every namespace named by a target, an explicit question, or a fixed identity must be listed."""
    known = set(namespaces)
    missing: set[str] = set()
    for question in questions:
        if question.get("wildcard"):
            continue
        namespace = "" if question.get("scope") == "cluster" else question.get("namespace") or ""
        if namespace and namespace not in known:
            missing.add(namespace)
    for row in fixed_rows:
        user = str(row.get("user") or "")
        if not user.startswith("system:serviceaccount:"):
            continue
        parts = user.split(":")
        if len(parts) >= 4 and parts[2] and parts[2] not in known:
            missing.add(parts[2])
    if missing:
        raise MatrixExit(2, "bundle: missing a namespace: " + ", ".join(sorted(missing)))


def assemble(lists: dict[str, Any], fixed_rows: list[dict]) -> list[dict]:
    by_user: dict[str, dict] = {}

    def add(ctx: dict, ask: bool, fixed_id: str = "", reason: str = "") -> None:
        current = by_user.get(ctx["user"])
        if current is None:
            by_user[ctx["user"]] = {
                "context": ctx,
                "ask": ask,
                "risk": False,
                "reason": reason,
                "fixed_id": fixed_id,
            }
            return
        if current["context"]["uid"]["state"] != "known" and ctx["uid"]["state"] == "known":
            current["context"] = ctx
        if ask:
            current["ask"] = True
        if fixed_id:
            current["fixed_id"] = fixed_id
            if reason:
                current["reason"] = reason

    sa_users: set[str] = set()
    for item in lists["serviceaccounts"]:
        meta = item.get("metadata") or {}
        name = str(meta.get("name") or "")
        namespace = str(meta.get("namespace") or "")
        if not name or not namespace:
            continue
        uid = meta.get("uid")
        user = f"system:serviceaccount:{namespace}:{name}"
        sa_users.add(user)
        add(
            service_account(
                namespace,
                name,
                str(uid) if uid else None,
                f"serviceaccount-object:{namespace}/{name}",
                False,
            ),
            True,
        )

    def absorb_binding(item: dict) -> None:
        for subject in item.get("subjects") or []:
            if not isinstance(subject, dict):
                continue
            kind = str(subject.get("kind") or "")
            name = str(subject.get("name") or "")
            if not name:
                continue
            if kind == "ServiceAccount":
                namespace = str(subject.get("namespace") or (item.get("metadata") or {}).get("namespace") or "")
                user = f"system:serviceaccount:{namespace}:{name}"
                if user not in sa_users and user not in by_user:
                    add(
                        service_account(namespace, name, None, f"binding-without-object:{namespace}/{name}", True),
                        True,
                    )
            elif kind == "User":
                add(user_context(name, f"binding-user:{name}"), True)
            elif kind == "Group":
                add(group_member(name, f"group-member:{name}"), True)

    for item in lists["rolebindings"] + lists["clusterrolebindings"]:
        absorb_binding(item)
    for item in lists["nodes"]:
        name = str((item.get("metadata") or {}).get("name") or "")
        if name:
            add(node_context(name, f"node:{name}"), True)

    risks: list[dict] = []
    for row in fixed_rows:
        if row["record"] == "auth-chain":
            continue
        ctx, ask = fixed_identity(row)
        if row["record"] == "risk":
            risks.append(
                {
                    "context": ctx,
                    "ask": False,
                    "risk": True,
                    "reason": row["reason"],
                    "id": row["id"],
                    "fixed_id": row["id"],
                }
            )
            continue
        add(ctx, ask, row["id"], "fixed identity")

    identities = list(by_user.values()) + risks
    identities.sort(key=lambda item: (item["context"]["kind"], item["context"]["user"], item["context"]["source"]))
    return identities


def check_review_context(spec: dict) -> None:
    """Reject a recorded question that violates the section 3 context table."""
    user = str(spec.get("user") or "")
    groups = spec.get("groups") or []
    if not isinstance(groups, list):
        raise MatrixExit(2, "bundle: review groups are not a list")
    if user.startswith("system:node:"):
        if "system:nodes" not in groups or "system:authenticated" not in groups:
            raise MatrixExit(2, f"bundle: node question for {user} is missing a required group")
        if "uid" in spec or "extra" in spec:
            raise MatrixExit(2, f"bundle: node question for {user} carries uid or extra")
    if user.startswith("prod-matrix:member-of:"):
        group = user.split("prod-matrix:member-of:", 1)[1]
        expected = [group] if group == "system:unauthenticated" else sorted({group, "system:authenticated"})
        if sorted(set(str(item) for item in groups)) != expected:
            raise MatrixExit(2, f"bundle: member question for {user} has the wrong groups")
        if "uid" in spec or "extra" in spec:
            raise MatrixExit(2, f"bundle: member question for {user} carries uid or extra")
