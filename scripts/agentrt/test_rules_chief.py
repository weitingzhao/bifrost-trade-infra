"""The chief of staff's job rule stays v1 while the chief sits its exam (TD-391).

    python3 -m pytest -q scripts/agentrt/test_rules_chief.py

The Owner 2026-10-20 17:1x 「参谋长规则保持现状，考过之前评估由试用中的 claude 只读地做，
不用 codex 兼任」: the assessments of cards and approvals go to the chief of
staff's seat as it is, exec:claude on probation, read-only. Two reasons it
must not change before the Owner signs a new version himself:
  - the chief exam (W-31 2.4, chief-exam-s5) scores the model with this
    job's text, so a changed text voids the sitting;
  - an active stand-in (the reviewer's exec:codex) would be routed every
    task of the seat (route.go reads active candidates first), briefs and
    mail included, without having passed the exam, and its executor runs
    in a workspace-write sandbox, where the seat is read-only.
So in each environment job:chief_of_staff is v1, initial, with exec:claude
on probation as its only candidate, and its text is v1's word for word.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

RULES = Path(__file__).resolve().parents[2] / "agent-config" / "agentrt-rules"
ENVS = ["stg", "prod"]
CANDIDATE = re.compile(r"^\s*-\s*\{executor:\s*([\w:-]+),\s*provider:\s*([\w-]+),.*status:\s*(\w+)\s*\}\s*$", re.MULTILINE)
# v1's text: sha256 of the block's lines without their indent, each ending
# in a newline.
CHIEF_TEXT_SHA256 = "4e8a371158f08883bf71b2ea5fc2bb5094676a43100417d5624f69270042e6bd"


def text_of(env: str) -> str:
    lines = (RULES / env / "job-chief_of_staff.yaml").read_text().split("\n")
    block = []
    for line in lines[lines.index("text: |") + 1:]:
        if not line.startswith("  "):
            break
        block.append(line[2:])
    return "\n".join(block) + "\n"


@pytest.mark.parametrize("env", ENVS)
def test_the_chief_rule_is_v1(env: str) -> None:
    text = (RULES / env / "job-chief_of_staff.yaml").read_text()
    assert re.search(r"^rule_version: 1$", text, re.MULTILINE) and re.search(r"^direction: initial$", text, re.MULTILINE), env
    candidates = {(e, p): s for e, p, s in CANDIDATE.findall(text)}
    assert candidates == {("exec:claude", "anthropic"): "probation"}, f"{env}: job:chief_of_staff's candidates are {candidates}"


@pytest.mark.parametrize("env", ENVS)
def test_the_chief_text_is_the_one_the_exam_scores(env: str) -> None:
    got = hashlib.sha256(text_of(env).encode()).hexdigest()
    assert got == CHIEF_TEXT_SHA256, f"{env}: job:chief_of_staff's text changed; the chief exam scores the old one (ask the coordinating thread first)"
