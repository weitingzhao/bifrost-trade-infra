"""Round 6. A request the collector would not send for this inventory is exit 2.

On 99c960c the three discovery reproductions replayed as exit 3 and the output
was unchanged: GET /api/v2, GET /apis/unserved.example/v1, and garbage/api/v2.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from support import command, load_defaults, reseal, review_attempt, run  # noqa: E402

BUNDLE_PATH = HERE / "testdata" / "recorded-bundle.json"
SAR_PATH = "/apis/authorization.k8s.io/v1/subjectaccessreviews"


def _bundle():
    return json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))


def _next(bundle: dict) -> int:
    return max(item["attempt"] for item in bundle["attempts"]) + 1


def _discovery_body(group_version: str, resource: str) -> dict:
    return {
        "groupVersion": group_version,
        "kind": "APIResourceList",
        "metadata": {"continue": ""},
        "resources": [{"name": resource, "namespaced": True, "verbs": ["create"]}],
    }


def _read(bundle: dict, path: str, body: dict) -> dict:
    return reseal(command(_next(bundle), path, body, params={"limit": "500"}))


def _review(bundle: dict, spec: dict) -> dict:
    return reseal(review_attempt(_next(bundle), spec, {"allowed": False, "denied": True}))


def _attributes(resource: str, namespace: str, verb: str) -> dict:
    return {
        "group": "",
        "name": "",
        "namespace": namespace,
        "resource": resource,
        "subresource": "",
        "verb": verb,
        "version": "v1",
    }


def appended_requests(bundle: dict) -> list[tuple[str, str, dict]]:
    """One sealed extra request per kind. Append each alone; they share the next attempt number.

    discovery: a version the root discovery did not name, carrying a new resource.
    list: configmaps, which the core discovery lists, inside a namespace the inventory does not.
    review-identity: an explicit configmaps question asked as an identity the inputs do not have.
    review-target: an identity the inputs do have, asked a target they do not.
    """
    stranger = {
        "groups": [
            "system:authenticated",
            "system:serviceaccounts",
            "system:serviceaccounts:not-in-inventory",
        ],
        "resourceAttributes": _attributes("configmaps", "cicd", "patch"),
        "user": "system:serviceaccount:not-in-inventory:stranger",
    }
    other_target = {
        "groups": ["system:authenticated"],
        "resourceAttributes": _attributes("widgets", "ns-a", "patch"),
        "user": "example-user",
    }
    return [
        ("discovery", "/api/v2", _read(bundle, "/api/v2", _discovery_body("v2", "widgets"))),
        (
            "list",
            "/api/v1/namespaces/not-in-inventory/configmaps",
            _read(
                bundle,
                "/api/v1/namespaces/not-in-inventory/configmaps",
                {
                    "items": [{"metadata": {"name": "extra-cm", "namespace": "not-in-inventory"}}],
                    "kind": "ConfigMapList",
                    "metadata": {"continue": ""},
                },
            ),
        ),
        ("review-identity", SAR_PATH, _review(bundle, stranger)),
        ("review-target", SAR_PATH, _review(bundle, other_target)),
    ]


def _play(bundle):
    targets, fixed, exceptions, nontargets = load_defaults()
    try:
        code, text = run(bundle, targets, fixed, exceptions, nontargets)
    except Exception as exc:  # noqa: BLE001 — MatrixExit, or a crash, is the outcome
        code = getattr(exc, "code", None)
        text = getattr(exc, "message", None) or repr(exc)
    return code, text


class Round6Tests(unittest.TestCase):
    def test_review66_extra_discovery_exits_2(self):
        bundle = _bundle()
        cases = [
            ("/api/v2", _discovery_body("v2", "widgets"), "not implied by this inventory"),
            (
                "/apis/unserved.example/v1",
                _discovery_body("unserved.example/v1", "widgets"),
                "not implied by this inventory",
            ),
            ("garbage/api/v2", _discovery_body("v2", "widgets"), "path is not canonical"),
        ]
        for path, body, reason in cases:
            mutant = _bundle()
            mutant["attempts"].append(_read(bundle, path, body))
            code, text = _play(mutant)
            self.assertEqual(code, 2, text)
            self.assertIn(f"GET {path}", text)
            self.assertIn(reason, text)

    def test_appended_request_of_each_kind_exits_2(self):
        bundle = _bundle()
        kinds = [label for label, _named, _attempt in appended_requests(bundle)]
        self.assertEqual(kinds, ["discovery", "list", "review-identity", "review-target"])
        for label, named, attempt in appended_requests(bundle):
            mutant = copy.deepcopy(bundle)
            mutant["attempts"].append(attempt)
            code, text = _play(mutant)
            self.assertEqual(code, 2, f"{label}: {text}")
            self.assertIn(named, text)
            self.assertIn("not implied by this inventory", text)


if __name__ == "__main__":
    unittest.main()
