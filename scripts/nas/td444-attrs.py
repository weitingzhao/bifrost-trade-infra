#!/usr/bin/env python3
"""Set owner and mode on a copy from its source (TD-444 step 5 runbook §3.3).

UGOS's rsync (1.18, rsync 3.4.1) copies contents, times and links but leaves owner and mode
unset, without an error: what it creates is root:root with mode 000 (NAS probe 11-04: a
`rsync -a --numeric-ids` copy of one file came out 000 0:0; chown and chmod on the same file
work). td444-move.sh therefore runs this after every pre and final copy and before the
verification, which stays the only gate (rsync -c -n --itemize-changes must list nothing).

  python3 -I td444-attrs.py --src <source dir> --dst <target dir>

For every path under the source (the source itself included, no symlink followed) the
target path must exist and be of the same type; its owner and group (lchown) and, except for
symlinks, its mode bits (07777, setuid/setgid/sticky included) are set to the source's,
owner first because chown may clear setuid/setgid. A hard-linked target inode is handled
once. Python 3.11 has no chmod without following symlinks on Linux, so a path is chmod'ed
only after lstat showed it is not a symlink (the target is ours alone while the move runs).
Exit 0 only when every path was set; any missing path, type mismatch or failed call is
reported (the first 20) and exits 1.
"""
import argparse
import os
import stat
import sys
import time

MAX_REPORT = 20


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()
    t0 = time.monotonic()
    errors = []
    paths = changed = repeats = 0
    seen = set()

    def fail(msg):
        errors.append(msg)
        if len(errors) <= MAX_REPORT:
            print("td444-attrs: " + msg, flush=True)

    def fix(rel, s):
        nonlocal paths, changed, repeats
        paths += 1
        dst = os.path.join(a.dst, rel) if rel != "." else a.dst
        try:
            d = os.lstat(dst)
        except FileNotFoundError:
            fail("the target lacks %s" % rel)
            return
        except OSError as e:
            fail("cannot read %s on the target: %s" % (rel, e.strerror))
            return
        if stat.S_IFMT(d.st_mode) != stat.S_IFMT(s.st_mode):
            fail("%s is another type on the target than in the source" % rel)
            return
        if d.st_nlink > 1 and not stat.S_ISDIR(d.st_mode):
            if (d.st_dev, d.st_ino) in seen:
                repeats += 1
                return
            seen.add((d.st_dev, d.st_ino))
        want = stat.S_IMODE(s.st_mode)
        if (d.st_uid, d.st_gid) == (s.st_uid, s.st_gid) and (stat.S_ISLNK(d.st_mode) or stat.S_IMODE(d.st_mode) == want):
            return
        try:
            os.chown(dst, s.st_uid, s.st_gid, follow_symlinks=False)
            if not stat.S_ISLNK(d.st_mode):
                os.chmod(dst, want)
        except OSError as e:
            fail("cannot set owner %d:%d and mode %04o on %s: %s" % (s.st_uid, s.st_gid, want, rel, e.strerror))
            return
        changed += 1

    try:
        root = os.lstat(a.src)
    except OSError as e:
        print("td444-attrs: cannot read the source %s: %s" % (a.src, e.strerror))
        return 1
    if not stat.S_ISDIR(root.st_mode):
        print("td444-attrs: the source %s is not a directory" % a.src)
        return 1
    fix(".", root)
    stack = [""]
    while stack:
        rel_dir = stack.pop()
        try:
            with os.scandir(os.path.join(a.src, rel_dir) if rel_dir else a.src) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as e:
            fail("cannot list %s in the source: %s" % (rel_dir or ".", e.strerror))
            continue
        for e in entries:
            rel = os.path.join(rel_dir, e.name) if rel_dir else e.name
            try:
                s = e.stat(follow_symlinks=False)
            except OSError as err:
                fail("cannot read %s in the source: %s" % (rel, err.strerror))
                continue
            fix(rel, s)
            if stat.S_ISDIR(s.st_mode):
                stack.append(rel)
    print("td444-attrs: %s: %d paths, owner and mode set on %d, %d hard-link repeats, %d errors, %.1f s"
          % (a.dst, paths, changed, repeats, len(errors), time.monotonic() - t0), flush=True)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
