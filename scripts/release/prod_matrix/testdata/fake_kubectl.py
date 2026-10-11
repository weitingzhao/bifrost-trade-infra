#!/usr/bin/env python3
"""Fake kubectl for collection tests. Invented names only. No cluster, no credentials."""

from __future__ import annotations

import json
import sys

NAMESPACES = ["bifrost-platform-prod", "cicd", "data", "ns-a"]

CORE = [
    {"name": "configmaps", "namespaced": True, "verbs": ["create", "patch", "update"]},
    {"name": "pods", "namespaced": True, "verbs": ["delete", "get", "create"]},
    {"name": "pods/exec", "namespaced": True, "verbs": ["get", "create"]},
    {"name": "pods/attach", "namespaced": True, "verbs": ["get", "create"]},
    {"name": "pods/portforward", "namespaced": True, "verbs": ["get", "create"]},
    {"name": "pods/ephemeralcontainers", "namespaced": True, "verbs": ["get", "patch", "update"]},
    {"name": "pods/eviction", "namespaced": True, "verbs": ["create"]},
    {"name": "pods/status", "namespaced": True, "verbs": ["patch"]},
    {"name": "secrets", "namespaced": True, "verbs": ["get"]},
    {"name": "services", "namespaced": True, "verbs": ["create", "patch", "update"]},
    {"name": "serviceaccounts", "namespaced": True, "verbs": ["create"]},
    {"name": "serviceaccounts/token", "namespaced": True, "verbs": ["create"]},
]

GROUPS = {
    "apps/v1": [
        {"name": "deployments", "namespaced": True, "verbs": ["create", "patch", "update"]},
        {"name": "deployments/scale", "namespaced": True, "verbs": ["update"]},
    ],
    "apps/v1beta1": [
        {"name": "deployments", "namespaced": True, "verbs": ["create", "patch", "update"]},
    ],
    "batch/v1": [
        {"name": "jobs", "namespaced": True, "verbs": ["create", "patch", "update"]},
        {"name": "cronjobs", "namespaced": True, "verbs": ["create", "patch", "update"]},
    ],
    "tekton.dev/v1": [
        {"name": "pipelineruns", "namespaced": True, "verbs": ["create", "delete"]},
        {"name": "taskruns", "namespaced": True, "verbs": ["create", "delete"]},
    ],
    "argoproj.io/v1alpha1": [
        {"name": "applications", "namespaced": True, "verbs": ["patch"]},
    ],
    "traefik.io/v1alpha1": [
        {"name": "ingressroutes", "namespaced": True, "verbs": ["create", "patch", "update"]},
    ],
}


class ApiError(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.stderr = f"Error from server ({status}): no"


def respond(method: str, path: str, body: dict | None) -> dict:
    """One invented apiserver answer. path has no query string."""
    if method == "WHOAMI":
        return {
            "apiVersion": "authentication.k8s.io/v1",
            "kind": "SelfSubjectReview",
            "status": {
                "userInfo": {
                    "groups": ["system:authenticated"],
                    "username": "system:serviceaccount:bifrost-access:bifrost-agent",
                }
            },
        }
    if method == "POST":
        kind = body.get("kind") if isinstance(body, dict) else None
        if kind == "SelfSubjectAccessReview":
            return {
                "apiVersion": "authorization.k8s.io/v1",
                "kind": "SelfSubjectAccessReview",
                "status": {"allowed": True},
            }
        if kind == "SubjectAccessReview":
            return {
                "apiVersion": "authorization.k8s.io/v1",
                "kind": "SubjectAccessReview",
                "status": {"allowed": False, "denied": True},
            }
        raise ApiError("BadRequest")
    if path == "/api":
        return {"kind": "APIVersions", "versions": ["v1"]}
    if path == "/apis":
        by_group: dict[str, list[dict]] = {}
        for group_version in GROUPS:
            group, version = group_version.split("/", 1)
            by_group.setdefault(group, []).append({"groupVersion": group_version, "version": version})
        groups = []
        for name, versions in by_group.items():
            preferred = next((item for item in versions if item["version"] == "v1"), versions[0])
            groups.append({"name": name, "preferredVersion": preferred, "versions": versions})
        return {"kind": "APIGroupList", "groups": groups}
    if path == "/api/v1":
        return {"groupVersion": "v1", "kind": "APIResourceList", "metadata": {"continue": ""}, "resources": CORE}
    if path.startswith("/apis/") and path.count("/") == 3:
        group_version = path[len("/apis/") :]
        return {
            "groupVersion": group_version,
            "kind": "APIResourceList",
            "metadata": {"continue": ""},
            "resources": GROUPS.get(group_version, []),
        }
    lists = {
        "/api/v1/namespaces": ("NamespaceList", [{"metadata": {"name": name}} for name in NAMESPACES]),
        "/api/v1/serviceaccounts": (
            "ServiceAccountList",
            [{"metadata": {"name": "example-sa", "namespace": "ns-a", "uid": "sa-uid-1"}}],
        ),
        "/api/v1/nodes": ("NodeList", [{"metadata": {"name": "node-a", "uid": "node-uid"}}]),
        "/apis/rbac.authorization.k8s.io/v1/roles": ("RoleList", []),
        "/apis/rbac.authorization.k8s.io/v1/rolebindings": (
            "RoleBindingList",
            [
                {
                    "metadata": {"name": "ops", "namespace": "cicd"},
                    "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "view"},
                    "subjects": [
                        {"apiGroup": "rbac.authorization.k8s.io", "kind": "Group", "name": "ops-admins"},
                        {"apiGroup": "rbac.authorization.k8s.io", "kind": "User", "name": "example-user"},
                    ],
                }
            ],
        ),
        "/apis/rbac.authorization.k8s.io/v1/clusterroles": (
            "ClusterRoleList",
            [
                {
                    "metadata": {"name": "example-role"},
                    "rules": [
                        {
                            "apiGroups": [""],
                            "resourceNames": ["platform-config"],
                            "resources": ["configmaps"],
                            "verbs": ["patch"],
                        }
                    ],
                }
            ],
        ),
        "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings": ("ClusterRoleBindingList", []),
    }
    if path in lists:
        kind, items = lists[path]
        return {"items": items, "kind": kind, "metadata": {"continue": ""}}
    raise ApiError("NotFound")


def main() -> None:
    args = sys.argv[1:]
    try:
        if args[:2] == ["auth", "whoami"]:
            payload = respond("WHOAMI", "", None)
        elif len(args) < 3 or args[1] != "--raw":
            raise ApiError("BadRequest")
        else:
            path = args[2].split("?", 1)[0]
            body = json.load(sys.stdin) if args[0] == "create" else None
            method = "POST" if args[0] == "create" else "GET"
            payload = respond(method, path, body)
    except ApiError as exc:
        print(exc.stderr, file=sys.stderr)
        sys.exit(1)
    json.dump(payload, sys.stdout)


if __name__ == "__main__":
    main()
