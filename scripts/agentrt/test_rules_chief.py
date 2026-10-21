"""The chief of staff's job rule: v1 while the chief sat its exam (TD-391), v2 once it passed (W-31 2.4 chief exam S5).

    python3 -m pytest -q scripts/agentrt/test_rules_chief.py

v2 (signed by the Owner after a sitting on STG passed with no misjudgment, the
fourth, 2026-10-21, and 06 offered exec:claude as the model it was sat with):
exec:claude is active, its model_pattern pinned to that model id, which the
agent units on 06 offer for exec:claude (routing matches the pattern against
the host's tool model, so the two must be the same string); the text is still
v1's word for word.

Until then (TD-391):

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
CANDIDATE = re.compile(r"^\s*-\s*\{executor:\s*([\w:-]+),\s*provider:\s*([\w-]+),\s*model_pattern:\s*\"?([^,\"]+)\"?,\s*status:\s*(\w+)\s*\}\s*$", re.MULTILINE)
AGENT_UNIT = Path(__file__).resolve().parents[1] / "agent-host" / "bifrost-agentd.service"
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


def offered_claude_model() -> str:
    tools = [ln.split("=", 2)[2] for ln in AGENT_UNIT.read_text().splitlines() if ln.startswith("Environment=AGENTD_TOOLS=")]
    claude = [t.split("=", 1)[1] for t in tools[0].split(",") if t.startswith("exec:claude=")]
    return claude[0].partition(":")[2]


@pytest.mark.parametrize("env", ENVS)
def test_the_chief_rule_is_v2_with_the_examined_model(env: str) -> None:
    text = (RULES / env / "job-chief_of_staff.yaml").read_text()
    assert re.search(r"^rule_version: 2$", text, re.MULTILINE) and re.search(r"^direction: loosen$", text, re.MULTILINE), env
    candidates = {(e, p, m): s for e, p, m, s in CANDIDATE.findall(text)}
    want = {("exec:claude", "anthropic", offered_claude_model()): "active"}
    assert candidates == want, f"{env}: job:chief_of_staff's candidates are {candidates}, want {want} (06 offers exec:claude as {offered_claude_model()!r})"


@pytest.mark.parametrize("env", ENVS)
def test_the_chief_text_is_the_one_the_exam_scores(env: str) -> None:
    got = hashlib.sha256(text_of(env).encode()).hexdigest()
    assert got == CHIEF_TEXT_SHA256, f"{env}: job:chief_of_staff's text changed; the chief exam scores the old one (ask the coordinating thread first)"
