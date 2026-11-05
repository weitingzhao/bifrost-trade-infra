# 台账清理：降级出台账的 24 条（2026-11-05）

状态：已执行，见 `CUT-r5-ledger-cleanup-2026-11-05.md`。这 24 条仍然成立，但够不上登记门槛（挡住业务、出过事故、有明确修法），从台账移出，按去处写在这里；对应设计稿改到时把它们并进风险节。

| TD | 级 | 领域 | 标题 | 去处 |
|---|---|---|---|---|
| TD-135 | P3 | data | Native barmanObjectStore backups are removed in CloudNativePG 1.30; the Barman C | bifrost-trade-infra/k8s/system/cnpg-operator 升级前置条件（README/RELEASE 风险段） |
| TD-144 | P3 | research-data | Settled candidates are not attributed to the judge (persona) that put them forwa | Research Copilot Vision §9.3 / JudgeTrackRecord.tsx 文件头 |
| TD-146 | P3 | research-data | No store accepts a hand verdict, so the Personas bench 'Agrees with you' column  | Research Copilot Vision §4/§9.3 |
| TD-186 | P3 | frontend | "My levels" (plan stop / target and price alerts as horizontal lines) on the Sym | design/uploads/ASK-symbol-chart-my-levels-2026-10-06.md |
| TD-311 | P3 | ops-platform | the send door's follow-ups: push paths that do not pass through it, an incomplet | agent-config/ADR-ops-architecture.md §5 风险（发送门） |
| TD-321 | P3 | multi-agent | a silent wrapped run now notifies nobody, and a session that inherited the wrapp | agent-config/work/multi-agent/DESIGN-host-minimal-2026-10-12.md 风险 |
| TD-340 | P3 | ops-platform | leaving the approvals page while a decision is in flight and a newer Console is  | bifrost-platform Console 审批页设计风险（ADR-ops-architecture.md §5） |
| TD-347 | P2 | agentrt | agentd's "machine-wide" lock is per user: two agentd under two users on one host | agent-config/work/multi-agent/DESIGN-agent-runtime-v5-2026-10-14.md §5.2 风险 |
| TD-362 | P3 | agentd | setup.json and siblings.json stay on the host: the platform never sees which set | agentd 设计文档风险节 |
| TD-368 | P3 | agentd | a read of the executor's log that hangs cannot be cut short | agentd 设计文档风险节 |
| TD-372 | P3 | agentrt | schema · a capability_score row's identity has no model provider | agentrt schema 设计文档风险节 |
| TD-376 | P3 | agentd | security · a process a setup command leaves behind (setsid) outlives the check a | bifrost-trade-infra/agent-config/work/multi-agent/CUT-agentd-confine-2026-10-19.md §7 |
| TD-427 | P3 | agentrt | presence · with several API instances the controller's health probe samples the  | agent-config/work/multi-agent/CUT-online-status-2026-10-23.md 风险 |
| TD-461 | P2 | infra code-health | 绝对基线与实测有历史差距 | agent-config/work/multi-agent/DESIGN-S6-v3-2026-10-29.md §5.6 风险 |
| TD-495 | P3 | Console | 新的审批单大约 50 秒后才出现在 Console | R5:5.5-16 设计稿风险 |
| TD-499 | P3 | 交付 | 交付前不在本机跑 code-health，超长的 infra 文档只在落地 CI 里才被拦 | DESIGN-r5-5.7-6-one-judge-before-main-2026-11-04.md 风险节 |
| TD-504 | P3 | 计划视图 | R5:5.5-19 整页解释的测量不数折叠次数 | R5:5.5-19 设计稿风险节 |
| TD-505 | P3 | 计划视图 | R5:5.5-19 逐项查取消的几处没有各自的回归测试 | R5:5.5-19 设计稿风险节 |
| TD-507 | P3 | NAS 备份 | MinIO 回读：一次性 MinIO 建出来后报错、按运行令牌又查不到时，当成「没有容器」删掉草稿快照（TD-444 第 5 步复核第 5 轮 S1） | TD-444 第 5 步设计（scripts/nas/backup-rollup）风险节 |
| TD-508 | P3 | NAS 备份 | `pending-cleanup.list` 里缺字段的行被悄悄丢掉或改写（TD-444 第 5 步复核第 5 轮 S2） | TD-444 第 5 步设计（scripts/nas/backup-rollup）风险节 |
| TD-509 | P3 | 发布 | push-main 跑仓库快测试时几分钟没有输出，看着像卡住了 | DESIGN-r5-5.7-6-one-judge-before-main-2026-11-04.md S4 |
| TD-510 | P3 | Console | 正在跑的步骤卡展开「To finish」后，同一个任务名出现两次（R5:5.5-20 复核 S2） | R5:5.5-20 设计稿风险节 |
| TD-511 | P3 | Console | `one_of` 的结论比 §4.2 的表多了一条例外（R5:5.5-20 复核 S3） | API-REQUIREMENTS-IA-v2 §4.2（Design） |
| TD-512 | P3 | agentd | 某个模型自己的周限额被拒时，只有厂商措辞对得上才冷却 claude 周池 | agentd 额度设计稿风险节 |

## TD-135（原文，去处：bifrost-trade-infra/k8s/system/cnpg-operator 升级前置条件（README/RELEASE 风险段））

**P3 · data · Native barmanObjectStore backups are removed in CloudNativePG 1.30; the Barman Cloud Plugin that replaces them needs cert-manager, which the cluster does not have**

- **状态**：未开始（Owner 10-07 暂缓）
- **Claim**: Applying the Cluster on 10-06 printed "Native support for Barman Cloud backups and recovery is deprecated and will be completely removed in CloudNativePG 1.30.0". The operator is 1.27.4. The plugin needs cert-manager; no cert-manager namespace or CRDs exist.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/cluster.yaml` — spec.backup.barmanObjectStore
  - `bifrost-trade-infra/k8s/system/cnpg-operator/kustomization.yaml` — operator version pin
- **Impact**: An operator upgrade past 1.29 would stop WAL archiving and backups.
- **Fix**: Before that upgrade: install cert-manager, deploy plugin-barman-cloud, move the Cluster to an ObjectStore plus plugin configuration, verify a backup and a restore drill.
- **Ratchet**: install-cnpg-operator.sh refuses a version of 1.30 or later while the Cluster still uses barmanObjectStore.
- **验收**: A completed Backup with method plugin and a restore drill that passes.
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-trade-infra

## TD-144（原文，去处：Research Copilot Vision §9.3 / JudgeTrackRecord.tsx 文件头）

**P3 · research-data · Settled candidates are not attributed to the judge (persona) that put them forward, so the Personas bench track-record columns stay grey**

- **状态**：未开始（Owner 10-07 暂缓）
- **验收**：选 A 时，上线后：`SELECT count(*), count(*) FILTER (WHERE source_ref ? 'persona') FROM research.candidate_pool WHERE source='harness' AND trade_date >= '<上线日>'`（Golden Source 副本只读）两数相等且 > 0
- **Claim**: research.candidate_pool has 129 rows and none carries a persona key in source_ref; no other table records which judge proposed which candidate. JudgeTrackRecord's four track-record columns and the Pilot Console bench bar have nothing to read.
- **Measured**: MEASURED 10-06 on the Golden Source replica.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/repositories/candidate_pool.py:24` — `"source_ref",`
  - `bifrost-trade-frontend/src/pages/copilot/personas/JudgeTrackRecord.tsx:15` — `*   a per-judge verdict against the outcome that followed, so the design's`
- **Impact**: The bench cannot say which judge earns its weight.
- **Fix**: Recommended: the harness writes source_ref.persona (and the judge model) when it inserts a candidate; forward only, no DDL, no backfill; candidate-outcome /summary groups by it. Alternative: a new research.* table if one candidate can carry several judges' votes (design first, database-design skill).
- **Ratchet**: Test that the harness insert path sets source_ref.persona; an asset check that new harness candidates without it are 0.
- 审批 要你批 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-frontend

## TD-146（原文，去处：Research Copilot Vision §4/§9.3）

**P3 · research-data · No store accepts a hand verdict, so the Personas bench 'Agrees with you' column cannot be computed**

- **状态**：未开始（Owner 10-07 暂缓）
- **验收**：建了的话：`git -C bifrost-research grep -n 'verdict' origin/main -- src/bifrost_research/schema` 出现新表的 DDL，且 `git -C bifrost-trade-frontend grep -n "column: 'Agrees with you'" origin/main -- src` 无输出（列不再登记为缺数据）
- **Claim**: Nothing records a hand verdict beside the machine's on the same name; JudgeTrackRecord greys 'Agrees with you' for that reason.
- **Measured**: CODE-READ 10-06: no verdict table under bifrost_research/schema on origin/main a242b22.
- **Evidence**:
  - `bifrost-trade-frontend/src/pages/copilot/personas/JudgeTrackRecord.tsx:23` — `* - **Agrees with you** needs a hand verdict beside a machine one on the same`
  - `bifrost-trade-frontend/src/pages/copilot/personas/JudgeTrackRecord.tsx:24` — `*   name. The hand-verdict store (Vision §4 · §9.3) does not exist yet.`
- **Impact**: One of the bench's columns stays grey; no agreement rate between the Owner and the judges.
- **Fix**: If wanted: a journal.* table keyed by research user (D-Journal-Stores), one row per (user, symbol, trade_date) verdict with an optional note, written from the bench; designed with the database-design skill before any DDL. If not: the column keeps its stated reason and this item is closed as not wanted.
- **Ratchet**: If built: a DB test of the store and the frontend column test. If not built: none needed (the page already states why).
- 审批 要你批 · 代价 M · 风险 low · repos: bifrost-research, bifrost-trade-frontend

## TD-186（原文，去处：design/uploads/ASK-symbol-chart-my-levels-2026-10-06.md）

**P3 · frontend · "My levels" (plan stop / target and price alerts as horizontal lines) on the Symbol chart waits on Design: ASK-symbol-chart-my-levels-2026-10-06**

- **状态**：未开始（Owner 10-07 暂缓）
- **验收**：Design 的回复（RESPONSE 或 Rev 说明）在 `design/trade/` 里；按回复落地后，Symbol › Price 图有对应图层，或台账 G5 改成「➖ 不做」并写明理由
- **现在**：Design 10-06 带回的 Package .63 @ Rev .162 只回了 Rev .161 回执，**没有回答这份 ASK**，继续等。ASK 写在 `design/uploads/ASK-symbol-chart-my-levels-2026-10-06.md`。实测：`strategy_plan` 有 `stop_kind/target_kind = underlying_price`，但 PROD 0 行；价格提醒没有存储（`/research/alerts` 是镜头级）
- **下一步**：Design 定形态；计划止损和止盈部分不需要新表，app 直接做；价格提醒要新表，先列方案给 Owner 批
- **Claim**: TradingView's drawing tools are useful to an option seller mainly as horizontal levels (planned strike, invalidation stop, alert price). K-LINE-SPEC / RESPONSE A7 keeps drawing tools off the chart, so the exception needs Design's ruling.
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/monitor/schemas/strategy_plans.py:48` — `target_kind: Optional[TargetKind] = None`（TargetKind 含 `underlying_price`）
  - `design/trade/RESPONSE-2026-10-05-price-chart-pine.md` A7 — 仍不放：均线、画线工具
- **Impact**: The chart cannot show where the trader's own plan says it is wrong; plans and alerts stay off price.
- **Fix**: Per Design's answer; plan levels from strategy_plan, alerts via a new store (Owner approval).
- **Ratchet**: Decide with the implementation.
- 审批 要你批 · 代价 M · 风险 low · repos: bifrost-trade-frontend, design

## TD-311（原文，去处：agent-config/ADR-ops-architecture.md §5 风险（发送门））

**P3 · ops-platform · the send door's follow-ups: push paths that do not pass through it, an incomplete hidden-character set, agent-written ids in its log line, and a corpus test that stops one step short of the relay**

- **状态**：未开始（2026-10-11 复核 70 留下的，都不挡 TD-306 合并）
- **Claim**: TD-306 put one predicate at `notice.Send`. Review 70 found four things outside what that round set out to do. (1) `notice.Send` is not the only place a push leaves: `api/internal/alertrelay/relay.go` `publish` posts to ntfy on its own (Alertmanager alerts, heartbeat missing / recovered, direct `/alerts/notify`), and `scripts/agent/peer_watchdog.sh` curls ntfy directly; none of these check for hidden characters. Their text comes from alert labels, annotations and configuration, not from an agent's request, which is why this is P3. (2) `HasHidden` does not include U+2800, U+3164, U+FFA0, U+17B4, U+17B5, U+206A–U+206F, U+180B–U+180D, U+180F, U+E0100–U+E01EF. (3) The `notice withheld` log line carries the thread key or host name as `id`; those are agent-reported and are not redacted (they are emptied only when they themselves contain a hidden character). (4) The 100,000-string clean-corpus tests compare `Posted` with the composer, not what the fake relay received.
- **Measured**: NOT MEASURED by the coordinator; read from review 70 (`work/multi-agent/reviews/codex-2026-10-11-review70-td306-send-door.md`), which cites `api/internal/notice/hide.go:85`, `:118`, `api/internal/approvalnotify/door_test.go:146`, `api/internal/alertrelay/relay.go:398`, `scripts/agent/peer_watchdog.sh:40`.
- **Evidence**: the review file above; `bifrost-platform` branch `w31/td-306-d` `d7802d0`.
- **Impact**: low. An alert whose label or annotation carries a hidden character would reach the phone as written; a thread key chosen by an agent appears in one warning log line.
- **Fix**: route `alertrelay`'s publish through the same predicate with a server-written fallback (`Alert · <alertname>` is itself label text — use the alert's fingerprint); add the missing code points with tests; log a digest of the thread key or host name instead of the value; add a bounded Send → fake relay pass over the clean corpus.
- **Ratchet**: a test that lists every call site that posts to the push endpoint and fails when one does not go through `notice.Send` (a source scan with a positive control).
- 验收: `cd bifrost-platform/api && go test ./internal/notice/ ./internal/alertrelay/ ./internal/approvalnotify/`
- 审批 无（代码改动，随平台发布）· 代价 S · 风险 low · repos: bifrost-platform

## TD-321（原文，去处：agent-config/work/multi-agent/DESIGN-host-minimal-2026-10-12.md 风险）

**P3 · multi-agent · a silent wrapped run now notifies nobody, and a session that inherited the wrapper's marker is still treated as a wrapped run**

- **状态**：未开始（TD-316 签收时留下的后续，Owner 2026-10-12 签收）
- **Claim**: after TD-316 a thread whose id begins `run-` is left out of the Owner's silent-thread push, of "Needs you" and of the host-lost message (`bifrost-platform` `api/internal/agentthreads/config.go` `Due`, `threads.go` host message; `console/src/api/agentThreads.ts` `silentThreads`). It stays in the thread list with status `silent`, but nothing calls anyone: the seat that dispatched the run has to watch it itself. Today the only dispatcher is the coordinator, whose own watcher covers it. Second: a process that is not a wrapped run but inherited both `BIFROST_HEARTBEAT_THREAD=run-…` and `BIFROST_HEARTBEAT_WRAPPED_RUN=1` (a daemon or a terminal started from inside a wrapped run) reports under the run's id and is hidden the same way (review 126, P3; unchanged by TD-316).
- **Measured**: on PROD 2026-10-12 a wrapped run silent for 700 s was counted silent and not pushed (the acceptance of TD-316). No process with both variables existed on the coordinator's machine that day (review 126).
- **Impact**: none while one seat dispatches and watches. With a second dispatching seat, or a dispatcher without a watcher, a hung background run would go unnoticed.
- **Fix**: when there is a second dispatching seat, route a silent wrapped run to the seat that started it (the platform needs to know which seat that is — an interface decision for the Owner); let the marker carry the wrapper's pid and have the hook check that it is alive.
- **Ratchet**: none yet; the tests of TD-316 hold the exclusion itself.
- 验收: a wrapped run that hangs is brought to the seat that dispatched it within the threshold plus one beat; a session started from inside a finished wrapped run reports under its own id
- 审批 Owner（接口） · 代价 M · 风险 low · repos: bifrost-platform, bifrost-trade-infra

## TD-340（原文，去处：bifrost-platform Console 审批页设计风险（ADR-ops-architecture.md §5））

**P3 · ops-platform · leaving the approvals page while a decision is in flight and a newer Console is deployed loses the reload guard: the page offers Reload and a reload cuts the decision short**

- **状态**：未开始（2026-10-13 22:57 TD-338 的独立复核（Claude 子代理，实验 E5）顺带查出；原来就有，不是 TD-338 带进来的；只记不做）
- **Claim**: the guard that disables Reload while a decision is in flight (`reloadHeld`, set from a per-mount counter of decision requests) lives in the approvals page component. When the Owner leaves the page (for example back to Needs you) the component unmounts; the request keeps going, but the next mount starts with the counter at zero, so the banner says "Reload before approving" and Reload is enabled. The banner on the Needs you page does not hold either.
- **Measured**: MEASURED by the reviewing subagent's test E5 on the TD-338 branch (2026-10-13): A's POST still hanging, page left and reopened, Reload enabled. NOT MEASURED in a browser.
- **Evidence**: `bifrost-platform/console/src/pages/ApprovalsPage.tsx` (`postsInFlight` is a ref of the page component; `reloadHeld` recomputed from it); `console/src/pwa/ConsoleBuildBanner.tsx`.
- **Impact**: a reload in that moment can cut a decision short; since TD-329 the server finishes an action whose decision it stored, so the visible damage is the page losing track of the result, not the action.
- **Fix**: keep the count of decision requests in flight outside the page component (the module store the question pages already use is the precedent), and let every build banner read it.
- **Ratchet**: a page test: decision in flight, newer Console deployed, leave and reopen the approvals page: Reload stays disabled until the request is answered.
- 验收: the page test above
- 审批 无（代码改动，随平台发布）· 代价 S · 风险 low · repos: bifrost-platform

## TD-347（原文，去处：agent-config/work/multi-agent/DESIGN-agent-runtime-v5-2026-10-14.md §5.2 风险）

**P2 · agentrt · agentd's "machine-wide" lock is per user: two agentd under two users on one host both run**

- **状态**：未开始（2026-10-15 10:38 统筹方记；Gate A 计划 T22 ② 时读出来）
- **Claim**: design v5 §5.2 and `api/cmd/agentd/main.go:4` say one agentd per host under a machine-wide lock. The lock is `~/.config/bifrost/agentd.lock` of the user agentd runs as, so an agentd started by another user (with any host token) takes its own lock and runs beside the launchd one.
- **Measured**: MEASURED: 2026-10-15, platform main `296468b`, `api/internal/agentd/local.go:33-39` (`HostLockPath` joins `os.UserHomeDir()`).
- **Evidence**: `api/internal/agentd/local.go:33`; `api/cmd/agentd/main.go:62-70`.
- **Impact**: T22 ② (a second agentd on the same host must not take work) holds only when both run as `bifrost-agentd`; the platform's per-host cap still bounds concurrent attempts, but the local registry and takeover assume one daemon per host.
- **Fix**: a lock outside any home (e.g. `/var/run` or `/Library/Application Support/bifrost/agentd.lock`, created by `install-agentd.sh` owned by the agentd user, mode 0644 so others can open and flock it, never write it); or agentd refuses to start unless it runs as the user the installer configured. Options to the Owner with the Gate A plan.
- **Ratchet**: a test that two processes under two users (or two homes) on one host cannot both hold the lock.
- 验收: with the launchd agentd running, `AGENTD_*` set and another user's home, a second `agentd` exits with "held"
- 审批 选法要你定（锁的位置，安装脚本改动）· 代价 S · 风险 low · repos: bifrost-platform

## TD-362（原文，去处：agentd 设计文档风险节）

**P3 · agentd · setup.json and siblings.json stay on the host: the platform never sees which setup command failed, how long each took, or which sibling commit a task was built against**

- **状态**：未开始（2026-10-17 记；06 的 STG 演练 M-9，走查会话 `local_42a46b17…` 的报告 F6）
- **Claim**: agentd writes the setup commands' traces (time, exit code, output tail) to setup.json and the cloned siblings' commits to siblings.json in the attempt's output directory, but uploads only the report (verify.json or the executor's report) and the log tail. A setup that fails shows on the platform as exit 3 and nothing else; a setup that passes leaves no record of what was built against what.
- **Evidence**: `bifrost-platform/api/internal/agentd/setup.go:71` (siblings.json written), `:85` (setup.json path); `api/internal/agentd/deliver.go:224-240` (only the report body is put); `~/agent-work/stg-walk-06/REPORT.md` F6.
- **Impact**: a setup failure on the agent host is as silent as TD-361's; a review cannot tell which `bifrost-ui` commit a Console change was checked against.
- **Fix**: put both as artifacts of the attempt (kind `verify` for setup.json so H8 scans it, with the same path rewrite agentd uses for verify.json since `9d16b6f`), and reference them from the attempt's end.
- **Ratchet**: an agentd test that an attempt with setup commands and a sibling ends with both artifacts put and no H8 match in either.
- 验收: on STG, a Console task's attempt shows its setup trace and sibling commits in the Console.
- 审批 不需要 · 代价 S · 风险 low · repos: bifrost-platform

## TD-368（原文，去处：agentd 设计文档风险节）

**P3 · agentd · a read of the executor's log that hangs cannot be cut short**

- **状态**：未开始（2026-10-18 01:5x 记，复核 266 第 3 项、267 第 2 项、268 第 2 项留下的 B；2.3 第 3 片收线时接受）
- **Claim**: the collector reads `log.txt` with `Open` / `Seek` / `ReadAll`; a read of a regular file cannot be interrupted in Go. If the disk call never returns, the flush and the attempt time out and go on, but the collector goroutine, its open file and the tail stay until the read returns.
- **Evidence**: `bifrost-platform/api/internal/agentd/actions.go`, `read` (the `os.Open` … `io.ReadAll` block) and `collect`; review 268 `~/agent-work/codex-review-268/REPORT.md` item 2.
- **Impact**: low: only a regular file is read (a FIFO or link is refused), agent-work is on 06's own disk, and a hung read holds one goroutine per attempt, never a heartbeat or the hand-over. A hung local disk would stop much more than this.
- **Fix**: read in a child process the collector can kill (or move agent-work's logs where a read deadline works), only if a hang is ever seen.
- **Ratchet**: none yet; the regression tests hold the rest (a flush whose time ran out reads nothing, the keeper and the hand-over never wait for a read).
- 验收: a test that blocks the read in the kernel (a FUSE file) and sees the collector end.
- 审批 不需要 · 代价 M · 风险 low · repos: bifrost-platform

## TD-372（原文，去处：agentrt schema 设计文档风险节）

**P3 · agentrt · schema · a capability_score row's identity has no model provider**

- **状态**：未开始（2026-10-18 19:0x 记，复核 286 B1；随下一次 agentrt 迁移一起做）
- **Claim**: `capability_score` is unique on (executor, model, tool_version, job, task class, core, source, window_end), without `model_provider`. One executor running one model name under two providers in one in-job computation (cursor with `opus` from anthropic and from cursor-mix) makes two groups with one identity. The computation inserts with `ON CONFLICT DO NOTHING`, so the second group has no row; its sample is still in the computation's `capability_scored` event, which is what routing reads, so routing is right and only the table (the record a screen would show) misses it.
- **Evidence**: `bifrost-platform/api/internal/agentrt/migrations/0001_core.sql:381`; `api/internal/agentrt/store/scores.go` (`ComputeScores`, the insert); `TestTwoProvidersOfOneModel`; `~/agent-work/codex-review-286/REPORT.md` item 1.
- **Impact**: none on routing; an audit gap in the table for that pairing only, none today (no candidate pairs one executor and model name with two providers).
- **Fix**: a migration that replaces the unique key with one that has `model_provider` after `executor_actor_id`, then the insert without `ON CONFLICT`; no data to move (append-only rows stay valid). Not done now: an agentrt migration is a Job the Owner creates on STG and PROD, with the PROD DDL approved first, and this alone is not worth that round.
- **Ratchet**: `TestTwoProvidersOfOneModel` asserts both rows once the key has the provider.
- 验收: `go test ./internal/agentrt/store -run TestTwoProvidersOfOneModel` with the row assertion added passes.
- 审批 要（PROD 的 agentrt 迁移，你建 Job）· 代价 S · 风险 low · repos: bifrost-platform, bifrost-trade-infra

## TD-376（原文，去处：bifrost-trade-infra/agent-config/work/multi-agent/CUT-agentd-confine-2026-10-19.md §7）

**P3 · agentd · security · a process a setup command leaves behind (setsid) outlives the check and can drop a cursor hook into the workspace**

- **状态**：未开始（2026-10-19 03:4x 记；你 03:3x「三件照建议」③，第 2 轮先接受）
- **Claim**: agentd kills an attempt's process group, but a process that left the group with `setsid` during the setup step keeps running inside its own (narrow) wall. After agentd's `--refuse` check and before cursor reads its configuration it can write `.cursor/hooks.json` into the workspace; the hook then runs inside cursor's wall. `checkChanges` fails an attempt that leaves executor configuration behind, so the result is not accepted, but the hook has run.
- **Evidence**: `bifrost-trade-infra/agent-config/work/multi-agent/CUT-agentd-confine-2026-10-19.md` §7 items 4 and 5; `bifrost-platform/api/internal/agentd/setup.go`, `run.go`.
- **Impact**: a hostile dependency's install script can run code as cursor inside cursor's write wall; it cannot write outside the attempt's directories.
- **Fix**: run each attempt in its own cgroup (systemd `Delegate=yes` on the agentd unit, a child cgroup per attempt) and kill the whole cgroup after setup and at the end, so nothing outlives its step.
- **Ratchet**: a test on Linux: a setsid process started by setup is gone before the executor starts.
- 验收: that test passes on 06 (the confine probe gains the check), with `Delegate=yes` in both agentd units.
- 审批 要（改 06 上两个 agentd 的 systemd 单元，架构决定；你批）· 代价 M · 风险 medium · repos: bifrost-platform, bifrost-trade-infra

## TD-427（原文，去处：agent-config/work/multi-agent/CUT-online-status-2026-10-23.md 风险）

**P3 · agentrt · presence · with several API instances the controller's health probe samples the Service, so host-loss detection can be deferred (an accepted boundary)**

- **状态**：未开始（2026-10-23 统筹线程记；Owner 17:5x CDT 选「选项 1」：接受多实例时的概率保证并加推迟提示。原话记在运行时产物 `sha256:50ddb7590b536d7c2eebc1eda1cf1bf2df17502adae0f5096a683f9eb6fa0cd0`）
- **Claim**: the workers' controller decides whether the platform takes agentd's calls by probing the API Service with 5 fresh connections a pass (`bifrost-platform` `api/internal/server/agentrt_wire.go`, `serviceTakesCalls`). With one ready and one unready API instance, every connection of a pass can land on the unready one; each such pass is an observed outage, and the recovery after it gives every host 30 s again, so a really lost host can be judged late. A deferral past 2 minutes across two recoveries raises `presence_deferred`, so it is never silent, but it is not bounded.
- **Evidence**: reviews 529 (A-2) and 530 (A), `agent-config/work/multi-agent/reviews/codex-2026-10-23-review530-r3-35-online-r5.md`; production runs one API replica, Recreate (`k8s/base-platform/manifest.yaml`), so the case does not arise today.
- **Impact**: none while there is one API replica; with two or more, host-loss announcements can come late (visible as `presence_deferred`).
- **Fix**: before running more than one API replica, give the controller evidence of the Service's whole availability: probe each ready endpoint (read EndpointSlices: a new RBAC grant for the platform SA, the Owner's), or make the API's Kubernetes readiness include `agentrt_ready` (weigh that the API's other features would leave the Service while agentrt is not ready).
- **Ratchet**: a manifest check that platform-api `replicas` stays 1 until this item is closed (to add with the fix's first step).
- 验收: with two API instances, one ready and one never ready, and every host really stopped, the hosts are announced within 35 s of their last contact.
- 审批 要（RBAC 或 readiness 的取舍归 Owner）· 代价 M · 风险 low · repos: bifrost-platform, bifrost-trade-infra

## TD-461（原文，去处：agent-config/work/multi-agent/DESIGN-S6-v3-2026-10-29.md §5.6 风险）

**P2 · infra code-health · 绝对基线与实测有历史差距**

- **状态**：未开始（2026-10-30，W-31 S6 §5.6）。
- **证据**：`agent-config/scripts/code-health/scan.sh:239`、`:246`、`:298`；在 infra `70c66c5` 上离线扫描得到 shell 重复函数 10 / 基线 3、Python 重复函数 35 / 基线 1、超过 500 行文件 57 / 基线 3。设计中的旧观测为 `85f578e` 的 10、34、52，本次没有抬高 `baselines.env`。
- **影响**：直接使用绝对基线会使 infra CI 恒红；此前 infra 没有这道交付门禁。
- **修法**：单独分批减少重复与超长文件，降到现有绝对基线；本项不借修改基线消除历史差距。
- **防线**：S6 `scripts/landing/coverage_infra.py` 用 M0 扫描器比较 M0 与 R；任一指标增长即拒绝；`test_ci_infra_stages.py::test_health_real_500_to_501` 验证文档越过 500 行必红，缺失/不完整结果不算通过。
- **验收**：在完整工作区运行 `bash bifrost-trade-infra/agent-config/scripts/code-health/scan.sh --repo bifrost-trade-infra` 退出 0，且未上调任何基线。

## TD-495（原文，去处：R5:5.5-16 设计稿风险）

**P3 · Console · 新的审批单大约 50 秒后才出现在 Console**

- **状态**：未开始（2026-11-02 22:47Z 记）。
- **证据**：#261 在 22:46:52Z 建好，你在 Console 上先看了一次没找到，约 50 秒后才出现；落地那一侧当时已经是 awaiting_owner。审批列表和「你的」两处的刷新路径（轮询间隔、缓存、控制器那一轮的速度）未逐项测量。
- **影响**：你在等一张要你批的单时，看到的是「没有」。
- **修法**：先量清是哪一段慢；要你动手的请求几秒内出现，或者页面上写明列表是几点读的。
- **防线**：Console 测试：列表显示读取时间；建单后下一次读取一定包含它。
- **验收**：建单到 Console 上出现不超过 10 秒，连测 5 次。

## TD-499（原文，去处：DESIGN-r5-5.7-6-one-judge-before-main-2026-11-04.md 风险节）

**P3 · 交付 · 交付前不在本机跑 code-health，超长的 infra 文档只在落地 CI 里才被拦**

- **状态**：未开始（2026-11-01，R5:5.8-1 落地 CI 红时记）。
- **证据**：一份 744 行的 Markdown 设计文档让 `code.oversized.rocket.infra` 从 57 变 58（infra 把超过 500 行的 `*.md` 也算进去，`agent-config/scripts/code-health/scan.sh:278-280`），落地 CI `landing-ci-infra-538b09b…` 才拦下。`handin.sh` 交付前不跑这个扫描。
- **影响**：一次红的落地，要你多点一张卡。
- **修法**：`handin.sh propose` 或 `run` 对目标仓库跑 `scan.sh`，比较基点和候选，有回退就拒。
- **防线**：`test_handin.sh` 加一个 501 行 md 的用例，交付被拒。
- **验收**：交付一份超长 infra 文档时，`handin.sh` 在推分支前就拒绝。

## TD-504（原文，去处：R5:5.5-19 设计稿风险节）

**P3 · 计划视图 · R5:5.5-19 整页解释的测量不数折叠次数**

- **状态**：未开始（2026-11-03，R5:5.5-19 复核第 13 轮 S1）。
- **证据**（platform main `bb6af68b`）：`api/internal/agentrt/store/stepexplain_measure_test.go:190` 的 `TestExplainWholeAtScale` 记下时间、语句数和堆峰值，只断言解释的步数、时间和堆（`:318-328`）；没有断言一次解释里，每个仓库的落地折叠和 B5 折叠各只跑一次。
- **影响**：以后哪条路径绕过共享的 `repoExplain`（`store/stepexplain.go:339`、`:488`）又折叠了一次，语句数不会变，只会表现为变慢，测量指不出原因。
- **修法**：在解释路径的 `LandingState` / `StgReleaseState` 外面套一个只在测试里用的读取计数，断言每个事务里每个仓库各一次，并和测量结果一起打印。
- **现在的挡板**：语句数（多 17,000 行与否都是 793）和每个仓库共享一个 `repoExplain`。折叠重复了会显在时间上，不会显在语句数上。
- **防线**：上面的计数断言留在测量测试里。
- **验收**：`AGENTRT_EXPLAIN_MEASURE=1 go -C api test ./internal/agentrt/store/ -run TestExplainWholeAtScale -v` 打印每个仓库的折叠次数为 1 并断言；故意多折叠一次时测试失败。

## TD-505（原文，去处：R5:5.5-19 设计稿风险节）

**P3 · 计划视图 · R5:5.5-19 逐项查取消的几处没有各自的回归测试**

- **状态**：未开始（2026-11-03，R5:5.5-19 复核第 14 轮 S1）。
- **证据**（platform main `bb6af68b`）：`api/internal/agentrt/store/stepexplain.go:255` `explainRework` 的三个循环（`:281`、`:296`、`:315`）和 `store/explainroot.go:54` `ExplainRootWithin` 的第一遍（`:99`）都逐项查 context；`store/stepexplain_internal_test.go:322` 的 `TestExplainRootCardsStopOnCancel` 只覆盖 `addRootCards`（`stepexplain.go:190`）和 `indexCards`（`:386`）。
- **影响**：删掉其中任何一处检查，测试照样绿；取消或超时之后，解释可能还要扫很多项才停。
- **修法**：每个循环一条测试，在它之前取消，断言它带着取消错误停下（rework 用预先建好的 `repoExplain` 和 `stepLanding`；第一遍用已取消的 context 加很多步骤）。
- **防线**：这几条测试本身；每条在删掉对应检查时失败（阴性对照）。
- **验收**：`go -C api test ./internal/agentrt/store/ -run StopOnCancel -count=1` 全过；逐一去掉这四处检查，各有一条测试失败。

## TD-507（原文，去处：TD-444 第 5 步设计（scripts/nas/backup-rollup）风险节）

**P3 · NAS 备份 · MinIO 回读：一次性 MinIO 建出来后报错、按运行令牌又查不到时，当成「没有容器」删掉草稿快照（TD-444 第 5 步复核第 5 轮 S1）**

- **状态**：未开始（2026-11-03 20:2x CST，复核停止线把它延后）。
- **证据**（infra `3f2b041`）：`scripts/nas/backup-rollup/minio-readback.sh:102` 按运行令牌查容器，查询失败被 `|| true` 吞掉，`RB_CID` 为空；`:104` 于是不记容器；`:264` 把空的 `RB_CID` 当成没有容器，删掉草稿快照。
- **影响**：`docker run` 建了容器再报错、`docker ps` 同时也失败时，容器可能还挂着这个草稿快照在跑，却没留下任何记录供下次清理。
- **修法**：分清「查过，没有」和「查不了」。查不了时保留草稿快照，在 `pending-cleanup.list` 记 `container-unknown <token>` 和 `scratch <path> <uuid>`，下次运行确认这个令牌的容器已经不在了再清；永远不按名字删。
- **防线**：`scripts/nas/tests/test_rollup_minio.sh` 加一个用例：替身在建容器后报错、`ps` 也失败：草稿保留，两行都挂起；下一次查询正常时两行都清掉。
- **验收**：`bash scripts/nas/tests/run.sh test_rollup_minio.sh` 全过，新用例在 `3f2b041` 上失败。

## TD-508（原文，去处：TD-444 第 5 步设计（scripts/nas/backup-rollup）风险节）

**P3 · NAS 备份 · `pending-cleanup.list` 里缺字段的行被悄悄丢掉或改写（TD-444 第 5 步复核第 5 轮 S2）**

- **状态**：未开始（2026-11-03 20:2x CST，复核停止线把它延后）。
- **证据**（infra `3f2b041`）：`scripts/nas/backup-rollup/rollup.sh:211`：没有 uuid 的 `snapshot` 行、路径又不存在时，`drop_snapshot` 因为 `:194` 的 `[[ -d $s ]] || return 0` 返回成功，这一行就没了；`:212` 的 `scratch` 一样。`:205` 和 `minio-readback.sh:77-80` 把缺令牌的 `container <id>` 改写成 `container <id> -`。
- **影响**：一条写坏的清理记录会被当作已清理而消失，或被改成别的样子；之后没人知道还有东西没清。
- **修法**：按类型检查每行的列数和格式（快照和草稿：绝对路径 + uuid；容器：12–64 位十六进制 id + 令牌）。不合格的行原样保留，在日志里写 ERROR，绝不交给 `drop_*`。
- **防线**：测试用例 `snapshot /missing`、`container <id>`、`scratch <path>`：三行都原样留下，并记 ERROR。
- **验收**：`bash scripts/nas/tests/run.sh test_rollup.sh test_rollup_minio.sh` 全过，这三个用例在 `3f2b041` 上失败。

## TD-509（原文，去处：DESIGN-r5-5.7-6-one-judge-before-main-2026-11-04.md S4）

**P3 · 发布 · push-main 跑仓库快测试时几分钟没有输出，看着像卡住了**

- **状态**：未开始（2026-11-03 20:2x CST 记）。
- **证据**（infra `3f2b041`）：`scripts/release/push_main_tests.py:149` 的 `run` 把每个进程的输出写进文件（`:171-174`），等待循环（`:168-198`）里什么都不打印，结束后只打印失败的（`:208-215`）和一行汇总（`:219`）。`scripts/release/push-main.sh:382` 只在开跑前列一次测试路径。一次 infra 推送要静默 3–5 分钟，被当成挂了。
- **影响**：推 main 的人分不清它是在跑还是卡住了，可能中途打断。
- **修法**：`push_main_tests.py` 每 15 秒打印一行进度（完成 N/M、还在跑的是哪几个、各跑了多久），每个文件跑完打印一行；`push-main.sh` 开头先说「推之前要跑 k 个测试文件」。
- **防线**：测试：跑得比间隔长的一次至少打印一行进度；失败时照样打印完整输出。
- **验收**：`python3 -m pytest -q scripts/release/test_push_main.py` 全过，含新用例；下一次 infra 推送跑测试时，每 15 秒至少有一行进度。

## TD-510（原文，去处：R5:5.5-20 设计稿风险节）

**P3 · Console · 正在跑的步骤卡展开「To finish」后，同一个任务名出现两次（R5:5.5-20 复核 S2）**

- **状态**：未开始（2026-11-03 23:0x CST，R5:5.5-20 第 1 轮复核的 should-fix，复核停止线把它延后）。
- **证据**（R5:5.5-20 交付提交 075b0f9b）：`console/src/pages/shell/agents/PlanModuleDetail.tsx:115-122`：步骤在跑时 `named` 为空，`Latest task` 照常写出最新的任务；挡路的行要在 `StepWhy` 里展开后才出现（`:178`），展开与否是 `StepWhy.tsx:110` 的内部状态（`:123-130`），`PlanModuleDetail` 不知道它开着。
- **影响**：展开后同一个任务名在卡上出现两次，不符合这一步「任务名在卡上只出现一次」的要求。
- **修法**：把展开状态提到 `Stage`，展开时从 `Latest task` 里去掉挡路的行已经点名的任务。
- **防线**：`stepCard` 测试：展开后任务名只出现一次。
- **验收**：`npm --prefix console test -- src/pages/shell/agents/__tests__/stepCard.test.tsx` 全过，新用例在 075b0f9b 上失败。

## TD-511（原文，去处：API-REQUIREMENTS-IA-v2 §4.2（Design））

**P3 · Console · `one_of` 的结论比 §4.2 的表多了一条例外（R5:5.5-20 复核 S3）**

- **状态**：未开始（2026-11-03 23:0x CST，R5:5.5-20 第 1 轮复核的 should-fix，复核停止线把它延后）。
- **证据**（R5:5.5-20 交付提交 075b0f9b）：`console/src/pages/shell/agents/explainModel.ts:382-383` 的 `anySig` 要每条路径都是「没人」才得出「Nobody is on it.」，`:385` 对 `one_of` 用它；`:369-376` 的说明先照 §4.2 的表写（有安静的、没有任务等任何一处就是 Nobody is on it），末尾另加了这条例外。设计文档 API-REQUIREMENTS-IA-v2 §4.2 不在仓库里，原文未核实。
- **影响**：一条路径没有任务、另一条在等审批时，卡上写「Waits.」，按表应是「Nobody is on it.」；实现和设计说法不一，后来的人不知道以哪个为准。
- **修法**：按表实现，或者请 Design 把这条例外写进 §4.2；定了之后改代码或改文档。
- **防线**：一个样例（一条 `no_task` 路径、一条等审批的路径）把定下的规则钉住。
- **验收**：`npm --prefix console test -- src/pages/shell/agents/__tests__/explainModel.test.tsx` 全过，含这个样例；§4.2 和 `anySig` 说法一致。

## TD-512（原文，去处：agentd 额度设计稿风险节）

**P3 · agentd · 某个模型自己的周限额被拒时，只有厂商措辞对得上才冷却 claude 周池**

- **状态**：未开始（2026-11-02 记；platform `a4c83f96` 没有关掉它，见证据）。
- **证据**（platform main `bb6af68b`）：`api/internal/agentd/usage.go:461` 只在 `refusal != ""` 时让 `modelRefusal` 的拒绝生效。`refusal` 只有两个来源：失败的 result 文字匹配 `claudeLimit`（`:182`、`:400-402`），或者一条 `error: rate_limit` 的 assistant 消息、且主线程模型在它之后没再回答（`:406-407`、`:451-452`）。`seven_day_opus` 这类被拒事件本身（`:426-429`）不算。这个条件正是 `a4c83f96`（11-02）有意加的，防的是「换了模型接着跑的运行也冷却整个账号」，所以它没有关掉这个缺口。`:370-374` 的注释也写着，拒绝文字的形状还没在真实运行里见过。`usage_test.go` 的 `TestMeasureClaudeModelWeeklyLimits` 没有「被拒的模型事件 + 失败但措辞不认识的 result + 没有 rate_limit 消息」这个用例。
- **影响**：厂商换个说法，或者不发 rate_limit 消息时，模型周限额被拒不冷却任何池；后面的认领照样派给 claude，一次次被拒，直到执行者因连续失败被撤下（TD-395）。
- **修法**：判断依据从措辞改成事件：最新的模型周限额事件是 rejected、主线程模型在它之后没有回答、且运行以失败或没有 result 结束，就算这个模型的拒绝，冷却到它的重置时间；被拒后又接着回答的运行照旧不算。
- **防线**：`usage_test.go` 两个方向的用例：上面这种运行冷却周池到该模型重置；被拒后主线程模型接着回答的运行不冷却。
- **验收**：`go -C api test ./internal/agentd/ -run TestMeasureClaudeModelWeeklyLimits -count=1` 通过，新用例在 `bb6af68b` 上失败。
