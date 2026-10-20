#!/usr/bin/env python3
"""TD-383, round 2's thin step: bring a result the agent runtime accepted into main, the way the
coordinator brought ten of them by hand on 2026-10-19 (M-9, M-12, M-30, M-31). A helper for the
coordinator, who holds the right to push main already; not a boundary for anyone else.

    python3 scripts/agentrt/merge_accepted.py --env prod list
    python3 scripts/agentrt/merge_accepted.py --env prod plan t_01M5B8BF2EM3SJQDKZ9E9TY2H8
    python3 scripts/agentrt/merge_accepted.py --env prod apply t_01M5B8BF2EM3SJQDKZ9E9TY2H8 [--push]
    python3 scripts/agentrt/merge_accepted.py prunable

list      every accepted implementation that has not landed on its repository's main and whose
          change is not empty; exit 1 when there is one. Landed: a commit of main carries its
          Agentrt-Task trailer or the accepted commit's Change-Id, and no later commit of main
          reverts it. The check TD-383 asks for: on PROD each of them is merged, or someone says why.
plan      what apply would do: the mission, the task, the attempt that was accepted and who wrote and
          reviewed it, the commit and the files it changes, whether apply may push it, the message.
apply     in a fresh worktree of the repository's main (its siblings beside it, as CI clones them):
          the accepted commit cherry-picked with its author (agentd), its Agentrt-Task and Change-Id
          trailers, TD-383 in Work, the message saying which mission, task, attempt and reviewer it
          came from; then the repository's suite as its CI runs it, and code-health. A repository
          with no suite here is built and left unverified (exit 4). With --push, only for a
          repository it may push and only once the suite passed, push-main.sh pushes it (the
          release window, fast-forward, code-health on that exact commit).
prunable  TD-383's deletion rule over the agent/<task>/a<n> branches of bifrost-platform and
          bifrost-ui, and why for each; it deletes nothing (who deletes, and how past Gitea's
          protection of agent/**, is the Owner's to decide). PROD and STG push to the same
          repositories: each task is looked up in both, and one both know is kept. A branch goes 7
          days after the event that made its rule hold; the accepted attempt's branch is kept, on
          main or not: main's history does not say when a commit reached it.

Where the line is (ADR §1, §5, §12.7: until the release queue, nothing reaches a running system
unattended, and merging is 「核对后合」, Owner 10-19). Pushing bifrost-platform's main starts its CI
and nothing else: a release is its own step (STG by an Agent, PROD on the Owner's approval). It is
the one repository apply pushes. bifrost-ui's main is what the Console and the Trade frontend build
against, and their checks are not run here; bifrost-trade-infra's k8s/ is synced by Argo
(bifrost-platform-stg and -prod automatically) and its agent-config/ holds the rules; any other
repository is outside this thin step and follows its own release rules. For those apply builds
and stops (agent-config/work/multi-agent/PLAN-td383-merge-and-prune-2026-10-20.md).

It reads the runtime with the environment's viewer token from bifrost-trade-infra/.env and prints
no credential; it writes nothing to the platform. Git objects come from the workspace's own
checkouts (BIFROST_WORKSPACE, else ~/Desktop/stocks): it fetches into them and registers worktrees
there, and never touches their working trees, index or branches.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
INFRA = HERE.parents[1]
BASES = {"prod": "http://192.168.10.100:30876", "stg": "http://192.168.10.73:30878"}
TOKEN_KEYS = {"prod": "PLATFORM_PROD_VIEWER_TOKEN", "stg": "PLATFORM_STG_VIEWER_TOKEN"}
EVENTS_PAGE = 500  # the events route answers at most this many after after_seq

# Repositories whose main apply may push: pushing it starts its CI and no release.
PUSHABLE = {"bifrost-platform"}
WHY_NOT = {
    "bifrost-ui": "the Console and the Trade frontend build against its main, and their checks are not run here",
    "bifrost-trade-infra": "Argo syncs its k8s/ (bifrost-platform-stg and -prod automatically) and its agent-config/ holds the rules",
}
WHY_NOT_DEFAULT = "it is outside this thin step's pushable set and follows its own release rules"

# Siblings a repository's suite needs beside it, as CI clones them at main.
SIBLINGS = {"bifrost-platform": ["bifrost-trade-infra", "bifrost-ui"]}

# The suite of a repository as its CI pipeline runs it (k8s/cicd/tekton/pipeline-ci-platform.yaml),
# with the MCP package's tests, which CI does not run; each command from the repository's root.
SUITES: dict[str, list[list[str]]] = {
    "bifrost-platform": [
        ["go", "-C", "api", "test", "./...", "-count=1", "-timeout=600s"],
        ["npm", "--prefix", "../bifrost-ui", "ci", "--no-audit", "--no-fund"],
        ["npm", "--prefix", "console", "ci", "--no-audit", "--no-fund"],
        ["npm", "--prefix", "console", "run", "type-check"],
        ["npm", "--prefix", "console", "run", "lint"],
        ["sh", "-c", "cd console && npx vitest run --maxWorkers=2"],
        ["npm", "--prefix", "console", "run", "build"],
        ["bash", "scripts/ci/check_spine_catalog.sh"],
        ["sh", "-c", "cd .. && python3 bifrost-trade-infra/scripts/check_ops_context_parity.py --self-test"
                     " && python3 bifrost-trade-infra/scripts/check_ops_context_parity.py"],
        ["npm", "--prefix", "mcp/platform", "ci", "--no-audit", "--no-fund"],
        ["npm", "--prefix", "mcp/platform", "test"],
    ],
}
# What a suite needs from the environment, as its CI has it: platform's database tests run
# against a Postgres and a Redis that CI starts, and must not skip (AGENTRT_TEST_REQUIRED).
SUITE_NEEDS = {"bifrost-platform": ["AGENTRT_TEST_PG", "AGENTRT_TEST_REDIS"]}
# Repositories push-main.sh scans with code-health (its GATED list).
CODE_HEALTH = {"bifrost-platform", "bifrost-trade-frontend", "bifrost-research", "bifrost-trade-api", "bifrost-trade-core",
               "bifrost-trade-worker"}

TRAILER = re.compile(r"^([A-Za-z][A-Za-z0-9-]*): (.*)$")
GENERIC_SUBJECT = re.compile(r"^agentrt: t_[0-9A-Z]{26} attempt \d+$")
REVERTS = re.compile(r"^This reverts commit ([0-9a-f]{40})\.$", re.M)  # git revert's own line


class Refused(Exception):
    """A task apply must not merge, and why."""


# ── the runtime ───────────────────────────────────────────────────────────────

def token(env: str) -> str:
    """The environment's viewer token: from the environment, else the .env of this infra checkout,
    else of the workspace's (a worktree has none of its own)."""
    key = TOKEN_KEYS[env]
    value = os.environ.get(key, "")
    places = [INFRA / ".env", workspace() / "bifrost-trade-infra" / ".env"]
    for dotenv in places:
        if value:
            break
        m = re.search(r"^" + key + r"=(.*)$", dotenv.read_text(), re.M) if dotenv.is_file() else None
        value = m.group(1).strip().strip('"') if m else ""
    if not value:
        sys.exit(f"merge_accepted: no {key} in the environment or in {' or '.join(map(str, places))}")
    return value


class Runtime:
    """GET of the agent runtime's read routes. Only a 404 reads as "none"; any other error is one."""

    def __init__(self, env: str, get: Callable[[str], object] | None = None):
        self.env = env
        if get is None:
            base, tok = BASES[env], token(env)

            def get(path: str) -> object:
                req = urllib.request.Request(base + "/api/v1/agentrt/" + path, headers={"Authorization": "Bearer " + tok})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.load(resp)
        self._get = get

    # A read that fails on the platform's side (a 5xx, a connection refused or dropped, an answer
    # cut short) is tried again:
    # the routes answered an occasional 500 on 2026-10-20 that the same read did not repeat.
    TRIES = 3
    PAUSE = 2.0

    def get(self, path: str, **query: str) -> object:
        full = path + ("?" + urllib.parse.urlencode(query) if query else "")
        for n in range(1, self.TRIES + 1):
            try:
                return self._get(full)
            except urllib.error.HTTPError as exc:
                if exc.code < 500 or n == self.TRIES:
                    raise
            except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError):
                # A connection refused or dropped, or an answer cut short while it was read.
                if n == self.TRIES:
                    raise
            time.sleep(self.PAUSE * n)
        raise AssertionError("unreachable")

    def _or_none(self, path: str) -> dict | None:
        try:
            return self.get(path)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def task(self, task_id: str) -> dict:
        return self.get("tasks/" + urllib.parse.quote(task_id))

    def find_task(self, task_id: str) -> dict | None:
        """The task, or None when this runtime has none of that id."""
        return self._or_none("tasks/" + urllib.parse.quote(task_id))

    def attempt(self, attempt_id: str) -> dict:
        return self.get("attempts/" + urllib.parse.quote(attempt_id))

    def mission(self, mission_id: str) -> dict | None:
        return self._or_none("missions/" + urllib.parse.quote(mission_id))

    def tasks(self, mission: str, state: str = "") -> list[dict]:
        doc = self.get("tasks", mission=mission, **({"state": state} if state else {}))
        if doc.get("truncated"):
            raise Refused(f"mission {mission} has more tasks than one list answers; this tool cannot see them all")
        return doc.get("tasks") or []

    def events(self, mission: str) -> list[dict]:
        """Every event of the mission's stream, a page at a time."""
        out: list[dict] = []
        while True:
            query = {"stream": "mission:" + mission}
            if out:
                query["after_seq"] = str(out[-1]["seq"])
            page = self.get("events", **query)
            out.extend(page)
            if len(page) < EVENTS_PAGE:
                return out

    def missions(self) -> list[str]:
        """Every mission, M-1 up: they are numbered without gaps (store/propose.go takes max + 1
        under a lock, and no route deletes one)."""
        out, n = [], 1
        while self.mission(f"M-{n}") is not None:
            out.append(f"M-{n}")
            n += 1
        return out


# ── what the runtime accepted ─────────────────────────────────────────────────

@dataclass
class Accepted:
    """An accepted implementation and the attempt that was accepted."""
    env: str
    task: str
    title: str
    repo: str
    base: str
    mission: str
    mission_label: str  # its work id, else the start of its title
    attempt: str
    attempt_no: int
    author: str  # the executor of the accepted attempt
    ref: str
    commit: str
    reviewers: list[str] = field(default_factory=list)  # empty when the records do not tie one
    accepted_at: str = ""


def accepted(rt: Runtime, task_id: str) -> Accepted:
    """What the runtime records of an accepted implementation. The accepted attempt is the one the
    last passing review names (verification_recorded on the task, method review, verdict pass:
    Conclude writes the checked attempt there, and a salvaged attempt adopted the same way); the
    reviewer, the executor of the last attempt of the review task accepted in that transaction;
    the time, the task's last move to accepted."""
    t = rt.task(task_id)
    if t.get("role") != "implement":
        raise Refused(f"task {task_id} is a {t.get('role')} task, not an implementation")
    if t.get("state") != "accepted":
        raise Refused(f"task {task_id} is {t.get('state')}, not accepted")
    repo, mission = t.get("repo") or "", t["mission_id"]
    if not repo:
        raise Refused(f"task {task_id} names no repository")
    events = rt.events(mission)
    mine = [e for e in events if e.get("task_id") == task_id]
    passes = [e for e in mine if e.get("event_type") == "verification_recorded"
              and (e.get("body_json") or {}).get("method") == "review" and (e.get("body_json") or {}).get("verdict") == "pass"]
    if not passes:
        raise Refused(f"task {task_id} has no passing review on record")
    attempt_id = passes[-1]["attempt_id"]
    a = rt.attempt(attempt_id)
    if not a.get("pushed_commit") or not a.get("pushed_ref"):
        raise Refused(f"attempt {attempt_id} of task {task_id} pushed no branch")
    at = [e.get("at", "") for e in mine if e.get("event_type") == "task_state_changed" and (e.get("body_json") or {}).get("to") == "accepted"]
    txid = passes[-1].get("txid")
    reviews = {e["task_id"] for e in events if e.get("event_type") == "task_state_changed" and e.get("task_id") != task_id
               and (e.get("body_json") or {}).get("to") == "accepted" and txid is not None and e.get("txid") == txid}
    if not reviews:
        # No transaction ties it: only a sole accepted review of the task names its reviewer.
        accepted_reviews = {x["task_id"] for x in rt.tasks(mission) if x.get("subject_task_id") == task_id
                            and x.get("role") == "review" and x.get("state") == "accepted"}
        reviews = accepted_reviews if len(accepted_reviews) == 1 else set()
    reviewer = ""
    for e in events:
        if e.get("event_type") == "attempt_leased" and e.get("task_id") in reviews:
            reviewer = (e.get("body_json") or {}).get("executor", "") or reviewer
    m = rt.mission(mission) or {}
    label = m.get("work_id") or first_words(m.get("title") or "", 60)
    return Accepted(env=rt.env, task=task_id, title=t.get("title") or "", repo=repo, base=t.get("base_commit") or "",
                    mission=mission, mission_label=label, attempt=attempt_id, attempt_no=int(a.get("attempt_no") or 0),
                    author=a.get("executor_actor_id") or "", ref=a["pushed_ref"], commit=a["pushed_commit"],
                    reviewers=[reviewer] if reviewer else [], accepted_at=at[-1] if at else "")


def first_words(text: str, n: int) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= n else line[: n - 1].rstrip() + "…"


def parse_time(at: str) -> datetime | None:
    try:
        d = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", at.replace("Z", "+00:00")))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def minute(at: str) -> str:
    """2026-10-20T00:02:41.123456+00:00 → 2026-10-20 00:02Z."""
    d = parse_time(at)
    if d is None:
        return at or "at a time not on record"
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")


# ── git ───────────────────────────────────────────────────────────────────────

def git(repo_dir: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo_dir), "-c", "core.hooksPath=/dev/null", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise Refused(f"git {' '.join(args)} in {repo_dir}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def workspace() -> Path:
    return Path(os.environ.get("BIFROST_WORKSPACE") or Path.home() / "Desktop" / "stocks")


@dataclass
class Main:
    """What a repository's main says of agent work: by task and by Change-Id, every commit that
    carries it, newest first; and which commit each revert on main reverts. Only git revert's own
    message counts as a revert (its subject starts 'Revert "' or, for a revert of a revert,
    'Reapply "', and its body says "This reverts commit <sha>."): a revert written by hand is not
    recognised, and a landing is then taken as standing."""
    by_task: dict[str, list[str]] = field(default_factory=dict)
    by_change: dict[str, list[str]] = field(default_factory=dict)
    reverts: dict[str, str] = field(default_factory=dict)  # the revert's commit → the commit it reverts

    def undone(self, sha: str, depth: int = 0) -> bool:
        """Whether a revert on main undoes sha and is not itself undone (a revert of a revert
        restores it)."""
        return depth < 20 and any(t == sha and not self.undone(r, depth + 1) for r, t in self.reverts.items())

    def landed(self, task: str, change_id: str = "") -> tuple[str, str]:
        """(the newest commit it landed as and still stands, "") when it is on main; ("", why
        not) otherwise. Its task's trailer and its Change-Id are looked at together, so a newer
        landing under either stands though an older one was reverted."""
        found = [*(self.by_task.get(task, []) if task else []), *(self.by_change.get(change_id, []) if change_id else [])]
        for sha in found:
            if not self.undone(sha):
                return sha, ""
        if found:
            return "", f"it landed as {found[0][:12]} and was reverted"
        return "", "not on main"


def read_main(repo_dir: Path) -> Main:
    m = Main()
    log = git(repo_dir, "log", "origin/main", "--format=%H%x00%(trailers:key=Agentrt-Task,valueonly,separator=%x2C)"
              "%x00%(trailers:key=Change-Id,valueonly,separator=%x2C)%x00%s%x00%B%x1e")
    for rec in log.split("\x1e"):
        parts = rec.strip("\n").split("\x00")
        if len(parts) < 5:
            continue
        sha, tasks, changes, subject, body = parts[0].strip(), parts[1], parts[2], parts[3], parts[4]
        for key, found in ((tasks, m.by_task), (changes, m.by_change)):
            for v in filter(None, (x.strip() for x in key.split(","))):
                found.setdefault(v, []).append(sha)  # newest first
        target = REVERTS.findall(body)
        if subject.startswith(('Revert "', 'Reapply "')) and len(target) == 1:  # git names a revert of a revert Reapply
            m.reverts[sha] = target[0]
    return m


def fetch(repo_dir: Path, refs: list[str]) -> None:
    git(repo_dir, "fetch", "--quiet", "--no-tags", "origin", "main", *refs)


def change(repo_dir: Path, a: Accepted) -> list[str]:
    """The files the accepted commit changes; it must be one commit on its task's base."""
    if not a.base:
        raise Refused(f"task {a.task} names no base commit: merge it by hand")
    if git(repo_dir, "cat-file", "-t", a.commit, check=False).strip() != "commit":
        raise Refused(f"commit {a.commit} of {a.ref} is not in {repo_dir}")
    parents = git(repo_dir, "rev-list", "--parents", "-n", "1", a.commit).split()[1:]
    if parents != [a.base]:
        raise Refused(f"{a.commit} is not one commit on its task's base {a.base}: merge it by hand")
    return [p for p in git(repo_dir, "diff", "--name-only", a.base, a.commit).splitlines() if p]


def change_id(message: str) -> str:
    for ln in reversed(message.strip("\n").split("\n")):
        if ln.startswith("Change-Id: "):
            return ln[len("Change-Id: "):].strip()
    return ""


def message(original: str, a: Accepted) -> str:
    """The accepted commit's message with where it came from said before its trailers, a
    cherry-pick line, and TD-383 in its Work trailer; Agentrt-Task and Change-Id as they were."""
    paragraphs = original.strip("\n").split("\n\n")
    last = paragraphs[-1].split("\n") if len(paragraphs) > 1 else []
    if not last or not all(TRAILER.match(ln) for ln in last):
        raise Refused(f"the commit of task {a.task} ends in no trailers")
    body, trailers = "\n\n".join(paragraphs[:-1]).split("\n"), last
    tasks = [ln[len("Agentrt-Task: "):].strip() for ln in trailers if ln.startswith("Agentrt-Task: ")]
    changes = [ln[len("Change-Id: "):].strip() for ln in trailers if ln.startswith("Change-Id: ")]
    if tasks != [a.task]:
        raise Refused(f"the commit of task {a.task} carries Agentrt-Task {tasks or 'none'}, not its own")
    if len(changes) != 1 or not re.fullmatch(r"I[0-9a-f]{8,}", changes[0]):
        raise Refused(f"the commit of task {a.task} carries no single Change-Id")
    out = []
    for ln in trailers:
        if ln.startswith("Work: "):
            ids = [x.strip() for x in ln[len("Work: "):].split(",") if x.strip() and x.strip() != "unassigned"]
            if "TD-383" not in ids:
                ids.append("TD-383")
            ln = "Work: " + ", ".join(ids)
        out.append(ln)
    if not any(ln.startswith("Work: ") for ln in out):
        out.append("Work: TD-383")
    reviewed = "reviewed by " + " and ".join(a.reviewers) if a.reviewers else "reviewed (the records tie no reviewer)"
    provenance = (f"Written by the agent runtime: {a.env.upper()} {a.mission} ({a.mission_label}), task {a.task}, "
                  f"attempt {a.attempt_no} {a.attempt} ({a.author}), {reviewed} and accepted {minute(a.accepted_at)}. "
                  "Until the release queue, the coordinator merges accepted results with "
                  "scripts/agentrt/merge_accepted.py (TD-383).")
    while body and not body[-1].strip():
        body.pop()
    # agentd's own subject before an executor wrote one names only the task and the attempt: the
    # task's title says what the change is.
    if body and GENERIC_SUBJECT.match(body[0]) and a.title.strip():
        body[0] = first_words(a.title, 120)
    return "\n".join(body + ["", provenance, "", f"(cherry picked from commit {a.commit})", ""] + out) + "\n"


# ── the steps ─────────────────────────────────────────────────────────────────

def may_push(repo: str) -> tuple[bool, str]:
    if repo in PUSHABLE:
        return True, f"pushing {repo} main starts its CI and no release"
    return False, f"pushing {repo} main is not this tool's: {WHY_NOT.get(repo, WHY_NOT_DEFAULT)}"


def plan(rt: Runtime, task_id: str, ws: Path) -> tuple[Accepted, list[str], str]:
    a = accepted(rt, task_id)
    repo_dir = ws / a.repo
    fetch(repo_dir, [a.ref])
    files = change(repo_dir, a)
    original = git(repo_dir, "log", "-1", "--format=%B", a.commit)
    landed, _ = read_main(repo_dir).landed(task_id, change_id(original))
    if landed:
        raise Refused(f"task {task_id} is already on {a.repo} main as {landed[:12]}")
    if not files:
        raise Refused(f"the accepted commit of task {task_id} changes nothing: nothing to merge")
    return a, files, message(original, a)


def build(a: Accepted, msg: str, ws: Path, dest: Path) -> Path:
    """The merge commit on a fresh worktree of main at dest/<repo>, siblings beside it. When it
    cannot be built, the worktrees it made are removed and dest with them; nothing else is."""
    if dest.exists():
        raise Refused(f"{dest} exists: remove it (git worktree remove for each worktree in it) or choose another --dir")
    dest.mkdir(parents=True)
    made: list[tuple[Path, Path]] = []  # (the checkout it belongs to, the worktree)
    try:
        for sib in SIBLINGS.get(a.repo, []):
            git(ws / sib, "fetch", "--quiet", "--no-tags", "origin", "main")
            git(ws / sib, "worktree", "add", "--quiet", "--detach", str(dest / sib), "origin/main")
            made.append((ws / sib, dest / sib))
        tree = dest / a.repo
        git(ws / a.repo, "worktree", "add", "--quiet", "--detach", str(tree), "origin/main")
        made.append((ws / a.repo, tree))
        r = subprocess.run(["git", "-C", str(tree), "-c", "core.hooksPath=/dev/null", "cherry-pick", a.commit],
                           capture_output=True, text=True)
        if r.returncode != 0:
            git(tree, "cherry-pick", "--abort", check=False)
            raise Refused(f"the accepted commit does not apply on {a.repo} main: {(r.stdout + r.stderr).strip()}")
        msg_file = dest / "MESSAGE"
        msg_file.write_text(msg)
        git(tree, "commit", "--amend", "--quiet", "-F", str(msg_file))
        lineage = INFRA / "agent-config" / "scripts" / "git-hooks" / "lineage.sh"
        if lineage.is_file() and (os.environ.get("CLAUDE_CODE_HOST_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID")):
            # The merging thread, as a hook would add it in a checkout with hooks.
            msg_file.write_text(git(tree, "log", "-1", "--format=%B"))
            r = subprocess.run(["sh", str(lineage), "prepare-commit-msg", str(msg_file), "message"], cwd=tree,
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise Refused(f"lineage.sh: {(r.stdout + r.stderr).strip()}")
            git(tree, "commit", "--amend", "--quiet", "-F", str(msg_file))
        return tree
    except BaseException:
        for checkout, wt in reversed(made):
            git(checkout, "worktree", "remove", "--force", str(wt), check=False)
        (dest / "MESSAGE").unlink(missing_ok=True)
        try:
            dest.rmdir()
        except OSError:
            pass
        raise


def suite_env(tree: Path, repo: str) -> dict[str, str]:
    """The environment the suite adds: CI's flag, the tree under test as the platform the
    parity check reads (an inherited PLATFORM_ROOT would point it elsewhere), and the database
    tests required where CI requires them."""
    env = {"BIFROST_CI": "1", "PLATFORM_ROOT": str(tree)}
    if SUITE_NEEDS.get(repo):
        env["AGENTRT_TEST_REQUIRED"] = "1"
    return env


def run_suite(tree: Path, repo: str, run: Callable[[list[str], Path, dict[str, str]], int]) -> tuple[bool, list[str]]:
    """The repository's suite and code-health on the tree: (whether it has a suite here, the
    steps that failed). Without a suite it is not verified, code-health or not: that is not a
    pass (review 434 A1)."""
    failed = []
    env = suite_env(tree, repo)
    cmds = SUITES.get(repo, [])
    for cmd in cmds:
        if run(cmd, tree, env) != 0:
            failed.append(" ".join(cmd))
    if repo in CODE_HEALTH:
        scan = INFRA / "agent-config" / "scripts" / "code-health" / "scan.sh"
        if run(["bash", str(scan), "--root", str(tree.parent), "--repo", repo], tree, env) != 0:
            failed.append("code-health")
    return bool(cmds), failed


def default_run(cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
    print("merge_accepted: $ " + " ".join(cmd), flush=True)
    try:
        return subprocess.run(cmd, cwd=cwd, env={**os.environ, **env}).returncode
    except OSError as exc:
        print(f"merge_accepted: cannot run {cmd[0]}: {exc}", file=sys.stderr)
        return 127


def push(tree: Path) -> int:
    return subprocess.run(["bash", str(INFRA / "scripts" / "release" / "push-main.sh"), str(tree), "HEAD"]).returncode


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_list(rt: Runtime, ws: Path, out=None) -> int:
    """Accepted implementations not landed on main, by repository; exit 1 when there is one."""
    out = out or sys.stdout
    found: dict[str, list[tuple[str, dict]]] = {}
    for m in rt.missions():
        for t in rt.tasks(m, state="accepted"):
            if t.get("role") == "implement" and t.get("repo"):
                found.setdefault(t["repo"], []).append((m, t))
    missing = 0
    for repo in sorted(found):
        repo_dir = ws / repo
        git(repo_dir, "fetch", "--quiet", "--no-tags", "origin", "main")
        main = read_main(repo_dir)
        for m, t in found[repo]:
            if main.landed(t["task_id"])[0]:
                continue
            try:
                a = accepted(rt, t["task_id"])
                fetch(repo_dir, [a.ref])
                if not change(repo_dir, a):
                    continue  # an empty change: nothing to bring
                landed, why = main.landed(t["task_id"], change_id(git(repo_dir, "log", "-1", "--format=%B", a.commit)))
                if landed:
                    continue  # landed under its Change-Id (merged by hand without the task's trailer)
                what = f"attempt {a.attempt_no} ({a.author}) {a.commit[:12]}; {why}"
            except Refused as exc:
                what = f"cannot tell: {exc}"
            missing += 1
            print(f"{repo}\t{m}\t{t['task_id']}\t{what}\t{first_words(t.get('title') or '', 80)}", file=out)
    print(f"merge_accepted: {missing} accepted implementation(s) of {rt.env} not on main", file=out)
    return 1 if missing else 0


KEEP_DAYS = 7  # TD-383: an attempt branch goes 7 days after its task ended or its attempt was superseded
AGENT_REF = re.compile(r"^refs/heads/agent/(t_[0-9A-Z]{26})/a([0-9]+)$")
PRUNE_REPOS = ("bifrost-platform", "bifrost-ui")


def entered(rt: Runtime, task: dict, state: str, cache: dict[tuple[str, str], list[dict]]) -> datetime | None:
    """When the task last moved to state, from its mission's events (its row's updated_at also
    moves when a plan change rebinds or moves it, review 434 B2)."""
    key = (rt.env, task.get("mission_id", ""))
    if key not in cache:
        cache[key] = rt.events(key[1]) if key[1] else []
    at = [e.get("at", "") for e in cache[key] if e.get("task_id") == task.get("task_id")
          and e.get("event_type") == "task_state_changed" and (e.get("body_json") or {}).get("to") == state]
    return parse_time(at[-1]) if at else None


def prunable(runtimes: dict[str, Runtime], repo_dir: Path, now: float) -> list[tuple[str, str, bool, str]]:
    """Each agent/ branch of the repository: (ref, the environment that knows its task, whether
    TD-383's rule deletes it, why). Deleted once the condition has held KEEP_DAYS, counted from
    the event that made it hold: its task moved to rejected or cancelled; it is an attempt of an
    accepted task other than the accepted one (superseded, from the acceptance). Kept: a branch
    that names no task attempt; a task no runtime or both runtimes know; a task still open; the
    accepted attempt's branch, on main or not (main's history does not say when a commit reached
    it, so "7 days after it landed" cannot be told here; review 434 A2); whatever it cannot read."""
    heads: dict[str, str] = {}
    for line in git(repo_dir, "ls-remote", "--heads", "origin", "refs/heads/agent/*").splitlines():
        sha, _, ref = line.partition("\t")
        if ref:
            heads[ref] = sha
    out: list[tuple[str, str, bool, str]] = []
    by_task: dict[str, list[tuple[str, int]]] = {}
    for ref in sorted(heads):
        m = AGENT_REF.match(ref)
        if m:
            by_task.setdefault(m.group(1), []).append((ref, int(m.group(2))))
        else:
            out.append((ref, "", False, "not an attempt branch (agent/<task>/a<n>)"))
    git(repo_dir, "fetch", "--quiet", "--no-tags", "origin", "main")
    main = read_main(repo_dir)
    events: dict[tuple[str, str], list[dict]] = {}
    for task, refs in sorted(by_task.items()):
        known = {name: t for name, rt in runtimes.items() if (t := rt.find_task(task)) is not None}
        env, t = next(iter(known.items())) if len(known) == 1 else ("", None)
        state = (t or {}).get("state", "")
        since: datetime | None = None
        accepted_no, kept = 0, ""  # kept: why the accepted attempt's branch stays
        if len(known) > 1:
            kept = "a task of this id is known to " + " and ".join(sorted(known))
        elif t is None:
            kept = "no task of this id in " + " or ".join(runtimes)
        elif state in ("rejected", "cancelled"):
            since = entered(runtimes[env], t, state, events)
        elif state == "accepted":
            try:
                a = accepted(runtimes[env], task)
                fetch(repo_dir, [a.ref])
                accepted_no, since = a.attempt_no, parse_time(a.accepted_at)
                landed, why = main.landed(task, change_id(git(repo_dir, "log", "-1", "--format=%B", a.commit)))
                kept = (f"its accepted result landed as {landed[:12]}; when it reached main is not on record" if landed
                        else "its accepted result is not on main" if why == "not on main" else why)
            except Refused as exc:
                kept = f"cannot tell which attempt was accepted: {exc}"
        for ref, n in sorted(refs, key=lambda x: x[1]):
            if state in ("rejected", "cancelled") and len(known) == 1:
                go, why = True, f"its task is {state}"
            elif state == "accepted" and len(known) == 1 and accepted_no > 0 and n != accepted_no:
                go, why = True, f"superseded: attempt {accepted_no} was accepted"
            elif kept:
                go, why = False, kept
            else:
                go, why = False, f"its task is {state}"
            if go:
                if since is None:
                    go, why = False, f"{why}; since when is not on record"
                elif (age := (now - since.timestamp()) / 86400) < KEEP_DAYS:
                    go, why = False, f"{why}; {age:.1f} of {KEEP_DAYS} days"
            out.append((ref, env, go, why))
    return out


def cmd_prunable(runtimes: dict[str, Runtime], ws: Path, now: float, out=None) -> int:
    out = out or sys.stdout
    total = deletable = 0
    for repo in PRUNE_REPOS:
        for ref, env, go, why in prunable(runtimes, ws / repo, now):
            total += 1
            deletable += go
            print(f"{repo}\t{ref}\t{env or '-'}\t{'delete' if go else 'keep'}\t{why}", file=out)
    print(f"merge_accepted: {deletable} of {total} agent/ branches would be deleted; nothing was", file=out)
    return 0


def apply(rt: Runtime, task_id: str, ws: Path, dest: Path | None, do_push: bool,
          run: Callable[[list[str], Path, dict[str, str]], int] = default_run) -> int:
    a, files, msg = plan(rt, task_id, ws)
    ok, why = may_push(a.repo)
    missing = [k for k in SUITE_NEEDS.get(a.repo, []) if not os.environ.get(k)]
    if missing:
        raise Refused(f"set {' and '.join(missing)} to the test database and Redis: {a.repo}'s CI runs its database tests, "
                      "and they would skip here")
    tree = build(a, msg, ws, dest or Path.home() / "agent-work" / "merge-accepted" / a.task)
    print(f"merge_accepted: built {git(tree, 'rev-parse', 'HEAD').strip()} in {tree} "
          f"(remove with git worktree remove for each worktree under {tree.parent})")
    checked, failed = run_suite(tree, a.repo, run)
    if failed:
        print("merge_accepted: the suite failed: " + "; ".join(failed) + ". Nothing pushed.", file=sys.stderr)
        return 1
    if not checked:
        print(f"merge_accepted: {a.repo} has no suite here: built, not verified. Nothing pushed.", file=sys.stderr)
        return 4
    print("merge_accepted: the suite and code-health passed")
    if not do_push:
        return 0
    if not ok:
        print(f"merge_accepted: {why}. Nothing pushed.", file=sys.stderr)
        return 3
    return push(tree)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--env", choices=sorted(BASES), default="prod")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("prunable")
    p = sub.add_parser("plan")
    p.add_argument("task")
    p = sub.add_parser("apply")
    p.add_argument("task")
    p.add_argument("--dir", help="where the worktrees go (default ~/agent-work/merge-accepted/<task>)")
    p.add_argument("--push", action="store_true", help="push with push-main.sh once the suite passes")
    args = ap.parse_args(argv)
    ws = workspace()
    try:
        if args.cmd == "prunable":
            return cmd_prunable({env: Runtime(env) for env in ("prod", "stg")}, ws, time.time())
        rt = Runtime(args.env)
        if args.cmd == "list":
            return cmd_list(rt, ws)
        if args.cmd == "apply":
            return apply(rt, args.task, ws, Path(args.dir) if args.dir else None, args.push)
        a, files, msg = plan(rt, args.task, ws)
        ok, why = may_push(a.repo)
        print(f"{a.repo}: task {a.task} of {a.env} {a.mission}, attempt {a.attempt_no} {a.attempt} by {a.author}, "
              f"reviewed by {', '.join(a.reviewers) or 'nobody the records tie'}; commit {a.commit} ({a.ref})")
        print("files:\n  " + "\n  ".join(files))
        print(("may push: " if ok else "will not push: ") + why)
        print("message:\n" + msg)
        return 0
    except (Refused, OSError, urllib.error.URLError) as exc:
        print(f"merge_accepted: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
