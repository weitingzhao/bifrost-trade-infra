# Bifrost 技术债（未结）

> **这份文件只放没还完的债。** 历史在 git 里，这里不留。审计扫出来的、日常工作里撞上的，都直接在这里加一条，编号接着当前最大号往下排。每条必须有证据（`文件:行`）、修法和防线。条目正文保留英文，标识符照抄。
>
> **每一项怎么走（Owner 2026-10-06）**
> 1. **状态**只有五种：`未开始` → `在做` → `观察中（到 MM-DD，看什么）` → `待你签收`；签收后删掉这一项。
> 2. **验收**：每项写一条验收命令和预期结果。进 `待你签收` 之前必须重跑它，把 `验收结果：PASS|FAIL 日期 提交号` 写回这一项。没有新的 PASS，不能进 `待你签收`。
> 3. **待你签收**：进这个状态时，在下面「待你签收」一节加一行：改了什么、验收结果、加了哪条防线（`RATCHETS.md`）、**后续**（引出的新编号，或「无后续：理由」）。Owner 回复「签收 TD-n」或「打回 TD-n：原因」。
> 4. **签收后**：删掉这一项和「待你签收」里那一行；「还债顺序」里把编号移到「已还」，计划进度一直看得见。提交信息写签收、防线和后续。打回的，状态回到 `在做`，原因写进 `下一步`。
> 5. **自上次以来**：下面「上次查看」记着 Owner 上次看过的提交。台账页从那个提交起生成变化清单（新增、关闭、状态变化、防线增减）。Owner 说「看过了」，就把它改成当前提交。

上次查看：4b4c957（2026-10-06，Owner 说「看过了」）

## 待你签收

- **TD-177** — 假设卡（active / validated）加「＋ Plan」，打开现有 PlanForm 并预填 source_kind=hypothesis、source_ref=假设 id（单 symbol 时带 symbol），存草稿前不写任何东西（frontend 0e0b69a3）· 验收 PASS（10-06，3 个用例 + 本地点击）· 防线：`src/pages/research/loop/HypothesisBoardPage.plan.test.tsx` · 后续：TD-143 正向验收要你在 DEV 从假设卡建 plan 并成交；随 10-07 Trade 发版上线
- **TD-179** — Stock screen 不选模型时可按财报日排序（逾期在前、无估计在后），RankDrawer 启用 Earnings（frontend 0e0c9637）· 验收 PASS（10-06，4 个用例；DEV 真数据 3,794 名）· 防线：`stockScreenEarnings.test.ts` 排序用例 + `RankDrawer.test.tsx` · 无后续；随 10-07 Trade 发版上线

**未结 78 项**：P0 0 · P1 5 · P2 30 · P3 43；要你批的 40 项（从总览表的审批列算）。

## 主题（第 2 轮）

- **Green while wrong: jobs succeed on zero, partial or garbage output** — The dominant round-2 class. Engines, gates, ingest handlers and writers convert failures into success: empty lists read as answers, exceptions become 0 or 'unknown', truncation is a field nobody checks, freshness bumps on zero-row jobs. Dagster and Flex show green; only manual metadata reading finds it. Fix pattern: raise or record reasons, and add output checks per asset. (TD-91, TD-92, TD-93, TD-94, TD-97, TD-100, TD-101, TD-106, TD-113, TD-116)
- **Session and calendar truth comes from the wall clock on UTC pods** — Session dates are derived from current_date/date.today() on UTC hosts at 02:30 UTC, producing next-day and Saturday stamps (SEPA, option_universe), a day-late alert judge, and a calendar that silently forgets holidays on a failed read. One session_today() helper plus a nightly session-date sweep closes the class. (TD-87, TD-98, TD-93, TD-97, TD-111)
- **Broker money ledger integrity (Flex / IB)** — The cash and commission ledgers have a 5-month hole the fixed window cannot refill, a writer that reports failure as success, a dedupe key that ignores IB's own id, mixed commission signs, DEV-routed reads and no tests on the money path; the gateway health signal is permanently false-red. (TD-91, TD-103, TD-114, TD-115, TD-116, TD-117, TD-104, TD-122)
- **Gates that do not gate** — CI runs after delivery and never blocks it (research and Trade); plugins and infra have code-health baselines but no CI; preflight D10 matching misses non-curl clients and in-place edits; operator streams use a denylist; no alert watches Dagster schedules or research/plugin 5xx. Making CI gate release is the single highest-leverage ratchet. (TD-95, TD-96, TD-105, TD-99, TD-109)
- **Hand-kept copies and dead config drift** — Schedule rosters, max-pain/PCR math, Black-Scholes and risk-free readers, declared indexes, spine copies, instance configs and suspended CronJobs exist in several places that have drifted from the source of truth. Generate from one source or delete; ratchet with manifest and catalog checks. (TD-108, TD-102, TD-110, TD-107, TD-112, TD-118, TD-119, TD-120, TD-121, TD-123, TD-124, TD-125)

## 先看这几条

- **TD-87** — SEPA 全部晚一个交易日、周五落到周六。代码已修（research 0.180.0）；历史 101,673 行要在 10-07 02:30 UTC 批处理前由 Owner 跑 restate，命令在备份目录 README。
- **TD-91** — 现金流水写库失败被记成「成功、0 行」。TD-88 刚补完五个月的洞，这个写入方再静默失败一次，新的覆盖告警要到月底才响。
- **TD-92** — Research 的引擎资产永远是绿的：按标的失败、0 行写入、跳过都只进元数据。TD-89 停了三天没人发现就是这一类。
- **TD-95** — 没有任何发布等 CI：research 0.172–0.174 是在 CI 红着的时候发的，trade-api main 从 10-04 起 CI 是红的，三个插件仓库自 09-29 起 32 次提交 0 次 CI。`RATCHETS.md` 里的测试类防线在这之前都只是提醒。
- **TD-96** — preflight 的 D10 闸门只认 curl；修改稿在 `REQUEST-td96-preflight-d10-2026-10-06/`，等 Owner 审。

- **TD-130** — 真正在生产数据层上动手的 Ops 自动修复跑在 Owner 的笔记本上（本机 bdev 的 platform-api），集群里 STG/PROD 那两份在空转；10-05 到 10-06 对备份 MinIO 的重启和补备份都是它做的。

## 还债顺序

### 第 0 波 · 第 1 轮收尾

目标：第 1 轮剩下的三项按已排的日期收掉。TD-85 剩 Golden Source 的 PUBLIC CONNECT；TD-51 等 Loki 闸门后随下一次 Trade 发布；TD-80 C2-b 改号 core 0.49.0 与 TD-51 同发。

项：TD-85 · 已还：TD-21, TD-51, TD-80

### 第 1 波 · 正在出错的数据与「绿着的失败」

目标：先让失败变红。错数据先修数据（TD-87 restate），再把引擎、闸门、写入方从「出错也报成功」改成失败即失败：引擎资产按输出判定、husbandry gate 失败即关、日历读失败报错、写入方失败抛错。不需要 Owner 批的先做。

项：TD-87, TD-91, TD-92, TD-94, TD-97, TD-101, TD-136, TD-156, TD-157, TD-166 · 已还：TD-88, TD-89, TD-90, TD-113, TD-93, TD-165, TD-167

### 第 2 波 · 让闸门真的卡住

目标：一个开关让所有测试类防线生效（CI 卡发布），再补上调度存活告警、D10 闸门的非 curl 写法、operator 流白名单、本机常驻任务和密钥轮换的盲区、spine 副本同步。

项：TD-95, TD-96, TD-100, TD-105, TD-109, TD-121, TD-152, TD-153, TD-155, TD-161, TD-162 · 已还：TD-99

### 第 3 波 · 交易日与日历只有一个来源

目标：所有「今天 / 本 session」都从 `db/calendar` 的一个函数来，代替 11 个私有 helper 和 44 处 `date.today()`；dbt 补 grain 测试；IV / 回测的定价参数统一。

项：TD-98, TD-110, TD-111, TD-112, TD-128, TD-129, TD-174, TD-175 · 已还：TD-164

### 第 4 波 · 券商资金账本（Flex / IB）

目标：现金与佣金账本可信：按 IB transactionID 去重（改表）、佣金一种符号、资金路径有测试、Flex 不再经 DEV 库读配置、IB Gateway 健康与镜像可追溯。

项：TD-103, TD-104, TD-114, TD-117, TD-122 · 已还：TD-115, TD-116

### 第 5 波 · 副本、死重与清单

目标：删掉没人用的（挂起的 CronJob、退役脚本、无调用路由），手抄的副本改成从一处生成（调度名单、max-pain / PCR），清单的应用顺序与 Argo 归属理顺。

项：TD-102, TD-106, TD-107, TD-118, TD-119, TD-120, TD-123, TD-124, TD-125, TD-160, TD-169, TD-170, TD-176 · 已还：TD-126, TD-108, TD-154, TD-163, TD-168

### 第 6 波 · 备份链与自动修复（10-06 日常发现）

目标：备份 MinIO 已搬到 NAS（infra 1ee0ac2，已接监控 ba03488），把剩下的收尾：自动修复只在 PROD 一处动手、失败记录不再被删、platform 的新检查上线、稳定一周后退役集群里的 MinIO 残留，再处理 WAL 体量和 CNPG 1.30 的备份插件。

项：TD-130, TD-131, TD-132, TD-133, TD-134, TD-135, TD-173

### 第 7 波 · 数据缺口（10-06 由 Data Gaps 看板并入）

目标：Data Gaps 看板上未结的 15 项并入台账：先把每日快照的写入修对（TD-137）再接读侧和三页，归因行补上价格，Research 侧已就绪的一个版本（0.185.0）发出去，长期限 IV 锥在 10-31 前从 option_daily 回填，其余按 Owner 已定的口径排。

项：TD-137, TD-138, TD-139, TD-140, TD-142, TD-143, TD-144, TD-145, TD-146, TD-148, TD-149, TD-150, TD-151, TD-158, TD-159, TD-171, TD-172, TD-177, TD-178, TD-179, TD-180, TD-181, TD-182 · 已还：TD-141, TD-147

## 数据边界（接受并留座）

> 订阅或市场本身没有的数据：接受，页面留座并写明原因；不算债、不编号，订阅或市场变化时重开（§5「缺数据先分原因」）。来自 Data Gaps 看板，10-06 并入。

- **已确认的财报日历（◉）** — 订阅里没有：10-06 `/research/events/calendar?days=60` 8 行，全是 ws:macro 与 ws:corporate，财报 0 行；插件只有 8-K Item 2.02 的过去财报。页面写 estimated · confirmed dates not in the subscription；预计日 expected_next 在跑（NVDA → 2026-11-18，track n=4、中位误差 0 天）。依据：看板 R2.a，10-06 实测。还在写「no earnings date reaches this side」的四处在 TD-150。
- **merger / spinoff 与 IB Flex 公司行为报表** — Owner 2026-09-17 裁定不做，除非重开：vendor 只给 dividend 与 split（抽样 17 名 833 行，0 merger、0 spinoff），能填的只有 Flex 的公司行为报表，没有接。依据：`bifrost-trade-frontend/src/layout/designNotes/portfolio.ts:76`；看板 B4.2-3。
- **CUE 只有调整合约** — CUE 1:30 合股（除权 2026-04-24）后交易所没有挂标准系列，只剩 10-16 到期的 14 个 CUE1 合约（10-05 OI 14 行）：市场本来没有，max pain / ATM IV / GEX / flow / PCR 留空是对的。依据：看板 R10.CUE，10-06 实测。页面上的说明在 TD-150。

## 需要你拍板

### 现金写入失败要改成抛错吗？（改 core 公开接口）

- 推荐：B。core 新增严格版写入函数（失败抛错、返回写入与跳过数），旧函数保留一个版本；Flex 插件改调新函数，解析出行数 > 0 而写入 0 时任务失败。做法同第 1 轮 TD-80 C2-a。
- 选项：A：直接改 `upsert_account_transactions` 的语义并抬高下游下限 · B：新增严格版、旧版留一版 · C：只在插件侧判断（core 不动）
- 项：TD-91

### 让 CI 卡住发布吗？（跨仓库发版）

- 推荐：A。`release.sh stg/prod` 和 deliver-research / build-research-dagster 在该 SHA 的 CI 未成功时拒绝（Owner 可用 `--allow-red <理由>` 放行）；先修好 trade-api main 的红，三个插件仓库补上 CI 触发。
- 选项：A：发布前要求同 SHA 的 CI 成功 · B：deliver 流水线里先跑 lint-test 再构建 · C：维持现状，只在发布后告警
- 项：TD-95

### 三个改表 / 迁移顺序项一起批吗？

- 推荐：一起批，分开执行。TD-103 加 `flex_transaction_id` 列、从 `raw_extra` 回填（169 行都有）、部分唯一索引；TD-107 用 CONCURRENTLY 补建 financials 的索引；TD-119 迁移 Job 拆成单独的 kustomization，先迁移后部署。
- 选项：A：三项都做 · B：只做 TD-103（钱）· C：都推后
- 项：TD-103, TD-107, TD-119

### 安全收口四项

- 推荐：都做。TD-85 收回 Golden Source 上 PUBLIC 的 CONNECT（先给 `market_reader` 等显式授权）；TD-105 operator 流改成显式白名单；TD-121 密钥轮换时重启所有挂这个 Secret 的 research Deployment；TD-96 按修改稿应用。
- 选项：A：四项都做 · B：先做 TD-96、TD-105（D10 相关）· C：只做 TD-96
- 项：TD-85, TD-96, TD-105, TD-121

### 删除两组死重吗？

- 推荐：删。TD-124 39 个永久挂起的 CronJob（25 research + 14 market-data + 1 孤儿）连同 verify 脚本里的检查；TD-125 TIBM 时代的 verify 脚本和已不存在 schema 的 flex_ops SQL。
- 选项：A：两组都删 · B：先删 TD-124 · C：都保留
- 项：TD-124, TD-125

### IB Gateway 的健康与镜像

- 推荐：A。网关健康哈希写 `updated_at`、Trade 的服务行指向 `data/ib-gateway`（TD-104）；镜像改走集群内 Tekton 构建、按 digest 钉版本（TD-122）。
- 选项：A：两项都做 · B：只做 TD-104 · C：维持本机构建
- 项：TD-104, TD-122

### 19 条没人调用的 research 路由

- 推荐：B。先加 Deprecation 头和访问日志观察一个版本，零命中再删（同第 1 轮 TD-40）；Agent / 蒸馏的手动触发改成「启动对应的 Dagster job」。
- 选项：A：直接删 · B：先观察一版再删 · C：保留
- 项：TD-123

### Ops 自动修复只在 PROD 动手吗？失败的备份记录保留吗？

- 推荐：A。PROD 的 platform-workers 作为唯一会动手的 autopilot：先干看一遍它拿到真实检查清单后会触发什么（09-22 那条顾虑），接上并在 PROD 审计日志里确认它在动手，**之后**本机 bdev 的 platform-api 才设 `PLATFORM_ROLE=api`（顺序反了就没有一份在动手）；STG 只观测不动手。修复工具不再删除失败的 Backup 记录，30 天后再清理（这一项不依赖前面的顺序，可以先做）。
- 选项：A：只 PROD 动手 + 保留失败记录 · B：本机先停，其余以后再定 · C：维持现状
- 项：TD-130, TD-131

### 备份链的三项后续

- 推荐：TD-132 现在发布（STG 再 PROD，只带 a332cff 一个提交）；TD-134 调大检查点间隔并开 `wal_compression`（只需 reload，不重启）；TD-135 在把 CNPG 升到 1.30 之前装 cert-manager 并换 Barman Cloud Plugin，单独排期。
- 选项：A：三项都按推荐 · B：先做 TD-132、TD-134 · C：只做 TD-132
- 项：TD-132, TD-134, TD-135

### 快照三列的 PROD DDL 与 core 0.51.0 单独发布

- 推荐：A。等 Code Refactor 那批（core 0.49.0 / 0.50.0 + api 0.10.0）PROD 通过后单独发 core 0.51.0 + infra deaa2ca。DDL 只有三条：`account_nav_daily` ADD COLUMN IF NOT EXISTS `cushion` / `excess_liquidity` / `maint_margin_req`（double precision、可空、无默认、不回填，10-05 起已存的行留 NULL）；无自加项；无不可逆步骤（不要时可 DROP COLUMN）。行为变化：收盘时陈旧的账户当天不写、20:30 的 `all` 补抓，U17113214 不再每天写 NAV。每个环境先跑 db-init 再换镜像，否则 capture 的 INSERT 缺列失败。
- 选项：A：按这三列确认并单独发 · B：并进下一批 Trade 发布一起发 · C：先不发（每晚继续锁进副账户的盘中值，压力历史继续丢）
- 项：TD-137

### 数据缺口的三处设计 / DDL

- 推荐：TD-144 做，评判记在 `candidate_pool.source_ref.persona`（零 DDL，只往后记，不回填）；TD-146 先不建，Agrees with you 列保持灰显并写明原因，等你要开始记手动判词时再按 database-design 出 `journal.*` 新表设计；TD-148 按清单确认：`strategy_plan` 的 source_kind CHECK 先删后加、只放宽（加 `lens`、`backtest_run`），PROD 0 行、无新列、无回填，core 的两处词表同改（改公开接口，core 抬小版本）。
- 选项：A：按推荐 · B：TD-144、TD-146 都出新表设计，TD-148 照做 · C：只做 TD-148，两列都保持灰显
- 项：TD-144, TD-146, TD-148

## 总览

| 编号 | 级别 | 领域 | 标题 | 审批 |
|---|---|---|---|---|
| [TD-85](#td-85) | P1 | trade (round 1) | One database password reaches everything: any DEV pod can write PROD Trade and all of Golden Source | 安全/凭据（要你批） |
| [TD-87](#td-87) | P1 | research-data | SEPA features are stamped with the next calendar day (UTC current_date at 02:30 UTC): every SEPA row is one session late and Friday sessions land on Saturday | 不用批 |
| [TD-91](#td-91) | P1 | flex-ib | A failed cash-transactions write is recorded as a successful run: core returns 0 on any exception and the job counts it as 'ok, 0 rows' | 改公开接口 |
| [TD-92](#td-92) | P2 | research-control | Engine assets never fail: per-symbol failures, zero-row writes and skips are only metadata, reasons are discarded, and research_trading_day is green regardless of output | 不用批 |
| [TD-94](#td-94) | P2 | research-control | husbandry_gate fails open: a probe exception leaves verdict 'unknown', which passes, and the gate never checks that the doctor's session is the one being closed | 不用批 |
| [TD-95](#td-95) | P2 | research-control | No release path is gated on CI: deliver-research ships SHAs whose CI is red (CI starts 7s after deliver), and release.sh never checks CI for Trade | 跨仓库发版 |
| [TD-96](#td-96) | P2 | agent-governance | preflight.js D10 rule only recognises curl: python requests, wget --post-data and sed -i on the daemon scale-zero patch all pass | 安全/凭据（要你批） |
| [TD-97](#td-97) | P2 | research-data | alert_scan judges each session once, a day late, and never revisits; composite_high has never fired because every >=90 score appeared on a later scan recompute | 不用批 |
| [TD-98](#td-98) | P2 | research-data | 'Today' is resolved by 11 private helpers plus 44 bare date.today() calls on UTC pods; option_universe stamps tomorrow's date | 不用批 |
| [TD-100](#td-100) | P2 | research-control | Event Radar SEC ingest runs from a Mac tmux loop on the shared checkout; it read .env once and failed 157 ticks over ~35.6h after a password rotation; the cluster event_radar slot never ingests and stays green | 不用批 |
| [TD-101](#td-101) | P2 | market-data | Doctor slot staleness reads a per-kind freshness row that other slots and zero-row jobs also refresh, so a stopped policed slot still reads fresh | 不用批 |
| [TD-102](#td-102) | P2 | market-data | Plugin's deprecated live max-pain and PCR routes duplicate Research and skip the adjusted-contract filter: different strikes on the same day, and trade-api SEPA PCR reads the contaminated one | 改公开接口 |
| [TD-103](#td-103) | P2 | flex-ib | The cash parser never stores IB's transactionID, so dedupe falls back to (account, day, amount, type, report_date) and same-amount items overwrite each other | 改表 |
| [TD-104](#td-104) | P2 | flex-ib | Trade Ops reports all three IB Gateway services 'offline' on PROD: the gateway's health hashes have no updated_at, and the service rows point at retired StatefulSets | 跨仓库发版 |
| [TD-105](#td-105) | P2 | flex-ib | DEV/STG operator streams accept every op except two (a denylist), so any op added later is open to DEV and STG by default | 安全/凭据（要你批） |
| [TD-106](#td-106) | P2 | market-data | Nightly trim (now with W3 archive) runs synchronously behind Dagster's 60s HTTP timeout; retries start overlapping trims and the recorded outcome is the retry's | 跨仓库发版 |
| [TD-107](#td-107) | P2 | market-data | Indexes declared for the six financials entity tables never reach a deployed DB (the migration returns early); live differs from fresh install | 改表 |
| [TD-109](#td-109) | P2 | ops-platform | PROD platform-api reads a deployed ops-context.yaml copy last synced 2026-08-24: about 33 spine decisions missing (D-Journal-Stores, D-Ops-Split, D-Wave-10..13) | 跨仓库发版 |
| [TD-110](#td-110) | P3 | research-data | Stored IV features solve Black-Scholes at r=0 while the backtester uses treasury rates from two separate readers; further BS copies in gex and opex | 不用批 |
| [TD-111](#td-111) | P3 | research-data | dbt: the pass_count range generic test sits in the singular folder (errors when selected, never applied); key intermediates lack grain tests; nothing ties eval_date to the session | 不用批 |
| [TD-112](#td-112) | P3 | research-data | option_surface_iv_daily upserts per (symbol, trade_date, expiry) and never deletes, so expiries a re-walk dropped keep their old smile | 不用批 |
| [TD-114](#td-114) | P3 | flex-ib | raw_broker.commissions mixes two sign conventions: Flex writes cost as negative, the TWS/gateway path writes it as positive | 不用批 |
| [TD-117](#td-117) | P3 | flex-ib | 'Latest Flex date in DB' after an import is one run behind: read through FDW in the same transaction as the pre-import read | 不用批 |
| [TD-118](#td-118) | P3 | market-data | option-refresh re-enumerates names with no listed options every run; its 7-day 'finished' lookback reads a table kept 48h | 不用批 |
| [TD-119](#td-119) | P3 | market-data | Schema-migrate Job and worker Deployments are applied in one `kubectl apply -k` with no ordering; a table-adding release fails the jobs that land in the DDL window | 改表 |
| [TD-120](#td-120) | P3 | research-control | Dagster Deployments are applied by hand outside Argo; a second, unmounted dagster_instance.yaml lacks the run_monitoring that catches zombie runs | 跨仓库发版 |
| [TD-121](#td-121) | P3 | research-control | Research pods read bifrost-research-secrets once at start (optional: true); the OpenAI key rotation helper restarts only research-api | 安全/凭据（要你批） |
| [TD-122](#td-122) | P3 | flex-ib | The IB Gateway image is built on the Mac and imported to nodes with ctr under a reused tag: no registry, no digest, no recorded source SHA | 跨仓库发版 |
| [TD-123](#td-123) | P3 | research-control | About 19 deployed research-api routes have no caller in frontend, platform, trade-api or MCP, including manual POST triggers that run engine code outside Dagster | 改公开接口 |
| [TD-124](#td-124) | P3 | research-control | 39 permanently suspended CronJobs (25 research, 14 market-data, plus an orphan pinned to 0.10.0) are still deployed and re-pinned every release; research ones carry a stale 26-name watchlist and the verify script contradicts the one active CronJob | 删除（要你批） |
| [TD-125](#td-125) | P3 | flex-ib | Retired IB topology still referenced: TIBM-era verify scripts at the top of scripts/, flex_ops compat SQL for a schema that no longer exists | 删除（要你批） |
| [TD-128](#td-128) | P3 | research-data | Pine signal rows mix adjustment bases: nightly runs rewrite only the last ~10 sessions on today's adjusted bars, older rows stay on the basis of their last full rebuild | 不用批 |
| [TD-129](#td-129) | P3 | research-data | The event backtest picks option legs from option_daily only; since mid-August 2026 it keeps ~10 strikes a side, so a target delta silently lands on the nearest strike that is left | 不用批 |
| [TD-130](#td-130) | P1 | ops-control | ops-autopilot acts on the shared cluster's data layer from the Owner's laptop (local bdev platform-api, role all); the in-cluster STG/PROD autopilots idle on an empty checklist, and each of the three keeps its own throttle | 要你批 |
| [TD-131](#td-131) | P2 | ops-control | repair_cnpg_wal_store deletes failed Backup CRs, erasing the record of failed backups | 要你批 |
| [TD-132](#td-132) | P2 | ops-control | bifrost-platform a332cff (checks and WAL repair aware of the NAS MinIO) is on main but not released to STG/PROD | 发布（要你批） |
| [TD-133](#td-133) | P3 | data | Leftovers of the in-cluster MinIO after the move to the NAS (deploy/minio at 0, its PVC/PV, an empty EndpointSlice, the backup-retry CronJob) | 要你批 |
| [TD-134](#td-134) | P2 | data | WAL is ~19.5 GiB/day (4.2 GiB compressed) because checkpoints run every 5 minutes without wal_compression | 要你批 |
| [TD-135](#td-135) | P3 | data | Native barmanObjectStore backups are removed in CloudNativePG 1.30; the Barman Cloud Plugin that replaces them needs cert-manager, which the cluster does not have | 新依赖（要你批） |
| [TD-136](#td-136) | P2 | research-data | GEX writes levels for an expiry whose open interest is all zero: walls and zero_gamma fall on an arbitrary strike, 1,534 rows on 496 names, and terrain and scan copy them | 已批（观察中） |
| [TD-137](#td-137) | P1 | trade-data | The daily snapshot capture locks an account's intraday book into the day (first write wins, no freshness test) and account_nav_daily stores no margin-pressure fields | 改表 + 发布（要你批） |
| [TD-138](#td-138) | P2 | trade-data | The daily position and NAV snapshots have no reader: no trade-api route, no Research or frontend read, and three pages still say the snapshot does not exist | 不用批 |
| [TD-139](#td-139) | P3 | trade-data | Snapshot Greeks carry no quality flag (vendor / degraded / missing): only mark_source and greeks_asof are stored | 不用批 |
| [TD-140](#td-140) | P2 | trade-data | Position attribution rows have no price, intraday or after the close: their only price source is contract_quote_live, which only the frozen daemon writes | 不用批 |
| [TD-142](#td-142) | P2 | research-data | The 90-day IV cone has 31–39 sessions of history and there is no 180-day tenor: ATM IV was stored only to 90 DTE before 2026-08-05 | 要你批 |
| [TD-143](#td-143) | P3 | research-data | Hypotheses never link to trades: linked_opportunity_ids is empty on all 91 rows, and only Research's own create / patch writes it | 不用批 |
| [TD-144](#td-144) | P3 | research-data | Settled candidates are not attributed to the judge (persona) that put them forward, so the Personas bench track-record columns stay grey | 要你批 |
| [TD-145](#td-145) | P3 | research-data | Settled candidates carry no regime label, so the Personas bench 'Best regime' column has nothing to group by | 不用批 |
| [TD-146](#td-146) | P3 | research-data | No store accepts a hand verdict, so the Personas bench 'Agrees with you' column cannot be computed | 要你批 |
| [TD-148](#td-148) | P3 | trade-data | A trade cannot name the lens or backtest run it came from: trade has no such column and strategy_plan.source_kind does not allow lens / backtest_run | 改表（要你批） |
| [TD-149](#td-149) | P2 | market-data | CTVA's adjusted daily bars ignore its 2026-10-01 spin-off, so every return-based feature on CTVA sees an ~84% one-day drop | 不用批 |
| [TD-150](#td-150) | P3 | frontend | Pages report gaps that are not there: 'no earnings date reaches this side', 'carry nothing at all' for names the vendor answered, and no note that CUE lists only adjusted contracts | 不用批 |
| [TD-151](#td-151) | P3 | research-data | The macro calendar is empty: features.macro_event_daily has 0 rows because macro_ingest has no scheduled caller | 不用批 |
| [TD-158](#td-158) | P3 | research-data | Earnings estimates are served one name per request, so no universe-wide page can show an Earn column | 不用批 |
| [TD-159](#td-159) | P3 | market-data | No read says how many standard and adjusted option contracts a name has, so "only adjusted contracts are listed" is inferred in the browser from ticker shapes | 不用批 |
| [TD-152](#td-152) | P2 | ops-platform | promtail drops log lines (ingester_error) around 02:00–03:15 and 22:xx UTC, so every Loki-based release gate can come out INCONCLUSIVE | 不用批 |
| [TD-153](#td-153) | P3 | ops-platform | loki_gate.py only knows the pre-0.10.0 log line ('deprecated query params'); after api 0.10.0 refused callers log 'retired query params' and the gate cannot see them | 不用批 |
| [TD-155](#td-155) | P2 | ops-platform | Pushes to GitHub main do not trigger CI until the Gitea pull mirror syncs, so a commit can be released before its CI ever ran | 跨仓库发版 |
| [TD-156](#td-156) | P2 | research-control | research_signal_hit_schedule fires at 00:10 UTC, before the 02:30 UTC batch writes the night's features, so it judges the previous night's features | 不用批 |
| [TD-157](#td-157) | P3 | research-data | GEX writes a wall on an arbitrary strike when one side of an expiry has no gamma exposure: 1,762 levels rows on 244 names, terrain reads both walls | 已批（观察中） |
| [TD-160](#td-160) | P3 | research-data | features.event_signal_radar_daily keeps the pre-rename copies of two indexes (event_radar_batch_collected, event_radar_importance) beside the current ones | 改表 |
| [TD-161](#td-161) | P3 | ops-platform | BifrostAPIHighErrorRate / HighLatency only see bifrost-* namespaces with http_requests_total; research-api and the plugins export no HTTP metrics, so their 5xx and latency go unalerted | 不用批 |
| [TD-162](#td-162) | P2 | ops-platform | Research and plugin releases have no release window: sessions collide on pins and on deliver runs | 跨仓库发版 |
| [TD-166](#td-166) | P2 | research-data | GEX zero_gamma was the strike nearest spot on 38% of daily levels rows (no change of sign), and a step out of zero counted as a crossing; terrain read it as a flip at spot | 已批（观察中） |
| [TD-169](#td-169) | P3 | market-data | ops_jobs.ingest_freshness.option_expiration is a fossil row frozen since 09-06 and still listed as ok | 不用批 |
| [TD-170](#td-170) | P3 | research-control | dagster-daemon logs one line over 256 KB at the 22:45 and 03:00 UTC schedule ticks every night | 不用批 |
| [TD-171](#td-171) | P3 | frontend | Positions shows the attribution price_last as if it were live: no EOD label or date now that core 0.51.0 fills it from the vendor EOD mark | 不用批 |
| [TD-172](#td-172) | P2 | research-data | ATM IV has almost no 50–90 DTE expiry from 2026-07-06 to 09-25 (the EOD chain stopped at the third listed expiry until plugin 0.39.0); the fix was forward-only, so term structure reads na for that stretch | 要你批 |
| [TD-173](#td-173) | P2 | infra | ubt-k3s-06 has no nfs-common: pods with an NFS volume scheduled there hang in ContainerCreating (mount exit 32) | 要你批 |
| [TD-174](#td-174) | P3 | market-data | Console marks fundamentals-rotate missed every Monday 03:45 → Tuesday 03:00 UTC: the trading-day check uses the UTC date of the fire | 不用批 |
| [TD-175](#td-175) | P3 | market-data | ticker-details adherence still credits the shared ticker_sync freshness row, so a stopped ticker-details reads on_plan after reference's 21:30 walk | 不用批 |
| [TD-176](#td-176) | P3 | research-control | Suspended CronJobs cronjob-signal-hit.yaml and cronjob-alert-scan.yaml still ship and get re-pinned every release though Dagster runs both | 删除（要你批） |
| [TD-177](#td-177) | P3 | frontend | No way to create a plan from a hypothesis: PlanThisButton writes source_kind 'symbol' and PlanForm takes a hand-typed slug, so TD-143's hypothesis → trade link never forms | 不用批 |
| [TD-178](#td-178) | P3 | trade-api | GET /strategies/plans has no source_kind filter: Research reads the newest 500 filled plans and filters itself, marking truncated at the cap | 改公开接口 |
| [TD-179](#td-179) | P3 | frontend | Stock screen with No model cannot sort by Earnings: RankDrawer still disables it although the batch read now serves the dates | 不用批 |
| [TD-180](#td-180) | P3 | research-data | The macro calendar has no CPI dates after 2026-12-10 and no payrolls at all: bls.gov answers 403 from this host, so they could not be read | 不用批 |
| [TD-181](#td-181) | P3 | research-data | /events/calendar takes its macro rows from a hand-dropped radar file (ends 2026-12-10) instead of macro_event_daily, and radar ids include the collection date so a re-drop duplicates them | 不用批 |
| [TD-182](#td-182) | P3 | research-data | Macro gap (actual vs expected) is always empty: consensus is not in the subscription, and the entitled /fed/v1/inflation actuals have no raw table | 改表（要你批） |

## 条目

### TD-85

**P1 · trade (round 1) · One database password reaches everything: any DEV pod can write PROD Trade and all of Golden Source**

- **状态**：观察中（到 10-07，看 `data_writer` 撤掉 `raw_broker` 权限后一个插件日内有无权限报错）
- **验收**：Golden Source 的 `datacl` 里没有 PUBLIC 的 CONNECT（`=c`），且 Postgres 日志 24 小时内 `data_writer` / `flex_writer` 的 `permission denied` 为 0：`kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -At -c "SELECT datacl FROM pg_database WHERE datname = current_database()"`
- **现在**：D1–D8 全部执行完：三环境 Trade 运行时用 `trade_app_<env>` 登录；D4 已在三个 Trade 库收回 PUBLIC 的 CONNECT 和 CREATE（10-06，验证 74/74）；D7 ConfigMap 已合入；D6 收口完成，`data_writer` 在 `raw_broker` 上的写权已撤（core 0.48.2，10-06）。
- **下一步**：Golden Source 上 PUBLIC 仍能 CONNECT（D6 范围，未排期，要你批）；`data_writer` 撤权后再看一个插件日的权限报错。（10-07）
- **Claim**: Measured 2026-10-04 (read-only): nine Secret keys hold the same value, the bifrost password (PGPASSWORD and GOLDEN_SOURCE_PASSWORD in bifrost-{dev,stg,prod}-secrets, flex-query postgres-password / trade-pg-password, market-data postgres-password). bifrost can INSERT into 320 Golden Source tables and CREATE in raw_broker and research; analytics_writer inherits bifrost and can write all 19 tables of bifrost_prod.public. PUBLIC has CONNECT/TEMP on all four databases and CREATE on public in the Trade databases. D13 is not enforced at the database layer in either direction.
- **Evidence**:
  - `REQUEST-trade-runtime-db-role-plan-2026-10-04.md:1` — ``
- **Impact**: A compromised or misconfigured DEV workload can modify PROD trading data and the Research store; Research can write Trade tables.
- **Fix**: Per-env runtime roles trade_app_<env> (NOINHERIT, own database only; Golden Source only raw_broker and ops_feedback), bifrost kept for db-init/CNPG; Secret switch per env with one-patch rollback; then revoke PUBLIC CONNECT/CREATE, rotate the bifrost password, and separately drop analytics_writer's bifrost membership after Research gets explicit grants.
- 审批 安全/凭据（要你批） · 代价 L · 风险 medium · repos: bifrost-trade-infra, bifrost-research

### TD-87

**P1 · research-data · SEPA features are stamped with the next calendar day (UTC current_date at 02:30 UTC): every SEPA row is one session late and Friday sessions land on Saturday**

- **状态**：在做（代码已上线；等 Owner 跑历史数据重排）
- **验收**：`SELECT count(*) FROM features.stock_signal_sepa_daily WHERE extract(isodow FROM trade_date) IN (6,7)` 为 0，且下一次 research_trading_day 里 asset check `sepa_projection:sessions_are_trading_days` 通过
- **现在**：代码已修并上线（research 0.180.0，10-06）：七张 SEPA mart 改用 `sepa_session()`（源表最新交易日），`sepa_projection` 写纽约 session；防线 dbt 测试 `sepa_session_is_newest_trading_day` + Dagster asset check `sepa_projection:sessions_are_trading_days` + 静态测试。历史行还没改：写 PROD Golden Source 被 auto mode 拦下，交 Owner。
- **下一步**：Owner 跑 `~/bifrost-backups/golden-source/2026-10-06_td87-sepa-restate/` 里的 restate.py（101,673 → 94,759 行，删碰撞 6,914 行，09-01 的行实为 08-27 收盘、按数据改到 08-27）和 SEPA lens 重走；须在 10-07 02:30 UTC 批处理前，否则先重跑 dry run。跑完删掉本条。（10-07）
- **Claim**: All seven SEPA marts set eval_date = current_date. The database runs in Etc/UTC and research_trading_day fires at 22:30 New York (02:30 UTC the next day). mart_sepa_feature_daily turns eval_date into trade_date, and sepa_projection copies MAX(trade_date) into features.stock_signal_sepa_daily. So the Monday 10-05 session is stored as 2026-10-06 and Friday sessions as Saturday. signal_hit (_load_sepa_triggers WHERE trade_date = %s), the backtest event source and every join on trade_date pair SEPA with the following session; signal_hit walks only trading days, so Friday SEPA triggers are never read and Monday sessions have no SEPA input.
- **Measured**: MEASURED (re-checked by verifier). show timezone = Etc/UTC; no role/profile timezone override. dw_stock.mart_sepa_feature_daily holds only 2026-10-06 (3,742 rows) while int_stock_daily_enriched max(trade_date) = 2026-10-05. features.stock_signal_sepa_daily since 07-01: 5 Saturday dates, 1 Sunday, 1 Monday (09-28, a manual run); 21,016 of 101,673 rows in the last 60 days fall on a weekend. It is the only features/research/dw_stock/journal table with weekend trade_dates. lens_hit lens='sepa' has 1 Monday vs 3-5 for every other weekday.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/dbt/models/marts/mart_sepa_technical_eval.sql:45` — `current_date as eval_date,`
  - `bifrost-research/src/bifrost_research/dbt/models/marts/mart_sepa_feature_daily.sql:9` — `w.eval_date as trade_date,`
  - `bifrost-research/src/bifrost_research/orchestration/sepa_projection.py:80` — `SELECT MAX(trade_date) FROM dw_stock.mart_sepa_feature_daily`
  - `bifrost-research/src/bifrost_research/orchestration/schedules.py:85` — `cron_schedule="30 22 * * 1-5",`
- **Impact**: Stored data is wrong now. SEPA lens hit rate, forward returns, SEPA backtests (entries one session late; Friday signals enter Monday) and the screener eval_date all describe the wrong session. Friday SEPA triggers never reach lens_hit; Monday lens_hit has no SEPA input.
- **Fix**: Derive the session from the data, not the clock: eval_date = (select max(trade_date) from int_stock_daily_enriched), or pass --vars '{as_of: <NY session>}' from the Dagster asset; sepa_projection passes the NY session explicitly. Then restate stock_signal_sepa_daily (Research-owned) by shifting each row to the last session on or before trade_date - 1 (dry run first) and re-walk the SEPA lens with delete-then-insert.
- **Ratchet**: (1) dbt test on mart_sepa_feature_daily: trade_date = max(bar_date) of source and is_trading_day (gives dim_trading_calendar a reader or replaces it). (2) Nightly session-date sweep (~30 lines SQL) as asset check/Prometheus rule: no features.*/research.* row with trade_date on a weekend, holiday or later than the newest SPY bar.
- 审批 不用批 · 代价 M · 风险 med · repos: bifrost-research

### TD-91

**P1 · flex-ib · A failed cash-transactions write is recorded as a successful run: core returns 0 on any exception and the job counts it as 'ok, 0 rows'**

- **状态**：未开始
- **Claim**: core upsert_account_transactions catches every exception, logs a warning and returns 0; the plugin turns that into ok:true 'Upserted 0 transaction(s)', _require_ok accepts it, record_freshness(ok=True) advances last_success, and no BifrostFlexIngest* alert fires. A lost grant (TD-86 class), lock timeout or type error drops a day's cash rows silently. It also returns len(rows), including rows skipped for missing account_id/report_date. core tests/test_connect_helpers.py:118 currently pins the silent 0 return, so this is a deliberate contract change. The trades path does not have this flaw (returns False → ok:false).
- **Measured**: CODE-READ for the failure path; jobs 151-185 all wrote 11-16 rows. Precedent is real: TD-86 broke a different writer on 10-05 via dropped grants.
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1417` — `logger.warning("upsert_account_transactions failed: %s", e)`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1413` — `return len(rows)`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/transactions.py:104` — `msg = f"Upserted {n} transaction(s) from {len(entries)} Flex account(s)."`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/worker/handlers.py:30` — `inserted = int(data.get("count") or data.get("inserted") or 0)`
- **Impact**: Cash ledger rows can stop landing while the plugin, its metrics and Ops Console report healthy runs: the failure-as-success class TD-08 fixed for reads, now on a money writer.
- **Fix**: Make upsert_account_transactions raise on DB errors (or return (written, skipped) and let the caller raise). Update test_connect_helpers.py:118 and bump core per the versioning rule since the plugin depends on the return. In the plugin treat parsed rows > 0 with written == 0 as ok:false; report skipped separately.
- **Ratchet**: Core test: a raising cursor must propagate. Plugin test: rows>0 with written 0 must raise. code-health metric: `except Exception` blocks in persistence writers ending in return 0/False without re-raise; baseline may only fall.
- 审批 改公开接口 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-platform-plugin-flex-query

### TD-92

**P2 · research-control · Engine assets never fail: per-symbol failures, zero-row writes and skips are only metadata, reasons are discarded, and research_trading_day is green regardless of output**

- **状态**：观察中（到 10-07 02:30 UTC 批处理，看 16 个引擎的 output_ok 检查都执行了）
- **验收**：`kubectl -n research logs deploy/dagster-daemon --since=3h | grep ASSET_CHECK_EVALUATION` 在 research_trading_day 里有 16 个 engines 的 output_ok；ERROR 级失败会发 `BifrostDagsterAssetCheckFailed`
- **验收结果**：部分 PASS 2026-10-06 a242b22：32 个 output_ok 检查已加载，intraday run 两个检查通过；批处理待今晚
- **Claim**: engine_assets._metadata wraps any result into MaterializeResult; run_gex/run_iv_surface/run_flow do `failed += 1` and drop result['error']; run_slot returns a non-raising 'skipped: no symbols'. No Dagster asset checks exist; only gex_intraday raises on zero output (added after three green weeks of 646-669/669 failures). The only other net is signal_health's 36h/72h computed_at freshness on a subset of tables, which misses partial failures, zero-row writes, wrong-date writes and tables such as research.option_pinned_contract. Silent failures like TD-89 and TD-97 are visible only by reading run metadata by hand.
- **Measured**: MEASURED. ops_dagster.runs research*/market*, 14 days: 1,026 SUCCESS, 1 FAILURE (memory_distill, TD-86), 1 CANCELED. 10-06 run metadata: gex 42 failed / 1,366 ok over 2 sessions (~3%, about 15-22 names a night), flow 41, surface 41, momentum skipped 4, vrp skipped 7, option_pinned rows_written 0, all green. Most failing names entered option_universe in the last few days (onboarding lag); persistent invisible gaps: NVR (in universe since 09-08, 0 OI rows since 08-01, never a GEX row) and GRML (since 09-24, no OI); QRVO stock_daily stops at 10-02.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/engine_assets.py:36` — `def _metadata(result: dict[str, Any]) -> dict[str, Any]:`
  - `bifrost-research/src/bifrost_research/scheduler/engines.py:108` — `failed += 1`
  - `bifrost-research/src/bifrost_research/orchestration/research_aux_schedules.py:51` — `return MaterializeResult(metadata=meta(result if isinstance(result, dict) else {}))`
  - `bifrost-research/src/bifrost_research/orchestration/engine_assets.py:300` — `result = runners.run_option_pinned_contract()`
- **Impact**: A broken engine looks the same as a working one on the Ops schedule view and in failure_alerts. NVR and GRML have had no GEX/surface/flow for weeks and nothing says why; onboarding lag, upstream gaps and bugs are indistinguishable.
- **Fix**: Return failures as {symbol: error} (capped) plus per-reason counts from gex/surface/flow. Add Dagster asset checks (or raise in runners) with floors against a trailing baseline: rows_written >= 50% of the 10-run median, failure share among names past the onboarding window <= ceiling, a past-onboarding name failing 2+ sessions, mode != skipped twice running. Route check failures through failure_alerts; push persistent per-reason gaps to the Data Gaps ledger.
- **Ratchet**: Test enumerating ENGINE_ASSETS and RESEARCH_AUX_ASSETS: each has a registered asset check or an explicit opt-out with reason. Unit test: every slot summary carrying symbols_failed carries a failures-by-reason dict. code-health metric: bare `failed += 1` in scheduler/ (baseline 3, falling).
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research

### TD-94

**P2 · research-control · husbandry_gate fails open: a probe exception leaves verdict 'unknown', which passes, and the gate never checks that the doctor's session is the one being closed**

- **状态**：观察中（到 10-07 02:30 UTC 批处理，看闸门放行且 expected_session = market_session）
- **验收**：今晚 husbandry_gate 的 metadata：`gate=pass`、`expected_session == market_session`；探针失败时 run 变红（12 个单测覆盖）
- **Claim**: Since research a241f30/47af11e (09-28) the gate reads a freshly computed doctor report (refresh=true, 600s timeout), which fixed the stale-session and empty-report runs of 09-16..09-26. What remains: any doctor/Flex probe exception is logged as a warning and the verdict stays 'unknown'; the gate raises only on critical/failed/stale/none, so 'unknown' passes, and no assertion ties doctor.session to the session being closed. dbt and every engine then run with the EOD gate off.
- **Measured**: MEASURED. Before the 09-28 fix: unknown verdicts passed on 09-16, 09-25, 09-26; wrong-session 'healthy' on 09-22 (gated 09-18) and 09-24 (gated 09-22). All 6 runs since 09-29 carry the right session and generated_at. tests/orchestration/test_husbandry_gate.py has no all-probes-fail case.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/plugin_batch_assets.py:148` — `except Exception as exc:  # noqa: BLE001`
  - `bifrost-research/src/bifrost_research/orchestration/plugin_batch_assets.py:169` — `if eod_verdict == "critical":`
- **Impact**: Latent: on a night the plugin is down or doctor computation exceeds 600s, dbt, SEPA and all engines rebuild on a possibly incomplete session and report SUCCESS, the 09-05 'recomputed on partial data' class the gate exists to stop.
- **Fix**: Treat 'unknown' as failure for EOD and Flex checks (raise; explicit override config for manual runs). Compute the expected session via fetch_recent_trading_days and raise when doctor.session differs or generated_at is missing.
- **Ratchet**: test_husbandry_gate.py: (a) all probes raise → asset raises; (b) doctor.session != expected → raises; (c) generated_at missing → raises.
- 审批 不用批 · 代价 S · 风险 med · repos: bifrost-research

### TD-95

**P2 · research-control · No release path is gated on CI: deliver-research ships SHAs whose CI is red (CI starts 7s after deliver), and release.sh never checks CI for Trade**

- **状态**：未开始
- **Claim**: pipeline-deliver-research goes mirror-sync → clone → build/pin-check → gitops-sync → rollout → verify and never reads the bifrost-ci-python result for the revision it ships; both start from the same push ~7s apart, so a red CI cannot stop a release. It also accepts revision=main instead of a SHA. release.sh (Trade) likewise does not check CI status. CI is a post-hoc report.
- **Measured**: MEASURED. research 0.172.0, 0.173.0 (twice) and 0.174.0 delivered while their CI runs (hkrvq, bjgln, z96rg, sccxz) Failed; the only failed task was a code-health false positive (pine image tag counted), fixed in infra 1984dac; lint-test passed, so nothing broken shipped. Ratchet inventory: trade-api main CI red since 10-04 (test_bs_core_switch::test_core_reproduces_the_recorded_research_math), 14 of 28 runs failed in 7 days, api 0.9.0 released anyway; the three plugin repos had 32 commits and infra 120 commits since 09-29 with 0 CI runs; Tekton metrics are not scraped.
- **Evidence**:
  - `bifrost-trade-infra/k8s/cicd/tekton/pipeline-deliver-research.yaml:126` — `- name: pin-check`
  - `bifrost-trade-infra/k8s/cicd/tekton/pipeline-ci-python.yaml:14` — `CI gate for Python repos — ruff lint + pytest (skipping IB/DB markers);`
  - `bifrost-trade-infra/scripts/release/release.sh` — `(no reference to ci-* PipelineRun status; CODE-READ per ratchet inventory)`
- **Impact**: A real ruff/pytest failure reaches the Golden Source writers (research) or Trade with nothing to stop it. Every test-based ratchet in this ledger is advisory until CI gates release.
- **Fix**: Add a lint-test (ruff + pytest + code-health) task on the cloned SHA ahead of build in pipeline-deliver-research and pipeline-build-research-dagster, or require a Succeeded ci-* run for that exact SHA. Reject non-40-char revisions. release.sh refuses stg/prod unless the SHA's CI Succeeded (--allow-red <reason> for Owner).
- **Ratchet**: Infra check-script YAML assertion: every deliver pipeline has a lint-test task in build's runAfter and validates revision as a SHA. BifrostCIMainRed alert (scrape tekton controller metrics): any repo's latest main ci-* Failed > 2h.
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-research

### TD-96

**P2 · agent-governance · preflight.js D10 rule only recognises curl: python requests, wget --post-data and sed -i on the daemon scale-zero patch all pass**

- **状态**：未开始
- **Claim**: The monitor /control/* rule requires curl-style -X/--request/-d/--data/--json/-F flags, and guard-file protection recognises rm/mv/truncate. A POST via python requests/httpx, wget --post-data, or an in-place edit of k8s/overlays/stg/daemon-scale-zero.patch.yaml with sed -i/tee/cp is allowed. The gate covers only agent tool calls; humans and CI do not pass through it.
- **Measured**: MEASURED by the ratchet-inventory pass (sample strings fed to preflight.js locally): `sed -i … daemon-scale-zero.patch.yaml`, `python3 -c requests.post('…/api/monitor/control/arm')` and `wget --post-data … /control/arm` each returned ALLOW. test.js (42 cases) passes but has no case for these forms and runs in no CI. Not adversarially re-verified.
- **Evidence**:
  - `bifrost-trade-infra/agent-config/scripts/agent-guard/preflight.js:107` — `/\/(account-sync\/)?control\/[\w-]+/.test(cmd) &&`
  - `bifrost-trade-infra/agent-config/scripts/agent-guard/preflight.js:109` — `/\bcurl\b[^|;&]*\s(-d|--data[\w-]*|--json|-F|--form)\b/.test(cmd))`
- **Impact**: The D10 hard boundary's mechanical layer can be bypassed by an ordinary alternate client or file edit; only the spine/overlay layer remains. Same class as TD-07.
- **Fix**: Owner-applied (agents must not edit guard files): extend d10Rules to match /control/ writes via requests/httpx .post/.put/.delete, wget --post-data/--method, http(ie) POST; extend the guard-file rule to sed -i/tee/cp/>/kubectl patch|edit|apply on the scale-zero/observe-safe patches and daemon replicas. Add one DENY case per form to test.js.
- **Ratchet**: test.js gains a DENY case per bypass form and runs blocking in a new ci-infra pipeline (see ratchet proposal 'ci-infra').
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-97

**P2 · research-data · alert_scan judges each session once, a day late, and never revisits; composite_high has never fired because every >=90 score appeared on a later scan recompute**

- **状态**：观察中（到 10-07 02:30 UTC 批处理，看 alert_scan 判的是当天 session）
- **验收**：今晚 alert_scan 的 metadata：`as_of == session == 2026-10-06`；`--dry-run --rejudge 25` 能重新判出 composite_high
- **Claim**: alert_scan runs at 22:30 UTC and takes as_of = MAX(trade_date) of the scan table, so session X is judged at 18:30 ET on X+1. It writes each date once. The scan engine re-walks the last 3 sessions, and the only composite_score >= 90 rows (META 08-31; AVGO/HUM/NKE/PEP/PSX/VLO 09-24) appeared on those later recomputes, so composite_high has produced nothing and the job is green.
- **Measured**: MEASURED. features.stock_signal_alert_daily since 08-28 (21 dates): hit_rate_drop 38, weight_shift 51, composite_high 0. META 08-31 was written 09-03 02:32; the six 09-24 names 09-29 02:36. 99th percentile score since 09-01 is 78.6; 7 qualifying rows ever.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/research_aux_schedules.py:473` — `"30 22 * * 1-5",`
  - `bifrost-research/src/bifrost_research/engines/alert_scan/entry.py:50` — `cur.execute(f"SELECT MAX(trade_date) FROM {TABLE_STOCK_SIGNAL_SCAN_DAILY}")`
  - `bifrost-research/src/bifrost_research/engines/alert_scan/entry.py:63` — `WHERE trade_date = %s AND composite_score >= 90`
- **Impact**: The headline alert kind is dead (small volume: 7 rows in ~5 weeks); digest and Copilot readers never see top-composite names; other kinds arrive a session late.
- **Fix**: Re-evaluate the last N scan dates with replace-per-(trade_date, kind) semantics so a recompute can raise or retract an alert, and move the job into research_trading_day with deps on engines/scan (removes the lag).
- **Ratchet**: Unit test parsing every ScheduleDefinition: an aux job whose engine reads a table written by research_trading_day may not fire between 20:00 and 02:30 UTC (small reads→writers map next to the assets). Asset check: judged as_of equals the latest NY session.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-98

**P2 · research-data · 'Today' is resolved by 11 private helpers plus 44 bare date.today() calls on UTC pods; option_universe stamps tomorrow's date**

- **状态**：观察中（到 10-07 02:40 UTC，看 option_universe 不再盖明天的日期）
- **验收**：10-07 02:40 UTC 之后 `select max(last_seen) from research.option_universe` = `2026-10-06`（若是 2026-10-07 即 FAIL）；ruff DTZ 基线 0
- **下一步**：已有错误盖章（10-06 那次 678 行 last_seen、44 行周六 entered_on）属于改写 Golden Source，由 Owner 决定是否修正；`orchestration/research_aux_schedules.py:108` 还剩一处内联纽约日期
- **Also (paydown lane A, 10-06)**：`engines/pine/build.py:191` `end = as_of or date.today()` — UTC date on the 02:30 UTC run, the next calendar day.
- **Claim**: Eight helpers return the New York date (_today_ny), three return the UTC date (_today in option_universe, option_pinned, terrain_backfill), and 44 date.today() calls return UTC because no research pod sets TZ. db/calendar.fetch_recent_trading_days also defaults to the UTC date. decline_memory.py documents the wrong 'same host' assumption, and the `noqa: DTZ011` there does nothing because ruff selects only E4/E7/E9/F. Anything run by research_trading_day (02:30 UTC) through _today()/date.today() gets the next calendar day.
- **Measured**: MEASURED. No TZ env on research-api, dagster-daemon, dagster-webserver, research-mcp, research-pine or api-research. In dagster-daemon, date.today() = 2026-10-06 while NY was 10-05. research.option_universe: 678 rows last_seen 2026-10-06; entered_on on Saturdays (10-03: 6, 09-26: 9, 09-19: 24). candidate_pool path is latent (writers run when UTC and NY agree).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/option_universe/entry.py:85` — `return datetime.now(timezone.utc).date()`
  - `bifrost-research/src/bifrost_research/engines/option_universe/entry.py:227` — `"last_seen": as_of if seen else (prev["last_seen"] if prev else as_of),`
  - `bifrost-research/src/bifrost_research/copilot/harness/decline_memory.py:320` — `trade_date=date.today(),  # noqa: DTZ011`
  - `bifrost-research/src/bifrost_research/db/calendar.py:181` — `end = as_of or datetime.now(timezone.utc).date()`
- **Impact**: option_universe stores wrong dates and its liquidity/liveness windows shift a day; any engine adopting date.today() for a session stamp repeats TD-87. Each copy is a place the session rule can drift.
- **Fix**: One session_today() (latest NYSE session <= NY date) and ny_now() in db/calendar.py; replace the 11 helpers and stamp-carrying date.today() calls. Set TZ=America/New_York on Dagster/research pods only as a defensive layer.
- **Also (found by the TD-87 fix, 10-06)**: `engines/option_pinned/entry.py` `_today()` and `engines/forecast/terrain_backfill.py` `_today()` (UTC); `engines/backtest/event_query.py:160,1322`, `engines/brief/synth.py:79,486`, `copilot/agents/_context.py:26`, `copilot/harness/readiness.py:29` (`date.today()`); `lenses/exhibit_lenses.py:532` (`CURRENT_DATE - 30`). `db/calendar.latest_closed_session` (0.180.0) is the shared NY-session helper to adopt.
- **Ratchet**: Enable ruff DTZ (DTZ005/DTZ011) for src/ with a falling baseline; code-health grep fails on a new `def _today`/`def _today_ny` outside db/calendar.py.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research

### TD-100

**P2 · research-control · Event Radar SEC ingest runs from a Mac tmux loop on the shared checkout; it read .env once and failed 157 ticks over ~35.6h after a password rotation; the cluster event_radar slot never ingests and stays green**

- **状态**：观察中（到 10-07 04:30 UTC 之后，看当天新申报由集群写入）
- **验收**：`research_event_radar_job` 最新 run 为 SUCCESS 且 metadata `mode: sec_8k`；10-07 04:30 UTC 批次后 `source LIKE 'ws:sec-8k-%'` 的 `max(computed_at)` ≥ `raw_market.sec_8k_filing` 的 `max(fetched_at)`
- **验收结果**：部分 PASS 2026-10-06：17:30 UTC run 8384e946 SUCCESS、mode sec_8k、读 736 条、新增 0（已全部入库）；Mac 上的 bdev 会话改为只处理投放目录文件（17:3x）
- **Claim**: The only producer of SEC 8-K input for features.event_signal_radar_daily is scripts/event_radar_watch.sh under bdev on the Owner's Mac, running uncommitted shared-checkout code as Trade role 'bifrost'. It sources .env once and swallows every failure with '|| echo ... will retry'. The cluster's event_radar_cron asset has no input mount and returns idle/sample_fallback every 30 minutes, green. (The Mac placement is a documented choice: no PVC mount, launchd lacks LAN permission.)
- **Measured**: MEASURED. ~/.bifrost-dev/logs/event-radar-watch.log: 158 'sec source failed' lines (1 on 09-28 QueryCanceled; 84 on 10-04; 73 on 10-05) from 10-04 09:15 to 10-05 20:52, all password auth failures for 'bifrost', until a manual restart at 20:54:31. Watermark kept loss at zero because no new filings landed in that window (145 filings written after restart). event_radar_cron, 30 days: 684 idle, 332 sample_fallback, 0 file_ingest.
- **Evidence**:
  - `bifrost-research/scripts/event_radar_watch.sh:16` — `set -a; source .env; set +a`
  - `bifrost-research/scripts/event_radar_watch.sh:25` — `|| echo "$(date '+%F %T') sec source failed (will retry next tick)"`
  - `bifrost-research/src/bifrost_research/orchestration/runners.py:181` — `"mode": "idle",`
- **Impact**: A research feed depends on the laptop being awake (it sleeps at night), a tmux session, credentials never re-read and unreleased code; failure is visible only in a local log. A rotation across a filing night delays events until someone notices, while the green Dagster schedule hides the dependency from Console.
- **Fix**: Move SEC 8-K collection into Dagster as an asset writing the batch directly as analytics_writer and raising on failure. Make the cluster asset raise (not 'idle') when its input mount is absent, or delete it. Interim: watcher re-sources .env each tick and exits non-zero after N consecutive failures so bdev-supervise/bdev status surface it.
- **Ratchet**: Freshness alert: max(computed_at) of features.event_signal_radar_daily older than 2 trading days. Test: run_event_radar raises when input_dir does not exist.
- 审批 不用批 · 代价 M · 风险 med · repos: bifrost-research, bifrost-trade-infra

### TD-101

**P2 · market-data · Doctor slot staleness reads a per-kind freshness row that other slots and zero-row jobs also refresh, so a stopped policed slot still reads fresh**

- **状态**：观察中（到 10-07 03:10 UTC，看五个 policed slot 都有自己的 slot:<slot> 新鲜度行）
- **验收**：`SELECT dimension, last_run_at FROM ops_jobs.ingest_freshness WHERE dimension LIKE 'slot:%'` 有 calendar / corporate / fundamentals-rotate / option-refresh / reference 五行，且 doctor 每条 `stale:*` 的 detail 写着 `by freshness.slot:<slot>`
- **验收结果**：部分 PASS 2026-10-06 market-data 0.79.0（7bf05b8）：slot:option-refresh 已写入（18:20，29,478 行）；其余四个在各自下一次运行时写入
- **Claim**: After any done job the worker upserts ops_jobs.ingest_freshness keyed by dimension only, bumping last_run_at even for 0-row or skipped jobs, with status always 'ok'. The doctor's stale:<slot> check (and Console adherence, ingest_dashboard._evidence_for_fire) reads that row by dimension, and several policed slots share a dimension: reference with ticker-details (ticker_sync), option-refresh with option-contract-expired (option_contract), corporate with corporate-backfill (dividends). If the reference walk stops, stale:reference stays ok while ticker-details runs.
- **Measured**: MEASURED. ingest_freshness.ticker_sync last_run_at 2026-10-06 03:30:26 rows_written=1 (a detail job) while the last universe walk finished 10-05 21:30:27 (600 detail vs 2 universe jobs). option_expiration frozen since 09-06 and stock_daily_unadjusted at 10-02, both 'ok'. All 23 rows status 'ok'.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/freshness.py:85` — `ON CONFLICT (dimension) DO UPDATE SET`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/doctor.py:1709` — `fresh = _freshness(conn)`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/daily.py:2690` — `_add("ticker_sync", {"mode": "universe"}, pri=priority)`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/daily.py:2739` — `_add("ticker_sync", {"mode": "detail", "symbol": sym}, pri=priority)`
- **Impact**: Doctor and Console report reference and option-refresh healthy whether or not they ran; any zero-row run counts as freshness ('firing is not delivery' class), hiding a stopped catalogue walk.
- **Fix**: Key freshness by (dimension, slot) via a slot field in job payloads, or have the doctor check slot adherence from job evidence of the slot's own payload shape. Bump last_run_at only when rows_written > 0 (or add last_nonzero_at). Drop the constant status column or write real statuses.
- **Ratchet**: Unit test derived from the slot→kinds map and contracts.staleness_by_slot(): no policed slot shares a freshness dimension with another slot (explicit allowlist otherwise).
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-102

**P2 · market-data · Plugin's deprecated live max-pain and PCR routes duplicate Research and skip the adjusted-contract filter: different strikes on the same day, and trade-api SEPA PCR reads the contaminated one**

- **状态**：未开始
- **Claim**: The plugin keeps a 'transition' copy of Research's max-pain math plus its own PCR query, both reading raw_market.option_open_interest with no adjusted-root predicate (Research added not_adjusted_contract_sql on 10-01). OI from adjusted roots (O:HON2…, O:MOD1…) is summed into standard chains. trade-api sepa_engine/stock_option_pcr.py calls fetch_pcr_aggregate against this route.
- **Measured**: MEASURED (re-run by verifier) for 2026-10-05: plugin vs Research max pain HON 12-18 210 vs 220, FDX 12-18 310 vs 300, GME 10-16 23 vs 22.5, MOD 10-16 same strike but OI 19,510 vs 9,848. 424 adjusted-root OI rows across 19 underlyings that day. Loki 7 days: /max-pain/compute called only by the probe; /options/analytics/pcr 4 times (trade-api SEPA PCR).
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/analytics.py:613` — `FROM raw_market.option_open_interest`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/pcr.py:65` — `FROM raw_market.option_open_interest`
  - `bifrost-research/src/bifrost_research/engines/adjusted_contracts.py:22` — `return f"substr({column}, 3, length({column}) - 17) !~ '[0-9]$'"`
- **Impact**: Wrong pin strikes for names with corporate-action roots from the plugin route; SEPA option-PCR condition in trade-api computed from contaminated OI; two implementations already disagree.
- **Fix**: Retire /market/analytics/max-pain/compute(+history) and analytics/max_pain_math.py (no real callers); point trade-api fetch_pcr_aggregate at Research's filtered PCR. Until then add the adjusted predicate to every plugin aggregate read of option_open_interest/snapshot/daily.
- **Ratchet**: Plugin test grepping api/*.py: aggregate reads of raw_market.option_(open_interest|snapshot|daily) must contain the adjusted-root predicate or be allowlisted. Register max-pain in the cross-repo duplication metric so a second compute_max_pain_curve fails the scan.
- 审批 改公开接口 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data, bifrost-trade-api

### TD-103

**P2 · flex-ib · The cash parser never stores IB's transactionID, so dedupe falls back to (account, day, amount, type, report_date) and same-amount items overwrite each other**

- **状态**：未开始
- **Claim**: parse_cash_transactions_xml reads transactionID only from a child element; the attribute fallback covers every other field but not this one, so on IB's attribute-style rows flex_transaction_id is always NULL. The UNIQUE key then uses a date-only ts, amount, and a type that maps fees/interest/withholding to 'other'. Two distinct same-day same-amount transactions collapse and the second DO UPDATE overwrites symbol/description/raw_extra. A row with no dateTime gets ts=now(), re-inserted every run.
- **Measured**: MEASURED: flex_transaction_id NULL on 121/121 rows while raw_extra->>'transactionID' is present on all 121. 89 rows typed 'other'. 30 (account, ts, type, report_date) groups hold >1 row, separated only by amount; 6 have coinciding absolute amounts. A collapse leaves no trace, so none observed directly.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/client/flex_client.py:288` — `transaction_id = _text(elem, "transactionID") or _text(elem, "TransactionID")`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/client/flex_client.py:367` — `ts_parsed = datetime.now(timezone.utc)`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1372` — `ON CONFLICT (account_id, ts, amount, type, report_date) DO UPDATE SET`
- **Impact**: Fees, dividends or withholding can be under-counted by exact duplicates, and the surviving row's description can belong to the other transaction, on a money table read by Transfer & Pay and net cash-flow.
- **Fix**: Read transactionID from the attribute too; backfill flex_transaction_id from raw_extra; add a partial UNIQUE index on (account_id, flex_transaction_id) as the conflict target when present (old key only for id-less rows); drop the now() fallback (skip and count dateless rows).
- **Ratchet**: After backfill, NOT NULL/CHECK on flex_transaction_id for flex-sourced rows. Parser test with an attribute-only <CashTransaction> fixture (made-up values): id set, two same-day same-amount rows yield two dicts with different ids.
- 审批 改表 · 代价 M · 风险 med · repos: bifrost-platform-plugin-flex-query, bifrost-trade-core

### TD-104

**P2 · flex-ib · Trade Ops reports all three IB Gateway services 'offline' on PROD: the gateway's health hashes have no updated_at, and the service rows point at retired StatefulSets**

- **状态**：未开始
- **Claim**: trade-api judges liveness from the health hash's updated_at (missing = dead). The gateway writes ws_ib_ingestor/ws_ib_account_agent/ws_ib_operator without updated_at and never has since 07-04. /ops/market-ingest/services shows runtime_status=inactive 'managed@platform-ib-gateway (offline)'; platform satellite maps 'inactive' to ReachFail and the endpoint is a Tier-B probe. The rows also name retired ib-operator/ib-market-gateway/ib-account-agent workloads and systemd units. TD-31's contract covers key names, not field names.
- **Measured**: MEASURED: PROD /api/monitor/ops/market-ingest/services returns inactive/offline for all three, naming deployments that do not exist, while data/ib-gateway has been Running 3d12h with 0 restarts. git log -S shows the gateway never wrote updated_at into these hashes.
- **Evidence**:
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/writer.py:74` — `self._write_hash(IB_INGESTER_HEALTH_KEY, {"env": self._env, "plugin": "ib-gateway", **fields})`
  - `bifrost-trade-api/src/bifrost_api/ops/market_ingest_health_clear.py:138` — `if updated <= 0 or (now - updated) > _HEALTH_RECENT_MAX_S:`
  - `bifrost-trade-api/src/bifrost_api/ops/market_ingest_display.py:66` — `"display_active": "managed@platform-ib-gateway (offline)",`
  - `bifrost-trade-api/src/bifrost_api/ops/market_ingest_config.py:71` — `"systemd_unit": "bifrost-ib-operator.service",`
- **Impact**: An always-red health signal trains people to ignore it; a real gateway outage looks like today's false one, and the market-ingest satellite/Tier-B probe is permanently fail.
- **Fix**: Gateway writes updated_at=time.time() into the three hashes (timestamp + age check per the liveness rule) or sets a TTL of a few write periods. Retarget the Trade service rows to deployment data/ib-gateway and drop retired systemd units.
- **Ratchet**: Extend tests/contracts/redis_ib_keys.json with required hash fields per health key (updated_at, connected/host_connected): plugin test asserts the writer emits them; core and trade-api tests assert readers use only listed fields.
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-platform-plugin, bifrost-trade-api, bifrost-trade-core

### TD-105

**P2 · flex-ib · DEV/STG operator streams accept every op except two (a denylist), so any op added later is open to DEV and STG by default**

- **状态**：未开始
- **Claim**: READ_ONLY_OPS = ALL_OPS minus disconnect_all/reconnect_all, and op_allowed_on_stream accepts READ_ONLY_OPS on the env streams, whose ACL users may XADD. The guard test asserts ALL_OPS - READ_ONLY_OPS == {disconnect_all, reconnect_all}, which still passes after a new op is added, and the env-stream test parametrises over READ_ONLY_OPS itself.
- **Measured**: CODE-READ. ALL_OPS today = fetch, refresh, ping and the two connection ops, so nothing is exposed now.
- **Evidence**:
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/protocol.py:27` — `READ_ONLY_OPS: Tuple[str, ...] = tuple(op for op in ALL_OPS if op not in ("disconnect_all", "reconnect_all"))`
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/operator.py:89` — `return stream not in IB_OPERATOR_ENV_CMD_STREAMS or op in READ_ONLY_OPS`
  - `bifrost-platform-plugin/tests/test_operator_streams.py:27` — `assert set(ALL_OPS) - set(READ_ONLY_OPS) == {"disconnect_all", "reconnect_all"}`
- **Impact**: Under D10, a future execution-adjacent op would be reachable from DEV/STG without anyone choosing it; the TD-21 boundary depends on reviewers remembering to extend a denylist.
- **Fix**: Make READ_ONLY_OPS an explicit literal allowlist and PROD_ONLY_OPS explicit; assert every op in ALL_OPS is in exactly one set.
- **Ratchet**: Test fails when ALL_OPS gains a member not classified in exactly one of READ_ONLY_OPS/PROD_ONLY_OPS; optionally a preflight warning on diffs adding to ALL_OPS.
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-platform-plugin

### TD-106

**P2 · market-data · Nightly trim (now with W3 archive) runs synchronously behind Dagster's 60s HTTP timeout; retries start overlapping trims and the recorded outcome is the retry's**

- **状态**：未开始
- **Claim**: The trim runs inline in POST /market/ingest/enqueue-slot with budgets totalling ~960s (240 job trim, 2x300 snapshot, 2x60 dated, statements up to 900s), while the Dagster client gives up at 60s and RetryPolicy fires a second trim during the first. The archive is safe under overlap (REPEATABLE READ + rowcount check makes the second pass error and roll back, 'never raises'), but Dagster's SUCCESS/FAILURE and logged result describe the retry, and overlapping passes contend on the same rows. From the first night with real rows to archive (~345k intraday option_snapshot rows/session at ~1,550 rows/s ≈ 220s) every first attempt will time out.
- **Measured**: MEASURED. ops_dagster.event_logs: 8 STEP_UP_FOR_RETRY for market_trim_job in 30 days, 2 FAILURE runs (09-09 883s, 09-10 821s). Run f70b9294 (10-01): STEP_START 02:15:07.43, retry 02:16:07.52 (exactly 60s), restart 02:17:10, success in 14s with trimmed: 0. /archive is empty; 10-06 retention_archive 0 rows on all passes.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/plugin_http.py:25` — `timeout: float = 60.0,`
  - `bifrost-research/src/bifrost_research/orchestration/market_slot_schedules.py:32` — `ENQUEUE_RETRY = RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL)`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/ingest.py:225` — `result = enqueue_slot(`
  - `bifrost-platform-plugin-market-data/k8s/base/configmap-schedule.yaml:181` — `snapshot_budget_sec: 300`
- **Impact**: Dagster and Console show trim outcomes from the retry; a FAILURE run (as 09-09/09-10) does not mean the trim failed. Once archiving has real rows, every night runs a timed-out attempt plus duplicate, contended scans. No archived row is lost or duplicated.
- **Fix**: Single-flight async trim: endpoint takes pg_try_advisory_lock, returns 202 'already running' to a second caller, runs in a background task and writes its full result (including archive_runs) to ops_jobs; the Dagster asset polls, or uses a trim-specific client timeout larger than the budget sum.
- **Ratchet**: Plugin test: sum of trim budget keys < exported TRIM_CLIENT_TIMEOUT_SEC; cross-repo parity test that Research's market_trim asset uses it. Test: two concurrent enqueue_slot('trim') produce exactly one trim. Alert on any STEP_UP_FOR_RETRY for market_trim_job.
- 审批 跨仓库发版 · 代价 M · 风险 med · repos: bifrost-platform-plugin-market-data, bifrost-research

### TD-107

**P2 · market-data · Indexes declared for the six financials entity tables never reach a deployed DB (the migration returns early); live differs from fresh install**

- **状态**：未开始
- **Claim**: create_financials_entity_tables declares {table}_symbol_period_date and {table}_period_date_symbol for ratios, short_interest, short_volume, income_statement, balance_sheet and cash_flow, but is reachable only via migrate_stock_financials_split, which returns when stock_financials is already a view (true everywhere). period_date_symbol was written to stop the full scan behind 'who is held on the latest day' that blew a 120s budget; only short_volume has it (added by hand).
- **Measured**: MEASURED pg_indexes on bifrost_golden_source: the six tables have only pkey + filing_date (short_volume also period_date_symbol); 11 declared indexes absent. pg_stat_user_tables: ratios 4,197 seq scans / 278M tuples, balance_sheet 1,451 / 267M, short_volume (4.98 GB) 1,524 / 3.58B.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/schema/wave8_migrations.py:173` — `if relkind == "v":`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/schema/wave8_migrations.py:71` — `CREATE INDEX IF NOT EXISTS {table}_symbol_period_date`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/schema/wave8_migrations.py:84` — `CREATE INDEX IF NOT EXISTS {table}_period_date_symbol`
- **Impact**: Schema in code is not the schema in the DB (same class as option_oi_indexes_never_existed); the 'latest day held' latency fix exists on one of six tables.
- **Fix**: Remove symbol_period_date from code (redundant with PK prefix). Move period_date_symbol into an unconditional idempotent step on the superuser apply_ddl path (tables owned by postgres), built CONCURRENTLY with Owner DDL approval.
- **Ratchet**: CI applies plugin DDL to an empty Postgres and snapshots the index catalog; weekly read-only diff of the snapshot vs live pg_index in GS fails on any declared-but-absent index.
- 审批 改表 · 代价 M · 风险 med · repos: bifrost-platform-plugin-market-data

### TD-109

**P2 · ops-platform · PROD platform-api reads a deployed ops-context.yaml copy last synced 2026-08-24: about 33 spine decisions missing (D-Journal-Stores, D-Ops-Split, D-Wave-10..13)**

- **状态**：未开始
- **Claim**: bifrost-trade-infra/k8s/overlays/platform-prod/config/ops-context.yaml is mounted as ConfigMap bifrost-platform-config by PROD platform-api and platform-workers. It is a hand-kept copy of bifrost-platform config/ops-context.yaml and has not been synced since 0170331 (2026-08-24), so Ops Console on the cluster shows a spine ~6 weeks stale. platform CI's check_spine_catalog.sh does not compare the deployed copies.
- **Measured**: MEASURED by the ratchet-inventory pass: 17 decision ids in the PROD copy vs 50 on platform origin/main (diff 502/538 lines); a quick regex recount here gives 22 vs 55 '- id: D…' lines. Last commit touching the copy: 0170331 2026-08-24. Not adversarially re-verified; whether D10 state read by preflight comes from this copy was not checked (preflight reads the workspace spine).
- **Evidence**:
  - `bifrost-trade-infra/k8s/overlays/platform-prod/config/ops-context.yaml:41` — `headline: "TIBM W3 signed — STG read-path complete (D10 BLOCKED)"`
- **Impact**: Owner and agents reading the cluster Console see a stale decision set (missing D-Journal-Stores and later program decisions), undermining 'code → Console Governance catalogs → spine' priority.
- **Fix**: Generate the ConfigMap at build/deliver time from the platform repo's config/ops-context.yaml (delete the infra copy), or add a sync step plus CI parity check.
- **Ratchet**: CI check (ci-infra or ci-platform): deployed copies' decision-id set equals platform main's; better, the copy no longer exists.
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-110

**P3 · research-data · Stored IV features solve Black-Scholes at r=0 while the backtester uses treasury rates from two separate readers; further BS copies in gex and opex**

- **状态**：观察中（到 10-07 批处理，看新写入的 vendor_snapshot mid 按当日国债利率算）
- **验收**：`rate` 在所有定价函数里是必填关键字；`risk_free_rate(conn, 2026-10-02)` = 0.0404；今晚之后新写入行的 `mid_price` 等于按当日国债利率的 `bs_price`
- **下一步**：历史 IV 特征未重述（r=0 → 国债利率：call IV 中位 −0.74、put +0.94 vol pts，近 ATM call-put 差 2.37 → 0.20）；canonical_pnl 标记价仍按 r=0，是否重述 `mart_canonical_pnl_daily` 由 Owner 决定
- **Claim**: iv_solver.solve_iv/bs_price/bs_delta default rate=0.0, and iv_solver.py:346/350/520/533, atm_iv.py:389, earnings_moves.py:54 and canonical_pnl omit rate. backtest/event_query._risk_free_rate and sim/chain.py each read raw_market.treasury_yield on their own; gex/exposure.approx_bs_gamma and opex_cycle/vanna_charm._norm_cdf are more BS copies. Features and backtests compute different IV/delta for the same contract. TD-42 fixed this class only in Trade.
- **Measured**: Inconclusive. Most stored IV since 08-05 is vendor_snapshot (4.26M rows); 19,435 Brent 'ok' rows (06-24..09-25) show median near-ATM put-call gap -2.3/-3.0 vol pts vs vendor -1.5/-2.3, partly carry/dividends. Copy drift CODE-READ; _risk_free_rate's own docstring admits research BS ran at r=0.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/atm_iv.py:389` — `iv, _status = solve_iv(spot_f, strike_f, max((exp - trade_date).days, 1) / 365.0, mid, right)`
  - `bifrost-research/src/bifrost_research/engines/backtest/event_query.py:685` — `def _risk_free_rate(conn: Any, on_or_before: date, cache: dict[date, float] | None = None) -> float:`
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:81` — `def approx_bs_gamma(`
- **Impact**: Matters where the Brent fallback fills IV30 and where backtest-selected strikes are compared with feature deltas.
- **Fix**: One research pricing module (bs_price/delta/gamma/vanna/charm, solve_iv) with keyword-required rate, plus one cached treasury reader; pass the rate in iv_solver and atm_iv.
- **Ratchet**: code-health grep metric: `def .*norm_cdf|def .*bs_(price|delta|gamma)|math.erf` outside the pricing module, baseline 0 after merge; rate keyword-required so a 0.0 default cannot return.
- 审批 不用批 · 代价 M · 风险 med · repos: bifrost-research

### TD-111

**P3 · research-data · dbt: the pass_count range generic test sits in the singular folder (errors when selected, never applied); key intermediates lack grain tests; nothing ties eval_date to the session**

- **状态**：观察中（到 10-07 夜间 dbt build，看新测试全部 pass）
- **验收**：10-07 build 后 `ops_dbt.dbt_run_results` 里 `assert_pass_count_range%`、`dbt_utils_unique_combination%`、`sepa_session_is_newest%` 全部 pass
- **Claim**: tests/assert_pass_count_range.sql defines a {% test %} block under the singular-test path; it errors whenever selected and no yml applies it, so pass_count has only warn-level anomaly checks. int_stock_daily_enriched (incremental on symbol, trade_date) and int_stock_crs have only not_null tests. mart_sepa_tier_options is absent from yml. No test checks eval_date/trade_date against the session, which let TD-87 through.
- **Measured**: MEASURED. ops_dbt.dbt_run_results: 14 error rows for assert_pass_count_range (08-21..09-28 manual full selections), never pass. Nightly builds run 82 tests, all pass, none on pass_count range or session. Grain clean today (1,656,685 = distinct; 382,026 = distinct).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/dbt/tests/assert_pass_count_range.sql:13` — `{% test assert_pass_count_range(model, column_name, min_value, max_value) %}`
  - `bifrost-research/src/bifrost_research/dbt/models/intermediate/_intermediate__models.yml:24` — `- name: int_stock_daily_enriched`
- **Impact**: A broken incremental merge or a SEPA date shift passes dbt build green.
- **Fix**: Move the macro to tests/generic/ and apply to pass_count (0-8, 0-11); add dbt_utils.unique_combination_of_columns on (symbol, trade_date) for both intermediates; add an expression/relationship test that eval_date/trade_date is a trading day and <= max(bar_date); document tier_options.
- **Ratchet**: CI check: `dbt ls --resource-type model` vs yml; fail on any model without a grain test.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-112

**P3 · research-data · option_surface_iv_daily upserts per (symbol, trade_date, expiry) and never deletes, so expiries a re-walk dropped keep their old smile**

- **状态**：观察中（到 10-07 批处理；存量清理待 Owner）
- **验收**：`trade_date > '2026-10-06'` 的 (symbol, trade_date) 组里没有比本组最新拟合早 1 小时以上的行
- **下一步**：存量 122 行（98 组）的清理脚本 `bifrost-research/scripts/oneoff/2026-10-06-td112-surface-stale-expiries.sql`（计数不符不提交）会改写 Golden Source，由 Owner 跑
- **Claim**: engines/volatility/surface.py writes with batch_upsert on (symbol, trade_date, expiry) and has no DELETE; expiries a later re-walk no longer produces keep the old fit beside the new one. Same class already fixed for signal_hit, gex, flow, pcr and max_pain.
- **Measured**: MEASURED. 122 rows in 98 of 12,635 (symbol, trade_date) groups are >1h older than their group's newest fit, up to 6d 21h; span 2026-07-14..09-03; only 10 are 0DTE.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/surface.py:588` — `conflict_keys=("symbol", "trade_date", "expiry"),`
- **Impact**: Small but wrong: surface reads for those days mix two fits; class stays open for any expiry-filter change.
- **Fix**: Delete-then-insert per (symbol, trade_date) in one transaction; one-off cleanup of the 122 rows (Research-owned).
- **Ratchet**: code-health metric listing batch_upsert targets whose conflict key is wider than (symbol, trade_date) with no DELETE in the module; fails on a new one without an allowlist comment.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-114

**P3 · flex-ib · raw_broker.commissions mixes two sign conventions: Flex writes cost as negative, the TWS/gateway path writes it as positive**

- **状态**：在做（三个环境已上 core 0.50.0；等 Owner 跑 6 行存量改写，预演 10-06 18:0x 仍为 6、Flex 符号不符 0）
- **验收**：GS 上跑 `db-steps.d/sql/2026-10-06-td114-commission-sign-dryrun.sql`：三个环境都上 0.50.0 且改写后需改写行数为 0（现在 6）
- **Claim**: Flex stores ibCommission as IB sends it (negative charge, positive rebate); the TWS commissionReport path writes IB API's positive cost into the same column and key. Flex re-imports overwrite to the Flex sign; TWS-only fills keep the opposite sign. No reader normalises (accounts_helpers.py:402-404 adds commission into period totals).
- **Measured**: MEASURED. Flex-backed: 435 negative, 15 positive (all rebates matching net_cash - proceeds to 4 dp), 32 NULL. TWS-only: 4 positive (~1.04-1.05), 0 negative, 33 NULL. 12 orphan commission rows. Reading TWS positives as costs relies on IB API docs.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/client/flex_client.py:551` — `commission = _f("ibCommission")`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1053` — `INSERT INTO {GOLDEN_COMMISSIONS} (exec_id, commission, currency, realized_pnl, yield_, yield_redemption_date)`
- **Impact**: Small amounts today, but per-trade cost and PnL reads including TWS-only fills get the cost sign backwards.
- **Fix**: Normalise at write time (keep Flex sign, negate TWS commissionReport value), backfill TWS-only rows, decide on the 12 orphans.
- **Ratchet**: Data-gaps/doctor SQL check: no exec_id whose commission sign disagrees with sign(net_cash - proceeds - taxes) on its Flex row; unit test on the TWS writer's sign.
- 审批 不用批 · 代价 S · 风险 med · repos: bifrost-trade-core

### TD-117

**P3 · flex-ib · 'Latest Flex date in DB' after an import is one run behind: read through FDW in the same transaction as the pre-import read**

- **状态**：观察中（到 10-07 06:30 ET 定时运行，看 after = data_to）
- **验收**：`select result->'result'->>'data_to', result->'result'->>'last_flex_date_after' from ops_jobs.job_flex_ingest where kind='flex-trades' order by id desc limit 1` 两值相等
- **Claim**: fetch_flex_trades_and_upsert_executions reads stats_before and stats_after on one Trade-DB connection with no commit between; brokerage.executions is a postgres_fdw view whose remote snapshot lasts the local transaction, so stats_after cannot see rows just written. The value reaches the UI.
- **Measured**: MEASURED in ops_jobs.job_flex_ingest: job 183 data_to 10-02 but after = 09-30; job 178 09-30 vs 09-28; job 172 09-28 vs 09-22. Each 'after' equals the previous run's data.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/trades.py:318` — `stats_after = get_flex_executions_stats(conn)`
  - `bifrost-trade-frontend/src/components/accounts/ExecutionImport.tsx:62` — `parts.push(`Latest Flex date in DB: ${r.last_flex_date_after}.`)`
- **Impact**: Operator is told the DB stops earlier than it does, inviting re-runs that burn IB's 1018 throttle.
- **Fix**: Read stats from GS raw_broker.executions_raw_flex on a fresh connection, or commit before stats_after.
- **Ratchet**: Integration test on real Postgres: after write_account_executions_to_db, last_flex_date_after = max(trade_date) written.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-flex-query

### TD-118

**P3 · market-data · option-refresh re-enumerates names with no listed options every run; its 7-day 'finished' lookback reads a table kept 48h**

- **状态**：观察中（到 10-07 00:20 UTC 那一轮 option-refresh）
- **验收**：10-07 00:15–01:00 UTC 之间 live `option_contract` 任务里 rows_written = 0 的个数为 0（改前每轮 17–20 个）
- **验收结果**：前提已到位 2026-10-06：18:20 记下 20 个 no-listed-options 判定（market-data 0.79.0）
- **Claim**: stalest_underlyings sorts never-enumerated names first, so names with no listed options are re-fetched at the head of every six-hourly batch forever. The 7-day finished-jobs guard feeds only the fresh ramp list (not the rotation) and is bounded by TRIM_KEEP_HOURS=48.
- **Measured**: MEASURED: 136 of 1,240 option_contract jobs in 48h wrote 0 rows; 17 names (ATLCL, ESQ, PLPC, NVR, NPK…) enqueued every run, always 0 rows.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/daily.py:2545` — `# Never enumerated sorts before any timestamp.`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/daily.py:638` — `AND created_at >= now() - interval '7 days'`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/enqueue.py:165` — `TRIM_KEEP_HOURS = 48.0`
- **Impact**: ~12% of each 144-name rotation wasted on an uncapped plan; stated cycle time overstated; the 7-day comment is false.
- **Fix**: On zero contracts record a symbol_source_void ('no listed options', retry-after date) and exclude those names from fresh and stalest lists.
- **Ratchet**: Unit test: a name with a recent zero-row void is excluded from both lists; lint that no job_ingest lookback interval exceeds TRIM_KEEP_HOURS.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-119

**P3 · market-data · Schema-migrate Job and worker Deployments are applied in one `kubectl apply -k` with no ordering; a table-adding release fails the jobs that land in the DDL window**

- **状态**：未开始
- **Claim**: k8s/base lists job-wave8-schema-migrate next to the Deployments, and `make deploy` applies base before waiting on the Job. Ordering lives only in a skill procedure. Jobs in the 30-60s DDL window fail loudly (failed:<kind>, doctor-retryable), not silently.
- **Measured**: CODE-READ plus documented 09-24 incident (56 sec_filings_symbol jobs died during a 40s gap). Live Deployments have no initContainers.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/k8s/base/kustomization.yaml:23` — `- job-wave8-schema-migrate.yaml`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/db/schema_guard.py:24` — `def assert_no_legacy_schemas(conn: Any) -> None:`
- **Impact**: Operator toil and delayed slot data on each table-adding release; depends on a manual three-step order.
- **Fix**: Move the Job into its own kustomization; `make deploy` deletes the old Job, applies the migration, waits for complete, then applies base. A schema_version gate in workers is optional hardening.
- **Ratchet**: Test that `kustomize build k8s/base` contains no kind: Job and that the deploy target applies the migration kustomization and waits before base.
- 审批 改表 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-120

**P3 · research-control · Dagster Deployments are applied by hand outside Argo; a second, unmounted dagster_instance.yaml lacks the run_monitoring that catches zombie runs**

- **状态**：未开始
- **Claim**: Argo app bifrost-research excludes orchestration/**, and pipeline-build-research-dagster only builds; nothing checks the -dagster tag matches the release pin. k8s/orchestration/dagster_instance.yaml is an unreferenced second instance config missing the run_monitoring block added after trading_day sat STARTED 20.5h on 09-08.
- **Measured**: MEASURED. Argo exclude '{orchestration/**,dbt/Dockerfile,**/_archived/**,_archived/**}'. kubectl diff of dagster.yaml rc=0 today; daemon and webserver run 0.175.0-dagster = pin. dagster_instance.yaml lacks the 15-line run_monitoring block and has no references.
- **Evidence**:
  - `bifrost-research/k8s/orchestration/dagster_instance.yaml:1` — `# Mounted as $DAGSTER_HOME/dagster.yaml — Postgres instance storage on Golden Source.`
  - `bifrost-research/k8s/orchestration/dagster.yaml:50` — `run_monitoring:`
  - `bifrost-trade-infra/k8s/cicd/tekton/pipeline-deliver-research.yaml:113` — `# base = Research API + CronJob engines. The Dagster image is a`
- **Impact**: Drift risk only today, but API and daemon on different code versions would write features with a different engine than the API reads; the duplicate file can undo a hard-won fix.
- **Fix**: Delete dagster_instance.yaml. Add a verify step asserting dagster-daemon image == '<pin>-dagster', or bring orchestration/** under Argo with image ignoreDifferences.
- **Ratchet**: verify-research assertion on the daemon tag (fails deliver); test that k8s/ holds exactly one dagster instance config.
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-infra

### TD-121

**P3 · research-control · Research pods read bifrost-research-secrets once at start (optional: true); the OpenAI key rotation helper restarts only research-api**

- **状态**：未开始
- **Claim**: research-api, research-mcp, dagster-daemon and dagster-webserver envFrom bifrost-research-secrets with optional: true. sync_openai_secret.sh patches the key and restarts only deployment/research-api, so the daemon (scheduled LLM agents) and MCP keep the old key until the next release. No rotation helper exists for analytics_writer. (DB rotation of 'bifrost' does not touch these pods; infra bifrost-password-rotate.sh already derives holder Deployments.)
- **Measured**: CODE-READ for cluster pods; secret key names checked live (OPENAI_API_KEY, DEEPSEEK_API_KEY, ANALYTICS_PG_PASSWORD present).
- **Evidence**:
  - `bifrost-research/scripts/sync_openai_secret.sh:41` — `kubectl -n "$NS" rollout restart deployment/research-api`
  - `bifrost-research/k8s/orchestration/dagster.yaml:98` — `- secretRef:`
- **Impact**: After an OpenAI/DeepSeek key rotation, scheduled agents and Copilot via MCP fail until a manual restart; optional: true lets pods start without credentials instead of failing fast.
- **Fix**: Restart every Deployment in namespace research that mounts the secret (derive the list as infra holder_deployments() does); add a checksum/secret annotation or reloader; drop optional: true for required keys.
- **Ratchet**: Lint over k8s/: every Deployment envFrom-ing bifrost-research-secrets carries the checksum annotation and none mark required keys optional; grep check that rotation helpers never hard-code one deployment.
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-research

### TD-122

**P3 · flex-ib · The IB Gateway image is built on the Mac and imported to nodes with ctr under a reused tag: no registry, no digest, no recorded source SHA**

- **状态**：未开始
- **Claim**: deployment.yaml runs bifrost-platform-plugin-ib-gateway:0.3.0 with IfNotPresent; the tag exists only in each node's containerd and the repo has no build pipeline (unlike flex-query). Different code can run under the same version and nothing reports which commit is live.
- **Measured**: MEASURED: live pod on ubt-k3s-04 runs a bare tag with local imageID sha256:cd51d656…; flex-query uses 192.168.10.73:30500/bifrost-flex-query:0.9.0; no k8s/cicd in the repo.
- **Evidence**:
  - `bifrost-platform-plugin/k8s/ib-gateway/base/deployment.yaml:22` — `image: bifrost-platform-plugin-ib-gateway:0.3.0`
  - `bifrost-platform-plugin/k8s/ib-gateway/base/deployment.yaml:23` — `imagePullPolicy: IfNotPresent`
- **Impact**: The process holding both TWS connections and redis-ib writes is the least reproducible deploy; rollback and audit depend on one laptop.
- **Fix**: Tekton build to the in-cluster registry (copy flex-query's pipeline-build.yaml), pin by digest, expose git SHA in the health hash.
- **Ratchet**: code-health metric: manifests whose image lacks registry host or digest = 0 for plugin repos; preflight warning on `ctr images import`.
- 审批 跨仓库发版 · 代价 M · 风险 med · repos: bifrost-platform-plugin, bifrost-trade-infra

### TD-123

**P3 · research-control · About 19 deployed research-api routes have no caller in frontend, platform, trade-api or MCP, including manual POST triggers that run engine code outside Dagster**

- **状态**：未开始
- **Claim**: Uncalled GETs: /analytics/sepa/technical-filter, /analytics/sepa/screening-ranked, /research/sepa/candidates, /research/volatility/surface, /research/forecast/{hourly,settlement,backtest}, /research/backtest/regime-stats, /research/canonical-pnl/coverage. Uncalled POSTs: forecast/terrain/compute, forecast/sessions/compute, forecast/settle, event-radar/run, events/ingest, backtest/aggregate, journal/memory/distill, agents/digest/run, agents/weekly-policy/run, hypothesis/{id}/retire. Most POSTs run engine code synchronously in the API pod with no run record or failure alert, and distill/digest can race their scheduled runs.
- **Measured**: MEASURED: live /openapi.json (208 path×methods) vs git grep on origin/main of frontend, platform, trade-api, infra and research mcp/copilot, with manual re-check. Callers outside these repos (Hermes, curl) not checked.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/api/wave4.py:1191` — `@router.post("/forecast/settle", dependencies=[Depends(require_owner)])`
  - `bifrost-research/src/bifrost_research/api/agents.py:80` — `@agents_router.post("/digest/run", dependencies=[Depends(require_owner)])`
  - `bifrost-research/src/bifrost_research/api/journal.py:327` — `@router.post("/memory/distill")`
  - `bifrost-research/src/bifrost_research/api/sepa.py:153` — `@router.get("/screening-ranked")`
- **Impact**: Extra surface to secure and test after the 0.163-0.168 auth work; a second, unobserved write path beside Dagster.
- **Fix**: Delete uncalled read routes and calculator POSTs; move agent/distill triggers to 'launch the Dagster job' via GraphQL; follow trade-api's TD-40 retirement pattern (test_retired_routes.py).
- **Ratchet**: Port the TD-40 route-caller check: CI diffs app.routes against a committed callers manifest; test that no research-api route imports engines.*.entry run functions directly.
- 审批 改公开接口 · 代价 M · 风险 low · repos: bifrost-research

### TD-124

**P3 · research-control · 39 permanently suspended CronJobs (25 research, 14 market-data, plus an orphan pinned to 0.10.0) are still deployed and re-pinned every release; research ones carry a stale 26-name watchlist and the verify script contradicts the one active CronJob**

- **状态**：未开始
- **Claim**: Since the Dagster migration all engine CronJobs are suspend: true but still applied (research by Argo auto-sync; market-data via k8s/base), and each release rewrites their image tags. Research manifests hardcode RESEARCH_WATCHLIST to 26 names including SATS (renamed ECHO); unsuspending one would double a writer on the wrong universe. verify_husbandry_schedulers.sh requires research-harness suspended while it is suspend: false, so the landing check can only fail. market-data k8s/cronjob-option-backfill.yaml sits outside kustomization at 0.10.0; each slot cron is written in three places.
- **Measured**: MEASURED. research: 25 CronJobs SUSPEND=True (17 manifest files, 12 set RESEARCH_WATCHLIST), harness active; all pinned 0.175.0. plugin-market-data: 14 CronJobs SUSPEND=True, last scheduled 08-29/30, image 0.77.0. Market-data skill says 'Do not unsuspend'.
- **Evidence**:
  - `bifrost-research/k8s/engines/cronjob-scan.yaml:67` — `value: "SPY,QQQ,IWM,SPX,NVDA,AAPL,META,GOOG,AMZN,MSFT,TSLA,PLTR,MU,MRVL,ANET,CAVA,CBRS,DAVE,DDOG,ECHO,HIMS,NBIS,NNE,RKLB,SATS,SPCX"`
  - `bifrost-research/k8s/engines/cronjob-harness.yaml:17` — `suspend: false`
  - `bifrost-research/scripts/verify_husbandry_schedulers.sh:67` — `research-harness \`
  - `bifrost-platform-plugin-market-data/k8s/base/cronjob-daily.yaml:25` — `# last three forever: these have all been suspended since 2026-08-29`
- **Impact**: Release churn and review noise; a one-line footgun that doubles writers; the documented landing check is permanently red so nobody runs it.
- **Fix**: Delete suspended CronJob manifests in both repos (keep research-harness or move it into Dagster) and the orphan backfill CronJob; flip the verify script's CronJob block to 'must not exist'. Deletes in Argo-pruned paths need Owner sign-off.
- **Ratchet**: CI check: `kustomize build` contains no kind: CronJob unless allowlisted with a reason (research baseline 26 → 1, market-data 14 → 0); test that no k8s manifest sets RESEARCH_WATCHLIST.
- 审批 删除（要你批） · 代价 S · 风险 low · repos: bifrost-research, bifrost-platform-plugin-market-data

### TD-125

**P3 · flex-ib · Retired IB topology still referenced: TIBM-era verify scripts at the top of scripts/, flex_ops compat SQL for a schema that no longer exists**

- **状态**：未开始
- **Claim**: Five plugin scripts reference the retired ib-operator/ib-market-gateway/ib-account-agent StatefulSets, plus per-wave verify-trade-ib-w{1,2,3}-* scripts, although TIBM rollout scripts already moved to scripts/archive. The flex repo keeps golden_source_flex_ops_compat_views.sql and drop_trade_flex_ops_legacy.sql for a flex_ops schema that does not exist. Current-gateway verify scripts (verify-ib-gateway*.sh, verify-redis-ib.sh) are live.
- **Measured**: MEASURED: no sts/deploy named ib-operator/ib-market-gateway/ib-account-agent; pg_namespace has no flex_ops.
- **Evidence**:
  - `bifrost-platform-plugin/scripts/verify-trade-cutover.sh:17` — `LEGACY_STS=(ib-market-gateway ib-account-agent ib-operator)`
- **Impact**: Readers and agents treat these as live procedures.
- **Fix**: Move TIBM-wave and cutover verify scripts with Makefile targets into scripts/archive; delete the two flex_ops SQL files and their CLAUDE.md mention on Owner approval; trade-api service rows are retargeted under TD-104.
- **Ratchet**: Per-repo CI grep ratchet: references to ib-operator/ib-market-gateway/ib-account-agent outside scripts/archive, falling baseline.
- 审批 删除（要你批） · 代价 S · 风险 low · repos: bifrost-platform-plugin, bifrost-platform-plugin-flex-query, bifrost-trade-api

### TD-128

**P3 · research-data · Pine signal rows mix adjustment bases: nightly runs rewrite only the last ~10 sessions on today's adjusted bars, older rows stay on the basis of their last full rebuild**

- **状态**：未开始（归 Pine 线程）
- **Claim**: The Pine build runs scripts on raw_market.stock_daily adjusted closes. Nightly (incremental) runs replace only the last ~10 sessions; a split or large dividend re-adjusts the whole history, so after one the older rows of that name were computed on a different price basis than the new ones until a script's next full rebuild (which happens only when its source changes or on a manual --full).
- **Measured**: Design reading (thread B, 2026-10-06); last full rebuild 2026-10-06 04:17–04:25 UTC (8 scripts, about 7 minutes with CHUNK 25).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/pine/build.py:210` — `since = None if rebuild else end - timedelta(...)`
  - `bifrost-research/src/bifrost_research/engines/pine/build.py:226` — `_write(..., replace_from=since, ...)`
- **Impact**: Signal dates on names with corporate actions can disagree with what the script would print today; signal-stats and backtests read the stale ones.
- **Fix**: A weekly full rebuild (weekend Dagster schedule, CHUNK 25 because the runner blocks /health on 100-name full-history batches), or a nightly per-symbol full rebuild of names with a split in the last N days.
- **Ratchet**: Dagster metadata records each script's last full rebuild; an alert when it is older than 8 days.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-129

**P3 · research-data · The event backtest picks option legs from option_daily only; since mid-August 2026 it keeps ~10 strikes a side, so a target delta silently lands on the nearest strike that is left**

- **状态**：未开始（归 Pine 线程）
- **Claim**: `_pick_option` reads candidate contracts from raw_market.option_daily. Since mid-August 2026 option_daily keeps about ten strikes either side of spot per expiry, so a 20–30 delta leg 30–45 days out is usually missing and the nearest remaining strike (often 35–40 delta) is priced instead, with no skip or flag. The simulator (0.175.0) and the suggestion ledger (0.174.1) fill from the 16:00 option_snapshot and skip off-target picks; the event backtest does not.
- **Measured**: Thread B 2026-10-06 on the simulator path: without the fill a 20-delta SPY put picked −0.35, QQQ −0.38 (2026-08-17..10-02); with it −0.20 ± 0.003. The event backtest path shares the option_daily source.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/backtest/event_query.py:781` — `_pick_option`
  - `bifrost-research/src/bifrost_research/engines/backtest/event_query.py:823` — `FROM raw_market.option_daily`
- **Impact**: Event backtests of delta-targeted structures after mid-August run a different trade than the template names.
- **Fix**: Read the snapshot day bars where option_daily lacks the contract (walk.snapshot_day_bars) and skip legs further than 0.05 from the target delta, counting the skip.
- **Ratchet**: A test with an option_daily chain thinned to ATM ±10 strikes that asserts either the target delta within 0.05 or an off-target skip.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-130

**P1 · ops-control · ops-autopilot acts on the shared cluster's data layer from the Owner's laptop (local bdev platform-api, role all); the in-cluster STG/PROD autopilots idle on an empty checklist, and each of the three keeps its own throttle**

- **状态**：未开始（要你批）。依赖：本机这份先不停（Owner 2026-10-06）——停了就没有任何一份 autopilot 在动手；等 PROD 接上真实清单之后再停本机。
- **Claim**: Three platform-api processes run the patrol autopilot loop against the one k3s cluster: platform-workers in bifrost-platform-stg and bifrost-platform-prod (PLATFORM_ROLE=workers) and the Owner's local bdev platform-api, where PLATFORM_ROLE is unset and therefore `all`. Only the local one reads the real checklist; the in-cluster ones idle on an empty checklist (Owner 2026-09-22: leave as is). So the actions on data/minio and the backups came from a dev laptop: repair_cnpg_wal_store every 15 minutes from 10-05 19:30 to 10-06 02:00 (all failed), a rollout restart of deploy/minio plus an on-demand Backup at 10-06 04:45, another restart at 05:15. The "same target not twice in 24h" throttle is kept per process.
- **Measured**: MEASURED 2026-10-06. Audit log of the local platform-api (MCP bifrost-platform → http://127.0.0.1:8780, get_audit_log) lists those actions; `curl 127.0.0.1:8780/health` → role all, background_loops true; kubectl: platform-workers 1 replica with PLATFORM_ROLE=workers in both namespaces. Again at 2026-10-06 16:15:07 UTC (12:15 New York, market hours): the local autopilot ran repair_cnpg_wal_store, deleted the failed Backup bifrost-postgres-ondemand-20261006-044532 and started bifrost-postgres-ondemand-20261006-161507, a full base backup.
- **Evidence**:
  - `bifrost-platform/api/internal/config/role.go:33` — `PLATFORM_ROLE`; unset or unknown means all
  - `bifrost-platform/api/internal/server/server.go` — `role.RunsWorkers()` gates the patrol, ibgateway auto-repair and data-clone loops
  - `bifrost-platform/config/patrol-skills/ops-autopilot.yaml` — every 15 minutes; tools include rollout_restart_deployment and trigger_cnpg_backup
- **Impact**: The process that restarts production backup infrastructure and starts backups is the least controlled one: it sleeps with the laptop, runs whatever is in the shared checkout and restarts on every bdev change. Several copies can each restart or back up the same target.
- **Fix**: In this order, so that exactly one autopilot acts at every moment: (1) dry look at what the PROD platform-workers autopilot would trigger with the real checklist; (2) give it the real checklist and confirm in the PROD audit log that it acts; (3) only then `PLATFORM_ROLE=api` in bifrost-platform/.env on the Owner's Mac and `bdev restart platform-api`; (4) STG observe only (a switch such as `PATROL_AUTOPILOT=off`, or report-only). Stopping the local one first leaves zero acting autopilots, a failure nobody notices.
- **Ratchet**: Outside the cluster, background loops start only with an explicit opt-in (for example `PLATFORM_ALLOW_LOCAL_LOOPS=1`); a test on the role default.
- **验收**: `curl -s 127.0.0.1:8780/health` shows background_loops false; the PROD audit log shows the autopilot's actions and the local one shows none.
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-platform

### TD-131

**P2 · ops-control · repair_cnpg_wal_store deletes failed Backup CRs, erasing the record of failed backups**

- **状态**：未开始（要你批）
- **Claim**: RepairPostgresWalStore calls deleteStuckBackupCRs, which deletes every bifrost-postgres-* Backup in phase failed or walArchivingFailing before it starts an on-demand Backup. CloudNativePG itself only deletes completed backups that are no longer in the object-store catalog. The failed 10-03 and 10-04 03:00 backups and the failed 10-03 manual one were gone from the cluster within hours; only Prometheus and a MinIO trace kept the evidence. On 10-06 16:15 UTC it deleted bifrost-postgres-ondemand-20261006-044532 (stopped on the Owner's request during the MinIO cutover) the same way. Independent of TD-130: can be fixed while the local autopilot is still the acting one.
- **Measured**: MEASURED 2026-10-06: the Backup CRs of those three runs are absent; CNPG v1.27.4 `pkg/management/postgres/backup.go` deleteBackupsNotInCatalog skips every phase but completed.
- **Evidence**:
  - `bifrost-platform/api/internal/cluster/postgres_wal_repair.go` — `pickStuckBackupNames`, `deleteStuckBackupCRs`
- **Impact**: Failure history for postmortems exists only in metrics; whoever looks at the cluster after the repair ran sees no failed backup.
- **Fix**: Stop deleting failed Backups; a separate sweep removes failed Backup CRs older than 30 days.
- **Ratchet**: A test that RepairPostgresWalStore issues no delete for a failed Backup.
- **验收**: After a failed backup and a repair run, `kubectl -n data get backups` still lists the failed one.
- 审批 要你批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-132

**P2 · ops-control · bifrost-platform a332cff (checks and WAL repair aware of the NAS MinIO) is on main but not released to STG/PROD**

- **状态**：在做（下一步：Owner 批发布，STG 后 PROD）
- **Claim**: Since the MinIO cutover (infra 1ee0ac2) the in-cluster Console reports "MinIO backup … scaled to zero" and "WAL archive … MinIO not ready" (degraded) for a healthy store, and the in-cluster repair tool would rollout-restart the 0-replica deploy/minio. a332cff reads Service data/minio, checks the external MinIO's /minio/health/cluster and never touches deploy/minio for an external MinIO.
- **Measured**: Local platform-api against the cluster after a332cff: MinIO backup ok "MinIO @ 192.168.10.20:9000 healthy", WAL archive ok (both degraded before). Last STG and PROD builds were a6794c4, bifrost-ui unchanged since: the release ships only a332cff.
- **Evidence**:
  - `bifrost-platform/api/internal/cluster/minio_backend.go` — `resolveMinioBackend`
  - `bifrost-platform/api/internal/cluster/postgres_wal_repair.go` — external branch of `RepairPostgresWalStore`
- **Fix**: Run bifrost-deliver-platform, then bifrost-deliver-platform-prod.
- **Ratchet**: `minio_backend_test.go` TestRepairWithUnhealthyExternalMinioLeavesDeploymentAlone (fails on the old code).
- **验收**: STG and PROD `GET /api/v1/cluster/postgres` → minio.id minio-backup-external, reachability ok; the clone-platform result commit is a332cff or later.
- 审批 发布（要你批） · 代价 S · 风险 low · repos: bifrost-platform

### TD-133

**P3 · data · Leftovers of the in-cluster MinIO after the move to the NAS (deploy/minio at 0, its PVC/PV, an empty EndpointSlice, the backup-retry CronJob)**

- **状态**：观察中（到 10-13，看每天 03:00 的备份都 completed、BifrostMinIONas* 没有告警）
- **Claim**: Kept for a week as the rollback path: deploy/minio (replicas 0 on purpose), PVC data/minio-data and PV pvc-871b4689-… (nfs-hot; its directory is the live data directory of the NAS MinIO), the controller's empty EndpointSlice minio-wv44q, the CronJob data/backup-retry (only needed while backups failed on NFS), and the data directory still under the provisioner's /volume1/k3s-hot path.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/minio/deployment.yaml` — replicas 0
  - `bifrost-trade-infra/k8s/data/backup-retry.yaml`
  - `bifrost-trade-infra/k8s/data/minio/nas/README.md` — "After a week of good backups"
- **Fix**: After 10-13: delete deploy/minio and backup-retry; delete the PVC and PV objects only (reclaim policy Retain, archiveOnDelete false: the directory stays — check again first); move the directory to its own share by a rename inside /volume1 and update the compose volume path (Owner, sudo); delete minio-wv44q.
- **Ratchet**: None new: BifrostMinIONasDown / DriveOffline / SpaceLow cover the store itself.
- **验收**: `kubectl -n data get deploy,pvc,cronjob | grep -E 'minio|backup-retry'` is empty; the NAS MinIO lists 272+ GiB and the next 03:00 backup completes.
- 审批 要你批 · 代价 S · 风险 med · repos: bifrost-trade-infra

### TD-134

**P2 · data · WAL is ~19.5 GiB/day (4.2 GiB compressed) because checkpoints run every 5 minutes without wal_compression**

- **状态**：未开始（要你批）
- **Claim**: bifrost-postgres runs with checkpoint_timeout 300 s, max_wal_size 1024 MB and wal_compression off. Each checkpoint makes the next change to every page write a full page image, so WAL is dominated by full pages. Archived WAL is 129 of the 272 GiB backup bucket.
- **Measured**: MEASURED 2026-10-06: cnpg_collector_wal_bytes 7-day average 19.48 GiB/day; 1,986 timed checkpoints in 7 days; full-page-image byte share upper bound 0.98 (8 KiB per FPI).
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/cluster.yaml` — spec.postgresql.parameters (no checkpoint or wal_compression settings)
- **Impact**: Backup storage and the WAL replay after a restore grow with it; the 30-day backup bucket is about 300 GiB and rising.
- **Fix**: checkpoint_timeout 15min, max_wal_size 4GB, wal_compression lz4 (reload, no restart); measure WAL per day for a week. Cost: crash recovery replays more WAL (about a minute instead of seconds).
- **Ratchet**: An alert when WAL per day goes above the new baseline by a margin.
- **验收**: A week after the change, cnpg_collector_wal_bytes per day is at most half of 19.48 GiB.
- 审批 要你批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-135

**P3 · data · Native barmanObjectStore backups are removed in CloudNativePG 1.30; the Barman Cloud Plugin that replaces them needs cert-manager, which the cluster does not have**

- **状态**：未开始（要你批：新依赖）
- **Claim**: Applying the Cluster on 10-06 printed "Native support for Barman Cloud backups and recovery is deprecated and will be completely removed in CloudNativePG 1.30.0". The operator is 1.27.4. The plugin needs cert-manager; no cert-manager namespace or CRDs exist.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/cluster.yaml` — spec.backup.barmanObjectStore
  - `bifrost-trade-infra/k8s/system/cnpg-operator/kustomization.yaml` — operator version pin
- **Impact**: An operator upgrade past 1.29 would stop WAL archiving and backups.
- **Fix**: Before that upgrade: install cert-manager, deploy plugin-barman-cloud, move the Cluster to an ObjectStore plus plugin configuration, verify a backup and a restore drill.
- **Ratchet**: install-cnpg-operator.sh refuses a version of 1.30 or later while the Cluster still uses barmanObjectStore.
- **验收**: A completed Backup with method plugin and a restore drill that passes.
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-trade-infra

### TD-136

**P2 · research-data · GEX writes levels for an expiry whose open interest is all zero: walls and zero_gamma fall on an arbitrary strike, 1,534 rows on 496 names, and terrain and scan copy them**

- **状态**：观察中（到 10-08，看 10-07 与 10-08 两次夜批后「验收」的 SQL 仍为 0）
- **进展（10-06，Owner 批「现在修」）**：research 0.185.0（a83abd1，pin 16b0f67）上线：`exposure.has_gamma_exposure`，没有 gamma 暴露的到期日不写分布也不写 levels（判定用两面 wall 的 gex 都为 0，覆盖 1,182 行零 OI 和 352 行「只有远离现价的行权价、gamma 舍入为 0」）；整天都没有暴露的名字清空当天并报 `No gamma exposure`；盘中 GEX 同样不写。Dagster 0.185.0-dagster 16:50 UTC apply。回填 Job `research-gex-zero-exposure-purge-0185`（`engines/gex/zero_exposure_purge`）：删 levels 1,534 行、分布 24,413 行，terrain 重算 104 行，scan 重算 145 行。核对：退化 levels 剩 0；levels 总数 70,974 → 69,440；没有 terrain 行再读到退化行；145 行 scan 的 regime 与 pin_score 全部与 terrain 一致。备份 `~/bifrost-backups/golden-source/2026-10-06_gex-zero-exposure-td136/`。防线：`tests/engines/test_gex_zero_exposure.py`（签收时登记进 RATCHETS.md）。后续：TD-157（单边）。
- **Claim**: compute_gex_levels takes the call wall with max(call_gex) and the put wall with min(put_gex); when every contract of an expiry has open_interest 0, every gex is 0, both walls become the first strike in the distribution, no sign flip exists, and zero_gamma falls back to the strike nearest spot. The row is written with total_net_gex 0 and call/put_wall_gex 0. Same class as max pain's zero-OI rows, fixed in research 0.155.0 (the expiry is skipped); GEX was not covered. Found on 10-06 checking CTVA after its 10-01 spin-off: the new standard series listed on 10-02 with OI 0 produced three such rows (walls and zero_gamma all 12.5, spot 11.92).
- **Measured**: MEASURED 10-06, read-only on Golden Source: features.option_metric_gex_levels_daily has 1,534 rows with total_net_gex = 0, all with call_wall_gex = put_wall_gex = 0; 1,186 name-sessions, 496 names, 07-06 → 10-05; still written nightly (09-28: 32, 09-29: 25, 09-30: 11, 10-01: 376, 10-02: 52, 10-05: 34).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:192` — `call_wall = max(distribution, key=lambda r: float(r.get("call_gex") or 0))`
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:220` — zero_gamma fallback to the strike nearest spot
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:560` — every expiry in by_exp is written, no zero-OI guard
  - `bifrost-research/src/bifrost_research/engines/forecast/terrain.py:182` — walls_reach_spot reads these walls; CTVA 10-02 terrain gamma zone 12.44–12.56 and scan gex_notional 0 came from them
- **Impact**: Levels pages, terrain (pin score, gamma zone, regime) and scan read a wall and a zero-gamma level where no open interest exists. One night after a corporate action (10-01: 376 rows) touches many names at once.
- **Fix**: In compute_gex_for_symbol skip an expiry whose summed open interest is 0 (write no distribution and no levels row), as max_pain does since 0.155.0; the session is already replaced delete-then-write, so the next recompute clears it. One-off: back up and delete the 1,534 rows, then recompute terrain and scan on the affected name-sessions (pattern: engines/adjusted_contract_purge --max-pain).
- **Ratchet**: A test that compute_gex_for_symbol writes nothing for an expiry whose contracts all have open_interest 0; a nightly check that features.option_metric_gex_levels_daily has no row with total_net_gex = 0 and both wall gex = 0.
- **验收**: `SELECT count(*) FROM features.option_metric_gex_levels_daily WHERE total_net_gex = 0 AND COALESCE(call_wall_gex,0) = 0 AND COALESCE(put_wall_gex,0) = 0` returns 0 after two nightly runs.
- 审批 已批（Owner 10-06）· 代价 S · 风险 low · repos: bifrost-research

### TD-137

**P1 · trade-data · The daily snapshot capture locks an account's intraday book into the day (first write wins, no freshness test) and account_nav_daily stores no margin-pressure fields**

- **状态**：在做（Owner 10-06 批准 3 条 DDL，10-07 收盘前发；代码在分支 core 5963422 / infra ab27841）
- **验收**：每个 Trade 库（`bifrost_dev` / `bifrost_stg` / `bifrost_prod`）发布后的 session：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_prod -X -At -c "SELECT count(*) FROM account_nav_daily WHERE snapshot_date >= '<发布日>' AND account_updated_at < (snapshot_date + time '16:00') AT TIME ZONE 'America/New_York'"` 为 0（NYSE 提前收盘日按提前收盘时间比），且 `SELECT snapshot_date, count(cushion), count(*) FROM account_nav_daily GROUP BY 1 ORDER BY 1 DESC LIMIT 3` 最新一天 count(cushion) = count(*)
- **现在**：道 K 10-06：rebase 到 TD-140（0.51.0）之上，capture 仍读 `attribution_live_marks_only`；门禁 core lint 0、1296 passed、test-db 102 passed（postgres:17），api 0805fb1 在新 core 上 1002 passed，infra 三环境 kustomize 可渲染。要批的 DDL（`snapshot_ddl.py:78-81`，只由 db-init 执行，三库各一次，可空、无默认、不重写表、不回填、无自加项、不可逆步骤无）：`ALTER TABLE account_nav_daily ADD COLUMN IF NOT EXISTS cushion double precision;` · `… excess_liquidity double precision;` · `… maint_margin_req double precision;`
- **下一步**：10-07 收盘前（16:20 ET 之前，避开 20:05–20:40 UTC）：① 每环境按 `scripts/release/db-steps.d/2026-10-07-td137-nav-margin-columns.md` 先 commit + verify 再 `release.sh db-done`（release.sh 的 before 检查会拦未做的）② `release.sh window && git push origin 5963422:refs/heads/main`（core，连同 0.51.0 / TD-140 与道 L 的前端）③ Owner 跑 `release.sh stg` → `prod` → `dev` ④ api 镜像带上 0.52.0 后合并 infra ab27841 并同步 bifrost-stg / bifrost-prod ⑤ 10-08 跑验收 SQL
- **Claim**: capture() inserts NAV and positions with ON CONFLICT DO NOTHING, so the first run of a date wins, and it copies every brokerage.account row with no freshness test. The secondary account's TWS logs off at 11:00 New York every weekday (TWS Auto log off), so the 16:20 capture stores that account's intraday values as the day's; the 20:30 job only enriches marks and Greeks. An account last synced 2026-05-11 (U17113214) still gets a NAV row every day. Separately, account_nav_daily has no column for Cushion / ExcessLiquidity / MaintMarginReq although brokerage.account.summary_extra carries all three keys for all three accounts; this history only accumulates forward, so every night without the columns is a day that cannot be refilled (SNAPSHOT-SPEC §1.1 pressure history).
- **Measured**: MEASURED 10-06 on the CNPG replica: 10-05 rows for U8829175 in DEV and STG have account_updated_at and positions_updated_at 15:48 UTC (11:48 New York, intraday); the PROD 10-05 row is a manual re-capture by another session at 22:48 UTC. First night 10-05: DEV 31 / STG 30 / PROD 31 position rows, NAV 3 rows per database. summary_extra: the three keys present on all three accounts (key names only were read).
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/portfolio/snapshot/daily.py:174` — `SELECT %s, account_id, net_liquidation, total_cash, buying_power, updated_at`
  - `bifrost-trade-core/src/bifrost_core/portfolio/snapshot/daily.py:177` — `ON CONFLICT (snapshot_date, account_id) DO NOTHING`
  - `bifrost-trade-core/src/bifrost_core/portfolio/snapshot/daily.py:187` — `ON CONFLICT ON CONSTRAINT position_snapshot_daily_uq DO NOTHING`
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/snapshot_ddl.py:69` — `buying_power double precision,`
  - `bifrost-trade-infra/k8s/overlays/prod/position-snapshot.cronjob.yaml:13` — `schedule: "20 16 * * 1-5"`
  - `bifrost-trade-infra/k8s/overlays/prod/position-snapshot.cronjob.yaml:113` — `command: [python, -m, bifrost_core.portfolio.snapshot, enrich]`
- **Impact**: P&L Explain, the Performance return basis and the Accounts curve (TD-138) will read the secondary account's intraday values as its close; a dead account adds a constant NAV row; Backing's pressure history and the Room-to-add lookback have nothing to read.
- **Fix**: core 9013ba2 (0.51.0): capture works per account; an account whose brokerage.account updated_at is older than the session close (16:00 New York, or the NYSE early close from market.us_market_holiday) is skipped with its positions and listed in stale_accounts; an account already captured for the date is left alone; the empty-attribution refusal counts only the accounts being written. infra deaa2ca: the 20:30 CronJob runs `all` (capture, then enrich), which takes an account that came back after the close. account_nav_daily gains cushion / excess_liquidity / maint_margin_req (ADD COLUMN IF NOT EXISTS, double precision, nullable, no default, no backfill; parsed from summary_extra, non-finite → NULL). Ordering risk: an image at 0.51.0 in an environment whose db-init has not run fails the capture INSERT on the missing columns.
- **Ratchet**: core tests in 9013ba2: test_capture_skips_a_stale_account_whole_and_lists_it, test_evening_rerun_takes_only_the_account_that_came_back, test_positions_without_an_account_row_count_as_stale, test_session_close_reads_an_early_close (db), test_margin_columns_are_additive_and_idempotent (db). No separate nightly check: the writer itself refuses a stale account and prints it as stale_accounts in the Job log; the 验收 SQL is the spot check.
- 审批 改表 + 发布（要你批） · 代价 S · 风险 med · repos: bifrost-trade-core, bifrost-trade-infra

### TD-138

**P2 · trade-data · The daily position and NAV snapshots have no reader: no trade-api route, no Research or frontend read, and three pages still say the snapshot does not exist**

- **状态**：未开始
- **验收**：PROD 读接口返回 200 且有行：`curl -s -o /dev/null -w '%{http_code}' http://192.168.10.73:30881/api/account/portfolio/nav-history` → 200（若实现时取了别的路由名，把命令改成那个）；`git -C bifrost-trade-api grep -c 'position_snapshot_daily\|account_nav_daily' origin/main -- src` 至少 1 个文件；`git -C bifrost-trade-frontend grep -n 'Nothing stores one' origin/main -- src/pages/portfolio/pnlExplain` 无输出
- **下一步**：等 10-06 收盘后有两天数据再开工：api 读接口 → 前端按 SNAPSHOT-SPEC §5 改三页；TD-139 的 quality 在这一步一起定。TD-137 上线前读侧要按 account_updated_at 过滤盘中行。
- **Claim**: Since 10-05 position_snapshot_daily and account_nav_daily are written nightly in all three Trade databases, but trade-api, Research and the frontend have no reference to either table, and GET /api/account/portfolio/nav-history, /snapshots and /api/monitor/status/history answer 404 on PROD. PnlExplainPage, PerformanceReturnBasis, the Transfer & Pay downstream band and the Accounts net-liquidation curve keep their not-wired state, and the P&L Explain model text still says nothing stores a snapshot.
- **Measured**: MEASURED 10-06: 10-05 rows DEV 31 / STG 30 / PROD 31, option Greeks 13/13; `git grep` for both table names on origin/main: 0 files in bifrost-trade-api (8a78042) and bifrost-research (a242b22), only core's writer; the three routes 404 on PROD.
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/snapshot_ddl.py:24` — `POSITION_SNAPSHOT_DAILY = "position_snapshot_daily"`
  - `bifrost-trade-frontend/src/pages/portfolio/pnlExplain/PnlExplainPage.tsx:348` — `⚠ needs the daily snapshot`
  - `bifrost-trade-frontend/src/pages/portfolio/pnlExplain/pnlExplainModel.ts:47` — `'The four attributions need a per-day snapshot of positions, marks and vendor Greeks. Nothing stores one, so Δ, Γ, vega and θ have no reading`
  - `bifrost-trade-frontend/src/pages/portfolio/performance/PerformanceReturnBasis.tsx:95` — `per account — net liquidation plus its snapshot time (SNAPSHOT-SPEC §1.1).`
- **Impact**: The stored history reaches no page: P&L Explain attribution and its Today / WTD / MTD windows, the Performance return basis, Transfer & Pay downstream and the Accounts curve stay grey while the data accumulates.
- **Fix**: trade-api read routes over both tables through a core reader (per account and date range, NAV history; positions per session with a trade_id rollup for SNAPSHOT-SPEC §2), then the three frontend items in SNAPSHOT-SPEC §5. Until TD-137 ships, the reader drops NAV rows whose account_updated_at is before that session's close.
- **Ratchet**: trade-api route test that reads the snapshot tables on a seeded DB; frontend test that P&L Explain stops rendering the not-wired text when the route returns rows.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-trade-core, bifrost-trade-api, bifrost-trade-frontend

### TD-139

**P3 · trade-data · Snapshot Greeks carry no quality flag (vendor / degraded / missing): only mark_source and greeks_asof are stored**

- **状态**：未开始（随 TD-138 读侧一起定：派生还是加列）
- **验收**：TD-138 的读接口对每个 OPT 行都给出 `greeks_quality` ∈ {vendor, degraded, missing}，且 missing 的个数等于 `SELECT count(*) FILTER (WHERE sec_type='OPT' AND delta IS NULL) FROM position_snapshot_daily WHERE snapshot_date = (SELECT max(snapshot_date) FROM position_snapshot_daily)`（同上的 CNPG 副本只读命令）
- **Claim**: SNAPSHOT-SPEC §1.3 asks for a quality field per option row so P&L Explain phase 2 can mark degraded Greeks instead of reading them as exact; position_snapshot_daily stores mark_source and greeks_asof only. Not biting yet: every option row of 10-05 has vendor values.
- **Measured**: MEASURED 10-06: 10-05 OPT rows 13/13 with delta present in all three databases.
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/snapshot_ddl.py:44` — `mark_source text,`
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/snapshot_ddl.py:51` — `greeks_asof timestamptz,`
  - `design/trade/SNAPSHOT-SPEC.md:61` — `(vendor / degraded / missing)`
- **Impact**: The first night a vendor Greek is missing or stale, P&L Explain phase 2 has no way to say so.
- **Fix**: Prefer deriving on read in the TD-138 reader: vendor when greeks_asof is that session and delta is present; missing when delta is null; degraded when greeks_asof is older than the session or mark_source is not vendor. Add a column only if the read cannot tell degraded apart (that would be 改表, back to the Owner).
- **Ratchet**: Unit test of the derivation over the three cases; the route contract test asserts the field on every OPT row.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-api

### TD-140

**P2 · trade-data · Position attribution rows have no price, intraday or after the close: their only price source is contract_quote_live, which only the frozen daemon writes**

- **状态**：在做（代码已推 core 4dbd316 = 0.51.0，不改 DDL；等 Trade 发版后验收）
- **验收**：收盘 enrich 之后：`curl -s http://192.168.10.73:30881/api/account/executions/position-attribution | python3 -c 'import json,sys;r=json.load(sys.stdin)["items"];print(len(r),sum(x.get("price_mid") is None and x.get("price_last") is None for x in r),sorted({str(x.get("mark_source")) for x in r}))'` → 第二个数为 0，第三项不含 None
- **下一步**：Owner 跑 Trade 发版（core 0.51.0，api 不改代码、下限不动）→ 跑验收命令，DEV 端口 30882；前端没有把这个价格标成 EOD，记为 TD-171
- **现在**：改前实测 10-06 18:41 UTC：DEV / PROD 各 31 行全无价格、无 mark_source；position_snapshot_daily 三环境只有 10-05 一个 session，DEV / PROD 29/29 持仓有 vendor_eod 标记。0.51.0：无新鲜 live quote 时取最新 vendor_eod 快照标记（股票取插件 benchmark 日收盘中更新的那个），每行加 `mark_source` / `mark_date`；capture 用 `fallback_marks=False`，`split_rows` 只认 `quote_live`，旧收盘价不会被回灌成当天 mark。门禁：core lint 0、1287 passed、test-db 99 passed；api 在 0.51.0 上 1002 passed
- **Claim**: get_position_instance_attribution takes price_mid / price_last only from a LEFT JOIN on brokerage.contract_quote_live, filtered to rows younger than 4 hours (TD-02, core 0.28.2). Under D10 the daemon does not run, so the table has 13 rows, newest 2026-03-28, and every attribution row has no price and no unrealized_pnl_est, intraday and after the close. The 09-29 reading that stocks had prices was March prices the freshness rule now excludes.
- **Measured**: MEASURED 10-06 after the close: GET /api/account/executions/position-attribution → PROD and DEV 31 rows each; OPT 13/13 and non-OPT 18/18 with price_mid, price_last and unrealized_pnl_est null; brokerage.contract_quote_live 13 rows, max(updated_at) 2026-03-28. (09-29: 30 rows, OPT 12/12 null, non-OPT 2/18 null.)
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/executions.py:1576` — `cql.mid AS price_mid, cql.last AS price_last`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/executions.py:1578` — `LEFT JOIN {CONTRACT_QUOTE_LIVE} cql`
  - `bifrost-trade-core/src/bifrost_core/portfolio/quote_freshness.py:33` — `def fresh_quote_sql(alias: str) -> str:`
- **Impact**: Positions and Ledger show no unrealized P&L for any position; anything that reads attribution prices reads nothing.
- **Fix**: Where no fresh live quote exists, take the newest position_snapshot_daily.mark for the contract (vendor EOD, written by the nightly enrich) and return mark_source and its date; intraday stocks may use the plugin daily-close fallback TD-02 already uses. The snapshot capture itself calls this reader, so the fallback must not become the snapshot's own mark (enrich stays its source). Nothing here writes contract_quote_live or touches the daemon (D10).
- **Ratchet**: core test: with contract_quote_live empty and a snapshot mark present, the row carries that price with mark_source vendor EOD; with a fresh live quote, the live one wins.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-frontend

### TD-142

**P2 · research-data · The 90-day IV cone has 31–39 sessions of history and there is no 180-day tenor: ATM IV was stored only to 90 DTE before 2026-08-05**

- **状态**：未开始（方向 Owner 10-06 已采纳：从 option_daily 回填；执行前列范围交你确认；须在 10-31 前做，W3 11-01 起删 option_daily 最老一个月，之后只能读归档）
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -At -c "SELECT count(DISTINCT trade_date) FROM features.option_metric_atm_iv_daily WHERE symbol='NVDA' AND expiry-trade_date>90 AND atm_iv IS NOT NULL"` ≥ 150（回填前 39 左右）；TD-141 的 iv-cone 命令里 NVDA 的 90 档 n ≥ 60、withheld 为 False，且出现 180 档
- **Claim**: The ATM IV store kept only expiries up to 90 DTE before 2026-08-05 (the Brent pass is still capped at DTE_MAX = 90), so the cone's 90-day horizon has fewer than MIN_SESSIONS (60) sessions and its percentiles are withheld; there is no 180-day horizon at all. It fills by itself around early November. raw_market.option_daily holds the long-dated bars to backfill from.
- **Measured**: MEASURED 10-06: iv-cone 90d NVDA 39, SPY 31, AAPL 32 sessions; no 180d. raw_market.option_daily: NVDA bars with trades at 150–220 DTE on 154 sessions, earliest 2025-11-10.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/iv_solver.py:53` — `DTE_MAX = 90`
  - `bifrost-research/src/bifrost_research/engines/volatility/atm_iv.py:366` — `AND (o.expiry - o.bar_date) BETWEEN {DTE_MIN} AND {DTE_MAX}`
  - `bifrost-research/src/bifrost_research/repositories/iv_cone.py:36` — `MIN_SESSIONS = 60`
- **Impact**: History's cone withholds 90-day percentiles for every name and has no long tenor for calendars and longer-dated structures.
- **Fix**: One-off Research backfill of long-tenor ATM IV into features.option_metric_atm_iv_daily from option_daily with the Brent method and the DTE cap lifted to about 220 for that pass only; first list the range (symbols × sessions × expected rows, which sessions already have >90 DTE rows) for the Owner. Then add 180 to the cone's tenors. Writes Research-owned features.* only (D13).
- **Ratchet**: A test that the longest cone tenor is inside the DTE range the ATM IV writers store, so the cone and the store cannot drift apart again.
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-research

### TD-143

**P3 · research-data · Hypotheses never link to trades: linked_opportunity_ids is empty on all 91 rows, and only Research's own create / patch writes it**

- **状态**：观察中（读时派生已上线 research 0.193.0，前端 357f237d 随 10-07 Trade 发版；正向验收要你在 DEV 走一遍）
- **验收**：在 DEV 上用一个 hypothesis 建 plan（source_kind='hypothesis'）并关联成交后，Research 的 hypothesis 读接口带出该 trade_id；`git -C bifrost-trade-frontend grep -n 'BROKEN_LINK' origin/main -- src/pages/review/objectives` 指向派生链接而不是 `hypothesis.linked_opportunity_ids`
- **验收结果**：部分 PASS 2026-10-06：`BROKEN_LINK` 已指向 `hypothesis.linked_trade_ids`；dev / stg / prod 各读 94 个假设、0 条 hypothesis 来源的已成交 plan、error 为空；`trade_env=qa` 返回 422。正向（真链出 trade_id）未做：要写 DEV Trade 库
- **下一步**：你在 DEV 用一个假设 id 建 plan（source_kind=hypothesis、source_ref=该 id）并让它成交后，看 `/research/hypothesis/<id>?trade_env=dev` 的 `linked_trade_ids`；前端还没有「从假设建 plan」的入口（TD-177）；trade-api plans 没有 source_kind 过滤（TD-178）
- **现在**：research 0.193.0：假设 list / get 每行加 `linked_trade_ids` / `linked_trades` / `trade_link_basis`，读 trade-api 现有 `GET /strategies/plans?status=filled&limit=500` 后筛 `source_kind='hypothesis'`，新参数 `?trade_env=dev|stg|prod`（默认 prod），读失败为 null 带错误、到上限标 truncated；两个库都没有新写入方（D13）。前端 `useTradeEnv` + Review › Objectives 链按本环境读。防线：`tests/repositories/test_hypothesis_trade_links.py`、`objectiveChainModel.test.ts`
- **Claim**: research.hypothesis holds 91 rows (active 65 · archived 25 · validated 1) and none has linked_opportunity_ids; the objective chain in the frontend names exactly that column as its broken link. Trade's strategy_plan already carries source_kind='hypothesis' with source_ref and trade_id, so the link can be derived, but plans are PROD 0 · STG 0 · DEV 3 (all manual) and trade-api GET /plans has no source_kind filter.
- **Measured**: MEASURED 10-06 on the replica (Golden Source and the three Trade databases).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/api/hypothesis.py:69` — `linked_opportunity_ids: list[str] = Field(default_factory=list)`
  - `bifrost-trade-frontend/src/pages/review/objectives/objectiveChainModel.ts:48` — `export const BROKEN_LINK = 'hypothesis.linked_opportunity_ids'`
  - `bifrost-trade-api/src/bifrost_api/strategy/routers/plans.py:72` — `status: Optional[str] = Query(None, description="draft, intended, filled or cancelled"),`
- **Impact**: /review/objectives shows the chain broken at the hypothesis for every objective; the Hypothesis Board's record stays thin.
- **Fix**: Research derives hypothesis → trade_id at read time from Trade plans with source_kind='hypothesis', source_ref = the hypothesis id and trade_id set. Read path (trade-api GET /plans with a source_kind filter, or another read path) is listed with the build; no new writer into either store (D13). The frontend chain reads the derived link. Links appear only once plans are used.
- **Ratchet**: Research test: a plan with source_kind hypothesis and a trade_id yields the link, a cancelled plan does not; frontend test that the chain is not broken when the link exists.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research, bifrost-trade-api, bifrost-trade-frontend

### TD-144

**P3 · research-data · Settled candidates are not attributed to the judge (persona) that put them forward, so the Personas bench track-record columns stay grey**

- **状态**：未开始（要你定：要不要做、记在哪；见「需要你拍板」）
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

### TD-145

**P3 · research-data · Settled candidates carry no regime label, so the Personas bench 'Best regime' column has nothing to group by**

- **状态**：在做（后端已上 research 0.186.0（995a890）：/rows 每行带 regime / regime_scope / regime_date，/summary?by_regime=true 按 regime 分组；10-06 GS 副本实测 127 个已结算候选 111 个名字 regime、16 个 SPY、0 个无标签；`tests/api/test_candidate_outcome_rows_regime.py` 5 passed。剩前端：JudgeTrackRecord 的 Best regime 列接 /summary?by_regime=true，设样本数门槛。**接手**：前端没有分支，从 main 新开；JudgeTrackRecord.tsx 的 Best regime 列读 `/research/candidate-outcome/summary?source=<src>&days=<n>&by_regime=true` 的 `data.by_regime`，取 hit_rate 最高且样本数过门槛的 regime；需 research 用户令牌（require_owner）；Journal Settled 的 Right / Wrong 拆分同时改读 TD-147 的 `/rows?source=&days=`）
- **验收**：`kubectl -n research exec deploy/research-api -- python -c "import bifrost_research;print(bifrost_research.__version__)"` ≥ 0.185.0；在 research origin/main 上 `python -m pytest tests/api/test_candidate_outcome_rows_regime.py -q` 通过；前端接上后 `git -C bifrost-trade-frontend grep -n 'by_regime' origin/main -- src` 至少一行
- **Claim**: No candidate's lens_snapshot has a regime key and Golden Source has no market-level regime table; the per-name regime lives in features.stock_forecast_terrain_daily (06-24 → 10-05). SPY was range on 25 of the 26 candidate days, so a market label would separate nothing.
- **Measured**: MEASURED 10-06: 0 candidates with lens_snapshot ? 'regime'. With 3109b04 on the replica: of 127 settled candidates 111 take the name's regime, 16 fall back to SPY, 0 unlabelled (the join takes that session or the newest within 7 days before it, since 15 candidate dates fall on weekends); the LATERAL join runs in about 2 ms. Side reading, small sample: harness 5d hit trending 19/24, range 24/64.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/api/candidate_outcome.py:136` — `@router.get("/rows", dependencies=[Depends(require_owner)])`
  - `bifrost-trade-frontend/src/pages/copilot/personas/JudgeTrackRecord.tsx:56` — `{ column: 'Best regime', missing: 'settled outcomes carry no regime label' },`
- **Impact**: The bench cannot say in which market a judge is right.
- **Fix**: 3109b04: /rows adds regime, regime_scope and regime_date per row, derived at read time as COALESCE(name terrain, SPY) (precedent: /research/signal-decay); /summary?by_regime=true groups by it. No table or column. Then JudgeTrackRecord's Best regime reads /summary?by_regime=true with a sample floor.
- **Ratchet**: tests/api/test_candidate_outcome_rows_regime.py (3109b04).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-frontend

### TD-146

**P3 · research-data · No store accepts a hand verdict, so the Personas bench 'Agrees with you' column cannot be computed**

- **状态**：未开始（要你定：要不要建手动判词库；要的话是新表，先出设计；见「需要你拍板」）
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

### TD-148

**P3 · trade-data · A trade cannot name the lens or backtest run it came from: trade has no such column and strategy_plan.source_kind does not allow lens / backtest_run**

- **状态**：未开始（口径 Owner 10-06 已定：(b) plan 的 source_kind 加 lens / backtest_run，经 plan → trade 派生；DDL 清单待你逐项确认，见「需要你拍板」）
- **验收**：三个 Trade 库各跑：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_prod -X -At -c "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='strategy_plan'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%source_kind%'"` 含 `'lens'` 与 `'backtest_run'`
- **Claim**: PROD trade has trade_id, strategy_opportunity_id, account_id, opened_at, label, created_at, updated_at and no public table has a lens, backtest or run_id column. strategy_plan.source_kind is checked against manual | symbol | hypothesis | inbox_draft | roll, and core repeats the same five in the reader and the request schema. Outcome / Lineage keep the lens and run chips grey (design D3, Owner 2026-09-17).
- **Measured**: MEASURED 10-06 on bifrost_prod (columns of trade; the CHECK definition).
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/trade_ddl.py:124` — `CHECK (source_kind IN ('manual', 'symbol', 'hypothesis', 'inbox_draft', 'roll')),`
  - `bifrost-trade-core/src/bifrost_core/monitor/reader/strategy_plan.py:593` — `_SOURCE_KINDS = ("manual", "symbol", "hypothesis", "inbox_draft", "roll")`
  - `bifrost-trade-core/src/bifrost_core/monitor/schemas/strategy_plans.py:17` — `SourceKind = Literal["manual", "symbol", "hypothesis", "inbox_draft", "roll"]`
  - `design/trade/DECISIONS.md:1232` — `**D3 · Outcome 的 lens / run 链条**(Owner 2026-09-17)`
- **Impact**: Record's Lens cut has a single 'no lens recorded' row and 'vs backtest' is a dash everywhere.
- **Fix**: DDL per environment through db-init: drop the source_kind CHECK on strategy_plan (name read from pg_constraint; default strategy_plan_source_kind_check) and add it back with 'lens' and 'backtest_run'. Widening only: existing rows pass, PROD has 0 plans, no new column, no backfill, reversible while no row uses the new values. Code: core _SOURCE_KINDS and SourceKind gain the two values (public interface: core minor bump, trade-api lower bound raised), source_ref carries the lens id or backtest run id; frontend Outcome / Lineage read them through the trade's plan.
- **Ratchet**: core test that the DDL CHECK list, _SOURCE_KINDS and SourceKind are the same set (three copies pinned together).
- 审批 改表（要你批） · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-api, bifrost-trade-frontend

### TD-149

**P2 · market-data · CTVA's adjusted daily bars ignore its 2026-10-01 spin-off, so every return-based feature on CTVA sees an ~84% one-day drop**

- **状态**：观察中（到 10-16，看数据源 adjusted=true 是否把分拆算进去）
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -At -c "SELECT bar_date, close, close_unadjusted FROM raw_market.stock_daily WHERE symbol='CTVA' AND bar_date BETWEEN '2026-09-28' AND '2026-10-02' ORDER BY 1"` 中 09-30 的 close ≠ close_unadjusted；且 `SELECT trade_date, rv_20d FROM features.stock_signal_vrp_daily WHERE symbol='CTVA' AND trade_date >= '2026-10-01' ORDER BY 1` 全部 < 1.0
- **现在**：每日定时任务 daily-ctva-adjust-and-unadjusted-close-check 在查（10-02、10-05、10-06 都未复权）。第 2 步 Owner 10-02 已批：数据源复权后重抓 CTVA 日线并重算 10-01 起的派生。
- **下一步**：复权后按已批的第 2 步做；到 10-16 仍不复权，另议：Research 按分拆比例自算（另批）。（10-16）
- **Claim**: The vendor's adjusted and unadjusted CTVA series are identical across the 10-01 spin-off (09-30 77.65 → 10-01 12.57), so raw_market.stock_daily.close carries the drop. VRP takes log(close_t / close_{t-1}) from that column and gives rv_20d about 6.4 from 10-01; momentum, SEPA, terrain and scan read the same bars; each session adds one more affected day, up to 252. The option metrics recovered separately once the standard series listed (closed on the board).
- **Measured**: MEASURED 10-06 13:33 UTC (scheduled check): 09-28 → 10-05 adjusted = unadjusted every day; close_unadjusted coverage on 10-05 100.00% (12,605/12,605, 0 rows off by more than 0.1%); CTVA rv_20d 09-30 0.209 → 10-01 6.438 · 10-02 6.433 · 10-05 6.444.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/ingest/stock_daily_grouped.py:8` — `the adjusted series folds in spin-offs as well as splits (HON 2025-10-29 reads`
  - `bifrost-research/src/bifrost_research/engines/vrp/compute.py:91` — `log_returns.append(math.log(cur / prev))`
  - `bifrost-research/src/bifrost_research/engines/vrp/compute.py:133` — `SELECT bar_date, close`
- **Impact**: CTVA's VRP, momentum, SEPA, terrain and scan are wrong from 10-01 and one more day wrong every session.
- **Fix**: Approved step 2: once the vendor restates, re-pull CTVA daily bars and recompute the derived features from 10-01. If not by 10-16: Research applies the spin ratio to the pre-spin bars itself (separate approval).
- **Ratchet**: For this case the daily scheduled check. For the class (proposed): a nightly sweep that flags any name whose close-to-close |log return| exceeds ln 3 on a day with no split in corporate_action, which catches the next unadjusted spin-off within one night.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data, bifrost-research

### TD-150

**P3 · frontend · Pages report gaps that are not there: 'no earnings date reaches this side', 'carry nothing at all' for names the vendor answered, and no note that CUE lists only adjusted contracts**

- **状态**：在做（代码就绪，已推为分支、未合并：frontend `fix/data-gap-wording` = 024077be（R2.b）· e8e554fc（B4.tail）· 7caac1f8（R10.CUE），基于 d1254adc；lint / build 过，改动文件相关测试 83 例过，全量 vitest 在最后一处改名后未重跑。**接手步骤**：① 等 Code Refactor 那批 Trade 发布（含前端 d1254adc）在 PROD 通过；② rebase 到最新 main，跑 `npm run lint && npm run build && npm run test:run`（全量）；③ 在 :5173 对 DEV 看 Today、Limits、Scan、Vol ratings、Corporate Actions、Symbol?CUE；④ `release.sh window && git push` 前端 main，随下一次 Trade 发布上线。Design 待看三点：Vol ratings 在 All 下 Earn 列部分有数、CUE 各指标块仍写 No reading — wait、440 紧凑版没有这条说明）
- **验收**：`git -C bifrost-trade-frontend grep -n -i 'earnings date reaches this side\|No earnings date on this side\|carry nothing at all\|cannot say whether they pay' origin/main -- src ':!src/layout/designNotes'` 无输出，且 `git -C bifrost-trade-frontend grep -n -i 'only adjusted contracts' origin/main -- src` 至少一行
- **Claim**: Three wording gaps, one batch. (1) Earnings (board R2.b): the shared earnings read from 10-04 (c85b0079 / 1b0baa53 / ca3694a2) gives estimated next dates, but Today checks, Limits, Scan and Vol ratings still say no earnings date reaches this side; TodayFace and stockRatingsModel already changed. (2) Corporate Actions (B4.tail): a name with a single row is treated as not backfilled and names with none are 'carry nothing at all'; after the 09-29 backfill CAOS's one split is a complete answer and CBRS · FN · HIMS · NBIS · NNE · RKLB really have 0 events. (3) CUE (R10.CUE): after the 1:30 reverse split (ex 2026-04-24) only 14 adjusted CUE1 contracts expiring 10-16 exist and no standard series is listed; the pages show empty max pain / ATM IV / GEX / flow / PCR with no reason.
- **Measured**: MEASURED 10-06 on bifrost-trade-frontend origin/main a9cbd02a: the lines below; 'only adjusted contracts' 0 hits; CUE 10-05 open interest 14 rows, all CUE1.
- **Evidence**:
  - `bifrost-trade-frontend/src/pages/home/today/useTodayChecks.ts:186` — `'no future earnings date reaches this side for any name in the book, so the week ahead cannot be read',`
  - `bifrost-trade-frontend/src/utils/limitsModel.ts:284` — `noReading: 'no future earnings date reaches this side, so no window can be drawn',`
  - `bifrost-trade-frontend/src/pages/research/discover/ScanPage.tsx:490` — `title="Days to the next print. No forward earnings date reaches this side — /research/events/calendar answers count 0, and the gap behind it`
  - `bifrost-trade-frontend/src/pages/research/discover/ScanPage.tsx:567` — `title="No earnings date on this side — see the column header."`
  - `bifrost-trade-frontend/src/lib/research/volRatingsModel.ts:46` — `* - an **Earn** column. No forward earnings date reaches this side:`
  - `bifrost-trade-frontend/src/pages/portfolio/corporateActions/corporateActionsModel.ts:211` — `/** Symbols with nothing at all — the feed cannot say whether they pay. */`
  - `bifrost-trade-frontend/src/pages/portfolio/corporateActions/CorporateActionsPage.tsx:391` — `${reach.silent.length} carry nothing at all: ${reach.silent.join(', ')}`
- **Impact**: The pages tell the Owner data is missing where an estimate exists or where the vendor answered zero; CUE's empty metrics read as a failure.
- **Fix**: The four earnings sites read the shared earnings read and say estimated ◎ · confirmed dates not in the subscription (see 数据边界); Corporate Actions says 'vendor answered none' / 'one event on record'; CUE's option metric cells say only adjusted contracts are listed (CUE1, 1:30 reverse split) and the exchange lists no standard series.
- **Ratchet**: A frontend test that searches src (outside designNotes) for the retired phrases and fails on a hit. Manual strength until vitest runs in CI (RATCHETS: FE 守卫测试).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-151

**P3 · research-data · The macro calendar is empty: features.macro_event_daily has 0 rows because macro_ingest has no scheduled caller**

- **状态**：在做（代码在 research main 4f1e34e = 0.197.0；镜像未建——auto mode 拒绝了道 O 起 deliver-research；构建与发布等你批）
- **验收**：上线并手动跑一次 `research_macro_calendar_job` 后：GS 只读 `SELECT count(*), max(event_date) FROM features.macro_event_daily` = `19|2027-12-08`；`/research/event-radar/macro/forward?days=30` count ≥ 2（10-14 CPI、10-28 FOMC）
- **下一步**：你批：① 起 `bifrost-deliver-research`（tag 0.197.0，revision 4f1e34e）与 `bifrost-build-research-dagster`（同 revision，在 mirror-sync 之后）② 推 pin ③ apply `dagster.yaml` 到 0.197.0-dagster（先确认无在途 run）④ 手动跑一次 job。后续：TD-180、TD-181、TD-182
- **现在**：实测：macro_event_daily 0 行，Dagster 里从没有 macro 的 job / run / asset，`macro_ingest` 只是读 Mac 路径的 CSV 投放目录（没实现 / 从未调度 → 修）。前瞻日历：0.197.0 新增包内维护源 `scheduler/data/macro_calendar.csv`（FOMC 2026–2027 共 16 条，10-06 读自 federalreserve.gov，2027 为官方 tentative；CPI 10-14 / 11-10 / 12-10），`macro_ingest` 改为按 (country, indicator, date) 稳定 id、删除已移除的 seed 行；新 asset `engines/macro_calendar` + `research_macro_calendar_job`（周一 10:00 UTC），roster 已同步。Macro gap（actual 对一致预期）：一致预期不在订阅里 = 权限缺口，接受并留座（见后续）。防线：asset output check（覆盖不到今天 + 30 天报 ERROR、序列将尽报 WARN）+ `tests/orchestration/test_macro_calendar.py`
- **Claim**: features.macro_event_daily is filled only by scheduler/macro_ingest.py, a CSV drop-zone ingest from Wave R4, and no Dagster schedule, job or CronJob calls it. /research/event-radar/macro/forward and /macro/gap answer 0 rows; the macro rows in /research/events/calendar come from a hand-placed ws:macro file.
- **Measured**: MEASURED 10-06: 0 rows; both routes 0 rows. CODE-READ: `git grep macro_ingest` on origin/main finds no caller in bifrost_research/orchestration or bifrost-trade-infra.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/scheduler/macro_ingest.py:1` — `"""Macro economic calendar CSV ingest (manual drop zone, Wave R4)."""`
  - `bifrost-research/src/bifrost_research/scheduler/macro_ingest.py:98` — `def run_macro_ingest_from_env() -> dict[str, Any]:`
  - `bifrost-research/src/bifrost_research/api/wave4.py:859` — `FROM features.macro_event_daily`
- **Impact**: Event radar has no macro look-ahead (FOMC, CPI, payrolls) from the store.
- **Fix**: Schedule macro_ingest weekly from Dagster over one maintained source (the ws:macro file the calendar already reads, or a vendor feed if the subscription has one). Or, if the calendar's ws:macro rows are enough, retire the two macro routes and the empty table instead (delete, not build).
- **Ratchet**: A Dagster asset check that features.macro_event_daily has a row dated within the next 30 days.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-152

**P2 · ops-platform · promtail drops log lines (ingester_error) around 02:00–03:15 and 22:xx UTC, so every Loki-based release gate can come out INCONCLUSIVE**

- **状态**：观察中（到 10-07 03:30 UTC，看夜间 dagster 批次不再丢日志）
- **验收**：10-07 03:30 UTC 之后经 Prometheus：`sum(increase(promtail_dropped_entries_total[12h]))` = 0，且 `sum(increase(promtail_mutated_entries_total{reason="line_too_long"}[12h]))` ≥ 1（超长行被截断而不是整批丢）
- **下一步**：那一行超长日志本身记为 TD-170
- **现在**：根因不是 Loki 背压：09-28..10-06 的 12 次全是 `{namespace="research", app="dagster-daemon"}` 在 22:45 / 03:00 UTC 有一行超过 256 KB，Loki 回 400，promtail 不重试、把整批 17–20 条记作 ingester_error。infra 677beb2：promtail `max_line_size: 250KB` + `max_line_size_truncate: true`（helm revision 7，5 个 pod 已加载）；`BifrostPromtailDroppingLogs` 说明补上 400 情形
- **Claim**: Release gates that prove 'nobody calls X any more' read Loki. promtail dropped 35 entries 10-02..10-05 and 18 more by 10-06 with reason ingester_error, clustered on ubt-k3s-04 (STG/DEV api pods) at ~03:00Z and ubt-k3s-02 (PROD) at 22:xxZ. loki_gate.py counts the drops and refuses to call a zero a zero.
- **Measured**: MEASURED 10-06 by paydown lane F: TD-51 gate dev 0 / stg 0 / prod 0 hits but INCONCLUSIVE (exit 3) because of 18 dropped entries; Prometheus `sum by (instance,reason)(increase(promtail_dropped_entries_total[1h]))`.
- **Evidence**:
  - `bifrost-trade-infra/scripts/release/loki_gate.py:241` — `res = prom_instant(f"sum(increase(promtail_dropped_entries_total[{secs}s]))", end)`
- **Impact**: Every compatibility-removal gate (TD-51 today, naming gates before it) needs an Owner judgement instead of a mechanical pass; real drops could hide a real caller.
- **Fix**: Find the Loki ingester limit or back-pressure hit at those times (rate / stream limits, ingester memory, the nightly batch log burst) and raise it or shape the burst; alert on promtail_dropped_entries_total > 0.
- **Ratchet**: PrometheusRule on increase(promtail_dropped_entries_total[1h]) > 0 (warning), so a gate's blind spot is visible the day it opens.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-153

**P3 · ops-platform · loki_gate.py only knows the pre-0.10.0 log line ('deprecated query params'); after api 0.10.0 refused callers log 'retired query params' and the gate cannot see them**

- **状态**：观察中（到 10-07 03:30 UTC，看 `td51-retired` 在无丢失窗口里给 PASS）
- **验收**：`python3 scripts/release/loki_gate.py td51-retired --since 2026-10-07T03:30:00Z` 退出 0（三环境 caller 0，release probe 行 > 0）
- **现在**：infra fc9961a：新 gate `td51-retired`（排除 bifrost-release-check，单列 release_probe_lines）；`GATE_FIXTURES` + `check_gate_fixtures()` 在 self-test 和每次运行前断言每个 gate 读得到它那版 api 的真实日志行。首跑 10-05 18:41Z..10-06 18:41Z：caller dev 0 / stg 0 / prod 0，probe 行 3/6/6，因窗口内有 TD-152 的 18 条丢失判 INCONCLUSIVE
- **Claim**: api 0.10.0 (TD-51) replaces the silent rewrite with a 422 and a WARNING 'retired query params: … user_agent=…'. loki_gate.py's TD-51 check builds its needle from the deprecated-params line only, so after the release a caller still sending old names is invisible to the gate that was built to find it.
- **Measured**: code-read 10-06 (paydown lane F).
- **Evidence**:
  - `bifrost-trade-infra/scripts/release/loki_gate.py:348` — `needle = f'|~ "{td51_group_regex(group)}"'`
  - `bifrost-trade-infra/scripts/release/loki_gate.py:55` — `TD51_NAMES = ("since_ts", "until_ts", "opened_at_from", "opened_at_until", "trade_date_from", "trade_date_to",`
- **Impact**: The 24-hour post-release check for TD-51 has to be done by hand with a raw LogQL query.
- **Fix**: Add a `td51-retired` check that counts 'retired query params' lines (excluding bifrost-release-check) and use it in the post-release step.
- **Ratchet**: A loki_gate test that every gate name has a needle matching the log line the current api version emits (fixture lines from both versions).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-155

**P2 · ops-platform · Pushes to GitHub main do not trigger CI until the Gitea pull mirror syncs, so a commit can be released before its CI ever ran**

- **状态**：未开始
- **Claim**: CI is triggered by Gitea webhooks; Gitea mirrors GitHub on a pull interval. On 10-06 core 0.49.0/0.50.0 (16:15/16:23 UTC) and api 0.10.0 had no CI run at all until `make k3s-sync-gitea-mirrors` was run by hand at ~16:30; core's previous CI was 14 h earlier. Together with TD-95 this means release.sh can deliver a SHA that CI has not seen.
- **Measured**: MEASURED 10-06: no ci-python-bifrost-trade-core/api PipelineRun after the pushes; the manual mirror sync created ci-python-bifrost-trade-core-9vgjk and -api-h7scl within seconds.
- **Evidence**:
  - `bifrost-trade-infra/k8s/cicd/tekton/trigger-trade-ci.yaml:225` — `body.repository.name in ['bifrost-trade-core', 'bifrost-trade-api',`
  - `bifrost-trade-infra/scripts/k3s/bootstrap-gitea-mirrors.sh:2` — `# Bootstrap Gitea org + GitHub pull mirrors (Session S7).`
- **Impact**: CI results lag pushes by up to the mirror interval; releases and reviews see 'no CI' and proceed anyway.
- **Fix**: Either a GitHub → Gitea push-mirror / webhook that syncs on push, or have release.sh (and the deliver pipelines, TD-95) sync the mirror and wait for the SHA's CI run before building.
- **Ratchet**: release.sh refuses a SHA with no Succeeded CI run (TD-95's switch) — which makes a missing run as visible as a red one.
- 审批 跨仓库发版 · 代价 S · 风险 med · repos: bifrost-trade-infra

### TD-156

**P2 · research-control · research_signal_hit_schedule fires at 00:10 UTC, before the 02:30 UTC batch writes the night's features, so it judges the previous night's features**

- **状态**：观察中（0.195.0 + 0.195.0-dagster 已上线；到 10-07 02:30 UTC 批次之后看 lens_hit 行数与步骤顺序）
- **验收**：10-07 批次后 GS 只读：`features.stock_signal_lens_hit_daily` 的 2026-10-06 ≥ 约 1,000 行、6–7 个 lens，max(computed_at) 晚于同日 iv_percentile；`research_trading_day` 的 STEP_START 顺序为 terrain / flow / vrp / sepa_projection → `engines__signal_hit` → `signal_hit_fwd_fill` → `alert_scan`；`dagster schedule list` 里没有 `research_signal_hit_schedule`
- **验收结果**：部分 PASS 2026-10-06：dagster-daemon 跑 0.195.0-dagster，`dagster schedule list` 里 `research_signal_hit_schedule` 0 条、`research_trading_day_schedule` 1 条；行数与步骤顺序待 10-07 批次
- **下一步**：已 suspend 的 `cronjob-signal-hit.yaml` / `cronjob-alert-scan.yaml` 还在跟着升 pin，记为 TD-176
- **现在**：research e96c360（0.194.0，未单独发布；0.195.0 叠在其上）：signal_hit 进 `TRADING_DAY_JUDGES`，依赖各特征写入方，终点改为 `latest_closed_session`；`research_signal_hit_schedule` 从代码与 roster 删除；`alert_scan` 依赖 `signal_hit_fwd_fill`。基线 10-05：lens_hit 只有 10 行、1 个 lens（02:31:58 写入，早于 iv_percentile 的 02:34:02）。防线 `tests/orchestration/test_judge_after_writer.py`（扩展）+ `tests/engines/test_signal_hit_session.py`。前端文案已同步（frontend e2c338f5）
- **Claim**: signal_hit runs on its own cron ('10 0 * * 1-6' UTC) instead of inside research_trading_day after the feature writers. At 00:10 UTC the night's SEPA / IV / scan features are not written yet, so each walk reads the previous session's features — the same class as TD-97 (judge before writer).
- **Measured**: code-read 10-06 by paydown lane A; not measured.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/research_aux_schedules.py:548` — `"research_signal_hit_schedule",`
  - `bifrost-research/src/bifrost_research/orchestration/research_aux_schedules.py:551` — `"10 0 * * 1-6",`
- **Impact**: Lens hit-rates and the alerts and drafts that read them lag a session and can pair features with the wrong session.
- **Fix**: Move signal_hit into research_trading_day after its sources and register it in READS_TRADING_DAY_OUTPUT (the TD-97 ratchet).
- **Ratchet**: tests/orchestration/test_judge_after_writer.py (added for TD-97) covers it once signal_hit is registered as a trading-day reader.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-157

**P3 · research-data · GEX writes a wall on an arbitrary strike when one side of an expiry has no gamma exposure: 1,762 levels rows on 244 names, terrain reads both walls**

- **状态**：观察中（到 10-08，看 10-07 与 10-08 两次夜批后「验收」的 SQL 仍为 0）
- **进展（10-06，Owner 批「TD-157 一起做」）**：research 0.191.0（ddf5642，pin e19d5cc）上线：`engines/gex/exposure_guards.drop_empty_side_walls`，日线 levels 中没有暴露的一侧，wall 和 wall gex 写 NULL（`has_gamma_exposure` 同时移入该模块，exposure.py 回到 800 行以内）；只改日线，盘中快照汇总全部到期日，且前端 GexTimelineChart 会把空 wall 画在 0。读 wall 的地方（terrain、mart_sepa_tier_options、brief、Symbol 各面、DealerHistory）都按缺失处理，已逐个核对。Dagster 0.191.0-dagster 18:24 UTC apply。回填 Job `research-gex-one-sided-walls-0191b`（`zero_exposure_purge --one-sided`）：置空 call 侧 820、put 侧 942，terrain 重算 237 行（156 行分数有变，regime 翻转 7 个，含与当前输入的其他漂移），scan 237 行。核对：空侧 wall 剩 0；TD-136 的整行无暴露仍为 0；scan 与 terrain 一致。备份 `~/bifrost-backups/golden-source/2026-10-06_gex-one-sided-walls-td157/`。同一天先跑了一次参数写错的 Job（`-0191`，执行的是 TD-136 那一步，0 行、无写入）。防线：`tests/engines/test_gex_zero_exposure.py` 的单边用例（签收时登记进 RATCHETS.md）。后续：TD-166（zero_gamma 兜底）。
- **Claim**: compute_gex_levels picks the call wall with max(call_gex) and the put wall with min(put_gex) independently. When only one side has exposure (every call gex 0, or every put gex 0), that side's wall is still written: the first strike in the distribution, with wall gex 0. TD-136 (0.185.0) covers only expiries where both sides are empty.
- **Measured**: MEASURED 10-06 after the TD-136 purge, read-only: of 69,440 levels rows, 820 have call_wall_gex 0 with a non-zero put wall and 942 the reverse; 244 names; 169 since 10-01.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:192` — `call_wall = max(distribution, key=lambda r: float(r.get("call_gex") or 0))`, and the put wall on the next line, with no check that the chosen wall has exposure
  - `bifrost-research/src/bifrost_research/engines/forecast/terrain.py:93` — pin_score_from_gex scores spot between the two walls
- **Impact**: terrain's pin score and gamma zone, and the levels pages, can place a call or put wall where no open interest of that side exists.
- **Fix**: Write NULL for a wall whose side has no exposure (call_wall_gex / put_wall_gex 0), so readers treat it as missing (terrain already handles a None wall). One-off: null those walls on the 1,762 rows and recompute terrain and scan on the name-sessions that read them (pattern: engines/gex/zero_exposure_purge).
- **Ratchet**: Extend tests/engines/test_gex_zero_exposure.py with a one-sided distribution; nightly check: no levels row with a non-null wall whose wall gex is 0.
- **验收**: `SELECT count(*) FROM features.option_metric_gex_levels_daily WHERE (major_call_wall IS NOT NULL AND COALESCE(call_wall_gex,0) = 0) OR (major_put_wall IS NOT NULL AND COALESCE(put_wall_gex,0) = 0)` returns 0 after two nightly runs.
- 审批 已批（Owner 10-06）· 代价 S · 风险 low · repos: bifrost-research

### TD-158

**P3 · research-data · Earnings estimates are served one name per request, so no universe-wide page can show an Earn column**

- **状态**：观察中（Research 部分已上线 0.193.0 / 0.196.0；前端 301c9bee / 357f237d 在 main，随 10-07 Trade 发版上线后看 Stock screen 的 Earn 列与 catalyst chip）
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n research exec deploy/research-api -- python -c "import urllib.request,json;d=json.loads(urllib.request.urlopen('http://127.0.0.1:8795/research/narrative/earnings/batch?symbols=NVDA,AAPL,KO').read());print(sorted(d['data']))"` → `['AAPL', 'KO', 'NVDA']`，每个都带 `expected_next`（或带原因的空）；`git -C bifrost-trade-frontend grep -n "is served across the universe" origin/main -- src` → 0 行
- **验收结果**：部分 PASS 2026-10-06：batch NVDA/AAPL/KO 24 ms、逐名与单名路由相等；全宇宙 3,742 名 8 次请求 1.4 s、525 名有预计日；前端 grep 0 行（357f237d）。页面未部署
- **下一步**：10-07 Trade 发版后在 :5173 看 Stock screen；No-model 下的 Earnings 排序仍未实现（TD-179）；`src/lib/schemas/research.ts` 已到 800 行上限，下次加 schema 先拆
- **现在**：research 0.193.0（212941e）新增 `GET /research/narrative/earnings/batch?symbols=`（≤ 500，一条 SQL，与单名共用 `_earnings_reading`）；0.196.0（7db30fa）`stock_screen.v2` catalyst 加 `earn_lt_10d` / `earn_10_30d` / `earn_gt_10d`（只增）。前端 `useNamesEarnings` 每 500 名一次 batch 并回填单名缓存。防线：`tests/api/test_narrative_api.py`、`tests/api/test_saved_screen.py`、`src/hooks/useNamesEarnings.test.tsx`（列表必须走 batch，白名单）、`stockScreenVocabulary.test.ts`
- **Claim**: GET /research/narrative/earnings takes exactly one symbol. The frontend's useNamesEarnings issues one query per name, so pages that list hundreds of names (Stock screen, Scan with All, Vol ratings) either fan out hundreds of requests or show no earnings estimate. The data-gap wording batch (TD-150) caps Scan at 60 names and reads only the selected row under All; Stock screen still says no earnings date is served across the universe.
- **Measured**: CODE-READ 10-06 on origin/main: the route signature is `symbol: str = Query(..., min_length=1, max_length=16)`; no batch route exists in api/narrative.py. Stock screen copy states the gap in four places.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/api/narrative.py:233` — `@router.get("/earnings")`
  - `bifrost-research/src/bifrost_research/api/narrative.py:234` — `def earnings_dates(symbol: str = Query(..., min_length=1, max_length=16))`
  - `bifrost-trade-frontend/src/hooks/useNamesEarnings.ts:33` — `export function useNamesEarnings(symbols: readonly string[])` (one query per name)
  - `bifrost-trade-frontend/src/pages/research/stocks/StockScreenPage.tsx:703` — `Earn is — on every row: no earnings date is served across the universe.`
  - `bifrost-trade-frontend/src/pages/research/stocks/stockScreenStages.ts:32` — `'No earnings window or theme is served across the universe: …'`
  - `bifrost-trade-frontend/src/pages/research/stocks/ResultTable.tsx:305`, `RankDrawer.tsx:125` — same wording
- **Impact**: Stock screen's Earn column and Catalyst stage stay empty; Scan under All and Vol ratings under All show earnings only for rows read elsewhere; the earnings veto in rules cannot be applied across a screen.
- **Fix**: Add `GET /research/narrative/earnings/batch?symbols=` (cap ~500 names, one SQL over the 8-K table plus the expected_next rule, same per-name shape and reasons as the single route; additive, nothing removed). Frontend: useNamesEarnings fills its per-name cache from the batch call for lists; then Stock screen, Scan (lift the 60-name cap) and Vol ratings read it and the four "not served across the universe" strings go.
- **Ratchet**: Research test that the batch route returns the same reading as the single route for each name in a fixture; frontend ratchet that no page calls the single-name earnings read inside a list of more than 60 names.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research, bifrost-trade-frontend

### TD-159

**P3 · market-data · No read says how many standard and adjusted option contracts a name has, so "only adjusted contracts are listed" is inferred in the browser from ticker shapes**

- **状态**：观察中（Research 部分已上线 0.193.0；前端 301c9bee 随 10-07 Trade 发版上线后看 CUE 的 Symbol 页提示）
- **验收**：对 CUE（或任一只有调整合约的名字）调用新增的计数读法 → `standard = 0`、`adjusted > 0`；对 NVDA → `standard > 0`；`git -C bifrost-trade-frontend grep -n "isAdjustedOptionTicker" origin/main -- src` → 只剩测试或 0 行
- **验收结果**：部分 PASS 2026-10-06：composite 对 CUE standard 0 / adjusted 14 {CUE1}，NVDA 4,180 / 0，APTV 70 / 40；前端 `isAdjustedOptionTicker` 只剩防线测试里的正则。页面未部署
- **现在**：research 0.193.0：`GET /research/exhibit/composite` 加 `option_listing`（as_of、standard / adjusted 计数、adjusted_roots，用共享谓词 `not_adjusted_contract_sql`）；前端 `useDossier` 读同一缓存，`SymbolAdjustedOnlyNote` 只按 Research 的计数显示。防线：`tests/engines/test_adjusted_contracts.py`、`tests/api/test_exhibit_lenses.py`、`SymbolAdjustedOnlyNote.test.tsx`（src 里不准从 ticker 推导调整 root）
- **Claim**: Research excludes adjusted contracts (OCC root ending in a digit) from every option metric, so a name with only adjusted contracts has empty max pain, ATM IV, GEX, flow and PCR by rule. Nothing served says so. The TD-150 frontend batch infers it by fetching the nearest expiry's snapshot rows and testing each option_ticker's root, copying Research's SQL rule into TypeScript; it reads one expiry only and costs two extra requests on names whose four option exhibits are all missing.
- **Measured**: CODE-READ 10-06: the rule lives in Research `not_adjusted_contract_sql` (27 call sites) and, on the wording branch, in frontend `adjustedListing.ts`; the plugin's `/market/options/snapshots` returns rows with option_ticker but no per-name counts. MEASURED 10-05: CUE 14 open-interest rows, all `CUE1…`.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/adjusted_contracts.py:20` — `def not_adjusted_contract_sql(column: str) -> str:`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/options.py:293` — `@router.get("/snapshots")`
  - `bifrost-trade-frontend` branch `fix/data-gap-wording` 7caac1f8 `src/pages/research/analyze/symbol/adjustedListing.ts:26` — `export function isAdjustedOptionTicker(…)` (copy of the Research rule)
- **Impact**: Two copies of one rule (Research SQL, frontend regex) can drift; the note covers only the nearest expiry; any other surface that wants the explanation has to repeat the probe.
- **Fix**: Serve per-name counts once: Research adds `standard_contracts` / `adjusted_contracts` for the latest session (from option_open_interest, using not_adjusted_contract_sql) to an existing per-name read the Symbol page already loads (dossier or options coverage), additive. Frontend reads those fields and deletes its own ticker test.
- **Ratchet**: A frontend ratchet that no file outside tests matches the adjusted-root regex once the field is served; Research test that the counts agree with not_adjusted_contract_sql on a fixture.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-frontend

### TD-160

**P3 · research-data · features.event_signal_radar_daily keeps the pre-rename copies of two indexes (event_radar_batch_collected, event_radar_importance) beside the current ones**

- **状态**：未开始
- **Claim**: The table was renamed from event_radar; ddl.py creates event_signal_radar_daily_batch_collected and _importance, but the old event_radar_batch_collected and event_radar_importance survived, so every write maintains two identical indexes each.
- **Measured**: MEASURED 10-06 (pg_indexes, read-only): event_radar_batch_collected 160 kB, event_radar_importance 152 kB beside event_signal_radar_daily_batch_collected 160 kB / _importance 152 kB; event_radar_pkey is the primary key (keep, name only).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/schema/ddl.py:1572` — `CREATE INDEX IF NOT EXISTS event_signal_radar_daily_batch_collected`
  - `bifrost-research/src/bifrost_research/schema/ddl.py:1578` — `CREATE INDEX IF NOT EXISTS event_signal_radar_daily_importance`
- **Impact**: Small today (~300 kB, double write cost on a low-volume table); the pattern (renames leave old indexes) repeats on bigger tables.
- **Fix**: Owner DDL step: DROP INDEX CONCURRENTLY features.event_radar_batch_collected, features.event_radar_importance (optionally rename event_radar_pkey).
- **Ratchet**: A schema check that lists indexes in research schemas whose definition duplicates another index on the same table (pg_index indkey + indpred equal) — warning in code-health or a db test.
- 审批 改表 · 代价 S · 风险 low · repos: bifrost-research

### TD-161

**P3 · ops-platform · BifrostAPIHighErrorRate / HighLatency only see bifrost-* namespaces with http_requests_total; research-api and the plugins export no HTTP metrics, so their 5xx and latency go unalerted**

- **状态**：未开始
- **Claim**: The two API alerts select http_requests_total in namespace=~"bifrost-.*". research-api (and the market-data / flex plugin APIs) export no http_requests_* series, so widening the namespace regex would change nothing; a research-api returning 5xx all night raises no alert.
- **Measured**: code-read 10-06 by paydown lane C (it checked the rule expressions against live Prometheus).
- **Evidence**:
  - `bifrost-trade-infra/k8s/monitoring/bifrost-alerting-rules.yaml:31` — `sum(rate(http_requests_total{namespace=~"bifrost-.*",status="5xx"}[5m])) by (namespace, service)`
- **Impact**: Research and plugin API outages are seen only by users or by indirect checks.
- **Fix**: Add the same HTTP middleware metrics to research-api and the plugin APIs (request count by status, latency histogram), then widen the two rules' namespace selector to research and plugin-.*.
- **Ratchet**: An alert-coverage test: every Deployment with a ServiceMonitor must export http_requests_total (checked against /metrics in CI or a release probe).
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research, bifrost-platform-plugin-market-data, bifrost-platform-plugin-flex-query, bifrost-trade-infra

### TD-162

**P2 · ops-platform · Research and plugin releases have no release window: sessions collide on pins and on deliver runs**

- **状态**：未开始
- **Claim**: release.sh window serializes Trade releases only. Research and plugin releases have no equivalent; on 10-06 a session started deliver-research for 0.185.0 while another waited on an ad-hoc lock in /tmp, and the S4 session built 0.187.0 while lane C built 0.188.0, leaving the pins two releases behind the images until the Owner approved one combined pin push.
- **Measured**: MEASURED 10-06: research 0.185.0 started via platform-api during another session's lock wait; 0.187.0 and 0.188.0 built back to back with one pin push (6cf4266).
- **Evidence**:
  - `bifrost-trade-infra/scripts/release/release.sh:2` — `# One entry for a Trade release (TD-84): STG from main, PROD pinned to an STG run, DEV catch-up.`
- **Impact**: Two sessions can ship over each other (pins pointing at an image that lacks the other's change, or a Dagster apply that drops one), and nobody can see who is releasing research right now.
- **Fix**: Extend release.sh window to cover research and the plugins (one window file, the repo in `what`), and have the deliver-research / build pipelines (and platform-api's start_pipeline_run) refuse while a window is held by someone else; document it in CLAUDE.md §5 next to the Trade window.
- **Ratchet**: deliver-research / plugin build PipelineRuns check the window as their first task (fail fast), the same way the Trade PROD pipeline checks its STG run.
- 审批 跨仓库发版 · 代价 M · 风险 med · repos: bifrost-trade-infra, bifrost-research, bifrost-platform

### TD-166

**P2 · research-data · GEX zero_gamma was the strike nearest spot on 38% of daily levels rows (no change of sign), and a step out of zero counted as a crossing; terrain read it as a flip at spot**

- **状态**：观察中（到 10-08，看 10-07 与 10-08 两次夜批后「验收」的重算结果仍为 0 变化）
- **Claim**: compute_gex_levels interpolated zero gamma wherever `prev_cum * cum <= 0`, so leaving zero counted as a crossing (an expiry whose low strikes carry no gamma "flipped" at the first strike that did), and without any crossing it stored the strike nearest spot. Nothing in the row said which. Terrain's pin score gives up to 40 points for spot near zero gamma, so a fallback at the nearest strike read as a pin.
- **Measured**: MEASURED 10-06, read-only on Golden Source (first written as "the 1,762 one-sided rows"; the real scope, measured before the fix, went back to the Owner, who chose A): of 69,440 daily levels rows, 26,518 (38%, 676 names) have no change of sign of cumulative net gex; 5,408 of those had a "crossing" out of zero; 360 more had a real crossing that a crossing out of zero beat on distance. Since 10-01, 565 of 2,040 front-expiry readings had no crossing. The old rule reproduces every stored value from the stored distribution (10,718 of 10,718 on three sample days).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:217` (before 0.192.0) — the `prev_cum * cum <= 0` test and the nearest-strike fallback
  - `bifrost-research/src/bifrost_research/engines/forecast/terrain.py:93` — pin_score_from_gex scores spot's distance to zero_gamma
  - `bifrost-research/src/bifrost_research/engines/scan/entry.py:105` — scan's zero_gamma_offset reads it
- **Fix**: research 0.192.0 (a53ee25, pin 0ed959f), Owner chose A on 10-06: `exposure_guards.zero_gamma_crossing` counts only a change of sign between non-zero cumulative values; `compute_gex_levels` says `zero_gamma_source` flip | nearest_strike; `drop_fallback_zero_gamma` stores NULL in daily levels without a crossing (intraday keeps the fallback, its timeline chart draws a missing value at zero). Readers checked for NULL: terrain, scan, mart_sepa_tier_options, sepa_fusion, exhibit lens, brief, frontend daily faces.
- **进展（10-06）**：Dagster 0.192.0-dagster 18:47 UTC apply。回填 Job `research-gex-zero-gamma-0192`（`zero_exposure_purge --zero-gamma`，从分布逐行重算）：更新 26,878 行（置空 26,518，换成真实翻转点 360），terrain 重算 4,526 行，scan 重算 6,810 行，45 秒。核对：重跑干跑 0 变化；空 zero_gamma 26,518；scan 与 terrain 一致；TD-136 / TD-157 的检查仍为 0。影响：terrain pin_score 有 3,389 行变化，其中 3,382 行下降，中位 −32 点；regime 翻转 338 个（range→trending 290）；scan 的 zero_gamma_offset 有 5,391 行变空，综合分 5,489 行变化，中位 −6.9。备份（三张整表）`~/bifrost-backups/golden-source/2026-10-06_gex-zero-gamma-td166/`。防线：`tests/engines/test_gex_zero_exposure.py` 的 TD-166 用例（签收时登记进 RATCHETS.md）。后续：前端可把空的 zero-γ 写成「无翻转」（未立项，Product）。
- **Ratchet**: tests/engines/test_gex_zero_exposure.py (leaving zero and touching zero are not crossings; the nearest crossing wins; daily rows store NULL without one; the pass counts read-only and refuses a mismatched update).
- **验收**: `python -m bifrost_research.engines.gex.zero_exposure_purge --zero-gamma` (dry run, read-only) reports `changed: 0` after two nightly runs.
- 审批 已批（Owner 10-06，选 A）· 代价 M · 风险 med · repos: bifrost-research

### TD-169

**P3 · market-data · ops_jobs.ingest_freshness.option_expiration is a fossil row frozen since 09-06 and still listed as ok**

- **状态**：观察中（到 10-07 00:20 UTC option-refresh 之后，看 option_expiration 行被写）
- **验收**：`SELECT last_run_at FROM ops_jobs.ingest_freshness WHERE dimension='option_expiration'` ≥ 2026-10-07 00:20 UTC（现在仍是 2026-09-06 12:58）
- **现在**：market-data 0.80.0（8e39aab）：option_contract 在写了 expiration 时返回 `freshness_extra={'option_expiration': n}`；防线 `tests/test_freshness_writers.py`：表里与 contracts / SLOT_EVIDENCE / quality 读到的每个维度都必须有现行写入方
- **Claim**: Expirations now come from option_contract jobs, which return no freshness_extra for option_expiration, so the row has not moved since 2026-09-06; nothing polices it, yet freshness listings show it with status ok.
- **Measured**: MEASURED 10-06 by paydown lane D (ingest_freshness row last_run_at 2026-09-06).
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/ingest/option_contract.py:1` — `option_contract handler (no freshness_extra for option_expiration)`
- **Impact**: A frozen 'ok' row in a freshness view teaches readers to ignore staleness.
- **Fix**: Either emit freshness_extra={'option_expiration': n_exp} from option_contract, or delete the row (the delete is a data write: Owner).
- **Ratchet**: A freshness test: every dimension listed in ingest_freshness must have a current writer (kind → dimension map).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-170

**P3 · research-control · dagster-daemon logs one line over 256 KB at the 22:45 and 03:00 UTC schedule ticks every night**

- **状态**：未开始
- **Claim**: Some logger call in the Dagster daemon / run path writes a single line larger than Loki's 256 KB max_line_size each night (probably a whole result object). Until 10-06 Loki rejected it with 400 and promtail dropped the whole batch (TD-152); from 10-07 promtail truncates it to 250 KB.
- **Measured**: MEASURED 10-06 by paydown lane H: 12 promtail 'final error sending batch status=400 max entry size 262144 bytes exceeded' lines 09-28..10-06, all for stream {namespace="research", app="dagster-daemon"}; 03:00 runs include market_fundamentals_rotate_job, research_forecast_job, research_event_radar_job. No file:line yet: the line never reached Loki and the daemon restarted ~18:30Z 10-06.
- **Evidence**:
  - `bifrost-trade-infra/scripts/k3s/values-promtail.yaml:25` — `max_line_size_truncate: true`
- **Impact**: A 256 KB log line is unreadable and costs Loki ingestion; any future truncation hides whatever is at its tail.
- **Fix**: After 10-07 find the truncated line in Loki (`{namespace="research", app="dagster-daemon"}` with promtail_mutated_entries_total line_too_long), trace it to the logger call and log a summary (counts, ids) instead of the object.
- **Ratchet**: A test or log filter in research that caps log message length (e.g. a logging.Filter that truncates over 16 KB and counts it), plus the existing promtail mutated-entries metric.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-171

**P3 · frontend · Positions shows the attribution price_last as if it were live: no EOD label or date now that core 0.51.0 fills it from the vendor EOD mark**

- **状态**：观察中（到 10-07 Trade 发版——core 0.51.0 上线后，看 Positions 上 vendor 收盘价的腿标 EOD MM-DD）
- **验收**：发版后 DEV：`curl -s http://192.168.10.73:30882/api/account/executions/position-attribution | python3 -c "import sys,json,collections;it=json.load(sys.stdin)['items'];print(collections.Counter(r.get('mark_source','<absent>') for r in it))"` 出现 vendor_eod；:5173 Positions Trade 视图展开分组，vendor_eod 的期权腿 UN PNL 后缀为 `EOD MM-DD`
- **现在**：frontend 4860e7cd 已推 main：`attributionMark` 只在价格取自 attribution 行时带上 mark_source / mark_date；`eodMarkLabel` 给出 `EOD MM-DD`（沿用 TradeRecord 的格式）；TradeOptionSubTable 的 UN PNL 后缀与 OptionContractDetail 的警告用它。门禁 tsc / lint / vitest 4022 passed / build / legacy-css / code-health 全 0，未调基线。防线 `src/utils/buildTradeGroups.test.ts` 4 个新用例。DEV 现在 30/30 行无 mark_source，页面与今天一样
- **Claim**: core 0.51.0 (TD-140) fills price_last from the newest vendor_eod snapshot mark when there is no live quote and labels each row mark_source / mark_date. The frontend type has only price_mid / price_last and buildTradeGroups falls back to price_last without saying it is a dated close.
- **Measured**: code-read 10-06 by paydown lane I.
- **Evidence**:
  - `bifrost-trade-frontend/src/types/positions.ts:107` — `price_last: number | null`
  - `bifrost-trade-frontend/src/utils/buildTradeGroups.ts:124` — `: a.price_last != null && Number.isFinite(Number(a.price_last))`
- **Impact**: Under D10 every attribution price is an EOD close; a reader cannot tell yesterday's close from a live mark.
- **Fix**: Add mark_source / mark_date to the attribution type (and the zod schema); where price_last is shown or used as the mark, tag it EOD with the date.
- **Ratchet**: A vitest on buildTradeGroups: a row with mark_source vendor_eod yields a mark labelled EOD with its date.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-172

**P2 · research-data · ATM IV has almost no 50–90 DTE expiry from 2026-07-06 to 09-25 (the EOD chain stopped at the third listed expiry until plugin 0.39.0); the fix was forward-only, so term structure reads na for that stretch**

- **状态**：未开始
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -At -c "WITH d AS (SELECT symbol, trade_date, bool_or(expiry - trade_date BETWEEN 50 AND 100) b FROM features.option_metric_atm_iv_daily WHERE trade_date BETWEEN '2026-07-06' AND '2026-09-25' AND symbol IN (SELECT symbol FROM research.option_universe) GROUP BY 1,2) SELECT date_trunc('week', trade_date)::date, round(avg(b::int), 2) FROM d GROUP BY 1 ORDER BY 1"` — every week ≥ 0.85 (06-22/06-29 read 0.88–0.91; 07-06..09-21 read 0.02–0.59 before the fix)
- **Claim**: Until market-data plugin 0.39.0 (2026-09-25, `54b05be`) the EOD chain was bounded at the third listed expiry, so from 2026-07-06 most names' option_daily held nothing past ~45 DTE. ATM IV is solved from option_daily (Brent) and the reconstructed table, so its 50–100 DTE expiries went missing with it. 0.39.0 fixed the bound forward only; nothing refilled the stretch. IV30 is unaffected (about 640 names a day throughout).
- **Measured**: MEASURED 10-06 (S6 context survey, `REPORT-pine-s6-context-series-2026-10-06.md`). Share of universe name-days with an ATM IV at 50–100 DTE, by week: 06-22 0.88 · 06-29 0.91 · 07-06 0.15 · 07-13 0.12 · 08-03 0.02 · 08-10 0.02 · 08-24 0.35 · 09-14 0.43 · 09-21 0.59 · 09-28 0.97. option_daily itself with a 50–90 DTE bar: 06-22 0.99 · 07-06 0.25 · 08-10 0.005.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/atm_iv.py:366` — `AND (o.expiry - o.bar_date) BETWEEN {DTE_MIN} AND {DTE_MAX}`
  - `bifrost-research/src/bifrost_research/engines/pine/context.py` — `TERM_30_60` reads na without a 50–120 DTE expiry (Owner 10-06: no stitching from SVI)
  - market-data plugin `54b05be` — "The EOD chain's bound was the third listed expiry"
- **Impact**: Pine `TERM_30_60` (S6) and every term-structure reader (`/atm-iv/term`, the 60-day cone) are blank or one-sided for 12 weeks, which is part of the S6 out-of-sample window (2026-01..10); a contango condition loses that stretch.
- **Fix**: List the range for the Owner first (names × sessions × contracts). Then (a) the plugin re-pulls option_daily bars for the 50–90 DTE contracts of 2026-07-06..09-25 from the vendor's history (Options Starter has two years), and (b) Research recomputes ATM IV for those sessions; from 08-05 the 16:00 snapshots are a second source if the bars stay thin. Writes raw_market.option_daily (plugin) and features.* (Research) only.
- **Ratchet**: The plugin doctor's option_daily breadth (0.59.0 counts 5–90 DTE) also counts names with a 50–90 DTE bar per session and warns below 0.8 of the trailing median, so a bound that stops short shows within a day.
- 审批 要你批 · 代价 M · 风险 low · repos: bifrost-platform-plugin-market-data, bifrost-research

### TD-173

**P2 · infra · ubt-k3s-06 has no nfs-common: pods with an NFS volume scheduled there hang in ContainerCreating (mount exit 32)**

- **状态**：未开始
- **Claim**: 06 was reinstalled 10-06 and is not in install-nfs-common-nodes.sh DEFAULT_NODES. market-data-api mounts market-data-archive (nfs-cold); twice on 10-06 its new pod landed on 06 and failed `mount failed: exit status 32`.
- **Measured**: MEASURED 10-06 by paydown lane J: on 192.168.10.79 `dpkg-query: package 'nfs-common' is not installed`, /sbin/mount.nfs absent; two FailedMount rollouts 19:08 and 19:11 UTC (lane J cordoned 06 ~10 s each time to reschedule, then uncordoned).
- **Evidence**:
  - `bifrost-trade-infra/scripts/k3s/install-nfs-common-nodes.sh:17` — `DEFAULT_NODES=(`
- **Impact**: 06 is the emptiest node so the scheduler prefers it; an evicted market-data-api (or any NFS-mounting pod) lands there and stays down — Dagster enqueue and the Trade gateway answer 503.
- **Fix**: Owner runs `K3S_NFS_NODES="vision@192.168.10.79" ./scripts/k3s/install-nfs-common-nodes.sh`; add .79 to DEFAULT_NODES.
- **Ratchet**: install-agent preflight installs or checks `dpkg -s nfs-common`; plus a FailedMount warning alert (kube_pod_container_status_waiting_reason ContainerCreating > 10m with FailedMount events).
- 审批 要你批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-174

**P3 · market-data · Console marks fundamentals-rotate missed every Monday 03:45 → Tuesday 03:00 UTC: the trading-day check uses the UTC date of the fire**

- **状态**：在做（代码在 main 767a5ac = market-data 0.81.0，镜像已建 digest 92af622d…；等你批发布）
- **下一步**：你批 market-data 0.81.0 发布（避开 21:05–23:15 UTC）→ deploy 提交 + `kubectl apply -k` → 验收：pod imageID 为 92af622d…、queue-dashboard 里 ticker-details 读 `slot:ticker-details`；10-12 周一 03:45 之后 fundamentals-rotate 仍 on_plan
- **现在**：按纽约日期判交易日，三处都改（`_slot_adherence` 的 trading_last、`_previous_expected_fire` 的 last / prev——只改 727 行会在后者里照样记 missed）。只读回放 09-29→10-06 六个 slot 12,102 个时点：翻转 288 个，全是 fundamentals-rotate 周一 03:05→周二 03:00 的假 missed。防线 `tests/test_ingest_dashboard.py` 三个用例（两条在老代码上失败）
- **Claim**: _slot_adherence asks is_trading_day(conn, cron_last.date()) on the UTC date; Monday 03:00 UTC is Sunday in New York, the slot rightly enqueues nothing, and the dashboard calls it missed. Platform's market_batch lane reports the miss once a week.
- **Measured**: MEASURED 10-06 by paydown lane J (replay): 280 of 2017 five-minute instants over 7 days, identical on old and new code.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/ingest_dashboard.py:727` — `trading_last = is_trading_day(conn, cron_last.date())`
- **Impact**: A weekly false miss trains readers to ignore the Data Husbandry market_batch lane.
- **Fix**: Judge the trading day on the New York date of the fire, as doctor's _closed_days_since does.
- **Ratchet**: A dashboard test: a Monday 03:00 UTC fire is not missed.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-175

**P3 · market-data · ticker-details adherence still credits the shared ticker_sync freshness row, so a stopped ticker-details reads on_plan after reference's 21:30 walk**

- **状态**：在做（代码在 main 767a5ac = market-data 0.81.0，镜像已建 digest 92af622d…；等你批发布）
- **下一步**：你批 market-data 0.81.0 发布（避开 21:05–23:15 UTC）→ deploy 提交 + `kubectl apply -k` → 验收：pod imageID 为 92af622d…、queue-dashboard 里 ticker-details 读 `slot:ticker-details`；10-12 周一 03:45 之后 fundamentals-rotate 仍 on_plan
- **现在**：ticker-details 加进 `SHAPE_NAMED_SLOTS`（不进 `POLICED_SLOTS`，避免新增 doctor finding）：只数自己的 `ticker_sync mode=detail` 作业，读新的 `slot:ticker-details` 行。回放 0 翻转；反事实删掉 detail 作业后新代码在 72 个时点判 missed、老代码判 on_plan。防线 `tests/test_slot_freshness.py` 新增 4 条（老代码上失败）+ `test_naming_ticker_details_adds_no_doctor_finding`
- **Claim**: Mirror of TD-167 for the one slot outside the policed list: ticker-details and reference both enqueue ticker_sync and both bump freshness.ticker_sync.
- **Measured**: code-read 10-06 by paydown lane J.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/ingest_dashboard.py:93` — `"ticker-details": {"kinds": ["ticker_sync"], "freshness": "ticker_sync"},`
- **Impact**: If ticker-details stops, the Console and the market_batch lane keep calling it on plan.
- **Fix**: Give ticker-details its own slot:<id> freshness row and job-shape filter like the five policed slots (or add it to POLICED_SLOTS).
- **Ratchet**: Extend tests/test_slot_freshness.py: ticker-details stopped while reference runs → missed.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-176

**P3 · research-control · Suspended CronJobs cronjob-signal-hit.yaml and cronjob-alert-scan.yaml still ship and get re-pinned every release though Dagster runs both**

- **状态**：未开始
- **Claim**: Both engines run inside research_trading_day (alert_scan since TD-97, signal_hit since TD-156); the suspended CronJob manifests have no runtime effect but every release bumps their image pins.
- **Measured**: code-read 10-06 by paydown lane G1.
- **Evidence**:
  - `bifrost-research/k8s/engines/cronjob-signal-hit.yaml:14` — `suspend: true`
  - `bifrost-research/k8s/engines/cronjob-alert-scan.yaml:15` — `suspend: true`
- **Impact**: Dead manifests suggest a second scheduler exists; someone unsuspending one would run the engine twice.
- **Fix**: Delete both manifests (and their kustomization entries) once Owner approves.
- **Ratchet**: A research test: no CronJob manifest names an engine that Dagster also runs (read from the roster).
- 审批 删除（要你批） · 代价 S · 风险 low · repos: bifrost-research

### TD-177

**P3 · frontend · No way to create a plan from a hypothesis: PlanThisButton writes source_kind 'symbol' and PlanForm takes a hand-typed slug, so TD-143's hypothesis → trade link never forms**

- **状态**：待你签收
- **验收**：`git -C bifrost-trade-frontend grep -n hypothesisPlanHref origin/main -- src/pages/research/loop/HypothesisBoardPage.tsx` 命中；`npx vitest run src/pages/research/loop/HypothesisBoardPage.plan.test.tsx` 3 passed
- **验收结果**：PASS 2026-10-06 frontend 0e0b69a3（main 0e0c9637）；本地 Vite 上点「＋ Plan」进入 `/trade/plans?new=1&source_kind=hypothesis&source_ref=<id>&symbol=QQQ`，表单预填正确，未写任何 plan（假设列表用编造数据：research 读接口要 research user）
- **Claim**: TD-143 derives hypothesis → trade from filled plans with source_kind='hypothesis' and source_ref = the hypothesis id. Nothing in the UI writes such a plan; on 10-06 dev / stg / prod each had 0.
- **Measured**: MEASURED 10-06 by paydown lane G2: 94 hypotheses per env, 0 hypothesis-sourced filled plans.
- **Evidence**:
  - `bifrost-trade-frontend/src/components/research/PlanThisButton.tsx:63` — `source_kind: 'symbol',`
- **Impact**: Review › Objectives breaks at `traded` for every objective; the hypothesis hit rate can never be measured.
- **Fix**: A Plan action on the hypothesis card that pre-fills source_kind='hypothesis' and source_ref=<id>.
- **Ratchet**: A vitest: the hypothesis card's Plan action submits source_kind hypothesis with the card's id.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-178

**P3 · trade-api · GET /strategies/plans has no source_kind filter: Research reads the newest 500 filled plans and filters itself, marking truncated at the cap**

- **状态**：未开始
- **Claim**: TD-143's read-time link pulls status=filled&limit=500 and filters source_kind='hypothesis' in Research; once filled plans approach 500 the oldest links drop out (flagged truncated, not silent).
- **Measured**: code-read 10-06 by paydown lane G2.
- **Evidence**:
  - `bifrost-trade-api/src/bifrost_api/strategy/routers/plans.py:70` — `def list_plans_endpoint(`
- **Impact**: Links silently age out of reach as the plan book grows (the truncated flag says so, but the link is gone).
- **Fix**: Additive `source_kind` (and `source_ref`) query params on core list_plans and the api route; Research passes them.
- **Ratchet**: An api test: source_kind=hypothesis returns only those plans and keeps the 500 cap per filter.
- 审批 改公开接口 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-api, bifrost-research

### TD-179

**P3 · frontend · Stock screen with No model cannot sort by Earnings: RankDrawer still disables it although the batch read now serves the dates**

- **状态**：待你签收
- **验收**：`npx vitest run src/pages/research/stocks/stockScreenEarnings.test.ts src/pages/research/stocks/RankDrawer.test.tsx` 4 passed；`/research/stocks?model=none` Sort 选 Earnings
- **验收结果**：PASS 2026-10-06 frontend 0e0c9637；本地 Vite 连 DEV 真数据：3,794 名「by next print」，逾期在前（AEHR / STZ 1d late），有日期的 527 名后接 3,267 名「—」按 A–Z
- **Claim**: TD-158 made earnings dates available for the whole list; the No-model branch never sorts by them and RankDrawer keeps the option disabled (its hint now says so honestly).
- **Measured**: code-read 10-06 by paydown lane G2.
- **Evidence**:
  - `bifrost-trade-frontend/src/pages/research/stocks/RankDrawer.tsx:124` — `disabled: true,`
- **Impact**: A reader cannot rank a screen by the nearest earnings without picking a model.
- **Fix**: In StockScreenPage's model==='none' branch sort by data.earnings daysAway and pass the sort state to RankDrawer.
- **Ratchet**: A vitest: No model + Earnings sort orders names by days to the expected date, unknown last.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-180

**P3 · research-data · The macro calendar has no CPI dates after 2026-12-10 and no payrolls at all: bls.gov answers 403 from this host, so they could not be read**

- **状态**：未开始
- **Claim**: TD-151's seed file carries FOMC through 2027 but CPI only for three 2026 releases (copied from a hand-dropped file) and no Employment Situation dates.
- **Measured**: MEASURED 10-06 by paydown lane O: bls.gov returned 403 to the Mac; federalreserve.gov answered.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/scheduler/data/macro_calendar.csv:35` — `2026-12-10,08:30,US,CPI,November 2026`
- **Impact**: From 11-05 the asset check warns; from 12-10 the forward calendar has no CPI and never had payrolls.
- **Fix**: Someone who can open bls.gov adds the 2027 CPI and Employment Situation schedules to the CSV.
- **Ratchet**: Already in place: the macro_calendar asset check warns when any series has under 30 days left.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-181

**P3 · research-data · /events/calendar takes its macro rows from a hand-dropped radar file (ends 2026-12-10) instead of macro_event_daily, and radar ids include the collection date so a re-drop duplicates them**

- **状态**：未开始
- **Claim**: Two macro paths exist: features.macro_event_daily (TD-151) and event_signal_radar_daily rows with source ws:macro-calendar-2026q4. The calendar page reads the latter; _stable_id hashes the collection date, so each weekly re-drop writes new ids for the same events.
- **Measured**: code-read 10-06 by paydown lane O.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/event_radar/pipeline.py:172` — `def _stable_id(source: str, collected: date, idx: int, text: str) -> str:`
- **Impact**: The calendar loses macro events after 12-10 and can show the same release twice.
- **Fix**: Have /events/calendar read macro rows from macro_event_daily and retire the ws:macro radar file, or give radar a macro writer with a date-free stable id.
- **Ratchet**: A research test: /events/calendar macro rows equal macro_event_daily for the window.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-182

**P3 · research-data · Macro gap (actual vs expected) is always empty: consensus is not in the subscription, and the entitled /fed/v1/inflation actuals have no raw table**

- **状态**：未开始
- **Claim**: The MacroPanel gap view needs expected and actual. Consensus estimates are not entitled (entitlement gap: accept and name it). Actuals for inflation are entitled via Massive /fed/v1/inflation but the plugin has no raw table for them. The front-end empty state still blames a CSV forward_flag.
- **Measured**: MEASURED 10-06 by paydown lane O: /macro/gap 0 rows; Benzinga 403; /fed/v1/inflation entitled.
- **Evidence**:
  - `bifrost-trade-frontend/src/components/research/EventRadarDashboard.tsx:213` — `'Forward releases appear when macro CSV includes forward_flag rows',`
- **Impact**: Readers see an empty panel with a wrong explanation.
- **Fix**: Now: change the empty-state copy to name the entitlement gap. Later (Owner): a plugin raw table for /fed/v1/inflation actuals feeding macro_event_daily.actual.
- **Ratchet**: None feasible for the gap itself (entitlement); the copy fix is covered by the existing EventRadarDashboard tests once updated.
- 审批 改表（要你批） · 代价 S · 风险 low · repos: bifrost-trade-frontend, bifrost-platform-plugin-market-data, bifrost-research

## 没覆盖到的（下一轮从这里开始）

- Per-engine numerical correctness beyond dates: GEX sign conventions, max-pain, VRP realized-vol windows, vanna/charm, SVI fit, flow maths
- EXPLAIN/plan stability of large raw_market reads by engines (option_snapshot, option_daily, option_open_interest); Dagster/dbt runtime cost (mart_sepa_tier_structure 144s, int_stock_daily_enriched 100s)
- research repositories/* write paths (copilot, journal, hypothesis, playbook) idempotency; copilot harness/agents and LLM provider failure paths; MCP write-tool approval-token validation (copilot/approvals.py)
- research-api read-side routes and their date defaults (api/pine.py, api/opex_cycle.py use date.today()); request-path performance and statement_timeout; callers outside the four consumer repos (Hermes on .50/.52, ad-hoc curl, Cowork)
- signal_hit_fwd_fill ordering inside research_trading_day (may read tonight's sources before they are written; self-heals next night; not measured); event_radar collected_at date basis judged intentional, not verified
- D13 grants: analytics_writer INSERT on ops_jobs.* and CREATE on raw_market/raw_broker; flex-query and market-data DB user switch to flex_writer/data_writer: all belong to open TD-85, not re-reported
- Plugin-side root cause of missing OI for NVR/GRML since 08-01 and QRVO stock_daily stopping at 10-02 (market-data plugin not opened for this)
- Market-data: retention_archive first real export (NFS behaviour, 768Mi API pod memory, serialization vs option-bars upserts); doctor internals beyond staleness/failed sections; Polygon rate limiting/429; per-symbol handlers, sec_filings, symbol_rename/void; plugin iv-percentile/atm-iv/pcr reads vs Research endpoints; dynamically built partition indexes
- IB Gateway live.py internals and ib_ops.py fill capture (D10-adjacent, skimmed only); live redis-ib ACL contents (needs admin password; Loki showed 0 NOPERM/WRONGPASS in 24h); DEV/STG /ops/market-ingest/services; Flex XML upload path and manual-trigger fallback; Flex token rotation scripts (handle secret values)
- core get_net_cash_flow semantics (round-1 Trade read domain); scripts/ one-off migration files in research; pine-runner NetworkPolicy; Loki logs for research-api/dagster; two RUNNING Dagster instigators (selector 8da707eb…) not resolved to names
- TD-96 (preflight bypass forms) and TD-109 (stale PROD ops-context copy) come from the ratchet-inventory pass and were not adversarially re-verified; whether any runtime consumer other than Console reads the stale copy was not checked
- 第 1 轮未覆盖项见 git 历史中本台账前身（artifact 版本 ≤ 48）。尚未扫描的领域：Ops 平台（bifrost-platform）、前端 UI 层、数据层（备份 / NFS / Secret）。

## 怎么做的

第 2 轮（2026-10-06）：10 个 Agent，约 35 分钟，全程只读（数据库只做 read-only 查询）。代码读的是各仓库 origin/main 的干净副本：research 6ed86ad · market-data acba67e · flex f7b5cd9 · IB gateway 插件 39eafe2 · infra d5aa457 · core 756bdb5。四个领域各一个盘点 Agent（Research 数据面、Research 控制面、market-data、flex + IB gateway），每个领域的发现交给一个专门反驳的 Agent 去推翻；另一个 Agent 清点现有防线并对照第 1 轮的各类债；最后一个 Agent 去重、排序、提出待建防线。40 条发现：22 条原样成立，18 条改了说法或优先级，0 条被推翻，3 条合并。之后日常工作里发现的直接加入（TD-127–129 来自 Pine 线程）。
第 1 轮（2026-10-01，Trade UI 之下）的原文在台账页 artifact 版本 ≤ 48 和 git 历史里。
