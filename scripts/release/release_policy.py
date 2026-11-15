#!/usr/bin/env python3
"""Render the release policy the Owner signs (W-42, card 2 = B).

platform-api is the only judge of a policy: it verifies the signature against
its compiled-in Owner key and evaluates every release. This script only builds
the canonical text that `release.sh policy sign` hands to ssh-keygen, from
agent-config/release-policy/template.json and paths.json.

  release_policy.py render --template t.json --paths p.json [--days N] [--now ISO] --out policy.yaml
  release_policy.py card --sha256 <hex>     the command of the card that signs the staged text

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


# The command of the owner_run_command card that signs a staged candidate
# (TD-576, Owner 2026-11-15). The Owner approves the card with his one-time
# code; owner-exec runs this as cluster administrator. It names the text only
# by its sha256: the text lists the D10 paths, and platform-api classifies a
# command whose words name one as tier X. One line, no background process,
# prints no secret, safe to run again.
CARD_COMMAND = (
    "set -eu; want={sha}; "
    "kubectl -n cicd get configmap bifrost-release-policy -o jsonpath='{{.data.candidate\\.yaml}}' > policy.yaml; "
    'echo "$want  policy.yaml" | sha256sum -c - >/dev/null; '
    "umask 077; "
    "kubectl -n bifrost-owner-exec get secret release-policy-signer -o jsonpath='{{.data.key}}' | base64 -d > key; "
    "ssh-keygen -Y sign -f key -n bifrost-release-policy policy.yaml >/dev/null 2>&1; rm -f key; "
    "ssh-keygen -Y check-novalidate -n bifrost-release-policy -s policy.yaml.sig < policy.yaml >/dev/null; "
    "python3 -c 'import json; print(json.dumps({{\"data\":{{\"policy.yaml\":open(\"policy.yaml\").read(),"
    "\"policy.sig\":open(\"policy.yaml.sig\").read(),\"candidate.yaml\":None}}}}))' > patch.json; "
    "kubectl -n cicd patch configmap bifrost-release-policy --type merge --patch-file patch.json >/dev/null; "
    'echo "signed and installed: policy.yaml sha256 $want"'
)


def card_command(sha: str) -> str:
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("--sha256 must be 64 lowercase hex characters")
    return CARD_COMMAND.format(sha=sha)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("--template", required=True)
    r.add_argument("--paths", required=True)
    r.add_argument("--days", type=int)
    r.add_argument("--now")
    r.add_argument("--out", required=True)
    c = sub.add_parser("card")
    c.add_argument("--sha256", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "card":
        try:
            print(card_command(args.sha256))
        except ValueError as exc:
            print(f"release_policy: {exc}", file=sys.stderr)
            return 2
        return 0
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
