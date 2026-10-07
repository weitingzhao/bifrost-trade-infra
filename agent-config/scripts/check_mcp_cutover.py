#!/usr/bin/env python3
"""MCP cutover ratchet.

- Only the server named bifrost-local may point at 127.0.0.1 / localhost.
- bifrost-approve is registered only on the Claude side (.mcp.json).
- Token env values stay interpolations. This script never prints those values.

    python3 agent-config/scripts/check_mcp_cutover.py
    python3 agent-config/scripts/check_mcp_cutover.py --self-test
    python3 agent-config/scripts/check_mcp_cutover.py --cursor path/to/cursor-mcp-bridges.json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

PROD = "http://192.168.10.100:30876"
LOOPBACK = ("127.0.0.1", "localhost", "[::1]")
AGENT_CONFIG = Path(__file__).resolve().parents[1]


def blob(server: dict) -> str:
    parts: list[str] = []
    command = server.get("command")
    if command is not None:
        parts.append(str(command))
    for arg in server.get("args") or []:
        parts.append(str(arg))
    env = server.get("env") or {}
    if isinstance(env, dict):
        for key, value in env.items():
            parts.append(f"{key}={value}")
    return "\n".join(parts)


def check_servers(path: Path, role: str, data: dict) -> list[str]:
    errors: list[str] = []
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return [f"{path}: mcpServers missing"]
    names = set(servers)
    if role == "claude":
        if "bifrost-approve" not in names:
            errors.append(f"{path}: Claude config is missing bifrost-approve")
        if "bifrost-local" not in names:
            errors.append(f"{path}: Claude config is missing bifrost-local")
    elif "bifrost-approve" in names:
        errors.append(f"{path}: bifrost-approve is Claude-only")

    for name, spec in servers.items():
        if not isinstance(spec, dict):
            errors.append(f"{path}: {name} is not an object")
            continue
        text = blob(spec)
        loopback = any(host in text for host in LOOPBACK)
        if loopback and name != "bifrost-local":
            errors.append(f"{path}: {name} points at loopback")
        if name == "bifrost-local" and "127.0.0.1" not in text:
            errors.append(f"{path}: bifrost-local must point at 127.0.0.1")
        env = spec.get("env") or {}
        if not isinstance(env, dict):
            errors.append(f"{path}: {name} env is not an object")
            continue
        url = env.get("PLATFORM_API_URL")
        if isinstance(url, str):
            if name == "bifrost-local":
                if url.rstrip("/") != "http://127.0.0.1:8780":
                    errors.append(f"{path}: bifrost-local PLATFORM_API_URL must be http://127.0.0.1:8780")
            elif url.rstrip("/") != PROD:
                errors.append(f"{path}: {name} PLATFORM_API_URL must be {PROD}")
        for key, value in env.items():
            if not str(key).endswith("_TOKEN"):
                continue
            if not isinstance(value, str) or not value.startswith("${"):
                errors.append(f"{path}: {name} {key} must be an env interpolation, not a literal")
        if name == "bifrost-approve":
            if env.get("PLATFORM_TOKEN_ENV_KEY") != "PLATFORM_ADMIN_TOKEN":
                errors.append(f"{path}: bifrost-approve must pin PLATFORM_TOKEN_ENV_KEY=PLATFORM_ADMIN_TOKEN")
            if env.get("MCP_BRIDGE_FOCUS") != "approve":
                errors.append(f"{path}: bifrost-approve must set MCP_BRIDGE_FOCUS=approve")
    return errors


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def check_paths(pairs: list[tuple[Path, str]]) -> list[str]:
    errors: list[str] = []
    for path, role in pairs:
        if not path.is_file():
            errors.append(f"missing {path}")
            continue
        try:
            data = load(path)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid json ({exc})")
            continue
        errors.extend(check_servers(path, role, data))
    return errors


def default_pairs(extra_cursor: list[Path]) -> list[tuple[Path, str]]:
    pairs = [
        (AGENT_CONFIG / ".mcp.json", "claude"),
        (AGENT_CONFIG / "cursor" / "mcp.servers.json", "cursor"),
    ]
    pairs.extend((path, "cursor") for path in extra_cursor)
    return pairs


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        good_claude = {
            "mcpServers": {
                "bifrost-platform": {
                    "command": "npx",
                    "args": ["tsx", "index.ts"],
                    "env": {
                        "PLATFORM_API_URL": PROD,
                        "PLATFORM_OPERATOR_TOKEN": "${PLATFORM_OPERATOR_TOKEN:-}",
                        "MCP_WRITES": "off",
                    },
                },
                "bifrost-local": {
                    "command": "npx",
                    "args": ["tsx", "index.ts"],
                    "env": {"PLATFORM_API_URL": "http://127.0.0.1:8780"},
                },
                "bifrost-approve": {
                    "command": "npx",
                    "args": ["tsx", "index.ts"],
                    "env": {
                        "PLATFORM_API_URL": PROD,
                        "PLATFORM_ADMIN_TOKEN": "${PLATFORM_ADMIN_TOKEN:-}",
                        "PLATFORM_TOKEN_ENV_KEY": "PLATFORM_ADMIN_TOKEN",
                        "MCP_BRIDGE_FOCUS": "approve",
                    },
                },
            }
        }
        good_cursor = {
            "mcpServers": {
                "bifrost-platform": good_claude["mcpServers"]["bifrost-platform"],
                "bifrost-local": good_claude["mcpServers"]["bifrost-local"],
            }
        }
        claude = root / "claude.json"
        cursor = root / "cursor.json"
        claude.write_text(json.dumps(good_claude))
        cursor.write_text(json.dumps(good_cursor))
        ok = check_paths([(claude, "claude"), (cursor, "cursor")])
        if ok:
            print("self-test failed on the good fixture:", ok)
            return 1

        bad_cursor = json.loads(json.dumps(good_cursor))
        bad_cursor["mcpServers"]["bifrost-approve"] = good_claude["mcpServers"]["bifrost-approve"]
        cursor.write_text(json.dumps(bad_cursor))
        bad = check_paths([(cursor, "cursor")])
        if not any("Claude-only" in item for item in bad):
            print("self-test did not catch bifrost-approve on the cursor side:", bad)
            return 1

        bad_loop = json.loads(json.dumps(good_claude))
        bad_loop["mcpServers"]["bifrost-platform"]["env"]["PLATFORM_API_URL"] = "http://127.0.0.1:8780"
        claude.write_text(json.dumps(bad_loop))
        looped = check_paths([(claude, "claude")])
        if not any("loopback" in item for item in looped):
            print("self-test did not catch loopback on a non-local server:", looped)
            return 1

        leaked = json.loads(json.dumps(good_claude))
        leaked["mcpServers"]["bifrost-approve"]["env"]["PLATFORM_ADMIN_TOKEN"] = "not-an-interpolation"
        claude.write_text(json.dumps(leaked))
        leak = check_paths([(claude, "claude")])
        if not any("interpolation" in item for item in leak):
            print("self-test did not catch a literal token:", leak)
            return 1
    print("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--cursor", action="append", default=[], type=Path, help="extra Cursor template")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    errors = check_paths(default_pairs(args.cursor))
    if errors:
        print(f"mcp cutover check failed ({len(errors)})")
        for item in errors:
            print(f"  - {item}")
        return 1
    print("mcp cutover check ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
