#!/usr/bin/env python3
"""One-shot: copy ``ib:`` host/secondary from Legacy engine overlay into bifrost-trade-infra/.env.

Used by sync_prod_config.sh / sync_dev_config.sh when IB_HOST is still the template default.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def _extract_ib_block(text: str) -> str | None:
    m = re.search(r"^ib:\n(?:(?:  .+|\s*)\n)+", text, re.MULTILINE)
    return m.group(0).rstrip() + "\n" if m else None


def _parse_scalar(block: str, *path: str) -> str:
    """Read indented YAML scalars without PyYAML (host.ip, secondary.ip, …)."""
    lines = block.splitlines()
    want_depth = len(path)
    for i, line in enumerate(lines):
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        depth = indent // 2
        key = line.strip().split(":", 1)[0].strip()
        if depth == want_depth - 1 and key == path[-1]:
            if ":" not in line:
                continue
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            if want_depth == 1:
                return val
            # walk back for nested path — simpler: regex per path
    return ""


def _rg(block: str, pattern: str) -> str:
    m = re.search(pattern, block, re.MULTILINE)
    return (m.group(1).strip().strip('"').strip("'") if m else "")


def parse_legacy_ib(block: str) -> dict[str, str]:
    return {
        "IB_HOST": _rg(block, r"^\s{2}host:\s*\n\s{4}ip:\s*[\"']?([^\"'\n#]+)"),
        "IB_PORT_TYPE": _rg(block, r"^\s{4}port_type:\s*[\"']?([^\"'\n#]+)"),
        "IB_SECONDARY_HOST": _rg(block, r"^\s{2}secondary:\s*\n\s{4}ip:\s*[\"']?([^\"'\n#]+)"),
        "IB_SECONDARY_PORT_TYPE": _rg(
            block, r"^\s{2}secondary:\s*\n(?:\s{4}.+\n)*?\s{4}port_type:\s*[\"']?([^\"'\n#]+)"
        ),
        "IB_CLIENT_ID_DAEMON": _rg(block, r"^\s{6}daemon:\s*(\d+)"),
        "IB_CLIENT_ID_LISTENER": _rg(block, r"^\s{6}listener:\s*(\d+)"),
        "IB_CLIENT_ID_OPERATOR": _rg(block, r"^\s{6}operator:\s*(\d+)"),
        "IB_CLIENT_ID_WORKER": _rg(block, r"^\s{6}worker_market:\s*(\d+)"),
        "IB_CLIENT_ID_INGESTOR": _rg(block, r"^\s{6}ingestor:\s*(\d+)"),
        "IB_CLIENT_ID_ACCOUNT": _rg(block, r"^\s{6}account_agent:\s*(\d+)"),
        "IB_SECONDARY_CLIENT_ID_LISTENER": _rg(
            block,
            r"^\s{2}secondary:\s*\n(?:\s{4}.+\n)*?\s{4}client_id:\s*\n\s{6}listener:\s*(\d+)",
        ),
        "IB_SECONDARY_CLIENT_ID_OPERATOR": _rg(
            block,
            r"^\s{2}secondary:\s*\n(?:\s{4}.+\n)*?\s{4}client_id:\s*\n(?:\s{6}.+\n)*?\s{6}operator:\s*(\d+)",
        ),
        "IB_SECONDARY_CLIENT_ID_ACCOUNT": _rg(
            block,
            r"^\s{2}secondary:\s*\n(?:\s{4}.+\n)*?\s{4}client_id:\s*\n(?:\s{6}.+\n)*?\s{6}account_agent:\s*(\d+)",
        ),
    }


def _env_get(env_text: str, key: str) -> str:
    for line in env_text.splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def _env_set(env_text: str, key: str, value: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"^{re.escape(key)}=", env_text, re.MULTILINE):
        return re.sub(rf"^{re.escape(key)}=.*$", line, env_text, count=1, flags=re.MULTILINE)
    return env_text.rstrip() + "\n" + line + "\n"


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: import_legacy_ib_env.py <env-file> <legacy-yaml> <default-host-to-replace>", file=sys.stderr)
        return 2
    env_path = Path(sys.argv[1])
    legacy_path = Path(sys.argv[2])
    default_host = sys.argv[3].strip()

    if not legacy_path.is_file():
        return 0
    block = _extract_ib_block(legacy_path.read_text(encoding="utf-8"))
    if not block:
        print(f"No ib: block in {legacy_path}", file=sys.stderr)
        return 1

    parsed = parse_legacy_ib(block)
    env_text = env_path.read_text(encoding="utf-8")
    current_host = _env_get(env_text, "IB_HOST")
    if current_host and current_host != default_host:
        return 0

    changed = 0
    for key, val in parsed.items():
        if not val:
            continue
        old = _env_get(env_text, key)
        if old == val:
            continue
        env_text = _env_set(env_text, key, val)
        changed += 1

    if changed:
        env_path.write_text(env_text, encoding="utf-8")
        host = parsed.get("IB_HOST") or "?"
        sec = parsed.get("IB_SECONDARY_HOST") or "—"
        print(f"Imported IB settings from {legacy_path} → {env_path} (host={host}, secondary={sec})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
