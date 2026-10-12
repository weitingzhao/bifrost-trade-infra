"""Each planted violation has to fail the test named for it."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import freeze_mutants  # noqa: E402

ROOT = HERE.parents[1]
COPY_PATHS = [
    "k8s/release-freeze",
    "k8s/cicd/tekton/task-release-window.yaml",
    "k8s/cicd/tekton/apply-manifest/actuation-policy.yaml",
    "k8s/overlays/platform-prod/config/actuation-policy.yaml",
    "k8s/overlays/platform-stg/config/actuation-policy.yaml",
    "scripts/release",
]


def _stage(tmp: Path) -> None:
    for rel in COPY_PATHS:
        src = ROOT / rel
        dst = tmp / rel
        if src.is_dir():
            shutil.copytree(
                src,
                dst,
                ignore=shutil.ignore_patterns("__pycache__", "freeze_mutants.py", "test_freeze_mutants.py"),
            )
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


class MutantListTests(unittest.TestCase):
    def test_each_old_occurs_once_and_names_a_test(self) -> None:
        self.assertGreaterEqual(len(freeze_mutants.MUTANTS), 20)
        names = set()
        for item in freeze_mutants.MUTANTS:
            self.assertNotIn(item["name"], names)
            names.add(item["name"])
            text = (ROOT / item["file"]).read_text(encoding="utf-8")
            self.assertEqual(text.count(item["old"]), 1, item["name"])
            self.assertNotEqual(item["old"], item["new"])
            self.assertTrue(item["must_fail"])


class MutantRunTests(unittest.TestCase):
    def test_each_mutant_is_killed(self) -> None:
        if os.environ.get("FREEZE_MUTANTS") != "1":
            self.skipTest("FREEZE_MUTANTS is not set")
        for item in freeze_mutants.MUTANTS:
            with tempfile.TemporaryDirectory() as raw:
                tmp = Path(raw)
                _stage(tmp)
                target = tmp / item["file"]
                text = target.read_text(encoding="utf-8")
                target.write_text(text.replace(item["old"], item["new"], 1), encoding="utf-8")
                env = os.environ.copy()
                env.pop("FREEZE_MUTANTS", None)
                env["PYTHONPATH"] = str(tmp / "scripts" / "release")
                cmd = [
                    sys.executable, "-m", "pytest", "-q", "--tb=line",
                    "-p", "no:cacheprovider", "-k", item["must_fail"],
                    "test_freeze_lang.py", "test_freeze_gate.py", "test_freeze_manifests.py",
                ]
                res = subprocess.run(
                    cmd,
                    cwd=tmp / "scripts" / "release",
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                )
                if res.returncode == 0:
                    print(f"mutant {item['name']} survived", flush=True)
                    self.fail(f"mutant {item['name']} survived\n{res.stdout}\n{res.stderr}")
                print(f"mutant {item['name']} killed", flush=True)


if __name__ == "__main__":
    unittest.main()
