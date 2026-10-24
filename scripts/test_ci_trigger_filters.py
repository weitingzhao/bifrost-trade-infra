"""TD-435 ratchet: every trigger of the CI EventListener admits only a 40-hex `after`;
the one that passes the ref on (github-sync) also pins the ref.

The EventListener bifrost-ci (k8s/cicd/tekton/trigger-trade-ci.yaml) has no webhook
secret, so anything that can reach it can post a push body. `after` becomes the
pipelines' `revision`, which Task scripts interpolate as $(params.revision). Each
trigger's CEL filter must pin it to a commit SHA and its ref to plain characters.

    python3 -m unittest scripts/test_ci_trigger_filters.py
"""

from __future__ import annotations

import pathlib
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
TRIGGERS = ROOT / "k8s" / "cicd" / "tekton" / "trigger-trade-ci.yaml"
SHA_RULE = "body.after.matches('^[0-9a-f]{40}$')"
REF_RULES = ("body.ref.matches('^refs/heads/[A-Za-z0-9._/+-]{1,200}$')",
             "body.ref.matches('^refs/tags/[A-Za-z0-9._/+-]{1,200}$')")


def filters(docs: list[dict]) -> dict[str, list[str]]:
    """trigger name -> the CEL filters of its interceptors."""
    found: dict[str, list[str]] = {}
    for d in docs:
        if d.get("kind") != "EventListener":
            continue
        for t in d["spec"].get("triggers") or []:
            cel = []
            for i in t.get("interceptors") or []:
                for p in i.get("params") or []:
                    if p.get("name") == "filter":
                        cel.append(" ".join(str(p.get("value")).split()))
            found[t["name"]] = cel
    return found


# Triggers whose template passes the ref on (github-sync); CI templates take only `after`.
REF_USERS = ("github-sync",)


def problems(docs: list[dict]) -> list[str]:
    out = []
    for name, cel in filters(docs).items():
        text = " && ".join(cel)
        if SHA_RULE not in text:
            out.append(f"{name}: no 40-hex rule on body.after")
        if name in REF_USERS and not any(r in text for r in REF_RULES):
            out.append(f"{name}: no plain-character rule on body.ref")
    return out


class TriggerFilters(unittest.TestCase):
    def test_every_trigger_pins_after_and_ref(self) -> None:
        docs = [d for d in yaml.safe_load_all(TRIGGERS.read_text()) if isinstance(d, dict)]
        self.assertGreaterEqual(len(filters(docs)), 6)
        self.assertEqual(problems(docs), [])

    def test_it_sees_a_missing_rule(self) -> None:
        # positive control: the filter as it was before TD-435
        old = [{"kind": "EventListener", "spec": {"triggers": [{"name": "python-ci", "interceptors": [
            {"ref": {"name": "cel"}, "params": [{"name": "filter", "value":
             "body.ref.startsWith('refs/heads/') && body.after != '0000000000000000000000000000000000000000'"}]}]},
            {"name": "github-sync", "interceptors": [{"ref": {"name": "cel"}, "params": [{"name": "filter", "value":
             "body.after.matches('^[0-9a-f]{40}$') && body.ref.startsWith('refs/tags/')"}]}]}]}}]
        self.assertEqual(problems(old), ["python-ci: no 40-hex rule on body.after",
                                         "github-sync: no plain-character rule on body.ref"])


if __name__ == "__main__":
    unittest.main()
