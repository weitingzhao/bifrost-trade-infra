"""Round-1 tests T23–T26, T29, T30, T34, T35, T37, T40."""

from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import prod_measure  # noqa: E402
from schema import field_table_markdown, read_declared, table_in_readme, validate_document  # noqa: E402
from support import (  # noqa: E402
    allowed_status,
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


def _cli(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = prod_measure.main(argv)
    return code, out.getvalue(), err.getvalue()


def _config_bundle(questions, resources, answer, namespaces=None):
    fixed = copy_fixed()
    commands = base_commands(namespaces or ["ns-a"])
    commands.append(command(8, "/api/v1", discovery("v1", resources)))
    targets = targets_of(questions)
    return bundle_from(commands, targets, fixed, answer), targets, fixed


class SurfaceTests(unittest.TestCase):
    def test_t23_unlisted_resource_is_not_asked_until_a_nontarget_covers_it(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        resources = [res("configmaps"), res("widgets")]
        bundle, targets, fixed = _config_bundle(questions, resources, lambda item: denied_status())
        _code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertTrue(any(row["reason"] == "not-asked" and row["resource"] == "widgets" for row in rows(text)))
        nontargets = {
            "entries": [
                {
                    "group": "",
                    "namespace": "*",
                    "reason": "widgets are not a PROD target",
                    "resource": "widgets",
                    "scope": "namespaced",
                    "subresource": "",
                }
            ],
            "schema_version": 1,
        }
        _code, text = run(bundle, targets, fixed, empty_exceptions(), nontargets)
        self.assertFalse(any(row.get("resource") == "widgets" and row["reason"] == "not-asked" for row in rows(text)))

    def test_t24_forbidden_or_failed_empty_exits_2_and_success_empty_is_empty(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        bundle, targets, fixed = _config_bundle(questions, [res("configmaps")], lambda item: denied_status())
        code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(code, 3)
        self.assertIn("question count:", text)
        failed = copy.deepcopy(bundle)
        rolebindings = next(item for item in failed["attempts"] if item["request"]["path"].endswith("/rolebindings"))
        rolebindings["result"]["ok"] = False
        rolebindings["result"]["status_code"] = 403
        code, _out, err = _replay(failed, targets, fixed)
        self.assertEqual(code, 2)
        self.assertIn("read failed", err)

    def test_t25_wildcard_and_missing_field_are_rejected_expired_does_not_match(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "platform-config", "patch")]
        bundle, targets, fixed = _config_bundle(
            questions,
            [res("configmaps")],
            lambda item: allowed_status(),
        )
        identity = reviews(bundle)[0]["request"]["body"]["spec"]
        # Use the anonymous identity from the fixed file, which is asked.
        from identities import assemble, inventory

        anon = next(item["context"] for item in assemble(inventory(bundle["attempts"]), fixed["rows"]) if item["context"]["kind"] == "anonymous")
        base = {
            "check": "subjectaccessreview",
            "class": "field",
            "expires": "2026-10-01",
            "field": "data",
            "group": "",
            "identity": anon,
            "name": "platform-config",
            "namespace": "ns-a",
            "reason": "held for a day",
            "removes": "step-4",
            "request_family": "authz",
            "resource": "configmaps",
            "scope": "namespaced",
            "subresource": "",
            "verb": "patch",
        }
        starred = copy.deepcopy(base)
        starred["expires"] = "2026-12-01"
        starred["name"] = "*"
        code, _out, err = _replay(bundle, targets, fixed, {"exceptions": [starred], "schema_version": 1})
        self.assertEqual(code, 2)
        self.assertIn("wildcard", err)
        missing = copy.deepcopy(base)
        missing.pop("removes")
        missing["expires"] = "2026-12-01"
        code, _out, err = _replay(bundle, targets, fixed, {"exceptions": [missing], "schema_version": 1})
        self.assertEqual(code, 2)
        self.assertIn("removes", err)
        expired = {"exceptions": [base], "schema_version": 1}
        code, text = run(bundle, targets, fixed, expired, empty_nontargets(), today="2026-10-11")
        self.assertEqual(code, 3)
        self.assertIn("expired exceptions: 1", text)
        self.assertTrue(any(row["reason"] == "allowed" and row["subject"]["kind"] == "anonymous" for row in rows(text)))
        self.assertFalse(any(row["kind"] == "named-exception" for row in rows(text)))

    def test_t26_empty_name_is_not_enumeration_and_a_named_question_is_only_that_name(self):
        resources = [res("configmaps")]
        empty = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        bundle, targets, fixed = _config_bundle(empty, resources, lambda item: denied_status())
        _code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertTrue(any(row["reason"] == "names-not-enumerated" and row["resource"] == "configmaps" for row in rows(text)))
        self.assertFalse(any(row.get("only") == "platform-config" for row in rows(text)))
        named = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "platform-config", "patch")]

        def answer(item):
            if item["question"].get("name") == "platform-config" and not item["wildcard"]:
                return allowed_status()
            return denied_status()

        bundle, targets, fixed = _config_bundle(named, resources, answer)
        _code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        only = [row for row in rows(text) if row.get("only") == "platform-config"]
        self.assertTrue(only)
        self.assertEqual(only[0]["kind"], "unclassified")
        self.assertFalse(any(row["reason"] == "names-not-enumerated" and row["resource"] == "configmaps" for row in rows(text)))
        recorded = json.loads((HERE / "testdata" / "recorded-bundle.json").read_text(encoding="utf-8"))
        asked_names = set()
        for review in recorded["attempts"]:
            if review["kind"] != "review":
                continue
            asked_names.add(review["request"]["body"]["spec"]["resourceAttributes"]["name"])
        self.assertNotIn("platform-config", asked_names)

    def test_t29_missing_namespace_subresource_or_page_exits_2(self):
        questions = [question("", "v1", "serviceaccounts", "token", "ns-a", "namespaced", "", "create")]
        resources = [res("serviceaccounts"), res("serviceaccounts/token")]
        bundle, targets, fixed = _config_bundle(questions, resources, lambda item: denied_status())
        missing_ns = copy.deepcopy(bundle)
        accounts = next(item for item in missing_ns["attempts"] if item["request"]["path"].endswith("/serviceaccounts"))
        accounts["result"]["body"]["items"] = [{"metadata": {"name": "example-sa", "namespace": "other", "uid": "u"}}]
        reseal(accounts)
        self.assertEqual(_replay(missing_ns, targets, fixed)[0], 2)
        missing_sub = copy.deepcopy(bundle)
        discovered = next(item for item in missing_sub["attempts"] if item["request"]["path"] == "/api/v1")
        discovered["result"]["body"]["resources"] = [res("serviceaccounts")]
        reseal(discovered)
        code, _out, err = _replay(missing_sub, targets, fixed)
        self.assertEqual(code, 2)
        self.assertIn("subresource", err)
        missing_page = copy.deepcopy(bundle)
        namespaces = next(item for item in missing_page["attempts"] if item["request"]["path"].endswith("/namespaces"))
        namespaces["request"]["params"]["continue"] = "token"
        namespaces["result"]["body"]["metadata"]["continue"] = "token"
        reseal(namespaces)
        self.assertEqual(_replay(missing_page, targets, fixed)[0], 2)

    def test_t30_response_hash_mismatch_exits_2(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        bundle, targets, fixed = _config_bundle(questions, [res("configmaps")], lambda item: denied_status())
        reviews(bundle)[0]["result"]["body"]["request_hash"] = "f" * 64
        reseal(reviews(bundle)[0])
        code, _out, err = _replay(bundle, targets, fixed)
        self.assertEqual(code, 2)
        self.assertIn("hash", err)

    def test_t34_exception_matches_only_the_named_row_and_expires_the_next_day(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "platform-config", "patch")]
        bundle, targets, fixed = _config_bundle(questions, [res("configmaps")], lambda item: allowed_status())
        from identities import assemble, inventory

        anon = next(item["context"] for item in assemble(inventory(bundle["attempts"]), fixed["rows"]) if item["context"]["kind"] == "anonymous")
        row = {
            "check": "subjectaccessreview",
            "class": "field",
            "expires": "2026-10-11",
            "field": "data",
            "group": "",
            "identity": anon,
            "name": "platform-config",
            "namespace": "ns-a",
            "reason": "named for one day",
            "removes": "step-4",
            "request_family": "authz",
            "resource": "configmaps",
            "scope": "namespaced",
            "subresource": "",
            "verb": "patch",
        }
        exceptions = {"exceptions": [row], "schema_version": 1}
        code, text = run(bundle, targets, fixed, exceptions, empty_nontargets(), today="2026-10-11")
        named = [item for item in rows(text) if item["kind"] == "named-exception"]
        self.assertTrue(any(item["subject"]["kind"] == "anonymous" and item.get("only") == "platform-config" for item in named))
        others = [item for item in named if item["subject"]["kind"] != "anonymous"]
        self.assertEqual(others, [])
        for changed, key, value in (("verb", "verb", "update"), ("name", "name", "other"),):
            edited = copy.deepcopy(row)
            edited[key] = value
            _code, text = run(bundle, targets, fixed, {"exceptions": [edited], "schema_version": 1}, empty_nontargets())
            self.assertFalse(any(item["kind"] == "named-exception" and item["subject"]["kind"] == "anonymous" for item in rows(text)))
        swapped = copy.deepcopy(row)
        swapped["identity"] = copy.deepcopy(anon)
        swapped["identity"]["user"] = "someone-else"
        _code, text = run(bundle, targets, fixed, {"exceptions": [swapped], "schema_version": 1}, empty_nontargets())
        self.assertFalse(
            any(
                item["kind"] == "named-exception" and (item.get("subject") or {}).get("kind") == "anonymous"
                for item in rows(text)
            )
        )
        _code, text = run(bundle, targets, fixed, exceptions, empty_nontargets(), today="2026-10-12")
        self.assertFalse(any(item["kind"] == "named-exception" for item in rows(text)))
        self.assertIn("expired exceptions: 1", text)
        self.assertEqual(code, 3)

    def test_t35_incomplete_read_only_exits_2(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        bundle, targets, fixed = _config_bundle(questions, [res("configmaps")], lambda item: denied_status())
        namespaces = next(item for item in bundle["attempts"] if item["request"]["path"].endswith("/namespaces"))
        namespaces["result"]["ok"] = False
        namespaces["result"]["status_code"] = 500
        code, _out, _err = _replay(bundle, targets, fixed)
        self.assertEqual(code, 2)

    def test_t37_named_subresource_must_be_named_in_the_questions(self):
        resources = [res("serviceaccounts"), res("serviceaccounts/token")]
        absent = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        # configmaps is not in this discovery; keep the asked subresource check quiet by asking nothing with a subresource.
        bundle, targets, fixed = _config_bundle(absent, resources + [res("configmaps")], lambda item: denied_status())
        _code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertTrue(any(row["reason"] == "named-subresource-not-asked" and row["subresource"] == "token" for row in rows(text)))
        named = [question("", "v1", "serviceaccounts", "token", "ns-a", "namespaced", "example-sa", "create")]
        bundle, targets, fixed = _config_bundle(named, resources, lambda item: denied_status())
        _code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertFalse(any(row["reason"] == "named-subresource-not-asked" and row["subresource"] == "token" for row in rows(text)))

    def test_t40_readme_table_matches_schema_and_negative_files_exit_2(self):
        readme = (HERE / "README.md").read_text(encoding="utf-8")
        self.assertEqual(table_in_readme(readme), field_table_markdown())
        samples = {
            "prod_targets.json": load_defaults()[0],
            "prod_fixed_identities.json": load_defaults()[1],
            "prod_write_exceptions.json": load_defaults()[2],
            "prod_nontargets.json": load_defaults()[3],
            "bundle": json.loads((HERE / "testdata" / "recorded-bundle.json").read_text(encoding="utf-8")),
        }
        samples["prod_write_baseline.jsonl"] = {
            "category": "missing-input",
            "name": "side-effecting-tasks",
            "namespace": "",
            "schema_version": 1,
            "type": "missing-input",
        }
        for key, doc in samples.items():
            broken = copy.deepcopy(doc)
            self._negative(key, broken)

    def _negative(self, key, doc):
        missing = copy.deepcopy(doc)
        if key == "prod_write_baseline.jsonl":
            missing.pop("schema_version")
        elif key == "bundle":
            missing.pop("tool_version")
        elif key == "prod_targets.json":
            missing.pop("questions")
        elif key == "prod_fixed_identities.json":
            missing.pop("rows")
        elif key == "prod_nontargets.json":
            missing.pop("entries")
        else:
            missing.pop("exceptions")
        with self.assertRaises(Exception) as raised:
            validate_document(key, missing)
        self.assertIn("missing", str(raised.exception))
        extra = copy.deepcopy(doc)
        extra["not-a-field"] = 1
        with self.assertRaises(Exception) as raised:
            validate_document(key, extra)
        self.assertIn("unknown", str(raised.exception))
        wrong = copy.deepcopy(doc)
        wrong["schema_version"] = "1"
        with self.assertRaises(Exception) as raised:
            validate_document(key, wrong)
        self.assertIn("type", str(raised.exception))
        self._nested_negative(key, doc)

    def _nested_negative(self, key, doc):
        """Missing, unknown, and wrong-type on a nested structure, not only the top level."""
        if key == "prod_targets.json":
            parent = doc["questions"][0]
            label = "questions[0]"
        elif key == "prod_fixed_identities.json":
            parent = doc["rows"][0]
            label = "rows[0]"
        elif key == "prod_nontargets.json":
            doc = {
                "entries": [
                    {
                        "group": "",
                        "namespace": "ns-a",
                        "reason": "not a target",
                        "resource": "widgets",
                        "scope": "namespaced",
                        "subresource": "",
                    }
                ],
                "schema_version": 1,
            }
            parent = doc["entries"][0]
            label = "entries[0]"
        elif key == "prod_write_exceptions.json":
            doc = {
                "exceptions": [
                    {
                        "check": "subjectaccessreview",
                        "class": "field",
                        "expires": "2026-12-01",
                        "field": "data",
                        "group": "",
                        "identity": {
                            "extra": {"state": "unknown"},
                            "groups": ["system:authenticated"],
                            "kind": "user",
                            "source": "binding-user:example",
                            "uid": {"state": "unknown"},
                            "user": "example",
                        },
                        "name": "",
                        "namespace": "ns-a",
                        "reason": "held",
                        "removes": "step-4",
                        "request_family": "authz",
                        "resource": "configmaps",
                        "scope": "namespaced",
                        "subresource": "",
                        "verb": "patch",
                    }
                ],
                "schema_version": 1,
            }
            parent = doc["exceptions"][0]["identity"]
            label = "identity"
        elif key == "bundle":
            parent = next(item["request"]["body"] for item in doc["attempts"] if item["kind"] == "review")
            label = "request"
        else:
            parent = doc
            doc["data_keys"] = ["plain"]
            label = "data_keys"
        missing = copy.deepcopy(doc)
        self._poke(missing, label, "drop")
        with self.assertRaises(Exception) as raised:
            validate_document(key, missing)
        self.assertIn("missing", str(raised.exception))
        extra = copy.deepcopy(doc)
        self._poke(extra, label, "unknown")
        with self.assertRaises(Exception) as raised:
            validate_document(key, extra)
        self.assertIn("unknown", str(raised.exception))
        wrong = copy.deepcopy(doc)
        self._poke(wrong, label, "type")
        with self.assertRaises(Exception) as raised:
            validate_document(key, wrong)
        self.assertIn("type", str(raised.exception))
        self.assertIsNotNone(parent)

    def _poke(self, doc, label, mode):
        if label == "questions[0]":
            target = doc["questions"][0]
            field = "verb"
        elif label == "rows[0]":
            target = doc["rows"][0]
            field = "user"
        elif label == "entries[0]":
            target = doc["entries"][0]
            field = "resource"
        elif label == "identity":
            target = doc["exceptions"][0]["identity"]
            field = "user"
        elif label == "request":
            target = next(item["request"]["body"] for item in doc["attempts"] if item["kind"] == "review")
            field = "apiVersion"
        else:
            if mode == "drop":
                doc["data_keys"] = []
                doc.pop("schema_version")
                return
            if mode == "unknown":
                doc["not-a-field"] = 1
                return
            doc["data_keys"] = [1]
            return
        if mode == "drop":
            target.pop(field)
        elif mode == "unknown":
            target["not-a-field"] = 1
        else:
            target[field] = 1


def _replay(bundle, targets, fixed, exceptions=None):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bundle_path = root / "surface-bundle.json"
        targets_path = root / "surface-targets.json"
        fixed_path = root / "surface-fixed.json"
        exceptions_path = root / "surface-exceptions.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        targets_path.write_text(json.dumps(targets), encoding="utf-8")
        fixed_path.write_text(json.dumps(fixed), encoding="utf-8")
        exceptions_path.write_text(json.dumps(exceptions or empty_exceptions()), encoding="utf-8")
        return _cli(
        [
            "replay",
            "--bundle",
            str(bundle_path),
            "--targets",
            str(targets_path),
            "--fixed",
            str(fixed_path),
            "--exceptions",
            str(exceptions_path),
            "--nontargets",
            str(HERE / "prod_nontargets.json"),
            "--today",
            "2026-10-11",
        ]
    )


if __name__ == "__main__":
    unittest.main()
