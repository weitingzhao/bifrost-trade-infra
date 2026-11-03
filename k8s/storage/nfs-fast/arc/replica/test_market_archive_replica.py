#!/usr/bin/env python3
"""Tests for market_archive_replica.py (TD-444 step 5 runbook §5.2).

Run: python3 -m unittest k8s/storage/nfs-fast/arc/replica/test_market_archive_replica.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_archive_replica as rep  # noqa: E402


def add(root: Path, table="option_snapshot", kind="intraday", start="2026-07-01", end="2026-07-02",
        body=b"parquet-bytes", stamp="20261001T021500Z", ledger=True) -> dict:
    file = f"{start}_{start}__{stamp}.parquet"
    d = root / "raw_market" / table / kind / start[:4]
    d.mkdir(parents=True, exist_ok=True)
    (d / file).write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    (d / file.replace(".parquet", ".json")).write_text(json.dumps({"sha256": sha, "file": file}))
    rec = {"table": f"raw_market.{table}", "kind": kind, "start": start, "end_exclusive": end, "rows": 3,
           "sha256": sha, "file": file, "archived_at": "2026-10-01T02:15:00+00:00"}
    if ledger:
        with (root / "raw_market" / "_ledger.jsonl").open("a") as f:
            f.write(json.dumps(rec) + "\n")
    return rec


class Replica(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = Path(self.tmp.name) / "src"
        self.dst = Path(self.tmp.name) / "dst"
        self.src.mkdir()
        self.dst.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self) -> int:
        return rep.main(["--src", str(self.src), "--dst", str(self.dst), "--no-require-mount"])

    def test_copies_and_publishes_ledger(self):
        r1 = add(self.src)
        add(self.src, start="2026-07-02", end="2026-07-03", body=b"second")
        self.assertEqual(self.run_it(), 0)
        out = self.dst / "raw_market" / "option_snapshot" / "intraday" / "2026" / r1["file"]
        self.assertEqual(out.read_bytes(), b"parquet-bytes")
        self.assertEqual((self.dst / "raw_market" / "_ledger.jsonl").read_bytes(),
                         (self.src / "raw_market" / "_ledger.jsonl").read_bytes())
        state = json.loads((self.dst / "_replica.state").read_text())
        self.assertEqual(state["records"], 2)
        self.assertEqual(self.run_it(), 0)  # idempotent

    def test_partial_trailing_line_is_left_out(self):
        add(self.src)
        full = (self.src / "raw_market" / "_ledger.jsonl").read_bytes()
        with (self.src / "raw_market" / "_ledger.jsonl").open("ab") as f:
            f.write(b'{"table": "raw_market.x"')
        self.assertEqual(self.run_it(), 0)
        self.assertEqual((self.dst / "raw_market" / "_ledger.jsonl").read_bytes(), full)

    def test_conflicting_target_is_not_overwritten(self):
        r = add(self.src)
        d = self.dst / "raw_market" / "option_snapshot" / "intraday" / "2026"
        d.mkdir(parents=True)
        (d / r["file"]).write_bytes(b"other")
        self.assertEqual(self.run_it(), 1)
        self.assertEqual((d / r["file"]).read_bytes(), b"other")
        self.assertFalse((self.dst / "raw_market" / "_ledger.jsonl").exists())

    def test_source_differs_from_ledger(self):
        r = add(self.src)
        p = self.src / "raw_market" / "option_snapshot" / "intraday" / "2026" / r["file"]
        p.write_bytes(b"tampered")
        self.assertEqual(self.run_it(), 1)

    def test_duplicate_with_other_sha_fails(self):
        r = add(self.src)
        r2 = dict(r, sha256="f" * 64)
        with (self.src / "raw_market" / "_ledger.jsonl").open("a") as f:
            f.write(json.dumps(r2) + "\n")
        self.assertEqual(self.run_it(), 1)

    def test_bad_start_date_fails(self):
        add(self.src)
        with (self.src / "raw_market" / "_ledger.jsonl").open("a") as f:
            f.write(json.dumps({"table": "raw_market.t", "kind": "k", "start": "2026-13-01",
                                "end_exclusive": "2026-13-02", "rows": 1, "sha256": "0" * 64,
                                "file": "2026-13-01_2026-13-01__20261001T021500Z.parquet",
                                "archived_at": "x"}) + "\n")
        self.assertEqual(self.run_it(), 1)

    def test_symlink_on_path_fails(self):
        add(self.src)
        outside = Path(self.tmp.name) / "outside"
        outside.mkdir()
        (self.dst / "raw_market").symlink_to(outside)
        self.assertEqual(self.run_it(), 1)
        self.assertEqual(list(outside.iterdir()), [])

    def test_orphan_files_are_ignored(self):
        add(self.src)
        add(self.src, start="2026-07-05", end="2026-07-06", body=b"orphan", ledger=False)
        self.assertEqual(self.run_it(), 0)
        self.assertFalse((self.dst / "raw_market" / "option_snapshot" / "intraday" / "2026" /
                          "2026-07-05_2026-07-05__20261001T021500Z.parquet").exists())

    def test_target_ledger_must_be_a_prefix(self):
        add(self.src)
        (self.dst / "raw_market").mkdir()
        (self.dst / "raw_market" / "_ledger.jsonl").write_text('{"something": "else"}\n')
        self.assertEqual(self.run_it(), 1)


if __name__ == "__main__":
    os.umask(0o022)
    unittest.main()
