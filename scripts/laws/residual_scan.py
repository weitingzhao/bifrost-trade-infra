#!/usr/bin/env python3
"""Residual scan of the laws (legislation, 2026-11-24).

Owner 2026-11-24: deleting or merging a law is not done until nothing in the
project still points at it; and the cycle (inventory, distil, delete,
inventory again) runs many rounds, so the scan is a tool run each round, not
a one-off.

It reads the register of laws (PROD, read-only as agent_reader, or --laws
JSON) and every repository's main, and reports:

  refs     every citation of a law by number in code and documents
           (LAW-k; and the old forms 法 N, law N, Law N, OWNER_LAW #N), each classified by the state
           of what it points at: 现行 (fine), 素材 (to be rewritten when a
           law absorbs it), 废止 (to be removed now), 无 (no such law);
  shadow   rules in the governance files that carry an Owner date but sit
           outside the framework (CLAUDE.md, OWNER_EXEC.md, skills,
           charters): the shadow laws.

  scripts/laws/residual_scan.py                  # summary
  scripts/laws/residual_scan.py --json out.json  # full list with places
  scripts/laws/residual_scan.py --law 50         # where law 50 is cited
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]  # the workspace
PSQL = os.environ.get("PSQL", "/opt/homebrew/opt/libpq/bin/psql")
QUERY = """SELECT json_agg(b ORDER BY (b->>'law')::int) FROM (
  SELECT DISTINCT ON (event_stream_id) body_json AS b FROM agentrt.event
  WHERE event_type = 'law_recorded' AND starts_with(event_stream_id, 'law:')
  ORDER BY event_stream_id, event_id DESC) x"""
# 法 N, but not a word ending in 法 followed by a number (合法 0, 读法 0, 算法 2:
# round 1 counted twelve 「合法 0」 as citations of a law 0).
CITE = r"(?:(?<![合方算办做写用语手说想看读解打玩立执修宪司违守依无设])法 ?|[Ll]aw |OWNER_LAW ?#)([0-9]{1,3})(?![0-9])"
# A law is written LAW-k (Owner 2026-11-25: 「以后法条统一叫LAW 开始，不用简写」):
# k counts from the first law the framework holds, number 86 (the platform's
# planstore lawcode.go). Rows 1 to 85 were material and have no code.
CODE = r"LAW-([1-9][0-9]*)(?![0-9])"
CODE_BASE = 85


def code(n):
    """Law n's code, or "" for material (n at most 85)."""
    return f"LAW-{int(n) - CODE_BASE}" if str(n).isdigit() and int(n) > CODE_BASE else ""


def number_of(ref):
    """A reference (LAW-k or a number) as the register's number."""
    m = re.fullmatch(CODE, ref.strip())
    return str(CODE_BASE + int(m.group(1))) if m else ref.strip()


SKIP = (":!**/node_modules/**", ":!*.lock", ":!**/OWNER_LAW.md", ":!scripts/laws/**")  # the scan's own examples are not citations
SHADOW_FILES = ("agent-config/CLAUDE.md", "agent-config/OWNER_EXEC.md", "agent-config/claude/skills", "agent-config/charters")
OWNER_DATE = re.compile(r"Owner[ ,，（(]*20[0-9]{2}-[0-9]{2}-[0-9]{2}|（Owner [0-9]{2}-[0-9]{2}")


def read_laws(path):
    if path:
        return json.loads(pathlib.Path(path).read_text())
    out = subprocess.run([PSQL, "-h", "192.168.10.73", "-p", "30432", "-U", "agent_reader", "-d", "bifrost_platform",
                          "-At", "-c", QUERY], check=True, capture_output=True, text=True).stdout.strip()
    return json.loads(out or "[]")


def state(law):
    if law.get("status") == "废止":
        return "废止"
    if law.get("op") == "transcribed" or not (law.get("frame") or {}).get("level") is not None:
        return "素材"
    return "现行"


EXCEPTIONS = pathlib.Path(__file__).resolve().parent / "exceptions.txt"


def exceptions(path=EXCEPTIONS):
    """The citations that are right as they are, each repo:path:law with a
    reason after #, kept in the repository so that adding one has a commit
    (the audit line's review, 2026-11-24: an exception list in a ledger
    anyone can edit would make the target 0 true by itself)."""
    out = set()
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        key = line.split("#", 1)[0].strip()
        if key:
            out.add(key)
    return out


def excepted(c, allowed):
    """Whether citation c is on the exception list. A line is repo:path:law;
    path and law may be shell patterns (a whole class of files, every law),
    so a class with one reason is one line, not one line per citation."""
    import fnmatch
    for key in allowed:
        repo, path, law = (key.split(":", 2) + ["", ""])[:3]
        if repo == c["repo"] and fnmatch.fnmatch(c["path"], path) and fnmatch.fnmatch(c["law"], law):
            return True
    return False


def repos():
    return sorted(p for p in ROOT.iterdir() if p.name.startswith("bifrost-") and (p / ".git").exists() and not p.name.endswith("-archived"))


def refs():
    out = []
    for r in repos():
        p = subprocess.run(["git", "-C", str(r), "grep", "-nP", f"{CITE}|{CODE}", "origin/main", "--", *SKIP], capture_output=True, text=True)
        for line in p.stdout.splitlines():
            _, path, num, text = line.split(":", 3)
            found = [(n, "number") for n in re.findall(CITE, text)] + [(str(CODE_BASE + int(k)), "code") for k in re.findall(CODE, text)]
            for n, form in found:
                out.append({"repo": r.name, "path": path, "line": int(num), "law": n, "form": form, "text": text.strip()[:200]})
    return out


def shadow():
    infra = ROOT / "bifrost-trade-infra"
    out = []
    p = subprocess.run(["git", "-C", str(infra), "grep", "-nE", OWNER_DATE.pattern, "origin/main", "--", *SHADOW_FILES],
                       capture_output=True, text=True)
    for line in p.stdout.splitlines():
        _, path, num, text = line.split(":", 3)
        out.append({"repo": infra.name, "path": path, "line": int(num), "text": text.strip()[:200]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--laws")
    ap.add_argument("--json")
    ap.add_argument("--law")
    ap.add_argument("--root", help="the workspace holding the bifrost-* repositories (default: two levels above this repository)")
    a = ap.parse_args()
    global ROOT
    if a.root:
        ROOT = pathlib.Path(a.root).resolve()
    laws = {str(l["law"]): l for l in read_laws(a.laws)}
    cited = refs()
    allowed = exceptions()
    for c in cited:
        c["state"] = state(laws[c["law"]]) if c["law"] in laws else "无"
        # A law in force cited by its number, not its code: written the old
        # way, to be rewritten (rewrite_refs.py --to-codes).
        if c["state"] == "现行" and c.get("form") == "number":
            c["state"] = "旧写法"
        if excepted(c, allowed):
            c["state"] = "例外"
    if a.law:
        for c in cited:
            if c["law"] == a.law:
                print(f'{c["repo"]}:{c["path"]}:{c["line"]}: {c["text"]}')
        return 0
    sh = shadow()
    by_state, by_law = {}, {}
    for c in cited:
        by_state[c["state"]] = by_state.get(c["state"], 0) + 1
        by_law.setdefault(c["law"], [c["state"], 0])[1] += 1
    report = {"refs": {"total": len(cited), "by_state": by_state,
                       "by_law": {n: {"state": s, "count": k} for n, (s, k) in sorted(by_law.items(), key=lambda x: -x[1][1])}},
              "shadow": {"total": len(sh)}}
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps({**report, "ref_list": cited, "shadow_list": sh}, ensure_ascii=False, indent=1))
    print(f'refs: {len(cited)} citations of a law by number; by state: {by_state}')
    for n, v in list(report["refs"]["by_law"].items())[:15]:
        print(f'  law {n} ({v["state"]}): {v["count"]}')
    print(f'shadow: {len(sh)} dated Owner rules in governance files outside the framework')
    return 0


if __name__ == "__main__":
    sys.exit(main())
