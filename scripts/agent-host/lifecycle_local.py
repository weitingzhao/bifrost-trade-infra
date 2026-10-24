#!/usr/bin/env python3
"""prune-merged-branches.sh --local-only: this machine's worktrees and local branches
(W-31 round 4, 4.6 S2; CUT-lifecycle-2026-10-24.md §2, §3 R5-R7, R11, R12, §4.3; reviews 539, 551).

    prune-merged-branches.sh --local-only [--repos "a b"]            report only (the default)
    prune-merged-branches.sh --local-only --apply [--repos "a b"]    archive, then remove
    prune-merged-branches.sh --local-only --offline                  report from remote-tracking
                                                                     refs, no network (never --apply)

It never pushes, fetches or calls gh: the remote is only read, with git ls-remote. Repositories:
agent-config/gitea-primary.txt under WORKSPACE, plus the real clones directly under AGENT_WORK
(bifrost-finance); a clone itself is never removed. What may go, and why the rest stays, is in
lifecycle_items.py and lifecycle_checks.py; bundles and run directories in lifecycle_bundles.py;
the guard, quarantine and what is still not protected in lifecycle_quarantine.py; records in
worktree_owner.py and worktree_sessions.py.

--apply: first move back any worktree an interrupted run left in quarantine. The backup root
must not overlap any worktree, admin dir or disk-guard cache root (else exit 4, nothing done).
Then per repository: read the remote's refs again; write the run directory
<backup root>/<machine>/<repo id>/<run id>/ with the unique bundle (commits no remote ref
reaches, whole history, restored once into an empty repository) and the redundant bundle
(everything else beyond main and tags), before anything goes; then for each worktree: its
record's flock, git worktree lock --reason lifecycle:<run>, every check again with a fresh
lsof, then the quarantine of lifecycle_quarantine.py; then each branch: the checks again, a
last read of the worktree list and its reflog, git update-ref -d <ref> <old sha>. A Git lock
someone else holds is never touched; a lifecycle:<run> lock a dead sweep left is released
when no process holds its record's flock. Last, redundant bundles past LIFECYCLE_BUNDLE_DAYS
whose heads the remote still holds are removed.

Environment: AGENT_WORK, WORKSPACE, BACKUP_ROOT (~/bifrost-backups/git-branches),
LIFECYCLE_MACHINE (host name), LIFECYCLE_WORKTREE_ROOTS (AGENT_WORK:WORKSPACE:TMPDIR),
LIFECYCLE_REPOS_FILE, LIFECYCLE_END_MIN_AGE_MIN (120), LIFECYCLE_BUNDLE_DAYS (90, never less),
LIFECYCLE_STATUS_DIR, LIFECYCLE_LOCK, LIFECYCLE_LSOF, LIFECYCLE_MOUNT (as disk-guard).
Exit 0 done, 1 a removal or archive step failed, 2 usage, 3 another sweep holds the machine
lock, 4 the configuration is unusable (an overlapping backup root included) or the report
cannot be written.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import secrets
import signal
import socket
import sys
import tempfile
import time
from typing import Dict, List, Optional, Tuple

import lifecycle_bundles as lb
import lifecycle_quarantine as lq
import worktree_owner as wo
from disk_guard_base import ConfigError, load_config, now_utc
from disk_guard_roots import OpenFiles, mount_points
from disk_guard_state import Lock, write_report
from lifecycle_checks import open_problem
from lifecycle_git import (GitError, commits_present, git, remote_refs, repo_id, repo_problem, without_copy,
                           worktree_list)
from lifecycle_items import Ctx, Item, classify_branches, classify_worktree, last_branch_check, recheck_branch, recheck_worktree

LOCK_PREFIX = "lifecycle:"


def _sweep_identity(env: Dict[str, str]) -> Dict[str, str]:
    """The author of the commits the sweep makes to archive an AUTO_MERGE tree."""
    return dict(env, GIT_AUTHOR_NAME="bifrost lifecycle sweep", GIT_AUTHOR_EMAIL="lifecycle@localhost.invalid",
                GIT_COMMITTER_NAME="bifrost lifecycle sweep", GIT_COMMITTER_EMAIL="lifecycle@localhost.invalid")


# Test seams, each a no-op here.
def _between_checks(ctx: Ctx, items: List[Item]) -> None:
    """After the archive is written, before the second checks."""


def _before_quarantine(ctx: Ctx, it: Item) -> None:
    """After a worktree's second check and lsof, before the journal entry and the move."""


def _in_quarantine(ctx: Ctx, it: Item, q: str) -> None:
    """After the move into quarantine, before the checks there."""


def _before_branch_delete(ctx: Ctx, it: Item) -> None:
    """After a branch's second check, before the last read and update-ref -d."""


class Settings:
    def __init__(self, env: Dict[str, str]) -> None:
        self.cfg = load_config(env)
        self.env = env
        home = env.get("HOME") or os.path.expanduser("~")
        self.workspace = wo.workspace(env)
        self.backup_root = os.path.abspath(env.get("BACKUP_ROOT", "").strip() or os.path.join(home, "bifrost-backups", "git-branches"))
        machine = env.get("LIFECYCLE_MACHINE", "").strip() or socket.gethostname().split(".")[0]
        self.machine = re.sub(r"[^A-Za-z0-9._-]", "_", machine) or "host"
        raw = env.get("LIFECYCLE_WORKTREE_ROOTS", "").strip()
        given = raw.split(":") if raw else [self.cfg.agent_work, self.workspace, env.get("TMPDIR", "").strip() or tempfile.gettempdir()]
        self.roots: List[Tuple[str, str]] = []
        for g in [x for x in given if x]:
            if not os.path.isabs(g) or not os.path.isdir(g):
                raise ConfigError(f"LIFECYCLE_WORKTREE_ROOTS: {g} is not an absolute directory")
            a, r = os.path.normpath(g), os.path.realpath(g)
            if r in ("/", os.path.realpath(home)):
                raise ConfigError(f"LIFECYCLE_WORKTREE_ROOTS: {g} is / or the home directory")
            self.roots.append((a, r))
        self.grace = wo.end_grace(env)
        try:
            self.days = float(env.get("LIFECYCLE_BUNDLE_DAYS", "").strip() or lb.MIN_DAYS)
        except ValueError:
            raise ConfigError("LIFECYCLE_BUNDLE_DAYS is not a number")
        if not self.days >= lb.MIN_DAYS or self.days == float("inf"):
            raise ConfigError(f"LIFECYCLE_BUNDLE_DAYS must be a number of at least {lb.MIN_DAYS}")
        self.guard = lq.Guard(self.backup_root, self.cfg.agent_work, self.cfg.registries)


def durable_of(env: Dict[str, str], repo: str, offline: bool) -> Tuple[List[str], List[str], Dict[str, object]]:
    """(durable shas present here, main and tags present here, a note for the report)."""
    refs = remote_refs(env, repo, offline)
    have = commits_present(env, repo, sorted(set(refs.values())))
    durable = sorted(s for s in set(refs.values()) if s in have)
    pre = sorted({s for r, s in refs.items() if s in have and (r == "refs/heads/main" or r.startswith("refs/tags/"))})
    note = {"source": "remote-tracking refs (offline: may be stale)" if offline else "git ls-remote origin",
            "refs": len(refs), "not_in_this_clone": len(set(refs.values()) - have)}
    return durable, pre, note


def _unlock_stale(env: Dict[str, str], repo: str, run_id: str, notes: List[str]) -> None:
    """Release lifecycle:<run> Git locks a dead sweep left; nobody else's lock is touched. A
    sweep holds the record's flock for as long as its Git lock stands, and the kernel drops
    the flock when the sweep dies: a flock still held means the lock is not stale."""
    for wt in worktree_list(env, repo):
        reason = wt.get("locked")
        if not (isinstance(reason, str) and reason.startswith(LOCK_PREFIX) and reason != LOCK_PREFIX + run_id):
            continue
        path = str(wt["path"])
        try:
            admin, _ = wo.admin_of(path)
            with wo.OwnerLock(admin, 0):
                git(env, repo, "worktree", "unlock", path)
        except (wo.OwnerError, OSError, GitError) as e:  # Busy: a live sweep (another lock dir) holds it
            notes.append(f"kept {reason} on {path}: {e}")
            continue
        notes.append(f"released {reason} on {path} (left by a sweep that is not running)")


def classify_repo(s: Settings, repo: str, lsof: OpenFiles, mounts: Optional[List[str]], offline: bool, apply: bool,
                  run_id: str) -> Dict[str, object]:
    env, rid = s.env, repo_id(repo)
    out: Dict[str, object] = {"repo": repo, "repo_id": rid, "items": [], "notes": []}
    notes: List[str] = out["notes"]  # type: ignore[assignment]
    try:
        bad = repo_problem(env, repo)
        if bad:
            out["problem"] = bad
            return out
        if apply:
            _unlock_stale(env, repo, run_id, notes)
        durable, pre, note = durable_of(env, repo, offline)
        out["remote"] = note
        wts = worktree_list(env, repo)
    except GitError as e:
        out["problem"] = f"{e}: nothing in this repository is removed"
        return out
    ctx = Ctx(env, repo, rid, durable, s.roots, time.time(), s.grace, lsof, mounts)
    items = [classify_worktree(ctx, wt) for wt in wts[1:] if not wt.get("bare")]
    out["paths"] = [str(wt["path"]) for wt in wts[1:]] + [i.admin for i in items if i.admin]
    try:
        items += classify_branches(ctx, wts, items)
    except GitError as e:
        notes.append(f"branches not read: {e}")
    out.update(items=items, ctx=ctx, prereqs=pre)
    return out


def apply_repo(s: Settings, plan: Dict[str, object], run_id: str, started: str) -> bool:
    """Archive, then remove. False when a step failed in a way the report must call a failure."""
    env, repo, rid = s.env, str(plan["repo"]), str(plan["repo_id"])
    items: List[Item] = plan["items"]  # type: ignore[assignment]
    cands = [i for i in items if (i.kind, i.action) in (("worktree", "remove"), ("branch", "delete"))]
    if not cands:
        return True
    try:
        durable, pre, _ = durable_of(env, repo, False)  # the remote may have dropped a ref meanwhile
    except GitError as e:
        for i in cands:
            i.keep("remote-unreadable", str(e))
        return True
    old: Ctx = plan["ctx"]  # type: ignore[assignment]
    ctx = Ctx(env, repo, rid, durable, s.roots, time.time(), s.grace, old.lsof, old.mounts)
    try:
        for i in cands:
            if without_copy(env, repo, [i.head], durable):
                i.keep("head-without-copy", "no longer reachable from the remote's refs")
            else:
                if i.auto_merge:  # a tree: archived as a commit no ref names, so it is unique
                    i.auto_merge_commit = git(_sweep_identity(env), repo, "commit-tree", i.auto_merge, "-m",
                                              f"lifecycle {run_id}: AUTO_MERGE of {i.name}").strip()
                i.archive = without_copy(env, repo, i.history(), durable)
        cands = [i for i in cands if i.action != "keep"]
        if not cands:
            return True
        run_dir = lb.new_run_dir(s.backup_root, s.machine, rid, run_id)
        s.guard.run_dirs.append(run_dir)
        bad = s.guard.problem(*[p for i in cands if i.kind == "worktree" for p in (i.name, i.admin)])
        if bad:
            raise lb.BundleError(bad[1])
        uniq = {c for i in cands for c in i.archive}  # each is an ancestor of a history sha in uniq
        unique = lb.make_bundle(env, repo, run_dir, run_id, "unique", [c for i in cands for c in i.history() if c in uniq], [])
        rest = [i.head for i in cands] + [c for i in cands for c in i.history() if c not in uniq]
        redundant = lb.make_bundle(env, repo, run_dir, run_id, "redundant", rest, pre)
        rows = [(i.kind, i.name, i.head, "") for i in cands]
        for b in (unique, redundant):
            for ref, sha in b["heads"].items():  # type: ignore[union-attr]
                rows.append((f"{b['kind']}-head", "", sha, ref))
        lb.write_refs(run_dir, rows)
        manifest: Dict[str, object] = {
            "schema": 1, "run_id": run_id, "created_at": started, "machine": s.machine, "repo": repo, "repo_id": rid,
            "restore": "unique: git init x && git -C x fetch <unique.bundle> 'refs/lifecycle-archive/*:refs/restored/*'; "
                       "redundant: the same in a clone of the remote; a worktree: git worktree add <path> <sha>; "
                       "a branch: git branch <name> <sha>",
            "planned": [i.public() for i in cands], "bundles": [unique, redundant],
        }
        lb.write_manifest(run_dir, manifest)
    except (GitError, lb.BundleError, OSError) as e:
        for i in cands:
            i.keep("archive-failed", str(e))
        plan["notes"].append(f"archive failed, nothing removed: {e}")  # type: ignore[union-attr]
        return False
    _between_checks(ctx, cands)
    ok = True
    for i in [c for c in cands if c.kind == "worktree"]:
        ok = _remove_worktree(s, ctx, i, run_id, run_dir) and ok
    for i in [c for c in cands if c.kind == "branch"]:
        ok = _delete_branch(ctx, i, run_dir) and ok
    manifest["done"] = [i.public() for i in cands]
    lb.write_manifest(run_dir, manifest)
    return ok


def _remove_worktree(s: Settings, ctx: Ctx, it: Item, run_id: str, run_dir: str) -> bool:
    env, repo, reason = ctx.env, ctx.repo, LOCK_PREFIX + run_id
    ok = True
    try:
        with wo.OwnerLock(it.admin, 2):
            try:
                git(env, repo, "worktree", "lock", "--reason", reason, it.name)
            except GitError as e:
                it.keep("locked", str(e))
                return True
            try:
                bad = (recheck_worktree(ctx, it, reason) or open_problem(OpenFiles(s.cfg), it.name)
                       or s.guard.problem(it.name, it.admin))
                if bad:
                    it.keep(*bad)
                else:
                    ok = lq.quarantine_remove(s.cfg, ctx, it, run_id, s.guard, _before_quarantine, _in_quarantine)
                    if it.action == "removed":
                        lb.log_action(run_dir, f"worktree-removed\t{it.name}\t{it.head}\t{it.branch or '(detached)'}")
            finally:
                _release(env, repo, it, reason)
    except wo.Busy as e:
        it.keep("record-busy", str(e))
    except wo.Gone as e:
        it.keep("gone", str(e))
    except (wo.OwnerError, OSError) as e:
        it.keep("record-unusable", str(e))
    return ok


def _release(env: Dict[str, str], repo: str, it: Item, reason: str) -> None:
    """Take this run's Git lock off the worktree at its own path, if it is still there."""
    try:
        for wt in worktree_list(env, repo):
            if str(wt["path"]) == it.name and wt.get("locked") == reason:
                git(env, repo, "worktree", "unlock", it.name)
    except GitError as e:
        it.detail += f"; could not release this run's Git lock: {e}"


def _delete_branch(ctx: Ctx, it: Item, run_dir: str) -> bool:
    if it.evidence is None or it.evidence.action != "removed":
        it.keep("worktree-kept", "the ended worktree that names it was not removed in this run")
        return True
    bad = recheck_branch(ctx, it)
    if bad:
        it.keep(*bad)
        return True
    _before_branch_delete(ctx, it)
    bad = last_branch_check(ctx, it)
    if bad:
        it.keep(*bad)
        return True
    try:
        git(ctx.env, ctx.repo, "update-ref", "-d", f"refs/heads/{it.name}", it.head)
    except GitError as e:
        it.keep("moved", f"update-ref refused (the branch is not at {it.head[:12]} any more): {e}")
        return True
    it.action, it.reason = "deleted", "update-ref -d with its old sha"
    lb.log_action(run_dir, f"branch-deleted\trefs/heads/{it.name}\t{it.head}")
    try:  # the upstream settings a later branch of this name would inherit
        git(ctx.env, ctx.repo, "config", "--remove-section", f"branch.{it.name}")
    except GitError:
        pass  # there was none
    return True


def _terminated(signum: int, frame: object) -> None:
    raise SystemExit(128 + signum)


def run(env: Dict[str, str], apply: bool, names: List[str], offline: bool) -> int:
    try:
        s = Settings(env)
        repos, notes = wo.known_repos(env)
    except (ConfigError, wo.OwnerError) as e:
        print(f"prune --local-only: {e}")
        return 4
    if names:
        repos = [r for r in repos if os.path.basename(r) in names]
        missing = set(names) - {os.path.basename(r) for r in repos}
        notes += [f"--repos {n}: not a repository this sweep scans" for n in sorted(missing)]
    run_id = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}-{secrets.token_hex(3)}"
    lock = Lock(s.cfg.lock_dir, run_id)
    got, why = lock.acquire()
    if not got:
        print(f"prune --local-only: {why}; this run stops")
        return 3
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _terminated)
    try:
        return _run_locked(s, repos, notes, apply, offline, run_id)
    finally:
        lock.release()
        signal.signal(signal.SIGTERM, previous)


def _run_locked(s: Settings, repos: List[str], notes: List[str], apply: bool, offline: bool, run_id: str) -> int:
    started = now_utc()
    lq.restore(s.env, repos, apply, notes)
    lsof = OpenFiles(s.cfg)
    points, err = mount_points(s.cfg)
    mounts = None if err else points
    if err:
        notes.append(f"mount table not read ({err}): cache roots with a kind are kept")
    plans = [classify_repo(s, r, lsof, mounts, offline, apply, run_id) for r in repos]
    bad = s.guard.problem(*[p for pl in plans for p in pl.get("paths", [])])  # type: ignore[union-attr]
    if bad:
        print(f"prune --local-only: BACKUP_ROOT {s.backup_root} cannot hold the archive: {bad[1]}; nothing is done")
        return 4
    ok = True
    expired: List[Dict[str, object]] = []
    for p in plans:
        base = os.path.join(s.backup_root, s.machine, str(p["repo_id"]))
        if apply and "problem" not in p:
            ok = apply_repo(s, p, run_id, started) and ok
            try:
                if os.path.isdir(base):
                    durable, _, _ = durable_of(s.env, str(p["repo"]), False)
                    expired += lb.expire(s.env, str(p["repo"]), base, durable, time.time(), s.days)
            except (GitError, lb.BundleError, OSError) as e:
                p["notes"].append(f"bundle expiry skipped: {e}")  # type: ignore[union-attr]
        try:
            left = lb.leftover_archive_refs(s.env, str(p["repo"]), run_id) if "problem" not in p else []
        except GitError:
            left = []
        if left:
            p["notes"].append(f"{len(left)} refs/lifecycle-archive refs a dead run left (they keep their objects; not removed)")  # type: ignore[union-attr]
    return _report(s, plans, notes, apply, offline, run_id, started, lsof, expired, ok)


def _report(s: Settings, plans: List[Dict[str, object]], notes: List[str], apply: bool, offline: bool, run_id: str,
            started: str, lsof: OpenFiles, expired: List[Dict[str, object]], ok: bool) -> int:
    counts: Dict[str, int] = {}
    reasons: Dict[str, int] = {}
    kept_cache = 0
    repos_out = []
    for p in plans:
        items: List[Item] = p.get("items", [])  # type: ignore[assignment]
        line: Dict[str, int] = {}
        for i in items:
            act = i.action if apply or i.action == "keep" else f"would-{i.action}"
            i.action = act
            counts[f"{i.kind}:{act}"] = counts.get(f"{i.kind}:{act}", 0) + 1
            key = f"{'branches' if i.kind == 'branch' else 'worktrees'}-{act}"
            line[key] = line.get(key, 0) + 1
            if act == "keep":
                reasons[f"{i.kind}:{i.reason}"] = reasons.get(f"{i.kind}:{i.reason}", 0) + 1
                kept_cache += sum(i.cache_bytes.values()) if i.reason.startswith("cache-root-") else 0
        repos_out.append({"repo": p["repo"], "repo_id": p["repo_id"], "problem": p.get("problem"), "remote": p.get("remote"),
                          "notes": p["notes"], "items": [i.public() for i in items]})
        text = " ".join(f"{k}={v}" for k, v in sorted(line.items()))
        print(f"prune --local-only: {os.path.basename(str(p['repo'])):32s} {p.get('problem') or text or 'nothing'}")
    report = {
        "schema": 1, "tool": "prune-merged-branches.sh --local-only (scripts/agent-host/lifecycle_local.py)",
        "run_id": run_id, "host": socket.gethostname(), "machine": s.machine,
        "mode": "apply" if apply else ("report-only, offline" if offline else "report-only"),
        "started_at": started, "finished_at": now_utc(), "roots": [r for r, _ in s.roots],
        "counts": counts, "kept_reasons": dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))),
        "kept_for_cache_roots_bytes": kept_cache,
        "lsof": {"ok": lsof.ok, "error": lsof.error}, "repos": repos_out, "bundles_expiry": expired,
        "notes": notes, "remote": "read with git ls-remote only; nothing is pushed or fetched",
    }
    path = os.path.join(s.cfg.status_dir, "lifecycle-local.json")
    try:
        os.makedirs(s.cfg.status_dir, exist_ok=True)
        write_report(path, report)
    except OSError as e:
        print(f"prune --local-only: cannot write {path}: {e}")
        return 4
    for k, v in sorted(counts.items()):
        print(f"prune --local-only:   {k}: {v}")
    if reasons:
        print("prune --local-only:   kept because: " + ", ".join(f"{k} {v}" for k, v in report["kept_reasons"].items()))  # type: ignore[union-attr]
    if kept_cache:
        print(f"prune --local-only:   kept for their cache roots: {kept_cache / (1 << 30):.2f} GiB")
    print(f"prune --local-only: report {path}" + ("" if apply else " (report only; --apply removes)"))
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None) -> int:
    env = dict(os.environ if env is None else env)
    args = list(sys.argv[1:] if argv is None else argv)
    apply = offline = False
    names: List[str] = []
    while args:
        a = args.pop(0)
        if a == "--local-only":
            continue
        if a in ("-h", "--help"):
            print(__doc__)
            return 0
        if a == "--apply":
            apply = True
        elif a == "--offline":
            offline = True
        elif a == "--repos" and args:
            names += args.pop(0).split()
        else:
            print(f"prune --local-only: {a} is not an option of --local-only (see --help)", file=sys.stderr)
            return 2
    if apply and offline:
        print("prune --local-only: --offline reads remote-tracking refs, which can be stale: report only, never with --apply", file=sys.stderr)
        return 2
    return run(env, apply, names, offline)


if __name__ == "__main__":
    sys.exit(main())
