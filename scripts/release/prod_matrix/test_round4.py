"""Round 4. One protocol transport: the collector, the bundle, and the replay."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from apiserver import FakeApiserver  # noqa: E402
from canon import MatrixExit  # noqa: E402
from support import (  # noqa: E402
    allowed_status,
    bundle_from,
    base_commands,
    command,
    copy_fixed,
    discovery,
    empty_exceptions,
    empty_nontargets,
    load_defaults,
    question,
    res,
    reseal,
    reviews,
    run,
    targets_of,
)
from test_reviews import _cli  # noqa: E402
from test_round2 import _small_bundle  # noqa: E402

_SPEC = importlib.util.spec_from_file_location("fake_kubectl", HERE / "testdata" / "fake_kubectl.py")
_FAKE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FAKE)
RESPOND = _FAKE.respond

PAGE_1 = ["bifrost-platform-prod", "cicd", "data"]
PAGE_2 = ["ns-a"]
SUMMARY = "authorization only; questions are the explicit list, not exhaustive\n"


def _handler(method: str, path: str, query: dict, body):
    if method == "GET" and path == "/api/v1/namespaces":
        if query.get("continue") == "t1":
            names, token = PAGE_2, ""
        else:
            names, token = PAGE_1, "t1"
        return {
            "items": [{"metadata": {"name": name}} for name in names],
            "kind": "NamespaceList",
            "metadata": {"continue": token},
        }
    return RESPOND(method, path, body)


class Round4Tests(unittest.TestCase):
    def test_e2e_fake_apiserver_collects_pages_retries_and_replays(self):
        probe = FakeApiserver(_handler)
        probe("GET", "/api/v1/namespaces?limit=500", None)
        code, _stdout, err = probe("GET", "/api/v1/namespaces?limit=500", None)
        self.assertNotEqual(code, 0)
        self.assertIn("continue", err)

        server = FakeApiserver(_handler, scripts={"/api": [503, 503]})
        log = []

        def now():
            stamp = f"2026-10-11T00:{(len(log) // 60) % 60:02d}:{len(log) % 60:02d}Z"
            log.append(("now", stamp))
            return stamp

        def transport(method, path, body):
            log.append(("send", path))
            return server(method, path, body)

        import collect

        original_transport = collect.kubectl_transport
        original_now = collect._now
        collect.kubectl_transport = transport
        collect._now = now
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                targets = root / "targets.json"
                out = root / "bundle.json"
                questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
                targets.write_text(json.dumps(targets_of(questions)), encoding="utf-8")
                code, text, err = _cli(["collect", "--bundle-out", str(out), "--targets", str(targets)])
                self.assertEqual(code, 3, err)
                bundle = json.loads(out.read_text(encoding="utf-8"))
        finally:
            collect.kubectl_transport = original_transport
            collect._now = original_now

        self.assertTrue(text.startswith(SUMMARY))
        self.assertNotIn("refused", text)
        self.assertNotIn("refused", err)
        namespaces = [item for item in server.received if item["path"] == "/api/v1/namespaces"]
        self.assertEqual(len(namespaces), 2)
        self.assertEqual(namespaces[0]["query"].get("limit"), "500")
        self.assertNotIn("continue", namespaces[0]["query"])
        self.assertEqual(namespaces[1]["query"].get("continue"), "t1")
        self.assertIn("limit=500", namespaces[1]["raw"])
        self.assertIn("continue=t1", namespaces[1]["raw"])

        attempts = bundle["attempts"]
        self.assertEqual(len(attempts), len(server.received))
        self.assertEqual([item["attempt"] for item in attempts], list(range(1, len(attempts) + 1)))
        api = [item for item in attempts if item["request"]["path"] == "/api"]
        self.assertEqual(len(api), 3)
        self.assertNotIn("retry_of", api[0])
        self.assertEqual(api[1]["retry_of"], api[0]["attempt"])
        self.assertEqual(api[2]["retry_of"], api[1]["attempt"])
        self.assertTrue(api[2]["result"]["ok"])
        self.assertEqual(api[2]["result"]["status_code"], 200)
        self.assertFalse(api[0]["result"]["ok"])
        self.assertEqual(api[0]["result"]["status_code"], 503)

        sends = [index for index, item in enumerate(log) if item[0] == "send"]
        self.assertEqual(len(sends), len(attempts))
        for attempt, index in zip(attempts, sends):
            self.assertEqual(log[index - 1][0], "now")
            self.assertEqual(log[index + 1][0], "now")
            self.assertEqual(attempt["started_at"], log[index - 1][1])
            self.assertEqual(attempt["finished_at"], log[index + 1][1])

    def test_failed_last_review_is_not_a_denial(self):
        bundle = json.loads((HERE / "testdata" / "recorded-bundle.json").read_text(encoding="utf-8"))
        review = next(
            item
            for item in bundle["attempts"]
            if item["kind"] == "review" and item["request"]["body"]["spec"]["user"] == "system:anonymous"
        )
        review["result"]["ok"] = False
        review["result"]["status_code"] = 503
        targets, fixed, exceptions, nontargets = load_defaults()
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, exceptions, nontargets)
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("review failed", raised.exception.message)

    def test_failed_retry_does_not_replace_an_allowed_row(self):
        questions = [question("", "v1", "configmaps", "", "ns-a", "namespaced", "", "patch")]
        commands = base_commands(["ns-a"])
        commands.append(command(8, "/api/v1", discovery("v1", [res("configmaps")])))
        bundle = bundle_from(commands, targets_of(questions), copy_fixed(True), lambda item: allowed_status())
        review = next(item for item in reviews(bundle) if item["request"]["body"]["spec"]["user"] == "system:anonymous")
        failed = copy.deepcopy(review)
        failed["attempt"] = max(item["attempt"] for item in bundle["attempts"]) + 1
        failed["retry_of"] = review["attempt"]
        failed["result"]["ok"] = False
        failed["result"]["status_code"] = 503
        failed["result"]["body"] = {
            "apiVersion": "authorization.k8s.io/v1",
            "kind": "SubjectAccessReview",
            "status": {"allowed": False, "denied": True},
        }
        reseal(failed)
        bundle["attempts"].append(failed)
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets_of(questions), copy_fixed(True), empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("review failed", raised.exception.message)

    def test_attempt_numbers_must_be_contiguous(self):
        bundle, targets, fixed = _small_bundle()
        last = max(bundle["attempts"], key=lambda item: item["attempt"])
        last["attempt"] += 10
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("1..n", raised.exception.message)

    def test_continue_zero_is_not_an_empty_token(self):
        bundle, targets, fixed = _small_bundle()
        roles = next(item for item in bundle["attempts"] if item["request"]["path"].endswith("/roles"))
        roles["result"]["body"]["metadata"]["continue"] = 0
        reseal(roles)
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("continue", raised.exception.message)

    def test_clusterrolebinding_subject_namespace_must_be_listed(self):
        bundle, targets, fixed = _small_bundle()
        binding = next(item for item in bundle["attempts"] if item["request"]["path"].endswith("/clusterrolebindings"))
        binding["result"]["body"]["items"] = [
            {
                "metadata": {"name": "ghost-binding"},
                "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "view"},
                "subjects": [{"kind": "ServiceAccount", "name": "ghost-sa", "namespace": "ghost"}],
            }
        ]
        reseal(binding)
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("ghost", raised.exception.message)

    def test_subject_namespace_zero_is_not_empty(self):
        bundle, targets, fixed = _small_bundle()
        binding = next(item for item in bundle["attempts"] if item["request"]["path"].endswith("/rolebindings"))
        binding["result"]["body"]["items"] = [
            {
                "metadata": {"name": "numbered", "namespace": "ns-a"},
                "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "view"},
                "subjects": [{"kind": "ServiceAccount", "name": "example-sa", "namespace": 0}],
            }
        ]
        reseal(binding)
        with self.assertRaises(MatrixExit) as raised:
            run(bundle, targets, fixed, empty_exceptions(), empty_nontargets())
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("not a string", raised.exception.message)

    def test_readme_says_the_bundle_is_unsigned(self):
        text = (HERE / "README.md").read_text(encoding="utf-8")
        self.assertIn("没有签名", text)
        self.assertIn("不能证明原始回答是真的", text)


if __name__ == "__main__":
    unittest.main()
