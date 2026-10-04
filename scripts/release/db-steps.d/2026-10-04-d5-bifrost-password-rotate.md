---
id: 2026-10-04-d5-bifrost-password-rotate
envs: prod
when: after
done: prod
---
# TD-85 D5: rotate bifrost's password, together with the plugin Secrets

Owner-approved 2026-10-04 ("Owner 批复" D5: rotate, and change the plugins' Secrets in the same pass). Listed under
`prod` / `after` only so `release.sh` prints it; it is not a release step and needs no image. **Run after
TD-85 is switched in all three envs** (the runtime Secrets carry `trade_app_<env>`; the script refuses otherwise) —
true since 2026-10-04 (read-only: `bifrost-{dev,stg,prod}-secrets` `PGUSER = trade_app_<env>`; no bifrost session
from a Trade namespace). If D6 moves the plugins off bifrost first, drop their two lines from `HOLDERS` in the
script and the rotation shrinks to db-init + CNPG.

**Why.** The bifrost password sat in every Trade pod of every env until TD-85; any copy that leaked (DEV pods, Mac
files, plugin Secrets) can still write PROD and own every Trade table. The switch to trade_app_<env> closed new
copies; only a rotation voids the old ones.

## Holders (read-only 2026-10-04 05:5x UTC: `scripts/bifrost-password-rotate.sh holders`, names and yes/no only)

| holder | key(s) | equal to the CNPG Secret today | used by | picks up a new value |
|--------|--------|------------|---------|----------------------|
| `data/bifrost-postgres-app` (CNPG `bootstrap.initdb.owner` = bifrost, `secret`) | `password` | reference | CloudNativePG 1.27.4 instance manager: on the primary it runs `ALTER ROLE bifrost WITH PASSWORD …` (logging suppressed) whenever the Secret's resourceVersion differs from what it applied last — **and after every instance-manager start or failover** (the cache is in memory). The Secret is therefore the role's source of truth: a rotation that skips it is undone by the next primary restart. (`refreshCredentialsFromSecret` / `reconcileUser`, `pkg/management/postgres/utils/roles.go SetUserPassword`, tag v1.27.4) | at once |
| `bifrost-{dev,stg,prod}/bifrost-<env>-db-owner` | `PGPASSWORD`, `GOLDEN_SOURCE_PASSWORD` | yes ×6 | db-init Jobs (explicit env, TD-85) | next db-init run |
| `plugin-market-data/market-data-secrets` | `postgres-password` | yes | market-data-api, polygon-worker-stocks (3), polygon-worker-options (8); 14 CronJobs (all suspended) | restart |
| `plugin-flex-query/flex-query-secrets` | `postgres-password`, `trade-pg-password` | yes ×2 | flex-query-api, flex-query-worker (Golden Source as bifrost; its Trade-DB reads and core's raw_broker writes also sign in as bifrost with `trade-pg-password`) | restart |
| Mac, gitignored (shared infra checkout) | `.env` `POSTGRES_PASSWORD` / `PGPASSWORD` / `GOLDEN_SOURCE_PASSWORD` (user bifrost), `k8s/base/secrets/*.yaml`, `k8s/data/secrets/bifrost-postgres-app.yaml` when present | (not readable from the lane worktree; `holders` from the shared checkout counts them) | compose stack, `materialize_k8s_trade_secrets.py`, `psql` over LAN `:30432` | the script replaces every value equal to the old one |
| Mac, `bifrost-platform-plugin-flex-query/.env` | `POSTGRES_PASSWORD` (1 value equal) | yes | local flex runs | same |
| Mac, `bifrost-research/.env` | `ANALYTICS_PG_PASSWORD` with `ANALYTICS_PG_USER=bifrost` (1 value equal) | yes | local Research tooling signs in **as bifrost** (after D2 it should be analytics_writer) | same |
| Mac, `bifrost-platform-plugin-market-data/.env` | — (its user is `data_writer`; 0 values equal) | no | — | — |

Not holders: `bifrost-<env>-secrets` (trade_app_<env> since TD-85), the FDW user mappings (they store
brokerage_reader / brokerage_writer passwords), Research (analytics_writer), Platform (no Postgres credential).
Live bifrost sessions at that time: plugin-market-data 11, plugin-flex-query 1, nothing else.

Found on the way: `materialize_k8s_trade_secrets.py` let the market-data plugin's `.env` (user `data_writer`)
override `POSTGRES_PASSWORD` for bifrost's Secrets — a `--apply` would have written data_writer's password into
`bifrost-<env>-db-owner` and broken db-init. Fixed in the same commit: a plugin `.env` whose `POSTGRES_USER` is not
bifrost no longer lends its passwords.

## How (`scripts/bifrost-password-rotate.sh`, from the shared infra checkout once merged)

Values live in that checkout's gitignored `.env` (`BIFROST_PG_PASSWORD_PREVIOUS`, `_NEXT`); nothing prints a
password, values travel on stdin or in mode-600 temp files. Order inside `rotate`:

| # | move | effect on running work | undo |
|---|------|------------------------|------|
| 0 | preflight: PREVIOUS signs in as bifrost; the CNPG Secret and all 9 holder keys equal PREVIOUS; no runtime Secret on bifrost; no db-init Job active; outside weekdays 20:55–23:30 UTC (market-data batch) unless `--any-time` | none; refuses with the names of the holders that disagree | — |
| 1 | the 5 holder Secrets → NEXT (`kubectl patch` from a temp file) | none: pods keep the env they started with | `rollback` |
| 2 | **cut-over**: `ALTER ROLE bifrost PASSWORD '<SCRAM-SHA-256 verifier of NEXT>'` (computed locally; the password never reaches Postgres) | new logins with PREVIOUS fail from here; open sessions stay | `rollback` |
| 3 | `data/bifrost-postgres-app` → NEXT | CNPG re-applies the same value (seconds); later failovers keep NEXT | `rollback` |
| 4 | `rollout restart` + `status` of every Deployment that mounts a holder Secret (5 today: flex-query-api, flex-query-worker, market-data-api, polygon-worker-options, polygon-worker-stocks) | a plugin pod that opens a new connection between 2 and its restart fails that connection (pools retry); a few seconds to a minute | — |
| 5 | Mac files: every value equal to PREVIOUS → NEXT (counts printed) | — | `rollback` |
| 6 | `check` | — | — |

## Quiet window

Plugin work runs from Dagster slots and the polygon workers' queue: trim 02:15, ratios hourly :10 02:10–20:10,
option refresh every 6 h at :20, intraday chain 14:30–19:30, the evening batch 21:05–23:15 (market-data's own
memory: avoid 21:05–23:15 UTC). db-init runs only with a deliver. **Recommended: a weekend day 06:00–20:00 UTC**
(the script refuses the weekday evening batch by itself), not during a release.

## Owner checklist

1. Merge this lane's infra commits; in the shared checkout: `scripts/bifrost-password-rotate.sh holders` → every
   key `yes`, the runtime Secrets on `trade_app_*`, the 5 Deployments, the Mac files and their counts.
2. `scripts/bifrost-password-rotate.sh ensure` (saves the current value from the CNPG Secret as PREVIOUS, generates NEXT).
3. `scripts/bifrost-password-rotate.sh rotate` → its step 6 must say `NEXT signs in: yes`, `PREVIOUS signs in: no`,
   every holder `= NEXT: yes`, and bifrost sessions only from the two plugin namespaces with `oldest` after the
   rotation time.
4. One minute later `scripts/bifrost-password-rotate.sh check` again (CNPG has re-applied: still `NEXT yes / PREVIOUS no`);
   `kubectl -n data get cluster bifrost-postgres -o jsonpath='{.status.secretsResourceVersion.applicationSecretVersion}'`
   changed from 43032835; market-data `GET /market/doctor` and the flex-query API answer 200.
5. Next deliver: the db-init log still says `Golden Source: bifrost@…` and `ops_feedback schema ready`.
6. After a plugin day without `password authentication failed for user "bifrost"` in
   `kubectl -n data logs bifrost-postgres-1 -c postgres`: delete `BIFROST_PG_PASSWORD_PREVIOUS` from `.env`;
   `release.sh db-done prod 2026-10-04-d5-bifrost-password-rotate`.

Rollback (any time before 6): `scripts/bifrost-password-rotate.sh rollback` — the same five moves back to PREVIOUS
(holders, verifier, CNPG Secret, restarts, Mac files); then `check` shows `PREVIOUS yes / NEXT no`.

Rehearsed 2026-10-04 against a fake kubectl (Secrets as JSON files, the same 9 keys + CNPG) and the throwaway
docker postgres:17 with SCRAM for bifrost on localhost: `holders` all yes → `ensure` twice (second leaves both) →
`rotate`: 5 Secrets + CNPG = NEXT, verifier login with NEXT yes / PREVIOUS no, 2+2 Mac values replaced, quotes
kept → `rotate` again refused (PREVIOUS no longer signs in) → `rollback`: all back, files back to the old value →
preflight refused a drifted plugin Secret and a runtime Secret on bifrost, naming both → `rotate` again ok. Not
rehearsable locally: CNPG's own re-apply (read from its source, checklist 4 verifies it live).

Also seen (not this step): the flex-query repo's committed `config/flex-query.yaml` carries three non-empty
`password:` fields for user bifrost (a code survey compared them locally, without printing: none equals a current
password). Public repo — the flex project should blank them and rotate if any was ever live.

## prod
dry-run: scripts/bifrost-password-rotate.sh holders
commit:  scripts/bifrost-password-rotate.sh ensure && scripts/bifrost-password-rotate.sh rotate
verify:  scripts/bifrost-password-rotate.sh check   (then checklist 4-6)
rollback: scripts/bifrost-password-rotate.sh rollback
