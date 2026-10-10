# TD-92 / TD-94 — daily output checks and gates

Read-only acceptance on 2026-10-10, approximately 18:15–18:25 UTC. Isolated
branches `codex/td-92-94` in infra and Research, based on infra `859d426` and
Research `d628fa6`. No production code change, release, enqueue, DB write,
backfill, hold change or real alert injection was performed.

## Result

- **TD-94 PASS, ready for Owner sign-off:** the last three nightly gates passed
  on the expected closed sessions, without `allow_unknown`. Existing tests
  verify probe failure, timeout, missing timestamp and wrong session block;
  a Flex failure blocks its own readers rather than unrelated Market analytics.
- **TD-92 partial PASS, remains open:** all 17 nightly engine `output_ok`
  evaluations actually ran in each of the last three runs. The checks preserve
  legitimate zero and identify zero output, repeated skips and large failure
  shares. WARNs remain for persistently missing inputs. Historical ERROR checks
  were observed, but their Alertmanager delivery/receiver receipt is unmeasured.
- This acceptance does not establish complete daily or historical data. The
  existing output checks are nonblocking by design: SUCCESS does not mean that
  all checks passed or that every symbol/session/tenor is present.

## Observed nightly runs

| Run created UTC | Run ID | Closed session / doctor session | Engine checks | Passed | Failed WARN | Failed ERROR |
|---|---|---|---:|---:|---:|---:|
| 10-10 02:30 | `7970bb70-f9b2-4aee-b3db-92e2fd075a0a` | 10-09 / 10-09 | 17 | 14 | 3 | 0 |
| 10-09 02:30 | `abd82cc4-2258-4281-be01-9828c4e65460` | 10-08 / 10-08 | 17 | 14 | 3 | 0 |
| 10-08 02:30 | `63a334af-cf98-40ed-b7fa-56afc3d344d5` | 10-07 / 10-07 | 17 | 14 | 3 | 0 |

All three runs have `gate=pass`, `market_eod=healthy` and fresh report timestamps
respectively 10-10 02:30:43Z, 10-09 02:30:35Z and 10-08 02:30:45Z. There is no
override metadata. The old ledger expected 16 engines; the actual current job
selects 17, all checked. Compare the selected keys, not a permanent numeric
constant, when the job evolves.

WARNs are GEX, surface and flow. On the last run the per-window counters were:

| Engine | Successful symbol-days | Failed symbol-days | Preserved reasons |
|---|---:|---:|---|
| GEX | 1400 | 44 | No OI contracts: 43; No gamma exposure: 1 |
| Surface | 1401 | 43 | No IV snapshot points: 43 |
| Flow | 1401 | 43 | No option tape or OI/snapshot rows: 43 |

These are a runner's multi-session window, not single-session name coverage.
The shared past-onboarding persistent sample contains 14 names: ATLCL, BPRN,
CIX, CUE, ESQ, GRML, ISTR, NPK, NVEC, NVR, OPHC, SENEA, SOTK, VNCE. Names and
reasons are retained in materialization metadata; individual reasons are not
silently discarded. This audit does not claim each is a collection bug or a
recoverable hole: contract catalogue, legitimate source void, illiquidity,
onboarding and actual missing collection require separate classification.
Feed this sample into the next completeness inventory, alongside (rather than
conflated with) TD-172/TD-142 historical tenor gaps.

Historical rerun `a5a88fe2-773f-4eba-b395-83326a480cd0` (10-07 04:31 UTC)
recorded ERROR output checks on GEX (~52% failures), surface/flow (~51%) and
alert_scan (wrong session). The run remained SUCCESS as the check contract
intends. Its Market gate judged the correct session 10-06. This is evidence
that the checks executed, not proof of alarm receipt or that the gate promises
complete historical inputs. The earlier 10-07 02:30 run failed at dbt; it must
not be cited as a observed husbandry-gate failure.

## Alert boundary

Both alert sensors are present with `DECLARED_IN_CODE`, their default is
RUNNING, and recent sensor ticks/reactions are recorded. The ERROR rerun has
a successful asset-check sensor tick around 10-07 04:42 UTC. A successful
sensor tick does **not** prove an HTTP post succeeded: `post_alert` is fail-soft,
and the sensor logs an unreachable Alertmanager without raising.

The retained event/tick evidence and currently accessible daemon logs did not
provide that historical delivery receipt. The old tick log key was found,
but its file was not found under the current daemon's Dagster home. No test
alert was sent. The existing sensor emits `BifrostDagsterAssetCheckFailed` for
failed ERROR checks in successful runs; WARNs intentionally stay on the asset.
Owner notification receipt has not been claimed.

TD-92 stays observational until delivery and receiver evidence can be captured
for a real failed ERROR check (or an explicitly authorized end-to-end alert
test). Do not relabel WARNs as ERROR or change the nonblocking policy in this
audit. Persistent data gaps remain unresolved despite working detection.

## Reproducible verification

- `scripts/audit-research-output-gates.sql`: READ ONLY, statement timeout 20s;
  last four nightly runs, verdicts from actual event-log JSON, gate metadata,
  sensor state and bounded tick summaries. No whole run configuration or
  account information is read. A check execution's SUCCEEDED status is not
  its `success` verdict; use evaluation events for PASS/WARN/ERROR.
- Existing Research tests, baseline `d628fa6`: **56 passed, no skips** across
  `test_asset_checks`, `test_asset_check_coverage`, `test_husbandry_gate`,
  `test_flex_gate`, and `test_slot_failure_reasons`.
- The shared venv lacked Dagster and initially skipped all four orchestration
  modules. A private worktree venv was installed using declared project extras
  and production versions: Dagster 1.13.26, dagster-dbt/postgres 0.29.26,
  SQLAlchemy 2.0.54. No dependency declaration changed. The production dbt
  manifest was copied read-only into the ignored local target directory to
  exercise the dbt/Flex dependency test instead of accepting its skip.
- The local asset-check, gate and failure-alert modules have byte-identical
  SHA-256 hashes to the corresponding production daemon modules:

| Module | SHA-256 |
|---|---|
| asset_checks | `e6cfc3e5f3e4dd624a64f6caf49da71eb69f3028936bcae584452372ff6b9a82` |
| plugin_batch_assets | `7710c13981a036a16b79b99f1ff64b7b380703fb0eb3f01a094c0acbe4a034f3` |
| failure_alerts | `f606eaf7ebcb473f756e63f9e9fb6b445ed1581dd5b9d891dc3c579b5226b05e` |

Runtime image: Research 0.205.0-dagster. Existing implementation provenance is
`2c34f4d` (TD-92/94 checks and gate), with `72e6473` separating Market and Flex.
No logic defect requiring a new production fix was reproduced by this pass.
Tests exited 0; logs include third-party sqlglotrs deprecation and temporary
Dagster SQLite cleanup messages. They are retained, not omitted from evidence.

Private aggregate evidence: `~/agent-work/td-92-94-evidence/`, including
`runtime-validation.txt`, `targeted-tests.log` and local dependency installation
log. Environment/manifest/cache files are ignored and not committed.

## Next boundary

The current checklist's runtime verification is complete, with TD-92's alarm
receipt limitation retained. Next is the **read-only TD-172/TD-142 joint gap
inventory and bounded repair proposal**. Before actual writes, Owner must
confirm that specific proposal; this audit gives no backfill authorization.
