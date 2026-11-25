#!/usr/bin/env python3
"""Tell the writer, at the moment of writing, that code cites ids, not the Owner (Station, LAW-1 four).

Code, tests, docs and config carry LAW-k / ISSUE-n / 「决定 日期」, never the Owner's words or
「Owner <date>」 as the reason; the words live in the platform's records (get_laws,
get_owner_issues). A rule in CLAUDE.md alone did not hold: main still had 1,430 such lines
on 2026-11-25.

PostToolUse on Edit, Write and MultiEdit: if the text just written matches the same pattern
the legislation patrol uses (scripts/laws/residual_scan.py OWNER_WORDS), add one line of
context naming the matching lines. It only informs: no decision is returned, nothing is
refused. Notes and memory outside the repositories are not checked.
Fail-soft: any error prints nothing and exits 0.
"""
import json
import re
import sys

# Same pattern as scripts/laws/residual_scan.py OWNER_WORDS; keep the two in step.
OWNER_WORDS = re.compile(
    r"Owner[ ,(（]{0,3}(20[0-9]{2}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}-[0-9]{2}\b)"
    r"|the Owner[^\n]{0,20}[:：] *[「\"“]")
SKIP_PARTS = ('/.claude/', '/side-session-notes/', '/scratchpad/', '/tmp/')
HINT = '依据写编号（LAW-k、ISSUE-n、决定 日期），原文在 get_laws / get_owner_issues。这次写进去的这几行带了 Owner 的署名或原话：'


def written_text(tool, inp):
    if tool == 'Write':
        return inp.get('content', '')
    if tool == 'Edit':
        return inp.get('new_string', '')
    if tool == 'MultiEdit':
        return '\n'.join(e.get('new_string', '') for e in inp.get('edits', []) or [])
    return ''


def hint(payload):
    tool = payload.get('tool_name', '')
    inp = payload.get('tool_input') or {}
    path = str(inp.get('file_path', ''))
    if not path or any(p in path for p in SKIP_PARTS):
        return None
    hits = [ln.strip()[:120] for ln in written_text(tool, inp).splitlines() if OWNER_WORDS.search(ln)]
    if not hits:
        return None
    return HINT + '\n' + '\n'.join('  ' + h for h in hits[:5])


def main():
    try:
        payload = json.loads(sys.stdin.read() or '{}')
        text = hint(payload)
        if text:
            print(json.dumps({'hookSpecificOutput': {
                'hookEventName': 'PostToolUse', 'additionalContext': text}}, ensure_ascii=False))
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
