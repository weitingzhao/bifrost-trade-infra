"""Round-2 tests. Each one fails on 713ca39."""

from __future__ import annotations

import copy
import json
import os
import stat
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from canon import MatrixExit  # noqa: E402
from collect import Session  # noqa: E402
from exceptions import match_risk, prepare  # noqa: E402
from identities import fixed_identity  # noqa: E402
from ratchet import diff, lines_of, scan  # noqa: E402
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
    rows,
    run,
    targets_of,
)
from test_reviews import _cli  # noqa: E402


def _small_bundle(resource_name="configmaps"):
    questions = [question("", "v1", resource_name, "", "ns-a", "namespaced", "", "patch")]
    commands = base_commands(["ns-a"])
    commands.append(command(8, "/api/v1", discovery("v1", [res("configmaps")])))
    fixed = copy_fixed()
    targets = targets_of(questions)
    bundle = bundle_from(commands, targets, fixed, lambda item: denied_status())
    return bundle, targets, fixed


class Round2Tests(unittest.TestCase):
    def test_deleted_discovery_command_exits_2(self):
        bundle = json.loads((HERE / "testdata" / "recorded-bundle.json").read_text(encoding="utf-8"))
        bundle["commands"] = [
            item for item in bundle["commands"] if item["request"]["path"] != "/apis/traefik.io/v1alpha1"
        ]
        targets, fixed, exceptions, nontargets = load_defaults()
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, exceptions, nontargets)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("traefik.io/v1alpha1", raised.exception.message)

    def test_failed_root_discovery_exits_2(self):
        bundle = json.loads((HERE / "testdata" / "recorded-bundle.json").read_text(encoding="utf-8"))
        for item in bundle["commands"]:
            if item["request"]["path"] == "/api":
                item["ok"] = False
                item["status_code"] = 500
        targets, fixed, exceptions, nontargets = load_defaults()
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, exceptions, nontargets)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("/api", raised.exception.message)

    def test_collect_fetches_every_served_version(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            targets = root / "targets.json"
            targets.write_text(json.dumps(targets_of(questions)), encoding="utf-8")
            out = root / "bundle.json"
            kubectl = root / "kubectl"
            fake = HERE / "testdata" / "fake_kubectl.py"
            kubectl.write_text(f'#!/bin/sh\nexec python3 "{fake}" "$@"\n', encoding="utf-8")
            kubectl.chmod(stat.S_IRWXU)
            previous = os.environ.get("PATH", "")
            os.environ["PATH"] = str(root) + os.pathsep + previous
            try:
                code, _text, err = _cli(["collect", "--bundle-out", str(out), "--targets", str(targets)])
            finally:
                os.environ["PATH"] = previous
            self.assertEqual(code, 3, err)
            bundle = json.loads(out.read_text(encoding="utf-8"))
        paths = [item["request"]["path"].split("?", 1)[0] for item in bundle["commands"]]
        self.assertIn("/apis/apps/v1", paths)
        self.assertIn("/apis/apps/v1beta1", paths)

    def test_all_denied_fixture_prints_each_fixed_identity(self):
        bundle = json.loads((HERE / "testdata" / "recorded-bundle.json").read_text(encoding="utf-8"))
        targets, fixed, exceptions, nontargets = load_defaults()
        code, text = run(bundle, targets, fixed, exceptions, nontargets)
        self.assertEqual(code, 3)
        printed = {
            (row.get("subject") or {}).get("source")
            for row in rows(text)
            if row["kind"] in {"unclassified", "named-exception"} and "resource" not in row
        }
        self.assertEqual(
            printed,
            {
                "fixed:member-of-system-masters",
                "fixed:k3s-admin-credentials",
                "fixed:node-root",
                "fixed:anonymous",
            },
        )

    def test_unconfirmed_context_is_not_a_denial(self):
        bundle = json.loads((HERE / "testdata" / "recorded-bundle.json").read_text(encoding="utf-8"))
        targets, fixed, exceptions, nontargets = load_defaults()
        _code, text = run(bundle, targets, fixed, exceptions, nontargets)
        self.assertIn("asked-not-allowed: 49\n", text)
        self.assertNotIn("asked-not-allowed: 294", text)
        affected = [
            row
            for row in rows(text)
            if row["reason"] == "context-unconfirmed"
            and (row.get("subject") or {}).get("user") == "prod-matrix:member-of:system:masters"
        ]
        self.assertTrue(affected)
        self.assertFalse(
            any(
                row["reason"] == "context-unconfirmed" and (row.get("subject") or {}).get("user") == "system:anonymous"
                for row in rows(text)
            )
        )

    def test_configmap_question_is_rejected_before_reviews(self):
        bundle, targets, fixed = _small_bundle("ConfigMap")
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("ConfigMap", raised.exception.message)
        questions = [question("", "v1", "ConfigMap", "", "ns-a", "namespaced", "", "patch")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            targets_path = root / "targets.json"
            targets_path.write_text(json.dumps(targets_of(questions)), encoding="utf-8")
            log = root / "argv"
            kubectl = root / "kubectl"
            fake = HERE / "testdata" / "fake_kubectl.py"
            kubectl.write_text(
                f'#!/bin/sh\necho "$@" >> "{log}"\nexec python3 "{fake}" "$@"\n',
                encoding="utf-8",
            )
            kubectl.chmod(stat.S_IRWXU)
            previous = os.environ.get("PATH", "")
            os.environ["PATH"] = str(root) + os.pathsep + previous
            try:
                code, _out, err = _cli(
                    ["collect", "--bundle-out", str(root / "out.json"), "--targets", str(targets_path)]
                )
            finally:
                os.environ["PATH"] = previous
            self.assertEqual(code, 2, err)
            self.assertIn("ConfigMap", err)
            self.assertNotIn("/v1/subjectaccessreviews", log.read_text(encoding="utf-8"))

    def test_missing_middle_page_exits_2(self):
        bundle, targets, fixed = _small_bundle()
        roles = next(item for item in bundle["commands"] if item["request"]["path"].endswith("/roles"))
        roles["pages"] = [
            {"body": {"items": [], "kind": "RoleList", "metadata": {"continue": "t1"}}, "continue": "t1"},
            {"body": {"items": [], "kind": "RoleList", "metadata": {"continue": ""}}, "continue": ""},
        ]
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("page", raised.exception.message)

    def test_role_list_without_items_exits_2(self):
        bundle, targets, fixed = _small_bundle()
        roles = next(item for item in bundle["commands"] if item["request"]["path"].endswith("/roles"))
        roles["pages"][0]["body"].pop("items")
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("items", raised.exception.message)

    def test_complete_page_chain_replays(self):
        bundle, targets, fixed = _small_bundle()
        roles = next(item for item in bundle["commands"] if item["request"]["path"].endswith("/roles"))
        roles["pages"] = [
            {"body": {"items": [], "kind": "RoleList", "metadata": {"continue": "t1"}}, "continue": ""},
            {"body": {"items": [], "kind": "RoleList", "metadata": {"continue": "t2"}}, "continue": "t1"},
            {"body": {"items": [], "kind": "RoleList", "metadata": {"continue": ""}}, "continue": "t2"},
        ]
        code, _text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(code, 3)
        del roles["pages"][1]
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)

    def test_retry_with_duplicate_id_and_wrong_hash_exits_2(self):
        bundle, targets, fixed = _small_bundle()
        clone = copy.deepcopy(bundle["reviews"][0])
        clone["request_hash"] = "ab" * 32
        clone["response"]["request_hash"] = clone["request_hash"]
        clone["retry_of"] = clone["id"]
        bundle["reviews"].append(clone)
        bundle["reviews"].append(copy.deepcopy(clone))
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)

    def test_discovery_retry_uses_the_successful_attempt(self):
        bundle, targets, fixed = _small_bundle()
        for item in bundle["commands"]:
            if item["request"]["path"] != "/api/v1":
                continue
            failed = copy.deepcopy(item)
            failed["ok"] = False
            failed["status_code"] = 503
            ok = copy.deepcopy(item)
            ok["id"] = item["id"] + "-r1"
            ok["retry_of"] = item["id"]
            bundle["commands"] = [failed if command["id"] == item["id"] else command for command in bundle["commands"]]
            bundle["commands"].append(ok)
            break
        code, _text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(code, 3)

    def test_diff_reports_order_and_repeats(self):
        order = diff(["a", "b"], ["b", "a"])
        repeat = diff(["a"], ["a", "a"])
        self.assertTrue(order)
        self.assertTrue(repeat)
        self.assertIn("顺序不同", order)
        self.assertIn("重复一行", repeat)

    def test_webhook_failure_policy_changes_the_row(self):
        body = textwrap.dedent(
            """\
            apiVersion: admissionregistration.k8s.io/v1
            kind: ValidatingWebhookConfiguration
            metadata:
              name: example-webhook
            webhooks:
              - name: example.invalid
                failurePolicy: Fail
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "webhook.yaml").write_text(body, encoding="utf-8")
            before = lines_of(scan(root, HERE / "prod_fixed_identities.json"))
            (root / "webhook.yaml").write_text(body.replace("Fail", "Ignore"), encoding="utf-8")
            after = lines_of(scan(root, HERE / "prod_fixed_identities.json"))
        self.assertNotEqual(before, after)

    def test_question_count_is_checked_before_discovery(self):
        calls = []

        def transport(method, path, body):
            bare = path.split("?", 1)[0]
            calls.append(bare)
            if method == "WHOAMI":
                payload = {"status": {"userInfo": {"username": "system:serviceaccount:bifrost-access:bifrost-agent", "groups": ["system:authenticated"]}}}
            elif method == "POST":
                payload = {"status": {"allowed": True}}
            elif bare == "/api/v1/serviceaccounts":
                payload = {
                    "items": [
                        {"metadata": {"name": f"sa-{index}", "namespace": "ns-a", "uid": f"uid-{index}"}}
                        for index in range(450)
                    ],
                    "kind": "ServiceAccountList",
                    "metadata": {"continue": ""},
                }
            elif bare == "/api/v1/namespaces":
                payload = {"items": [{"metadata": {"name": "ns-a"}}], "kind": "NamespaceList", "metadata": {"continue": ""}}
            else:
                payload = {"items": [], "kind": "List", "metadata": {"continue": ""}}
            return 0, json.dumps(payload), ""

        import collect

        original = collect.kubectl_transport
        collect.kubectl_transport = transport
        try:
            with tempfile.TemporaryDirectory() as tmp:
                code, out, err = _cli(["collect", "--bundle-out", str(Path(tmp) / "out.json")])
        finally:
            collect.kubectl_transport = original
        self.assertEqual(code, 2, err)
        self.assertNotIn("/api", calls)
        self.assertFalse(any(path.endswith("/subjectaccessreviews") for path in calls))
        lines = out.splitlines()
        self.assertEqual(lines[0], "authorization only; questions are the explicit list, not exhaustive")
        self.assertTrue(lines[2].startswith("question count:"))

    def test_replay_rejects_too_many_attempts(self):
        bundle, targets, fixed = _small_bundle()
        extra = copy.deepcopy(bundle["commands"][0])
        for index in range(500):
            item = copy.deepcopy(extra)
            item["id"] = f"extra-{index}"
            bundle["commands"].append(item)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bundle.json"
            targets_path = Path(tmp) / "targets.json"
            fixed_path = Path(tmp) / "fixed.json"
            path.write_text(json.dumps(bundle), encoding="utf-8")
            targets_path.write_text(json.dumps(targets), encoding="utf-8")
            fixed_path.write_text(json.dumps(fixed), encoding="utf-8")
            code, _out, err = _cli(
                [
                    "replay",
                    "--bundle",
                    str(path),
                    "--targets",
                    str(targets_path),
                    "--fixed",
                    str(fixed_path),
                ]
            )
        self.assertEqual(code, 2)
        self.assertIn("read attempts", err)
        bundle, targets, fixed = _small_bundle()
        while len(bundle["reviews"]) <= 20000:
            bundle["reviews"].append({"id": f"pad-{len(bundle['reviews'])}"})
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("review attempts", raised.exception.message)

    def test_wall_clock_is_checked_after_the_request(self):
        def transport(method, path, body):
            time.sleep(0.05)
            return 0, "{}", ""

        session = Session(transport, wall_seconds=0.01)
        with self.assertRaises(MatrixExit) as raised:
            session.call("GET", "/api", None, "read")
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("wall", raised.exception.message)

    def test_node_root_exception_does_not_match_a_foreign_scope(self):
        _targets, fixed, _exceptions, _nontargets = load_defaults()
        row = next(item for item in fixed["rows"] if item["id"] == "node-root")
        ctx, _ask = fixed_identity(row)
        exception = {
            "check": "subjectaccessreview",
            "class": "trust-root",
            "expires": "2026-12-01",
            "expired": False,
            "field": "",
            "group": "",
            "identity": ctx,
            "name": "",
            "namespace": "wrong",
            "reason": "node root",
            "removes": "step-4",
            "request_family": "authz",
            "resource": "",
            "scope": "namespaced",
            "subresource": "",
            "verb": "",
        }
        self.assertFalse(match_risk(exception, ctx))
        matching = dict(exception)
        matching["scope"] = "cluster"
        matching["namespace"] = ""
        self.assertTrue(match_risk(matching, ctx))


class RatchetLimitTests(unittest.TestCase):
    def test_prepare_rejects_namespace_on_a_cluster_exception(self):
        from datetime import date

        _targets, fixed, _exceptions, _nontargets = load_defaults()
        row = next(item for item in fixed["rows"] if item["id"] == "node-root")
        ctx, _ask = fixed_identity(row)
        foreign = {
            "check": "subjectaccessreview",
            "class": "trust-root",
            "expires": "2026-12-01",
            "field": "",
            "group": "",
            "identity": ctx,
            "name": "",
            "namespace": "wrong",
            "reason": "node root",
            "removes": "step-4",
            "request_family": "authz",
            "resource": "",
            "scope": "cluster",
            "subresource": "",
            "verb": "",
        }
        with self.assertRaises(MatrixExit) as raised:
            prepare([foreign], date(2026, 10, 11))
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("namespace", raised.exception.message)
