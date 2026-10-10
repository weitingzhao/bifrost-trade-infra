#!/usr/bin/env python3
"""Install the Cursor MCP servers from mcp.servers.json into ~/.cursor/mcp.json.

The template spells server paths as ${workspaceFolder}/...; a user-level mcp.json has no
workspace of its own, so this renders them to the workspace root. The root is
$BIFROST_WORKSPACE, else the directory holding bifrost-trade-infra. Servers named in the
template replace same-named entries; other entries are kept. The previous file is backed up
as mcp.json.bak-<timestamp> and the result is written with mode 0600.

The template carries no token values and this script never reads the token file: each
server pins PLATFORM_TOKEN_ENV_KEY and reads that key itself at start.

    python3 bifrost-trade-infra/agent-config/cursor/install-mcp.py
    python3 bifrost-trade-infra/agent-config/cursor/install-mcp.py --dry-run
    python3 bifrost-trade-infra/agent-config/cursor/install-mcp.py --target /tmp/mcp.json

Cursor reads the file at start; reload MCP (or restart Cursor) after installing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "mcp.servers.json"
PLACEHOLDER = "${workspaceFolder}"
MARKER = Path("bifrost-platform") / "config" / "ops-context.yaml"

sys.path.insert(0, str(HERE.parent / "scripts"))
from check_mcp_cutover import check_servers  # noqa: E402


def workspace_root() -> Path:
    env = os.environ.get("BIFROST_WORKSPACE", "").strip()
    root = Path(env).expanduser().resolve() if env else HERE.parents[2]
    if not (root / MARKER).is_file():
        source = "BIFROST_WORKSPACE" if env else "the directory holding bifrost-trade-infra"
        sys.exit(f"{root} ({source}) is not a Bifrost workspace: {MARKER} is missing")
    return root


def render(template: dict, root: Path) -> dict:
    servers = json.loads(json.dumps(template["mcpServers"]).replace(PLACEHOLDER, str(root)))
    for name, spec in servers.items():
        for arg in spec.get("args") or []:
            if arg.endswith(".ts") and not Path(arg).is_file():
                sys.exit(f"{name}: {arg} does not exist")
    return servers


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--target", default=str(Path.home() / ".cursor" / "mcp.json"))
    ap.add_argument("--dry-run", action="store_true", help="print the merged file instead of writing it")
    args = ap.parse_args()

    root = workspace_root()
    servers = render(json.loads(TEMPLATE.read_text()), root)
    target = Path(args.target).expanduser()
    current = json.loads(target.read_text()) if target.is_file() else {}
    merged = dict(current)
    merged["mcpServers"] = {**(current.get("mcpServers") or {}), **servers}

    errors = check_servers(target, "cursor", merged)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    text = json.dumps(merged, indent=2, ensure_ascii=False) + "\n"
    if args.dry_run:
        print(text, end="")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        backup = target.with_name(f"{target.name}.bak-{time.strftime('%Y%m%dT%H%M%S')}")
        shutil.copy2(target, backup)
        os.chmod(backup, 0o600)
        print(f"backup: {backup}")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(target, 0o600)
    print(f"wrote {target}: {', '.join(sorted(servers))} (workspace {root})")
    print("Reload MCP in Cursor (or restart it) for the change to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
