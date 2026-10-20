"""The card-auto-answer rule is STG's alone (TD-390, Owner 2026-10-20 「STG 用 A … PROD 不变」).

    python3 -m pytest -q scripts/agentrt/test_rules_prod.py

No file under agent-config/agentrt-rules/prod is, or names, a card-auto-answer
rule: without one in force the PROD platform answers no card by rule.
"""
from __future__ import annotations

import re
from pathlib import Path

RULES = Path(__file__).resolve().parents[2] / "agent-config" / "agentrt-rules"
# rule_id as the platform's YAML reader takes it: plain or quoted, a comment
# after it (review 442 C1).
RULE_ID = re.compile(r"""^rule_id:[ \t]*(["']?)card-auto-answer\1[ \t]*(#.*)?$""", re.MULTILINE)


def test_prod_has_no_card_auto_answer_rule() -> None:
    prod = RULES / "prod"
    assert prod.is_dir()
    named = [p.name for p in sorted(prod.rglob("*")) if p.is_file()
             and ("card-auto-answer" in p.name or RULE_ID.search(p.read_text(errors="replace")))]
    assert named == [], f"PROD must not hold a card-auto-answer rule: {named}"


def test_stg_draft_is_the_rule() -> None:
    text = (RULES / "stg" / "card-auto-answer.yaml").read_text()
    assert RULE_ID.search(text)
    # v3 (TD-393): five seconds, every kind of card the runtime asks
    assert re.search(r"^rule_version: 3$", text, re.MULTILINE)
    assert re.search(r"^after_seconds: 5$", text, re.MULTILINE)
    assert not re.search(r"^after_minutes:", text, re.MULTILINE)
    assert re.search(r"^kinds: \[blocked, plan_question, plan_change, plan_import, recorder_import, mission\]$", text, re.MULTILINE)


def test_the_check_reads_rule_id_as_yaml_does() -> None:
    for text in ("rule_id: card-auto-answer\n", 'rule_id: "card-auto-answer"\n', "rule_id: 'card-auto-answer'  # STG\n",
                 "rule_version: 1\nrule_id:\tcard-auto-answer\n"):
        assert RULE_ID.search(text), text
    for text in ("rule_id: card-auto-answer-x\n", "# rule_id: card-auto-answer\n", "rule_id: plan-standing\n"):
        assert not RULE_ID.search(text), text
