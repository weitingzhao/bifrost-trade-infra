#!/usr/bin/env python3
"""Early word, for the repository that causes it, that a commit changes what the registry of
document consumers fingerprints in that repository.

The registry (doc-consumers.yaml of this repository, a hard floor) holds rows for files of
another repository too. A commit there that changes a fingerprinted line is not checked by that
repository's own CI; the next landing of this repository is refused instead, for everyone, and
whoever made the change does not see it (2026-10-31, 11-01, 11-02 and 11-14: six hours that
time). This reads the registry at one commit and a candidate commit of the other repository,
and lists every row of that repository that no longer matches and every unregistered hit, with
the value the row needs. It changes nothing and loosens nothing: the registry check itself
(doc_consumers.py) still runs in ci-infra and is still what refuses a landing. The hit lines
and the fingerprint are computed by that script's own functions.

  consumers_of_repo.py --registry-repo <clone> --registry-revision HEAD \\
      --name <repository> --candidate <clone> --candidate-revision HEAD
"""
import argparse
import runpy
import subprocess
import sys
from pathlib import Path

D = runpy.run_path(str(Path(__file__).with_name("doc_consumers.py")))
P = D["P"]


def resolve(repo, revision):
    return P["git"](repo, "rev-parse", "--verify", "--quiet", revision + "^{commit}").decode().strip()


def candidates(repo, revision):
    """Files of the commit with a line the registry's first pattern matches, by one search of
    the tree. It only narrows what is read: the hits themselves are the registry check's own."""
    proc = subprocess.run(["git", "-C", str(repo), "grep", "-l", "-a", "-z", "-E", "-e", D["S1"].pattern, revision, "--"],
                          capture_output=True, check=False)
    if proc.returncode not in (0, 1):
        raise P["PolicyError"]("git_read_failed grep")
    prefix = revision + ":"
    return {n[len(prefix):] for n in proc.stdout.decode("utf-8", errors="replace").split("\0") if n.startswith(prefix)}


def differences(rows, repo, revision, name):
    """(problems, notes): every row of `name` the candidate no longer matches, every unregistered hit."""
    entries = {r["file"]: r for r in rows if r.get("repo", P["REPO"]) == name}
    tree = P["tree"](repo, revision)
    problems, notes = [], []
    for path in sorted(candidates(repo, revision) | (entries.keys() & tree.keys())):
        if path not in tree or not D["scanned"](path):
            continue
        _, kind, oid = tree[path]
        if kind != "blob":
            problems.append({"what": "unreadable_consumer", "file": path})
            continue
        found = D["hits"](path, P["git"](repo, "cat-file", "blob", oid), True)
        if not found:
            continue
        now = D["fingerprint"](found)
        if path not in entries:
            problems.append({"what": "unregistered_consumer", "file": path, "hits": now, "lines": found})
        elif entries[path]["hits"] != now:
            problems.append({"what": "consumer_changed", "file": path, "hits": now, "was": entries[path]["hits"], "lines": found})
    for path in sorted(entries.keys() - tree.keys()):
        notes.append(f"registry_stale {name}/{path}")
    return problems, notes


def report(problems, name, registry_revision):
    out = [f"{len(problems)} file(s) of {name} do not match the registry of document consumers",
           f"({P['REPO']} {P['REGISTRY']} at {registry_revision[:12]}).",
           f"Landed as it is, this commit gets every landing of {P['REPO']} refused (consumer_changed) until the registry follows.",
           "The registry is a hard floor: its rows are changed by the Owner, before this commit lands. What each row needs:", ""]
    for p in problems:
        out.append(f"FAIL {p['what']} {p['file']}")
        if "was" in p:
            out.append(f"  the row's hits: {p['was']}")
        if "hits" in p:
            out.append(f"  hits now:       {p['hits']}")
        if p["what"] == "unregistered_consumer":
            out.append(f'  a new row: {{"repo": "{name}", "file": "{p["file"]}", "class": "<classify by hand>", "effect": "<…>", "hits": "{p["hits"]}", "why": "<…>"}}')
        for n, line in p.get("lines", [])[:8]:
            out.append(f"  line {n}: {line[:200]}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry-repo", type=Path, required=True)
    ap.add_argument("--registry-revision", default="HEAD")
    ap.add_argument("--name", required=True, help="the repository's name in the registry's rows")
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--candidate-revision", default="HEAD")
    args = ap.parse_args()
    try:
        registry_revision = resolve(args.registry_repo, args.registry_revision)
        revision = resolve(args.candidate, args.candidate_revision)
        rows = P["registry"](args.registry_repo, registry_revision)
        problems, notes = differences(rows, args.candidate, revision, args.name)
    except (P["PolicyError"], OSError, ValueError, KeyError, TypeError, P["yaml"].YAMLError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2
    if notes:
        print(f"WARN {len(notes)} row(s) of {args.name} name a file the commit does not have (not a failure): " + ", ".join(n.split(" ", 1)[1] for n in notes[:3]) + (" …" if len(notes) > 3 else ""))
    if problems:
        print(report(problems, args.name, registry_revision), file=sys.stderr)
        return 1
    print(f"ok: every hit of {args.name} at {revision[:12]} matches the registry at {registry_revision[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
