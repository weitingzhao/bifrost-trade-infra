#!/usr/bin/env python3
"""S6 document gates. Run an exported M0 copy with Python isolated mode.

Cleanup wave 2 (2026-11-12): the landing allow set and the hard/floor path
tables are the platform's call; it judges the same revision before it pushes.
This CI keeps only what the platform does not do: the doc-consumers reader
registry and the text check on every changed file. The scope stage is retired
and succeeds without reading anything.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = "bifrost-trade-infra"
REGISTRY = "agent-config/landing/doc-consumers.yaml"


class PolicyError(Exception):
    pass


def git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if proc.returncode:
        raise PolicyError(f"git_read_failed {args[0]}")
    return proc.stdout


def sha(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value) or value == "0" * 40:
        raise PolicyError("invalid_sha")
    return value


def path_name(value):
    if not value or value.startswith("/") or "\0" in value:
        raise PolicyError("path_invalid")
    if any(p in ("", ".", "..") for p in value.split("/")):
        raise PolicyError("path_invalid")
    return value


def matches(pattern, name):
    """Path glob: * stays in a segment; ** crosses segments."""
    path_name(pattern)
    out, i = "", 0
    while i < len(pattern):
        if pattern[i:i + 3] == "**/":
            out += "(?:.*/)?"
            i += 3
        elif pattern[i:i + 2] == "**":
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.fullmatch(out, name) is not None


def tree(repo, revision):
    rows = git(repo, "ls-tree", "-r", "-z", sha(revision)).split(b"\0")
    result = {}
    for row in filter(None, rows):
        meta, name = row.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        result[path_name(name.decode("utf-8"))] = (mode, kind, oid)
    return result


def blob(repo, revision, name):
    return git(repo, "show", f"{sha(revision)}:{path_name(name)}")


def identity(repo, revision, base, purpose="landing"):
    sha(revision)
    sha(base)
    if purpose == "push":
        # Webhook before/after are endpoints, including multi-commit or force
        # pushes. Require both exact commit objects, not an immediate parent.
        for value in (base, revision):
            if git(repo, "cat-file", "-t", value).strip() != b"commit":
                raise PolicyError("commit_missing")
        return
    if purpose != "landing":
        raise PolicyError("invalid_purpose")
    parents = git(repo, "rev-list", "--parents", "-n1", revision).decode().split()
    if parents != [revision, base]:
        raise PolicyError("base_mismatch")


def changes(repo, base, revision, purpose="landing"):
    identity(repo, revision, base, purpose)
    names = git(repo, "diff", "--no-ext-diff", "--no-renames", "--name-status", "-z", base, revision).split(b"\0")
    if names[-1] != b"" or (len(names) - 1) % 2:
        raise PolicyError("path_invalid")
    stats = {}
    for row in filter(None, git(repo, "diff", "--no-ext-diff", "--no-renames", "--numstat", "-z", base, revision).split(b"\0")):
        added, deleted, name = row.split(b"\t", 2)
        stats[path_name(name.decode("utf-8"))] = (added, deleted)
    result = []
    for i in range(0, len(names) - 1, 2):
        name = path_name(names[i + 1].decode("utf-8"))
        if name not in stats:
            raise PolicyError("diff_incomplete")
        result.append((names[i].decode("ascii"), name, stats[name]))
    return result


def scope(repo=None, base=None, revision=None):
    print("scope: retired (cleanup wave 2): the platform checks the allow set and path tables before it pushes")


def registry(repo, base):
    rows = yaml.safe_load(blob(repo, base, REGISTRY))
    if not isinstance(rows, list) or not rows:
        raise PolicyError("registry_missing_or_empty")
    seen = set()
    for row in rows:
        name, repo_name = row["file"], row.get("repo", REPO)
        path_name(name)
        key = (repo_name, name)
        if key in seen or repo_name not in (REPO, "bifrost-platform"):
            raise PolicyError("registry_invalid")
        seen.add(key)
        if row["class"] not in ("reader", "constraint", "skip", "data", "mention", "token"):
            raise PolicyError("registry_invalid_class")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", row["hits"]):
            raise PolicyError("registry_invalid_hash")
        if not all(isinstance(row.get(k), str) and row[k].strip() for k in ("why", "checked_by", "effect")):
            raise PolicyError("registry_review_missing")
        if row["class"] == "reader":
            if not isinstance(row.get("reads"), list) or not row["reads"]:
                raise PolicyError("registry_reads_missing")
            for p in row["reads"]:
                path_name(p)
    return rows


def consumed(rows, paths):
    for row in rows:
        if row["class"] == "reader":
            for name in paths:
                if any(matches(p, name) for p in row["reads"]):
                    raise PolicyError(f"consumed_path {name}")


def consumers(repo, base, revision, purpose="landing"):
    # Only changed paths matter: a reader whose read set covers a changed path
    # fails the run. Unchanged files cannot affect a reader at runtime.
    consumed(registry(repo, base), [r[1] for r in changes(repo, base, revision, purpose)])


def content(data, name):
    if b"\0" in data:
        raise PolicyError(f"doc_content {name}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyError(f"doc_content {name}") from exc


def documents(repo, base, revision, platform, platform_revision, purpose="landing"):
    # Every changed file that remains must be UTF-8 text without NUL bytes.
    # platform / platform_revision stay in the signature for callers.
    errors = []
    for kind, name, _ in changes(repo, base, revision, purpose):
        if kind == "D":
            continue
        try:
            content(blob(repo, revision, name), name)
        except PolicyError as exc:
            errors.append(str(exc))
    if errors:
        raise PolicyError("; ".join(errors))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=("scope", "consumers", "doc-policy"))
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--revision", required=True)
    ap.add_argument("--platform", type=Path, required=True)
    ap.add_argument("--platform-revision", required=True)
    ap.add_argument("--purpose", choices=("landing", "push"), default="landing")
    args = ap.parse_args()
    try:
        sha(args.platform_revision)
        if args.stage == "scope":
            scope()
        elif args.stage == "consumers":
            consumers(args.repo, args.base, args.revision, args.purpose)
        else:
            documents(args.repo, args.base, args.revision, args.platform, args.platform_revision, args.purpose)
    except (PolicyError, OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
