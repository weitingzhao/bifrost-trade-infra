#!/usr/bin/env python3
"""Install the Cursor hooks from hooks.json into the user-level ~/.cursor/hooks.json.

Cursor refuses a project hooks.json reached through a symlink below the workspace root
("Refusing to load Project hooks.json via symlink below workspace root"), and the
workspace's .cursor is such a symlink, so the project file is never loaded. The
user-level file is. A user-level hook runs from ~/.cursor, not from the workspace, so
this renders every relative script path to the workspace root and `node` to an absolute
path (Cursor started from the Dock may not have Homebrew on PATH).

The root is $BIFROST_WORKSPACE, else the directory holding bifrost-trade-infra.
Entries this script manages are the ones that run a script named in the template; they
are replaced on every run. Any other entry already in the target is kept and listed.
The previous file is backed up as hooks.json.bak-<timestamp>. Re-run after the template
changes (for example when new hooks land in hooks.json).

    python3 bifrost-trade-infra/agent-config/cursor/install-hooks.py
    python3 bifrost-trade-infra/agent-config/cursor/install-hooks.py --dry-run
    python3 bifrost-trade-infra/agent-config/cursor/install-hooks.py --check

--check writes nothing: exit 0 when the target carries exactly the rendered entries,
1 when it is missing or differs. Cursor reloads hooks.json on change; if a hook does
not fire, reload the window.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "hooks.json"
MARKER = Path("bifrost-platform") / "config" / "ops-context.yaml"
NODE_FALLBACKS = ("/opt/homebrew/bin/node", "/usr/local/bin/node")


def workspace_root() -> Path:
    env = os.environ.get("BIFROST_WORKSPACE", "").strip()
    root = Path(env).expanduser().resolve() if env else HERE.parents[2]
    if not (root / MARKER).is_file():
        source = "BIFROST_WORKSPACE" if env else "the directory holding bifrost-trade-infra"
        sys.exit(f"{root} ({source}) is not a Bifrost workspace: {MARKER} is missing")
    return root


def node_path() -> str:
    found = shutil.which("node")
    for cand in ([found] if found else []) + list(NODE_FALLBACKS):
        if cand and os.access(cand, os.X_OK):
            return cand
    sys.exit("node not found on PATH or in " + ", ".join(NODE_FALLBACKS))


def script_args(command: str) -> list[str]:
    """Relative script paths a template command runs (the managed-entry key)."""
    return [t for t in shlex.split(command)[1:] if t.endswith(".js") and not os.path.isabs(t)]


def render_command(command: str, root: Path, node: str) -> str:
    tokens = shlex.split(command)
    if tokens and tokens[0] == "node":
        tokens[0] = node
    out = []
    for tok in tokens:
        if tok in script_args(command):
            p = root / os.path.normpath(tok)
            if not p.is_file():
                sys.exit(f"{command!r}: {p} does not exist")
            tok = str(p)
        out.append(tok)
    return shlex.join(out)


def render(template: dict, root: Path, node: str) -> tuple[dict[str, list[dict]], set[str]]:
    hooks: dict[str, list[dict]] = {}
    keys: set[str] = set()
    for event, entries in (template.get("hooks") or {}).items():
        for entry in entries:
            keys.update(os.path.normpath(a) for a in script_args(entry["command"]))
            hooks.setdefault(event, []).append({**entry, "command": render_command(entry["command"], root, node)})
    return hooks, keys


def is_managed(entry: dict, keys: set[str]) -> bool:
    cmd = entry.get("command", "")
    return any(f"/{k}" in cmd or f" {k}" in cmd for k in keys)


def merge(current: dict, rendered: dict[str, list[dict]], keys: set[str]) -> tuple[dict, list[str]]:
    kept: list[str] = []
    merged_hooks: dict[str, list[dict]] = {}
    for event, entries in (current.get("hooks") or {}).items():
        for entry in entries:
            if not is_managed(entry, keys):
                merged_hooks.setdefault(event, []).append(entry)
                kept.append(f"{event}: {entry.get('command', '')}")
    for event, entries in rendered.items():
        merged_hooks.setdefault(event, []).extend(entries)
    merged = {**current, "version": current.get("version", 1), "hooks": merged_hooks}
    return merged, kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", default=str(Path.home() / ".cursor" / "hooks.json"))
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print the merged file instead of writing it")
    mode.add_argument("--check", action="store_true", help="exit 1 if the target is missing or out of date")
    args = ap.parse_args()

    root = workspace_root()
    rendered, keys = render(json.loads(TEMPLATE.read_text()), root, node_path())
    target = Path(args.target).expanduser()
    if target.is_symlink():
        print(f"{target} is a symlink; Cursor may refuse it. Remove it and re-run.", file=sys.stderr)
        return 1
    current = json.loads(target.read_text()) if target.is_file() else {}
    merged, kept = merge(current, rendered, keys)
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not target.is_file():
            print(f"{target} is missing: run python3 {HERE / 'install-hooks.py'}")
            return 1
        if merged != current:
            print(f"{target} differs from {TEMPLATE}: run python3 {HERE / 'install-hooks.py'}")
            return 1
        print(f"{target} matches {TEMPLATE}")
        return 0
    if args.dry_run:
        print(text, end="")
        return 0

    if target.is_file() and merged == current:
        print(f"{target} already up to date (workspace {root})")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        backup = target.with_name(f"{target.name}.bak-{time.strftime('%Y%m%dT%H%M%S')}")
        shutil.copy2(target, backup)
        print(f"backup: {backup}")
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, target)
    print(f"wrote {target}: {', '.join(f'{e} ({len(v)})' for e, v in rendered.items())} (workspace {root})")
    for line in kept:
        print(f"kept, not managed here: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
