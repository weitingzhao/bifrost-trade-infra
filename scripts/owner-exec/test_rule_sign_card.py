"""Origin: 2026-11-25, the Owner: re-signing must work from the phone; the card's
command must sign exactly the text it shows."""

import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import rule_sign_card as card  # noqa: E402

TEXT = "rule_id: plan-standing\nrule_version: 2\ndone_rules: true\n"


def test_the_command_carries_the_text_and_its_sha256():
    cmd, sha = card.card_command(TEXT)
    assert sha == hashlib.sha256(TEXT.encode()).hexdigest()
    assert f"want={sha};" in cmd and TEXT in cmd and "-n bifrost-agentrt-rule" in cmd
    # what the card writes is byte for byte the text: the shell's printf of the quoted text
    out = subprocess.run(["sh", "-c", f"printf '%s' '{TEXT}'"], capture_output=True, text=True).stdout
    assert out == TEXT


def test_refuses_a_single_quote():
    try:
        card.card_command("it's\n")
    except ValueError:
        return
    raise AssertionError("accepted a single quote")
