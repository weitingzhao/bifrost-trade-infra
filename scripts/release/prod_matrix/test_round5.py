"""Round 5. Every request group has a result, and a review is bound to its endpoint.

These tests fail on 5812f3d: a failed whoami or self-check still replays, and a
review with an empty path, GET, or another endpoint is still counted.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from support import load_defaults, reseal, run  # noqa: E402

BUNDLE_PATH = HERE / "testdata" / "recorded-bundle.json"
SAR_PATH = "/apis/authorization.k8s.io/v1/subjectaccessreviews"
SSAR_PATH = "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews"
WHOAMI_PATH = "/apis/authentication.k8s.io/v1/selfsubjectreviews"


def _bundle():
    return json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))


def _inputs():
    return load_defaults()


def _outcome(bundle):
    targets, fixed, exceptions, nontargets = _inputs()
    try:
        code, text = run(bundle, targets, fixed, exceptions, nontargets)
    except Exception as exc:  # noqa: BLE001 — MatrixExit, or a crash, is the outcome
        code = getattr(exc, "code", None)
        text = getattr(exc, "message", None) or repr(exc)
    lines = text.splitlines()
    return code, "\n".join(lines[:6])


class Round5Tests(unittest.TestCase):
    def test_failed_auxiliary_read_exits_2(self):
        """Whoami and every permission self-check: a failed last attempt is exit 2."""
        bundle = _bundle()
        auxiliary = [
            item
            for item in bundle["attempts"]
            if item["request"]["path"] in {WHOAMI_PATH, SSAR_PATH}
        ]
        self.assertEqual(len(auxiliary), 9)
        for attempt in auxiliary:
            mutant = _bundle()
            target = next(item for item in mutant["attempts"] if item["attempt"] == attempt["attempt"])
            target["result"]["ok"] = False
            target["result"]["status_code"] = 503
            code, text = _outcome(mutant)
            self.assertEqual(code, 2, text)
            self.assertIn(target["request"]["path"], text)
            self.assertIn(str(target["attempt"]), text)

    def test_review_must_be_post_to_its_endpoint(self):
        bundle = _bundle()
        review = next(item for item in bundle["attempts"] if item["kind"] == "review")
        number = review["attempt"]

        def replay(mutate):
            mutant = _bundle()
            target = next(item for item in mutant["attempts"] if item["attempt"] == number)
            mutate(target)
            return _outcome(mutant)

        code, text = replay(lambda item: item["request"].__setitem__("path", ""))
        self.assertEqual(code, 2, text)
        self.assertIn("(empty path)", text)

        code, text = replay(lambda item: item["request"].__setitem__("method", "GET"))
        self.assertEqual(code, 2, text)
        self.assertIn(SAR_PATH, text)

        code, text = replay(lambda item: item["request"].__setitem__("path", "/api/v1/namespaces"))
        self.assertEqual(code, 2, text)
        self.assertIn("/api/v1/namespaces", text)

        code, text = replay(lambda item: item["request"]["params"].__setitem__("limit", "500"))
        self.assertEqual(code, 2, text)
        self.assertIn(SAR_PATH, text)

    def test_read_must_be_get_on_a_collector_path(self):
        bundle = _bundle()
        listed = next(item for item in bundle["attempts"] if item["request"]["path"] == "/api/v1/namespaces")
        number = listed["attempt"]

        def replay(mutate):
            mutant = _bundle()
            target = next(item for item in mutant["attempts"] if item["attempt"] == number)
            mutate(target)
            reseal(target)
            return _outcome(mutant)

        code, text = replay(lambda item: item["request"].__setitem__("method", "POST"))
        self.assertEqual(code, 2, text)
        self.assertIn("/api/v1/namespaces", text)

        code, text = replay(lambda item: item["request"].__setitem__("params", {}))
        self.assertEqual(code, 2, text)
        self.assertIn("limit", text)

        code, text = replay(lambda item: item["request"].__setitem__("path", "/api/v1/pods"))
        self.assertEqual(code, 2, text)
        self.assertIn("/api/v1/pods", text)

    def test_self_check_body_must_be_one_the_collector_sends(self):
        mutant = _bundle()
        target = next(item for item in mutant["attempts"] if item["request"]["path"] == SSAR_PATH)
        target["request"]["body"]["spec"]["resourceAttributes"]["verb"] = "delete"
        reseal(target)
        code, text = _outcome(mutant)
        self.assertEqual(code, 2, text)
        self.assertIn(SSAR_PATH, text)

    def test_attempts_out_of_order_exit_2(self):
        mutant = _bundle()
        mutant["attempts"][0], mutant["attempts"][1] = mutant["attempts"][1], mutant["attempts"][0]
        code, text = _outcome(mutant)
        self.assertEqual(code, 2, text)
        self.assertIn("order", text)


if __name__ == "__main__":
    unittest.main()
