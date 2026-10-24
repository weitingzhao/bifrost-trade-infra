"""Which roots a sweep may touch and what proves their owner is done (disk-guard, W-31 4.6
S1): the registry, its expansion (no symlink followed, no wildcard over a name with a
space, '=' or a quote), end evidence, Git and open files (review 539 F1, F3; review 543
A3, A4, C).
"""

from __future__ import annotations

import fnmatch
import math
import os
import re
import shutil
import stat
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from disk_guard_base import CAP_KINDS, Config, GIB, GLOB_CHARS, KINDS, Problem, QUARANTINE, WEIRD, _first, _join, _under
from disk_guard_layout import Walker


LSOF_STAT_WARNING = re.compile(r"^lsof: WARNING: can't stat\(\) \S+ file system (.+)$")
LSOF_INCOMPLETE = "Output information may be incomplete."
LSOF_ASSUMING = re.compile(r'^assuming "dev=[0-9A-Fa-fx]+" from mount table$')
# macOS: "<dev> on <path> (<type>, ...)"; Linux: "<dev> on <path> type <type> (...)"
MOUNT_LINE = re.compile(r"^.+? on (/.*?) (?:\(|type \S+ \()")


@dataclass
class Entry:
    pattern: str
    kind: str
    policy: str
    cap_bytes: Optional[int]
    note: str
    source: str


def parse_registry(path: str, required: bool) -> Tuple[List[Entry], List[str]]:
    entries: List[Entry] = []
    errors: List[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        if required:
            errors.append(f"{path}: missing")
        return entries, errors
    except (OSError, UnicodeDecodeError) as e:
        errors.append(f"{path}: cannot read ({e})")
        return entries, errors
    for no, line in enumerate(text.split("\n"), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        where = f"{path}:{no}"
        cols = line.rstrip("\r").split("\t")
        if len(cols) < 3:
            errors.append(f"{where}: expected path<TAB>kind<TAB>policy<TAB>note")
            continue
        pattern, kind, policy = cols[0], cols[1].strip(), cols[2].strip()
        note = "\t".join(cols[3:]).strip()
        segs = pattern.split("/")
        if not pattern or pattern.startswith("/") or any(s in ("", ".", "..") for s in segs) or "\0" in pattern:
            errors.append(f"{where}: path {pattern!r} must be relative to AGENT_WORK, without . or .. segments")
            continue
        if kind not in KINDS:
            errors.append(f"{where}: kind {kind!r} is not one of {', '.join(KINDS)}")
            continue
        cap = None
        if policy == "run.done":
            if len(segs) < 2:
                errors.append(f"{where}: run.done needs the owner directory above the cache root")
                continue
        elif policy == "ended":
            if not note:
                errors.append(f"{where}: ended needs a note saying who confirmed the owner finished")
                continue
        elif policy.startswith("cap="):
            if kind not in CAP_KINDS:
                errors.append(f"{where}: cap= is for {', '.join(CAP_KINDS)}")
                continue
            try:
                gb = float(policy[4:])
                cap = int(gb * GIB) if math.isfinite(gb) else -1
            except (ValueError, OverflowError):
                cap = -1
            if cap < 0:
                errors.append(f"{where}: {policy!r} is not cap=<GiB>")
                continue
        else:
            errors.append(f"{where}: policy {policy!r} is not run.done, ended or cap=<GiB>")
            continue
        entries.append(Entry(pattern, kind, policy, cap, note, where))
    return entries, errors


@dataclass
class Cand:
    rel: str
    entry: Optional[Entry]
    problem: Optional[Problem] = None
    missing: bool = False
    leftover: Optional[str] = None  # run id of the sweep that renamed it


def expand(agent_work: str, entry: Entry) -> List[Cand]:
    """Every directory the entry names. Never follows a symlink; a wildcard never takes a
    name with a space, '=' or a quote (what lies under such a name is reported, not
    removed); a directory it cannot list is reported, not skipped."""
    out: List[Cand] = []
    segs = entry.pattern.split("/")
    literal = not any(GLOB_CHARS.search(s) for s in segs)

    def rec(abs_dir: str, rel_dir: str, i: int, refused: Optional[str]) -> None:
        seg = segs[i]
        last = i == len(segs) - 1
        globbed = bool(GLOB_CHARS.search(seg))
        matches: List[Tuple[str, str, Optional[str]]] = []  # (name, base name, leftover run)
        if globbed or last:
            try:
                names = sorted(os.listdir(abs_dir))
            except FileNotFoundError:
                return
            except OSError as e:
                where = rel_dir or "."
                out.append(Cand(_join(rel_dir, seg), entry, Problem("unreadable", f"{where}: {e.strerror or e}")))
                return
            for n in names:
                base, run = n, None
                if last and QUARANTINE in n:
                    base, run = n.rsplit(QUARANTINE, 1)
                if globbed:
                    if base.startswith(".") and not seg.startswith("."):
                        continue
                    if not fnmatch.fnmatchcase(base, seg):
                        continue
                elif base != seg:
                    continue
                matches.append((n, base, run))
            if last and not globbed and literal and not any(r is None for _, _, r in matches):
                out.append(Cand(_join(rel_dir, seg), entry, missing=True))
        else:
            matches = [(seg, seg, None)]
        for n, base, run in matches:
            rel = _join(rel_dir, n)
            p = os.path.join(abs_dir, n)
            why = refused
            if globbed and WEIRD & set(base) and why is None:
                why = f"{rel}: a wildcard matched a name with a space, '=' or a quote; register it by its exact name"
            try:
                st = os.lstat(p)
            except FileNotFoundError:
                continue
            except OSError as e:
                out.append(Cand(rel, entry, Problem("unreadable", f"{rel}: {e.strerror or e}")))
                continue
            if stat.S_ISLNK(st.st_mode):
                out.append(Cand(rel, entry, Problem("symlink-in-path", f"{rel} is a symlink (not followed)")))
                continue
            if not stat.S_ISDIR(st.st_mode):
                if last:
                    out.append(Cand(rel, entry, Problem("not-a-directory", rel)))
                continue
            if last:
                out.append(Cand(rel, entry, Problem("glob-weird-name", why) if why else None, leftover=run))
            else:
                rec(p, rel, i + 1, why)

    rec(agent_work, "", 0, None)
    return out


def check_policy(cfg: Config, entry: Entry, owner_fd: Optional[int], owner: str, w: Walker, now: float) -> None:
    """Positive end evidence. owner_fd is a handle on the first directory of the path."""
    if entry.policy == "run.done":
        if owner_fd is None:
            raise Problem("no-run-done", "no owner directory above the root")
        try:
            st = os.stat("run.done", dir_fd=owner_fd, follow_symlinks=False)
        except FileNotFoundError:
            raise Problem("no-run-done", f"{owner}/run.done is missing: no evidence the review ended")
        except OSError as e:
            raise Problem("run-done-unreadable", f"{owner}/run.done: {e.strerror or e}")
        if not stat.S_ISREG(st.st_mode):
            raise Problem("run-done-unreadable", f"{owner}/run.done is not a regular file")
        if now - st.st_mtime < cfg.done_min_age:
            raise Problem("run-done-too-fresh", f"{owner}/run.done is {int((now - st.st_mtime) / 60)} min old")
        # run.done is written after the review exits: nothing in its cache can be newer
        if w.max_mtime > st.st_mtime:
            raise Problem("written-after-run-done", "the cache changed after run.done")
    elif entry.policy == "ended":
        if w.max_mtime and now - w.max_mtime < cfg.done_min_age:
            raise Problem("recently-written", f"written {int((now - w.max_mtime) / 60)} min ago")


def _git_env(cfg: Config) -> Dict[str, str]:
    # Git's own discovery decides; nothing inherited may point it elsewhere or stop it early.
    env = {k: v for k, v in cfg.env.items() if not k.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_DISCOVERY_ACROSS_FILESYSTEM="1", LC_ALL="C")
    return env


def _git(cfg: Config, cwd: str, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", cwd, *args], env=_git_env(cfg), capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Problem("git-error", f"git {args[0]}: {e}")


def git_top(cfg: Config, root: str) -> Optional[str]:
    """The Git worktree holding root, looked for all the way up (AGENT_WORK may itself be
    inside one, review 543 A4). None only when there is no .git above it and Git agrees."""
    parent = os.path.dirname(root)
    found = None
    d = parent
    while True:
        try:
            os.lstat(os.path.join(d, ".git"))
            found = d
            break
        except FileNotFoundError:
            pass
        except OSError as e:
            raise Problem("git-error", f"{d}/.git: {e.strerror or e}")
        if d == os.path.dirname(d):
            break
        d = os.path.dirname(d)
    r = _git(cfg, parent, "rev-parse", "--show-toplevel")
    if r.returncode == 0:
        top = r.stdout.decode(errors="surrogateescape").strip()
        if not top or not _under(root, os.path.realpath(top)):
            raise Problem("git-error", f"git rev-parse gave {top!r} for {parent}")
        return os.path.realpath(top)
    if found is None and b"not a git repository" in r.stderr:
        return None
    raise Problem("git-error", f"git rev-parse in {parent}: {_first(r.stderr)}" + (f" (.git at {found})" if found else ""))


def check_git(cfg: Config, root: str, tracked_only: bool = False) -> None:
    top = git_top(cfg, root)
    if top is None:
        return
    rel = os.path.relpath(root, top)
    where = os.path.relpath(top, cfg.agent_work) if _under(top, cfg.agent_work) else top
    r = _git(cfg, top, "ls-files", "-z", "--", rel)
    if r.returncode != 0:
        raise Problem("git-error", f"git ls-files in {where}: {_first(r.stderr)}")
    if r.stdout.strip(b"\0"):
        raise Problem("git-tracked-inside", f"git tracks files under it ({where})")
    if tracked_only:
        return
    r = _git(cfg, top, "status", "--porcelain=v1", "-z", "--ignored=matching", "--untracked-files=all", "--", rel)
    if r.returncode != 0:
        raise Problem("git-error", f"git status in {where}: {_first(r.stderr)}")
    for rec in r.stdout.split(b"\0"):
        if rec and not rec.startswith(b"!! "):
            raise Problem("git-not-ignored", f"git status: {rec[:2].decode(errors='replace')} (not ignored: someone's material?)")


def overlaps(a: str, b: str) -> bool:
    return _under(a, b) or _under(b, a)


def mount_points(cfg: Config) -> Tuple[List[str], str]:
    """The mount points in the current mount table (/sbin/mount; its output is read, nothing
    is stat()ed, since stat is what fails on the mounts lsof warns about)."""
    try:
        r = subprocess.run([cfg.mount], env=cfg.env, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [], f"{cfg.mount}: {e}"
    if r.returncode != 0:
        return [], f"{cfg.mount} exit {r.returncode}: {_first(r.stderr)}"
    points = []
    for line in r.stdout.decode(errors="surrogateescape").split("\n"):
        m = MOUNT_LINE.match(line)
        if m:
            points.append(m.group(1).rstrip("/") or "/")
    if not points:
        return [], f"{cfg.mount} printed no mount table"
    return points, ""


class OpenFiles:
    """One lsof snapshot of this user's processes. ok is False when lsof failed or printed
    anything on stderr (review 543 A3), with one exception: the three-line can't-stat
    warning lsof prints for a mount it cannot stat (macOS: the Time Machine share, whose path
    holds a UUID), when that path is absolute, is a mount point in the current mount table,
    and neither contains nor lies inside AGENT_WORK. problem_for() also refuses a root that
    such a mount contains or lies inside."""

    def __init__(self, cfg: Config) -> None:
        self.ok = False
        self.error = ""
        self.paths: List[str] = []
        self.tolerated: List[str] = []
        exe = shutil.which(cfg.lsof, path=cfg.env.get("PATH")) if os.sep not in cfg.lsof else cfg.lsof
        if not exe:
            self.error = f"{cfg.lsof} not found"
            return
        try:
            r = subprocess.run([exe, "-nP", "-Fn"], env=cfg.env, capture_output=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as e:
            self.error = f"lsof: {e}"
            return
        if r.returncode != 0:
            self.error = f"lsof exit {r.returncode}: {_first(r.stderr)}"
            return
        warned, error = self.stat_warnings(r.stderr.decode(errors="replace"))
        if not error and warned:
            mounts, error = mount_points(cfg)
            for path in warned:
                if error:
                    break
                resolved = os.path.join(os.path.realpath(os.path.dirname(path)), os.path.basename(path))
                if path not in mounts:
                    error = f"lsof: can't stat {path}, which is not a mount point in the mount table"
                elif overlaps(path, cfg.agent_work) or overlaps(resolved, cfg.agent_work):
                    error = f"lsof: can't stat {path}, which overlaps AGENT_WORK"
        if error:
            self.error = error
            return
        self.tolerated = warned
        for line in r.stdout.decode(errors="surrogateescape").split("\n"):
            if line.startswith("n/"):
                self.paths.append(line[1:])
        self.ok = True

    @staticmethod
    def stat_warnings(stderr: str) -> Tuple[List[str], str]:
        """The paths of complete three-line can't-stat warnings, or why stderr is not only those."""
        lines = [ln.rstrip() for ln in stderr.split("\n") if ln.strip()]
        paths: List[str] = []
        i = 0
        while i < len(lines):
            m = LSOF_STAT_WARNING.match(lines[i])
            if not m:
                return [], f"lsof: {lines[i].strip()}"
            follow = lines[i + 1:i + 3]
            if (len(follow) != 2 or not all(ln[:1].isspace() for ln in follow)
                    or follow[0].strip() != LSOF_INCOMPLETE or not LSOF_ASSUMING.match(follow[1].strip())):
                return [], f"lsof: {lines[i].strip()} (not followed by the two lines lsof always adds)"
            path = m.group(1)
            if not path.startswith("/"):
                return [], f"lsof: {lines[i].strip()} (not an absolute path)"
            paths.append(path.rstrip("/") or "/")
            i += 3
        return paths, ""

    def problem_for(self, *roots: str) -> Optional[str]:
        """Why this snapshot cannot say whether anything is open under these roots."""
        if not self.ok:
            return self.error
        for m in self.tolerated:
            for root in roots:
                if overlaps(m, root):
                    return f"lsof: can't stat {m}, which overlaps {root}"
        return None

    def under(self, *roots: str) -> Optional[str]:
        for p in self.paths:
            for root in roots:
                if p == root or p.startswith(root + "/"):
                    return p
        return None
