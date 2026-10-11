# TD-304 — durable Research alerts and daily deadline defenses

Owner-authorized scope: isolated implementation, tests, DEV acceptance and an
Owner delivery proposal. No release, production change, real alert injection,
vendor request or expanded backfill. D10 BLOCKED; existing valid readings and
legal zeros are untouched. Private evidence: `~/agent-work/td-304-evidence`.

## Progress

| Phase | Result |
|---|---|
| Durable retry and dedup | Complete in isolated Research worktree; actual Dagster persistent local instance reopened after a failed send |
| Missing/stuck daily batch and sender liveness | Complete locally; calendar/deadline fault tests, independent existing metrics probe |
| DEV acceptance | Complete with real read-only runtime data; CHECKS CAUTION, 30 candidates retained, retry/deadline monitor unmeasured and Owner receipt unverified |
| Owner routing and true delivery | Concrete draft prepared and statically checked; NOT APPLIED / NOT VERIFIED, requires Owner confirmation |

## Implementation and limits

New regular sensor `bifrost_alert_delivery` has its own versioned JSON cursor in
existing `ops_dagster` instance persistence. It defaults to **STOPPED**; declaring
it does not authorize sending. Old callbacks are retained for a reversible
cutover, rather than changing their incompatible run-status cursor format.
The approved release must explicitly stop both old senders before enabling this
one; changing a default cannot override an instance's existing RUNNING state.

The sensor discovers RUN_FAILURE events and ERROR checks in SUCCESS runs in
ascending pages of 20 per stream. Newly queued messages are **never sent until
their discovery tick's cursor commits**. Each event advances only after all its
messages fit; capacity exhaustion holds the source checkpoint and is observable.
Messages retain only safe diagnostics and stable job/run/asset/check labels;
raw error URLs, findings, licensed rows and credentials are not sent or persisted
in the new outbox. Normal WARN checks are not promoted into failure alerts.

Pending capacity is 200; recent acknowledged identities are bounded at 512.
Each tick sends at most ten committed items, with two-second transport timeouts.
Failures retry after 60/120/240/... seconds capped at one hour, with **no retry
count that discards pending work**. Expired firing endsAt is refreshed without
changing identity or original startsAt. Corrupt/unknown-version state is rejected
before sending, never reset. Read failures retain pending work and watermarks.

Delivery is **at least once**, not exactly once: a crash after accepted POST but
before cursor commit can repeat the same labels. Alertmanager's identity/grouping
must deduplicate this replay. HTTP 2xx clears only the transport outbox; it is not
proof of downstream relay publication or Owner receipt.

The primary `research_trading_day` deadline is its NYSE session's 22:30 ET fire
plus two hours. Read the complete canonical `dw_stock.dim_trading_calendar`, not
an absence of SPY bars. Weekends/closed holidays are excluded; DST is respected;
missing, duplicate or unreadable calendar dates are **unmeasured**, not holidays.
Runs must belong to the actual schedule and creation window; manual SUCCESS and
old runs finishing late cannot cover another session. No run, QUEUED/STARTED,
FAILURE or CANCELED without successful recovery creates one stable
`BifrostDagsterScheduleMissed` incident per session. Late recovery cancels an
undelivered firing before send and persists a matching resolution for the next
tick. A gap between ticks catches due sessions in the 14-day lookback; a longer
gap remains explicitly unverified for operator reconciliation, never silently
resets. Bootstrap checks only the latest due session, not an old incident storm.
Incident capacity is 64 and truncation at over 100 matching runs is unverified.

The existing API keeps its response fields: detail includes pending count,
oldest age, missed incidents and heartbeat age when measured. Missing, stopped,
ambiguous, stale (>300 seconds), unreadable or faulty monitoring prevents a
HEALTHY notification verdict while preserving actual batch failure/overdue
precedence and valid candidate visibility. Owner receipt stays explicitly
unverified even with a drained outbox.

The existing `/metrics` family gains only `probe="alert_delivery"`; value 0
means the retry monitor is missing/stopped/stale/pending/unverified. It is scraped
outside the sensor daemon, so a stopped sender can be detected independently.
Existing `BifrostResearchMetricsProbeFailing` fires after 15 minutes, and existing
critical daemon-heartbeat rules remain the external daemon backstop. The existing
schedule roster rules monitor all declared schedules' stopped/missed/failed
ticks; the new session-specific completion incident targets the daily main batch.
The new probe does not prove receipt. Today's warning routes are still audit-only.

## Validation and DEV evidence

- Research `make lint` (ruff + SQLFluff): PASS.
- Research full `make test`: **2325 passed / 17 skipped**; all new Dagster tests run
  with orchestration dependencies installed. Existing optional skips are not
  evidence of alert delivery.
- Fault regressions include persistent state reopen and retry, atomic discovery,
  crash-after-POST identity replay, backoff/expiry refresh, full queue checkpoint,
  corrupt/version/NaN state, source and calendar failures, unexpected deadline error redaction, ERROR check dedup and
  findings redaction, missing/queued/started/failed runs, manual-run exclusion,
  delayed recovery before send, missed dates between ticks, long-gap unverified,
  weekend/holiday/DST, send limits and sender health through the existing metric.
- Focused affected suites: **79 passed / 1 skipped**; the one skip is the
  pre-existing optional dbt manifest test. All 24 new durable-delivery cases run.
- Draft route tests: **4 passed**; existing `check_alert_routing.py`: PASS.
  Current route remains unchanged and has no new paging behavior.
- Bounded agent_reader READ ONLY preflight: 72 SUCCESS events, zero failure
  events and zero failed ERROR evaluations in SUCCESS in the last 24 hours.
  Only the old two sensors are declared; the new sender has no production state.
  Calendar contains 15 consecutive dates through 10-09 (11 sessions).
  Repeat source: `scripts/audit-research-alert-delivery.sql`; re-run before any
  later cutover, since this observation is not a future replay authorization.
- Actual DEV :5173 uses isolated Research :8795, restarted through bdev.
  `CHECKS CAUTION`, **99 pass / 5 WARN / 0 ERROR**, 30 valid candidates retained.
  Detail states `alert retry/deadline monitor unmeasured (not enabled)` and
  `Owner receipt unverified`. Actual `/metrics`: alert_delivery=0, existing
  daemon/schedules/event_radar probes=1. Production has no new sensor state;
  this is an honest rollout boundary, not a simulated Owner receipt.
- Real calendar/deadline computation against agent_reader reads: latest expected
  fire 2026-10-10 02:30 UTC (10-09 NYSE session), deadline measured, no missing
  incident, no pending message and zero POST calls.
- Local fault tests use mocked transport and local persistent Dagster storage;
  shared `ops_dagster`, business tables and runtime instigators are never written.
- Screenshot/API/metric/raw test logs remain private, outside Git.

## Concrete Owner approval packet — do not execute yet

**Change A: release/cutover and routing (separate from synthetic tests).**

1. Review isolated Research commit and this infra draft. The route file
   `TD-304_OWNER_ROUTE_DRAFT.yaml` is deliberately not referenced by Helm or
   Kustomize. Insert its `routes` before the final audit catch-all only after
   approval. Exact names: BifrostDagsterRunFailed and
   BifrostDagsterAssetCheckFailed; namespace research, severity warning.
   Reuse Owner ntfy relay and authentication files. `continue: true` retains
   PROD platform audit. No blanket WARN escalation or credential change.
2. Recommended companion scope, explicitly separate in the draft:
   BifrostDagsterScheduleMissed in research, plus
   BifrostResearchMetricsProbeFailing only when probe=alert_delivery.
   Otherwise a missing sender/daily batch can still be audit-only. Existing
   critical daemon heartbeat continues to page through the current route.
3. Before enabling, read/reconcile the previous **24 hours** of eligible
   failure and SUCCESS/ERROR events and the latest due session, record counts
   and watermarks, and confirm they fit the 200-item outbox. Bootstrap never
   scans earlier events automatically. Pending older incidents require a
   separate explicit reconciliation, not a blanket historical replay.
4. Release only these approved commits through the normal Research/platform
   action paths. Snapshot old two cursor/state records privately. Explicitly
   STOP `bifrost_run_failure_alert` and `bifrost_asset_check_alert`, then START
   `bifrost_alert_delivery` with a fresh version-1 cursor. Watch first discovery
   commit, subsequent transport, source/deadline measurements and pending age.
   Never write production cursor SQL or use kubectl/curl credential bypass.
5. Rollback: STOP the new sender, preserve its complete cursor/pending queue,
   restore the old sender statuses and the previous route config through
   approved platform actions. Do not delete/reset cursor or silently mark
   pending notifications as delivered. Reconcile the cutover overlap by stable
   identities; a route rollback cannot undo already sent notifications.

**Change B: bounded real Owner receipt test, separately confirmed.**

| Item | Exact scope |
|---|---|
| Alerts | Two synthetic alerts, one for each exact failure name; warning, namespace research, synthetic=true, common unique test_id and distinct run identity |
| Content | Clearly synthetic; generic job/check identifiers only; no licensed rows, accounts, tokens or raw errors |
| Time / limit | Each firing expires within ten minutes; at most two firing plus two explicit resolved submissions, total **4** |
| Path | Normal authenticated platform action → Alertmanager → PROD audit and Owner relay; no direct credential/kubectl bypass |
| Acceptance | Same identity at producer ACK, Alertmanager receiver/group, PROD audit, relay publication, and **Owner receipt within five minutes** |
| Stop | No receipt, wrong routing, unexpected recipients or exhausted four-submission budget: stop, preserve evidence, identify failed hop; no extra retry/test expansion |

Use local mocks for network faults; do not break production credentials/network,
create failed production batches, touch trading execution or trigger backfills.
The companion monitor routes are validated offline only; real tests for those
are outside this two-alert/four-submission packet and need another explicit scope.

No publishing or test action is implied by preparation of this packet. TD-304
remains open until rollout and true Owner receipt acceptance are signed off.

## Isolated commit and review identity

Research commits: `999e8ca` + final `16f7841` on `codex/td-304`, based on accepted TD-303 `cc575bf`.
Research and infra reuse their existing managed-by-Git isolated worktrees under
`~/agent-work`, with a separate TD-304 branch; shared checkouts are unchanged.
No public REST fields, DDL or package dependencies added. The existing metrics
family gains the `alert_delivery` probe label; old sender registration is retained
for the separately approved handover. Default STOPPED prevents implicit activation.
