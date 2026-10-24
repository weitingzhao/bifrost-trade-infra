"""What a cache root must look like, read in full before anything is removed (disk-guard,
W-31 4.6 S1; review 539 F2, review 543 A1, A2).

Every level of a layout accepts only the entries the tool writes there; anything else (a
hand-written .go, notes, ignored material) keeps the whole root. Subtrees whose files cannot
be told from someone's are kept by design, each under its own reason so the report says why
a cache is not reclaimed: npm's _npx installs and a non-empty _cacache/tmp, Go's cache/vcs
checkouts, a Go download's leftover .tmp, a writable module directory (hand-placed, or
-modcacherw). The walk goes through directory handles opened without following links, from
a handle on the root, so a directory swapped for a symlink mid-walk stops it instead of
leading elsewhere. A walk that passes leaves its inventory (every entry it accepted, with
its signature, and every directory's listing): removal touches only that (review 544 A1).
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
from typing import Callable, Dict, Iterator, List, Optional, Tuple

from disk_guard_base import Chain, O_DIR, O_FILE, Problem, Sig, ident, sig
from disk_guard_inventory import Inventory

GO_README_MARK = b"Go build system"
HEX2 = re.compile(r"^[0-9a-f]{2}$")
GO_ENTRY = re.compile(r"^([0-9a-f]{2})[0-9a-f]{62}-([ad])$")
TIMESTAMP = re.compile(rb"^\s*\d{1,20}\s*$")
VERSION = r"v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.!+-]*)?"
GO_DOWNLOAD_TMP = re.compile(r"\.tmp$")
NPM_LASTVERIFIED = re.compile(rb"^[0-9]{1,20}$")
AT_V_FILE = re.compile(rf"^(?:list|list\.lock|{VERSION}\.(?:info|mod|zip|ziphash|lock|partial|zip\.partial))$")
MODULE_AT = re.compile(rf"@{VERSION}$")
TILE_DIR = re.compile(r"^(?:[0-9]+|x[0-9]{3}|[0-9]{3}\.p|data)$")
TILE_FILE = re.compile(r"^[0-9]+$")
NPM_LOG = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}_\d{2}_\d{2}_\d{3}Z-debug-\d+\.log$")
NPM_ALGO = re.compile(r"^sha(1|256|384|512)$")
HEXN = re.compile(r"^[0-9a-f]+$")
# A file with one of these suffixes outside extracted module source is someone's material.
SOURCE_EXT = {
    ".go", ".sum", ".md", ".txt", ".py", ".sh", ".js", ".mjs", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".sql", ".rs", ".c", ".h", ".java", ".rb", ".patch",
    ".diff", ".rst", ".csv", ".html", ".css", ".org", ".ipynb", ".log",
}

Entry = Tuple[str, str, os.stat_result]  # (name, path relative to the root, lstat)


class Walker:
    """Reads a tree through directory handles without following symlinks or leaving its
    filesystem. A read error, a symlink, a nested .git, a special file or a directory that
    changed between listing and opening stops the walk with a Problem."""

    def __init__(self, root_fd: int, redact: bool = False) -> None:
        st = os.fstat(root_fd)
        if not stat.S_ISDIR(st.st_mode):
            raise Problem("not-a-directory", ".")
        self.root_fd = root_fd
        self.root_id = ident(st)
        self.dev = st.st_dev
        self.redact = redact
        self.leaf: Optional[str] = None  # chain: relative path of the Go cache inside it
        self.bytes = 0
        self.files = 0
        self.max_mtime = 0.0  # entries only: renaming the root changes nothing here
        self.inv: Dict[str, Sig] = {}  # every accepted entry, by path relative to the root
        self.listed: Dict[str, List[str]] = {}  # every directory read in full: its names

    def inventory(self) -> Inventory:
        return Inventory(dict(self.inv), {k: list(v) for k, v in self.listed.items()}, self.root_id, self.redact, self.leaf)

    def show(self, rel: str) -> str:
        if not self.redact:
            return rel
        # A chain's directory names can hold a whole command line (values included): name a
        # chain level by number only, and the leaf's entries from the leaf down.
        if self.leaf is not None and (rel == self.leaf or rel.startswith(self.leaf + "/")):
            return "<leaf>" + rel[len(self.leaf):]
        return "<chain level>"

    def entries(self, fd: int, rel: str, source_ok: bool = False) -> List[Entry]:
        try:
            names = sorted(os.listdir(fd))
        except OSError as e:
            raise Problem("unreadable", f"{self.show(rel) or '.'}: {e.strerror or e}")
        out = []
        for n in names:
            crel = f"{rel}/{n}" if rel else n
            try:
                st = os.stat(n, dir_fd=fd, follow_symlinks=False)
            except OSError as e:
                raise Problem("unreadable", f"{self.show(crel)}: {e.strerror or e}")
            if n == ".git":
                raise Problem("nested-git", self.show(crel))
            if stat.S_ISLNK(st.st_mode):
                raise Problem("symlink", f"{self.show(crel)} (not followed)")
            if st.st_dev != self.dev:
                raise Problem("cross-device", self.show(crel))
            if not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
                raise Problem("special-file", self.show(crel))
            if stat.S_ISREG(st.st_mode) and not source_ok and os.path.splitext(n)[1].lower() in SOURCE_EXT:
                raise Problem("handwritten-file", f"{self.show(crel)} looks hand-written")
            self.bytes += st.st_blocks * 512
            if stat.S_ISREG(st.st_mode):
                self.files += 1
            self.max_mtime = max(self.max_mtime, st.st_mtime)
            self.inv[crel] = sig(st)
            out.append((n, crel, st))
        self.listed[rel] = [n for n, _, _ in out]
        return out

    @contextlib.contextmanager
    def opened(self, fd: int, name: str, rel: str, st: os.stat_result) -> Iterator[int]:
        try:
            cfd = os.open(name, O_DIR, dir_fd=fd)
        except OSError as e:
            raise Problem("unreadable", f"{self.show(rel)}: {e.strerror or e}")
        try:
            if ident(os.fstat(cfd)) != ident(st):
                raise Problem("changed-during-check", self.show(rel))
            yield cfd
        finally:
            os.close(cfd)

    def head(self, fd: int, name: str, rel: str, st: os.stat_result, n: int = 4096) -> bytes:
        try:
            rfd = os.open(name, O_FILE, dir_fd=fd)
        except OSError as e:
            raise Problem("unreadable", f"{self.show(rel)}: {e.strerror or e}")
        try:
            if ident(os.fstat(rfd)) != ident(st):
                raise Problem("changed-during-check", self.show(rel))
            return os.read(rfd, n)
        except OSError as e:
            raise Problem("unreadable", f"{self.show(rel)}: {e.strerror or e}")
        finally:
            os.close(rfd)

    def tree(self, fd: int, rel: str, check: Callable[[str, str, os.stat_result], None], source_ok: bool = False) -> None:
        for n, crel, st in self.entries(fd, rel, source_ok):
            check(n, crel, st)
            if stat.S_ISDIR(st.st_mode):
                with self.opened(fd, n, crel, st) as cfd:
                    self.tree(cfd, crel, check, source_ok)


def unknown(w: Walker, rel: str, why: str = "") -> Problem:
    return Problem("unknown-entry", w.show(rel) + (f" ({why})" if why else ""))


def only_dirs(w: Walker) -> Callable[[str, str, os.stat_result], None]:
    def check(n: str, rel: str, st: os.stat_result) -> None:
        if not stat.S_ISDIR(st.st_mode):
            raise unknown(w, rel)
    return check


def check_go_build(w: Walker, fd: int, rel: str) -> None:
    ents = w.entries(fd, rel, source_ok=True)  # trim.txt is Go's; every root name is checked below
    if "README" not in {n for n, _, _ in ents}:
        raise Problem("layout-marker-missing", "no README (not a Go build cache)")
    for n, crel, st in ents:
        if n in ("README", "trim.txt", "testexpire.txt"):
            if not stat.S_ISREG(st.st_mode):
                raise unknown(w, crel, "expected a file")
            head = w.head(fd, n, crel, st)
            if n == "README" and GO_README_MARK not in head:
                raise Problem("layout-marker-missing", "README is not the Go build cache's")
            if n != "README" and not TIMESTAMP.match(head):
                raise unknown(w, crel, "not a Go timestamp")
        elif HEX2.match(n) and stat.S_ISDIR(st.st_mode):
            with w.opened(fd, n, crel, st) as bfd:
                for fn, frel, fst in w.entries(bfd, crel):
                    m = GO_ENTRY.match(fn)
                    if not m or m.group(1) != n:
                        raise unknown(w, frel)
                    if stat.S_ISREG(fst.st_mode):
                        continue
                    # go run / go tool keep one built executable as <hash>-d/<name>
                    if m.group(2) == "d" and stat.S_ISDIR(fst.st_mode):
                        with w.opened(bfd, fn, frel, fst) as efd:
                            inner = w.entries(efd, frel)
                        if len(inner) == 1 and stat.S_ISREG(inner[0][2].st_mode) and inner[0][2].st_mode & stat.S_IXUSR:
                            continue
                    raise unknown(w, frel)
        else:
            raise unknown(w, crel)


def check_go_mod(w: Walker, fd: int, rel: str) -> None:
    ents = w.entries(fd, rel)
    if not any(n == "cache" and stat.S_ISDIR(st.st_mode) for n, _, st in ents):
        raise Problem("layout-marker-missing", "no cache/ (not a Go module cache)")
    for n, crel, st in ents:
        if not stat.S_ISDIR(st.st_mode):
            raise unknown(w, crel, "a file outside any module")
        with w.opened(fd, n, crel, st) as cfd:
            if n == "cache":
                _go_mod_cache(w, cfd, crel)
            else:
                _module_path(w, cfd, crel, st)


def _go_mod_cache(w: Walker, fd: int, rel: str) -> None:
    for n, crel, st in w.entries(fd, rel):
        if n == "lock" and stat.S_ISREG(st.st_mode) and st.st_size == 0:
            continue
        if not stat.S_ISDIR(st.st_mode) or n not in ("download", "vcs"):
            raise unknown(w, crel)
        with w.opened(fd, n, crel, st) as cfd:
            if n == "vcs":
                if w.entries(cfd, crel):
                    raise Problem("go-vcs-checkouts", f"{crel} holds VCS checkouts (direct fetches), which cannot be told from someone's repository: kept, reported only")
                continue
            for dn, drel, dst in w.entries(cfd, crel):
                if not stat.S_ISDIR(dst.st_mode):
                    raise unknown(w, drel)
                with w.opened(cfd, dn, drel, dst) as dfd:
                    if dn == "sumdb":
                        _sumdb(w, dfd, drel)
                    else:
                        _download_path(w, dfd, drel)


def _download_path(w: Walker, fd: int, rel: str) -> None:
    for n, crel, st in w.entries(fd, rel):
        if not stat.S_ISDIR(st.st_mode):
            raise unknown(w, crel, "a file outside @v")
        with w.opened(fd, n, crel, st) as cfd:
            if n == "@v":
                for vn, vrel, vst in w.entries(cfd, crel):
                    if stat.S_ISREG(vst.st_mode) and GO_DOWNLOAD_TMP.search(vn):
                        raise Problem("go-download-tmp", f"{w.show(vrel)}: a download temp file a killed go left: kept, reported only")
                    if not (stat.S_ISREG(vst.st_mode) and AT_V_FILE.match(vn)):
                        raise unknown(w, vrel)
            else:
                _download_path(w, cfd, crel)


def _sumdb(w: Walker, fd: int, rel: str) -> None:
    for host, hrel, hst in w.entries(fd, rel):
        if not stat.S_ISDIR(hst.st_mode):
            raise unknown(w, hrel)
        with w.opened(fd, host, hrel, hst) as hfd:
            for n, crel, st in w.entries(hfd, hrel):
                if not stat.S_ISDIR(st.st_mode) or n not in ("lookup", "tile"):
                    raise unknown(w, crel)
                with w.opened(hfd, n, crel, st) as cfd:
                    if n == "lookup":
                        w.tree(cfd, crel, _lookup_entry(w))
                    else:
                        w.tree(cfd, crel, _tile_entry(w))


def _lookup_entry(w: Walker) -> Callable[[str, str, os.stat_result], None]:
    def check(n: str, rel: str, st: os.stat_result) -> None:
        if stat.S_ISREG(st.st_mode) and not MODULE_AT.search(n):
            raise unknown(w, rel, "a lookup entry is module@version")
    return check


def _tile_entry(w: Walker) -> Callable[[str, str, os.stat_result], None]:
    def check(n: str, rel: str, st: os.stat_result) -> None:
        if not (TILE_DIR if stat.S_ISDIR(st.st_mode) else TILE_FILE).match(n):
            raise unknown(w, rel)
    return check


def _module_path(w: Walker, fd: int, rel: str, st: os.stat_result) -> None:
    """Module path components down to <module>@<version>, which is extracted read-only."""
    if "@" in os.path.basename(rel):
        if not MODULE_AT.search(rel):
            raise unknown(w, rel, "not <module>@<version>")
        _module_tree(w, fd, rel, st)
        return
    for n, crel, cst in w.entries(fd, rel):
        if not stat.S_ISDIR(cst.st_mode):
            raise unknown(w, crel, "a file outside any module")
        with w.opened(fd, n, crel, cst) as cfd:
            _module_path(w, cfd, crel, cst)


def _module_tree(w: Walker, fd: int, rel: str, st: os.stat_result) -> None:
    # Go extracts a module read-only (files 0444, directories 0555) unless -modcacherw was
    # given: a writable entry is hand-placed or from -modcacherw, and the two look alike.
    why = "writable in a module directory (hand-placed, or -modcacherw): kept, reported only"
    if st.st_mode & 0o222:
        raise Problem("writable-in-module", f"{w.show(rel)}: {why}")
    for n, crel, cst in w.entries(fd, rel, source_ok=True):
        if cst.st_mode & 0o222:
            raise Problem("writable-in-module", f"{w.show(crel)}: {why}")
        if stat.S_ISDIR(cst.st_mode):
            with w.opened(fd, n, crel, cst) as cfd:
                _module_tree(w, cfd, crel, cst)


def check_npm(w: Walker, fd: int, rel: str) -> None:
    ents = w.entries(fd, rel)
    if not any(n == "_cacache" and stat.S_ISDIR(st.st_mode) for n, _, st in ents):
        raise Problem("layout-marker-missing", "no _cacache/ (not an npm cache)")
    for n, crel, st in ents:
        if n == "_update-notifier-last-checked" and stat.S_ISREG(st.st_mode) and st.st_size == 0:
            continue
        if n == "_npx":
            raise Problem("npm-npx-installs", "_npx holds packages npm exec / npx installed: kept, reported only")
        if not stat.S_ISDIR(st.st_mode) or n not in ("_cacache", "_logs"):
            raise unknown(w, crel)
        with w.opened(fd, n, crel, st) as cfd:
            if n == "_logs":
                for ln, lrel, lst in w.entries(cfd, crel, source_ok=True):
                    if not (stat.S_ISREG(lst.st_mode) and NPM_LOG.match(ln)):
                        raise unknown(w, lrel)
            else:
                _cacache(w, cfd, crel)


def _cacache(w: Walker, fd: int, rel: str) -> None:
    for n, crel, st in w.entries(fd, rel):
        if n == "_lastverified" and stat.S_ISREG(st.st_mode):
            # npm cache verify writes the time in milliseconds, and nothing else
            if not NPM_LASTVERIFIED.match(w.head(fd, n, crel, st, 64)):
                raise unknown(w, crel, "not npm's millisecond timestamp")
            continue
        if not stat.S_ISDIR(st.st_mode) or n not in ("content-v2", "index-v5", "tmp"):
            raise unknown(w, crel)
        with w.opened(fd, n, crel, st) as cfd:
            if n == "tmp":
                if w.entries(cfd, crel):
                    raise Problem("npm-tmp-not-empty", f"{crel} is not empty: npm's temporary files cannot be told from someone's: kept, reported only")
            elif n == "index-v5":
                _hex_buckets(w, cfd, crel)
            else:
                for an, arel, ast in w.entries(cfd, crel):
                    if not (NPM_ALGO.match(an) and stat.S_ISDIR(ast.st_mode)):
                        raise unknown(w, arel)
                    with w.opened(cfd, an, arel, ast) as afd:
                        _hex_buckets(w, afd, arel)


def _hex_buckets(w: Walker, fd: int, rel: str) -> None:
    for an, arel, ast in w.entries(fd, rel):
        if not (HEX2.match(an) and stat.S_ISDIR(ast.st_mode)):
            raise unknown(w, arel)
        with w.opened(fd, an, arel, ast) as afd:
            for bn, brel, bst in w.entries(afd, arel):
                if not (HEX2.match(bn) and stat.S_ISDIR(bst.st_mode)):
                    raise unknown(w, brel)
                with w.opened(afd, bn, brel, bst) as bfd:
                    for fn, frel, fst in w.entries(bfd, brel):
                        if not (HEXN.match(fn) and stat.S_ISREG(fst.st_mode)):
                            raise unknown(w, frel)


def check_go_build_chain(w: Walker, fd: int, rel: str) -> None:
    def level(cfd: int, crel: str, depth: int) -> None:
        if depth > 16:
            raise Problem("chain-shape", "deeper than 16 levels")
        ents = w.entries(cfd, crel, source_ok=True)  # names checked below, or by check_go_build
        if any(n == "README" for n, _, _ in ents):
            w.leaf = crel
            w.bytes -= sum(st.st_blocks * 512 for _, _, st in ents)  # counted again below
            w.files -= sum(1 for _, _, st in ents if stat.S_ISREG(st.st_mode))
            check_go_build(w, cfd, crel)
            return
        if len(ents) != 1 or not stat.S_ISDIR(ents[0][2].st_mode):
            raise Problem("chain-shape", f"level {depth}: {len(ents)} entries, expected one directory")
        n, nrel, nst = ents[0]
        with w.opened(cfd, n, nrel, nst) as nfd:
            level(nfd, nrel, depth + 1)

    level(fd, rel, 0)


VALIDATORS: Dict[str, Callable[[Walker, int, str], None]] = {
    "go-build": check_go_build,
    "go-mod": check_go_mod,
    "npm": check_npm,
    "go-build-chain": check_go_build_chain,
}


def validate(root_fd: int, kind: str) -> Walker:
    w = Walker(root_fd, redact=(kind == "go-build-chain"))
    VALIDATORS[kind](w, root_fd, "")
    return w


def guess(names: List[str]) -> Optional[str]:
    if "README" in names:
        return "go-build"
    if "cache" in names:
        return "go-mod"
    if "_cacache" in names:
        return "npm"
    if len(names) == 1:
        return "go-build-chain"
    return None


def detect(aw_fd: int, rel: str, path: str) -> Tuple[Optional[str], Optional[Problem], Tuple[int, bool]]:
    """Best guess at what an unregistered directory is (report only); size is (bytes, complete)."""
    try:
        with Chain(aw_fd, rel) as ch:
            kind = guess(os.listdir(ch.fd))
            if kind is None:
                return None, Problem("layout-unknown", "no known cache marker"), du(path)
            try:
                return kind, None, (validate(ch.fd, kind).bytes, True)
            except Problem as p:
                # one directory inside is only a guess at a chain: if it is not one, say unknown
                return (None if kind == "go-build-chain" and p.code == "chain-shape" else kind), p, du(path)
    except (Problem, OSError) as e:
        return None, e if isinstance(e, Problem) else Problem("unreadable", str(e)), du(path)


def du(path: str) -> Tuple[int, bool]:
    """Disk use for the report (never for a decision): (bytes, False if anything was unreadable)."""
    total, complete = 0, True

    def failed(e: OSError) -> None:
        nonlocal complete
        complete = False

    for dp, dns, fns in os.walk(path, onerror=failed):
        for n in dns + fns:
            try:
                total += os.lstat(os.path.join(dp, n)).st_blocks * 512
            except OSError:
                complete = False
    return total, complete
