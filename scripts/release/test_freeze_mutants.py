"""Each planted violation has to fail the test named for it."""

from __future__ import annotations

import json
import os
import re
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


def _evidence_held(doc: dict, evidence: str) -> bool:
    """A case name, or a byte-class position written as '<base> <mode> <index>'."""
    if any(evidence in case["name"] for case in doc["cases"]):
        return True
    parts = evidence.split(" ")
    if len(parts) != 3:
        return False
    name, mode, index = parts
    try:
        k = int(index)
    except ValueError:
        return False
    key = {"replace": "positions", "insert": "insert_positions"}.get(mode)
    if key is None:
        return False
    return any(item["name"] == name and k in item[key] for item in doc["byte_classes"])


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
            if item.get("evidence"):
                doc = json.loads((ROOT / "scripts/release/freeze_http_vectors.json").read_text(encoding="ascii"))
                self.assertTrue(_evidence_held(doc, item["evidence"]), item["name"])


class MutantRunTests(unittest.TestCase):
    def test_each_mutant_is_killed(self) -> None:
        if os.environ.get("FREEZE_MUTANTS") != "1":
            self.skipTest("FREEZE_MUTANTS is not set")
        controlled: set = set()
        for item in freeze_mutants.MUTANTS:
            with tempfile.TemporaryDirectory() as raw:
                tmp = Path(raw)
                _stage(tmp)
                target = tmp / item["file"]
                text = target.read_text(encoding="utf-8")
                env = os.environ.copy()
                env.pop("FREEZE_MUTANTS", None)
                env["PYTHONPATH"] = str(tmp / "scripts" / "release")
                cmd = [
                    sys.executable, "-m", "pytest", "-q", "--tb=short",
                    "-p", "no:cacheprovider", "-k", item["must_fail"],
                    "test_freeze_lang.py", "test_freeze_gate.py", "test_freeze_manifests.py", "test_freeze_http.py",
                ]
                # Negative control: the selected tests pass on the copy before anything is planted. A copy that
                # fails by itself (a missing fixture, a broken import) proves nothing about the planted change.
                if item["must_fail"] not in controlled:
                    base = subprocess.run(cmd, cwd=tmp / "scripts" / "release", env=env, capture_output=True, text=True, timeout=180, check=False)
                    if base.returncode != 0 or not re.search(r"\b[1-9][0-9]* passed\b", base.stdout):
                        self.fail(f"negative control for {item['name']}: the selected tests do not pass on an unmutated copy\n{base.stdout}\n{base.stderr}")
                    controlled.add(item["must_fail"])
                target.write_text(text.replace(item["old"], item["new"], 1), encoding="utf-8")
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
                # Caught means a selected test FAILED. A collection error, a syntax error or an empty selection is not a catch.
                if not re.search(r"\b[1-9][0-9]* failed\b", res.stdout) or re.search(r"\b[1-9][0-9]* errors?\b", res.stdout):
                    print(f"mutant {item['name']} broke the run without failing a test", flush=True)
                    self.fail(f"mutant {item['name']} did not fail a named test\n{res.stdout}\n{res.stderr}")
                if item.get("evidence") and item["evidence"] not in res.stdout:
                    print(f"mutant {item['name']} failed without its evidence", flush=True)
                    self.fail(f"mutant {item['name']} failed a test, but not on the response it is about ({item['evidence']!r})\n{res.stdout}")
                print(f"mutant {item['name']} killed", flush=True)


if __name__ == "__main__":
    unittest.main()
