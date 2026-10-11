"""Round-3 tests T42–T48. T42 mutates the committed sample bundle."""

from __future__ import annotations

import copy
import json
import os
import random
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from canon import MatrixExit  # noqa: E402
from classify import replay  # noqa: E402
from exceptions import parse_today  # noqa: E402
from questions import count_questions, fixed_askable  # noqa: E402
from ratchet import lines_of, scan  # noqa: E402
from schema import validate_document  # noqa: E402
from support import (  # noqa: E402
    base_commands,
    bundle_from,
    command,
    copy_fixed,
    denied_status,
    discovery,
    empty_exceptions,
    empty_nontargets,
    load_defaults,
    question,
    res,
    reseal,
    reviews,
    rows,
    run,
    targets_of,
)
from test_reviews import _cli  # noqa: E402

BUNDLE_PATH = HERE / "testdata" / "recorded-bundle.json"
SEED = 56
# Review interiors are sampled unless PROD_MATRIX_T42_FULL=1. Every other record kind is fully mutated.
REVIEW_EXTRA = 40

# A mutant that does not exit 2 must be one of these. The reason is written next to the name.
HARMLESS = {
    "already-empty-string": "the string was already empty, so writing '' changes nothing",
    "caller-metadata": (
        "classification does not read bundle.caller "
        "(fields: kind, user, groups, uid, extra, source)"
    ),
}


def _play(bundle, targets, fixed, exceptions, nontargets):
    try:
        validate_document("bundle", bundle)
        return replay(bundle, targets, fixed, exceptions, nontargets, parse_today("2026-10-11"))
    except MatrixExit as exc:
        return exc.code, exc.message


def _counts(text: str) -> dict[str, int]:
    line = text.splitlines()[1]
    found = {}
    for part in line.split(";"):
        name, value = part.split(":")
        found[name.strip()] = int(value.strip())
    return found


def _risk_rows(text: str) -> int:
    return sum(
        1
        for row in rows(text)
        if str((row.get("subject") or {}).get("source") or "").startswith("fixed:") and "resource" not in row
    )


def _keys(text: str) -> set[str]:
    return {row["row_key"] for row in rows(text) if row.get("row_key")}


def _record_kind(attempt: dict) -> str:
    if attempt.get("kind") == "review":
        return "review"
    path = attempt["request"]["path"]
    if path in {"/api", "/apis"}:
        return "root-discovery"
    if path.endswith("/selfsubjectreviews"):
        return "whoami"
    if path.endswith("/selfsubjectaccessreviews"):
        return "self-check"
    if (path.startswith("/api/") and path.count("/") == 2) or (path.startswith("/apis/") and path.count("/") == 3):
        return "version-discovery"
    return "list"


def _walk(node, path):
    if isinstance(node, dict):
        for key, value in node.items():
            child = path + (("k", key),)
            yield child, value
            yield from _walk(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            child = path + (("i", index),)
            yield child, value
            yield from _walk(value, child)


def _show(path) -> str:
    text = "$"
    for kind, key in path:
        text += f"[{key}]" if kind == "i" else f".{key}"
    return text


# Strings at these keys, and string elements of these lists, are values the tool reads.
READ_STRING_KEYS = {
    "body_sha256",
    "continue",
    "evaluationError",
    "group",
    "groupVersion",
    "kind",
    "limit",
    "method",
    "name",
    "namespace",
    "path",
    "request_hash",
    "resource",
    "subresource",
    "user",
    "username",
    "verb",
    "version",
}
READ_STRING_LISTS = {"groups", "verbs", "versions"}


def _string_is_read(path) -> bool:
    if not path:
        return False
    kind, key = path[-1]
    if kind == "k" and key in READ_STRING_KEYS:
        return True
    if kind == "i" and len(path) >= 2 and path[-2][0] == "k" and path[-2][1] in READ_STRING_LISTS:
        return True
    return False


def _apply(root, path, op):
    if isinstance(op, tuple) and op[0] == "swap":
        node = root
        for _kind, key in path:
            node = node[key]
        index = op[1]
        node[index], node[index + 1] = node[index + 1], node[index]
        return
    node = root
    for _kind, key in path[:-1]:
        node = node[key]
    last = path[-1][1]
    if op == "delete":
        del node[last]
    elif op == "null":
        node[last] = None
    elif op == "duplicate":
        node.insert(last, copy.deepcopy(node[last]))
    elif op == "flip":
        node[last] = not node[last]
    elif op == "zero":
        node[last] = 0
    elif op == "swap-status":
        node[last] = 503 if node[last] == 200 else 200
    elif op == "blank":
        node[last] = ""
    else:
        raise AssertionError(op)


def _harmless(path, op, node) -> str | None:
    if op == "blank" and isinstance(node, str) and node == "":
        return "already-empty-string"
    if path and path[0] == ("k", "caller"):
        return "caller-metadata"
    return None


def _value_ops(path, node):
    ops = []
    if isinstance(node, bool):
        ops.append("flip")
        return ops
    if isinstance(node, str) and _string_is_read(path):
        ops.append("blank")
    if isinstance(node, (int, float)):
        ops.append("zero")
        if path and path[-1] == ("k", "status_code") and node in (200, 503):
            ops.append("swap-status")
    return ops


def _ops_for(path, node, parent_is_list):
    ops = ["delete", "null"]
    if parent_is_list:
        ops.append("duplicate")
    if isinstance(node, list) and len(node) >= 2:
        ops.extend([("swap", index) for index in range(len(node) - 1)])
    return ops


def _attempt_index(path):
    if len(path) >= 2 and path[0] == ("k", "attempts") and path[1][0] == "i":
        return path[1][1]
    return None


def _covered(original, full: bool):
    full_indexes = set()
    review_indexes = []
    seen_kind = set()
    for index, attempt in enumerate(original["attempts"]):
        kind = _record_kind(attempt)
        if kind == "review":
            review_indexes.append(index)
        else:
            full_indexes.add(index)
        if kind not in seen_kind and kind != "review":
            seen_kind.add(kind)
    if full:
        covered = set(range(len(original["attempts"])))
        review_full = len(review_indexes)
    else:
        full_indexes.add(review_indexes[0])
        picked = set(random.Random(SEED).sample(review_indexes[1:], REVIEW_EXTRA))
        covered = full_indexes | picked
        review_full = 1 + len(picked)
    return covered, review_full, len(review_indexes), seen_kind


class Round3Tests(unittest.TestCase):
    def test_t42_mutation_keeps_every_row_or_exits_2(self):
        self._t42(full=False)

    @unittest.skipUnless(
        os.environ.get("PROD_MATRIX_T42_FULL") == "1",
        "set PROD_MATRIX_T42_FULL=1 to mutate all 294 review interiors",
    )
    def test_t42_full_review_interiors(self):
        self._t42(full=True)

    def _t42(self, full: bool):
        started = time.perf_counter()
        original = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        targets, fixed, exceptions, nontargets = load_defaults()
        code, text = _play(original, targets, fixed, exceptions, nontargets)
        self.assertEqual(code, 3, text.splitlines()[0] if text else text)
        covered, review_full, review_total, seen_kind = _covered(original, full)
        self.assertEqual(seen_kind, {"root-discovery", "whoami", "self-check", "version-discovery", "list"})
        self.assertEqual(review_total, 294)

        mutants = []
        for path, node in _walk(original, ()):
            index = _attempt_index(path)
            # The attempt record itself is always mutated. Interiors of extra reviews are sampled.
            if index is not None and index not in covered and len(path) > 2:
                continue
            parent_is_list = len(path) >= 1 and path[-1][0] == "i"
            for op in _ops_for(path, node, parent_is_list):
                mutants.append((path, op, "structural", node))
            for op in _value_ops(path, node):
                mutants.append((path, op, "value", node))

        exit2 = {"structural": 0, "value": 0}
        classes = {name: 0 for name in HARMLESS}
        failures = []
        for path, op, family, node in mutants:
            mutant = copy.deepcopy(original)
            label = "swap" if isinstance(op, tuple) else op
            try:
                _apply(mutant, path, op)
                code, text = _play(mutant, targets, fixed, exceptions, nontargets)
            except Exception as exc:  # noqa: BLE001 — a crash is a failed mutant
                failures.append(f"{_show(path)} {label}: {exc!r}")
                continue
            if code == 2:
                exit2[family] += 1
                continue
            harmless = _harmless(path, op, node)
            if harmless in HARMLESS:
                classes[harmless] += 1
                continue
            failures.append(f"{_show(path)} {label}: exit {code}")
        elapsed = time.perf_counter() - started
        structural_n = sum(1 for item in mutants if item[2] == "structural")
        value_n = sum(1 for item in mutants if item[2] == "value")
        print(
            f"T42 mode={'full' if full else 'sample'} structural={structural_n} exit2={exit2['structural']} "
            f"value={value_n} exit2={exit2['value']} "
            f"already-empty-string={classes['already-empty-string']} "
            f"caller-metadata={classes['caller-metadata']} "
            f"review_records={review_full}/{review_total} seconds={elapsed:.2f}"
        )
        self.assertFalse(failures[:8], failures[:8])
        self.assertEqual(exit2["structural"] + exit2["value"] + sum(classes.values()) + len(failures), len(mutants))
        expected = {
            False: (6006, 6004, 1418, 1287, 129, 4),
            True: (24593, 24591, 7207, 6564, 641, 4),
        }[full]
        self.assertEqual(
            (
                structural_n,
                exit2["structural"],
                value_n,
                exit2["value"],
                classes["already-empty-string"],
                classes["caller-metadata"],
            ),
            expected,
        )
        self.assertEqual(review_full, review_total if full else 1 + REVIEW_EXTRA)

    def test_t43_legal_retries_replay_the_last_attempt(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        commands = base_commands(["ns-a"])
        commands.append(command(8, "/api/v1", discovery("v1", [res("configmaps")])))
        bundle = bundle_from(commands, targets_of(questions), copy_fixed(True), lambda item: denied_status())
        read = next(item for item in bundle["attempts"] if item["request"]["path"] == "/api/v1")
        failed = copy.deepcopy(read)
        failed["result"]["ok"] = False
        failed["result"]["status_code"] = 503
        failed["result"]["body"] = {"kind": "Status", "message": "unavailable"}
        reseal(failed)
        succeeded = copy.deepcopy(read)
        succeeded["attempt"] = max(item["attempt"] for item in bundle["attempts"]) + 1
        succeeded["retry_of"] = failed["attempt"]
        bundle["attempts"] = [
            failed if item["attempt"] == read["attempt"] else item for item in bundle["attempts"]
        ]
        bundle["attempts"].append(succeeded)
        review = next(item for item in reviews(bundle) if item["request"]["body"]["spec"]["user"] == "system:anonymous")
        denied = copy.deepcopy(review)
        denied["result"]["ok"] = False
        denied["result"]["status_code"] = 503
        denied["result"]["body"] = {"kind": "Status", "message": "unavailable"}
        reseal(denied)
        allowed = copy.deepcopy(review)
        allowed["attempt"] = max(item["attempt"] for item in bundle["attempts"]) + 1
        allowed["retry_of"] = denied["attempt"]
        allowed["result"]["body"]["status"] = {"allowed": True, "denied": False}
        reseal(allowed)
        bundle["attempts"] = [
            denied if item["attempt"] == review["attempt"] else item for item in bundle["attempts"]
        ]
        bundle["attempts"].append(allowed)
        code, text = run(bundle, targets_of(questions), copy_fixed(True), empty_exceptions(), empty_nontargets())
        self.assertEqual(code, 3, text)
        self.assertTrue(
            any(row["reason"] == "allowed" and row["subject"]["user"] == "system:anonymous" for row in rows(text))
        )

    def test_t44_unchained_attempts_exit_2(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        commands = base_commands(["ns-a"])
        commands.append(command(8, "/api/v1", discovery("v1", [res("configmaps")])))
        bundle = bundle_from(commands, targets_of(questions), copy_fixed(), lambda item: denied_status())
        clone = copy.deepcopy(reviews(bundle)[0])
        clone["attempt"] = max(item["attempt"] for item in bundle["attempts"]) + 1
        clone.pop("retry_of", None)
        bundle["attempts"].append(clone)
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets_of(questions), copy_fixed(), empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("chain", raised.exception.message)

    def test_t45_unconfirmed_allow_is_not_absorbed_by_an_exception(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "platform-config", "patch")]
        commands = base_commands(
            ["ns-a"],
            sas=[{"metadata": {"name": "example-sa", "namespace": "ns-a", "uid": "sa-uid-1"}}],
        )
        commands.append(command(8, "/api/v1", discovery("v1", [res("configmaps")])))
        bundle = bundle_from(commands, targets_of(questions), copy_fixed(), lambda item: {"allowed": True, "denied": False})
        from identities import assemble, inventory

        subject = next(
            item["context"]
            for item in assemble(inventory(bundle["attempts"]), copy_fixed()["rows"])
            if item["context"]["user"] == "system:serviceaccount:ns-a:example-sa"
        )
        exception = {
            "check": "subjectaccessreview",
            "class": "field",
            "expires": "2026-12-01",
            "field": "data",
            "group": "",
            "identity": subject,
            "name": "platform-config",
            "namespace": "ns-a",
            "reason": "named",
            "removes": "step-4",
            "request_family": "authz",
            "resource": "configmaps",
            "scope": "namespaced",
            "subresource": "",
            "verb": "patch",
        }
        code, text = run(
            bundle,
            targets_of(questions),
            copy_fixed(),
            {"exceptions": [exception], "schema_version": 1},
            empty_nontargets(),
        )
        matched = [
            row
            for row in rows(text)
            if (row.get("subject") or {}).get("user") == "system:serviceaccount:ns-a:example-sa"
            and row.get("name") == "platform-config"
        ]
        self.assertTrue(matched)
        self.assertTrue(all(row["reason"] == "context-unconfirmed" for row in matched))
        self.assertFalse(any(row["kind"] == "named-exception" for row in matched))
        self.assertNotEqual(code, 0)

    def test_t46_response_metadata_and_spec_replay(self):
        bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        review = next(item for item in bundle["attempts"] if item["kind"] == "review")
        review["result"]["body"]["metadata"] = {"continue": ""}
        review["result"]["body"]["spec"] = {"ignored": True}
        reseal(review)
        targets, fixed, exceptions, nontargets = load_defaults()
        code, text = run(bundle, targets, fixed, exceptions, nontargets)
        self.assertEqual(code, 3, text)
        self.assertNotIn("refused", text)

    def test_t47_two_budget_checks_and_deduped_identities(self):
        targets, fixed, _exceptions, _nontargets = load_defaults()
        duplicated = copy.deepcopy(fixed)
        duplicated["rows"].append(copy.deepcopy(next(row for row in fixed["rows"] if row["id"] == "anonymous")))
        self.assertEqual(count_questions(fixed_askable(duplicated["rows"]), targets["questions"]), 98)
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", f"v{index}") for index in range(10000)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "targets.json"
            out = Path(tmp) / "bundle.json"
            path.write_text(json.dumps(targets_of(questions)), encoding="utf-8")
            code, out_text, _err = _cli(["collect", "--bundle-out", str(out), "--targets", str(path)])
            self.assertEqual(code, 2)
            self.assertFalse(out.exists())
            self.assertTrue(out_text.splitlines()[2].startswith("question count:"))
        calls = []

        def transport(method, path, body):
            calls.append(path.split("?", 1)[0])
            if method == "WHOAMI":
                payload = {"status": {"userInfo": {"username": "system:serviceaccount:bifrost-access:bifrost-agent", "groups": ["system:authenticated"]}}}
            elif method == "POST":
                payload = {"status": {"allowed": True}}
            elif path.split("?", 1)[0] == "/api/v1/serviceaccounts":
                payload = {
                    "items": [
                        {"metadata": {"name": f"sa-{index}", "namespace": "ns-a", "uid": f"uid-{index}"}}
                        for index in range(450)
                    ],
                    "kind": "ServiceAccountList",
                    "metadata": {"continue": ""},
                }
            elif path.split("?", 1)[0] == "/api/v1/namespaces":
                payload = {"items": [{"metadata": {"name": "ns-a"}}], "kind": "NamespaceList", "metadata": {"continue": ""}}
            else:
                payload = {"items": [], "kind": "List", "metadata": {"continue": ""}}
            return 0, json.dumps(payload), ""

        import collect

        original = collect.kubectl_transport
        collect.kubectl_transport = transport
        try:
            with tempfile.TemporaryDirectory() as tmp:
                code, out_text, err = _cli(["collect", "--bundle-out", str(Path(tmp) / "out.json")])
        finally:
            collect.kubectl_transport = original
        self.assertEqual(code, 2, err)
        self.assertNotIn("/api", calls)
        self.assertIn("/api/v1/serviceaccounts", calls)
        self.assertFalse(any(path.endswith("/subjectaccessreviews") for path in calls))
        self.assertTrue(out_text.splitlines()[2].startswith("question count:"))

    def test_t48_target_namespace_missing_from_the_inventory_exits_2(self):
        questions = [question("", "v1", "configmaps", "", "missing-ns", "namespaced", "", "patch")]
        commands = base_commands(["ns-a"])
        commands.append(command(8, "/api/v1", discovery("v1", [res("configmaps")])))
        bundle = bundle_from(commands, targets_of(questions), copy_fixed(), lambda item: denied_status())
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets_of(questions), copy_fixed(), empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("missing-ns", raised.exception.message)

    def test_review54_reproductions_exit_2_or_keep_counts(self):
        original = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
        targets, fixed, exceptions, nontargets = load_defaults()
        _code, base = _play(original, targets, fixed, exceptions, nontargets)
        base_counts = _counts(base)

        def outcome(mutate, reseal_paths=()):
            mutant = copy.deepcopy(original)
            mutate(mutant)
            for path in reseal_paths:
                attempt = next(item for item in mutant["attempts"] if item["request"]["path"] == path)
                reseal(attempt)
            code, text = _play(mutant, targets, fixed, exceptions, nontargets)
            if code == 2:
                return "exit 2"
            if code == 3 and _counts(text) == base_counts:
                return "exit 3 counts unchanged"
            return f"exit {code} counts changed"

        def drop_path(path):
            def mutate(bundle):
                bundle["attempts"] = [item for item in bundle["attempts"] if item["request"]["path"] != path]
            return mutate

        def duplicate(path):
            def mutate(bundle):
                clone = copy.deepcopy(next(item for item in bundle["attempts"] if item["request"]["path"] == path))
                clone["attempt"] = max(item["attempt"] for item in bundle["attempts"]) + 1
                clone.pop("retry_of", None)
                bundle["attempts"].append(clone)
            return mutate

        def swap_attempts(bundle):
            bundle["attempts"][0], bundle["attempts"][1] = bundle["attempts"][1], bundle["attempts"][0]

        def groups_null(bundle):
            attempt = next(item for item in bundle["attempts"] if item["request"]["path"] == "/apis")
            attempt["result"]["body"]["groups"] = [None]

        def empty_body(bundle):
            attempt = next(item for item in bundle["attempts"] if item["request"]["path"] == "/api/v1")
            attempt["result"]["body"] = {}

        def drop_unasked(bundle):
            attempt = next(item for item in bundle["attempts"] if item["request"]["path"] == "/api/v1")
            attempt["result"]["body"]["resources"] = [
                item for item in attempt["result"]["body"]["resources"] if item["name"] != "pods/status"
            ]

        def drop_namespace(bundle):
            attempt = next(item for item in bundle["attempts"] if item["request"]["path"] == "/api/v1/namespaces")
            attempt["result"]["body"]["items"] = [
                item for item in attempt["result"]["body"]["items"] if item["metadata"]["name"] != "cicd"
            ]

        def drop_data(bundle):
            attempt = next(item for item in bundle["attempts"] if item["request"]["path"] == "/api/v1/namespaces")
            attempt["result"]["body"]["items"] = [
                item for item in attempt["result"]["body"]["items"] if item["metadata"]["name"] != "data"
            ]

        def empty_sa(bundle):
            attempt = next(item for item in bundle["attempts"] if item["request"]["path"] == "/api/v1/serviceaccounts")
            attempt["result"]["body"] = {}

        def empty_spec(bundle):
            attempt = next(item for item in bundle["attempts"] if item["kind"] == "review")
            attempt["request"]["body"]["spec"] = {}

        def override_discovery(bundle):
            attempt = copy.deepcopy(next(item for item in bundle["attempts"] if item["request"]["path"] == "/api/v1"))
            attempt["attempt"] = max(item["attempt"] for item in bundle["attempts"]) + 1
            attempt.pop("retry_of", None)
            attempt["result"]["body"]["resources"] = [
                item for item in attempt["result"]["body"]["resources"] if item["name"] != "pods/status"
            ]
            reseal(attempt)
            bundle["attempts"].append(attempt)

        cases = [
            ("根发现 删除", drop_path("/api"), ()),
            ("根发现 重复", duplicate("/api"), ()),
            ("根发现 重排", swap_attempts, ()),
            ("根发现 截短 groups [null]", groups_null, ("/apis",)),
            ("版本发现 删除", drop_path("/api/v1"), ()),
            ("版本发现 重复", duplicate("/apis/apps/v1"), ()),
            ("版本发现 重排", swap_attempts, ()),
            ("版本发现 截短 空 body", empty_body, ("/api/v1",)),
            ("版本发现 截短 删未问资源", drop_unasked, ()),
            ("分页 删除", drop_path("/api/v1/namespaces"), ()),
            ("分页 重复终页", duplicate("/api/v1/namespaces"), ()),
            ("分页 重排", swap_attempts, ()),
            ("命名空间列表 截短 删除 cicd", drop_namespace, ("/api/v1/namespaces",)),
            ("身份列表 删除", drop_path("/api/v1/serviceaccounts"), ()),
            ("身份列表 重复", duplicate("/api/v1/serviceaccounts"), ()),
            ("身份列表 截短 空 body", empty_sa, ("/api/v1/serviceaccounts",)),
            ("评审 删除", lambda bundle: bundle["attempts"].remove(next(item for item in bundle["attempts"] if item["kind"] == "review")), ()),
            ("评审 重复", lambda bundle: duplicate_review(bundle), ()),
            ("评审 截短 空 spec", empty_spec, ()),
            ("同一请求追加一条并删 pods/status", override_discovery, ()),
            ("命名空间列表 截短 删除 data", drop_data, ("/api/v1/namespaces",)),
        ]
        results = []
        for name, mutate, reseal_paths in cases:
            result = outcome(mutate, reseal_paths)
            results.append(f"{name}: {result}")
            self.assertIn(result, {"exit 2", "exit 3 counts unchanged"}, name + " " + result)
        print("\n".join(results))

    def test_crd_spec_digest_changes_when_the_spec_changes(self):
        body = textwrap.dedent(
            """\
            apiVersion: apiextensions.k8s.io/v1
            kind: CustomResourceDefinition
            metadata:
              name: widgets.example.invalid
            spec:
              group: example.invalid
              names:
                plural: widgets
              versions:
                - name: v1
                  served: true
                  subresources:
                    status: {}
                  schema:
                    openAPIV3Schema:
                      type: object
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "crd.yaml").write_text(body, encoding="utf-8")
            before = lines_of(scan(root, HERE / "prod_fixed_identities.json"))
            self.assertTrue(any("widgets.example.invalid#spec" in line for line in before))
            self.assertTrue(any('"name":"widgets.example.invalid"' in line for line in before))
            (root / "crd.yaml").write_text(body.replace("type: object", "type: string"), encoding="utf-8")
            schema_changed = lines_of(scan(root, HERE / "prod_fixed_identities.json"))
            self.assertNotEqual(before, schema_changed)
            (root / "crd.yaml").write_text(body.replace("served: true", "served: false"), encoding="utf-8")
            served_changed = lines_of(scan(root, HERE / "prod_fixed_identities.json"))
            self.assertNotEqual(before, served_changed)


def duplicate_review(bundle):
    clone = copy.deepcopy(next(item for item in bundle["attempts"] if item["kind"] == "review"))
    clone["attempt"] = max(item["attempt"] for item in bundle["attempts"]) + 1
    clone.pop("retry_of", None)
    bundle["attempts"].append(clone)


if __name__ == "__main__":
    unittest.main()
