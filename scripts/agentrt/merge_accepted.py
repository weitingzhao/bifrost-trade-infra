#!/usr/bin/env python3
"""TD-383, round 2's thin step: bring a result the agent runtime accepted into main, the way the
coordinator brought ten of them by hand on 2026-10-19 (M-9, M-12, M-30, M-31).

    python3 scripts/agentrt/merge_accepted.py --env prod list
    python3 scripts/agentrt/merge_accepted.py --env prod plan t_01M5B8BF2EM3SJQDKZ9E9TY2H8
    python3 scripts/agentrt/merge_accepted.py --env prod apply t_01M5B8BF2EM3SJQDKZ9E9TY2H8 [--push]
    python3 scripts/agentrt/merge_accepted.py prunable

list   every accepted implementation whose task is on no commit of its repository's main (by its
       Agentrt-Task trailer) and whose change is not empty; exit 1 when there is one. The check
       TD-383 asks for: on PROD each of them is merged, or someone says why not.
plan   what apply would do: the mission, the task, the attempt that was accepted and who wrote and
       reviewed it, the commit and the files it changes, whether apply may push it, the message.
prunable  every agent/ branch of bifrost-platform and bifrost-ui that TD-383's rule would delete,
       and why; it deletes nothing (who deletes, and how past Gitea's protection of agent/**, is the
       Owner's to decide: the plan named below). PROD and STG push to the same repositories, so a
       branch's task is looked up in both.
apply  in a fresh worktree of the repository's main (siblings beside it, as CI clones them): the
       accepted commit cherry-picked with its author (agentd) and its Agentrt-Task, Change-Id and
       Work trailers, the message saying which mission, task, attempt and reviewer it came from;
       then the repository's whole suite as CI runs it, and code-health. With --push, and only
       for a repository whose main deploys nothing by itself, push-main.sh then pushes it (the
       release window, fast-forward, code-health on that exact commit).

Where the line is (ADR §1, §5, §12.7: until the release queue, nothing reaches a running system
unattended). Pushing bifrost-platform's or bifrost-ui's main starts no release: a release of either
is its own step (STG by an Agent, PROD on the Owner's approval). Any other repository's main
reaches a running system or the rules by itself: bifrost-trade-infra's k8s/ is synced by Argo
(bifrost-platform-stg and -prod automatically) and its agent-config/ holds the rules; the others
feed their deliveries. For those apply builds and checks the commit and stops; the push is the
Owner's to decide (agent-config/work/multi-agent/PLAN-td383-merge-and-prune-2026-10-20.md).

It reads the runtime with the environment's viewer token from bifrost-trade-infra/.env and prints
no credential; it writes nothing to the platform. Git objects come from the workspace's own
checkouts (BIFROST_WORKSPACE, else ~/Desktop/stocks), whose working trees it does not touch.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
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

# Repositories whose main apply may push: pushing it deploys nothing by itself.
PUSHABLE = {"bifrost-platform", "bifrost-ui"}
WHY_NOT = {
    "bifrost-trade-infra": "Argo syncs its k8s/ (bifrost-platform-stg and -prod automatically) and its agent-config/ holds the rules",
}
WHY_NOT_DEFAULT = "its main feeds a delivery or a pinned release"

# Siblings a repository's suite needs beside it, as CI clones them at main.
SIBLINGS = {"bifrost-platform": ["bifrost-trade-infra", "bifrost-ui"]}


def _ci_env() -> dict[str, str]:
    """What the suite adds to the environment: CI's flags; the database tests run where the
    caller set AGENTRT_TEST_PG (else they skip, as they do outside CI)."""
    env = {"BIFROST_CI": "1", "GOTOOLCHAIN": "local"}
    if os.environ.get("AGENTRT_TEST_PG"):
        env["AGENTRT_TEST_REQUIRED"] = "1"
    return env


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
    "bifrost-ui": [
        ["npm", "ci", "--no-audit", "--no-fund"],
        ["npm", "run", "typecheck"],
        ["npm", "test"],
    ],
}
# Repositories push-main.sh scans with code-health (its GATED list).
CODE_HEALTH = {"bifrost-platform", "bifrost-trade-frontend", "bifrost-research", "bifrost-trade-api", "bifrost-trade-core",
               "bifrost-trade-worker"}

TRAILER = re.compile(r"^([A-Za-z][A-Za-z0-9-]*): (.*)$")
GENERIC_SUBJECT = re.compile(r"^agentrt: t_[0-9A-Z]{26} attempt \d+$")


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
    """GET of the agent runtime's read routes."""

    def __init__(self, env: str, get: Callable[[str], object] | None = None):
        self.env = env
        if get is None:
            base, tok = BASES[env], token(env)

            def get(path: str) -> object:
                req = urllib.request.Request(base + "/api/v1/agentrt/" + path, headers={"Authorization": "Bearer " + tok})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.load(resp)
        self._get = get

    def get(self, path: str, **query: str) -> object:
        return self._get(path + ("?" + urllib.parse.urlencode(query) if query else ""))

    def task(self, task_id: str) -> dict:
        return self.get("tasks/" + urllib.parse.quote(task_id))

    def find_task(self, task_id: str) -> dict | None:
        """The task, or None when this runtime has none of that id."""
        try:
            return self.task(task_id)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def attempt(self, attempt_id: str) -> dict:
        return self.get("attempts/" + urllib.parse.quote(attempt_id))

    def mission(self, mission_id: str) -> dict | None:
        try:
            return self.get("missions/" + urllib.parse.quote(mission_id))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

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
        """Every mission, M-1 up: they are numbered without gaps."""
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
    reviewers: list[str] = field(default_factory=list)
    accepted_at: str = ""


def accepted(rt: Runtime, task_id: str) -> Accepted:
    """What the runtime records of an accepted implementation: the attempt its passing review
    accepted (verification_recorded on the task, method review, verdict pass), the executors of
    its accepted reviews, and when it was accepted."""
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
    # The review whose pass accepted it: its task is accepted in the transaction that records the
    # pass. Any accepted review of the task when the events carry no transaction.
    txid = passes[-1].get("txid")
    reviews = {e["task_id"] for e in events if e.get("event_type") == "task_state_changed" and e.get("task_id") != task_id
               and (e.get("body_json") or {}).get("to") == "accepted" and txid is not None and e.get("txid") == txid}
    if not reviews:
        reviews = {x["task_id"] for x in rt.tasks(mission) if x.get("subject_task_id") == task_id and x.get("role") == "review"
                   and x.get("state") == "accepted"}
    reviewers: list[str] = []
    for e in events:
        if e.get("event_type") == "attempt_leased" and e.get("task_id") in reviews:
            who = (e.get("body_json") or {}).get("executor", "")
            if who:
                reviewers = [x for x in reviewers if x != who] + [who]
    reviewers = reviewers[-1:]  # the review's last attempt is the one whose result was used
    m = rt.mission(mission) or {}
    label = m.get("work_id") or first_words(m.get("title") or "", 60)
    return Accepted(env=rt.env, task=task_id, title=t.get("title") or "", repo=repo, base=t.get("base_commit") or "",
                    mission=mission, mission_label=label, attempt=attempt_id, attempt_no=int(a.get("attempt_no") or 0),
                    author=a.get("executor_actor_id") or "", ref=a["pushed_ref"], commit=a["pushed_commit"],
                    reviewers=reviewers, accepted_at=at[-1] if at else "")


def first_words(text: str, n: int) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= n else line[: n - 1].rstrip() + "…"


def minute(at: str) -> str:
    """2026-10-20T00:02:41.123456+00:00 → 2026-10-20 00:02Z."""
    try:
        d = datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", at.replace("Z", "+00:00")))
    except ValueError:
        return at or "at a time not on record"
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%MZ")


# ── git ───────────────────────────────────────────────────────────────────────

def git(repo_dir: Path, *args: str, check: bool = True, env: dict[str, str] | None = None) -> str:
    full = {**os.environ, **(env or {})}
    r = subprocess.run(["git", "-C", str(repo_dir), "-c", "core.hooksPath=/dev/null", *args], capture_output=True,
                       text=True, env=full)
    if check and r.returncode != 0:
        raise Refused(f"git {' '.join(args)} in {repo_dir}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def workspace() -> Path:
    return Path(os.environ.get("BIFROST_WORKSPACE") or Path.home() / "Desktop" / "stocks")


def on_main(repo_dir: Path) -> dict[str, str]:
    """The tasks on main of a repository, by their Agentrt-Task trailer: task → commit."""
    out: dict[str, str] = {}
    log = git(repo_dir, "log", "origin/main", "--format=%H%x00%(trailers:key=Agentrt-Task,valueonly,separator=%x2C)%x1e")
    for rec in log.split("\x1e"):
        sha, _, tasks = rec.strip().partition("\x00")
        for task in filter(None, (x.strip() for x in tasks.split(","))):
            out.setdefault(task, sha)
    return out


def fetch(repo_dir: Path, refs: list[str]) -> None:
    git(repo_dir, "fetch", "--quiet", "--no-tags", "origin", "main", *refs)


def change(repo_dir: Path, a: Accepted) -> list[str]:
    """The files the accepted commit changes; it must be one commit on its task's base."""
    if git(repo_dir, "cat-file", "-t", a.commit, check=False).strip() != "commit":
        raise Refused(f"commit {a.commit} of {a.ref} is not in {repo_dir}")
    parents = git(repo_dir, "rev-list", "--parents", "-n", "1", a.commit).split()[1:]
    if len(parents) != 1 or (a.base and parents[0] != a.base):
        raise Refused(f"{a.commit} is not one commit on its task's base {a.base or '(none)'}: merge it by hand")
    return [p for p in git(repo_dir, "diff", "--name-only", parents[0], a.commit).splitlines() if p]


def message(original: str, a: Accepted) -> str:
    """The accepted commit's message with where it came from said before its trailers, a
    cherry-pick line, and TD-383 in its Work trailer; Agentrt-Task and Change-Id as they were."""
    paragraphs = original.strip("\n").split("\n\n")
    last = paragraphs[-1].split("\n") if len(paragraphs) > 1 else []
    if not last or not all(TRAILER.match(ln) for ln in last):
        raise Refused(f"the commit of task {a.task} ends in no trailers")
    body, trailers = "\n\n".join(paragraphs[:-1]).split("\n"), last
    if not any(ln.startswith("Agentrt-Task: ") for ln in trailers) or not any(ln.startswith("Change-Id: ") for ln in trailers):
        raise Refused(f"the commit of task {a.task} lacks its Agentrt-Task or Change-Id trailer")
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
    reviewed = "reviewed by " + " and ".join(a.reviewers) if a.reviewers else "reviewed"
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
        return True, f"pushing {repo} main starts no release"
    return False, f"pushing {repo} main is the Owner's to decide: {WHY_NOT.get(repo, WHY_NOT_DEFAULT)}"


def plan(rt: Runtime, task_id: str, ws: Path) -> tuple[Accepted, list[str], str]:
    a = accepted(rt, task_id)
    repo_dir = ws / a.repo
    fetch(repo_dir, [a.ref])
    landed = on_main(repo_dir).get(task_id)
    if landed:
        raise Refused(f"task {task_id} is already on {a.repo} main as {landed[:12]}")
    files = change(repo_dir, a)
    if not files:
        raise Refused(f"the accepted commit of task {task_id} changes nothing: nothing to merge")
    return a, files, message(git(repo_dir, "log", "-1", "--format=%B", a.commit), a)


def build(a: Accepted, msg: str, ws: Path, dest: Path) -> Path:
    """The merge commit on a fresh worktree of main at dest/<repo>, siblings beside it."""
    repo_dir = ws / a.repo
    if dest.exists():
        raise Refused(f"{dest} exists: remove it or choose another --dir")
    dest.mkdir(parents=True)
    for sib in SIBLINGS.get(a.repo, []):
        git(ws / sib, "fetch", "--quiet", "--no-tags", "origin", "main")
        git(ws / sib, "worktree", "add", "--quiet", "--detach", str(dest / sib), "origin/main")
    tree = dest / a.repo
    git(repo_dir, "worktree", "add", "--quiet", "--detach", str(tree), "origin/main")
    r = subprocess.run(["git", "-C", str(tree), "-c", "core.hooksPath=/dev/null", "cherry-pick", "--allow-empty-message", a.commit],
                       capture_output=True, text=True)
    if r.returncode != 0:
        git(tree, "cherry-pick", "--abort", check=False)
        raise Refused(f"the accepted commit does not apply on {a.repo} main: {r.stdout.strip()} {r.stderr.strip()}".strip())
    (dest / "MESSAGE").write_text(msg)
    git(tree, "commit", "--amend", "--quiet", "-F", str(dest / "MESSAGE"))
    lineage = INFRA / "agent-config" / "scripts" / "git-hooks" / "lineage.sh"
    if lineage.is_file() and (os.environ.get("CLAUDE_CODE_HOST_SESSION_ID") or os.environ.get("CLAUDE_CODE_SESSION_ID")):
        # The merging thread, as a hook would add it in a checkout with hooks.
        msg_file = dest / "MESSAGE"
        msg_file.write_text(git(tree, "log", "-1", "--format=%B"))
        subprocess.run(["sh", str(lineage), "prepare-commit-msg", str(msg_file), "message"], cwd=tree, check=True)
        git(tree, "commit", "--amend", "--quiet", "-F", str(msg_file))
    return tree


def run_suite(tree: Path, repo: str, run: Callable[[list[str], Path, dict[str, str]], int]) -> list[str]:
    """The repository's suite and code-health on the tree; the names of the steps that failed."""
    failed = []
    env = _ci_env()
    for cmd in SUITES.get(repo, []):
        if run(cmd, tree, env) != 0:
            failed.append(" ".join(cmd))
    if repo in CODE_HEALTH:
        scan = INFRA / "agent-config" / "scripts" / "code-health" / "scan.sh"
        if run(["bash", str(scan), "--root", str(tree.parent), "--repo", repo], tree, env) != 0:
            failed.append("code-health")
    return failed


def default_run(cmd: list[str], cwd: Path, env: dict[str, str]) -> int:
    print("merge_accepted: $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, env={**os.environ, **env}).returncode


def push(tree: Path) -> None:
    subprocess.run(["bash", str(INFRA / "scripts" / "release" / "push-main.sh"), str(tree), "HEAD"], check=True)


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_list(rt: Runtime, ws: Path, out=None) -> int:
    """Accepted implementations not on main, by repository; exit 1 when there is one."""
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
        landed = on_main(repo_dir)
        for m, t in found[repo]:
            if t["task_id"] in landed:
                continue
            try:
                a = accepted(rt, t["task_id"])
                fetch(repo_dir, [a.ref])
                if not change(repo_dir, a):
                    continue  # an empty change: nothing to bring
                what = f"attempt {a.attempt_no} ({a.author}) {a.commit[:12]}"
            except Refused as exc:
                what = f"cannot tell: {exc}"
            missing += 1
            print(f"{repo}\t{m}\t{t['task_id']}\t{what}\t{first_words(t.get('title') or '', 80)}", file=out)
    print(f"merge_accepted: {missing} accepted implementation(s) of {rt.env} not on main", file=out)
    return 1 if missing else 0


KEEP_DAYS = 7  # TD-383: an attempt branch goes 7 days after its task's end or its attempt's
AGENT_REF = re.compile(r"^refs/heads/agent/(t_[0-9A-Z]{26})/a([0-9]+)$")
PRUNE_REPOS = ("bifrost-platform", "bifrost-ui")


def prunable(runtimes: dict[str, Runtime], repo_dir: Path, now: float) -> list[tuple[str, str, bool, str]]:
    """Each agent/ branch of the repository: (ref, the environment that knows its task, whether
    TD-383's rule deletes it, why). Deleted, once its head is KEEP_DAYS old: a branch of a task
    rejected or cancelled; of an accepted task on main (by its Agentrt-Task trailer); of an
    accepted task, an attempt other than the accepted one (superseded). Kept: a task still open,
    an accepted result not on main, a task neither runtime knows, a head younger than that."""
    heads = {}
    for line in git(repo_dir, "ls-remote", "--heads", "origin", "refs/heads/agent/*").splitlines():
        sha, _, ref = line.partition("\t")
        if AGENT_REF.match(ref):
            heads[ref] = sha
    if heads:
        git(repo_dir, "fetch", "--quiet", "--no-tags", "origin", "main", *sorted(heads))
    landed = on_main(repo_dir)
    by_task: dict[str, list[tuple[str, int]]] = {}
    for ref in heads:
        m = AGENT_REF.match(ref)
        by_task.setdefault(m.group(1), []).append((ref, int(m.group(2))))
    out = []
    for task, refs in sorted(by_task.items()):
        env, t = "", None
        for name, rt in runtimes.items():
            if (t := rt.find_task(task)) is not None:
                env = name
                break
        accepted_no = 0
        if t is not None and t.get("state") == "accepted" and task not in landed:
            try:
                accepted_no = accepted(runtimes[env], task).attempt_no
            except Refused:
                accepted_no = -1  # cannot tell which attempt was accepted: keep them all
        for ref, n in sorted(refs, key=lambda x: x[1]):
            age = (now - int(git(repo_dir, "log", "-1", "--format=%ct", heads[ref]).strip() or 0)) / 86400
            state = (t or {}).get("state", "")
            if t is None:
                go, why = False, "no task of this id in " + " or ".join(runtimes)
            elif state in ("rejected", "cancelled"):
                go, why = True, f"its task is {state}"
            elif state == "accepted" and task in landed:
                go, why = True, f"its task is accepted and on main as {landed[task][:12]}"
            elif state == "accepted" and accepted_no > 0 and n != accepted_no:
                go, why = True, f"superseded: attempt {accepted_no} was accepted"
            elif state == "accepted":
                go, why = False, "its accepted result is not on main" if accepted_no >= 0 else "cannot tell which attempt was accepted"
            else:
                go, why = False, f"its task is {state}"
            if go and age < KEEP_DAYS:
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
    if args.cmd == "prunable":
        import time
        return cmd_prunable({env: Runtime(env) for env in ("prod", "stg")}, ws, time.time())
    rt = Runtime(args.env)
    try:
        if args.cmd == "list":
            return cmd_list(rt, ws)
        a, files, msg = plan(rt, args.task, ws)
        ok, why = may_push(a.repo)
        print(f"{a.repo}: task {a.task} of {a.env} {a.mission}, attempt {a.attempt_no} {a.attempt} by {a.author}, "
              f"reviewed by {', '.join(a.reviewers) or 'nobody on record'}; commit {a.commit} ({a.ref})")
        print("files:\n  " + "\n  ".join(files))
        print(("may push: " if ok else "will not push: ") + why)
        print("message:\n" + msg)
        if args.cmd == "plan":
            return 0
        dest = Path(args.dir) if args.dir else Path.home() / "agent-work" / "merge-accepted" / a.task
        tree = build(a, msg, ws, dest)
        print(f"merge_accepted: built {git(tree, 'rev-parse', 'HEAD').strip()} in {tree}")
        failed = run_suite(tree, a.repo, default_run)
        if failed:
            print("merge_accepted: the suite failed: " + "; ".join(failed) + ". Nothing pushed.", file=sys.stderr)
            return 1
        print("merge_accepted: the suite and code-health passed")
        if not args.push:
            return 0
        if not ok:
            print(f"merge_accepted: {why}. Nothing pushed.", file=sys.stderr)
            return 3
        push(tree)
        return 0
    except Refused as exc:
        print(f"merge_accepted: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
