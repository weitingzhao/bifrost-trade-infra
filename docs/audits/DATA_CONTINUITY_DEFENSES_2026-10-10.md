# Daily data continuity — isolated defenses and acceptance

Owner scope: daily collection, long-tenor retention, valid coverage and alert delivery.
Checked 2026-10-10 Chicago / 2026-10-11 UTC. Research/Ops mode; D10 BLOCKED.
No release, merge, push, vendor request, backfill, production mutation or real alert injection.
Database observations used `agent_reader`, READ ONLY and a 20-second statement limit.
Private evidence and screenshots remain outside Git under `~/agent-work/data-continuity-evidence`.

## Outcome and limits

The isolated code and DEV acceptance are complete. Production defenses are **not deployed**.
The collector is running; the project is not fully covered. Alertmanager transport health
does not prove that a Research failure reached the Owner. TD-92/142/172/183 remain open.

| Link | Observed failure mode | Isolated defense / remaining boundary |
|---|---|---|
| Daily enqueue | Empty/malformed acknowledgment could materialize success | Require explicit ok, matching slot and nonnegative integer counters; measured zero/dedup/holiday remain valid; record skip reason |
| Self-heal | Critical with no prescription returned success; missing counters looked drained | Critical requires operator action; malformed queue and unknown doctor verdict cannot prove recovery; reject unacknowledged heal and changed recheck session |
| Long-tenor recompute | An expiry seen in invalid/one-sided input authorized deleting a valid repaired row | Long replacements are authorized only by accepted upsert keys; existing short-tenor replacement semantics retained |
| Valid coverage | A missing requested calendar session could borrow the preceding session; eroding relative baseline could appear ok | Unmeasured when requested session is absent; unique session/universe denominators; absolute coverage plus independent data/history status in check metadata |
| Batch health | Latest run SUCCESS produced HEALTHY despite failed checks | Read actual, latest-per-key evaluations for that run; WARN/ERROR/empty/unreadable checks prevent a green verdict, preserving existing API fields |
| DEV consumer | CAUTION was displayed as BATCH SUCCESS but held/not re-judged | Show CHECKS CAUTION and check counts; retain valid candidate rows; failed/overdue runs still block |
| Alert send | Failed POST only logged a warning, callback returned success | Callback raises, making delivery failure visible in the sensor tick; **no durable retry guarantee** |

## Read-only runtime evidence

Five latest trading sessions, 2026-10-05 through 10-09, all have stock, priced-option
and valid ATM rows. Stock breadth is 12,519–12,605 symbols, priced option breadth
678–694, and valid ATM breadth 685–702. Only 26–27 symbols have an accepted ATM expiry
at/above 180 DTE; this is an upper-leg count, **not** a strict 180-day bracket count.
Strict Research interpolation independently confirms that SPY/NVDA/AAPL each have
valid 60/90/180 readings on 10-09. These facts do not prove universe-wide coverage.

The last three trading-day engine batches each have 17 `output_ok` checks:
14 pass / 3 WARN, although their runs are SUCCESS. The complete latest batch has
104 latest evaluations including dbt checks: **99 pass / 5 WARN / 0 ERROR**.
DEV `/research/orchestration/status` now reports CAUTION with those counts.

Recent queue history initially showed 131 failed option_daily jobs across 28
underlyings. All failures are source authentication 401, created 10-09 22:45 UTC
and last failed 23:01 UTC, after three attempts. Further reconciliation is essential:
**all 131 have a later DONE job for the same kind and payload hash**. All target
10-09 only. The later jobs report 64 one-row results / 67 zero-row results.
Raw data confirms the same 64 requests contain positive-close rows; 67 remain empty.
Therefore this is a recovered authentication interruption plus **67 unresolved empty
contract-day responses**, not 131 outstanding jobs. No new retries were made here.
Zero returned rows are not a stored legal zero and are not evidence of no trading.
Historical listing, existing source-void evidence and entitlement require a separate
bounded read-only classification before any retry proposal.

Freshness is the latest successful write per dimension, so it cannot independently
clear an entire batch. Doctor already distinguishes failed history from later retry
rows (TD-281); preserve that distinction rather than re-enqueueing old failures.
The 24-hour failure window can cease displaying older incidents; missing output must
remain observable through calendar/coverage evidence after that window expires.

## Retention and future collection

Current source configuration protects a 60-day expiry floor for windowed chains/bars;
it does not promise a 180-day bracket for every member. Brent's ordinary price pass
still caps at 90 DTE. Existing full-chain/vendor reconstruction can supply long readings,
as the latest three primary symbols demonstrate; that is not a guaranteed daily contract.
The Plugin's relative breadth on 50–220 DTE also cannot prove a strict 180 bracket.
The new absolute coverage metadata makes shrinking breadth visible; an absolute
threshold and notification policy have **not** been silently introduced.

Archive-before-delete exists for option_daily, option_snapshot and short_volume.
The prior real intraday archive audit decoded and verified two files; restore execution,
first nonzero option_daily/short_volume archive and all/EOD snapshot export remain pending
under TD-183. This turn did not re-run restore or mutate archive/retention holds.
See `TD-183_ARCHIVE_READINESS_2026-10-10.md` for that bounded proposal. Preserving repaired
features does not replace testing restore of their underlying sources.

## Alert chain and approval-ready proposal — NOT EXECUTED

The Research callbacks POST warning alerts named BifrostDagsterRunFailed and
BifrostDagsterAssetCheckFailed. The configured route delivers warning to the platform
audit receiver; Owner ntfy receives critical and selected backup alerts. Long-tenor WARN
checks do not enter the ERROR-check callback at all. A relay heartbeat is not Research
receipt evidence. Read-only relay heartbeat was healthy and the last 24 hours of
Alertmanager webhook notification-failure increments were zero; neither clears this gap.
Dagster's run-status sensor updates its cursor even when the callback raises, so the
new visible FAILED tick must not be sold as eventual delivery or automatic replay.
An entirely missed schedule also produces no failed run to trigger this callback.

Recommended next design, before production changes:

1. Preserve normal warning policy; route just the two named Research failure alerts to
   Owner as well as platform audit. Choose explicit coverage/session targets separately:
   primary SPY/NVDA/AAPL 90/180 daily availability first, full universe after a scoped
   collection/budget decision. Do not convert all low breadth to critical automatically.
2. Choose durable resend: recommended independent delivery sensor with a bounded pending list in Dagster
   cursor persistence (without altering the run-status cursor format), with replay, deduplication, capped retries and a visible oldest-pending age;
   alternative a dedicated delivery outbox table. The latter is an architecture/DDL
   decision. Both require design acceptance and restart/cursor-migration tests first.
3. Include expected-run deadline monitoring so stopped/missed scheduling is detectable
   without a run-failure event. Use trading-calendar/session checks; weekends are not
   missing trading sessions. No new schedule/rule has been installed this turn.
4. Only after explicit approval of routing/deployment and the final concrete test packet:
   send **two synthetic alerts**, one per named Research alert, with one unique test id,
   clearly marked synthetic and no licensed rows/accounts/credentials. Each expires
   within 10 minutes and is explicitly resolved; maximum two firing + two resolved
   submissions. Send through the normal authenticated platform action, never a bypass.
   Verify producer acknowledgment, Alertmanager grouping/route, platform audit entry,
   relay publication and Owner receipt by the same id. Owner receipt must arrive within
   5 minutes; absent receipt, stop and report the exact broken link. No trading action,
   real failed run, or backfill is needed. Keep fault injection of transport failures in
   mocks/local tests; do not disable production network or credentials.

Production change and real test approval are separate from this isolated implementation.
The test cannot establish Owner delivery under today's audit-only warning route.

## Validation

- Research `make lint`: PASS (ruff and SQLFluff).
- Research `make test`: **2286 passed / 17 skipped**; affected tests **75 passed / 0 skipped**.
  Skips are existing optional/external paths, not the new orchestration regressions.
  Tests include malformed acknowledgments, legal zero/dedup/holiday, missing calendar,
  missing vs insufficient history, invalid long replacement, failing delivery callbacks
  and output WARN/ERROR/unmeasured visibility. External writes are mocked.
- Frontend lint/build/legacy-CSS: PASS; lint has 67 existing warnings, no errors.
  Model regression: **13 passed**, including caution retention and overdue precedence.
- DEV Vite :5173, isolated frontend + isolated Research :8795, real read-only data:
  CHECKS CAUTION, **99 pass / 5 WARN / 0 ERROR**, 30 candidates retained, current batch
  timestamp remains visible. No false held/retry-pending text. Screenshot kept privately.
- The bounded runtime SQL is `scripts/audit-data-continuity.sql`; READ ONLY PASS.
- DEV smoke: retired Instances redirects to Rules with instance records; Live renders its overnight/unread state explicitly; Ledger renders the retained AAPL filter and empty scoped result. No controls that write were used.
- DEV services remain managed by bdev; only trade-ui cwd/command was changed to the isolated frontend, preserving existing DEV API configuration. Research already used its isolated worktree. Shared frontend package-lock changes were not staged or altered.
- Database writes/vendor HTTP/backfill/real alerts/releases in this task: **0**.

## Follow-up order

1. TD-304: durable alert/deadline design, targeted Owner route and separately approved
   real receipt test. This is the largest remaining silent-failure risk.
2. TD-172/142: specify primary daily long-tenor renewal scope, strict valid coverage
   floors and source budget before altering collection or retention. No scope expanded.
3. TD-305: classify exactly the 67 empty 10-09 request receipts read-only; publish
   historical as_of evidence and request-specific dispositions before proposing retries.
4. TD-183 remains the next restore acceptance item after these priorities are decided.
   No next phase starts automatically.

Code commits: Research `cc575bf` on `codex/td-172-142`; Frontend `c57283ae` on
`codex/data-continuity`. TD-303 records isolated acceptance; TD-304/305 explicitly
retain pending production receipt and historical empty-response classification.
