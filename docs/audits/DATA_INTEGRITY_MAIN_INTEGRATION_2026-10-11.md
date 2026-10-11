# Data integrity main integration — 2026-10-11

Status: 已合入／未发布. Research, Market Data and frontend remote main heads verified; infra records promoted with this commit.
Owner authorized source/evidence integration only. No release, sender enablement,
real alert test, database migration, archive restore, vendor request or expanded backfill.

## Scope and lineage

All worktrees started from freshly fetched main. Changes were replayed individually,
retaining Claude-Session, Claude-Transcript, Change-Id and Work trailers. TD-302
Research was a separate branch and was explicitly included before the later repairs.
Existing TD-281 doctor behavior and newer workspace governance were retained.

| Repository | Main base | Integrated source HEAD | Replayed commits |
|---|---|---|---|
| research | `ecdce437` | `e094659b` | 5 |
| market-data | `d25bd0e5` | `4c960247` | 5 |
| frontend | `809d5579` | `2cf45185` | 3 |
| infra | `a490bcad` | `691351bf` | 16 |

TD-274: Dealer/Chain/History no-flip semantics and independent wall retention.
TD-302: latest usable coverage, missing/history distinction and legal zero.
TD-172/142: bounded repair/pilot/as_of/budget/transaction/receipt protections and prior approved execution records.
TD-183: archive read-only validation and restore readiness only; actual restore remains NOT RUN.
TD-92/94: previously verified gate/output-check audit records, without a new production change.
TD-303/304: accepted long-row retention, daily failure visibility, durable retries,
deduplication, missed-run monitor and an unapplied Owner route draft.
TD-305: inventory/follow-up record only; historical classification NOT RUN.

## Why main promotion does not deploy

Read-only live Argo Application inspection agrees with repository manifests:
Research tracks main/k8s with automatic synchronization; platform tracks infra
main/k8s/overlays/platform-stg and platform-prod with automatic synchronization;
Trade environments remain manual. The complete tracked k8s trees are byte-for-byte
unchanged in Research, plugin and infra; frontend has no k8s tree. Infra ConfigMap
generators use unchanged inputs inside k8s, and no k8s/base input changed.
No Dockerfile, GitHub workflow, runtime config, image reference, Helm values,
Tekton definition or deploy script changed. The Owner route exists only under
`docs/audits/TD-304_OWNER_ROUTE_DRAFT.yaml`, outside the rendered deployment paths.

Live TriggerTemplates select only bifrost-ci-python, bifrost-ci-frontend and
bifrost-ci-platform; checked pipeline bodies lint/test/build frontend assets and
code-health, without image delivery or rollout. GitHub-main-to-Gitea mirror updates
can initiate CI, not a release. Gitea is not directly pushed. Each main push must
check the release window in the same command and remain a fast-forward.

## Integrated verification

- Research: make lint (ruff/sqlfluff) PASS; make test 2339 passed / 17 skipped.
  Combined affected delivery/API/coverage/exhibit/repair/long-health cases: 106 passed.
  Module paths were checked to resolve the new worktree rather than the reused venv's editable source.
- Market Data: make lint PASS; make test 1315 passed / 9 skipped. TD-281 retained.
- Infra: 28 audit/range/budget/route checks plus 5 archive integrity cases PASS.
  Existing Alertmanager route checker PASS; proposed route remains unapplied.
- Frontend: lint 0 errors / 67 existing warnings, build PASS with existing chunk warning,
  check:legacy-css PASS; full Vitest 551 files / 4141 passed / 1 skipped (187s).
- git diff --check PASS; 29 original commits have all four lineage trailers.

## DEV acceptance

bdev manages the integrated local Research API (:8795) and Vite (:5173).
Research uses agent_reader and default_transaction_read_only=on, statement_timeout=20s.
Only GET reads were made; no Dagster daemon, sender or repair worker was started.
Data session remains 2026-10-09.

| Case | Integrated result |
|---|---|
| AAL Dealer | short gamma, no flip; put wall 12/call wall 14 retained; four consecutive short sessions |
| AAL Chain and History | same walls/no-flip chips; numeric history retained; missing 09-24 reads unavailable and breaks continuity |
| APT | rank/percentile withheld for 2/126 sessions, IV30 57.8% retained |
| AU | actual rank 0/Cold preserved; percentile follows existing rounding |
| ZZQ | no IV rows and no Dealer reading; no invented zero, history warm-up or no-flip reading |
| Instances / Live / Ledger smoke | Instances reads 89 trades; Live renders existing 0/38 fresh marks; Ledger reads 32 executions after clearing carried SPY filter in its rolling one-month window |
| SPY DEV | 90d/180d cone percentiles shown at n66/n60; previous withheld state absent |
| Coverage GET | IV Rank/Percentile each 631/725 usable, VRP 697/725; categorical Forecast 721/725 |
| Primary long depth GET | SPY 90/180: 66/60; NVDA 61/60; AAPL 61/60; sufficient history, not withheld |
| Queue | CHECKS CAUTION, 30 valid candidates retained; 99 pass/5 WARN/0 ERROR; sender not enabled and Owner receipt unverified |
| Metrics | alert_delivery=0; daemon_heartbeats/schedules/event_radar=1 |

The broad Symbol overview again reached agent_reader's connection limit; failed
lenses were visibly labelled rather than green. Focused Dealer/Chain/Volatility
checks above succeeded without permission or production changes. This existing
runtime limitation is not resolved by the source integration.

## Remaining release gates

Source integration is not production acceptance or debt closure. TD-183 restoration,
full-universe breadth/long-history/short-leg gaps and TD-305 historical classification
remain open. TD-304 sensor stays default STOPPED; existing senders remain unchanged.
Routing/cutover and the bounded real Owner receipt test still require separate approval.
Prior accepted limited data repairs are historical receipts; this task does not repeat them.

## Promotion receipts

Verified remote main after safe fast-forward pushes:
Research `e094659bef11a69791ffdb485c3304e1e981d602`,
Market Data `4c960247067d858916194877ae29e7c581bdf653`,
frontend `2cf451850c0c5f7d59f6e8db2a588419c5e44d47`.
Infra integrates the 16 historical record commits atop latest `a490bcad` (original start `85fff6d9`; a concurrent WORK.md-only
Owner record was retained by rebase before the final push); the final
record/ledger commit is the enclosing commit of this file (no circular self-SHA).
All pushes checked no release window open; no deliver/build-image/rollout was requested.

Newly integrated public API signatures, dependencies, schemas and deployment inputs: none.
Existing skipped optional integration cases are not counted as production validation.
The ledger keeps 89 unresolved debts; TD-303/304/305 were placed inside its canonical
item section and added to its overview so the rendered ledger includes them. The existing
TD-299 item was also moved into that section without changing its content; its prior
placement under methodology hid it from the renderer. Canonical items now reconcile at 89.

Screenshots, endpoint responses, service backup and raw logs stay outside public Git.
