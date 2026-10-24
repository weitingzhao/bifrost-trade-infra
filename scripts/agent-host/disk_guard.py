#!/usr/bin/env python3
"""disk-guard: free-space check and lifecycle sweep for a machine that runs agents
(W-31 round 4, 4.6 slice S1; CUT-lifecycle-2026-10-24.md §2, §4.1; reviews 539, 543).

    disk-guard.sh check            free space on the volume that holds AGENT_WORK: exit 0 at or
                                   above WARN_GB (30), 1 below it (no new review, npm ci or
                                   worktree), 2 below STOP_GB (15) or when it cannot be read
    disk-guard.sh sweep            report only (the default): what a sweep would remove, and why
                                   everything else stays; writes <status>/lifecycle.json
    disk-guard.sh sweep --apply    remove what the report says can go
    disk-guard.sh status           check, then the ten largest entries under AGENT_WORK

A sweep removes registered cache roots and nothing else under AGENT_WORK:

  - Registration: cache-roots.tsv beside this script, then <status>/cache-roots.tsv (or the
    files named in LIFECYCLE_CACHE_ROOTS, colon-separated). One root per line:
    path<TAB>kind<TAB>policy<TAB>note. The path is relative to AGENT_WORK and may use * ? []
    in a segment; a wildcard never matches a name with a space, '=' or a quote (those are
    registered by their exact name). kind is go-build, go-mod, npm or go-build-chain (a chain
    of single directories ending in a Go build cache, left by a GOCACHE that held a whole
    line of assignments). policy says what proves the owner is done:
      run.done   the first directory of the path holds run.done, older than
                 LIFECYCLE_DONE_MIN_AGE_MIN (120), and nothing in the cache is newer than it
      ended      the note records who confirmed the owner finished; nothing written for
                 LIFECYCLE_DONE_MIN_AGE_MIN
      cap=<GiB>  a shared root: removed whole when larger than the cap (what go clean -cache,
                 go clean -modcache and npm cache clean do), after the same checks; the
                 tools themselves are not called because they follow the path
  - Layout: the whole tree is read before anything is removed, and every level accepts only
    the entries the tool writes there. A symlink, a nested .git, another filesystem, a file
    the layout does not have (a hand-written .go, notes, ignored material), a non-empty
    _cacache/tmp or cache/vcs, or a read error anywhere keeps the whole root, with the reason.
  - In a Git worktree (looked for above AGENT_WORK too) the root must hold no tracked file
    and Git must report it ignored; a Git error keeps it.
  - Open files: one lsof snapshot before and one after; lsof failing or printing any warning
    keeps everything, except a can't-stat warning about a mount in
    LIFECYCLE_LSOF_TOLERATED_MOUNTS (which may not overlap AGENT_WORK).
  - One sweep at a time per machine (flock on LIFECYCLE_LOCK/lock, default
    AGENT_WORK/.lifecycle.lock). Paths are resolved once, without following links; from then
    on only directory handles are used. A root that passes is renamed to
    <name>.lifecycle-del-<run> through a handle on its parent, after checking every directory
    on the path is still the one first checked (device and inode), checked again in full
    (layout, end evidence, tracked files, open files), then removed through handles; if any
    check fails it is renamed back. A rename left by a sweep that died is finished next time.

Everything else is reported, never removed: caches found by name that nobody registered
(review dirs, the other entries of AGENT_WORK/.cache), worktrees and branches (S2,
prune-merged-branches.sh --local-only), node_modules (each reported with its size). With
--apply the host steps that the
Owner set on 2026-10-21 also run (R13): Docker build cache and dangling images older than 7
days once a week, the default Go build cache over DEFAULT_GOCACHE_CAP_GB (30) while no Go
build runs, SysV shared memory a killed test Postgres left (macOS), local Time Machine
snapshots thinned when still under STOP_GB (macOS). --no-host skips them.

Environment: AGENT_WORK (~/agent-work), WARN_GB, STOP_GB, DISK_GUARD_VOLUME (AGENT_WORK),
LIFECYCLE_CACHE_ROOTS, LIFECYCLE_STATUS_DIR (AGENT_WORK/status), LIFECYCLE_LOCK,
LIFECYCLE_DONE_MIN_AGE_MIN, LIFECYCLE_LSOF (lsof), LIFECYCLE_LSOF_TOLERATED_MOUNTS,
LIFECYCLE_EXCLUDE (colon-separated paths
under AGENT_WORK another owner manages, e.g. agentd), LIFECYCLE_DISCOVER (codex-review-*),
DEFAULT_GOCACHE_CAP_GB, CURSOR_DB_WARN_GB.

Exit: check 0/1/2 as above; sweep 0 when the report is written, 3 when another sweep holds
the lock, 4 when the configuration is unusable or the report cannot be written.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import signal
import socket
import sys
import time
from typing import Dict, List, Optional, Tuple

from disk_guard_base import O_DIR, Config, ConfigError, GIB, free_space, gib, load_config, now_utc, thresholds
from disk_guard_layout import du
from disk_guard_roots import Entry, OpenFiles, parse_registry
from disk_guard_items import classify, discovered_items, registered_items, unmanaged_items
from disk_guard_apply import Lock, apply_items
from disk_guard_host import host_steps, thin_snapshots


def level(space: Dict[str, object], warn_gb: float, stop_gb: float) -> Tuple[int, str]:
    if "error" in space:
        return 2, f"disk-guard: cannot read free space ({space['error']}): treat it as under {stop_gb:g} GiB"
    f = int(space["free_bytes"]) / GIB  # type: ignore[arg-type]
    if f < stop_gb:
        return 2, f"disk-guard: {f:.0f} GiB free (< {stop_gb:g}): sweep now and tell the Owner"
    if f < warn_gb:
        return 1, f"disk-guard: {f:.0f} GiB free (< {warn_gb:g}): no new review, npm ci or worktree until it is above"
    return 0, f"disk-guard: {f:.0f} GiB free"


def cmd_check(env: Dict[str, str]) -> int:
    try:
        warn, stop = thresholds(env)
    except ConfigError as e:
        print(f"disk-guard: {e}: treat it as under the stop line")
        return 2
    home = env.get("HOME") or os.path.expanduser("~")
    volume = env.get("DISK_GUARD_VOLUME", "").strip() or env.get("AGENT_WORK", "").strip() or os.path.join(home, "agent-work")
    rc, msg = level(free_space(volume), warn, stop)
    print(msg)
    return rc


def cmd_status(env: Dict[str, str]) -> int:
    rc = cmd_check(env)
    try:
        cfg = load_config(env)
    except ConfigError as e:
        print(f"disk-guard: {e}")
        return rc
    sizes = []
    for n in sorted(os.listdir(cfg.agent_work)):
        sizes.append((du(os.path.join(cfg.agent_work, n)), n))
    for b, n in sorted(sizes, reverse=True)[:10]:
        print(f"{b / GIB:7.1f} GiB  {n}")
    return rc


def _terminated(signum: int, frame: object) -> None:
    # launchd and systemd stop a job with SIGTERM: unwind so the lock is released.
    raise SystemExit(128 + signum)


def sweep(env: Dict[str, str], apply: bool, host: bool) -> int:
    try:
        cfg = load_config(env)
    except ConfigError as e:
        print(f"disk-guard: {e}")
        return 4
    run_id = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}"
    lock = Lock(cfg.lock_dir, run_id)
    ok, why = lock.acquire()
    if not ok:
        print(f"disk-guard: {why}; this run stops")
        return 3
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _terminated)
    try:
        return _sweep_locked(cfg, run_id, apply, host)
    finally:
        lock.release()
        signal.signal(signal.SIGTERM, previous)


def _sweep_locked(cfg: Config, run_id: str, apply: bool, host: bool) -> int:
    started = now_utc()
    entries: List[Entry] = []
    reg_report = []
    errors: List[str] = []
    for path, required in cfg.registries:
        e, errs = parse_registry(path, required)
        entries += e
        errors += errs
        reg_report.append({"path": path, "entries": len(e), "errors": errs})
    try:
        aw_fd = os.open(cfg.agent_work, O_DIR)
    except OSError as e:
        print(f"disk-guard: cannot open AGENT_WORK={cfg.agent_work}: {e.strerror or e}")
        return 4
    try:
        items = registered_items(cfg, entries)
        lsof = OpenFiles(cfg)
        now = time.time()
        for it in items:
            classify(cfg, aw_fd, it, lsof, now)
        if apply:
            apply_items(cfg, aw_fd, run_id, items)
        found = discovered_items(cfg, aw_fd, items)
    finally:
        os.close(aw_fd)
    found += unmanaged_items(cfg, [it.path for it in items + found])
    steps = host_steps(cfg, apply) if host else []
    tm = thin_snapshots(cfg, apply) if host else None
    if tm:
        steps.append(tm)
    space = free_space(cfg.volume)
    rc, level_msg = level(space, cfg.warn_gb, cfg.stop_gb)
    every = items + found
    counts: Dict[str, int] = {}
    sizes: Dict[str, int] = {}
    reasons: Dict[str, int] = {}
    for it in every:
        act = it.action if apply or it.action == "keep" else f"would-{it.action}"
        it.action = act
        counts[act] = counts.get(act, 0) + 1
        sizes[act] = sizes.get(act, 0) + it.bytes
        if act == "keep":
            reasons[it.reason] = reasons.get(it.reason, 0) + 1
    report = {
        "schema": 1,
        "tool": "disk-guard (scripts/agent-host/disk_guard.py)",
        "run_id": run_id,
        "host": socket.gethostname(),
        "mode": "apply" if apply else "report-only",
        "started_at": started,
        "finished_at": now_utc(),
        "agent_work": cfg.agent_work,
        "volume": {**space, "warn_gib": cfg.warn_gb, "stop_gib": cfg.stop_gb, "level": ["ok", "warn", "stop"][rc]},
        "registries": reg_report,
        "counts": counts,
        "bytes": sizes,
        "kept_reasons": dict(sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))),
        "lsof": {"ok": lsof.ok, "error": lsof.error, "scope": "processes of this user" if os.geteuid() != 0 else "all processes"},
        "items": [it.public() for it in every],
        "host_steps": steps,
        "not_in_this_sweep": "worktrees and local branches (S2: prune-merged-branches.sh --local-only); remote branches; node_modules are reported, not removed",
        "errors": errors,
    }
    status_file = os.path.join(cfg.status_dir, "lifecycle.json")
    try:
        os.makedirs(cfg.status_dir, exist_ok=True)
        tmp = f"{status_file}.tmp-{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, status_file)
        wrote = True
    except OSError as e:
        print(f"disk-guard: cannot write {status_file}: {e}")
        wrote = False
    mode = "apply" if apply else "report only (--apply removes)"
    print(f"disk-guard: sweep {run_id}, {mode}, AGENT_WORK={cfg.agent_work}")
    for act in sorted(counts):
        print(f"disk-guard:   {act}: {counts[act]} ({gib(sizes[act])})")
    if reasons:
        print("disk-guard:   kept because: " + ", ".join(f"{k} {v}" for k, v in report["kept_reasons"].items()))  # type: ignore[union-attr]
    for s in steps:
        print(f"disk-guard:   host {s['step']}: {s['action']} ({s['detail']})")
    for e in errors:
        print(f"disk-guard:   registry: {e}")
    if wrote:
        print(f"disk-guard: report {status_file}")
    print(level_msg)
    return 0 if wrote else 4


def main(argv: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None) -> int:
    env = dict(os.environ if env is None else env)
    ap = argparse.ArgumentParser(prog="disk-guard.sh", description="Free-space check and lifecycle sweep (see the module docstring).")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("check")
    sp = sub.add_parser("sweep")
    sp.add_argument("--apply", action="store_true", help="remove what the report says can go (default: report only)")
    sp.add_argument("--no-host", action="store_true", help="skip the host steps (Docker, default Go cache, shared memory, Time Machine)")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    if args.cmd in (None, "check"):
        return cmd_check(env)
    if args.cmd == "status":
        return cmd_status(env)
    return sweep(env, apply=args.apply, host=not args.no_host)


if __name__ == "__main__":
    sys.exit(main())
