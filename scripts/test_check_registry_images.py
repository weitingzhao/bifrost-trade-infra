"""TD-282: the registry manifest keeps its images. Fixtures are invented."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_registry_images as reg  # noqa: E402


def _docs() -> list[dict]:
    return [d for d in yaml.safe_load_all(reg.MANIFEST.read_text()) if d]


class StaticTests(unittest.TestCase):
    def test_repo_manifest_is_persistent(self) -> None:
        self.assertEqual(reg.static_problems(_docs()), [])

    def test_the_old_manifest_is_refused(self) -> None:
        docs = copy.deepcopy(_docs())
        docs = [d for d in docs if d["kind"] != "PersistentVolumeClaim"]
        deploy = next(d for d in docs if d["kind"] == "Deployment")
        deploy["spec"].pop("strategy")
        pod = deploy["spec"]["template"]["spec"]
        pod.pop("volumes")
        for c in pod["containers"]:
            c.pop("volumeMounts", None)
        problems = reg.static_problems(docs)
        self.assertTrue(any("Recreate" in p for p in problems), problems)
        self.assertTrue(any("not a PersistentVolumeClaim" in p for p in problems), problems)

    def test_claim_must_be_defined(self) -> None:
        docs = [d for d in copy.deepcopy(_docs()) if d["kind"] != "PersistentVolumeClaim"]
        self.assertTrue(any("is not defined" in p for p in reg.static_problems(docs)))


class RefTests(unittest.TestCase):
    def test_split_ref(self) -> None:
        self.assertEqual(reg.split_ref("192.168.10.73:30500/bifrost-worker:prod"), ("bifrost-worker", "prod"))
        self.assertEqual(reg.split_ref("192.168.10.73:30500/x@sha256:abc"), ("x", "sha256:abc"))
        self.assertEqual(reg.split_ref("192.168.10.73:30500/x"), ("x", "latest"))


if __name__ == "__main__":
    unittest.main()
