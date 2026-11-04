#!/usr/bin/env python3
"""Set owner and mode on a copy from its source (TD-444 step 5 runbook §3.3, §5.1).

UGOS's rsync (1.18, rsync 3.4.1) copies contents, times and links but leaves owner and mode
unset, without an error: what it creates is root:root with mode 000 (NAS probe 11-04: a
`rsync -a --numeric-ids` copy of one file came out 000 0:0; chown and chmod on the same file
work). td444-move.sh (after every pre and final copy) and backup-rollup/rollup.sh (after every
generation's copy) run this before the verification, which stays the only gate.

  python3 -I td444-attrs.py --src <source dir> --dst <target dir>

Both trees are walked through directory file descriptors opened with O_DIRECTORY|O_NOFOLLOW,
level by level, and every call names its path relative to such a descriptor without following
a symlink: no component of any path, the roots included, is ever resolved through a symlink,
so nothing outside the target tree (the source least of all) can be changed. The source is
only read. For every path under the source the target path must exist with the same type;
its owner and group and, except for symlinks, its mode bits (07777, setuid/setgid/sticky
included) are set to the source's, owner first because chown may clear setuid/setgid.
A root that is not a real directory stops at once; a directory whose target is of another type
(a symlink included) is reported and never entered. One target inode reached by several names
(hard links) is set once, and every further name must want the same owner and mode from its
own source path, or that is an error. Exit 0 only when every path was set; anything else is
reported (the first 20) and exits 1.
"""
import argparse
import errno
import os
import stat
import sys
import time

MAX_REPORT = 20
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class Fixer:
    def __init__(self, dst_name):
        self.dst_name = dst_name
        self.errors = []
        self.paths = self.changed = self.repeats = 0
        self.inodes = {}     # target (dev, ino) -> (uid, gid, mode) wanted by the first name

    def fail(self, msg):
        self.errors.append(msg)
        if len(self.errors) <= MAX_REPORT:
            print("td444-attrs: " + msg, flush=True)

    def wanted(self, s):
        return s.st_uid, s.st_gid, stat.S_IMODE(s.st_mode)

    def first_name(self, rel, s, d):
        """False when this target inode was set already (or conflicts, which is reported)."""
        if stat.S_ISDIR(d.st_mode) or d.st_nlink < 2:
            return True
        key, want = (d.st_dev, d.st_ino), self.wanted(s)
        if key not in self.inodes:
            self.inodes[key] = want
            return True
        if self.inodes[key] != want:
            self.fail("%s shares its target inode with another name, but its source wants owner %d:%d mode %04o, not %d:%d %04o"
                      % ((rel,) + want + self.inodes[key]))
        else:
            self.repeats += 1
        return False

    def set_fd(self, rel, fd, s, d):
        want = self.wanted(s)
        if (d.st_uid, d.st_gid, stat.S_IMODE(d.st_mode)) == want:
            return
        try:
            os.fchown(fd, s.st_uid, s.st_gid)
            os.fchmod(fd, want[2])
        except OSError as e:
            self.fail("cannot set owner %d:%d and mode %04o on %s: %s" % (want + (rel, e.strerror)))
            return
        self.changed += 1

    def entry(self, rel, name, sfd, dfd, s):
        """One non-directory entry (regular file, symlink, other) of a directory pair."""
        self.paths += 1
        try:
            d = os.stat(name, dir_fd=dfd, follow_symlinks=False)
        except FileNotFoundError:
            self.fail("the target lacks %s" % rel)
            return
        except OSError as e:
            self.fail("cannot read %s on the target: %s" % (rel, e.strerror))
            return
        if stat.S_IFMT(d.st_mode) != stat.S_IFMT(s.st_mode):
            self.fail("%s is another type on the target than in the source" % rel)
            return
        if not self.first_name(rel, s, d):
            return
        if stat.S_ISLNK(s.st_mode):
            if (d.st_uid, d.st_gid) != (s.st_uid, s.st_gid):
                try:
                    os.chown(name, s.st_uid, s.st_gid, dir_fd=dfd, follow_symlinks=False)
                    self.changed += 1
                except OSError as e:
                    self.fail("cannot set owner %d:%d on the symlink %s: %s" % (s.st_uid, s.st_gid, rel, e.strerror))
            return
        if stat.S_ISREG(s.st_mode):
            try:
                fd = os.open(name, FILE_FLAGS, dir_fd=dfd)
            except OSError as e:
                self.fail("cannot open %s on the target: %s" % (rel, e.strerror))
                return
            try:
                if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != (d.st_dev, d.st_ino):
                    self.fail("%s changed on the target while it was set" % rel)
                else:
                    self.set_fd(rel, fd, s, d)
            finally:
                os.close(fd)
            return
        # fifos, sockets, devices: opening them is not safe; the name is not a symlink (lstat
        # above) and the target is ours alone while it is set
        want = self.wanted(s)
        if (d.st_uid, d.st_gid, stat.S_IMODE(d.st_mode)) == want:
            return
        try:
            os.chown(name, s.st_uid, s.st_gid, dir_fd=dfd, follow_symlinks=False)
            os.chmod(name, want[2], dir_fd=dfd)
            self.changed += 1
        except OSError as e:
            self.fail("cannot set owner %d:%d and mode %04o on %s: %s" % (want + (rel, e.strerror)))

    def directory(self, rel, sfd, dfd):
        """A directory pair, both opened without following any symlink: set it, then its entries."""
        self.paths += 1
        s, d = os.fstat(sfd), os.fstat(dfd)
        self.set_fd(rel, dfd, s, d)
        try:
            names = sorted(os.listdir(sfd))
        except OSError as e:
            self.fail("cannot list %s in the source: %s" % (rel, e.strerror))
            return
        for name in names:
            sub = name if rel == "." else rel + "/" + name
            try:
                cs = os.stat(name, dir_fd=sfd, follow_symlinks=False)
            except OSError as e:
                self.fail("cannot read %s in the source: %s" % (sub, e.strerror))
                continue
            if not stat.S_ISDIR(cs.st_mode):
                self.entry(sub, name, sfd, dfd, cs)
                continue
            try:
                csfd = os.open(name, DIR_FLAGS, dir_fd=sfd)
            except OSError as e:
                self.fail("cannot open %s in the source: %s" % (sub, e.strerror))
                continue
            try:
                try:
                    cdfd = os.open(name, DIR_FLAGS, dir_fd=dfd)
                except FileNotFoundError:
                    self.paths += 1
                    self.fail("the target lacks %s" % sub)
                    continue
                except OSError as e:
                    self.paths += 1
                    why = "another type (a symlink or no directory)" if e.errno in (errno.ELOOP, errno.ENOTDIR) else e.strerror
                    self.fail("%s on the target is %s; not entered" % (sub, why))
                    continue
                try:
                    self.directory(sub, csfd, cdfd)
                finally:
                    os.close(cdfd)
            finally:
                os.close(csfd)


def open_root(path, which):
    try:
        return os.open(path, DIR_FLAGS)
    except OSError as e:
        why = "a symlink or no directory" if e.errno in (errno.ELOOP, errno.ENOTDIR) else e.strerror
        print("td444-attrs: the %s %s is %s; nothing done" % (which, path, why), flush=True)
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()
    t0 = time.monotonic()
    sfd = open_root(a.src, "source")
    if sfd is None:
        return 1
    dfd = open_root(a.dst, "target")
    if dfd is None:
        os.close(sfd)
        return 1
    f = Fixer(a.dst)
    try:
        f.directory(".", sfd, dfd)
    finally:
        os.close(sfd)
        os.close(dfd)
    print("td444-attrs: %s: %d paths, owner and mode set on %d, %d hard-link repeats, %d errors, %.1f s"
          % (a.dst, f.paths, f.changed, f.repeats, len(f.errors), time.monotonic() - t0), flush=True)
    return 0 if not f.errors else 1


if __name__ == "__main__":
    sys.exit(main())
