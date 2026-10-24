#!/usr/bin/env python3
"""new-worktree.sh: make a registered worktree, end it, renew it (W-31 round 4, 4.6 S3;
CUT-lifecycle-2026-10-24.md §4.2). The record format and its states are in worktree_owner.py.

    new-worktree.sh <repo> <dir> <branch> --work W-n [--base REV] [--session ID]
                    [--purpose TEXT] [--cache-root [KIND:]REL]...
        git worktree add <dir> on <branch>: an existing branch is checked out
        (branch_created false), a new one is made from --base (default origin/main)
    new-worktree.sh <repo> <dir> --detach <rev> --work W-n [...]
    new-worktree.sh --end <dir> [--by WHO] [--reason TEXT]
        ended_at, so a sweep may remove it once its content has copies. A worktree with no
        record (one made before S3) gets one only with --work and --by: the person or
        thread that confirmed its work ended (D-L8)
    new-worktree.sh --renew <dir>     a use by its own session: the lease is renewed and an end voided
    new-worktree.sh --take <dir> --session ID [--host-session ID]
        hand the worktree to session ID as a new ownership generation: the old session's
        later end events match nothing; an end and a recorded foreign use are cleared
        (reviews 551 D2, 552 A3). The host session is --host-session, or the caller's
        CLAUDE_CODE_HOST_SESSION_ID when the caller is session ID, else recorded as unknown
        (empty: only the session id then ends it). A session that uses another session's
        worktree takes it first
    new-worktree.sh --show <dir>      the record and its state

--cache-root names a directory inside the worktree meant for a cache. With a KIND (go-build,
go-mod, npm, go-build-chain) the sweep checks its whole content against that layout; without
one (node_modules) a sweep keeps the worktree whenever the directory holds anything.

Registering makes the session markers directory (worktree_sessions.py) if it is missing: a
sweep cannot tell whether a session resumed without it, and keeps every ended worktree then.

<repo> is one of the repositories the lifecycle tools scan (agent-config/gitea-primary.txt
under WORKSPACE, or a clone directly under AGENT_WORK), by path or name. <dir> must lie
under AGENT_WORK (R7: no new worktrees in the workspace root) with no symlink below it.
--session defaults to CLAUDE_CODE_SESSION_ID; host_session is CLAUDE_CODE_HOST_SESSION_ID.

Exit 0 done, 1 refused or failed (the message says why), 2 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from typing import Dict, List, Optional

import worktree_owner as wo
import worktree_sessions as ws


def _git(cwd: str, *args: str, env: Dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", cwd, *args], env=env, capture_output=True, text=True)


def _fail(msg: str) -> int:
    print(f"new-worktree: {msg}", file=sys.stderr)
    return 1


def _resolve_repo(env: Dict[str, str], repo: str) -> str:
    repos, _ = wo.known_repos(env)
    cand = os.path.realpath(repo if os.sep in repo or repo.startswith(".") else os.path.join(wo.workspace(env), repo))
    for r in repos:
        if os.path.realpath(r) == cand:
            return r
    raise wo.OwnerError(f"{repo} is not a repository the lifecycle tools scan (the list file under WORKSPACE, "
                        "or a clone directly under AGENT_WORK): its worktrees would never be ended or swept")


def _check_dir(env: Dict[str, str], d: str) -> str:
    """The absolute target dir, under AGENT_WORK with no symlink or non-directory below it."""
    aw = wo.agent_work(env)
    absd = os.path.abspath(d)
    if not absd.startswith(aw + os.sep):
        raise wo.OwnerError(f"{d} is not under AGENT_WORK ({aw}): worktrees go to $AGENT_WORK/<lane>/ (R7)")
    cur = aw
    for comp in absd[len(aw) + 1:].split(os.sep):
        cur = os.path.join(cur, comp)
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            break
        if stat.S_ISLNK(st.st_mode):
            raise wo.OwnerError(f"{cur} is a symlink (not followed)")
        if not stat.S_ISDIR(st.st_mode):
            raise wo.OwnerError(f"{cur} is not a directory")
    if os.path.lexists(absd) and os.listdir(absd):
        raise wo.OwnerError(f"{absd} exists and is not empty")
    return absd


def create(env: Dict[str, str], a: argparse.Namespace) -> int:
    if not a.work or not wo.WORK_RE.match(a.work):
        return _fail("--work W-n, TD-n, BI-n or LANE-... is required")
    session = a.session or env.get("CLAUDE_CODE_SESSION_ID", "")
    if not wo.SESSION_RE.match(session):
        return _fail("--session is required (or CLAUDE_CODE_SESSION_ID): the hook ends a worktree by it")
    roots: List[Dict[str, object]] = []
    for r in a.cache_root or []:
        kind, _, rel = r.rpartition(":") if ":" in r.split("/")[0] else ("", "", r)
        if not wo.canonical_rel(rel) or (kind and kind not in wo.KINDS):
            return _fail(f"--cache-root {r!r} is not [KIND:]REL with a canonical path inside the worktree "
                         f"and KIND one of {', '.join(wo.KINDS)}")
        roots.append({"path": rel, "kind": kind or None})
    try:
        repo = _resolve_repo(env, a.repo)
        target = _check_dir(env, a.dir)
    except wo.OwnerError as e:
        return _fail(str(e))
    branch: Optional[str] = None
    created = False
    if a.detach:
        r = _git(repo, "rev-parse", "--verify", "--quiet", a.detach + "^{commit}", env=env)
        if r.returncode != 0:
            return _fail(f"--detach {a.detach}: not a commit in {repo}")
        base = r.stdout.strip()
        add = ["worktree", "add", "--detach", target, base]
    else:
        branch = a.branch
        if not branch or _git(repo, "check-ref-format", "--branch", branch, env=env).returncode != 0 or branch == "main":
            return _fail(f"{branch!r} is not a branch name new-worktree.sh may use")
        exists = _git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", env=env).returncode == 0
        if exists:
            base = _git(repo, "rev-parse", f"refs/heads/{branch}", env=env).stdout.strip()
            add = ["worktree", "add", target, branch]
        else:
            r = _git(repo, "rev-parse", "--verify", "--quiet", (a.base or "origin/main") + "^{commit}", env=env)
            if r.returncode != 0:
                return _fail(f"--base {a.base or 'origin/main'}: not a commit in {repo}")
            base = r.stdout.strip()
            add = ["worktree", "add", "-b", branch, target, base]
            created = True
    r = _git(repo, *add, env=env)
    if r.returncode != 0:
        return _fail(f"git {' '.join(add)}: {r.stderr.strip()}")
    try:
        admin, _ = wo.admin_of(target)
        rec = wo.new_record(a.work, session, env.get("CLAUDE_CODE_HOST_SESSION_ID", ""), a.purpose or "",
                            branch, created, base, roots, wo.now_ns(), wo.lease_hours(env))
        with wo.OwnerLock(admin, 30):
            wo.write_record(admin, rec)
        # the markers directory only: a marker says a session (re)started, which only SessionStart knows
        for p in ws.write_markers(env, [], wo.now_ns()):
            print(f"new-worktree: {p}; a sweep keeps every ended worktree until that directory exists", file=sys.stderr)
    except (wo.OwnerError, OSError) as e:
        # The worktree stands without a record: a sweep never removes it (no end evidence).
        return _fail(f"made {target} but could not register it: {e}; it stays until someone ends it by hand")
    print(f"new-worktree: {target} ({branch or 'detached at ' + base[:12]}) registered for {a.work}, session {session}")
    return 0


def _admin(d: str) -> str:
    return wo.admin_of(os.path.abspath(d))[0]


def end_or_renew(env: Dict[str, str], a: argparse.Namespace, which: str) -> int:
    d = {"end": a.end, "renew": a.renew, "take": a.take}[which]
    try:
        admin = _admin(d)
        with wo.OwnerLock(admin, 30):
            rec, _, bad = wo.read_record(admin)
            if bad:
                return _fail(f"{d}: {bad}")
            now = wo.now_ns()
            if rec is None:
                if which != "end" or not a.work or not a.by:
                    return _fail(f"{d} has no record (made before new-worktree.sh): --end with --work and --by "
                                 "records who confirmed its work ended; nothing else registers it")
                if not wo.WORK_RE.match(a.work):
                    return _fail("--work W-n, TD-n, BI-n or LANE-...")
                head = _git(d, "symbolic-ref", "--quiet", "--short", "HEAD", env=env)
                rec = wo.new_record(a.work, "unregistered", "", "registered at its end", head.stdout.strip() or None,
                                    False, "", [], now, wo.lease_hours(env))
                rec["registered_at_end"] = True
            if which == "end":
                by = a.by or f"new-worktree.sh --end ({env.get('USER', '')})"
                wo.end(rec, now, by, a.reason or "")
                if a.by:
                    rec.pop("foreign_use", None)  # a person confirmed the work ended
            elif which == "take":
                session = a.session or ""
                if not wo.SESSION_RE.match(session):
                    return _fail("--take needs --session: the session that takes the worktree")
                host = a.host_session or (env.get("CLAUDE_CODE_HOST_SESSION_ID", "")
                                          if env.get("CLAUDE_CODE_SESSION_ID") == session else "")
                if host and not wo.SESSION_RE.match(host):
                    return _fail("--host-session is not an id")
                wo.take(rec, now, session, host, wo.lease_hours(env))
            else:
                wo.renew(rec, now, wo.lease_hours(env))
            wo.write_record(admin, rec)
        if which == "end":
            ws.write_markers(env, [], now)  # the markers directory a sweep needs to judge any end
    except (wo.OwnerError, OSError) as e:
        return _fail(f"{d}: {e}")
    said = {"end": f"ended at {rec.get('ended_at')}", "renew": f"renewed until {rec.get('lease_until')}",
            "take": f"taken by session {rec.get('session')}"}
    print(f"new-worktree: {d} {said[which]}")
    return 0


def state_of(env: Dict[str, str], rec: Optional[Dict[str, object]], bad: Optional[str], now: float, grace: float,
             admin: str) -> str:
    """What a sweep would make of the record: in-use, ended, ended-recently, or another reason."""
    if bad:
        return "unusable"
    if rec is None:
        return "unregistered"
    hit = ws.foreign_problem(rec)
    if hit:
        return hit[0]
    code, _ = wo.end_evidence(rec, now, grace)
    if code == "not-ended":
        return "in-use"
    if code is None or code == "end-too-recent":
        hit = ws.session_problem(env, rec, admin)
        if hit:
            return hit[0]
    if code is None:
        return "ended"
    return "ended-recently" if code == "end-too-recent" else code


def show_one(env: Dict[str, str], a: argparse.Namespace) -> int:
    try:
        admin = _admin(a.show)
    except wo.OwnerError as e:
        return _fail(str(e))
    rec, _, bad = wo.read_record(admin)
    grace = wo.end_grace(env)
    print(json.dumps({"admin": admin, "state": state_of(env, rec, bad, wo.now_ts(), grace, admin), "problem": bad, "record": rec}, indent=1))
    return 0 if not bad else 1


def main(argv: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None) -> int:
    env = dict(os.environ if env is None else env)
    env.setdefault("GIT_OPTIONAL_LOCKS", "0")
    ap = argparse.ArgumentParser(prog="new-worktree.sh", description="Registered worktrees (see the module docstring).")
    ap.add_argument("repo", nargs="?")
    ap.add_argument("dir", nargs="?")
    ap.add_argument("branch", nargs="?")
    ap.add_argument("--detach", metavar="REV")
    ap.add_argument("--base", metavar="REV")
    ap.add_argument("--work")
    ap.add_argument("--session")
    ap.add_argument("--host-session")
    ap.add_argument("--purpose")
    ap.add_argument("--cache-root", action="append", metavar="REL")
    ap.add_argument("--end", metavar="DIR")
    ap.add_argument("--renew", metavar="DIR")
    ap.add_argument("--take", metavar="DIR")
    ap.add_argument("--show", metavar="DIR")
    ap.add_argument("--by")
    ap.add_argument("--reason")
    a = ap.parse_args(argv)
    modes = [m for m in ("end", "renew", "take", "show") if getattr(a, m)]
    if len(modes) > 1 or (modes and (a.repo or a.dir or a.branch)):
        ap.error("--end, --renew, --take and --show take only a worktree dir")
    if modes:
        return show_one(env, a) if modes[0] == "show" else end_or_renew(env, a, modes[0])
    if not a.repo or not a.dir or bool(a.branch) == bool(a.detach):
        ap.error("give <repo> <dir> and either <branch> or --detach <rev>")
    if a.detach and a.base:
        ap.error("--base is for a new branch, not --detach")
    try:
        return create(env, a)
    except wo.OwnerError as e:
        return _fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
