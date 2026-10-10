#!/usr/bin/env python3
"""Read-only Parquet/manifest/ledger validation; never invokes trim or restore."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow.parquet as pq

TABLES = {
    "raw_market.option_snapshot": ("snapshot_ts", ("option_ticker", "snapshot_ts")),
    "raw_market.option_daily": ("bar_date", ("option_ticker", "bar_date")),
    "raw_market.short_volume": (
        "period_date",
        ("symbol", "period_date", "period_type"),
    ),
}


def check(root: Path, max_files: int) -> dict:
    files = sorted(root.glob("raw_market/*/*/*/*.parquet"))
    if not files:
        raise ValueError("No completed archives: recovery is unmeasured")
    if len(files) > max_files:
        raise ValueError(
            "Inventory exceeds bounded pass; select a narrower reviewed root"
        )
    partials = sorted(root.rglob("*.partial"))
    if partials:
        raise ValueError(f"Unfinished archive files: {len(partials)}")
    ledger = [
        json.loads(line)
        for line in (root / "raw_market/_ledger.jsonl").read_text().splitlines()
        if line.strip()
    ]
    if len(ledger) != len(files) or len(
        list(root.glob("raw_market/*/*/*/*.json"))
    ) != len(files):
        raise ValueError("File/manifest/ledger inventory mismatch")
    seen_keys = set()
    reports = []
    for path in files:
        manifest = json.loads(path.with_suffix(".json").read_text())
        table = manifest["table"]
        date_col, pk = TABLES[table]
        expected_path = (
            root
            / table.replace(".", "/")
            / manifest["kind"]
            / manifest["start"][:4]
            / manifest["file"]
        )
        if path != expected_path:
            raise ValueError(f"Manifest path mismatch: {path.name}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
        if (
            digest.hexdigest() != manifest["sha256"]
            or path.stat().st_size != manifest["bytes"]
        ):
            raise ValueError(f"Hash/size mismatch: {path.name}")
        matches = [
            row
            for row in ledger
            if all(
                row.get(key) == manifest[key]
                for key in (
                    "table",
                    "kind",
                    "start",
                    "end_exclusive",
                    "rows",
                    "sha256",
                    "file",
                    "archived_at",
                )
            )
        ]
        if len(matches) != 1:
            raise ValueError(f"Ledger missing/ambiguous: {path.name}")
        parquet = pq.ParquetFile(path)
        declared = manifest["columns"]
        fields = parquet.schema_arrow
        if fields.names != [col["name"] for col in declared]:
            raise ValueError(f"Column mismatch: {path.name}")
        for field, col in zip(fields, declared):
            if (field.metadata or {}).get(b"pg_type", b"").decode() != col["pg_type"]:
                raise ValueError(f"PG type metadata mismatch: {field.name}")
        start = date.fromisoformat(manifest["start"])
        end = date.fromisoformat(manifest["end_exclusive"])
        per_day = Counter()
        rows = 0
        for batch in parquet.iter_batches(batch_size=8192):
            # Decode every column, not just footer counts or selected PK columns.
            for row in batch.to_pylist():
                value = row[date_col]
                day = (
                    value.astimezone(UTC).date()
                    if isinstance(value, datetime)
                    else value
                )
                if not start <= day < end:
                    raise ValueError(f"Date outside manifest range: {path.name}")
                if (
                    table == "raw_market.option_snapshot"
                    and manifest["kind"] == "intraday"
                ):
                    if (
                        value.astimezone(ZoneInfo("America/New_York")).strftime(
                            "%H:%M:%S"
                        )
                        == "16:00:00"
                    ):
                        raise ValueError(f"EOD anchor in intraday archive: {path.name}")
                values = [row[key] for key in pk]
                if any(value is None for value in values):
                    raise ValueError(f"NULL primary key: {path.name}")
                key = hashlib.sha256(
                    json.dumps([table, *values], default=str).encode()
                ).digest()
                if key in seen_keys:
                    raise ValueError(
                        "Duplicate primary key across archives; dedupe plan required"
                    )
                seen_keys.add(key)
                per_day[day.isoformat()] += 1
                rows += 1
        if (
            rows != manifest["rows"]
            or rows != parquet.metadata.num_rows
            or dict(per_day) != manifest["rows_per_day"]
        ):
            raise ValueError(f"Decoded row/day counts mismatch: {path.name}")
        reports.append(
            {
                "file": str(path.relative_to(root)),
                "table": table,
                "rows": rows,
                "bytes": manifest["bytes"],
                "sha256": digest.hexdigest(),
                "columns": len(fields),
                "rows_per_day": dict(per_day),
            }
        )
    return {
        "read_only": True,
        "restore_executed": False,
        "files": reports,
        "total_rows": sum(row["rows"] for row in reports),
        "checks": (
            "hash,size,ledger,schema,full_decode,day_counts,"
            "PK_digest_uniqueness,intraday_anchor"
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-files", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(check(args.root, args.max_files), indent=2))
