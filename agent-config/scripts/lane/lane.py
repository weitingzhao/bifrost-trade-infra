#!/usr/bin/env python3
"""Dispatch lane, round 1: recorder, decision and transition tables.

``run`` refuses with ``run is implemented in round 2``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from commands import (
    cmd_abandon,
    cmd_confirm,
    cmd_new,
    cmd_next_round,
    cmd_pass_set,
    cmd_queue,
    cmd_resolve,
    cmd_run,
    cmd_status,
    default_root,
    dumps,
    format_status,
    collect_repos,
)
from errors import LaneError


def _root(value: str | None) -> Path:
    return Path(value) if value else default_root()


def _build() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lane.py", description="Dispatch lane recorder (round 1)")
    parser.add_argument("--root", help="lane root (default ~/agent-work/lanes)")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="create a lane and open round 1")
    new.add_argument("lane_id")
    new.add_argument("--title", required=True)
    new.add_argument("--brief", required=True)
    new.add_argument("--repo", action="append", required=True, help="NAME:change|context:REF:SHA:TREE")
    new.add_argument("--max-rounds", type=int, default=2)
    new.add_argument("--config")
    new.add_argument("--pin", action="append", default=[])

    run = sub.add_parser("run", help="refuses in round 1")
    run.add_argument("lane_id")

    nxt = sub.add_parser("next-round", help="open the next round")
    nxt.add_argument("lane_id")
    nxt.add_argument("--brief", required=True)
    nxt.add_argument("--start", choices=("baseline", "pinned"), default="pinned")

    resolve = sub.add_parser("resolve", help="record a human resolution")
    resolve.add_argument("lane_id")
    resolve.add_argument("--attempt", required=True)
    resolve.add_argument("--kind", required=True, choices=("failed", "cancelled", "evidence-lost", "still-unknown", "exit-code"))
    resolve.add_argument("--operator", required=True)
    resolve.add_argument("--reason", required=True)
    resolve.add_argument("--evidence", required=True)
    resolve.add_argument("--code", type=int)

    confirm = sub.add_parser("confirm-ended", help="mark an execution confirmed ended")
    confirm.add_argument("lane_id")
    confirm.add_argument("--attempt", required=True)
    confirm.add_argument("--operator", required=True)
    confirm.add_argument("--how", required=True)

    abandon = sub.add_parser("abandon", help="abandon a lane")
    abandon.add_argument("lane_id")
    abandon.add_argument("--operator", required=True)
    abandon.add_argument("--reason", required=True)

    status = sub.add_parser("status", help="show the computed state")
    status.add_argument("lane_id")
    status.add_argument("--json", action="store_true")

    queue = sub.add_parser("queue", help="list lanes that are waiting")
    queue.add_argument("--check", action="store_true")
    queue.add_argument("--json", action="store_true")

    passed = sub.add_parser("pass-set", help="emit the passed commit set")
    passed.add_argument("lane_id")
    passed.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build()
    args = parser.parse_args(argv)
    root = _root(args.root)
    try:
        if args.command == "new":
            repos = collect_repos(args.repo)
            cmd_new(
                root,
                args.lane_id,
                title=args.title,
                brief=args.brief,
                repos=repos,
                max_rounds=args.max_rounds,
                config=args.config,
                pins=args.pin,
            )
        elif args.command == "run":
            cmd_run(root, args.lane_id)
        elif args.command == "next-round":
            cmd_next_round(root, args.lane_id, brief=args.brief, start=args.start)
        elif args.command == "resolve":
            cmd_resolve(
                root,
                args.lane_id,
                attempt=args.attempt,
                kind=args.kind,
                operator=args.operator,
                reason=args.reason,
                evidence=args.evidence,
                code=args.code,
            )
        elif args.command == "confirm-ended":
            cmd_confirm(root, args.lane_id, attempt=args.attempt, operator=args.operator, how=args.how)
        elif args.command == "abandon":
            cmd_abandon(root, args.lane_id, operator=args.operator, reason=args.reason)
        elif args.command == "status":
            view = cmd_status(root, args.lane_id)
            print(dumps(view) if args.json else format_status(view), end="" if args.json else "\n")
        elif args.command == "queue":
            rows, code = cmd_queue(root)
            print(dumps(rows) if args.json else _format_queue(rows), end="" if args.json else "\n")
            if args.check and code:
                return code
        elif args.command == "pass-set":
            print(dumps(cmd_pass_set(root, args.lane_id)), end="")
    except LaneError as exc:
        print(exc, file=sys.stderr)
        return exc.exit_code
    return 0


def _format_queue(rows: list[dict]) -> str:
    if not rows:
        return "queue: empty"
    lines = []
    for row in rows:
        needs = row.get("needs") or "-"
        why = "; ".join(row.get("why_waiting") or [])
        lines.append(f"{row['id']} state={row['state']} round={row['round']} budget={row['budget']} needs={needs} {why}")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
