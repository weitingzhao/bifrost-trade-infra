"""The mutant list. The slow run is RECORDER_MUTANTS=1; the anchor check is always on."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mutants import MUTANTS

HERE = Path(__file__).resolve().parent


def test_mutant_anchors_are_unique():
    names = [item["name"] for item in MUTANTS]
    assert len(names) == len(set(names))
    assert names
    for item in MUTANTS:
        text = (HERE / item["file"]).read_text()
        assert text.count(item["old"]) == 1, item["name"]
        assert item["old"] != item["new"]
        assert item["must_fail"]
    collected = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=HERE,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert collected.returncode == 0, collected.stdout + collected.stderr
    have = set(collected.stdout.split())
    for item in MUTANTS:
        for node in item["must_fail"]:
            assert node in have, node


def test_every_mutant_fails_its_tests():
    if os.environ.get("RECORDER_MUTANTS") != "1":
        return
    env = {key: value for key, value in os.environ.items() if key != "RECORDER_MUTANTS"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    missed = []
    for item in MUTANTS:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "recorder"
            shutil.copytree(HERE, copy, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            target = copy / item["file"]
            text = target.read_text()
            target.write_text(text.replace(item["old"], item["new"], 1))
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider", *item["must_fail"]],
                cwd=copy,
                capture_output=True,
                text=True,
                env=env,
            )
        failed = []
        for line in (proc.stdout + "\n" + proc.stderr).splitlines():
            if line.startswith("FAILED "):
                failed.append(line[len("FAILED "):])
            elif line.startswith("ERROR "):
                failed.append(line[len("ERROR "):])
        print(f"{item['name']} → {', '.join(failed) if failed else 'passed'}")
        if proc.returncode == 0:
            missed.append(item["name"])
    assert not missed, missed
