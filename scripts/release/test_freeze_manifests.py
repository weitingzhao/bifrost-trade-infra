"""Pin k8s/release-freeze. Every assertion has a mutated copy that must fail."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import freeze_decision  # noqa: E402
ROOT = HERE.parents[1]
FREEZE_DIR = ROOT / "k8s" / "release-freeze"
WINDOW = ROOT / "k8s" / "cicd" / "tekton" / "task-release-window.yaml"
POLICY_PATHS = [
    ROOT / "k8s" / "cicd" / "tekton" / "apply-manifest" / "actuation-policy.yaml",
    ROOT / "k8s" / "overlays" / "platform-prod" / "config" / "actuation-policy.yaml",
    ROOT / "k8s" / "overlays" / "platform-stg" / "config" / "actuation-policy.yaml",
]
EXPECTED_NAMES = {
    "crd.yaml",
    "admission.yaml",
    "rbac-list.yaml",
    "rbac-create.yaml",
    "tombstone.yaml",
}
NAME_RULE = "self.metadata.name.matches('^freeze-[0-9a-f]{32}$')"
RECORDS_RULE = {
    "apiGroups": ["release.bifrost.io"],
    "apiVersions": ["*"],
    "scope": "*",
    "operations": ["CREATE", "UPDATE", "DELETE"],
    "resources": ["freezes", "freezes/*", "policies", "policies/*"],
}
RECORD_VALIDATIONS = [
    ("request.operation != 'UPDATE'", "a release record is never updated"),
    (
        "request.operation != 'CREATE' || !(has(object.metadata.ownerReferences) || "
        "has(object.metadata.finalizers) || has(object.metadata.labels) || "
        "has(object.metadata.annotations) || has(object.metadata.generateName))",
        "a release record carries a name and no other metadata",
    ),
    (
        "request.operation != 'DELETE' || (request.userInfo.username == 'OWNER_USERNAME' && "
        "(!has(request.options.propagationPolicy) || request.options.propagationPolicy == 'Background'))",
        "only the Owner removes a release record, with a plain delete",
    ),
]
RECORDS_RAW = """\
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata: {name: bifrost-release-records}
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - {apiGroups: ["release.bifrost.io"], apiVersions: ["*"], scope: "*", operations: ["CREATE", "UPDATE", "DELETE"],
         resources: ["freezes", "freezes/*", "policies", "policies/*"]}
  validations:
    - expression: "request.operation != 'UPDATE'"
      message: "a release record is never updated"
    - expression: "request.operation != 'CREATE' || !(has(object.metadata.ownerReferences) || has(object.metadata.finalizers) || has(object.metadata.labels) || has(object.metadata.annotations) || has(object.metadata.generateName))"
      message: "a release record carries a name and no other metadata"
    - expression: "request.operation != 'DELETE' || (request.userInfo.username == 'OWNER_USERNAME' && (!has(request.options.propagationPolicy) || request.options.propagationPolicy == 'Background'))"
      message: "only the Owner removes a release record, with a plain delete"
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: {name: bifrost-release-records}
spec: {policyName: bifrost-release-records, validationActions: [Deny]}
"""
WINDOW_TEST = 'if (data.get("frozen") or "").strip().lower() == "true":'
FORBIDDEN_VERBS = {"get", "watch", "update", "patch", "delete", "deletecollection", "*"}
LIST_SUBJECTS = [
    {"kind": "Group", "apiGroup": "rbac.authorization.k8s.io", "name": "system:serviceaccounts:cicd"},
    {"kind": "ServiceAccount", "name": "bifrost-platform", "namespace": "bifrost-platform-prod"},
    {"kind": "ServiceAccount", "name": "bifrost-platform", "namespace": "bifrost-platform-stg"},
    {"kind": "ServiceAccount", "name": "bifrost-agent", "namespace": "bifrost-access"},
]
CREATE_SUBJECTS = [
    {"kind": "ServiceAccount", "name": "bifrost-platform", "namespace": "bifrost-platform-prod"},
    {"kind": "ServiceAccount", "name": "bifrost-platform", "namespace": "bifrost-platform-stg"},
]
STAMPS = ("2026-10-11T18:00:00Z", "2026-10-11T18:00:00-05:00")


def _docs(text: str) -> list[dict]:
    return [doc for doc in yaml.safe_load_all(text) if doc]


def _has_key(node: object, key: str) -> bool:
    if isinstance(node, dict):
        return key in node or any(_has_key(value, key) for value in node.values())
    if isinstance(node, list):
        return any(_has_key(value, key) for value in node)
    return False


def _kind(docs: list[dict], kind: str, name: str | None = None) -> dict | None:
    for doc in docs:
        if doc.get("kind") != kind:
            continue
        if name is None or doc.get("metadata", {}).get("name") == name:
            return doc
    return None


def _covered(prefixes: list[str], path: str) -> bool:
    path = path.strip("/")
    for prefix in prefixes:
        prefix = str(prefix).strip("/")
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _subject(item: dict) -> dict:
    kept = {"kind": item.get("kind"), "name": item.get("name")}
    if item.get("kind") == "Group":
        kept["apiGroup"] = item.get("apiGroup")
    if "namespace" in item:
        kept["namespace"] = item.get("namespace")
    return kept


def _path_hits(root: Path) -> list[str]:
    hits: list[str] = []
    k8s = root / "k8s"
    for path in k8s.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".yaml", ".yml"}:
            continue
        if FREEZE_DIR in path.parents or path.parent == FREEZE_DIR:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "k8s/release-freeze" not in text:
            continue
        if path.name == "kustomization.yaml":
            hits.append(str(path.relative_to(root)))
            continue
        for doc in _docs(text):
            if doc.get("kind") == "Application":
                hits.append(str(path.relative_to(root)))
                break
    return hits


def problems(bundle: dict) -> set[str]:
    found: set[str] = set()
    docs: dict[str, list[dict]] = bundle["docs"]
    if set(bundle["names"]) != EXPECTED_NAMES:
        found.add("directory")
    for name, items in docs.items():
        for doc in items:
            if doc.get("kind") == "Secret":
                found.add("secret")

    crd = _kind(docs.get("crd.yaml", []), "CustomResourceDefinition")
    if crd is None:
        found.add("crd-missing")
    else:
        spec = crd.get("spec") or {}
        if spec.get("scope") != "Cluster":
            found.add("crd-scope")
        names = spec.get("names") or {}
        if (names.get("kind"), names.get("plural"), names.get("singular"), names.get("listKind")) != (
            "Freeze", "freezes", "freeze", "FreezeList",
        ):
            found.add("crd-names")
        versions = spec.get("versions") or []
        if len(versions) != 1 or versions[0].get("name") != "v1" or versions[0].get("served") is not True or versions[0].get("storage") is not True:
            found.add("crd-version")
        if _has_key(crd, "subresources"):
            found.add("crd-subresources")
        schema = (((versions or [{}])[0].get("schema") or {}).get("openAPIV3Schema") or {})
        if schema.get("required") != ["spec"]:
            found.add("crd-root-spec")
        rules = schema.get("x-kubernetes-validations") or []
        if [item.get("rule") for item in rules] != [NAME_RULE]:
            found.add("crd-name-rule")
        properties = ((schema.get("properties") or {}).get("spec") or {}).get("properties") or {}
        required = ((schema.get("properties") or {}).get("spec") or {}).get("required")
        bounds = (
            properties.get("who"),
            properties.get("reason"),
            properties.get("at"),
            properties.get("via"),
            required,
        )
        want = (
            {"type": "string", "minLength": 1, "maxLength": 128},
            {"type": "string", "minLength": 1, "maxLength": 500},
            {"type": "string", "format": "date-time"},
            {"type": "string", "maxLength": 64},
            ["who", "reason", "at"],
        )
        if bounds != want:
            found.add("crd-spec")

    admission = docs.get("admission.yaml", [])
    records = _kind(admission, "ValidatingAdmissionPolicy", "bifrost-release-records")
    records_binding = _kind(admission, "ValidatingAdmissionPolicyBinding", "bifrost-release-records")
    if RECORDS_RAW not in bundle["admission_text"]:
        found.add("records-exact")
    if records is None or records_binding is None:
        found.add("records-missing")
    else:
        if records["spec"].get("failurePolicy") != "Fail":
            found.add("records-failure")
        rules = records["spec"].get("matchConstraints", {}).get("resourceRules")
        if rules != [RECORDS_RULE]:
            found.add("records-rules")
        validations = records["spec"].get("validations") or []
        got = [(item.get("expression"), item.get("message")) for item in validations]
        if got != RECORD_VALIDATIONS:
            found.add("records-validations")
        for key in ("matchConditions", "paramKind", "namespaceSelector", "objectSelector"):
            if _has_key(records, key):
                found.add("records-selector")
        if records_binding["spec"].get("validationActions") != ["Deny"]:
            found.add("records-binding-actions")
        if "matchResources" in records_binding.get("spec", {}) or "paramRef" in records_binding.get("spec", {}):
            found.add("records-binding-extra")
        if records_binding["spec"].get("policyName") != "bifrost-release-records":
            found.add("records-binding-extra")

    tomb_policy = _kind(admission, "ValidatingAdmissionPolicy", "bifrost-release-freeze-tombstone")
    tomb_binding = _kind(admission, "ValidatingAdmissionPolicyBinding", "bifrost-release-freeze-tombstone")
    if tomb_policy is None or tomb_binding is None:
        found.add("tombstone-guard")
    else:
        spec = tomb_policy["spec"]
        constraints = spec.get("matchConstraints") or {}
        rule = (constraints.get("resourceRules") or [{}])[0]
        selector = (constraints.get("namespaceSelector") or {}).get("matchLabels") or {}
        validations = spec.get("validations") or []
        shape_ok = (
            spec.get("failurePolicy") == "Fail"
            and "namespaceSelector" not in spec
            and rule.get("apiGroups") == [""]
            and rule.get("apiVersions") == ["v1"]
            and rule.get("operations") == ["DELETE"]
            and rule.get("resources") == ["configmaps"]
            and rule.get("resourceNames") == ["bifrost-release-freeze"]
            and selector.get("kubernetes.io/metadata.name") == "cicd"
            and len(constraints.get("resourceRules") or []) == 1
            and [(item.get("expression")) for item in validations] == ["request.userInfo.username == 'OWNER_USERNAME'"]
            and not _has_key(tomb_policy, "matchConditions")
            and not _has_key(tomb_policy, "paramKind")
            and "objectSelector" not in constraints
        )
        if not shape_ok:
            found.add("tombstone-guard")
        if tomb_binding["spec"].get("validationActions") != ["Deny"] or tomb_binding["spec"].get("policyName") != "bifrost-release-freeze-tombstone":
            found.add("tombstone-binding")
        if "matchResources" in tomb_binding.get("spec", {}) or "paramRef" in tomb_binding.get("spec", {}):
            found.add("tombstone-binding")

    roles = []
    for name, items in docs.items():
        for doc in items:
            if doc.get("kind") != "ClusterRole":
                continue
            roles.append((name, doc))
            if doc.get("aggregationRule") is not None:
                found.add("rbac-aggregation")
            labels = (doc.get("metadata") or {}).get("labels") or {}
            if any(str(label).startswith("rbac.authorization.k8s.io/aggregate-to-") for label in labels):
                found.add("rbac-aggregate-label")
            for rule in doc.get("rules") or []:
                verbs = set(rule.get("verbs") or [])
                if verbs & FORBIDDEN_VERBS or verbs - {"list", "create"}:
                    found.add("rbac-verbs")
                if "resourceNames" in rule:
                    found.add("rbac-resource-names")
    list_roles = [(name, doc) for name, doc in roles if any("list" in (rule.get("verbs") or []) for rule in doc.get("rules") or [])]
    create_roles = [(name, doc) for name, doc in roles if any("create" in (rule.get("verbs") or []) for rule in doc.get("rules") or [])]
    if len(list_roles) != 1 or list_roles[0][0] != "rbac-list.yaml":
        found.add("rbac-list-role")
    if len(create_roles) != 1 or create_roles[0][0] != "rbac-create.yaml":
        found.add("rbac-create-role")
    list_binding = _kind(docs.get("rbac-list.yaml", []), "ClusterRoleBinding", "bifrost-release-freeze-list")
    create_binding = _kind(docs.get("rbac-create.yaml", []), "ClusterRoleBinding", "bifrost-release-freeze-create")
    if list_binding is None or [_subject(item) for item in list_binding.get("subjects") or []] != LIST_SUBJECTS:
        found.add("rbac-list-subjects")
    if create_binding is None or [_subject(item) for item in create_binding.get("subjects") or []] != CREATE_SUBJECTS:
        found.add("rbac-create-subjects")

    tombstone = _kind(docs.get("tombstone.yaml", []), "ConfigMap", "bifrost-release-freeze")
    if tombstone is None or tombstone.get("immutable") is not True:
        found.add("tombstone-immutable")
    else:
        data = tombstone.get("data") or {}
        if set(data) != {"frozen", "frozen_at", "who", "reason"} or data.get("frozen") != "true":
            found.add("tombstone-data")
        if data.get("frozen_at") != "TOMBSTONE_WRITTEN_AT":
            found.add("placeholder-time")
        if data.get("who") != "owner" or data.get("reason") != "tombstone: freezes moved to freezes.release.bifrost.io":
            found.add("tombstone-data")
        for stamp in STAMPS:
            sample = dict(data)
            if sample.get("frozen_at") == "TOMBSTONE_WRITTEN_AT":
                sample["frozen_at"] = stamp
            allow, line = freeze_decision.decide(sample)
            if allow or not str(line).startswith("拒绝：发布已冻结（"):
                found.add("tombstone-decide")

    if "OWNER_USERNAME" not in bundle["admission_text"]:
        found.add("placeholder-owner")
    if "request.userInfo.username == 'OWNER_USERNAME' && (!has(request.options.propagationPolicy)" not in bundle["admission_text"]:
        found.add("placeholder-owner")
    if WINDOW_TEST not in bundle["window_text"]:
        found.add("window-test")
    for policy in bundle["policies"]:
        for repo in (policy.get("apply") or {}).get("repos") or []:
            if repo.get("name") != "bifrost-trade-infra":
                continue
            if _covered(repo.get("prefixes") or [], "k8s/release-freeze"):
                found.add("apply-prefix")
    if bundle["path_hits"]:
        found.add("referenced")
    return found


def load_bundle() -> dict:
    texts = {path.name: path.read_text(encoding="utf-8") for path in FREEZE_DIR.iterdir() if path.is_file()}
    return {
        "names": set(texts),
        "docs": {name: _docs(text) for name, text in texts.items()},
        "admission_text": texts["admission.yaml"],
        "policies": [_docs(path.read_text(encoding="utf-8"))[0] for path in POLICY_PATHS],
        "window_text": WINDOW.read_text(encoding="utf-8"),
        "path_hits": _path_hits(ROOT),
    }


class FreezeManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = load_bundle()

    def test_real_files_have_no_problems(self) -> None:
        self.assertEqual(problems(self.bundle), set())

    def _expect(self, code: str, mutate) -> None:
        bundle = copy.deepcopy(self.bundle)
        mutate(bundle)
        found = problems(bundle)
        self.assertIn(code, found, found)

    def test_negative_crd_scope(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["crd.yaml"][0]["spec"]["scope"] = "Namespaced"
        self._expect("crd-scope", mutate)

    def test_negative_crd_names(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["crd.yaml"][0]["spec"]["names"]["kind"] = "Other"
        self._expect("crd-names", mutate)

    def test_negative_crd_version(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["crd.yaml"][0]["spec"]["versions"].append({"name": "v2", "served": True, "storage": False})
        self._expect("crd-version", mutate)

    def test_negative_crd_subresources(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["crd.yaml"][0]["spec"]["versions"][0]["subresources"] = {"status": {}}
        self._expect("crd-subresources", mutate)

    def test_negative_crd_name_rule(self) -> None:
        def mutate(bundle: dict) -> None:
            schema = bundle["docs"]["crd.yaml"][0]["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
            schema["x-kubernetes-validations"][0]["rule"] = "self.metadata.name == 'freeze'"
        self._expect("crd-name-rule", mutate)

    def test_negative_crd_root_spec(self) -> None:
        def mutate(bundle: dict) -> None:
            schema = bundle["docs"]["crd.yaml"][0]["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
            schema.pop("required", None)
        self._expect("crd-root-spec", mutate)

    def test_negative_crd_spec_bounds(self) -> None:
        def mutate(bundle: dict) -> None:
            spec = bundle["docs"]["crd.yaml"][0]["spec"]["versions"][0]["schema"]["openAPIV3Schema"]["properties"]["spec"]
            spec["properties"]["reason"]["maxLength"] = 50
        self._expect("crd-spec", mutate)

    def test_negative_records_exact_text(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["admission_text"] = bundle["admission_text"].replace("policies/*", "policies")
        self._expect("records-exact", mutate)

    def test_negative_records_failure_policy(self) -> None:
        def mutate(bundle: dict) -> None:
            _kind(bundle["docs"]["admission.yaml"], "ValidatingAdmissionPolicy", "bifrost-release-records")["spec"]["failurePolicy"] = "Ignore"
        self._expect("records-failure", mutate)

    def test_negative_records_rules(self) -> None:
        def mutate(bundle: dict) -> None:
            rules = _kind(bundle["docs"]["admission.yaml"], "ValidatingAdmissionPolicy", "bifrost-release-records")["spec"]["matchConstraints"]["resourceRules"]
            rules[0]["resources"] = ["freezes"]
        self._expect("records-rules", mutate)

    def test_negative_records_validation_dropped(self) -> None:
        def mutate(bundle: dict) -> None:
            validations = _kind(bundle["docs"]["admission.yaml"], "ValidatingAdmissionPolicy", "bifrost-release-records")["spec"]["validations"]
            del validations[2]
        self._expect("records-validations", mutate)

    def test_negative_records_selector(self) -> None:
        def mutate(bundle: dict) -> None:
            _kind(bundle["docs"]["admission.yaml"], "ValidatingAdmissionPolicy", "bifrost-release-records")["spec"]["matchConditions"] = [
                {"name": "always", "expression": "true"}
            ]
        self._expect("records-selector", mutate)

    def test_negative_records_binding_actions(self) -> None:
        def mutate(bundle: dict) -> None:
            _kind(bundle["docs"]["admission.yaml"], "ValidatingAdmissionPolicyBinding", "bifrost-release-records")["spec"]["validationActions"] = ["Audit"]
        self._expect("records-binding-actions", mutate)

    def test_negative_records_binding_match(self) -> None:
        def mutate(bundle: dict) -> None:
            _kind(bundle["docs"]["admission.yaml"], "ValidatingAdmissionPolicyBinding", "bifrost-release-records")["spec"]["matchResources"] = {}
        self._expect("records-binding-extra", mutate)

    def test_negative_tombstone_guard_selector_at_root(self) -> None:
        def mutate(bundle: dict) -> None:
            spec = _kind(bundle["docs"]["admission.yaml"], "ValidatingAdmissionPolicy", "bifrost-release-freeze-tombstone")["spec"]
            spec["namespaceSelector"] = spec["matchConstraints"].pop("namespaceSelector")
        self._expect("tombstone-guard", mutate)

    def test_negative_tombstone_binding(self) -> None:
        def mutate(bundle: dict) -> None:
            _kind(bundle["docs"]["admission.yaml"], "ValidatingAdmissionPolicyBinding", "bifrost-release-freeze-tombstone")["spec"]["paramRef"] = {"name": "x"}
        self._expect("tombstone-binding", mutate)

    def test_negative_rbac_get_verb(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["rbac-list.yaml"][0]["rules"][0]["verbs"].append("get")
        self._expect("rbac-verbs", mutate)

    def test_negative_rbac_create_also_lists(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["rbac-create.yaml"][0]["rules"][0]["verbs"].append("list")
        self._expect("rbac-list-role", mutate)

    def test_negative_rbac_list_also_creates(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["rbac-list.yaml"][0]["rules"][0]["verbs"] = ["list", "create"]
        self._expect("rbac-create-role", mutate)

    def test_negative_rbac_resource_names(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["rbac-list.yaml"][0]["rules"][0]["resourceNames"] = ["one"]
        self._expect("rbac-resource-names", mutate)

    def test_negative_rbac_aggregation_rule(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["rbac-list.yaml"][0]["aggregationRule"] = {"clusterRoleSelectors": []}
        self._expect("rbac-aggregation", mutate)

    def test_negative_rbac_aggregate_label(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["rbac-list.yaml"][0]["metadata"]["labels"] = {
                "rbac.authorization.k8s.io/aggregate-to-admin": "true"
            }
        self._expect("rbac-aggregate-label", mutate)

    def test_negative_rbac_list_subjects(self) -> None:
        def mutate(bundle: dict) -> None:
            del bundle["docs"]["rbac-list.yaml"][1]["subjects"][0]
        self._expect("rbac-list-subjects", mutate)

    def test_negative_rbac_create_subjects(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["rbac-create.yaml"][1]["subjects"].append(
                {"kind": "ServiceAccount", "name": "bifrost-agent", "namespace": "bifrost-access"}
            )
        self._expect("rbac-create-subjects", mutate)

    def test_negative_tombstone_not_immutable(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["tombstone.yaml"][0]["immutable"] = False
        self._expect("tombstone-immutable", mutate)

    def test_negative_tombstone_data_key(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["tombstone.yaml"][0]["data"]["extra"] = "x"
        self._expect("tombstone-data", mutate)

    def test_negative_tombstone_never_frozen_is_allowed(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["tombstone.yaml"][0]["data"] = {"frozen": "false"}
        self._expect("tombstone-decide", mutate)

    def test_negative_placeholder_owner(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["admission_text"] = bundle["admission_text"].replace("OWNER_USERNAME", "system:admin")
        self._expect("placeholder-owner", mutate)

    def test_negative_placeholder_time(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["tombstone.yaml"][0]["data"]["frozen_at"] = "2026-10-11T18:00:00Z"
        self._expect("placeholder-time", mutate)

    def test_negative_window_test_removed(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["window_text"] = bundle["window_text"].replace(WINDOW_TEST, "if False:")
        self._expect("window-test", mutate)

    def test_negative_directory_extra_file(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["names"] = set(bundle["names"]) | {"kustomization.yaml"}
        self._expect("directory", mutate)

    def test_negative_secret(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["docs"]["crd.yaml"].append({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "x"}})
        self._expect("secret", mutate)

    def test_negative_apply_prefix(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["policies"] = [{
                "apply": {"repos": [{"name": "bifrost-trade-infra", "prefixes": ["k8s/release-freeze"]}]}
            }]
        self._expect("apply-prefix", mutate)

    def test_negative_kustomization_lists_the_directory(self) -> None:
        def mutate(bundle: dict) -> None:
            bundle["path_hits"] = ["k8s/cicd/kustomization.yaml"]
        self._expect("referenced", mutate)

    def test_plugin_prefix_is_not_this_repo(self) -> None:
        # Another repo's prefix "k8s" would cover this path. The match is per repo.
        self.assertTrue(_covered(["k8s"], "k8s/release-freeze"))
        self.assertFalse(_covered(
            ["k8s/overlays/dev", "k8s/monitoring", "k8s/cicd/tekton", "k8s/cicd/gitea", "k8s/data/logical-backup"],
            "k8s/release-freeze",
        ))


if __name__ == "__main__":
    unittest.main()
