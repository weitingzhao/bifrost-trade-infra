#!/usr/bin/env python3
"""Tests of registry-check.py through its command line, the entry backup-checks.sh uses
(TD-444 step 5 runbook §3.8 item 1). Every store is synthetic and content-addressed.

Run: python3 scripts/nas/tests/test_registry_check.py   (test_rollup.sh runs it as well)
Fix review round 3: F1 (a manifest referenced again must still match that reference's size
and type, whatever the order), F2 (a tag without a readable current/link fails), S3 (config
and layer media types outside the supported set fail).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

CHECK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "registry-check.py")
DM = "application/vnd.docker.distribution.manifest.v2+json"
DL = "application/vnd.docker.distribution.manifest.list.v2+json"
OM = "application/vnd.oci.image.manifest.v1+json"
OI = "application/vnd.oci.image.index.v1+json"
OCFG = "application/vnd.oci.image.config.v1+json"
OLAY = "application/vnd.oci.image.layer.v1.tar+gzip"
DCFG = "application/vnd.docker.container.image.v1+json"
DLAY = "application/vnd.docker.image.rootfs.diff.tar.gzip"


class Store:
    def __init__(self, root):
        self.v2 = os.path.join(root, "docker", "registry", "v2")
        self.expect = []
        os.makedirs(os.path.join(self.v2, "repositories"))

    def blob(self, data):
        if isinstance(data, dict):
            data = json.dumps(data, separators=(",", ":"))
        raw = data.encode()
        h = hashlib.sha256(raw).hexdigest()
        d = os.path.join(self.v2, "blobs", "sha256", h[:2], h)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "data"), "wb") as f:
            f.write(raw)
        return "sha256:" + h

    def size(self, dg):
        h = dg[7:]
        return os.path.getsize(os.path.join(self.v2, "blobs", "sha256", h[:2], h, "data"))

    def link(self, repo, kind, dg):
        sub = ("_manifests", "revisions") if kind == "revision" else ("_layers",)
        d = os.path.join(self.v2, "repositories", repo, *sub, "sha256", dg[7:])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "link"), "w") as f:
            f.write(dg)

    def tag(self, repo, tag, dg, current=True, current_dir=True):
        t = os.path.join(self.v2, "repositories", repo, "_manifests", "tags", tag)
        idx = os.path.join(t, "index", "sha256", dg[7:])
        os.makedirs(idx, exist_ok=True)
        with open(os.path.join(idx, "link"), "w") as f:
            f.write(dg)
        if current_dir:
            os.makedirs(os.path.join(t, "current"), exist_ok=True)
        if current:
            with open(os.path.join(t, "current", "link"), "w") as f:
                f.write(dg)

    def desc(self, mt, dg, size=None):
        return {"mediaType": mt, "digest": dg, "size": self.size(dg) if size is None else size}

    def image(self, repo, name, mt=OM, cfg_mt=OCFG, layer_mt=OLAY):
        c, l = self.blob("config-" + name), self.blob("layer-" + name)
        self.link(repo, "layer", c)
        self.link(repo, "layer", l)
        m = self.blob({"schemaVersion": 2, "mediaType": mt, "config": self.desc(cfg_mt, c), "layers": [self.desc(layer_mt, l)]})
        self.link(repo, "revision", m)
        return m

    def index(self, repo, entries, mt=OI):
        m = self.blob({"schemaVersion": 2, "mediaType": mt, "manifests": entries})
        self.link(repo, "revision", m)
        return m

    def run(self):
        f = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(self.v2))), "expect.txt")
        with open(f, "w") as fh:
            fh.write("".join("%s@%s\n" % e for e in self.expect))
        p = subprocess.run([sys.executable, "-I", CHECK, "--root", self.v2, "--expect", f],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        return p.returncode, p.stdout


class RegistryCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.s = Store(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def passes(self):
        rc, out = self.s.run()
        self.assertEqual(rc, 0, out)

    def fails(self, *needles):
        rc, out = self.s.run()
        self.assertEqual(rc, 1, out)
        for n in needles:
            self.assertIn(n, out)

    # ---- controls
    def test_control_index_child_and_tagged_image(self):
        s = self.s
        app = s.image("app", "a", DM, DCFG, DLAY)
        s.tag("app", "v1", app)
        child = s.image("multi", "m")
        idx = s.index("multi", [s.desc(OM, child)])
        s.tag("multi", "latest", idx)
        s.expect = [("app", app), ("multi", idx)]
        self.passes()

    def test_control_shared_child_any_order(self):
        s = self.s
        child = s.image("multi", "m")
        a = s.index("multi", [s.desc(OM, child)])
        b = s.index("multi", [s.desc(OM, child), s.desc(OM, child)], DL)
        for order in ([("multi", child), ("multi", a), ("multi", b)], [("multi", b), ("multi", a), ("multi", child)]):
            s.expect = order
            self.passes()

    def test_control_buildkit_attestation_layer(self):
        s = self.s
        img = s.image("multi", "m")
        att = s.image("multi", "att", OM, OCFG, "application/vnd.in-toto+json")
        s.expect = [("multi", s.index("multi", [s.desc(OM, img), s.desc(OM, att)]))]
        self.passes()

    # ---- F1: every reference is checked against the manifest, cached or not
    def bad_size_index(self):
        s = self.s
        child = s.image("multi", "m")
        idx = s.index("multi", [s.desc(OM, child, s.size(child) + 123)])
        return child, idx

    def test_f1_bad_size_index_alone(self):
        child, idx = self.bad_size_index()
        self.s.expect = [("multi", idx)]
        self.fails("the descriptor in child of %s says" % idx)

    def test_f1_bad_size_child_expected_first(self):
        child, idx = self.bad_size_index()
        self.s.expect = [("multi", child), ("multi", idx)]
        self.fails("the descriptor in child of %s says" % idx)

    def test_f1_bad_size_child_expected_after(self):
        child, idx = self.bad_size_index()
        self.s.expect = [("multi", idx), ("multi", child)]
        self.fails("the descriptor in child of %s says" % idx)

    def test_f1_bad_size_repeated_entry_in_one_index(self):
        s = self.s
        child = s.image("multi", "m")
        idx = s.index("multi", [s.desc(OM, child), s.desc(OM, child, s.size(child) + 1)])
        s.expect = [("multi", idx)]
        self.fails("the descriptor in child of %s says" % idx)

    def test_f1_bad_size_shared_child_across_indexes(self):
        s = self.s
        child = s.image("multi", "m")
        good = s.index("multi", [s.desc(OM, child)])
        bad = s.index("multi", [s.desc(OM, child, 1)])
        for order in ([("multi", good), ("multi", bad)], [("multi", bad), ("multi", good)]):
            s.expect = order
            self.fails("the descriptor in child of %s says" % bad)

    def test_f1_bad_type_child_expected_first(self):
        s = self.s
        child = s.image("multi", "m")
        idx = s.index("multi", [s.desc(OI, child)])
        for order in ([("multi", child), ("multi", idx)], [("multi", idx), ("multi", child)]):
            s.expect = order
            self.fails("is %s, the descriptor in child of %s says %s" % (OM, idx, OI))

    # ---- F2: every tag needs a readable current/link
    def test_f2_extra_tag_with_empty_current(self):
        s = self.s
        app = s.image("app", "a")
        s.tag("app", "v1", app)
        s.tag("app", "broken", "sha256:" + "e" * 64, current=False)
        s.expect = [("app", app)]
        self.fails("tag broken has no readable current/link")

    def test_f2_extra_tag_without_current_dir(self):
        s = self.s
        app = s.image("app", "a")
        s.tag("app", "v1", app)
        s.tag("app", "broken", "sha256:" + "e" * 64, current=False, current_dir=False)
        s.expect = [("app", app)]
        self.fails("tag broken has no readable current/link")

    def test_f2_control_tag_link_names_a_missing_manifest(self):
        s = self.s
        app = s.image("app", "a")
        s.tag("app", "v1", app)
        s.tag("app", "broken", "sha256:" + "e" * 64)
        s.expect = [("app", app)]
        self.fails("has no revision link")

    # ---- S3: config and layer media types outside the supported set fail
    def test_s3_unknown_config_type(self):
        s = self.s
        s.expect = [("app", s.image("app", "a", OM, "application/unknown"))]
        self.fails("unsupported media type application/unknown")

    def test_s3_unknown_layer_type(self):
        s = self.s
        s.expect = [("app", s.image("app", "a", OM, OCFG, "application/x-opaque"))]
        self.fails("unsupported media type application/x-opaque")

    def test_s3_foreign_layer(self):
        s = self.s
        s.expect = [("app", s.image("app", "a", DM, DCFG, "application/vnd.docker.image.rootfs.foreign.diff.tar.gzip"))]
        self.fails("is a foreign layer")


if __name__ == "__main__":
    unittest.main()
