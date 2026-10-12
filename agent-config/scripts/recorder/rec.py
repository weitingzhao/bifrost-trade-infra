"""Local recorder CLI: bookkeeping, process wrapper, process observation and fold."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from commands import (
    RecorderError,
    close_work,
    declare_step,
    finish_step,
    open_work,
    owner_close,
    owner_open,
    owner_ready,
    start_step,
    withdraw_step,
    write_note,
)
from fsutil import canonical_json


def _root(value: str | None) -> Path:
    if value:
        return Path(value)
    return Path.home() / "agent-work" / "events"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rec.py")
    parser.add_argument("--root", default=None)
    sub = parser.add_subparsers(dest="subcommand", required=True)

    folded = sub.add_parser("fold")
    folded.add_argument("--now", type=float)
    sub.add_parser("observe")
    run = sub.add_parser("run")
    run.add_argument("--work", required=True)
    run.add_argument("--name", required=True)
    run.add_argument("--kind", required=True)
    run.add_argument("--who", required=True)
    run.add_argument("--after")
    run.add_argument("--round", type=float)
    run.add_argument("--replaces")
    run.add_argument("--text")
    run.add_argument("--quote-first-line", type=Path)
    run.add_argument("child_command", nargs=argparse.REMAINDER)

    opened = sub.add_parser("open")
    opened.add_argument("--work", required=True)
    opened.add_argument("--title", required=True)
    opened.add_argument("--goal")
    opened.add_argument("--work-ref")

    closed = sub.add_parser("close")
    closed.add_argument("--work", required=True)
    closed.add_argument("--claim", required=True, choices=("landed", "stopped", "dropped"))

    declared = sub.add_parser("declare")
    declared.add_argument("--work", required=True)
    declared.add_argument("--name", required=True)
    declared.add_argument("--kind", required=True)
    declared.add_argument("--who", required=True)
    declared.add_argument("--watch", required=True, choices=("process", "none", "record"))
    declared.add_argument("--cluster")
    declared.add_argument("--namespace")
    declared.add_argument("--run-name")
    declared.add_argument("--after")
    declared.add_argument("--waiting-on", action="append")
    declared.add_argument("--round", type=float)
    declared.add_argument("--replaces")
    declared.add_argument("--text")

    withdrawn = sub.add_parser("withdraw")
    withdrawn.add_argument("--work", required=True)
    withdrawn.add_argument("--step", required=True)
    withdrawn.add_argument("--text")

    started = sub.add_parser("start")
    started.add_argument("--work", required=True)
    started.add_argument("--step", required=True)

    finished = sub.add_parser("finish")
    finished.add_argument("--work", required=True)
    finished.add_argument("--step", required=True)
    finished.add_argument("--reported", required=True, choices=("finished", "failed"))
    finished.add_argument("--quote")

    noted = sub.add_parser("note")
    noted.add_argument("--work", required=True)
    noted.add_argument("--text", required=True)
    noted.add_argument("--step")

    owner = sub.add_parser("owner-open")
    owner.add_argument("--work", required=True)
    owner.add_argument("--title", required=True)
    owner.add_argument("--can-act", required=True, choices=("yes", "not_yet"))
    owner.add_argument("--where", choices=("thread", "console", "terminal"))
    owner.add_argument("--reply")
    owner.add_argument("--no-reply", action="store_true")
    owner.add_argument("--reply-words")
    owner.add_argument("--command", action="append")
    owner.add_argument("--deadline", type=float)
    owner.add_argument("--no-deadline", action="store_true")
    owner.add_argument("--blocks-nothing", action="store_true")
    owner.add_argument("--blocks-text")
    owner.add_argument("--after-text")
    owner.add_argument("--not-before-text")
    owner.add_argument("--advice")
    owner.add_argument("--after")
    owner.add_argument("--replaces")

    ready = sub.add_parser("owner-ready")
    ready.add_argument("--work", required=True)
    ready.add_argument("--wait", required=True)

    shut = sub.add_parser("owner-close")
    shut.add_argument("--work", required=True)
    shut.add_argument("--wait", required=True)
    shut.add_argument("--how", required=True, choices=("done", "withdrawn"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = _root(args.root)
    from runtime import fold_root, observe, run_process
    try:
        if args.subcommand == "fold":
            print(canonical_json(fold_root(root, args.now)))
            return 0
        if args.subcommand == "observe":
            observe(root)
            return 0
        if args.subcommand == "run":
            return run_process(root, args)
        event = _run(root, args)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RecorderError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    print(canonical_json(event))
    return 0


def _run(root: Path, args):
    command = args.subcommand
    if command == "open":
        return open_work(root, args.work, args.title, goal=args.goal, work_ref=args.work_ref)
    if command == "close":
        return close_work(root, args.work, args.claim)
    if command == "declare":
        locator = None
        if args.watch == "record":
            locator = {"cluster": args.cluster or "", "namespace": args.namespace or ""}
            if args.run_name:
                locator["name"] = args.run_name
        return declare_step(
            root,
            args.work,
            name=args.name,
            kind=args.kind,
            who=args.who,
            watch=args.watch,
            locator=locator,
            waiting_on=args.waiting_on,
            after=args.after,
            round=args.round,
            replaces=args.replaces,
            text=args.text,
        )
    if command == "withdraw":
        return withdraw_step(root, args.work, args.step, text=args.text)
    if command == "start":
        return start_step(root, args.work, args.step)
    if command == "finish":
        return finish_step(root, args.work, args.step, args.reported, quote=args.quote)
    if command == "note":
        return write_note(root, args.work, args.text, step_id=args.step)
    if command == "owner-open":
        return owner_open(
            root,
            args.work,
            args.title,
            can_act=args.can_act,
            where=args.where,
            reply=args.reply,
            reply_needed=False if args.no_reply else None,
            reply_words=args.reply_words,
            commands=args.command,
            deadline=args.deadline,
            no_deadline=True if args.no_deadline else None,
            blocks_nothing=True if args.blocks_nothing else None,
            blocks_text=args.blocks_text,
            after_text=args.after_text,
            not_before_text=args.not_before_text,
            advice=args.advice,
            after=args.after,
            replaces=args.replaces,
        )
    if command == "owner-ready":
        return owner_ready(root, args.work, args.wait)
    if command == "owner-close":
        return owner_close(root, args.work, args.wait, args.how)
    raise RecorderError("unknown command")


if __name__ == "__main__":
    sys.exit(main())
