#!/usr/bin/env python3
"""Render one seat's identity card (Crew, 2026-11-21): column 1 from charters/seats.yaml, columns 2-6 from
charters/cards/<id>.yaml. Prints at most one screen (40 lines); exits 1 when the card is longer or the seat is unknown.
Usage: render-card.py <seat id> | render-card.py --all (checks every card)."""
import pathlib, sys, yaml
root = pathlib.Path(__file__).resolve().parents[1] / 'charters'
seats = {s['id']: s for s in yaml.safe_load((root / 'seats.yaml').read_text())['seats']}
def card(i):
    s = seats[i]; c = yaml.safe_load((root / 'cards' / f'{i}.yaml').read_text()); L = []
    L.append(f"【{i}】{'主人席位' if s['kind']=='owner' else '临时席位'} · 领域 {s['domain']} · 坐的是 {s['harness']}（{c['as_of']}）")
    L.append('合约：' + '；'.join(str(x) for x in c['laws']))
    for title, key in (('我握的', 'owns'), ('对外答应的口子', 'promises'), ('我自己定、不用问', 'decide_alone'), ('别人来问我必须答', 'must_answer'), ('墙', 'walls')):
        L.append(f'{title}：'); L += ['  - ' + x for x in c[key]]
    L.append('不是我的：'); L += [f"  - {x['what']} → {x['to']}" for x in c['not_mine']]
    return L
ids = sorted(p.stem for p in (root / 'cards').glob('*.yaml')) if sys.argv[1:] == ['--all'] else sys.argv[1:]
bad = 0
for i in ids:
    L = card(i)
    if len(L) > 40: print(f'{i}: {len(L)} lines, over one screen', file=sys.stderr); bad = 1
    if sys.argv[1:] != ['--all']: print('\n'.join(L))
print(f'cards ok: {len(ids)}') if sys.argv[1:] == ['--all'] and not bad else None
sys.exit(bad)
