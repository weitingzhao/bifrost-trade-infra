"""TD-432 ratchet: no Ops platform ServiceAccount can read a denied Secret.

Reads every manifest under k8s/ (no cluster). For every binding whose subjects
include a ServiceAccount of a bifrost-platform-* namespace (named directly, as
the User system:serviceaccount:<ns>:<name>, or through the Groups
system:serviceaccounts:<ns>, system:serviceaccounts and system:authenticated;
review 542 C), it resolves the
role and fails when a rule lets that account get, list or watch a Secret on
the deny list in the namespace the binding covers. A ClusterRoleBinding
covers every namespace; a RoleBinding its own.

EXCEPTIONS names what is still granted on purpose, with the slice that takes
it away; an exception that no longer matches anything fails too, so the list
only shrinks. The live counterpart is scripts/check_platform_rbac.py (the
SubjectAccessReview rows for these Secrets).

    python3 -m unittest scripts/test_platform_rbac_secrets.py
"""

from __future__ import annotations

import pathlib
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
K8S = ROOT / "k8s"
RBAC = K8S / "platform-rbac"
# The namespaces whose ServiceAccounts a group-wide subject reaches.
PLATFORM_NAMESPACES = ("bifrost-platform-stg", "bifrost-platform-prod")

# (namespace, Secret) a platform identity must never read through the API server.
DENY = {
    ("cicd", "gitea-bootstrap"),  # the Gitea administrator's token
    ("cicd", "gitea-git-credentials"),  # the CI clone credential (an administrator's until TD-432 S7)
    ("cicd", "gitea-ci-reader"),  # the CI reader: mounted by Tekton, not read by the platform
    ("bifrost-platform-stg", "bifrost-gitea-reader"),  # mounted into the platform, never read via the API
    ("bifrost-platform-prod", "bifrost-gitea-reader"),
}

# (ServiceAccount namespace, Secret namespace, Secret) -> the slice that removes it.
EXCEPTIONS = {}

# A deliberately unsafe role used only as the positive control. It must not
# come from the production manifests after S6 removed that role.
UNSAFE_ROLE = {
    "kind": "ClusterRole", "metadata": {"name": "bifrost-platform-gitea-creds"},
    "rules": [{"apiGroups": [""], "resources": ["secrets"],
               "resourceNames": ["gitea-bootstrap"], "verbs": ["get"]}],
}

READ = {"get", "list", "watch", "*"}


def load(paths: list[pathlib.Path]) -> list[dict]:
    docs: list[dict] = []
    for path in paths:
        docs += [d for d in yaml.safe_load_all(path.read_text()) if isinstance(d, dict)]
    return docs


def rule_reads(rule: dict, name: str) -> bool:
    if not ({"", "*"} & set(rule.get("apiGroups") or [])):
        return False
    if not ({"secrets", "*"} & set(rule.get("resources") or [])):
        return False
    if not (READ & set(rule.get("verbs") or [])):
        return False
    names = rule.get("resourceNames") or []
    return not names or name in names


def platform_namespaces(subject: dict, binding_ns: str) -> set[str]:
    """The bifrost-platform-* namespaces whose ServiceAccounts the subject includes."""
    kind, name = subject.get("kind"), subject.get("name") or ""
    if kind == "ServiceAccount":
        found = {subject.get("namespace") or binding_ns}
    elif kind == "User" and name.startswith("system:serviceaccount:"):
        found = {name.split(":")[2]}
    elif kind == "Group" and name.startswith("system:serviceaccounts:"):
        found = {name.split(":", 2)[2]}
    elif kind == "Group" and name in ("system:serviceaccounts", "system:authenticated"):
        found = set(PLATFORM_NAMESPACES)
    else:
        found = set()
    return {ns for ns in found if ns.startswith("bifrost-platform-")}


def grants(docs: list[dict]) -> set[tuple[str, str, str]]:
    """(SA namespace, Secret namespace, Secret) for every denied Secret a platform SA can read."""
    roles = {}
    for d in docs:
        if d.get("kind") in ("ClusterRole", "Role"):
            roles[(d["kind"], (d["metadata"].get("namespace") or "") if d["kind"] == "Role" else "", d["metadata"]["name"])] = d
    found: set[tuple[str, str, str]] = set()
    for d in docs:
        if d.get("kind") not in ("ClusterRoleBinding", "RoleBinding"):
            continue
        bns = d["metadata"].get("namespace") or ""
        ref = d["roleRef"]
        role = roles.get((ref["kind"], bns if ref["kind"] == "Role" else "", ref["name"]))
        if role is None:
            continue
        accounts = set().union(*(platform_namespaces(s, bns) for s in d.get("subjects") or []))
        for sa_ns in accounts:
            for ns, name in DENY:
                if d["kind"] == "RoleBinding" and bns != ns:
                    continue
                if any(rule_reads(rule, name) for rule in role.get("rules") or []):
                    found.add((sa_ns, ns, name))
    return found


class PlatformSecretDenyList(unittest.TestCase):
    def test_no_platform_account_reads_a_denied_secret(self) -> None:
        found = grants(load(sorted(K8S.rglob("*.yaml"))))
        unexpected = sorted(found - set(EXCEPTIONS))
        self.assertEqual(unexpected, [], "a platform ServiceAccount can read a denied Secret (TD-432)")
        stale = sorted(set(EXCEPTIONS) - found)
        self.assertEqual(stale, [], "an exception no longer matches a grant: delete it from EXCEPTIONS")

    def test_it_sees_a_grant(self) -> None:
        # positive control: the same reader finds a grant written the way 00-clusterroles.yaml does
        docs = [UNSAFE_ROLE, {
            "kind": "RoleBinding", "metadata": {"name": "x", "namespace": "cicd"},
            "roleRef": {"kind": "ClusterRole", "name": "bifrost-platform-gitea-creds"},
            "subjects": [{"kind": "ServiceAccount", "name": "bifrost-platform", "namespace": "bifrost-platform-stg"}],
        }, {
            "kind": "ClusterRole", "metadata": {"name": "wide"},
            "rules": [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["list"]}],
        }, {
            "kind": "ClusterRoleBinding", "metadata": {"name": "y"},
            "roleRef": {"kind": "ClusterRole", "name": "wide"},
            "subjects": [{"kind": "ServiceAccount", "name": "bifrost-platform", "namespace": "bifrost-platform-prod"}],
        }]
        found = grants(docs)
        self.assertIn(("bifrost-platform-stg", "cicd", "gitea-bootstrap"), found)
        self.assertIn(("bifrost-platform-prod", "bifrost-platform-prod", "bifrost-gitea-reader"), found)
        self.assertIn(("bifrost-platform-prod", "cicd", "gitea-git-credentials"), found)

    def test_it_sees_a_grant_to_a_group_or_user(self) -> None:
        # review 542 C: the old reader saw only kind ServiceAccount and missed these
        docs = [UNSAFE_ROLE]
        for subject, sa_ns in (
            ({"kind": "Group", "name": "system:serviceaccounts:bifrost-platform-stg"}, "bifrost-platform-stg"),
            ({"kind": "Group", "name": "system:serviceaccounts"}, "bifrost-platform-prod"),
            ({"kind": "Group", "name": "system:authenticated"}, "bifrost-platform-stg"),
            ({"kind": "User", "name": "system:serviceaccount:bifrost-platform-prod:bifrost-platform"}, "bifrost-platform-prod"),
        ):
            with self.subTest(subject=subject["name"]):
                binding = {"kind": "RoleBinding", "metadata": {"name": "x", "namespace": "cicd"},
                           "roleRef": {"kind": "ClusterRole", "name": "bifrost-platform-gitea-creds"},
                           "subjects": [subject]}
                self.assertIn((sa_ns, "cicd", "gitea-bootstrap"), grants(docs + [binding]))
        other = {"kind": "RoleBinding", "metadata": {"name": "x", "namespace": "cicd"},
                 "roleRef": {"kind": "ClusterRole", "name": "bifrost-platform-gitea-creds"},
                 "subjects": [{"kind": "Group", "name": "system:serviceaccounts:cicd"}]}
        self.assertEqual(grants(docs + [other]), set())

    def test_it_reads_all_of_k8s(self) -> None:
        # the deny list holds outside k8s/platform-rbac too (review 542 C); the walk must reach it
        paths = sorted(K8S.rglob("*.yaml"))
        self.assertTrue(any("platform-rbac" in p.parts for p in paths))
        self.assertTrue(any("cicd" in p.parts for p in paths))


if __name__ == "__main__":
    unittest.main()
