"""Offline fixtures verify the read-only audit refuses misleading recovery evidence."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

spec = importlib.util.spec_from_file_location(
    "archive_audit", Path(__file__).with_name("audit-retention-archive.py")
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ArchiveAuditTests(unittest.TestCase):
    def fixture(self, root, *, duplicate=False):
        folder = root / "raw_market/option_snapshot/intraday/2026"
        folder.mkdir(parents=True)
        path = folder / "2026-09-08_2026-09-08__20261009T021516Z.parquet"
        schema = pa.schema(
            [
                pa.field("option_ticker", pa.string(), metadata={"pg_type": "text"}),
                pa.field(
                    "snapshot_ts",
                    pa.timestamp("us", tz="UTC"),
                    metadata={"pg_type": "timestamp with time zone"},
                ),
                pa.field("iv", pa.float64(), metadata={"pg_type": "double precision"}),
            ]
        )
        rows = [
            {
                "option_ticker": "fixture",
                "snapshot_ts": datetime(2026, 9, 8, 14, 30, tzinfo=UTC),
                "iv": None,
            }
        ]
        if duplicate:
            rows.append(rows[0])
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
        manifest = {
            "table": "raw_market.option_snapshot",
            "kind": "intraday",
            "start": "2026-09-08",
            "end_exclusive": "2026-09-09",
            "rows": len(rows),
            "rows_per_day": {"2026-09-08": len(rows)},
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "file": path.name,
            "archived_at": "fixture",
            "columns": [
                {"name": f.name, "pg_type": f.metadata[b"pg_type"].decode()}
                for f in schema
            ],
        }
        path.with_suffix(".json").write_text(json.dumps(manifest))
        (root / "raw_market/_ledger.jsonl").write_text(json.dumps(manifest) + "\n")
        return path, manifest

    def test_readable_is_not_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            result = audit.check(root, 20)
            self.assertEqual(result["total_rows"], 1)
            self.assertFalse(result["restore_executed"])

    def test_corrupt_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, _ = self.fixture(root)
            with path.open("ab") as stream:
                stream.write(b"corrupt")
            with self.assertRaisesRegex(ValueError, "Hash/size"):
                audit.check(root, 20)

    def test_matching_manifest_and_ledger_cannot_fake_row_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, manifest = self.fixture(root)
            manifest["rows"] = 2
            path.with_suffix(".json").write_text(json.dumps(manifest))
            (root / "raw_market/_ledger.jsonl").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "row/day counts"):
                audit.check(root, 20)

    def test_duplicate_keys_need_dedupe_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root, duplicate=True)
            with self.assertRaisesRegex(ValueError, "Duplicate primary key"):
                audit.check(root, 20)

    def test_missing_ledger_refuses_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.fixture(root)
            (root / "raw_market/_ledger.jsonl").write_text("")
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                audit.check(root, 20)


if __name__ == "__main__":
    unittest.main()
