"""Round 7. A request has one closed shape, and each expected request has one group.

On e88fd5a a resealed copy of GET /api or GET /apis with request.body = {} was a new
request hash, so it formed its own group. Replay exited 3 and the output was unchanged.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from attempts import each_group, the_group  # noqa: E402
from canon import MatrixExit  # noqa: E402
from identities import assert_discovery_complete  # noqa: E402
from support import load_defaults, reseal, run  # noqa: E402

BUNDLE_PATH = HERE / "testdata" / "recorded-bundle.json"

# Added onto every request record. body:{} is the reviewer's GET reproduction.
EXTRA_KEYS = (
    ("body", {}),
    ("body", None),
    ("headers", {}),
    ("x", 1),
)


def _bundle():
    return json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))


def _play(bundle):
    targets, fixed, exceptions, nontargets = load_defaults()
    try:
        code, text = run(bundle, targets, fixed, exceptions, nontargets)
    except Exception as exc:  # noqa: BLE001 — MatrixExit, or a crash, is the outcome
        code = getattr(exc, "code", None)
        text = getattr(exc, "message", None) or repr(exc)
    return code, text


def apply_extra_key(attempt: dict, key: str, value) -> None:
    """Put one extra key on the request and reseal when the new value still has a hash."""
    attempt["request"][key] = value
    try:
        reseal(attempt)
    except (KeyError, TypeError):
        return


def twin_attempt(attempt: dict, number: int) -> dict:
    """A second record: same method, path, and params, and a different request hash."""
    clone = copy.deepcopy(attempt)
    clone.pop("retry_of", None)
    clone["attempt"] = number
    request = clone["request"]
    if clone.get("kind") == "review":
        request["body"]["spec"]["user"] = str(request["body"]["spec"].get("user") or "") + "#twin"
    elif request.get("method") == "POST":
        request["body"] = dict(request["body"])
        request["body"]["twin"] = number
    else:
        request["body"] = {"twin": number}
    reseal(clone)
    return clone


def _append_body(bundle: dict, path: str) -> tuple[dict, int]:
    source = next(
        item
        for item in bundle["attempts"]
        if item["request"]["method"] == "GET" and item["request"]["path"] == path and "body" not in item["request"]
    )
    clone = copy.deepcopy(source)
    clone.pop("retry_of", None)
    clone["attempt"] = max(item["attempt"] for item in bundle["attempts"]) + 1
    clone["request"]["body"] = {}
    reseal(clone)
    mutant = copy.deepcopy(bundle)
    mutant["attempts"].append(clone)
    return mutant, clone["attempt"]


class Round7Tests(unittest.TestCase):
    def test_review71_get_with_body_exits_2(self):
        bundle = _bundle()
        for path in ("/api", "/apis"):
            mutant, number = _append_body(bundle, path)
            code, text = _play(mutant)
            self.assertEqual(code, 2, text)
            self.assertIn(f"GET {path}", text)
            self.assertIn("unexpected key body", text)
            self.assertIn(str(number), text)

    def test_unexpected_key_and_wrong_type_name_the_request(self):
        mutant = _bundle()
        target = next(item for item in mutant["attempts"] if item["request"]["path"] == "/api")
        target["request"]["headers"] = {}
        reseal(target)
        code, text = _play(mutant)
        self.assertEqual(code, 2, text)
        self.assertIn("GET /api", text)
        self.assertIn("unexpected key headers", text)

        mutant = _bundle()
        target = next(item for item in mutant["attempts"] if item["request"]["path"] == "/api")
        target["request"]["method"] = 1
        reseal(target)
        code, text = _play(mutant)
        self.assertEqual(code, 2, text)
        self.assertIn("/api", text)
        self.assertIn("wrong type", text)

    def test_two_root_groups_raise_and_name_both_attempts(self):
        left = {"attempt": 1, "kind": "read", "request": {"method": "GET", "path": "/api", "params": {}}}
        right = {
            "attempt": 320,
            "kind": "read",
            "request": {"method": "GET", "path": "/api", "params": {}, "body": {}},
        }
        with self.assertRaises(MatrixExit) as raised:
            the_group([left, right])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("attempt 1 and attempt 320", raised.exception.message)
        self.assertIn("GET /api", raised.exception.message)
        self.assertNotEqual(the_group([left]), right)

        reads = {
            "/api": [left, right],
            "/apis": [
                {"attempt": 2, "kind": "read", "request": {"method": "GET", "path": "/apis", "params": {}}}
            ],
        }
        with self.assertRaises(MatrixExit) as raised:
            assert_discovery_complete(reads)
        self.assertIn("attempt 1 and attempt 320", raised.exception.message)
        self.assertIn("more than one group", raised.exception.message)

    def test_a_duplicate_page_is_not_dropped(self):
        page = {"attempt": 4, "request": {"method": "GET", "path": "/api/v1", "params": {"limit": "500"}}}
        twin = {
            "attempt": 9,
            "request": {"method": "GET", "path": "/api/v1", "params": {"limit": "500"}, "body": {"twin": 1}},
        }
        with self.assertRaises(MatrixExit) as raised:
            each_group([page, twin])
        self.assertIn("attempt 4 and attempt 9", raised.exception.message)

        nxt = {
            "attempt": 5,
            "request": {"method": "GET", "path": "/api/v1", "params": {"continue": "tok", "limit": "500"}},
        }
        self.assertEqual([item["attempt"] for item in each_group([page, nxt])], [4, 5])

    def test_readme_names_the_shapes_and_the_optional_preamble(self):
        text = (HERE / "README.md").read_text(encoding="utf-8")
        self.assertIn("三种封闭形状", text)
        self.assertIn("whoami 和八条权限自检", text)
        self.assertIn("九个请求组必须齐全", text)


if __name__ == "__main__":
    unittest.main()
