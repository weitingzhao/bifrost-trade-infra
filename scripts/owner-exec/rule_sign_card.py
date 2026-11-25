#!/usr/bin/env python3
"""The command of the card that signs an agent runtime rule (Owner 2026-11-25).

Owner 2026-11-25: 「任何需要重签的话，可以通过我这个就是 Ops 里面的验证码的那种 ticket
的形式来去签，不要我非要回到电脑上才能签」. platform-api verifies an agent runtime
rule against two keys (bifrost-platform api/internal/releasepolicy RuleAnchors):
the Owner's Mac key and the cluster key in Secret
bifrost-owner-exec/release-policy-signer, which only an owner_run_command card
he approves with his one-time code reaches (TD-576). This script prints that
card's command for one rule text: the card carries the whole text and its
sha256, checks the sha256, signs with the cluster key in namespace
bifrost-agentrt-rule, checks the signature and prints it. It installs nothing:
the agent then posts the text and the printed signature to
POST /api/v1/agentrt/rules/<rule_id>/sign, where the signature, not the
caller, is the authority. A command that names a forbidden path is refused by
platform-api when the card is created (tier X), not here.

  rule_sign_card.py --text plan-standing.yaml     prints the command and, on stderr, the sha256

Refused: a text that is not UTF-8 or holds a single quote (the card writes the
text between single quotes).
"""

from __future__ import annotations

import argparse
import hashlib
import sys

TEMPLATE = (
    "set -eu; want={sha}; umask 077; "
    "printf '%s' '{text}' > rule.yaml; "
    'echo "$want  rule.yaml" | sha256sum -c - >/dev/null; '
    "kubectl -n bifrost-owner-exec get secret release-policy-signer -o jsonpath='{{.data.key}}' | base64 -d > key; "
    "ssh-keygen -Y sign -f key -n bifrost-agentrt-rule rule.yaml >/dev/null 2>&1; rm -f key; "
    "ssh-keygen -Y check-novalidate -n bifrost-agentrt-rule -s rule.yaml.sig < rule.yaml >/dev/null; "
    'echo "signed: rule.yaml sha256 $want"; cat rule.yaml.sig'
)


def card_command(text: str) -> tuple[str, str]:
    if "'" in text:
        raise ValueError("the rule text holds a single quote; reword it")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return TEMPLATE.format(sha=sha, text=text), sha


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", required=True)
    args = ap.parse_args(argv)
    try:
        with open(args.text, encoding="utf-8") as f:
            text = f.read()
        cmd, sha = card_command(text)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print(f"rule_sign_card: {exc}", file=sys.stderr)
        return 2
    print(cmd)
    print(f"sha256 {sha}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
