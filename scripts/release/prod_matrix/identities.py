"""Section 3 identities. Contexts are copied from the table, not invented."""

from __future__ import annotations

from typing import Any

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


def _logical_commands(commands: list[dict]) -> list[dict]:
    return [command for command in commands if not command.get("retry_of")]


def _assert_pages(command: dict) -> None:
    pages = command["pages"]
    if not pages:
        raise MatrixExit(2, f"bundle: {command['id']}: missing page")
    if command["status_code"] == 410 or not command["ok"]:
        raise MatrixExit(2, f"bundle: {command['id']}: read failed ({command['status_code']})")
    for index, page in enumerate(pages):
        body = page["body"]
        token = page["continue"]
        if not isinstance(body, dict):
            raise MatrixExit(2, f"bundle: {command['id']}: page {index} is not an object")
        meta = body.get("metadata") or {}
        body_token = str(meta.get("continue") or "") if isinstance(meta, dict) else ""
        if token != body_token:
            raise MatrixExit(2, f"bundle: {command['id']}: page {index} continue does not match the body")
        if index < len(pages) - 1 and not token:
            raise MatrixExit(2, f"bundle: {command['id']}: missing page")
        if index == len(pages) - 1 and token:
            raise MatrixExit(2, f"bundle: {command['id']}: missing page")


def _items(commands: list[dict], path_prefix: str) -> list[dict]:
    matched = [
        command
        for command in _logical_commands(commands)
        if command["request"]["path"].split("?", 1)[0] == path_prefix
    ]
    if not matched:
        raise MatrixExit(2, f"bundle: missing command {path_prefix}")
    found: list[dict] = []
    for command in matched:
        _assert_pages(command)
        for page in command["pages"]:
            body = page["body"]
            items = body.get("items")
            if items is None:
                kind = str(body.get("kind") or "")
                if kind.endswith("List"):
                    items = []
                else:
                    raise MatrixExit(2, f"bundle: {command['id']}: list has no items")
            if not isinstance(items, list):
                raise MatrixExit(2, f"bundle: {command['id']}: items is not a list")
            found.extend(item for item in items if isinstance(item, dict))
    return found


def namespaces_of(commands: list[dict]) -> list[str]:
    names = []
    for item in _items(commands, "/api/v1/namespaces"):
        name = str((item.get("metadata") or {}).get("name") or "")
        if name:
            names.append(name)
    if not names:
        raise MatrixExit(2, "bundle: missing a namespace")
    return sorted(set(names))


def discovery_resources(commands: list[dict]) -> list[dict]:
    found: list[dict] = []
    saw = False
    for command in _logical_commands(commands):
        path = command["request"]["path"].split("?", 1)[0]
        core = path == "/api/v1"
        grouped = path.startswith("/apis/") and path.count("/") == 3
        if not core and not grouped:
            continue
        saw = True
        _assert_pages(command)
        for page in command["pages"]:
            body = page["body"]
            group_version = str(body.get("groupVersion") or "")
            group = group_version.split("/", 1)[0] if "/" in group_version else ""
            for resource in body.get("resources") or []:
                if not isinstance(resource, dict) or "name" not in resource:
                    continue
                raw_name = str(resource["name"])
                if "/" in raw_name:
                    parent, sub = raw_name.split("/", 1)
                else:
                    parent, sub = raw_name, ""
                found.append(
                    {
                        "group": group,
                        "resource": parent,
                        "subresource": sub,
                        "namespaced": bool(resource.get("namespaced", True)),
                        "named_subresource": "/" in raw_name,
                    }
                )
    if not saw:
        raise MatrixExit(2, "bundle: missing discovery")
    if not found:
        raise MatrixExit(2, "bundle: missing a subresource")
    return found


def inventory(commands: list[dict]) -> dict[str, Any]:
    namespaces = namespaces_of(commands)
    serviceaccounts = _items(commands, "/api/v1/serviceaccounts")
    nodes = _items(commands, "/api/v1/nodes")
    rolebindings = _items(commands, "/apis/rbac.authorization.k8s.io/v1/rolebindings")
    clusterrolebindings = _items(commands, "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings")
    _items(commands, "/apis/rbac.authorization.k8s.io/v1/roles")
    _items(commands, "/apis/rbac.authorization.k8s.io/v1/clusterroles")
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
        "resources": discovery_resources(commands),
    }


def assemble(lists: dict[str, Any], fixed_rows: list[dict]) -> list[dict]:
    by_user: dict[str, dict] = {}

    def add(ctx: dict, ask: bool) -> None:
        current = by_user.get(ctx["user"])
        if current is None or (current["context"]["uid"]["state"] != "known" and ctx["uid"]["state"] == "known"):
            by_user[ctx["user"]] = {"context": ctx, "ask": ask, "risk": False, "reason": ""}

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
            risks.append({"context": ctx, "ask": False, "risk": True, "reason": row["reason"], "id": row["id"]})
            continue
        add(ctx, ask)

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
