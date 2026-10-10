#!/usr/bin/env python3
"""Render the release policy the Owner signs (W-42, card 2 = B).

platform-api is the only judge of a policy: it verifies the signature against
its compiled-in Owner key and evaluates every release. This script only builds
the canonical text that `release.sh policy sign` hands to ssh-keygen, from
agent-config/release-policy/template.json and paths.json.

  release_policy.py render --template t.json --paths p.json [--days N] [--now ISO] --out policy.yaml

Prints `policy_id <id>`, `signed_at <ts>` and `expires_at <ts>`. The output is
JSON (a subset of YAML) with sorted keys, so the signed bytes are reproducible.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

MAX_DAYS = 366


def parse_now(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc).replace(microsecond=0)
    t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).replace(microsecond=0)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def render(template: dict, paths: dict, days: int | None, now: datetime) -> dict:
    days = int(days if days is not None else template.get("valid_days", 0))
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"valid_days must be 1..{MAX_DAYS}, got {days}")
    if not template.get("allow"):
        raise ValueError("template allows no pipeline")
    if not paths.get("paths"):
        raise ValueError("paths.json has no path rules")
    doc = {k: v for k, v in template.items() if k != "about"}
    doc.update({k: v for k, v in paths.items() if k not in ("about", "version")})
    doc["version"] = 1
    doc["valid_days"] = days
    doc["policy_id"] = "rp-" + now.strftime("%Y%m%d-%H%M")
    doc["signed_at"] = iso(now)
    doc["expires_at"] = iso(now + timedelta(days=days))
    return doc


def canonical(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--template", required=True)
    r.add_argument("--paths", required=True)
    r.add_argument("--days", type=int)
    r.add_argument("--now")
    r.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        with open(args.template, encoding="utf-8") as f:
            template = json.load(f)
        with open(args.paths, encoding="utf-8") as f:
            paths = json.load(f)
        doc = render(template, paths, args.days, parse_now(args.now))
    except (OSError, ValueError) as exc:
        print(f"release_policy: {exc}", file=sys.stderr)
        return 2
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(canonical(doc))
    print(f"policy_id {doc['policy_id']}")
    print(f"signed_at {doc['signed_at']}")
    print(f"expires_at {doc['expires_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
