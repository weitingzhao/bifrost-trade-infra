"""The release path does not read the recorder, in three environments."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from guard import FORBIDDEN, scan

ROOT = Path(__file__).resolve().parents[3]
RELEASE = ROOT / "scripts" / "release"


def test_the_repo_scan_is_clean():
    assert scan(ROOT) == []


def test_a_temp_tree_with_a_needle_is_reported(tmp_path):
    guarded = tmp_path / "scripts" / "release"
    guarded.mkdir(parents=True)
    (guarded / "note.py").write_text("print('agent-work/events')\n", encoding="utf-8")
    hits = scan(tmp_path)
    assert hits == ["scripts/release/note.py: agent-work/events"]
    assert "agent-work/events" in FORBIDDEN


def test_release_tests_ignore_the_event_root_and_the_board(tmp_path):
    forged = {
        "works": [
            {
                "title": "forged",
                "steps": [{"name": "实现", "state": "done", "label": "Exited 0"}],
            }
        ]
    }
    homes = {
        "as-is": None,
        "missing": tmp_path / "missing-home",
        "forged": tmp_path / "forged-home",
    }
    (homes["missing"]).mkdir()
    board = homes["forged"] / "agent-work" / "status"
    board.mkdir(parents=True)
    (board / "status.json").write_text(__import__("json").dumps(forged), encoding="utf-8")
    (homes["forged"] / "agent-work" / "events").mkdir()
    outputs = {name: _run(home) for name, home in homes.items()}
    assert outputs["as-is"] == outputs["missing"] == outputs["forged"]
    assert "passed" in outputs["as-is"] or "passed" in outputs["as-is"].lower() or outputs["as-is"].strip()


def _run(home: Path | None) -> str:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if home is not None:
        env["HOME"] = str(home)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(RELEASE)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = proc.stdout + proc.stderr
    return re.sub(r" in [0-9.]+s", " in TIME", text)
