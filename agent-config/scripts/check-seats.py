#!/usr/bin/env python3
"""Read-only reconcile of charters/seats.yaml against the charter files (2026-11-21, Labor block).
Checks: one seat row per charter page; domain_id in domain_ids; temporary rows name an owner seat or human in invited_by.
Not wired into CI (a new check is a referee rule: it goes to the Owner first). Exit 1 on any mismatch."""
import pathlib, sys, yaml
root = pathlib.Path(__file__).resolve().parents[1] / 'charters'
t = yaml.safe_load((root / 'seats.yaml').read_text())
pages = {p.name for p in root.glob('*.md') if p.name != 'README.md'}
rows = t['seats']; bad = []
have = [r['charter'] for r in rows]
bad += [f'charter page without a seat row: {p}' for p in sorted(pages - set(have))]
bad += [f'seat row without a charter page: {c}' for c in sorted(set(have) - pages)]
bad += [f'duplicate charter row: {c}' for c in set(have) if have.count(c) > 1]
ids = {r['id'] for r in rows} | {h['id'] for h in t.get('humans', [])}
for r in rows:
    d = r.get('domain_id')
    if d is not None and d not in t['domain_ids']: bad.append(f"{r['id']}: unknown domain_id {d}")
    if r['kind'] not in ('owner',): bad.append(f"{r['id']}: kind must be owner here")
for x in t.get('temporary') or []:
    if x.get('invited_by') not in ids: bad.append(f"temporary {x.get('run_key')}: invited_by not a seat or human")
print('\n'.join(bad) or f'seats ok: {len(rows)} seats, {len(t.get("temporary") or [])} temporary, {len(t.get("humans") or [])} human')
sys.exit(1 if bad else 0)
