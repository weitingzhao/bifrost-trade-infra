"""Collector-mode credentials and local paths (R5:5.5-12 S1-5).

Shared by dispatch-codex.py, dispatch-claude.py, register-claude-work.py and
collector_work.py. Nothing here talks to the platform.

Collector mode is on only when a collector token is configured:
PLATFORM_COLLECTOR_TOKEN, else the first line of
~/.config/bifrost/collector.token. Without one every script keeps its earlier
behaviour exactly. BIFROST_HOME_OVERRIDE replaces the home directory (tests).
"""

from __future__ import annotations

import os
import re
import socket
from pathlib import Path

# The platform's shapes: agentthreads idRe and hostRe, store identityShape.
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
HOST_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
LAUNCH_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
VENDORS = ("claude", "cursor", "codex")


def home() -> Path:
    return Path(os.environ.get("BIFROST_HOME_OVERRIDE") or Path.home())


def first_line(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").split("\n")[0].strip()
    except (OSError, UnicodeDecodeError):
        return ""


def collector_token() -> str:
    """The collector token, or '' when collector mode is off."""
    env = os.environ.get("PLATFORM_COLLECTOR_TOKEN", "").strip()
    if env:
        return env
    return first_line(home() / ".config" / "bifrost" / "collector.token")


def host_id() -> tuple[str, str]:
    """This host's id and its source (env, file, hostname), as the hooks read it."""
    env = os.environ.get("BIFROST_HOST_ID", "").strip()
    if env and HOST_RE.fullmatch(env):
        return env, "env"
    value = first_line(home() / ".config" / "bifrost" / "host-id")
    if value and HOST_RE.fullmatch(value):
        return value, "file"
    short = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname().split(".")[0] or "unknown")[:64]
    return short, "hostname"


def external_work_root() -> Path:
    return home() / ".cache" / "bifrost" / "external-work"


def launch_dir(launch_id: str) -> Path:
    if not LAUNCH_RE.fullmatch(launch_id or ""):
        raise ValueError("invalid launch id")
    return external_work_root() / "launches" / launch_id


def epoch_dir(vendor: str, session: str, epoch: int) -> Path:
    """The writer's own directory for one (vendor, session, epoch): state.json and wrapper.lock."""
    if vendor not in VENDORS or not ID_RE.fullmatch(session or "") or not (isinstance(epoch, int) and epoch >= 1):
        raise ValueError("invalid session identity")
    return external_work_root() / vendor / session / str(epoch)
