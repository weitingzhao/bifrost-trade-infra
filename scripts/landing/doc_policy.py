#!/usr/bin/env python3
"""S6 document gates. Run an exported M0 copy with Python isolated mode."""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = "bifrost-trade-infra"
RULES = "agent-config/agentrt-rules/prod/landing-dev.yaml"
REGISTRY = "agent-config/landing/doc-consumers.yaml"
CLAIM = re.compile(r"Owner\s*(的)?\s*(决定|已定|采纳|批准|签收|拍板|点选|定了|同意)")


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


def hard(name):
    parts = name.split("/")
    if parts[0] in ("k8s", "scripts", "docker", "config", ".github", ".gitea"):
        return True
    if name.startswith("agent-config/") and not name.startswith("agent-config/work/"):
        return True
    if any(p in (".vscode", ".idea", ".claude", ".cursor", ".codex") for p in parts):
        return True
    leaf = parts[-1]
    if leaf in (".gitattributes", ".gitmodules", ".gitignore", "AGENTS.md", "CLAUDE.md", "SKILL.md"):
        return True
    if any(matches(p, leaf) for p in ("*.mdc", "*.code-workspace", ".env*", "OWNER-STEPS-*",
                                     "*RUNBOOK*", "TICKET-*", "REQUEST-*", "RULE-*")):
        return True
    return any(matches(p, name) for p in ("Makefile", "docker-compose*.yml", "mkdocs.yml", "requirements*.txt"))


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


def identity(repo, revision, base):
    sha(revision)
    sha(base)
    parents = git(repo, "rev-list", "--parents", "-n1", revision).decode().split()
    if parents != [revision, base]:
        raise PolicyError("base_mismatch")


def changes(repo, base, revision):
    identity(repo, revision, base)
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


def allow(repo, base):
    rules = yaml.safe_load(blob(repo, base, RULES))
    entries = [r for r in rules["repos"] if r["repo"] == REPO]
    if len(entries) != 1 or not entries[0].get("allow"):
        raise PolicyError("infra_allow_missing")
    patterns = entries[0]["allow"]
    if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
        raise PolicyError("invalid_allow")
    for p in patterns:
        path_name(p)
    return patterns


def scope(repo, base, revision):
    patterns, files = allow(repo, base), tree(repo, revision)
    count = lines = 0
    for kind, name, (added, deleted) in changes(repo, base, revision):
        mode = files.get(name, (None,))[0]
        if kind == "T" or b"-" in (added, deleted) or (kind != "D" and mode != "100644"):
            raise PolicyError(f"structural {name}")
        if hard(name):
            raise PolicyError(f"hard_floor {name}")
        if kind not in ("A", "M"):
            raise PolicyError(f"change_kind {name}")
        if not any(matches(p, name) for p in patterns):
            raise PolicyError(f"scope {name}")
        count += 1
        lines += int(added) + int(deleted)
    if not count or count > 5 or lines > 1500:
        raise PolicyError("scope_size")


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


def consumers(repo, base, revision):
    rows, patterns = registry(repo, base), allow(repo, base)
    changed = [r[1] for r in changes(repo, base, revision)]
    paths = set(tree(repo, revision)) | set(changed)
    for row in rows:
        if row["class"] != "reader":
            continue
        for name in sorted(paths):
            if any(matches(p, name) for p in row["reads"]) and any(matches(p, name) for p in patterns):
                raise PolicyError(f"registry_overlap {row['file']} {name}")
    consumed(rows, changed)


def content(data, name):
    if len(data) > 256 * 1024 or b"\0" in data:
        raise PolicyError(f"doc_content {name}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyError(f"doc_content {name}") from exc


def marked(lines):
    active, result = [], set()
    for i, line in enumerate(lines):
        heading = re.match(r"^(#{1,6})\s+(.+)", line)
        if heading:
            level = len(heading[1])
            active = [(n, yes) for n, yes in active if n < level]
            active.append((level, "Owner 决定" in heading[2]))
        if CLAIM.search(line) or (line.strip() and any(yes for _, yes in active)):
            result.add(i)
    return result


def paragraph(lines, at):
    start, end = at, at + 1
    while start and lines[start - 1].strip():
        start -= 1
    while end < len(lines) and lines[end].strip():
        end += 1
    return "\n".join(lines[start:end])


def evidence(text, repo, base, platform, platform_revision, name):
    simple = re.search(r"(?:审批|单|request|approval)\s*#\d+", text)
    if simple:
        return simple[0]
    stamp = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text)
    if "线程" in text and stamp:
        return "线程 " + stamp[0] + " CDT"
    references = list(re.finditer(r"([\w./-]+\.md)\s+§([0-9]+(?:\.[0-9]+)*)", text))
    files = tree(repo, base) if references else {}
    for match in references:
        ref, section = match.groups()
        options = {ref, str(Path(name).parent / ref)}
        if "/" not in ref:
            options |= {p for p in files if p.split("/")[-1] == ref}
        for p in options & files.keys():
            old = blob(repo, base, p).decode("utf-8")
            if re.search(r"^#{1,6}\s+" + re.escape(section) + r"(?=[\s.、:：]|$)", old, re.MULTILINE):
                return match[0]
    for match in re.finditer(r"(?<![0-9A-Za-z])[0-9a-fA-F]{7,40}(?![0-9A-Za-z])", text):
        for source, head in ((repo, base), (platform, platform_revision)):
            if source is None:
                continue
            # A shallow checkout cannot prove older history; never fetch to make it pass.
            probe = subprocess.run(["git", "-C", str(source), "merge-base", "--is-ancestor", match[0], head], capture_output=True, check=False)
            if probe.returncode == 0:
                return match[0]
    return ""


def diff_hunks(repo, base, revision, name):
    raw = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--unified=3",
              base, revision, "--", name).decode("utf-8")
    hunks, current = [], None
    left = right = 0
    for line in raw.splitlines():
        header = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if header:
            left, right = int(header[1]) - 1, int(header[2]) - 1
            current = ([], [])
            hunks.append(current)
        elif current is not None:
            if line.startswith("+"):
                current[0].append(right)
                right += 1
            elif line.startswith("-"):
                current[1].append(left)
                left += 1
            elif line.startswith(" "):
                left += 1
                right += 1
    return hunks


def owner_claims(old, new, repo, base, platform, platform_revision, name, hunks=None):
    before, after = old.splitlines(), new.splitlines()
    old_marks, new_marks = marked(before), marked(after)
    if hunks is None:  # Inner tests; the CLI always uses Git's actual hunks.
        hunks = []
        matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
        for group in matcher.get_grouped_opcodes(3):
            additions, removals = [], []
            for tag, a, b, c, d in group:
                if tag in ("replace", "delete"):
                    removals.extend(range(a, b))
                if tag in ("replace", "insert"):
                    additions.extend(range(c, d))
            hunks.append((additions, removals))
    errors = []
    for additions, deleted in hunks:
        removals = [i for i in deleted if i in old_marks]
        linked = False
        for i in additions:
            if i not in new_marks and not removals:
                continue
            proof = evidence(paragraph(after, i), repo, base, platform, platform_revision, name)
            # Removal requires evidence on an added line in this hunk, not an
            # unchanged approval somewhere else in the surrounding paragraph.
            linked |= bool(evidence(after[i], repo, base, platform, platform_revision, name))
            if i in new_marks:
                print(json.dumps({"file": name, "line": i + 1, "claim": after[i], "evidence": proof}, ensure_ascii=False))
                if not proof:
                    errors.append(f"owner_claim_unlinked {name}:{i + 1}")
        for i in removals:
            print(json.dumps({"file": name, "deleted_line": i + 1, "claim": before[i]}, ensure_ascii=False))
        if removals and not linked:
            errors.append(f"owner_claim_removed {name}")
    if errors:
        raise PolicyError("; ".join(errors))


def documents(repo, base, revision, platform, platform_revision):
    patterns = allow(repo, base)
    errors = []
    for kind, name, _ in changes(repo, base, revision):
        if not any(matches(p, name) for p in patterns) or hard(name):
            continue
        new = content(blob(repo, revision, name), name) if kind != "D" else ""
        old = blob(repo, base, name).decode("utf-8") if kind != "A" else ""
        try:
            owner_claims(old, new, repo, base, platform, platform_revision, name,
                         diff_hunks(repo, base, revision, name))
        except PolicyError as exc:
            errors.append(str(exc))
    if errors:
        raise PolicyError("; ".join(errors))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stage", choices=("scope", "consumers", "doc-policy", "owner-claims"))
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--revision", required=True)
    ap.add_argument("--platform", type=Path, required=True)
    ap.add_argument("--platform-revision", required=True)
    args = ap.parse_args()
    try:
        sha(args.platform_revision)
        if args.stage == "scope":
            scope(args.repo, args.base, args.revision)
        elif args.stage == "consumers":
            consumers(args.repo, args.base, args.revision)
        else:
            documents(args.repo, args.base, args.revision, args.platform, args.platform_revision)
    except (PolicyError, OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
