"""Origin: 2026-11-25, the Owner: re-signing must work from the phone; the card's
command must sign exactly the text it shows."""

import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
import rule_sign_card as card  # noqa: E402

TEXT = "rule_id: plan-standing\n# the step's own tasks\nrule_version: 2\ndone_rules: true\n"


def test_the_command_carries_the_text_and_its_sha256():
    cmd, sha = card.card_command(TEXT)
    assert sha == hashlib.sha256(TEXT.encode()).hexdigest()
    assert f"want={sha};" in cmd and TEXT in cmd and "-n bifrost-agentrt-rule" in cmd
    # what the card writes is byte for byte the text, apostrophes included
    head = cmd.split("kubectl", 1)[0] + "cat rule.yaml"
    out = subprocess.run(["sh", "-c", head.replace("set -eu; want=", "want=")], capture_output=True, text=True, cwd=_tmp()).stdout
    assert out == TEXT


def _tmp():
    import tempfile
    return tempfile.mkdtemp()


def test_refuses_what_the_here_document_cannot_carry():
    for bad in ("no newline at the end", "a\nRULE_TEXT_END\nb\n"):
        try:
            card.card_command(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")
