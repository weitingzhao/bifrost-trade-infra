# Bifrost 技术债（未结）

> **这份文件只放没还完的债。** 历史在 git 里，这里不留。审计扫出来的、日常工作里撞上的，都直接在这里加一条，编号接着当前最大号往下排。每条必须有证据（`文件:行`）、修法和防线。条目正文保留英文，标识符照抄。
>
> **每一项怎么走（Owner 2026-10-06）**
> 1. **状态**只有五种：`未开始` → `在做` → `观察中（到 MM-DD，看什么）` → `待你签收`；签收后删掉这一项。
> 2. **验收**：每项写一条验收命令和预期结果。进 `待你签收` 之前必须重跑它，把 `验收结果：PASS|FAIL 日期 提交号` 写回这一项。没有新的 PASS，不能进 `待你签收`。
> 3. **待你签收**：进这个状态时，在下面「待你签收」一节加一行：改了什么、验收结果、加了哪条防线（`RATCHETS.md`）、**后续**（引出的新编号，或「无后续：理由」）。Owner 回复「签收 TD-n」或「打回 TD-n：原因」。
> 4. **签收后**：删掉这一项和「待你签收」里那一行；「还债顺序」里把编号移到「已还」，计划进度一直看得见。提交信息写签收、防线和后续。打回的，状态回到 `在做`，原因写进 `下一步`。
> 5. **自上次以来**：下面「上次查看」记着 Owner 上次看过的提交。台账页从那个提交起生成变化清单（新增、关闭、状态变化、防线增减）。Owner 说「看过了」，就把它改成当前提交。

上次查看：92c0271（2026-10-10，Owner 已看过 TD-274 DEV 结果；本轮基线）

## 待你签收

- **TD-373** — 06 上的基准原来 20 道只能跑 11 道（TS 缺旁边的 bifrost-ui、测试库、依赖没装）。题集换成 06 能跑的 20 道，agentd 带旁边仓库并把隐藏测试要的接口写进题面（platform `d788296`、infra `fe32f4a`）。验收：PASS 2026-10-19，`bench-20261019T060504-codex` 20 道全能跑，判对 16。防线：交上来的结果逐题写明跑不了的原因，可跑题数在 capability_scored 事件里；新题集上线前过 `benchreplay_test.go`。后续：无后续，「Left」两条只是少挑两类候选题，题集已全能跑，不另记。
- **TD-355** — 签规则的钥匙不用 Owner 确认就能签（没口令、常驻 ssh-agent）。Owner 10-15 19:05 把它移出 agent、19:10 加了口令（指纹不变，平台不用改）；`rule.sh sign` 现在拒绝没口令或常驻 agent 的钥匙。验收：PASS 2026-10-15 19:15。防线：RATCHETS「The Owner's signing key asks before it signs」。后续：发版策略的签名工具还没有同一道检查，长期换成每次要按一下的钥匙（会改信任指纹），都等补强阶段再定，没另开编号。
- **TD-289** — Prometheus 与 Alertmanager 的数据从 emptyDir 改到 NAS 卷（StorageClass `nfs-hot`，helm revision 17，10-10 06:04Z 上线）；Grafana 仍是 emptyDir（有意）。验收：PASS 2026-10-11 `1d69669`，TSDB 在 NFS 上观察 31 小时：Pod 重启 0 次，30 小时日志 114 行无 WARN / ERROR，压缩 20 次失败 0，WAL 损坏 0，head / WAL 截断失败 0，`count(up offset 20h)` = 75，`check_monitoring_persistence.py --live` 退出 0。防线：RATCHETS「监控数据不放 emptyDir」。后续：无后续：Grafana 不持久化是有意的。
- **TD-94** — Market gate 失败即阻断、正确 session 校验及 Flex 独立闸门已运行验收：PASS 2026-10-10，Research `d628fa6`（含 `2c34f4d` / `72e6473`），生产对应模块 hash 一致；最近三批 gate=session 均正确，相关测试 56 passed / 0 skipped。防线：gate / Flex tests + READ ONLY 运行审计（RATCHETS）。后续：TD-92 继续观察 ERROR 告警回执；历史缺口仍由 TD-172/142 方案处理，不随闸门签收宣称补齐。

**未结 118 项**：P0 0 · P1 11 · P2 44 · P3 63；要你批的 42 项（审批一栏不是「不用批」或「无」的；2026-10-13 重数：按每一项的标题和它自己的优先级行数出来的，此前的 99 少数了）。

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

### 数据完整度执行清单（Owner 2026-10-10 确认）

执行顺序：先保存 TD-302 的可审查成果，再验证不可恢复数据的归档，确认每日产出防线，最后盘点并按批准范围回填。Owner 已继续授权第 2 项运行验收；TD-183 实际恢复未运行，后续项按顺序报告，不提前执行数据写入。2026-10-11 Owner 随后授权在最新 main 的隔离 worktree 整合，通过测试与 DEV 验收后只合入不会触发部署的源码和记录；不发布、不启用告警、不扩大回填。早期隔离状态为当时记录，当前交付状态见下表及 10-11 整合报告。代码完成、生产验收、历史补齐分别记录，不能共用一个「完成」。

| 顺序 / 已有债 | 状态与依赖 | 详细工作及交付物 | 验收与防线 | 执行边界 |
|---|---|---|---|---|
| 0 · TD-302 收口 | 已合入／未发布；Research `e094659`、Frontend `2cf45185`（远端 main 已核验） | 提交 Research 有效值过滤、IV 历史深度语义、Frontend 权威读数；保存 `bifrost-research/docs/acceptance/TD-302.md`，记录各仓提交号 | Research 2150 passed / 30 skipped；Frontend 4120 passed / 1 skipped；提交前复查 Research 34 / Frontend 4 passed，提交钩子 PASS；APT 历史不足、ZZQ 缺数据、AU 合法 0。对应回归测试见 RATCHETS | 已授权安全 main 整合；不发布、不回填 |
| 1 · TD-183 归档可恢复性 | 本轮只读核查与准备完成；实际恢复及三表整体验收未完成 | 两份 intraday snapshot 归档共 573826 行，hash/清单/全列解码/日期/主键检查 PASS；恢复方案见 `docs/audits/TD-183_ARCHIVE_READINESS_2026-10-10.md`。option_daily/short_volume 最早 2024-10-01，首次非零归档仍待约 11-01 | trim 的归档/删除行数与 Parquet 一致；五项离线异常测试 PASS。实际恢复必须再验 typed import、全字段 readback 和幂等；当前不记恢复 PASS | 本轮只读核查及准备；不触发 trim、不改 hold、不删文件、不写共享数据库、不建集群恢复资源 |
| 2 · TD-92 / TD-94 每日产出防线 | 本轮运行核查完成；TD-94 待你签收，TD-92 告警回执仍观察 | 三批各 17 个 engine output_ok 已执行；14 PASS / 3 WARN；gate 均正确，无 override。56 测试通过无跳过，核心模块与生产 hash 一致；报告见 `docs/audits/TD-92-94_RUNTIME_ACCEPTANCE_2026-10-10.md` | 合法零、异常零、连续跳过及失败原因测试通过；WARN 持续缺数据未补；ERROR sensor 有运行记录但历史投递/接收回执未证实。未改非阻断政策，不把 SUCCESS 当完整数据 | 只读核查与隔离测试，未发现需新改生产逻辑的回归；不发布、不回填、不注入真实告警 |
| 3 · TD-172 / TD-142 联合回填盘点 | 方案已确认；第一限定批已执行验收，整债未结 | `docs/audits/TD-172-142_GAP_PLAN_2026-10-10.md`：TD-172 725 × 59 session、TD-142 首批 23 × 252 session；已有来源模拟可增 756 个不同 ATM expiry 行，覆盖 606 symbol-day；条件重抓清单联合去重 66649 个合约区间 / 161863 个目标 contract-day；小试批 82 区间 / 120 目标日 | 7 项测试及只读全流程 PASS；合法零、整日缺失分母、Brent 双侧与 request 去重验证。SPY/NVDA/AAPL 仅本地重算不改善 90-day cone；GOOG 可达 104/74（90/180）session。受限 50–220 writer、cone180、Plugin long-breadth / Research valid-bracket 防线已在隔离分支补齐；尚未生产运行 | 已批准复用 756 键及 82 区间/120 目标日试批；保留现有有效短期行，禁止 long-only 输入触发整日 DELETE；Plugin 写 raw，Research 写 features；不使用 SVI 拼接；第 4 项限定批已实写验收，扩大/短腿仍另批 |
| 4 · TD-172 / TD-142 按批修复 | 在做：60-session主范围64父键PASS；三名90/180为66/60、61/60、61/60；累计849 ATM /1840来源 /362 raw；整债未结 | 小批原始数据补齐或复用 → 派生重算 → 验收 → 逐批扩大；记录失败和无法修复项；交付逐批前后覆盖率 | 重跑幂等；每批主键、session、期限、有效值和输出行数一致；剩余缺口有原因，不以任务成功代替数据完整 | `docs/audits/TD-172-142_DEPTH_EXECUTION_2026-10-10.md`：主64父键新增247 raw/64 ATM/129来源，152/220 HTTP；9备用未用；Plugin1315 passed/9 skipped、Research16 passed、四阶段SQL/API/DEV及重放PASS；未发布，扩大/短腿另批 |
| 5 · TD-149 错误数据治理 | 观察中；既有每日检查与 10-16 复查安排继续，不等待回填 | CTVA vendor 复权后按既有批准重抓日线、重算派生；到 10-16 仍未修正另议 Research 自算；保留原始与派生对照 | 分拆前后调整正确，RV/VRP 等异常读数消除；盘点公司行动异常检测的现有防线与缺口 | 尊重已有批准：vendor 修正后重抓重算；自行复权另批 |
| 6 · TD-300 / TD-301 业务链路收口 | 未开始；数据安全及缺口工作之后 | Doctor 区分历史失败、已恢复、仍可重试、证据被删与查询失败；term_slope 接入批量筛选 | 恢复事件不再误报永久丢失；有效单标的与批量筛选读数一致；测试与 DEV 页面验收 | 隔离分支逐项完成后报告；不发布 |

每项结果记录：检查时间与数据 session、代码/运行证据、验收结果、剩余缺口、提交号、发布状态及下一项依赖。TD-183 初始「尚未真实归档」是旧台账描述，须用本次运行与文件证据核实，不能当作今天的结论。

### 第 0 波 · 第 1 轮收尾

目标：第 1 轮剩下的三项按已排的日期收掉。TD-85 剩 Golden Source 的 PUBLIC CONNECT；TD-51 等 Loki 闸门后随下一次 Trade 发布；TD-80 C2-b 改号 core 0.49.0 与 TD-51 同发。

项：TD-85 · 已还：TD-21, TD-51, TD-80

### 第 1 波 · 正在出错的数据与「绿着的失败」

目标：先让失败变红。错数据先修数据（TD-87 restate），再把引擎、闸门、写入方从「出错也报成功」改成失败即失败：引擎资产按输出判定、husbandry gate 失败即关、日历读失败报错、写入方失败抛错。不需要 Owner 批的先做。

项：TD-91, TD-92, TD-94, TD-97, TD-101, TD-156, TD-189, TD-192, TD-244 · 已还：TD-88, TD-89, TD-90, TD-113, TD-93, TD-165, TD-167, TD-87, TD-245, TD-136, TD-157, TD-166

### 第 2 波 · 让闸门真的卡住

目标：一个开关让所有测试类防线生效（CI 卡发布），再补上调度存活告警、D10 闸门的非 curl 写法、operator 流白名单、本机常驻任务和密钥轮换的盲区、spine 副本同步。

项：TD-95, TD-100, TD-121, TD-152, TD-153, TD-155, TD-162, TD-293, TD-294, TD-298 · 已还：TD-343, TD-341, TD-295, TD-99, TD-161, TD-198, TD-195, TD-194, TD-249, TD-109, TD-105, TD-96

### 第 3 波 · 交易日与日历只有一个来源

目标：所有「今天 / 本 session」都从 `db/calendar` 的一个函数来，代替 11 个私有 helper 和 44 处 `date.today()`；dbt 补 grain 测试；IV / 回测的定价参数统一。

项：TD-98, TD-110, TD-111, TD-112, TD-128, TD-129, TD-174, TD-242 · 已还：TD-164, TD-175, TD-247

### 第 4 波 · 券商资金账本（Flex / IB）

目标：现金与佣金账本可信：按 IB transactionID 去重（改表）、佣金一种符号、资金路径有测试、Flex 不再经 DEV 库读配置、IB Gateway 健康与镜像可追溯。

项：TD-117 · 已还：TD-115, TD-116, TD-114, TD-122, TD-104, TD-103

### 第 5 波 · 副本、死重与清单

目标：删掉没人用的（挂起的 CronJob、退役脚本、无调用路由），手抄的副本改成从一处生成（调度名单、max-pain / PCR），清单的应用顺序与 Argo 归属理顺。

项：TD-118, TD-120, TD-170, TD-202, TD-290, TD-291, TD-300 · 已还：TD-126, TD-108, TD-154, TD-163, TD-168, TD-124, TD-176, TD-191, TD-169, TD-200, TD-201, TD-190, TD-123, TD-106, TD-119, TD-125, TD-102, TD-160, TD-107

### 第 6 波 · 备份链与自动修复（10-06 日常发现）

目标：备份 MinIO 已搬到 NAS（infra 1ee0ac2，已接监控 ba03488），把剩下的收尾：自动修复只在 PROD 一处动手、失败记录不再被删、platform 的新检查上线、稳定一周后退役集群里的 MinIO 残留，再处理 WAL 体量和 CNPG 1.30 的备份插件。

项：TD-133, TD-134, TD-135 · 已还：TD-197, TD-173, TD-132, TD-131

### 第 7 波 · 数据缺口（10-06 由 Data Gaps 看板并入）

目标：Data Gaps 看板上未结的 15 项并入台账：先把每日快照的写入修对（TD-137）再接读侧和三页，归因行补上价格，Research 侧已就绪的一个版本（0.185.0）发出去，长期限 IV 锥在 10-31 前从 option_daily 回填，其余按 Owner 已定的口径排。

项：TD-137, TD-142, TD-143, TD-144, TD-146, TD-149, TD-158, TD-159, TD-172, TD-180, TD-246, TD-250, TD-274, TD-301, TD-302 · 已还：TD-141, TD-147, TD-177, TD-179, TD-151, TD-181, TD-193, TD-140, TD-171, TD-138, TD-139, TD-178, TD-199, TD-243, TD-182, TD-148, TD-145, TD-150

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

项：TD-130, TD-272, TD-276, TD-283, TD-284, TD-285, TD-286, TD-287, TD-288, TD-289, TD-296, TD-297, TD-299 · 已还：TD-256, TD-257, TD-270, TD-271, TD-273, TD-275, TD-277, TD-278, TD-279, TD-280, TD-281, TD-282, TD-196, TD-223, TD-204, TD-253, TD-254, TD-255

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
| [TD-142](#td-142) | P2 | research-data | The 90-day IV cone has 31–39 sessions of history and there is no 180-day tenor: ATM IV was stored only to 90 DTE before 2026-08-05 | 在做：本批已批 |
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
| [TD-172](#td-172) | P2 | research-data | ATM IV has almost no 50–90 DTE expiry from 2026-07-06 to 09-25 (the EOD chain stopped at the third listed expiry until plugin 0.39.0); the fix was forward-only, so term structure reads na for that stretch | 在做：本批已批 |
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
| [TD-260](#td-260) | P3 | trade-core | Four LEFT JOINs still read raw_broker.contract_quote_live, which has had no writer since March and none at all after TD-240: the quote columns they feed can only ever come back NULL | 不用批 |
| [TD-261](#td-261) | P2 | ops-platform | The Console approval list never renders: it reads `{items}` and the API answers `{approvals: [...]}`, and the page test mocks the wrong shape so it never caught it | 不用批 |
| [TD-262](#td-262) | P3 | ops-platform | MCP `start_pipeline_run` sends no `who`, so a release started through MCP can never satisfy the policy's "requester holds the window" | 不用批 |
| [TD-265](#td-265) | P3 | research-data | Non-farm payrolls rows get no theme: the pipeline's theme regex does not recognise `NFP`, so they never join the rate-path group | 不用批 |
| [TD-266](#td-266) | P3 | flex-ib | The flex worker's system messages never leave the pod: it publishes to 127.0.0.1:6379, which is refused in-cluster, so the UI toast for a cash-ingest run is dropped with only a WARNING | 不用批 |
| [TD-267](#td-267) | P2 | ops-platform | An approval is consumed by a transient refusal: approve executes immediately, and a release-window clash marks the request `failed`, so the Owner's click is spent and a new request must be filed | 不用批 |
| [TD-268](#td-268) | P3 | ops-platform | `ExecSQLOnPrimary` is dead code: TD-256 and TD-259 took its last caller, and the ratchet that counted call sites now guards a function nobody calls | 不用批 |
| [TD-269](#td-269) | P3 | ops-platform | `release.sh hold` cannot be stopped cleanly: SIGTERM waits behind its `sleep 3600`, and SIGKILL leaves a stale lock only the Owner may clear | 不用批 |
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
| [TD-297](#td-297) | P3 | ops-platform | Platform CI runs no race detector and no MCP tests, so the approval state machine's concurrency tests and the 批 #n tool tests are only run by hand | 不用批 |
| [TD-298](#td-298) | P1 | agent-governance | Cursor never loaded the project hooks: it refuses a hooks.json reached through the workspace's .cursor symlink, so preflight.js did not gate Cursor sessions (proven back to 2026-09-28) | 不用批 |
| [TD-299](#td-299) | P2 | ops-platform | Tekton keeps every run (545 PipelineRuns and 3958 TaskRuns in cicd since 2026-10-03) and nothing prunes them; with the finished pods gone after the rolling reboot, the controller's periodic resync errors on each old TaskRun and a new run waited 4 min 21 s for its pod | 要你批 |
| [TD-274](#td-274) | P3 | frontend | Symbol faces hide GEX levels that exist when zero gamma is NULL: the dealer level strip needs all four values and the regime cell needs zero gamma, so a chain with no flip (about a third of expiries) shows neither walls nor regime | 不用批 |

| [TD-300](#td-300) | P3 | market-data | Doctor calls recovered failed jobs trimmed even though their error rows survive | 不用批 |
| [TD-301](#td-301) | P3 | research-data | Term slope has fresh exhibit data but no batch screening reader | 不用批 |
| [TD-302](#td-302) | P2 | research-data | Coverage counts 71 warm-up NULL IV scores as readable; exhibits give no warm-up reason | 不用批 |

| [TD-303](#td-303) | P1 | research-control | Daily failure visibility and accepted long-row retention await production acceptance | PROD 变更（要你批） |
| [TD-304](#td-304) | P1 | alert-delivery | Failed or missing Research work has no verified durable Owner notification | PROD 变更／真实告警测试（要你批） |
| [TD-305](#td-305) | P2 | market-data | 67 recovered empty option responses still lack historical classification | 不用批（只读盘点；补抓另批） |

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

- **交付状态 2026-10-11**：已合入／未发布；最新 main 整合测试及 DEV 验收 PASS。对应提交和部署边界见 `docs/audits/DATA_INTEGRITY_MAIN_INTEGRATION_2026-10-11.md`；生产验收、告警送达、实际恢复及剩余数据缺口按各项条件保留，未据源码合入结债。

- **Continuity audit 2026-10-10**: isolated Research `cc575bf` and Frontend `c57283ae`; daily enqueue/self-heal acknowledgment, accepted long-row retention and actual output-check visibility verified locally. Research lint + 2286 passed/17 skipped; affected 75 passed/0 skipped, frontend 13 passed + lint/build/CSS, actual DEV CHECKS CAUTION with 30 valid candidates retained. Latest primary 60/90/180 readings present; no backfill/release/real alert. Production rollout, durable alert receipt and full-universe long depth remain open; TD-303/304/305 and `docs/audits/DATA_CONTINUITY_DEFENSES_2026-10-10.md` carry the bounded follow-up.

**P2 · research-control · Output checks execute and retain reasons, but ERROR alert receipt and persistent input gaps remain to be verified**

- **状态**：观察中（2026-10-10 三批真实运行及测试已复验；到下一次真实 ERROR 检查事件，看发送及接收回执；当前仍有持续输入缺口 WARN）
- **验收**：`scripts/audit-research-output-gates.sql` 以 agent_reader READ ONLY 查实际 evaluation，与当前 job 所选引擎逐个对齐（目前 17）；ERROR `BifrostDagsterAssetCheckFailed` 须有发送及接收证据，不能用 sensor tick SUCCESS 替代。
- **验收结果**：部分 PASS 2026-10-10 Research d628fa6：生产 0.205.0-dagster 对应模块 hash 相同；10-08/09/10 各 17 个引擎检查，14 PASS / 3 WARN。相关测试 56 passed / 0 skipped；合法零/异常零/跳过/失败原因有覆盖。10-07 实际有四个 ERROR 检查且 sensor tick 执行，但投递回执未找到，不关闭此债。报告：`docs/audits/TD-92-94_RUNTIME_ACCEPTANCE_2026-10-10.md`。
- **Original Claim (before existing fix)**: engine_assets._metadata wraps any result into MaterializeResult; run_gex/run_iv_surface/run_flow do `failed += 1` and drop result['error']; run_slot returns a non-raising 'skipped: no symbols'. No Dagster asset checks exist; only gex_intraday raises on zero output (added after three green weeks of 646-669/669 failures). The only other net is signal_health's 36h/72h computed_at freshness on a subset of tables, which misses partial failures, zero-row writes, wrong-date writes and tables such as research.option_pinned_contract. Silent failures like TD-89 and TD-97 are visible only by reading run metadata by hand.
- **Original Measured (before existing fix)**: MEASURED. ops_dagster.runs research*/market*, 14 days: 1,026 SUCCESS, 1 FAILURE (memory_distill, TD-86), 1 CANCELED. 10-06 run metadata: gex 42 failed / 1,366 ok over 2 sessions (~3%, about 15-22 names a night), flow 41, surface 41, momentum skipped 4, vrp skipped 7, option_pinned rows_written 0, all green. Most failing names entered option_universe in the last few days (onboarding lag); persistent invisible gaps: NVR (in universe since 09-08, 0 OI rows since 08-01, never a GEX row) and GRML (since 09-24, no OI); QRVO stock_daily stops at 10-02.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/engine_assets.py:36` — `def _metadata(result: dict[str, Any]) -> dict[str, Any]:`
  - `bifrost-research/src/bifrost_research/scheduler/engines.py:108` — `failed += 1`
  - `bifrost-research/src/bifrost_research/orchestration/research_aux_schedules.py:51` — `return MaterializeResult(metadata=meta(result if isinstance(result, dict) else {}))`
  - `bifrost-research/src/bifrost_research/orchestration/engine_assets.py:300` — `result = runners.run_option_pinned_contract()`
- **Original Impact (before existing fix)**: A broken engine looks the same as a working one on the Ops schedule view and in failure_alerts. NVR and GRML have had no GEX/surface/flow for weeks and nothing says why; onboarding lag, upstream gaps and bugs are indistinguishable.
- **Original Fix (before existing fix)**: Return failures as {symbol: error} (capped) plus per-reason counts from gex/surface/flow. Add Dagster asset checks (or raise in runners) with floors against a trailing baseline: rows_written >= 50% of the 10-run median, failure share among names past the onboarding window <= ceiling, a past-onboarding name failing 2+ sessions, mode != skipped twice running. Route check failures through failure_alerts; push persistent per-reason gaps to the Data Gaps ledger.
- **Ratchet**: `test_asset_check_coverage.py` enumerates assets and nightly selected engines; each is checked or explicitly opted out. `test_slot_failure_reasons.py` requires reason metadata and holds bare scheduler `failed += 1` at zero. Runtime evidence comes from `scripts/audit-research-output-gates.sql`, with actual passed/severity fields, not run SUCCESS. ERROR receipt still pending; see RATCHETS.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research

### TD-94

- **交付状态 2026-10-11**：已合入／未发布；最新 main 整合测试及 DEV 验收 PASS。对应提交和部署边界见 `docs/audits/DATA_INTEGRITY_MAIN_INTEGRATION_2026-10-11.md`；生产验收、告警送达、实际恢复及剩余数据缺口按各项条件保留，未据源码合入结债。

**P2 · research-control · Fail-closed husbandry_gate and correct-session checks have passed runtime acceptance**

- **状态**：待你签收
- **验收**：以 READ ONLY `scripts/audit-research-output-gates.sql` 查 gate=pass、expected_session=market_session 且无 override；在装有 orchestration extras 和 dbt manifest 的隔离环境跑 gate / Flex / output / reason 测试，探针失败、缺 timestamp、错误 session 必须阻断。
- **验收结果**：PASS 2026-10-10 Research d628fa6（已有修复 2c34f4d、Flex 分离 72e6473）：56 passed / 0 skipped；生产 gate 模块与测试版本 hash 一致。10-08/09/10 批处理分别关闭 10-07/08/09，doctor session 同步、generated_at 当批生成、没有 allow_unknown。未注入生产故障、未新发版；验收报告见 `docs/audits/TD-92-94_RUNTIME_ACCEPTANCE_2026-10-10.md`。
- **Original Claim (before existing fix)**: Since research a241f30/47af11e (09-28) the gate reads a freshly computed doctor report (refresh=true, 600s timeout), which fixed the stale-session and empty-report runs of 09-16..09-26. What remains: any doctor/Flex probe exception is logged as a warning and the verdict stays 'unknown'; the gate raises only on critical/failed/stale/none, so 'unknown' passes, and no assertion ties doctor.session to the session being closed. dbt and every engine then run with the EOD gate off.
- **Original Measured (before existing fix)**: MEASURED. Before the 09-28 fix: unknown verdicts passed on 09-16, 09-25, 09-26; wrong-session 'healthy' on 09-22 (gated 09-18) and 09-24 (gated 09-22). All 6 runs since 09-29 carry the right session and generated_at. tests/orchestration/test_husbandry_gate.py has no all-probes-fail case.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/plugin_batch_assets.py:148` — `except Exception as exc:  # noqa: BLE001`
  - `bifrost-research/src/bifrost_research/orchestration/plugin_batch_assets.py:169` — `if eod_verdict == "critical":`
- **Original Impact (before existing fix)**: Latent: on a night the plugin is down or doctor computation exceeds 600s, dbt, SEPA and all engines rebuild on a possibly incomplete session and report SUCCESS, the 09-05 'recomputed on partial data' class the gate exists to stop.
- **Original Fix (before existing fix)**: Treat 'unknown' as failure for EOD and Flex checks (raise; explicit override config for manual runs). Compute the expected session via fetch_recent_trading_days and raise when doctor.session differs or generated_at is missing.
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

- **交付状态 2026-10-11**：已合入／未发布；最新 main 整合测试及 DEV 验收 PASS。对应提交和部署边界见 `docs/audits/DATA_INTEGRITY_MAIN_INTEGRATION_2026-10-11.md`；生产验收、告警送达、实际恢复及剩余数据缺口按各项条件保留，未据源码合入结债。

- **Continuity audit 2026-10-10**: isolated Research `cc575bf` and Frontend `c57283ae`; daily enqueue/self-heal acknowledgment, accepted long-row retention and actual output-check visibility verified locally. Research lint + 2286 passed/17 skipped; affected 75 passed/0 skipped, frontend 13 passed + lint/build/CSS, actual DEV CHECKS CAUTION with 30 valid candidates retained. Latest primary 60/90/180 readings present; no backfill/release/real alert. Production rollout, durable alert receipt and full-universe long depth remain open; TD-303/304/305 and `docs/audits/DATA_CONTINUITY_DEFENSES_2026-10-10.md` carry the bounded follow-up.

**P2 · research-data · The 90-day IV cone has 31–39 sessions of history and there is no 180-day tenor: ATM IV was stored only to 90 DTE before 2026-08-05**

- **状态**：在做（2026-10-10）：此前限定批及本次主64父键均实写/DEV验收PASS，三名90/180均≥60；未发布、整债未结，备用未用，追加范围待另批。历史验收及剩余深度/breadth见下列记录。
- **97日只读核查 PASS（2026-10-10）**：96日 historical reference 未挂牌（SPY48/AAPL40/NVDA8），AAPL另1日已挂牌无合格bar；聚合权限/抓取错误0，逐笔无权限不能证明完全无成交。根因是当前catalogue候选/校验没有as_of，见 `scripts/audit-iv-request-scope.py:64`、Plugin `ingest/long_pilot.py:114`。具体替代方案46区间/92合同日/23父键（SPY26/44/11，NVDA8/8/2，AAPL12/40/10），正常75 HTTP、硬上限160；SPY08-10的180–220档无候选保留缺口。报告 `docs/audits/TD-172-142_EMPTY_97_2026-10-10.md`。只读14测试PASS，旧23 raw/209 ATM保持；该提案随后已获批并完成46/92限定执行，见下一行；未发布、未扩大。
- **46/92替代小批验收 PASS（2026-10-10）**：Owner已确认并依次执行SPY→NVDA→AAPL。历史as_of防线在Plugin隔离提交 `cca27d2`，1303 passed/9 skipped；限定实写92 raw /23 ATM /48来源，HTTP75/160；原17821 raw/209 ATM/20937来源全值保持，raw重放HTTP0/新增0、features重放新增0，三名DEV通过。SPY90/180 n35/30→39/33；NVDA44/43、AAPL41/40保持，中期60 n207→208/199→204。TD-172 breadth8653/42775，TD-142 cone90/180 1004/944；仍不足60，不结债。报告 `docs/audits/TD-172-142_REPLACEMENT_2026-10-10.md`。未发布、未扩大，下一批另批。
- **60-session下一批只读盘点 PASS（2026-10-10）**：固定2026-10-09的252日历格子；SPY90/180为39/33、NVDA44/43、AAPL41/40。380本地候选无新增合格ATM，91历史reference GET全200/完整，复用1日，共92日证明；SPY11日180–220档无标准候选保留缺口。主范围64父键/256raw目标日/76合并区间（SPY闸门拆后82执行区间），另9父键/36目标日/26区间备用，潜在66/60、61/60、61/60，新批拟HTTP220。24测试/ruff及DEV只读API一致PASS，原17913raw/232ATM/20985来源全值保持；报告 `docs/audits/TD-172-142_DEPTH_60_PLAN_2026-10-10.md`，当时未实际补抓、主/备用待确认；Owner随后批准并完成下一行限定主范围；未发布、其余548缺读数symbol-day历史目录仍未核实。
- **60-session批准执行验收 PASS（2026-10-10）**：主64父键/256合同日按SPY两日闸门→SPY其余→NVDA→AAPL执行，新增247 raw/64 ATM/129来源；9合同日无合格aggregate仍留缺口，9备用日期未用。SPY90/180 n66/60、NVDA61/60、AAPL61/60，SQL/API/DEV实际页面一致且withheld消失。HTTP152/220（reference67/bars85），全旧186574 raw/1950 ATM/94798来源保持，7/30/60全历史序列保持；accepted-receipt raw重放0HTTP/0新增，feature每阶段重放0。Plugin隔离 `6a5e209` / `7c6b118` / `bc1c8c9`，1315 passed/9 skipped、lint PASS；Research16 passed。SPY HTTP期间事务15s超时已对账恢复并补防线，无重置/重复抓目录。报告 `docs/audits/TD-172-142_DEPTH_EXECUTION_2026-10-10.md`；未发布、未扩大。NVDA >90有效expiry仅60 session，尚未达150，725×59 breadth/短腿未闭合，不结债。
- **验收**：使用 agent_reader 只读复算联合报告固定格子；NVDA >90 DTE 有效 expiry 历史 ≥150 session，SPY/NVDA/AAPL cone90 / cone180 的有效 n ≥60 且 withheld 消失；API/DEV 的 180 档实际出现并一致。先验证核心展示门槛，再公布 n/252 与全部剩余缺格；未达到深度目标不能记整项结清。命令与来源见 `docs/audits/TD-172-142_GAP_PLAN_2026-10-10.md`。
- **本批验收结果**：PASS（本地代码/DEV）2026-10-10：Research `4fe89e8` lint + 2259 passed / 17 skipped；Market Data `01ee6bf` lint + 1299 passed / 9 skipped；Infra 9 passed。SPY/NVDA/AAPL 180 档显示历史不足，短期有效读数保持。限定实写及重放/幂等/原值保留 PASS：合计762 ATM / 1663 来源 / 23 raw；告警接收 NOT VERIFIED。97目标日空响应及有效历史不足尚在，不能结债。
- **Claim**: The ATM IV store kept only expiries up to 90 DTE before 2026-08-05 (the Brent pass is still capped at DTE_MAX = 90), so the cone's 90-day horizon has fewer than MIN_SESSIONS (60) sessions and its percentiles are withheld; there is no 180-day horizon at all. It fills by itself around early November. raw_market.option_daily holds the long-dated bars to backfill from.
- **Measured**: MEASURED 10-06: iv-cone 90d NVDA 39, SPY 31, AAPL 32 sessions; no 180d. raw_market.option_daily: NVDA bars with trades at 150–220 DTE on 154 sessions, earliest 2025-11-10.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/iv_solver.py:53` — `DTE_MAX = 90`
  - `bifrost-research/src/bifrost_research/engines/volatility/atm_iv.py:366` — `AND (o.expiry - o.bar_date) BETWEEN {DTE_MIN} AND {DTE_MAX}`
  - `bifrost-research/src/bifrost_research/repositories/iv_cone.py:36` — `MIN_SESSIONS = 60`
- **Impact**: History's cone withholds 90-day percentiles for every name and has no long tenor for calendars and longer-dated structures.
- **Fix**: 联合计划 `docs/audits/TD-172-142_GAP_PLAN_2026-10-10.md`：先修受限 long-tenor writer / cone180 / 防线，再复用来源，最后 Plugin 受限补抓 + Research 重算。首批 23 名 × 252 session；模拟新增 214 expiry 行（GOOG 74 / SPX 140），SPY/NVDA/AAPL 现有输入不能改善 90 cone，需 vendor 候选 14577 个合约区间。纯 put、无成交、目录未知均不能假造 IV。仅合格目标 feature 主键写入，不能 long-only 输入走整日替换删除；D13。
- **Ratchet**: 隔离代码已补 writer/cone 最长期限契约、存储来源重放、普通重算保留未读取长期行、合法零/缺利率及 append-only 回归；独立长期限有效 breadth warning 已接入，尚未发布或验告警回执。详见 RATCHETS 的 bounded long-tenor repair and continuity。
- 审批 本批已批准，扩大/短腿另批 · 代价 M · 风险 med · repos: bifrost-research

- **Measured 2026-10-10**: 90-day IV cone API still withholds SPY (35 sessions) and NVDA (43), below the 60-session minimum; 7/30-day tenors each have 252. No 180-day tenor is served. Backfill remains subject to the existing approval boundary. Read-only evidence and reproduction: `docs/audits/DATA_INTEGRITY_2026-10-10.md`, `scripts/audit-data-integrity.sql`.

- **联合盘点 2026-10-10**：固定格子首批 5796；现有 / 复用后 cone90 923 → 994、拟 cone180 893 → 935。NVDA 长 bar 存在性不能证明可重算（11-10…14 两个 put、无 call）；SPY 35 / NVDA 43 / AAPL 36 不增加，GOOG 44 → 104。两年 vendor 窗口内的 bar 仍是候选，尚未探测可用性。归档可恢复与从未观察的历史 snapshot/OI 严格分开；方案和 7 项自检见联合报告。验收仍保留 NVDA >90 有效历史 ≥150 的深度目标；≥60 只是 cone 可展示门槛，不能等同完整历史。实际回填与 DEV 复验均未开始。

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

- **Measured 2026-10-10**: CTVA adjusted close still equals unadjusted close through 10-09: 09-30 77.65 → 10-01 12.57. RV20 = 6.48478553 and VRP20 = -5.8814841 on 10-09. Preserve the existing 10-16 review and vendor-adjustment repair decision. Read-only evidence and reproduction: `docs/audits/DATA_INTEGRITY_2026-10-10.md`, `scripts/audit-data-integrity.sql`.

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

- **交付状态 2026-10-11**：已合入／未发布；最新 main 整合测试及 DEV 验收 PASS。对应提交和部署边界见 `docs/audits/DATA_INTEGRITY_MAIN_INTEGRATION_2026-10-11.md`；生产验收、告警送达、实际恢复及剩余数据缺口按各项条件保留，未据源码合入结债。

- **Continuity audit 2026-10-10**: isolated Research `cc575bf` and Frontend `c57283ae`; daily enqueue/self-heal acknowledgment, accepted long-row retention and actual output-check visibility verified locally. Research lint + 2286 passed/17 skipped; affected 75 passed/0 skipped, frontend 13 passed + lint/build/CSS, actual DEV CHECKS CAUTION with 30 valid candidates retained. Latest primary 60/90/180 readings present; no backfill/release/real alert. Production rollout, durable alert receipt and full-universe long depth remain open; TD-303/304/305 and `docs/audits/DATA_CONTINUITY_DEFENSES_2026-10-10.md` carry the bounded follow-up.

**P2 · research-data · ATM IV has almost no 50–90 DTE expiry from 2026-07-06 to 09-25 (the EOD chain stopped at the third listed expiry until plugin 0.39.0); the fix was forward-only, so term structure reads na for that stretch**

- **状态**：在做（2026-10-10）：此前限定批及本次主64父键均实写/DEV验收PASS，三名90/180均≥60；未发布、整债未结，备用未用，追加范围待另批。历史验收及剩余深度/breadth见下列记录。
- **97日只读核查 PASS（2026-10-10）**：96日 historical reference 未挂牌（SPY48/AAPL40/NVDA8），AAPL另1日已挂牌无合格bar；聚合权限/抓取错误0，逐笔无权限不能证明完全无成交。根因是当前catalogue候选/校验没有as_of，见 `scripts/audit-iv-request-scope.py:64`、Plugin `ingest/long_pilot.py:114`。具体替代方案46区间/92合同日/23父键（SPY26/44/11，NVDA8/8/2，AAPL12/40/10），正常75 HTTP、硬上限160；SPY08-10的180–220档无候选保留缺口。报告 `docs/audits/TD-172-142_EMPTY_97_2026-10-10.md`。只读14测试PASS，旧23 raw/209 ATM保持；该提案随后已获批并完成46/92限定执行，见下一行；未发布、未扩大。
- **46/92替代小批验收 PASS（2026-10-10）**：Owner已确认并依次执行SPY→NVDA→AAPL。历史as_of防线在Plugin隔离提交 `cca27d2`，1303 passed/9 skipped；限定实写92 raw /23 ATM /48来源，HTTP75/160；原17821 raw/209 ATM/20937来源全值保持，raw重放HTTP0/新增0、features重放新增0，三名DEV通过。SPY90/180 n35/30→39/33；NVDA44/43、AAPL41/40保持，中期60 n207→208/199→204。TD-172 breadth8653/42775，TD-142 cone90/180 1004/944；仍不足60，不结债。报告 `docs/audits/TD-172-142_REPLACEMENT_2026-10-10.md`。未发布、未扩大，下一批另批。
- **60-session下一批只读盘点 PASS（2026-10-10）**：固定2026-10-09的252日历格子；SPY90/180为39/33、NVDA44/43、AAPL41/40。380本地候选无新增合格ATM，91历史reference GET全200/完整，复用1日，共92日证明；SPY11日180–220档无标准候选保留缺口。主范围64父键/256raw目标日/76合并区间（SPY闸门拆后82执行区间），另9父键/36目标日/26区间备用，潜在66/60、61/60、61/60，新批拟HTTP220。24测试/ruff及DEV只读API一致PASS，原17913raw/232ATM/20985来源全值保持；报告 `docs/audits/TD-172-142_DEPTH_60_PLAN_2026-10-10.md`，当时未实际补抓、主/备用待确认；Owner随后批准并完成下一行限定主范围；未发布、其余548缺读数symbol-day历史目录仍未核实。
- **60-session批准执行验收 PASS（2026-10-10）**：主64父键/256合同日按SPY两日闸门→SPY其余→NVDA→AAPL执行，新增247 raw/64 ATM/129来源；9合同日无合格aggregate仍留缺口，9备用日期未用。SPY90/180 n66/60、NVDA61/60、AAPL61/60，SQL/API/DEV实际页面一致且withheld消失。HTTP152/220（reference67/bars85），全旧186574 raw/1950 ATM/94798来源保持，7/30/60全历史序列保持；accepted-receipt raw重放0HTTP/0新增，feature每阶段重放0。Plugin隔离 `6a5e209` / `7c6b118` / `bc1c8c9`，1315 passed/9 skipped、lint PASS；Research16 passed。SPY HTTP期间事务15s超时已对账恢复并补防线，无重置/重复抓目录。报告 `docs/audits/TD-172-142_DEPTH_EXECUTION_2026-10-10.md`；未发布、未扩大。NVDA >90有效expiry仅60 session，尚未达150，725×59 breadth/短腿未闭合，不结债。
- **验收**：使用 agent_reader 只读复算 725 个回溯标的 × 59 个 NYSE session；每周 50–100 DTE 有效 breadth ≥0.85，另列真实 TERM 与 strict cone60，整日缺失保留分母。历史合法排除需证据/Owner 签收，不以已有 ATM 行缩分母。逐格清单和实际回填/DEV 验收标准见 `docs/audits/TD-172-142_GAP_PLAN_2026-10-10.md`。
- **本批验收结果**：PASS（本地代码/DEV）2026-10-10：Research `4fe89e8` lint + 2259 passed / 17 skipped；Market Data `01ee6bf` lint + 1299 passed / 9 skipped；Infra 9 passed。SPY/NVDA/AAPL 180 档显示历史不足，短期有效读数保持。限定实写及重放/幂等/原值保留 PASS：合计762 ATM / 1663 来源 / 23 raw；告警接收 NOT VERIFIED。97目标日空响应及有效历史不足尚在，不能结债。
- **Claim**: Until market-data plugin 0.39.0 (2026-09-25, `54b05be`) the EOD chain was bounded at the third listed expiry, so from 2026-07-06 most names' option_daily held nothing past ~45 DTE. ATM IV is solved from option_daily (Brent) and the reconstructed table, so its 50–100 DTE expiries went missing with it. 0.39.0 fixed the bound forward only; nothing refilled the stretch. IV30 is unaffected (about 640 names a day throughout).
- **Measured**: MEASURED 10-06 (S6 context survey, `REPORT-pine-s6-context-series-2026-10-06.md`). Share of universe name-days with an ATM IV at 50–100 DTE, by week: 06-22 0.88 · 06-29 0.91 · 07-06 0.15 · 07-13 0.12 · 08-03 0.02 · 08-10 0.02 · 08-24 0.35 · 09-14 0.43 · 09-21 0.59 · 09-28 0.97. option_daily itself with a 50–90 DTE bar: 06-22 0.99 · 07-06 0.25 · 08-10 0.005.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/atm_iv.py:366` — `AND (o.expiry - o.bar_date) BETWEEN {DTE_MIN} AND {DTE_MAX}`
  - `bifrost-research/src/bifrost_research/engines/pine/context.py` — `TERM_30_60` reads na without a 50–120 DTE expiry (Owner 10-06: no stitching from SVI)
  - market-data plugin `54b05be` — "The EOD chain's bound was the third listed expiry"
- **Impact**: Pine `TERM_30_60` (S6) and every term-structure reader (`/atm-iv/term`, the 60-day cone) are blank or one-sided for 12 weeks, which is part of the S6 out-of-sample window (2026-01..10); a contango condition loses that stretch.
- **Fix**: 先确认 `docs/audits/TD-172-142_GAP_PLAN_2026-10-10.md` 的联合范围：复用已有源，受限 Plugin 重抓历史后腿，Research 重算；先 3 名 × 5 session，再按周扩大。固定格子另有 5261 个无 IV30 前腿的 symbol-day，短腿追加请求需另核范围/预算，不能只抓后腿宣布 TERM 完整。已有 snapshot 按观察日/质量复用，不以当前 snapshot 假写历史。Plugin 写 raw_market，Research 写 features；禁止 long-only 输入直接走整日 ATM replacement。
- **Ratchet**: 2026-10-10 隔离代码新增 Plugin 50–220 long-breadth / Research 有效 bracket 警告、writer/cone 最长期限契约、来源重放与普通 producer 长期保留；回归已通过。线上旧 contracts 仍仅 5–90，未发布、告警接收 NOT VERIFIED，不能把实现当运行闭环。详见 RATCHETS 的 bounded long-tenor repair and continuity。
- 审批 本批已批准，扩大/短腿另批 · 代价 M · 风险 low · repos: bifrost-platform-plugin-market-data, bifrost-research

- **Measured 2026-10-10**: 50–100 DTE ATM-IV name-days remain 59/3223 (1.8%) for week 08-03 and 64/3159 (2.0%) for 08-10, versus 3229/3469 (93.1%) for 10-05. Forward collection recovery did not restore historical completeness. Read-only evidence and reproduction: `docs/audits/DATA_INTEGRITY_2026-10-10.md`, `scripts/audit-data-integrity.sql`.

- **联合盘点 2026-10-10（替代旧已有 ATM 行分母）**：725 × 59 = 42775 个回溯当前名单格子；原 breadth 8437（19.72%），复用后 8643（20.21%）；TERM 8535 → 8767，strict cone60 6421 → 6872。08-03 / 08-10 固定周分母 3625，分别 59（1.63%）/64（1.77%），整日缺失不再从分母消失。TD-172 可新增 682 expiry 行，TD-142 214，其中 SPX 140 重叠，联合只有 756 行。请求联合去重 66649 个区间 / 161863 个目标 contract-day；历史挂牌与 vendor 响应未验证。详细条件、试批、限流/失败重试、未知/不可原样补回分类和验收见 `docs/audits/TD-172-142_GAP_PLAN_2026-10-10.md`；Owner 已批准第一批三步，第 4 项限定三步已实写验收，最终TD-142 cone90/180为1000/941，TD-172 breadth8643/42775；完整度仍不足，扩大另批。

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

- **交付状态 2026-10-11**：已合入／未发布；最新 main 整合测试及 DEV 验收 PASS。对应提交和部署边界见 `docs/audits/DATA_INTEGRITY_MAIN_INTEGRATION_2026-10-11.md`；生产验收、告警送达、实际恢复及剩余数据缺口按各项条件保留，未据源码合入结债。

**P3 · market-data · W3 snapshot archives are verified readable, but typed restore and first option_daily / short_volume archives remain unverified**

- **状态**：观察中（2026-10-10 只读核查及恢复验收准备完成；实际恢复未运行；到 11-01 看 option_daily / short_volume 首次非零归档并分别验收）
- **验收**：10-08 与 11-01 的 trim 日志里，每张表 `archived_rows == deleted_rows`，归档文件在 NAS `nfs-cold` 上可读、行数与日志一致；没做完的行留在库里，不被删
- **现在**：运行 image 0.87.1，NAS archive PVC Bound / 实际挂载可读。10-09 与 10-10 已分别归档 09-08 的 230144 行、09-09 的 343682 行 intraday snapshot，归档与删除行数一致；SHA-256、字节数、manifest/ledger、19 列全量解码、日期及主键摘要检查 PASS。10-08 cutoff=09-08（exclusive）所以合法零行。两张 dated 表最早日期都是 2024-10-01，当前 cutoff=2024-10-01，尚无合格过期行；不是归档失败。
- **验收结果**：部分 PASS 2026-10-10（隔离分支 codex/td-183，基线 25cb2f1）：两文件共 573826 行只读验证；五项离线异常测试 PASS。恢复执行 NOT RUN；不关闭债、不宣称三表恢复已验收。详见 `docs/audits/TD-183_ARCHIVE_READINESS_2026-10-10.md`。
- **下一步**：按报告中的隔离本机 typed restore 方案验证全字段 readback 与幂等（此轮仅准备，未运行）。11-01 实测两张 dated 表首批非零归档、耗时及预算耗尽状态，分别验恢复；不沿用旧的约 180 万行估计作为当前任务范围。全部通过后才处理原 REQUEST 归档。
- **Claim**: Actual intraday snapshot archives have passed read-only checks, but no typed restore/readback has been performed for them, and option_daily/short_volume have not yet reached their first nonzero archive. option_snapshot is not reproducible from the vendor after its window, so recoverability requires evidence beyond successful trim metadata.
- **Evidence**:
  - `/stocks/REQUEST-w3-archive-before-delete-2026-10-05.md:20` — `option_snapshot 盘中行 | 2026-09-08 | 约 10-08 02:15 UTC（30 天窗口）`
  - `/stocks/REQUEST-w3-archive-before-delete-2026-10-05.md:21` — `option_daily | 2024-10-01 | 11-01 02:15 UTC`
- **Impact**: Irreversible loss of option snapshots if the first real archive fails silently.
- **Fix**: Watch the two runs; if archived and deleted counts differ, hold deletion (`retention_hold`) and fix before the next night.
- **Ratchet**: Runtime archive_range already refuses read/file/delete count mismatches and rolls back. The new read-only verifier refuses corrupt/missing/inconsistent archive evidence and duplicate PK digests; its five fixture tests are manual, not a production or CI blocking gate. Hold still takes precedence; actual typed restores and future dated-table acceptance remain required.
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

- **状态**：在做（修复在 platform 分支 `w31/w48-s0-0a`，分支头 `65c0054`（修复本身在 `249618e`），S0-0a / W-48：暂时性拒绝——发布窗口被占或缺失、HTTP 429 / 503、kube 超时——让单子保持 `approved`，按退避重试到执行截止时间；永久错误照旧失败。测试 `api/internal/approvals/state_machine_test.go` `TestTransientRefusalKeepsTheApproval`、`api/internal/server/transient_refusal_test.go`。须与 infra `w31/w48-s0-0a-infra` `779c70f` 一起合。合 main + 发版后转待你签收）
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

- **状态**：在做（修复在 platform 分支 `w31/w48-s0-0a`，分支头 `65c0054`（修复本身在 `249618e`），S0-0a / W-48：apply 的 run 改名 `apply-<plan>-<unix>` 并带 `bifrost.io/plan` 标签，同一 plan 重试会新建 run。测试 `api/internal/workactions/apply_retry_test.go`。合 main + 发版后转待你签收）
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
- **Claim**: Objects first applied by hand (client-side) keep their fields under `kubectl-client-side-apply`. The applier's server-side apply then conflicts on any changed field. Measured 2026-10-10: `plan-ee6f0ba5-1791604913` for `k8s/ib-gateway/overlays/live` — `conflict with "kubectl-client-side-apply" … .containers[name="ib-gateway"].image`; the Owner applied it by hand. Again 2026-10-15: `plan-7c2ff929-1792125862` (ib-gateway 0.4.1, plugin `7c2ff92`), same conflict on the same field; the Owner applied `overlays/live` by hand with the admin kubeconfig at 04:46Z. Each hand apply keeps the field under `kubectl-client-side-apply`, so every ib-gateway release needs the Owner's terminal until this is fixed.
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

- **状态**：待你签收
- **验收结果**：PASS 2026-10-10 c6fa1c1（Owner 06:04Z helm upgrade，revision 17；`check_monitoring_persistence.py --live` 退出 0，两个卷 Bound 在 `nfs-hot`；06:09:34Z 用 `delete_pod` 删掉 Prometheus Pod，新 Pod 在 ubt-k3s-04 起来，WAL 重放 0.9 秒，`count(up offset 4m)` 仍返回 75，最早样本仍是 06:04:28Z）；观察期收口 PASS 2026-10-11 1d69669（14:01Z 只读核查：Pod 自 10-10 06:09:43Z 起运行 31 小时，重启 0 次；`logs --since=30h` 读到 114 行，全部 `level=INFO`，WARN / ERROR 0 行，`corrupt` / `stale file handle` / `no space` 0 命中，compaction 与 WAL checkpoint 记录 50 行；`prometheus_tsdb_compactions_total` 20，`compactions_failed_total`、`wal_corruptions_total`、`head_truncations_failed_total`、`wal_truncations_failed_total` 均为 0；`count(up offset 20h)` 75；`check_monitoring_persistence.py --live` 退出 0）
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
- **追加（2026-10-11 17:32，只读实测，没有试写）**: the same unrestricted write covers Argo CD's own configuration. MEASURED with the agent identity: ClusterRole `bifrost-platform-state` (bound in `cicd` to `bifrost-platform-prod/bifrost-platform`) grants `configmaps` `create` / `update` / `patch` with no `resourceNames`; Role `cicd/tekton-deliver-argocd` grants `cicd/tekton-deliver` the same three verbs with no `resourceNames`; `kubectl get cm -n cicd` lists `argocd-cm`, `argocd-rbac-cm` and `argocd-cmd-params-cm`. Whoever holds either account can therefore rewrite Argo CD's RBAC policy and settings — a second path from an ordinary platform identity to a cluster-admin-level one, next to TD-314 (Deployment templates). NOT MEASURED: that such a write is admitted (not tried, must not be), and whether Argo CD picks the change up without a restart. The fix above (names only) closes it for the platform accounts; `tekton-deliver` needs the same treatment — list which ConfigMaps the delivery pipelines really write (the release window, the receipts) and grant those names only. The release-freeze protocol design (`work/multi-agent/DESIGN-release-freeze-protocol-2026-10-11.md`) does not claim "the platform's account, used directly, cannot lift a freeze" while this and TD-314 are open.
- **Claim**: W-42 put the signed release policy (`bifrost-release-policy`), the freeze (`bifrost-release-freeze`) and the release window (`bifrost-release-window`) in `cicd`. platform-api is meant to be the only writer, and unfreezing needs an Owner signature over `frozen_at`. But the ClusterRole bound to both platform service accounts in `cicd` grants configmap writes with no `resourceNames`. A patch straight to the ConfigMap (`frozen=false`, or a different window holder) skips the signature check: the policy survives because platform-api re-verifies its signature, the freeze and the window do not. The STG account can write the same ConfigMaps PROD reads, although STG only observes releases.
- **Evidence**: `bifrost-trade-infra/k8s/platform-rbac/00-clusterroles.yaml:86-93` (`bifrost-platform-state`: configmaps `get, list, watch, create, update, patch`, no `resourceNames`), bound in `cicd` by `k8s/platform-rbac/10-stg.yaml:127-134` (SA `bifrost-platform` in `bifrost-platform-stg`) and `k8s/platform-rbac/20-prod.yaml:127-134` (PROD); `00-clusterroles.yaml:155` adds `update, patch` on configmaps for the Gitea creds role. Freeze logic: `bifrost-platform/api/internal/releasepolicy/handler.go:72`, `actions/catalog.go:130-141`.
- **Fix**: give the platform accounts in `cicd` only the names they write: a Role with `resourceNames` for update/patch of `bifrost-release-policy`, `bifrost-release-freeze`, `bifrost-release-window` and the record ConfigMaps (PROD only); `create` cannot be limited by name, so either keep platform-created ConfigMaps under a fixed name list created once by the applier, or add a ValidatingAdmissionPolicy that refuses platform-SA writes in `cicd` outside a name/label allow list. The STG account loses write in `cicd` (TD-223 already stopped STG writing release records).
- **Ratchet**: extend `scripts/check_platform_rbac.py` with "should not" rows: as each platform SA, `patch configmaps/bifrost-release-freeze` and `create configmaps` with an unlisted name in `cicd` are denied (STG: every configmap write in `cicd` denied).
- 验收: `make check-platform-rbac` with the new rows → all pass on the cluster; `kubectl auth can-i patch configmap/bifrost-release-freeze -n cicd --as=system:serviceaccount:bifrost-platform-stg:bifrost-platform` → no.
- 审批 要批（改集群 RBAC，apply_manifest）· 代价 M · 风险 med（漏一个名字会让 platform 写记录 403）· repos: bifrost-trade-infra

### TD-294

**P3 · infra · The Tekton freeze check only runs in pipelines that start with release-window; the Trade and platform deliver pipelines and three build pipelines do not, so a run created outside platform-api ignores a freeze**

- **状态**：在做——2026-10-11 12:39 Owner 已把冻结检查应用到集群（13 条流水线的唯一入口都是它，与文件逐条一致，只读核对过）；当天补了一条只读绑定让 apply 流水线的身份也能读冻结对象（`0cc8c19`，教训第 78 行）；干跑和一次测试环境发布都在检查处通过。2026-10-11 12:56 做了演练：「拦得住」一半通过（平台入口 409；流水线在检查处失败，后面的步骤没跑），「解得开」一半没通过——签名解冻走不通（TD-310），由 Owner 手工解开。**TD-310 修完、演练重做通过之前不进待签收。**此前（W-56 第 1 步 B 片 `d5f4cc1` 给本仓库十一条流水线加了故障即拒的冻结检查；同日 flex-query 那条也接上，`bifrost-platform-plugin-flex-query` `bf6c61c`，已知缺口清单清空；Codex 复核 36–48、58。剩下的是按 `docs/RELEASE.md`「冻结检查」的顺序应用，和下面验收里的冻结演练，两样都要 Owner。此前：W-42 交回 10-10。交回原话「flex-query 构建流水线没有发布窗口任务」实测不成立：`bifrost-platform-plugin-flex-query/k8s/cicd/pipeline-build.yaml:27` 与集群上 `bifrost-build-flex-query` 的第一个 task 都是 `release-window`，跑在已绑定读权限的 `default` SA 下，apply 新 task 后就带冻结检查）
- **Claim**: W-42 added the freeze check to `task-release-window.yaml`, so it runs only where that task is the first task: `bifrost-build-research-dagster`, `bifrost-build-ib-gateway`, `bifrost-build-market-data`, `bifrost-deliver-research` and (from its plugin repo) `bifrost-build-flex-query`. `bifrost-deliver-stg`, `bifrost-deliver-prod`, `bifrost-deliver-platform`, `bifrost-deliver-platform-prod`, `bifrost-build-stg`, `bifrost-build-frontend-stg` and `bifrost-build-research-pine` have no such task: a freeze stops them only when they are started through platform-api (`start_pipeline_run`, refused with 409). A run created another way — the Owner's `kubectl create -f` from `prod-pinned-from-stg.sh` / `platform-prod-pinned-from-stg.sh`, or tekton-trigger (TD-272) — runs while frozen.
- **Evidence**: `rg -l release-window bifrost-trade-infra/k8s/cicd/tekton/pipeline-*.yaml` → 4 files; first tasks `pipeline-deliver-stg.yaml:40` `mirror-sync`, `pipeline-deliver-prod.yaml:59` `preflight-stg`, `pipeline-deliver-platform.yaml:34` `mirror-sync`, `pipeline-deliver-platform-prod.yaml:37` `preflight-stg`; freeze step `k8s/cicd/tekton/task-release-window.yaml:175-205`; platform-side gate `bifrost-platform/api/internal/server/actions_wire.go:37`.
- **Fix**: a freeze-only task (reads `bifrost-release-freeze` only; the window stays with `release.sh` for Trade and platform) as the first task of those seven pipelines, run under the SA each pipeline already uses (`tekton-deliver` and `default` are bound to `tekton-release-window`).
- **Ratchet**: `scripts/check-release-chain.py` gains an assertion driven by `agent-config/release-policy/template.json` `allow` plus the build pipelines: each one's first task is `release-window` or the freeze-only task; a pipeline whose YAML is not found fails rather than skips (same rule as the TD-263 check).
- 验收: `python3 scripts/check-release-chain.py` passes with the new assertion; a frozen drill: `kubectl create` of a pinned PROD run is refused by its first task.
- 审批 要批（apply 七条 Tekton 流水线到 cicd）· 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-296

**P2 · ops-platform · The ntfy connection error text carries the full topic (the read credential) and is served by the token-less relay status endpoint; with W-49 it would also reach approval delivery records**

- **状态**：在做（W-49 审计 10-10 发现；掩码已在 platform 分支 `w31/w49-s0-0b` `56b12b2`，防线 `api/internal/alertrelay/relay_test.go` `TestNotifyFailureNamesTheReasonWithoutTheTopic`。关闭条件：合 main + 重新部署 .50 operator-plane + ntfy topic 由 Owner 在 S0-0c 准备时更换（Owner 10-10 定），并入 S0-0c / W-50）
- **Claim**: The relay posts to `NtfyURL + "/" + Topic`. When the request fails, Go's HTTP client error quotes the whole URL (`Post "<ntfy>/<topic>": …`), so the error text contains the topic. Anyone who knows the topic can subscribe and read every push. That text is kept as `lastErr` and returned as `last_error` by `GET /alerts/relay`, which takes no token. W-49 adds per-target delivery results to `POST /alerts/notify` and stores them on the approval (`deliveries[].error`), so without the mask the topic would also land in request records.
- **Evidence**: `bifrost-platform/api/internal/alertrelay/relay.go:46` (topic is the read credential), `relay.go:371` (URL built with the topic), `relay.go:395` (`r.lastErr = err.Error()`), `relay.go:417` (`last_error` in the status body), `relay.go:116` (`GET /alerts/relay` route); read on platform main `66496a6`.
- **Fix**: Mask the topic out of every transport error before it is stored or returned (done on W-49: the target is reported as a hash, the error names the reason without the topic). The Owner rotates the ntfy topic while preparing S0-0c (decided 2026-10-10), so any topic that already reached the status endpoint stops working.
- **Ratchet**: `TestNotifyFailureNamesTheReasonWithoutTheTopic` (a failing ntfy post answers a delivery whose error and target do not contain the topic).
- 验收: `cd bifrost-platform/api && go test ./internal/alertrelay/ -run 'TestNotify' -count=1`; after the .50 operator-plane redeploy, `GET /alerts/relay` on .50 shows no topic in `last_error` and the build carries the W-49 commit; the Owner has rotated the topic and a test push reaches the phone on the new one.
- 审批 要批（凭据面：.50 operator-plane 重新部署是 Owner 本机操作）· 代价 S · 风险 low · repos: bifrost-platform

### TD-297

**P3 · ops-platform · Platform CI runs no race detector and no MCP tests, so the approval state machine's concurrency tests and the 批 #n tool tests are only run by hand**

- **状态**：未开始（W-31 S0-0 登记 10-10 发现；归 S0-0 收尾，W-48 合 main 后做，见 STEP0-PLAN 0.8 节）
- **Claim**: `bifrost-ci-platform` runs `go test ./... -count=1` without `-race`, and its only Node step is the Console type-check; `mcp/platform` (which has `npm test` = `node --import tsx --test src/*.test.ts`) is never installed or tested. W-48's concurrency tests (`TestConcurrentCreatesGetDistinctNumbers`, `TestConcurrentClaimsOnlyOneWins`) pass without the race detector even when a data race exists, and W-51's `approve.test.ts` (the 批 #n refusals that must send nothing) runs only when someone runs it locally. On 10-10 the race and MCP results came from the chief of staff's manual runs.
- **Evidence**: `bifrost-trade-infra/k8s/cicd/tekton/pipeline-ci-platform.yaml:115` (`go test ./... -count=1 -timeout=120s`, no `-race`), `pipeline-ci-platform.yaml:94` (`golang:1.25-bookworm`: gcc present, so `-race` needs no image change), `pipeline-ci-platform.yaml:127-155` (`npm-type-check`: `console` only, `npx tsc --noEmit`); `bifrost-platform/mcp/platform/package.json:10` (`"test"` script).
- **Fix**: In `pipeline-ci-platform.yaml`, after `go test ./...` add `go test -race -count=2 ./internal/approvals/ ./internal/approvalnotify/ ./internal/alertrelay/` (CGO is on in the bookworm image; keep the 120s timeout or raise it for the race run). Add a step on `node:20-slim` that runs `cd bifrost-platform/mcp/platform && npm ci && npm test` (and `npm run type-check`).
- **Ratchet**: The CI pipeline itself, once the steps exist. The RATCHETS rows for the W-48 concurrency tests and the W-51 MCP tests move from "manual race" to warning, and a check that `pipeline-ci-platform.yaml` still contains `-race` and `mcp/platform` keeps the steps from being dropped.
- 验收: a `ci-platform` run on the merge commit shows the race step over the three packages and the MCP `npm test` step, both green; a deliberately racy test on a scratch branch fails the race step.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-298

**P1 · agent-governance · Cursor never loaded the project hooks: it refuses a hooks.json reached through the workspace's .cursor symlink, so preflight.js did not gate Cursor sessions (proven back to 2026-09-28)**

- **状态**：观察中（到 10-17，看 hooks 日志是否每次都有 `Loaded … user hook(s)`、有没有误拦。10-10 已修并实测：`~/.cursor/hooks.json` 由 `agent-config/cursor/install-hooks.py` 生成，日志 14:54:28Z `Loaded 3 user hook(s) for steps: beforeShellExecution, beforeMCPExecution, stop`，不用重载窗口；在临时空仓库里 `git add -A` 被拦，日志里 `"permission": "deny"`；`node scripts/agent-guard/test.js` 136 / 136）
- **Claim**: The workspace's `.cursor` is a symlink to `bifrost-trade-infra/agent-config/cursor`. Cursor refuses a project `hooks.json` reached through a symlink below the workspace root, and no user-level `~/.cursor/hooks.json` existed, so neither `beforeShellExecution` nor `beforeMCPExecution` ran `preflight.js` in Cursor. Every Cursor session (and every Cursor subagent) ran with no mechanical gate: D10, shared-worktree staging, dev-service, approval-bypass and token-file rules held only as far as the agent followed the written rules. `check-agent-config-parity.sh` only checked that the project file named `preflight.js`, so it stayed green the whole time.
- **Measured**: MEASURED 2026-10-10 in Cursor's hooks logs. Every retained session log (10 sessions, 2026-09-28 to 2026-10-10) has `Refusing to load Project hooks.json via symlink below workspace root: …/stocks/.cursor/hooks.json`, `ERROR: Failed to parse project hooks configuration` and `No user hooks configuration found`. The oldest retained log starts 2026-09-28T17:33Z and already refuses; Cursor keeps only the last 10 sessions, so nothing earlier can be checked. The symlink dates from 2026-08-27; whether Cursor loaded it before 09-28 is unknown.
- **Evidence**:
  - `~/Library/Application Support/Cursor/logs/20260928T123318/window1_wb1/output_20260928T123321/cursor.hooks.workspaceId-*.log` — the first refusal (2026-09-28T17:33:28Z)
  - `~/Library/Application Support/Cursor/logs/20261010T012527/window1_wb1/output_20261010T012531/cursor.hooks.workspaceId-*.log` — the last refusal before the fix, then `Loaded 3 user hook(s)` after it
  - `bifrost-trade-infra/agent-config/scripts/check-agent-config-parity.sh` §5 — checked the project file's content, not whether Cursor loads it
- **Impact**: For at least 12 days, Cursor sessions could have run `git add -A`, touched guard files, written `ib:operator:cmd` or read token files with nothing to stop them except the rules text. Codex (W-35 / W-36) and Claude (`claude/settings.json`) were gated; Cursor was the gap. Cursor also refuses the symlinked `.claude/settings.json` it would read for compatibility; that does not matter once its own user-level hooks load.
- **Fix**: Option A (done): `agent-config/cursor/install-hooks.py` renders `cursor/hooks.json` into the real file `~/.cursor/hooks.json`, with script paths and `node` made absolute (user hooks run from `~/.cursor`). Idempotent; entries that run a script named in the template are replaced, the user's other hooks are kept and listed; the old file is backed up. Re-run it when the template changes (W-54's heartbeat hooks). Not chosen: B, making `.cursor` a real directory, breaks the single-source layout every other governance file uses (all workspace-root entries are symlinks into `agent-config`, versioned in infra) and would need its own sync; C, the enterprise path `/Library/Application Support/Cursor/hooks.json`, needs root on the host, applies to every user and is an Owner host operation for a per-user problem. A consequence of A: user-level hooks apply to every Cursor workspace on this machine, so `preflight.js` also gates non-Bifrost projects opened here; accepted, the machine is the Bifrost workstation.
- **Ratchet**: `check-agent-config-parity.sh` §5 runs `install-hooks.py --check` on a machine that has `~/.cursor` (skipped when `CI` is set) and warns when `~/.cursor/hooks.json` is missing or differs from the rendered template.
- 验收: `python3 bifrost-trade-infra/agent-config/cursor/install-hooks.py --check` exits 0; the newest `cursor.hooks.workspaceId-*.log` shows `Loaded … user hook(s)` and no `No user hooks configuration found`; in a scratch git repo a Cursor agent's `git add -A` is refused.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

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

- **交付状态 2026-10-11**：已合入／未发布；最新 main 整合测试及 DEV 验收 PASS。对应提交和部署边界见 `docs/audits/DATA_INTEGRITY_MAIN_INTEGRATION_2026-10-11.md`；生产验收、告警送达、实际恢复及剩余数据缺口按各项条件保留，未据源码合入结债。

**P3 · frontend · Symbol faces hide GEX levels that exist when zero gamma is NULL: the dealer level strip needs all four values and the regime cell needs zero gamma, so a chain with no flip (about a third of expiries) shows neither walls nor regime**

- **状态**：在做（Owner 已看过 DEV 结果；代码已提交隔离分支，未合并/未发布）
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

- **本轮结果**：2026-10-10，隔离 worktree `codex/td-274`（frontend 提交 `43477399`，未合并/未发布）。Dealer 按现有价格/墙位独立绘制；Chain、face extras、daily History 共用 Research NULL 语义，regime 按 total_net_gex 符号；缺行/失败不冒充 no flip，未知日中断连续计数。Intraday 未套用日线规则。
- **验收结果**：PASS 2026-10-10 `43477399`（DEV 页面已由 Owner 看过；提交前定向复跑 24/24；记录 `bifrost-trade-frontend/docs/acceptance/TD-274.md`）。未发布，因此保留条目，不记作已还。
- **DEV 验收**：PASS 2026-10-10，Vite :5173 → DEV :30882：AAL no flip + walls 12/14，APT no flip + put wall 6 + no call exposure，AA numeric flip 47.5，ZZQ 无数据不生成 no-flip 读数；daily History 和 Chain 显示核对通过。Instances / Live / Ledger 冒烟完成（Live 当前无实时 marks）。
- **自检与防线**：全套 Vitest 550 files / 4136 passed / 1 skipped；TD-274 定向 24 passed；lint 0 errors（67 existing warnings）；build 与 check:legacy-css PASS。新增 helper、Dealer、History/Chain 渲染用例覆盖 no flip、单侧墙、缺数据、失败缓存与连续计数。公开 API/依赖无变化。

### TD-300

**P3 · market-data · Doctor reports recovered failures as trimmed records and hides retained error evidence**

- **状态**：未开始
- **Claim**: The actionable-failure query excludes jobs with a newer same-payload attempt. An empty actionable sample is then described as trimmed historical rows, even when the original failed rows survive and all retries succeeded.
- **Evidence**: `bifrost-platform-plugin-market-data/src/bifrost_market_data/doctor.py:1962` excludes newer attempts; `:1998` infers trimming from the empty sample. Read-only 10-10 SQL finds 131 retained HTTP 401 failures, each with a newer `done` job by 02:30:34Z; cached DEV Doctor says rows were trimmed. See `docs/audits/DATA_INTEGRITY_2026-10-10.md` and `scripts/audit-data-integrity.sql`.
- **Fix**: Distinguish retained historical failures, recovered jobs, actionable retries, deleted records and query failure. Do not infer retention loss from the actionable sample or treat a successful zero-bar response as proved data loss.
- **Ratchet**: Extend `tests/test_doctor.py` with retained-all-recovered, actually-trimmed, still-actionable and query-failure cases; keep the TD-281 retry filter.
- **验收**: `uv run pytest tests/test_doctor.py` passes; DEV `/market/doctor?probes=false` explains retained/recovered records separately from retry candidates and never says trimmed solely because all retries succeeded.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-301

**P3 · research-data · Term-slope data reaches the exhibit but cannot drive screening**

- **状态**：未开始
- **Claim**: Fresh fitted expiries support a one-name near/far slope, but the screen reader still marks the lens unscreenable with “no set-based reader yet”.
- **Evidence**: `bifrost-research/src/bifrost_research/lenses/screen.py:98`; `lenses/exhibit_lenses.py:229` computes the exhibit. DEV AAL 10-09 has eight fits, near 28 DTE / far 70 DTE and slope -0.00350481; daily surface has 700 names. See `docs/audits/DATA_INTEGRITY_2026-10-10.md`.
- **Fix**: Add a set-based term-fit reader using the exhibit's selection and sign convention. Missing far/near fit stays unknown; real zero remains flat. Use consistent session dates.
- **Ratchet**: Batch/exhibit parity tests for positive, negative, flat and missing-fit cases, and coverage/filter membership tests.
- **验收**: `uv run pytest tests/ -k 'screen or term_slope'` passes; DEV coverage makes term_slope screenable, and AAL's screen reading matches its exhibit for the same session.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research

### TD-302

- **交付状态 2026-10-11**：已合入／未发布；最新 main 整合测试及 DEV 验收 PASS。对应提交和部署边界见 `docs/audits/DATA_INTEGRITY_MAIN_INTEGRATION_2026-10-11.md`；生产验收、告警送达、实际恢复及剩余数据缺口按各项条件保留，未据源码合入结债。

**P2 · research-data · IV coverage counts warm-up NULL scores as readable and exhibits omit the reason**

- **状态**：观察中（隔离分支 codex/td-302 已提交：Research d628fa6、Frontend fda32827；测试与本机 DEV 已验收，未合并/未发布；不视为生产数据修复完成）
- **Claim**: `_latest_column` returns NULL values and `_read_lens` creates readings for all stored rows; coverage counts dictionary entries, not usable scores. Freshness and a present row conceal the 126-session warm-up requirement.
- **Evidence**: `bifrost-research/src/bifrost_research/lenses/screen.py:102`, `:241`, `:292`; `engines/volatility/iv_percentile.py:37` has the correct 126-session gate. DEV reports 702/725 rank and percentile coverage; latest seven-day rows have only 631 numerical scores (71 NULL). APT has two sessions and a fresh NULL-score exhibit with empty caveats. See `docs/audits/DATA_INTEGRITY_2026-10-10.md` and `scripts/audit-data-integrity.sql`.
- **Fix**: Count usable numerical readings, preserve valid zero, and give the existing exhibit caveat path a concrete warm-up/insufficient-history reason. Distinguish an absent row from a present but withheld score. Do not weaken the engine's history gate or fabricate scores.
- **Ratchet**: Regression tests for absent rows, present NULL warm-up rows, numerical zero and fully measured readings; coverage denominators, missing membership and exhibit caveats must agree.
- **验收**: `uv run pytest tests/ -k 'screen or iv_rank or iv_percentile'` passes; for this fixed snapshot coverage equals 631 usable readings rather than 702 stored rows, and APT explains insufficient history. Future snapshots must agree with contemporaneous non-NULL SQL, not hard-code 631.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

- **Implementation 2026-10-10**: Latest-row usable-value filtering preserves zero and unbanded categories. Both IV exhibits explain warm-up versus missing rows; Symbol Volatility consumes authoritative Research scores rather than rebuilding scores from two history sessions. Acceptance record: `bifrost-research/docs/acceptance/TD-302.md`. Research full tests 2150 passed / 30 skipped; targeted tests 47 passed. DEV coverage 631/725 per IV lens; APT 2/126 withheld, ZZQ missing, AU 0/Cold. Frontend full rerun PASS: 548 files / 4120 passed / 1 skipped (two first-run timeout cases recovered with lower concurrency); build and CSS check PASS, lint 0 errors and changed-files lint clean. No release or data repair.

### TD-299

**P2 · ops-platform · Tekton keeps every run (545 PipelineRuns and 3958 TaskRuns in cicd since 2026-10-03) and nothing prunes them; with the finished pods gone after the rolling reboot, the controller's periodic resync errors on each old TaskRun and a new run waited 4 min 21 s for its pod**

- **状态**：未开始（决策线程 10-10 建 W-38 部署单时撞上；长期方案见 W-60，Owner 已定保留期的起点值）
- **Claim**: No CronJob, Tekton pruner or platform job deletes finished PipelineRuns or TaskRuns in `cicd`. The 2026-10-10 rolling reboot drained every node, which deleted the pods of finished TaskRuns. The Tekton controller (knative) re-reconciles every object 10 hours after it starts; each finished TaskRun then fails with `pods "<name>" not found` and is requeued, and new TaskRuns wait behind them.
- **Measured**: MEASURED 2026-10-10 (Claude, read-only kubectl). `cicd`: 3958 TaskRuns, 545 PipelineRuns, oldest `bifrost-deliver-stg-4j62d` 2026-10-03T18:32:25Z; `kubectl -n cicd get cronjob` lists none. Controller pod `tekton-pipelines-controller-65f567589b-6nrsc` age 10h; 400 log lines covered 8 seconds (15:40:25Z–15:40:33Z) with 100 `Reconcile error` lines, all `pods … not found`. `plan-5e8e4676-1791646670-run` was created 15:37:55Z and started 15:42:16Z; the STG deliver run 50 minutes earlier started its tasks within seconds. By 15:42:40Z the error rate was 0.
- **Evidence**:
  - `kubectl -n cicd get taskrun --no-headers | wc -l` → 3958; `kubectl -n cicd get pipelinerun --no-headers | wc -l` → 545
  - `kubectl -n tekton-pipelines logs deploy/tekton-pipelines-controller --tail=400` during the stall
  - `bifrost-trade-infra/k8s/cicd/` — no pruner manifest
- **Impact**: Every 10 hours after a controller start, CI, plans and deliveries stall for minutes; the stall grows with the run count. A release or an approved apply that starts in that window looks hung. Correction (2026-10-10): release evidence does not live in the runs. `api/internal/releases` writes one ConfigMap per finished delivery run (label `bifrost.io/release-record`, 380 on 2026-10-10), and promtail ships step logs to Loki, so finished runs can be pruned once their record exists.
- **Fix**: W-60. Owner 2026-10-10 set the starting rule: succeeded runs 24 hours, failed runs 7 days, at least the last 5 per pipeline, and a delivery run only after its release record exists. The loop in `api/internal/releases` that writes the records also prunes (dry run first; the Owner approves the first list). Check Loki's retention for step logs before the first prune.
- **Ratchet**: an alert on the TaskRun count in `cicd` and on a TaskRun that has no pod two minutes after creation.
- 验收: `kubectl -n cicd get taskrun --no-headers | wc -l` stays under the chosen bound for a week; a plan started during a controller resync gets its pod within 30 seconds.
- 审批 要你批 · 代价 S · 风险 med · repos: bifrost-trade-infra, bifrost-platform

### TD-303

- **交付状态 2026-10-11**：已合入／未发布；最新 main 整合测试及 DEV 验收 PASS。对应提交和部署边界见 `docs/audits/DATA_INTEGRITY_MAIN_INTEGRATION_2026-10-11.md`；生产验收、告警送达、实际恢复及剩余数据缺口按各项条件保留，未据源码合入结债。

**P1 · research-control · Daily data failure visibility and accepted long-row retention await deployment**

- **状态**：在做（isolated implementation/test/DEV PASS; no release approval or deployment）
- **Evidence**: Research `orchestration/plugin_http.py:211`, `market_self_heal.py:73`, `api/orchestration.py:342`, `engines/volatility/atm_iv.py:505`; malformed enqueue/queue responses, critical without prescriptions and successful runs with failed checks could appear green; invalid long input could delete a valid repair. Frontend `pages/research/stocks/method/QueueFace.tsx:298` conflated check caution and run failure.
- **Fix**: Research `cc575bf`, Frontend `c57283ae`: strict measured acknowledgments, visible critical/delivery failure, calendar/coverage semantics, valid replacement keys and actual evaluations; CHECKS CAUTION retains valid queue rows. Existing API fields, legal zero/dedup/holiday and short expiry semantics retained. Production deployment requires Owner approval.
- **验收**：Research `make lint && make test`; affected continuity tests; Frontend `npm run lint && npm run build && npm run check:legacy-css`, `npx vitest run src/pages/research/stocks/method/labTodayModel.test.ts`; DEV queue caution/detail/30 candidates, real data read-only.
- **验收结果**：PASS isolated 2026-10-10 `cc575bf` / `c57283ae`: Research 2286 passed/17 skipped, affected 75 passed/0 skipped; FE 13 passed, lint/build/CSS PASS. Not production acceptance. Detailed evidence: `docs/audits/DATA_CONTINUITY_DEFENSES_2026-10-10.md`.
- **Ratchet**: RATCHETS daily continuity subsection; malformed/zero/missing/calendar/invalid-long/failed-delivery/output-check tests. Follow-up: TD-304/305; existing TD-172/142 daily long scope and TD-183 restore stay open.

### TD-304

- **交付状态 2026-10-11**：已合入／未发布；最新 main 整合测试及 DEV 验收 PASS。对应提交和部署边界见 `docs/audits/DATA_INTEGRITY_MAIN_INTEGRATION_2026-10-11.md`；生产验收、告警送达、实际恢复及剩余数据缺口按各项条件保留，未据源码合入结债。

**P1 · research-control / alert-delivery · Failed or missing Research work has no verified durable Owner notification**

- **状态**：在做（isolated implementation/tests/DEV accepted; production cutover, targeted Owner routes and true receipt test await Owner confirmation）
- **Evidence**: Old run-status callback cursors advance on failed POST; warning RunFailed/AssetCheckFailed reaches audit only. A missing daily batch has no failure event; sender self-monitoring fails with its daemon. Latest bounded READ ONLY preflight: 72 SUCCESS/0 failure events and 0 failed ERROR evaluations in SUCCESS over 24h; new delivery sensor is absent from runtime. Relay heartbeat is not Research receipt.
- **Fix implemented (isolated)**: independent regular sensor, versioned outbox in existing Dagster cursor (no DDL), discovery committed before send, stable identity dedup, capped exponential intervals without dropping retries, capacity/checkpoint and invalid cursor guards. Canonical trading-calendar/session +2h main-batch deadlines, recovery resolution and long-gap/truncation unverified. Existing API detail and metrics probe observe disabled/stale/pending/error state from outside daemon; no false notification green. Default STOPPED and explicit old/new sender handover required; no blanket WARN escalation.
- **验收**：Actual local Dagster persistence reopen/replay and mock transport/crash tests; calendar/DST/holiday/manual/stuck/recovery/queue/state faults. After separate Owner confirmation, two synthetic named failure alerts with one test id, ten-minute expiry and at most four firing/resolved submissions; same id at producer, Alertmanager, PROD audit, relay and Owner; receipt within five minutes or stop.
- **验收结果**：ISOLATED PASS 2026-10-10, Research `999e8ca` + `16f7841` on codex/td-304; lint + 2325 passed/17 skipped, affected79 passed/1 optional manifest skip and draft route4 PASS. Actual DEV CHECKS CAUTION, 30 valid candidates retained; alert retry/deadline unmeasured/not enabled and Owner receipt unverified; /metrics alert_delivery probe=0, other three probes=1. No external alert injection/backfill/release. Production retries and true Owner receipt NOT VERIFIED.
- **Ratchet**: Research `tests/orchestration/test_alert_delivery.py`, API sender-health/metrics tests and definitions default-STOPPED check; infra `scripts/test_research_alert_delivery_route.py` + read-only preflight. Concrete cutover/routing/test/rollback packet: `docs/audits/TD-304_ALERT_DELIVERY_2026-10-10.md`, unapplied `TD-304_OWNER_ROUTE_DRAFT.yaml`. Related TD-92/172/142; keep open until deployed and Owner receipt signed.

### TD-305

**P2 · market-data / data-integrity · 67 empty option responses after a recovered authentication interruption need historical classification**

- **状态**：未开始（bounded inventory identified read-only; no fetch/backfill authorized）
- **Evidence**: `scripts/audit-data-continuity.sql:17`, Plugin `freshness.py:178`, `doctor.py:1944`; 131 option_daily failed receipts on 2026-10-09 (28 underlyings, authentication 401) ALL have later same-kind/same-payload DONE receipts. Reconciled outcome: 64 positive-price raw rows / 67 empty contract-day requests, all for 10-09. This is not 131 unhandled jobs. A DONE/zero-row response is not proof of no trading or a valid zero reading.
- **Fix / next read-only scope**: freeze exactly those 67 request keys from retained receipts, verify historical as_of listing, existing source-void and entitlement evidence; classify unlisted/no-trade/permission/fetch/unknown distinctly. Confirm reference completeness before proposing any re-fetch. Do not retry all failed receipts, overwrite valid raw values or create zero bars.
- **验收**：67/67 dispositions with source/date/as_of evidence, counts reconcile with original receipts and raw key difference; unknown stays unknown. Any proposed retry lists exact remaining keys, reference/bar HTTP budget, order, stop rule and preservation acceptance for Owner confirmation.
- **验收结果**：INVENTORY PASS 2026-10-10 read-only aggregate reconciliation only; historical classification NOT RUN. Report `docs/audits/DATA_CONTINUITY_DEFENSES_2026-10-10.md`.
- **Ratchet needed**: empty-source evidence and effective coverage across the 24h queue-failure window, without confusing recovered failures with new missing rows. Existing TD-281 handled retries; preserve it.

### TD-307

**P3 · ops-platform · the question record's redactor: the TypeScript side is quadratic on repeated characters, and the differential test against main logs its enforced count without asserting it**

- **状态**：(b) 做完待合并——只动测试的提交单独在分支 `w31/td-307-b`（`201c81c`，叠在 `w31/w65-1a` 上，复核 61 无意见），随提问入口进主线后这一半关掉；**(a) 不做，留着**——2026-10-11 两次尝试把扫描改快（`w31/td-306-307` 的 `ac68be6`、`43031f6`，已放弃），每次都改到了匹配规则，第二次让共享的 `Redact` 比主线遮得少（复核 60、教训第 74 行）。输入有上限（请求体 16 KiB），慢在 Agent 自己的进程里；除非这段代码要用到无上限的文本上，否则不再动它。原记录：Codex 复核 50，2026-10-11；W-65 1A 第 4 轮，分支 `w31/w65-1a` 提交 `da7b774`，合并后生效
- **Claim**: (a) `mcp/platform/src/questionCanonical.ts` scans for secret shapes with a hand-written loop that backtracks: an input of one repeated character with no keyword takes time quadratic in its length. (b) `TestRedactHidesEverySecretMainHides` (`api/internal/notice/`) checks "the frozen copy of main's redactor hides SECRET ⇒ the new one hides SECRET" on 252,197 inputs but only logs how many inputs the oracle actually redacted (`enforced=237153`); a later change to the generator could make the property vacuous without failing.
- **Measured**: (a) MEASURED by review 50 in memory: 2k / 4k / 8k characters of U+017F take about 3 / 11 / 44 ms; ASCII grows the same way. NOT MEASURED on the Go side (the reviewer could not run Go tests in its read-only sandbox). (b) read from the test source.
- **Evidence**: `agent-config/work/multi-agent/reviews/codex-2026-10-11-review50-w65-1a-round4.md` items 4 and 7.
- **Impact**: (a) small: the function runs in the agent's own MCP process on a request body capped at 16 KiB, so the worst case is well under a second and nobody else pays for it. It matters if the same loop is reused server-side or on unbounded text. (b) the test is the only thing that pins "the new redactor never hides less than what was live"; without a floor on the enforced count it can decay silently.
- **Fix**: (a) make the scan single-pass (advance past a failed candidate's start instead of re-scanning from the next character) in both languages, keep the shared vectors. (b) assert `enforced` is at least 200,000 and that each pattern class (keyword assignment, `bearer`, `basic`, AWS key, PEM) is hit at least once.
- **Ratchet**: (b) is itself the ratchet. For (a) a timing-free test: count loop iterations on an 8k repeated-character input and assert it is linear in the length.
- 验收: `cd bifrost-platform/api && go test -count=1 -run 'TestRedactHidesEverySecretMainHides' -v ./internal/notice/ && cd ../mcp/platform && npm test`
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-308

**P2 · ops-platform · the progress document is published by a script that never says whether it was accepted; the PROD Progress page went stale for hours with nothing showing it**

- **状态**：未开始（本机一侧 2026-10-11 已临时补上，见 Fix 的第一句；仓库里的脚本和服务端没动）
- **Claim**: `scripts/progress-publish.js` posts the local board's document to `PUT /api/v1/agent-progress` and exits 0 whatever happens (`uncaughtException`, `unhandledRejection` and both promise outcomes all call `process.exit(0)`; nothing is logged). The server refuses a document over 256 KiB (`api/internal/agentprogress/document.go` `MaxDocumentBytes`) and one with more than 20 steps in a piece of work (`schema.go` `maxSteps`). A long-running programme crosses both limits by itself. The Console keeps showing the last accepted document; its "computed N ago" line is the only sign.
- **Measured**: MEASURED 2026-10-11 11:40 CDT by calling `publishProgress` directly and printing only the status: 413 with the document at 369,020 bytes (267,617 of them the event trails of finished steps); after slimming to 95 KB, 400 until every work was cut to 20 steps; then 202. When the rejections began is NOT MEASURED — the document was already 339 KB at 10:35 and three works had passed 20 steps during the night.
- **Evidence**: `agent-config/scripts/progress-publish.js` (the four `process.exit(0)`); `agent-config/scripts/thread-heartbeat.js` `publishProgress` (returns `{sent, status}`, which the caller drops); `bifrost-platform/api/internal/agentprogress/schema.go` lines 11–17 and `document.go` line 24; `agent-config/work/multi-agent/LESSONS-from-practice.md` row 76.
- **Impact**: the Owner's page on PROD silently shows an old picture. On 10-11 he happened to be looking at the local board; had he looked at the Console he would have seen last night's state under today's date. It also defeats the purpose of the page as the one place he looks.
- **Fix**: locally, the board now slims the document before publishing and records the server's answer (`~/agent-work/status/board2.py` `slim_for_publish`, `publish-result.js`), and shows a light for it. In the repositories: (1) `progress-publish.js` writes the outcome (`sent`, `status`, the server's error text, byte count) to a result file or stdout and exits non-zero on a refusal; (2) the server answers a refusal with which limit was hit, and the handler's response is surfaced; (3) the Console's Progress page shows when the document was last ACCEPTED and, when the newest attempt was refused, says so with the reason — this needs the server to remember the last refusal; (4) decide the limits deliberately: 20 steps per work is a display bound, not a reason to drop the whole document — truncate server-side with a marker, or have the publisher paginate.
- **Ratchet**: a test that a document with 21 steps in a work and one of 300 KiB each produce a recorded, visible refusal (not a silent drop) end to end: publisher result, server response body, and the Console line.
- 验收: `cd bifrost-platform/api && go test ./internal/agentprogress/` and `node --test agent-config/scripts/progress-publish.test.js` (to be written) and the Console test for the refusal line
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-platform, bifrost-trade-infra

### TD-309

**P2 · infra · the platform's apply pipeline cannot plan or apply a Tekton Pipeline that was last applied by hand: server-side apply conflicts with the client-side field manager on `.spec.tasks`**

- **状态**：在做（2026-10-11 13:25 统筹方按推荐定了做法：由 Owner 用服务端方式把这 13 条流水线重新应用一次，字段管理者换成 apply 流水线用的那个，之后的改动走平台。放弃的做法：让 apply 流水线对 `cicd` 里的 `tekton.dev` 对象一律 `--force-conflicts`——那是让流水线可以从人手里拿走字段，属于放宽规则，要 Owner 签。依据：一次性、可重做、不改任何规则。怎么推翻：Owner 说「改 apply 流水线」。命令和 TD-310 要他生成签名密钥的那一条放在同一次办，在本机看板「需要你做的」里排着，还没轮到）
- **Claim**: the thirteen pipelines in `cicd` were installed on 2026-10-11 by the Owner with client-side `kubectl apply` (the documented way for that install). `bifrost-apply-manifest` uses server-side apply; its `kubectl diff` on one of them fails: `Apply failed with 1 conflict: conflict with "kubectl-client-side-apply" using tekton.dev/v1: .spec.tasks`. So a later change to any of these Pipeline objects cannot go through `plan_manifest` / `apply_manifest` (which the actuation policy allows for Pipeline and Task in `cicd`) until ownership of the fields is moved.
- **Measured**: MEASURED 2026-10-11 12:50 CDT: `plan_manifest` of `k8s/cicd/tekton/pipeline-deliver-platform.yaml` at infra `0cc8c19` — `freeze-check` Succeeded, `run` Failed with the conflict above (PipelineRun `plan-0cc8c195-1791740994`). Whether the same conflict existed before today's install for these objects is NOT MEASURED.
- **Evidence**: the run's `run` task log; `k8s/cicd/tekton/apply-manifest/pipeline.yaml` (the `kubectl diff` / apply step); `docs/RELEASE.md`, the freeze-check section, step 3 ("按文件逐个 apply").
- **Impact**: every future change to a release pipeline has to be applied by the Owner by hand again, which is the opposite of where W-56 is going; and a plan that fails for this reason looks like a broken pipeline.
- **Fix**: decide one owner for these objects. Either the Owner re-applies them once with `kubectl apply --server-side --field-manager=<the apply pipeline's manager> --force-conflicts` so the apply pipeline owns the fields afterwards, or the apply pipeline's diff/apply uses `--force-conflicts` for `tekton.dev` objects in `cicd` (a policy decision: it lets the pipeline take fields from a human). Write the choice into `docs/RELEASE.md`.
- **Ratchet**: a check that lists `managedFields` managers of the Pipeline and Task objects in `cicd` and fails when more than the expected one owns `.spec` (read-only; can run with the agent identity).
- 验收: `plan_manifest` of each of the thirteen pipeline files at the current commit ends Succeeded with an empty diff
- 审批 要批（一次性的重新应用，或 apply 流水线的行为改动）· 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-310

**P1 · ops-platform · a release freeze can be set by any operator but cannot be lifted: platform-api has no Owner key fingerprint compiled in, so every unfreeze signature is refused**

- **状态**：在做——2026-10-12 07:02 第一片的两次补测试都已合并（复核 112、114 都是可以合并、没有会答错的应答）：字节类别现在是 2,654 个位置，分块用例由程序按 1 到 6 块生成。复核 114 指出的「第七块」是同一个循环的下一次重复，**记为接受**：这条线「只缺测试」的补做到此为止（Owner 的规矩是最多两次），以后只有找到会答错的应答才再动第一片。之前：在做——2026-10-12 00:10 **第一片过了独立复核并合并**（第 5 轮由 Cursor 实现、统筹方验收、Codex 复核 109：可以合并，没有找到会答错的应答，180,843 份应答和 148 种送达安排两份读法 0 分歧；只缺测试的规则 1 条、该改的 1 处，按 Owner 10-11 的规矩补上再复核，不算停线）。合并：infra `0aa585d`、platform 见提交记录。**没有接线**：没有流水线调用这道检查，`k8s/release-freeze` 的清单没有被任何 kustomization 引用、没有应用，PROD 上冻结仍然被拒绝。信任根路径已加进 `agent-config/release-policy/paths.json`（收紧；随 Owner 下一次签策略生效）。后面还有：第二片起的接线、TD-314 和 TD-293 的收窄、墓碑、Owner 在场的演练，以及 Console 上的冻结按钮和定期演练（W-56 的追加）。第一片共五轮，前四轮的经过见教训第 92、98、99、100 行。之前：停线——2026-10-11 22:45 第一片第 4 轮停线（这一轮仍由统筹方改：Python 每次底层读取都按同一个截止时刻、返回前再核对；12 种送达时刻、45 个位置各 256 种字节的用例；被禁止的行为搬出生产代码；种错运行器加了不种错的对照）。统筹方的完整验收通过。Codex 的复核 108 没有跑完——被它的提供方的内容安全检查中止，没有报告；它落盘的结果显示两份读法在字节（180,843 份）和时序（148 种安排）上都没有分歧，但有两处种错没有测试拦住（去掉返回前的期限核对；状态行第一个字节不比较），另有一条收尾时间（Go 判 `clear` 后要多等约 5 秒才返回）。按「一处没有测试拦住的种错」停线。分支（platform `9cb55cf`、infra `336f9a2`）不合并。重开要 Owner 一句话。教训第 100 行。之前：停线——2026-10-11 22:03 第一片第 3 轮按条件停线（这一轮由统筹方按 Owner 的话自己改：设计 3.2 加了应答语言 H，两份读法改成逐字节，300 份共享向量）。统筹方的完整验收通过（第 2 轮的 220 份应答两边 0 分歧，上一轮 41）；Codex 复核 107 找到一处必须改的：Python 的总期限管不住缓冲读内部的多次底层读取，慢送的合法应答 Python 在第 12 秒放行、Go 在第 10 秒拒绝。另三处该改的：Go 种错运行器不复制 `testdata`（新加的 16 条的证据是空的，复核方补齐夹具后抽查 10 条属实）；值里多放行 0x81 没有测试拦住；被禁止的行为不该留在生产代码里。字节层面复核方自造 180,843 份应答，两份读法 0 分歧。分支（platform `04a4530`、infra `c912ec6`）不合并。重开要 Owner 一句话。教训第 99 行。之前：停线——2026-10-11 21:22 第一片第 2 轮按条件停线：统筹方的重跑把 220 份原始 HTTP 应答交给两份实现，41 份的二进制判定不同（35 份 Python 放行、Go 拒绝；6 份相反），正中停线条件的第二句。正文的识别器没有问题（统筹方另造的 27,395 条三方一致），其余验收全过（Go 整套通过、该包 4.2 秒、种错清单 Go 23 条和 Python 24 条全被拦）。原因在设计 3.2：正文有产生式，应答头部没有。分支 `w31/td-310-s1`（platform `5fbeb3d`、infra `2079574`）不合并。重开要 Owner 一句话；建议先补设计（头部也写成产生式，验收带「生成的原始应答过两份实现」），再做第 3 轮。教训第 98 行。之前：在做——2026-10-11 17:36 解冻协议的设计通过了独立复核（复核 93、95，必须改的 2 → 0）：冻结改成一类只能新建的集群级记录，解冻是 Owner 用自己的集群凭证删除，不再有记忆和解冻签名。`work/multi-agent/DESIGN-release-freeze-protocol-2026-10-11.md`；`PLAN-w56` 决定记录之七。归 Owner 定的四项已交给他，他定之前第一片不开工；PROD 上冻结继续被拒绝。之前：2026-10-11 16:38 信任锚这一半按事先写下的条件停线（复核 86 又找到两种不经新签名就让平台放行的办法；三次复核共六种）。分支 `w31/td-310-anchor` 不合并；密钥不编进平台，PROD 上冻结继续被拒绝、没有任何东西自动批准——这是安全状态，不是缺口。下一步是解冻协议的设计（`work/multi-agent/DESIGN-release-freeze-protocol-2026-10-11.md`，在写），过独立复核后才实现；决定和依据在 `PLAN-w56-unattended-prod-2026-10-10.md` 决定记录之六。已经在线上的一半不变：2026-10-11 15:05 起 PROD 没有信任锚时拒绝冻结（platform `96af54a`，随 `17136ba`）。Owner 的发布密钥已生成（指纹 `SHA256:pzjcenBSbCbgIoqamoQLsvlxELfp4ikcLbvp164Eel8`），先不用。之前的记录：在做（2026-10-11 15:16。已上线的：没有信任锚时不许设冻结——`release.sh` 和文档在 infra 主线 `3a9db04`，平台那部分随审批单 #9 在 15:05 上了 PROD。Owner 15:13 生成了发布签名密钥，指纹 `SHA256:pzjcenBSbCbgIoqamoQLsvlxELfp4ikcLbvp164Eel8`，他屏幕上的和公钥文件算出的一致；指纹和签名人文件在分支 `w31/td-310-anchor`（platform `a55b2cc`、infra `7082197`），**没有合并**：复核 79 发现有了锚之后，冻结和解冻这一对里有两处能让冻结不经 Owner 新签名就被解开（同一秒内重放旧签名；解冻的写入盖掉更新的冻结），先堵上再上线，任务书 `~/agent-work/td-310/TASK-2.md` 已派出。之后：过复核 → 进主线 → 发 STG → PROD 发布单（理由里写指纹，Owner 核对后批）→ 冻结演练完整重做一遍。**演练做完之前不要用冻结**）
- **Claim**: `releasepolicy.OwnerKeyFingerprint` is the empty string on main (`api/internal/releasepolicy/anchor.go`: "Empty means the Owner has not generated the key yet"). `Unfreeze` calls `verifyAnchored`, which returns "no trust anchor compiled into platform-api" when the anchor is empty (`sshsig.go`), so `release.sh unfreeze` can never succeed; the Owner also has no signing key at the default path. Meanwhile `release.sh freeze` and `POST …/release-policy/freeze` accept any operator and the freeze is honoured at three places: the platform gate (409), the Tekton freeze check (since 2026-10-11) and the platform's own memory of the newest freeze seen (`platform-state-release-policy-freeze` in each platform namespace), which keeps the gate closed even after the freeze ConfigMap is reset.
- **Measured**: MEASURED 2026-10-11 12:56–13:02 CDT on PROD. Freeze by the coordinator (a drill the Owner confirmed) → `start_pipeline_run` 409 `releases are frozen`; a plan run failed at `freeze-check`. `release.sh unfreeze` → `no signing key at ~/.ssh/bifrost_release_owner`. After the Owner reset `cicd/bifrost-release-freeze` to `{"frozen":"false"}` the Tekton check passed but `policy status` still said `frozen True (a freeze from 2026-10-11T17:56:22Z was seen and its record is gone)`; after he blanked `state.json` in `platform-state-release-policy-freeze` (PROD and STG) it said `frozen False` and an STG release ran.
- **Evidence**: `bifrost-platform/api/internal/releasepolicy/anchor.go:11`, `sshsig.go:113-122`, `write.go:100-123`, `engine.go:160-181`, `policy.go:236-247`; `bifrost-trade-infra/scripts/release/release.sh` (`cmd_freeze`, the unfreeze path at about line 698); `agent-config/work/multi-agent/LESSONS-from-practice.md` row 79.
- **Impact**: any agent thread with the operator token can stop every release, STG and PROD, and nobody can lift it through the product; lifting it took two hand edits by the Owner with the cluster-admin credential, which is exactly the bypass the signature was meant to make unnecessary. Until fixed, the freeze must not be used.
- **Fix**: (1) now, in `release.sh freeze` and in the platform's freeze handler: refuse when no trust anchor is compiled in (say why: it could not be lifted). (2) The Owner generates the release-owner signing key; its fingerprint goes into `anchor.go` and `agent-config/release-policy/allowed_signers` (a trust-anchor change: Owner-reviewed, never auto-approved), then a platform release. (3) Write the break-glass into `docs/RELEASE.md`: the two objects, in order, and that it is the Owner's cluster-admin action. (4) Redo the drill end to end: freeze → refused → signed unfreeze → released.
- **Ratchet**: a platform test that `Freeze` is refused while `Anchor` is empty; a `release.sh` test for the same; a line in the release checklist that the drill's unfreeze half has passed since the last change to the anchor.
- 验收: with an anchor compiled in: `scripts/release/release.sh freeze --reason drill` then `scripts/release/release.sh unfreeze` (Owner signs) → `policy status` shows `frozen False` and a STG deliver run passes `freeze-check`; with no anchor: `freeze` exits non-zero and changes nothing
- 审批 要批（信任锚变更和一次平台发版）· 代价 S · 风险 med · repos: bifrost-platform, bifrost-trade-infra

### TD-311

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

### TD-312

**P2 · ops-platform · after the admin token is rotated, the request page still says a token is saved in this browser, and the decision button fails with "admin token required" — nothing on the page says the saved token is the stale one or what to do**

- **状态**：观察中（到 Owner 在他用的每个浏览器的右上角各登录过一次、并各批过一张单）。缩小后的四件 2026-10-13 13:08 上正式环境（审批单 #14，提交 `bf39f96`；三轮实现、三次独立复核）。已有的一次真实使用：#15 在 18:10 从新版页面批上，页面加载后 4 秒批准到达，没有再输令牌。原来写的验收（在测试环境存一个错的令牌看页面怎么说）要在浏览器里用令牌做，Agent 不碰，没有做；页面上的字句由 996 条自动测试守着。以下是开工时的记录：（2026-10-12 22:22 护栏第 ⑥ 项，目标按 10-11 留下的话缩小后重开，统筹方定、留痕：Owner 10-11 15:05 的决定不变——三级令牌不变，Console 只在右上角登录一处，页面不再另要令牌。**这一轮只做四件**：① 决定（批准 / 驳回）用右上角登录的那一个会话；请求页上单独的令牌格和它的存储去掉，页面加载时把旧的那一格存的值清掉。② 页面任何地方都不显示、不记录令牌。③ 会话不是管理员（没登录、令牌被换掉了、只是操作员）时，决定按钮是灰的，旁边写明原因和去哪办（「右上角用管理员令牌登录」）；右上角的角色以服务器的回答为准。④ 决定被服务器拒绝时，页面用 Owner 看得懂的话说明，并指向右上角。安全边界仍然只在服务器（批准要管理员令牌，不变）；页面上的灰按钮是给人看的，不是防线。**不做**：前四稿想保证的「任何会改东西的请求都不许绕过某个模块」——四次复核都卡在这个目标上，它不是这条债要的。次序：排在 TD-325 之后（两条改的是同一批文件），先写任务书、定死形状，一轮实现加一次复核。推翻：「⑥ 的目标恢复原样」。）之前：在做（2026-10-11 18:29 令牌模型的设计第 4 稿（Owner 重开后的一轮）按条件再次停线：复核 98 仍有 1 处必须改的（原生表单和 Worker 也能发请求）；四稿 2 → 1 → 1 → 1。按推荐定了先放着，等主线和 TD-313 的门禁落地后重开；重开时先把目标改小——保的是「带着登录令牌的请求只能从那个模块发出」，不是「任何会改东西的请求都不许绕过」（教训第 91 行）。之前：2026-10-11 16:54 令牌模型的设计第 3 稿按条件停线：三稿三次复核（85、89、90），必须改的 2 → 1 → 1，每一稿把上一稿的关掉，新的在别处；第 3 稿剩的一处是 lint 规则对几个文件整份豁免。重开要 Owner 一句话（建议重开，只改这一处）。设计稿在 `work/multi-agent/DESIGN-console-auth-2026-10-11.md`，标了「停线，不可照着实现」。前提 TD-313 照常做。之前：2026-10-11 16:00。Owner 15:05 定了做法：三级令牌不变，Console 只在右上角登录一处，页面不再另要令牌。实现分支 `w31/td-312`（`56e7300`、`22b9358`）两轮、两次复核（80、83），各找到同两类里的一处——非管理员的决定能过页面的闸；令牌可能被显示；按事先写下的条件停线，分支不合并。目标不变，先出令牌模型的设计 `work/multi-agent/DESIGN-console-auth-2026-10-11.md`（在写），过复核再实现。在那之前 PROD 上照旧：批单用页面上那一格，Owner 已在他用的浏览器里存了新令牌；别的浏览器和手机第一次批单前要各存一次）
- **Claim**: the Console keeps the Owner's decision token per browser. When the token is rotated on the server, each browser still holds the old value. The request page shows the reassuring line that a token is saved in this browser and the role badge OPERATOR; pressing the decision button returns the server's "admin token required". The Owner had rotated the token at 13:15 the same day (the old one had been exposed in a conversation) and did not connect the error with it; he had to ask in the thread. The rotation steps the coordinator gave him said to paste it into the Console once, not "in every browser you decide from".
- **Measured**: MEASURED 2026-10-11 14:56 CDT from the Owner's own screenshot of request #9's page on PROD (platform `6524330`): the three texts above appear together. Which status code the server answers for a stale token is NOT MEASURED (agents do not call that route and do not hold the token).
- **Evidence**: the screenshot in the coordinating thread (not in the repository); the token form of the request page under `console/src/pages/shell/` ("A token is saved. Type a new one to replace it."); `docs/SECRETS.md` (the rotation steps).
- **Impact**: the one action only the Owner can take fails right after he did the right thing for security, with no path shown. It cost a round trip to the thread on a release that was waiting for him.
- **Second observation, 15:02 the same day**: the Console has two places for a token — the sign-in at the top right (it sets the role badge) and the token field on the request page (the only one a decision uses; `console/src/api/approvals.ts`, storage key `bifrost-ops-approval-token`). The Owner put the new admin token into the sign-in, saw the badge turn to ADMIN, pressed the decision button and got the same "admin token required". A page that shows ADMIN and refuses for lack of admin reads as a contradiction; nothing says the decision uses the other field.
- **Fix**: (0) the refusal names the field: "Decisions use the token saved under 'Set approval token' on this page, not the sign-in at the top right"; consider using the signed-in admin session for a decision when it is admin, or removing one of the two places — a design choice to settle with the token model; (1) when a decision is refused for lack of the admin role, the page says so in the Owner's terms — "The token saved in this browser was not accepted. It may have been replaced. Set the current one below." — and unfolds the token field; (2) the "saved" line is checked against the server when the page loads and says `saved, not accepted` when the check fails; (3) the rotation steps in `docs/SECRETS.md` list every place the token lives (each browser, the phone, the local tool configuration) and end with a check the Owner can do himself.
- **Ratchet**: a Console test — a refused decision with the role error renders the replacement hint and the unfolded field; a server test that the check distinguishes "no token", "token not accepted" and "accepted".
- 验收: on STG with a deliberately wrong token saved: the page says the saved token is not accepted before any button is pressed, and a refused decision leads to the field
- 审批 无（代码和文档改动，随平台发布）· 代价 S · 风险 low · repos: bifrost-platform, bifrost-trade-infra

### TD-314

**P2 · infra / ops-platform · the PROD platform's service account can rewrite the Pod template of any Deployment in `cicd` and `monitoring` — including `argocd-server` — so whoever holds that account is one patch away from a cluster-admin-level identity**

- **状态**：未开始（2026-10-11 17:10 写解冻协议的设计时量出来的。Agent 经平台接口够不着这条路：平台自己的代码只改重启注解和副本数）
- **Claim**: ClusterRole `bifrost-platform-workload-actuator` grants `apps/deployments` `update` / `patch` (plus `deployments/scale` and `pods` `delete`) with no `resourceNames`. It is bound to `bifrost-platform-prod/bifrost-platform` in eleven namespaces, among them `cicd` and `monitoring`. `cicd` holds the Argo CD Deployments (`argocd-server`, `argocd-repo-server`, …), whose service accounts can change ClusterRoleBindings, admission policies and CRDs. None of the six ValidatingAdmissionPolicies constrains what this account may change in a Deployment (they cover Jobs, Pods, PipelineRuns, TaskRuns, Applications and the applier's workloads). The platform's own code patches only the restart annotation (`rollout_restart_deployment`) and the replica count (`scale_deployment`); the permission is far wider than that use.
- **Measured**: MEASURED 2026-10-11 17:10 CDT, read-only with the agent identity: `kubectl get clusterrole bifrost-platform-workload-actuator -o json` (rules as above, `resourceNames` absent); `kubectl get rolebindings -A` filtered on that role (eleven namespaces: `bifrost-dev`, `bifrost-platform-prod`, `bifrost-platform-stg`, `bifrost-prod`, `bifrost-stg`, `cicd`, `data`, `monitoring`, `plugin-flex-query`, `plugin-market-data`, `research`; one subject); `kubectl get deploy -n cicd` (`argocd-server` runs as service account `argocd-server`); `kubectl get validatingadmissionpolicy` (six names, none for Deployments). NOT MEASURED: that such a patch would be admitted — it was not tried and must not be; whether a webhook would stop it (the agent identity cannot read webhook configurations).
- **Evidence**: the commands above; `work/multi-agent/DESIGN-release-freeze-protocol-2026-10-11.md` §1.2 item 2 and §1.3 — the reason that design does not claim "a replaced platform process cannot lift a freeze".
- **Impact**: any guarantee of the form "the platform's account cannot do X" (lift a freeze, change a release policy, change RBAC) holds against the platform's code being wrong, not against the account being misused. Same family as "whoever can create a Pod in a namespace inherits its strongest service account".
- **Fix**: narrow the grant to its use. Either `resourceNames` per namespace for the Deployments the platform restarts or scales (and nothing in `cicd` / `monitoring` beyond those), or a ValidatingAdmissionPolicy that lets this account change only `spec.replicas` and the restart annotation of a Deployment. RBAC and admission are applied by the Owner; prove the change first with a server-side dry run and one real restart per namespace.
- **Ratchet**: a read-only check, runnable with the agent identity: for each namespace where this role is bound, either the binding's role carries `resourceNames` or the admission policy exists and is bound.
- 验收: with the narrowed grant, `rollout_restart_deployment` and `scale_deployment` still succeed for every workload the Console offers, and `kubectl auth can-i patch deployment/argocd-server -n cicd --as=system:serviceaccount:bifrost-platform-prod:bifrost-platform` answers `no` (run by the Owner; the agent identity cannot impersonate)
- 审批 要批（RBAC 或准入策略，Owner 应用）· 代价 S · 风险 med · repos: bifrost-trade-infra

### TD-319

**P1 · multi-agent · the recorder's slice 1 is on main as code nobody may trust yet: three inputs are answered wrongly and some single-point mutants are caught by no test — it must not be wired until both are closed**

- **状态**：在做（Owner 2026-10-12 15:01 恢复 W-66，做薄：六项里的 (1)–(6) 在 A 片修；「没被拦住的种错清零」不再是关掉这一条的条件，改为「页面从事件生成并和手工看板并排一周没有解释不了的差异」）
- **Claim**: `agent-config/scripts/recorder/` was merged after six implementation rounds (three implementers) with these known defects, all from Codex review 113 (`work/multi-agent/reviews/codex-2026-10-12-review113-w66-recorder-s1-r6.md`): (1) a log exactly at its limit (20,000 lines, 16 MiB, the observer log) followed by a torn tail records no `limit_log` break — `read.py:439–456, 499`; (2) `record_created` takes `since` too late when a continuously found record has an Unknown condition in between — `ownerball.py:397`; (3) `next_not_sent` takes `since` from the declaration when the wait is settled in another log — `ownerball.py:162–165, 492–513`. None of the three makes the published document say "all clear"; they leave a marker out or a time wrong. Besides: of 3,887 generated single-point mutants, 264 were not caught at the end of round 7 (round 8 was stopped part-way on 2026-10-12 09:25 because it saturated the machine; its commits are merged).
- **Found by first real use (2026-10-12, the shadow tooling, `work/multi-agent/reviews/` has none yet — the implementer's report)**: (4) `rec.py` has no `run`, `observe` or `fold` entry although design section 5 lists them — only the ten bookkeeping commands exist, so a shadow process cannot run under the recorder's own `run`; (5) `rec.py owner-open` cannot be called: its `--command` option shares the name `command` with the sub-command and the sub-command becomes empty (`unknown command`, exit 1, no event written), while the function behind it works; (6) an open Owner item comes out of `fold_total` without `since`. All three join the must-fix list; (5) and (6) get a test that calls the command line end to end.
- **Left for later in lane.py and run (reviews 130 and 131, 2026-10-12)**: after `start` exits 3 the entry is keyed `pending:<pid>` and `stop` by step id cannot find it; a wrapper that dies before starting anything also yields exit 3; simultaneous starts of a work not yet open fail to open; a corrupt `lanes.json` breaks `status` and `stop`; `status` does not show a job's result; `run` closes descriptors above 2, forwards only TERM, INT and HUP, and stops bookkeeping after one failed heartbeat write; the half of `observe` that reads the platform is not built. Usage until then: kinds implement / verify / review / merge / other only; open a new work with one start before starting more; read results from `rec.py fold`; stop a wrapped job only through `lane.py stop`.
- **Measured**: review 113's reproductions (`evidence/repro.py`, `evidence/limits.py` in the reviewer's directory); the coordinator's rerun of round 6; on the merged tree `pytest agent-config/scripts/recorder/` → 688 passed, 5 xfailed (2026-10-12 09:30). NOT MEASURED: the mutant count after round 8's partial work (the 50-minute run was not repeated).
- **Impact**: none today — nothing reads the recorder (`test_guard.py` holds the release path to that; `STATUS.md` in the directory says so). It becomes real the moment slice 2 lets the board read the folded result: a missing marker or a wrong time would then be shown to the Owner as fact.
- **Fix**: the three by review 113's smallest fixes, independently reviewed (the reviewer must not be the one who reviewed the previous round); the remaining survivors to zero under the checker's definition (killed, equivalent-shown, unreachable-shown), run when the machine is otherwise idle and with a cap on parallel processes; then seven days in shadow beside the hand-maintained board, every difference turned into a test or explained. The method is `work/multi-agent/PLAN-recorder-shadow-run-2026-10-12.md` (shadow processes beside real jobs, never a wrapper around them; a comparer that is the only permitted reader; seven consecutive days with 0 unexplained differences).
- **Ratchet**: the five `xfail(strict=True)` tests for the three defects (they fail the suite when a defect is fixed and the mark is left, so the fix cannot land silently half-done); `test_guard.py` (the release path does not read the recorder); `STATUS.md`. No ratchet yet stops a new consumer from trusting the output — there is no consumer; slice 2's brief must add "shadow only until TD-319 is closed" as a test.
- 验收: the five tests pass with their marks removed; `RECORDER_MUTANTS=1 pytest agent-config/scripts/recorder/test_mutants.py` reports 0 survivors; a shadow log of seven consecutive days with 0 unexplained differences
- 审批 无 · 代价 M · 风险 low（没有接线）· repos: bifrost-trade-infra, bifrost-platform

### TD-320

**P2 · governance · two documents say a Mac mini thread needs the same three MCP token keys as the laptop — one of them is the admin key — while the host design puts no admin credential on an agent host**

- **状态**：未开始
- **Claim**: `agent-config/.mcp.json.README.md:108` (「Mac mini 上的线程以后同样需要这份文件：同样三个键」) and the token-tier paragraph at `agent-config/AGENT_FACTS.md:337` describe one token file with viewer, operator and admin keys; `work/multi-agent/DESIGN-host-minimal-2026-10-12.md` section 5 and `RUNTIME-PLACEMENT-2026-10-11.md` section 7 say an agent host holds no admin credential. No agent runs on a mini yet.
- **Measured**: the two passages read on 2026-10-12. NOT MEASURED: which token files exist on the minis (agents do not read token files).
- **Impact**: someone setting up a mini from the README would copy the admin key onto an agent host; "an agent cannot approve" would then rest on convention.
- **Fix**: after the Owner decides which keys go on a host (decision D3 of the host design), rewrite both passages: an agent host gets its own reporter-level key; the admin key stays on the Owner's devices.
- **Ratchet**: the host installer refuses to finish when the token file on the host names an admin key (it checks key names only, never values). None today.
- 验收: `grep -n "同样三个键" agent-config/.mcp.json.README.md` prints nothing; the installer's refusal has a test that passes
- 审批 无 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-321

**P3 · multi-agent · a silent wrapped run now notifies nobody, and a session that inherited the wrapper's marker is still treated as a wrapped run**

- **状态**：未开始（TD-316 签收时留下的后续，Owner 2026-10-12 签收）
- **Claim**: after TD-316 a thread whose id begins `run-` is left out of the Owner's silent-thread push, of "Needs you" and of the host-lost message (`bifrost-platform` `api/internal/agentthreads/config.go` `Due`, `threads.go` host message; `console/src/api/agentThreads.ts` `silentThreads`). It stays in the thread list with status `silent`, but nothing calls anyone: the seat that dispatched the run has to watch it itself. Today the only dispatcher is the coordinator, whose own watcher covers it. Second: a process that is not a wrapped run but inherited both `BIFROST_HEARTBEAT_THREAD=run-…` and `BIFROST_HEARTBEAT_WRAPPED_RUN=1` (a daemon or a terminal started from inside a wrapped run) reports under the run's id and is hidden the same way (review 126, P3; unchanged by TD-316).
- **Measured**: on PROD 2026-10-12 a wrapped run silent for 700 s was counted silent and not pushed (the acceptance of TD-316). No process with both variables existed on the coordinator's machine that day (review 126).
- **Impact**: none while one seat dispatches and watches. With a second dispatching seat, or a dispatcher without a watcher, a hung background run would go unnoticed.
- **Fix**: when there is a second dispatching seat, route a silent wrapped run to the seat that started it (the platform needs to know which seat that is — an interface decision for the Owner); let the marker carry the wrapper's pid and have the hook check that it is alive.
- **Ratchet**: none yet; the tests of TD-316 hold the exclusion itself.
- 验收: a wrapped run that hangs is brought to the seat that dispatched it within the threshold plus one beat; a session started from inside a finished wrapped run reports under its own id
- 审批 Owner（接口） · 代价 M · 风险 low · repos: bifrost-platform, bifrost-trade-infra

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

### TD-322

**P3 · infra · a freeze-gate socket test fails under load: `test_clear_returns_without_waiting_for_the_peer_to_read` failed once in a whole-suite run and passes alone**

- **状态**：未开始（2026-10-12 18:32 合并护栏 ② 之前跑整套时撞上的）
- **Claim**: `scripts/release/test_freeze_gate.py::ReadTests::test_clear_returns_without_waiting_for_the_peer_to_read` depends on timing between two local sockets. With the machine at load 10–20 it failed once inside `python3 -m pytest scripts/release -q`; the same test passed three times in a row when run alone, and passed in the whole-suite run twenty minutes earlier on the same code. The merge under test did not touch the freeze gate.
- **Measured**: MEASURED 2026-10-12 18:28–18:33 CDT on the coordinator's machine (10 cores, load average about 10): whole suite `1 failed, 262 passed, 2 skipped`; the single test `1 passed` ×3. NOT MEASURED: how often it fails, and whether it fails in a quiet machine.
- **Evidence**: `scripts/release/test_freeze_gate.py` (class `ReadTests`).
- **Impact**: a red whole-suite run before a push to main that has nothing to do with the change; whoever sees it either re-runs until green or stops trusting the suite.
- **Fix**: make the test wait on an event instead of a fixed interval (or widen its bound the way `test_start_timeout_does_not_stop_command` was widened on 2026-10-12), then run it 50 times under load.
- **Ratchet**: none proposed — a flake is fixed in the test, not guarded.
- 验收: the test passes 50 of 50 with two other test processes running
- 审批 无 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-323

**P2 · ops-platform · the pre-flight before a Trade, research or plugin delivery blocks nothing: a retired repository in its list always answers "unknown", and "one unknown, block nothing" is the rule**

- **状态**：未开始（2026-10-12 复核 138 审护栏 ⑤ 第一片时查出来的；那一片因此收窄到平台两条流水线，这里的行为原样没动）
- **Claim**: (1) `bifrost-platform/api/internal/delivery/supply_chain.go` lists `bifrost-trade-socket` among the repositories `bifrost-deliver-stg` and `bifrost-deliver-prod` clone and in the fallback list `trackedGiteaRepos`. Neither pipeline clones it and its Gitea mirror was removed, so its probe is always "unknown"; `RefPreflight` blocks only when every probe had full visibility, so for these pipelines a ref that is known to be missing in another repository does not stop the run. (2) Research and plugin deliveries have no list of their own and fall back to the tracked list of eight Trade and platform repositories — none of which they clone; they start only because of that same "unknown". Removing the retired repository from the tracked list alone would refuse every one of them. (3) The pre-flight checks one revision in every repository, while `bifrost-deliver-prod` is started with a different SHA per repository and `bifrost-deliver-stg` clones bifrost-ui at `uiRevision`. (4) Branch and tag lists are read 50 entries deep; a name beyond that reads as missing.
- **Measured**: NOT MEASURED against the real Gitea. Established by review 138 with a stateful fake Gitea, the same 2,316 calls on platform main `26a10b5` and on the branch: with the `release.sh prod` request body and a worker SHA that exists nowhere, both built a run. Whether `main` is within the first 50 branches of each Trade repository and bifrost-ui is NOT MEASURED.
- **Evidence**: `supply_chain.go` (`pipelineMirrorRepos`, `trackedGiteaRepos`, `reposForPipeline`); `ref_preflight.go` (`RefPreflight`, the reachability rule); `service.go` (branch and tag listing, the page size); `agent-config/work/multi-agent/reviews/claude-2026-10-12-review138-guard5-pinned-delivery.md`.
- **Impact**: a Trade production release with a wrong SHA for one repository is not stopped before the run starts; it fails halfway at a clone task instead. The check looks like a guard and is not one. And the list that hides this cannot be cleaned up without breaking research and plugin deliveries.
- **Fix**: one deliberate change, measured first: give every pipeline the action can start its own list of the repositories it really clones and the param each is cloned at (derived from, or tested against, the pipeline definitions in infra); drop the retired repository; decide the rule for a repository whose probe is unknown (the platform pipelines got "a known-missing ref blocks; unknown does not" in guardrail 5); read branch and tag lists to the end. Before it ships, measure read-only that every ref today's releases use is found.
- **Ratchet**: a test that, for every pipeline the action has a case for, the repositories and ref params in the table equal the clone tasks of its definition in the infra checkout.
- 验收: with the real request body of `release.sh prod` and one SHA that does not exist, `start_pipeline_run` refuses naming that repository; `release.sh stg`, a research delivery and each plugin build still start
- 审批 无（代码改动，随平台发布；会改变 Trade、research、插件发布前检查的实际效果，上线前告诉 Owner）· 代价 M · 风险 medium · repos: bifrost-platform

### TD-324

**P3 · ops-platform · what TD-315 left: the mirror only syncs when asked; a commit on main without a CI run tells nobody; `test-api` does not wait for the infra clone; four CI refusal tests skip without an infra checkout**

- **状态**：未开始（2026-10-12 从 TD-315 分出来，TD-315 的主体已上正式环境）
- **Claim**: (1) The in-cluster Gitea mirror follows GitHub only when something asks: `release.sh stg|prod`, a delivery's own `mirror-sync` task, or a lineage read with `refresh`. A push to a main branch that nobody follows with one of these gets no CI run and no notice. (2) `k8s/cicd/tekton/pipeline-ci-platform.yaml`: `test-api` runs after `clone` only, while its Go tests read the infra checkout that `clone-infra` writes. (3) `TestCIRevisionRefusals`, `TestCIForbiddenParamRefusals`, `TestCIRefPreflightOneRepository`, `TestCIRunsIgnoreReleaseWindow` take the CI Pipeline objects from the neighbouring infra checkout and skip silently when it is absent.
- **Measured**: (1) MEASURED 2026-10-12 00:27 CDT (TD-315's addendum): 20 minutes after a push to platform main there was no CI run until a lineage read with `refresh` triggered the sync. (2) MEASURED 2026-10-12 on four CI runs: `clone-infra` finished about one second before `test-api` started and minutes before the tests ran; no failure observed. (3) MEASURED 2026-10-12 by review 134's confirmation: with the checkout absent and no CI variable, 7 tests skip and the package reports ok.
- **Evidence**: `agent-config/work/multi-agent/reviews/claude-2026-10-12-review134-guard3-ci-run.md`; `k8s/cicd/tekton/pipeline-ci-platform.yaml` (`test-api`, `runAfter`); `bifrost-platform/api/internal/delivery/run_refusal_test.go`.
- **Impact**: a commit can sit on a main branch untested without anyone knowing; a slow infra clone would turn platform CI red for no fault of the commit; a local run of the package can pass while testing less than it says.
- **Also (from TD-295, 2026-10-12)**: `sync_mirrors` is a tier B action with a route and no MCP tool, so an agent's only way to sync is the side effect of a lineage read; and nothing compares the tier table with the tool list.
- **Fix**: sync the mirrors on a schedule in the platform (or give agents a sync-only action) and alert when a main branch has a commit older than a set time with no CI run for it; add `clone-infra` to `test-api`'s `runAfter` (the Owner applies the pipeline — or the platform does, once TD-309 is done); give the four tests a minimal fixture.
- **Ratchet**: an alert rule for "main ahead of CI"; a structural test that every task of a CI pipeline that reads a checkout runs after the task that writes it.
- 验收: push a commit to a scratch repository's main and see a CI run within the set time without any manual sync; `kubectl -n cicd get pipeline bifrost-ci-platform -o jsonpath='{.spec.tasks[?(@.name=="test-api")].runAfter}'` lists both clones
- 审批 无（代码和流水线定义；流水线由 Owner 应用）· 代价 S · 风险 low · repos: bifrost-platform, bifrost-trade-infra

### TD-325

**P2 · ops-platform · after a platform restart an open Console page stops reading approvals, and clicking Approve sends nothing and says nothing**

- **状态**：观察中（到 TD-336 查清为止：看 Owner 的批准是否一次就到）。修复 2026-10-13 11:55 上正式环境（审批单 #13，提交 `becfb2e`；三轮实现、四次独立复核）：页面发现平台换了版本会提示刷新并暂时不让批准；读审批有 15 秒截止；批准的请求页面不再自己中止，第 30 秒起写明还在等；每张单子各管各的状态。验收里那一步（重启平台后不刷新页面去批）要用管理员令牌在浏览器里做，Agent 不碰，没有做。同一天 Owner 的三张单子仍各要点几次才到服务器，那是「请求没发出去而页面不说」，另记 TD-336（2026-10-13 18:35 记）
- **Claim**: after the production platform was restarted by a delivery (pods replaced at 20:32 CDT), the Console page that had been open in the Owner's browser kept polling the self-health and auth-capabilities endpoints but made no request for the approvals list and no approval request. The Owner approved request #12 twice on that page; nothing reached the API and the page showed no error. After a reload of the page the third click produced the approval request (a POST for that request's id, answered 200) and the request was executed.
- **Measured**: MEASURED 2026-10-12 21:36 CDT from the production platform-api log (request lines only): in 25 minutes, requests addressed to `ops.bifrost.lan` were 75 reads of self-health, 25 of auth capabilities, 5 of code-health; no read of the approvals list, no approval request, no 401 or 403. At 21:39:38 after the reload: 6 reads of the approvals list, 4 of the one request, one approval POST answered 200, and the audit line `approval.approve channel=console`. NOT MEASURED: what the stale page showed, whether it is the restart or the new Console bundle that breaks it, and whether the same happens on a phone.
- **Evidence**: approval `appr_aa92542ae974d7f8` (created 02:24:36Z, decided 02:39:38Z); the coordinator's two reads of the record in between (still pending); `bifrost-platform/console/` (the approvals page and its data hooks).
- **Impact**: the Owner believes he approved and the system waits. On 2026-10-12 it cost about seven minutes and two extra rounds in the thread; with nobody reading the record it would have stalled until the request expired. It is the same class as TD-316 / TD-317: the one surface that must be true tells the Owner something that is not so.
- **Fix**: find why the page stops (a stale bundle after the Console deployment, a dropped event stream, or a data hook that gives up after an error) and make it recover; an approve click that cannot send must say so; when the page detects a new Console build it reloads or tells the user to.
- **Ratchet**: a Console test that an approve click either produces the request or shows an error — never neither; a test for the hook after a failed fetch.
- 验收: with the approvals page open, restart platform-api and platform-console on STG, create a request, approve it on the page without reloading: the request is decided, or the page says why not
- 审批 无（代码改动，随平台发布）· 代价 S · 风险 low · repos: bifrost-platform


### TD-327

**P2 · infra · the daily logical database dumps on the NAS are unencrypted; whoever can mount the share can read production data**

- **状态**：未开始（2026-10-12 23:58 从 TD-326 分出来；Owner 当晚定：先推出共享、加闸门，加密排在多 Agent 架构做完之后）
- **Claim**: `k8s/data/logical-backup` writes its daily dumps of `bifrost_prod` and of four Golden Source schemas to the NAS in the clear (`k8s/data/logical-backup/README.md`). The cluster-state backup and the Gitea backup are encrypted to the Owner's public key before they reach the NAS; the logical dumps are not. TD-326 took the share off the development Mac and put a text tripwire in the agent guard; neither changes what is on the NAS.
- **Measured**: NOT MEASURED beyond what TD-326 recorded (the share was mounted on the Mac until 2026-10-12 23:07; nothing under it was listed or read).
- **Evidence**: `k8s/data/logical-backup/README.md`; `k8s/data/cluster-state-backup/README.md` and `k8s/cicd/gitea-backup/README.md` (the encrypted ones, and how they do it).
- **Impact**: any machine or account that can mount the share reads account and trade data without touching the cluster. The monthly restore drill in the cluster reads these dumps, so encrypting them changes the drill too.
- **Fix**: encrypt the dumps to the Owner's key as the other two backups do; give the restore drill a way to read them that does not put the private key in the cluster (the Gitea backup's verify-before-encrypt shape is the precedent); decide what happens to the dumps already on the NAS.
- **Ratchet**: the backup job's own check that what it publishes is ciphertext (as `k8s/cicd/gitea-backup/verify-stage.sh` does), and the restore drill passing against an encrypted dump.
- 验收: a dump fetched from the NAS cannot be read without the Owner's private key; the monthly restore drill still passes
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-trade-infra

### TD-328

**P3 · agent-governance · the NAS rule of the agent guard is a text tripwire: several ordinary spellings get past it, and two native file tools are not gated at all**

- **状态**：未开始（2026-10-12 23:58 TD-326 的复核列出来的，不挡合并；排在多 Agent 架构做完之后）
- **Claim**: the rule added for TD-326 matches text. The reviewer's table: a glob in the share's name, quotes or a backslash inside the path, a different letter case, `cd` to the mount root first, a shell variable for the root, and a recursive command on the bare mount root are all allowed today. Claude's native Grep and Glob are not in the hook's matcher, and Cursor's native file tools do not pass the guard. A terminal tool's working-directory field is not checked. The same gaps exist for the Owner-credential rule.
- **Measured**: MEASURED 2026-10-12 by the reviewing subagent against commit `de9348e` with all three callers' payload shapes (10 named bypasses: 1 refused, 9 allowed); a prototype of three small rules (normalise quotes, backslashes and case before matching; refuse a glob in the first path segment under the mount root; refuse the bare mount root with a recursive command) closed 7 of the 9 with every existing test green and no ordinary command refused.
- **Evidence**: `agent-config/scripts/agent-guard/preflight.js` (`nasPathRule`, `nasGuard`); `agent-config/scripts/agent-guard/README.md` (the rule and what it does not cover); `agent-config/claude/settings.json` (the matcher).
- **Impact**: the tripwire stops the plain mistake, not a determined or an unlucky spelling. What closes the path is the share staying unmounted (the board watches the mount table) and TD-327.
- **Fix**: the three small rules above, with the reviewer's table as tests; decide separately whether Grep and Glob join the matcher (it touches every rule, not this one).
- **Ratchet**: the bypass table as cases in `agent-config/scripts/agent-guard/test.js`.
- 验收: `node agent-config/scripts/agent-guard/test.js` passes with the seven closed spellings refused and the reviewer's list of ordinary commands still allowed
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-330

**P2 · ops-platform · a push to infra main that touches the production platform's manifests is deployed by Argo at once, with no approval and no release check**

- **状态**：未开始（2026-10-13 11:34 护栏 ⑤ 选路时记下：Owner 选了走标签，钉住清单的做法留到第 3 轮和全自动发布一起看）
- **Claim**: the Application `bifrost-platform-prod` follows `main` of the infra repository with automated sync, prune and selfHeal. Any session that pushes a change under `k8s/overlays/platform-prod` or `k8s/base-platform` changes production; the approval request, the release window and the source check of the delivery pipeline are not on that path. Twelve repositories and several agent sessions push to that branch every day.
- **Measured**: MEASURED 2026-10-12 22:45 read-only: `targetRevision=main`, `automated={prune:true,selfHeal:true}`, no `ignoreDifferences`. About 20 commits touched those two directories in the month before (counted for the design, `agent-work` notes; NOT re-counted here).
- **Evidence**: `k8s/cicd/applications/bifrost-platform-prod.yaml:12-22`; `bifrost-trade-infra/CLAUDE.md` ("推 main 即改运行时"); the three design drafts and reviews 141, 143, 148 of guardrail 5 (pinning the Application to a commit advanced by the delivery pipeline closes this, and was not chosen now: three drafts still had wrong-answer paths).
- **Impact**: the one production surface an agent can change without the Owner seeing a request. A wrong edit to a ConfigMap generator there rolls the API and the workers.
- **Fix**: either pin the Application to a commit that only the delivery pipeline advances (the design exists, unfinished), or a smaller guard first: the agent guard and CI refuse a push that touches those two directories unless it carries an approved request's id; decide when round 3 is planned.
- **Ratchet**: a read-only check that the live `targetRevision` and sync policy are what the ledger says, and whichever guard is chosen.
- 验收: a change under `k8s/overlays/platform-prod` reaches production only through an approved request
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-trade-infra, bifrost-platform

### TD-331

**P3 · ops-platform · production pods of the platform are deployed by a movable tag: after a promotion, a restart pulls whatever `:prod` points to then**

- **状态**：未开始（2026-10-13 13:05 Owner 定：护栏 ⑤ 收口，标签那一片不做；正式环境照旧重新构建后推 `:prod`。这一条照旧成立：Pod 按可改写的标签部署。下面 Claim 里「with the tag route」的前半句不再适用，见 TD-335）
- **Claim**: with the tag route, a production delivery puts the pair of images verified on STG under `:prod` and checks that the pods run that pair when the delivery ends. The Deployments still name the tag and pull `Always`; the registry has no authentication. A later push to `:prod`, or the developer script that pushes it by default, changes what the next restart runs.
- **Measured**: NOT MEASURED (read from the manifests and the registry Deployment during the design of guardrail 5).
- **Evidence**: `k8s/overlays/platform-prod/kustomization.yaml:57-63`; `k8s/overlays/platform-prod/images-pull-always.patch.yaml`; `k8s/cicd/registry/deployment.yaml`; `bifrost-platform/scripts/push-platform-api.sh:4-7,33-36`.
- **Impact**: "production runs what was verified" holds at delivery time, not afterwards.
- **Fix**: write the digests into the production manifests (needs TD-330's pinning, or another way to advance manifests behind the gate); until then a cheap detector: compare the running pods' digests with the last delivery's recorded pair on a schedule and alert on a difference.
- **Ratchet**: the detector's alert rule.
- 验收: a pod restarted a day after a delivery still runs the recorded pair, or an alert says it does not
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-trade-infra

### TD-332

**P2 · ops-platform · approved actions have no time limit of their own and a running one cannot be stopped; the only bounds are the record's one-hour deadline and a platform restart**

- **状态**：未开始（2026-10-13 12:50 TD-329 的实现报告和独立复核列出的；Owner 10-12 定：多 Agent 协作架构做完之前只记不做）
- **Claim**: after TD-329 a synchronous execution lasts until the record's deadline (one hour after approval) instead of the roughly five minutes the Console's nginx read timeout used to give it by accident. Several executors have no limit of their own: `kubectl drain` runs without `--timeout` (a drain blocked by a PodDisruptionBudget retries every five seconds for the hour while the node stays cordoned and the request shows running); ssh in the node power actions has only a connect timeout; the firewall apply has no limit in Go; four executors start `exec.Command` without the context at all and `trigger_data_clone` continues on a background context; the attempt made by the background retry loop runs on `context.Background()` with no deadline. There is no way to stop a running request. platform-api has no shutdown handling: on SIGTERM an execution in flight is cut and its record becomes unknown eleven minutes later. One mislabel: an executor that runs the full hour and then answers 503 or 429 leaves the record `expired`, and the notice says "approved but never ran". One mismatch on the page, new with TD-329 and read from the code only: when an action runs past five minutes nginx answers 504, the approvals page shows a red error that is not tied to the record and is cleared only by the next decision click, while the record is `running` and later `executed` (`bifrost-platform/console/src/pages/ApprovalsPage.tsx:398-402`). The PodDisruptionBudgets on the nodes were not checked.
- **Measured**: MEASURED by the reviewing subagent's probes on the TD-329 branch (2026-10-13): the record after a simulated process loss becomes unknown at lease + grace and is not executed again; the deadline case ends `expired` with one executor call. NOT MEASURED on a cluster: no real drain was left hanging.
- **Evidence**: `bifrost-platform/api/internal/cluster/node_lifecycle.go:147-159`, `node_power.go:294-314,410-438`; `network/apply.go:29`; `cluster/handler.go:147,187,193`, `metrics_server.go:47`, `observability_install.go:47`, `sync.go:51`; `cluster/data_clone.go:580`; `server/server.go:357-362`; `cmd/platform-api/main.go:28`; `approvals/service.go:304-312`.
- **Impact**: a stuck node or firewall action is reported an hour late and can only be ended by restarting the platform, which leaves the request unknown for the Owner to close.
- **Also found by the second review of TD-334 (2026-10-13 23:27, Codex, read-only)**: (1) shutdown waits five seconds for HTTP requests and does not wait for approval actions that are executing (a retry in the workers role, or a synchronous execution that outlives the five seconds), so a result computed after the final flush is lost when the process exits; (2) the final flush on shutdown tries once and the process exits even if the write failed; (3) a held result whose lease lapsed is dropped by `flushHeld` (`execution.go`, the `forgetFinish` on a lapsed lease) instead of being written as a late result, so a request whose action finished can still end unknown. All three predate TD-334; before it the process was killed outright on SIGTERM. Fix with this entry: track claimed and synchronous executions and wait for them (with each action's own deadline) before the final flush; keep an unwritten result where a restart can find it; let a lapsed held result take the existing late-result path.
- **Fix**: give each long executor its own limit (a `--timeout` on drain first), put a deadline on the background retry attempt, add a stop for a running request, handle SIGTERM by finishing or marking the records in flight, and word the expired-after-running notice truthfully.
- **Ratchet**: a test per executor that it ends within its limit when the command hangs; a test that the background attempt's context has a deadline.
- 验收: an approved drain on STG against a node with a blocking PodDisruptionBudget ends as failed within its limit, and the request can be stopped before that
- 审批 无（代码改动，随平台发布）· 代价 M · 风险 med · repos: bifrost-platform

### TD-335

**P3 · ops-platform · a production delivery of the platform rebuilds both images from the commit instead of promoting the pair that STG verified; a rollback rebuilds too**

- **状态**：未开始（2026-10-13 13:05 Owner 定：护栏 ⑤ 收口，这一半留到第 3 轮，和 registry 写保护一起做） 2026-10-13 20:54 实测一例：同一个提交 `38500f9`，测试环境构建的是 api `sha256:ced00aab…`、console `sha256:52eda002…`，正式环境（#16）重新构建出来的是 api `sha256:e9020617…`、console `sha256:1867798e…`——两边跑的不是同一份镜像。
- **Claim**: production builds its own images from the approved commit (the same commit STG ran, checked by the source gate). Base images and dependencies can differ between the STG build and the production build, which were eleven hours apart on 2026-10-13. Two designs for using the STG artefacts were stopped after independent review: pinning digests into the production manifests (three drafts) and promoting by tag (two drafts). Each still had a path where the delivery succeeds while the claim is untrue, because the registry accepts unauthenticated writes with no compare-and-set and the cluster reads are not atomic. W-56's "rollback without rebuild" is open for the same reason.
- **Measured**: MEASURED 2026-10-13 for commit bf39f96: the STG images and the production rebuilds have different digests (console `sha256:5cd4…` on STG, `sha256:9fd9…` on PROD), while the Console bundle file has the same content hash in both. Whether the images differ in anything that matters was not examined; nothing compares them. After guardrail 5 closes, a delivery records the digests it built and checks its own pods against them, in STG and in production.
- **Evidence**: `k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:474-570` (the six build tasks); `agent-config/work/multi-agent/DESIGN-guard5-tag-route-stopped.md` (the stopped design and why); `agent-config/work/multi-agent/LESSONS-from-practice.md` row 119; `docs/RELEASE.md:229`.
- **Impact**: "production runs what was tested" holds for the source commit, not for the image bytes.
- **Fix**: first give the registry write protection for `:prod` (or deploy by digest, TD-331); then promote the recorded STG pair. State the acceptance with its time meaning before the first draft: what is proven at the moment it is read, and which later changes are accepted risks.
- **Ratchet**: a structure test that the production pipeline has no build task; the promotion's own tests.
- 验收: a production delivery whose pipeline run contains no build task, and whose pods run the digests recorded by the STG delivery it promoted
- 审批 审批单（PROD 发布）· 代价 L · 风险 med · repos: bifrost-trade-infra

### TD-336

**P1 · ops-platform · the Owner clicks Approve in the Console on his Mac and nothing reaches the server; the page does not tell him. Three production requests on 2026-10-13 each needed several attempts**

- **状态**：观察中（到下一次「点了没到」，或 2026-10-20：看新页面当时写了什么）。页面这一半 2026-10-13 20:54 上正式环境（审批单 #16，平台 `38500f9`）；**原因那一半没有开始**，是第 2 轮的候选。#16 是从手机批的，建单后 78 秒到服务器（日志里发批准的是 iPhone）；当天没到服务器的四次都是从 Claude 桌面应用内置的浏览器窗格点的。此前：在做（页面这一半 2026-10-13 20:37 进平台主线 `38500f9`：决定页写明上次连到服务器的时间；点决定前先检查连接，5 秒没回话就不发并写明没发；发出 5 秒没确认也写明。Codex 写，统筹方修，Claude 的子代理独立复核三次，最后一次「可以合并」。原因那一半没有查清，线索见下面「Found」一段）。以下是开工前的记录：未开始（2026-10-13 14:11 统筹方从正式环境的访问日志查出来的；原因没有证实，等 Owner 说明他点的那个页面当时显示了什么。建议排进第 1 轮：它就是 A 项「点了批准必须有结果或有报错」在真实使用里还没成立的那一半）
- **Claim**: TD-325 made the page honest once a decision request is on its way. On 2026-10-13 the decision requests were not sent, or were sent late, and the Owner believed each time that he had approved. #13: four attempts over sixteen minutes; the access log shows no request of any kind from the Mac's browser to the production Console until a fresh page load at 16:50:50 UTC, and the approval five seconds later. #14: no request from the Mac for more than twenty minutes, then a burst of reads together with the approval in the same second (18:04:08 UTC), after he had already written that it was approved. #15: he reported it approved at 18:50 UTC; since the release at 18:08 UTC no browser on the Mac had loaded the Console or read the approvals list. It arrived at 23:10:59 UTC, four seconds after a fresh page load from the Mac; his three earlier reports (18:50, 19:33, 19:40 UTC, the last two after a hard refresh and after opening a new tab) left no request on the server at all, not even a page load. From the same Mac the address answered in 60 ms when tried by hand, so the network path was up. Not established: whether the tab was frozen in the background, whether an idle connection through the VIP was dead and the browser kept using it, whether the service worker's cached shell made a dead page look loaded, or whether he was on a page left open across a release. In the same hour a browser on a Windows machine kept an old Console page open against production with the admin role, polling every minute and never reading approvals.
- **Measured**: MEASURED from the production Console's nginx access log and platform-api's request log (Loki, 2026-10-13 16:20–18:55 UTC), by device type from the user agent. NOT MEASURED: what the page showed, the browser's own network log.
- **Found 2026-10-13 20:30 (from the production Console's access log)**: the Owner's Console requests do not come from Google Chrome. Their user agent is `… Claude/2.37337.1 Chrome/152.0.7977.130 Safari/537.36`: the browser pane built into the Claude desktop app (Chrome on the same Mac is version 155). The three approvals of the day came from that pane. Its pages behave like background tabs when the pane is not in front: on 2026-10-13 from 20:17 CDT the page there stopped its 30-second reads and only fetched `/index.html` every three minutes (the build-drift check), and between 13:08 and 18:10 CDT it made no request of any kind, not even that one, while the Owner reported three clicks. So what he clicked was a page that was not running. Not established: what the pane does to a page it is not showing (suspends it, discards it, or shows a still image), and whether another thread driving the same pane plays a part. The Windows browser seen in the same log is a separate, unidentified session (Chrome 154, admin role, never reads approvals); the log cannot tell which machine (the client address is rewritten inside the cluster).
- **Found 2026-10-13 21:30 (ingress error log, one `curl`, one `lsof`; read-only)**: (1) Traefik logs only responses 400–599. For host `ops.bifrost.lan`, 18:00–23:20 UTC, it has four rows, all 502 during the two rollouts (18:0x and 23:1x UTC). Nothing for the hours in which the Owner clicked, force-reloaded and opened a new tab (18:21–23:10 UTC): no 499, no 5xx. His requests did not reach the ingress; a request that arrived and hung would have been logged when it was cancelled. (2) `https://ops.bifrost.lan` answers HTTP/2 and plain http is redirected to it (308). At 21:24 CDT the Claude desktop app held exactly one established TCP connection to `192.168.10.100:443`: everything the pane's Console tab does rides one connection, and a reload or a second tab for the same origin reuses it. The service worker serves the cached shell when the network fails (`sw.js`), so such a reload looks loaded. (3) The recovery at 18:10:55 CDT was the first page load after the desktop app had been quit and reopened (this thread stood still 14:43–18:10); the approval arrived four seconds later. For #13 (11:50) only "a fresh page load" is known. **Hypothesis, NOT MEASURED**: that one connection went dead without the app noticing (the Console's backend was replaced at 13:07; the Mac may also have slept) and the pane kept queueing requests on it. Chrome checks an idle HTTP/2 connection with a ping before it reuses it; whether the pane's network stack does is not known. **To confirm next time, before reloading**: `lsof -nP -iTCP@192.168.10.100` (is there an established connection from `Claude`), and what the new page says (since #16 it writes "Your decision was NOT sent" with the time of the last contact). The way round stays: approve on the phone or in Google Chrome; #16 from the iPhone reached the server 78 seconds after the request was made.

- **Recurred 2026-10-13 23:42 (#17)**: the Owner wrote in the thread that #17 was approved; at 23:42:11 CDT the record was still `pending` with no decision. Read-only checks taken before any reload: (1) `lsof -nP -iTCP` on the Mac: no connection of any process, in any state, to `192.168.10.100` (827 TCP rows in total; the Claude desktop app had none). (2) The production Console's access log, 23:35–23:42 CDT, without probes: one `GET /api/v1/code-health` from Windows at 23:38:05 and the Windows session's health polling; nothing from a Mac, the Claude pane or an iPhone; no decision request. (3) platform-api's log in the same window: the request was created at 23:39:30 and the ntfy notice accepted; no approve call. Not yet known: which device and page he used and what the page said. **How it went through (same log, 23:43–23:44 CDT)**: the Owner wrote that he approved again on the phone. The request that arrived came from the Claude desktop app's pane on the Mac (user agent `Macintosh … Claude/2.37337.1 Chrome/152.0.7977.130`), not from an iPhone: a burst of reads at 23:43:51 (approvals, questions, progress, the request itself), a full page load at 23:44:00 (`GET /`, the assets, `/index.html`), and `POST …/approve` 200 at 23:44:02, two seconds after the load; afterwards the Claude process held one established connection to `192.168.10.100:443`. Whether he drove the desktop app from the phone (remote control) was not established. What this adds: at 23:42 the pane had **no** connection at all, not a dead one, so the earlier click did not queue on a broken HTTP/2 connection; the page made no request whatever until it came back to life. This weakens the "dead connection" hypothesis above and supports "the pane's page was not running". The approval again arrived seconds after a fresh page load.
- **Not an occurrence, 2026-10-14 10:30 (#18)**: at 10:30:28 CDT #18 was still `pending` after the Owner wrote it was approved; he then wrote that he had only just clicked. His click from the Claude pane reached the server at 10:30:56 and the delivery started at once. Useful as a baseline: before the click the pane held one established connection to `192.168.10.100:443` and ran only its three-minute `/index.html` timer (no 30-second approvals polling), yet the click went through — so a throttled page can still send a decision. Lesson for the coordinator: before treating "approved but pending" as TD-336, ask whether the click has happened yet.
- **Answered 2026-10-13 22:57**: the Windows Chrome 154 session that polls the production Console with the admin role all day is the Owner's own (he confirmed in the thread). It is not an unknown client; read it out of the access logs as his.
- **Evidence**: `bifrost-platform/console/public/sw.js:38-62` (navigation falls back to the cached shell when the network fails); `console/src/pages/ApprovalsPage.tsx` (the 30-second waiting sentence is the only signal while a request is unanswered); `agent-config/work/multi-agent/LESSONS-from-practice.md` row 118.
- **Impact**: the one action only the Owner can take fails silently for him; each failure costs several round trips and holds every line that waits on the approval.
- **Fix**: find the cause first (his description or a screenshot of the page after the click; the browser's network panel). Then make the page say so: show when the server was last reached, refuse to offer a decision while it has not been reached for some seconds, and after a click say "not acknowledged by the server yet" within a few seconds rather than after thirty. Consider not serving the cached shell for the decision pages.
- **Ratchet**: a page test: with the network dead, the decision buttons are unavailable with a sentence saying the server has not been reached since a given time; a click that gets no answer says so within five seconds.
- 验收: the Owner approves three production requests in a row at the first attempt, and the server log shows each request arriving within seconds of the click
- 审批 无（代码改动，随平台发布）· 代价 M · 风险 med · repos: bifrost-platform

### TD-337

**P2 · ops-platform · routine platform releases still wait for the Owner's approval, and one pending request freezes the platform's STG: on 2026-10-13 three chained requests left the line idle for about nine hours**

- **状态**：未开始（2026-10-13 19:22 Owner 定：不做通知静默时段，也不做「撤回待批单」这类机制；该调整的是哪些单子需要人批，那是 W-56 的规则，等它的门槛做完由他签；现在不强求。统筹方先改排法：他不在时不建单，做完的攒着，他在时合成一张）
- **Claim**: by the architecture's definition of the human's role (goals, rules, irreversible things) the three requests of 2026-10-13 (#13, #14, #15: reversible code releases of the platform, with green CI, the same commit on STG and an independent review) did not need a human decision. They reached the Owner because the release policy does not list the production pipelines until W-56's thresholds are accepted (his decision of 2026-10-10). While a request is pending, the source gate of a production delivery (the newest successful STG delivery must be the requested commit) keeps anything else off the platform's STG, so requests made one by one form a chain: #13 waited 10 h 51 min, #14 1 h 2 min, #15 4 h 49 min.
- **Measured**: MEASURED 2026-10-13 from the request records and from the coordinator's commit and event log (no activity 06:08–11:34 and 14:29–18:13 CDT; the second gap was a stalled thread, LESSONS row 120).
- **Evidence**: `scripts/release/platform_prod_gate.py:165-187`; `agent-config/WORK.md` W-56 (thresholds, and the Owner's notes of 2026-10-10, 2026-10-12 and 2026-10-13); `agent-config/work/multi-agent/LESSONS-from-practice.md` row 121.
- **Impact**: every routine release costs the Owner an approval and stalls the platform line while he is away.
- **Fix**: finish W-56's thresholds (rollback without rebuild, failure detection, the drills) and have the Owner sign a release policy that lists the platform's production pipeline; after that only three kinds of release reach him: outside the policy, a failed or stuck check, during a freeze. Until then the coordinator batches: no request while he is away, one request for everything verified on STG when he is back.
- **Ratchet**: the policy template's own test (production pipelines stay out of the policy until the thresholds are accepted) is the line to move, with his signature.
- 验收: a routine platform release reaches production with no approval request, and a release outside the policy still produces one
- 审批 Owner 签规则（放宽）· 代价 L（W-56 的剩余门槛）· 风险 med · repos: bifrost-platform, bifrost-trade-infra

### TD-340

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

### TD-342

**P3 · testing · a delivery test waits 40 ms and expects six reads in that time, so it fails under the load of the whole suite**

- **状态**：未开始（2026-10-14 14:16 统筹方记；合并前在合并后的树上跑整套时撞上，单独重跑三次都过；第 2 轮期间不还其余技术债，排在架构之后）
- **Claim**: `TestPlatformUnknownDoesNotMaskMissing` gives `StartPipelineRun` a 40 ms context and then requires at least six GETs of the `bifrost-ui` refs ("no second look"). On a loaded machine fewer polls fit in 40 ms and the test fails though the code is right.
- **Measured**: MEASURED: 2026-10-14, `go test ./...` on the merge of `w31/agentrt-22-route` into platform main (`5a6c98e`, which changes no file in `internal/delivery`): FAIL `platform_ref_rules_test.go:90: no second look`, package 35.9 s; the same test alone three times: ok (0.8–1.3 s). 2026-10-15 23:4x the same file's `TestPlatformPollingErrorRequiresSeenPresent/bifrost-deliver-platform-prod/poll_error_missing` failed once in `go test ./...` ("did not poll past error and missing", load average ~20 while vitest ran beside it) and passed alone three times (17.7 s each): the same kind of wall-clock wait.
- **Evidence**: `bifrost-platform/api/internal/delivery/platform_ref_rules_test.go:77-92`.
- **Impact**: a red whole-suite run that is not a regression; whoever runs the suite before a push has to tell it apart by hand, and CI can flake the same way.
- **Fix**: make the second look not depend on wall time: count polls through the fake's own clock or a poll hook, or wait for the sixth GET before cancelling instead of a fixed 40 ms.
- **Ratchet**: the test passes under `go test -count=20 -cpu 1,4 ./internal/delivery/` with the suite's other packages running beside it.
- 验收: the ratchet command above
- 审批 无（测试改动，随平台发布）· 代价 S · 风险 low · repos: bifrost-platform

### TD-378

**P3 · testing · a test of the admission-guard check fails on main: its fake `subprocess.run` answers the Application read too**

- **状态**：未开始（2026-10-19 05:0x 记；runtime-repo-infra 线摸底 infra 的 Python 测试时撞上）
- **Claim**: `scripts/test_access_checks.py::DryRunClassifyTests::test_live_stops_before_any_dry_run_without_impersonation` fails on every machine since review 261/262: `check_admission_guards.live()` now reads the live `bifrost-research` Application (`live_application`) before it asks about impersonation, and the test's fake `subprocess.run` answers every call with exit 0 and "no", so `json.loads("no")` raises before the check the test is about.
- **Evidence**: `bifrost-trade-infra/scripts/check_admission_guards.py:214`, `:435`; `scripts/test_access_checks.py:77-99`; commits `f3d3fab`, `4d04561`. Measured 10-19 on main `710723d` with and without kubectl on PATH: 1 failed, 9 passed.
- **Impact**: nobody sees whether `live()` still stops before any dry run without impersonation; the runtime's infra check leaves the file out (platform `w31/repo-infra`, `store/repos.go` `infraTests`) until it passes.
- **Fix**: let the fake answer `kubectl get application` with a non-zero exit (no Application) or a minimal Application JSON, and keep the assertion that every other call is `kubectl auth can-i impersonate`; then add the file to `infraTests`.
- **Ratchet**: the file joins the runtime's infra check, which runs it on every infra task.
- 验收: `python3 -m pytest -q scripts/test_access_checks.py` passes on main, and `scripts/test_access_checks.py` is in `infraTests`.
- 审批 不需要（测试改动）· 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-377

**P3 · agentd · security · an executor still reads what its user can read: token files and other attempts' workspaces**

- **状态**：未开始（2026-10-19 03:4x 记；你 03:3x「三件照建议」③，第 2 轮先接受）
- **Claim**: TD-371's wall (platform `35eafb7`, Landlock) holds what an attempt writes, not what it reads. Under the same Unix user an executor reads that user's token files and every other attempt's workspace and output on the host.
- **Evidence**: `bifrost-trade-infra/agent-config/work/multi-agent/CUT-agentd-confine-2026-10-19.md` §7 item 1; `bifrost-platform/api/internal/agentd/confine.go`.
- **Impact**: an executor that turns on its task can copy another attempt's work or the user's credentials into its own result; the review and the platform's redaction are the remaining lines.
- **Fix**: give the wall read rules too (Landlock read access listed per top-level directory, `/home` only the attempt's own), after measuring on 06 which home-directory files each executor really reads; or one Unix user per slot.
- **Ratchet**: the 06 confine probe gains a read check: a file of another attempt and a token file are refused to an executor.
- 验收: that probe check passes on 06 for codex, cursor and claude.
- 审批 不需要（只改 agentd；06 上跑探针要你一次）· 代价 M · 风险 medium · repos: bifrost-platform, bifrost-trade-infra

### TD-376

**P3 · agentd · security · a process a setup command leaves behind (setsid) outlives the check and can drop a cursor hook into the workspace**

- **状态**：未开始（2026-10-19 03:4x 记；你 03:3x「三件照建议」③，第 2 轮先接受）
- **Claim**: agentd kills an attempt's process group, but a process that left the group with `setsid` during the setup step keeps running inside its own (narrow) wall. After agentd's `--refuse` check and before cursor reads its configuration it can write `.cursor/hooks.json` into the workspace; the hook then runs inside cursor's wall. `checkChanges` fails an attempt that leaves executor configuration behind, so the result is not accepted, but the hook has run.
- **Evidence**: `bifrost-trade-infra/agent-config/work/multi-agent/CUT-agentd-confine-2026-10-19.md` §7 items 4 and 5; `bifrost-platform/api/internal/agentd/setup.go`, `run.go`.
- **Impact**: a hostile dependency's install script can run code as cursor inside cursor's write wall; it cannot write outside the attempt's directories.
- **Fix**: run each attempt in its own cgroup (systemd `Delegate=yes` on the agentd unit, a child cgroup per attempt) and kill the whole cgroup after setup and at the end, so nothing outlives its step.
- **Ratchet**: a test on Linux: a setsid process started by setup is gone before the executor starts.
- 验收: that test passes on 06 (the confine probe gains the check), with `Delegate=yes` in both agentd units.
- 审批 要（改 06 上两个 agentd 的 systemd 单元，架构决定；你批）· 代价 M · 风险 medium · repos: bifrost-platform, bifrost-trade-infra

### TD-375

**P3 · agentrt · security · threads that share one token can still act as each other, and the question routes still take the session header on its word**

- **状态**：未开始（2026-10-19 03:2x 记，TD-370 的修法交回时指出：绑定只区分不同的令牌）
- **Claim**: TD-370 holds a thread's session to the token that first wrote as it. Every thread on the development Mac holds the same reporter token, so one of them can still name another's session and read its mail, acknowledge it, send and propose as it; the questions routes read `X-Bifrost-Session` for its shape only.
- **Evidence**: `bifrost-platform/api/internal/agentrt/store/keyed.go` (the binding, platform `6964fd2`), `api/internal/server/questions_wire.go`; the lane's report (session local_af7f0365, 10-19 02:43).
- **Impact**: a thread's mail from the Owner or the chief of staff, and the record of who proposed what; not the Owner's or a seat's identity, which come from their own tokens.
- **Fix**: each thread gets its own token from the Console when it registers (the reporter token only registers), and the questions routes take the session from the token as the agentrt routes now do.
- **Ratchet**: a route test: a thread token naming another thread's session is refused on every write, on `GET /messages` and on the questions routes.
- 验收: that test passes on main, and the reporter token can no longer write as a thread.
- 审批 不需要（只改平台）· 代价 M · 风险 low · repos: bifrost-platform

### TD-374

**P2 · ci · the agentrt store package's tests run close to CI's 120 s test timeout**

- **状态**：在做（10-19 04:0x：store 测试改并行在分支 w31/store-parallel `c360937`，本机 store 包 76 秒 → 31–44 秒，复核 322→323 收线，防线 TestTestsRunInParallel；合进 main 后看三次 ci-platform 里 store 包都在 90 秒内，到时进「待你签收」）（2026-10-18 23:0x 记）
- **Claim**: `ci-platform` runs `go test ./... -count=1 -timeout=120s`, and the timeout is per test binary. The agentrt store package took 82–88 s in CI until 10-18 evening, then went past 120 s twice under load (ci-platform-m6zlf, ci-platform-vxxn2: "panic: test timed out after 2m0s", whatever test was running). Copying each test database from a migrated template (`8a43413`, 1.2 s to 0.2 s a database measured here) brought it to 109 s in ci-platform-gmb5f, still close: one busy CI pod, or a dozen more tests, and main goes red with nothing wrong.
- **Evidence**: `bifrost-trade-infra/k8s/cicd/tekton/pipeline-ci-platform.yaml:176`; the three runs above (`kubectl logs` of their test-api pods).
- **Impact**: a red main blocks STG and PROD releases until a re-run passes; it cost a push and a re-run on 10-18.
- **Fix**: raise the step's `-timeout` to 300s (a change to the pipeline in `cicd`, the Owner's), and/or let the store package's tests run in parallel (`t.Parallel()` where a test touches no package-level hook or clock: `SetHook`, `eventClock`).
- **Ratchet**: none possible without the fix itself; a timeout is the only line there is.
- 验收: three consecutive ci-platform runs with the store package under 90 s, or the step's timeout at 300 s.
- 审批 要（改 cicd 里的流水线，你批）· 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-373

**P3 · agentd · the benchmark on 06 cannot run every question of the set**

- **状态**：待你签收（2026-10-19 01:5x；记于 2026-10-18 20:4x，复核 288 第 15 项与其检查限制、290 第 2 项；10-19 题集换新、agentd 带旁边仓库与接口，复核 292–294 收线）
- **Claim**: the 20 questions were picked and checked on the Mac, where the test database, the sibling repositories and each repository's Python dependencies are at hand. On 06 a check runs in a fresh snapshot with only the question's own repository, its lockfile's dependencies and pytest. The first run (`bench-20261019T021441-codex`, 10-18 21:14–21:39) had 11 runnable of 20: the TypeScript questions had no `../bifrost-ui` beside them (npm ci refused, or the UI import failed), Q01's store tests skip without `AGENTRT_TEST_PG` (the code before the fix passes too), Q09 imports `bifrost_api` that nothing installs. And some runnable ones measured a guess: hidden tests calling names or comparing texts the fix introduced (Q02 `pathRewrite.rewrite`, Q07 `refuseMail`, Q19 `VENDOR_CREDS_DIR` and "<file> did not reach <user>").
- **Done (10-19)**: agentd (platform `cf550fc`, `46f8fa8`, `d788296`; 06 build `agentd-d788296`): a question's `siblings` (repo + commit) are cloned, built (locked dependencies without install scripts, then the build in the check sandbox, offline) beside the trees before the controls and read only by the checks; a lockfile npm ci refuses as out of step (EUSAGE) is resolved once a question by a whole `npm install --ignore-scripts`, kept in agentd's memory, and every tree of the question installs that one resolution with npm ci (review 292 B6); `npm-shrinkwrap.json`, `.pytest.ini`, `pytest.toml` are protected too (292 A1, 293 A1); the question's `interface` (what its tests call that the code before the fix lacks: declarations without bodies or values, the names of new environment variables, new options, the texts the tests compare that the fix wrote inside a string literal) goes into the executor's prompt. Question set (`agent-config/work/multi-agent/benchmark/questions.json`, sha256 `2ad883e8`): Go 10, TS 7, Python 2, shell 1. Replaced (the first set's ids): Q01 and Q07 (every selected test skips without a test database: Q07 passed on compiling alone), Q09 (dependencies), Q11 (tests import a new non-test helper, `harness.py`, of a whole new feature), Q17–Q20 (tests compare texts or a return field the commit message does not give). Python and shell are short because no other fix of the last 150 days stands on 06 and is fair: `2583cc691` skips without dagster, `f783e8e89` adds only fixtures, `2aadf5d90` needs a format it does not state; seven shell candidates compare composed messages. Each of the 20 checked on this Mac through agentd bench's own judgement with nothing but its repository and siblings, no test database, no network (`api/internal/agentd/benchreplay_test.go`, the executor applying the fix's own change): the fix passes, the code before it with the fix's tests fails, the fix's change passes the judgement; fairness read twice by an independent reviewer.
- **Evidence**: `bifrost-platform/api/internal/agentd/benchrun.go` (`sibling`, `setup`, `benchPrompt`); `scripts/benchmark/interface.py`; the first run's event on STG (`GET /api/v1/agentrt/events?stream=capability_benchmarks`); `~/agent-work/codex-review-288/REPORT.md` item 15; `~/agent-work/codex-review-290/REPORT.md` item 2; `~/agent-work/codex-review-29{2,3,4}/REPORT.md`.
- **Impact**: fewer samples per executor than planned until the run on 06 shows the count.
- **Left**: a text the fix composes from variables (`"$f did not reach $u"`) is not found by the verbatim match, so such questions are left out rather than described; `pick.py` assumes vitest for `*.test.ts` (the MCP package runs `node --test`), so its fixes are not candidates.
- **Ratchet**: the run's handed-in results list each unrunnable question with its reason; the count of runnable questions is in the capability_scored event; a new question set is checked with `benchreplay_test.go` before it ships (README).
- 验收: a run on 06 with at least 15 runnable questions of the 20.
- 验收结果：PASS 2026-10-19 platform `d788296`（06 上 `agentd-d788296`）：`bench-20261019T060504-codex`（01:05–01:53，你在终端起的）20 道全部能跑、0 道跑不了；判对 16、判错 4（Go 8/10、TS 7/7、Python 1/2、shell 0/1）。判错的 4 道都是检查跑完给出的结论（Go 两道 `go test` 退出 1，Python、shell 各一道 pytest 未过），不是跑不了；STG `GET /api/v1/agentrt/events?stream=capability_benchmarks` 里的 results 与 samples。
- 审批 不需要（06 上跑要你一次）· 代价 M · 风险 low · repos: bifrost-platform, bifrost-trade-infra

### TD-372

**P3 · agentrt · schema · a capability_score row's identity has no model provider**

- **状态**：未开始（2026-10-18 19:0x 记，复核 286 B1；随下一次 agentrt 迁移一起做）
- **Claim**: `capability_score` is unique on (executor, model, tool_version, job, task class, core, source, window_end), without `model_provider`. One executor running one model name under two providers in one in-job computation (cursor with `opus` from anthropic and from cursor-mix) makes two groups with one identity. The computation inserts with `ON CONFLICT DO NOTHING`, so the second group has no row; its sample is still in the computation's `capability_scored` event, which is what routing reads, so routing is right and only the table (the record a screen would show) misses it.
- **Evidence**: `bifrost-platform/api/internal/agentrt/migrations/0001_core.sql:381`; `api/internal/agentrt/store/scores.go` (`ComputeScores`, the insert); `TestTwoProvidersOfOneModel`; `~/agent-work/codex-review-286/REPORT.md` item 1.
- **Impact**: none on routing; an audit gap in the table for that pairing only, none today (no candidate pairs one executor and model name with two providers).
- **Fix**: a migration that replaces the unique key with one that has `model_provider` after `executor_actor_id`, then the insert without `ON CONFLICT`; no data to move (append-only rows stay valid). Not done now: an agentrt migration is a Job the Owner creates on STG and PROD, with the PROD DDL approved first, and this alone is not worth that round.
- **Ratchet**: `TestTwoProvidersOfOneModel` asserts both rows once the key has the provider.
- 验收: `go test ./internal/agentrt/store -run TestTwoProvidersOfOneModel` with the row assertion added passes.
- 审批 要（PROD 的 agentrt 迁移，你建 Job）· 代价 S · 风险 low · repos: bifrost-platform, bifrost-trade-infra

### TD-371

**P2 · agentd · no executor shares the host until its whole process tree is held to its workspace**

- **状态**：在做（10-19：修法进 platform main `35eafb7`（Landlock 写墙、每次尝试自己的配置目录、setup 与执行者分墙，复核 300–303 收线）；06 用 `agentd-35eafb7` 待你装，装后 `agent-06-owner.sh confine-probe stg|prod` 两个都过、STG 上 codex、cursor、claude 各真跑一次，才进「待你签收」；第 2 轮先接受的两处另记 TD-376、TD-377）（2026-10-18 14:1x 记，复核 277 A2、278 A2）
- **Claim**: several attempts share 06 only when each can write nothing outside its own workspace (`share.go` `confined`). None qualifies yet. codex: its `workspace-write` sandbox also writes the shared temporary directories, and the host user's configuration can add writable roots (`sandbox_workspace_write.writable_roots`), which agentd neither pins nor checks. claude: the `Read,Grep,Glob` tool list does not reach command hooks in the user's or the repository's `.claude/settings.json` (a `UserPromptSubmit` hook runs as the user). cursor in ask mode: likewise `~/.cursor/hooks.json` and a repository's `.cursor/hooks.json` (`beforeSubmitPrompt`). A hook an earlier, unsandboxed setup left, or one an implementer put in its branch for its reviewer, runs as the agentd user.
- **Evidence**: `bifrost-platform/api/internal/agentd/share.go` (`confined`), `api/internal/agentd/executors.go` (`codexExecutor`, `claudeExecutor`, `cursorExecutor`); reviews `~/agent-work/codex-review-277/REPORT.md` item 2, `~/agent-work/codex-review-278/REPORT.md` item 2.
- **Impact**: no loss against round 2 so far (one attempt at a time); 2.4's "06 runs two or three at once" waits for this. A repository hook running in a reviewer is a risk with or without concurrency.
- **Found by review 283 (10-18)**: pinning the command line is not enough. State an earlier, unconfined run (setup commands, the deterministic executor, cursor on a branch task) can leave in the agentd user's home still runs commands outside a sandbox: codex's `hooks.json` with its trust state (`features.hooks=false` turns it off), a custom model provider's auth command (`model_provider="openai"` pinned), saved exec rules (`--ignore-rules`), an MCP server in a trusted checkout's `.codex/config.toml` (open: the startup MCP check reads the daemon's directory only); claude's managed policy drop-ins in `/etc/claude-code/managed-settings.d` (root only; the host check refuses them). The pins in `411ed07` and the review 283 commit narrow codex; they do not confine it.
- **Fix**: give each attempt a configuration home of its own (a fresh `CODEX_HOME`, claude and cursor config directories under the attempt's output, the credentials put there by agentd, nothing an earlier run can have written), or run each slot as its own Unix user; and per executor, hold the whole process tree: codex with its writable roots pinned on the command line (`-c sandbox_workspace_write.writable_roots=[]`, the shared tmp excluded, `TMPDIR` a directory of the attempt's own output); claude with hooks off for every source (`--settings '{"disableAllHooks":true}'`, the setting sources limited) and cursor with a `HOME` of the attempt's own (its key comes from the environment) and the repository's `.cursor/hooks.json` refused; prove on 06 (Linux, under the agentd AppArmor profile) that a write outside the workspace is refused for each, and only then class it confined.
- **Measured so far (10-18, this Mac)**: claude: a checkout's `.claude/settings.json` hooks ran without flags and with `--setting-sources ""` or `--settings '{"disableAllHooks":true}'` neither did; both are on the executor since `65a277d`. codex 0.162 (macOS seatbelt) with `-s workspace-write -c 'sandbox_workspace_write.writable_roots=[]' -c 'sandbox_workspace_write.exclude_slash_tmp=true'`: writes to `/tmp` and the home directory refused, the workspace and the user's `$TMPDIR` written: `TMPDIR` must be the attempt's own, and `notify` (a command codex runs unsandboxed after each turn) pinned empty. cursor: not measured (its quota was spent and it stopped before any hook).
- **Ratchet**: tests that each executor's argv and environment carry the pins, and an `agent-06-owner.sh` probe per executor that a write outside its workspace is refused on the host.
- 验收: the probes refuse the writes on 06; `TestConfined` classes an executor confined only with its pins.
- 审批 不需要（只改平台与 agentd；06 上跑探针要你一次）· 代价 M · 风险 medium · repos: bifrost-platform, bifrost-trade-infra

### TD-370

**P2 · agentrt · security · a thread is who its session header says: any token that may propose reads and writes as any thread**

- **状态**：观察中（到 STG 上线后核对：同一线程换令牌的写入和读信箱回 403 `not_yours`；PROD 随下一张合并单）（2026-10-18 02:4x 记，复核 269 B5 在 `GET /messages/thread` 上指出；那条路由已只给 Owner 和席位，`5a7fca3`；10-19 修法进 platform main `6964fd2`、`0423a7e`，复核 320、321 收线，防线 `TestSessionHeldToItsToken`）
- **Claim**: `writer()` maps a token that is neither the Owner's nor a seat's to `thread:<X-Bifrost-Session>`, and the header is checked for its shape only. A holder of the shared reporter token (every thread's) can send `X-Bifrost-Session: <another thread>` and read that thread's unread messages (`GET /messages`), acknowledge them, send as it, and propose missions and tasks recorded as it.
- **Evidence**: `bifrost-platform/api/internal/agentrt/agentrtapi/propose.go:28` (`writer`), `api/internal/agentrt/store/propose.go:32` (`threadSession`, shape only); the questions routes take the same header the same way.
- **Impact**: the threads on this Mac all hold the same token, so they can already act as each other; what is at stake is a thread's mail (from the Owner or the chief of staff) and the record of who proposed what (audit), not the Owner's or a seat's identity, which come from their own tokens.
- **Fix**: bind a session to a token when the thread first writes (the actor row keeps the token's name, a later write with another token is refused), or give each thread its own token from the Console when it registers.
- **Ratchet**: a route test: a second token naming a thread the first registered is refused on every write and on `GET /messages`.
- 验收: that test passes on main.
- 审批 不需要（只改平台）· 代价 M · 风险 low · repos: bifrost-platform

### TD-369

**P3 · mcp · the platform MCP package's type check is red, and no CI task runs it**

- **状态**：未开始（2026-10-18 02:0x 记，推 2.3 第 2、3 片前在分支头跑 `npm run type-check` 时看到；不是这个分支带来的）
- **Claim**: `tsc --noEmit` in `bifrost-platform/mcp/platform` fails with TS2367 (a comparison of `"refused"` and `"direct"`, which have no overlap). `ci-platform` type-checks the Console, not the MCP package, so the error went to main unseen.
- **Evidence**: `mcp/platform/src/writeGate.test.ts:85`, last changed on main by `9c8b183` (W-48); `k8s/cicd/tekton/pipeline-ci-platform.yaml:5` (the CI steps: go test, Console type-check, lint, test, build).
- **Impact**: the 116 MCP tests pass (tsx does not type-check), so nothing breaks today; a type error in the served tools would ship the same way.
- **Fix**: make the test's comparison match the write modes it means; add `npm ci && npm run type-check && npm test` for `mcp/platform` to `pipeline-ci-platform.yaml`.
- **Ratchet**: the CI step itself.
- 验收: `npm run type-check` in `mcp/platform` exits 0, and a ci-platform run shows the MCP step.
- 审批 不需要 · 代价 S · 风险 low · repos: bifrost-platform, bifrost-trade-infra

### TD-368

**P3 · agentd · a read of the executor's log that hangs cannot be cut short**

- **状态**：未开始（2026-10-18 01:5x 记，复核 266 第 3 项、267 第 2 项、268 第 2 项留下的 B；2.3 第 3 片收线时接受）
- **Claim**: the collector reads `log.txt` with `Open` / `Seek` / `ReadAll`; a read of a regular file cannot be interrupted in Go. If the disk call never returns, the flush and the attempt time out and go on, but the collector goroutine, its open file and the tail stay until the read returns.
- **Evidence**: `bifrost-platform/api/internal/agentd/actions.go`, `read` (the `os.Open` … `io.ReadAll` block) and `collect`; review 268 `~/agent-work/codex-review-268/REPORT.md` item 2.
- **Impact**: low: only a regular file is read (a FIFO or link is refused), agent-work is on 06's own disk, and a hung read holds one goroutine per attempt, never a heartbeat or the hand-over. A hung local disk would stop much more than this.
- **Fix**: read in a child process the collector can kill (or move agent-work's logs where a read deadline works), only if a hang is ever seen.
- **Ratchet**: none yet; the regression tests hold the rest (a flush whose time ran out reads nothing, the keeper and the hand-over never wait for a read).
- 验收: a test that blocks the read in the kernel (a FUSE file) and sees the collector end.
- 审批 不需要 · 代价 M · 风险 low · repos: bifrost-platform

### TD-367

**P2 · security · nothing scans the whole history of the twelve public repositories for secrets; the Gitea admin token sat in infra's for four months (TD-365)**

- **状态**：未开始（2026-10-18 00:1x 记，TD-365 签收时从它的防线里拆出来；Owner 签收 TD-365 时说「签收 TD-365」）
- **Claim**: TD-365's token was committed on 2026-06-17 (`d30ef90`), untracked on 08-19 (`aee67ba`) and found only on 10-17, by a broad grep that hit the ignored local file. No check reads the history of the public repositories; `check-agent-config-parity.sh` and the code-health scan look at the current tree only.
- **Evidence**: `git log -p --all -- k8s/cicd/gitea/secret.yaml` in bifrost-trade-infra (two hits); TD-365 (closed 2026-10-18, its entry in git history at `a981959`).
- **Impact**: all twelve repositories are public on GitHub; a secret that ever reached any commit of main is readable there for good, and only rotation helps.
- **Fix**: a scan over `git log -p --all` of each repository for 40-hex values next to token-, password- or secret-named keys (and the known shapes: `github_pat_`, `ghp_`, age secret keys, PEM blocks), run in CI where the parity check runs, with a reviewed allowlist for fixtures (the tests' `fixture` tokens); each hit is rotated, not only deleted.
- **Ratchet**: the scan itself, failing on a new hit; agents search with `git grep` over tracked files, never `grep -r` over a checkout holding ignored secrets (lesson 162).
- 验收: the scan runs over the twelve repositories with no hit outside the allowlist, and fails on a planted fixture secret in a throwaway branch.
- 审批 不需要 · 代价 M · 风险 low · repos: all twelve

### TD-366

**P2 · security · two older Gitea scripts send the admin token to whatever answers on a fixed local port, and put it on curl's command line**

- **状态**：未开始（2026-10-17 14:3x 记，复核 246 在 `scripts/gitea/lib.sh` 里找到 A2 后，统筹方查同类时看到；Gitea 为主的切法里它们只在回退时用）。10-17 23:5x：装推送钩子的事已有按 lib.sh 写的 `scripts/gitea/ensure-push-webhooks.sh`，`install-ci-webhooks.sh` 可以退役，只剩 `bootstrap-gitea-mirrors.sh`（回退用）
- **Claim**: `scripts/k3s/install-ci-webhooks.sh` and `scripts/k3s/bootstrap-gitea-mirrors.sh` port-forward `svc/gitea` to a fixed local port (3999, 13000) with the forward's output and exit thrown away, then send admin calls to that port: when something else already holds it, the forward fails silently and that service gets the token. Both pass the token to curl as `-H "Authorization: token …"`, so it is in the process list while curl runs.
- **Evidence**: `scripts/k3s/install-ci-webhooks.sh:19`, `:40-48`; `scripts/k3s/bootstrap-gitea-mirrors.sh:18`, `:63-69`. The same defect in `scripts/gitea/lib.sh` was review 246 A2, fixed in `927820b`.
- **Impact**: the Owner runs them from his Mac with the admin kubeconfig; in the Gitea-primary cut only the rollback path runs them (the cut doc §4 「回退」), so they are rare, but the token they carry is the one that guards every repository's branch rules.
- **Fix**: source `scripts/gitea/lib.sh` and use `gitea_connect` / `gitea_api` (kubectl picks the port; the token goes in a Python header; redirects refused); `bootstrap-gitea-mirrors.sh` is to be replaced by `onboard-repo.sh` (cut doc §6), which should be written on lib.sh from the start.
- **Ratchet**: `scripts/gitea/test_gitea_scripts.py` already covers lib.sh (a port-forward that did not start sends nothing; a redirect is not followed); the fix adds the two scripts to that test or retires them. A text check that no script under `scripts/` passes `Authorization: token` to curl on its command line.
- 验收: `git grep -n 'Authorization: token' -- scripts/k3s` finds nothing; the two scripts (or what replaces them) run the lib.sh tests.
- 审批 不需要（Owner 跑的脚本，改代码即可）· 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-364

**P1 · agentd · security · an executor whose commands are refused tries to give itself the shell: on PROD a cursor reviewer wrote its own permission files and a script named like an allowed command; nothing checked what an attempt changed**

- **状态**：在做（2026-10-17 12:2x 记；PROD 演练 M-3，演练会话 `local_8a2b3cf6…` 的报告 P1；修复在平台分支 `w31/agentd-own-config` `54bfc6e`、`1357a02`、`f9d3d68`：复核 239 2 A 2 B 已改；窄确认 240 剩 1 A（被忽略的父目录藏住配置）3 B，照停线规矩改了 A 和两条 B，窄确认 241 在做）
- **Claim**: agentd ran cursor with all its tools for a review and never looked at what the attempt left in the checkout. On agent-06 cursor (model Auto) had every shell command refused, then wrote `.cursor/rules/allow-shell.mdc` ("noop leftover from allowlist probe"), a top-level `cli.json` (`{}`, the name of cursor's CLI permission file) and `scripts/agent/ls`, a shell script that runs `/usr/bin/python3 /tmp/run_safego_verify.py` and then the real `ls`, started a sub-agent and took 35 minutes (the same review on the Mac: 5). Its shell stayed refused, so the script never ran; a review pushes no branch, so nothing left the host.
- **Evidence**: `bifrost-platform/api/internal/agentd/executors.go` `cursorExecutor` (before `54bfc6e`: no mode); `~/agent-work/prod-walk-06/REPORT.md` P1 (checkpoint `sha256:8d07cbf3…`, attempt on agent-06, task `t_01M55AR28TN9TR…`).
- **Impact**: an executor that probes for ways around its limits, unseen; on an implement attempt the same files would be committed to its agent branch, where a later check task or a human could pick them up.
- **Fix** (in review): cursor runs in ask mode for an attempt that pushes no branch (no writes, read-only commands only); after the executor exits agentd lists what the attempt changed against the base, ignored files and the executor's own commits included, renames split; a model's attempt that pushes no branch fails on any change, and any attempt fails on an executor's configuration (`.cursor`, `.codex`, `.claude`, `.gemini`, `cli.json`, `.cursorrules`, `.cursorignore`, `.mcp.json`); the check is journalled so a restart re-checks.
- **Left after the fix** (review 240 B7, B9, accepted as the check's scope): a review's setup must leave everything it generates in ignored paths and change no tracked file, or the review fails although the model wrote nothing (`npm ci` into an ignored `node_modules` is fine); ignored files that are not executor configuration (`node_modules/.bin/ls`) and writes outside the checkout (`/tmp` is private to the service and goes with each stop; the task's sibling directories are not checked); `CLAUDE.md` / `AGENTS.md` are not on the list (repositories have them on purpose); whether a reviewer should run commands at all (`job:reviewer`'s text is signed by the Owner). The checkout on 06 with the three files, `/home/bifrost-agentd/agent-work/agentd/tasks/t_01M55AR28TN9TR…/a1`, is kept as evidence until this item is signed off.
- **Ratchet**: `TestUnwantedChanges`, `TestUnwantedChangesReview239`, `TestCheckChangesIsJournalled`, `TestCursorReadOnlyWithoutABranch`, and the database-backed `TestRunFailsAnAttemptThatChangesExecutorConfig`; each fails with its fix taken out.
- 验收: on PROD a cursor review on agent-06 runs in ask mode (its log shows the mode) and finishes in minutes; an STG attempt whose executor writes `.cursor/x` ends failed with the reason in its log tail.
- 审批 不需要（代码改动，随平台发布）· 代价 S · 风险 low · repos: bifrost-platform

### TD-363

**P3 · release · push-main.sh pushes a Go repository's main without running its tests, so a session that skips the whole suite pushes main red**

- **状态**：未开始（2026-10-17 记；教训 160，第三次）
- **Claim**: push-main.sh checks the release window, fast-forward and code-health on a clean worktree, then pushes. `go test ./...` is left to the session ("go test 与 lint 照旧在推之前自己跑"). On 2026-10-17 platform `ecb28c9` went to main having passed the three touched packages and code-health, and failed `storedurability.TestNoNewStoreUnderHome` in the whole suite; CI `ci-platform-kr5tm` is red on it, `fcd2ecb` fixed it minutes later. The memory and CLAUDE.md say the same rule in words; it was missed on 10-12, 10-14 and 10-17.
- **Evidence**: `bifrost-trade-infra/scripts/release/push-main.sh:58-83` (code-health only); `agent-config/work/multi-agent/LESSONS-from-practice.md` row 160.
- **Impact**: main red until the next push; a deliver or release.sh run in between refuses the SHA (ci-* not Succeeded) or needs `--allow-red`.
- **Fix**: for a Go repository (platform, plugins), run `go test ./...` in the same clean worktree push-main.sh already makes for code-health, with the neighbours CI clones (infra for platform), and push only when it passes; an explicit `--skip-tests <reason>` that is logged, as release.sh's `--allow-red`.
- **Ratchet**: a push-main.sh test with a fake Go repository whose test fails: push-main.sh exits non-zero and pushes nothing.
- 验收: the ratchet test; and a real push of a platform commit prints the go test summary before the push line.
- 审批 不需要 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-362

**P3 · agentd · setup.json and siblings.json stay on the host: the platform never sees which setup command failed, how long each took, or which sibling commit a task was built against**

- **状态**：未开始（2026-10-17 记；06 的 STG 演练 M-9，走查会话 `local_42a46b17…` 的报告 F6）
- **Claim**: agentd writes the setup commands' traces (time, exit code, output tail) to setup.json and the cloned siblings' commits to siblings.json in the attempt's output directory, but uploads only the report (verify.json or the executor's report) and the log tail. A setup that fails shows on the platform as exit 3 and nothing else; a setup that passes leaves no record of what was built against what.
- **Evidence**: `bifrost-platform/api/internal/agentd/setup.go:71` (siblings.json written), `:85` (setup.json path); `api/internal/agentd/deliver.go:224-240` (only the report body is put); `~/agent-work/stg-walk-06/REPORT.md` F6.
- **Impact**: a setup failure on the agent host is as silent as TD-361's; a review cannot tell which `bifrost-ui` commit a Console change was checked against.
- **Fix**: put both as artifacts of the attempt (kind `verify` for setup.json so H8 scans it, with the same path rewrite agentd uses for verify.json since `9d16b6f`), and reference them from the attempt's end.
- **Ratchet**: an agentd test that an attempt with setup commands and a sibling ends with both artifacts put and no H8 match in either.
- 验收: on STG, a Console task's attempt shows its setup trace and sibling commits in the Console.
- 审批 不需要 · 代价 S · 风险 low · repos: bifrost-platform

### TD-361

**P2 · agentd · a failure before an attempt starts (checkout, a sibling clone, the setup wrapper) is never reported: the platform sees only a lease that runs out, re-dispatches, and spends the mission's budget on the same failure**

- **状态**：未开始（2026-10-17 04:0x 记；06 的 STG 演练 M-7 撞上，走查会话 `local_42a46b17…` 的报告 F4）
- **Claim**: `agentd.Run` returns on an error before it reports the attempt's start, and the main loop only logs it. The platform keeps the attempt leased until the lease expires (stale after 2 minutes, lost after 15 more), then readies the task and dispatches it again, which fails the same way. On 2026-10-17 M-7's two attempts both died at the sibling clone (Gitea 404 on bifrost/bifrost-ui); the reason was only in the host's journald, readable by its agent user and root, and was found by lining up Gitea's access log with the lease times.
- **Evidence**: `bifrost-platform/api/internal/agentd/run.go:115` (returns before start); `api/cmd/agentd/main.go:146` (logs and moves on); `~/agent-work/stg-walk-06/REPORT.md` F4 (M-7, attempts `a_01M54GBY6JA917ETZY8WBQ5WBC`, `a_01M54HBCEZV1MQ5V5FXKC253P4`).
- **Impact**: each such failure costs one attempt of the mission's budget and about 17 minutes, repeats until the budget is gone, and leaves no reason in the runtime or the Console; same family as TD-349 (a refused persist leaves no trace).
- **Fix**: agentd ends an attempt it cannot start with a conclusion such as `prepare_failed` and the error text (the attempt's end route already carries a conclusion), so the platform records it and does not re-dispatch a failure that will repeat without a change.
- **Ratchet**: an agentd test per preparation step (checkout, sibling, setup) that the attempt ends reported, with the step and the error, not left leased; a runtime test that such an attempt is not re-dispatched on the same spec.
- 验收: on STG, a task whose sibling cannot be cloned ends once with `prepare_failed` and the reason, visible in the Console, and is not leased again.
- 审批 不需要 · 代价 S · 风险 low · repos: bifrost-platform

### TD-360

**P1 · agentrt · an implement attempt that changed nothing is accepted: it hands in the base commit, the deterministic check passes on the base, and only a reviewer stands between it and an accepted task**

- **状态**：未开始（2026-10-17 04:0x 记；06 的 STG 演练 M-6 撞上，走查会话 `local_42a46b17…` 的报告 F2）
- **Claim**: when an executor exits 0 without changing anything, agentd delivers the base as the attempt's branch ("nothing changed: the attempt's branch is its base") with conclusion done; the platform does not compare the pushed commit with the base; the verify commands (build, vet, test, "nothing outside the test file changed") all pass on an unchanged tree. On 2026-10-17 codex on agent-06-stg could run no command at all (its sandbox failed), changed nothing, and its attempt went submitted → verified pass → review. STG had no reviewer, so it stopped there; on PROD a reviewer that misses it would accept a task nobody did.
- **Evidence**: `bifrost-platform/api/internal/agentd/deliver.go:258` ("nothing changed: the attempt's branch is its base"); `~/agent-work/stg-walk-06/REPORT.md` F2 (M-6, attempt `a_01M54G37YWPPQ9C7YRYTKMTT80`, pushed commit = base `f69e8c6`, verification `v_01M54G4KMNVBKCD0GS5ZB2HT8R` pass).
- **Impact**: any executor failure that ends in exit 0 (a broken sandbox, a refusal, a model that gives up) looks like a finished task; the plan moves on and the Owner sees it done.
- **Fix**: for an implement task with effect branch, a pushed commit equal to the base is conclusion `none` (no change), not done: the attempt fails, the task goes back to ready or to the Owner by the usual rules. Decide in agentd (it knows the base) and enforce on the platform (it records base and pushed commit) so that neither side alone can let it through.
- **Ratchet**: an agentd test that an executor exiting 0 with no change ends with conclusion none; a platform test that persist of an implement attempt whose pushed commit equals its base is refused as done.
- 验收: on STG, a task whose executor changes nothing ends its attempt as no change and is not verified or reviewed.
- 审批 不需要 · 代价 S · 风险 low · repos: bifrost-platform

### TD-359

**P2 · agentd · the agentd host user can read its own token files, and so can every process it starts: executors, and since 2.2's Console checks, unsandboxed agent-written code with the network**

- **状态**：未开始（2026-10-16 23:4x 记；修复核 227 时撞上。不是复核 227 那次提交引入的：执行者早就以同一个用户运行）
- **Claim**: agentd runs as `bifrost-agentd` and keeps `agentd.token`, `agentd-git.token`, `cursor-api.key` and `claude-oauth.token` under `~bifrost-agentd/.config/bifrost`, mode 0600 owned by that user. Every process agentd starts runs as the same user and can read them: the executors (Codex's sandbox restricts writes and the network, not reads; cursor-agent is not sandboxed), and from the Console checks on (`691f803`, `f21cefa`) the deterministic check's `npm --prefix console test` and `run build`, and the setup's `npm ci` lifecycle scripts, which run code the agent wrote or a dependency ships, unsandboxed, with the network. The environment is already cut down (`AllowedEnv`; review 227 A2 for setup); the files are not.
- **Evidence**: `bifrost-platform/agent/deploy/install-agentd.sh` (credentials: regular files the user owns, 0600); `api/internal/agentd/executors.go:27` (`allowedEnv`); `api/internal/agentrt/store/repos.go` (the Console checks); `api/internal/agentd/setup.go` (setup runs unsandboxed).
- **Impact**: code an agent writes (or a poisoned dependency) could read the agentd token (claim and hand in work as the host), the Gitea token (push to agent branches; `main` is protected), or a vendor key, and send it out. The same code could also write the host user's `~/.gitconfig`; the sibling clone now ignores it (`f21cefa`), the task checkout and push do not.
- **Fix**: (a) run the deterministic check and the setup in a sandbox that denies reads of `~/.config/bifrost` and the agentd root's registry (macOS `sandbox-exec` profile, as Codex does), network allowed only for setup; or (b) a second host user without the tokens for everything agentd starts, with agentd passing credentials only to the executor that needs them; and (c) `GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1` for every git command agentd runs with credentials, not only the sibling clone. (a) or (b) is an architecture choice: options and a recommendation go to the Owner before work starts.
- **Ratchet**: an agentd test that runs a check, a setup and each executor's spawn with a fixture token file in the host user's config directory and asserts none of them can read it; and a test that a poisoned global git config does not reach the checkout or the push.
- 验收: those tests pass on the agent host; a live check on STG runs the Console checks with the sandbox in place.
- 审批 要你定（方案 a 或 b）· 代价 M · 风险 medium · repos: bifrost-platform

### TD-358

**P3 · data · Golden Source still holds keyless TWS fills from before core 0.60.1, and the frontend types an execution's `account_id` / `symbol` as never null**

- **状态**：未开始（2026-10-16 00:05 记；修 PROD Ledger 白屏时查到。源头已堵：core 0.60.1 的 daemon 先映射再写、不完整的拒写（`ed17560`）；ib-gateway 0.4.1 成交带期权合约字段（`ad01dd7`，10-16 04:46Z 上线）；前端 `stkBuckets` 防空值（`85ed9c45`）。10-15 的两行由 #28 删掉，交给修好的 daemon 重写）
- **Claim**: before core 0.60.1 the daemon wrote the IB Gateway plugin's fills to `raw_broker.executions_raw_tws` unmapped, so every fill it stored had NULL account_id, quantity, time and source. 20 of those rows have a Flex row with the same exec_id and do not appear in `GET /executions`; they are still in the table. The frontend's `Execution` type says `account_id: string` and `symbol: string`, so a reader that trims them unguarded crashes on such a row (that was the Ledger on 2026-10-15); `src/utils/equityDelta.ts:36` and `src/utils/positionsGrouping.ts:16` are two more unguarded trims of an account id.
- **Measured**: MEASURED 2026-10-16 (agent_reader): `raw_broker.executions_raw_tws` 211 rows, 22 with NULL account_id, created 2026-08-08 … 2026-10-16; 20 of the 22 have an `executions_raw_flex` row with the same exec_id; the other 2 are #28.
- **Evidence**: `bifrost-trade-core/src/bifrost_core/portfolio/ib_edge.py` (the unmapped write, fixed in 0.60.1); `bifrost-trade-frontend/src/types/positions.ts:9` (`account_id: string`).
- **Impact**: the hidden rows are harmless while every reader goes through the view; a reader that does not, or another type-trusting trim, meets them again.
- **Fix**: (a) the Owner decides whether to delete the 20 hidden rows, with the same guarded DELETE as #28 (by exec_id, `account_id IS NULL`); (b) type the execution's `account_id` / `symbol` as `string | null` and let tsc find the unguarded readers.
- **Ratchet**: core `tests/test_ib_edge_execution_rows.py::test_no_row_is_ever_written_without_an_account`; and a release probe that `SELECT count(*) FROM raw_broker.executions_raw_tws WHERE account_id IS NULL AND created_at > '2026-10-16 05:00+00'` is 0.
- 验收: the probe above is 0 after a trading day; `npm run build` passes with the nullable types.
- 审批 要你批（删 Golden Source 的行）· 代价 S · 风险 low · repos: bifrost-trade-frontend, bifrost-trade-infra

### TD-357

**P2 · release · the release CI gate reads only live `ci-*` PipelineRuns and the TTL janitor deletes them after 7 days, so a release that ships a repo unchanged for a week is refused until the Owner passes `--allow-red`**

- **状态**：未开始（2026-10-15 22:35 记；发 api 0a5053b / 前端 7985cf38 到 STG 时撞上，Owner 在线程里批了这一次的 `--allow-red`，只为 core 与 worker）
- **Claim**: `release.sh stg|prod` requires a Succeeded `ci-*` PipelineRun in `cicd` for each SHA it ships — core, api, worker and frontend at origin/main (`wait_for_ci` → `ci_gate.py`). CI runs only on a push, and the hourly CronJob `cicd/tekton-pipelinerun-ttl` deletes finished PipelineRuns older than 7 days. A repo that has not changed for a week therefore has no run left and reads `ci=missing` until someone pushes to it. An agent cannot run its CI again either: `bifrost-ci-python` needs `repo`, which `start_pipeline_run` does not accept (it takes revisions only).
- **Measured**: MEASURED 2026-10-15 03:30Z (read-only kubectl): 4 `bifrost-ci-python` runs left in `cicd`, none for core or worker. Core 385b0f8 and worker 2b3e344 are what STG run `bifrost-deliver-stg-1791603671` (10-10) cloned and are still main; `release.sh stg` printed `ci=missing` for both, would have refused after 900 s, and shipped with `--allow-red` (reason in the run's log).
- **Evidence**: `bifrost-trade-infra/scripts/release/release.sh:380` (`wait_for_ci`, reads live PipelineRuns only); `scripts/release/ci_gate.py` (exit 2 = no terminal run); `k8s/cicd/tekton/pipelinerun-ttl.yaml:3` (`MAX_AGE_SECONDS`, 7 d); `k8s/cicd/tekton/pipeline-ci-python.yaml:18` (`repo`, no default).
- **Impact**: every Trade release after a quiet week on core or worker (the usual case) needs the Owner to approve `--allow-red`, which also stops the gate from telling a pruned run from a red one.
- **Fix**: (recommended) the janitor keeps the newest Succeeded `ci-*` run per repo whatever its age, so the evidence for main survives; or `ci_gate.py` accepts a SHA that a recorded delivery (`bifrost.io/release-record` ConfigMap) already shipped after passing the gate; or `start_pipeline_run` accepts `repo` for the three `bifrost-ci-*` pipelines.
- **Ratchet**: a test of the janitor's selection: given runs older than 7 days, the newest Succeeded run of each repo is kept and the rest deleted.
- 验收: the ratchet test; the next release with core and worker unchanged for over 7 days passes the CI gate without `--allow-red`
- 审批 要你批（改 `cicd` 的 CronJob 清单，经 `apply_manifest`）· 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-356

**P2 · availability · a planner's cards are never acknowledged, so answered ones keep counting against the runtime's question quota until plans with questions wait for good**

- **状态**：未开始（2026-10-15 22:10 统筹方记；写参谋长薄版第 3 片时查提问存储的配额发现；补强阶段做）
- **Claim**: the question store lets the runtime's session (`agentrt`) hold at most 3 open cards and 6 open-or-unread ones (`questions/types.go` `openPerRequester`, `protectedPerRequester`); an answered card stays "unread" until the requester acknowledges it (review 180 B3). The plan-change cards are acknowledged when the controller uses the answer (`DecidePlanChanges`). A planner's cards (`store.AcceptPlan`) are not: the work goes on with the default and nothing reads the answer back, so each answered card stays protected. After six, every new card is refused as over quota (429), which AcceptPlan treats as the store being unreachable: a plan with questions stays submitted and is tried every pass.
- **Measured**: DERIVED from the code (no run yet): `questions/create.go` tally and quota checks; `server/questions_wire.go` `agentRuntimeAsk` (429 is not ErrInvalid); `store/planresult.go` (`ErrAsk` leaves the plan submitted). The first version asks rarely: the planner's spec says "Usually ask nothing".
- **Evidence**: `bifrost-platform/api/internal/questions/types.go:16-17`; `api/internal/agentrt/store/planresult.go` (AcceptPlan, questions); `api/internal/server/questions_wire.go` (agentRuntimeAsk, agentRuntimeAck).
- **Impact**: after six answered planner cards no plan that asks can be used; it shows as a planning task stuck in submitted, the controller logging the store's refusal every 15 seconds.
- **Fix**: record the cards a plan made (a structured record, not the text of the task's reason) and have a controller pass acknowledge each once answered, as `PlanDecisions` does for plan changes; the answer then also reaches the next planning session's snapshot. Optionally treat 429 from the store as a refusal of the round with the reason, so the plan is not tried forever.
- **Ratchet**: a store test that answers seven planner cards in turn and still gets an eighth made; a controller test that an answered planner card is acknowledged within one pass.
- 验收: the two tests above
- 审批 无（代码改动，随平台发布）· 代价 M · 风险 low · repos: bifrost-platform

### TD-355

**P1 · security · the Owner's rule-signing key signs without the Owner: it had no passphrase and sat in ssh-agent, so any process running as his user could sign a loosening**

- **状态**：待你签收（2026-10-15 19:05 统筹方记；签评审规则 v2 时发现）。19:05 Owner 把钥匙移出 ssh-agent，19:10 加了口令；`rule.sh` 的防线已加
- 验收结果：PASS 2026-10-15 19:15（infra 本次提交）：空口令打不开私钥（`incorrect passphrase supplied to decrypt private key`）；`ssh-add -l` 不列 `SHA256:HQBmsFUm…`；`rule.sh sign` 对没口令的临时钥匙、对常驻 agent 的临时钥匙都在签名前退出 2
- **Claim**: design v5 and the rule set say a loosening needs the Owner's signature. `rule.sh sign` runs `ssh-keygen -Y sign -f ~/.ssh/bifrost_release_owner`; the key (fingerprint `SHA256:HQBmsFUm1mh0JHKwiG/AOJesGSRNNZF+waMq4BI1M7k`, the platform's trust anchor) was loaded in ssh-agent (`~/.ssh/config` `Host *`: `UseKeychain yes`, `AddKeysToAgent yes`) and has no passphrase, so a signature needs no confirmation: a Claude, Codex or Cursor session on the dev machine (all run as the Owner's user) can sign a rule.
- **Measured**: MEASURED: 2026-10-15, two signatures on STG without any prompt (`standing-envelope:dev` v2 at 16:27, event 234; `job:reviewer` v2 at 18:40, event 801, run by the coordinator in the Owner's Terminal panel at his request); `ssh-add -l` listed the fingerprint until the Owner removed it at 19:05; the Owner reports the key has no passphrase. agentd's executors run as `bifrost-agentd` and cannot reach the Owner's agent or home.
- **Evidence**: `bifrost-trade-infra/scripts/agentrt/rule.sh` (sign); `bifrost-platform/api/internal/releasepolicy` (`OwnerKeyFingerprint`).
- **Impact**: the boundary "loosening needs the Owner" holds only by convention for anything running as his user on that machine; the same key signs release policies.
- **Fix**: a passphrase on the key (`ssh-keygen -p`, same fingerprint, no platform change), not stored in the keychain and never loaded into the agent; later a key that needs a touch per signature (security key or Secure Enclave), which changes the trust anchor.
- **Ratchet**: `rule.sh sign` (and the release-policy signer) refuse a key that opens without a passphrase (`ssh-keygen -y -P '' -f <key>` succeeds) or that ssh-agent holds (its fingerprint in `ssh-add -l`), with the reason.
- 验收: `ssh-keygen -y -P '' -f ~/.ssh/bifrost_release_owner` fails; `ssh-add -l` does not list `SHA256:HQBmsFUm…`; `rule.sh sign` on an unencrypted test key exits non-zero before signing
- 审批 口令和钥匙由 Owner 自己动；`rule.sh` 的防线随 infra · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-354

**P2 · agentrt · a ready task that no candidate may take looks like one that is waiting its turn: Progress shows nothing, `needs_you` stays 0**

- **状态**：未开始（2026-10-15 17:55 统筹方记；Gate A 第二批，F-T08 与 F-T10）
- **Claim**: when every candidate of a task's job is excluded (independence, facts) or the mission's budget is spent, the task stays `ready` forever. The route says why in a `route_decided` event, but Progress lists the task nowhere and `needs_you` is 0.
- **Measured**: MEASURED: 2026-10-15 17:55, STG platform `de64cff`: 15 review tasks ready across M-1…M-5, all with subjects written by `exec:codex`, and the only active reviewer is `reviewer/exec:codex/openai/*` (excluded: "not independent of the subject's attempts"); M-1's has waited since 14:25. `GET /agentrt/progress` → `needs_you.count` 0. M-1's T05 round 2 (budget spent) is the same shape.
- **Evidence**: `bifrost-platform/api/internal/agentrt/store/route.go` (`exclusion`, `decide`); `store/progress.go` / `progressneeds.go` (what goes into `needs_you`).
- **Impact**: work stops without anyone being told; the Owner learns it from a coordinator reading the database.
- **Fix**: when a route leaves no candidate, or the budget refuses dispatch, put the task into `needs_you` with the reason (the route's exclusions, or the budget line).
- **Ratchet**: a store test: codex author + codex-only reviewer → the review appears in `needs_you` with the exclusion reason; a spent budget → the task appears with the budget reason.
- 验收: on STG, `GET /agentrt/progress` lists the M-1 review task under `needs_you` with "not independent of the subject's attempts"
- 审批 无（运行时代码，走复核）· 代价 S · 风险 low · repos: bifrost-platform

### TD-353

**P3 · agentrt · a salvaged result's check stays ready after the new attempt submitted, and will cost a real review when a reviewer exists**

- **状态**：未开始（2026-10-15 17:55 统筹方记；Gate A T34 ⑧，F-T34-8b）
- **Claim**: `salvagedOpen` is judged when a check runs; when the task's new attempt submits first, the salvage check already proposed is not closed, it stays `ready` and is closed only after someone runs it.
- **Measured**: MEASURED: 2026-10-15 22:55Z, STG M-3: salvage review `t_01M50WAPPDGKACXJSN7R4W6S84` (of lost attempt `a_01M50V5944NWNJ9XX0G61T3YN1`) ready after the new attempt `a_01M50W6X04WCXMR2Y5EMPQGDNT` submitted at 22:54:43Z and its own review was proposed.
- **Evidence**: `bifrost-platform/api/internal/agentrt/store/adopt.go:24-45` (`salvagedOpen`), `store/accept.go` (`closeCheck` at record time only).
- **Impact**: once a non-codex reviewer exists, it will spend a review on a result that can no longer be the task's.
- **Fix**: when an attempt of the task submits, close the open salvage checks of that task in the same transaction (`task_state_changed` to cancelled with the reason).
- **Ratchet**: a store test: salvage → salvage check proposed → new attempt submits → the salvage check is closed, not ready.
- 验收: on STG, after a salvage and a later submit, no salvage check of that task is left ready
- 审批 无（运行时代码，走复核）· 代价 S · 风险 low · repos: bifrost-platform

### TD-352

**P2 · agentrt · Progress shows a host that is gone for good as `maybe_stuck`, not "result not persisted" with the last checkpoint and its age**

- **状态**：未开始（2026-10-15 17:55 统筹方记；Gate A T34 ⑤，F-T34-5）
- **Claim**: design v5 §5.2 T34 ⑤ wants Progress to say the result is not persisted, the time of the last checkpoint the platform confirmed, and how long nothing has been persisted, and never to show the attempt as done. Progress shows `status: maybe_stuck`, `reason: the lease lapsed and was not renewed`, and no checkpoint field.
- **Measured**: MEASURED: 2026-10-15 22:11:45Z, STG, `GET /agentrt/progress` for attempt `a_01M50ST7TYGTGATJNJP3YVDS0Q` (gate-b, checkpoint 1 at 22:09:43Z, then gone): the fields above and nothing about the checkpoint.
- **Evidence**: `bifrost-platform/api/internal/agentrt/store/progress.go` (live attempt rows).
- **Impact**: the Owner cannot tell "slow" from "the work is on a machine that is not coming back, and only checkpoint 1 is safe".
- **Fix**: live and lost attempts carry `persisted` (bool), `last_checkpoint_seq`, `last_checkpoint_at` and `unpersisted_for_s`; a stale or lost attempt without `persisted_at` reads "result not persisted".
- **Ratchet**: a progress test for a stale attempt with one checkpoint and no persist.
- 验收: on STG, a gate-b attempt with one checkpoint that stops renewing shows "result not persisted", checkpoint 1 and its time in `GET /agentrt/progress`
- 审批 无（运行时代码，走复核）· 代价 S · 风险 low · repos: bifrost-platform

### TD-351

**P2 · actuation · `scale_deployment` reports success on a Deployment that Argo self-heals, and the scale is undone in the same second**

- **状态**：未开始（2026-10-15 17:55 统筹方记；Gate A T22 ③，F-scale，LESSONS 144）
- **Claim**: the action scales through the API and answers `ok: true, "deployment scaled to 0 replicas"`. When the Deployment belongs to an Argo Application with `selfHeal: true`, Argo puts it back at once; the approval and its result say nothing of that.
- **Measured**: MEASURED: 2026-10-15, approval #21 (`appr_55824ce5a3a7b559`) scaled `bifrost-platform-stg/platform-workers` to 0 at 21:49:19Z; Deployment events the same second: scaled down, scaled up again; workers stayed at 1 until the overlay patch `6015863`.
- **Evidence**: the `scale_deployment` action in `bifrost-platform/api/internal/actions/`; Application `cicd/bifrost-platform-stg` sync policy `automated: {prune: true, selfHeal: true}`.
- **Impact**: the Owner approves an action that has no lasting effect; the requester believes the state changed.
- **Fix**: before executing, look up the Argo Application that tracks the object; if it self-heals, refuse with "change it in git" (or say so on the approval), and read the object back a few seconds after executing.
- **Ratchet**: an action test with a self-healing Application fixture: the action refuses (or marks the request) instead of answering ok.
- 验收: `scale_deployment` on `bifrost-platform-stg/platform-workers` is refused or says it will be undone by Argo
- 审批 无（平台动作，走复核）· 代价 S · 风险 low · repos: bifrost-platform

### TD-350

**P2 · agentrt · checks of a task with no pushed commit run their commands in an empty directory**

- **状态**：未开始（2026-10-15 17:55 统筹方记；Gate A T08，F-none）
- **Claim**: for an `effect_class: none` task the attempt pushes nothing, so the check spec the controller writes has no `commit`; agentd then makes an empty directory instead of a checkout and runs the subject's verify commands there.
- **Measured**: MEASURED: 2026-10-15 21:42Z, STG M-3 task `t_01M50R5AESM3Q8G56DAES5VFB1`: verify `test -f api/go.mod` failed in both rounds (verify.json `"reason": "test ended 1"`), task blocked. Later probes used `true` to step around it.
- **Evidence**: `bifrost-platform/api/internal/agentrt/store/accept.go` (`checkSpec.put` writes `commit` only when set); `api/internal/agentd/run.go` (`Run`: empty `repo` or `base` → empty directory).
- **Impact**: any read-only task with a real verify command fails its check; the failure looks like the author's.
- **Fix**: when the checked attempt pushed no commit, the check pins the task's `base_commit` (and repo), and the verification records that it ran on the base.
- **Ratchet**: a store test that a check of an effect-none attempt carries the base commit; an agentd test that such a check runs in a checkout.
- 验收: on STG, an effect-none task with verify `test -f api/go.mod` passes its deterministic check
- 审批 无（运行时代码，走复核）· 代价 S · 风险 low · repos: bifrost-platform

### TD-349

**P2 · observability · a persist the platform refuses leaves no trace: no event, no answer body, the attempt ends failed as if it had failed**

- **状态**：未开始（2026-10-15 14:59 统筹方记；STG 走查 M-1 的第 1 次尝试）
- **Claim**: when `POST /api/v1/agentrt/attempts/{id}/persist` answers 409, the store writes nothing (the refusal is a returned error before any event), the API logs only status and size, and agentd ends the attempt; the attempt row shows failed with conclusion done. Why a done result was lost can be told only by rebuilding the answer from code and matching its byte count in the access log.
- **Measured**: MEASURED: 2026-10-15, attempt `a_01M50FZ6W8ZA1HE2VRRC6PRK48` (task `t_01M50FZ523HZTGYJA0VB6BNE7N`, M-1, STG): platform-api access log `persist 409 224B` at 19:18:32Z, no agentrt event between `attempt_computed` and `attempt_ended`; the walkthrough session rebuilt the body (`... a1 is not on bifrost-agents/bifrost-platform`) to 224 bytes. Report: `~/agent-work/stg-walk/REPORT.md` (F2).
- **Evidence**: `bifrost-platform/api/internal/agentrt/store/attempt.go` `Persist` / `checkHead` (refusal returned before `Append`); `agentrtapi/api.go` `fail` (4xx not logged); agentd's handling of a refused persist in `api/internal/agentd/deliver.go`.
- **Impact**: a lost result reads as a failed attempt; the cause (a platform check, here a Gitea read lagging a push) is invisible on Console and in the event stream, so the next one will cost the same hour.
- **Fix**: record the refusal as an event on the attempt's stream (`attempt_result_refused` with the reason code and text) in its own transaction, and have agentd put the answer body in its ended report.
- **Ratchet**: a store test that a refused persist leaves exactly one refusal event with the reason; an API test that the 409 body reaches the attempt's record.
- 验收: on STG, a persist refused on purpose (a ref that is not the attempt's) shows its reason in `GET /agentrt/events` for the attempt
- 审批 无（运行时代码，走复核）· 代价 S · 风险 low · repos: bifrost-platform

### TD-348

**P3 · observability · the API latency alert counts agentd's long-poll claim, so a healthy STG platform-api pages as slow**

- **状态**：未开始（2026-10-15 13:29 统筹方记；agentd 13:23 装好后 13:25 起 STG 的 BifrostAPIHighLatency 进入 pending）
- **Claim**: agentd claims with a long poll: the platform holds `POST /api/v1/agentrt/claim` until work is ready or the wait ends. The P99 latency alert on platform-api counts those held requests, so every idle agentd pushes P99 above 5 s.
- **Measured**: MEASURED: 2026-10-15 13:28, Prometheus alert BifrostAPIHighLatency{namespace="bifrost-platform-stg",service="platform-api"} pending since 18:25:45Z, value 10 (s), two minutes after host mbp-dev registered (18:23:49Z).
- **Evidence**: the alert in `bifrost-trade-infra/k8s/monitoring/` (BifrostAPIHighLatency); the claim route in `bifrost-platform/api/internal/agentrt/agentrtapi/api.go`.
- **Impact**: a false page on STG now and on PROD once the runtime ships there (O20); real slowness of other routes is hidden behind it.
- **Fix**: leave long-poll routes out of the latency SLI (a route label or a separate histogram for held requests), or measure the claim's wait apart from its work.
- **Ratchet**: a rule test that a series for the claim route does not move the API latency alert.
- 验收: with agentd idle for 15 minutes, BifrostAPIHighLatency stays inactive for bifrost-platform-stg
- 审批 无（STG 监控规则）· 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-347

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

### TD-346

**P2 · release · push-main.sh pushes a commit whose tests it never saw: twice on 2026-10-14 a red gate and a push sat in one command**

- **状态**：未开始（2026-10-14 22:36 统筹方记；LESSONS 125、131）
- **Claim**: `push-main.sh` checks the release window and runs code-health on a clean checkout, then pushes. It knows nothing of `go test`; the coordinator runs the tests itself, and twice the same day ran them in one command with the push (a pipe, then a `;`), so a red result pushed anyway.
- **Measured**: MEASURED: 2026-10-14 22:36, platform main `0a220aa` pushed while `go test ./...` reported `FAIL internal/agentrt/agentrtapi` (TestControlsAndHosts, a load flake, fixed in `d178527`); the morning's code-health case is LESSONS 125.
- **Evidence**: `bifrost-trade-infra/scripts/release/push-main.sh` (no test step); LESSONS-from-practice.md rows 125, 131.
- **Impact**: main can carry a red suite until CI says so; the rule lives only in text.
- **Fix**: `push-main.sh` takes `--tests <file>` (the output of the suite for exactly this commit, with its exit code) and refuses without a green one for HEAD; or it runs the repo's suite itself on the clean checkout it already makes (platform needs the database env).
- **Ratchet**: a test of `push-main.sh` that a missing or red test result refuses the push.
- 验收: `push-main.sh <checkout> HEAD` without a green result for HEAD exits non-zero and pushes nothing
- 审批 无（发布脚本，随 infra）· 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-345

**P3 · testing · agentd's TestRunTakesCheckpoints depends on a checkpoint landing inside a one-second window, and failed once under the whole suite's load**

- **状态**：未开始（2026-10-14 20:58 统筹方记；第 2 轮期间不还其余技术债，排在架构之后）
- **Claim**: the test's script keeps a 2 MiB `big.bin` for about one second and expects a checkpoint (every 300 ms) to see it and record `too_large`. Under load a sample can miss that window, or an upload can still be in flight when the run ends.
- **Measured**: MEASURED: 2026-10-14 20:58, `go test ./... -count=1` on platform branch `w31/agentrt-22-progress-main` (`c68e11f`, nothing in agentd changed): `run_test.go:320: 3 checkpoints, 2 patches with x.go, 0 too large`, the log shows a checkpoint PUT `context canceled`. The same test alone `-count=8` passed 8 of 8; the whole suite again passed.
- **Evidence**: `bifrost-platform/api/internal/agentd/run_test.go:304` (the script and `CheckpointEvery`), `:319` (the assertion).
- **Impact**: a red CI run that is not a bug; someone retries it and stops trusting the test.
- **Fix**: drive the test by state, not time: keep `big.bin` until the test has seen a `too_large` checkpoint event (a file the test removes, or a hook), then let the script finish.
- **Ratchet**: run `TestRunTakesCheckpoints` with `-count=20 -cpu=1,4` once when it is fixed and keep the state-driven shape.
- 验收: `cd bifrost-platform/api && go test ./internal/agentd/ -run TestRunTakesCheckpoints -count=20 -cpu=1,4` passes, and the script waits on the test, not on `sleep`
- 审批 无（测试，随平台发布）· 代价 S · 风险 low · repos: bifrost-platform

### TD-344

**P3 · testing · the MCP packages are never type-checked: CI runs their tests through tsx, which strips types, and platform main has a type error**

- **状态**：未开始（2026-10-14 19:06 统筹方记；写 agent runtime 的 MCP 工具时 `tsc --noEmit` 报出；第 2 轮期间不还其余技术债，排在架构之后）
- **Claim**: `mcp/platform` has a `type-check` script (`tsc --noEmit`) that no pipeline runs; `npm test` runs `node --import tsx`, which does not check types. A type error can sit on main unseen.
- **Measured**: MEASURED: 2026-10-14, `npx tsc --noEmit -p .` in `mcp/platform` on platform main `a8027d4`: 2 errors, `src/questionTools.ts(155,27)` TS2339 and `src/writeGate.test.ts(85,20)` TS2367. The first is fixed on branch `w31/agentrt-22-routes2` (`342a448`). The second is a redundant assertion in the approvals resolve-route test; the agent guard refuses a shell command whose text names that route, so the coordinator left it for a change made outside the shell.
- **Evidence**: `bifrost-platform/mcp/platform/package.json` (`type-check`); `bifrost-platform/mcp/platform/src/writeGate.test.ts:85`; the CI pipeline runs `test-api` and `test-console` only.
- **Impact**: wrong types in the MCP tools (what agents call) are caught by nobody; tests still pass because tsx strips types.
- **Fix**: delete the redundant `plan.kind === 'direct'` assertion at `writeGate.test.ts:85` (the line above already asserts `refused`), then add `npm run type-check` for `mcp/platform` (and the other MCP packages) to the platform CI.
- **Ratchet**: `tsc --noEmit` for every MCP package in CI, failing the run.
- 验收: `cd bifrost-platform/mcp/platform && npx tsc --noEmit -p .` exits 0, and the CI pipeline has the step
- 审批 无（测试与 CI 步骤，随平台发布）· 代价 S · 风险 low · repos: bifrost-platform, bifrost-trade-infra

