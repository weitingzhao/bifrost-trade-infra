"""Section 3 identities. Contexts are copied from the table, not invented."""

from __future__ import annotations

from typing import Any

from canon import MatrixExit, sha256_hex


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


def _command_path(command: dict) -> str:
    return str(command["request"]["path"]).split("?", 1)[0]


def _validate_command_attempts(commands: list[dict]) -> None:
    """Every attempt has its own id. A retry points at an earlier attempt of the same request."""
    seen: dict[str, int] = {}
    for index, command in enumerate(commands):
        cid = command.get("id")
        if not isinstance(cid, str) or not cid:
            raise MatrixExit(2, "bundle: command missing id")
        if cid in seen:
            raise MatrixExit(2, f"bundle: {cid}: duplicate id")
        seen[cid] = index
        retry = command.get("retry_of")
        if not retry:
            continue
        if retry not in seen:
            raise MatrixExit(2, f"bundle: {cid}: retry_of does not point at an earlier attempt")
        earlier = commands[seen[retry]]
        if sha256_hex(earlier.get("request")) != sha256_hex(command.get("request")):
            raise MatrixExit(2, f"bundle: {cid}: retry hash does not match")


def _selected_commands(commands: list[dict]) -> list[dict]:
    """The result of a read is its last attempt. A later success replaces a failure."""
    _validate_command_attempts(commands)
    last: dict[str, dict] = {}
    order: list[str] = []
    for command in commands:
        path = _command_path(command)
        if path not in last:
            order.append(path)
        last[path] = command
    return [last[path] for path in order]


def _page_body(command: dict) -> dict:
    pages = command.get("pages") or []
    if not pages or not isinstance(pages[0], dict):
        raise MatrixExit(2, f"bundle: {command.get('id')}: missing page")
    body = pages[0].get("body")
    if not isinstance(body, dict):
        raise MatrixExit(2, f"bundle: {command.get('id')}: page 0 is not an object")
    return body


def discovery_paths_from(api: Any, apis: Any) -> list[str]:
    """Every served version named by the root discovery documents, not only the preferred one."""
    if not isinstance(api, dict) or not isinstance(apis, dict):
        return []
    versions = api.get("versions")
    groups = apis.get("groups")
    if not isinstance(versions, list) or not isinstance(groups, list):
        return []
    paths: list[str] = []
    for version in versions:
        if isinstance(version, str) and version:
            paths.append(f"/api/{version}")
    for group in groups:
        if not isinstance(group, dict):
            continue
        served = group.get("versions")
        if not isinstance(served, list) or not served:
            preferred = group.get("preferredVersion")
            served = [preferred] if isinstance(preferred, dict) else []
        for item in served:
            if isinstance(item, dict) and item.get("groupVersion"):
                paths.append(f"/apis/{item['groupVersion']}")
    unique: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def assert_discovery_complete(commands: list[dict]) -> None:
    """Root discovery must have succeeded, and every version it names must be present and ok."""
    by_path: dict[str, dict] = {}
    for command in commands:
        by_path[_command_path(command)] = command
    api = by_path.get("/api")
    apis = by_path.get("/apis")
    if api is None or not api.get("ok"):
        raise MatrixExit(2, "bundle: root discovery /api failed")
    if apis is None or not apis.get("ok"):
        raise MatrixExit(2, "bundle: root discovery /apis failed")
    expected = discovery_paths_from(_page_body(api), _page_body(apis))
    if not expected:
        raise MatrixExit(2, "bundle: root discovery failed")
    for path in expected:
        command = by_path.get(path)
        if command is None or not command.get("ok"):
            raise MatrixExit(2, f"bundle: missing discovery {path}")


def _assert_pages(command: dict) -> None:
    """The continue chain is the token each page was requested with, and the page count matches it."""
    pages = command["pages"]
    if not pages:
        raise MatrixExit(2, f"bundle: {command['id']}: missing page")
    if command["status_code"] == 410 or not command["ok"]:
        raise MatrixExit(2, f"bundle: {command['id']}: read failed ({command['status_code']})")
    previous = ""
    for index, page in enumerate(pages):
        body = page["body"]
        requested = page["continue"]
        if not isinstance(body, dict):
            raise MatrixExit(2, f"bundle: {command['id']}: page {index} is not an object")
        if not isinstance(requested, str):
            raise MatrixExit(2, f"bundle: {command['id']}: page {index} continue is not a string")
        if requested != previous:
            raise MatrixExit(2, f"bundle: {command['id']}: page count")
        meta = body.get("metadata") or {}
        if not isinstance(meta, dict):
            raise MatrixExit(2, f"bundle: {command['id']}: page {index} metadata is not an object")
        previous = str(meta.get("continue") or "")
    if previous:
        raise MatrixExit(2, f"bundle: {command['id']}: missing page")


def _items(commands: list[dict], path_prefix: str) -> list[dict]:
    matched = [command for command in commands if _command_path(command) == path_prefix]
    if not matched:
        raise MatrixExit(2, f"bundle: missing command {path_prefix}")
    found: list[dict] = []
    for command in matched:
        _assert_pages(command)
        for page in command["pages"]:
            body = page["body"]
            if "items" not in body:
                raise MatrixExit(2, f"bundle: {command['id']}: list has no items")
            items = body["items"]
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
    for command in commands:
        path = _command_path(command)
        core = path.startswith("/api/") and path.count("/") == 2
        grouped = path.startswith("/apis/") and path.count("/") == 3
        if not core and not grouped:
            continue
        saw = True
        _assert_pages(command)
        for page in command["pages"]:
            body = page["body"]
            group_version = str(body.get("groupVersion") or "")
            if "/" in group_version:
                group, version = group_version.split("/", 1)
            else:
                group, version = "", group_version
            for resource in body.get("resources") or []:
                if not isinstance(resource, dict) or "name" not in resource:
                    continue
                raw_name = str(resource["name"])
                if "/" in raw_name:
                    parent, sub = raw_name.split("/", 1)
                else:
                    parent, sub = raw_name, ""
                listed = resource.get("verbs") if isinstance(resource.get("verbs"), list) else []
                found.append(
                    {
                        "group": group,
                        "version": version,
                        "resource": parent,
                        "subresource": sub,
                        "namespaced": bool(resource.get("namespaced", True)),
                        "named_subresource": "/" in raw_name,
                        "verbs": [str(verb) for verb in listed],
                    }
                )
    if not saw:
        raise MatrixExit(2, "bundle: missing discovery")
    if not found:
        raise MatrixExit(2, "bundle: missing a subresource")
    return found


def inventory(commands: list[dict], *, require_discovery: bool = True) -> dict[str, Any]:
    selected = _selected_commands(commands)
    if require_discovery:
        assert_discovery_complete(selected)
    namespaces = namespaces_of(selected)
    serviceaccounts = _items(selected, "/api/v1/serviceaccounts")
    nodes = _items(selected, "/api/v1/nodes")
    rolebindings = _items(selected, "/apis/rbac.authorization.k8s.io/v1/rolebindings")
    clusterrolebindings = _items(selected, "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings")
    _items(selected, "/apis/rbac.authorization.k8s.io/v1/roles")
    _items(selected, "/apis/rbac.authorization.k8s.io/v1/clusterroles")
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
        "resources": discovery_resources(selected) if require_discovery else [],
    }


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
