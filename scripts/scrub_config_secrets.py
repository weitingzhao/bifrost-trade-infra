#!/usr/bin/env python3
"""Empty tracked YAML secret fields (passwords, tokens, api_key). Never prints values.

  scrub_config_secrets.py                  empty the fields in the working tree
  scrub_config_secrets.py --check          exit 1 if any field holds a value
  scrub_config_secrets.py --check --staged same, on the staged copies (pre-commit)

TD-280: a sync script once wrote the redis-ib trade-prod password into
config/config.dev.yaml and eight commits carried it to the public repo. --check
reports file, line and key only.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "config/config.dev.yaml",
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


# Keys that hold a credential. token_env and the like name an env var and end
# in something else, so they are not matched.
SECRET_KEY = re.compile(
    r"^[ \t]*-?[ \t]*([A-Za-z_]*(?:password|token|secret)|api_key|fdw_password):[ \t]*(.*?)[ \t]*$",
    re.IGNORECASE,
)
TOKENS_LIST = re.compile(r"^[ \t]*tokens:[ \t]*$")
LIST_ITEM = re.compile(r"^[ \t]+-[ \t]+\S")
ENV_REF = re.compile(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?$")


def _is_empty(value: str) -> bool:
    value = value.split(" #", 1)[0].strip()
    if value in ("", '""', "''", "null", "~", "[]", "{}"):
        return True
    return bool(ENV_REF.match(value.strip("\"'")))


def findings(text: str) -> list[tuple[int, str]]:
    """(line number, key) for every secret field that holds a value."""
    out: list[tuple[int, str]] = []
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        m = SECRET_KEY.match(line)
        if m and not _is_empty(m.group(2)):
            out.append((i, m.group(1)))
        if TOKENS_LIST.match(line) and i < len(lines) and LIST_ITEM.match(lines[i]):
            out.append((i, "tokens"))
    return out


def _staged(rel: str) -> str | None:
    r = subprocess.run(["git", "-C", str(ROOT), "show", f":{rel}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def check(staged: bool) -> int:
    bad = 0
    for path in FILES:
        rel = str(path.relative_to(ROOT))
        if staged:
            text = _staged(rel)
        else:
            text = path.read_text(encoding="utf-8") if path.is_file() else None
        if text is None:
            continue
        for line, key in findings(text):
            bad += 1
            print(f"FAIL {rel}:{line} {key} holds a value; tracked config must leave it empty", file=sys.stderr)
    if bad:
        print("Run scripts/scrub_config_secrets.py, give the process the value through its environment, "
              "and keep the real value out of git (the repo is public).", file=sys.stderr)
        return 1
    print(f"ok: no secret values in {len(FILES)} tracked config files" + (" (staged)" if staged else ""))
    return 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return check("--staged" in sys.argv[1:])
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
