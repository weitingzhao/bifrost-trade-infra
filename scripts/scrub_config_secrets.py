#!/usr/bin/env python3
"""Empty tracked YAML secret fields (passwords, tokens, api_key). Never prints values."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "config/config.dev.yaml",
    ROOT / "config/config.stg.yaml",
    ROOT / "config/config.prod.yaml",
    ROOT / "k8s/overlays/dev/config/config.dev.yaml",
    ROOT / "k8s/overlays/stg/config/config.stg.yaml",
    ROOT / "k8s/overlays/prod/config/config.prod.yaml",
]


def scrub_text(text: str) -> tuple[str, list[str]]:
    changed: list[str] = []
    out, n_pw = re.subn(
        r"^([ \t]*(?:password|fdw_password|api_key):)[ \t]*.*$",
        r'\1 ""',
        text,
        flags=re.MULTILINE,
    )
    if n_pw:
        changed.append(f"password/api_key_lines={n_pw}")
    out2, n_tok = re.subn(
        r"^([ \t]*tokens:)[ \t]*\n(?:[ \t]+-[ \t]+.+\n(?:[ \t]{4,}.+\n)*)+",
        r"\1 []\n",
        out,
        flags=re.MULTILINE,
    )
    if n_tok:
        changed.append(f"token_blocks={n_tok}")
    return out2, changed


def main() -> int:
    for path in FILES:
        if not path.is_file():
            print(f"SKIP missing {path.relative_to(ROOT)}")
            continue
        raw = path.read_text(encoding="utf-8")
        text, changed = scrub_text(raw)
        if not changed or text == raw:
            print(f"OK already empty {path.relative_to(ROOT)}")
            continue
        path.write_text(text, encoding="utf-8")
        print(f"Scrubbed {path.relative_to(ROOT)} {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
