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

（无）

**未结 80 项**：P0 0 · P1 5 · P2 28 · P3 47；要你批的 38 项（从总览表的审批列算）。

## 主题（第 2、3 轮）

- **Green while wrong: jobs succeed on zero, partial or garbage output** — The dominant round-2 class. Engines, gates, ingest handlers and writers convert failures into success: empty lists read as answers, exceptions become 0 or 'unknown', truncation is a field nobody checks, freshness bumps on zero-row jobs. Dagster and Flex show green; only manual metadata reading finds it. Fix pattern: raise or record reasons, and add output checks per asset. (TD-91, TD-92, TD-93, TD-94, TD-97, TD-100, TD-101, TD-106, TD-113, TD-116)
- **Session and calendar truth comes from the wall clock on UTC pods** — Session dates are derived from current_date/date.today() on UTC hosts at 02:30 UTC, producing next-day and Saturday stamps (SEPA, option_universe), a day-late alert judge, and a calendar that silently forgets holidays on a failed read. One session_today() helper plus a nightly session-date sweep closes the class. (TD-87, TD-98, TD-93, TD-97, TD-111)
- **Broker money ledger integrity (Flex / IB)** — The cash and commission ledgers have a 5-month hole the fixed window cannot refill, a writer that reports failure as success, a dedupe key that ignores IB's own id, mixed commission signs, DEV-routed reads and no tests on the money path; the gateway health signal is permanently false-red. (TD-91, TD-103, TD-114, TD-115, TD-116, TD-117, TD-104, TD-122)
- **Gates that do not gate** — CI runs after delivery and never blocks it (research and Trade); plugins and infra have code-health baselines but no CI; preflight D10 matching misses non-curl clients and in-place edits; operator streams use a denylist; no alert watches Dagster schedules or research/plugin 5xx. Making CI gate release is the single highest-leverage ratchet. (TD-95, TD-96, TD-105, TD-99, TD-109)
- **Hand-kept copies and dead config drift** — Schedule rosters, max-pain/PCR math, Black-Scholes and risk-free readers, declared indexes, spine copies, instance configs and suspended CronJobs exist in several places that have drifted from the source of truth. Generate from one source or delete; ratchet with manifest and catalog checks. (TD-108, TD-102, TD-110, TD-107, TD-112, TD-118, TD-119, TD-120, TD-121, TD-123, TD-124, TD-125)
- **The control plane is open to the LAN with no credentials (round 3)** — An SSH shell (platform-api /console/ws), whole-tree commit and push (git-bridge), agent start and approval (remediation runner, Hermes), checklist dispatch, and PROD daemon control (Redis NodePort) all answer anonymous LAN callers. The Mac firewall is off and the services bind 0.0.0.0. No test enumerates routes for auth, so the class recurs with each new route. (TD-203, TD-205, TD-206, TD-207, TD-208, TD-220, TD-225)
- **Over-privileged identities and duplicated actuators (round 3)** — STG and PROD platform run as system:masters through a copied admin kubeconfig. The D10 scale guard covers only 0→n. Two environments each run IB gateway auto-repair against one live gateway. The runner can switch the PROD gateway to mock behind a prompt-only approval. Page views start full-auto agents without server-side dedupe. The governance catalog contradicts the signed D-IB-Heal. (TD-204, TD-221, TD-222, TD-223, TD-224, TD-231)
- **Unknown, failed or unmeasured shown as green (round 3)** — Alerts are delivered to a memory-only webhook that nobody reads. Launch and release-gate verdicts pass on unknown, the mission snapshot keeps stale verdicts, Hermes reports ok while every skill fails, IV-radar errors read as 'no data', trust overrides swallow store errors, and the daemon drops its INFO logs and has no freshness alert. (TD-209, TD-215, TD-216, TD-226, TD-227, TD-228, TD-229, TD-230, TD-233)
- **Broker book and P&L readings are wrong on screen (round 3)** — Working orders are truncated to empty every hour and shown as 'none at IB'. A degraded IB snapshot wipes positions and NAV. Risk › Limits daily loss is lifetime P&L. Performance ranges start at UTC midnight. The rail's fired-alerts count is always 0. 24 frontend sites read tomorrow's date after 20:00 ET. (TD-211, TD-212, TD-213, TD-214, TD-219, TD-232)
- **Recoverability and release-chain hygiene (round 3)** — The nightly logical backup loses a NetworkPolicy race. Barman has never been restored and was not tried against the new NAS endpoint. Every backup sits on one NAS. The live Redis instances claim a persistence they lack. A phantom MinIO has a public placeholder Secret. The Console ships an unpinned @bifrost/ui, the ui build deletes dist under live dev servers, and dead stream and export surface lingers. (TD-210, TD-217, TD-218, TD-234, TD-235, TD-236, TD-237, TD-238, TD-239)

## 先看这几条

- **TD-91** — 现金流水写库失败被记成「成功、0 行」。TD-88 刚补完五个月的洞，这个写入方再静默失败一次，新的覆盖告警要到月底才响。
- **TD-92** — Research 的引擎资产永远是绿的：按标的失败、0 行写入、跳过都只进元数据。TD-89 停了三天没人发现就是这一类。
- **TD-95** — 没有任何发布等 CI：research 0.172–0.174 是在 CI 红着的时候发的，trade-api main 从 10-04 起 CI 是红的，三个插件仓库自 09-29 起 32 次提交 0 次 CI。`RATCHETS.md` 里的测试类防线在这之前都只是提醒。

- **TD-130** — 真正在生产数据层上动手的 Ops 自动修复跑在 Owner 的笔记本上（本机 bdev 的 platform-api），集群里 STG/PROD 那两份在空转；10-05 到 10-06 对备份 MinIO 的重启和补备份都是它做的。

## 还债顺序

### 第 0 波 · 第 1 轮收尾

目标：第 1 轮剩下的三项按已排的日期收掉。TD-85 剩 Golden Source 的 PUBLIC CONNECT；TD-51 等 Loki 闸门后随下一次 Trade 发布；TD-80 C2-b 改号 core 0.49.0 与 TD-51 同发。

项：TD-85 · 已还：TD-21, TD-51, TD-80

### 第 1 波 · 正在出错的数据与「绿着的失败」

目标：先让失败变红。错数据先修数据（TD-87 restate），再把引擎、闸门、写入方从「出错也报成功」改成失败即失败：引擎资产按输出判定、husbandry gate 失败即关、日历读失败报错、写入方失败抛错。不需要 Owner 批的先做。

项：TD-91, TD-92, TD-94, TD-97, TD-101, TD-156, TD-189, TD-192, TD-244 · 已还：TD-88, TD-89, TD-90, TD-113, TD-93, TD-165, TD-167, TD-87, TD-245, TD-136, TD-157, TD-166

### 第 2 波 · 让闸门真的卡住

目标：一个开关让所有测试类防线生效（CI 卡发布），再补上调度存活告警、D10 闸门的非 curl 写法、operator 流白名单、本机常驻任务和密钥轮换的盲区、spine 副本同步。

项：TD-95, TD-100, TD-121, TD-152, TD-153, TD-155, TD-162, TD-293, TD-294, TD-295 · 已还：TD-99, TD-161, TD-198, TD-195, TD-194, TD-249, TD-109, TD-105, TD-96

### 第 3 波 · 交易日与日历只有一个来源

目标：所有「今天 / 本 session」都从 `db/calendar` 的一个函数来，代替 11 个私有 helper 和 44 处 `date.today()`；dbt 补 grain 测试；IV / 回测的定价参数统一。

项：TD-98, TD-110, TD-111, TD-112, TD-128, TD-129, TD-174, TD-242 · 已还：TD-164, TD-175, TD-247

### 第 4 波 · 券商资金账本（Flex / IB）

目标：现金与佣金账本可信：按 IB transactionID 去重（改表）、佣金一种符号、资金路径有测试、Flex 不再经 DEV 库读配置、IB Gateway 健康与镜像可追溯。

项：TD-117 · 已还：TD-115, TD-116, TD-114, TD-122, TD-104, TD-103

### 第 5 波 · 副本、死重与清单

目标：删掉没人用的（挂起的 CronJob、退役脚本、无调用路由），手抄的副本改成从一处生成（调度名单、max-pain / PCR），清单的应用顺序与 Argo 归属理顺。

项：TD-118, TD-120, TD-170, TD-202, TD-290, TD-291 · 已还：TD-126, TD-108, TD-154, TD-163, TD-168, TD-124, TD-176, TD-191, TD-169, TD-200, TD-201, TD-190, TD-123, TD-106, TD-119, TD-125, TD-102, TD-160, TD-107

### 第 6 波 · 备份链与自动修复（10-06 日常发现）

目标：备份 MinIO 已搬到 NAS（infra 1ee0ac2，已接监控 ba03488），把剩下的收尾：自动修复只在 PROD 一处动手、失败记录不再被删、platform 的新检查上线、稳定一周后退役集群里的 MinIO 残留，再处理 WAL 体量和 CNPG 1.30 的备份插件。

项：TD-133, TD-134, TD-135 · 已还：TD-197, TD-173, TD-132, TD-131

### 第 7 波 · 数据缺口（10-06 由 Data Gaps 看板并入）

目标：Data Gaps 看板上未结的 15 项并入台账：先把每日快照的写入修对（TD-137）再接读侧和三页，归因行补上价格，Research 侧已就绪的一个版本（0.185.0）发出去，长期限 IV 锥在 10-31 前从 option_daily 回填，其余按 Owner 已定的口径排。

项：TD-137, TD-142, TD-143, TD-144, TD-146, TD-149, TD-158, TD-159, TD-172, TD-180, TD-246, TD-250, TD-274 · 已还：TD-141, TD-147, TD-177, TD-179, TD-151, TD-181, TD-193, TD-140, TD-171, TD-138, TD-139, TD-178, TD-199, TD-243, TD-182, TD-148, TD-145, TD-150

### 第 8 波 · Pine 线程收尾后的跟进（10-06）

目标：Pine 与路线图那条线（会话「Pine 信号业务与实现」）收尾时留下的日后核对：W3 两次真正的归档、一个只差发布的前端修复、路线图台账的月度重评、「我的价位」等 Design、auto mode 规则重新应用。

项：TD-183, TD-184, TD-185, TD-186, TD-188 · 已还：TD-187

### 第 9 波 · 控制面对局域网敞开（第 3 轮，10-07）

目标：先关门再修代码。本机 platform-api 只监听本机、PROD/STG Redis 的局域网 NodePort 删掉，然后 git-bridge、修复 runner、Hermes、husbandry-sync 都要令牌；platform 换成按需授权的 ServiceAccount，停用管理员 kubeconfig；路由鉴权测试卡住回退。

项：（无） · 已还：TD-205, TD-203, TD-224, TD-220, TD-231, TD-225, TD-222, TD-207, TD-221, TD-206, TD-208

### 第 10 波 · 告警有人收、备份能恢复（第 3 轮）

目标：数据层告警有一个人能收到的通道和外部心跳；逻辑备份先修好等库就绪；做一次 Barman 恢复演练；决定异地副本；daemon 停写与日志丢失要能被看见。

项：TD-210, TD-218, TD-292 · 已还：TD-248, TD-209, TD-215, TD-216, TD-238, TD-237, TD-217, TD-258

### 第 11 波 · 账本与页面读数、绿着的未知（第 3 轮）

目标：挂单与 IB 读失败不再被当真写库；Risk / Performance / 告警计数按交易日算；Console 的裁决条在探针失败时不再显示绿色；ui 的发布可追溯；台账与文档的过时说法改正。

项：TD-228, TD-234 · 已还：TD-214, TD-219, TD-232, TD-233, TD-226, TD-230, TD-227, TD-251, TD-235, TD-252, TD-229, TD-241, TD-213, TD-239, TD-211, TD-212, TD-236, TD-240

### 第 12 波 · Ops 维护只在 PROD 一处（Owner 10-07）

目标：会动手的维护只由 PROD 的 platform-workers 做，本机与 STG 只观测。已做：本机停手（TD-130 第一步）、STG 不修 IB 也不写发布记录（TD-223）、页面不再触发维护、状态持久化（TD-196）。接着：PROD 自己探测、带时间戳的检查信号，只给 PROD 挂技能并先只报告，再逐项放开；备份只归 CNPG 与 backup-retry；不再清掉失败现场。

项：TD-130, TD-272, TD-276, TD-283, TD-284, TD-285, TD-286, TD-287, TD-288, TD-289, TD-296 · 已还：TD-256, TD-257, TD-270, TD-271, TD-273, TD-275, TD-277, TD-278, TD-279, TD-280, TD-281, TD-282, TD-196, TD-223, TD-204, TD-253, TD-254, TD-255

## 数据边界（接受并留座）

> 订阅或市场本身没有的数据：接受，页面留座并写明原因；不算债、不编号，订阅或市场变化时重开（§5「缺数据先分原因」）。来自 Data Gaps 看板，10-06 并入。

- **已确认的财报日历（◉）** — 订阅里没有：10-06 `/research/events/calendar?days=60` 8 行，全是 ws:macro 与 ws:corporate，财报 0 行；插件只有 8-K Item 2.02 的过去财报。页面写 estimated · confirmed dates not in the subscription；预计日 expected_next 在跑（NVDA → 2026-11-18，track n=4、中位误差 0 天）。依据：看板 R2.a，10-06 实测。还在写「no earnings date reaches this side」的四处在 TD-150。
- **merger / spinoff 与 IB Flex 公司行为报表** — Owner 2026-09-17 裁定不做，除非重开：vendor 只给 dividend 与 split（抽样 17 名 833 行，0 merger、0 spinoff），能填的只有 Flex 的公司行为报表，没有接。依据：`bifrost-trade-frontend/src/layout/designNotes/portfolio.ts:76`；看板 B4.2-3。
- **CUE 只有调整合约** — CUE 1:30 合股（除权 2026-04-24）后交易所没有挂标准系列，只剩 10-16 到期的 14 个 CUE1 合约（10-05 OI 14 行）：市场本来没有，max pain / ATM IV / GEX / flow / PCR 留空是对的。依据：看板 R10.CUE，10-06 实测。页面上的说明已上线（frontend 8d991d8，原 TD-150，2026-10-08 签收）。

## 需要你拍板

### 现金写入失败要改成抛错吗？（改 core 公开接口）

- 推荐：B。core 新增严格版写入函数（失败抛错、返回写入与跳过数），旧函数保留一个版本；Flex 插件改调新函数，解析出行数 > 0 而写入 0 时任务失败。做法同第 1 轮 TD-80 C2-a。
- 选项：A：直接改 `upsert_account_transactions` 的语义并抬高下游下限 · B：新增严格版、旧版留一版 · C：只在插件侧判断（core 不动）
- 项：TD-91

### 让 CI 卡住发布吗？（跨仓库发版）

- 推荐：A。`release.sh stg/prod` 和 deliver-research / build-research-dagster 在该 SHA 的 CI 未成功时拒绝（Owner 可用 `--allow-red <理由>` 放行）；先修好 trade-api main 的红，三个插件仓库补上 CI 触发。
- 选项：A：发布前要求同 SHA 的 CI 成功 · B：deliver 流水线里先跑 lint-test 再构建 · C：维持现状，只在发布后告警
- 项：TD-95

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

- 推荐：TD-132 已上线并签收（10-06）；TD-134 调大检查点间隔并开 `wal_compression`（只需 reload，不重启）；TD-135 在把 CNPG 升到 1.30 之前装 cert-manager 并换 Barman Cloud Plugin，单独排期。
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

### 挂单要真的记下来吗？（跨仓库发版）

- 推荐：A。插件在快照里加只读的 reqOpenOrders / reqExecutions 输出（无下单路径，D10 安全），core 只在键存在时写 open_orders（缺键≠空）；同时停掉缺键时的 TRUNCATE。
- 选项：A：记下来 · B：退役 open_orders 表和 TWS 成交分支，界面改成「不跟踪挂单」
- 项：TD-211, TD-212

### 告警发给人用什么通道？备份要异地副本吗？（PROD 变更）

- 推荐：A。从 Mac mini 的 operator-plane（集群外）发 ntfy 或 Pushover，severity=critical 与备份类告警走它，webhook 保留 `continue: true`；Watchdog 接外部心跳。异地副本单独定（NAS 之外一份，例如云桶或另一台盘）。
- 选项：A：ntfy / Pushover · B：邮件 · C：维持只进 webhook
- 项：TD-209, TD-218

## 总览

| 编号 | 级别 | 领域 | 标题 | 审批 |
|---|---|---|---|---|
| [TD-85](#td-85) | P1 | trade (round 1) | One database password reaches everything: any DEV pod can write PROD Trade and all of Golden Source | 安全/凭据（要你批） |
| [TD-91](#td-91) | P1 | flex-ib | A failed cash-transactions write is recorded as a successful run: core returns 0 on any exception and the job counts it as 'ok, 0 rows' | 改公开接口 |
| [TD-92](#td-92) | P2 | research-control | Engine assets never fail: per-symbol failures, zero-row writes and skips are only metadata, reasons are discarded, and research_trading_day is green regardless of output | 不用批 |
| [TD-94](#td-94) | P2 | research-control | husbandry_gate fails open: a probe exception leaves verdict 'unknown', which passes, and the gate never checks that the doctor's session is the one being closed | 不用批 |
| [TD-95](#td-95) | P2 | research-control | No release path is gated on CI: deliver-research ships SHAs whose CI is red (CI starts 7s after deliver), and release.sh never checks CI for Trade | 跨仓库发版 |
| [TD-97](#td-97) | P2 | research-data | alert_scan judges each session once, a day late, and never revisits; composite_high has never fired because every >=90 score appeared on a later scan recompute | 不用批 |
| [TD-98](#td-98) | P2 | research-data | 'Today' is resolved by 11 private helpers plus 44 bare date.today() calls on UTC pods; option_universe stamps tomorrow's date | 不用批 |
| [TD-100](#td-100) | P2 | research-control | Event Radar SEC ingest runs from a Mac tmux loop on the shared checkout; it read .env once and failed 157 ticks over ~35.6h after a password rotation; the cluster event_radar slot never ingests and stays green | 不用批 |
| [TD-101](#td-101) | P2 | market-data | Doctor slot staleness reads a per-kind freshness row that other slots and zero-row jobs also refresh, so a stopped policed slot still reads fresh | 不用批 |
| [TD-110](#td-110) | P3 | research-data | Stored IV features solve Black-Scholes at r=0 while the backtester uses treasury rates from two separate readers; further BS copies in gex and opex | 不用批 |
| [TD-111](#td-111) | P3 | research-data | dbt: the pass_count range generic test sits in the singular folder (errors when selected, never applied); key intermediates lack grain tests; nothing ties eval_date to the session | 不用批 |
| [TD-112](#td-112) | P3 | research-data | option_surface_iv_daily upserts per (symbol, trade_date, expiry) and never deletes, so expiries a re-walk dropped keep their old smile | 不用批 |
| [TD-117](#td-117) | P3 | flex-ib | 'Latest Flex date in DB' after an import is one run behind: read through FDW in the same transaction as the pre-import read | 不用批 |
| [TD-118](#td-118) | P3 | market-data | option-refresh re-enumerates names with no listed options every run; its 7-day 'finished' lookback reads a table kept 48h | 不用批 |
| [TD-120](#td-120) | P3 | research-control | Dagster Deployments are applied by hand outside Argo; a second, unmounted dagster_instance.yaml lacks the run_monitoring that catches zombie runs | 跨仓库发版 |
| [TD-121](#td-121) | P3 | research-control | Research pods read bifrost-research-secrets once at start (optional: true); the OpenAI key rotation helper restarts only research-api | 安全/凭据（要你批） |
| [TD-128](#td-128) | P3 | research-data | Pine signal rows mix adjustment bases: nightly runs rewrite only the last ~10 sessions on today's adjusted bars, older rows stay on the basis of their last full rebuild | 不用批 |
| [TD-129](#td-129) | P3 | research-data | The event backtest picks option legs from option_daily only; since mid-August 2026 it keeps ~10 strikes a side, so a target delta silently lands on the nearest strike that is left | 不用批 |
| [TD-130](#td-130) | P1 | ops-control | ops-autopilot acts on the shared cluster's data layer from the Owner's laptop (local bdev platform-api, role all); the in-cluster STG/PROD autopilots idle on an empty checklist, and each of the three keeps its own throttle | 要你批 |
| [TD-133](#td-133) | P3 | data | Leftovers of the in-cluster MinIO after the move to the NAS (deploy/minio at 0, its PVC/PV, an empty EndpointSlice, the backup-retry CronJob) | 要你批 |
| [TD-134](#td-134) | P2 | data | WAL is ~19.5 GiB/day (4.2 GiB compressed) because checkpoints run every 5 minutes without wal_compression | 要你批 |
| [TD-135](#td-135) | P3 | data | Native barmanObjectStore backups are removed in CloudNativePG 1.30; the Barman Cloud Plugin that replaces them needs cert-manager, which the cluster does not have | 新依赖（要你批） |
| [TD-137](#td-137) | P1 | trade-data | The daily snapshot capture locks an account's intraday book into the day (first write wins, no freshness test) and account_nav_daily stores no margin-pressure fields | 改表 + 发布（要你批） |
| [TD-142](#td-142) | P2 | research-data | The 90-day IV cone has 31–39 sessions of history and there is no 180-day tenor: ATM IV was stored only to 90 DTE before 2026-08-05 | 要你批 |
| [TD-143](#td-143) | P3 | research-data | Hypotheses never link to trades: linked_opportunity_ids is empty on all 91 rows, and only Research's own create / patch writes it | 不用批 |
| [TD-144](#td-144) | P3 | research-data | Settled candidates are not attributed to the judge (persona) that put them forward, so the Personas bench track-record columns stay grey | 要你批 |
| [TD-146](#td-146) | P3 | research-data | No store accepts a hand verdict, so the Personas bench 'Agrees with you' column cannot be computed | 要你批 |
| [TD-149](#td-149) | P2 | market-data | CTVA's adjusted daily bars ignore its 2026-10-01 spin-off, so every return-based feature on CTVA sees an ~84% one-day drop | 不用批 |
| [TD-158](#td-158) | P3 | research-data | Earnings estimates are served one name per request, so no universe-wide page can show an Earn column | 不用批 |
| [TD-159](#td-159) | P3 | market-data | No read says how many standard and adjusted option contracts a name has, so "only adjusted contracts are listed" is inferred in the browser from ticker shapes | 不用批 |
| [TD-152](#td-152) | P2 | ops-platform | promtail drops log lines (ingester_error) around 02:00–03:15 and 22:xx UTC, so every Loki-based release gate can come out INCONCLUSIVE | 不用批 |
| [TD-153](#td-153) | P3 | ops-platform | loki_gate.py only knows the pre-0.10.0 log line ('deprecated query params'); after api 0.10.0 refused callers log 'retired query params' and the gate cannot see them | 不用批 |
| [TD-155](#td-155) | P2 | ops-platform | Pushes to GitHub main do not trigger CI until the Gitea pull mirror syncs, so a commit can be released before its CI ever ran | 跨仓库发版 |
| [TD-156](#td-156) | P2 | research-control | research_signal_hit_schedule fires at 00:10 UTC, before the 02:30 UTC batch writes the night's features, so it judges the previous night's features | 不用批 |
| [TD-162](#td-162) | P2 | ops-platform | Research and plugin releases have no release window: sessions collide on pins and on deliver runs | 跨仓库发版 |
| [TD-170](#td-170) | P3 | research-control | dagster-daemon logs one line over 256 KB at the 22:45 and 03:00 UTC schedule ticks every night | 不用批 |
| [TD-172](#td-172) | P2 | research-data | ATM IV has almost no 50–90 DTE expiry from 2026-07-06 to 09-25 (the EOD chain stopped at the third listed expiry until plugin 0.39.0); the fix was forward-only, so term structure reads na for that stretch | 要你批 |
| [TD-174](#td-174) | P3 | market-data | Console marks fundamentals-rotate missed every Monday 03:45 → Tuesday 03:00 UTC: the trading-day check uses the UTC date of the fire | 不用批 |
| [TD-180](#td-180) | P3 | research-data | The macro calendar has no CPI dates after 2026-12-10 and no payrolls at all: bls.gov answers 403 from this host, so they could not be read | 不用批 |
| [TD-183](#td-183) | P3 | market-data | W3 archive-before-delete has never archived for real: the first intraday option_snapshot archive is ~10-08 02:15 UTC and option_daily / short_volume on 11-01 | 不用批 |
| [TD-184](#td-184) | P3 | frontend | The Simulator says "stored with the run" for runs that were not stored: the fix (fe 53d6939e) is on main but not in STG/PROD | 发布（要你批） |
| [TD-185](#td-185) | P3 | research-control | The Pine-vs-TradingView roadmap ledger is a point-in-time judgement: its scores and next steps need a re-evaluation around 11-06 | 不用批 |
| [TD-186](#td-186) | P3 | frontend | "My levels" (plan stop / target and price alerts as horizontal lines) on the Symbol chart waits on Design: ASK-symbol-chart-my-levels-2026-10-06 | 要你批 |
| [TD-188](#td-188) | P3 | frontend | The app's design registry is still at Rev .157: packages .158–.162 are built but designRoutes / adoption were not re-synced (the Design project's DS mirror was synced to 0.13.0 on 10-06) | 不用批 |
| [TD-189](#td-189) | P3 | research-data | SEPA has no rows for four sessions (08-28, 08-31, 09-08, 09-16): those nights never computed it, so the SEPA lens and its hit rate skip them | 不用批 |
| [TD-192](#td-192) | P2 | research-control | One IB Flex failure loses that night's SEPA for good: husbandry_gate blocks sepa_projection although SEPA reads nothing from Flex, and the projection never back-fills a missed night | 要你批 |
| [TD-202](#td-202) | P3 | market-data | market-data code strings and scripts still mention CronJobs: the dashboard label 'CronJob archived' and verify-market-data.sh's hint are user-visible | 不用批 |
| [TD-210](#td-210) | P1 | data | The nightly logical backup of hand-entered data failed on its first scheduled run: it connects before the new pod's NetworkPolicy is programmed and gets Connection refused | 不用批 |
| [TD-218](#td-218) | P2 | data | Every backup copy (Barman base+WAL, logical dumps hot and cold, the W3 archive) is on the one NAS 192.168.10.20:/volume1, and the open offsite decision is not in the ledger | PROD 变更（要你批） |
| [TD-228](#td-228) | P3 | ops-console | Every scheduled Hermes skill run on .52 fails with 'No such file or directory', while /health returns status ok and the checklist counts the gateway healthy | 不用批 |
| [TD-234](#td-234) | P3 | trade-worker | @bifrost/ui is unversioned for the Ops Console: a ui push never runs platform CI, and platform deliver builds whatever ui main is without recording its SHA | 不用批 |
| [TD-242](#td-242) | P2 | market-data | market-data /ingest/queue-dashboard takes 5–25 s per call, and the platform-api proxy carries the same delay: with the new latency rule live it will page whenever someone keeps the queue dashboard open | 不用批 |
| [TD-244](#td-244) | P3 | research-control | agents/journal_distill reads raw_broker.executions_final with no Flex freshness check (own 23:55 UTC schedule, outside any gate) | 不用批 |
| [TD-246](#td-246) | P3 | trade-data | Snapshot enrich stores a vendor 'day close' that can sit below the option's intrinsic value (a stale last trade), and P&L attribution then books it as unexplained | 已批（Owner 10-07「做」） |
| [TD-250](#td-250) | P3 | trade-data | A stale vendor close above intrinsic is still stored as vendor_eod: the plugin's snapshot read does not return last_trade_ts, so enrich cannot tell a morning trade from a session close | 不用批 |
| [TD-272](#td-272) | P3 | ops-platform | tekton-trigger can create any PipelineRun in cicd, and no admission policy matches it, so its token is still a path to the cluster-admin Argo controller account | 安全/凭据（要你批） |
| [TD-276](#td-276) | P3 | ops-platform | An apply_manifest run is named apply-<plan id>, so a failed apply of a plan cannot be retried; a new plan is needed | 不用批 |
| [TD-283](#td-283) | P3 | ops-platform | release.sh dev still restarts DEV with kubectl rollout restart, which the read-only Agent identity cannot do | 不用批 |
| [TD-284](#td-284) | P3 | ops-platform | Plugin and pine image builds cannot be started through start_pipeline_run: no image tag, no workspaces, pine missing from the window map | 不用批 |
| [TD-285](#td-285) | P2 | ops-platform | The applier cannot take over a field that kubectl-client-side-apply owns: plan and apply fail with a server-side apply conflict | 安全/凭据（要你批） |
| [TD-286](#td-286) | P2 | ops-platform | Approval notifications carry no short id or parameters and their delivery is not recorded; session, Console and phone are not one approval experience | 安全/凭据（要你批） |
| [TD-287](#td-287) | P3 | ops-platform | The gpu-server power manager on ubt-k3s-01 has failed every poweroff since the node key changed and logs success; platform wake/poweroff have no SSH identity | 安全/凭据（要你批） |
| [TD-288](#td-288) | P2 | infra | ubt-k3s-01, the sole control plane, went down without a shutdown on 10-10 and no boot since June recorded a clean shutdown; nothing alerts on an unplanned reboot | 不用批 |
| [TD-289](#td-289) | P2 | infra | Prometheus, Alertmanager and Grafana keep their data in emptyDir: a node drain erases 10 days of metrics, the silences and Grafana's database | 安全/凭据（要你批） |
| [TD-290](#td-290) | P3 | ops-platform | The retired remediation runner's ConfigMap cicd/bifrost-remediation-runner-stg-dockerfile is still in the cluster, and the supply check and the deliver phase list still name it | PROD 变更（要你批） |
| [TD-291](#td-291) | P3 | ops-platform | The PROD operator plane probes git-bridge on the Owner's laptop (192.168.10.40:8785) and gets 401, so agent-bridge shows git_bridge unavailable instead of local-only | PROD 变更（要你批） |
| [TD-292](#td-292) | P2 | infra | The powered-off standby node gpu-server keeps 18 warning alerts firing in Prometheus, so the Console header verdict is stuck at Degraded and a real warning cannot be seen | PROD 变更（要你批） |
| [TD-293](#td-293) | P2 | infra | The platform service accounts of STG and PROD can create, update and patch any ConfigMap in cicd, so either can lift the release freeze or rewrite the release window without the Owner's signature | 安全/凭据（要你批） |
| [TD-294](#td-294) | P3 | infra | The Tekton freeze check only runs in pipelines that start with release-window; the Trade and platform deliver pipelines and three build pipelines do not, so a run created outside platform-api ignores a freeze | PROD 变更（要你批） |
| [TD-295](#td-295) | P2 | ops-platform | start_pipeline_run checks one revision in every repo a pipeline clones, so a platform deliver cannot be started by full SHA: the W-42 pinned rule for bifrost-deliver-platform-prod can never be met through the API | 不用批 |
| [TD-296](#td-296) | P2 | ops-platform | The ntfy connection error text carries the full topic (the read credential) and is served by the token-less relay status endpoint; with W-49 it would also reach approval delivery records | 安全/凭据（要你批） |
| [TD-274](#td-274) | P3 | frontend | Symbol faces hide GEX levels that exist when zero gamma is NULL: the dealer level strip needs all four values and the regime cell needs zero gamma, so a chain with no flip (about a third of expiries) shows neither walls nor regime | 不用批 |

## 条目

### TD-85

**P1 · trade (round 1) · One database password reaches everything: any DEV pod can write PROD Trade and all of Golden Source**

- **状态**：观察中（到 10-09 01:00 UTC，看撤权后 24 小时内 Postgres 日志里 `analytics_writer` / `market_reader` / `role_matrix_reader` 的 `permission denied` 为 0——夜里的 Dagster 批次与 Research 写入会用到 analytics_writer；为 0 就进「待你签收」）。防线已全部落地（10-08）：期望矩阵 + 只读检查 `k8s/data/role-matrix/`（infra 5ff1624、99e557e）接进 `release-check.sh <env> before`；每日 CronJob `data/db-role-matrix`（05:15 UTC，登录 `role_matrix_reader`，只 CONNECT，Secret `data/db-role-matrix-reader`）与告警 `BifrostDbPrivilegeDrift` 已 apply；手动 Job `db-role-matrix-manual-1008b` → `role-matrix: 0 difference(s)`。两个 db-step（`2026-10-07-td85-analytics-writer-create`、`2026-10-07-td85-role-matrix-reader`）已执行并记 done
- **验收结果**：PASS 2026-10-07 eaf68ac — GS `datacl` 里 PUBLIC 只剩 `=T`（无 CONNECT）；10-06 16:43 → 10-07 16:43 UTC 两个实例的 Postgres 日志里 `data_writer` / `flex_writer` 的 `permission denied` 为 0；`flex_writer` 10-07 10:30 UTC 照常写入 raw_broker（5 行）。日志里另有 2 条是 `bifrost` 的 pg_dump 读不了 `research.suggestion_adoption_suggestion_adoption_id_seq`（10-07 01:42 手动逻辑备份，已失败；之后 03:14 手动与 04:30 定时两次都 Complete），不属于本项
- **验收**：Golden Source 的 `datacl` 里没有 PUBLIC 的 CONNECT（`=c`），且 Postgres 日志 24 小时内 `data_writer` / `flex_writer` 的 `permission denied` 为 0：`kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -At -c "SELECT datacl FROM pg_database WHERE datname = current_database()"`
- **现在**：D1–D8 与 GS 的 PUBLIC CONNECT 收回（10-06，eaf68ac）全部执行完：三环境 Trade 运行时用 `trade_app_<env>` 登录；D4 已在三个 Trade 库收回 PUBLIC 的 CONNECT 和 CREATE（10-06，验证 74/74）；D7 ConfigMap 已合入；D6 收口完成，`data_writer` 在 `raw_broker` 上的写权已撤（core 0.48.2，10-06）。
- **Claim**: Measured 2026-10-04 (read-only): nine Secret keys hold the same value, the bifrost password (PGPASSWORD and GOLDEN_SOURCE_PASSWORD in bifrost-{dev,stg,prod}-secrets, flex-query postgres-password / trade-pg-password, market-data postgres-password). bifrost can INSERT into 320 Golden Source tables and CREATE in raw_broker and research; analytics_writer inherits bifrost and can write all 19 tables of bifrost_prod.public. PUBLIC has CONNECT/TEMP on all four databases and CREATE on public in the Trade databases. D13 is not enforced at the database layer in either direction.
- **Evidence**:
  - `REQUEST-trade-runtime-db-role-plan-2026-10-04.md:1` — ``
- **Impact**: A compromised or misconfigured DEV workload can modify PROD trading data and the Research store; Research can write Trade tables.
- **Fix**: Per-env runtime roles trade_app_<env> (NOINHERIT, own database only; Golden Source only raw_broker and ops_feedback), bifrost kept for db-init/CNPG; Secret switch per env with one-patch rollback; then revoke PUBLIC CONNECT/CREATE, rotate the bifrost password, and separately drop analytics_writer's bifrost membership after Research gets explicit grants.
- 审批 安全/凭据（要你批） · 代价 L · 风险 medium · repos: bifrost-trade-infra, bifrost-research

### TD-91

**P1 · flex-ib · A failed cash-transactions write is recorded as a successful run: core returns 0 on any exception and the job counts it as 'ok, 0 rows'**

- **状态**：观察中（core 0.58.0 + flex 0.13.0 均已上线 10-07；到 10-08 看 flex 现金流水作业结果）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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

- **状态**：观察中（validate-git-sha 与 research-lint-test 已 apply 进 deliver-research / build-research-dagster；下一次 research 发版首跑）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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

### TD-120

**P3 · research-control · Dagster Deployments are applied by hand outside Argo; a second, unmounted dagster_instance.yaml lacks the run_monitoring that catches zombie runs**

- **状态**：观察中（research 0.205.0 已上线 10-07：api/mcp 0.205.0、Dagster 0.205.0-dagster；verify-research 新校验已 apply，下一次 deliver-research 生效）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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

- **状态**：观察中（research 0.205.0 已去掉 optional: true；infra 7a346b1 的 scripts/research-secret-restart.sh 已就位，等下一次轮换 Secret 时用）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
- **Claim**: research-api, research-mcp, dagster-daemon and dagster-webserver envFrom bifrost-research-secrets with optional: true. sync_openai_secret.sh patches the key and restarts only deployment/research-api, so the daemon (scheduled LLM agents) and MCP keep the old key until the next release. No rotation helper exists for analytics_writer. (DB rotation of 'bifrost' does not touch these pods; infra bifrost-password-rotate.sh already derives holder Deployments.)
- **Measured**: CODE-READ for cluster pods; secret key names checked live (OPENAI_API_KEY, DEEPSEEK_API_KEY, ANALYTICS_PG_PASSWORD present).
- **Evidence**:
  - `bifrost-research/scripts/sync_openai_secret.sh:41` — `kubectl -n "$NS" rollout restart deployment/research-api`
  - `bifrost-research/k8s/orchestration/dagster.yaml:98` — `- secretRef:`
- **Impact**: After an OpenAI/DeepSeek key rotation, scheduled agents and Copilot via MCP fail until a manual restart; optional: true lets pods start without credentials instead of failing fast.
- **Fix**: Restart every Deployment in namespace research that mounts the secret (derive the list as infra holder_deployments() does); add a checksum/secret annotation or reloader; drop optional: true for required keys.
- **Ratchet**: Lint over k8s/: every Deployment envFrom-ing bifrost-research-secrets carries the checksum annotation and none mark required keys optional; grep check that rotation helpers never hard-code one deployment.
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-research

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

- **状态**：观察中（到 10-12，看 PROD platform-workers 的只报告 autopilot：每 15 分钟一轮，它写「REPORT-ONLY: would …」的每一项是不是真该做、有没有漏掉该做的）
- **现在**：10-07 第 4 步上线。本机 `PLATFORM_ROLE=api`（background_loops=false）；STG 只观测、不挂技能；PROD platform-workers 挂 PROD 专用技能（ops-autopilot、fleet-drift-scan、cert-expiry-check），`PATROL_MODE=report`、`PATROL_DISPATCH=local`、`CHECKLIST_PROBER=on`（infra 5d1c208，platform 2727eb0 起）。第一轮 06:00Z：22 个信号、2 红（argo-apps 是 rollout 中的假红，已由 d8833e5 修掉、10-07 06:17 起 PROD 生效；hermes-tooling 只观测），0 动作。补备份交还 CNPG + backup-retry（TD-254），漂移扫描不再删失败现场（TD-255），信号自带时间、过期读 unknown（TD-253）
- **下一步**：观察到 10-12 后，把只报告记录整理给 Owner，逐项放开（每放开一项改 `check_platform_maintenance.py` 的 REPORT_ONLY 规则与 overlay 同一提交）；防线 `make check-platform-maintenance` 已在
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

- **状态**：观察中（Owner 10-07 批第一组；已 apply 到 data/bifrost-postgres，reload 生效、两个 pod 未重启；到 10-14 看一周 WAL 量（apply 前约 18 GiB/天））
- **验收结果**：PASS（生效）2026-10-07：pg_settings checkpoint_timeout=900s、max_wal_size=4096MB、wal_compression=lz4；bifrost-postgres-1/-3 restartCount 未变
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

### TD-137

**P1 · trade-data · The daily snapshot capture locks an account's intraday book into the day (first write wins, no freshness test) and account_nav_daily stores no margin-pressure fields**

- **状态**：观察中（10-06 晚已上三环境：core 0.52.0 = 5963422，tag v0.52.0；晚间 CronJob 改 `all`（infra 3581880，STG / PROD 经 Argo、DEV 单独 apply）；到 10-07 16:20 ET 抓取与 20:30 ET 补抓之后跑验收 SQL）
- **验收**：每个 Trade 库（`bifrost_dev` / `bifrost_stg` / `bifrost_prod`）发布后的 session：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_prod -X -At -c "SELECT count(*) FROM account_nav_daily WHERE snapshot_date >= '<发布日>' AND account_updated_at < (snapshot_date + time '16:00') AT TIME ZONE 'America/New_York'"` 为 0（NYSE 提前收盘日按提前收盘时间比），且 `SELECT snapshot_date, count(cushion), count(*) FROM account_nav_daily GROUP BY 1 ORDER BY 1 DESC LIMIT 3` 最新一天 count(cushion) = count(*)
- **现在**：10-06 Owner 在 dev / stg / prod 加 3 列并 verify（db-step done）；release.sh stg（stbr9）/ prod（lq5zd）/ dev 全部 PASS，health core 0.52.0@5963422。今晚 20:30 ET 的 `all` 只会补抓 16:20 之后才同步的账户（今天 16:20 由 0.50.0 抓过，已抓的账户不再碰），然后 enrich
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

### TD-142

**P2 · research-data · The 90-day IV cone has 31–39 sessions of history and there is no 180-day tenor: ATM IV was stored only to 90 DTE before 2026-08-05**

- **状态**：观察中（Cursor LANE-D2 已完成并复验；待你批：回填：约 3883 个 symbol-day、约 2972 行可补）
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -At -c "SELECT count(DISTINCT trade_date) FROM features.option_metric_atm_iv_daily WHERE symbol='NVDA' AND expiry-trade_date>90 AND atm_iv IS NOT NULL"` ≥ 150（回填前 39 左右）；TD-141 的 iv-cone 命令里 NVDA 的 90 档 n ≥ 60、withheld 为 False，且出现 180 档
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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

### TD-146

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

- **状态**：观察中（release.sh 10-07 首用：镜像同步与 CI 检查生效；ci_gate 漏认前端 CI 已修 infra 403ba7f，下一次发版应不再需要 --allow-red）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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
- **Claim**: Research excludes adjusted contracts (OCC root ending in a digit) from every option metric, so a name with only adjusted contracts has empty max pain, ATM IV, GEX, flow and PCR by rule. Nothing served says so. The shipped data-gap-wording frontend batch infers it by fetching the nearest expiry's snapshot rows and testing each option_ticker's root, copying Research's SQL rule into TypeScript; it reads one expiry only and costs two extra requests on names whose four option exhibits are all missing.
- **Measured**: CODE-READ 10-06: the rule lives in Research `not_adjusted_contract_sql` (27 call sites) and, on the wording branch, in frontend `adjustedListing.ts`; the plugin's `/market/options/snapshots` returns rows with option_ticker but no per-name counts. MEASURED 10-05: CUE 14 open-interest rows, all `CUE1…`.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/adjusted_contracts.py:20` — `def not_adjusted_contract_sql(column: str) -> str:`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/options.py:293` — `@router.get("/snapshots")`
  - `bifrost-trade-frontend` branch `fix/data-gap-wording` 7caac1f8 `src/pages/research/analyze/symbol/adjustedListing.ts:26` — `export function isAdjustedOptionTicker(…)` (copy of the Research rule)
- **Impact**: Two copies of one rule (Research SQL, frontend regex) can drift; the note covers only the nearest expiry; any other surface that wants the explanation has to repeat the probe.
- **Fix**: Serve per-name counts once: Research adds `standard_contracts` / `adjusted_contracts` for the latest session (from option_open_interest, using not_adjusted_contract_sql) to an existing per-name read the Symbol page already loads (dossier or options coverage), additive. Frontend reads those fields and deletes its own ticker test.
- **Ratchet**: A frontend ratchet that no file outside tests matches the adjusted-root regex once the field is served; Research test that the counts agree with not_adjusted_contract_sql on a fixture.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-frontend

### TD-162

**P2 · ops-platform · Research and plugin releases have no release window: sessions collide on pins and on deliver runs**

- **状态**：观察中（release-window 任务、RBAC 与各流水线已 apply 10-07；首次 ib-gateway 构建已走窗口校验通过；platform 79ed8db 的 start_pipeline_run who 校验已上线）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
- **Claim**: release.sh window serializes Trade releases only. Research and plugin releases have no equivalent; on 10-06 a session started deliver-research for 0.185.0 while another waited on an ad-hoc lock in /tmp, and the S4 session built 0.187.0 while lane C built 0.188.0, leaving the pins two releases behind the images until the Owner approved one combined pin push.
- **Measured**: MEASURED 10-06: research 0.185.0 started via platform-api during another session's lock wait; 0.187.0 and 0.188.0 built back to back with one pin push (6cf4266).
- **Evidence**:
  - `bifrost-trade-infra/scripts/release/release.sh:2` — `# One entry for a Trade release (TD-84): STG from main, PROD pinned to an STG run, DEV catch-up.`
- **Impact**: Two sessions can ship over each other (pins pointing at an image that lacks the other's change, or a Dagster apply that drops one), and nobody can see who is releasing research right now.
- **Fix**: Extend release.sh window to cover research and the plugins (one window file, the repo in `what`), and have the deliver-research / build pipelines (and platform-api's start_pipeline_run) refuse while a window is held by someone else; document it in CLAUDE.md §5 next to the Trade window.
- **Ratchet**: deliver-research / plugin build PipelineRuns check the window as their first task (fail fast), the same way the Trade PROD pipeline checks its STG run.
- 审批 跨仓库发版 · 代价 M · 风险 med · repos: bifrost-trade-infra, bifrost-research, bifrost-platform

### TD-170

**P3 · research-control · dagster-daemon logs one line over 256 KB at the 22:45 and 03:00 UTC schedule ticks every night**

- **状态**：观察中（修复随 research 0.202.0-dagster 10-07 01:4x UTC 上线；到 22:45 / 03:00 UTC tick 之后看 line_too_long 不再增长）
- **验收**：Dagster 镜像含 2583cc6 上线后，下一个 22:45 与 03:00 UTC tick 之后：`sum(increase(promtail_mutated_entries_total{reason="line_too_long"}[1d]))` = 0；Loki 里 22:45 那行形如 `'jobs': {'count': …, 'first': […]}`
- **现在**：道 X 在 Loki 找到那一行：10-06 22:45:33 UTC `market_option_bars_job`，`plugin_http.py:106` 的 `context.log.info("market slot=%s result=%s", slot, result)` 把插件 enqueue-slot 响应里 91,431 条 job 整个打成一行，原始约 17 MB（promtail_mutated_bytes 17,264,403），截断到 256,000。flex 侧 `plugin_batch_assets.py:102` 同样写法一并修。修复：`summarize_result` / `summary_line`（标量原样、列表变 {count, first 3}、长字符串截断、整行上限 16 KB）；job 列表本来无人读，资产 metadata 不变。门禁 lint 0、2196 passed。防线 `tests/orchestration/test_plugin_enqueue_log_size.py`（10 万条 job 的响应，每行 ≤ LOG_LINE_MAX_CHARS；回退旧写法即失败）。03:00 那次（fundamentals-rotate）同一函数，按代码推断、无日志实证，由验收一并覆盖
- **Claim**: Some logger call in the Dagster daemon / run path writes a single line larger than Loki's 256 KB max_line_size each night (probably a whole result object). Until 10-06 Loki rejected it with 400 and promtail dropped the whole batch (TD-152); from 10-07 promtail truncates it to 250 KB.
- **Measured**: MEASURED 10-06 by paydown lane H: 12 promtail 'final error sending batch status=400 max entry size 262144 bytes exceeded' lines 09-28..10-06, all for stream {namespace="research", app="dagster-daemon"}; 03:00 runs include market_fundamentals_rotate_job, research_forecast_job, research_event_radar_job. No file:line yet: the line never reached Loki and the daemon restarted ~18:30Z 10-06.
- **Evidence**:
  - `bifrost-trade-infra/scripts/k3s/values-promtail.yaml:25` — `max_line_size_truncate: true`
- **Impact**: A 256 KB log line is unreadable and costs Loki ingestion; any future truncation hides whatever is at its tail.
- **Fix**: After 10-07 find the truncated line in Loki (`{namespace="research", app="dagster-daemon"}` with promtail_mutated_entries_total line_too_long), trace it to the logger call and log a summary (counts, ids) instead of the object.
- **Ratchet**: A test or log filter in research that caps log message length (e.g. a logging.Filter that truncates over 16 KB and counts it), plus the existing promtail mutated-entries metric.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-172

**P2 · research-data · ATM IV has almost no 50–90 DTE expiry from 2026-07-06 to 09-25 (the EOD chain stopped at the third listed expiry until plugin 0.39.0); the fix was forward-only, so term structure reads na for that stretch**

- **状态**：观察中（Cursor LANE-D2 已完成并复验；待你批：向 vendor 重拉 50–90 DTE：约 4.8 万次区间请求，缺口几十万根 bar）
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -At -c "WITH d AS (SELECT symbol, trade_date, bool_or(expiry - trade_date BETWEEN 50 AND 100) b FROM features.option_metric_atm_iv_daily WHERE trade_date BETWEEN '2026-07-06' AND '2026-09-25' AND symbol IN (SELECT symbol FROM research.option_universe) GROUP BY 1,2) SELECT date_trunc('week', trade_date)::date, round(avg(b::int), 2) FROM d GROUP BY 1 ORDER BY 1"` — every week ≥ 0.85 (06-22/06-29 read 0.88–0.91; 07-06..09-21 read 0.02–0.59 before the fix)
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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

### TD-174

**P3 · market-data · Console marks fundamentals-rotate missed every Monday 03:45 → Tuesday 03:00 UTC: the trading-day check uses the UTC date of the fire**

- **状态**：观察中（0.81.0 已上线；到 10-12 周一 03:45–10-13 03:00 UTC 看 fundamentals-rotate 仍 on_plan、last_fire 2026-10-10T03:00Z）
- **验收结果**：部分 PASS 2026-10-06 market-data 0.81.0：已上线，当前 fundamentals-rotate on_plan；周一窗口待 10-12
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

### TD-180

**P3 · research-data · The macro calendar has no CPI dates after 2026-12-10 and no payrolls at all: bls.gov answers 403 from this host, so they could not be read**

- **状态**：在做（**2026 那半已合入** research 481c96c：`2026-11-06` 与 `2026-12-04` 两行 NFP 写进 `macro_calendar.csv`，`MACRO_IMPORTANCE` 给 `NFP` 设 2（与 CPI 同级，否则页面会标成 low、和分红同列）；防线 `test_every_series_has_a_future_date`（注入日期，不读时钟）+ 反例测试；`make test` 2135 passed。**预期告警**：11-05 起 NFP、11-11 起 CPI 会报 WARN（剩余不足 30 天），这是对的，等 2027 日程补上就消失。证据行号从 `:35` 变 `:39`。2027 那半仍等 BLS —— LANE-E 2026-10-07 查证：BLS 官方只排到 2026-12，**2027 全年日程尚未发布**——`/schedule/2027/home.htm` 404，官方 ICS 80672 字节全文无 `2027`；Claude 2026-10-08 用 `empsit.htm` 独立复核，最后一行是 Dec. 04, 2026，页面明确没有 2027。所以 TD-180 的 2027 部分**等 BLS 发布**，不是我们能做的工作。能做的那半已交 LANE-E2：把官方已确认的两行非农写进 CSV——`2026-11-06,08:30,US,NFP,October 2026` 与 `2026-12-04,08:30,US,NFP,November 2026`，三处来源一致）
- **Claim**: TD-151's seed file carries FOMC through 2027 but CPI only for three 2026 releases (copied from a hand-dropped file) and no Employment Situation dates.
- **Measured**: MEASURED 10-06 by paydown lane O: bls.gov returned 403 to the Mac; federalreserve.gov answered.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/scheduler/data/macro_calendar.csv:35` — `2026-12-10,08:30,US,CPI,November 2026`
- **Impact**: From 11-05 the asset check warns; from 12-10 the forward calendar has no CPI and never had payrolls.
- **Fix**: 两段。(a) 现在：写入官方已发布的两行 2026 非农（日历从来没有过非农，这是 Claim 的一半）。(b) BLS 发布 2027 日程后：补 2027 的 CPI 与非农。**本机 urllib 直连 bls.gov 一律 403**（Access Denied），要用能打开页面的浏览器会话读同一 URL。
- **Ratchet**: 已有的 macro_calendar asset check（任一序列剩余不足 30 天即告警）。原定的「最后一个日期 ≥ 今天+180 天」防线**作废**：BLS 只提前约 14 个月排期，这条线在正常年份也会红，LANE-E 正确地拒绝了它。LANE-E2 改为断言每个序列（FOMC / CPI / NFP）至少有一个未来日期。
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-183

**P3 · market-data · W3 archive-before-delete has never archived for real: the first intraday option_snapshot archive is ~10-08 02:15 UTC and option_daily / short_volume on 11-01**

- **状态**：观察中（到 11-01，看三张表第一次真正的归档）
- **验收**：10-08 与 11-01 的 trim 日志里，每张表 `archived_rows == deleted_rows`，归档文件在 NAS `nfs-cold` 上可读、行数与日志一致；没做完的行留在库里，不被删
- **现在**：market-data 0.77.0 起三张表（option_snapshot 盘中行、option_daily、short_volume）都改成先归档后删（10-05）；到今天为止还没有一次真正触发
- **下一步**：10-08 看盘中快照那一次；11-01 看两张大表（option_daily 一次约 180 万行，单事务，trim 调用可能超过 `dated_budget_sec` 60 秒，分几晚做完）。全部通过后把 `/stocks/REQUEST-w3-archive-before-delete-2026-10-05.md` 移到 `/stocks/archive/`
- **Claim**: The archive path is new and has only been exercised in tests. option_snapshot is not reproducible from the vendor after its window, so a broken archive that still deletes would lose data for good.
- **Evidence**:
  - `/stocks/REQUEST-w3-archive-before-delete-2026-10-05.md:20` — `option_snapshot 盘中行 | 2026-09-08 | 约 10-08 02:15 UTC（30 天窗口）`
  - `/stocks/REQUEST-w3-archive-before-delete-2026-10-05.md:21` — `option_daily | 2024-10-01 | 11-01 02:15 UTC`
- **Impact**: Irreversible loss of option snapshots if the first real archive fails silently.
- **Fix**: Watch the two runs; if archived and deleted counts differ, hold deletion (`retention_hold`) and fix before the next night.
- **Ratchet**: The retention hold already takes precedence over archive; a check that fails the trim when archived_rows != deleted_rows belongs in the plugin if the first run shows a gap.
- 审批 不用批 · 代价 S · 风险 med · repos: bifrost-platform-plugin-market-data

### TD-184

**P3 · frontend · The Simulator says "stored with the run" for runs that were not stored: the fix (fe 53d6939e) is on main but not in STG/PROD**

- **状态**：观察中（到下一次 `release.sh`，看前端克隆的提交包含 53d6939e）
- **验收**：最新 `bifrost-deliver-prod-pinned-*` 的 `clone-frontend` 提交是 53d6939e 的后代：`git -C bifrost-trade-frontend merge-base --is-ancestor 53d6939e <clone commit>`
- **现在**：10-06 STG `kk259` 与 PROD `cdw6r` 克隆的是 `60ed2368`，不含 53d6939e
- **下一步**：随下一次 Trade 发布带出，不单独发
- **Claim**: Found while walking P1 on DEV (10-06): a simulator run sent with persist:false still showed "stored with the run". The copy claims a record that does not exist.
- **Evidence**:
  - `bifrost-trade-frontend` commit `53d6939e` — `fix(research/sim): drop "stored with the run" for runs that were not stored`
- **Impact**: A reader can look for a stored run that is not there.
- **Fix**: Already on main; release it.
- **Ratchet**: The fix ships with a unit test on the label; no further ratchet needed.
- 审批 发布（要你批） · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-185

**P3 · research-control · The Pine-vs-TradingView roadmap ledger is a point-in-time judgement: its scores and next steps need a re-evaluation around 11-06**

- **状态**：观察中（到 11-06，重评 `/stocks/LEDGER-pine-tradingview-gaps.md` §0）
- **验收**：台账 §0 的标题日期是 11 月、§7 有一行重评记录，且 V2（Pine 建议来源）、B4、B5、G5 的状态与当时的实测一致
- **现在**：10-06 晚的重评：五轮预注册回放 41 个候选都没有超过机械基准，Pine 建议来源按预注册停止；P1 与 S6 已在三环境上线；门槛 thresholds 2026-10-06.3（IV 两段各 ≥ 10 条，research 0.190.0）
- **下一步**：11-06 前后看：机械来源在新门槛下攒了多少已结算样本（高、低 IV 各几条）；有没有新的信号假设值得写预注册；G5 的 Design 回复（TD-186）
- **Claim**: The roadmap ledger scores capability against TradingView by business value for option trading; it is not self-updating, and several rows depend on forward samples that accrue over weeks.
- **Evidence**:
  - `/stocks/LEDGER-pine-tradingview-gaps.md` §8 — next re-evaluation after a month of the ledger running
- **Impact**: Without a dated review the ledger goes stale and stops being the place the Owner tracks the gap.
- **Fix**: Re-evaluate §0 and the open rows against the month's reports and ledger samples.
- **Ratchet**: None feasible (a judgement, not a mechanism); this entry is the reminder.
- 审批 不用批 · 代价 S · 风险 low · repos: (workspace doc)

### TD-186

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

### TD-188

**P3 · frontend · The app's design registry is still at Rev .157: packages .158–.162 are built but designRoutes / adoption were not re-synced, and the Design project's DS mirror is 0.11.0 against @bifrost/ui 0.13.0**

- **状态**：在做（app 侧登记已到 Rev .162：frontend 85d93f14；剩 Symbol 五条偏离等 Design 回 + Check 小 K 线走查要你填 Research 身份）
- **验收**：`bifrost-trade-frontend/src/lib/design/designRoutes.generated.ts` 的 `DESIGN_REV` 是 `2026-10-06.162`（或之后的 Rev），adoption 测试全绿；Design 项目的 DS 镜像是 0.13.0；Pine library 的 Check 小 K 线在有 Research 身份的 DEV 上走查过并写进 designNotes
- **验收结果**：部分 PASS 2026-10-06 frontend 85d93f14：DESIGN_REV = 2026-10-06.162（生成脚本 design-nav-snapshot.mjs 重生成）；`npx vitest run src/lib/design` 71 passed；DS 镜像 0.13.0（RECEIPT-ds-mirror-0.13.0）。/research/stocks、/research/backtest、/research/signal-decay 盖到 .162（reviewing）；/research/symbol 不盖：c9527e86 的五条偏离从未得到 Design 回复，已发 `design/uploads/ASK-symbol-kline-five-divergences-2026-10-06.md`。Check 小 K 线走查未做
- **现在**：DS 镜像那一半已完成（Pine 会话核过：远端 _ds_sync.json 对 bifrost-ui 2271260，fence 已清）。app 侧：researchPipeline / routeTable.research 停在 .160；.161 已建成（fe 198a8ccf + 60ed2368）未补戳；.162 Design 回执写明 app 无需改代码，纯补登记
- **下一步**：① 你在 :5173 设好 Research 用户，打开 `/research/backtest?tab=pine` 做一次 Check，结果写进 Backtest note ② Design 回复五条偏离后把 /research/symbol 盖到当时的 Rev ③ `RECEIPT-pine-library-nav-row-2026-10-06.md` 说 app 已做 `/research/pine`，但 origin/main 的 routeTable 里没有——待查去向
- **Claim**: Code is ahead of the registry: the adoption view reads stale revs for the pages these five packages touched (Research Symbol, Backtest, Signal Decay, Stock Screen), so "aligned / stale" says nothing true about them until re-synced.
- **Evidence**:
  - `bifrost-trade-frontend/src/lib/design/designRoutes.generated.ts:311` — `export const DESIGN_REV = "2026-10-04.157"`
  - `design/trade/RESPONSE-2026-10-06-rev161-receipt.md` 第 3 部分 — Design 侧 DS 镜像仍是 0.11.0
- **Impact**: The adoption page under-reports what is landed; the Design prototypes draw chips the DS already ships.
- **Fix**: Run design-sync for Rev .162 and the 0.13.0 DS mirror; re-stamp the touched pages' notes.
- **Ratchet**: None new; the existing adoption tests catch drift once the registry is current.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend, design

### TD-189

**P3 · research-data · SEPA has no rows for four sessions (08-28, 08-31, 09-08, 09-16): those nights never computed it, so the SEPA lens and its hit rate skip them**

- **状态**：观察中（0.199.0-dagster 已 apply；到 10-07 02:30 UTC research_trading_day 之后看 `sepa_covers_recent_sessions`）
- **验收**：0.198.0-dagster apply 后的下一次 research_trading_day：`features/sepa_projection` 的 `sepa_covers_recent_sessions` passed，metadata accepted_gaps 为四个日期、missing_sessions 0
- **验收结果**：部分 PASS 2026-10-07：research-api 里 `missing_sessions` = 08-28 / 08-31 / 09-08 / 09-16 + 10-06（10-06 今晚批次才投影，检查在投影之后跑）
- **现在**：诊断（副本 ops_dagster）：08-28 / 08-31 是 dbt 步骤加入批次前投影了过期 mart（写的是 08-27 收盘，已被 TD-87 改写）；09-08 / 09-16 是 husbandry_gate 因 IB Flex [1003] 失败、sepa_projection 被跳过。无法忠实回补：基本面 99.3% 在 09-29 后按 v1 重建、IV 库在之间被改写（09-15 的 iv_percentile 518 只对上 3）、dim_universe 只有当前态。所以不回补；新增 WARN 资产检查 `sepa_covers_recent_sessions`（近 30 个交易日缺 SEPA 即告警），四个已判定日期列在 `ACCEPTED_GAPS` 并写明原因（偏离原文「任何缺口都 warn」：否则会红约 3 周，删掉名单即可恢复严格）。防线 `tests/orchestration/test_sepa_session.py`（+6）。后续 TD-192
- **Claim**: After the TD-87 restate every stored SEPA date is a real session, which exposes the gaps: between 08-21 and 10-05 there are 31 sessions and 27 carry SEPA. The lens re-walk reports lenses_without_source ['sepa'] for exactly those four days.
- **Measured**: MEASURED 10-06 22:26 UTC (signal_hit sepa re-walk output; replica: 27 distinct SEPA dates).
- **Evidence**:
  - `bifrost-backups/golden-source/2026-10-06_td87-sepa-restate/README.md:28` — `08-28 and 08-31 then have no SEPA (never computed)`
- **Impact**: Four missing days in the SEPA history understate its sample and hide any setup that fired only on those days.
- **Fix**: Find why the batch skipped those nights (Dagster run history), and if SEPA can be recomputed for a past session from stock_daily, backfill the four days through the mart with an as-of parameter and re-walk the lens.
- **Ratchet**: The TD-87 asset check already flags non-trading dates; add a coverage check: SEPA dates over the last 30 sessions = trading sessions (warn on any gap).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-192

**P2 · research-control · One IB Flex failure loses that night's SEPA for good: husbandry_gate blocks sepa_projection although SEPA reads nothing from Flex, and the projection never back-fills a missed night**

- **状态**：观察中（research 0.202.0 + 0.202.0-dagster 10-07 01:4x UTC 上线；到下一个 Flex [1003] 夜看 flex_gate 失败而 sepa_projection 成功）
- **验收**：下一个 Flex [1003] 夜：同一 research_trading_day run 里 `batch__flex_gate` STEP_FAILURE 且 `features__sepa_projection` STEP_SUCCESS（`ops_dagster.event_logs` 按 run_id 查）
- **现在**：道 BB：husbandry_gate 下游 77 个资产（54 dbt + 23 Python）里只有 `engines/option_pinned_contract` 读 Flex 派生数据（Trade /executions）。`batch/husbandry_gate` key 不变、只判 Market（fail-closed）；新增 `batch/flex_gate`（failed / stale / none / unknown 都 raise），唯一下游 option_pinned_contract；dbt 源若出现 raw_broker 自动挂 flex_gate。Flex 失败的夜里 run 仍红、告警照常，SEPA / dbt / 引擎照常产出。线上已核：flex_gate 存在，子节点只有 option_pinned_contract。防线 `tests/orchestration/test_flex_gate.py`（16 个：从代码扫 raw_broker. / "/executions 读取方，须与 FLEX_READERS 及 flex_gate 下游一致）+ `test_trading_day_edges.py` 重放 [1003] 夜。后续 TD-244、TD-245
- **Claim**: husbandry_gate raises when Flex is failed / stale / none (fail-closed per TD-94) and sepa_projection depends on the gate. Two of the four SEPA gaps (09-08, 09-16) are Flex [1003] nights. The projection only writes latest_closed_session, so a skipped night is lost unless research_trading_day is re-run before the next close.
- **Measured**: MEASURED 10-06 by paydown lane P (ops_dagster runs 831ad92b, f638e59b, f9d10c09).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/plugin_batch_assets.py:235` — `raise RuntimeError(f"husbandry_gate: Flex ingest {flex_verdict} ({flex_reason}) — block dbt")`
- **Impact**: Every Flex outage (TWS log-off, report not generated) silently drops a day of SEPA history and its lens hits.
- **Fix**: Split the gate so Flex only blocks Flex-dependent assets (or make sepa_projection depend on market_eod only); optionally a run config that projects a named session while the mart still holds it. Changes TD-94's fail-closed design, so Owner decides.
- **Ratchet**: TD-189's sepa_covers_recent_sessions check already warns on a new gap.
- 审批 要你批 · 代价 S · 风险 med · repos: bifrost-research

### TD-202

**P3 · market-data · market-data code strings and scripts still mention CronJobs: the dashboard label 'CronJob archived' and verify-market-data.sh's hint are user-visible**

- **状态**：观察中（market-data 0.84.0 已上线 10-07 03:4x UTC：932f97c 快进进 main、deploy 637bfd6、12 个 pod 都是 0d09ad6d…；到 04:45 UTC 看过去 1 小时 queue-dashboard > 1 s 的请求数）
- **验收结果**：PASS 2026-10-07 932f97c：五处措辞改为 Dagster；`tests/test_k8s_no_cronjobs.py` 扩到 src / scripts 的字符串与注释、scripts/*.sh；线上 queue-dashboard 本来就不显示该标签（readiness-refresh 不在 slots 里）
- **Claim**: TD-201's guard scans Markdown only. ingest_dashboard.py:194 renders 'CronJob archived'; scripts/verify-market-data.sh:121 prints 'CronJobs may still be running'; comments in quality.py:22 and scheduler/daily.py:725, :2927.
- **Measured**: code-read 10-07 by paydown lane Y.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/ingest_dashboard.py:194` — `"readiness-refresh": "Readiness rollup — RETIRED (Wave 14G-A; CronJob archived)",`
- **Impact**: The Console and the verify script tell readers about a scheduler that no longer exists.
- **Fix**: Reword to the Dagster wording; extend test_k8s_no_cronjobs.py to scan src/**/*.py string literals and scripts/*.sh (same HISTORY_LINES allowlist). The label change ships with the next plugin release.
- **Ratchet**: The extended scan.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-210

**P1 · data · The nightly logical backup of hand-entered data failed on its first scheduled run: it connects before the new pod's NetworkPolicy is programmed and gets Connection refused**

- **状态**：观察中（授权与修复都已生效；到连续三个夜间定时 Job 都 S=1）
- **验收结果**：部分 PASS 2026-10-07：Owner 批准后本会话执行 GS 授权（2 个 research 序列 + analytics_writer 默认权限）；手动 Job logical-backup-manual-202610070314 成功，7 个目标全 ok（research 25 表 1.9M）；README Prerequisite 补上 research
- **下一步**：你以 postgres 身份在 Golden Source 跑授权（命令见线程）→ 我起一次手动 Job 复验 → 观察三个夜间定时 Job 都 S=1；README 的 Prerequisite 补上 research。旧的两个 logical-backup-scripts ConfigMap（g48f6c8k6b、tf98d5m6g7）无人引用，删不删由你定
- **现在**：道 FF：10-06 04:30Z 定时那次两次尝试前 6 个目标都 `Connection refused`（新 pod 与 NetworkPolicy 的竞态，同 memory probe-pod-networkpolicy-race），10-05 手动「成功」靠的是第二次尝试。修复：CronJob 加 `wait-pg` initContainer（同一 postgres 镜像），backup.sh 首个目标前 pg_isready 最多等 60 s；内容与写入位置不变；该目录不归 Argo，apply 前 diff 为空、apply 后只剩本改动。手动复验 `logical-backup-manual-20261007`：wait-pg 打印 `wait 1 → ready`（竞态确认被挡住），prod / stg / dev public、journal、ops_feedback、raw_broker 都 ok，**只有 `bifrost_golden_source:research` 失败：`permission denied for sequence suggestion_adoption_suggestion_adoption_id_seq`**（建议账本新表，10-05 时还没有），所以仍 PARTIAL，BifrostLogicalBackupMissing 仍 firing。防线 `scripts/check_pg_wait.py`（连 CNPG 的 Job / CronJob 必须有 wait-pg 或带理由注解；`make check-pg-wait`，并接进 run-deliver-stg / prod 发布前检查）
- **Claim**: CronJob data/logical-backup starts psql against bifrost-postgres-rw within the pod's first second. It has no wait-pg initContainer and no connect retry. The only rule letting the pod reach Postgres is a podSelector NetworkPolicy, which the k3s policy controller programs a few seconds after the pod IP exists. On 2026-10-06 04:30 UTC both attempts (backoffLimit 1) got Connection refused on 6 of 7 targets. raw_broker, the last target, dumped fine 2 s later, which is the signature of the known new-pod race, not a policy gap. The run wrote PARTIAL folders and the Job failed. Only the manual run on 10-05 has ever succeeded (and that manual job also shows one failed attempt).
- **Measured**: MEASURED 2026-10-07 00:43 UTC. job/logical-backup-29854350 Failed (BackoffLimitExceeded, S=<none> F=2). Loki for pods -hzzrm (04:30:00) and -hf6kw (04:30:12) shows 'connection to server at "bifrost-postgres-rw" (10.43.130.10), port 5432 failed: Connection refused' for bifrost_prod/stg/dev public and GS journal/research/ops_feedback, then '[bifrost_golden_source.raw_broker] ok: 10 tables, 156K' 2 s later, ending 'PARTIAL'. The CronJob's lastSuccessfulTime is 2026-10-05T20:03:26Z (the manual run). BifrostLogicalBackupMissing has been firing since 22:03Z.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/logical-backup/cronjob-backup.yaml:42` — `containers:`
  - `bifrost-trade-infra/k8s/data/logical-backup/backup.sh:74` — `log "[$target] could not export snapshot: ${snap:-<no answer>}"`
  - `bifrost-trade-infra/k8s/data/logical-backup/network-policy.yaml:17` — `- from:`
- **Impact**: The only table-level copy of hand-entered PROD data (strategy, trade, review, journal, ops_feedback) that survives a broken CNPG or Barman chain is not being made, and every nightly run depends on a scheduling race. Barman PITR still covers this data, but the logical copy is the layer meant to outlive it, and its alert reaches no human (TD-209).
- **Fix**: Add a wait-pg initContainer to CronJob data/logical-backup only. Copy the busybox `nc -z -w 2 bifrost-postgres-rw.data.svc.cluster.local 5432` loop from bifrost-research k8s/dbt/cronjob.yaml; there is no ddl-apply.yaml in infra. Also make backup.sh retry `pg_isready -h $PGHOST` for up to 60 s before the first target. Leave logical-backup-drill alone: it restores into its own emptyDir Postgres and never connects to the cluster.
- **Ratchet**: Infra manifest policy check: every Job/CronJob whose pod is a source in a postgres ingress NetworkPolicy, or whose env sets PGHOST, must have an initContainer named wait-pg (or a declared retry). BifrostLogicalBackupMissing stays as the runtime backstop, with an absent() twin.
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data get jobs -l app.kubernetes.io/name=logical-backup -o custom-columns=N:.metadata.name,S:.status.succeeded,F:.status.failed --sort-by=.metadata.creationTimestamp </dev/null | grep -v manual  # newest three scheduled jobs show S=1 and F <none>`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-218

**P2 · data · Every backup copy (Barman base+WAL, logical dumps hot and cold, the W3 archive) is on the one NAS 192.168.10.20:/volume1, and the open offsite decision is not in the ledger**

- **状态**：未开始（Owner 10-07 暂缓）
- **Claim**: Every backup copy sits on the one NAS: the Barman bucket on the NAS-native MinIO (since 10-06), the logical dumps in k3s-hot and k3s-cold, and the W3 market-data archive. The weekly 'cold' tier is on the same /volume1 as 'hot'. An offsite copy is an open W5 item in PLAN-phase0 (Owner to choose the target), and the logical-backup README notes it, but TECH_DEBT.md has no entry.
- **Measured**: MEASURED 2026-10-07. Every NFS PV (logical-backup-hot/cold, market-data-archive, both provisioner PVs, the retired minio-data PV) points at server 192.168.10.20 under /volume1/k3s-hot or /volume1/k3s-cold. NAS MinIO usage is 284.2 GiB on the same 22.3 TiB volume. No CronJob in any namespace matches offsite, mirror, rclone or sync. PLAN-phase0-foundation-2026-10-05.md lines 42/101/135 record the pending decision.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/logical-backup/README.md:25` — `the Barman WAL archive, which lives on the same NAS; an offsite copy is open.`
  - `bifrost-trade-infra/k8s/data/logical-backup/nas-volumes.yaml:4` — `# both StorageClasses Retain, so deleting a claim never deletes a backup.`
- **Impact**: There is no copy outside a single failure domain. One NAS incident (hardware, volume corruption, LAN ransomware or a wrong rm) could make both the hand-entered trade and journal data and the 34 GB Golden Source history unrecoverable.
- **Fix**: Owner picks the W5 offsite target (PLAN-phase0 line 101). Then add a nightly mirror of the bifrost-postgres-backup bucket (at least the newest base plus the WAL since) and the logical-backup cold/weekly folder to that target, and record the last success as a metric. Until then the item is tracked in TECH_DEBT.md.
- **Ratchet**: Alert BifrostOffsiteCopyStale on the mirror job's last-success timestamp (> 8 days, or absent()).
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-prometheus:9090/proxy/api/v1/query?query=time()-max(kube_cronjob_status_last_successful_time%7Bcronjob%3D%22offsite-mirror%22%7D)" </dev/null  # value < 691200`
- 审批 PROD 变更（要你批） · 代价 M · 风险 low · repos: bifrost-trade-infra

### TD-228

**P3 · ops-console · Every scheduled Hermes skill run on .52 fails with 'No such file or directory', while /health returns status ok and the checklist counts the gateway healthy**

- **状态**：观察中（platform STG 1791346065 + PROD 1791346310 已上 22863e2（10-07）；.52 网关 10-07 04:12 UTC 重部署为 v0.2.0、scripts_dir=~/bifrost-agent/hermes-scripts；到 10-07 06:00 UTC 看 stale-pipeline-triage 05:55 那次是否 success）
- **验收结果**：部分 PASS 2026-10-07：.52 /health ok、failing_skills []、v0.2.0、4 skills；PROD platform 读到 hermes_mcp ok v0.2.0。待首个排程运行。注：deploy 脚本里 `npm install` 在远端非交互 shell 找不到 npm（旧依赖仍在，服务正常）
- **Claim**: skills.yaml points at ../../scripts/agent/*.sh, resolved with cwd = the skills.yaml directory. deploy_hermes_gateway.sh rsyncs only agent/hermes-gateway to ~/bifrost-agent/hermes-gateway, so the scripts path (~/scripts/agent) never exists on the host. The deployed copy is also stale: 3 skills versus 4 in the repo. /health hard-codes status 'ok', and the hermes-tooling checklist item is healthy when hermes_mcp.status=ok. Runner failover is still covered, because a separate launchd peer_watchdog is deployed by deploy_mac_mini.sh.
- **Measured**: MEASURED 2026-10-07 01:00 UTC: .52:8782/executions?limit=50 shows 50/50 peer-watchdog failures ('bash: ../../scripts/agent/peer_watchdog.sh: No such file or directory'). /health returns ok, skill_count 3, uptime ~4.74M s (~55 days). The local bdev ring shows 500/500 failures since 10-05, including nightly-drift-scan daily at 11:00Z.
- **Evidence**:
  - `bifrost-platform/agent/hermes-gateway/skills.yaml:9` — `script: "../../scripts/agent/peer_watchdog.sh"`
  - `bifrost-platform/agent/hermes-gateway/src/scheduler.ts:92` — `cwd: this.registry.skillsDir(),`
  - `bifrost-platform/scripts/agent/deploy_hermes_gateway.sh:24` — `"${PLATFORM_ROOT}/agent/hermes-gateway/" \`
  - `bifrost-platform/agent/hermes-gateway/src/server.ts:39` — `status: 'ok',`
  - `bifrost-platform/console/src/lib/control-room/dailyOpsChecklistCatalog.ts:542` — `healthyCriteria: 'nous_hermes.status=ok OR hermes_mcp.status=ok',`
- **Impact**: Hermes-scheduled drift scanning and triage have done nothing, possibly for the whole 55-day uptime, behind a false-green health signal.
- **Fix**: Resolve script paths against an explicit HERMES_SCRIPTS_DIR and rsync scripts/agent alongside the gateway. Validate at startup that every enabled skill's script exists, and mark the skill errored if not. /health reports degraded when an enabled skill's last K runs failed. Redeploy so all 4 skills land.
- **Ratchet**: Gateway unit test: loading skills.yaml with the deploy layout (gateway dir only) fails validation for a missing script. The checklist hermes-tooling healthyCriteria adds 'no enabled skill failing for > 2 schedule periods'.
- **验收**: `curl -s 'http://192.168.10.52:8782/executions?limit=50' | python3 -c "import json,sys;e=json.load(sys.stdin)['executions'];print(sum(x['result']=='failure' for x in e),len(e))"  # failures far below total, and /health is not ok while any enabled skill is failing`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-234

**P3 · trade-worker · @bifrost/ui is unversioned for the Ops Console: a ui push never runs platform CI, and platform deliver builds whatever ui main is without recording its SHA**

- **状态**：观察中（infra 2d04455 的 5 条 Pipeline + trigger 已 apply 到集群，platform 26cd884 已上 PROD；到下一次 bifrost-ui 推 main 时看 ci-platform 是否带 uiRevision=<40hex> 起跑）
- **验收结果**：PASS（代码层 + 集群对象）2026-10-07：check_ui_revision.py 0；kubectl apply 5 Pipeline configured、bifrost-ci-platform-template 与 EventListener bifrost-ci configured
- **Claim**: Both consumers take @bifrost/ui as file:../../bifrost-ui, with Vite and tsconfig aliases to its dist, so no version is pinned. A ui push triggers only frontend-ci-ui, never ci-platform. pipeline-deliver-platform(-prod) clones bifrost-ui at $(params.revision), which can only be main, and nothing records the ui commit. Type breaks are still caught by the deliver build, but default and behaviour changes marked 'Ops 同变' reach the PROD Console untested, and a Console rollback cannot restore the ui it was built with. The Trade UserCenter UI_VERSION_NOW is a hand constant.
- **Measured**: MEASURED in cicd: ci-frontend runs carry uiRevision=<ui SHA> for 4 ui pushes; no ci-platform run in retention has a non-main uiRevision, and every bifrost-deliver-platform run binds revision=main. ui 0.10.0–0.13.0 landed 10-04..10-06 with Console defaults changed.
- **Evidence**:
  - `bifrost-trade-infra/k8s/cicd/tekton/trigger-trade-ci.yaml:250` — `- name: frontend-ci-ui`
  - `bifrost-trade-infra/k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:91` — `value: $(params.revision)`
  - `bifrost-platform/console/package.json:22` — `"@bifrost/ui": "file:../../bifrost-ui",`
  - `bifrost-trade-frontend/src/lib/design/uiVersion.ts:50` — `export const UI_VERSION_NOW = '0.13.0'`
- **Impact**: A ui change that alters Console behaviour is found only at a later platform push or in PROD, and the PROD Console's ui commit cannot be reconstructed.
- **Fix**: (1) Add a ui-push binding to the platform CI trigger (revision=main, uiRevision=$(body.after)). (2) Give pipeline-deliver-platform(-prod) its own uiRevision param, with PROD pinned from the STG run's clone-ui commit (the prod-pinned-from-stg pattern). (3) Write the ui SHA into the image (build arg → /health or an OCI label), and derive UI_VERSION_NOW from bifrost-ui/package.json at build time.
- **Ratchet**: Infra pipeline check: every pipeline that clones bifrost-ui takes a distinct uiRevision param, and trigger-trade-ci has a ui-push binding for each of them.
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n cicd get pipelineruns -o go-template='{{range .items}}{{.metadata.name}} {{range .spec.params}}{{.name}}={{.value}} {{end}}{{"\n"}}{{end}}' </dev/null | grep ci-platform | grep -cE 'uiRevision=[0-9a-f]{40}'  # ≥1 after the next ui push`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform, bifrost-ui

### TD-242

**P2 · market-data · market-data /ingest/queue-dashboard takes 5–25 s per call, and the platform-api proxy carries the same delay: with the new latency rule live it will page whenever someone keeps the queue dashboard open**

- **状态**：观察中（market-data 0.84.0 已上线 10-07 03:4x UTC：932f97c 快进进 main、deploy 637bfd6、12 个 pod 都是 0d09ad6d…；到 04:45 UTC 看过去 1 小时 queue-dashboard > 1 s 的请求数）
- **验收结果**：代码层 PASS 2026-10-07：PROD pod 内插桩，未命中缓存一次 1.6 s 里 SQL 只占 0.06 s，98% 花在 `cronutil.iter_cron_fires` 逐分钟判断（每 slot 前后 14 天，一次约 100 万次）；改为按本地日期逐天、只枚举 cron 指定的时分 → 1.66 s → 0.06–0.16 s、CPU 0.81 → 0.02 s，返回逐字节一致。防线 `tests/test_cronutil_fires.py`（旧实现作参照、全 slot + DST）+ `test_a_dashboard_miss_is_a_handful_of_reads_and_little_cpu`（CPU < 0.15 s）。线上 0.83.0 仍每小时 107 次 > 1 s
- **Claim**: 164 requests over 1 s in 90 minutes on plugin-market-data; PROD platform-api p99 2.5–7.4 s from /api/v1/plugins/market-data/api/*.
- **Measured**: MEASURED 10-07 by paydown lane CC (Prometheus, the TD-161 / TD-195 metrics).
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/ingest_dashboard.py:891` — `def build_queue_dashboard(`
- **Impact**: A slow Console page, and (after TD-194) a real-but-noisy latency alert about every 90 minutes of dashboard use.
- **Fix**: Cache the dashboard per minute (it is a derived read), or make its job_ingest / queue_sample reads cheap (EXPLAIN first; see memory plan-follows-anchor-estimate).
- **Ratchet**: A test or check that the dashboard's p99 stays under the latency rule threshold on PROD-sized data (or a cache hit test).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-244

**P3 · research-control · agents/journal_distill reads raw_broker.executions_final with no Flex freshness check (own 23:55 UTC schedule, outside any gate)**

- **状态**：观察中（research 0.203.0 已上线 10-07 04:04 UTC：api/mcp 0.203.0、Dagster 0.203.0-dagster；等下一个 Flex 失败夜看 fills_skip_reason）
- **验收**：上线后下一个 Flex 失败夜：`agents/journal_distill` 的结果带 `fills_skip_reason`、输出检查 WARN，decisions/visits/notes 照跑；单元证据 `cd bifrost-research && pytest tests/orchestration/test_flex_gate.py tests/engines -k distill -q`
- **验收结果**：PASS（代码层）2026-10-07 fb1808e：run_distill 先问 flex_gate 的判定（同一 freshness-kpis 探针与规则，重试一次、不抛错），failed/stale/unknown 只跳过 fills 记忆并写原因；FLEX_READERS 里 journal_distill 从豁免改为挂 gate，原测试强制。手工 POST /research/journal/memory/distill 走同一闸门
- **Claim**: TD-192 mapped every Flex reader; journal_distill is one of the four outside the batch and was never gated (before or after the split).
- **Measured**: code-read 10-07 by paydown lane BB.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/journal_distill.py:383` — `executions_final`
- **Impact**: On a Flex-failed night the distill writes journal rows from a stale ledger.
- **Fix**: Gate its job on flex_gate, or read freshness-kpis inside distill and skip when not fresh; tighten its FLEX_READERS entry from None.
- **Ratchet**: test_flex_gate.py's FLEX_READERS check (None entries must name a reason; drop the exemption).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-246

**P3 · trade-data · Snapshot enrich stores a vendor 'day close' that can sit below the option's intrinsic value (a stale last trade), and P&L attribution then books it as unexplained**

- **状态**：观察中（Trade 10-07 三环境：STG bifrost-deliver-stg-6wrjs、PROD bifrost-deliver-prod-pinned-ntfpf（core 0.58.0 @ 3c79f41，tag v0.58.0）、DEV 跟随；看发布后第一次 enrich 的 OPT 行 mark_source）
- **验收**：下一次 Trade 发版后 api-monitor `/health` core_sha = 668c63f；之后每环境跑 dry-run SQL，snapshot_date ≥ 发版日的行里不再有 mark 低于内在价值且标 vendor_eod 的
- **现在**：道 L4 实测：低于内在价值的 OPT 行 DEV / STG 10-05 各 1 行（DAVE 2027-01-15 280C，close 74.3 < 内在 88.94，最后成交停在 09-24），10-06 各 0 行；插件不存 NBBO，拿不到 mid；vendor IV 每个快照都在变（按报价算），BS(vendor iv) 对其余 22 个合约·日有 19 个在 ±4% 内。修法 `snapshot.daily.option_eod_mark`：close ≥ 内在 − 0.01 照旧 `vendor_eod`；否则存 BS(标的收盘, vendor IV, r 0.04) 并以内在为下限，标 `vendor_iv_model`；无 IV / 当天到期 / 模型仍低于内在 → 内在价值，标 `intrinsic_floor`。下游：greeks_quality `vendor_iv_model` → vendor、`intrinsic_floor` → degraded（一行可改：reader/snapshots.py MARKS_WITH_THE_GREEKS）；TD-140 兜底读三种日终来源里最新的一条。防线 `tests/test_snapshot_mark_intrinsic.py`（1728 组合网格、day_close 只经 option_eod_mark 读的 AST 扫描、每个 mark_source 必须归入 greeks 分级之一）+ db 测试。后续 TD-250
- **Claim**: DEV 10-05 has one LEAP call whose vendor_eod mark is below intrinsic; on 10-06 it accounts for most of the attribution's unexplained residual. TD-138's reader flags it (mark_below_intrinsic) but the writer keeps storing the last trade.
- **Measured**: MEASURED 10-07 by paydown lane AA (DEV, read-only).
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/portfolio/snapshot/daily.py:547` — `vals["mark"] = _finite(hit.get("day_close"))`
- **Impact**: P&L Explain reports a large unexplained share driven by a bad mark, not by risk.
- **Fix**: At enrich, when day_close < intrinsic (or outside the session bid/ask), use the vendor mid or bid/ask and label mark_source accordingly (new value, no DDL). Restating existing rows is an Owner decision.
- **Ratchet**: A core test: enrich never stores a mark below intrinsic without a distinct mark_source.
- 审批 已批（Owner 10-07「做」）· 代价 S · 风险 low · repos: bifrost-trade-core

### TD-250

**P3 · trade-data · A stale vendor close above intrinsic is still stored as vendor_eod: the plugin's snapshot read does not return last_trade_ts, so enrich cannot tell a morning trade from a session close**

- **状态**：观察中（Trade 10-07 三环境：STG bifrost-deliver-stg-6wrjs、PROD bifrost-deliver-prod-pinned-ntfpf（core 0.58.0 @ 3c79f41，tag v0.58.0）、DEV 跟随；看发布后第一次 enrich 的 OPT 行 mark_source）
- **验收**：插件上线后：`curl -s 'http://127.0.0.1:8780/api/v1/plugins/market-data/api/market/options/snapshots?symbol=DAVE&expiration=2027-01-15&as_of=2026-10-06'` 里 O:DAVE270115C00280000 带 last_trade_ts=2026-10-06T13:48:03.112000+00:00；core 上线后 api-monitor /health core_sha=549a656，且之后第一次 enrich 里 last_trade_ts 早于本 session 的 OPT 行不再是 vendor_eod
- **验收结果**：插件 PASS 2026-10-07 a7beb5b：DAVE 2027-01-15 280C 返回 last_trade_ts=2026-10-06T13:48:03.112000+00:00，husbandry healthy。core FAIL（未发版，预期）。代码层：插件 pytest 1281 passed，core make test 13459 / test-db 110 passed，防线 tests/test_api_session_and_filters.py 3 个 + test_snapshot_mark_intrinsic.py 网格 12,096 组
- **Claim**: query_snapshots in the market-data plugin selects iv / greeks / OI / day_volume / day_close / day_vwap but not last_trade_ts (present in raw_market.option_snapshot). DEV 10-06 DAVE 280C close 110.5 came from a 09:48 ET trade, 32% above the vendor-IV model price, and still drives a large unexplained residual.
- **Measured**: MEASURED 10-07 by loop lane L4 (DEV / STG, read-only).
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/options.py:186` — `s.iv, s.delta, s.gamma, s.theta, s.vega,`
- **Impact**: P&L attribution keeps a large unexplained share on thinly traded contracts.
- **Fix**: Plugin: add last_trade_ts to the snapshot read (additive field). Core: when the trade is not from that session, or is older than N minutes before the close and deviates from the vendor-IV model by more than a threshold, store vendor_iv_model.
- **Ratchet**: Extend test_snapshot_mark_intrinsic.py's grid with a last_trade_ts dimension.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data, bifrost-trade-core

### TD-260

**P3 · trade-core · Four LEFT JOINs still read raw_broker.contract_quote_live, which has had no writer since March and none at all after TD-240: the quote columns they feed can only ever come back NULL**

- **状态**：观察中（到 10-09，看四页的价格读数；**已上 PROD** `bifrost-deliver-prod-pinned-j4vg9`，core **0.60.0**（385b0f8，tag v0.60.0）+ frontend 81a796b）。LANE-X 先量后改：发现这四处（Accounts 环形图、Performance 固收市值、Ledger STK 快照、Watchlist Sizing / risk power）直接读 `/status` 的股票价格，读到的是 3 月旧价。core 删掉死 JOIN 后 `/status` 不再带股票价格——10-08 STG 实测持仓行只剩 `avgCost` / `position` / `category`，无价格字段——所以同一批在前端补了 `spotPrice.ts` / `usePricedStatus.ts` / `repriceAccounts`：取价顺序 live → 带日期的收盘 → 仅当 broker mark 比收盘更新才用，三者都没有就留空，**不拿成本价或行权价顶**，来源与时间跟着数字走
- **Claim**: TD-240 deleted the only writers (`write_contract_quote_live`, the mirror). Owner kept the table, so four read sites remain and each filters on `fresh_quote_sql(alias)` = `updated_at >= now() - make_interval(secs => LIVE_QUOTE_MAX_AGE_SEC)`. The newest row in PROD is 2026-03-28, so every one of these JOINs now matches nothing, for good. They are not broken — they are a live-looking quote path that cannot return a quote, which is the project's own "unmeasured shown as green" class.
- **Measured**: MEASURED 2026-10-08 (code read + the TD-240 measurement): `raw_broker.contract_quote_live` 13 rows, `max(updated_at)` 2026-03-28 06:16; after TD-240 no code writes it.
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/portfolio/model/core.py:65` — `LEFT JOIN {CONTRACT_QUOTE_LIVE} cq ... AND {fresh_quote_sql('cq')}`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:441` — `LEFT JOIN {CONTRACT_QUOTE_LIVE} ip`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/executions.py:1592` — `LEFT JOIN {CONTRACT_QUOTE_LIVE} cql`
  - `bifrost-trade-core/src/bifrost_core/portfolio/services/short_legs.py:46` — `FROM {CONTRACT_QUOTE_LIVE} q`
  - `bifrost-trade-worker/CLAUDE.md:61` — still documents `contract_quote_live`（来自 Redis 报价）as a daemon write
- **Impact**: Unknown until measured — whichever page columns these four feed read as an empty quote. The risk is a page that prints 0 or a dash where it means "nothing writes this any more". The worker doc also still tells the next reader the daemon mirrors quotes.
- **Fix**: Measure first (LANE-X): for each of the four, find what page column it feeds and what that column shows with a NULL quote. Then per site: drop the JOIN if the page has a live source already (`GET /quotes` reads Redis directly), or keep it and say on the page that the reading is not served. Do not give the table a writer — Owner chose B on 2026-10-08. Fix `bifrost-trade-worker/CLAUDE.md:61` either way.
- **Ratchet**: core `tests/test_accounts_price_not_served.py`、`test_accounts_stk_live_stale.py`（价格取不到时读作「没有供给」而不是 0）+ frontend `src/utils/spotPrice.test.ts`、`equityDelta.test.ts`、`accountsBrokerRows.test.ts`；合并态 core 13464 passed、frontend 4111 passed
- **残留**：portfolio model 仍 JOIN `contract_quote_live` 取**期权 mid**，那些行永远取不到，于是对应腿的 Greeks 记为 degraded（`degraded_leg_count`）——而前端没有任何地方显示这个计数，见 TD-264
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-worker, bifrost-trade-frontend

### TD-267

**P2 · ops-platform · An approval is consumed by a transient refusal: approve executes immediately, and a release-window clash marks the request `failed`, so the Owner's click is spent and a new request must be filed**

- **状态**：在做（修复在 platform 分支 `w31/w48-s0-0a` `249618e`，S0-0a / W-48：暂时性拒绝——发布窗口被占或缺失、HTTP 429 / 503、kube 超时——让单子保持 `approved`，按退避重试到执行截止时间；永久错误照旧失败。测试 `api/internal/approvals/state_machine_test.go` `TestTransientRefusalKeepsTheApproval`、`api/internal/server/transient_refusal_test.go`。须与 infra `w31/w48-s0-0a-infra` `779c70f` 一起合。合 main + 发版后转待你签收）
- **Claim**: `approvals.Service.approve` calls `actions.Execute` in the same step as the decision and stores `StatusFailed` on **any** error, transient or permanent (`service.go` around the `execErr` branch). Since `approve` refuses anything whose status is not `pending`, a request that failed on a precondition cannot be approved again — the human's click is gone and the requester has to create a fresh request. There is no distinction between "this can never work" (bad params, expired) and "this would work in a minute" (a release window held for other repos, CI not green yet).
- **Measured**: MEASURED 2026-10-08. `appr_cb8b3f52329cbe8c` (platform PROD, revision main) was approved through `channel: chat` at 15:50:56Z and came back `status: failed` with `REFUSED: release window held by someone else (who=… what=bifrost-trade-core,bifrost-trade-api,bifrost-trade-worker,bifrost-trade-frontend,bifrost-trade-infra); bifrost-deliver-platform-prod needs one of bifrost-platform,bifrost-ui`. The click landed inside this session's own Trade release (`bifrost-deliver-prod-pinned-9lg2r`, 15:47–15:54Z), which legitimately held the window for the Trade repos. No PipelineRun was created; platform main stayed a7ecb08 and PROD kept the old image. The window check did its job — what is wrong is that the approval did not survive it.
- **Evidence**:
  - `bifrost-platform/api/internal/approvals/service.go` — the `approve` path: `actions.Execute` then `rec.Status = StatusFailed` on `execErr`
  - the same file's guard: a record whose status is not `pending` answers `409 already decided`
- **Impact**: Every approval the Owner clicks at the wrong moment is burned, and the only recovery is for an agent to file another request and ask for another click. That makes the approval queue feel unreliable exactly when releases are busy, which is when it matters. It also pushes agents toward holding the window for long stretches before asking, which blocks everyone else.
- **Fix**: Separate the decision from the execution. On a **transient** refusal (window held by another repo set, CI not finished, a run in flight) keep the request `pending` — or move it to a `retryable` state with the reason — and let it execute when the precondition clears, rather than consuming it. Keep `failed` for permanent errors. Decide explicitly whether a retry needs a fresh click; if it does, say so in the record so the requester does not have to guess.
- **Ratchet**: A Go test that an executor returning a transient refusal leaves the request approvable (not `failed`), and that a permanent error still terminates it.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-platform

### TD-268

**P3 · ops-platform · `ExecSQLOnPrimary` is dead code: TD-256 and TD-259 took its last caller, and the ratchet that counted call sites now guards a function nobody calls**

- **状态**：未开始
- **Claim**: After TD-256 (286c305) and TD-259 (a7ecb08) moved both plugin freshness probes onto plugin HTTP, `api/internal/cluster/pod_exec.go:65` `ExecSQLOnPrimary` has **no non-test caller**. What remains is the definition plus two test files that exist only to constrain it: `execsql_callers_test.go` (the LANE-P2 ratchet, baseline 2 → 0, now satisfied) and `pod_exec_live_test.go`. A ratchet counting call sites of a function with no call sites protects nothing.
- **Measured**: MEASURED 2026-10-08 on platform main 634e305, verified in this session rather than taken from the report that raised it: `git grep -n ExecSQLOnPrimary origin/main -- 'api/**/*.go' | grep -v _test` returns only the definition at `pod_exec.go:62,65`; test references are `execsql_callers_test.go` (5) and `pod_exec_live_test.go` (4).
- **Evidence**:
  - `bifrost-platform/api/internal/cluster/pod_exec.go:65` — the definition, now unreachable from production code
  - `bifrost-platform/api/internal/cluster/execsql_callers_test.go` — the call-site ratchet
  - `bifrost-platform/api/internal/cluster/pod_exec_live_test.go` — a live test against it
- **Impact**: A `psql -tAc` helper that execs into the CNPG primary stays available to the next person who needs a quick read, which is how the privilege got entrenched in the first place. Deleting it makes the HTTP path the only way.
- **Fix**: Delete `ExecSQLOnPrimary` and the two tests that exist only for it, and replace the call-site ratchet with one asserting **zero** references to the symbol anywhere outside its own removal test. **Do not narrow PROD `pods/exec` in `data`**: `execOnPrimary` is used throughout `data_clone.go` / `data_clone_fk.go`, and `execOnMinio` by `postgres_wal_repair.go` — both verified still in use on 634e305.
- **Ratchet**: A Go test (or a code-health count) asserting 0 references to `ExecSQLOnPrimary` in the repo, so it cannot come back quietly.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-269

**P3 · ops-platform · `release.sh hold` cannot be stopped cleanly: SIGTERM waits behind its `sleep 3600`, and SIGKILL leaves a stale lock only the Owner may clear**

- **状态**：未开始
- **Claim**: `release.sh hold` ends in `while true; do sleep 3600; done`. Bash defers a trapped signal until the foreground command returns, so `kill -TERM <holder>` does nothing for up to an hour. `kill -9` works but skips the EXIT trap, so the window file and ConfigMap survive as a stale lock — and clearing that is `release.sh window --clear`, which the rules reserve for the Owner. The working way is to signal the `sleep` child instead, which lets bash return and run its trap; that is not written down anywhere.
- **Measured**: MEASURED 2026-10-08, twice in one session. First time: `kill -9` on the holder left a stale lock and cost an Owner round-trip to clear. Second time: `kill -TERM` on the holder did nothing (process still alive after the signal); `pgrep -P <holder>` then `kill -TERM` on the `sleep` child exited the holder and the trap removed both the window file and `cicd/bifrost-release-window` cleanly.
- **Evidence**:
  - `bifrost-trade-infra/scripts/release/release.sh` — the `hold` branch: `while true; do sleep 3600; done`
  - the same file's `window_open` trap, which is what SIGKILL skips
- **Impact**: Every held window that has to end early either blocks releases for up to an hour or needs the Owner to clear a lock. It is pure friction on a path agents take often, and it makes the stale-lock warning appear for a reason that has nothing to do with a crash.
- **Fix**: Make `hold` interruptible — wait on something a signal can break (`sleep` in a background job plus `wait`, or a `read` with a timeout), so SIGTERM runs the trap immediately. Then say in `docs/RELEASE.md` how to end a hold.
- **Ratchet**: A shell test that sends SIGTERM to a `hold` and asserts the window file is gone within a couple of seconds.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-272

**P3 · ops-platform · tekton-trigger can create any PipelineRun in cicd, and no admission policy matches it, so its token is still a path to the cluster-admin Argo controller account**

- **状态**：未开始
- **Claim**: TD-271's policies match only the platform identities and tekton-deliver. Role `cicd/tekton-trigger-runs` grants `tekton-trigger` create on PipelineRuns and TaskRuns (and get/list/watch on Secrets in cicd). A run it creates may inline a spec, use a resolver, bind a secret workspace or name `argocd-application-controller`. The EventListener only renders fixed TriggerTemplates, so the exposure is the SA token or the EventListener pod, not an anonymous webhook.
- **Measured**: MEASURED 2026-10-09 (Claude, read-only). Role rules: `pipelineruns, taskruns` create/get/list; `secrets` get/list/watch. `40-admission.yaml` matchConditions list `bifrost-platform` (STG, PROD) and `tekton-deliver` only.
- **Evidence**:
  - `bifrost-trade-infra/k8s/platform-rbac/40-admission.yaml` — `matchConditions` of `bifrost-platform-pipelinerun` / `bifrost-platform-taskrun`
  - live: `role/tekton-trigger-runs` in cicd
- **Impact**: Whoever holds the tekton-trigger token is cluster-admin through the Argo account, the same way the platform was before TD-271.
- **Fix**: Add `system:serviceaccount:cicd:tekton-trigger` to the two run policies' matchConditions, after measuring that its TriggerTemplates only use `pipelineRef` names, volumeClaimTemplate workspaces and the `default` account. Drop the Secrets list/watch from its role if the interceptors do not need it.
- **Ratchet**: `check_admission_guards.py --live` gains the same inline / resolver / secret-workspace cases as tekton-trigger, plus a normal templated run allowed.
- 验收: `python3 scripts/check_admission_guards.py --live`（tekton-trigger 的反例被拒、正常 run 放行）
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-276

**P3 · ops-platform · An apply_manifest run is named apply-<plan id>, so a failed apply of a plan cannot be retried; a new plan is needed**

- **状态**：在做（修复在 platform 分支 `w31/w48-s0-0a` `249618e`，S0-0a / W-48：apply 的 run 改名 `apply-<plan>-<unix>` 并带 `bifrost.io/plan` 标签，同一 plan 重试会新建 run。测试 `api/internal/workactions/apply_retry_test.go`。合 main + 发版后转待你签收）
- **Claim**: `workactions.Apply` names the run `trimName("apply-" + planID)`. After an apply of a plan fails, a second approved apply of the same plan fails at create with `pipelineruns.tekton.dev "apply-<plan>" already exists`, and the approval ends `failed`.
- **Measured**: MEASURED 2026-10-09: `appr_49781a21b0d86b9d` (plan `plan-1dfc9375-1791567153`, whose first apply failed closed) → `failed`, `already exists`. A fresh plan applied fine.
- **Evidence**:
  - `bifrost-platform/api/internal/workactions/service.go` — `name := trimName("apply-" + planID)`
- **Impact**: Small. The caller must plan again; the error looks like a platform fault. Approval audit shows a failed C-tier action that changed nothing.
- **Fix**: Name the run `apply-<plan>-<unix>` (keep the plan id in a label) or refuse the request up front when an apply of that plan already succeeded.
- **Ratchet**: workactions test: two Apply calls for one ready plan create two distinct runs (or the second is refused with a clear message when the first succeeded).
- 验收: `cd bifrost-platform/api && go test ./internal/workactions -run Apply -count=1`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-283

**P3 · ops-platform · `release.sh dev` still restarts DEV with `kubectl rollout restart`, which the read-only Agent identity cannot do since W-33 step 3**

- **状态**：未开始
- **Claim**: The retag step works (registry HTTP), then `scripts/registry/dev-sync-backend-images.sh` runs `kubectl -n bifrost-dev rollout restart` and the release reports `failed`. Measured 2026-10-10 03:47Z: six `:dev` tags moved, summary `dev (failed)` in 3 s.
- **Evidence**: `bifrost-trade-infra/scripts/registry/dev-sync-backend-images.sh:73` — `kubectl -n bifrost-dev rollout restart "deploy/$d"`
- **Fix**: restart through the platform action `rollout_restart_deployment` (B in bifrost-dev), as release.sh already does for its other writes.
- **Ratchet**: `scripts/release/test_w33c_static.py` refuses `kubectl … rollout restart` / `apply` / `delete` in release scripts.
- 验收: `release.sh dev` exits 0 with the Agent kubeconfig.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-284

**P3 · ops-platform · Plugin and pine image builds cannot be started through `start_pipeline_run`: the image tag and workspaces are not passed, and the pine pipeline is missing from the release-window map**

- **状态**：未开始
- **Claim**: `start_pipeline_run` maps `tag` to the image only for research and market-data; `bifrost-build-flex-query` built its default `:0.2.0` instead of `0.13.2`, `bifrost-build-ib-gateway` has the same shape, and `bifrost-build-research-pine` needs a `build-context` workspace (`InvalidWorkspaceBindings`). Pine is also absent from `guardedPipelineRepos`, so any open window refuses it. On 2026-10-10 the three were rebuilt with the Owner's `kubectl create`.
- **Evidence**: `bifrost-platform/api/internal/delivery/release_window.go` `requiredRepos`; PipelineRuns `bifrost-build-flex-query-1791604363` (image `:0.2.0`), `bifrost-build-research-pine-1791604434` (`InvalidWorkspaceBindings`)
- **Fix**: per-pipeline image and workspace templates in the delivery catalog (the volumeClaimTemplate the VAP allows); register pine with repo `bifrost-research`.
- **Ratchet**: delivery test: every build pipeline in the catalog can be started with `tag` and gets its workspaces; every guarded pipeline maps to a repo.
- 验收: the three builds start through `start_pipeline_run` with the right tag.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-285

**P2 · ops-platform · The applier cannot take over a field that `kubectl-client-side-apply` owns: plan and apply fail with a server-side apply conflict**

- **状态**：未开始（Owner 2026-10-10 定：给 applier 的 diff 和 apply 加 `--force-conflicts`，边界由 allow-list 和准入策略兜住；W-31 第 0 步第 2 波做，apply 要你批）
- **Claim**: Objects first applied by hand (client-side) keep their fields under `kubectl-client-side-apply`. The applier's server-side apply then conflicts on any changed field. Measured 2026-10-10: `plan-ee6f0ba5-1791604913` for `k8s/ib-gateway/overlays/live` — `conflict with "kubectl-client-side-apply" … .containers[name="ib-gateway"].image`; the Owner applied it by hand.
- **Evidence**: `bifrost-trade-infra/k8s/cicd/tekton/apply-manifest/pipeline.yaml` — diff and apply without `--force-conflicts`
- **Fix**: either `--force-conflicts` on the applier's diff and apply (git is the source of truth; the allow-list and admission policies still bound it), or a one-off ownership migration per object by the Owner.
- **Ratchet**: `check_admission_guards.py` asserts whichever is chosen.
- 验收: a plan that changes a client-side-applied field succeeds and applies.
- 审批 要批 · 代价 S · 风险 med · repos: bifrost-trade-infra

### TD-286

**P2 · ops-platform · Approval notifications carry no short id or parameters and their delivery is not recorded; the session, Console and phone are not one approval experience**

- **状态**：在做（修复在 platform 分支 `w31/w49-s0-0b` `56b12b2`，S0-0b / W-49，基于 W-48：推送标题 `#n · tier · action · env`，正文是动作目录的一行摘要、关键参数、请求者 / 线程 / work id、谁执行、到期时间，`owner_run_command` 的命令全文不进推送；每次通知按目标记一条投递记录（单子上的 `deliveries[]`：kind、channel、target、at、result accepted / failed / skipped、error）并写审计 `approval.notify`，relay 挂了也不让建单失败。合 main + 发版后转待你签收；签收前按 W-49 的验收在 STG 建一张 C 级 `trigger_cnpg_backup` 单看手机和 deliveries）
- **Claim**: The ntfy message is `<who> requested <action> (tier X). Open to approve or reject.`: no number, no pipeline, environment or commits. Delivery is not logged per message (the operator-plane log only records startup); on 2026-10-10 all four approval messages reached ntfy (priority 4, click link) but the Owner's phone showed none. The Console approvals page shows raw JSON params and plan output and does not group pending / executed / rejected. A session can approve only through a tool permission prompt. After a click on Approve the page gives no confirmation: the card stays under `Open request` with status `executed` and no button, and for a record-only action (`rolling_reboot`) `executed` means only that the approval was recorded. On 2026-10-10 the Owner approved `appr_49d505d827db8b4a` in Console (channel console, 05:17:26Z) and then reported that the approve button could not be found. The recorded command in the result also omits the flags the requester asked for (`--upgrade`).
- **Evidence**: `bifrost-platform/api/internal/approvalnotify/notify.go:116`; `bifrost-platform/api/internal/alertrelay/relay.go` `handleNotify`
- **Fix**: short numeric approval number; message with action, environment, key params, requester thread, expiry; delivery result stored on the approval; Console page grouped by status with readable params and plan; chat reply `批 #n` path; executor for `owner_run_command`.
- **Ratchet**: notify test asserts number and params in the message; approvals store a delivery record.
- 验收: the next C-tier request shows `#n`, action and environment on the phone and its delivery status in Console.
- 审批 要批（设计）· 代价 M · 风险 low · repos: bifrost-platform

### TD-287

**P3 · ops-platform · The gpu-server power manager on ubt-k3s-01 has failed every poweroff since the node key changed and logs success; the platform's wake and poweroff actions have no SSH identity**

- **状态**：未开始（归多 Agent 协作项目第 0 步「审批后由系统执行」：带外操作面上的执行者）。方案见 `work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md`，实现在 S0-0c（W-50），等 W-42 合 main（Owner 10-10 按推荐定了执行卡 1–7）
- **Claim**: `bifrost-gpu-power-manager.service` (enabled, active on ubt-k3s-01) drains gpu-server after 30 idle minutes, then runs `ssh vision@192.168.10.60 'sudo -n systemctl poweroff'`. Since the node key change (W-33 step 3) .60 answers `Permission denied (publickey)`; the script discards the error (`2>/dev/null … || true`) and logs `Poweroff command sent` every ~33 minutes. gpu-server has been up since 2026-10-09 03:26Z with no workload (cordoned since 08-02, only DaemonSet pods, `ai` namespace empty). The service also runs on the sole control plane with that node's admin kubeconfig. The platform actions `wake_compute_node` (B) and `poweroff_compute_node` (D) SSH from platform-api, whose PROD pod has no SSH identity, so neither can work.
- **Evidence**: `bifrost-trade-infra/scripts/k3s/gpu-node-power-manager.sh` `power_off_node`; node journal 2026-10-10 04:40:16Z `vision@192.168.10.60: Permission denied (publickey)` then `Poweroff command sent`; `bifrost-platform/api/internal/cluster/node_power.go:254`
- **Fix**: one owner for gpu-server power, on the out-of-band operator plane (.50): WOL needs no credential; poweroff uses a dedicated key that .60 restricts to a forced `sudo -n systemctl poweroff` (from .50 only, no pty, no forwarding). Report the real exit status. Retire the unit on ubt-k3s-01 and route the two platform actions to that executor.
- **Ratchet**: test that `power_off_node` fails (and does not log success) when ssh fails; `check_platform_maintenance.py` lists the power manager under exactly one runtime.
- 验收: gpu-server idle for 30 minutes powers off; a Pending compute pod wakes it; the log shows the ssh exit status.
- 审批 要批（钥匙与放置）· 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-288

**P2 · infra · ubt-k3s-01, the sole control plane and etcd member, went down at 2026-10-10 01:18Z without a shutdown, and none of its boots since June recorded a clean shutdown; nothing alerts on an unplanned node reboot**

- **状态**：观察中（到 11-09，看 01 在两次计划内重启之外有没有再重启：`changes(node_boot_time_seconds{instance="192.168.10.73:9100"}[30d])`。Owner 10-10 查了 UPS，正常，认为不用再追。原因仍未知，所以不删：告警那一半归 W-31 第 0 步；30 天内没有再出现就交签收，再出现就读上一次开机的内核日志，脚本在 Fix 里）
- **Claim**: The previous boot's journal ends at 01:18:36Z with routine k3s lines and no shutdown sequence; the next boot started 01:19:31Z (node-exporter boot time 01:19:26Z). Bare metal (`systemd-detect-virt` none), no `Automatic-Reboot`, last apt run 10-09 06:36, memory 16 of 24 GB free and load 0.57 before, no platform audit record, no session active. `last -x` shows five boots since 06-08, all without a shutdown record; the 08-11 18:14Z → 08-12 23:50Z gap is 29.5 hours. The reboot emptied the in-cluster registry (fixed by TD-282's persistent volume) and was found only through that symptom.
- **Evidence**: ubt-k3s-01 `journalctl --list-boots` (boot -1 ends 2026-10-10 01:18:36 UTC); Prometheus `node_boot_time_seconds{instance="192.168.10.73:9100"}` = 1791595166; kube-state-metrics: almost every pod on ubt-k3s-01 got a new pod IP.
- **Fix**: the alert below, so the next one is seen when it happens. Owner checked the UPS on 2026-10-10: fine, so mains power is unlikely. If it happens again, read on ubt-k3s-01 (Owner's node key): `journalctl -k -b -1 -p warning`, `ls /sys/fs/pstore /var/crash`, `sysctl kernel.panic`, and whether `last -x` shows a shutdown record for the planned reboot of 2026-10-10 05:35Z (if it does not, the missing records before it mean nothing). Hardware then: PSU, memory, board; it is the only control plane.
- **Ratchet**: alert `BifrostNodeUnexpectedReboot`: `changes(node_boot_time_seconds[15m]) > 0` on a node that no `rolling_reboot` approval covers (rule test in `check_alert_rules`).
- 验收: the alert rule exists and fires in a rule unit test; the cause is written here, or the node has run 30 days without an unclean boot.
- 审批 不用批（查硬件要你到场）· 代价 S · 风险 med · repos: bifrost-trade-infra

### TD-289

**P2 · infra · Prometheus, Alertmanager and Grafana keep their data in emptyDir: a node drain erases the metric history (10 days), the silences and Grafana's own database**

- **状态**：观察中（到 10-11 06:05 UTC，看 Prometheus 日志里有没有 WAL、compaction 或 `corrupt` 报错：TSDB 在 NFS 上，上游不支持，启动时自己会打一条 WARN。有报错就改用固定节点的 local-path；没有就进待你签收）
- **验收结果**：PASS 2026-10-10 c6fa1c1（Owner 06:04Z helm upgrade，revision 17；`check_monitoring_persistence.py --live` 退出 0，两个卷 Bound 在 `nfs-hot`；06:09:34Z 用 `delete_pod` 删掉 Prometheus Pod，新 Pod 在 ubt-k3s-04 起来，WAL 重放 0.9 秒，`count(up offset 4m)` 仍返回 75，最早样本仍是 06:04:28Z）
- **Claim**: `values-kube-prometheus.yaml` sets `retention: 10d` and no `storageSpec`, so the operator gives Prometheus an emptyDir. That survives a node reboot (same pod) but not an eviction. The rolling reboot of 2026-10-10 drained ubt-k3s-01 with `--delete-emptydir-data`; the new Prometheus pod started 05:32:13Z on ubt-k3s-06 with an empty TSDB: at 05:54Z `count(up offset 30m)` returned nothing, while 36-hour windows had answered at 04:41Z. Alertmanager (`alertmanager-db`) and Grafana (`storage`) are emptyDir too. Same class as TD-282 (registry). The check before the run read PodDisruptionBudgets and did not look at emptyDir state.
- **Evidence**: `bifrost-trade-infra/scripts/k3s/values-kube-prometheus.yaml:41` — `retention: 10d`, no `storageSpec`; pod `prometheus-kube-prometheus-stack-prometheus-0` volume `prometheus-kube-prometheus-stack-prometheus-db emptyDir {}`
- **Fix**: `prometheusSpec.storageSpec.volumeClaimTemplate` and `alertmanagerSpec.storage` on a PersistentVolume (nfs-cold like the registry, or local-path pinned to one node); Grafana persistence, or dashboards only from provisioning. Helm upgrade by the Owner.
- **Ratchet**: `scripts/check_monitoring_persistence.py` (static: both values carry a claim and Prometheus a `retentionSize` below it; `--live`: both pods mount a Bound PersistentVolumeClaim), `make check-monitoring-persistence`, 9 tests. No general check for "this emptyDir holds state": a volume name does not say it. The emptyDir users left on 2026-10-10 are Grafana (on purpose), Argo CD caches, CNPG scratch and Traefik; platform state goes to ConfigMaps (TD-196) and the registry to a claim (TD-282).
- 验收: `KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_monitoring_persistence.py --live` exits 0; then delete the Prometheus pod (`delete_pod`) and `count(up offset 30m)` still answers.
- 审批 要批（存储位置）· 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-290

**P3 · ops-platform · The retired remediation runner's ConfigMap `cicd/bifrost-remediation-runner-stg-dockerfile` is still in the cluster, and the platform still lists it**

- **状态**：在做（10-10：两处名单已删，platform `d6b2849`。删 ConfigMap 留给 S0-0c（W-50）做演练：Owner 只点一次批准，系统执行并回写结果（Owner 10-10 定）。在那之前不建单）
- **Claim**: The runner and Hermes were retired in W-33 and their plists were deleted in W-36 (D-6), but the Dockerfile ConfigMap created 2026-06-21 is still in `cicd`. Nothing builds from it. The supply check keeps it in its Dockerfile list and the Console deliver phases show it as `retired-dockerfile`, so deleting only the ConfigMap would turn the supply check red.
- **Evidence**: `kubectl -n cicd get cm bifrost-remediation-runner-stg-dockerfile` (2026-10-10, exists); `bifrost-platform/api/internal/delivery/supply_chain.go:25`; `bifrost-platform/console/src/lib/delivery/deliverPlatformPhases.ts:5`
- **Fix**: drop the name from both lists (one platform commit), then delete the ConfigMap through an approval (`owner_run_command`, the Agent identity is read-only).
- **Ratchet**: none new: the supply check already fails on a listed ConfigMap that is missing, which is why the code goes first. `check_hardcoded_paths.py` does not cover cluster objects.
- 验收: `kubectl -n cicd get cm bifrost-remediation-runner-stg-dockerfile` → NotFound; `git -C bifrost-platform grep -n remediation-runner-stg-dockerfile origin/main` → no hits outside tests; the supply check stays green.
- 审批 要批（删集群对象）· 代价 S · 风险 low · repos: bifrost-platform

### TD-291

**P3 · ops-platform · The PROD operator plane probes git-bridge on the Owner's laptop (192.168.10.40:8785) and gets 401, so agent-bridge shows git_bridge unavailable instead of local-only**

- **状态**：在做（10-10：部署脚本不再写 `GIT_BRIDGE_URL`，提示文案同步改，platform `16ece5a`。重新部署两台 Mini 的主机变更并入 S0-0c（W-50），Owner 10-10 定；部署之后线上才变成 `not_configured`）
- **Claim**: git-bridge is a dev-workstation tool (`handler.go` treats an unset `GIT_BRIDGE_URL` as `not_configured` / "local-only (dev workstation)"). PROD platform-api forwards the agent-bridge routes to the operator plane on the Mac Mini (`OPERATOR_PLANE_URL=http://192.168.10.50:8783`), and the Mini's plane env sets `GIT_BRIDGE_URL` to the laptop. The laptop's bridge only accepts tokens loaded on the laptop, so every probe is a 401 and Console reports a failure for something PROD should not depend on. The variable is not in the k8s overlay: the PROD platform-api pod, its ConfigMap `bifrost-platform-config` and the image Dockerfile do not set it (checked 2026-10-10); the Mini deploy script writes it.
- **Evidence**: `get_agent_bridge` on PROD (2026-10-10): `git_bridge {url: http://192.168.10.40:8785, status: unavailable, error: HTTP 401 Unauthorized}`; `bifrost-platform/scripts/agent/deploy_mac_mini.sh:575` (`export GIT_BRIDGE_URL=http://${PLATFORM_LAN_HOST}:8785` into `env.operator-plane.sh`); `bifrost-platform/api/internal/server/server.go:154` (routes forwarded to the plane); `bifrost-platform/console/src/lib/agent/operatorPlaneFixPrompt.ts:42` and `bifrost-trade-infra/agent-config/MAINTAINERS.yaml:378` both say PROD should point at `192.168.10.40:8785` (MAINTAINERS also names platform-workers, which does not set it).
- **Fix**: stop writing `GIT_BRIDGE_URL` in `deploy_mac_mini.sh` (keep `SATELLITE_PROBE_BRIDGE_URL`, which answers `ok`); fix the two texts; the Owner re-runs `deploy_mac_mini.sh` for .50 and .52 (host change, not a cluster write).
- **Ratchet**: `bifrost-platform/scripts/agent/test_deploy_mac_mini_secrets.py` `test_plane_env_does_not_point_at_git_bridge`: the `env.operator-plane.sh` heredoc has no `GIT_BRIDGE_URL` and the script has no `:8785` (platform `16ece5a`).
- 验收: `get_agent_bridge` on PROD → `git_bridge.status == "not_configured"`; `git -C bifrost-platform grep -n GIT_BRIDGE_URL origin/main -- scripts/agent/deploy_mac_mini.sh` → no hits.
- 审批 要批（重部署两台 Mini 的 operator plane）· 代价 S · 风险 low · repos: bifrost-platform, bifrost-trade-infra

### TD-292

**P2 · infra · The powered-off standby node gpu-server keeps 18 warning alerts firing in Prometheus, so the Console header verdict is stuck at Degraded and a real warning cannot be seen**

- **状态**：未开始（不碰 TD-288：那条是 01 的非计划重启，观察中）
- **Claim**: gpu-server is the elastic WOL standby; cordoned and powered off is its normal state. `BifrostElasticStandbyMarker` fires for it and Alertmanager's `inhibit_rules` mute part of the noise, but inhibition lives only in Alertmanager. The W-44 header (`shellStatusLine.ts` `alertCauses`) counts warnings from `GET /api/v1/telemetry/alerts`, which is Prometheus `/api/v1/alerts` (`bifrost-platform/api/internal/telemetry/client.go:148`) and knows nothing about inhibition. On 10-10 07:38Z 22 warnings fired, 18 of them from gpu-server, so the header says Degraded all the time and a new real warning changes nothing on it. The inhibit rules also miss some of them: `TargetDown` only for jobs matching node-exporter / kubelet (not promtail, node-reboot-required), and `BifrostPromtailScrapeDown` carries no `node`.
- **Evidence**: PROD Prometheus 2026-10-10 07:38Z: `count by (alertname, node, job) (ALERTS{alertstate="firing",severity="warning"})` → 22; with `kube_pod_info` joined, gpu-server accounts for `KubeNodeUnreachable` 1, `KubeletInstanceUnreachable` 1, `KubePodNotReady` 4, `KubeDaemonSetRolloutStuck` 4 (promtail, svclb-traefik, node-exporter, node-reboot-required), `KubeDaemonSetMisScheduled` 2, `BifrostPromtailScrapeDown` 1, `TargetDown` 5 (node-exporter, kubelet, promtail, node-reboot-required, grafana; grafana not yet tied to the node). The other 4 are `KubeJobFailed` 3 and `BifrostMaintainerPatrolCertExpiryStale` 1. `kube_node_spec_unschedulable{node="gpu-server"} = 1`, Ready = 0; `ALERTS{alertname="BifrostElasticStandbyMarker"}` firing. Inhibit rules: `bifrost-trade-infra/scripts/k3s/values-kube-prometheus.yaml:178-196`; marker: `k8s/monitoring/bifrost-alerting-rules.yaml:429`.
- **Fix**: in the alerting layer, not in the Console: (1) cover every alert the standby produces while cordoned and off: extend the inhibit rules (TargetDown for promtail / node-reboot-required, `BifrostPromtailScrapeDown` by instance → node) and, for the stack's default rules that Prometheus still reports as firing, add `unless on (node) ALERTS{alertname="BifrostElasticStandbyMarker"}` through `defaultRules.disabled` + Bifrost copies, so they stop firing instead of only being muted; (2) the header's alert source counts what Alertmanager would deliver: `/telemetry/alerts` reads Alertmanager `/api/v2/alerts?inhibited=false&silenced=false` (or returns its `status.inhibitedBy`), the Console keeps counting severities as now. Helm upgrade by the Owner.
- **Ratchet**: a promtool rule test (`k8s/monitoring/rule-tests/`, `make check-alert-rules`) that powers gpu-server off in series data and expects no warning from the node, its DaemonSet pods or its scrape targets; plus `check_alert_routing.py` asserting every node-scoped default alert name is either rewritten with the standby `unless` or inhibited by `elastic_standby="true"`.
- 验收: gpu-server cordoned and off: `count(ALERTS{alertstate="firing",severity="warning"} and on(node) kube_node_info{node="gpu-server"})` → 0 and no TargetDown for its targets; Console header no longer says Degraded because of it; waking the node (WOL) and uncordoning raises nothing new.
- 审批 要批（helm upgrade 监控栈）· 代价 M · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-293

**P2 · infra · The platform service accounts of STG and PROD can create, update and patch any ConfigMap in cicd, so either can lift the release freeze or rewrite the release window without the Owner's signature**

- **状态**：未开始（W-42 交回 10-10；STEP0-PLAN 0.6 节）
- **Claim**: W-42 put the signed release policy (`bifrost-release-policy`), the freeze (`bifrost-release-freeze`) and the release window (`bifrost-release-window`) in `cicd`. platform-api is meant to be the only writer, and unfreezing needs an Owner signature over `frozen_at`. But the ClusterRole bound to both platform service accounts in `cicd` grants configmap writes with no `resourceNames`. A patch straight to the ConfigMap (`frozen=false`, or a different window holder) skips the signature check: the policy survives because platform-api re-verifies its signature, the freeze and the window do not. The STG account can write the same ConfigMaps PROD reads, although STG only observes releases.
- **Evidence**: `bifrost-trade-infra/k8s/platform-rbac/00-clusterroles.yaml:86-93` (`bifrost-platform-state`: configmaps `get, list, watch, create, update, patch`, no `resourceNames`), bound in `cicd` by `k8s/platform-rbac/10-stg.yaml:127-134` (SA `bifrost-platform` in `bifrost-platform-stg`) and `k8s/platform-rbac/20-prod.yaml:127-134` (PROD); `00-clusterroles.yaml:155` adds `update, patch` on configmaps for the Gitea creds role. Freeze logic: `bifrost-platform/api/internal/releasepolicy/handler.go:72`, `actions/catalog.go:130-141`.
- **Fix**: give the platform accounts in `cicd` only the names they write: a Role with `resourceNames` for update/patch of `bifrost-release-policy`, `bifrost-release-freeze`, `bifrost-release-window` and the record ConfigMaps (PROD only); `create` cannot be limited by name, so either keep platform-created ConfigMaps under a fixed name list created once by the applier, or add a ValidatingAdmissionPolicy that refuses platform-SA writes in `cicd` outside a name/label allow list. The STG account loses write in `cicd` (TD-223 already stopped STG writing release records).
- **Ratchet**: extend `scripts/check_platform_rbac.py` with "should not" rows: as each platform SA, `patch configmaps/bifrost-release-freeze` and `create configmaps` with an unlisted name in `cicd` are denied (STG: every configmap write in `cicd` denied).
- 验收: `make check-platform-rbac` with the new rows → all pass on the cluster; `kubectl auth can-i patch configmap/bifrost-release-freeze -n cicd --as=system:serviceaccount:bifrost-platform-stg:bifrost-platform` → no.
- 审批 要批（改集群 RBAC，apply_manifest）· 代价 M · 风险 med（漏一个名字会让 platform 写记录 403）· repos: bifrost-trade-infra

### TD-294

**P3 · infra · The Tekton freeze check only runs in pipelines that start with release-window; the Trade and platform deliver pipelines and three build pipelines do not, so a run created outside platform-api ignores a freeze**

- **状态**：未开始（W-42 交回 10-10。交回原话「flex-query 构建流水线没有发布窗口任务」实测不成立：`bifrost-platform-plugin-flex-query/k8s/cicd/pipeline-build.yaml:27` 与集群上 `bifrost-build-flex-query` 的第一个 task 都是 `release-window`，跑在已绑定读权限的 `default` SA 下，apply 新 task 后就带冻结检查）
- **Claim**: W-42 added the freeze check to `task-release-window.yaml`, so it runs only where that task is the first task: `bifrost-build-research-dagster`, `bifrost-build-ib-gateway`, `bifrost-build-market-data`, `bifrost-deliver-research` and (from its plugin repo) `bifrost-build-flex-query`. `bifrost-deliver-stg`, `bifrost-deliver-prod`, `bifrost-deliver-platform`, `bifrost-deliver-platform-prod`, `bifrost-build-stg`, `bifrost-build-frontend-stg` and `bifrost-build-research-pine` have no such task: a freeze stops them only when they are started through platform-api (`start_pipeline_run`, refused with 409). A run created another way — the Owner's `kubectl create -f` from `prod-pinned-from-stg.sh` / `platform-prod-pinned-from-stg.sh`, or tekton-trigger (TD-272) — runs while frozen.
- **Evidence**: `rg -l release-window bifrost-trade-infra/k8s/cicd/tekton/pipeline-*.yaml` → 4 files; first tasks `pipeline-deliver-stg.yaml:40` `mirror-sync`, `pipeline-deliver-prod.yaml:59` `preflight-stg`, `pipeline-deliver-platform.yaml:34` `mirror-sync`, `pipeline-deliver-platform-prod.yaml:37` `preflight-stg`; freeze step `k8s/cicd/tekton/task-release-window.yaml:175-205`; platform-side gate `bifrost-platform/api/internal/server/actions_wire.go:37`.
- **Fix**: a freeze-only task (reads `bifrost-release-freeze` only; the window stays with `release.sh` for Trade and platform) as the first task of those seven pipelines, run under the SA each pipeline already uses (`tekton-deliver` and `default` are bound to `tekton-release-window`).
- **Ratchet**: `scripts/check-release-chain.py` gains an assertion driven by `agent-config/release-policy/template.json` `allow` plus the build pipelines: each one's first task is `release-window` or the freeze-only task; a pipeline whose YAML is not found fails rather than skips (same rule as the TD-263 check).
- 验收: `python3 scripts/check-release-chain.py` passes with the new assertion; a frozen drill: `kubectl create` of a pinned PROD run is refused by its first task.
- 审批 要批（apply 七条 Tekton 流水线到 cicd）· 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-295

**P2 · ops-platform · start_pipeline_run checks one revision in every repo a pipeline clones, so a platform deliver cannot be started by full SHA: the W-42 pinned rule for bifrost-deliver-platform-prod can never be met through the API**

- **状态**：未开始（W-31 第 9 步调查 10-10 发现；第 9 步用 `revision=main` 绕开，见 STEP0-PLAN 0.7 节）
- **Claim**: Before creating a run, platform-api runs `RefPreflight(pipeline, revision)` against every repo the pipeline clones; for both platform deliver pipelines that is `bifrost-platform` and `bifrost-ui`. A platform commit never exists in `bifrost-ui`, so any full-SHA (or platform-only branch) revision is refused as "missing in: bifrost-ui"; `params.uiRevision` changes the clone param but not the preflight. W-42's `paths.json` pins `bifrost-deliver-platform-prod` to full SHAs (`revision` and `uiRevision` equal to the newest `bifrost-deliver-platform` record), so a request that the policy would auto-approve is one the API refuses; with `revision=main` it starts but the policy answers "not a full commit id". The preflight also reads the Gitea mirror before the pipeline's own mirror-sync, so a SHA pushed after the last sync is "missing" even in its own repo.
- **Evidence**: `bifrost-platform/api/internal/delivery/service.go:237` (preflight with the single `rev`), `service.go:530-531` (`uiRevision` defaults to the same `rev`), `supply_chain.go:41-42` (both platform pipelines clone `bifrost-platform` and `bifrost-ui`), `ref_preflight.go:85`; `api/internal/releasepolicy/engine.go:493-545` (`pinnedReasons`: full SHAs required); `bifrost-trade-infra/agent-config/release-policy/paths.json` `pinned`. Gitea mirror on 10-10: main `efeaf69` while GitHub main is `66496a6`.
- **Fix**: preflight each repo at the ref the run will clone it at (`revision` for `bifrost-platform`, the caller's `uiRevision` or `revision` for `bifrost-ui`, the Trade per-repo params likewise), computed after `mergePipelineParams`; for a full SHA missing from the mirror, sync that mirror first (or report Unknown rather than missing).
- **Ratchet**: Go tests in `api/internal/delivery`: `bifrost-deliver-platform-prod` with `revision=<platform sha>` and `params.uiRevision=<ui sha>` passes preflight when each SHA exists in its own repo, and is refused when either is missing; a `releasepolicy` test that the request `platform-prod-pinned-from-stg.sh` describes reaches `Auto` under a signed policy.
- 验收: `cd bifrost-platform/api && go test ./internal/delivery/ ./internal/releasepolicy/`; on STG, `start_pipeline_run name=bifrost-deliver-platform revision=<platform full sha>` with `params.uiRevision=<ui full sha>` starts.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-296

**P2 · ops-platform · The ntfy connection error text carries the full topic (the read credential) and is served by the token-less relay status endpoint; with W-49 it would also reach approval delivery records**

- **状态**：在做（W-49 审计 10-10 发现；掩码已在 platform 分支 `w31/w49-s0-0b` `56b12b2`，防线 `api/internal/alertrelay/relay_test.go` `TestNotifyFailureNamesTheReasonWithoutTheTopic`。关闭条件：合 main + 重新部署 .50 operator-plane，并入 S0-0c / W-50）
- **Claim**: The relay posts to `NtfyURL + "/" + Topic`. When the request fails, Go's HTTP client error quotes the whole URL (`Post "<ntfy>/<topic>": …`), so the error text contains the topic. Anyone who knows the topic can subscribe and read every push. That text is kept as `lastErr` and returned as `last_error` by `GET /alerts/relay`, which takes no token. W-49 adds per-target delivery results to `POST /alerts/notify` and stores them on the approval (`deliveries[].error`), so without the mask the topic would also land in request records.
- **Evidence**: `bifrost-platform/api/internal/alertrelay/relay.go:46` (topic is the read credential), `relay.go:371` (URL built with the topic), `relay.go:395` (`r.lastErr = err.Error()`), `relay.go:417` (`last_error` in the status body), `relay.go:116` (`GET /alerts/relay` route); read on platform main `66496a6`.
- **Fix**: Mask the topic out of every transport error before it is stored or returned (done on W-49: the target is reported as a hash, the error names the reason without the topic). After the redeploy, if the status endpoint ever showed a connection error, treat the topic as exposed; rotating it is an Owner own-key operation.
- **Ratchet**: `TestNotifyFailureNamesTheReasonWithoutTheTopic` (a failing ntfy post answers a delivery whose error and target do not contain the topic).
- 验收: `cd bifrost-platform/api && go test ./internal/alertrelay/ -run 'TestNotify' -count=1`; after the .50 operator-plane redeploy, `GET /alerts/relay` on .50 shows no topic in `last_error` and the build carries the W-49 commit.
- 审批 要批（凭据面：.50 operator-plane 重新部署是 Owner 本机操作）· 代价 S · 风险 low · repos: bifrost-platform

### TD-261

**P2 · ops-platform · The Console approval list never renders: it reads `{items}` and the API answers `{approvals: [...]}`, and the page test mocks the wrong shape so it never caught it**

- **状态**：在做（LANE-A 已就绪、**未合**：`cursor/a-platform` 3bd067f。`parseApprovalList` 读 `approvals` 信封，遇到 `{items}` 抛错；`ApprovalsPage` 待决单不再显示 Go 零值时间。防线是真的——`console/src/api/__tests__/approvals.test.ts` 在**运行时读** `api/internal/approvals/types.go` 与 `handler.go`，解析 `Approval` 的 json tag 逐个比对夹具，并断言 handler 发 `"approvals": list` 而非 `"items": list`。门禁 tsc / lint / vitest（809 passed）/ build 全 0。**platform main 现冻在 a7ecb08 等 `appr_cb8b3f52329cbe8c`，所以没合**）
- **下一步**：合并前补一处——`approvalJsonTagsFromGo` 的正则匹配不到 `type Approval struct {` 时返回空列表，循环体不执行，这条契约测试会**空过**。加一句 `expect(tags.length).toBeGreaterThan(8)` 之类的下界即可。合并顺序见「要你执行」
- **Claim**: The Console's approval list parses `{items}`, while the list route answers `{"approvals": [...]}`. The list therefore renders empty whatever is waiting. The page's own test mocks `{items}`, so it passes against a shape the API never sends. Found by LANE-RP while wiring the release policy; not introduced by it.
- **Measured**: MEASURED 2026-10-08 (LANE-RP, code read). The live shape is confirmed by this session's own MCP listing, which returned an `approvals` array.
- **Evidence**:
  - `bifrost-platform/console/src/…` approval list — parses `items`
  - `bifrost-platform/api/internal/approvals/handler.go` — list route answers `approvals`
- **Impact**: The Console is one of the three ways the Owner is meant to decide a tier C release (chat, phone, Console). That third way shows an empty list, so the Owner cannot decide from the Console at all — and the test suite says it works.
- **Fix**: Parse `approvals`, and build the page test's fixture from the Go handler's response type instead of a hand-written literal.
- **Ratchet**: A console test whose fixture is generated from the handler's response type, so the two cannot drift again.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-262

**P3 · ops-platform · MCP `start_pipeline_run` sends no `who`, so a release started through MCP can never satisfy the policy's "requester holds the window"**

- **状态**：在做（LANE-B 已就绪、**未合**：`cursor/b-platform` 5b0e511。MCP `start_pipeline_run` 增可选 `who` 写进请求体，不在 MCP 侧推断身份；`decideReleaseWindow` 在窗口与 pipeline 已匹配但 `callerWho` 为空时返回 `REFUSED: missing who; …`，不再误读成 "someone else"、也不静默退回人工。防线 `TestMissingWhoIsRefusedWhenWindowMatches` + MCP `startPipelineRun.test.ts`。门禁 go build / vet / test 全 0、MCP tsc + 20 passed。**同 TD-261，等 platform main 解冻**）
- **Claim**: The signed release policy requires `window_held_by_requester`. The MCP tool `start_pipeline_run` takes `name` / `revision` / `tag` and sends no `who`, so the engine cannot match the caller against the window holder. Every MCP-initiated release falls through to a manual decision — the one path the policy exists to remove.
- **Measured**: CODE-READ 2026-10-08 (LANE-RP). Consistent with this session's own MCP call, which produced a pending request rather than an automatic one.
- **Evidence**:
  - `bifrost-platform/mcp/…` `start_pipeline_run` input schema — `name`, `revision`, `tag` only
  - `bifrost-platform/api/internal/releasepolicy/engine.go` — `window_held_by_requester`
- **Impact**: Once a policy is signed, releases started from a Claude session through MCP still queue for a human; only the `release.sh` paths benefit.
- **Fix**: Add `who` to the MCP tool and pass it through; the server keeps requiring it to equal the window holder.
- **Ratchet**: A test that `start_pipeline_run` without `who` is refused rather than silently falling back to the manual path.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-265

**P3 · research-data · Non-farm payrolls rows get no theme: the pipeline's theme regex does not recognise `NFP`, so they never join the rate-path group**

- **状态**：在做（已合入 research main **5029084**，随下次 Research 发布上线）。LANE-E3 在 `THEME_LINES` 的利率路径正则加 `\bNFP\b` 与 `Employment Situation`；`macro_calendar.csv` 的三类指标（`CPI` / `FOMC rate decision` / `NFP`）修前只有 NFP 无主题，修后都归「利率路径重定价」。防线 `test_every_macro_calendar_indicator_resolves_theme`（表驱动，CSV 里每个指标都要解析出非空主题）+ 雷达侧 `test_theme_matcher_lines`；两条我单独跑过，2 passed
- **Claim**: TD-180's first half wrote `NFP` rows into `macro_calendar.csv`. The theme regex matches CPI and FOMC wording but not `NFP`, so those rows carry an empty theme and are not grouped with the rate path. The same regex classifies rows on the way into the event radar.
- **Measured**: MEASURED 2026-10-08 by LANE-E2, which did not change the regex: out of its lane.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/…/pipeline.py:357` — the theme regex
  - `bifrost-research/src/bifrost_research/scheduler/data/macro_calendar.csv` — the two `NFP` rows
- **Impact**: The macro calendar shows payrolls, but a theme view of the next rate decision is missing the single biggest input to it.
- **Fix**: Add payrolls to the theme regex (`NFP`, plus the spelled-out `Employment Situation` if the radar ever ingests that wording), with a test per matched term.
- **Ratchet**: A table-driven test: every indicator present in `macro_calendar.csv` resolves to a non-empty theme.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-266

**P3 · flex-ib · The flex worker's system messages never leave the pod: it publishes to 127.0.0.1:6379, which is refused in-cluster, so the UI toast for a cash-ingest run is dropped with only a WARNING**

- **状态**：未开始
- **Claim**: `bifrost_flex_query/orchestration/notify.py:64` builds its Redis URL from `effective_redis_dict(config, default_db=0)`. The `flex-query-worker` Deployment carries no `REDIS*` env at all, so the default resolves to `127.0.0.1:6379` and the publish is refused inside the cluster. The message center has real consumers — trade-api runs a blocking XREAD reader loop and the frontend turns those events into toasts and alerts — so the notification for a flex run is lost, not merely unused.
- **Measured**: MEASURED 2026-10-08 in the 10:30 UTC flex cash run (Der ran the TD-103 acceptance): `WARNING [bifrost_core.core.message_center] message center xadd failed topic=portfolio.flex_executions …: Error 111 connecting to 127.0.0.1:6379. Connection refused.` CODE-READ confirms the default and the absent env; `kubectl get deploy flex-query-worker -o jsonpath=…env` shows no `REDIS*` key.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/notify.py:64` — `format_redis_url(effective_redis_dict(config, default_db=0))`
  - `bifrost-trade-api/src/bifrost_api/monitor/routers/messages.py:32` — `_message_center_reader_loop`, the consumer
  - `bifrost-trade-frontend/src/components/MessageCenter/MessageToastStack.tsx` — where the event would surface
- **Impact**: The cash ingest itself is fine (TD-103's acceptance passed, 177/0/177), so no data is lost. What is lost is the signal: a run that ingests money data produces no UI message, and the only trace is a WARNING nobody reads. Same class as "failure as a warning".
- **Fix**: Give `flex-query-worker` the live Redis address the other plugin workloads use (env or the plugin's config block), then confirm the topic arrives. Decide separately whether a failed publish should raise rather than warn — on its own, a warning here is the thing that hid it.
- **Ratchet**: A plugin test that `notify` refuses to fall back to a loopback address when it runs with no explicit Redis configuration (so the next deployment cannot inherit the default silently).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-flex-query


### TD-274

**P3 · frontend · Symbol faces hide GEX levels that exist when zero gamma is NULL: the dealer level strip needs all four values and the regime cell needs zero gamma, so a chain with no flip (about a third of expiries) shows neither walls nor regime**

- **状态**：未开始
- **Claim**: Since research 0.191.0 / 0.192.0 (TD-157, TD-166) daily GEX levels store NULL for a wall on a side without exposure and for zero gamma when cumulative gamma never changes sign; NULL there is a reading ("no flip: the whole chain is long gamma" or short, by the sign of `total_net_gex`), not missing data. The Symbol faces treat it as missing: the dealer face draws its level strip only when spot, zero gamma and both walls are all present, so the walls that do exist disappear too; the face extras drop the GEX regime cell entirely; the history table and chain chips print `—`. Same class as the closed TD-150 (pages report gaps that are not there).
- **Measured**: MEASURED 2026-10-08 (acceptance run of TD-166, read-only): zero gamma NULL on 1,426 of 4,262 levels rows written for 10-06 (33.5%) and 1,503 of 4,294 for 10-07 (35.0%); 29,447 NULL in the table. On 10-06, 565 of 2,040 front-expiry readings since 10-01 had no flip. One-sided walls NULL on 24 of the 10-06 rows and 14 of the 10-07 rows.
- **Evidence**:
  - `bifrost-trade-frontend/src/pages/research/analyze/symbol/SymbolDealerFace.tsx:206` — `spot != null && zeroG != null && callWall != null && putWall != null` gates the whole level strip
  - `bifrost-trade-frontend/src/pages/research/analyze/symbol/faceExtras.ts:142` — `regime && zeroGamma != null ? { gex_regime: … flip … } : {}` drops the regime cell
  - `bifrost-trade-frontend/src/pages/research/analyze/symbol/SymbolDealerHistory.tsx:285` — `r.zero_gamma?.toFixed(2) ?? '—'`
  - `bifrost-trade-frontend/src/pages/research/analyze/symbol/SymbolChainFace.tsx:233` — the Zero γ chip with a null value
  - Research side: `bifrost-research/src/bifrost_research/engines/gex/exposure_guards.py` — `drop_fallback_zero_gamma`, `drop_empty_side_walls`
- **Impact**: On roughly a third of names the dealer face shows no walls and no regime although the levels row has them; the user reads "no GEX data" where the answer is "no flip, long (or short) gamma throughout".
- **Fix**: When a levels row exists, show what it has and say what a NULL means: draw the strip with whatever of spot / walls / zero gamma is present; regime cell "long γ · no flip" (sign of `total_net_gex`) when zero gamma is NULL; `no flip` instead of `—` in the history table and chip; a missing wall reads "no call (put) exposure". Keep `—` only when there is no levels row. Copy may want a Design pass; the data rule does not.
- **Ratchet**: vitest on the dealer face and face extras with a levels row whose zero gamma is NULL (strip still drawn with walls, regime cell present and says no flip), and one with a NULL wall.
- **验收**: On :5173 (DEV inner loop) a name whose front expiry has NULL zero gamma shows walls and a regime cell saying "no flip"; the vitest above passes.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

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
- (round 3) Whether the in-cluster platform-api images carry any SSH key or agent socket (kubectl exec into platform pods not allowed); whether the Mac mini operator plane (192.168.10.50:8783) accepts PROD operator tokens (token values not read).
- (round 3) No probe pod started: pod-to-NodePort reachability of Redis/Postgres from other namespaces is code-read. Secret contents never read (the platform kubeconfig identity is inferred from the code path).
- (round 3) The local platform-api rewrites bifrost-platform/config/ops-context.yaml (the D10 source preflight reads) on admin release-gate and migrate-wave POSTs, using read-modify-rename with no lock; noted, not filed (admin-gated, no live diff). The STG ops-context copy is also stale (treated under TD-109).
- (round 3) Only skimmed for role tier: delivery, Tekton and Gitea routes (start/delete PipelineRun, GiteaAccess creds), stack add-on install/upgrade, UniFi firewall apply, node join/drain/poweroff/wake, vision and build-phase gates, hermesgateway/agentdeploy, and the operator-plane proxy auth parity.
- (round 3) Cost limits on anonymous GET /telemetry/promql and /telemetry/query against memory-tight Loki; Console polling load (376 refetch sites) against platform-api; goroutine and fd leak profiling (no go_goroutines or process_open_fds series exist; all loops use context.Background()).
- (round 3) Which MCP tools a cluster_issues_full_auto agent may call on the runner, and whether the runner enforces D10 beyond prompt text; the market_data_heal dry_run=false default and drift in restart_dev_session's description were not reported.
- (round 3) Research endpoints that need the research auth header were not measured live (row counts checked against Golden Source instead); plugin-proxied Console TS types were not compared with their Python producers; FE↔trade-api key drift found no new instance across 21 endpoints.
- (round 3) Positions, Book, Backing, Room to add and Risk profile ×100 and Greeks scaling sampled by code-read only; option chain, vol surface, GEX, terrain, Simulator, backtest and Pine editor units not audited; LivePage Refresh posting /quotes/cleanup before status loads is too unproven to file.
- (round 3) Barman WAL continuity between base backups, NAS MinIO bucket contents, Postgres pg_hba/SSL for NodePort 30432, why logical-backup-drill-manual-1 failed, and RBAC of Tekton deliver SAs and the Argo controller over the data namespace.
- (round 3) Daemon execution, hedge FSM, guards and lease internals beyond a skim (D10); the worker Dockerfile and mutable :prod tag; redis-ib memory use of ib:account:stream:v1 (no redis exec on redis-ib); bifrost-ui token and visual defaults (Design track).
- (round 3) A nightly drift report on .52 that probes 192.168.10.40:8780 during Mac sleep (overlaps TD-130); agent/drift, drift-proposals, code-health, remediation-jobs and schedules subdirectories; whether Tekton metrics are scraped.

## 怎么做的

第 3 轮（2026-10-07，Ops 平台 · Console 与 MCP · Trade 前端数据正确性 · bifrost-ui 与 trade-worker · 数据层）：10 个 Agent，约 30 分钟，约 230 万 token，全程只读。代码读的是 origin/main 的干净副本：platform e95be35 · frontend dfb7858e · ui 2271260 · worker c04fc80 · infra f41dab5 · trade-api 630ca41 · core 53378bf。五个领域各一个盘点 Agent，三个反驳 Agent（平台两块合一个、前端与 ui/worker 合一个、数据层一个），一个 Agent 清点防线，最后一个去重排序。41 条发现：18 条原样成立，23 条改了说法或优先级，0 条被推翻；去重后 37 条，另 5 条并入已有条目或拆分；TD-196 加补充；关闭的 TD-140 原因写错，另开 TD-240；过时的登记文字汇成 TD-241。
第 2 轮（2026-10-06）：10 个 Agent，约 35 分钟，全程只读（数据库只做 read-only 查询）。代码读的是各仓库 origin/main 的干净副本：research 6ed86ad · market-data acba67e · flex f7b5cd9 · IB gateway 插件 39eafe2 · infra d5aa457 · core 756bdb5。四个领域各一个盘点 Agent（Research 数据面、Research 控制面、market-data、flex + IB gateway），每个领域的发现交给一个专门反驳的 Agent 去推翻；另一个 Agent 清点现有防线并对照第 1 轮的各类债；最后一个 Agent 去重、排序、提出待建防线。40 条发现：22 条原样成立，18 条改了说法或优先级，0 条被推翻，3 条合并。之后日常工作里发现的直接加入（TD-127–129 来自 Pine 线程）。
第 1 轮（2026-10-01，Trade UI 之下）的原文在台账页 artifact 版本 ≤ 48 和 git 历史里。
