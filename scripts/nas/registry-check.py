#!/usr/bin/env python3
"""Offline check of a Distribution (registry:2) storage tree, TD-444 step 5 runbook §3.8, §5.1.

Used by backup-checks.sh (td444-move.sh and backup-rollup/rollup.sh), python3 standard library
only, run as `python3 -I registry-check.py --root <dir>/docker/registry/v2 --expect <file>`.

1. Every blob (blobs/sha256/<2>/<64>/data) hashes to its directory name; there is at least one.
2. Starting points: every line `<repository>@sha256:<64 hex>` of the expected list (required,
   tagged or not) and every tag; a tag directory without a readable current/link fails.
3. From each starting point, the graph as a pull reads it. A manifest needs its revision link in
   that repository and its blob; the blob is parsed as JSON (schemaVersion 2) and handled by its
   media type:
     - image index / manifest list: every entry of "manifests" is a manifest of the same
       repository (revision link required, never a layer link instead), walked recursively;
     - image manifest: "config" (CONFIG types) and every entry of "layers" (LAYER types) are
       blobs with a layer link in that repository and the size the descriptor states.
   A manifest is walked once, but every reference to it is checked against its actual size and
   media type, whatever the order of the references. Bad JSON, schema 1, media types outside the
   sets below, a descriptor that disagrees with the manifest, foreign or non-distributable
   layers, other digest algorithms, a missing link or blob, and a size mismatch all fail.
Exit 0 only when every check passed; every finding is printed (stdout).
"""
import argparse
import hashlib
import json
import os
import re
import sys

DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
EXPECT = re.compile(r"^([a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*(?:/[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*)*)@(sha256:[0-9a-f]{64})$")
INDEX = {"application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json"}
IMAGE = {"application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"}
FOREIGN = ("application/vnd.docker.image.rootfs.foreign.", "application/vnd.oci.image.layer.nondistributable.")
CONFIG = {"application/vnd.docker.container.image.v1+json", "application/vnd.oci.image.config.v1+json"}
LAYER = {"application/vnd.docker.image.rootfs.diff.tar.gzip", "application/vnd.oci.image.layer.v1.tar",
         "application/vnd.oci.image.layer.v1.tar+gzip", "application/vnd.oci.image.layer.v1.tar+zstd",
         "application/vnd.in-toto+json"}   # the last: BuildKit attestation manifests


class Check:
    def __init__(self, root):
        self.root = root
        self.errors = 0
        self.sizes = {}          # blob hex -> size, for blobs that hash to their name
        self.types = {}          # (repository, digest) walked -> its media type (None: unreadable)
        self.manifests = 0

    def fail(self, msg):
        self.errors += 1
        print("FAIL registry: " + msg)

    def link(self, repo, *parts):
        path = os.path.join(self.root, "repositories", repo, *parts, "link")
        try:
            with open(path, "rb") as f:
                return f.read().decode("ascii")
        except (OSError, UnicodeDecodeError):
            return None

    def blob_data(self, hexd):
        return os.path.join(self.root, "blobs", "sha256", hexd[:2], hexd, "data")

    def hash_blobs(self):
        base = os.path.join(self.root, "blobs", "sha256")
        if not os.path.isdir(base):
            self.fail("no blobs directory " + base)
            return

        def walk_error(err):
            self.fail("cannot list " + str(err.filename) + ": " + err.strerror)

        for top, dirs, files in os.walk(base, onerror=walk_error):
            rel = os.path.relpath(top, base).split(os.sep)
            if len(rel) == 2 and "data" in files:
                hexd = rel[1]
                if not re.match(r"^[0-9a-f]{64}$", hexd) or rel[0] != hexd[:2]:
                    self.fail("unexpected blob path " + top)
                    continue
                h = hashlib.sha256()
                try:
                    with open(os.path.join(top, "data"), "rb") as f:
                        for chunk in iter(lambda: f.read(4 << 20), b""):
                            h.update(chunk)
                except OSError as e:
                    self.fail("cannot read blob %s: %s" % (hexd, e.strerror))
                    continue
                if h.hexdigest() != hexd:
                    self.fail("blob %s hashes to %s" % (hexd, h.hexdigest()))
                    continue
                self.sizes[hexd] = os.path.getsize(os.path.join(top, "data"))
        if not self.sizes:
            self.fail("no blob that hashes to its name")

    def descriptor(self, d, repo, where):
        if not isinstance(d, dict):
            self.fail("%s: %s is not a descriptor" % (repo, where))
            return None
        dg, size, mt = d.get("digest"), d.get("size"), d.get("mediaType")
        m = DIGEST.match(dg) if isinstance(dg, str) else None
        if not m:
            self.fail("%s: %s has an unsupported or bad digest %r" % (repo, where, dg))
            return None
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            self.fail("%s: %s %s has no valid size" % (repo, where, dg))
            return None
        if not isinstance(mt, str) or not mt:
            self.fail("%s: %s %s has no media type" % (repo, where, dg))
            return None
        return dg, m.group(1), size, mt

    def blob_ref(self, repo, desc, where, allowed):
        dg, hexd, size, mt = desc
        if mt.startswith(FOREIGN):
            self.fail("%s: %s %s is a foreign layer (%s); it is not stored here" % (repo, where, dg, mt))
            return
        if mt not in allowed:
            self.fail("%s: %s %s has the unsupported media type %s" % (repo, where, dg, mt))
        if self.link(repo, "_layers", "sha256", hexd) != dg:
            self.fail("%s: %s %s has no layer link" % (repo, where, dg))
        if hexd not in self.sizes:
            self.fail("%s: %s blob %s is missing or does not hash to its name" % (repo, where, dg))
        elif self.sizes[hexd] != size:
            self.fail("%s: %s %s is %d bytes, the descriptor says %d" % (repo, where, dg, self.sizes[hexd], size))

    def manifest(self, repo, dg, via, want_type=None, want_size=None):
        m = DIGEST.match(dg)
        if not m:
            self.fail("%s: %s names an unsupported or bad digest %r" % (repo, via, dg))
            return
        hexd = m.group(1)
        # this reference's own claims, on every visit (the cache below only saves the walk)
        if want_size is not None and hexd in self.sizes and self.sizes[hexd] != want_size:
            self.fail("%s: manifest %s is %d bytes, the descriptor in %s says %d" % (repo, dg, self.sizes[hexd], via, want_size))
        key = (repo, dg)
        if key in self.types:
            mt = self.types[key]
            if mt is not None and want_type is not None and want_type != mt:
                self.fail("%s: manifest %s is %s, the descriptor in %s says %s" % (repo, dg, mt, via, want_type))
            return
        self.types[key] = None   # walked from here on; stops a cycle; a failure below is already counted
        if self.link(repo, "_manifests", "revisions", "sha256", hexd) != dg:
            self.fail("%s: manifest %s (%s) has no revision link" % (repo, dg, via))
            return
        if hexd not in self.sizes:
            self.fail("%s: manifest blob %s (%s) is missing or does not hash to its name" % (repo, dg, via))
            return
        try:
            with open(self.blob_data(hexd), "rb") as f:
                doc = json.loads(f.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as e:
            self.fail("%s: manifest %s (%s) is not valid JSON: %s" % (repo, dg, via, e))
            return
        if not isinstance(doc, dict) or doc.get("schemaVersion") != 2:
            self.fail("%s: manifest %s (%s) is not a schema 2 manifest" % (repo, dg, via))
            return
        mt = doc.get("mediaType")
        if mt is None:   # OCI allows it to be left out; the structure decides
            mt = "application/vnd.oci.image.index.v1+json" if "manifests" in doc else "application/vnd.oci.image.manifest.v1+json"
        self.types[key] = mt
        if want_type is not None and want_type != mt:
            self.fail("%s: manifest %s is %s, the descriptor in %s says %s" % (repo, dg, mt, via, want_type))
        self.manifests += 1
        if mt in INDEX:
            children = doc.get("manifests")
            if not isinstance(children, list) or not children:
                self.fail("%s: index %s (%s) lists no manifests" % (repo, dg, via))
                return
            for n, d in enumerate(children):
                desc = self.descriptor(d, repo, "entry %d of index %s" % (n, dg))
                if desc is None:
                    continue
                if desc[3] not in INDEX and desc[3] not in IMAGE:
                    self.fail("%s: index %s entry %s has media type %s, not a manifest" % (repo, dg, desc[0], desc[3]))
                    continue
                self.manifest(repo, desc[0], "child of " + dg, desc[3], desc[2])
        elif mt in IMAGE:
            desc = self.descriptor(doc.get("config"), repo, "config of " + dg)
            if desc is not None:
                self.blob_ref(repo, desc, "config of " + dg, CONFIG)
            layers = doc.get("layers")
            if not isinstance(layers, list):
                self.fail("%s: manifest %s has no layer list" % (repo, dg))
                return
            for n, d in enumerate(layers):
                desc = self.descriptor(d, repo, "layer %d of %s" % (n, dg))
                if desc is not None:
                    self.blob_ref(repo, desc, "layer %d of %s" % (n, dg), LAYER)
        else:
            self.fail("%s: manifest %s (%s) has the unsupported media type %s" % (repo, dg, via, mt))


def tags(check):
    base = os.path.join(check.root, "repositories")
    found = []
    if not os.path.isdir(base):
        check.fail("no repositories directory " + base)
        return found

    def walk_error(err):
        check.fail("cannot list " + str(err.filename) + ": " + err.strerror)

    for top, dirs, files in os.walk(base, onerror=walk_error):
        rel = os.path.relpath(top, base).replace(os.sep, "/")
        if rel.endswith("/_manifests/tags"):
            # every tag directory is a tag: it needs a readable current/link (Distribution
            # deletes a tag by removing its whole directory, so no leftover is legitimate)
            repo = rel[: -len("/_manifests/tags")]
            for t in sorted(dirs):
                dg = check.link(repo, "_manifests", "tags", t, "current")
                if dg is None:
                    check.fail("%s: tag %s has no readable current/link" % (repo, t))
                else:
                    found.append((repo, dg, "tag " + t))
            dirs[:] = []
            continue
        # only repository paths and their tag directories hold starting points
        dirs[:] = [d for d in dirs if d not in ("_layers", "_uploads") and not (rel.endswith("/_manifests") and d != "tags")]
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True, help="<registry data>/docker/registry/v2")
    ap.add_argument("--expect", required=True, help="expected digests: <repository>@sha256:<hex> per line")
    a = ap.parse_args()
    check = Check(a.root)
    starts = []
    try:
        with open(a.expect, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = EXPECT.match(line)
                if not m:
                    check.fail("expected list line %d is not <repository>@sha256:<64 hex>: %r" % (n, line))
                    continue
                starts.append((m.group(1), m.group(2), "expected"))
    except (OSError, UnicodeDecodeError) as e:
        check.fail("cannot read the expected list %s: %s" % (a.expect, e))
    if not starts:
        check.fail("the expected list names no digest")
    check.hash_blobs()
    tagged = tags(check)
    for repo, dg, via in starts + tagged:
        check.manifest(repo, dg if dg is not None else "", via)
    print("registry: %d blobs hash to their names; %d expected digests and %d tags walked, %d manifests; %d findings"
          % (len(check.sizes), len(starts), len(tagged), check.manifests, check.errors))
    return 0 if check.errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
