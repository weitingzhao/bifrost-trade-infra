#!/usr/bin/env python3
"""Point citations of absorbed material at the laws that absorb it.

Legislation, 2026-11-24. Owner: once the new laws cover the material, every
citation of the material in code and documents points at the new law, and
then the material is archived (repealed). This rewrites one checkout's
working tree in place; review the diff and commit it like any change.

The map comes from the register (PROD, read-only as agent_reader, or --laws
JSON): each law in force names the material it absorbs (frame.absorbs); a
citation of material N becomes a citation of the lowest-numbered law that
absorbs N, in the same form (law N, Law N, 法 N, OWNER_LAW #N).

Not rewritten:
  - migration files already applied (their checksums are recorded);
  - the auto mode rules (the Owner's);
  - tests whose law numbers are a test register's, not the real one.

  scripts/laws/rewrite_refs.py <checkout>            # rewrite, print a summary
  scripts/laws/rewrite_refs.py <checkout> --dry-run  # only print
  scripts/laws/rewrite_refs.py <checkout> --to-codes # laws in force by number -> LAW-k
"""
import argparse
import fnmatch
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import residual_scan  # noqa: E402

# The scan's pattern, with the form kept as a group.
FORMS = residual_scan.CITE.replace("(?:", "((?:", 1).replace(")([0-9]", "))([0-9]", 1)
SKIP = (
    "*/migrations/*.sql",
    "*/auto-mode/*",
    "*/planstore/*_test.go",
    "*/instruments/*",
    "*/owner/__tests__/lawFramework.test.tsx",
    "*/laws/test_*.py",
    "*/laws/*.py",
    "*OWNER_LAW.md",
    "*/node_modules/*",
)


def absorbed_map(laws):
    """material number -> the lowest-numbered law in force that absorbs it."""
    out = {}
    for b in laws:
        frame = b.get("frame") or {}
        if residual_scan.state(b) != "现行":
            continue
        for m in frame.get("absorbs") or []:
            n = int(b["law"])
            if m not in out or n < out[m]:
                out[m] = n
    return out


def rewrite(text, amap, material):
    count = 0

    def sub(mt):
        nonlocal count
        n = mt.group(2)
        if n in material and n in amap:
            count += 1
            return mt.group(1) + str(amap[n])
        return mt.group(0)

    return re.sub(FORMS, sub, text), count


def to_codes(text, codes):
    """Rewrite citations of laws in force by number (law 95, 法 95, OWNER_LAW
    #95) as their code (LAW-10), the form and its prefix replaced. codes maps
    a law in force's number to its code."""
    count = 0

    def sub(mt):
        nonlocal count
        n = mt.group(2)
        if codes.get(n):
            count += 1
            return codes[n]
        return mt.group(0)

    return re.sub(FORMS, sub, text), count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("checkout")
    ap.add_argument("--laws", help="the register as JSON (default: read PROD as agent_reader)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--to-codes", action="store_true", help="rewrite citations of laws in force as LAW-k (LAW-1 一)")
    a = ap.parse_args()
    laws = residual_scan.read_laws(a.laws)
    material = {b["law"] for b in laws if residual_scan.state(b) == "素材"}
    amap = absorbed_map(laws)
    in_force = {b["law"] for b in laws if residual_scan.state(b) == "现行"}
    root = pathlib.Path(a.checkout)
    files = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
    total, touched = 0, 0
    for f in files:
        if not f or any(fnmatch.fnmatch("/" + f, g) for g in SKIP):
            continue
        p = root / f
        try:
            text = p.read_text()
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        if a.to_codes:
            new, n = to_codes(text, {k: residual_scan.law_code(b) for b in laws if (k := str(b["law"])) in in_force})
        else:
            new, n = rewrite(text, amap, material)
        if n:
            total += n
            touched += 1
            print(f"{n:4d}  {f}")
            if not a.dry_run:
                p.write_text(new)
    print(f"{total} citations in {touched} files {'would be ' if a.dry_run else ''}rewritten; material absorbed: {len(amap)}")


if __name__ == "__main__":
    main()
