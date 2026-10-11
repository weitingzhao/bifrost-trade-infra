#!/usr/bin/env python3
"""Line-for-line ratchet over this repository's k8s/ tree."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from canon import MatrixExit
from ratchet import diff, lines_of, read_baseline, scan

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PROD matrix repository ratchet")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--root", default=str(REPO / "k8s"))
    parser.add_argument("--baseline", default=str(HERE / "prod_write_baseline.jsonl"))
    parser.add_argument("--fixed", default=str(HERE / "prod_fixed_identities.json"))
    args = parser.parse_args(argv)
    if not args.check and not args.write:
        args.check = True
    try:
        rows = scan(Path(args.root), Path(args.fixed))
        lines = lines_of(rows)
        baseline = Path(args.baseline)
        if args.write:
            baseline.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"prod_ratchet: wrote {len(lines)} lines")
            return 0
        messages = diff(lines, read_baseline(baseline))
    except MatrixExit as exc:
        print(exc.message, file=sys.stderr)
        return exc.code
    if messages:
        print("\n".join(messages))
        return 1
    print(f"prod_ratchet: ok ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
