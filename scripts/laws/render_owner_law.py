#!/usr/bin/env python3
"""Render agent-config/OWNER_LAW.md's register table from the platform's
register of laws (legislation, 2026-11-24).

From 2026-11-24 a law changes only by an approved law_amend card, and the
register in the platform (each law a stream law:<n> of law_recorded events)
is the record. OWNER_LAW.md is no longer written by hand: this script
rewrites the numbered rows of its 「## 登记」 table from each law as it stands
in the register, keeps the rest of the file (the preamble, the H1-H6 table)
as it is, and appends a law the register has that the file has not.

It reads PROD's register read-only as agent_reader (AGENT_FACTS.md: psql
-h 192.168.10.73 -p 30432 -U agent_reader, password in ~/.pgpass), or a JSON
file of the laws (--laws, one object per law with the law_recorded body
fields) for a test or an offline run.

  scripts/laws/render_owner_law.py            # rewrite in place
  scripts/laws/render_owner_law.py --check    # exit 1 if the file differs
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILE = ROOT / "agent-config" / "OWNER_LAW.md"
ROW = re.compile(r"^\|\s*(\d+|(?:DAO|CORE|LAW|ZONE)-\d+)\s*\|")
CODE_BASE = 85  # LAW-k is number 85+k (LAW-1 一; platform planstore lawcode.go)


def code(law):
    """A law's code: the one its record carries (from round 2 on), else LAW-k
    = number 85+k, and CORE-1 for 89; the number for material."""
    if law.get("code"):
        return law["code"]
    n = str(law["law"])
    if not (n.isdigit() and int(n) > CODE_BASE):
        return n
    return "CORE-1" if int(n) == CODE_BASE + 4 else f"LAW-{int(n) - CODE_BASE}"


def number_of(ref, laws=()):
    """A row's first cell as the register's number."""
    for l in laws:
        if code(l) == ref:
            return str(l["law"])
    m = re.fullmatch(r"LAW-(\d+)", ref)
    return str(CODE_BASE + int(m.group(1))) if m else ref
PSQL = os.environ.get("PSQL", "/opt/homebrew/opt/libpq/bin/psql")
QUERY = """SELECT json_agg(b ORDER BY (b->>'law')::int) FROM (
  SELECT DISTINCT ON (event_stream_id) body_json AS b FROM agentrt.event
  WHERE event_type = 'law_recorded' AND starts_with(event_stream_id, 'law:')
  ORDER BY event_stream_id, event_id DESC) x"""


def read_laws(path):
    if path:
        return json.loads(pathlib.Path(path).read_text())
    out = subprocess.run([PSQL, "-h", "192.168.10.73", "-p", "30432", "-U", "agent_reader", "-d", "bifrost_platform",
                          "-At", "-c", QUERY], check=True, capture_output=True, text=True).stdout.strip()
    return json.loads(out or "[]")


def cell(s):
    s = (s or "").strip().replace("\n", " ")
    return s if s else "—"


def row(law):
    status = law.get("status", "")
    if law.get("op") != "transcribed":
        # A card changed it: the card is the law; say which, and which version.
        status = f"{status}（第 {law.get('version')} 版）"
    return "| " + " | ".join([code(law), cell(law.get("said_on")), cell(law.get("text")), cell(law.get("where")),
                              cell(law.get("enforced_by")), cell(status), cell(law.get("old_wording"))]) + " |"


def render(text, laws):
    by = {str(l["law"]): l for l in laws}
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith("## 登记"))
    seen, last, drop = set(), None, set()
    for i in range(start, len(lines)):
        m = ROW.match(lines[i])
        if not m:
            continue
        n = number_of(m.group(1), laws)
        seen.add(n)
        last = i
        law = by.get(n)
        # A repealed law leaves the file (LAW-1: a repealed law
        # must not linger; it stays only in the platform's ledger).
        if law and repealed(law):
            drop.add(i)
            continue
        # A transcribed law is the file's own row: keep its bytes (the
        # transcription trimmed them; the file stays as written).
        if law and law.get("op") != "transcribed":
            lines[i] = row(law)
    extra = [row(by[n]) for n in sorted(by, key=int) if n not in seen and not repealed(by[n])]
    if extra:
        lines[last + 1:last + 1] = extra
    return "\n".join(l for i, l in enumerate(lines) if i not in drop)


def repealed(law):
    return law.get("status") == "废止"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--laws", help="a JSON file of the laws instead of PROD's register")
    ap.add_argument("--check", action="store_true", help="exit 1 if the file differs from the register")
    a = ap.parse_args()
    text = FILE.read_text()
    out = render(text, read_laws(a.laws))
    if a.check:
        if out != text:
            print("OWNER_LAW.md differs from the register; run scripts/laws/render_owner_law.py", file=sys.stderr)
            return 1
        return 0
    FILE.write_text(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
