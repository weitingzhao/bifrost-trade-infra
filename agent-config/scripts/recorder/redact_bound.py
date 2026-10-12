"""Upper bound on how much the platform's redactor can lengthen a document.

The publisher does not redact. It counts, in the document's own strings,
characters each rule must consume, and multiplies by that rule's maximum
growth. More than the true growth is allowed; less is not. Rules that cannot
lengthen text contribute nothing. notice/redact.go is the rule table.
"""

from __future__ import annotations

# Most bytes one match can add, in the order of notice.redactions.
# 0: a match is at least as long as its replacement.
RULE_MAX_GROWTH = (0, 2, 9, 0, 0, 1, 9)

_SLACK = ("xoxa-", "xoxb-", "xoxp-", "xoxr-")


def _keywords(text: str) -> int:
    """Bearer/Basic matches, including the long-s and kelvin folds."""
    folded = text.casefold()
    return folded.count("bearer") + folded.count("basic")


def _slack(text: str) -> int:
    return sum(text.count(prefix) for prefix in _SLACK)


def string_growth(text: str) -> int:
    """Bytes this one string can gain. Structural JSON punctuation is absent."""
    if type(text) is not str or text == "":
        return 0
    return (
        RULE_MAX_GROWTH[2] * (text.count(":") + text.count("="))
        + RULE_MAX_GROWTH[6] * text.count("@")
        + RULE_MAX_GROWTH[1] * _keywords(text)
        + RULE_MAX_GROWTH[5] * _slack(text)
    )


def growth(document) -> int:
    """Sum of string_growth over every key and string value in the tree."""
    total = 0
    stack = [document]
    while stack:
        node = stack.pop()
        kind = type(node)
        if kind is str:
            total += string_growth(node)
        elif kind is dict:
            for key, child in node.items():
                if type(key) is str:
                    total += string_growth(key)
                stack.append(child)
        elif kind is list:
            stack.extend(node)
    return total
