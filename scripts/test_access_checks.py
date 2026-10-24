"""TD-277: the live access checks work with the Agent's read-only identity.

check_platform_rbac asks through SubjectAccessReview objects instead of
`kubectl auth can-i --as`; check_admission_guards counts a dry-run as denied
only for an admission policy or an RBAC refusal of the impersonated account;
bifrost-agent-read may create SubjectAccessReviews and nothing else new.
Fixtures are invented.
"""

from __future__ import annotations

import json
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
        class Result:
            stderr = ""

            def __init__(self, returncode: int, stdout: str):
                self.returncode = returncode
                self.stdout = stdout

        application_read = ["kubectl", "get", "application", "bifrost-research", "-n", "cicd", "-o", "json"]
        application = {"metadata": {"name": "bifrost-research"},
                       "spec": {"source": {"repoURL": "https://example.invalid/research.git", "path": "k8s"}}}
        stg_read = ["kubectl", "get", "application", "bifrost-platform-stg", "-n", "cicd", "-o", "json"]
        stg = {"metadata": {"name": "bifrost-platform-stg"},
               "spec": {"source": {"repoURL": "https://example.invalid/infra.git", "path": "k8s/overlays/platform-stg"}}}
        gitea_read = ["kubectl", "get", "deployment", "gitea", "-n", "cicd", "-o", "json"]
        gitea = {"metadata": {"name": "gitea", "namespace": "cicd"},
                 "spec": {"template": {"spec": {"containers": [{"name": "gitea", "image": "gitea/gitea:1.21"}]}}}}
        reads = (application_read, stg_read, gitea_read)
        for readable in (False, True):
            with self.subTest(readable=readable):
                calls: list[list[str]] = []

                def fake_run(args, **_kwargs):
                    calls.append(list(args))
                    if list(args) == application_read:
                        return Result(0, json.dumps(application)) if readable else Result(1, "")
                    if list(args) == stg_read:
                        return Result(0, json.dumps(stg)) if readable else Result(1, "")
                    if list(args) == gitea_read:
                        return Result(0, json.dumps(gitea)) if readable else Result(1, "")
                    if list(args[:4]) == ["kubectl", "auth", "can-i", "impersonate"]:
                        return Result(0, "no\n")
                    self.fail(f"unexpected command: {args}")

                original = guards.subprocess.run
                guards.subprocess.run = fake_run
                try:
                    with self.assertRaises(guards.OwnerOnly):
                        guards.live()
                finally:
                    guards.subprocess.run = original
                self.assertEqual(calls.count(application_read), 1, calls)
                self.assertGreater(len(calls), 1, calls)
                self.assertTrue(all(c[:2] != ["kubectl", "apply"]
                                    and not any("--dry-run" in arg for arg in c) for c in calls), calls)
                self.assertEqual(calls.count(stg_read), 1, calls)
                self.assertEqual(calls.count(gitea_read), 1, calls)
                self.assertTrue(all(c[:4] == ["kubectl", "auth", "can-i", "impersonate"]
                                    for c in calls if c not in reads), calls)


class RefusalSourceTests(unittest.TestCase):
    """Review 545 F3: a refusal counts only when the rule under test made it."""

    def test_an_evaluation_error_is_not_a_denial(self) -> None:
        err = ("deployments.apps \"gitea\" is forbidden: ValidatingAdmissionPolicy 'bifrost-platform-deployment-restart-scale' "
               "with binding 'bifrost-platform-deployment-restart-scale' denied request: expression 'x' resulted in error: no such key")
        self.assertEqual(guards.classify(PLATFORM, 1, err), "error")

    def test_a_refusal_by_another_policy_is_reported(self) -> None:
        class Result:
            def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
                self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

        app = {"metadata": {"name": "x", "namespace": "cicd"},
               "spec": {"project": "bifrost", "source": {"repoURL": "https://example.invalid/x.git", "path": "k8s"},
                        "destination": {"namespace": "x", "server": "https://kubernetes.default.svc"}}}
        gitea = {"metadata": {"name": "gitea", "namespace": "cicd"},
                 "spec": {"template": {"metadata": {}, "spec": {"containers": [{"name": "gitea", "image": "g:1"}]}}}}

        def fake_run(args, **_kwargs):
            args = list(args)
            if args[:3] == ["kubectl", "get", "application"]:
                return Result(0, json.dumps(app))
            if args[:4] == ["kubectl", "get", "deployment", "gitea"]:
                return Result(0, json.dumps(gitea))
            if args[:4] == ["kubectl", "auth", "can-i", "impersonate"]:
                return Result(0, "yes\n")
            who = args[args.index("--as") + 1]
            return Result(1, stderr=f"x is forbidden: ValidatingAdmissionPolicy 'some-other-policy' with binding 'b' denied request: no ({who})")

        original = guards.subprocess.run
        guards.subprocess.run = fake_run
        try:
            problems = guards.live()
        finally:
            guards.subprocess.run = original
        self.assertTrue(any("platform-deployment-image: denied, but not by bifrost-platform-deployment-restart-scale" in p
                            for p in problems), problems)
        self.assertTrue(any("param-semicolon: denied, but not by bifrost-platform-pipelinerun" in p for p in problems), problems)
        self.assertTrue(any("platform-deployment-restart: denied=True want False" in p for p in problems), problems)

    def test_a_refusal_by_another_validation_of_the_same_policy_is_reported(self) -> None:
        # review 546 R2: the policy's name alone does not show which rule refused
        class Result:
            def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
                self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

        app = {"metadata": {"name": "x", "namespace": "cicd"},
               "spec": {"project": "bifrost", "source": {"repoURL": "https://example.invalid/x.git", "path": "k8s"},
                        "destination": {"namespace": "x", "server": "https://kubernetes.default.svc"}}}
        gitea = {"metadata": {"name": "gitea", "namespace": "cicd"},
                 "spec": {"template": {"metadata": {}, "spec": {"containers": [{"name": "gitea", "image": "g:1"}]}}}}
        policies = [guards.PR_POLICY, guards.TR_POLICY, guards.CM_POLICY, guards.DEPLOY_POLICY,
                    "bifrost-platform-application", "bifrost-applier-pod-spec"]

        def fake_run(args, **_kwargs):
            args = list(args)
            if args[:3] == ["kubectl", "get", "application"]:
                return Result(0, json.dumps(app))
            if args[:4] == ["kubectl", "get", "deployment", "gitea"]:
                return Result(0, json.dumps(gitea))
            if args[:4] == ["kubectl", "auth", "can-i", "impersonate"]:
                return Result(0, "yes\n")
            named = " ".join(f"ValidatingAdmissionPolicy '{p}'" for p in policies)
            return Result(1, stderr=f"x is forbidden: {named} denied request: an unrelated rule")

        original = guards.subprocess.run
        guards.subprocess.run = fake_run
        try:
            problems = guards.live()
        finally:
            guards.subprocess.run = original
        wrong = [p for p in problems if "denied, but not by" in p]
        self.assertTrue(any(p.startswith("platform-deployment-image:") for p in wrong), problems)
        self.assertTrue(any(p.startswith("url-other-host-taskrun:") for p in wrong), problems)
        self.assertFalse(any("must name its policy and message" in p for p in problems), problems)


class PlanDiffTests(unittest.TestCase):
    def test_the_old_diff_line_is_refused(self) -> None:
        old = 'kubectl diff -f /tmp/normalized.json --server-side > /tmp/diff.txt 2>&1 || test "$?" -eq 1'
        problems = guards.plan_diff_problems("run", old)
        self.assertEqual(len(problems), 2, problems)

    def test_the_repo_pipeline_passes(self) -> None:
        self.assertEqual([p for p in guards.pipeline_task_params() if "diff" in p or "field-manager" in p], [])


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


class DeliveryPinCaseTests(unittest.TestCase):
    """TD-335: the live cases try the pin the gitops-sync Task writes, as tekton-deliver."""

    def test_the_cases_cover_the_delivery_pin_and_its_neighbours(self) -> None:
        class Result:
            stderr = ""

            def __init__(self, returncode: int, stdout: str):
                self.returncode = returncode
                self.stdout = stdout

        apps = {
            name: {"metadata": {"name": name, "namespace": "cicd"},
                   "spec": {"project": "bifrost", "source": {"repoURL": "https://example.invalid/x.git", "path": path},
                            "destination": {"namespace": name, "server": "https://kubernetes.default.svc"}}}
            for name, path in (("bifrost-research", "k8s"), ("bifrost-platform-stg", "k8s/overlays/platform-stg"))
        }
        tried: list[tuple[str, dict]] = []
        written: list[tuple[str, str]] = []
        replaced: list[tuple[str, dict]] = []
        gitea = {"metadata": {"name": "gitea", "namespace": "cicd"},
                 "spec": {"template": {"spec": {"containers": [{"name": "gitea", "image": "gitea/gitea:1.21"}]}}}}

        def fake_run(args, **kwargs):
            args = list(args)
            if args[:3] == ["kubectl", "get", "application"]:
                return Result(0, json.dumps(apps[args[3]]))
            if args[:4] == ["kubectl", "get", "deployment", "gitea"]:
                return Result(0, json.dumps(gitea))
            if args[:4] == ["kubectl", "auth", "can-i", "impersonate"]:
                return Result(0, "yes\n")
            if args[:2] in (["kubectl", "apply"], ["kubectl", "replace"]) and args[2] == "--dry-run=server":
                body = kwargs["input"]
                who = args[args.index("--as") + 1]
                tried.append((who, json.loads(body) if body.lstrip().startswith("{") else {}))
                if body.startswith("apiVersion: v1\nkind: ConfigMap\n"):
                    written.append((who, body.split("name: ", 1)[1].split("\n", 1)[0]))
                if args[1] == "replace":
                    replaced.append((who, json.loads(body)))
                return Result(0, "")
            self.fail(f"unexpected command: {args}")

        original = guards.subprocess.run
        guards.subprocess.run = fake_run
        try:
            guards.live()
        finally:
            guards.subprocess.run = original
        deliver = "system:serviceaccount:cicd:tekton-deliver"
        pins = [(who, body) for who, body in tried if "kustomize" in body.get("spec", {}).get("source", {})
                and body["metadata"]["name"].startswith("bifrost-platform-")]
        allowed = [body for who, body in pins if who == deliver
                   and body["spec"]["source"]["kustomize"] == guards.delivery_pin()]
        self.assertEqual(len(allowed), 1, pins)
        zero = "sha256:" + "0" * 64
        self.assertEqual(guards.delivery_pin()["images"], [
            "registry.cicd.svc.cluster.local:5000/bifrost-platform-api=192.168.10.73:30500/bifrost-platform-api@" + zero,
            "registry.cicd.svc.cluster.local:5000/bifrost-platform-console="
            "192.168.10.73:30500/bifrost-platform-console@" + zero,
        ])
        self.assertIn(PLATFORM, [who for who, _ in pins])
        research = [body for who, body in tried if who == deliver and body.get("metadata", {}).get("name") == "bifrost-research"]
        self.assertEqual(len(research), 1)
        # Review 542 TD-434: both platform accounts try every foreign ConfigMap and every own one.
        stg = "system:serviceaccount:bifrost-platform-stg:bifrost-platform"
        for who in (PLATFORM, stg):
            for name in guards.CICD_FOREIGN_CONFIGMAPS + guards.PLATFORM_CICD_CONFIGMAPS:
                self.assertIn((who, name), written)
        self.assertIn((deliver, "bifrost-api-stg-dockerfile"), written)
        # Review 542 A2, 545 F3/F4: every Deployment case is a full-object update of the live
        # gitea object, as the platform; the allowed ones are there, not only refusals.
        self.assertEqual(len(replaced), len(guards.DEPLOYMENT_CASES))
        self.assertTrue(all(who == PLATFORM and b["metadata"]["name"] == "gitea" for who, b in replaced))
        images = [b["spec"]["template"]["spec"]["containers"][0]["image"] for _, b in replaced]
        self.assertEqual(images.count("example.invalid/gitea:td432"), 1)
        self.assertIn("kubectl.kubernetes.io/restartedAt",
                      replaced[0][1]["spec"]["template"]["metadata"]["annotations"])
        self.assertEqual({label for label, _, deny in guards.DEPLOYMENT_CASES if not deny},
                         {"restart", "scale", "session-annotation"})
        # TD-436: every delivery step tekton-deliver may run is tried, and every CI step as a refusal.
        steps = guards.deliver_steps()
        self.assertGreaterEqual(len(steps), 15)
        pairs = [(b["spec"]["pipelineRef"]["name"], s["pipelineTaskName"]) for who, b in tried
                 if b.get("kind") == "PipelineRun" for s in b["spec"].get("taskRunSpecs", [])
                 if s.get("serviceAccountName") == "tekton-deliver"]
        for pair in steps:
            self.assertIn(tuple(pair.split("/")), pairs)
        for step in guards.ci_platform_steps():
            self.assertIn(("bifrost-ci-platform", step), pairs)
