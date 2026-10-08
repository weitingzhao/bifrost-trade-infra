#!/usr/bin/env python3
"""Report Work: trailer coverage. This is a report, not a gate: it always exits 0.

Scans the workspace's git checkouts (``.git`` is a directory; worktrees and the
archived analytics repo are skipped) and prints, per repo, how many commits in
the window lack a ``Work:`` trailer or carry ``Work: unassigned``.

    python3 scripts/check_work_trailers.py --since 7d
    python3 scripts/check_work_trailers.py --self-test
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

WORK_LINE = re.compile(r"^Work:\s*(.*\S)\s*$", re.I)


def parse_since(raw: str) -> str:
    m = re.fullmatch(r"(\d+)([dh])", raw.strip())
    if not m:
        raise SystemExit(f"--since wants Nd or Nh, got {raw!r}")
    n, unit = int(m.group(1)), m.group(2)
    if n <= 0:
        raise SystemExit("--since must be positive")
    return f"{n} {'days' if unit == 'd' else 'hours'} ago"


def work_trailer(message: str) -> str | None:
    """The Work value in the trailer block, or None when that block has no Work key.

    Git's trailer block is the last paragraph. A one-paragraph message has none.
    The first Work line wins, matching lineage.sh.
    """
    lines = message.replace("\r\n", "\n").rstrip("\n").split("\n")
    start = len(lines)
    while start > 1 and lines[start - 1].strip() == "":
        start -= 1
    while start > 1 and lines[start - 1].strip() != "":
        start -= 1
    if start <= 1:
        return None
    found = None
    for line in lines[start:]:
        m = WORK_LINE.match(line)
        if m and found is None:
            found = m.group(1).strip()
    return found


def classify(message: str) -> str:
    """'ok', 'missing', or 'unassigned'."""
    value = work_trailer(message)
    if value is None:
        return "missing"
    if value.lower() == "unassigned":
        return "unassigned"
    return "ok"


def workspace_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    # scripts/ lives in bifrost-trade-infra; the checkouts are its siblings.
    return here.parents[1].parent


def repos(root: pathlib.Path) -> list[pathlib.Path]:
    out = []
    for path in sorted(root.glob("bifrost-*")):
        if not path.is_dir():
            continue
        if path.name == "bifrost-analytics":
            continue
        git_entry = path / ".git"
        if git_entry.is_dir():
            out.append(path)
    return out


def commits(repo: pathlib.Path, since: str) -> list[str]:
    r = subprocess.run(
        ["git", "-C", str(repo), "log", f"--since={since}", "--format=%x1e%B"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return []
    parts = r.stdout.split("\x1e")
    return [p for p in parts if p.strip()]


def report(root: pathlib.Path, since_arg: str) -> str:
    since = parse_since(since_arg)
    lines = [f"Work: trailers since {since_arg} ({since})", ""]
    header = f"{'repo':<42} {'commits':>7} {'missing':>8} {'unassigned':>11} {'gap':>7}"
    lines.append(header)
    total_c = total_m = total_u = 0
    found = repos(root)
    if not found:
        lines.append("(no checkouts)")
    for repo in found:
        msgs = commits(repo, since)
        missing = sum(1 for m in msgs if classify(m) == "missing")
        unassigned = sum(1 for m in msgs if classify(m) == "unassigned")
        n = len(msgs)
        gap = (missing + unassigned) / n if n else 0.0
        total_c += n
        total_m += missing
        total_u += unassigned
        lines.append(f"{repo.name:<42} {n:7d} {missing:8d} {unassigned:11d} {gap:6.0%}")
    gap = (total_m + total_u) / total_c if total_c else 0.0
    lines.append(f"{'TOTAL':<42} {total_c:7d} {total_m:8d} {total_u:11d} {gap:6.0%}")
    lines.append("")
    lines.append(f"checkouts: {len(found)} (worktrees skipped; bifrost-analytics skipped)")
    lines.append("gap = (missing + unassigned) / commits. Not a gate.")
    return "\n".join(lines)


def self_test() -> int:
    cases = [
        ("fix\n\nWork: TD-1, LANE-C\n", "ok"),
        ("fix a typo\n", "missing"),
        ("fix\n\nWork: unassigned\n", "unassigned"),
        ("fix\n\nWork: Unassigned\n", "unassigned"),
        ("subject\n\nWork: TD-1\n\nnot a trailer\n", "missing"),
        ("only one paragraph Work: TD-1\n", "missing"),
    ]
    bad = 0
    for msg, want in cases:
        got = classify(msg)
        if got != want:
            print(f"FAIL classify {got!r} want {want!r} for {msg!r}", file=sys.stderr)
            bad += 1
    if parse_since("7d") != "7 days ago" or parse_since("12h") != "12 hours ago":
        print("FAIL parse_since", file=sys.stderr)
        bad += 1
    if bad:
        return 1
    print("ok check_work_trailers --self-test")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Report Work: trailer coverage (not a gate).")
    p.add_argument("--since", default="7d", help="window: Nd or Nh (default 7d)")
    p.add_argument("--self-test", action="store_true", help="check the trailer parser and exit")
    p.add_argument("--root", default="", help="workspace root (default: sibling of this repo)")
    args = p.parse_args(argv)
    if args.self_test:
        return self_test()
    root = pathlib.Path(args.root) if args.root else workspace_root()
    print(report(root, args.since))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
