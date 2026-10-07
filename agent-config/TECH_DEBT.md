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

- **TD-236** — 已删除的 Account Sync daemon 的残留清掉：插件不再写 ib:account:stream:v1，core / Console / 两份 redis_ib_keys.json 去掉该流，旧键已删（ib-gateway 0.4.0 + Owner DEL，10-07） · 验收 PASS（键不存在且未重建、快照正常） · 防线：插件 `tests/test_redis_key_manifest.py`（键清单与 core 一致） · 后续：无
- **TD-96** — preflight 的 D10 闸门不再只认 curl：Python/wget/httpie/node 写 /control/*、patch 扩容 daemon、各种方式改闸门文件都会被拦（Owner 应用，infra 560e58c） · 验收 PASS（agent-guard test.js 74/74） · 防线：`agent-config/scripts/agent-guard/test.js`（74 例，含 28 条不得误拦） · 后续：test.js 不在 infra CI 里（只在改闸门时手跑）
- **TD-148 / TD-160 / TD-107** — strategy_plan 允许 lens / backtest_run 来源；删 GS 两个改名残留的重复索引；6 张 financials 表补上 (period_date, symbol) 索引（Owner 10-07 批第一组，均已执行并核对） · 验收 PASS（三库约束含新值、旧索引已删、6 个新索引 valid） · 防线：core `tests/test_td148_source_kind_prepare.py`、research TD-160 核对 SQL、market-data `tests/test_td107_financials_period_index.py`（apply_ddl 路径建索引） · 后续：TD-134 观察一周 WAL 量（同批 apply，到 10-14）
- **TD-204** — platform 不再以集群管理员身份运行：STG/PROD 改用按需授权的 ServiceAccount（STG 只读、PROD 只有维护所需的几项），管理员 kubeconfig Secret 已删，读 Pod 日志要令牌。验收 PASS 2026-10-07（Secret NotFound、读不到 data 的 Secret、匿名读日志 401、权限检查 82/82、切换后无 forbidden）。防线：`RATCHETS.md`「check_platform_rbac.py」。后续：TD-256（STG 两个插件新鲜度探测靠主库 exec，现在不可用）、TD-257（管理员客户端证书是否轮换，要你定）
- **TD-223** — IB Gateway 自动修复只留 PROD 一份：STG 的 platform-workers 与 platform-api 关掉（infra 7b82568），STG 也不再重复写发布记录。验收 PASS 2026-10-07（STG `auto_repair_enabled` false、PROD true）。防线：无可行的机械防线——overlay 值由 Owner 原则「STG 只观测、PROD 维护」约束，写进了 overlay 注释。后续：无后续：Ops 维护收敛计划其余步骤在 TD-130
- **TD-253** — 检查信号不再是几周前的：每条带观测时间和来源，超过 2 小时读 unknown、autopilot 不会按它动手；PROD platform-workers 自己每 10 分钟探测一次（不再靠 Mac 上报）。验收 PASS 2026-10-07 d8bdf41（22/22 带时间）。防线：`RATCHETS.md`「检查信号的时效与来源」测试 + `check_platform_maintenance.py`（探测器只在 PROD workers）。后续：无后续：放开 autopilot 动手在 TD-130（观察到 10-12）
- **TD-254** — 备份只归 CNPG 每日备份 + backup-retry：autopilot 遇到备份不新鲜只报告、不再调 repair_cnpg_wal_store（不再删失败的 Backup、不再盘中补全量备份；工具留给人手动用）。验收 PASS 2026-10-07 dc1488e。防线：`RATCHETS.md`「autopilot 备份不动手测试」。后续：无后续：剩下的收敛在 TD-130（观察到 10-12）
- **TD-255** — 漂移扫描不再删失败现场：只删被驱逐的 Pod，失败的备份 Job Pod 留着（日志可读），只报告模式下一个不删。验收 PASS 2026-10-07 dc1488e。防线：`RATCHETS.md`「漂移扫描只删 Evicted 测试」。后续：无后续：Job 历史上限与 TTL 负责回收
- **TD-214 / TD-219 / TD-232 / TD-233** — 前端「今天」统一按纽约交易日、区间按芝加哥日界、告警「今天触发」按 computed_at、IV 读失败不再显示为没数据（frontend 119726cc，已上三环境）· 验收 PASS（10-07，各自 vitest + grep 0）· 防线：eslint no-restricted-syntax + `utcTodayRatchet.test.ts`、`performanceUtils.test.ts`、`useFiredAlerts.test.ts`、`ivRadar.test.ts` · 后续：TD-247（回看起点与三份纽约日期副本）

**未结 78 项**：P0 0 · P1 7 · P2 28 · P3 43；要你批的 38 项（从总览表的审批列算）。

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

## 还债顺序

### 第 0 波 · 第 1 轮收尾

目标：第 1 轮剩下的三项按已排的日期收掉。TD-85 剩 Golden Source 的 PUBLIC CONNECT；TD-51 等 Loki 闸门后随下一次 Trade 发布；TD-80 C2-b 改号 core 0.49.0 与 TD-51 同发。

项：TD-85 · 已还：TD-21, TD-51, TD-80

### 第 1 波 · 正在出错的数据与「绿着的失败」

目标：先让失败变红。错数据先修数据（TD-87 restate），再把引擎、闸门、写入方从「出错也报成功」改成失败即失败：引擎资产按输出判定、husbandry gate 失败即关、日历读失败报错、写入方失败抛错。不需要 Owner 批的先做。

项：TD-91, TD-92, TD-94, TD-97, TD-101, TD-136, TD-156, TD-157, TD-166, TD-189, TD-192, TD-244 · 已还：TD-88, TD-89, TD-90, TD-113, TD-93, TD-165, TD-167, TD-87, TD-245

### 第 2 波 · 让闸门真的卡住

目标：一个开关让所有测试类防线生效（CI 卡发布），再补上调度存活告警、D10 闸门的非 curl 写法、operator 流白名单、本机常驻任务和密钥轮换的盲区、spine 副本同步。

项：TD-95, TD-96, TD-100, TD-121, TD-152, TD-153, TD-155, TD-162 · 已还：TD-99, TD-161, TD-198, TD-195, TD-194, TD-249, TD-109, TD-105

### 第 3 波 · 交易日与日历只有一个来源

目标：所有「今天 / 本 session」都从 `db/calendar` 的一个函数来，代替 11 个私有 helper 和 44 处 `date.today()`；dbt 补 grain 测试；IV / 回测的定价参数统一。

项：TD-98, TD-110, TD-111, TD-112, TD-128, TD-129, TD-174, TD-242 · 已还：TD-164, TD-175, TD-247

### 第 4 波 · 券商资金账本（Flex / IB）

目标：现金与佣金账本可信：按 IB transactionID 去重（改表）、佣金一种符号、资金路径有测试、Flex 不再经 DEV 库读配置、IB Gateway 健康与镜像可追溯。

项：TD-103, TD-104, TD-117 · 已还：TD-115, TD-116, TD-114, TD-122

### 第 5 波 · 副本、死重与清单

目标：删掉没人用的（挂起的 CronJob、退役脚本、无调用路由），手抄的副本改成从一处生成（调度名单、max-pain / PCR），清单的应用顺序与 Argo 归属理顺。

项：TD-107, TD-118, TD-120, TD-160, TD-170, TD-202 · 已还：TD-126, TD-108, TD-154, TD-163, TD-168, TD-124, TD-176, TD-191, TD-169, TD-200, TD-201, TD-190, TD-123, TD-106, TD-119, TD-125, TD-102

### 第 6 波 · 备份链与自动修复（10-06 日常发现）

目标：备份 MinIO 已搬到 NAS（infra 1ee0ac2，已接监控 ba03488），把剩下的收尾：自动修复只在 PROD 一处动手、失败记录不再被删、platform 的新检查上线、稳定一周后退役集群里的 MinIO 残留，再处理 WAL 体量和 CNPG 1.30 的备份插件。

项：TD-133, TD-134, TD-135 · 已还：TD-197, TD-173, TD-132, TD-131

### 第 7 波 · 数据缺口（10-06 由 Data Gaps 看板并入）

目标：Data Gaps 看板上未结的 15 项并入台账：先把每日快照的写入修对（TD-137）再接读侧和三页，归因行补上价格，Research 侧已就绪的一个版本（0.185.0）发出去，长期限 IV 锥在 10-31 前从 option_daily 回填，其余按 Owner 已定的口径排。

项：TD-137, TD-142, TD-143, TD-144, TD-145, TD-146, TD-148, TD-149, TD-150, TD-158, TD-159, TD-172, TD-180, TD-246, TD-250 · 已还：TD-141, TD-147, TD-177, TD-179, TD-151, TD-181, TD-193, TD-140, TD-171, TD-138, TD-139, TD-178, TD-199, TD-243, TD-182

### 第 8 波 · Pine 线程收尾后的跟进（10-06）

目标：Pine 与路线图那条线（会话「Pine 信号业务与实现」）收尾时留下的日后核对：W3 两次真正的归档、一个只差发布的前端修复、路线图台账的月度重评、「我的价位」等 Design、auto mode 规则重新应用。

项：TD-183, TD-184, TD-185, TD-186, TD-188 · 已还：TD-187

### 第 9 波 · 控制面对局域网敞开（第 3 轮，10-07）

目标：先关门再修代码。本机 platform-api 只监听本机、PROD/STG Redis 的局域网 NodePort 删掉，然后 git-bridge、修复 runner、Hermes、husbandry-sync 都要令牌；platform 换成按需授权的 ServiceAccount，停用管理员 kubeconfig；路由鉴权测试卡住回退。

项：TD-208 · 已还：TD-205, TD-203, TD-224, TD-220, TD-231, TD-225, TD-222, TD-207, TD-221, TD-206

### 第 10 波 · 告警有人收、备份能恢复（第 3 轮）

目标：数据层告警有一个人能收到的通道和外部心跳；逻辑备份先修好等库就绪；做一次 Barman 恢复演练；决定异地副本；daemon 停写与日志丢失要能被看见。

项：TD-210, TD-217, TD-218, TD-237 · 已还：TD-248, TD-209, TD-215, TD-216, TD-238

### 第 11 波 · 账本与页面读数、绿着的未知（第 3 轮）

目标：挂单与 IB 读失败不再被当真写库；Risk / Performance / 告警计数按交易日算；Console 的裁决条在探针失败时不再显示绿色；ui 的发布可追溯；台账与文档的过时说法改正。

项：TD-228, TD-234, TD-236, TD-240 · 已还：TD-214, TD-219, TD-232, TD-233, TD-226, TD-230, TD-227, TD-251, TD-235, TD-252, TD-229, TD-241, TD-213, TD-239, TD-211, TD-212

### 第 12 波 · Ops 维护只在 PROD 一处（Owner 10-07）

目标：会动手的维护只由 PROD 的 platform-workers 做，本机与 STG 只观测。已做：本机停手（TD-130 第一步）、STG 不修 IB 也不写发布记录（TD-223）、页面不再触发维护、状态持久化（TD-196）。接着：PROD 自己探测、带时间戳的检查信号，只给 PROD 挂技能并先只报告，再逐项放开；备份只归 CNPG 与 backup-retry；不再清掉失败现场。

项：TD-130, TD-196, TD-223, TD-204, TD-253, TD-254, TD-255, TD-256 · 已还：TD-257

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
| [TD-103](#td-103) | P2 | flex-ib | The cash parser never stores IB's transactionID, so dedupe falls back to (account, day, amount, type, report_date) and same-amount items overwrite each other | 改表 |
| [TD-104](#td-104) | P2 | flex-ib | Trade Ops reports all three IB Gateway services 'offline' on PROD: the gateway's health hashes have no updated_at, and the service rows point at retired StatefulSets | 跨仓库发版 |
| [TD-107](#td-107) | P2 | market-data | Indexes declared for the six financials entity tables never reach a deployed DB (the migration returns early); live differs from fresh install | 改表 |
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
| [TD-136](#td-136) | P2 | research-data | GEX writes levels for an expiry whose open interest is all zero: walls and zero_gamma fall on an arbitrary strike, 1,534 rows on 496 names, and terrain and scan copy them | 已批（观察中） |
| [TD-137](#td-137) | P1 | trade-data | The daily snapshot capture locks an account's intraday book into the day (first write wins, no freshness test) and account_nav_daily stores no margin-pressure fields | 改表 + 发布（要你批） |
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
| [TD-180](#td-180) | P3 | research-data | The macro calendar has no CPI dates after 2026-12-10 and no payrolls at all: bls.gov answers 403 from this host, so they could not be read | 不用批 |
| [TD-183](#td-183) | P3 | market-data | W3 archive-before-delete has never archived for real: the first intraday option_snapshot archive is ~10-08 02:15 UTC and option_daily / short_volume on 11-01 | 不用批 |
| [TD-184](#td-184) | P3 | frontend | The Simulator says "stored with the run" for runs that were not stored: the fix (fe 53d6939e) is on main but not in STG/PROD | 发布（要你批） |
| [TD-185](#td-185) | P3 | research-control | The Pine-vs-TradingView roadmap ledger is a point-in-time judgement: its scores and next steps need a re-evaluation around 11-06 | 不用批 |
| [TD-186](#td-186) | P3 | frontend | "My levels" (plan stop / target and price alerts as horizontal lines) on the Symbol chart waits on Design: ASK-symbol-chart-my-levels-2026-10-06 | 要你批 |
| [TD-188](#td-188) | P3 | frontend | The app's design registry is still at Rev .157: packages .158–.162 are built but designRoutes / adoption were not re-synced (the Design project's DS mirror was synced to 0.13.0 on 10-06) | 不用批 |
| [TD-189](#td-189) | P3 | research-data | SEPA has no rows for four sessions (08-28, 08-31, 09-08, 09-16): those nights never computed it, so the SEPA lens and its hit rate skip them | 不用批 |
| [TD-192](#td-192) | P2 | research-control | One IB Flex failure loses that night's SEPA for good: husbandry_gate blocks sepa_projection although SEPA reads nothing from Flex, and the projection never back-fills a missed night | 要你批 |
| [TD-196](#td-196) | P2 | ops-platform | platform-api and platform-workers keep their state in per-pod emptyDir: every rollout erases release cycles, gate history, the operate queue and checklist signals, and the audit log is memory-only | 已批 |
| [TD-202](#td-202) | P3 | market-data | market-data code strings and scripts still mention CronJobs: the dashboard label 'CronJob archived' and verify-market-data.sh's hint are user-visible | 不用批 |
| [TD-204](#td-204) | P1 | ops-platform | STG and PROD platform-api and platform-workers run as system:masters through a copy of the k3s admin kubeconfig, and anonymous GETs use it to read pod logs in any namespace | 安全/凭据（要你批） |
| [TD-208](#td-208) | P1 | ops-platform | Anonymous POST /checklist/husbandry-sync starts full-auto remediation agents: it merges the stored checklist and dispatches every failing item, and three Console pages call it on load | 安全/凭据（要你批） |
| [TD-210](#td-210) | P1 | data | The nightly logical backup of hand-entered data failed on its first scheduled run: it connects before the new pod's NetworkPolicy is programmed and gets Connection refused | 不用批 |
| [TD-217](#td-217) | P2 | data | The Barman base+WAL backup, the only copy of the 34 GB Golden Source history, has never been restored, and has not been tried at all against the NAS MinIO it moved to on 10-06 | PROD 变更（要你批） |
| [TD-218](#td-218) | P2 | data | Every backup copy (Barman base+WAL, logical dumps hot and cold, the W3 archive) is on the one NAS 192.168.10.20:/volume1, and the open offsite decision is not in the ledger | PROD 变更（要你批） |
| [TD-223](#td-223) | P3 | ops-platform | STG and PROD platform-workers both run the IB gateway auto-repair loop against the one live data/ib-gateway, each with its own 15-minute cooldown | PROD 变更（要你批） |
| [TD-228](#td-228) | P3 | ops-console | Every scheduled Hermes skill run on .52 fails with 'No such file or directory', while /health returns status ok and the checklist counts the gateway healthy | 不用批 |
| [TD-234](#td-234) | P3 | trade-worker | @bifrost/ui is unversioned for the Ops Console: a ui push never runs platform CI, and platform deliver builds whatever ui main is without recording its SHA | 不用批 |
| [TD-236](#td-236) | P3 | trade-worker | Leftovers of the deleted Account Sync daemon: the plugin still XADDs every account snapshot to ib:account:stream:v1, which nothing reads | 跨仓库发版 |
| [TD-237](#td-237) | P3 | data | The data-warehouse 'second MinIO' never ran (PVC Pending 109 days, Deployment 0/0), yet AGENT_FACTS lists it, and its placeholder root Secret is committed to a PUBLIC repo and applied | 删除（要你批） |
| [TD-240](#td-240) | P3 | trade-worker | The running PROD daemon never writes contract_quote_live: the observe-only quote mirror sits under mock_hedging, which is hard-coded True | 跨仓库发版 |
| [TD-242](#td-242) | P2 | market-data | market-data /ingest/queue-dashboard takes 5–25 s per call, and the platform-api proxy carries the same delay: with the new latency rule live it will page whenever someone keeps the queue dashboard open | 不用批 |
| [TD-244](#td-244) | P3 | research-control | agents/journal_distill reads raw_broker.executions_final with no Flex freshness check (own 23:55 UTC schedule, outside any gate) | 不用批 |
| [TD-246](#td-246) | P3 | trade-data | Snapshot enrich stores a vendor 'day close' that can sit below the option's intrinsic value (a stale last trade), and P&L attribution then books it as unexplained | 已批（Owner 10-07「做」） |
| [TD-250](#td-250) | P3 | trade-data | A stale vendor close above intrinsic is still stored as vendor_eod: the plugin's snapshot read does not return last_trade_ts, so enrich cannot tell a morning trade from a session close | 不用批 |
| [TD-253](#td-253) | P2 | ops-platform | The autopilot acts on checklist signals that are weeks old: signals carry no time of their own, and nothing marks a stale one unknown | 不用批 |
| [TD-254](#td-254) | P2 | ops-platform | Two mechanisms repair the same failed backup: the autopilot's repair_cnpg_wal_store (every 15 min) and the backup-retry CronJob | 不用批 |
| [TD-255](#td-255) | P3 | ops-platform | The hourly drift scan deletes every Failed pod it may, including failed backup Job pods in data | 不用批 |
| [TD-256](#td-256) | P3 | ops-platform | Plugin freshness probes read Postgres by exec into the primary as superuser: STG cannot run them, PROD keeps pods/exec for a read | 不用批 |

## 条目

### TD-85

**P1 · trade (round 1) · One database password reaches everything: any DEV pod can write PROD Trade and all of Golden Source**

- **状态**：在做（验收已 PASS，只差防线：`RATCHETS.md` 里 TD-85 那行的 role-matrix 检查还没建）
- **验收结果**：PASS 2026-10-07 eaf68ac — GS `datacl` 里 PUBLIC 只剩 `=T`（无 CONNECT）；10-06 16:43 → 10-07 16:43 UTC 两个实例的 Postgres 日志里 `data_writer` / `flex_writer` 的 `permission denied` 为 0；`flex_writer` 10-07 10:30 UTC 照常写入 raw_broker（5 行）。日志里另有 2 条是 `bifrost` 的 pg_dump 读不了 `research.suggestion_adoption_suggestion_adoption_id_seq`（10-07 01:42 手动逻辑备份，已失败；之后 03:14 手动与 04:30 定时两次都 Complete），不属于本项
- **验收**：Golden Source 的 `datacl` 里没有 PUBLIC 的 CONNECT（`=c`），且 Postgres 日志 24 小时内 `data_writer` / `flex_writer` 的 `permission denied` 为 0：`kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -At -c "SELECT datacl FROM pg_database WHERE datname = current_database()"`
- **现在**：D1–D8 与 GS 的 PUBLIC CONNECT 收回（10-06，eaf68ac）全部执行完：三环境 Trade 运行时用 `trade_app_<env>` 登录；D4 已在三个 Trade 库收回 PUBLIC 的 CONNECT 和 CREATE（10-06，验证 74/74）；D7 ConfigMap 已合入；D6 收口完成，`data_writer` 在 `raw_broker` 上的写权已撤（core 0.48.2，10-06）。
- **下一步**：建 role-matrix 防线（只读脚本 + 期望矩阵，每日 CronJob，`BifrostDbPrivilegeDrift`），落地后进「待你签收」。已交 Cursor：`cursor-tasks/LANE-M-db-role-matrix.md`（含 analytics_writer 在 raw_market / raw_broker 的 CREATE 要另写 db-step 撤掉）。（10-07）
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

### TD-96

**P2 · agent-governance · preflight.js D10 rule only recognises curl: python requests, wget --post-data and sed -i on the daemon scale-zero patch all pass**

- **状态**：待你签收（Owner 10-07 应用草案：infra 560e58c，工作区根 scripts/agent-guard 即这份）
- **验收结果**：PASS 2026-10-07 560e58c：agent-guard test.js 74 通过 / 0 失败（D10 新增 python requests/httpx/urllib、wget、httpie、node fetch 写 /control/*，kubectl patch daemon 扩容，sed -i / perl -pi / cp / tee / > / kubectl apply|patch|edit / git rm / open(w) 改 guard 文件均 DENY；只读与无关操作 ALLOW）
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

### TD-103

**P2 · flex-ib · The cash parser never stores IB's transactionID, so dedupe falls back to (account, day, amount, type, report_date) and same-amount items overwrite each other**

- **状态**：观察中（flex 0.13.0 解析器已保存 transactionID；GS 回填 UPDATE 与唯一索引在第 4 批，要你逐项点头）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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

- **状态**：在做（ib-gateway 0.4.0 已上 PROD 10-07 17:19 UTC（digest sha256:278c4c07…，插件 e335bd6）+ Trade core 0.58.0：三个健康 hash 已带 updated_at（实测 6.5 s）；但 PROD trade-api /api/monitor/ops/market-ingest/services 三行仍 process_active=inactive、k8s_replicas=0——api-ops SA 读不了 data/ib-gateway（can-i no），hash 也未读到；交 Cursor LANE-T2）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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

### TD-107

**P2 · market-data · Indexes declared for the six financials entity tables never reach a deployed DB (the migration returns early); live differs from fresh install**

- **状态**：待你签收（Owner 10-07 批；GS 6 张 financials 表已有 (period_date, symbol) 索引）
- **验收结果**：PASS 2026-10-07：CREATE INDEX CONCURRENTLY 5 个新建、short_volume 已存在跳过；6 个 indisvalid=t；market-data 0.86.0 代码不再声明 symbol_period_date
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

### TD-148

**P3 · trade-data · A trade cannot name the lens or backtest run it came from: trade has no such column and strategy_plan.source_kind does not allow lens / backtest_run**

- **状态**：待你签收（Owner 10-07 批；bifrost_dev / stg / prod 已执行）
- **验收**：三个 Trade 库各跑：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_prod -X -At -c "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='strategy_plan'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%source_kind%'"` 含 `'lens'` 与 `'backtest_run'`
- **验收结果**：PASS 2026-10-07：三库 strategy_plan_source_kind_check 现含 'lens' 与 'backtest_run'，约束名不变；单事务执行（-1）
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

- **状态**：待你签收（Owner 10-07 批；GS 已 DROP INDEX CONCURRENTLY）
- **验收结果**：PASS 2026-10-07：执行前两个旧索引与新索引定义相同、idx_scan=0；执行后 features.event_signal_radar_daily 只剩 pkey + 两个 event_signal_radar_daily_* 索引
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

- **状态**：未开始
- **Claim**: TD-151's seed file carries FOMC through 2027 but CPI only for three 2026 releases (copied from a hand-dropped file) and no Employment Situation dates.
- **Measured**: MEASURED 10-06 by paydown lane O: bls.gov returned 403 to the Mac; federalreserve.gov answered.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/scheduler/data/macro_calendar.csv:35` — `2026-12-10,08:30,US,CPI,November 2026`
- **Impact**: From 11-05 the asset check warns; from 12-10 the forward calendar has no CPI and never had payrolls.
- **Fix**: Someone who can open bls.gov adds the 2027 CPI and Employment Situation schedules to the CSV.
- **Ratchet**: Already in place: the macro_calendar asset check warns when any series has under 30 days left.
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

### TD-196

**P2 · ops-platform · platform-api and platform-workers keep their state in per-pod emptyDir: every rollout erases release cycles, gate history, the operate queue and checklist signals, and the audit log is memory-only**

- **状态**：观察中（platform 87965ce 已上 STG/PROD 10-07；看第一次真实写入后，下一次 PROD 发版 release-cycles 与 audit 仍在）
- **现在**：新包 `internal/statefile`：各 store 照旧用原路径读写；集群里 `PLATFORM_DATA_DIR` 下的每个状态文件存成本命名空间的 ConfigMap `platform-state-<key>`（STG/PROD 分开，900 KiB 预算，后写为准），本机与 operator-plane 仍是文件。迁移：checklist、operate queue + briefs、release gate 状态与历史、release cycles、patrol、hermes insights、escape hatch、agent deploy、data-clone 计划与最近一次。审计按角色存 `audit-api.json` / `audit-workers.json`（各留 500 条），api 的 `GET /audit` 合并两份，每条同时打一行日志进 Loki。data-clone 计划 `Get` 每次重读（api 写、workers 读）。写入时截断：闸门历史 100 条、已结束的队列条目 200 条。两 Pod 启动日志都有「platform state in ConfigMaps」。未迁：data-clone 任务记录（一个目录，按 Pod 保存）
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
- **验收**: After a PROD platform rollout, `GET /api/v1/promote/release-cycles?lane=platform` and `GET /api/v1/audit` still list the entries recorded before it. 经 api pod `PUT` data-clone schedule 后，workers pod 的 `maybeAutoClone` 读到 `enabled:true`（store 每个 tick 重读）。
- **验收结果**：部分 PASS 2026-10-07：STG 上 04:43Z 写入的审计记录（Alertmanager webhook）在 04:45 与 04:59 两次 Pod 重启后仍由 `GET /api/v1/audit` 返回（ConfigMap `platform-state-audit-audit-api-json`）；PROD 还没有发生过写入
- 审批 已批（ConfigMap） · 代价 M · 风险 med · repos: bifrost-platform, bifrost-trade-infra
- **Also (round 3, 10-07)**: the data-clone schedule is written by the api pod and read by the workers pod's scheduler, each with its own emptyDir, and `DataCloneScheduleStore` loads its file only once at construction, so a schedule enabled in the Console never fires in-cluster (all three GETs answer enabled:false today). The ConfigMap store must be re-read on every `maybeAutoClone` tick; acceptance gains: a schedule PUT through the api pod is visible to the workers pod (`bifrost-platform/api/internal/cluster/data_clone.go:285`, `server.go:129`).

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

### TD-204

**P1 · ops-platform · STG and PROD platform-api and platform-workers run as system:masters through a copy of the k3s admin kubeconfig, and anonymous GETs use it to read pod logs in any namespace**

- **状态**：待你签收
- **现在**：10-07（Owner 批 A）：`k8s/platform-rbac/`（手工 apply，infra d5aad06）给每个 platform 命名空间建 ServiceAccount `bifrost-platform`：两环境都有全集群只读（无 Secret）、只在 Bifrost 命名空间读日志、自己命名空间与 cicd 的状态 ConfigMap、`gitea-bootstrap`；只 PROD 有 Bifrost 命名空间的重启/扩缩/删 Pod、节点 cordon、data 里的 pods/exec 与 CNPG Backup 与 `minio-backup`、cicd 的 PipelineRun 与 Argo 同步。切换不改代码：kubeconfig 仍在原路径，但来自一个指向 Pod 自身令牌的 ConfigMap（STG bc03d27、PROD 27829fb）；两份管理员 kubeconfig Secret 已删除。读 Pod 日志的路由改为要 viewer（platform a162fe8，Console 带令牌）。权限按实测调用清单定（typed 27 类 + CNPG/Tekton/Argo/Traefik）
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
- **验收结果**：PASS 2026-10-07 infra 27829fb / platform a162fe8：STG `bifrost-platform-kubeconfig` NotFound（PROD 同）；两环境 `kubectl auth can-i get secrets -n data --as=system:serviceaccount:bifrost-platform-<env>:bifrost-platform` → no；匿名读 kube-system 与 data 的 Pod 日志在 30876/30878 都 401；`make check-platform-rbac` 82/82；切换后两环境 api/workers 日志 0 条 forbidden，STG 与 PROD 共有的矩阵格子状态一致
- 审批 安全/凭据（要你批） · 代价 M · 风险 med · repos: bifrost-platform, bifrost-trade-infra

### TD-208

**P1 · ops-platform · Anonymous POST /checklist/husbandry-sync starts full-auto remediation agents: it merges the stored checklist and dispatches every failing item, and three Console pages call it on load**

- **状态**：在做
- **现在**：鉴权一半已上线（platform e504020，STG/PROD）：`POST /checklist/husbandry-sync` 移进 operator 组，HusbandryStrip 只在有令牌时发送；无令牌 401 已在三处实测
- **下一步**：只派发本次探到的 husbandry 项、不再派发整个合并后的清单（或改成 workers 侧定时），之后进签收
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

### TD-217

**P2 · data · The Barman base+WAL backup, the only copy of the 34 GB Golden Source history, has never been restored, and has not been tried at all against the NAS MinIO it moved to on 10-06**

- **状态**：观察中（Cursor LANE-D2 已完成并复验；待你批：建临时恢复集群演练、演练完删除）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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

### TD-223

**P3 · ops-platform · STG and PROD platform-workers both run the IB gateway auto-repair loop against the one live data/ib-gateway, each with its own 15-minute cooldown**

- **状态**：待你签收
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
- **验收结果**：PASS 2026-10-07 infra 7b82568：STG `"auto_repair_enabled":false`、PROD `"auto_repair_enabled":true`；STG workers 另设 `PLATFORM_RELEASE_RECORDER=off`（发布记录只由 PROD 写）
- 审批 PROD 变更（要你批） · 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform

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

### TD-236

**P3 · trade-worker · Leftovers of the deleted Account Sync daemon: the plugin still XADDs every account snapshot to ib:account:stream:v1, which nothing reads**

- **状态**：待你签收（ib-gateway 0.4.0 不再 XADD；Owner 10-07 在 redis-ib 上 DEL ib:account:stream:v1）
- **验收结果**：PASS 2026-10-07：DEL 返回 1；之后 ib:account:stream:v1 不存在且未被重建，ib:account:snapshot:v1 正常；core / Console 已不引用该流
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

- **状态**：观察中（Cursor LANE-D2 已完成并复验；待你批：删 data-warehouse namespace、两个 Released PV 与 np-redis-fresh）
- **验收结果**：PASS（代码层）2026-10-07 Claude 10-07 复验：各仓库分支合并后门禁全绿（core 13463、worker 180、trade-api 1018、flex 160、market-data 1288、research 2132、ib-gateway 84、platform Go 56 包 + Console 801 + agent 25、ui 5）
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

### TD-240

**P3 · trade-worker · The running PROD daemon never writes contract_quote_live: the observe-only quote mirror sits under mock_hedging, which is hard-coded True**

- **状态**：在做（Owner 10-07 选 A：给报价镜像单独开关 daemon.quote_mirror，默认关；交 Cursor LANE-T2）
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

### TD-253

**P2 · ops-platform · The autopilot acts on checklist signals that are weeks old: signals carry no time of their own, and nothing marks a stale one unknown**

- **状态**：待你签收
- **验收结果**：PASS 2026-10-07 d8bdf41（PROD `GET :30876/api/v1/checklist/signals`：22 个信号全部带 observed_at，来源只有 checklist-prober 与 data-husbandry；06:17 起探测器每 10 分钟一轮，唯一红项 hermes-tooling 为真实状态）。做了什么：信号带 observed_at/source、超过 `CHECKLIST_SIGNAL_TTL`（2h）读 unknown（1eaffd2）；PROD workers 进程内探测器（2727eb0、d8833e5、b08d009）；实时 husbandry 三项带时间（dc1488e）
- **Claim**: The checklist store keeps one `updated_at` for the whole record; each item signal (`ItemSignal`) has no time of its own. The autopilot fixes whatever reads `fail`, whenever that was observed. On the Owner's Mac (the only acting autopilot until 10-07) 19 of 22 signals dated from 09-29 or earlier: `db-backup-fresh` still cited a July backup, `nodes-ready` said 6/6 while gpu-server was off. Since TD-203 (local platform-api loopback-only) the .50 runner can no longer report there at all.
- **Measured**: MEASURED 2026-10-07 04:06 UTC: `GET /api/v1/checklist/signals` on the local platform-api → updated_at 2026-09-29T03:32:01Z; `db-backup-fresh` detail `bifrost-postgres-daily-20260711030000`.
- **Evidence**:
  - `bifrost-platform/api/internal/checklist/types.go:14` — `type ItemSignal struct {`
  - `bifrost-platform/api/internal/patrol/autopilot.go:220` — `case "db-backup-fresh":`
- **Impact**: An autopilot can repair what is already fine (or miss what broke) based on a snapshot nobody refreshed.
- **Fix**: Each signal carries `observed_at` and `source`; signals older than their TTL read `unknown` and are never fixed; in PROD the signals are probed in-cluster by the workers (not reported from a Mac). Part of the Ops maintenance plan step 4 (TD-130).
- **Ratchet**: Test: an item signal older than its TTL is reported unknown and the autopilot skips it.
- **验收**: `curl -s -m10 http://192.168.10.73:30876/api/v1/checklist/signals | python3 -c "import json,sys;print(all(x.get('observed_at') for x in json.load(sys.stdin)['signals']))"  # True`
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-platform

### TD-254

**P2 · ops-platform · Two mechanisms repair the same failed backup: the autopilot's repair_cnpg_wal_store (every 15 min) and the backup-retry CronJob; the autopilot started a full base backup in market hours after the day's backup had completed**

- **状态**：待你签收
- **验收结果**：PASS 2026-10-07 dc1488e（`git grep repairCnpgWalStore` 无输出；`go test ./internal/patrol -run 'StaleBackup|ReportOnly'` ok）。PROD 自 2727eb0 起生效
- **Claim**: When `db-backup-fresh` reads fail the autopilot calls repair_cnpg_wal_store, which deletes failed Backup CRs (TD-131) and starts an on-demand base backup. The in-cluster CronJob `data/backup-retry` (*/15 04–09 UTC) also starts one retry Backup when no backup completed today. Neither knows the other. On 10-06 the daily backup completed at 03:00 and a manual one at 05:16, yet the autopilot started `bifrost-postgres-ondemand-20261006-161507` (a full base backup) at 16:15 UTC, in US market hours.
- **Measured**: MEASURED 2026-10-07: local autopilot runs 10-05 06:21 → 10-07 03:45: `db-backup-fresh` handled 54 times, `repair_cnpg_wal_store` HTTP 502 52 times, 202 twice. `kubectl -n data get backups` lists the 10-06 daily (completed 03:00), manual-nas (05:16) and ondemand-161507.
- **Evidence**:
  - `bifrost-platform/api/internal/patrol/autopilot.go:220` — `case "db-backup-fresh":`
  - `bifrost-platform/api/internal/patrol/autopilot.go:221` — `return a.repairCnpgWalStore(ctx)`
- **Impact**: Extra full backups load the primary (shares a node with PROD) and the NAS; repeated repair attempts delete the failed-backup record.
- **Fix**: Backups belong to CNPG (ScheduledBackup) and backup-retry only: drop `db-backup-fresh` from the autopilot's fix map (report + page instead), keep repair_cnpg_wal_store as a manual operator tool. Part of plan step 4.
- **Ratchet**: Test: the autopilot fix map has no entry that creates a Backup or touches data/minio.
- **验收**: `git -C bifrost-platform grep -n 'repairCnpgWalStore' origin/main -- api/internal/patrol  # no call from the fix map`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-255

**P3 · ops-platform · The hourly drift scan deletes every Failed pod it may, including failed backup Job pods in data: the evidence of a failed backup is gone within the hour**

- **状态**：待你签收
- **验收结果**：PASS 2026-10-07 dc1488e（`go test ./internal/patrol -run ChainCleanup -count=1`：两例 PASS）。修法比原写的更窄：漂移扫描只删被驱逐（Evicted）的 Pod，Failed/Succeeded 一律保留并记一行 KEEP（Job 历史上限与 TTL 会回收）；只报告模式下一个也不删。PROD 自 2727eb0 起生效
- **Claim**: fleet-drift-scan's chain cleanup deletes terminal pods that pass `isSafeToDelete` (phase Succeeded or Failed, not a protected prefix). Failed `logical-backup-*` pods in `data` qualify, so their logs vanish within an hour; investigating TD-210 needed Loki.
- **Measured**: MEASURED 2026-10-07: local patrol evidence 10-05 20:05 → 10-07 02:05 shows six `DELETE data/logical-backup-…` (phase=Failed) HTTP 200.
- **Evidence**:
  - `bifrost-platform/api/internal/patrol/local.go:131` — `fmt.Fprintf(&b, "- DELETE %s/%s (phase=%s) … ", p.Namespace, p.Name, p.Phase)`
  - `bifrost-platform/api/internal/patrol/local.go:280` — `func isSafeToDelete(p stalePod) bool {`
- **Impact**: Failed backup and drill runs leave no pod or log in the cluster to read; Kubernetes already garbage-collects Job pods by the Job's history limits.
- **Fix**: Never delete pods owned by a Job, or in namespace data, younger than 7 days (let Job history limits and TTL handle them). Part of plan step 4.
- **Ratchet**: Unit test on isSafeToDelete: a Failed Job-owned pod in data younger than 7 days is not safe to delete.
- **验收**: `cd bifrost-platform/api && go test ./internal/patrol -run 'ChainCleanup' -count=1`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-256

**P3 · ops-platform · Plugin freshness probes read Postgres by exec into the primary as superuser: STG (read-only since TD-204) cannot run them, and PROD needs pods/exec in data only for this read**

- **状态**：未开始
- **Claim**: marketdata and flexquery `probeFreshness` run `SELECT … FROM ops_jobs.ingest_freshness` / `flex_ingest_freshness` through `ExecSQLOnPrimary` (pods/exec into bifrost-postgres, psql as postgres). Since the STG platform runs as the read-only ServiceAccount (TD-204) these probes fail on STG; on PROD they keep pods/exec in data, a superuser-equivalent right, for a read the plugins already serve over HTTP.
- **Measured**: CODE-READ; RBAC measured 2026-10-07: STG `can-i create pods --subresource=exec -n data` → no, PROD → yes.
- **Evidence**:
  - `bifrost-platform/api/internal/marketdata/service.go` — `out, err := s.cluster.ExecSQLOnPrimary(ctx, db, sql)`
  - `bifrost-platform/api/internal/flexquery/service.go` — `out, err := s.cluster.ExecSQLOnPrimary(ctx, db, sql)`
- **Impact**: STG plugin freshness views read unavailable; PROD keeps a broader right than reads need (the data clone still needs exec).
- **Fix**: Read freshness from the plugins' own HTTP endpoints through the service proxy (observer already allows services/proxy), as other plugin health reads do; then pods/exec in data serves only the data clone.
- **Ratchet**: code-health metric: ExecSQLOnPrimary call sites outside cluster/data_clone*.go, baseline 2, falling.
- **验收**: `git -C bifrost-platform grep -n 'ExecSQLOnPrimary' origin/main -- api/internal/marketdata api/internal/flexquery  # no output`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

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
