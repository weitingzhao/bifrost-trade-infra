# TD-183 — read-only archive checks and restore acceptance preparation

Checked 2026-10-10 18:03 UTC against the shared Golden Source as `agent_reader`
with read-only transactions, and the existing market-data API pod. Isolated
branch `codex/td-183`. No trim, enqueue, hold change, archive mutation, database
write, restore container, cluster resource, merge, push or release was performed.

## Result

**Read-only checks PASS for two actual intraday option_snapshot archives.
Restore execution is NOT RUN. TD-183 remains open.** The old statement that no
real archive has run is obsolete; its expected first date was one day early.

| Trim job / completed UTC | Archived UTC day | Manifest rows | Parquet decoded rows | Recorded deleted rows |
|---|---|---:|---:|---:|
| 9487718 / 2026-10-09 02:15:26 | 2026-09-08 | 230144 | 230144 | 230144 |
| 9588253 / 2026-10-10 02:15:23 | 2026-09-09 | 343682 | 343682 | 343682 |

Total: **573826 rows**, 43322749 bytes (~41.3 MiB), 19 columns per file.
Both `retention_archive` results have `error=null`, `budget_exhausted=false`.
The job on 10-08 (9388431) archived/deleted zero rows: its intraday cutoff was
09-08, exclusive. The earliest day was not yet eligible. This is not lost data.

The files, companion manifests and `_ledger.jsonl` agree. SHA-256 and file
sizes match; every Parquet batch and every column was decoded, not just the
footer. Date bounds and per-day counts match; no NULL primary key, duplicate
primary-key digest or 16:00 NY EOD anchor was found in the selected archives.
No `.partial` or file/manifest/ledger inventory mismatch was found.

After trim, 64 intraday rows on 09-08 and 96 on 09-09 remain in the database;
all are currently Research-pinned contracts, consistent with the archive's
explicit pinned-contract exclusion. They must not be treated as missed deletes.

| File under `/archive/raw_market/option_snapshot/intraday/2026/` | SHA-256 |
|---|---|
| `2026-09-08_2026-09-08__20261009T021516Z.parquet` | `6a6c177950cd85fe72213ebdfae673745045819a7187c42291de66a440ecf4da` |
| `2026-09-09_2026-09-09__20261010T021510Z.parquet` | `06e9cbe5d9d3d06905243ef663691426e762278d2c29e0781db65672cde36c83` |

## Runtime and remaining acceptance

- Market-data API and workers run image `bifrost-market-data:0.87.1`.
  `market-data-archive` PVC is Bound, 200 GiB, RWX, `nfs-cold`. `/archive` is an
  actual mount point and readable from the existing API pod.
- The mounted `/config/schedule.yaml` has all three tables in
  `retention_archive`, `retention_hold=[]`, 30-day intraday retention,
  90-session snapshot retention and a 300-second snapshot budget.
- Runtime `archive_range` source confirms REPEATABLE READ, read/file row-count
  comparison, matching delete count and rollback on mismatch. Its source hash
  is `b56e50fba395c0760179c5af214fc01e7997c5dfe1853633c95cbf0445d40f55`.
- `option_daily` and `short_volume` both start at **2024-10-01**. All three
  retained trim jobs report zero rows for these tables, with cutoff 2024-10-01.
  The cutoff is month-floored and exclusive; the first nonzero archive is still
  expected around **11-01 02:15 UTC**. This is pending real acceptance, not PASS.
- Snapshot `all` (including EOD) likewise has no actual export in these jobs;
  only the intraday path has been exercised with real rows.
- Manifests/ledger are written after the DB commit. A crash can leave a valid
  Parquet file without those records; a crash before commit can leave duplicate
  archive content. The verifier refuses an inconsistent inventory or duplicate
  keys and requires investigation/deduplication, rather than deleting files.
  Neither condition was observed in this inventory.

## Prepared restore acceptance plan — not executed

1. **Freeze a bounded input inventory.** Start with the smaller 09-08 file,
   its JSON and matching ledger entry (230144 rows, 17378189 bytes), then add
   09-09 (343682 rows). Copy only these files read-only into the private local
   evidence directory, outside Git. Verify their hashes after transfer. Never
   alter `/archive`; do not use the production DB as a restore target.
2. **Use a disposable local PostgreSQL target.** Local Docker is available;
   an existing PostgreSQL 17 image is present at
   `sha256:d74eeac9a635390a49bc21bd49fccd973de707e2a53a76ac49b552b8712ec46f`.
   Pin that image, disable container networking, expose no port, mount the
   copied inputs read-only, and keep all restored rows in disposable storage.
   No image pull or cluster resources are needed. This target has not been
   started. The restore runner must use that explicit local target; it must
   have no Golden Source DSN, writer role or production credentials.
3. **Preserve the table contract.** Create a typed staging table in the local
   test database using the 19 archived columns and the verified live PG types.
   Primary key: `(option_ticker, snapshot_ts)`. Preserve NULLs, numerical 0,
   double precision values and timezone-aware timestamps. For later dated
   tables, numeric/json/array columns exported as text require explicit casts;
   do not infer types from sample rows. No production table or schema changes.
4. **Load and compare every row.** Stream all Parquet batches into the local
   staging target. Require first-file count 230144, second-file count 343682,
   union count 573826; verify PK uniqueness, UTC day distribution, NY intraday
   predicate, column types and NULL counts. Read the restored table back by PK
   and compare all 19 fields with typed archive values, including explicit
   handling for NULL and nonfinite floats. Row counts alone do not prove a
   faithful restore.
5. **Prove safe repetition.** Repeat the same input import using the documented
   PK policy; total remains 573826 and every stored field is unchanged. A
   conflicting duplicate from a different archive must be reported and resolved
   explicitly, not overwritten with a guessed winner. Do not execute manifest
   predicates as SQL: manifests are evidence, not executable instructions.
6. **Record and clean up.** Save counts, field-comparison results, image ID,
   elapsed time and runner version outside Git. Stop and remove only the
   disposable test resources, retaining the source copies and audit results.
   Mark restore PASS only after the import/readback/repetition checks succeed.
7. **Keep future table acceptance separate.** On the first actual nonzero
   option_daily / short_volume export, repeat file/manifest/ledger and decoded
   row checks, then test their own typed restore. Their PKs are respectively
   `(option_ticker, bar_date)` and `(symbol, period_date, period_type)`.
   Do not close TD-183 after only the snapshot test.

Any hash/count/type/content mismatch stops the test and preserves its evidence.
If a live archive safety fault is found, report the exact affected table/range
and prepare a platform-action retention-hold proposal; this audit does not
change the hold or run trim. Historical backfill remains a separate Owner-
confirmed TD-172/TD-142 plan.

## Reproduction and checks

Database state: `scripts/audit-retention-state.sql` via LAN psql as
`agent_reader`; it begins READ ONLY and uses a 20-second statement timeout.

File validation (read-only execution in the already running API pod):

```sh
KUBECONFIG="$HOME/.kube/bifrost-k3s.yaml" kubectl \
  -n plugin-market-data exec -i market-data-api-596c8d75d4-rbjcp -- \
  python - /archive < scripts/audit-retention-archive.py
```

The pod name is the observed instance; select the current API pod before later
checks. The script neither imports the trim runner nor executes manifest SQL.
It decodes at most 20 inventoried completed files, failing rather than silently
sampling if the limit is exceeded. Archive inventories with ledger-only,
manifest-only or orphan Parquet entries are rejected for investigation.

Offline fixture checks in `scripts/test_audit_retention_archive.py`: five PASS
(readable does not mean restored; corruption; fabricated matching manifest and
ledger counts; duplicate PK; missing ledger). Existing plugin venv supplies
PyArrow; no dependency was added. Ruff and `git diff --check` pass.

Raw aggregate evidence is outside Git at
`~/agent-work/td-183-evidence/`:
`archive-validation.json`, `database-validation.txt`. No data archive, dump,
account contents, token or secret is included in this commit.
