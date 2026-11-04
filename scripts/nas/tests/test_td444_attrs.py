#!/usr/bin/env python3
"""Tests of td444-attrs.py (TD-444 step 5 runbook §3.3), mostly through its command line.

Run: python3 scripts/nas/tests/test_td444_attrs.py   (test_move_ugos.sh runs it as well)
Fix review round 6: a target of the wrong type is never entered and nothing outside the
target tree, the source least of all, is changed (a directory symlink in the target, a target
root that is a symlink, a target symlink back into the source); target names that share an
inode must want the same owner and mode from their sources.
"""
import contextlib
import importlib.util
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HELPER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "td444-attrs.py")


def mode(p):
    return stat.S_IMODE(os.lstat(p).st_mode)


def put(p, m):
    with open(p, "w") as f:
        f.write("synthetic fixture\n")
    os.chmod(p, m)


class Attrs(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.s, self.t = os.path.join(self.d, "source"), os.path.join(self.d, "target")
        os.mkdir(self.s)
        os.mkdir(self.t)

    def tearDown(self):
        for top, dirs, files in os.walk(self.d):
            for n in dirs:
                p = os.path.join(top, n)
                if not os.path.islink(p):
                    os.chmod(p, 0o755)
        shutil.rmtree(self.d)

    def run_helper(self, src=None, dst=None):
        p = subprocess.run([sys.executable, "-I", HELPER, "--src", src or self.s, "--dst", dst or self.t],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, timeout=30)
        return p.returncode, p.stdout

    # ---- controls
    def test_normal_tree(self):
        s, t, ext = self.s, self.t, os.path.join(self.d, "external")
        put(ext, 0o640)
        for root, fmode in ((s, 0o600), (t, 0o644)):
            os.mkdir(os.path.join(root, "sticky"))
            os.mkdir(os.path.join(root, "sub"))
            put(os.path.join(root, "a"), fmode)
            os.link(os.path.join(root, "a"), os.path.join(root, "b"))
            put(os.path.join(root, "sub", "f"), fmode)
            os.symlink(ext, os.path.join(root, "link"))
        os.chmod(os.path.join(s, "sticky"), 0o1777)
        if os.geteuid() == 0:   # as UGOS leaves them (root reads through mode 000, as on the NAS)
            os.chmod(os.path.join(t, "sub"), 0)
            os.chmod(t, 0)
        rc, out = self.run_helper()
        self.assertEqual(rc, 0, out)
        for x in (".", "a", "b", "sticky", "sub", "sub/f"):
            self.assertEqual(mode(os.path.join(t, x)), mode(os.path.join(s, x)), x)
        self.assertEqual(mode(ext), 0o640, "the leaf symlink's target is untouched")
        self.assertIn("1 hard-link repeats", out)

    def test_published_link_keeps_its_inode_untouched(self):
        pub = os.path.join(self.d, "published")
        os.mkdir(pub)
        put(os.path.join(self.s, "a"), 0o600)
        put(os.path.join(pub, "a"), 0o600)
        os.link(os.path.join(pub, "a"), os.path.join(self.t, "a"))
        before = os.stat(os.path.join(pub, "a")).st_ctime_ns
        rc, out = self.run_helper()
        self.assertEqual(rc, 0, out)
        self.assertEqual(os.stat(os.path.join(pub, "a")).st_ctime_ns, before)

    # ---- reported errors
    def test_missing_path(self):
        put(os.path.join(self.s, "absent"), 0o600)
        rc, out = self.run_helper()
        self.assertEqual(rc, 1, out)
        self.assertIn("the target lacks absent", out)

    def test_leaf_of_another_type(self):
        put(os.path.join(self.s, "leaf"), 0o600)
        os.mkdir(os.path.join(self.t, "leaf"))
        rc, out = self.run_helper()
        self.assertEqual(rc, 1, out)
        self.assertIn("leaf is another type", out)

    # ---- round 6 must-fix: nothing outside the target tree is changed
    def test_directory_symlink_in_target_is_not_entered(self):
        out_dir = os.path.join(self.d, "outside")
        os.mkdir(os.path.join(self.s, "sub"))
        os.mkdir(out_dir)
        put(os.path.join(self.s, "sub", "file"), 0o600)
        put(os.path.join(out_dir, "file"), 0o644)
        os.symlink(out_dir, os.path.join(self.t, "sub"))
        rc, out = self.run_helper()
        self.assertEqual(rc, 1, out)
        self.assertIn("not entered", out)
        self.assertEqual(mode(os.path.join(out_dir, "file")), 0o644, "the file outside the target tree changed")

    def test_target_root_symlink_stops_at_once(self):
        out_dir = os.path.join(self.d, "outside")
        os.mkdir(out_dir)
        put(os.path.join(self.s, "file"), 0o600)
        put(os.path.join(out_dir, "file"), 0o644)
        os.rmdir(self.t)
        os.symlink(out_dir, self.t)
        before = mode(out_dir)
        rc, out = self.run_helper()
        self.assertEqual(rc, 1, out)
        self.assertIn("nothing done", out)
        self.assertEqual(mode(os.path.join(out_dir, "file")), 0o644)
        self.assertEqual(mode(out_dir), before, "the directory the target root points to changed")

    def test_target_symlink_back_into_the_source_changes_nothing_there(self):
        os.mkdir(os.path.join(self.s, "sub"))
        os.mkdir(os.path.join(self.s, "victim"))
        put(os.path.join(self.s, "sub", "file"), 0o600)
        put(os.path.join(self.s, "victim", "file"), 0o644)
        os.mkdir(os.path.join(self.t, "victim"))
        put(os.path.join(self.t, "victim", "file"), 0o644)
        os.symlink(os.path.join(self.s, "victim"), os.path.join(self.t, "sub"))
        rc, out = self.run_helper()
        self.assertEqual(rc, 1, out)
        self.assertEqual(mode(os.path.join(self.s, "victim", "file")), 0o644, "the source changed")

    def test_source_root_symlink_stops_at_once(self):
        real = os.path.join(self.d, "real")
        os.mkdir(real)
        put(os.path.join(real, "f"), 0o600)
        link = os.path.join(self.d, "srclink")
        os.symlink(real, link)
        rc, out = self.run_helper(src=link)
        self.assertEqual(rc, 1, out)
        self.assertIn("the source %s is a symlink or no directory" % link, out)

    # ---- round 6 should-fix 1: one target inode, two different wishes
    def test_conflicting_target_hardlinks(self):
        put(os.path.join(self.s, "a"), 0o600)
        put(os.path.join(self.s, "b"), 0o644)
        put(os.path.join(self.t, "a"), 0o600)
        os.link(os.path.join(self.t, "a"), os.path.join(self.t, "b"))
        rc, out = self.run_helper()
        self.assertEqual(rc, 1, out)
        self.assertIn("b shares its target inode with another name", out)

    # ---- failed calls
    def test_failed_calls(self):
        put(os.path.join(self.s, "a"), 0o600)
        put(os.path.join(self.t, "a"), 0o644)
        spec = importlib.util.spec_from_file_location("td444_attrs", HELPER)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        refused = PermissionError(1, "Operation not permitted")
        for ops in (("chown", "fchown"), ("chmod", "fchmod")):
            out = io.StringIO()
            with mock.patch.object(sys, "argv", [HELPER, "--src", self.s, "--dst", self.t]), \
                    mock.patch.object(m.os, ops[0], side_effect=refused), mock.patch.object(m.os, ops[1], side_effect=refused), \
                    contextlib.redirect_stdout(out):
                rc = m.main()
            self.assertEqual(rc, 1, ops[0] + ": " + out.getvalue())
            self.assertIn("Operation not permitted", out.getvalue())


if __name__ == "__main__":
    unittest.main()
