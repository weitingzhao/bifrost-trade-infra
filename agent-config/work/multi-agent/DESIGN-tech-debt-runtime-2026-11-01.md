# DESIGN — 技术债进运行时（R5:5.8-1）· 2026-11-01 r4
> 拆分（r5，2026-11-01）：infra 的代码健康棘轮规定 Markdown 不超过 500 行，本设计拆成两份、内容不变：本文件是修订记录和第零至第四节；**第五至第十二节**（依赖、生命周期、导入导出、Console、挑债、切片、风险、待定项）在 `DESIGN-tech-debt-runtime-2026-11-01-part2.md`。

> 状态：**r4，只写文档；独立复核三轮后 PASS**（复核记录在 `reviews/REVIEW-tech-debt-runtime-2026-11-01.r{1,2,3}.md`）。没有改任何代码、表、集群或仓库。r1 复核 FAIL（`reviews/REVIEW-tech-debt-runtime-2026-11-01.r1.md`：2 BLOCKING、12 SHOULD-FIX、3 NOTE）→ r2；r2 复核 PASS（`….r2.md`：0 BLOCKING、6 SHOULD-FIX、1 NOTE）→ 本版 r3。两轮的改动见下面两张「修订记录」。
> 下一步：Owner 过目（5.8-2）定第十二节的待定项 → 才开 5.8-3。
> 依据（全部只读）：infra `origin/main` de152c7；platform `origin/main` bfa513d6（下文 `file:line` 不带仓库名的都指 platform）；core `2277054`；
> PROD 运行时计划 `R5:5.8`（get_plan）；Design v3.6 `design/ops/`；记忆 `project_crew_institution_north_star`、`feedback_discipline_into_code`、
> `feedback_build_vs_adopt`、`project_crew_memory_core_asset`。方向：Owner 2026-11-01 在统筹线程里选了 B（技术债成为运行时一等记录），没选 A、C。
> 标 **〔推断〕** 的没有在代码或环境里核实。台账数字是用脚本读 de152c7 的 `TECH_DEBT.md` 得出的，可复现（1.1 末）。

## 修订记录（r2）

| 发现 | 改了什么 |
|---|---|
| B1 导出路径 E2 做不出来 | 7.2 重算 T6 的代价：E2 撞上 256 KiB 上限（`doc_policy.py:209-211`）、每次 5 个文件 / 1500 行（`:158`）、编进代码的 `InfraLandingAllow`（`landing_checks.go:101`、`landing_infra.go:5-12`）、`registry_overlap`（`doc_policy.py:196-205`），而且导出提交要有任务来领（`landing/protocol.go:42`）。**改推荐 E3**：不再导出到 git；运行时 + Console + MCP + 只读导出端点 + 快照产物；冻结时两份 Markdown 换成指针。E2′（按项目拆、每份小于 256 KiB、确定性任务产出）要动的东西逐条列出，作备选。删掉「doc-consumers 已登记渲染器」那句错话 |
| B2 导入的状态过不了自己的规则 | 6.1 新增三值判定：规格为空、对空集说「全部」，一律算 Unknown，不推进；导入的债 `flow='manual'`，验收规格改写之前不进自动流转；导入时带 `runner='imported'` 的历史验收结果（存原文哈希），现在待你签收的 25 条照样能签（7.1 规则 9）。空集上的每个条件逐条写了定义 |
| S1 STG/DEV 怎么发号 | 2.4：只有 PROD 发 `TD-n`（`approvalhome.IsProd()`，`home.go:14-16`）；STG 发 `TDS-n`，DEV 发 `TDD-n`；规则不在就不受理（同 `rules/intake.go:15-16`） |
| S2 切片顺序会撞号 | 第十节重排：3a 在 PROD 不发号，只在 STG 演练；导出器挪进 3a；3b 在同一个窗口里导入、冻结两份 Markdown、上签收与打回路由和一个最小签收列表 |
| S3 尾注不能当落地证据 | 6.3：尾注只用来**建议**候选提交；非运行时仓库的段 = 声明的提交 + 核实它在 main 上 + `ci_seen` 成功；这些仓库**读不到部署**（`server/agentrt_sources.go:23`、`:88-95` 只读 platform 这一条线），观察窗从声明的部署时刻算 |
| S4 防线怎么导入 | 7.1 规则 13：191 行引用的 223 个编号里只有 68 个还开着，其余作历史编号存进数组、不建外键；`RATCHETS.md` 与 `TECH_DEBT.md` 同时冻结（T7）。删掉不存在的「RATCHETS 里 TD-371 那一行」，改引 `TECH_DEBT.md:33` |
| S5 依赖规则不全 | 5.3–5.5：`gate` 的意思是「动手那一步要你批」，挂在段上，不挡开工；哪张审批单、哪个回答算「覆盖」要显式连；审批被拒、回答选了「不做」、计划步被 dropped 或改挂、挡路的债以 duplicate / withdrawn 关闭，各自的去向写清；`needs` 对到五态；跨种类的环在合并后的等待图上拒 |
| S6 数错了 | 1.1 改正：有审批行的 200 条（渲染器读得到的 109 条；约 87 条写成「）· 代价」缺空格；4 条写成「审批：」），没有的 50 条；波次 13 个；状态写法按切法算 17–18 种，其中三种映射不到四态。规则 4 和风险 3 跟着改 |
| S7 表草图 | 2.2 重写：复合外键（同 0009:280-282）；债↔债与债→别的东西分两张表，外键类型化；段的先后用联结表；同一个仓库可以分多段；落地提交单独一张只追加的表；`duplicate_of` 只存一处；核对结果另表；写者检查 `debt_writer_ok`（同 `0009:395-405`）；逐个授权（同 `0009:963-994`）；把债的表加进 `legacy_imported` 的排除名单（`0009:325-326`）；补上 `debt_decision`、`ratchet`、`accepted_gap`、`debt_counter` 的草图；不再拿 Trade 的数据库规范当 agentrt 的依据 |
| S8 私有正文能被直接读到 | 4.3 明写：`agent_reader` 有 `pg_read_all_data`（`AGENT_FACTS.md:406`；`0009:966-969`），`visibility` 只在 API 层生效。新增待定项 T13 |
| S9 验收会执行任意命令 | 6.4：`test` 类改成**不由运行时执行**的「CI 证据」：含修复的 main 提交 CI 成功（`release_policy_facts.go:50` 的三条流水线），并且测试函数在那个提交里存在（Gitea 读）。在 agent-06 上执行，等 TD-377（执行者还能读令牌，`TECH_DEBT.md:2856`）关了再说；剩余风险写明 |
| S10 双飞轮防线写得太宽 | 4.1：扫描只覆盖债相关的文件；项目键改叫 `shared-ui`、`data-layer`，避开常见词；删掉「读 Trade `/health` 的 `core_sha`」 |
| S11 迁移怎么上线没写 | 2.5 新增：`0011` 改 `event` 表约束、替换三个共享守卫函数，要加强锁，只能往前；STG 由发布流水线先跑，PROD 由你建 Job（`k8s/agentrt-migrate/README.md:25-31`）；TD-411 还在做；先在 STG 演练导入；迁移后跑 `logical-backup` 和 `logical-backup-drill`（`k8s/data/logical-backup/README.md:70`、`:81-85`），这一步写进切片 |
| S12 哪些债要你签收 | 新增待定项 T12 |
| N1 | 正则引用改为 `render-tech-debt-page.py:76`；「6.6 的 preflight」改指 7.3；Console 的 `.ts` 视图模型不在落地放行里（`landing-dev.yaml:9` 只放 `*.tsx`），走卡 |
| N2 | 换掉过时的 TD-91 例子（core 0.58.0 `2277054` 已经改成抛错，TD-91 现在是观察中）；跨仓库的例子改用 TD-172；TD-91 改作「拍板一节已过时」的证据 |
| N3 | 删掉没出处的「Owner 否定 Gitea Issues」，改引 11-01 Owner 选 B；5.8-7 的撞号基线改成可测的量；E3 下不再有「infra CI 读 PROD 哈希」；地板放进只增不减的 `debt_counter`，不放规则；reporter 不能登记（新能力 `debt` 只给 operator、admin） |

## 修订记录（r3）

| 发现 | 改了什么 |
|---|---|
| R1 冻结不只推一次 | 7.3：冻结还要两件事。一是 platform 改代码，让 AI 评估（TD-391）从 `agentrt.debt` 读条目——今天它在 main 上读 `AGENTRT_LEDGER` 指的文件并解析（`server/agentrt_assess.go:134-150`、`:258-263`），换成指针后会悄悄读不到。二是 Owner 推 overlay，去掉 `AGENTRT_LEDGER`（`k8s/overlays/platform-{prod,stg}/platform-agentrt-env.patch.yaml:63-64`，`k8s/**` 硬底线）。先后顺序写明。`render-tech-debt-page.py` 在 3b 退役，不等到 5.8-6；5.8-6 的验收加上运行时读者 |
| R2 E3 的代价写得不诚实 | 7.2：逻辑备份每天 04:30 UTC 跑一次（`k8s/data/logical-backup/cronjob-backup.yaml:20`），最多丢一天；保留 14 份日备份加每周冷备（`backup.sh:18-26`），全在同一台 NAS 上。删掉「每日快照产物」这条缓解（它存在同一个库的 `artifact_blob` 里，`0001_core.sql:43-46`）。逐条列出 git 能给、E3 给不了的。新增 E4（不在 `gitea-primary.txt` 里的私有 Gitea 仓库），代价写明：平台要一份 Gitea 写凭据（今天只有只读账号，TD-432）；推送触发的 github-sync 会不会碰到新仓库，要先核实。T6 改成 E3 对 E4，仍推荐 E3，理由写明 |
| R3 前缀依据的环境信号 | 2.4：前缀按 `AGENTRT_ENV` 选（连接池只认本环境的运行时角色，`server/agentrt_wire.go:61-65`、`:123`），不用 `OPS_VIEWER_ENV`；库里加守卫：只有 `current_user = 'platform_agentrt_prod'` 能写 `TD-`。STG 演练导入时把号映射成 `TDS-n`，往返比对时再映射回来 |
| R4 表草图 | manual 的 CHECK 改成 `checked_by_actor_id IS NOT NULL AND checked_by_actor_id <> created_by_actor_id`；`debt_ref` 加复合外键 `(debt_part_id, debt_id)`；`debt_floor_raised` 只能 owner 或 controller 写 |
| R5 `ci_test` 证明不了测试跑过 | 6.4：只认 lint 卡住的四个 python 仓库（`pipeline-ci-python.yaml:164-166`）加 frontend、platform；其他仓库没有 pytest 时 CI 照样绿（`:217-220`）。CI 跑的是 `pytest -m 'not ib and not db'`（`:218`），所以要核对那个测试在该提交里没有 `ib`/`db` 标记，Go 的测试文件没有 build tag。CI 不出 JUnit，已确认。仍然证明不了的逐条列出；JUnit 输出作为跟进的新债 |
| R6 T12 与 6.2 打架 | 6.2 加「重开」转换（`closed → doing`）和 `debt_reopened` 事件。导入的 PASS 不能用于自动关闭，只对「导入时就在待签收、之后没离开过」的债有效，写死在 store 里。`ci_test`、`promql` 的 PASS 由控制器从 CI / Prometheus 读出来，作者写不进去，所以不另做复核；要独立复核的是**验收规格**（用哪个测试证明修好了），自动关闭只认复核过的规格。T12 按复核意见改：只有接受残余风险的关闭和改规则的债要你签 |
| R7 / NOTE | 6.3 改成「main 上有一个包含它、且 CI 成功的后代提交」；3b 验收改成「号大于地板且不重复」；冻结提交的父提交必须正好是导入读的那个提交，只快进推（`push-main.sh`）；解析器认「无后续：」写法（TD-392、TD-384、TD-378）；T13 写清扫描扫什么，并把选项 C 写实；去掉 T14（调整计划步并进 5.8-2 的设计批准）；TD-473 基线改成 1 次（`fdf36f8` 对 `497c6ba`，父提交都是 `8291857`；前者是统筹本机没推的提交，不在 Gitea 上）；5.8-7 改量「冻结后有没有人手写号」 |

---


**修订记录（r4，统筹按第 3 轮确认改）**：S1 `ci_test` 只认五个仓库，frontend 的 CI 不跑测试、platform 要求 `api-scope=full`（6.4、风险 7、T9）；S2 评估在库里没导入前回退读文件，3a 上 PROD 不会空窗（7.3 第 1 步）；NOTE：STG overlay 由 Agent 推（7.3 第 4 步）、E3 风险补上 Barman（未演练）、T13 扫描放过提交号和已知编号格式；库守卫的正向测试要在测试库里建 `platform_agentrt_prod` 角色（已写进 3a 那一行）。第 3 轮确认后又改 4 处：T13 只放过含 a–f 字母或核实过的提交号；STG 评估按 `TD-n`→`TDS-n` 查；第 4 步改为本环境导入完成之后；3a 验收补上 PROD 未导入仍读文件。

## 零、一页看完

- **做什么**：技术债从一份手写 Markdown 变成运行时的一等记录。PROD 平台发 `TD-n`，不撞号；状态按事件流转；验收结果来自证据或运行；
  只有接受残余风险或改规则的关闭要 Owner 在 PROD 的 Console 上签，其余自动关闭、7 天内可重开（T12）。`TECH_DEBT.md` 和 `RATCHETS.md` 在导入那一刻冻结成指针，
  同时平台的 AI 评估改读运行时、overlay 去掉 `AGENTRT_LEDGER`、旧台账页退役（7.3）。
- **记录模型（T1-B）**：新建 `agentrt.debt*` 一族表，**不**复用 `agentrt.issue`：issue 的标题上限 80 字（`0009_issues.sql:108`），250 条里有 187 条超过。借 issue 的做法，不借它的表。
- **编号（T2）**：保留 `TD-n`，只有 PROD 发号（按 `AGENTRT_ENV`，库里再守一道），加锁取 `max(已有, 地板)+1`，地板 488；STG 发 `TDS-n`，DEV 发 `TDD-n`。
- **项目（T3）**：项目键是不透明的字符串，清单放在签名规则 `debt-projects` 里；平台代码里不出现产品名。
- **依赖**：债↔债一张表；债→计划步 / 问题卡 / 审批单 / 防线 / 业务问题另一张表，都有类型化的外键。「能开工」是算出来的；环在合并后的等待图上拒。
- **自动化**：三值判定，Unknown 和空集都不推进；导入的债先走手动，验收规格改写之后才进自动流转。验收不让运行时执行任意命令：
  测试类只在 CI 真卡住的仓库读 CI 证据，PromQL 走只读查询，其余建卡或手工；要复核的是验收规格。
- **放哪（T6）**：推荐 E3，不再往 git 写副本，读面是 Console、MCP、只读导出端点，持久性靠 PROD 每日逻辑备份（最多丢一天，同一台 NAS）。备选 E4：一个不同步到 GitHub 的私有 Gitea 仓库，要给平台写凭据。
- **切片**：3a 数据层与接口（PROD 不发号，STG 演练导入）→ 3b 导入、冻结、签收在同一个窗口 → 4 状态联动与验收 → 5 Console 页 → 6 收尾 → 7 实测。
- **待你定**：第十二节 13 项，每项都带推荐。

---

## 一、现状（实测）

### 1.1 台账本身（infra de152c7 `agent-config/TECH_DEBT.md`，3955 行，704,672 字节）

| 事实 | 读数 | 说明 |
|---|---|---|
| 条目 | 250 条，`TD-85`…`TD-488`，缺 154 个号 | 缺号是签收后删掉的，不能复用 |
| 两种格式 | 194 条 `Claim/Evidence/Impact/Fix/Ratchet`，46 条 `证据/影响/修法/防线` | 另有约 30 种自由小标题（「交付状态 2026-10-11」「止血（已做）」…） |
| 标题长度 | 187 / 250 超过 80 字，最长 267，中位 124 | 决定 T1 |
| 状态写法 | 未开始 104 · 观察中 54 · 在做 53 · 待你签收 25；其余 14 条是变体，按切法算 17–18 种 | `待 Owner 改配置`、空串、`**2026-10-28…` 三种映射不到四态 |
| 观察中过期 | 27 条「到 MM-DD」早于 11-01（最早是 TD-97，到 10-07）；24 条没写日期 | 台账落后于现实 |
| 审批 / 代价 / 风险 / 仓库行 | 200 条有：其中 109 条渲染器的正则读得到（`render-tech-debt-page.py:83`）；约 87 条写成「）· 代价」，缺空格（如第 1467 行）；4 条写成「审批：」。另有 50 条没有 | 页上有 141 条看不到审批、代价、仓库 |
| 跨仓库 | 62 条的 `repos:` 列了不止一个仓库 | platform 105、infra 88、research 33、frontend 12、market-data 10、core 5… |
| 没有验收行 | 21 条 | — |
| 「需要你拍板」 | 12 组引用 26 个编号，其中 15 个已不在条目里；还在的也有过时的：TD-91 那组问「要不要改成抛错」，core 0.58.0（`2277054`，10-07）已经这样做了 | 拍板一节在变旧 |
| 「还债顺序」 | 13 个波次（第 0–12 波）列了 77 个未还编号；173 条不在任何波次里 | — |
| 「待你签收」 | 25 行，与状态为待你签收的 25 条一一对上；每行都有「验收：PASS…」「防线」「后续」 | 这一节是准的（B2 的依据） |
| 手数的总数 | 第 42 行写「未结 121 项」（10-13）；实际 250 | 手抄的统计会漂 |
| 「上次查看」 | `92c0271`（2026-10-10） | 三周没动 |
| 改动频率 | 10-01 以来 577 个提交，10-25 以来 49 个 | 一个大文件，多个会话并发改 |

`RATCHETS.md`：`## 现有防线` 240 行，其中 191 行引用了 223 个不同的 TD，只有 68 个还开着。强度：warning 94、blocking 55、manual 48、alert 12…

Owner 列的五件事在 git 里都能找到形状：
- 137 条曾经放在 `## 怎么做的` 之后，而渲染器只读 `## 条目`（`render-tech-debt-page.py:179`），三周看不见，de152c7 修了；
- TD-331 观察到 10-23，11-01 只做了「部分核对，不是验收」；
- TD-434 是「已应用，差验收」，验收要冒充平台 SA；
- TD-473 撞号：`fdf36f8`（17:41:45）和 `497c6ba`（17:49:03）的父提交都是 `8291857`，互不为祖先，各登了一条 TD-473（:3815「platform B5 · 外部发布巡检…」、:3646「research-control · dagster-daemon…」），
  统筹在 de152c7 里把自己那批改号成 TD-474 起。`fdf36f8` 只是统筹本机一个没推的提交对象，不在 Gitea 上，别人复现不了；推之前就改了号的撞号，git 里永远看不到。

### 1.2 为什么每次登记都要 Owner 推

- `agent-config/` 下除 `work/` 以外都是硬底线：平台侧 `rules/landing_infra.go:14-16`，infra CI 侧 `scripts/landing/doc_policy.py:150-151`。
- infra 的落地放行有两道，两道都要命中（`landing_checks.go:101`）：一道在签名规则 `landing:dev` v5（infra `agentrt-rules/prod/landing-dev.yaml:12-13`），一道编进平台代码（`InfraLandingAllow`，`landing_infra.go:5-12`）。
  两道都只放 `work/multi-agent/` 下的几类设计文档。

### 1.3 运行时里能借的东西

| 能力 | 在哪 | 本设计怎么用 |
|---|---|---|
| 事件守卫：写状态表必须带同一事务里、类型对、点名这一行的事件；文字表只追加 | `0002_guards.sql:115-241`；`0009_issues.sql:13-26`、`:289-380` | 新表照搬；`0011` 替换同样的三个函数 |
| 写者检查做在库里 | `0009_issues.sql:395-405`（`issue_writer_ok`） | `debt_writer_ok` |
| 建号：`pg_advisory_xact_lock` + `max+1`，包在幂等写里 | `store/issuesubmit.go:214-221`；`store/keyed.go:50` | `TD-n` 同样做，再加地板 |
| 事件只放 id、枚举、哈希，文字另放一张表 | `0009_issues.sql:5-11`、`:148-168` | `debt_text` 同理 |
| 门槛做成签名规则；规则不在就不受理 | `rules/intake.go:9-24`（`rule_in_force`，`:15-16`）；`0001_core.sql:49-63` | `debt-projects` |
| 步骤自己的证据（任务、落地、B5） | `store/stepevidence.go:25`、`:59`、`:73`；B5 只发 platform（`:66-72`） | 判断 platform、infra 段是否落地 |
| 经运行时落地的仓库只有 platform、infra | `rules/landing_repos.go:18-33` | 其他仓库要别的证据（6.3） |
| CI 读数：Tekton 里的三条 ci 流水线 | `delivery/release_policy_facts.go:50`（`bifrost-ci-python`、`-frontend`、`-platform`）；`server/agentrt_sources.go:78-85` | python 各仓库和前端的「main 上 CI 绿」；infra、finance 不在里面 |
| 部署读数只有 platform 一条线 | `server/agentrt_sources.go:23`、`:88-95` | Trade、Research、插件读不到部署（6.3） |
| CI 与部署的 watch 只从计划规则来 | `controller/controller.go:271-282` | 要给债加一个 watch 来源 |
| 尾注 `Work:` 已经被解析；任一仓库的 main 都能读 | `lineage/trailers.go:29`、`:73-87`；`lineage/mainevidence.go:30` | **只用来建议**候选提交（6.3） |
| Gitea 只读账号读原始文件 | `delivery/gitea_reader.go:13-21` | 核对证据行；核对测试函数在某个提交里存在 |
| Owner 签收只限 admin、没有 MCP 工具；人批的东西只在 PROD | `agentrtapi/api.go:127`、`:186`；`store/signoff.go:16-22`；`approvalhome/home.go:14-16`（platform bfa513d6） | 债的签收照抄 |
| 运行时环境 `AGENTRT_ENV`：连接池只认本环境的运行时角色 | `server/agentrt_wire.go:61-65`、`:123` | 发号前缀（2.4） |
| AI 评估（TD-391）读台账文件 | `AGENTRT_LEDGER`（`k8s/overlays/platform-{prod,stg}/platform-agentrt-env.patch.yaml:63-64`）；`server/agentrt_assess.go:134-150`、`:258-263` | 冻结前改成读 `agentrt.debt`（7.3） |
| 预算账 | `0001_core.sql:398-406` | 每条债的花费（第九节） |
| mission 租户 `dev` / `business` | `0001_core.sql:73`；business 没有常备授权（infra `DESIGN-screening-loop-2026-10-22.md:185`） | 还债的 mission 一律 `dev` |
| agentrt 已在 PROD 逻辑备份里：每天 04:30 UTC，14 份日备份加每周冷备，同一台 NAS | infra `k8s/data/logical-backup/README.md:70`、`:81-85`；`cronjob-backup.yaml:20`；`backup.sh:18-26` | E3 的持久性（最多丢一天）；迁移后备份加演练 |

### 1.4 Design v3.6 里已有的位置

- `BoardHome` / `InboxPage`：「技术债台账：25 项待你签收 — Only in the repo ledger. If it fits none of the three classes, it should become automatic.」→ 签收项改由平台算；这句也是 T12 的出处。
- `ProjectPage`：「+ about 44 more open lines in the ledger, not yet tagged to a project」→ 债要按项目打标签。
- `API-REQUIREMENTS-IA-v2.md`：「Accepted risks — risk ledger 逐条 + `review_at`」→ T8。

**复现**：`git -C bifrost-trade-infra show de152c7:agent-config/TECH_DEBT.md`，按 `^### TD-\d+$` 切块，标题用 `render-tech-debt-page.py:56` 的正则；其余计数同理。复现脚本未入库。

---

## 二、记录模型、编号、迁移

### 2.1 T1：存在哪

| 选项 | 做法 | 代价 |
|---|---|---|
| A | `agentrt.issue` 加 `kind='debt'`，再加一张子表 | 要放宽 `issue_id ~ '^BI-'`（`:105`）、标题 ≤80（`:108`）、状态与 `waiting_on`（`:111-113`）、`served_person` 约束（`:134-137`）；`list_issues` 的六个视图都要排除债；改的是一张带活守卫的表 |
| **B（推荐）** | 新表族 `agentrt.debt*`，事件流 `debt:TD-n` | 一次新迁移、几百行 store 代码，样板和 issue 相似 |
| C | Gitea Issues | Owner 11-01 已选 B 而不选 C；跨仓库债、事件、守卫、签收都要另造 |

业务问题可以**变成**债：用 `raised_by_issue` 连起来，两个对象各走各的流程。

### 2.2 表草图（迁移 `0011_debts.sql`；按 agentrt 自己的写法：`text + CHECK` 做枚举、`<表>_id` 做主键、事件守卫，照 0001 和 0009）

```sql
CREATE TABLE agentrt.debt_counter (id int PRIMARY KEY CHECK (id = 1), floor int NOT NULL CHECK (floor >= 0),
  version int NOT NULL DEFAULT 0);                     -- 只增（守卫比较新旧值），由 debt_floor_raised 写；导入时设为 488

CREATE TABLE agentrt.debt (
  debt_id       text PRIMARY KEY CHECK (debt_id ~ '^TD[SD]?-[1-9][0-9]*$'),   -- TD 只在 PROD；TDS 是 STG；TDD 是 DEV（2.4）
  project       text NOT NULL CHECK (project ~ '^[a-z][a-z0-9-]{0,31}$'),
  area          text CHECK (char_length(area) BETWEEN 1 AND 60),             -- 原来的「领域」
  title         text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 400),
  priority      text NOT NULL CHECK (priority IN ('P0','P1','P2','P3')),
  state         text NOT NULL CHECK (state IN ('open','doing','watching','awaiting_signoff','closed')),
  conclusion    text CHECK (conclusion IN ('signed_off','auto_closed','duplicate','withdrawn','boundary','superseded')),
  duplicate_of  text REFERENCES agentrt.debt(debt_id) DEFERRABLE INITIALLY DEFERRED,   -- 只存这一处
  flow          text NOT NULL CHECK (flow IN ('manual','auto')),            -- 导入的是 manual（6.1）
  watch_until   timestamptz,
  watch_text_id bigint,
  cost          text CHECK (cost IN ('S','M','L','XL')),
  risk          text CHECK (risk IN ('low','medium','high')),
  visibility    text NOT NULL DEFAULT 'project' CHECK (visibility IN ('project','summary','private')),  -- 只在 API 层生效（4.3）
  tags          text[] NOT NULL DEFAULT '{}',                               -- wave:<n>、theme:<slug>、look-first
  acceptance_json jsonb NOT NULL DEFAULT '[]',                              -- 6.4 的封闭语法；'[]' 表示还没有规格
  acceptance_reviewed_sha256 text CHECK (acceptance_reviewed_sha256 ~ '^[0-9a-f]{64}$'),  -- 独立复核过的那一版规格（R6）
  acceptance_reviewed_by text REFERENCES agentrt.actor(actor_id),
  filed_at      timestamptz NOT NULL, state_since timestamptz NOT NULL,
  created_by_actor_id text NOT NULL REFERENCES agentrt.actor(actor_id),
  version       int NOT NULL DEFAULT 0 CHECK (version >= 0),
  CHECK ((state = 'closed') = (conclusion IS NOT NULL)),
  CHECK ((state = 'watching') = (watch_until IS NOT NULL)),
  CHECK ((conclusion IS NOT DISTINCT FROM 'duplicate') = (duplicate_of IS NOT NULL)),
  CHECK (duplicate_of IS DISTINCT FROM debt_id),
  CHECK ((acceptance_reviewed_sha256 IS NULL) = (acceptance_reviewed_by IS NULL))
);

CREATE TABLE agentrt.debt_text (                                            -- 只追加；同一种 kind 取最新的一条
  debt_text_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  debt_id       text NOT NULL REFERENCES agentrt.debt(debt_id) DEFERRABLE INITIALLY DEFERRED,
  text_kind     text NOT NULL CHECK (text_kind IN ('claim','measured','impact','fix','ratchet_plan','now','next','watch',
                  'acceptance_text','signoff_summary','ratchet_text','follow_up_text','no_ratchet_reason','no_follow_up_reason',
                  'reject_reason','note','import_raw')),
  heading       text CHECK (char_length(heading) BETWEEN 1 AND 200),       -- 自由小标题原样保留
  body          text NOT NULL CHECK (octet_length(body) BETWEEN 1 AND 262144),
  sha256        text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  created_by_actor_id text NOT NULL REFERENCES agentrt.actor(actor_id), created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (debt_text_id, debt_id)
);
ALTER TABLE agentrt.debt ADD FOREIGN KEY (watch_text_id, debt_id)
  REFERENCES agentrt.debt_text(debt_text_id, debt_id) DEFERRABLE INITIALLY DEFERRED;   -- 同 0009:280-282

CREATE TABLE agentrt.debt_evidence (                                        -- 只追加
  debt_evidence_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  debt_id       text NOT NULL REFERENCES agentrt.debt(debt_id) DEFERRABLE INITIALLY DEFERRED,
  evidence_kind text NOT NULL CHECK (evidence_kind IN ('code_ref','command','run_ref','commit','doc_ref','measurement')),
  repo text, path text, line_from int, line_to int,
  commit_sha    text CHECK (commit_sha ~ '^[0-9a-f]{7,40}$'),
  quote         text CHECK (char_length(quote) <= 400),
  command       text CHECK (char_length(command) <= 4000),               -- 只记录，不执行
  observed_at   timestamptz,
  supersedes_id bigint REFERENCES agentrt.debt_evidence(debt_evidence_id),
  created_by_actor_id text NOT NULL REFERENCES agentrt.actor(actor_id),
  CHECK (evidence_kind <> 'code_ref' OR (repo IS NOT NULL AND path IS NOT NULL))
);
CREATE TABLE agentrt.debt_evidence_check (                                  -- 只追加：平台核对的结果
  debt_evidence_check_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  debt_evidence_id bigint NOT NULL REFERENCES agentrt.debt_evidence(debt_evidence_id),
  result text NOT NULL CHECK (result IN ('matches','moved','missing','unreadable')),
  at_commit text NOT NULL CHECK (at_commit ~ '^[0-9a-f]{40}$'), checked_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE agentrt.debt_edge (                                            -- 债↔债；不删，只结束
  debt_edge_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  edge_kind     text NOT NULL CHECK (edge_kind IN ('blocks','part_of','follows_from','related')),
  from_debt_id  text NOT NULL REFERENCES agentrt.debt(debt_id),            -- blocks：from 挡住 to；part_of：from 是子条
  to_debt_id    text NOT NULL REFERENCES agentrt.debt(debt_id),
  needs         text CHECK (needs IN ('landed','closed')),
  ended_at timestamptz, ended_why text CHECK (ended_why IN ('withdrawn_link','rewired_by_merge','blocker_withdrawn')),
  created_by_actor_id text NOT NULL REFERENCES agentrt.actor(actor_id),
  CHECK (from_debt_id <> to_debt_id), CHECK ((edge_kind = 'blocks') = (needs IS NOT NULL))
);
CREATE UNIQUE INDEX debt_edge_live ON agentrt.debt_edge (edge_kind, from_debt_id, to_debt_id) WHERE ended_at IS NULL;

CREATE TABLE agentrt.debt_ref (                                             -- 债 → 别的东西，外键类型化
  debt_ref_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  debt_id       text NOT NULL REFERENCES agentrt.debt(debt_id),
  ref_kind      text NOT NULL CHECK (ref_kind IN ('paid_by_step','waits_on_owner','guarded_by','raised_by_issue','reclassified_as')),
  plan_node_id  text REFERENCES agentrt.plan_node(plan_node_id),
  issue_id      text REFERENCES agentrt.issue(issue_id),
  ratchet_id    text REFERENCES agentrt.ratchet(ratchet_id),
  accepted_gap_id text REFERENCES agentrt.accepted_gap(accepted_gap_id),
  debt_decision_id bigint REFERENCES agentrt.debt_decision(debt_decision_id),
  approval_no   bigint CHECK (approval_no > 0),                             -- 审批单在平台的审批库里，不在 agentrt（同 plan_node_binding）
  question_id   text CHECK (question_id ~ '^Q[1-9][0-9]*$'),
  covers        text CHECK (covers IN ('start','apply')), debt_part_id bigint,   -- waits_on_owner：卡开工，还是卡某一段的动手
  go_options    text[],                                                     -- 问题卡里哪些选项算「做」
  ended_at timestamptz, outcome text CHECK (outcome IN ('satisfied','rejected','declined','dropped','rebound','superseded')),
  created_by_actor_id text NOT NULL REFERENCES agentrt.actor(actor_id),
  CHECK (num_nonnulls(plan_node_id, issue_id, ratchet_id, accepted_gap_id, debt_decision_id, approval_no, question_id) = 1),
  CHECK (ref_kind <> 'paid_by_step'    OR plan_node_id IS NOT NULL),
  CHECK (ref_kind <> 'guarded_by'      OR ratchet_id IS NOT NULL),
  CHECK (ref_kind <> 'raised_by_issue' OR issue_id IS NOT NULL),
  CHECK (ref_kind <> 'reclassified_as' OR accepted_gap_id IS NOT NULL),
  CHECK (ref_kind <> 'waits_on_owner'  OR (num_nonnulls(debt_decision_id, approval_no, question_id) = 1 AND covers IS NOT NULL)),
  CHECK ((covers = 'apply') = (debt_part_id IS NOT NULL)),
  FOREIGN KEY (debt_part_id, debt_id) REFERENCES agentrt.debt_part(debt_part_id, debt_id)   -- 只能指同一条债的段（R4）
);

CREATE TABLE agentrt.debt_work (debt_work_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  debt_id text NOT NULL REFERENCES agentrt.debt(debt_id), mission_id text NOT NULL REFERENCES agentrt.mission(mission_id),
  started_at timestamptz NOT NULL, ended_at timestamptz, UNIQUE (debt_id, mission_id, started_at));

CREATE TABLE agentrt.debt_part (                                            -- 跨仓库：一段对一个仓库，同一个仓库可以分多段
  debt_part_id  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  debt_id       text NOT NULL REFERENCES agentrt.debt(debt_id),
  repo          text NOT NULL, ordinal int NOT NULL CHECK (ordinal >= 1),
  apply_gate    text NOT NULL DEFAULT 'none' CHECK (apply_gate IN ('none','public_interface','ddl','security','delete',
                  'prod_change','cluster_write','rule_sign','cross_repo_release','other')),
  version int NOT NULL DEFAULT 0, UNIQUE (debt_id, ordinal), UNIQUE (debt_part_id, debt_id));
CREATE TABLE agentrt.debt_part_order (debt_id text NOT NULL, debt_part_id bigint NOT NULL, after_debt_part_id bigint NOT NULL,
  PRIMARY KEY (debt_part_id, after_debt_part_id), CHECK (debt_part_id <> after_debt_part_id),
  FOREIGN KEY (debt_part_id, debt_id) REFERENCES agentrt.debt_part(debt_part_id, debt_id),
  FOREIGN KEY (after_debt_part_id, debt_id) REFERENCES agentrt.debt_part(debt_part_id, debt_id));   -- 只能在同一条债内
CREATE TABLE agentrt.debt_part_landing (                                    -- 只追加：一段可以有多个提交
  debt_part_landing_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  debt_part_id bigint NOT NULL REFERENCES agentrt.debt_part(debt_part_id),
  commit_sha text NOT NULL CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
  via text NOT NULL CHECK (via IN ('runtime_landing','declared')),
  on_main_checked_at timestamptz, ci_status text CHECK (ci_status IN ('succeeded','failed','unread')),
  deployed_env text CHECK (deployed_env IN ('dev','stg','prod')), deployed_at timestamptz,
  deploy_read text CHECK (deploy_read IN ('observed','declared')),
  created_by_actor_id text NOT NULL REFERENCES agentrt.actor(actor_id), created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE agentrt.debt_acceptance_run (                                  -- 只追加
  debt_acceptance_run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  debt_id text NOT NULL REFERENCES agentrt.debt(debt_id),
  runner text NOT NULL CHECK (runner IN ('imported','ci_evidence','promql','owner','manual')),
  spec_sha256 text CHECK (spec_sha256 ~ '^[0-9a-f]{64}$'),                 -- imported 时为 NULL
  source_sha256 text CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),             -- imported：原文「验收结果 / 验收：PASS…」的哈希
  result text NOT NULL CHECK (result IN ('pass','partial','fail','unknown')),
  at_commits jsonb NOT NULL DEFAULT '{}', ran_at timestamptz NOT NULL,
  evidence_artifact_id text REFERENCES agentrt.artifact(artifact_id),
  checked_by_actor_id text REFERENCES agentrt.actor(actor_id),             -- manual 的独立复核者
  created_by_actor_id text NOT NULL REFERENCES agentrt.actor(actor_id),
  CHECK ((runner = 'imported') = (source_sha256 IS NOT NULL AND spec_sha256 IS NULL)),
  CHECK (runner <> 'manual' OR result = 'unknown'
         OR (checked_by_actor_id IS NOT NULL AND checked_by_actor_id <> created_by_actor_id)));   -- R4

CREATE TABLE agentrt.debt_decision (                                        -- 待定事项（原来的「需要你拍板」），还没问或已经问了
  debt_decision_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  title text NOT NULL, body_text text NOT NULL,                             -- 选项、推荐、成员原文
  state text NOT NULL CHECK (state IN ('pending','asked','answered','dropped')),
  question_id text CHECK (question_id ~ '^Q[1-9][0-9]*$'), answer_option text,
  version int NOT NULL DEFAULT 0, CHECK ((state IN ('asked','answered')) = (question_id IS NOT NULL)));

CREATE TABLE agentrt.ratchet (                                              -- T7
  ratchet_id text PRIMARY KEY CHECK (ratchet_id ~ '^R-[1-9][0-9]*$'),
  name text NOT NULL, location text NOT NULL, guards text NOT NULL, strength text NOT NULL, scope_gaps text,
  strength_class text NOT NULL CHECK (strength_class IN ('blocking','warning','alert','manual','other')),
  td_refs text[] NOT NULL DEFAULT '{}',                                     -- 历史编号，不建外键（多数已关）
  state text NOT NULL CHECK (state IN ('active','retired')), version int NOT NULL DEFAULT 0);

CREATE TABLE agentrt.accepted_gap (                                         -- T8：数据边界与接受的风险
  accepted_gap_id text PRIMARY KEY CHECK (accepted_gap_id ~ '^AG-[1-9][0-9]*$'),
  project text NOT NULL, gap_kind text NOT NULL CHECK (gap_kind IN ('data_boundary','accepted_risk')),
  title text NOT NULL, reason text NOT NULL, reopen_when text NOT NULL, review_at date,
  state text NOT NULL CHECK (state IN ('accepted','reopened')), version int NOT NULL DEFAULT 0);
```

（实际 DDL 里建表顺序按外键依赖排，`debt_ref` 引用的表先建。）

**守卫与授权**：
- 状态表（`debt`、`debt_counter`、`debt_edge`、`debt_ref`、`debt_work`、`debt_part`、`debt_part_order`、`debt_decision`、`ratchet`、`accepted_gap`）：每次写都要有同一事务里、类型对、点名这一行的 `debt_*` / `ratchet_*` / `gap_*` 事件。
  只追加表（`debt_text`、`debt_evidence`、`debt_evidence_check`、`debt_part_landing`、`debt_acceptance_run`）用 `forbid_change`，插入要有点名它的事件。
- `event_may_write` 的 `legacy_imported` 排除名单（`0009_issues.sql:325-326`）要加上全部债的表，否则导入有后门。
- 写者检查 `debt_writer_ok(event_type, actor)`，形状同 `issue_writer_ok`：
  - `debt_signed_off`、`debt_signoff_rejected`、`gap_accepted` 只能是 `owner`；
  - `debt_auto_closed`、带 `by_rule` 的 `debt_state_changed`、`runner` 为 `ci_evidence` / `promql` 的 `debt_acceptance_ran` 只能是 `controller`；
  - `debt_floor_raised` 只能是 `owner` 或 `controller`（R4）；`debt_reopened` 是 `owner`，或 `thread:%` / `seat:%` 重开 7 天内的 `auto_closed`（store 查时限）；
  - `debt_acceptance_reviewed` 的写者不能是这版规格的作者（事件体带作者，store 比较）；
  - 其余只能是 `thread:%`、`seat:%`、`owner`、`controller`；
  - `agent:%`（intake）和 `host:%` 一律拒。
- 前缀守卫（R3）：`debt` 的插入触发器里，`NEW.debt_id LIKE 'TD-%'` 而 `current_user <> 'platform_agentrt_prod'` 就拒。角色名是常量，迁移文件在三个环境仍然字节相同。
- 授权逐个写（同 `0009_issues.sql:963-994`）：只追加表给 SELECT、INSERT；状态表给 SELECT、INSERT、UPDATE；序列给 USAGE；函数给 EXECUTE；不给 DELETE。`agent_reader` 不单独授权（但见 4.3）。

### 2.3 事件词表（加进 `event_type_closed`）

`debt_filed`（`source: file|import`）· `debt_edited` · `debt_text_added` · `debt_evidence_added` · `debt_evidence_checked` · `debt_state_changed`（from、to、why、`by_rule`）·
`debt_flow_set` · `debt_edge_added` · `debt_edge_ended` · `debt_ref_added` · `debt_ref_ended` · `debt_work_linked` · `debt_work_ended` · `debt_part_set` · `debt_part_landed` ·
`debt_acceptance_set` · `debt_acceptance_reviewed` · `debt_acceptance_ran` · `debt_signed_off` · `debt_auto_closed`（T12）· `debt_reopened` · `debt_signoff_rejected` · `debt_merged` · `debt_floor_raised` ·
`debt_decision_set` · `ratchet_registered` · `ratchet_changed` · `gap_accepted` · `gap_reopened`。流：`debt:<id>`、`ratchet:<id>`、`gap:<id>`、`debt-decisions`。

### 2.4 T2：编号

- 保留 `TD-n`，原号原样导入，缺的号保持缺着。
- **只有 PROD 发 `TD-n`**：前缀按 `AGENTRT_ENV` 选——这是「连的是哪个运行时库」的信号，连接池建立时会核对它和本环境的运行时角色一致，否则拒绝（`server/agentrt_wire.go:61-65`、`:123`）；
  不用 `OPS_VIEWER_ENV`（`IsProd()` 管的是人批的东西）。库里再守一道：只有 `current_user = 'platform_agentrt_prod'` 能写 `TD-`（2.2）。
  STG 发 `TDS-n`，DEV 发 `TDD-n`，测试和演练永远碰不到真号。迁移文件在三个环境里字节相同，CHECK 同时接受三种前缀。
  STG 演练导入时，导入器把 `TD-n` 映射成 `TDS-n`（号不变），往返比对时再映射回去。
- 每个环境都要「规则在、读得到」才受理登记（同 `rules/intake.go:15-16`）：PROD 的 `debt-projects` 在 3b 签；STG 另有一份（放在 `agentrt-rules/stg/` 下），只管 `TDS`。
- 建号：在幂等写里先拿 `pg_advisory_xact_lock(<号锁>)`，再取 `max(同前缀已有的号, debt_counter.floor) + 1`。同一个幂等键重发，拿回同一个号（`store/keyed.go:50`）。
- 地板放在 `debt_counter`，只增不减，由导入事件或 Owner / 控制器的 `debt_floor_raised` 写；不放进规则，免得出现「抬地板算 tighten 还是 loosen」的歧义。
  导入时取三处的最大值：de152c7 以来 infra 所有分支里出现过的 `### TD-n`；各仓库 main 尾注里的 `Work: TD-n`；统筹待登记笔记里预占的号。de152c7 时是 488。
- 测试：两个会话同一秒各登一条，拿到两个不同的号；同一个幂等键拿到同一个号；低于地板的号永远不发；STG 永远发不出 `TD-`。

### 2.5 迁移怎么上线（S11）

- `0011` 只能往前：它替换 `event_type_closed`（`ALTER` 在检查已有行时会对 `event` 加强锁，`0009_issues.sql:34-35`），还替换 `only_liveness`、`event_may_write`、`event_names_row`
  三个共享的守卫函数（签名不变，旧分支逐字保留，同 0009 的做法）。没有回滚，出问题只能再写一个前向迁移来修。老版本平台遇到它要能照常启动（词表只增不减），照 0009 的办法用上一个提交的代码核对一遍。
- 顺序：STG 由 `bifrost-deliver-platform` 先跑迁移（`k8s/agentrt-migrate/README.md` 「Since TD-411」一节）；PROD 由你在 DDL 批准后建 Job（同一文件 `:25-31`），
  PROD 发布流水线会检查 `agentrt_schema_applied`。TD-411（发版缺迁移时，控制器每 15 秒静默失败一次）还在做，所以按 README 的顺序手工核对，不依赖它已经修好。
- PROD 迁移之后：用 `create_job_from_cronjob` 跑 `data/logical-backup`，成功后再跑 `logical-backup-drill`。要看到新的 `bifrost_platform.agentrt` 转储，演练报告里的行数一致（`logical-backup/README.md:81-85`）。
- 导入先在 STG 用真实文件完整演练一遍（往返比对、报告），PROD 才导。

---

## 三、字段

| 现在台账里 | 运行时 | 谁写、怎么变 |
|---|---|---|
| `### TD-n` | `debt_id` | 平台发，不改 |
| `**P · 领域 · 标题**` | `priority`、`area`、`title` | crew 写；改优先级是一个 `debt_edited` 事件，「自上次以来」看得见 |
| 状态（含「到 MM-DD，看什么」） | `state`、`watch_until`、`watch_text_id` | 第六节 |
| 证据 / Evidence / Measured | `debt_evidence` + `debt_text(measured)` | 追加；平台核对的结果写进 `debt_evidence_check` |
| 影响、修法、Claim、现在、下一步 | `debt_text` 的各种 kind | 追加，取最新的一条 |
| 防线 / Ratchet | 计划中的写 `ratchet_plan`；已建的是 `debt_ref(guarded_by → ratchet)` | 签收时查（6.6） |
| 验收 | `acceptance_json`（封闭语法）+ `acceptance_text`（原文） | 6.4 |
| 验收结果 | `debt_acceptance_run` | 导入的记 `imported`；以后只由运行或经过复核的手工记录写 |
| 审批（要你批 / 不用批 / 自由文字） | 段上的 `apply_gate`，或一条 `waits_on_owner(covers=start)`；原文进 `import_raw` | 5.3 |
| 代价、风险 | `cost`、`risk` | — |
| repos: | `debt_part`（一段对一个仓库，同一个仓库可以分多段） | 先后记在 `debt_part_order` |
| 自由小标题 | `debt_text(note, heading=原标题)` | 原样保留 |
| 待你签收那一行 | `signoff_summary`、`ratchet_text`、`follow_up_text` | 导入时从那一行里拆出来 |
| 历史 | 事件流 `debt:<id>` | 只追加，哈希链 |

`apply_gate` 的词表是通用的（公开接口、DDL、安全、删除、PROD 变更、集群写、签规则、跨仓库发版、其他），不出现业务词。

---

## 四、各项目与小牛牛自己的平台

### 4.1 项目键与登记规则（T3）

```yaml
# 草图：infra agent-config/agentrt-rules/prod/debt-projects.yaml → 签名规则 debt-projects v1（PROD）
rule_id: debt-projects
projects:
  - {key: crew,        name: "Crew & Ops Platform", group: crew,
     owns: ["bifrost-platform/**", "bifrost-trade-infra/agent-config/**", "bifrost-trade-infra/k8s/cicd/**",
            "bifrost-trade-infra/k8s/platform-*/**", "bifrost-trade-infra/k8s/overlays/platform-*/**", "bifrost-trade-infra/scripts/landing/**"]}
  - {key: trade,       name: "Trade",   group: product, owns: ["bifrost-trade-core/**", "bifrost-trade-api/**", "bifrost-trade-worker/**",
            "bifrost-trade-frontend/**", "bifrost-trade-infra/k8s/overlays/{dev,stg,prod}/**", "bifrost-trade-infra/k8s/base/**"]}
  - {key: research,    name: "Research", group: product, owns: ["bifrost-research/**"]}
  - {key: market-data, name: "Market data plugin", group: plugin, owns: ["bifrost-platform-plugin-market-data/**"]}
  - {key: flex-query,  name: "IB Flex plugin",     group: plugin, owns: ["bifrost-platform-plugin-flex-query/**"]}
  - {key: ib-gateway,  name: "IB Gateway plugin",  group: plugin, owns: ["bifrost-platform-plugin/**"]}
  - {key: shared-ui,   name: "Shared UI",  group: shared, owns: ["bifrost-ui/**"]}
  - {key: data-layer,  name: "Data layer", group: shared, owns: ["bifrost-trade-infra/k8s/data/**"]}
  - {key: finance,     name: "Finance",    group: product, owns: ["bifrost-finance/**"], text_scan: strict}   # T13
acceptance_runners: {}   # 6.4：每个仓库允许的 CI 测试路径前缀
budgets: {}              # 第九节以后才填
```

- 平台只比较键、不解释键（同 issue 的 `product`，`0009_issues.sql:106`）。显示名、分组、默认归属都从规则里读；加一个产品，就是签一版新规则。
  `owns` 只用来建议项目：infra 一个仓库里既有 Trade 的清单，也有 crew 的治理层，光看仓库推不出归属，所以 `project` 是显式字段。上面的路径划分是本稿的提议〔推断：`k8s/base/**`、`k8s/data/**` 的归属要你看一眼〕。
- **双飞轮防线**：平台的非测试源码里本来就有 `"data"`、`"ui"`、`"research"`、`"trade"` 这些字面量（如 `probe/trade_routes.go:43`、`landing_repos.go:23`），不能全仓扫。
  防线只扫债相关的文件（`store/debt*.go`、`agentrtapi/debts*.go`、`console/src/pages/shell/agents/debt*`）；项目键避开常见词，所以叫 `shared-ui`、`data-layer`。
  写法同 RATCHETS 里 TD-268 那一行（`TestRemovedPrimarySQLHelperStaysGone`）。
- **D13**：一条债只有一个归属项目，但段可以跨域（TD-172：market-data 插件写 raw → Research 写 features）。越界的修法在设计复核里拦，数据层不懂业务。
  平台**不**去读 Trade core 的版本或 `/health` 字段，core 的版本规则是 Trade 自己的事；core 和下游的先后，只用段的顺序和「这一段已落地」来表达。
- **租户**：债不带租户；还债的 mission 一律 `tenant='dev'`。
- **按项目看**：`list_debts?project=`；各项目的 P0–P3 分开看；预算只在规则里留了位置。

### 4.2 谁能做什么

| 动作 | 谁 | 备注 |
|---|---|---|
| 登记、补证据、改字段、连依赖、挂 mission、写验收规格 | 新能力 `debt`：operator（统筹线程、席位）、admin | reporter 只登记外部工作（`agentrtapi/api.go:109-110`），不给；intake 令牌也不给（库里的 `debt_writer_ok` 也拒 `agent:`） |
| 自动推进 | `controller` | 只有证据能推，一次推进写一个事件 |
| 撤回、并重复、改归入接受的缺口 | crew，要带理由 | 进「自上次以来」；`gap_accepted` 只能由 Owner 写（T8） |
| 签收、打回 | Owner，只在 PROD | 照 `store/signoff.go:16-22`、`approvalhome/home.go:14-16`；没有 MCP 工具。哪些债要他签见 T12 |
| 重开 | Owner 任何时候；crew 只能重开 7 天内的 `auto_closed`，带理由 | `debt_reopened`（6.2） |
| 复核验收规格 | 规格作者以外的 crew 写者（另一个工具或席位） | `debt_acceptance_reviewed`；自动关闭只认复核过的那一版 |

### 4.3 公开与私有（按 S8 改写）

- **E3 下不再有公开副本**（7.2）。冻结时两份 Markdown 换成指针，当前的树里不再列出还开着的安全洞（TD-434 那一类）；git 历史里已有的内容留着，删不掉。
- 读正文走 `/debts/{id}`，`visibility` 在 **API 层**过滤；事件体里不放正文（同 `0009_issues.sql:9-11`）。
- **但库这一层挡不住**：`agent_reader` 是 `pg_read_all_data` 加 CONNECT（`AGENT_FACTS.md:406`），0009 自己也写明了有这个角色照样能读正文（`0009_issues.sql:966-969`）。
  Agent 平常查库就用它，所以 `private` 和 Finance 债的正文，任何拿着 `agent_reader` 的会话都能读到。要不要接受，见 T13。

---

（第五至第十二节见 `DESIGN-tech-debt-runtime-2026-11-01-part2.md`。）
