"""The card-auto-answer rule is STG's alone (TD-390, Owner 2026-10-20 「STG 用 A … PROD 不变」).

    python3 -m pytest -q scripts/agentrt/test_rules_prod.py

No file under agent-config/agentrt-rules/prod is, or names, a card-auto-answer
rule: without one in force the PROD platform answers no card by rule.
"""
from __future__ import annotations

import re
from pathlib import Path

RULES = Path(__file__).resolve().parents[2] / "agent-config" / "agentrt-rules"
RULE_ID = re.compile(r"^rule_id:\s*card-auto-answer\s*$", re.MULTILINE)


def test_prod_has_no_card_auto_answer_rule() -> None:
    prod = RULES / "prod"
    assert prod.is_dir()
    named = [p.name for p in sorted(prod.rglob("*")) if p.is_file()
             and ("card-auto-answer" in p.name or RULE_ID.search(p.read_text(errors="replace")))]
    assert named == [], f"PROD must not hold a card-auto-answer rule: {named}"


def test_stg_draft_is_the_rule() -> None:
    text = (RULES / "stg" / "card-auto-answer.yaml").read_text()
    assert RULE_ID.search(text)
    assert re.search(r"^after_minutes: 30$", text, re.MULTILINE)
