#!/usr/bin/env python3
"""Conservative discovery ratchet (S1/S2), not a proof of no consumers."""
import argparse
import hashlib
import re
import runpy
import sys
from pathlib import Path

# This directory is exported from M0 by ci-infra.sh, never from candidate imports.
P = runpy.run_path(str(Path(__file__).with_name("doc_policy.py")))
S1 = re.compile(r'''multi-agent|agent-config/work|work/multi|["']work["']|/work/''')
S2 = re.compile(r'''ls-files|git grep|rglob\(|os\.walk\(|\.glob\(|readdirSync|filepath\.Walk|WalkDir|find\s+[."'$]''')


def scanned(name):
    return not name.endswith(".md") or Path(name).name in ("CLAUDE.md", "AGENTS.md", "SKILL.md")


def hits(name, data, platform=False):
    if not scanned(name):
        return []
    # Binary tracked files may contain literal path references too; decoding with
    # replacement preserves all ASCII discovery signals, without skipping them.
    return [(n, line.strip()) for n, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1)
            if S1.search(line) or (not platform and S2.search(line))]


def fingerprint(found):
    return "sha256:" + hashlib.sha256("\n".join(sorted(line for _, line in found)).encode()).hexdigest()


def discover(repo, revision, platform=False):
    result = {}
    for name, (_, kind, oid) in P["tree"](repo, revision).items():
        if not scanned(name):
            continue
        if kind != "blob":
            raise P["PolicyError"](f"unreadable_consumer {name}")
        found = hits(name, P["git"](repo, "cat-file", "blob", oid), platform)
        if found:
            result[name] = found
    return result


def verify(rows, found, repo_name):
    entries = {r["file"]: r for r in rows if r.get("repo", P["REPO"]) == repo_name}
    for name, lines in sorted(found.items()):
        if name not in entries:
            raise P["PolicyError"](f"unregistered_consumer {name}:{lines[0][0]}")
        if entries[name]["hits"] != fingerprint(lines):
            raise P["PolicyError"](f"consumer_changed {name}")
    for name in sorted(entries.keys() - found.keys()):
        print(f"WARN registry_stale {repo_name}/{name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--revision", required=True)
    ap.add_argument("--platform", type=Path, required=True)
    ap.add_argument("--platform-revision", required=True)
    args = ap.parse_args()
    try:
        rows = P["registry"](args.repo, args.base)
        verify(rows, discover(args.repo, args.revision), P["REPO"])
        verify(rows, discover(args.platform, args.platform_revision, True), "bifrost-platform")
        P["consumers"](args.repo, args.base, args.revision)
    except (P["PolicyError"], OSError, ValueError, KeyError, TypeError, P["yaml"].YAMLError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
