"""LANE-W33C static checks. No cluster."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ReleaseChainStaticTests(unittest.TestCase):
    def test_release_sh_does_not_create_objects_itself(self) -> None:
        text = (ROOT / "scripts/release/release.sh").read_text(encoding="utf-8")
        for forbidden in (
            "kubectl create",
            "kubectl apply",
            "kubectl delete",
            "kubectl exec",
            "bootstrap-gitea-mirrors.sh",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("/api/v1/delivery/release-window", text)
        self.assertIn("/api/v1/delivery/mirrors/sync", text)
        self.assertIn("bifrost-release-window", text)

    def test_pinned_output_is_six_shas(self) -> None:
        text = (ROOT / "scripts/release/prod-pinned-from-stg.sh").read_text(encoding="utf-8")
        self.assertNotIn("pipelineSpec", text)
        for name in (
            "coreRevision",
            "workerRevision",
            "apiRevision",
            "frontendRevision",
            "uiRevision",
            "infraRevision",
        ):
            self.assertIn(name, text)

    def test_release_docs_do_not_create_pipelineruns_by_hand(self) -> None:
        paths = [ROOT / "docs/RELEASE.md"]
        paths.extend((ROOT / "agent-config").glob("*/skills/**/SKILL.md"))
        bad = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            if "kubectl create -f" in text and "pipelinerun" in text:
                bad.append(str(path.relative_to(ROOT)))
            if "kubectl apply -k k8s/base" in text:
                bad.append(str(path.relative_to(ROOT)))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
