"""The sweep's items: classify registered roots, report unregistered ones, and remove under
the machine lock with a second full check after the rename (disk-guard, W-31 4.6 S1;
review 539 F4).
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import socket
import stat
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from disk_guard_base import CACHE_NAMES, Config, Problem, QUARANTINE, _first, _join, _under, gib, now_utc
from disk_guard_layout import _du, detect, validate
from disk_guard_roots import Entry, OpenFiles, check_git, check_policy, expand


# Test seam: called with the quarantined items after the renames and before the second
# check, so a test can play another session writing in between (review 539 F4).
between_check_and_delete: Optional[Callable[[list], None]] = None


@dataclass
class Item:
    path: str
    source: str
    kind: Optional[str]
    policy: Optional[str]
    action: str = "keep"
    reason: str = ""
    detail: str = ""
    bytes: int = 0
    bytes_complete: bool = False
    layout: Optional[str] = None
    run_done: Optional[bool] = None
    entry: Optional[Entry] = field(default=None, repr=False)
    leftover: Optional[str] = None

    def keep(self, p: Problem) -> "Item":
        self.action, self.reason, self.detail = "keep", p.code, p.detail
        return self

    def public(self) -> Dict[str, object]:
        d = {k: getattr(self, k) for k in ("path", "source", "kind", "policy", "action", "reason", "detail", "bytes", "bytes_complete", "layout", "run_done", "leftover")}
        return {k: v for k, v in d.items() if v not in (None, "")}


def registered_items(cfg: Config, entries: List[Entry]) -> List[Item]:
    by_path: Dict[str, Item] = {}
    order: List[str] = []
    for entry in entries:
        for c in expand(cfg.agent_work, entry):
            it = Item(c.rel, entry.source, entry.kind, entry.policy, entry=entry, leftover=c.leftover)
            if c.problem:
                it.keep(c.problem)
            elif c.missing:
                it.keep(Problem("missing", "the registered root does not exist"))
            prev = by_path.get(c.rel)
            if prev is None:
                by_path[c.rel] = it
                order.append(c.rel)
            elif (prev.kind, prev.policy) != (entry.kind, entry.policy) and not prev.reason and not it.reason:
                prev.keep(Problem("registry-conflict", f"also registered as {entry.kind} {entry.policy} at {entry.source}"))
    items = [by_path[p] for p in order]
    for a in items:
        for b in items:
            if a is not b and _under(b.path, a.path):
                for x in (a, b):
                    if not x.reason:
                        x.keep(Problem("registry-overlap", f"{a.path} contains {b.path}: register one or the other"))
    for it in items:
        if it.reason:
            continue
        for ex in cfg.exclude:
            if _under(it.path, ex):
                it.keep(Problem("excluded", f"{ex} is managed by its own owner (LIFECYCLE_EXCLUDE)"))
        for own in (cfg.lock_dir, cfg.status_dir):
            if _under(os.path.join(cfg.agent_work, it.path), own):
                it.keep(Problem("excluded", "the sweep's own lock or status directory"))
    return items


def classify(cfg: Config, it: Item, lsof: OpenFiles, now: float) -> None:
    if it.reason:
        return
    assert it.entry is not None and it.kind is not None
    path = os.path.join(cfg.agent_work, it.path)
    try:
        w = validate(path, it.kind)
    except Problem as p:
        it.bytes = _du(path)
        it.keep(p)
        return
    it.bytes, it.bytes_complete, it.layout = w.bytes, True, it.kind
    try:
        if it.entry.policy == "run.done":
            it.run_done = os.path.isfile(os.path.join(cfg.agent_work, it.path.split("/", 1)[0], "run.done"))
        check_policy(cfg, it.entry, it.path, w, now)
        if it.entry.cap_bytes is not None and w.bytes <= it.entry.cap_bytes:
            raise Problem("under-cap", f"{gib(w.bytes)} <= cap {gib(it.entry.cap_bytes)}")
        if it.leftover:
            # renamed by a sweep that died: git judges the name it had
            check_git(cfg, path, tracked_only=True)
            check_git(cfg, os.path.join(cfg.agent_work, it.path.rsplit(QUARANTINE, 1)[0]), tracked_only=True)
        else:
            check_git(cfg, path)
        if not lsof.ok:
            raise Problem("open-files-unknown", lsof.error)
        hit = lsof.under(path)
        if hit:
            raise Problem("open-files", "a process has a file open under it")
    except Problem as p:
        it.keep(p)
        return
    it.action = "prune" if it.entry.cap_bytes is not None else "delete"
    it.reason = "pruned-over-cap" if it.action == "prune" else "registered-and-ended"
    it.detail = f"{it.kind} layout checked in full ({w.files} files)"


def discovered_items(cfg: Config, registered: List[Item]) -> List[Item]:
    """Caches found by name that nobody registered: reported so they can be registered."""
    taken = [it.path for it in registered]
    out: List[Item] = []
    seen = set()

    def add(rel: str, owner_done: Optional[bool]) -> None:
        if rel in seen or any(_under(rel, t) or _under(t, rel) for t in taken):
            return
        seen.add(rel)
        p = os.path.join(cfg.agent_work, rel)
        it = Item(rel, "discovered", None, None, run_done=owner_done)
        try:
            st = os.lstat(p)
        except OSError as e:
            out.append(it.keep(Problem("unreadable", e.strerror or str(e))))
            return
        if stat.S_ISLNK(st.st_mode):
            out.append(it.keep(Problem("unregistered", "a symlink (not followed)")))
            return
        if not stat.S_ISDIR(st.st_mode):
            it.bytes, it.bytes_complete = st.st_blocks * 512, True
            out.append(it.keep(Problem("unregistered", "a file, not a cache")))
            return
        kind, problem, size = detect(p)
        it.layout, it.bytes = kind, size
        if problem is None:
            it.bytes_complete = True
            hint = f"layout {kind} confirmed in full"
            if owner_done:
                hint += ", owner has run.done"
            out.append(it.keep(Problem("unregistered", hint + ": the sweep removes registered roots only")))
        else:
            out.append(it.keep(Problem("unregistered", f"layout {kind or 'unknown'}: {problem.code} {problem.detail}".strip())))

    for pattern in cfg.discover:
        segs = pattern.split("/")
        for owner in _glob_dirs(cfg.agent_work, segs):
            if any(_under(owner, ex) for ex in cfg.exclude):
                continue
            done = os.path.isfile(os.path.join(cfg.agent_work, owner, "run.done"))
            try:
                names = sorted(os.listdir(os.path.join(cfg.agent_work, owner)))
            except OSError:
                continue
            for n in names:
                if n in CACHE_NAMES:
                    add(f"{owner}/{n}", done)
    shared = os.path.join(cfg.agent_work, ".cache")
    if os.path.isdir(shared) and not os.path.islink(shared):
        try:
            for n in sorted(os.listdir(shared)):
                add(f".cache/{n}", None)
        except OSError as e:
            out.append(Item(".cache", "discovered", None, None).keep(Problem("unreadable", e.strerror or str(e))))
    return out


def _glob_dirs(base: str, segs: List[str]) -> List[str]:
    found: List[str] = []

    def rec(abs_dir: str, rel_dir: str, i: int) -> None:
        try:
            names = sorted(os.listdir(abs_dir))
        except OSError:
            return
        for n in names:
            if QUARANTINE in n or not fnmatch.fnmatchcase(n, segs[i]):
                continue
            p = os.path.join(abs_dir, n)
            if os.path.islink(p) or not os.path.isdir(p):
                continue
            rel = _join(rel_dir, n)
            if i == len(segs) - 1:
                found.append(rel)
            else:
                rec(p, rel, i + 1)

    rec(base, "", 0)
    return found


def remove_tree(top: str, dev: int) -> None:
    st = os.lstat(top)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise OSError(f"{top}: not a directory")
    if st.st_dev != dev:
        raise OSError(f"{top}: another filesystem")
    if (st.st_mode & stat.S_IRWXU) != stat.S_IRWXU:
        os.chmod(top, stat.S_IMODE(st.st_mode) | stat.S_IRWXU)
    for n in os.listdir(top):
        p = os.path.join(top, n)
        est = os.lstat(p)
        if stat.S_ISDIR(est.st_mode):
            remove_tree(p, dev)
        else:
            os.unlink(p)
    os.rmdir(top)


def _restore(cfg: Config, orig: str, q: str) -> str:
    if q == orig:
        return ""
    if os.path.lexists(orig):
        return f"; left as {os.path.relpath(q, cfg.agent_work)} because {os.path.relpath(orig, cfg.agent_work)} exists again"
    try:
        os.rename(q, orig)
    except OSError as e:
        return f"; left as {os.path.relpath(q, cfg.agent_work)}: rename back failed ({e.strerror or e})"
    return "; renamed back"


def apply_items(cfg: Config, run_id: str, items: List[Item], lsof_first: OpenFiles) -> None:
    deletes = [it for it in items if it.action == "delete"]
    prunes = [it for it in items if it.action == "prune"]
    staged: List[Tuple[Item, str, str]] = []
    for it in deletes:
        cur = os.path.join(cfg.agent_work, it.path)
        if it.leftover:
            base = it.path.rsplit(QUARANTINE, 1)[0]
            staged.append((it, os.path.join(cfg.agent_work, base), cur))
            continue
        q = cur + QUARANTINE + run_id
        try:
            os.rename(cur, q)
        except OSError as e:
            it.keep(Problem("rename-failed", e.strerror or str(e)))
            continue
        staged.append((it, cur, q))
    if between_check_and_delete is not None:
        between_check_and_delete([(it, orig, q) for it, orig, q in staged])
    lsof = OpenFiles(cfg) if (staged or prunes) else lsof_first
    now = time.time()
    for it, orig, q in staged:
        assert it.entry is not None and it.kind is not None
        try:
            w = validate(q, it.kind)
            check_policy(cfg, it.entry, it.path, w, now)
            check_git(cfg, orig, tracked_only=True)
            if not lsof.ok:
                raise Problem("open-files-unknown", lsof.error)
            if lsof.under(q, orig):
                raise Problem("open-files", "a process has a file open under it")
        except Problem as p:
            it.keep(Problem("recheck-" + p.code, p.detail + _restore(cfg, orig, q)))
            continue
        try:
            remove_tree(q, w.dev)
        except OSError as e:
            it.keep(Problem("delete-error", f"{e}; what is left stays at {os.path.relpath(q, cfg.agent_work)}"))
            continue
        it.action = "deleted"
    for it in prunes:
        assert it.entry is not None and it.kind is not None
        path = os.path.join(cfg.agent_work, it.path)
        try:
            w = validate(path, it.kind)
            check_git(cfg, path, tracked_only=True)
            if not lsof.ok:
                raise Problem("open-files-unknown", lsof.error)
            if lsof.under(path):
                raise Problem("open-files", "a process has a file open under it")
        except Problem as p:
            it.keep(Problem("recheck-" + p.code, p.detail))
            continue
        ok, msg = run_cache_tool(cfg, it.kind, path)
        if not ok:
            it.keep(Problem("tool-failed", msg))
            continue
        it.action, it.detail = "pruned", f"{gib(w.bytes)} -> {gib(_du(path))} ({msg})"


def run_cache_tool(cfg: Config, kind: str, root: str) -> Tuple[bool, str]:
    env = dict(cfg.env)
    env.update(GOTOOLCHAIN="local", GOFLAGS="")
    if kind == "go-build":
        tool, args, env["GOCACHE"] = "go", ["clean", "-cache"], root
    elif kind == "go-mod":
        tool, args, env["GOMODCACHE"] = "go", ["clean", "-modcache"], root
    else:
        tool, args, env["npm_config_cache"] = "npm", ["cache", "clean", "--force"], root
    exe = shutil.which(tool, path=env.get("PATH"))
    if not exe:
        return False, f"{tool} not found"
    try:
        r = subprocess.run([exe, *args], env=env, cwd=os.path.dirname(root), capture_output=True, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"{tool} {' '.join(args)}: {e}"
    if r.returncode != 0:
        return False, f"{tool} {' '.join(args)} exit {r.returncode}: {_first(r.stderr)}"
    return True, f"{tool} {' '.join(args)}"


class Lock:
    def __init__(self, path: str, run_id: str) -> None:
        self.path = path
        self.run_id = run_id
        self.held = False

    def _owner(self) -> Optional[Dict[str, object]]:
        try:
            with open(os.path.join(self.path, "owner"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def acquire(self) -> Tuple[bool, str]:
        try:
            os.mkdir(self.path)
        except FileExistsError:
            owner = self._owner()
            stale = False
            if owner and owner.get("host") == socket.gethostname():
                try:
                    os.kill(int(owner.get("pid", 0)), 0)  # type: ignore[arg-type]
                except ProcessLookupError:
                    stale = True
                except (PermissionError, ValueError, OverflowError):
                    stale = False
            elif owner is None:
                try:
                    stale = time.time() - os.lstat(self.path).st_mtime > 6 * 3600
                except OSError:
                    stale = False
            if not stale:
                who = f"run {owner.get('run_id')} pid {owner.get('pid')} on {owner.get('host')} since {owner.get('started_at')}" if owner else "an owner that wrote no record yet"
                return False, f"another sweep holds {self.path}: {who}"
            aside = f"{self.path}.stale-{self.run_id}"
            try:
                os.rename(self.path, aside)
                os.mkdir(self.path)
            except OSError as e:
                return False, f"could not take over the stale lock {self.path}: {e.strerror or e}"
            try:
                shutil.rmtree(aside)
            except OSError:
                pass
        except OSError as e:
            return False, f"cannot create {self.path}: {e.strerror or e}"
        rec = {"run_id": self.run_id, "pid": os.getpid(), "host": socket.gethostname(), "started_at": now_utc()}
        try:
            tmp = os.path.join(self.path, "owner.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rec, f)
            os.replace(tmp, os.path.join(self.path, "owner"))
        except OSError as e:
            try:
                os.rmdir(self.path)
            except OSError:
                pass
            return False, f"cannot write {self.path}/owner: {e.strerror or e}"
        self.held = True
        return True, ""

    def release(self) -> None:
        if not self.held:
            return
        owner = self._owner()
        if owner and owner.get("run_id") == self.run_id:
            try:
                os.unlink(os.path.join(self.path, "owner"))
                os.rmdir(self.path)
            except OSError:
                pass
        self.held = False
