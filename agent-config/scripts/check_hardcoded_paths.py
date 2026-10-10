#!/usr/bin/env python3
"""Hardcoded home-path ratchet (W-36 / D-4).

Counts macOS home paths (/Users/<name>/...) committed in the workspace repos. A file may
not gain one and no new file may carry one; the remaining ones are listed in
hardcoded-paths-baseline.txt with their counts. Placeholder names (you, x, ...) are fine.
agent-config/work/ in bifrost-trade-infra holds dated reports and is not scanned.

Code finds the workspace from BIFROST_WORKSPACE or by walking up to
bifrost-platform/config/ops-context.yaml; docs write ~/... or <workspace>/....

    python3 agent-config/scripts/check_hardcoded_paths.py                 # HEAD of each repo
    python3 agent-config/scripts/check_hardcoded_paths.py --ref origin/main
    python3 agent-config/scripts/check_hardcoded_paths.py --worktree      # uncommitted files too
    python3 agent-config/scripts/check_hardcoded_paths.py --update        # rewrite the baseline (lower only)

Exit 0 = at or below baseline everywhere and baseline exact, 1 = a new or grown file, or a
baseline entry that can be lowered (run --update and commit it).
Repos missing from the workspace (e.g. CI with one checkout) are skipped.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
INFRA = HERE.parents[1]
BASELINE = HERE / "hardcoded-paths-baseline.txt"
MARKER = Path("bifrost-platform") / "config" / "ops-context.yaml"
REPOS = (
    "bifrost-trade-core",
    "bifrost-trade-worker",
    "bifrost-trade-api",
    "bifrost-trade-frontend",
    "bifrost-trade-infra",
    "bifrost-research",
    "bifrost-platform",
    "bifrost-platform-plugin",
    "bifrost-platform-plugin-market-data",
    "bifrost-platform-plugin-flex-query",
    "bifrost-ui",
)
GREP = r"/Users/[A-Za-z0-9._-]+/"
NAME = re.compile(r"/Users/([A-Za-z0-9._-]+)/")
PLACEHOLDERS = {"you", "x", "me", "user", "username", "name", "example", "someone", "Shared"}
WORKTREE = "<worktree>"
SKIP = {"bifrost-trade-infra": ("agent-config/work/",)}


def workspace_root() -> Path:
    env = os.environ.get("BIFROST_WORKSPACE", "").strip()
    if env:
        root = Path(env).expanduser().resolve()
        if not (root / MARKER).is_file():
            sys.exit(f"BIFROST_WORKSPACE={root} is not a Bifrost workspace ({MARKER} missing)")
        return root
    for d in INFRA.parents:
        if (d / MARKER).is_file():
            return d
    sys.exit(f"workspace root not found above {INFRA}; set BIFROST_WORKSPACE")


def repo_dir(root: Path, repo: str) -> Path:
    # This script's own checkout is the infra tree under test (it may be a worktree).
    return INFRA if repo == "bifrost-trade-infra" else root / repo


def scan_repo(path: Path, repo: str, ref: str) -> Counter:
    opts, revs = (["--untracked"], []) if ref == WORKTREE else ([], [ref])
    out = subprocess.run(
        ["git", "-C", str(path), "grep", "-I", "-o", *opts, "-E", GREP, *revs, "--"],
        capture_output=True, text=True,
    )
    if out.returncode not in (0, 1):
        sys.exit(f"git grep failed in {path} at {ref}: {out.stderr.strip()}")
    counts: Counter = Counter()
    prefix = f"{ref}:"
    for line in out.stdout.splitlines():
        if line.startswith(prefix):
            line = line[len(prefix):]
        file, _, match = line.partition(":")
        if any(file.startswith(s) for s in SKIP.get(repo, ())):
            continue
        m = NAME.search(match)
        if m and m.group(1) not in PLACEHOLDERS:
            counts[f"{repo}/{file}"] += 1
    return counts


def scan(root: Path, ref: str) -> tuple[Counter, list[str]]:
    counts: Counter = Counter()
    scanned: list[str] = []
    for repo in REPOS:
        path = repo_dir(root, repo)
        if not (path / ".git").exists():
            continue
        if ref != WORKTREE and subprocess.run(["git", "-C", str(path), "rev-parse", "-q", "--verify", ref],
                                              capture_output=True).returncode:
            continue
        counts.update(scan_repo(path, repo, ref))
        scanned.append(repo)
    return counts, scanned


def load_baseline(path: Path = BASELINE) -> dict[str, int]:
    base: dict[str, int] = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        count, _, file = line.partition(" ")
        base[file.strip()] = int(count)
    return base


def compare(counts: Counter, base: dict[str, int], scanned: list[str]) -> tuple[list[str], list[str]]:
    grown = [f"{f}: {n} (baseline {base.get(f, 0)})" for f, n in sorted(counts.items()) if n > base.get(f, 0)]
    lower = [
        f"{f}: {counts.get(f, 0)} (baseline {n})"
        for f, n in sorted(base.items())
        if f.split("/", 1)[0] in scanned and counts.get(f, 0) < n
    ]
    return grown, lower


def write_baseline(counts: Counter, path: Path = BASELINE) -> None:
    head = [line for line in path.read_text().splitlines() if line.startswith("#")] if path.is_file() else []
    body = [f"{n} {f}" for f, n in sorted(counts.items())]
    path.write_text("\n".join(head + body) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--worktree", action="store_true", help="scan the working trees instead of a ref")
    ap.add_argument("--update", action="store_true", help="lower the baseline to the current counts")
    args = ap.parse_args()

    root = workspace_root()
    ref = WORKTREE if args.worktree else args.ref
    counts, scanned = scan(root, ref)
    base = load_baseline()
    grown, lower = compare(counts, base, scanned)
    if grown:
        print("✗ hardcoded home paths added (use BIFROST_WORKSPACE / walk up to the marker in code, ~/ or <workspace>/ in docs):")
        print("\n".join("  " + g for g in grown))
        return 1
    if args.update:
        kept = Counter({f: n for f, n in base.items() if f.split("/", 1)[0] not in scanned})
        write_baseline(kept + counts)
        print(f"baseline rewritten: {sum((kept + counts).values())} paths in {len(kept + counts)} files")
        return 0
    if lower:
        print("✗ baseline can be lowered (run with --update and commit hardcoded-paths-baseline.txt):")
        print("\n".join("  " + item for item in lower))
        return 1
    print(f"✓ hardcoded home paths at baseline: {sum(counts.values())} in {len(counts)} files "
          f"({len(scanned)} repos at {ref})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
