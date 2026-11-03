#!/usr/bin/env python3
"""Nightly copy of the market-data archive onto the SSD share (TD-444 step 5 runbook §5.2).

Source: the archive the market-data plugin writes (read-only mount). Layout and ledger
are the plugin's (bifrost-platform-plugin-market-data src/bifrost_market_data/
retention_archive.py: layout docstring, archive_range, the ledger keys):

    raw_market/<table without schema>/<kind>/<start year>/<file>.parquet  (+ .json manifest)
    raw_market/_ledger.jsonl   one JSON object per line:
        table, kind, start, end_exclusive, rows, sha256, file, archived_at

Rules (§5.2):
- the source ledger is read once; only lines that end in a newline are used, a
  trailing partial line is left for the next run;
- every record is validated (keys, names, dates, path stays inside the mount root,
  no symlink on the way) before anything is copied;
- a file is copied to <name>.partial, fsynced, checked against the ledger sha256 and
  renamed; an existing target with other content is a failure, never overwritten;
  the .json manifest is copied the same way and must name the same sha256;
- files that are not in the ledger (a crash between rename and ledger line) are ignored;
- only when every complete line verified, the target ledger is replaced by exactly
  those bytes (a prefix of the source ledger) and _replica.state records the boundary;
- any problem exits 1 and leaves the target ledger as it was. Nothing is ever deleted.

Usage: market_archive_replica.py --src /archive --dst /replica [--no-require-mount]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

LEDGER = Path("raw_market") / "_ledger.jsonl"
STATE = "_replica.state"
KEYS = {"table", "kind", "start", "end_exclusive", "rows", "sha256", "file", "archived_at"}
NAME = re.compile(r"[a-z][a-z0-9_]{0,62}")
SHA = re.compile(r"[0-9a-f]{64}")
FILE = re.compile(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})__\d{8}T\d{6}Z\.parquet")
CHUNK = 1 << 20


class ReplicaError(Exception):
    pass


def log(msg: str) -> None:
    print(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def safe_path(root: Path, rel: Path, create_dirs: bool = False) -> Path:
    """root/rel, with every existing component checked to be a real directory or file (no symlink)."""
    if rel.is_absolute() or any(p in ("", ".", "..") for p in rel.parts):
        raise ReplicaError(f"bad relative path {rel}")
    cur = root
    for i, part in enumerate(rel.parts):
        cur = cur / part
        last = i == len(rel.parts) - 1
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            if create_dirs and not last:
                os.mkdir(cur, 0o755)
                continue
            if last:
                break
            raise ReplicaError(f"missing directory {cur}")
        if stat.S_ISLNK(st.st_mode):
            raise ReplicaError(f"symlink on the path: {cur}")
        if not last and not stat.S_ISDIR(st.st_mode):
            raise ReplicaError(f"not a directory: {cur}")
    real_root = os.path.realpath(root)
    real = os.path.realpath(cur)
    if os.path.commonpath([real_root, real]) != real_root:
        raise ReplicaError(f"{cur} resolves outside {root}")
    return cur


def parse_ledger(data: bytes) -> tuple[list[dict], int]:
    """Complete lines only. Returns (records, byte boundary after the last complete line)."""
    boundary = data.rfind(b"\n") + 1
    if boundary < len(data):
        log(f"ledger: trailing partial line of {len(data) - boundary} bytes left for the next run")
    records = []
    seen: dict[str, str] = {}
    for n, line in enumerate(data[:boundary].split(b"\n")[:-1], start=1):
        try:
            rec = json.loads(line)
        except ValueError as e:
            raise ReplicaError(f"ledger line {n}: not JSON ({e})")
        if not isinstance(rec, dict) or set(rec) != KEYS:
            raise ReplicaError(f"ledger line {n}: keys are {sorted(rec) if isinstance(rec, dict) else type(rec)}")
        schema, _, table = str(rec["table"]).partition(".")
        if schema != "raw_market" or not NAME.fullmatch(table):
            raise ReplicaError(f"ledger line {n}: bad table {rec['table']!r}")
        if not NAME.fullmatch(str(rec["kind"])):
            raise ReplicaError(f"ledger line {n}: bad kind {rec['kind']!r}")
        try:
            start = dt.date.fromisoformat(str(rec["start"]))
            end = dt.date.fromisoformat(str(rec["end_exclusive"]))
        except ValueError:
            raise ReplicaError(f"ledger line {n}: bad dates")
        if end <= start:
            raise ReplicaError(f"ledger line {n}: end_exclusive not after start")
        m = FILE.fullmatch(str(rec["file"]))
        if not m or m.group(1) != start.isoformat():
            raise ReplicaError(f"ledger line {n}: file {rec['file']!r} does not match start {start}")
        if not SHA.fullmatch(str(rec["sha256"])):
            raise ReplicaError(f"ledger line {n}: bad sha256")
        if not isinstance(rec["rows"], int) or rec["rows"] < 0:
            raise ReplicaError(f"ledger line {n}: bad rows")
        rel = Path("raw_market") / table / rec["kind"] / f"{start:%Y}" / rec["file"]
        prev = seen.get(str(rel))
        if prev is not None and prev != rec["sha256"]:
            raise ReplicaError(f"ledger line {n}: {rel} listed twice with different sha256")
        seen[str(rel)] = rec["sha256"]
        rec["_rel"] = rel
        records.append(rec)
    return records, boundary


def copy_verified(src: Path, dst: Path, expect_sha: str | None) -> str:
    """Copy src to dst via dst.partial; return the sha256 of the bytes written."""
    tmp = dst.with_name(dst.name + ".partial")
    if tmp.exists():
        tmp.unlink()
    h = hashlib.sha256()
    with src.open("rb") as fi, open(tmp, "xb") as fo:
        for block in iter(lambda: fi.read(CHUNK), b""):
            h.update(block)
            fo.write(block)
        fo.flush()
        os.fsync(fo.fileno())
    got = h.hexdigest()
    if expect_sha is not None and got != expect_sha:
        tmp.unlink()
        raise ReplicaError(f"{src}: sha256 {got} differs from the ledger {expect_sha}")
    if sha256_of(tmp) != got:
        tmp.unlink()
        raise ReplicaError(f"{tmp}: read-back sha256 differs")
    os.replace(tmp, dst)
    fsync_dir(dst.parent)
    return got


def replicate(src_root: Path, dst_root: Path) -> int:
    ledger_src = safe_path(src_root, LEDGER)
    data = ledger_src.read_bytes()
    records, boundary = parse_ledger(data)
    log(f"ledger: {len(records)} complete records, boundary {boundary} bytes")

    ledger_dst = safe_path(dst_root, LEDGER, create_dirs=True)
    if ledger_dst.exists():
        old = ledger_dst.read_bytes()
        if not data[:boundary].startswith(old):
            raise ReplicaError("target ledger is not a prefix of the source ledger; refusing")

    copied = skipped = 0
    for rec in records:
        rel = rec["_rel"]
        src = safe_path(src_root, rel)
        if not src.exists():
            raise ReplicaError(f"{rel}: in the ledger but missing at the source")
        if sha256_of(src) != rec["sha256"]:
            raise ReplicaError(f"{rel}: source content differs from the ledger")
        dst = safe_path(dst_root, rel, create_dirs=True)
        if dst.exists():
            if sha256_of(dst) != rec["sha256"]:
                raise ReplicaError(f"{rel}: target exists with other content; not overwriting")
            skipped += 1
        else:
            copy_verified(src, dst, rec["sha256"])
            copied += 1
        jrel = rel.with_name(rel.name.removesuffix(".parquet") + ".json")
        jsrc = safe_path(src_root, jrel)
        if jsrc.exists():
            manifest = json.loads(jsrc.read_bytes())
            if manifest.get("sha256") != rec["sha256"] or manifest.get("file") != rec["file"]:
                raise ReplicaError(f"{jrel}: manifest does not name the ledger's file / sha256")
            jdst = safe_path(dst_root, jrel, create_dirs=True)
            want = sha256_of(jsrc)
            if jdst.exists():
                if sha256_of(jdst) != want:
                    raise ReplicaError(f"{jrel}: target exists with other content; not overwriting")
            else:
                copy_verified(jsrc, jdst, want)

    tmp = ledger_dst.with_name(ledger_dst.name + ".partial")
    with open(tmp, "wb") as f:
        f.write(data[:boundary])
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, ledger_dst)
    fsync_dir(ledger_dst.parent)
    state = {"boundary": boundary, "records": len(records), "copied": copied, "already_present": skipped,
             "source_ledger_bytes": len(data),
             "published_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    st_tmp = dst_root / (STATE + ".partial")
    st_tmp.write_text(json.dumps(state, indent=2) + "\n")
    os.replace(st_tmp, dst_root / STATE)
    log(f"ok: copied {copied}, already present {skipped}, ledger published up to byte {boundary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, type=Path)
    ap.add_argument("--dst", required=True, type=Path)
    ap.add_argument("--no-require-mount", action="store_true", help="tests only")
    args = ap.parse_args(argv)
    try:
        if not args.no_require_mount:
            for p in (args.src, args.dst):
                if not os.path.ismount(p):
                    raise ReplicaError(f"{p} is not a mount point")
        return replicate(args.src, args.dst)
    except (ReplicaError, OSError) as e:
        log(f"FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
