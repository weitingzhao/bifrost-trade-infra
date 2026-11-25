#!/usr/bin/env python3
"""Pick where a piece of work runs: a harness's account with quota left, and who to hand it to there (Station, 2026-11-24).

Usage: pick.py <harness> [--skip <account label> ...]

A seat names only the harness it wants (claude, codex, opencode). This walks the accounts table in
agent-config/charters/seats.yaml: start at the first account of that harness that lives on a Mac mini
(agents live on the minis, ISSUE-60), follow `fallback`, and stop at the first label not in --skip
(the ones whose quota ran out), preferring one whose host already has a resident thread. It prints the label, the host, and the resident thread on that host to
send the brief to, if one is registered (a temporary row with that account, ended: null, a session).
Exit 1 when every account of that harness is skipped.
"""
import pathlib
import sys

import yaml

SEATS = pathlib.Path(__file__).resolve().parents[2] / 'agent-config' / 'charters' / 'seats.yaml'


def pick(table, harness, skip=()):
    accts = {a['id']: a for a in table.get('accounts') or []}
    own = [a for a in accts.values() if a['harness'] == harness]
    if not own:
        return None
    start = next((a for a in own if 'mini' in str(a.get('host', ''))), own[0])

    def resident_of(acct):
        return next((t for t in table.get('temporary') or []
                     if t.get('account') == acct['id'] and t.get('ended') is None and t.get('session')), None)

    chain, cur = [], start
    while cur and cur['id'] not in {c['id'] for c in chain}:
        chain.append(cur)
        cur = accts.get(cur.get('fallback'))
    left = [c for c in chain if c['id'] not in skip]
    if not left:
        return None
    # Prefer a login that has a resident thread on its host: the work can be handed over without starting one.
    cur = next((c for c in left if resident_of(c)), left[0])
    resident = resident_of(cur)
    return cur, resident


def main(argv):
    if not argv:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    harness, skip = argv[0], set()
    rest = argv[1:]
    while rest:
        if rest[0] == '--skip' and len(rest) > 1:
            skip.add(rest[1]); rest = rest[2:]
        else:
            print(f'unknown argument {rest[0]}', file=sys.stderr); return 2
    got = pick(yaml.safe_load(SEATS.read_text()), harness, skip)
    if not got:
        print(f'no {harness} account left (skipped: {", ".join(sorted(skip)) or "none"}); quota and accounts are the Owner\'s call')
        return 1
    acct, resident = got
    print(f"account\t{acct['id']}\nhost\t{acct.get('host')}")
    if resident:
        sid = str(resident['session']).removeprefix('codex-')
        print(f"send_to\tthread:{sid}\t({resident['id']})")
    else:
        print('send_to\tnone registered on that host: start one there (dispatch.sh for Codex) or send to 11-station')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
