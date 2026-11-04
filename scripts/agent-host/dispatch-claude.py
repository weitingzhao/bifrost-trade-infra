#!/usr/bin/env python3
"""Launch Claude Code as a managed session (R5:5.5-12 S1-5, design §2.2).

    dispatch-claude.py --root R5 --node R5:5.5-12 --plan-version 7 \\
        --acceptance-ref S1-5 --task "..." --repo bifrost-trade-infra \\
        --branch r5/x --estimate-minutes 30 60 -- [claude arguments]
    dispatch-claude.py --unlinked -- [claude arguments]

It writes a launch record and, for a linked launch, the work description,
exports the launch's environment and replaces itself with `claude` (exec:
the CLI keeps this process id, so the record's cli_pid is the CLI's). The
hooks then append every (session, epoch) the CLI opens to the record's
`sessions`, and run the work's single writer (register-claude-work.py event)
for that launch only. A launch whose `sessions` stays empty is a gap the audit
reports (collector-audit.js), not a launch that never ran.

The description is complete or the launch does not happen: every field is
given on the command line, nothing is guessed. --unlinked gives no plan
context and writes no description: a managed sample of the unlinked path.

Sidebar (§2.2 step 4, §12 D6): a process inside a running Claude session has
CLAUDE_CODE_SESSION_ID; the CLI rewrites it for its own children. So when it is
set here, any CLAUDE_CODE_HOST_SESSION_ID was inherited from that session and
belongs to it, and the launch takes launch-<launch_id> instead. Only without it
is a CLAUDE_CODE_HOST_SESSION_ID the desktop's own for this process, and kept.

Nothing here talks to the platform; arguments for claude are never recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location("collector_auth", Path(__file__).with_name("collector_auth.py"))
auth = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auth)

LINKED_FIELDS = ("root", "node", "plan_version", "task", "repo", "branch", "acceptance_ref", "estimate_minutes")


def write_private(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def description_of(options) -> bytes:
    missing = [name for name in LINKED_FIELDS if not getattr(options, name)]
    if missing:
        raise ValueError("the work description is incomplete; missing: " + ", ".join("--" + m.replace("_", "-") for m in missing))
    low, high = options.estimate_minutes
    if not (0 < low <= high):
        raise ValueError("--estimate-minutes needs 0 < LOW <= HIGH")
    body = {
        "v": 1,
        "kind": "agentrt.external_work/v1",
        "task": options.task,
        "executor": "claude",
        "provider": "anthropic",
        "repo": options.repo,
        "branch": options.branch,
        "acceptance_refs": options.acceptance_ref,
        "estimate_minutes": [low, high],
    }
    for name in ("task", "repo", "branch", "root", "node", "plan_version"):
        if not str(getattr(options, name)).strip():
            raise ValueError(f"--{name.replace('_', '-')} is empty")
    return json.dumps(body, ensure_ascii=False, sort_keys=True).encode()


def sidebar_for(env, launch_id):
    """The sidebar id this launch's sessions report, and where it came from (D6)."""
    inherited = env.get("CLAUDE_CODE_HOST_SESSION_ID", "").strip()
    parent = env.get("CLAUDE_CODE_SESSION_ID", "").strip()
    if inherited and not parent and auth.ID_RE.fullmatch(inherited):
        return inherited, "desktop", ""
    return "launch-" + launch_id, "launch", parent


def prepare(options, env, pid: int):
    """Write the launch record; return the environment for claude. Raises before writing anything when incomplete."""
    unlinked_extra = [name for name in LINKED_FIELDS if getattr(options, name)]
    if options.unlinked and unlinked_extra:
        raise ValueError("--unlinked takes no plan context; drop: " + ", ".join("--" + m.replace("_", "-") for m in unlinked_extra))
    description = None if options.unlinked else description_of(options)
    launch_id = str(uuid.uuid4())
    directory = auth.launch_dir(launch_id)
    directory.mkdir(parents=True, mode=0o700)
    host, source = auth.host_id()
    sidebar, sidebar_source, parent = sidebar_for(env, launch_id)
    record = {
        "v": 1,
        "launch_id": launch_id,
        "mode": "unlinked" if options.unlinked else "linked",
        "vendor": "claude",
        "host": host,
        "host_id_source": source,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "cli_pid": pid,
        "sidebar": sidebar,
        "sidebar_source": sidebar_source,
        "sessions": [],
    }
    if parent and auth.ID_RE.fullmatch(parent):
        record["parent_session"] = parent
    child = dict(env)
    child["BIFROST_LAUNCH_ID"] = launch_id
    child["CLAUDE_CODE_HOST_SESSION_ID"] = sidebar
    for name in ("BIFROST_PLAN_ROOT", "BIFROST_PLAN_NODE", "BIFROST_WORK_DESCRIPTION"):
        child.pop(name, None)
    if description is not None:
        write_private(directory / "description.json", description)
        record.update(
            root=options.root,
            node=options.node,
            plan_version=options.plan_version,
            description_digest="sha256:" + hashlib.sha256(description).hexdigest(),
        )
        child.update(
            BIFROST_PLAN_ROOT=options.root,
            BIFROST_PLAN_NODE=options.node,
            BIFROST_WORK_DESCRIPTION=str(directory / "description.json"),
        )
    write_private(directory / "launch.json", json.dumps(record, ensure_ascii=False).encode())
    return launch_id, child


def parser():
    p = argparse.ArgumentParser(prog="dispatch-claude.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    p.add_argument("--unlinked", action="store_true")
    for name in ("root", "node", "plan-version", "task", "repo", "branch"):
        p.add_argument("--" + name, default="")
    p.add_argument("--acceptance-ref", action="append", default=[])
    p.add_argument("--estimate-minutes", nargs=2, type=int, default=None)
    p.add_argument("--claude", default=os.environ.get("BIFROST_CLAUDE_BIN", "claude"), help="the claude executable")
    p.add_argument("args", nargs=argparse.REMAINDER)
    return p


def main(argv=None) -> int:
    options = parser().parse_args(argv)
    args = options.args[1:] if options.args[:1] == ["--"] else options.args
    try:
        launch_id, env = prepare(options, os.environ, os.getpid())
    except (ValueError, OSError) as exc:
        print(f"dispatch-claude: {exc}", file=sys.stderr)
        return 2
    if not auth.collector_token() or os.environ.get("BIFROST_HEARTBEAT") == "off":
        print("dispatch-claude: collector mode is off here: this launch's sessions are not recorded (the audit will show the gap)", file=sys.stderr)
    print(f"dispatch-claude: launch {launch_id}", file=sys.stderr)
    try:
        os.execvpe(options.claude, [options.claude, *args], env)
    except OSError as exc:
        print(f"dispatch-claude: cannot start {options.claude}: {exc}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    sys.exit(main())
