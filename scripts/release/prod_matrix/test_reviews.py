"""Round-1 tests T07–T09, T17, T20, T28, T31, T32, T36, T38–T41."""

from __future__ import annotations

import io
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import prod_measure  # noqa: E402
from questions import sar_spec  # noqa: E402
from support import (  # noqa: E402
    allowed_status,
    base_commands,
    bundle_from,
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


def _ops_binding() -> dict:
    return {
        "metadata": {"name": "ops", "namespace": "ns-a"},
        "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "view"},
        "subjects": [{"apiGroup": "rbac.authorization.k8s.io", "kind": "Group", "name": "ops-admins"}],
    }


def _small(answer, questions, confirmed=False, discovery_docs=None):
    fixed = copy_fixed(confirmed)
    commands = base_commands(["ns-a"], bindings=[_ops_binding()])
    docs = discovery_docs or [("/api/v1", discovery("v1", [res("configmaps")]))]
    for index, (path, body) in enumerate(docs, start=8):
        from support import command

        commands.append(command(index, path, body))
    bundle = bundle_from(commands, targets_of(questions), fixed, answer)
    return bundle, targets_of(questions), fixed


class ReviewTests(unittest.TestCase):
    def test_t07_group_member_is_unclassified_without_an_exception(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]

        def answer(item):
            if item["identity"]["context"]["user"] == "prod-matrix:member-of:ops-admins":
                return allowed_status()
            return denied_status()

        bundle, targets, fixed = _small(answer, questions)
        code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        matched = [
            row
            for row in rows(text)
            if row["kind"] == "unclassified" and (row.get("subject") or {}).get("user") == "prod-matrix:member-of:ops-admins"
        ]
        self.assertTrue(matched)
        self.assertEqual(matched[0]["subject"]["groups"], ["ops-admins", "system:authenticated"])
        self.assertEqual(matched[0]["subject"]["uid"], {"state": "unknown"})
        self.assertNotIn("exception_class", matched[0])
        self.assertNotEqual(code, 0)

    def test_t08_missing_fixed_identity_exits_2(self):
        _targets, fixed, _exceptions, _nontargets = load_defaults()
        for dropped in ("member-of-system-masters", "k3s-admin-credentials", "node-root", "anonymous", "auth-chain"):
            doc = {"rows": [row for row in fixed["rows"] if row["id"] != dropped], "schema_version": 1}
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / f"missing-{dropped}.json"
                path.write_text(json.dumps(doc), encoding="utf-8")
                code, _out, err = _cli(
                    ["replay", "--bundle", str(HERE / "testdata" / "recorded-bundle.json"), "--fixed", str(path)]
                )
            self.assertEqual(code, 2, dropped)
            self.assertIn(dropped, err)

    def test_t09_bad_reviews_are_unknown_surface(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        cases = {
            "evaluation-error": {"allowed": False, "denied": False, "evaluationError": "no opinion from webhook"},
            "missing-status": None,
            "no-opinion": {"allowed": False, "denied": False},
            "malformed": {"allowed": "yes", "denied": False},
            "contradictory": {"allowed": True, "denied": True},
        }
        for reason, status in cases.items():
            def answer(item, status=status):
                return status

            bundle, targets, fixed = _small(answer, questions)
            if status is None:
                for review in bundle["reviews"]:
                    review["response"].pop("status", None)
            elif reason == "malformed":
                for review in bundle["reviews"]:
                    review["response"]["status"] = {"allowed": "yes", "denied": False}
            code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
            kinds = {row["reason"] for row in rows(text) if row["kind"] == "unknown-surface"}
            self.assertIn(reason, kinds, reason)
            self.assertNotEqual(code, 0)
            self.assertNotIn("refused", text)

    def test_t17_question_count_over_budget_exits_2_without_a_partial_matrix(self):
        questions = [
            question("", "v1", "configmaps", "", "ns-a", "namespaced", "", f"verb{index}") for index in range(10000)
        ]
        bundle, targets, fixed = _small(lambda item: denied_status(), questions[:1])
        targets = targets_of(questions)
        code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(code, 2)
        self.assertIn("unclassified: derivation truncated", text)
        self.assertEqual(sum(1 for row in rows(text) if row["reason"] != "derivation truncated"), 0)

    def test_t20_missing_slice_b_is_unknown_surface(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        bundle, targets, fixed = _small(lambda item: denied_status(), questions)
        code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertNotEqual(code, 0)
        self.assertTrue(any(row["reason"] == "side-effecting tasks not provided" for row in rows(text)))

    def test_t28_node_groups_and_unknown_uid_extra(self):
        from identities import node_context

        spec = sar_spec(node_context("node-a", "node:node-a"), question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch"))
        self.assertIn("system:nodes", spec["groups"])
        self.assertIn("system:authenticated", spec["groups"])
        self.assertNotIn("uid", spec)
        self.assertNotIn("extra", spec)
        member = sar_spec(
            __import__("identities", fromlist=["group_member"]).group_member("ops-admins", "group-member:ops-admins"),
            question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch"),
        )
        self.assertEqual(member["groups"], ["ops-admins", "system:authenticated"])
        self.assertNotIn("uid", member)
        self.assertNotIn("extra", member)
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        commands = base_commands(["ns-a"], nodes=[{"metadata": {"name": "node-a"}}])
        from support import command

        commands.append(command(8, "/api/v1", discovery("v1", [res("configmaps")])))
        bundle = bundle_from(commands, targets_of(questions), copy_fixed(), lambda item: denied_status())
        for review in bundle["reviews"]:
            user = review["request"]["spec"]["user"]
            if user.startswith("system:node:"):
                review["request"]["spec"]["groups"] = ["system:nodes"]
                review["request_hash"] = "0" * 64
                review["id"] = "q-" + "0" * 16
                review["response"]["request_hash"] = review["request_hash"]
        code, _text, err = _replay_raw(bundle, targets_of(questions), copy_fixed())
        self.assertEqual(code, 2)
        self.assertTrue(err)

    def test_t31_allowed_denied_and_confirmed_no_opinion(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "platform-config", "patch")]

        def answer(item):
            user = item["identity"]["context"]["user"]
            if user == "system:anonymous":
                return allowed_status()
            if user.endswith("ops-admins"):
                return {"allowed": False, "denied": False}
            return denied_status()

        bundle, targets, fixed = _small(answer, questions, confirmed=True)
        code, text = run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        allowed_rows = [row for row in rows(text) if row["reason"] == "allowed"]
        self.assertTrue(any(row["subject"]["user"] == "system:anonymous" for row in allowed_rows))
        self.assertTrue(all(row["kind"] == "unclassified" for row in allowed_rows))
        self.assertNotIn("refused", text)
        self.assertIn("asked-not-allowed:", text)
        denied_users = {row.get("subject", {}).get("user") for row in rows(text) if row["kind"] != "unknown-surface" or row["reason"] in {"no-opinion", "allowed"}}
        self.assertNotIn("prod-matrix:member-of:ops-admins", {row.get("subject", {}).get("user") for row in rows(text) if row["reason"] in {"allowed", "no-opinion"}})
        self.assertNotEqual(code, 0)
        self.assertNotIn("no-opinion", {row["reason"] for row in rows(text)})

    def test_t32_read_only_half_exits_3_and_states_the_limit(self):
        code, out, err = _cli(["replay", "--bundle", str(HERE / "testdata" / "recorded-bundle.json")])
        self.assertEqual(code, 3)
        self.assertTrue(out.startswith("authorization only; questions are the explicit list, not exhaustive\n"))
        self.assertNotIn("refused", out)
        self.assertNotIn("refused", err)

    def test_t36_replay_does_not_open_a_process_or_a_socket(self):
        def boom(*_args, **_kwargs):
            raise AssertionError("replay opened a process or a socket")

        originals = (subprocess.run, subprocess.Popen, socket.socket, socket.create_connection)
        subprocess.run = boom
        subprocess.Popen = boom
        socket.socket = boom
        socket.create_connection = boom
        try:
            code, out, _err = _cli(["replay", "--bundle", str(HERE / "testdata" / "recorded-bundle.json")])
        finally:
            subprocess.run, subprocess.Popen, socket.socket, socket.create_connection = originals
        self.assertEqual(code, 3)
        self.assertNotIn("refused", out)

    def test_t38_over_budget_sends_nothing(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", f"v{index}") for index in range(10000)]
        calls = []

        def boom(*_args, **_kwargs):
            calls.append(1)
            raise AssertionError("a request was sent")

        original = subprocess.run
        subprocess.run = boom
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "too-many-questions.json"
                out_path = Path(tmp) / "should-not-write.json"
                path.write_text(json.dumps(targets_of(questions)), encoding="utf-8")
                code, out, _err = _cli(["collect", "--bundle-out", str(out_path), "--targets", str(path)])
                self.assertFalse(out_path.exists())
        finally:
            subprocess.run = original
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        lines = out.splitlines()
        self.assertEqual(lines[0], "authorization only; questions are the explicit list, not exhaustive")
        self.assertTrue(lines[2].startswith("question count:"))
        self.assertIn("unclassified: derivation truncated", out)

    def test_collect_uses_a_fake_kubectl_on_path(self):
        import os
        import stat
        import tempfile

        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        with tempfile.TemporaryDirectory() as tmp:
            targets = Path(tmp) / "one-question.json"
            targets.write_text(json.dumps(targets_of(questions)), encoding="utf-8")
            out_path = Path(tmp) / "collected-one.json"
            kubectl = Path(tmp) / "kubectl"
            fake = HERE / "testdata" / "fake_kubectl.py"
            kubectl.write_text(f'#!/bin/sh\nexec python3 "{fake}" "$@"\n', encoding="utf-8")
            kubectl.chmod(stat.S_IRWXU)
            previous = os.environ.get("PATH", "")
            os.environ["PATH"] = str(Path(tmp)) + os.pathsep + previous
            try:
                code, out, err = _cli(["collect", "--bundle-out", str(out_path), "--targets", str(targets)])
                self.assertEqual(code, 3, err)
                lines = out.splitlines()
                self.assertEqual(lines[0], "authorization only; questions are the explicit list, not exhaustive")
                self.assertTrue(lines[2].startswith("question count:"))
                self.assertNotIn("refused", out)
                code, replay_out, err = _cli(["replay", "--bundle", str(out_path), "--targets", str(targets)])
                self.assertEqual(code, 3, err)
                self.assertTrue(replay_out.startswith("authorization only; questions are the explicit list, not exhaustive\n"))
            finally:
                os.environ["PATH"] = previous

    def test_t39_missing_duplicate_and_repeated_ids_exit_2(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        bundle, targets, fixed = _small(lambda item: denied_status(), questions)
        missing = json.loads(json.dumps(bundle))
        missing["reviews"] = missing["reviews"][1:]
        self.assertEqual(_replay_raw(missing, targets, fixed)[0], 2)
        doubled = json.loads(json.dumps(bundle))
        doubled["reviews"].append(dict(doubled["reviews"][0]))
        self.assertEqual(_replay_raw(doubled, targets, fixed)[0], 2)
        repeated = json.loads(json.dumps(bundle))
        clone = dict(repeated["reviews"][0])
        clone["retry_of"] = clone["id"]
        repeated["reviews"].append(clone)
        extra = dict(clone)
        extra["retry_of"] = clone["id"]
        repeated["reviews"].append(extra)
        # Two retries that reuse the primary id are a repeated id, not a second pass over `doubled`.
        self.assertEqual(_replay_raw(repeated, targets, fixed)[0], 2)

    def test_t41_summary_lines_and_no_refusal_and_no_zero(self):
        code, out, err = _cli(["replay", "--bundle", str(HERE / "testdata" / "recorded-bundle.json")])
        lines = out.splitlines()
        self.assertEqual(lines[0], "authorization only; questions are the explicit list, not exhaustive")
        self.assertTrue(lines[1].startswith("not-asked:"))
        self.assertIn("names-not-enumerated:", lines[1])
        self.assertIn("named-subresource-not-asked:", lines[1])
        self.assertNotIn("refused", out)
        self.assertNotIn("refused", err)
        self.assertNotEqual(code, 0)
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "not-json.json"
            bad.write_text("{", encoding="utf-8")
            code, out, err = _cli(["replay", "--bundle", str(bad)])
        self.assertEqual(out.splitlines()[0], "authorization only; questions are the explicit list, not exhaustive")
        self.assertNotEqual(code, 0)
        self.assertNotIn("refused", out)


def _cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = prod_measure.main(argv)
    return code, out.getvalue(), err.getvalue()


def _replay_raw(bundle, targets, fixed):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        bundle_path = root / "case-bundle.json"
        targets_path = root / "case-targets.json"
        fixed_path = root / "case-fixed.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
        targets_path.write_text(json.dumps(targets), encoding="utf-8")
        fixed_path.write_text(json.dumps(fixed), encoding="utf-8")
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
            str(HERE / "prod_write_exceptions.json"),
            "--nontargets",
            str(HERE / "prod_nontargets.json"),
        ]
    )


if __name__ == "__main__":
    unittest.main()
