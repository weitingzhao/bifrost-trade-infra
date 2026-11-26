#!/usr/bin/env python3
"""The commit trailers rules of the landing and of push-main.sh: one module.

The land task of k8s/cicd/tekton/pipeline-land.yaml embeds the block between
the BEGIN and END lines as it is (it runs without a checkout);
scripts/landing/test_trailers.py holds the two alike. push-main.sh and
scripts/release/add-lineage.sh call this file (walls review [79], 决定
2026-11-25 #783: one trailer check for both).

  trailers.py missing   stdin: records "<sha>\x1f<message>" separated by NUL;
                        prints "<short> (no Change-Id Claude-Session) <subject>"
                        for each commit lacking either, exit 0.
  trailers.py fix --sha <sha> [--session <id>]
                        stdin: a message; stdout: it with a Change-Id in its
                        last paragraph (fixed_message) and the Claude-Session
                        when given and missing.
"""
import hashlib
import re
import sys

# BEGIN shared trailer rules: scripts/landing/trailers.py and the land task of pipeline-land.yaml hold this block alike (walls review [79]).
TRAILER = re.compile(r'^[A-Za-z0-9-]+: \S')

def change_id(message):
    """The Change-Id trailer of a commit message, or None. A trailer is a line of the last
    paragraph, and that paragraph holds trailers only: the same words in the body are text."""
    parts = re.split(r'\n[ \t]*\n', message.strip())
    # git counts the line it writes for a cherry-pick as part of the trailer block.
    last = [line for line in (parts[-1].splitlines() if len(parts) > 1 else [])
            if not line.startswith('(cherry picked from commit ')]
    if not last or not all(TRAILER.match(line) or line[:1] in (' ', '\t') for line in last):
        return None
    found = [line.split(': ', 1)[1].strip() for line in last if line.startswith('Change-Id: ')]
    return found[-1] if found and re.fullmatch(r'\S+', found[-1]) else None

def misplaced_change_id(message):
    """True when a paragraph before the last is a trailer block with a Change-Id and every
    paragraph after it holds trailers only: the trailers were split by a blank line (plan's
    986bef69 on 2026-11-23 had Co-Authored-By alone below the block)."""
    parts = re.split(r'\n[ \t]*\n', message.strip())
    for i in range(1, len(parts) - 1):
        if change_id('x\n\n' + parts[i]):
            rest = [line for part in parts[i + 1:] for line in part.splitlines()
                    if not line.startswith('(cherry picked from commit ')]
            if rest and all(TRAILER.match(line) for line in rest):
                return True
    return False

def fixed_message(message, sha):
    """`message` with a Change-Id in its last paragraph: trailers split by a blank line are joined
    into one block; a message with none gets one made from `sha`, the same however often this
    runs (walls review [74], 2026-11-25: a missing trailer was refused, and a branch whose pusher
    never heard of it sat for an hour or more; now the landing adds it and goes on)."""
    if change_id(message):
        return message
    body = message.strip()
    parts = re.split(r'\n[ \t]*\n', body)
    if misplaced_change_id(message):
        for i in range(1, len(parts) - 1):
            if change_id('x\n\n' + parts[i]):
                return '\n\n'.join(parts[:i] + ['\n'.join(parts[i:])]) + '\n'
    made = 'I' + hashlib.sha1(('land:' + sha).encode()).hexdigest()
    last = parts[-1].splitlines() if len(parts) > 1 else []
    if last and all(TRAILER.match(line) or line[:1] in (' ', '\t') or line.startswith('(cherry picked from commit ')
                    for line in last) and not any(line.startswith('Change-Id:') for line in last):
        return body + '\nChange-Id: ' + made + '\n'
    return body + '\n\nChange-Id: ' + made + '\n'

def session_of(message):
    """The commit's Claude-Session trailer (the thread that made it), or ''."""
    found = re.findall(r'^Claude-Session:\s*(\S+)\s*$', message or '', re.M)
    return found[-1] if found else ''
# END shared trailer rules


def missing(data):
    out = []
    for record in data.split('\0'):
        if not record.strip():
            continue
        sha, _, message = record.partition('\x1f')
        lacks = [name for name, ok in (('Change-Id', change_id(message)), ('Claude-Session', session_of(message))) if not ok]
        if lacks:
            subject = message.strip().splitlines()[0] if message.strip() else ''
            out.append('%s (no %s) %s' % (sha.strip()[:7], ' '.join(lacks), subject))
    return out


def fix(message, sha, session=''):
    message = fixed_message(message, sha)
    if session and not session_of(message):
        message = message.rstrip('\n') + '\nClaude-Session: ' + session + '\n'
    return message


def main(argv):
    if argv[:1] == ['missing']:
        for line in missing(sys.stdin.read()):
            print(line)
        return 0
    if argv[:1] == ['fix'] and '--sha' in argv:
        sha = argv[argv.index('--sha') + 1]
        session = argv[argv.index('--session') + 1] if '--session' in argv else ''
        sys.stdout.write(fix(sys.stdin.read(), sha, session))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
