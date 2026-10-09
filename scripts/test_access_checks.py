"""TD-277: the live access checks work with the Agent's read-only identity.

check_platform_rbac asks through SubjectAccessReview objects instead of
`kubectl auth can-i --as`; check_admission_guards counts a dry-run as denied
only for an admission policy or an RBAC refusal of the impersonated account;
bifrost-agent-read may create SubjectAccessReviews and nothing else new.
Fixtures are invented.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_admission_guards as guards  # noqa: E402
import check_agent_access as access  # noqa: E402
import check_platform_rbac as rbac  # noqa: E402

PLATFORM = "system:serviceaccount:bifrost-platform-prod:bifrost-platform"


class ReviewBodyTests(unittest.TestCase):
    def test_matrix_notation_maps_to_resource_attributes(self) -> None:
        cases = {
            ("patch", "deployments.apps:scale", "bifrost-prod"): {
                "verb": "patch", "group": "apps", "resource": "deployments",
                "subresource": "scale", "namespace": "bifrost-prod",
            },
            ("get", "pods:log", "data"): {
                "verb": "get", "group": "", "resource": "pods", "subresource": "log", "namespace": "data",
            },
            ("get", "secret/minio-backup", "data"): {
                "verb": "get", "group": "", "resource": "secrets", "name": "minio-backup", "namespace": "data",
            },
            ("delete", "configmap/bifrost-release-window", "cicd"): {
                "verb": "delete", "group": "", "resource": "configmaps",
                "name": "bifrost-release-window", "namespace": "cicd",
            },
            ("list", "nodes.metrics.k8s.io", ""): {"verb": "list", "group": "metrics.k8s.io", "resource": "nodes"},
            ("create", "clusterrolebindings.rbac.authorization.k8s.io", ""): {
                "verb": "create", "group": "rbac.authorization.k8s.io", "resource": "clusterrolebindings",
            },
        }
        for (verb, resource, ns), want in cases.items():
            self.assertEqual(rbac.resource_attributes(verb, resource, ns), want, resource)

    def test_service_account_review_carries_the_groups_impersonation_adds(self) -> None:
        body = rbac.review_body(PLATFORM, "create", "pipelineruns.tekton.dev", "cicd")
        self.assertEqual(body["kind"], "SubjectAccessReview")
        self.assertEqual(body["spec"]["user"], PLATFORM)
        self.assertEqual(
            body["spec"]["groups"],
            ["system:serviceaccounts", "system:serviceaccounts:bifrost-platform-prod", "system:authenticated"],
        )
        self.assertEqual(body["spec"]["resourceAttributes"]["group"], "tekton.dev")


class DryRunClassifyTests(unittest.TestCase):
    def test_only_policy_or_rbac_refusal_of_the_target_counts_as_denied(self) -> None:
        policy = 'The pipelineruns "x" is invalid: : ValidatingAdmissionPolicy \'bifrost-pipelinerun\' with binding \'b\' denied request'
        rbac_refusal = f'pipelineruns.tekton.dev "x" is forbidden: User "{PLATFORM}" cannot create resource'
        agent = 'serviceaccounts "bifrost-platform" is forbidden: User "system:serviceaccount:bifrost-access:bifrost-agent" cannot impersonate resource "serviceaccounts"'
        other = "error: unable to recognize \"STDIN\": no matches for kind"
        self.assertEqual(guards.classify(PLATFORM, 0, ""), "allowed")
        self.assertEqual(guards.classify(PLATFORM, 1, policy), "denied")
        self.assertEqual(guards.classify(PLATFORM, 1, rbac_refusal), "denied")
        self.assertEqual(guards.classify(PLATFORM, 1, agent), "impersonation")
        self.assertEqual(guards.classify(PLATFORM, 1, other), "error")

    def test_forbidden_for_another_user_is_not_a_denial_of_the_target(self) -> None:
        stderr = 'x is forbidden: User "someone-else" cannot create resource'
        self.assertEqual(guards.classify(PLATFORM, 1, stderr), "error")

    def test_live_stops_before_any_dry_run_without_impersonation(self) -> None:
        # Measured 2026-10-09: as bifrost-agent every dry-run failed on the OpenAPI
        # download, and the old code read each failure as a policy denial.
        calls: list[list[str]] = []

        class Result:
            returncode = 0
            stdout = "no\n"
            stderr = ""

        def fake_run(args, **_kwargs):
            calls.append(list(args))
            return Result()

        original = guards.subprocess.run
        guards.subprocess.run = fake_run
        try:
            with self.assertRaises(guards.OwnerOnly):
                guards.live()
        finally:
            guards.subprocess.run = original
        self.assertTrue(calls)
        self.assertTrue(all(c[:4] == ["kubectl", "auth", "can-i", "impersonate"] for c in calls), calls)


class AgentReadRoleTests(unittest.TestCase):
    @staticmethod
    def _verb_problems(name: str, rules: list[dict]) -> list[str]:
        role = {"apiVersion": "rbac.authorization.k8s.io/v1", "kind": "ClusterRole",
                "metadata": {"name": name}, "rules": rules}
        # static_problems also reports the objects a one-role fixture lacks; keep the verb findings.
        return [p for p in access.static_problems([role]) if "verb" in p]

    def test_subject_access_review_create_is_allowed_only_in_the_read_role(self) -> None:
        sar = {"apiGroups": ["authorization.k8s.io"], "resources": ["subjectaccessreviews"], "verbs": ["create"]}
        self.assertEqual(self._verb_problems("bifrost-agent-read", [sar]), [])
        self.assertTrue(self._verb_problems("some-other-role", [sar]))

    def test_impersonate_is_refused(self) -> None:
        rule = {"apiGroups": [""], "resources": ["serviceaccounts"], "verbs": ["impersonate"]}
        self.assertTrue(self._verb_problems("bifrost-agent-read", [rule]))

    def test_other_authorization_writes_are_refused(self) -> None:
        rule = {"apiGroups": ["authorization.k8s.io"], "resources": ["subjectaccessreviews", "localsubjectaccessreviews"], "verbs": ["create"]}
        self.assertTrue(self._verb_problems("bifrost-agent-read", [rule]))


if __name__ == "__main__":
    unittest.main()
