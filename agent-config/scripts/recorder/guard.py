"""The release path does not read this recorder.

The scan is a text search of the four directories the design names.
It catches a direct mention. It does not catch a rename, a symlink,
or a person who looked at the board and then merged.
"""

from __future__ import annotations

from pathlib import Path

FORBIDDEN = (
    "agent-work/events",
    "agent-work/status",
    "recorder/",
    "rec.py",
    "board2",
    "status.publish",
    "agent/progress",
)

GUARDED = (
    "scripts/release",
    "k8s/cicd",
    "agent-config/scripts/git-hooks",
    "agent-config/scripts/agent-guard",
)


def scan(root: Path) -> list[str]:
    """Return ``path: needle`` for every guarded file that contains a needle."""
    hits = []
    root = Path(root)
    for relative in GUARDED:
        base = root / relative
        if not base.exists():
            continue
        files = [base] if base.is_file() else sorted(path for path in base.rglob("*") if path.is_file())
        for path in files:
            try:
                data = path.read_bytes()
            except OSError:
                continue
            for needle in FORBIDDEN:
                if needle.encode("utf-8") in data:
                    hits.append(f"{path.relative_to(root)}: {needle}")
    return hits
