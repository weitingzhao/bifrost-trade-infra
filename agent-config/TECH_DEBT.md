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

- **TD-199** — 删掉自 09-24 起无人引用的 EventsBoard.tsx / EventRadarDashboard.tsx，改正两处注释（frontend e98afbf0）· 验收 PASS（10-07）· 防线：`src/lib/orphanModules.test.ts`（从 main.tsx 走导入图，KNOWN_ORPHANS 只许缩短）· 后续：TD-243（其余 42 个孤儿模块）

**未结 117 项**：P0 1 · P1 12 · P2 39 · P3 65；要你批的 62 项（从总览表的审批列算）。

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
- **TD-96** — preflight 的 D10 闸门只认 curl；修改稿在 `REQUEST-td96-preflight-d10-2026-10-06/`，等 Owner 审。

- **TD-130** — 真正在生产数据层上动手的 Ops 自动修复跑在 Owner 的笔记本上（本机 bdev 的 platform-api），集群里 STG/PROD 那两份在空转；10-05 到 10-06 对备份 MinIO 的重启和补备份都是它做的。
- **TD-203** — 本机 platform-api 的 `/console/ws` 不要令牌就给局域网任何设备一个 SSH 终端（用你的 key，7 台主机，含能读集群管理员 kubeconfig 的 k3s 控制节点）；本机监听 *:8780、防火墙关着。最小止血：本机 `.env` 设 `PLATFORM_LISTEN=127.0.0.1:8780` 后 `bdev restart platform-api`。
- **TD-205** — PROD Redis 没有密码、局域网 NodePort 30382 可达，里面是 PROD daemon 的控制键：局域网任何设备都能让 daemon stop / flatten，绕过 trade-api 的控制闸门和审计。
- **TD-209** — 所有数据层告警（备份失败、WAL 停、NAS MinIO 掉线、逻辑备份缺失）只进 STG platform-api 的内存审计日志，没有人会收到；`BifrostLogicalBackupMissing` 从 10-06 22:03Z 起一直在响。

## 还债顺序

### 第 0 波 · 第 1 轮收尾

目标：第 1 轮剩下的三项按已排的日期收掉。TD-85 剩 Golden Source 的 PUBLIC CONNECT；TD-51 等 Loki 闸门后随下一次 Trade 发布；TD-80 C2-b 改号 core 0.49.0 与 TD-51 同发。

项：TD-85 · 已还：TD-21, TD-51, TD-80

### 第 1 波 · 正在出错的数据与「绿着的失败」

目标：先让失败变红。错数据先修数据（TD-87 restate），再把引擎、闸门、写入方从「出错也报成功」改成失败即失败：引擎资产按输出判定、husbandry gate 失败即关、日历读失败报错、写入方失败抛错。不需要 Owner 批的先做。

项：TD-91, TD-92, TD-94, TD-97, TD-101, TD-136, TD-156, TD-157, TD-166, TD-189, TD-192 · 已还：TD-88, TD-89, TD-90, TD-113, TD-93, TD-165, TD-167, TD-87

### 第 2 波 · 让闸门真的卡住

目标：一个开关让所有测试类防线生效（CI 卡发布），再补上调度存活告警、D10 闸门的非 curl 写法、operator 流白名单、本机常驻任务和密钥轮换的盲区、spine 副本同步。

项：TD-95, TD-96, TD-100, TD-105, TD-109, TD-121, TD-152, TD-153, TD-155, TD-162, TD-194 · 已还：TD-99, TD-161, TD-198, TD-195

### 第 3 波 · 交易日与日历只有一个来源

目标：所有「今天 / 本 session」都从 `db/calendar` 的一个函数来，代替 11 个私有 helper 和 44 处 `date.today()`；dbt 补 grain 测试；IV / 回测的定价参数统一。

项：TD-98, TD-110, TD-111, TD-112, TD-128, TD-129, TD-174, TD-242 · 已还：TD-164, TD-175

### 第 4 波 · 券商资金账本（Flex / IB）

目标：现金与佣金账本可信：按 IB transactionID 去重（改表）、佣金一种符号、资金路径有测试、Flex 不再经 DEV 库读配置、IB Gateway 健康与镜像可追溯。

项：TD-103, TD-104, TD-114, TD-117, TD-122 · 已还：TD-115, TD-116

### 第 5 波 · 副本、死重与清单

目标：删掉没人用的（挂起的 CronJob、退役脚本、无调用路由），手抄的副本改成从一处生成（调度名单、max-pain / PCR），清单的应用顺序与 Argo 归属理顺。

项：TD-102, TD-106, TD-107, TD-118, TD-119, TD-120, TD-123, TD-125, TD-160, TD-170, TD-190, TD-202 · 已还：TD-126, TD-108, TD-154, TD-163, TD-168, TD-124, TD-176, TD-191, TD-169, TD-200, TD-201

### 第 6 波 · 备份链与自动修复（10-06 日常发现）

目标：备份 MinIO 已搬到 NAS（infra 1ee0ac2，已接监控 ba03488），把剩下的收尾：自动修复只在 PROD 一处动手、失败记录不再被删、platform 的新检查上线、稳定一周后退役集群里的 MinIO 残留，再处理 WAL 体量和 CNPG 1.30 的备份插件。

项：TD-130, TD-131, TD-133, TD-134, TD-135, TD-196 · 已还：TD-197, TD-173, TD-132

### 第 7 波 · 数据缺口（10-06 由 Data Gaps 看板并入）

目标：Data Gaps 看板上未结的 15 项并入台账：先把每日快照的写入修对（TD-137）再接读侧和三页，归因行补上价格，Research 侧已就绪的一个版本（0.185.0）发出去，长期限 IV 锥在 10-31 前从 option_daily 回填，其余按 Owner 已定的口径排。

项：TD-137, TD-138, TD-139, TD-142, TD-143, TD-144, TD-145, TD-146, TD-148, TD-149, TD-150, TD-158, TD-159, TD-172, TD-178, TD-180, TD-182, TD-199, TD-243 · 已还：TD-141, TD-147, TD-177, TD-179, TD-151, TD-181, TD-193, TD-140, TD-171

### 第 8 波 · Pine 线程收尾后的跟进（10-06）

目标：Pine 与路线图那条线（会话「Pine 信号业务与实现」）收尾时留下的日后核对：W3 两次真正的归档、一个只差发布的前端修复、路线图台账的月度重评、「我的价位」等 Design、auto mode 规则重新应用。

项：TD-183, TD-184, TD-185, TD-186, TD-188 · 已还：TD-187

### 第 9 波 · 控制面对局域网敞开（第 3 轮，10-07）

目标：先关门再修代码。本机 platform-api 只监听本机、PROD/STG Redis 的局域网 NodePort 删掉，然后 git-bridge、修复 runner、Hermes、husbandry-sync 都要令牌；platform 换成按需授权的 ServiceAccount，停用管理员 kubeconfig；路由鉴权测试卡住回退。

项：TD-203, TD-205, TD-206, TD-207, TD-208, TD-204, TD-220, TD-225, TD-221, TD-222, TD-223, TD-224, TD-231

### 第 10 波 · 告警有人收、备份能恢复（第 3 轮）

目标：数据层告警有一个人能收到的通道和外部心跳；逻辑备份先修好等库就绪；做一次 Barman 恢复演练；决定异地副本；daemon 停写与日志丢失要能被看见。

项：TD-209, TD-210, TD-217, TD-218, TD-215, TD-216, TD-238, TD-237

### 第 11 波 · 账本与页面读数、绿着的未知（第 3 轮）

目标：挂单与 IB 读失败不再被当真写库；Risk / Performance / 告警计数按交易日算；Console 的裁决条在探针失败时不再显示绿色；ui 的发布可追溯；台账与文档的过时说法改正。

项：TD-211, TD-212, TD-213, TD-214, TD-219, TD-232, TD-233, TD-226, TD-227, TD-228, TD-229, TD-230, TD-234, TD-235, TD-236, TD-239, TD-240, TD-241

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

### 平台状态存哪里？线程标题改由会话自己上报吗？（Owner 2026-10-06 已定：按推荐）

- 已定：TD-196 选 A：门禁历史、发布 cycle、操作队列、checklist 信号改存平台命名空间的 ConfigMap（和发布记录、线程标题同一个做法，不加依赖），审计日志写一个有上限的 ConfigMap；以后要 HA 或审计量变大再上 Postgres。TD-197 做：会话自己的 Stop hook 上报标题，本机同步保留作回填。
- 选项：A：ConfigMap · B：Postgres（新依赖、DDL、凭据）· C：PVC（local-path，重装节点会丢，仍是每个 pod 一份）
- 项：TD-196, TD-197

### 局域网敞开的几处先怎么关？（安全，第 3 轮）

- 推荐：A。今天先止血：本机 platform-api 只监听本机（TD-203）、删掉 PROD/STG Redis 的局域网 NodePort 改用 port-forward（TD-205，PROD 变更）；随后一个 platform 版本给 `/console/ws`、husbandry-sync 加鉴权并检查主机密钥，git-bridge / runner / Hermes 加令牌并默认只听本机。
- 选项：A：先止血再修代码 · B：只修代码随下一版发（期间仍敞开）· C：只开 macOS 防火墙（你来做，挡不住 Redis 与 mini）
- 项：TD-203, TD-205, TD-206, TD-207, TD-208

### platform 换成按需授权的身份吗？（安全）

- 推荐：A。每个 namespace 建 platform-api / platform-workers 两个 ServiceAccount：集群范围只读；只有 PROD 有点名的动作权限（指定 namespace 的 scale/rollout、节点 cordon、data 里建 Backup）；STG 只读。删除 kubeconfig Secret，之后轮换管理员客户端证书。
- 选项：A：最小权限 SA · B：先只把 STG 降成只读 · C：维持 system:masters
- 项：TD-204, TD-222, TD-223

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
| [TD-125](#td-125) | P3 | flex-ib | Retired IB topology still referenced: TIBM-era verify scripts at the top of scripts/, flex_ops compat SQL for a schema that no longer exists | 删除（要你批） |
| [TD-128](#td-128) | P3 | research-data | Pine signal rows mix adjustment bases: nightly runs rewrite only the last ~10 sessions on today's adjusted bars, older rows stay on the basis of their last full rebuild | 不用批 |
| [TD-129](#td-129) | P3 | research-data | The event backtest picks option legs from option_daily only; since mid-August 2026 it keeps ~10 strikes a side, so a target delta silently lands on the nearest strike that is left | 不用批 |
| [TD-130](#td-130) | P1 | ops-control | ops-autopilot acts on the shared cluster's data layer from the Owner's laptop (local bdev platform-api, role all); the in-cluster STG/PROD autopilots idle on an empty checklist, and each of the three keeps its own throttle | 要你批 |
| [TD-131](#td-131) | P2 | ops-control | repair_cnpg_wal_store deletes failed Backup CRs, erasing the record of failed backups | 要你批 |
| [TD-133](#td-133) | P3 | data | Leftovers of the in-cluster MinIO after the move to the NAS (deploy/minio at 0, its PVC/PV, an empty EndpointSlice, the backup-retry CronJob) | 要你批 |
| [TD-134](#td-134) | P2 | data | WAL is ~19.5 GiB/day (4.2 GiB compressed) because checkpoints run every 5 minutes without wal_compression | 要你批 |
| [TD-135](#td-135) | P3 | data | Native barmanObjectStore backups are removed in CloudNativePG 1.30; the Barman Cloud Plugin that replaces them needs cert-manager, which the cluster does not have | 新依赖（要你批） |
| [TD-136](#td-136) | P2 | research-data | GEX writes levels for an expiry whose open interest is all zero: walls and zero_gamma fall on an arbitrary strike, 1,534 rows on 496 names, and terrain and scan copy them | 已批（观察中） |
| [TD-137](#td-137) | P1 | trade-data | The daily snapshot capture locks an account's intraday book into the day (first write wins, no freshness test) and account_nav_daily stores no margin-pressure fields | 改表 + 发布（要你批） |
| [TD-138](#td-138) | P2 | trade-data | The daily position and NAV snapshots have no reader: no trade-api route, no Research or frontend read, and three pages still say the snapshot does not exist | 不用批 |
| [TD-139](#td-139) | P3 | trade-data | Snapshot Greeks carry no quality flag (vendor / degraded / missing): only mark_source and greeks_asof are stored | 不用批 |
| [TD-142](#td-142) | P2 | research-data | The 90-day IV cone has 31–39 sessions of history and there is no 180-day tenor: ATM IV was stored only to 90 DTE before 2026-08-05 | 要你批 |
| [TD-143](#td-143) | P3 | research-data | Hypotheses never link to trades: linked_opportunity_ids is empty on all 91 rows, and only Research's own create / patch writes it | 不用批 |
| [TD-144](#td-144) | P3 | research-data | Settled candidates are not attributed to the judge (persona) that put them forward, so the Personas bench track-record columns stay grey | 要你批 |
| [TD-145](#td-145) | P3 | research-data | Settled candidates carry no regime label, so the Personas bench 'Best regime' column has nothing to group by | 不用批 |
| [TD-146](#td-146) | P3 | research-data | No store accepts a hand verdict, so the Personas bench 'Agrees with you' column cannot be computed | 要你批 |
| [TD-148](#td-148) | P3 | trade-data | A trade cannot name the lens or backtest run it came from: trade has no such column and strategy_plan.source_kind does not allow lens / backtest_run | 改表（要你批） |
| [TD-149](#td-149) | P2 | market-data | CTVA's adjusted daily bars ignore its 2026-10-01 spin-off, so every return-based feature on CTVA sees an ~84% one-day drop | 不用批 |
| [TD-150](#td-150) | P3 | frontend | Pages report gaps that are not there: 'no earnings date reaches this side', 'carry nothing at all' for names the vendor answered, and no note that CUE lists only adjusted contracts | 不用批 |
| [TD-158](#td-158) | P3 | research-data | Earnings estimates are served one name per request, so no universe-wide page can show an Earn column | 不用批 |
| [TD-159](#td-159) | P3 | market-data | No read says how many standard and adjusted option contracts a name has, so "only adjusted contracts are listed" is inferred in the browser from ticker shapes | 不用批 |
| [TD-152](#td-152) | P2 | ops-platform | promtail drops log lines (ingester_error) around 02:00–03:15 and 22:xx UTC, so every Loki-based release gate can come out INCONCLUSIVE | 不用批 |
| [TD-153](#td-153) | P3 | ops-platform | loki_gate.py only knows the pre-0.10.0 log line ('deprecated query params'); after api 0.10.0 refused callers log 'retired query params' and the gate cannot see them | 不用批 |
| [TD-155](#td-155) | P2 | ops-platform | Pushes to GitHub main do not trigger CI until the Gitea pull mirror syncs, so a commit can be released before its CI ever ran | 跨仓库发版 |
| [TD-156](#td-156) | P2 | research-control | research_signal_hit_schedule fires at 00:10 UTC, before the 02:30 UTC batch writes the night's features, so it judges the previous night's features | 不用批 |
| [TD-157](#td-157) | P3 | research-data | GEX writes a wall on an arbitrary strike when one side of an expiry has no gamma exposure: 1,762 levels rows on 244 names, terrain reads both walls | 已批（观察中） |
| [TD-160](#td-160) | P3 | research-data | features.event_signal_radar_daily keeps the pre-rename copies of two indexes (event_radar_batch_collected, event_radar_importance) beside the current ones | 改表 |
| [TD-162](#td-162) | P2 | ops-platform | Research and plugin releases have no release window: sessions collide on pins and on deliver runs | 跨仓库发版 |
| [TD-166](#td-166) | P2 | research-data | GEX zero_gamma was the strike nearest spot on 38% of daily levels rows (no change of sign), and a step out of zero counted as a crossing; terrain read it as a flip at spot | 已批（观察中） |
| [TD-170](#td-170) | P3 | research-control | dagster-daemon logs one line over 256 KB at the 22:45 and 03:00 UTC schedule ticks every night | 不用批 |
| [TD-172](#td-172) | P2 | research-data | ATM IV has almost no 50–90 DTE expiry from 2026-07-06 to 09-25 (the EOD chain stopped at the third listed expiry until plugin 0.39.0); the fix was forward-only, so term structure reads na for that stretch | 要你批 |
| [TD-174](#td-174) | P3 | market-data | Console marks fundamentals-rotate missed every Monday 03:45 → Tuesday 03:00 UTC: the trading-day check uses the UTC date of the fire | 不用批 |
| [TD-178](#td-178) | P3 | trade-api | GET /strategies/plans has no source_kind filter: Research reads the newest 500 filled plans and filters itself, marking truncated at the cap | 改公开接口 |
| [TD-180](#td-180) | P3 | research-data | The macro calendar has no CPI dates after 2026-12-10 and no payrolls at all: bls.gov answers 403 from this host, so they could not be read | 不用批 |
| [TD-182](#td-182) | P3 | research-data | Macro gap (actual vs expected) is always empty: consensus is not in the subscription, and the entitled /fed/v1/inflation actuals have no raw table | 改表（要你批） |
| [TD-183](#td-183) | P3 | market-data | W3 archive-before-delete has never archived for real: the first intraday option_snapshot archive is ~10-08 02:15 UTC and option_daily / short_volume on 11-01 | 不用批 |
| [TD-184](#td-184) | P3 | frontend | The Simulator says "stored with the run" for runs that were not stored: the fix (fe 53d6939e) is on main but not in STG/PROD | 发布（要你批） |
| [TD-185](#td-185) | P3 | research-control | The Pine-vs-TradingView roadmap ledger is a point-in-time judgement: its scores and next steps need a re-evaluation around 11-06 | 不用批 |
| [TD-186](#td-186) | P3 | frontend | "My levels" (plan stop / target and price alerts as horizontal lines) on the Symbol chart waits on Design: ASK-symbol-chart-my-levels-2026-10-06 | 要你批 |
| [TD-188](#td-188) | P3 | frontend | The app's design registry is still at Rev .157: packages .158–.162 are built but designRoutes / adoption were not re-synced (the Design project's DS mirror was synced to 0.13.0 on 10-06) | 不用批 |
| [TD-189](#td-189) | P3 | research-data | SEPA has no rows for four sessions (08-28, 08-31, 09-08, 09-16): those nights never computed it, so the SEPA lens and its hit rate skip them | 不用批 |
| [TD-190](#td-190) | P3 | ops-platform | Platform's research CronJob trigger route has no caller but keeps seven suspended CronJob templates alive in the research namespace | 改公开接口 |
| [TD-192](#td-192) | P2 | research-control | One IB Flex failure loses that night's SEPA for good: husbandry_gate blocks sepa_projection although SEPA reads nothing from Flex, and the projection never back-fills a missed night | 要你批 |
| [TD-194](#td-194) | P2 | ops-platform | BifrostAPIHighLatency can never fire: the histogram it reads tops out at a 1 s bucket, so histogram_quantile returns at most 1 and `> 2` is impossible | 要你批 |
| [TD-196](#td-196) | P2 | ops-platform | platform-api and platform-workers keep their state in per-pod emptyDir: every rollout erases release cycles, gate history, the operate queue and checklist signals, and the audit log is memory-only | 已批 |
| [TD-199](#td-199) | P3 | frontend | EventsBoard.tsx and EventRadarDashboard.tsx have had no importer since 09-24 (c81e5a29); a comment still says EventRadarBody 'stays the Explorer tab's body' though Explorer was retired in 594a3f3f | 删除（要你批） |
| [TD-202](#td-202) | P3 | market-data | market-data code strings and scripts still mention CronJobs: the dashboard label 'CronJob archived' and verify-market-data.sh's hint are user-visible | 不用批 |
| [TD-203](#td-203) | P0 | ops-platform | GET /api/v1/console/ws hands out an interactive SSH shell with no token: the bdev platform-api listens on *:8780 with the Owner's SSH key, and the Mac firewall is off | 安全/凭据（要你批） |
| [TD-204](#td-204) | P1 | ops-platform | STG and PROD platform-api and platform-workers run as system:masters through a copy of the k3s admin kubeconfig, and anonymous GETs use it to read pod logs in any namespace | 安全/凭据（要你批） |
| [TD-205](#td-205) | P1 | data | PROD Redis, which holds the daemon's control stream and state hash, has no password and is open on NodePort 30382 to two LAN /24s and, through NodePort SNAT, to every pod in the cluster | 安全/凭据（要你批） |
| [TD-206](#td-206) | P1 | ops-console | git-bridge answers anyone on the LAN, and its /commit runs `git add -A` on the shared checkout; /push pushes the current branch with no release-window check | 安全/凭据（要你批） |
| [TD-207](#td-207) | P1 | ops-console | The remediation runner (:8781) and the Hermes gateway (:8782) on the Mac minis start, approve and cancel agent jobs for anyone on the LAN: POST /run, /run/:id/respond and /skills/:id/trigger have no auth | 安全/凭据（要你批） |
| [TD-208](#td-208) | P1 | ops-platform | Anonymous POST /checklist/husbandry-sync starts full-auto remediation agents: it merges the stored checklist and dispatches every failing item, and three Console pages call it on load | 安全/凭据（要你批） |
| [TD-209](#td-209) | P1 | data | Every data-layer alert (backup failed, WAL archive stalled, NAS MinIO down, logical backup missing) goes to one webhook that writes it to STG platform-api's in-memory audit log and returns 200: no human is ever told | PROD 变更（要你批） |
| [TD-210](#td-210) | P1 | data | The nightly logical backup of hand-entered data failed on its first scheduled run: it connects before the new pod's NetworkPolicy is programmed and gets Connection refused | 不用批 |
| [TD-211](#td-211) | P1 | trade-worker | Working orders are never persisted: the plugin's snapshot has no open_orders, the daemon TRUNCATEs raw_broker.open_orders every hour, and the UI says 'No working orders at IB.' | 跨仓库发版 |
| [TD-212](#td-212) | P2 | trade-worker | A failed IB positions or summary read is written as truth: the daemon deletes every raw_broker.positions row of the account and nulls its NAV until the slot reconnects | 跨仓库发版 |
| [TD-213](#td-213) | P2 | frontend | Risk › Limits 'Daily loss on the allocation' sums the realised P&L of every trade the allocation ever closed, not today's, so a losing day reads 0 consumed | 不用批 |
| [TD-214](#td-214) | P2 | frontend | Performance and Portfolio Overview summaries start the range at UTC midnight, so they include the previous month's last Chicago day | 不用批 |
| [TD-215](#td-215) | P2 | trade-worker | Nothing alerts when the only writer of raw_broker.account and positions stops: the daemon has no liveness probe and no freshness rule | 不用批 |
| [TD-216](#td-216) | P2 | trade-worker | The daemon never configures logging: every INFO line is dropped, and write failures logged at debug are invisible | 不用批 |
| [TD-217](#td-217) | P2 | data | The Barman base+WAL backup, the only copy of the 34 GB Golden Source history, has never been restored, and has not been tried at all against the NAS MinIO it moved to on 10-06 | PROD 变更（要你批） |
| [TD-218](#td-218) | P2 | data | Every backup copy (Barman base+WAL, logical dumps hot and cold, the W3 archive) is on the one NAS 192.168.10.20:/volume1, and the open offsite decision is not in the ledger | PROD 变更（要你批） |
| [TD-219](#td-219) | P2 | frontend | The rail's amber 'alerts fired today' count can never be non-zero: it matches trade_date against the UTC date, and alerts are stamped with an earlier session | 不用批 |
| [TD-220](#td-220) | P3 | ops-platform | No test enumerates platform-api routes for auth: POST /cluster/sync-kubeconfig and the plane's POST /hermes/run-first-task are unauthenticated, and a failed LoadAuth is not logged | 不用批 |
| [TD-221](#td-221) | P3 | ops-console | The governance catalog says nobody but the daemon writes ib:operator:cmd, but platform-api does (sanctioned by D-IB-Heal), and the runner's ib_gateway_control can switch the PROD gateway to mock with only a prompt-level approval | 安全/凭据（要你批） |
| [TD-222](#td-222) | P3 | ops-platform | Platform's D10 scale guard only blocks daemon 0→n: the PROD daemon (2, observe-safe) and DEV (1) can be scaled to 20 by any operator-token caller that bypasses preflight | 安全/凭据（要你批） |
| [TD-223](#td-223) | P3 | ops-platform | STG and PROD platform-workers both run the IB gateway auto-repair loop against the one live data/ib-gateway, each with its own 15-minute cooldown | PROD 变更（要你批） |
| [TD-224](#td-224) | P3 | ops-console | Opening the Cluster page as an operator auto-starts a full-auto remediation run, and neither platform-api nor the runner deduplicates by scope or active job | 不用批 |
| [TD-225](#td-225) | P3 | ops-console | Read-only MCP bridges fail open: an unknown or misspelled MCP_BRIDGE_FOCUS registers all 74 tools, and PLATFORM_OPERATOR_TOKEN in env overrides the viewer-token pin | 不用批 |
| [TD-226](#td-226) | P3 | ops-console | The release desk's Launch verdict says 'Clear to launch' and enables Agent Deploy when readiness probes failed or are still loading | 不用批 |
| [TD-227](#td-227) | P3 | ops-console | The cockpit mission snapshot keeps a failing probe's last good verdict, under a 'Last probe' stamp that is the newest of seven queries | 不用批 |
| [TD-228](#td-228) | P3 | ops-console | Every scheduled Hermes skill run on .52 fails with 'No such file or directory', while /health returns status ok and the checklist counts the gateway healthy | 不用批 |
| [TD-229](#td-229) | P3 | ops-platform | Trust overrides resolve to $HOME in the cluster and swallow read and write errors: the Owner's 09-07 L0 grant for research-loop-batch never reached the harness that reads PROD | 不用批 |
| [TD-230](#td-230) | P3 | ops-platform | The platform release gate passes when required checks are 'unknown', and its 'ready' never expires | 不用批 |
| [TD-231](#td-231) | P3 | ops-platform | Platform's IB feed verdict hangs on one hard-coded NVDA sample tick, and Trade namespaces and DB names are Go literals (53 matches), with no ratchet against growth | 不用批 |
| [TD-232](#td-232) | P3 | frontend | 24 frontend sites take 'today' as the UTC date although four session helpers exist: from 20:00 ET until midnight they read tomorrow, and one writes a default opened_at | 不用批 |
| [TD-233](#td-233) | P3 | frontend | fetchIvPercentileForSymbols turns every non-404 failure into 'no data', so IV Radar and the Watch book report a plugin outage as names without an IV rank | 不用批 |
| [TD-234](#td-234) | P3 | trade-worker | @bifrost/ui is unversioned for the Ops Console: a ui push never runs platform CI, and platform deliver builds whatever ui main is without recording its SHA | 不用批 |
| [TD-235](#td-235) | P3 | bifrost-ui | bifrost-ui's build starts with rm -rf dist (and prepare runs it on every npm install), white-screening both running dev servers until it finishes, or for good if tsc fails | 不用批 |
| [TD-236](#td-236) | P3 | trade-worker | Leftovers of the deleted Account Sync daemon: the plugin still XADDs every account snapshot to ib:account:stream:v1, which nothing reads | 跨仓库发版 |
| [TD-237](#td-237) | P3 | data | The data-warehouse 'second MinIO' never ran (PVC Pending 109 days, Deployment 0/0), yet AGENT_FACTS lists it, and its placeholder root Secret is committed to a PUBLIC repo and applied | 删除（要你批） |
| [TD-238](#td-238) | P3 | data | The three per-env Redis instances run --appendonly yes with no volume, and with noeviction but no maxmemory the only memory bound is an OOMKill | 不用批 |
| [TD-239](#td-239) | P3 | trade-worker | Up to about 40 runtime exports of @bifrost/ui have no importer in either consumer (ContextMenu family, KpiStrip, holidayLine, shellNav* constants); dead-code share unmeasured | 改公开接口 |
| [TD-240](#td-240) | P3 | trade-worker | The running PROD daemon never writes contract_quote_live: the observe-only quote mirror sits under mock_hedging, which is hard-coded True | 跨仓库发版 |
| [TD-241](#td-241) | P3 | agent-governance | RATCHETS.md, TECH_DEBT.md and agent docs state facts the round-3 scan measured as no longer true | 不用批 |
| [TD-242](#td-242) | P2 | market-data | market-data /ingest/queue-dashboard takes 5–25 s per call, and the platform-api proxy carries the same delay: with the new latency rule live it will page whenever someone keeps the queue dashboard open | 不用批 |
| [TD-243](#td-243) | P3 | frontend | 42 frontend modules are unreachable from src/main.tsx (largest clusters: components/cockpit/ 8, utils/dataOverview/ 6); dead code invites fixes and false audit findings | 删除（要你批） |

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

### TD-138

**P2 · trade-data · The daily position and NAV snapshots have no reader: no trade-api route, no Research or frontend read, and three pages still say the snapshot does not exist**

- **状态**：在做（道 AA，10-07 01:1x UTC 开工：两天快照已在（PROD 10-05 31 行、10-06 32 行），读侧 core → api → 前端三页；发版前停下）
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

- **状态**：在做（道 AA，10-07 01:1x UTC 开工：两天快照已在（PROD 10-05 31 行、10-06 32 行），读侧 core → api → 前端三页；发版前停下）
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

### TD-170

**P3 · research-control · dagster-daemon logs one line over 256 KB at the 22:45 and 03:00 UTC schedule ticks every night**

- **状态**：在做（修复在 research main 2583cc6，未建镜像；要随下一个 research 版本连同 Dagster 镜像一起上线，等你批）
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

### TD-178

**P3 · trade-api · GET /strategies/plans has no source_kind filter: Research reads the newest 500 filled plans and filters itself, marking truncated at the cap**

- **状态**：在做（research 部分已随 0.199.0 上线；core 0.53.0 / api 0.11.0 等 Trade 发版）
- **验收**：发版后：`curl -s -o /dev/null -w '%{http_code}' 'http://192.168.10.73:30881/api/account/strategies/plans?source_kind=bogus&limit=1'` = 422（三个网关同）；DEV `?source_kind=hypothesis` count 0、`manual` count 3；research 发布后 `/research/hypothesis?trade_env=dev` 的 `trade_link_basis.source` 含 `source_kind=hypothesis`
- **现在**：发版前基线 10-06 23:31 UTC：三网关 `source_kind=bogus` 都是 200（api 0.10.0 忽略参数）；DEV plans 3 行。EXPLAIN（副本）走 `strategy_plan_status_created`，行数 DEV 3 / STG 0 / PROD 0，不需新索引。门禁：core lint 0 / 1301 passed / test-db 103 passed；api 1005 passed；research 2091 passed。防线：api `tests/test_strategy_plans_routes.py`（hypothesis 只回 hypothesis、上限按过滤后计、未知 kind 422、不撞退役名）、core `tests/test_strategy_plan.py` + `test_strategy_plan_db.py::test_list_filters_by_source_kind_and_ref`、research `test_hypothesis_trade_links.py::test_the_kind_is_sent_and_still_checked_here`
- **Claim**: TD-143's read-time link pulls status=filled&limit=500 and filters source_kind='hypothesis' in Research; once filled plans approach 500 the oldest links drop out (flagged truncated, not silent).
- **Measured**: code-read 10-06 by paydown lane G2.
- **Evidence**:
  - `bifrost-trade-api/src/bifrost_api/strategy/routers/plans.py:70` — `def list_plans_endpoint(`
- **Impact**: Links silently age out of reach as the plan book grows (the truncated flag says so, but the link is gone).
- **Fix**: Additive `source_kind` (and `source_ref`) query params on core list_plans and the api route; Research passes them.
- **Ratchet**: An api test: source_kind=hypothesis returns only those plans and keeps the 500 cap per filter.
- 审批 改公开接口 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-api, bifrost-research

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

- **状态**：未开始（等 Owner 把 ASK 带给 Design，Design 回复）
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

### TD-190

**P3 · ops-platform · Platform's research CronJob trigger route has no caller but keeps seven suspended CronJob templates alive in the research namespace**

- **状态**：在做（platform 3e9eadd 已上 STG / PROD，触发路由 405；research 删 7 个模板的提交 630db76 等研究锁后推 main（PVC 声明保留，删 PVC 另行决定）；之后线上 CronJob 要你 `kubectl delete`）
- **Claim**: POST /research/cronjobs/{name}/trigger builds a Job from a whitelist of seven CronJob names (bifrost-analytics-daily, research-engines-event-radar/-forecast/-momentum, research-gex-intraday, research-iv-percentile, research-terrain-intraday). Lane R found no caller in console/src; researchEngineCatalog.ts marks them legacy. Because of the route, TD-124 had to keep the seven templates.
- **Measured**: code-read 10-06 by paydown lane R (grep of console/src and platform api).
- **Evidence**:
  - `bifrost-platform/api/internal/research/cronjob_trigger.go:15` — `var cronJobTriggers = map[string]string{`
- **Impact**: Seven dead CronJobs keep shipping and getting re-pinned; anyone triggering them runs an engine outside Dagster's ordering.
- **Fix**: Remove the route and whitelist (and the legacy catalog rows), then delete the seven templates and empty the names in test_k8s_cronjobs.py and verify_husbandry_schedulers.sh.
- **Ratchet**: test_k8s_cronjobs.py already allows the template set only to shrink; after the fix it becomes harness-only.
- 审批 改公开接口 · 代价 S · 风险 low · repos: bifrost-platform, bifrost-research

### TD-192

**P2 · research-control · One IB Flex failure loses that night's SEPA for good: husbandry_gate blocks sepa_projection although SEPA reads nothing from Flex, and the projection never back-fills a missed night**

- **状态**：在做（Owner 10-07 「按推荐」批准：拆门禁：Flex 只挡读 Flex 数据的资产，sepa_projection 只依赖 market_eod；其余仍失败即关闭；道 BB）
- **Claim**: husbandry_gate raises when Flex is failed / stale / none (fail-closed per TD-94) and sepa_projection depends on the gate. Two of the four SEPA gaps (09-08, 09-16) are Flex [1003] nights. The projection only writes latest_closed_session, so a skipped night is lost unless research_trading_day is re-run before the next close.
- **Measured**: MEASURED 10-06 by paydown lane P (ops_dagster runs 831ad92b, f638e59b, f9d10c09).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/plugin_batch_assets.py:235` — `raise RuntimeError(f"husbandry_gate: Flex ingest {flex_verdict} ({flex_reason}) — block dbt")`
- **Impact**: Every Flex outage (TWS log-off, report not generated) silently drops a day of SEPA history and its lens hits.
- **Fix**: Split the gate so Flex only blocks Flex-dependent assets (or make sepa_projection depend on market_eod only); optionally a run config that projects a named session while the mart still holds it. Changes TD-94's fail-closed design, so Owner decides.
- **Ratchet**: TD-189's sepa_covers_recent_sessions check already warns on a new gap.
- 审批 要你批 · 代价 S · 风险 med · repos: bifrost-research

### TD-194

**P2 · ops-platform · BifrostAPIHighLatency can never fire: the histogram it reads tops out at a 1 s bucket, so histogram_quantile returns at most 1 and `> 2` is impossible**

- **状态**：在做（core 0.55.0 = 0203b94 与 infra 7780a7e 已上 main，**规则未 apply**——要等三环境 Trade 都跑到 core ≥ 0203b94；先 apply 会在旧数据上误报，DEV 一周约 25 次。有人在此之前 `kubectl apply -k k8s/monitoring` 也会带上它）
- **下一步**：发版顺序：Trade 发版带 core ≥ 0.55.0 到 DEV / STG / PROD（`/health` core_sha ≥ 0203b94）→ 再 `kubectl apply -k k8s/monitoring` → `check_http_metrics_coverage.py --live`。Owner 10-07 已确认 /health 计数不计时
- **现在**：道 CC 实测（7 天）：trade-api 只有两个流式路由（/quotes/stream、/api/messages/stream，25 s keepalive SSE），旧计时按连接结束算，平均约 40 s；PROD api-monitor >1 s 的 211 个观测里 172 个是 SSE。另：kubelet 的 /health 占延迟观测 87–97%，把 p99 稀释成真实请求的约 p70。core 0.55.0：两个延迟直方图都计时到响应头（库自带 should_exclude_streaming_duration），/health 计数不计时（**超出原话「排除 SSE」的范围，待你确认**），指标名与标签不变、默认桶不变。规则改读 highr p99，`or` 低精度直方图（只对 platform-api），阈值 `> 5 for 10m`：按新口径 7 天回放 PROD 0、STG 0、DEV 3–9 次（都是真慢窗口）。防线：core `tests/test_prometheus_instrumentation.py`（6 个）+ `check_http_metrics_coverage.py`（延迟规则须读 highr、阈值低于所读直方图的最大有限桶，`--live` 核真实桶）。后续 TD-242
- **Claim**: prometheus-fastapi-instrumentator's default http_request_duration_seconds buckets are 0.1 / 0.5 / 1 / +Inf (core observability/prometheus.py). The rule asks p99 > 2 s. The fine histogram (http_request_duration_highr_seconds, no handler label, 0.01–60 s) would fire: over 7 days PROD api-monitor had ~20 and api-market ~17 windows of ≥5 min with p99 > 2 s — possibly streaming routes timed to response end (unverified).
- **Measured**: MEASURED 10-06 by paydown lane Q (Prometheus via apiserver proxy).
- **Evidence**:
  - `bifrost-trade-infra/k8s/monitoring/bifrost-alerting-rules.yaml:60` — `- alert: BifrostAPIHighLatency`
- **Impact**: Slow APIs are never alerted; the rule looks like coverage and is not.
- **Fix**: Either add a 2.5 s / 5 s bucket to the instrumentator config in core (and the three new middlewares) or switch the rule to the highr histogram; exclude streaming routes (SSE) from latency first, then set the threshold from the measured distribution.
- **Ratchet**: check_http_metrics_coverage.py can assert the rule's threshold is below the largest finite bucket of the histogram it reads.
- 审批 要你批 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-infra, bifrost-research, bifrost-platform-plugin-market-data, bifrost-platform-plugin-flex-query

### TD-196

**P2 · ops-platform · platform-api and platform-workers keep their state in per-pod emptyDir: every rollout erases release cycles, gate history, the operate queue and checklist signals, and the audit log is memory-only**

- **状态**：未开始（Owner 10-06 已批 A：ConfigMap + 审计长尾进 Loki；排在 TD-197 之后）
- **Claim**: Both platform Deployments mount `/app/data` as an emptyDir, one per pod (the api pod and the workers pod do not share it). Every file store resolves under it: release-gate state and history, release cycles (including `agent_session_id`), the operate queue, checklist signals, patrol state, the escape-hatch drill and agent-deploy last. The audit log is built with `NewAuditLog("")` and `PLATFORM_AUDIT_LOG` is set in no overlay, so audit records only live in memory. A rollout, crash or reschedule erases all of it.
- **Measured**: MEASURED 2026-10-06 23:40Z. Five platform deliveries were started through platform-api today (STG/PROD 17:53–23:34). PROD `GET /api/v1/promote/release-cycles?lane=platform` → `{"entries":[]}` and `GET /api/v1/audit?limit=5` → `{"records":[]}`; the PROD pods started 23:33 with the last rollout.
- **Evidence**:
  - `bifrost-trade-infra/k8s/base-platform/manifest.yaml:87` — `emptyDir: {}`
  - `bifrost-trade-infra/k8s/base-platform/manifest.yaml:185` — `emptyDir: {}`
  - `bifrost-trade-infra/k8s/overlays/platform-prod/replicas-ha.patch.yaml:12` — `# One replica is the honest configuration until that state moves to Postgres.`
  - `bifrost-platform/api/internal/promote/cycle_store.go:23` — `dataDir := os.Getenv("PLATFORM_DATA_DIR")`
  - `bifrost-platform/api/internal/promote/store.go:19` — `path := os.Getenv("PLATFORM_RELEASE_GATE_STATE")`
  - `bifrost-platform/api/internal/operatequeue/store.go:29` — `return &Store{path: filepath.Join(dir, "queue.json")}`
  - `bifrost-platform/api/internal/server/server.go:112` — `audit := actuation.NewAuditLog("")`
  - `bifrost-platform/api/internal/actuation/audit.go:34` — `path = os.Getenv("PLATFORM_AUDIT_LOG")`
- **Impact**: The Console's Promote history, release cycles and Audit view only show what happened since the last rollout; "who released what, when" has no durable record on the platform side; PROD platform-api is pinned to one replica because of it. The commit-lineage release records and thread titles avoided this by writing ConfigMaps (platform f53713b, 45277ce).
- **Fix**: Move the small stores to ConfigMaps in the platform namespace behind one store interface (same pattern as `internal/releases` and `internal/threadtitles`: get-or-create, update with retry on conflict, capped size), the audit log to a capped ConfigMap (or ship it to Loki and read back); then drop the emptyDir mount. Postgres only if HA or audit volume needs it.
- **Ratchet**: A platform test that no store resolves a path under `PLATFORM_DATA_DIR` once migrated, and a manifest check that no platform Deployment mounts an emptyDir at `/app/data`.
- **验收**: After a PROD platform rollout, `GET /api/v1/promote/release-cycles?lane=platform` and `GET /api/v1/audit` still list the entries recorded before it.
- 审批 已批（ConfigMap） · 代价 M · 风险 med · repos: bifrost-platform, bifrost-trade-infra
- **Also (round 3, 10-07)**: the data-clone schedule is written by the api pod and read by the workers pod's scheduler, each with its own emptyDir, and `DataCloneScheduleStore` loads its file only once at construction, so a schedule enabled in the Console never fires in-cluster (all three GETs answer enabled:false today). The ConfigMap store must be re-read on every `maybeAutoClone` tick; acceptance gains: a schedule PUT through the api pod is visible to the workers pod (`bifrost-platform/api/internal/cluster/data_clone.go:285`, `server.go:129`).

### TD-199

**P3 · frontend · EventsBoard.tsx and EventRadarDashboard.tsx have had no importer since 09-24 (c81e5a29); a comment still says EventRadarBody 'stays the Explorer tab's body' though Explorer was retired in 594a3f3f**

- **状态**：待你签收
- **验收**：`git -C bifrost-trade-frontend ls-tree -r --name-only origin/main | grep -cE 'EventsBoard.tsx|EventRadarDashboard.tsx'` = 0；`npx vitest run src/lib/orphanModules.test.ts src/pages/research/events/eventDate.test.tsx` 通过
- **验收结果**：PASS 2026-10-07 frontend e98afbf0：0 个匹配、6/6 通过；删前复核无生产导入、只被它俩导入的模块 0 个；两处注释已改正。另修了 origin/main 上 Pine 会话两次提交造成的 code-health 超线（`pct` / `signed` 各 4 处定义 → `simRuns.ts` 导出 `signedPct`，显示不变）。门禁 tsc / lint / vitest 4067 / build / legacy-css / code-health 全 0。孤儿基线 42 个记为 TD-243
- **Claim**: Lane U grepped src: the two modules are referenced only in comments (EventsPage.tsx:145, AlertsPage.tsx:16). TD-193 was filed against EventsBoard because the code looked live.
- **Measured**: MEASURED 10-07 by paydown lane U (grep of origin/main src for imports).
- **Evidence**:
  - `bifrost-trade-frontend/src/pages/research/events/EventsPage.tsx:145` — ``EventRadarBody` stays the Explorer tab's body — nothing deleted. */`
- **Impact**: Dead pages attract fixes (this round fixed one) and mislead audits into filing debt against code nobody sees.
- **Fix**: Owner confirms by eye (CLAUDE.md §15 rule: deletion is the Owner's call), then delete both files and correct the two comments.
- **Ratchet**: An orphan-module check (knip or a vitest over the import graph) in code-health, with the current orphans as a baseline that can only shrink.
- 审批 删除（要你批） · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-202

**P3 · market-data · market-data code strings and scripts still mention CronJobs: the dashboard label 'CronJob archived' and verify-market-data.sh's hint are user-visible**

- **状态**：未开始
- **Claim**: TD-201's guard scans Markdown only. ingest_dashboard.py:194 renders 'CronJob archived'; scripts/verify-market-data.sh:121 prints 'CronJobs may still be running'; comments in quality.py:22 and scheduler/daily.py:725, :2927.
- **Measured**: code-read 10-07 by paydown lane Y.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/ingest_dashboard.py:194` — `"readiness-refresh": "Readiness rollup — RETIRED (Wave 14G-A; CronJob archived)",`
- **Impact**: The Console and the verify script tell readers about a scheduler that no longer exists.
- **Fix**: Reword to the Dagster wording; extend test_k8s_no_cronjobs.py to scan src/**/*.py string literals and scripts/*.sh (same HISTORY_LINES allowlist). The label change ships with the next plugin release.
- **Ratchet**: The extended scan.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-203

**P0 · ops-platform · GET /api/v1/console/ws hands out an interactive SSH shell with no token: the bdev platform-api listens on *:8780 with the Owner's SSH key, and the Mac firewall is off**

- **状态**：未开始
- **Claim**: The console WebSocket route is registered outside every auth group. HandleWebSocket checks only the host allowlist, then upgrades and dials SSH. CheckOrigin returns true for an empty Origin, so any non-browser LAN client passes. It dials SSH as `vision` to any allowlisted host (both Mac minis, the gpu-server and all 5 K3s nodes) using the Owner's ssh-agent or key, and it never verifies host keys. The default listen address is all interfaces. One allowlisted host is ubt-k3s-01 (.73), where `vision` can read /etc/rancher/k3s/k3s.yaml; fetch-kubeconfig.sh does exactly that. So anonymous LAN access leads to a shell on 7 hosts and from there to cluster-admin.
- **Measured**: MEASURED 2026-10-07 00:4x and again at 00:57 UTC; no SSH session was opened. lsof shows platform-api PID 64432 bound to *:8780, and the bdev env sets PLATFORM_LISTEN=:8780 explicitly. socketfilterfw reports 'Firewall is disabled'. From LAN IP 192.168.20.74 with no token, /api/v1/console/ws?node=ubt-k3s-04 returns 400: the request reached the websocket upgrader, so no 401 stage exists. An unknown host returns 403. /console/hosts lists 8 targets anonymously (7 reachable, all user vision), and ssh-agent holds a key. The same route answers 400 on PROD NodePort 30876. PROD/STG pods mount no SSH key, so the shell is live on the bdev instance; this was not verified by exec.
- **Evidence**:
  - `bifrost-platform/api/internal/server/server.go:503` — `r.Get("/console/ws", s.console.HandleWebSocket)`
  - `bifrost-platform/api/internal/console/ssh_ws.go:32` — `if origin == "" {`
  - `bifrost-platform/api/internal/console/ssh_ws.go:289` — `HostKeyCallback: ssh.InsecureIgnoreHostKey(),`
  - `bifrost-platform/api/internal/config/config.go:70` — `listen = ":8780"`
  - `bifrost-trade-infra/scripts/k3s/fetch-kubeconfig.sh:10` — `ssh "${REMOTE}" 'cat /etc/rancher/k3s/k3s.yaml' >"${OUT}.tmp"`
- **Impact**: Any device on the home LAN gets a full shell on every cluster node and both Mac minis without credentials. On the k3s server node that shell can read the cluster-admin kubeconfig. This is the largest blast radius in the system, and it bypasses D10, preflight and all platform role tiers.
- **Fix**: (1) Put /console/ws behind Require(RoleAdmin or RoleOperator). The Console gets a short-lived single-use ticket from an authenticated POST and passes it as a query parameter or Sec-WebSocket-Protocol. (2) Make the default listen 127.0.0.1:8780 in config.go and run_platform_api.sh; LAN exposure becomes opt-in. (3) Check host keys against a known_hosts file. (4) Reject an empty Origin on this route.
- **Ratchet**: Route-auth matrix test (see ratchet proposal 'platform-route-auth-walk'): chi.Walk the router, and every route outside an explicit, commented public allowlist must answer 401 without a token. /console/ws must never be on the allowlist. A config test asserts that the default PLATFORM_LISTEN host is loopback.
- **验收**: `curl -s -m5 -o /dev/null -w '%{http_code}\n' 'http://192.168.20.74:8780/api/v1/console/ws?node=ubt-k3s-04'  # expect 401 or connection refused (today: 400)`
- 审批 安全/凭据（要你批） · 代价 M · 风险 med · repos: bifrost-platform

### TD-204

**P1 · ops-platform · STG and PROD platform-api and platform-workers run as system:masters through a copy of the k3s admin kubeconfig, and anonymous GETs use it to read pod logs in any namespace**

- **状态**：未开始
- **Claim**: No platform namespace binds a ServiceAccount: platform-api, platform-console and platform-workers have SA <none> in STG and PROD. Both Deployments instead mount Secret bifrost-platform-kubeconfig and set PLATFORM_KUBECONFIG to it. EnsureKubeconfigSecret creates the Secret by copying the local ~/.kube/bifrost-k3s.yaml, which is system:admin in group system:masters, a client certificate that cannot be revoked without rotating the k3s CA. Every cluster call runs as cluster-admin: actuation, pod logs, exec, secrets, deleting Backup CRs. The anonymous GET /cluster/workloads/pods/{namespace}/{name}/logs takes any namespace. validateDeploymentTarget checks only kind, with no namespace allowlist, so an STG operator token can scale or restart PROD Trade and data Deployments. A STG workload can read bifrost-postgres-app, minio-backup and every per-env DB password, which bypasses the DB-level isolation TD-85 is building.
- **Measured**: MEASURED 2026-10-07. Bindings that mention platform: only tekton-deliver-rollout. Secret bifrost-platform-kubeconfig (single key bifrost-k3s.yaml) exists in bifrost-platform-stg (2026-06-28T19:04:35Z) and -prod (19:04:36Z). `kubectl auth whoami` on the local source file gives system:admin / [system:masters system:authenticated]. Secret contents were not read, so the in-cluster identity is inferred from the code path that copies that file. An unauthenticated GET of a kube-system coredns pod's logs (tailLines=1) returned 200 via PROD 30876, via STG 30878, and via Host ops.bifrost.lan.
- **Evidence**:
  - `bifrost-platform/api/internal/cluster/ensure_kubeconfig_secret.go:80` — `data, err := os.ReadFile(kubeconfigPath)`
  - `bifrost-trade-infra/k8s/base-platform/manifest.yaml:84` — `secretName: bifrost-platform-kubeconfig`
  - `bifrost-trade-infra/k8s/base-platform/secrets/platform-kubeconfig.example.yaml:13` — `# Replace with cluster admin kubeconfig (make k3s-fetch-kubeconfig).`
  - `bifrost-platform/api/internal/server/server.go:525` — `r.Get("/workloads/pods/{namespace}/{name}/logs", s.cluster.HandlePodLogs)`
  - `bifrost-platform/api/internal/cluster/actuation.go:246` — `if kind != "Deployment" {`
- **Impact**: A bug, a leaked token or an injected agent tool call in either platform environment becomes cluster-admin over PROD Trade, Golden Source, PITR backups and kube-system, so STG has the same blast radius as PROD. Anyone on the LAN can read any pod's logs without a token. RBAC and audit cannot tell a platform action from the Owner's own.
- **Fix**: Create ServiceAccounts platform-api and platform-workers per namespace, and bind only what the code uses: cluster-wide get/list/watch on core, apps and CNPG; for PROD only, the named actuations (patch deployments/scale and rollout in listed namespaces, patch nodes for cordon, create Backups in data). STG gets read-only. Restrict pods/log by RoleBinding to platform-relevant namespaces and put the route behind RoleViewer. Add a namespace allowlist to validateDeploymentTarget. Switch to in-cluster config, delete the kubeconfig Secret, and later rotate the admin client cert.
- **Ratchet**: Infra manifest policy check (ratchet proposal 'infra-manifest-policy'): no Deployment mounts a Secret whose name matches *kubeconfig*, and every platform Deployment sets serviceAccountName. Platform test: the pod-logs route returns 401 without a token. Optionally, platform-api exports a gauge when SelfSubjectReview shows system:masters, and an alert fires on it.
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml sh -c 'kubectl -n bifrost-platform-stg get secret bifrost-platform-kubeconfig </dev/null; kubectl auth can-i get secrets -n data --as=system:serviceaccount:bifrost-platform-stg:platform-api </dev/null'  # expect NotFound, then no; and an anonymous GET of a kube-system pod's logs on 30876 returns 401`
- 审批 安全/凭据（要你批） · 代价 M · 风险 med · repos: bifrost-platform, bifrost-trade-infra

### TD-205

**P1 · data · PROD Redis, which holds the daemon's control stream and state hash, has no password and is open on NodePort 30382 to two LAN /24s and, through NodePort SNAT, to every pod in the cluster**

- **状态**：未开始
- **Claim**: redis-live-prod-lan-ingress allows 192.168.10.0/24, 192.168.20.0/24 and the five flannel.1 /32 addresses, which are the SNAT source of any NodePort connection, including one from a pod in bifrost-dev, research or a plugin namespace. The NodePort file says 'dev only' but exposes redis-live-stg (30380) and redis-live-prod (30382). The server has no requirepass and no ACL. The live keys include bifrost:daemon:trading:control, which the PROD daemon consumes (poll_and_consume_control accepts 'flatten' and maps unknown commands to 'stop'), and bifrost:daemon:trading:state. Any LAN device can therefore stop or un-suspend the 2-replica PROD daemon, bypassing the trade-api /control gates and the audit trail. The NodePorts 30379/30380/30382/30432 are missing from the AGENT_FACTS §8c table.
- **Measured**: MEASURED 2026-10-07. From 192.168.20.74, PING to 192.168.10.73:30382 (PROD) and to 30380 (STG) both return +PONG with no AUTH. svc list in data: redis-live-prod-lan 30382, redis-live-stg-lan 30380, redis-dev-lan 30379, bifrost-postgres-lan 30432. redis-cli --scan in redis-live-prod lists the three daemon keys. PROD reaches this instance through ExternalName redis → redis-live-prod. bifrost-prod/daemon is 2/2 (observe-safe). Pod-to-NodePort reachability is CODE-READ; no probe pod was started.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/redis/redis-nodeport.yaml:4` — `# No password is configured on these phase-⑥ single-replica instances (dev only).`
  - `bifrost-trade-infra/k8s/data/redis/redis-nodeport.yaml:74` — `nodePort: 30382`
  - `bifrost-trade-infra/k8s/data/redis/network-policies.yaml:169` — `cidr: 192.168.10.0/24`
  - `bifrost-trade-core/src/bifrost_core/persistence/redis_daemon_state.py:20` — `TRADING_CONTROL_STREAM = "bifrost:daemon:trading:control"`
- **Impact**: A boundary hole next to D10. PROD daemon control and state are writable by any LAN device, and by any compromised pod, with no credential and no audit. Observe-safe mode prevents real orders today, but nothing protects control once execution is unlocked. Namespace isolation of the STG and PROD Redis instances is void.
- **Fix**: Delete the redis-live-prod-lan and redis-live-stg-lan NodePorts and their -lan-ingress policies; use kubectl port-forward for Redis Insight. If LAN access must stay, enable ACL users (read-only for Insight, a writer for trade) and drop the flannel.1 /32 entries. Add every remaining NodePort to AGENT_FACTS §8c.
- **Ratchet**: Infra manifest policy check: fail if a NodePort Service selects a pod labelled bifrost.io/environment in {prod, stg} without an allowlist entry, or if a NetworkPolicy for a prod/stg data pod has an ipBlock wider than /32.
- **验收**: `nc -z -w3 192.168.10.73 30382; echo $?  # expect 1; and KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data get svc redis-live-prod-lan </dev/null  # expect NotFound`
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-206

**P1 · ops-console · git-bridge answers anyone on the LAN, and its /commit runs `git add -A` on the shared checkout; /push pushes the current branch with no release-window check**

- **状态**：未开始
- **Claim**: agent/git-bridge listens on 0.0.0.0:8785 and has no auth middleware (only express.json). POST /commit stages the whole tree (`git add -A`) in any of 9 repos of the multi-session shared checkout and commits. That is exactly the action preflight.js blocks for agents (the 09-07 and 09-22 incidents). POST /push pushes HEAD's branch, normally main, to the PUBLIC origin and never runs `release.sh window`. The remediation runner's git_commit and git_push tools call these endpoints, so preflight never sees them.
- **Measured**: MEASURED 2026-10-07: node PID 65068 listens on *:8785. From LAN IP 192.168.20.74, an anonymous GET /status returns 200, and /health reports workspace=/Users/vision-mac-trader/Desktop/stocks with repos=9. PROD platform-api /api/v1/agent/bridge reports git_bridge http://192.168.10.40:8785 status=ok (the same Mac, another interface). No POST was sent.
- **Evidence**:
  - `bifrost-platform/agent/git-bridge/src/server.ts:308` — `await git(dir, ['add', '-A'])`
  - `bifrost-platform/agent/git-bridge/src/server.ts:346` — `const output = await git(dir, ['push', 'origin', branch])`
  - `bifrost-platform/agent/git-bridge/src/server.ts:372` — `const server = app.listen(PORT, '0.0.0.0', () => {`
  - `bifrost-platform/agent/remediation/src/tools/gitTools.ts:64` — `const data = await gitBridgePost('/commit', { repos, message })`
- **Impact**: Any LAN host, or any prompt run by the runner, can sweep other sessions' in-progress work into one commit and push it to a public main. That repeats the shared-worktree incident and bypasses the release window and the Owner's per-release approval. Untracked files that are not gitignored would be published too.
- **Fix**: Require a bearer token (from platform-auth.yaml) on every non-GET route, and bind to 127.0.0.1 unless the token is set. Replace `add -A` with an explicit paths[] list (`git add -- <paths>`) and reject an empty list. Make /push refuse main on Trade repos unless `release.sh window` exits 0, or drop /push and return a pull/new link.
- **Ratchet**: Code-health grep (scan.sh) that fails on argv arrays `'add', '-A'`, `'add', '.'` or `'commit', '-a'` in any repo's src. A server test asserts 401 on POST /commit without Authorization (ratchet proposal 'agent-host-route-auth').
- **验收**: `curl -s -o /dev/null -w '%{http_code}\n' http://192.168.20.74:8785/status  # expect 401 or connection refused; git -C bifrost-platform grep -n "'add', '-A'" origin/main -- agent  # expect no output`
- 审批 安全/凭据（要你批） · 代价 M · 风险 med · repos: bifrost-platform

### TD-207

**P1 · ops-console · The remediation runner (:8781) and the Hermes gateway (:8782) on the Mac minis start, approve and cancel agent jobs for anyone on the LAN: POST /run, /run/:id/respond and /skills/:id/trigger have no auth**

- **状态**：未开始
- **Claim**: deploy_mac_mini.sh exports REMEDIATION_RUNNER_BIND=0.0.0.0 on both minis, and the runner registers no auth middleware. POST /run starts a Cursor agent with a caller-supplied prompt, and that agent holds the runner's PLATFORM_OPERATOR token (or the ADMIN token as fallback). POST /run/:id/respond answers the agent's request_operator_approval gate, which is only a prompt-level guard over cordon, rollout, IB Gateway control and git_push. The Hermes gateway on .52 also binds the LAN and exposes POST /skills/:id/trigger and /reload with no auth.
- **Measured**: MEASURED 2026-10-07: anonymous GET http://192.168.10.50:8781/run and http://192.168.10.52:8781/run both return 200 (job list), and 192.168.10.52:8782/health and /executions answer anonymously. No POST was sent.
- **Evidence**:
  - `bifrost-platform/agent/remediation/src/server.ts:184` — `app.post('/run', (req, res) => {`
  - `bifrost-platform/agent/remediation/src/server.ts:211` — `app.post('/run/:id/respond', (req, res) => {`
  - `bifrost-platform/scripts/agent/deploy_mac_mini.sh:154` — `export REMEDIATION_RUNNER_BIND=0.0.0.0`
  - `bifrost-platform/agent/remediation/src/platformClient.ts:5` — `process.env.PLATFORM_OPERATOR_TOKEN?.trim() ||`
  - `bifrost-platform/agent/hermes-gateway/src/server.ts:89` — `app.post('/skills/:id/trigger', async (req, res) => {`
- **Impact**: The operator/admin tier of platform-api, including the IB Gateway control path and git push, is reachable without a token: start a runner job, then approve its own approval request. Audit records show the runner's identity, not the caller's.
- **Fix**: Add a shared-secret bearer check (a runner token in each mini's .env, sent by platform-api's remediation client) to every non-GET runner and gateway route. Refuse to start when bound off-loopback without a token. /run/:id/respond requires the operator token, never the runner token, so a job cannot approve itself.
- **Ratchet**: Server tests in agent/remediation and agent/hermes-gateway walk the express router stack and assert that every POST/PUT/DELETE layer sits behind the auth middleware (allowlist empty). A startup assertion exits 1 when bindHost != 127.0.0.1 and no token is configured.
- **验收**: `for h in 192.168.10.50 192.168.10.52; do curl -s -o /dev/null -w "$h %{http_code}\n" http://$h:8781/run; done  # expect 401 on both`
- 审批 安全/凭据（要你批） · 代价 M · 风险 med · repos: bifrost-platform

### TD-208

**P1 · ops-platform · Anonymous POST /checklist/husbandry-sync starts full-auto remediation agents: it merges the stored checklist and dispatches every failing item, and three Console pages call it on load**

- **状态**：未开始
- **Claim**: POST /api/v1/checklist/signals is operator-gated; POST /api/v1/checklist/husbandry-sync sits outside every auth group. It merges the husbandry probe into the stored checklist and runs executeDispatch over the whole merged set, not just the husbandry items. Every stored FixFullAuto item that is fail or degraded (failing-pods, redis, nginx-edge, trade-apis) is therefore started through remediation.StartInternal with scope cluster_issues_full_auto, with no role or trust check. The job's Actor is 'checklist-dispatch'; only the audit line records 'anonymous'. HusbandryStrip, mounted on Market Data Overview, Flex Query and Research Engine, POSTs it without a token from a useEffect whenever the strip shows degraded or caution. The only throttle is a per-tab sessionStorage key. Existing mitigations, a 24 h per-item dedupe and maxConcurrentAuto=1, limit how often it fires but not who can fire it.
- **Measured**: CODE-READ for the dispatch path; the POST was deliberately not sent. MEASURED: the local checklist store holds 22 signals, all ok or unknown, with empty last_dispatch, so nothing would fire right now. config/agent-tasks.yaml marks cluster_issues_full_auto as `tier: manual`. Remediation runners receive PLATFORM_OPERATOR_TOKEN (deploy_mac_mini.sh:201).
- **Evidence**:
  - `bifrost-platform/api/internal/server/server.go:418` — `r.Post("/checklist/husbandry-sync", s.checklist.HandleHusbandrySync)`
  - `bifrost-platform/api/internal/checklist/handler.go:111` — `actions := h.executeDispatch(r.Context(), resp.Signals)`
  - `bifrost-platform/api/internal/checklist/dispatch.go:162` — `job, err := h.remediation.StartInternal(ctx, remediation.StartRunnerRequest{`
  - `bifrost-platform/console/src/api/checklist.ts:63` — `const r = await fetch('/api/v1/checklist/husbandry-sync', { method: 'POST' })`
  - `bifrost-platform/console/src/components/delivery/HusbandryStrip.tsx:71` — `void syncHusbandryChecklist()`
- **Impact**: Anyone who can reach :8780, 30876 or ops.bifrost.lan, or anyone who just opens one of three Console pages, can start an autonomous repair agent holding an operator token over a cluster-admin identity (TD-204). The checklist's own operator-gated write path is bypassed.
- **Fix**: Put husbandry-sync behind RoleOperator, or move it to a timer on the workers side. Dispatch only the item ids it just probed, not the merged store. The Console calls it with authedFetch or only reads; no page effect POSTs.
- **Ratchet**: Route-auth walk test (no non-GET route outside Require, allowlist empty). A checklist test that HandleHusbandrySync dispatches only the ids it probed. A Console vitest/grep that bans mutating API calls inside useEffect without an allowlist comment.
- **验收**: `cd bifrost-platform/api && go test ./internal/server ./internal/checklist -run 'RouteAuth|HusbandrySync' -count=1; curl -s -m5 -o /dev/null -w '%{http_code}\n' -X POST http://192.168.10.73:30876/api/v1/checklist/husbandry-sync  # expect 401`
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-platform

### TD-209

**P1 · data · Every data-layer alert (backup failed, WAL archive stalled, NAS MinIO down, logical backup missing) goes to one webhook that writes it to STG platform-api's in-memory audit log and returns 200: no human is ever told**

- **状态**：未开始
- **Claim**: Alertmanager's root route and only real receiver is bifrost-ops-agent, a webhook to platform-api.bifrost-platform-stg. HandleAlertmanager runs a static Diagnose(), writes one line to the memory-only audit log (NewAuditLog("")) and returns 200. There is no email, chat or push channel, and Watchdog routes to "null" with no external dead-man's switch. Alertmanager counts this as successful delivery, so alerting looks healthy while nobody is told. TD-196 covers the audit log's persistence, not this routing.
- **Measured**: MEASURED 2026-10-07 00:45 UTC. The live config has two receivers, "null" and bifrost-ops-agent (webhook_configs only). Over 24 h, notifications_total is non-zero only for webhook (~41) and failed_total is 0 for every integration. BifrostLogicalBackupMissing has been active since 22:33Z with receivers ['bifrost-ops-agent'] and no one acting on it. platform and infra contain no telegram, ntfy, pushover, smtp or dead-man configuration.
- **Evidence**:
  - `bifrost-platform/api/internal/opsagent/handler.go:77` — `h.audit.RecordDirect("ops-agent", actuation.RoleOperator, "ops-agent.alertmanager", payload.Receiver, "ok", detail)`
  - `bifrost-platform/api/internal/server/server.go:113` — `audit := actuation.NewAuditLog("")`
  - `bifrost-trade-infra/scripts/k3s/values-kube-prometheus.yaml:148` — `- url: http://platform-api.bifrost-platform-stg.svc.cluster.local:8780/api/v1/ops-agent/alertmanager`
  - `bifrost-trade-infra/scripts/k3s/values-kube-prometheus.yaml:122` — `alertname: 'Watchdog|InfoInhibitor'`
- **Impact**: A failing backup, a stalled WAL archive or an offline NAS drive is noticed only if someone opens the Console. The 10-05 MinIO drive-offline outage ran 6h40m with BifrostPostgresWalArchiveStalled firing and no one handling it, and the same path applies today (TD-210 is firing now). Any STG platform-api rollout erases even the audit record.
- **Fix**: Add a human receiver for severity=critical and for Bifrost(Postgres|MinIONas|LogicalBackup).* (for example ntfy, Pushover or email, sent from the Mac mini operator-plane outside the cluster), and keep the webhook with continue: true. Route Watchdog to an external heartbeat check (healthchecks on the NAS or a Mac mini) that pages when the heartbeat stops. Persist webhook receipts once TD-196 lands.
- **Ratchet**: Infra alerting test (ratchet proposal 'alerting-contract'): load values-kube-prometheus.yaml and fail unless every critical and Bifrost backup/WAL/MinIO alert routes to at least one receiver that is not an in-cluster webhook, and Watchdog routes to a non-null receiver.
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl get --raw "/api/v1/namespaces/monitoring/services/kube-prometheus-stack-alertmanager:9093/proxy/api/v2/alerts?active=true" </dev/null | python3 -c "import json,sys;a=json.load(sys.stdin);print(sorted({(x['labels']['alertname'],tuple(sorted(r['name'] for r in x['receivers']))) for x in a if x['labels']['alertname'] in ('Watchdog','BifrostLogicalBackupMissing') or x['labels'].get('severity')=='critical'}))"  # every critical/backup alert lists a receiver other than bifrost-ops-agent; Watchdog lists a non-null receiver`
- 审批 PROD 变更（要你批） · 代价 M · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-210

**P1 · data · The nightly logical backup of hand-entered data failed on its first scheduled run: it connects before the new pod's NetworkPolicy is programmed and gets Connection refused**

- **状态**：未开始
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

### TD-211

**P1 · trade-worker · Working orders are never persisted: the plugin's snapshot has no open_orders, the daemon TRUNCATEs raw_broker.open_orders every hour, and the UI says 'No working orders at IB.'**

- **状态**：未开始
- **Claim**: The IB Gateway plugin's account snapshot carries only host_connected, secondary_connected, accounts_snapshot, accounts_count and mode; it never includes open_orders or last_execution_rows. On every hourly accounts refresh (and every refresh_accounts command), core refresh_accounts_from_redis_edge reads `data.get("open_orders") or []`, so it always gets [], and calls write_open_orders([]), which TRUNCATEs the table and writes nothing. /api/monitor/open-orders and /status portfolio.open_orders therefore always return [], and the Trade menubar states 'No working orders at IB.' as fact. The intraday TWS fills path (last_execution_rows → write_account_executions) is dead the same way and has written nothing since June. The worker CLAUDE.md and the ib_account_keys docstring still describe both as persisted.
- **Measured**: MEASURED 2026-10-07 00:44 UTC. raw_broker.open_orders has 0 rows. /api/monitor/open-orders returns {"open_orders":[]}. executions_raw_tws max(created_at) for tws_client is 2026-06-10 03:51 (plus one null-source row dated 08-08), while executions_raw_flex has fills on 7 trade dates since 09-16. `git grep open_orders|last_execution_rows` on plugin origin/main src returns nothing. The PROD daemon runs 2/2 with broker writes on. The TRUNCATE itself is CODE-READ, because the daemon logs no INFO (TD-216).
- **Evidence**:
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/live.py:304` — `"accounts_snapshot": snap_accounts,`
  - `bifrost-trade-core/src/bifrost_core/portfolio/ib_edge.py:107` — `oo = data.get("open_orders") or []`
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/postgres_sink.py:541` — `cur.execute(f"TRUNCATE TABLE {GOLDEN_OPEN_ORDERS}")`
  - `bifrost-trade-frontend/src/layout/menubar/BookControl.tsx:272` — `? 'No working orders at IB.'`
  - `bifrost-trade-worker/CLAUDE.md:62` — `账户、持仓、未成交订单、TWS 成交 → Golden Source 'raw_broker.*'`
- **Impact**: The Owner places orders by hand in TWS (D10 does not stop that). Every working order is reported as nonexistent on the Live page, in the BookControl ORD list and in the Research MCP trade_context, and same-day fills reach the system only through next-day Flex.
- **Fix**: Owner chooses. (A) The plugin adds read-only reqOpenOrders/reqExecutions output to the snapshot (no order path, D10-safe), and core writes open_orders only when the key is present, because absent is not empty. (B) Retire raw_broker.open_orders and the TWS-fill branch, and change the UI to 'Working orders are not tracked'. In both cases stop the TRUNCATE when the key is missing, and fix the worker CLAUDE.md and the ib_account_keys docstring.
- **Ratchet**: Redis-ib snapshot contract (ratchet proposal 'redis-ib-snapshot-contract'): tests/contracts/redis_ib_keys.json in core and plugin lists every snapshot key core reads, with its producer; a key core reads but the plugin never writes fails. Core test: refresh_accounts_from_redis_edge with a snapshot lacking 'open_orders' does not call write_open_orders.
- **验收**: `git -C bifrost-trade-core grep -n 'data.get("open_orders") or \[\]' origin/main -- src/bifrost_core/portfolio/ib_edge.py | wc -l  # 0; and either git -C bifrost-platform-plugin grep -c '"open_orders"' origin/main -- src/bifrost_plugin/ib_gateway/live.py ≥ 1 (A) or the string 'No working orders at IB.' is gone from the frontend (B)`
- 审批 跨仓库发版 · 代价 M · 风险 med · repos: bifrost-platform-plugin, bifrost-trade-core, bifrost-trade-worker, bifrost-trade-frontend

### TD-212

**P2 · trade-worker · A failed IB positions or summary read is written as truth: the daemon deletes every raw_broker.positions row of the account and nulls its NAV until the slot reconnects**

- **状态**：未开始
- **Claim**: When reqPositionsAsync or accountSummaryAsync fails on a session that still lists managedAccounts, the plugin publishes the account with positions [] and a summary holding only {account}. Since worker 0.2.6, account_push writes any snapshot younger than 120 s whose fingerprint changed, with no sanity check. Core sync_accounts_snapshot_to_tables then runs DELETE FROM raw_broker.positions WHERE account_id = %s (seen_keys is empty) and upserts net_liquidation, total_cash and buying_power as NULL. TD-137's freshness check (core 0.52.0) keeps a 07:00 or 11:00 ET wipe out of the 16:20 capture. It does not stop a wipe written after 16:00, because the wipe itself stamps updated_at=now().
- **Measured**: MEASURED trigger via Loki {namespace=data, app=ib-gateway}: 2026-10-06 10:59:58 UTC (host TWS auto log-off, 07:00 ET) shows 'reqPositionsAsync: Socket disconnect' and 'accountSummaryAsync U17123565: Not connected'; there was also a 'positions request timed out' at 04:15 UTC. The write path is CODE-READ, and worker tests/test_account_push.py has no degraded case. No stored damage was found: bifrost_prod account_nav_daily for 10-05 and 10-06 has non-null NAV for all accounts. How long the wipe window lasts was not measured.
- **Evidence**:
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/ib_ops.py:76` — `all_positions = []`
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/ib_ops.py:91` — `summary["account"] = aid`
  - `bifrost-trade-worker/src/bifrost_worker/daemon/app/account_push.py:92` — `if aid and self._written.get(aid) != _fingerprint(a):`
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/accounts_sync.py:212` — `f"DELETE FROM {GOLDEN_POSITIONS} WHERE account_id = %s", (account_id,)`
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/accounts_sync.py:117` — `net_liquidation = EXCLUDED.net_liquidation,`
- **Impact**: After a routine IB disconnect (daily at 07:00 ET), Positions, attribution and the Research trade context read the account as flat with no NAV until the slot reconnects. A degraded write between 16:00 and 16:20 ET would store a wrong day permanently.
- **Fix**: Worker account_push: refuse to write an account whose summary lacks NetLiquidation, or whose positions went from non-empty to empty unless the snapshot marks the positions read as successful; log the refusal at warning. Plugin: omit the account row (or emit positions_ok=false) when reqPositionsAsync or accountSummaryAsync failed. Core sync: never null an existing NAV from an empty summary.
- **Ratchet**: Worker unit test test_degraded_snapshot_is_not_written (summary {account} only, or positions [] after a non-empty write → writer.write returns 0). Plugin test: a reqPositionsAsync exception → the row is omitted or flagged. Both are part of ratchet proposal 'redis-ib-snapshot-contract'.
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -At </dev/null -c "SET default_transaction_read_only=on;" -c "select count(*) from raw_broker.account where net_liquidation is null and updated_at > now()-interval '2 days'"  # 0 after two weekdays that include the 07:00 / 11:00 ET log-offs; plus the worker test passes`
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-trade-worker, bifrost-platform-plugin, bifrost-trade-core

### TD-213

**P2 · frontend · Risk › Limits 'Daily loss on the allocation' sums the realised P&L of every trade the allocation ever closed, not today's, so a losing day reads 0 consumed**

- **状态**：未开始
- **Claim**: useLimitBook builds lossToday from closedToday, but that filter keeps every closed or expired trade of the running allocation (`i.closed && i.openedOn != null`) and never compares a close date with today. The UTC date only decides whether any reading is shown at all (a fill with trade_date == UTC today). On any day with a fill, the gate-daily-loss row compares the allocation's lifetime realised P&L with guard.max_daily_loss_usd. TradeReading drops closed_on, although all closed trades carry it. readTrades also multiplies every fill by 100, including STK fills; none are attached to trades today, so that part is latent.
- **Measured**: MEASURED on PROD with GETs only, at origin/main dfb7858e. Gate set 1 has guard.risk.max_daily_loss_usd=5000; status.strategy.active is allocation 1 on gate 1. Recomputing the hook's formula for opportunities {1,2} (53 closed or expired trades) gives lifetime realised of about +$23.5k, so on any fill day the row reads 0 consumed. All 79 closed or expired trades carry closed_on.
- **Evidence**:
  - `bifrost-trade-frontend/src/hooks/useLimitBook.ts:188` — `const closedToday = mine.filter((i) => i.closed && i.openedOn != null)`
  - `bifrost-trade-frontend/src/hooks/useLimitBook.ts:201` — `lossToday: todayFills.length === 0 ? null : closedToday.reduce((a, i) => a + (i.realised ?? 0), 0),`
  - `bifrost-trade-frontend/src/utils/limitsModel.ts:405` — `current: r.lossToday == null ? null : Math.max(0, -r.lossToday),`
  - `bifrost-trade-frontend/src/utils/tradeReadings.ts:71` — `return a + (isBuySide(e.side) ? -(price * qty * 100 + commission) : price * qty * 100 - commission)`
- **Impact**: The one written daily-loss limit on the Risk page cannot show a losing day while the allocation is up overall: a breach hidden behind a green row. Nothing enforces the gate today (paper_trade true, daemon under D10), so the harm is a misleading risk reading, not a missed halt.
- **Fix**: Carry closed_on into TradeReading (closedOn). Filter closedToday by closedOn === the session day (etTodayIso, or the Chicago day if the ledger's day is meant), and gate todayFills on the same day. In readTrades use the execution's multiplier (1 for STK) instead of a hard-coded 100.
- **Ratchet**: Extract the gateReadings derivation into a pure function and test it: a trade closed yesterday with a large loss plus a fill today gives lossToday 0, and a trade closed today counts. A readTrades test with an STK fill is not multiplied by 100. These run once ci-frontend runs vitest (ratchet proposal 'frontend-vitest-and-date-lint').
- **验收**: `cd bifrost-trade-frontend && npx vitest run src/hooks/useLimitBook.test.ts src/utils/tradeReadings.test.ts  # new cases: closed-yesterday excluded, closed-today counted, STK fill ×1`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-214

**P2 · frontend · Performance and Portfolio Overview summaries start the range at UTC midnight, so they include the previous month's last Chicago day**

- **状态**：未开始
- **Claim**: getTimeRangeStamps parses sinceStr ('YYYY-MM-01') with new Date(), which reads a date-only string as UTC midnight, while untilStr is parsed as local 23:59:59. trade-api compares from_ts/to_ts as the calendar day in America/Chicago. UTC midnight on the 1st is 19:00 Chicago on the previous day, so every month, quarter, half-year and year summary also counts the fills of the day before the range. The by-day path uses getChicagoDayRange (defined in the same file) correctly, so the strip and the calendar under it disagree.
- **Measured**: MEASURED on PROD /api/account/performance (granularity=day, source_scope=performance_book) with to_ts=1790830799. Q3 2026: from_ts=1782864000 (the client's UTC midnight) gives fill_count 111 and win_count 41; 1782882000 (Chicago midnight) gives 110 and 40, and realised P&L differs by a 06-30 fill. May 2026: 36 vs 33 fills (three 04-30 fills). Sep and Q2 2026 match only because the prior month-end had no fills.
- **Evidence**:
  - `bifrost-trade-frontend/src/utils/ledger/performanceUtils.ts:162` — `sinceTs: Math.floor(new Date(sinceStr).getTime() / 1000),`
  - `bifrost-trade-frontend/src/utils/ledger/performanceUtils.ts:163` — `untilTs: Math.floor(new Date('${untilStr}T23:59:59').getTime() / 1000),`
  - `bifrost-trade-api/src/bifrost_api/trading/routers/executions.py:179` — `_TRADE_DATE_NOTE = "Compared as a date: the timestamp's calendar day in America/Chicago."`
  - `bifrost-trade-frontend/src/pages/portfolio/overview/PortfolioOverviewPage.tsx:154` — `const range = useMemo(() => getTimeRangeStamps('quarter', anchorMonth), [anchorMonth])`
- **Impact**: Headline realised P&L, win rate, fills and return on Performance and Portfolio Overview are wrong whenever the previous month's last day had trades, and they disagree with the by-day calendar on the same page.
- **Fix**: Build both ends from getChicagoDayRange: sinceTs = getChicagoDayRange(sinceStr).since_ts and untilTs = getChicagoDayRange(untilStr).until_ts, independent of the browser's time zone.
- **Ratchet**: A unit test run under TZ=UTC and TZ=America/Chicago: getTimeRangeStamps('quarter','2026-09') returns sinceTs 1782882000 and untilTs 1790830799 in both. ESLint no-restricted-syntax bans new Date(<date-only identifier>) and Date.parse on *Str/*Date/*Iso variables without an explicit time and zone (ratchet proposal 'frontend-vitest-and-date-lint').
- **验收**: `cd bifrost-trade-frontend && TZ=UTC npx vitest run src/utils/ledger/performanceUtils.test.ts -t getTimeRangeStamps && TZ=America/Chicago npx vitest run src/utils/ledger/performanceUtils.test.ts -t getTimeRangeStamps`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-215

**P2 · trade-worker · Nothing alerts when the only writer of raw_broker.account and positions stops: the daemon has no liveness probe and no freshness rule**

- **状态**：未开始
- **Claim**: The daemon leader pod is the only writer of raw_broker.account and raw_broker.positions, which feed Positions, attribution and the nightly NAV and position snapshots. Its readinessProbe only checks that CNPG and Redis accept connections, and it has no livenessProbe, so a hung FSM loop or a dead pub/sub listener keeps the pod Ready. No live PrometheusRule covers the Trade daemon or raw_broker freshness. A 'per-table last_nonzero_write for raw_broker' stale rule is planned in RATCHETS.md but not implemented.
- **Measured**: MEASURED 2026-10-07: live alert names matching daemon|broker|account|worker|stale|fresh are only Flex*, MarketData*, DagsterDaemonHeartbeat, EventRadar, ResearchCronJob and LogicalBackupDrill. PROD deploy/daemon has an empty livenessProbe. raw_broker.account also still holds U17113214, last written 2026-05-11 (adjacent to TD-137; not re-reported).
- **Evidence**:
  - `bifrost-trade-infra/k8s/base/worker/manifest.yaml:94` — `command: ["python", "scripts/wait_for_data.py", "--once"]`
  - `bifrost-trade-worker/src/bifrost_worker/daemon/app/account_push.py:198` — `logger.warning("[account_push] listener error: %s; re-subscribing", e)`
- **Impact**: If account sync stops during market hours, pages keep showing the last book as current, and once the account has been written after 16:00 ET the 16:20 capture can store it as the day's.
- **Fix**: Add a freshness gauge (daemon /metrics, or a postgres-exporter query on max(updated_at) per account in raw_broker.account) and a PrometheusRule that fires when the host account has not been written for 15 minutes during RTH while the gateway reports host_connected. Add a livenessProbe that checks the heartbeat timestamp the daemon writes to Redis. Neither scales nor arms the daemon (D10-safe).
- **Ratchet**: The alert rule itself, with an absent() twin. An infra check that every Deployment writing Golden Source has a livenessProbe or is on an allowlist (ratchet proposal 'infra-manifest-policy').
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl get prometheusrules -A -o go-template='{{range .items}}{{range .spec.groups}}{{range .rules}}{{if .alert}}{{.alert}}{{"\n"}}{{end}}{{end}}{{end}}{{end}}' </dev/null | grep -ci 'broker.*stale\|daemon.*stale'  # ≥1; and kubectl -n bifrost-prod get deploy daemon -o jsonpath='{.spec.template.spec.containers[0].livenessProbe}' </dev/null  # non-empty`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-trade-worker

### TD-216

**P2 · trade-worker · The daemon never configures logging: every INFO line is dropped, and write failures logged at debug are invisible**

- **状态**：未开始
- **Claim**: Nothing in worker src or scripts calls logging.basicConfig or dictConfig or adds a handler, so Python's lastResort handler emits only WARNING and above. The leader-election lines were raised to warning just so they would show. Everything at INFO disappears, including '[ib_edge] snapshot applied', account_push, heartbeat state and control commands. Failures of write_open_orders, write_account_executions and the contract_quote_live sync are logged at debug. The in-process Metrics class is never exported.
- **Measured**: MEASURED 2026-10-07: `kubectl -n bifrost-prod logs deploy/daemon --since=3h` shows only 'Defaulted container' and the 'standby until acquired' WARNING; the leader pod (114 min old) had 3 lines in total. A 2 h Loki query for 'ib_edge' in bifrost-prod returns 0 lines, although raw_broker.account was written at 00:07 and 00:27 UTC.
- **Evidence**:
  - `bifrost-trade-worker/scripts/run_daemon.py:13` — `from bifrost_worker.daemon.app.entry import run_daemon`
  - `bifrost-trade-worker/src/bifrost_worker/daemon/lease.py:632` — `on_started_leading=lambda: logger.warning(`
  - `bifrost-trade-core/src/bifrost_core/portfolio/ib_edge.py:113` — `logger.debug("[ib_edge] write_open_orders: %s", e)`
  - `bifrost-trade-worker/src/bifrost_worker/daemon/core/metrics.py:11` — `"""In-memory counters and running averages; log on update or periodically."""`
- **Impact**: A write path can fail or never run (TD-211, the contract_quote_live mirror under TD-140) and nothing appears in Loki or kubectl logs. Debugging the only writer of raw_broker account and positions data means reading the database.
- **Fix**: Configure logging at process start in run_daemon (level from LOG_LEVEL, default INFO, one-line format to stdout). Raise the sink and edge write-failure logs from debug to warning. Optionally export a few counters (accounts written, writes failed, last write ts) on /metrics, which also feeds TD-215.
- **Ratchet**: Worker test: the entry's logging setup leaves the root logger at INFO with a stream handler. A grep test that no logger.debug call sits on a line that names write_ (baseline 0).
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n bifrost-prod logs deploy/daemon --since=2h </dev/null | grep -c -E 'ib_edge|account_push'  # > 0`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-worker, bifrost-trade-core

### TD-217

**P2 · data · The Barman base+WAL backup, the only copy of the 34 GB Golden Source history, has never been restored, and has not been tried at all against the NAS MinIO it moved to on 10-06**

- **状态**：未开始
- **Claim**: The CNPG cluster has a 30-day recoverability window (firstRecoverabilityPoint 2026-09-06), but infra has never had a bootstrap.recovery or externalClusters manifest, and only one Cluster has ever existed. The monthly drill in k8s/data/logical-backup restores only the logical dump of 7 hand-entered schemas into an emptyDir Postgres and never reads the Barman object store. So nobody knows whether barman-cloud-restore works against the NAS MinIO the bucket moved to on 10-06, with its credentials, gzip WAL and serverName. TD-135 mentions a restore drill only as a one-off step of the plugin migration.
- **Measured**: MEASURED 2026-10-07. Only data/bifrost-postgres exists. firstRecoverabilityPoint is 2026-09-06T06:19:40Z, lastSuccessfulBackup 2026-10-06T17:32:39Z. `git grep` over infra finds no recovery bootstrap (the only 'bootstrap:' is initdb at cluster.yaml:19). 10-03 and 10-04 do have completed ondemand backups; only the scheduled 'daily' names are missing for those days. The first NAS backup is bifrost-postgres-manual-20261006-nas.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/cluster.yaml:43` — `barmanObjectStore:`
  - `bifrost-trade-infra/k8s/data/logical-backup/cronjob-drill.yaml:4` — `# (emptyDir) and requires every table's row count to equal the manifest. Never`
  - `bifrost-trade-infra/k8s/data/logical-backup/README.md:24` — `RPO is one day for this copy. Point-in-time recovery to the minute is still`
- **Impact**: If both instances or the cluster are lost, restoring market data, features and research history is untested exactly when it is needed. Credential, endpoint, compression, serverName or WAL-gap problems would surface only during the incident.
- **Fix**: Add a monthly CNPG recovery drill: a scratch Cluster (1 instance, bootstrap.recovery from the bifrost-postgres object store with targetTime about 1 h ago, a different serverName, read-only creds) in its own namespace on a node with about 80 GB free. Compare row counts of a fixed table list with PROD at the target time, record the result as a metric or ConfigMap, then delete the scratch Cluster. Coordinate with TD-135's plugin migration.
- **Ratchet**: Alert BifrostPostgresRecoveryDrillStale: time() - max(kube_cronjob_status_last_successful_time{cronjob="pg-recovery-drill"}) > 35d, plus absent() of the series, so a drill that has never run also fires.
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data get cronjob pg-recovery-drill -o jsonpath='{.status.lastSuccessfulTime}' </dev/null  # a date within the last 35 days`
- 审批 PROD 变更（要你批） · 代价 M · 风险 med · repos: bifrost-trade-infra

### TD-218

**P2 · data · Every backup copy (Barman base+WAL, logical dumps hot and cold, the W3 archive) is on the one NAS 192.168.10.20:/volume1, and the open offsite decision is not in the ledger**

- **状态**：未开始
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

### TD-219

**P2 · frontend · The rail's amber 'alerts fired today' count can never be non-zero: it matches trade_date against the UTC date, and alerts are stamped with an earlier session**

- **状态**：未开始
- **Claim**: firedTodayCount keeps alerts whose trade_date equals the UTC date of the browser clock. alert_scan stamps each alert with the session it judges and writes it on a later day: today at 22:30 UTC the next weekday, and after TD-97's planned move into the 02:30 UTC batch still the next UTC day. No alert can have trade_date == UTC today, so the Market group's amber count is always 0 and its tooltip says '0 alerts fired today'. TD-97 fixes the backend lag only; this reader stays broken afterwards.
- **Measured**: MEASURED: GET /api/plugin/research/research/alerts?limit=200&days=90 returned 89 alerts. In 0 of 89 does trade_date equal the UTC day of computed_at, and in 0 of 89 the NY day (for example computed_at 2026-10-05T22:30Z with trade_date 2026-10-02).
- **Evidence**:
  - `bifrost-trade-frontend/src/hooks/useFiredAlerts.ts:27` — `return (data?.items ?? []).filter((i) => i.trade_date === today).length`
  - `bifrost-trade-frontend/src/layout/EquipRail.tsx:433` — `const firedToday = firedTodayCount(alerts, new Date().toISOString().slice(0, 10))`
  - `bifrost-trade-frontend/src/layout/EquipRail.tsx:469` — `'${firedToday} alert${firedToday === 1 ? '' : 's'} fired today'`
- **Impact**: Silent green. The one ambient signal that Research alerts fired has been quiet for at least 90 days, while 89 alerts were written.
- **Fix**: Define 'today' for alerts the way the store writes them: count alerts on the newest session (trade_date == max(trade_date)) whose computed_at falls on the current NY day, or count by computed_at's NY day. Share that definition with AlertsPage's firedStanding.
- **Ratchet**: Unit test with a fixture shaped like the live store (trade_date 2026-10-02, computed_at 2026-10-05T22:30Z, now 2026-10-05T23:00Z → count 1). The UTC-today lint in ratchet proposal 'frontend-vitest-and-date-lint' blocks the pattern.
- **验收**: `cd bifrost-trade-frontend && npx vitest run src/hooks/useFiredAlerts.test.ts`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-220

**P3 · ops-platform · No test enumerates platform-api routes for auth: POST /cluster/sync-kubeconfig and the plane's POST /hermes/run-first-task are unauthenticated, and a failed LoadAuth is not logged**

- **状态**：未开始
- **Claim**: TestRouterRequiresAuthForOperatorRoutes spot-checks only /agent/nightly-run and /patrol/trigger. The only chi.Walk test (operatorplane/plane_test.go) checks route-set parity, not auth. So mutating routes outside Require groups ship unnoticed. Besides /console/ws (TD-203) and /checklist/husbandry-sync (TD-208), there are two more. POST /cluster/sync-kubeconfig runs the ssh kubeconfig-sync script and overwrites ~/.kube/bifrost-k3s.yaml on the bdev instance, where PLATFORM_CLUSTER_SYNC_ENABLED=1; it answers 200 with OK:false when sync is disabled. The plane's POST /hermes/run-first-task is operator=false; it runs readiness and appends an insight record. Separately, server.New replaces a failed LoadAuth with an empty AuthService without logging. That fails closed (every gated route answers 401) but looks like a token problem.
- **Measured**: MEASURED: a chi.Walk over a scratch copy (reading middleware names only, no requests sent) found 3 of 83 non-GET routes without Require: husbandry-sync, sync-kubeconfig and run-first-task. A POST without a token to /api/v1/patrol/trigger/does-not-exist-x on PROD returns 401, so the gated routes work. The bdev process env has PLATFORM_CLUSTER_SYNC_ENABLED=1. No POST was sent to the ungated routes.
- **Evidence**:
  - `bifrost-platform/api/internal/server/server_test.go:196` — `func TestRouterRequiresAuthForOperatorRoutes(t *testing.T) {`
  - `bifrost-platform/api/internal/server/server.go:524` — `r.Post("/sync-kubeconfig", s.cluster.HandleSyncKubeconfig)`
  - `bifrost-platform/api/internal/operatorplane/plane.go:132` — `{"POST", "/hermes/run-first-task", false,`
  - `bifrost-platform/api/internal/server/server.go:111` — `auth = &actuation.AuthService{}`
- **Impact**: The unauthenticated-route class (TD-203, TD-208) comes back with every new route. Today anyone on the LAN can repeatedly trigger an ssh sync that rewrites the Owner's kubeconfig, and fill the Hermes insight store. A broken auth file is mistaken for a token problem.
- **Fix**: Move /cluster/sync-kubeconfig into the operator group, set operator=true for /hermes/run-first-task, and switch Console callers (clusterActuation.ts:62) to authedFetch. Log slog.Error on LoadAuth failure and expose auth_loaded in /health. Return non-2xx when the sync is disabled.
- **Ratchet**: TestEveryMutatingRouteRequiresARole: chi.Walk srv.Router(); every POST/PUT/PATCH/DELETE route, plus /console/ws, must carry auth.Require, against an explicit allowlist with a reason per entry (empty today). The same walk over operatorplane.routeTable() asserts operator=true for every non-GET entry. Alert BifrostPlatformAuthNotLoaded on auth_loaded=false.
- **验收**: `cd bifrost-platform/api && go test ./internal/server ./internal/operatorplane -run 'TestEveryMutatingRouteRequiresARole|TestPlaneWritesRequireOperator' -count=1`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-221

**P3 · ops-console · The governance catalog says nobody but the daemon writes ib:operator:cmd, but platform-api does (sanctioned by D-IB-Heal), and the runner's ib_gateway_control can switch the PROD gateway to mock with only a prompt-level approval**

- **状态**：未开始
- **Claim**: platform-api XADDs op=reconnect_all to ib:operator:cmd. That is sanctioned by spine D-IB-Heal (SIGNED 2026-08-27: 'L1 platform-api reconnect soft-first then rollout … D10 BLOCKED — reconnect/observe only'). But FORBIDDEN_ACTIONS ('ib:operator:cmd RPC', all modes), CLAUDE.md §3 ('only the daemon writes it') and probe.go ('Platform must not access ib:operator:cmd') all still say otherwise. Separately, the remediation runner's ib_gateway_control tool can call reconnect and also mode live|mock|maintenance on the PROD gateway. Its only approval is a prompt instruction (request_operator_approval), and the respond endpoint behind it is unauthenticated (TD-207). preflight.js does not see this path.
- **Measured**: CODE-READ. Live: PROD platform-api runs with OPS_IB_AUTOREPAIR_ENABLED=true and REDIS_IB_PLATFORM_PASS present (env names only). The autorepair loop only rolls out; it does not XADD.
- **Evidence**:
  - `bifrost-platform/console/src/lib/architecture/agentProtocolCatalog.ts:105` — `{ action: 'ib:operator:cmd RPC', scope: 'All modes' },`
  - `bifrost-platform/api/internal/ibgateway/operator_cmd.go:55` — `"XADD", operatorCmdStream, "*",`
  - `bifrost-platform/api/internal/ibgateway/service.go:183` — `softErr := s.sendOperatorCommand(ctx, "reconnect_all", 30*time.Second)`
  - `bifrost-platform/agent/remediation/src/tools/platformTools.ts:294` — `'/api/v1/plugins/ib-gateway/control/${encodeURIComponent(action)}',`
- **Impact**: Agents and the Owner read a boundary that matches neither the code nor the spine. An agent can switch the PROD gateway to mock without an enforced approval, after which downstream consumers see non-live market data.
- **Fix**: Record platform-api as the sanctioned writer of exactly {reconnect_all} in FORBIDDEN_ACTIONS, AGENT_FACTS and CLAUDE.md §3 (with the Cursor parity bump), optionally enforced with a Redis ACL. Remove 'mode' from the runner tool, or require an admin token server-side for /control/mode. Add a preflight rule for POST /plugins/ib-gateway/control/(mode|reconnect).
- **Ratchet**: Go AST test: sendOperatorCommand's op argument is only ever "reconnect_all", and operatorCmdStream appears only in ibgateway/operator_cmd.go. A code-health check compares the set of XADD writers to the operator stream across repos with an allowlist in AGENT_FACTS.
- **验收**: `git -C bifrost-platform grep -n "'mode'" origin/main -- agent/remediation/src/tools/platformTools.ts  # no mode action; git -C bifrost-platform grep -n 'ib:operator:cmd' origin/main -- console/src/lib/architecture/agentProtocolCatalog.ts  # the catalog names the sanctioned reconnect_all writer`
- 审批 安全/凭据（要你批） · 代价 M · 风险 med · repos: bifrost-platform, bifrost-trade-infra

### TD-222

**P3 · ops-platform · Platform's D10 scale guard only blocks daemon 0→n: the PROD daemon (2, observe-safe) and DEV (1) can be scaled to 20 by any operator-token caller that bypasses preflight**

- **状态**：未开始
- **Claim**: Scale refuses only when Name=='daemon' and current==0. The PROD daemon runs at 2 and DEV at 1, so 2→20 and 1→20 pass. Claude sessions are covered: preflight d10McpRule blocks MCP scale_deployment of daemon to any replicas>0. The remediation runner, the Console and a direct HTTP call with an operator token are not covered. Argo does not auto-sync bifrost-prod or bifrost-stg, so a manual scale persists. The only test covers 0→2 in stg and 2→0 in prod.
- **Measured**: MEASURED 2026-10-07: bifrost-prod/daemon 2/2, bifrost-dev/daemon 1/1, bifrost-stg/daemon 0/0. syncPolicy.automated is empty on Argo apps bifrost-prod and bifrost-stg. The scale endpoint was not called.
- **Evidence**:
  - `bifrost-platform/api/internal/cluster/actuation.go:149` — `if req.Name == "daemon" && current == 0 && req.Replicas > 0 {`
  - `bifrost-trade-infra/k8s/overlays/prod/daemon-observe-safe.patch.yaml:8` — `replicas: 2`
- **Impact**: Non-Claude callers can start several observe-mode daemon FSM writers in PROD without an Owner unlock, and those writers are not designed for N replicas. Live orders stay unarmed while the observe-safe patch holds.
- **Fix**: Block any replica increase (requested > current) for Deployment daemon in the Trade namespaces until spine D10 reads UNLOCKED, reading D10 from ops-context as preflight does.
- **Ratchet**: actuation_scale_test.go: TestScaleDaemonUpFromNonZeroBlocked (2→3 in bifrost-prod), plus a table test over all three Trade namespaces.
- **验收**: `cd bifrost-platform/api && go test ./internal/cluster -run 'TestScaleDaemon' -count=1 -v | grep -E 'NonZero|PASS|FAIL'`
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-platform

### TD-223

**P3 · ops-platform · STG and PROD platform-workers both run the IB gateway auto-repair loop against the one live data/ib-gateway, each with its own 15-minute cooldown**

- **状态**：未开始
- **Claim**: Both platform overlays set OPS_IB_AUTOREPAIR_ENABLED=true for platform-workers (and for platform-api, where the role gate makes it inert). Both read the same redis-ib health, and both may roll out data/Deployment/ib-gateway. lastAutoRollout is a local variable in each process, so the 900 s cooldown is not shared. D-IB-Heal sanctions one optional auto-repair loop, not two. The trigger bar is high: stale streak ≥3, rollout_recommended, mode live and host_connected, so it has never been seen to fire.
- **Measured**: MEASURED 2026-10-07: /api/v1/plugins/ib-gateway/self-heal returns auto_repair_enabled:true on both 30876 and 30878, with identical last_action_ts (1790169059.9). ib-gateway restartedAt is 2026-09-08. The audit log is memory-only (TD-196).
- **Evidence**:
  - `bifrost-trade-infra/k8s/overlays/platform-stg/platform-workers-env.patch.yaml:16` — `- name: OPS_IB_AUTOREPAIR_ENABLED`
  - `bifrost-platform/api/internal/ibgateway/autorepair.go:25` — `var lastAutoRollout time.Time`
  - `bifrost-platform/api/internal/ibgateway/service.go:176` — `target := dataNamespace + "/Deployment/" + gatewayDeployName`
- **Impact**: During a stale-snapshot streak, STG and PROD workers can each roll out the single live gateway within about 30 s of each other, and a STG platform release with a bug in this loop acts on production market data.
- **Fix**: Set OPS_IB_AUTOREPAIR_ENABLED=false in the platform-stg overlays (workers and api) so STG only observes, consistent with TD-130 step (4) for the autopilot. Optionally take a coordination.k8s.io Lease in data before any rollout.
- **Ratchet**: Infra manifest policy check: across `kustomize build overlays/platform-*`, exactly one Deployment has OPS_IB_AUTOREPAIR_ENABLED=true with PLATFORM_ROLE in {workers, all}.
- **验收**: `curl -s -m10 http://192.168.10.73:30878/api/v1/plugins/ib-gateway/self-heal | grep -o '"auto_repair_enabled":[a-z]*'  # false on STG; PROD 30876 stays true`
- 审批 PROD 变更（要你批） · 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-224

**P3 · ops-console · Opening the Cluster page as an operator auto-starts a full-auto remediation run, and neither platform-api nor the runner deduplicates by scope or active job**

- **状态**：未开始
- **Claim**: For an authenticated operator, ClusterOpsIssuesPanel auto-starts a remediation run from a useEffect whenever issues exist; ClusterPage always passes autoAssess. Its once-per-signature guard is a per-tab useRef, which resets on reload or in a new tab, and the signature changes whenever a row flips between degraded and fail. The client skips only while its own activeRemediationJob is running. platform-api HandleStart has no active-job or same-scope dedupe, and neither does the runner's POST /run. The HusbandryStrip path is covered by TD-208.
- **Measured**: CODE-READ only; no browser was opened. Matches the known Owner memory note 'Cluster page load dispatches repair agents'.
- **Evidence**:
  - `bifrost-platform/console/src/components/cluster/ClusterOpsIssuesPanel.tsx:339` — `autoAssessKeyRef.current = key`
  - `bifrost-platform/console/src/components/cluster/ClusterOpsIssuesPanel.tsx:340` — `onAutoCheck()`
  - `bifrost-platform/api/internal/remediation/handler.go:72` — `job, err := h.StartInternal(r.Context(), runReq)`
- **Impact**: Two tabs, or the Owner plus an agent session, start parallel full-auto agents with operator tokens against the same cluster issue. Cost and churn scale with page views, not incidents.
- **Fix**: Dedupe server-side: HandleStart returns 409 with the existing job id when a non-terminal job with the same scope exists, or one with the same issue signature finished within N minutes. Gate client auto-start explicitly on Dock Auto mode.
- **Ratchet**: Go test TestStartDedupsActiveScope (a second HandleStart with the same scope while the first is running returns 409 with the first job id). A Console vitest/grep bans mutating API calls inside useEffect without an allowlist comment.
- **验收**: `cd bifrost-platform/api && go test ./internal/remediation -run TestStartDedupsActiveScope -count=1`
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-platform

### TD-225

**P3 · ops-console · Read-only MCP bridges fail open: an unknown or misspelled MCP_BRIDGE_FOCUS registers all 74 tools, and PLATFORM_OPERATOR_TOKEN in env overrides the viewer-token pin**

- **状态**：未开始
- **Claim**: focusAllowList returns null for an unknown focus ('for backward compatibility'), and index.ts treats null as 'register everything', so a typo on a bridge documented as read-only L0 (redis, postgres) serves drain, data-clone and rollback. In platformClient.resolveToken, PLATFORM_OPERATOR_TOKEN from env wins before the PLATFORM_TOKEN_ENV_KEY viewer pin is consulted, and .mcp.json passes a PLATFORM_OPERATOR_TOKEN reference to the redis, postgres and prometheus bridges. Today the reference expands to empty in this shell, so the pin holds; the risk needs a focus typo plus an exported operator token.
- **Measured**: CODE-READ. Live: the configured bridges expose the expected sliced tool lists in this session. Only .mcp.json key names and the first two characters of values were read; PLATFORM_OPERATOR_TOKEN is unset in the session shell.
- **Evidence**:
  - `bifrost-platform/mcp/platform/src/focusBridges.ts:88` — `if (!list) return null`
  - `bifrost-platform/mcp/platform/src/index.ts:27` — `if (allow && !allow.has(String(args[0]))) return undefined`
  - `bifrost-platform/mcp/platform/src/platformClient.ts:42` — `process.env.PLATFORM_OPERATOR_TOKEN?.trim() || (pinnedKey ? '' : process.env.PLATFORM_ADMIN_TOKEN?.trim() || '')`
- **Impact**: One config typo silently turns a viewer bridge into a full operator/admin surface for any agent that loads it, with no error.
- **Fix**: An unknown focus prints an error and exits 1; the full surface only when MCP_BRIDGE_FOCUS is empty. When PLATFORM_TOKEN_ENV_KEY is set, read only that key. Drop PLATFORM_OPERATOR_TOKEN from the read-only bridges' env in .mcp.json.
- **Ratchet**: A vitest next to mcpStdioParity.test.ts: focusAllowList('postgress') throws, and every non-kubernetes focus list contains only catalog tools with level=read (runs once ci-platform runs vitest).
- **验收**: `cd bifrost-platform/console && npx vitest run src/lib/architecture/__tests__ -t 'focus bridge'`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform, bifrost-trade-infra

### TD-226

**P3 · ops-console · The release desk's Launch verdict says 'Clear to launch' and enables Agent Deploy when readiness probes failed or are still loading**

- **状态**：未开始
- **Claim**: The readiness helpers return 'unknown' when their fetch has no data (gate, socket, matrix or promote is null). Both blocking predicates treat only 'fail' and 'degraded' as blocking, so 'unknown' falls through to kind 'GO'. buildLaunchCheckpoints sets ok = !blocked, and the signal defaults to 'ok', so the checkpoints render green. TradeReleasePage enables deploy on GO, behind canOperate. Tests cover clear and blocked prod but not unknown.
- **Measured**: CODE-READ only; no browser was opened, because the Cluster page auto-dispatches.
- **Evidence**:
  - `bifrost-platform/console/src/lib/task-mode/satelliteLaunchVerdict.ts:81` — `return s === 'fail' || s === 'degraded'`
  - `bifrost-platform/console/src/components/task-mode/readiness/utils.ts:220` — `if (gate == null) return { signal: 'unknown', detail: 'probing' }`
  - `bifrost-platform/console/src/components/task-mode/readiness/hooks.ts:109` — `const promoteSignal: Signal = promote != null ? promoteVerifySignal(promote) : 'unknown'`
  - `bifrost-platform/console/src/pages/TradeReleasePage.tsx:408` — `const deployDispatchAllowed = !aiDeploy.disabled && satelliteVerdict.kind === 'GO'`
- **Impact**: An authenticated operator sees 'Clear to launch' with all checkpoints green while readiness is unmeasured, and can start a deploy agent on it. The release window and Owner per-action approval still apply downstream.
- **Fix**: signalBlocksLaunch and isProdReleaseBlocked return true for 'unknown'. Add a PROBING verdict that disables Launch with the reason 'readiness not measured'. A checkpoint is ok only when signal === 'ok'.
- **Ratchet**: vitest in satelliteLaunchVerdict.test.ts and researchLaunchVerdict.test.ts: each of rocket/tradeProd/promote = 'unknown' gives kind !== 'GO' and no ok:true checkpoint. This is part of the 'unknown is not green' suite in ratchet proposal 'console-and-frontend-vitest-in-ci'.
- **验收**: `cd bifrost-platform/console && npx vitest run src/lib/task-mode/__tests__/satelliteLaunchVerdict.test.ts -t unknown`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-227

**P3 · ops-console · The cockpit mission snapshot keeps a failing probe's last good verdict, under a 'Last probe' stamp that is the newest of seven queries**

- **状态**：未开始
- **Claim**: useMissionSnapshot builds the Control Room and FocusStrip verdict from seven useQuery results. It never reads isError, and TanStack v5 keeps data from the last success when a refetch fails. dataUpdatedAt is the max over all seven queries, so if one probe (matrix or cluster) keeps failing while others succeed, its stale verdict shows under a fresh stamp. A full platform-api outage is visible, because the stamp ages. 11 files use the hook.
- **Measured**: CODE-READ only (TanStack ^5.100.14; main.tsx sets retry:1).
- **Evidence**:
  - `bifrost-platform/console/src/hooks/useMissionSnapshot.ts:26` — `const matrixQ = useQuery({ queryKey: ['cockpit', 'matrix'], queryFn: () => fetchMatrix(), refetchInterval: REFETCH })`
  - `bifrost-platform/console/src/hooks/useMissionSnapshot.ts:51` — `const dataUpdatedAt = Math.max(`
  - `bifrost-platform/console/src/components/FocusStrip.tsx:277` — `{dataUpdatedAt > 0 ? 'Last probe ${formatAge(dataUpdatedAt)}' : 'Probing…'}`
- **Impact**: During a partial probe outage, the cockpit and the Launch verdict can show a stale green for the failing dimension with a fresh timestamp.
- **Fix**: Per query, when isError is set or dataUpdatedAt is older than 2× REFETCH, feed undefined ('unknown') into buildMissionSnapshot for that dimension. Report freshness as the minimum over queries, plus a list of stale sources.
- **Ratchet**: vitest with a mocked QueryClient: the matrix query fails after one success → snapshot.tradeProd.signal === 'unknown' and freshness reflects the stale query.
- **验收**: `cd bifrost-platform/console && npx vitest run src/hooks/__tests__ -t 'mission snapshot stale'`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-228

**P3 · ops-console · Every scheduled Hermes skill run on .52 fails with 'No such file or directory', while /health returns status ok and the checklist counts the gateway healthy**

- **状态**：未开始
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

### TD-229

**P3 · ops-platform · Trust overrides resolve to $HOME in the cluster and swallow read and write errors: the Owner's 09-07 L0 grant for research-loop-batch never reached the harness that reads PROD**

- **状态**：未开始
- **Claim**: In both cluster overlays, TrustOverrideStore resolves to $HOME/.bifrost-platform/governance, outside even the /app/data emptyDir, because PLATFORM_GOVERNANCE_DIR and PLATFORM_PROJECT_ROOT are unset. Put discards the os.WriteFile error, and List returns {} on a read error. The Owner's 2026-09-07 L0 for research-loop-batch exists only as a file in the shared checkout (bifrost-platform/agent/governance/trust_overrides.json). PROD and STG serve {} and L1, so research-harness records trust L1 every weekday. As of 00:57 UTC the local bdev platform-api also serves {}, although its PLATFORM_PROJECT_ROOT points at that file, so the read fails silently there too. The same silent read failure hides the local release_gate_state*.json (TD-230). TD-196's planned ratchet checks only PLATFORM_DATA_DIR paths and would miss this.
- **Measured**: MEASURED 2026-10-07 00:57 UTC: trust-overrides returns {} on local 127.0.0.1:8780, PROD 30876 and STG 30878; trust-matrix is L1 everywhere. The last research-harness Job logs 'research-loop-batch at Trust L1', trust_l0_override=false. The checkout file holds L0 dated 2026-09-07.
- **Evidence**:
  - `bifrost-platform/api/internal/agentgovernance/trust_override_store.go:31` — `dir = filepath.Join(os.Getenv("HOME"), ".bifrost-platform", "governance")`
  - `bifrost-platform/api/internal/agentgovernance/trust_override_store.go:70` — `_ = os.WriteFile(s.path, raw, 0o644)`
  - `bifrost-research/src/bifrost_research/copilot/harness/trust_gate.py:68` — `return matrix_level() == "L0"`
- **Impact**: An Owner autonomy decision never reached the process it governs, and because List and Put swallow errors, losing a grant (or a demotion) is invisible. All three instances now agree on L1, so the Console no longer shows a misleading L0.
- **Fix**: Move trust overrides into a ConfigMap store in the platform namespace (the internal/releases and internal/threadtitles pattern, alongside TD-196). Return 5xx on store read or write errors, and show which platform instance the Console is editing. The Owner then re-applies the intended level on PROD.
- **Ratchet**: Unit test: HandlePutTrustOverride returns non-2xx when the store write fails, and List surfaces read errors. Extend TD-196's store check to flag any store path derived from $HOME or os.UserHomeDir in non-test platform code (ratchet proposal 'platform-store-durability').
- **验收**: `curl -s -m10 http://192.168.10.73:30876/api/v1/agent/governance/trust-overrides; cd bifrost-platform/api && go test ./internal/agentgovernance -run 'TrustOverride.*(WriteFail|ReadFail)' -count=1  # PROD shows the override from a ConfigMap; store errors surface as 5xx`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform, bifrost-research

### TD-230

**P3 · ops-platform · The platform release gate passes when required checks are 'unknown', and its 'ready' never expires**

- **状态**：未开始
- **Claim**: RunReleaseGate fails only on ReachFail. Required checks that return ReachUnknown (spine milestone missing, smoke URLs unset, an empty probe matrix) produce result=pass, and narrativeBlockers does not treat Unknown as a blocker. responseFromRecord sets ready=true for any past pass with no age bound. checkProdMatrix fails when cfg is nil or prod is missing, but reports OK when the matrix has zero targets. The stale-ready display could not be reproduced on 10-07: the local instance serves no records although the state files exist (the same silent read as TD-229), and PROD's store is empty (TD-196).
- **Measured**: CODE-READ for unknown→pass. MEASURED 00:59 UTC: local GET release-gate answers 'No … release gate recorded yet' for all four tiers while bifrost-platform/data/release_gate_state*.json exists (newest prod record 08-31). The gate has not run for over a month; releases go through release.sh and Tekton.
- **Evidence**:
  - `bifrost-platform/api/internal/promote/service.go:102` — `if c.Reachability == probe.ReachFail {`
  - `bifrost-platform/api/internal/promote/service.go:332` — `check.Detail = "milestone 2c-b-prod-cutover not found in spine"`
  - `bifrost-platform/api/internal/promote/service.go:785` — `ready := rec.Result == "pass" && len(blockers) == 0`
- **Impact**: Promote surfaces (Console, MCP get_release_gate) can show a green 'ready' earned weeks ago, or earned with required checks never run. This is the same 'unknown passes' class as TD-94, on the platform side.
- **Fix**: Treat ReachUnknown on Required checks as not-pass ('inconclusive'). Make ready false when rec.At is older than a configurable window (for example 24 h), and say so in blockers. A zero-target matrix is Unknown, not OK.
- **Ratchet**: promote/service_test.go: a required Unknown check gives result not-pass, and a record older than the window gives ready=false.
- **验收**: `cd bifrost-platform/api && go test ./internal/promote -run 'RequiredUnknown|StaleRecord' -count=1 -v | grep -E '^(--- )?(PASS|FAIL)'`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-231

**P3 · ops-platform · Platform's IB feed verdict hangs on one hard-coded NVDA sample tick, and Trade namespaces and DB names are Go literals (53 matches), with no ratchet against growth**

- **状态**：未开始
- **Claim**: In live mode, platform's IB gateway verdict uses one hard-coded sample contract, ib:ingester:tick:NVDA|STK|||: a missing tick yields degraded, and a tick older than 180 s yields fail. Trade namespaces, DB names and daemon auto_status parsing are Go literals across ibgateway, cluster, satellite and others. IB-gateway health living in platform is sanctioned by the signed D-IB-Heal (authority api/internal/ibgateway), so the defect is the hard-coded contract and the literals, not the package's existence. Separately, 32 Console/MCP files outside the architecture catalog carry Trade vocabulary (SEPA, Greeks).
- **Measured**: MEASURED by grep on origin/main non-test Go under api/internal: 53 matches for NVDA|"ib:|ws_ib_|auto_status|"bifrost-(prod|stg|dev)". PROD /plugins/ib-gateway/status exposes sample_tick_nvda (fresh). 32 non-catalog Console/MCP files carry Trade vocabulary.
- **Evidence**:
  - `bifrost-platform/api/internal/ibgateway/service.go:78` — `tick, _ := s.redisGet("ib:ingester:tick:NVDA|STK|||")`
  - `bifrost-platform/api/internal/ibgateway/config.go:21` — `var tradeCutoverNamespaces = []string{"bifrost-dev", "bifrost-stg", "bifrost-prod"}`
  - `bifrost-platform/api/internal/satellite/service.go:385` — `AutoStatus:   mapFromAny(raw.Daemon.Trading["auto_status"]),`
- **Impact**: IB health turns wrong if NVDA leaves the subscription set, and Trade renames break platform verdicts silently. The 'clone platform elsewhere' test of Flywheel B fails on these literals.
- **Fix**: Let the IB plugin publish its own sample-contract or feed-quality verdict, or read the sample contract from config. Move the Trade namespace and DB lists into environments.yaml. Leave a broader plugin-owned health contract to the Ops-split program.
- **Ratchet**: code-health metric PLATFORM_TRADE_VOCAB (Go plus Console files outside architecture catalogs and prompt packs that match the vocabulary regex), baselined today and only allowed to fall, blocking in ci-platform.
- **验收**: `bash bifrost-trade-infra/agent-config/scripts/code-health/scan.sh --repo bifrost-platform | grep PLATFORM_TRADE_VOCAB  # ok and ≤ baseline; grep -c 'NVDA' bifrost-platform/api/internal/ibgateway/service.go  # 0`
- 审批 不用批 · 代价 L · 风险 med · repos: bifrost-platform, bifrost-platform-plugin

### TD-232

**P3 · frontend · 24 frontend sites take 'today' as the UTC date although four session helpers exist: from 20:00 ET until midnight they read tomorrow, and one writes a default opened_at**

- **状态**：未开始
- **Claim**: 24 inline `new Date().toISOString().slice(0,10)` sites take 'today' as the UTC date, although etTodayIso, chicagoTodayDateStr, todayIso and localDayStamp exist. From 20:00 ET (19:00 CDT) until midnight they read the next day: the Trade create form's default opened_at (POSTed as `${dateStr}T12:00:00.000Z`, but editable), event and corporate-action countdowns, the Review queue, habits and fit, Shares band yields, and the Alerts page. There are also 3 todayIso copies with different zones. FillsPage's `todayUtc` is intentionally UTC. This is the frontend half of the TD-98 class.
- **Measured**: Counted on origin/main dfb7858e: 24 sites outside tests against 4 helpers (77 helper call sites). PROD public.trade: 89 rows, all noon-UTC stamps, 0 dated after their NY creation day, so there is no stored damage yet. Per-site consequences are CODE-READ.
- **Evidence**:
  - `bifrost-trade-frontend/src/components/strategy/TradeCreateModal.tsx:48` — `return new Date().toISOString().slice(0, 10)`
  - `bifrost-trade-frontend/src/pages/trade/expiration/AssignmentSection.tsx:59` — `const [today] = useState(() => new Date().toISOString().slice(0, 10))`
  - `bifrost-trade-frontend/src/pages/research/events/EventsBookFace.tsx:110` — `const today = new Date().toISOString().slice(0, 10)`
  - `bifrost-trade-frontend/src/utils/localDayStamp.test.ts:11` — `// UTC would roll this to the 6th and stamp every leg stale after 7pm.`
- **Impact**: Every evening, countdowns, review queues and the default trade date read the wrong day, and one of them can be written to the Trade DB.
- **Fix**: Pick one session helper per meaning (etTodayIso for the session, chicagoTodayDateStr for the ledger day), collapse the 3 todayIso copies, and replace the sites. Name the zone in each, and make the useState-frozen ones re-evaluate at the NY day boundary.
- **Ratchet**: ESLint no-restricted-syntax on the zero-argument `new Date().toISOString().slice(...)` pattern, with inline-disable allowed only for sites that are UTC on purpose and say so in the variable name (todayUtc). The baseline is the allowlist count and may only fall. A fake-clock vitest at 23:30 ET asserts TradeCreateModal's default is still the same day.
- **验收**: `cd bifrost-trade-frontend && grep -rnE "new Date\(\)\.toISOString\(\)\.(slice\(0, ?10\)|split|substring)" src --include='*.ts' --include='*.tsx' | grep -v '\.test\.' | grep -v 'todayUtc' | wc -l  # 0`
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-trade-frontend

### TD-233

**P3 · frontend · fetchIvPercentileForSymbols turns every non-404 failure into 'no data', so IV Radar and the Watch book report a plugin outage as names without an IV rank**

- **状态**：未开始
- **Claim**: fetchIvPercentile maps a 404 to null (a real absence) and rethrows everything else. fetchIvPercentileForSymbols then catches every error (5xx, timeout, network; 'Treat hard errors as no data') and stores null. useIvRadarData counts it as noData with isError false, and useWatchBook renders the IV column as absent. The fan-out is one request per symbol every 120 s, although the same route returns the whole universe in one call.
- **Measured**: CODE-READ for the failure path; no failure was induced. The route answers 200 today with sane values (iv_current max 1.216 over 500 rows).
- **Evidence**:
  - `bifrost-trade-frontend/src/api/research/ivRadar.ts:91` — `return [sym, null] as const`
  - `bifrost-trade-frontend/src/api/research/ivRadar.ts:49` — `if (e instanceof HttpError && e.status === 404) return null`
  - `bifrost-trade-frontend/src/hooks/useIvRadarData.ts:74` — `else noData++`
- **Impact**: An outage reads as missing data, which is the class CLAUDE.md §5 forbids, and every refresh costs N requests where one would do.
- **Fix**: Return a tri-state per symbol ({row} | {absent} | {error}). Count errors separately and set isError when all fail; render 'read failed' in amber. Optionally read the bulk list once and join client-side.
- **Ratchet**: Unit test: a mocked 500 yields the error state, and a 404 yields absent. code-health metric: `catch {` blocks in src/api that return null or [] without checking HttpError status; the baseline may only fall.
- **验收**: `cd bifrost-trade-frontend && npx vitest run src/api/research/ivRadar.test.ts`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-234

**P3 · trade-worker · @bifrost/ui is unversioned for the Ops Console: a ui push never runs platform CI, and platform deliver builds whatever ui main is without recording its SHA**

- **状态**：未开始
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

### TD-235

**P3 · bifrost-ui · bifrost-ui's build starts with rm -rf dist (and prepare runs it on every npm install), white-screening both running dev servers until it finishes, or for good if tsc fails**

- **状态**：未开始
- **Claim**: Both consumers resolve @bifrost/ui to bifrost-ui/dist. The build script deletes dist before tsc, and prepare runs the build on any npm install in bifrost-ui. On the shared checkout, another session's install or build removes dist under the running :5173 trade-ui and :5180 platform-console; if tsc then fails, dist stays missing. This is a known memory pitfall with no guard.
- **Measured**: CODE-READ only; no build was run (shared checkout, live dev servers).
- **Evidence**:
  - `bifrost-ui/package.json:8` — `"build": "rm -rf dist && tsc -p tsconfig.build.json && mkdir -p dist/styles`
  - `bifrost-ui/package.json:11` — `"prepare": "npm run build"`
  - `bifrost-trade-frontend/vite.config.ts:188` — `{ find: '@bifrost/ui', replacement: resolve(uiRoot, 'dist/index.js') },`
- **Impact**: Local DEV acceptance (D-IL1 on :5173) and the Ops Console dev server break for every session at once.
- **Fix**: Build into dist.tmp (tsc --outDir dist.tmp, copy styles) and swap it in with an atomic mv only on success. Alternatively drop rm -rf and keep a separate clean script.
- **Ratchet**: A line in bifrost-ui's lint or code-health scan that fails if the build script contains 'rm -rf dist &&' before the compile step.
- **验收**: `git -C bifrost-ui show origin/main:package.json | grep -c 'rm -rf dist &&'  # 0`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-ui

### TD-236

**P3 · trade-worker · Leftovers of the deleted Account Sync daemon: the plugin still XADDs every account snapshot to ib:account:stream:v1, which nothing reads**

- **状态**：未开始
- **Claim**: TD-22 deleted the Account Sync daemon, the only consumer of ib:account:stream:v1. The IB Gateway plugin still XADDs the full snapshot (all accounts, summaries, positions) to that stream on every snapshot write, capped at about 1000 entries on redis-ib. Core still defines the key and a health-key comment describing the retired consumer, and the Console architecture catalog lists the stream as live. The key is also pinned in core and plugin tests/contracts/redis_ib_keys.json (and core test_redis_ib_contract.py:75-76), so removing it means updating both contract files together.
- **Measured**: CODE-READ. `git grep` over origin/main of core, api, worker, platform, research, frontend, infra and the market-data and flex plugins finds no XREAD or consumer. redis-ib memory was not measured.
- **Evidence**:
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/writer.py:91` — `self._rds.xadd(`
  - `bifrost-trade-core/src/bifrost_core/core/realtime/ib_account_keys.py:28` — `IB_ACCOUNT_STREAM_KEY = "ib:account:stream:v1"`
  - `bifrost-trade-core/src/bifrost_core/core/redis_health_keys.py:41` — `# Account Sync Daemon: independent process that consumes ib:account:stream:v1 and`
  - `bifrost-platform/console/src/lib/architecture/dualFlywheelVisionCatalog.ts:313` — `keys: 'ib:account:stream:v1, ib:account:{id}',`
- **Impact**: Up to 1000 full copies of the account book sit in redis-ib for no reader, and the architecture page documents a data path that does not exist.
- **Fix**: Remove the XADD and the stream constants from the plugin, the key and comment from core, and the stream from the Console catalog, updating both redis_ib_keys.json contracts together. DEL the key once on redis-ib (Owner).
- **Ratchet**: Extend the existing redis_ib_keys.json contract with a consumer field per key; a written key with no named consumer fails (ratchet proposal 'redis-ib-snapshot-contract').
- **验收**: `git -C bifrost-platform-plugin grep -c 'IB_ACCOUNT_STREAM_KEY' origin/main -- src  # 0`
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-platform-plugin, bifrost-trade-core, bifrost-platform

### TD-237

**P3 · data · The data-warehouse 'second MinIO' never ran (PVC Pending 109 days, Deployment 0/0), yet AGENT_FACTS lists it, and its placeholder root Secret is committed to a PUBLIC repo and applied**

- **状态**：未开始
- **Claim**: k8s/compute/warehouse/minio.yaml commits a kind: Secret with a literal placeholder MINIO_ROOT_PASSWORD. It is the only committed Secret manifest under k8s outside the examples, and it was applied as-is. PVC data-warehouse/minio-data has been Pending since creation (gpu-server NotReady,SchedulingDisabled) and deploy/minio is 0/0, so the store never held data. AGENT_FACTS still says it serves Research and Golden Source objects. The data namespace also carries an unmanaged Service np-redis-fresh with no endpoints for 98 days, and two Released test-nfs-hot PVs. TD-133 covers only the in-cluster MinIO leftovers in data.
- **Measured**: MEASURED 2026-10-07: PVC Pending at 109d; deploy 0/0; secret minio-root carries last-applied-configuration and was created 2026-06-19T09:13:12Z together with deploy/minio; svc data/np-redis-fresh has no endpoints and no source in any repo; two test-nfs-hot PVs are Released. The live secret value was not read.
- **Evidence**:
  - `bifrost-trade-infra/k8s/compute/warehouse/minio.yaml:4` — `kind: Secret`
  - `bifrost-trade-infra/k8s/compute/warehouse/minio.yaml:11` — `MINIO_ROOT_PASSWORD:`
  - `bifrost-trade-infra/agent-config/AGENT_FACTS.md:396` — `第二个 MinIO @ 'data-warehouse'（gpu-server）供 Research / Golden Source 对象。`
- **Impact**: Agents and the Owner reason from a data location that does not exist. If gpu-server comes back, a MinIO would start with a root password published on GitHub.
- **Fix**: Either delete the data-warehouse objects and the k8s/compute/warehouse manifests (an Owner delete), or replace the committed Secret with a .example plus a .gitignore entry and generate the password out of band. Fix the AGENT_FACTS line. Delete np-redis-fresh and the two Released test PVs.
- **Ratchet**: CI check in infra: `git grep -l '^kind: Secret' -- k8s ':!*.example.yaml' ':!*.example'` must be empty. A gitleaks step covers the broader committed-secret class (ratchet proposal 'secret-scan').
- **验收**: `cd bifrost-trade-infra && git grep -l '^kind: Secret' origin/main -- k8s ':!*.example.yaml' ':!*.example'  # no output; KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl get pvc -A </dev/null | grep -c Pending  # 0`
- 审批 删除（要你批） · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-238

**P3 · data · The three per-env Redis instances run --appendonly yes with no volume, and with noeviction but no maxmemory the only memory bound is an OOMKill**

- **状态**：未开始
- **Claim**: instances.yaml starts redis-live-prod, redis-live-stg and redis-dev with --appendonly yes and --maxmemory-policy noeviction, with no volumes and no --maxmemory. AOF and RDB go to the container's writable layer and vanish on any pod recreate, while about 29 MB of AOF is written for 3 keys. With maxmemory 0, noeviction never applies, so a runaway writer is OOM-killed at the limit instead of getting write errors.
- **Measured**: MEASURED 2026-10-07 via read-only INFO on PROD: aof_enabled 1, aof_current_size 29728464, maxmemory 0, policy noeviction, DBSIZE 3, used_memory 1.59M. The Deployments have no volumes.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/redis/instances.yaml:116` — `- --appendonly`
  - `bifrost-trade-infra/k8s/data/redis/instances.yaml:120` — `- --maxmemory-policy`
- **Impact**: Low today (TTL'd IPC), but the config reads as durable, and anyone who adds real state would lose it on the next reschedule.
- **Fix**: Declare the live Redis instances ephemeral: drop --appendonly, set --save "", and set --maxmemory a little below the container limit. Or add a PVC if persistence is really wanted.
- **Ratchet**: Infra manifest policy check: fail on a redis-server command with '--appendonly yes' but no volumeMount at /data, or '--maxmemory-policy noeviction' without '--maxmemory'.
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec deploy/redis-live-prod -c redis </dev/null -- redis-cli CONFIG GET appendonly maxmemory  # appendonly no and maxmemory > 0`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-239

**P3 · trade-worker · Up to about 40 runtime exports of @bifrost/ui have no importer in either consumer (ContextMenu family, KpiStrip, holidayLine, shellNav* constants); dead-code share unmeasured**

- **状态**：未开始
- **Claim**: Of 283 names re-exported from src/index.ts, 85 have no textual hit in either consumer's src, about 45 of them Props types. Of the remaining runtime exports, some (useMorph and composeRefs, used in 5 internal files) are live inside bifrost-ui and only need not be public. Others (KpiStrip, the ContextMenu wrappers, holidayLine) may be fully unused. No tool measures unused exports.
- **Measured**: MEASURED by script on origin/main: 85 of 283 names have no consumer hit. A spot check of 7 names confirmed 0 consumer hits; useMorph and composeRefs are used internally. Internal use was not subtracted overall.
- **Evidence**:
  - `bifrost-ui/src/data-display/Kpi.tsx:62` — `export function KpiStrip({ children, inset = false, state, className }: KpiStripProps) {`
  - `bifrost-ui/src/index.ts:1` — `297 lines of re-exports; 14 ContextMenu entries`
- **Impact**: Low: extra public surface that every DS default change must keep compatible, and noise in design-sync inventories.
- **Fix**: Run knip (or ts-prune) over bifrost-ui with both consumers as entry points. Drop exports with no user, and mark the ones kept on purpose for Design.
- **Ratchet**: code-health metric UI_UNUSED_EXPORTS in scan.sh with a baseline in baselines.env, run by a CI job that actually scans --repo bifrost-ui (none does today).
- **验收**: `bash /Users/vision-mac-trader/Desktop/stocks/scripts/code-health/scan.sh --repo bifrost-ui | grep UI_UNUSED_EXPORTS  # value ≤ baseline`
- 审批 改公开接口 · 代价 S · 风险 low · repos: bifrost-ui, bifrost-trade-infra

### TD-240

**P3 · trade-worker · The running PROD daemon never writes contract_quote_live: the observe-only quote mirror sits under mock_hedging, which is hard-coded True**

- **状态**：未开始
- **Claim**: Both contract_quote_live write sites in the heartbeat are inside `if not getattr(app, "mock_hedging", True)`, and GsTrading sets mock_hedging = True in __init__ and _reload_config as the D10 hedging guard. The PROD daemon runs (2/2), so the Redis→raw_broker.contract_quote_live mirror, which is observe-only, never runs; _on_ticker / _on_ticker_for_contract_key have no caller. Closed TD-140 recorded the cause as 'the daemon does not run'; its fix (vendor EOD fallback, core 0.51.0) routes around the table.
- **Measured**: MEASURED 2026-10-07 00:45 UTC: bifrost-prod deploy/daemon 2/2; raw_broker.contract_quote_live 13 rows, max(updated_at) 2026-03-28 06:16; no caller of _on_ticker* in worker src/tests.
- **Evidence**:
  - `bifrost-trade-worker/src/bifrost_worker/daemon/app/control_heartbeat.py:259` — `if not getattr(app, "mock_hedging", True):`
  - `bifrost-trade-worker/src/bifrost_worker/daemon/app/gs_trading.py:85` — `self.mock_hedging = True`
- **Impact**: Attribution and Positions have no intraday price; the closed item recorded the wrong cause, so the fallback looked like the only option.
- **Fix**: Owner decides: (A) give the observe-only STK quote mirror its own flag (daemon.quote_mirror) outside mock_hedging, no order path; or (B) delete the mirror, the _on_ticker* callbacks and the write path. Do not keep a write path that can never run.
- **Ratchet**: (A) worker test: with mock_hedging=True and quotes in Redis, one heartbeat writes contract_quote_live. (B) a dead-symbol check (vulture baseline) failing on _on_ticker*.
- **验收**: `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_prod -X -At -c "select max(updated_at) from raw_broker.contract_quote_live" </dev/null  # (A) within the last trading session; (B) table and code gone`
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-trade-worker

### TD-241

**P3 · agent-governance · RATCHETS.md, TECH_DEBT.md and agent docs state facts the round-3 scan measured as no longer true**

- **状态**：未开始
- **Claim**: (1) RATCHETS: BifrostAPIHighErrorRate says it matches only namespace=~"bifrost-.*"; bifrost-alerting-rules.yaml:49 now matches "bifrost-.*|research|plugin-.*". (2) RATCHETS: the TD-161 row names research/market-data test_http_metrics.py under tests/; the real path is tests/api/test_http_metrics.py (only flex-query uses tests/). (3) RATCHETS: the ci-python row says trade-api main has been CI-red since 10-04; ci-python-bifrost-trade-api-5jndn (10-06 18:56Z) is Completed (green). (4) RATCHETS: the FE eslint row says 0 error / 65 warning; measured now: 0 error / 1 warning. (5) RATCHETS: DoctorPanel.computing (TD-165) and slotScheduler (TD-108) are registered as warning (in CI), but ci-platform runs no Console vitest, so they are manual. (6) RATCHETS: the FE husky pre-commit is registered as blocking but was bypassed: origin/main dfb7858e pushed frontend duplicated-function-names to 1/0 (four `pct` definitions with four unit conventions), and scan.sh exits 1 on clean and shared trees. (7) RATCHETS: OVERSIZED_UI_BASELINE has a baseline, but no CI job runs code-health --repo bifrost-ui. (8) TECH_DEBT TD-140: the stated cause ('only the frozen daemon writes contract_quote_live') is wrong; the daemon runs, and the mirror is gated off by mock_hedging (see merged_into_existing). (9) TECH_DEBT TD-196: its acceptance checks only survival across a rollout, not api→workers visibility, and the data-clone store caches its file at construction. (10) Docs: CLAUDE.md §3 and agentProtocolCatalog FORBIDDEN_ACTIONS say only the daemon writes ib:operator:cmd, which contradicts the signed D-IB-Heal (TD-221). AGENT_FACTS §8c omits NodePorts 30379/30380/30382/30432 (TD-205) and lists a data-warehouse MinIO that never ran (TD-237). Worker CLAUDE.md:62 claims open orders and TWS fills are persisted (TD-211).
- **Measured**: MEASURED by the round-3 ratchet-inventory agent (2026-10-07); not adversarially re-verified.
- **Evidence**:
  - `bifrost-trade-infra/agent-config/RATCHETS.md` — `rows named in the claim`
- **Impact**: The registry overstates what is enforced (a pre-commit hook registered as blocking was bypassed; Console vitest guards registered as CI warnings run nowhere) and the docs mislead agents about who writes ib:operator:cmd.
- **Fix**: Correct each row in RATCHETS.md; downgrade the Console vitest rows to manual until ci-platform runs vitest; fix CLAUDE.md §3 / agentProtocolCatalog FORBIDDEN_ACTIONS to name D-IB-Heal (Owner rule text); add the missing NodePorts to AGENT_FACTS §8c and drop the data-warehouse MinIO.
- **Ratchet**: None practical for prose; the render script could flag RATCHETS rows whose file path does not exist on origin/main.
- **验收**: `Re-run the ratchet-inventory prompt from round 3 against origin/main: stale_registry is empty.`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-242

**P2 · market-data · market-data /ingest/queue-dashboard takes 5–25 s per call, and the platform-api proxy carries the same delay: with the new latency rule live it will page whenever someone keeps the queue dashboard open**

- **状态**：未开始
- **Claim**: 164 requests over 1 s in 90 minutes on plugin-market-data; PROD platform-api p99 2.5–7.4 s from /api/v1/plugins/market-data/api/*.
- **Measured**: MEASURED 10-07 by paydown lane CC (Prometheus, the TD-161 / TD-195 metrics).
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/ingest_dashboard.py:891` — `def build_queue_dashboard(`
- **Impact**: A slow Console page, and (after TD-194) a real-but-noisy latency alert about every 90 minutes of dashboard use.
- **Fix**: Cache the dashboard per minute (it is a derived read), or make its job_ingest / queue_sample reads cheap (EXPLAIN first; see memory plan-follows-anchor-estimate).
- **Ratchet**: A test or check that the dashboard's p99 stays under the latency rule threshold on PROD-sized data (or a cache hit test).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-243

**P3 · frontend · 42 frontend modules are unreachable from src/main.tsx (largest clusters: components/cockpit/ 8, utils/dataOverview/ 6); dead code invites fixes and false audit findings**

- **状态**：未开始
- **Claim**: TD-199's orphan-module ratchet lists them in KNOWN_ORPHANS; each is imported by nothing reachable from the app entry.
- **Measured**: MEASURED 10-07 by paydown lane EE (import-graph walk from src/main.tsx).
- **Evidence**:
  - `bifrost-trade-frontend/src/lib/orphanModules.test.ts:9` — `* KNOWN_ORPHANS is the 2026-10-07 baseline (42). It may only shrink:`
- **Impact**: Dead pages and helpers get fixed, audited and reported as bugs (TD-193 was one).
- **Fix**: Owner reviews in batches by directory (deletion is the Owner's call, §15); delete and drop each from KNOWN_ORPHANS.
- **Ratchet**: orphanModules.test.ts already fails on any new orphan and forces the list to shrink.
- 审批 删除（要你批） · 代价 S · 风险 low · repos: bifrost-trade-frontend

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
