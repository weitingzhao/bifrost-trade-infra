"""Shared pieces of disk-guard (W-31 4.6 S1): constants, Problem, the configuration read
from the environment, and the directory-handle chain every check and removal goes through
(review 543 A2: a path is resolved once, without following links, and from then on only
handles are used). See disk_guard.py for the rules.
"""

from __future__ import annotations

import datetime as _dt
import math
import os
import re
import stat
from dataclasses import dataclass
from typing import Dict, List, Tuple

GIB = 1 << 30
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REGISTRY = os.path.join(HERE, "cache-roots.tsv")
QUARANTINE = ".lifecycle-del-"
WEIRD = set(" =\t\n\r'\"\\")
GLOB_CHARS = re.compile(r"[*?\[]")
KINDS = ("go-build", "go-mod", "npm", "go-build-chain")
CAP_KINDS = ("go-build", "go-mod", "npm")
# Names that look like a cache inside a review dir: found by name, reported, never removed
# unless registered.
CACHE_NAMES = {
    "gocache", ".gocache", "go-cache", ".go-cache", "go-build", ".go-build", "gomodcache",
    "go-mod", ".go-mod", "cache", ".cache", "review-cache", ".review-cache", "npm-cache",
    ".npm", "tmp", ".tmp", ".check-tmp",
}
# Opening never follows a symlink, at any level.
O_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
O_FILE = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)

Ident = Tuple[int, int]  # (st_dev, st_ino)


class ConfigError(Exception):
    pass


class Problem(Exception):
    """Why a root stays. code is a short key for the counts; detail says where."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gib(n: float) -> str:
    return f"{n / GIB:.2f} GiB"


def ident(st: os.stat_result) -> Ident:
    return (st.st_dev, st.st_ino)


def open_dir_at(parent_fd: int, name: str, where: str) -> int:
    """Open one directory below a handle, never through a symlink."""
    try:
        return os.open(name, O_DIR, dir_fd=parent_fd)
    except OSError as e:
        try:
            st = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except OSError:
            raise Problem("unreadable", f"{where}: {e.strerror or e}")
        if stat.S_ISLNK(st.st_mode):
            raise Problem("symlink-in-path", f"{where} is a symlink (not followed)")
        if not stat.S_ISDIR(st.st_mode):
            raise Problem("not-a-directory", where)
        raise Problem("unreadable", f"{where}: {e.strerror or e}")


class Chain:
    """Handles on every directory from AGENT_WORK down to rel, each opened without following
    a link, with each one's (device, inode). fd is the last one (AGENT_WORK's for rel "")."""

    def __init__(self, aw_fd: int, rel: str) -> None:
        self.fds: List[int] = []
        self.ids: List[Ident] = []
        cur, done = aw_fd, ""
        try:
            for comp in [c for c in rel.split("/") if c]:
                done = _join(done, comp)
                fd = open_dir_at(cur, comp, done)
                self.fds.append(fd)
                self.ids.append(ident(os.fstat(fd)))
                cur = fd
        except BaseException:
            self.close()
            raise
        self.fd = cur

    def close(self) -> None:
        for fd in self.fds:
            try:
                os.close(fd)
            except OSError:
                pass
        self.fds = []

    def __enter__(self) -> "Chain":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@dataclass
class Config:
    env: Dict[str, str]
    agent_work: str
    registries: List[Tuple[str, bool]]
    warn_gb: float
    stop_gb: float
    volume: str
    status_dir: str
    lock_dir: str
    done_min_age: float
    lsof: str
    lsof_tolerated: List[str]
    exclude: List[str]
    discover: List[str]
    host_go_cap_gb: float
    cursor_warn_gb: float


def _float(env: Dict[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} is not a number")
    if not math.isfinite(v) or v < 0:
        raise ConfigError(f"{name}={raw!r} is not a finite number >= 0")
    return v


def _rel_list(env: Dict[str, str], name: str, default: str) -> List[str]:
    out = []
    for p in env.get(name, default).split(":"):
        p = p.strip().strip("/")
        if not p:
            continue
        if p.startswith("..") or "/../" in f"/{p}/":
            raise ConfigError(f"{name}: {p!r} leaves AGENT_WORK")
        out.append(p)
    return out


def thresholds(env: Dict[str, str]) -> Tuple[float, float]:
    warn = _float(env, "WARN_GB", 30)
    stop = _float(env, "STOP_GB", 15)
    if stop > warn:
        raise ConfigError(f"STOP_GB ({stop:g}) is above WARN_GB ({warn:g})")
    return warn, stop


def _under(rel: str, prefix: str) -> bool:
    p = prefix.rstrip("/")
    return rel == prefix or rel == p or rel.startswith(p + "/")


def load_config(env: Dict[str, str]) -> Config:
    home = env.get("HOME") or os.path.expanduser("~")
    raw = env.get("AGENT_WORK", "").strip() or os.path.join(home, "agent-work")
    if not os.path.isdir(raw):
        raise ConfigError(f"AGENT_WORK={raw} is not a directory")
    aw = os.path.realpath(raw)
    if aw == "/" or aw == os.path.realpath(home):
        raise ConfigError(f"AGENT_WORK={aw} is / or the home directory: refusing")
    warn, stop = thresholds(env)
    status_dir = os.path.realpath(env.get("LIFECYCLE_STATUS_DIR", "").strip() or os.path.join(aw, "status"))
    regs_env = env.get("LIFECYCLE_CACHE_ROOTS", "").strip()
    if regs_env:
        registries = [(p, True) for p in regs_env.split(":") if p]
    else:
        registries = [(DEFAULT_REGISTRY, True), (os.path.join(status_dir, "cache-roots.tsv"), False)]
    # lsof warnings keep everything (review 543 A3) unless the warning names a mount listed
    # here, and a listed mount may neither contain AGENT_WORK nor lie inside it.
    tolerated = []
    for m in env.get("LIFECYCLE_LSOF_TOLERATED_MOUNTS", "").split(":"):
        m = m.strip()
        if not m:
            continue
        if not m.startswith("/"):
            raise ConfigError(f"LIFECYCLE_LSOF_TOLERATED_MOUNTS: {m!r} is not an absolute mount point")
        if _under(aw, m) or _under(m, aw):
            raise ConfigError(f"LIFECYCLE_LSOF_TOLERATED_MOUNTS: {m} overlaps AGENT_WORK")
        tolerated.append(m.rstrip("/") or "/")
    return Config(
        env=env,
        agent_work=aw,
        registries=registries,
        warn_gb=warn,
        stop_gb=stop,
        volume=env.get("DISK_GUARD_VOLUME", "").strip() or aw,
        status_dir=status_dir,
        lock_dir=os.path.abspath(env.get("LIFECYCLE_LOCK", "").strip() or os.path.join(aw, ".lifecycle.lock")),
        done_min_age=_float(env, "LIFECYCLE_DONE_MIN_AGE_MIN", 120) * 60,
        lsof=env.get("LIFECYCLE_LSOF", "").strip() or "lsof",
        lsof_tolerated=tolerated,
        exclude=_rel_list(env, "LIFECYCLE_EXCLUDE", ""),
        discover=_rel_list(env, "LIFECYCLE_DISCOVER", "codex-review-*"),
        host_go_cap_gb=_float(env, "DEFAULT_GOCACHE_CAP_GB", 30),
        cursor_warn_gb=_float(env, "CURSOR_DB_WARN_GB", 30),
    )


def free_space(volume: str) -> Dict[str, object]:
    try:
        s = os.statvfs(volume)
    except OSError as e:
        return {"path": volume, "error": f"statvfs {volume}: {e.strerror or e}"}
    return {"path": volume, "free_bytes": s.f_bavail * s.f_frsize, "total_bytes": s.f_blocks * s.f_frsize}


def _join(a: str, b: str) -> str:
    return f"{a}/{b}" if a else b


def _first(b: bytes) -> str:
    s = b.decode(errors="replace").strip().splitlines()
    return s[0] if s else "no output"


def split_rel(rel: str) -> Tuple[str, str]:
    """('a/b', 'c') for 'a/b/c'; ('', 'c') for 'c'."""
    if "/" in rel:
        parent, name = rel.rsplit("/", 1)
        return parent, name
    return "", rel
