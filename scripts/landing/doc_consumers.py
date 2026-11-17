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


def registry_change(base_rows, rows, found, found_platform):
    """What a commit may do to the registry itself without anyone reading it (step 1,
    2026-11-14). The registry of the candidate is the one the checks below read, so a
    commit that changes a fingerprinted line can carry the new fingerprint with it; this
    says which changes of the registry that is allowed to be.

    Allowed: a row whose hits alone changed (every other field as it was: the row's class
    and read set, which are all the protection reads, stay); a row removed whose file no
    longer has a hit. Refused, for someone to read: a row added, a row whose class, reads,
    effect, why or checked_by changed, a row removed while its file still has hits. That
    the new hits are the real ones is verify's part, on the candidate's tree.
    """
    def keyed(listed):
        return {(r.get("repo", P["REPO"]), r["file"]): r for r in listed}
    was, now = keyed(base_rows), keyed(rows)
    for key in sorted(now.keys() - was.keys()):
        raise P["PolicyError"](f"registry_row_added {key[1]}")
    for key in sorted(was.keys() & now.keys()):
        if {k: v for k, v in was[key].items() if k != "hits"} != {k: v for k, v in now[key].items() if k != "hits"}:
            raise P["PolicyError"](f"registry_row_changed {key[1]}")
    for repo_name, name in sorted(was.keys() - now.keys()):
        if name in (found if repo_name == P["REPO"] else found_platform):
            raise P["PolicyError"](f"registry_row_removed {name}")


RETIRED = ("consumers: retired 2026-11-16 (confirmed by the Owner): documents and code pass the same CI, "
           "so the registry of document consumers is no longer read")


def main():
    # The check answered one question: may a document land by the light lane, unread?
    # That lane left on 2026-11-12 (the scope stage); every commit now runs every stage.
    # judge() below is the check as it was; reverting this commit puts it back.
    print(RETIRED)
    return 0


def judge():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--revision", required=True)
    ap.add_argument("--platform", type=Path, required=True)
    ap.add_argument("--platform-revision", required=True)
    ap.add_argument("--purpose", choices=("landing", "push"), default="landing")
    args = ap.parse_args()
    try:
        # The candidate's own registry is what its tree is held to (2026-11-14): a commit
        # that changes a fingerprinted line brings the new fingerprint with it, and what it
        # may do to the registry is registry_change's. Before, the base's registry was
        # read, so such a commit was red by construction and reached main only by hand.
        base_rows = P["registry"](args.repo, args.base)
        rows = P["registry"](args.repo, args.revision)
        found = discover(args.repo, args.revision)
        found_platform = discover(args.platform, args.platform_revision, True)
        registry_change(base_rows, rows, found, found_platform)
        verify(rows, found, P["REPO"])
        verify(rows, found_platform, "bifrost-platform")
        # A changed path may not be one a reader reads, by the base's rows (a commit
        # cannot drop a reader and change what it reads) and by the candidate's.
        P["consumers"](args.repo, args.base, args.revision, args.purpose)
        P["consumed"](rows, [r[1] for r in P["changes"](args.repo, args.base, args.revision, args.purpose)])
    except (P["PolicyError"], OSError, ValueError, KeyError, TypeError, P["yaml"].YAMLError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
