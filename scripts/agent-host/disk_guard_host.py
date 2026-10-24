"""Host steps of the sweep (R13; Owner 2026-10-21): Docker, the default Go build cache,
SysV shared memory a killed test Postgres left, Cursor's state DB, Time Machine local
snapshots. Each acts only with --apply; a report-only run says what it would do.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

from disk_guard_base import Config, GIB, _under, free_space, gib, now_utc
from disk_guard_layout import du


def _which(cfg: Config, name: str) -> Optional[str]:
    return shutil.which(name, path=cfg.env.get("PATH"))


def _run(cfg: Config, argv: List[str], timeout: int = 120, extra_env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    env = dict(cfg.env)
    if extra_env:
        env.update(extra_env)
    try:
        r = subprocess.run(argv, env=env, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)
    return r.returncode, r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace")


def host_steps(cfg: Config, apply: bool) -> List[Dict[str, object]]:
    steps: List[Dict[str, object]] = []
    darwin = sys.platform == "darwin"

    def step(name: str, action: str, detail: str) -> None:
        steps.append({"step": name, "action": action, "detail": detail})

    # Default Go build cache over the cap while no Go build runs.
    go = _which(cfg, "go")
    if go:
        rc, out, err = _run(cfg, [go, "env", "GOCACHE"])
        gc = out.strip()
        if rc != 0 or not gc:
            step("default-go-cache", "skip", f"go env GOCACHE failed: {err.strip()[:200]}")
        elif _under(os.path.realpath(gc), cfg.agent_work):
            step("default-go-cache", "skip", "GOCACHE is under AGENT_WORK: only the registry decides there")
        elif os.path.isdir(gc) and not os.path.islink(gc):
            size = du(gc)[0]
            cap = int(cfg.host_go_cap_gb * GIB)
            if size <= cap:
                step("default-go-cache", "keep", f"{gib(size)} <= cap {gib(cap)}")
            else:
                pg = _which(cfg, "pgrep")
                rc2 = _run(cfg, [pg, "-f", "/compile |/link |go (build|test|vet) "])[0] if pg else -1
                if rc2 == 0:
                    step("default-go-cache", "keep", f"{gib(size)} over cap, but a Go build is running")
                elif rc2 != 1:
                    step("default-go-cache", "keep", f"{gib(size)} over cap, but pgrep could not tell whether a Go build runs")
                elif not apply:
                    step("default-go-cache", "would-clean", f"{gib(size)} > cap {gib(cap)}: go clean -cache")
                else:
                    rc3, _, err3 = _run(cfg, [go, "clean", "-cache"], timeout=3600)
                    step("default-go-cache", "cleaned" if rc3 == 0 else "failed", f"{gib(size)}: go clean -cache {err3.strip()[:200]}".strip())
        else:
            step("default-go-cache", "skip", "no default Go build cache")
    # SysV shared memory a killed test Postgres left: no process attached, 56 bytes, creator gone.
    if darwin:
        ipcs = _which(cfg, "ipcs")
        rc, out, err = _run(cfg, [ipcs, "-ma"]) if ipcs else (-1, "", "ipcs not found")
        if rc != 0:
            step("shared-memory", "skip", f"ipcs failed: {err.strip()[:200]}")
        else:
            leaked = []
            for line in out.splitlines()[3:]:
                cols = line.split()
                if len(cols) >= 11 and cols[1].isdigit() and cols[8] == "0" and cols[9] == "56" and cols[10].isdigit():
                    try:
                        os.kill(int(cols[10]), 0)
                        continue
                    except ProcessLookupError:
                        leaked.append(cols[1])
                    except (PermissionError, OverflowError):
                        continue
            if not leaked:
                step("shared-memory", "keep", "no leaked segment")
            elif not apply:
                step("shared-memory", "would-remove", f"{len(leaked)} leaked segments")
            else:
                ipcrm = _which(cfg, "ipcrm")
                n = sum(1 for sid in leaked if ipcrm and _run(cfg, [ipcrm, "-m", sid])[0] == 0)
                step("shared-memory", "removed", f"{n} of {len(leaked)} leaked segments")
    # Review caches some sessions left in the system temp dir: not registered, so reported
    # only, every one with its size and age (review 543 B, 544 D), for their producers to clean.
    try:
        left = sorted(n for n in os.listdir(cfg.tmp_root) if n.startswith("review"))
    except OSError:
        left = []
    if left:
        now, rows = time.time(), []
        for n in left[:500]:
            p = os.path.join(cfg.tmp_root, n)
            size, complete = du(p)
            try:
                age = round((now - os.lstat(p).st_mtime) / 86400, 1)
            except OSError:
                age, complete = None, False
            rows.append({"name": n, "bytes": size, "bytes_complete": complete, "age_days": age})
        more = f"; {len(left) - 500} more not listed" if len(left) > 500 else ""
        steps.append({"step": "tmp-review-dirs", "action": "keep", "entries": rows,
                      "detail": f"{len(left)} {cfg.tmp_root}/review* entries ({gib(sum(r['bytes'] for r in rows))}), not registered, reported only{more}"})
    # Cursor's state DB: compacting it needs Cursor closed, so it is only reported.
    if darwin:
        home = cfg.env.get("HOME") or os.path.expanduser("~")
        cdb = os.path.join(home, "Library", "Application Support", "Cursor", "User", "globalStorage", "state.vscdb")
        try:
            size = os.stat(cdb).st_size
            if size > cfg.cursor_warn_gb * GIB:
                step("cursor-state-db", "tell-owner", f"state.vscdb is {gib(size)}: compact it with Cursor closed")
        except OSError:
            pass
    # Docker, at most once a week: build cache and dangling images older than 7 days.
    docker = _which(cfg, "docker")
    if docker:
        stamp = os.path.join(cfg.status_dir, "docker-pruned-at")
        # the old ~/agent-work/bin/disk-guard.sh kept its stamp in .cache: honour the newer
        ages = []
        for st_path in (stamp, os.path.join(cfg.agent_work, ".cache", "docker-pruned-at")):
            try:
                ages.append(time.time() - os.stat(st_path).st_mtime)
            except OSError:
                pass
        age = min(ages) if ages else None
        if age is not None and age < 6.5 * 86400:
            step("docker", "keep", f"pruned {age / 86400:.1f} days ago")
        elif _run(cfg, [docker, "info"], timeout=30)[0] != 0:
            step("docker", "skip", "docker is not running")
        elif not apply:
            step("docker", "would-prune", "build cache and dangling images older than 7 days")
        else:
            r1 = _run(cfg, [docker, "builder", "prune", "-a", "-f", "--filter", "until=168h"], timeout=1800)
            r2 = _run(cfg, [docker, "image", "prune", "-f", "--filter", "until=168h"], timeout=1800)
            tail = lambda r: (r[1].strip().splitlines() or [r[2].strip()])[-1:]  # noqa: E731
            step("docker", "pruned" if r1[0] == 0 and r2[0] == 0 else "failed", f"build cache: {tail(r1)}; images: {tail(r2)}")
            if r1[0] == 0 and r2[0] == 0:
                try:
                    os.makedirs(cfg.status_dir, exist_ok=True)
                    with open(stamp, "w") as f:
                        f.write(now_utc() + "\n")
                except OSError:
                    pass
    return steps


def thin_snapshots(cfg: Config, apply: bool) -> Optional[Dict[str, object]]:
    if sys.platform != "darwin":
        return None
    space = free_space(cfg.volume)
    if "error" not in space and int(space["free_bytes"]) >= cfg.stop_gb * GIB:  # type: ignore[arg-type]
        return None
    if not apply:
        return {"step": "time-machine", "action": "would-thin", "detail": f"under {cfg.stop_gb:g} GiB after the sweep"}
    tm = _which(cfg, "tmutil")
    if not tm:
        return {"step": "time-machine", "action": "skip", "detail": "tmutil not found"}
    rc, out, err = _run(cfg, [tm, "thinlocalsnapshots", "/", "60000000000", "4"], timeout=1800)
    return {"step": "time-machine", "action": "thinned" if rc == 0 else "failed", "detail": (out + err).strip()[:300]}
