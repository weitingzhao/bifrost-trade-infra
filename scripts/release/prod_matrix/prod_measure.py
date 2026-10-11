#!/usr/bin/env python3
"""PROD write matrix, round 1: inventory, explicit questions, offline replay.

The two summary lines are always first on replay. Exit 0 is not produced.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from canon import SUMMARY_1, MatrixExit, dump_line, summary_line
from classify import replay, truncated
from exceptions import parse_today
from questions import count_questions, expand, fixed_askable, over_budget
from schema import read_declared

HERE = Path(__file__).resolve().parent


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PROD write matrix, round 1")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("replay", "collect"):
        command = sub.add_parser(name)
        if name == "replay":
            command.add_argument("--bundle", required=True)
        else:
            command.add_argument("--bundle-out", required=True)
        command.add_argument("--targets", default=str(HERE / "prod_targets.json"))
        command.add_argument("--fixed", default=str(HERE / "prod_fixed_identities.json"))
        command.add_argument("--exceptions", default=str(HERE / "prod_write_exceptions.json"))
        command.add_argument("--nontargets", default=str(HERE / "prod_nontargets.json"))
        command.add_argument("--today", default=None)
    return parser


def _load(args):
    targets = read_declared(Path(args.targets), "prod_targets.json")
    fixed = read_declared(Path(args.fixed), "prod_fixed_identities.json")
    exceptions = read_declared(Path(args.exceptions), "prod_write_exceptions.json")
    nontargets = read_declared(Path(args.nontargets), "prod_nontargets.json")
    today = parse_today(args.today)
    return targets, fixed, exceptions, nontargets, today


def run_replay(args) -> tuple[int, str]:
    targets, fixed, exceptions, nontargets, today = _load(args)
    bundle = read_declared(Path(args.bundle), "bundle")
    return replay(bundle, targets, fixed, exceptions, nontargets, today)


def run_collect(args) -> int:
    targets, fixed, exceptions, nontargets, today = _load(args)
    lower = count_questions(fixed_askable(fixed["rows"]), targets["questions"])
    if over_budget(lower):
        _code, text = truncated(lower)
        sys.stdout.write(text)
        return 2
    from collect import kubectl_transport, read_discovery, read_identities, send_questions
    from exceptions import assert_asked_discovered
    from identities import assemble, inventory

    session, caller = read_identities(kubectl_transport)
    identities = assemble(inventory(session.commands, require_discovery=False), fixed["rows"])
    planned = expand(identities, targets["questions"])
    count = len(planned)
    if over_budget(count):
        _code, text = truncated(count)
        sys.stdout.write(text)
        return 2
    read_discovery(session)
    discovered = inventory(session.commands)
    assert_asked_discovered(targets["questions"], discovered["resources"])
    bundle = send_questions(session, caller, planned)
    from schema import validate_document

    validate_document("bundle", bundle)
    Path(args.bundle_out).write_text(dump_line(bundle) + "\n", encoding="utf-8")
    code, text = replay(bundle, targets, fixed, exceptions, nontargets, today)
    sys.stdout.write(text)
    return code


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "replay":
            code, text = run_replay(args)
            sys.stdout.write(text)
            return code
        return run_collect(args)
    except MatrixExit as exc:
        sys.stdout.write(SUMMARY_1 + "\n")
        sys.stdout.write(summary_line(0, 0, 0) + "\n")
        print(exc.message, file=sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
