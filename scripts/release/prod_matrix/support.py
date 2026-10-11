"""Builders for recorded bundles. Not collected as a test."""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

from canon import TOOL_VERSION
from classify import replay
from exceptions import parse_today
from identities import assemble, context, inventory
from questions import expand, sar_body
from schema import read_declared

HERE = Path(__file__).resolve().parent
DAY = date(2026, 10, 11)


def load_defaults():
    return (
        read_declared(HERE / "prod_targets.json", "prod_targets.json"),
        read_declared(HERE / "prod_fixed_identities.json", "prod_fixed_identities.json"),
        read_declared(HERE / "prod_write_exceptions.json", "prod_write_exceptions.json"),
        read_declared(HERE / "prod_nontargets.json", "prod_nontargets.json"),
    )


def command(index: int, path: str, body: dict) -> dict:
    return {
        "finished_at": "2026-10-11T00:00:01Z",
        "id": f"c-{index:04d}",
        "ok": True,
        "pages": [{"body": body, "continue": ""}],
        "request": {"method": "GET", "params": {}, "path": path},
        "started_at": "2026-10-11T00:00:00Z",
        "status_code": 200,
    }


def resource_list(kind: str, items: list) -> dict:
    return {"items": items, "kind": kind, "metadata": {"continue": ""}}


def discovery(group_version: str, resources: list[dict]) -> dict:
    return {
        "groupVersion": group_version,
        "kind": "APIResourceList",
        "metadata": {"continue": ""},
        "resources": resources,
    }


def res(name: str, verbs: list[str] | None = None, namespaced: bool = True) -> dict:
    return {"name": name, "namespaced": namespaced, "verbs": verbs or ["create", "patch", "update", "delete"]}


def base_commands(namespaces: list[str], bindings: list | None = None, sas: list | None = None, nodes: list | None = None) -> list[dict]:
    return [
        command(1, "/api/v1/namespaces", resource_list("NamespaceList", [{"metadata": {"name": name}} for name in namespaces])),
        command(2, "/api/v1/serviceaccounts", resource_list("ServiceAccountList", sas or [])),
        command(3, "/api/v1/nodes", resource_list("NodeList", nodes or [])),
        command(4, "/apis/rbac.authorization.k8s.io/v1/roles", resource_list("RoleList", [])),
        command(
            5,
            "/apis/rbac.authorization.k8s.io/v1/rolebindings",
            resource_list("RoleBindingList", bindings or []),
        ),
        command(6, "/apis/rbac.authorization.k8s.io/v1/clusterroles", resource_list("ClusterRoleList", [])),
        command(7, "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings", resource_list("ClusterRoleBindingList", [])),
    ]


def caller() -> dict:
    return context(
        "serviceaccount",
        "system:serviceaccount:bifrost-access:bifrost-agent",
        ["system:authenticated"],
        {"state": "unknown"},
        {"state": "unknown"},
        "kubectl-auth-whoami",
    )


def ensure_root_discovery(commands: list[dict]) -> list[dict]:
    """Replay derives the discovery paths from /api and /apis. Test bundles record both."""
    commands = list(commands)
    paths = {item["request"]["path"].split("?", 1)[0] for item in commands}
    core: list[str] = []
    grouped: dict[str, list[str]] = {}
    for item in commands:
        path = item["request"]["path"].split("?", 1)[0]
        if path.startswith("/api/") and path.count("/") == 2:
            core.append(path.split("/")[-1])
        elif path.startswith("/apis/") and path.count("/") == 3:
            group_version = path[len("/apis/") :]
            group = group_version.split("/", 1)[0]
            bucket = grouped.setdefault(group, [])
            if group_version not in bucket:
                bucket.append(group_version)
    extra = []
    if "/api" not in paths:
        extra.append(command(9101, "/api", {"kind": "APIVersions", "versions": core or ["v1"]}))
    if "/apis" not in paths:
        groups = []
        for group, versions in grouped.items():
            entries = [{"groupVersion": group_version, "version": group_version.split("/", 1)[-1]} for group_version in versions]
            groups.append({"name": group, "preferredVersion": entries[0], "versions": entries})
        extra.append(command(9102, "/apis", {"kind": "APIGroupList", "groups": groups}))
    if not extra:
        return commands
    insert_at = len(commands)
    for index, item in enumerate(commands):
        path = item["request"]["path"].split("?", 1)[0]
        core = path.startswith("/api/") and path.count("/") == 2
        grouped = path.startswith("/apis/") and path.count("/") == 3
        if core or grouped:
            insert_at = index
            break
    return commands[:insert_at] + extra + commands[insert_at:]


def bundle_from(commands: list[dict], targets: dict, fixed: dict, answer) -> dict:
    commands = ensure_root_discovery(commands)
    lists = inventory(commands)
    identities = assemble(lists, fixed["rows"])
    planned = expand(identities, targets["questions"])
    reviews = []
    for item in planned:
        status = answer(item)
        response = {
            "apiVersion": "authorization.k8s.io/v1",
            "kind": "SubjectAccessReview",
            "request_hash": item["request_hash"],
            "status": status,
        }
        reviews.append(
            {
                "id": item["id"],
                "request": sar_body(item["spec"]),
                "request_hash": item["request_hash"],
                "response": response,
            }
        )
    return {
        "caller": caller(),
        "commands": commands,
        "finished_at": "2026-10-11T00:00:02Z",
        "reviews": reviews,
        "schema_version": 1,
        "started_at": "2026-10-11T00:00:00Z",
        "tool_version": TOOL_VERSION,
    }


def run(bundle, targets, fixed, exceptions, nontargets, today: str = "2026-10-11"):
    return replay(bundle, targets, fixed, exceptions, nontargets, parse_today(today))


def rows(text: str) -> list[dict]:
    import json

    return [json.loads(line) for line in text.splitlines() if line.startswith("{")]


def denied_status() -> dict:
    return {"allowed": False, "denied": True}


def allowed_status() -> dict:
    return {"allowed": True, "denied": False}


def question(group: str, version: str, resource: str, sub: str, namespace: str, scope: str, name: str, verb: str) -> dict:
    return {
        "group": group,
        "identity_scope": {"match": "all"},
        "name": name,
        "namespace": namespace,
        "resource": resource,
        "scope": scope,
        "subresource": sub,
        "verb": verb,
        "version": version,
    }


def targets_of(questions: list[dict]) -> dict:
    return {"questions": questions, "schema_version": 1}


def empty_exceptions() -> dict:
    return {"exceptions": [], "schema_version": 1}


def empty_nontargets() -> dict:
    return {"entries": [], "schema_version": 1}


def copy_fixed(confirmed: bool = False) -> dict:
    _targets, fixed, _exceptions, _nontargets = load_defaults()
    doc = copy.deepcopy(fixed)
    for row in doc["rows"]:
        if row["id"] == "auth-chain":
            row["confirmed"] = confirmed
            if confirmed:
                row["at"] = "2026-10-11T00:00:00Z"
                row["by"] = "owner"
                row["evidence"] = "k3s startup arguments reviewed"
    return doc
