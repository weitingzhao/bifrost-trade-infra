"""Walls review [79] (决定 2026-11-25 #783): the landing and push-main.sh check commit trailers
with one module, scripts/landing/trailers.py; the land task embeds its rules block as it is."""
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/landing/trailers.py"
BEGIN, END = "# BEGIN shared trailer rules", "# END shared trailer rules"


def block(text):
    start = text.index(BEGIN)
    return text[start:text.index(END, start) + len(END)]


def test_the_land_task_embeds_the_modules_rules_as_they_are():
    spec = yaml.safe_load((ROOT / "k8s/cicd/tekton/pipeline-land.yaml").read_text())["spec"]
    (land,) = [t for t in spec["tasks"] if t["name"] == "land"]
    assert block(land["taskSpec"]["steps"][0]["script"]) == block(MODULE.read_text())


def run(*args, stdin=""):
    return subprocess.run([sys.executable, "-I", str(MODULE), *args], input=stdin, capture_output=True, text=True)


def test_missing_names_each_commit_without_a_change_id_or_a_session():
    """The same rule as the landing: a Change-Id counts only in the last paragraph. Positive control:
    a commit with both trailers in its last paragraph is not named."""
    records = "\0".join([
        "a" * 40 + "\x1ffix: both\n\nClaude-Session: local_x\nChange-Id: Iabc\n",
        "b" * 40 + "\x1ffix: none\n\nbody\n",
        "c" * 40 + "\x1ffix: split\n\nClaude-Session: local_x\nChange-Id: Iabc\n\nCo-Authored-By: A <a@b.c>\n",
    ])
    out = run("missing", stdin=records).stdout.splitlines()
    assert out == ["bbbbbbb (no Change-Id Claude-Session) fix: none", "ccccccc (no Change-Id) fix: split"]


def test_fix_adds_what_is_missing_and_reads_back():
    fixed = run("fix", "--sha", "d" * 40, "--session", "local_y", stdin="fix: none\n\nbody\n").stdout
    assert run("missing", stdin="d" * 40 + "\x1f" + fixed).stdout == ""
    again = run("fix", "--sha", "d" * 40, "--session", "local_y", stdin=fixed).stdout
    assert again == fixed  # positive control: nothing left to add
