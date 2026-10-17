#!/usr/bin/env python3
"""read-primaries.py <out-file> <repo>... — writes to out-file, one per line,
the repositories Gitea holds as its own (regular repositories, not pull
mirrors). Only those are copied to GitHub; a pull mirror still has GitHub as
its upstream (CUT-gitea-primary-2026-10-17 step 0e). The answer is read as
JSON, its top-level "mirror" (not one in a fork's parent; review 243 A1), and
the token goes in a request header, never on a command line (review 243 B). A
repository Gitea cannot read, or whose answer does not say, stops the run: the
sync must not guess. Runs in alpine/k8s (python3)."""

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    out, repos = sys.argv[1], sys.argv[2:]
    api = os.environ.get("GITEA_API", "http://gitea.cicd.svc.cluster.local:3000/api/v1").rstrip("/")
    org = os.environ.get("GITEA_ORG", "bifrost")
    token = os.environ.get("GITEA_TOKEN", "")
    if not token:
        print("ERROR: gitea-bootstrap/gitea_admin_token missing: cannot read the repositories", file=sys.stderr)
        return 1
    primaries = []
    for repo in repos:
        req = urllib.request.Request(f"{api}/repos/{org}/{repo}", headers={"Authorization": "token " + token})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                code, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, b""
        except (urllib.error.URLError, OSError) as e:
            print(f"ERROR: repository {org}/{repo}: {e}", file=sys.stderr)
            return 1
        if code != 200:
            print(f"ERROR: repository {org}/{repo} → HTTP {code}", file=sys.stderr)
            return 1
        try:
            doc = json.loads(raw)
        except ValueError:
            doc = None
        mirror = doc.get("mirror") if isinstance(doc, dict) else None
        if mirror is False:
            primaries.append(repo)
            print(f"{org}/{repo}: Gitea's primary")
        elif mirror is True:
            print(f"{org}/{repo}: pull mirror, GitHub is its upstream")
        else:
            print(f"ERROR: Gitea did not say whether {org}/{repo} is a mirror", file=sys.stderr)
            return 1
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("".join(r + "\n" for r in primaries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
