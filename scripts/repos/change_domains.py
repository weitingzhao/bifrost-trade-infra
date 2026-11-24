#!/usr/bin/env python3
"""Which domains a structural change touched: the reading behind law
"structure elasticity" s2 and s3 (approval #719; Foundation 2026-11-24).

Maps every file a commit range changed in bifrost-platform to its domain by
config/domain-ownership.json at the range's end: an exact file in "paths",
else the longest matching directory among "packages" and the domains'
building paths, else "default". Bookkeeping files (ownership table,
gate baselines, unit declarations, map reviews) are listed apart. Users of the moved code are the domains
outside the ones named by --moved (and assembly, which only wires); s2/s3
want that count at 0.

Usage: change_domains.py <platform checkout> <rev range> --moved crew,station
"""
import argparse
import collections
import json
import subprocess

# The structure's own bookkeeping: the ownership table (and the console's copy), the gates' baselines,
# the unit declarations and the map's reviews change with every move and are
# not users of the moved code.
BOOKKEEPING = ("config/domain-ownership.json", "console/domain-ownership.json", "config/catalog-", "bifrost.units.yaml", "api/internal/codeguard/")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def owner_of(o, path):
    if path in o["paths"]:
        return o["paths"][path]["domains"]
    best, who = "", o["default"]["domains"]
    prefixes = [(k, v["domains"]) for k, v in o["packages"].items()]
    for d in o["domains"]:
        for b in d.get("buildings", []):
            prefixes += [(p, [d["id"]]) for p in b["paths"]]
    for p, ds in prefixes:
        if (path == p or path.startswith(p + "/")) and len(p) > len(best):
            best, who = p, ds
    return who


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("range")
    ap.add_argument("--moved", default="", help="comma-separated domains the change moves")
    a = ap.parse_args()
    end = a.range.split("..")[-1] or "HEAD"
    o = json.loads(git(a.repo, "show", f"{end}:config/domain-ownership.json"))
    files = [f for f in git(a.repo, "diff", "--name-only", a.range).splitlines() if f]
    moved = set(filter(None, a.moved.split(","))) | {"assembly"}
    by = collections.defaultdict(list)
    for f in files:
        for d in owner_of(o, f):
            by[d].append(f)
    books = sorted(f for f in files if f.startswith(BOOKKEEPING))
    outside = sorted({f for d, fs in by.items() if d not in moved for f in fs} - set(books))
    for d in sorted(by):
        print(f"{d}: {len(by[d])}")
    print(f"bookkeeping (not counted): {len(books)}")
    print(f"files changed outside {sorted(moved)}: {len(outside)}")
    for f in outside[:40]:
        print("  " + f)


if __name__ == "__main__":
    main()
