"""What a cache root must look like, read in full before anything is removed (disk-guard,
W-31 4.6 S1; review 539 F2). A symlink, a nested .git, another filesystem, an entry the
layout does not have or a read error anywhere stops the walk with a Problem.
"""

from __future__ import annotations

import os
import re
import stat
from typing import Callable, Dict, List, Optional, Tuple

from disk_guard_base import Problem


GO_README_MARK = b"Go build system"


class Walker:
    """Reads a tree without following symlinks or leaving its filesystem. Any read error,
    symlink, nested .git or special file stops the walk with a Problem."""

    def __init__(self, root: str, redact: bool = False) -> None:
        self.root = root
        self.redact = redact
        self.leaf: Optional[str] = None
        try:
            st = os.lstat(root)
        except OSError as e:
            raise Problem("unreadable", f".: {e.strerror or e}")
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise Problem("not-a-directory", ".")
        self.dev = st.st_dev
        self.bytes = 0
        self.files = 0
        self.max_mtime = 0.0  # entries only: renaming the root changes nothing here
        self.complete = False

    def rel(self, path: str) -> str:
        if self.redact:
            # A chain's directory names can hold a whole command line (values included):
            # report a chain level by number only, and the leaf's entries from the leaf down.
            if self.leaf and (path == self.leaf or path.startswith(self.leaf + os.sep)):
                return "<leaf>/" + os.path.relpath(path, self.leaf)
            return "<chain level>"
        return os.path.relpath(path, self.root)

    def listdir(self, path: str) -> List[Tuple[str, str, os.stat_result]]:
        try:
            names = sorted(os.listdir(path))
        except OSError as e:
            raise Problem("unreadable", f"{self.rel(path)}: {e.strerror or e}")
        out = []
        for n in names:
            p = os.path.join(path, n)
            try:
                st = os.lstat(p)
            except OSError as e:
                raise Problem("unreadable", f"{self.rel(p)}: {e.strerror or e}")
            if n == ".git":
                raise Problem("nested-git", self.rel(p))
            if stat.S_ISLNK(st.st_mode):
                raise Problem("symlink", f"{self.rel(p)} (not followed)")
            if st.st_dev != self.dev:
                raise Problem("cross-device", self.rel(p))
            if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
                raise Problem("special-file", self.rel(p))
            self.bytes += st.st_blocks * 512
            if stat.S_ISREG(st.st_mode):
                self.files += 1
            if st.st_mtime > self.max_mtime:
                self.max_mtime = st.st_mtime
            out.append((n, p, st))
        return out

    def subtree(self, path: str, check: Callable[[str, str, os.stat_result], None]) -> None:
        for n, p, st in self.listdir(path):
            check(n, p, st)
            if stat.S_ISDIR(st.st_mode):
                self.subtree(p, check)


def unknown(w: Walker, path: str, why: str = "") -> Problem:
    return Problem("unknown-entry", w.rel(path) + (f" ({why})" if why else ""))


HEX2 = re.compile(r"^[0-9a-f]{2}$")


GO_ENTRY = re.compile(r"^([0-9a-f]{2})[0-9a-f]{62}-([ad])$")


HEX64 = re.compile(r"^[0-9a-f]{64}$")


VCS_FILE = re.compile(r"^[0-9a-f]{64}\.(info|lock)$")


DOWNLOAD_SUFFIXES = (".info", ".mod", ".zip", ".ziphash", ".lock", ".partial")


NPM_LOG = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}_\d{2}_\d{2}_\d{3}Z-debug-\d+\.log$")


NPM_ALGO = re.compile(r"^sha(1|256|384|512)$")


HEXN = re.compile(r"^[0-9a-f]+$")


def check_go_build(w: Walker, root: str) -> None:
    ents = w.listdir(root)
    names = {n for n, _, _ in ents}
    if "README" not in names:
        raise Problem("layout-marker-missing", "no README (not a Go build cache)")
    for n, p, st in ents:
        if n in ("README", "trim.txt", "testexpire.txt"):
            if not stat.S_ISREG(st.st_mode):
                raise unknown(w, p, "expected a file")
            if n == "README":
                try:
                    with open(p, "rb") as f:
                        head = f.read(4096)
                except OSError as e:
                    raise Problem("unreadable", f"{w.rel(p)}: {e.strerror or e}")
                if GO_README_MARK not in head:
                    raise Problem("layout-marker-missing", "README is not the Go build cache's")
            continue
        if HEX2.match(n) and stat.S_ISDIR(st.st_mode):
            for fn, fp, fst in w.listdir(p):
                m = GO_ENTRY.match(fn)
                if not m or m.group(1) != n:
                    raise unknown(w, fp)
                if stat.S_ISREG(fst.st_mode):
                    continue
                # go run / go tool keep a built executable as <hash>-d/<name>
                if m.group(2) == "d" and stat.S_ISDIR(fst.st_mode):
                    inner = w.listdir(fp)
                    if len(inner) == 1 and stat.S_ISREG(inner[0][2].st_mode) and inner[0][2].st_mode & stat.S_IXUSR:
                        continue
                raise unknown(w, fp)
            continue
        raise unknown(w, p)


def check_go_mod(w: Walker, root: str) -> None:
    ents = w.listdir(root)
    if not any(n == "cache" and stat.S_ISDIR(st.st_mode) for n, _, st in ents):
        raise Problem("layout-marker-missing", "no cache/ (not a Go module cache)")
    for n, p, st in ents:
        if not stat.S_ISDIR(st.st_mode):
            raise unknown(w, p, "a file outside any module")
        if n == "cache":
            _go_mod_cache(w, p)
        else:
            _module_tree(w, p, st, "@" in n)


def _go_mod_cache(w: Walker, path: str) -> None:
    for n, p, st in w.listdir(path):
        if n == "download" and stat.S_ISDIR(st.st_mode):
            _download(w, p, in_v=False, in_sumdb=False)
        elif n == "vcs" and stat.S_ISDIR(st.st_mode):
            for vn, vp, vst in w.listdir(p):
                if HEX64.match(vn) and stat.S_ISDIR(vst.st_mode):
                    w.subtree(vp, lambda *_: None)
                elif VCS_FILE.match(vn) and stat.S_ISREG(vst.st_mode):
                    continue
                else:
                    raise unknown(w, vp)
        elif n == "lock" and stat.S_ISREG(st.st_mode):
            continue
        else:
            raise unknown(w, p)


def _download(w: Walker, path: str, in_v: bool, in_sumdb: bool) -> None:
    for n, p, st in w.listdir(path):
        if stat.S_ISDIR(st.st_mode):
            _download(w, p, in_v=(n == "@v"), in_sumdb=in_sumdb or n == "sumdb")
        elif in_sumdb:
            continue
        elif in_v and (n == "list" or n.endswith(DOWNLOAD_SUFFIXES)):
            continue
        else:
            raise unknown(w, p)


def _module_tree(w: Walker, path: str, st: os.stat_result, in_mod: bool) -> None:
    # Go extracts a module read-only (files 0444, directories 0555): anything writable in a
    # module directory was put there by hand.
    if in_mod and st.st_mode & 0o222:
        raise Problem("writable-in-module", w.rel(path))
    for n, p, cst in w.listdir(path):
        child_in_mod = in_mod or "@" in n
        if stat.S_ISDIR(cst.st_mode):
            _module_tree(w, p, cst, child_in_mod)
        elif not child_in_mod:
            raise unknown(w, p, "a file outside any module")
        elif cst.st_mode & 0o222:
            raise Problem("writable-in-module", w.rel(p))


def check_npm(w: Walker, root: str) -> None:
    ents = w.listdir(root)
    if not any(n == "_cacache" and stat.S_ISDIR(st.st_mode) for n, _, st in ents):
        raise Problem("layout-marker-missing", "no _cacache/ (not an npm cache)")
    for n, p, st in ents:
        if n == "_cacache" and stat.S_ISDIR(st.st_mode):
            _cacache(w, p)
        elif n == "_logs" and stat.S_ISDIR(st.st_mode):
            for ln, lp, lst in w.listdir(p):
                if not (NPM_LOG.match(ln) and stat.S_ISREG(lst.st_mode)):
                    raise unknown(w, lp)
        elif n == "_update-notifier-last-checked" and stat.S_ISREG(st.st_mode):
            continue
        else:
            raise unknown(w, p)


def _cacache(w: Walker, path: str) -> None:
    for n, p, st in w.listdir(path):
        if not stat.S_ISDIR(st.st_mode):
            raise unknown(w, p)
        if n == "content-v2":
            for an, ap, ast in w.listdir(p):
                if not (NPM_ALGO.match(an) and stat.S_ISDIR(ast.st_mode)):
                    raise unknown(w, ap)
                _hex_buckets(w, ap)
        elif n == "index-v5":
            _hex_buckets(w, p)
        elif n == "tmp":
            for tn, tp, tst in w.listdir(p):
                if not stat.S_ISREG(tst.st_mode):
                    raise unknown(w, tp)
        else:
            raise unknown(w, p)


def _hex_buckets(w: Walker, path: str) -> None:
    for an, ap, ast in w.listdir(path):
        if not (HEX2.match(an) and stat.S_ISDIR(ast.st_mode)):
            raise unknown(w, ap)
        for bn, bp, bst in w.listdir(ap):
            if not (HEX2.match(bn) and stat.S_ISDIR(bst.st_mode)):
                raise unknown(w, bp)
            for fn, fp, fst in w.listdir(bp):
                if not (HEXN.match(fn) and stat.S_ISREG(fst.st_mode)):
                    raise unknown(w, fp)


def check_go_build_chain(w: Walker, root: str) -> None:
    cur, depth = root, 0
    while True:
        ents = w.listdir(cur)
        if any(n == "README" for n, _, _ in ents):
            w.leaf = cur
            check_go_build(w, cur)
            return
        if len(ents) != 1 or not stat.S_ISDIR(ents[0][2].st_mode):
            raise Problem("chain-shape", f"level {depth}: {len(ents)} entries, expected one directory")
        cur, depth = ents[0][1], depth + 1
        if depth > 16:
            raise Problem("chain-shape", "deeper than 16 levels")


VALIDATORS: Dict[str, Callable[[Walker, str], None]] = {
    "go-build": check_go_build,
    "go-mod": check_go_mod,
    "npm": check_npm,
    "go-build-chain": check_go_build_chain,
}


def validate(path: str, kind: str) -> Walker:
    w = Walker(path, redact=(kind == "go-build-chain"))
    VALIDATORS[kind](w, path)
    w.complete = True
    return w


def detect(path: str) -> Tuple[Optional[str], Optional[Problem], int]:
    """Best guess at what an unregistered directory is (report only)."""
    try:
        names = os.listdir(path)
    except OSError as e:
        return None, Problem("unreadable", f".: {e.strerror or e}"), 0
    if "README" in names:
        kind = "go-build"
    elif "cache" in names:
        kind = "go-mod"
    elif "_cacache" in names:
        kind = "npm"
    elif len(names) == 1 and os.path.isdir(os.path.join(path, names[0])) and not os.path.islink(os.path.join(path, names[0])):
        kind = "go-build-chain"
    else:
        return None, Problem("layout-unknown", f"{len(names)} entries, no known cache marker"), _du(path)
    try:
        w = validate(path, kind)
        return kind, None, w.bytes
    except Problem as p:
        # one directory inside is only a guess at a chain: if it is not one, say unknown
        return (None if kind == "go-build-chain" and p.code == "chain-shape" else kind), p, _du(path)


def _du(path: str) -> int:
    total = 0
    for dp, dns, fns in os.walk(path, onerror=lambda e: None):
        for n in dns + fns:
            try:
                total += os.lstat(os.path.join(dp, n)).st_blocks * 512
            except OSError:
                pass
    return total
