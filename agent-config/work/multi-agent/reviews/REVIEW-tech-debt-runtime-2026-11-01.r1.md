# REVIEW r1 — DESIGN-tech-debt-runtime-2026-11-01.draft.md

只读复核，基线 infra `de152c7`、platform `bfa513d6`（均为 origin/main）。复现脚本只在 scratchpad，未改任何仓库或集群。

## 发现

**B1 · BLOCKING · §7.2 E2 / T6（推荐的导出路径做不出来，代价写错）**
- 体积：`doc_policy.py:209-211` 对放行的文档超过 256 KiB 就拒（`:384-390` 对放行路径生效），而 `TECH_DEBT.md` 有 704,672 字节。
- 改动量：infra 一次最多 5 个文件、1500 行（`doc_policy.py:158`、`landing-dev.yaml:16`），首次导出就是约 3,955 行的新文件。
- 平台代码里还有一道放行：`landing_checks.go:101` 要求同时命中编进代码的 `InfraLandingAllow`（`landing_infra.go:5-12`），只签 `landing:dev` v6 不够，还要改 platform 代码。
- S6 登记表：`consumers()`（`doc_policy.py:196-205`）不允许一个已登记的读者去读放行路径（`registry_overlap`），所以旧渲染器不能读导出文件。草稿说 `doc-consumers.yaml` 里已经登记了 `render-tech-debt-page.py`，实际不对：`git show origin/main:agent-config/landing/doc-consumers.yaml | grep -i tech_debt` 没有结果。
- 谁来提交：落地要由某个任务的 attempt 领取（`landing/protocol.go:42`），草稿没写导出提交由哪个任务、哪个执行者来做。
- 结论：「一次签名 + 一次推，之后零推」不成立。
- 修法：重新给 T6 估代价。可选 E3（Console/MCP 加只读 Artifact），或单开一条生成文件的通道：按项目拆成每份小于 256 KiB 的文件，由确定性任务产出，把要动的硬底线逐条列出来交 Owner。

**B2 · BLOCKING · §6.1/§6.6/§7.1（导入的状态过不了平台自己的规则）**
- 签收的前提是「最新验收运行 PASS」（§6.6），而验收结果「只由运行写，不手填」（§3:272）。导入时 `acceptance_json='[]'`（§6.4:440），所以现在待你签收的 25 条导入后永远签不了。
- 规则 5 说过期的 27 条第一轮就去重跑，但规格是空的，没东西可跑。
- 几处「对空集成立」的条件没有定义：53 条在做的没有挂 mission，6.1 末行「mission 全部结束」会把它们自动打回 `open`；53 条没有 `repos:`，「全部段已落地」直接成立。
- 修法：规格为空、条件对空集成立，一律算 Unknown，不推进；导入时给这 25 条带一个 `imported` 类的历史验收结果（存原文哈希）；导入的债在验收规格改写之前不参加自动流转。

**S1 · SHOULD-FIX · §2.4（STG/DEV 怎么发号没写）**
- `0011` 会在三个环境都跑（`k8s/agentrt-migrate/{stg,prod}`），`.mcp.json` 里有 `bifrost-platform-stg`，而且每条 prod 规则在 `agentrt-rules/stg/` 下都有一份对应的。
- 如果 STG 也有 `debt-projects` 规则，它会发出和 PROD 一样的 TD-489+；如果没有，地板是 0，会从 TD-1 开始发，复用已经退役的号。
- 修法：学 `rules/intake.go:15-16` 的「规则不在就不受理」，并且这条规则只放在 prod；或者 STG 用别的前缀。

**S2 · SHOULD-FIX · §10/§7.3（切片顺序会自己制造撞号）**
- 5.8-3a 的验收要在 PROD 登一条真实新债，但手写台账要到 3b 才冻结，期间两边都会发 489。
- 导出器写在 5.8-6，可 3b 的往返验收②和 7.3 的临时页都要用它。
- 从冻结（3b）到签收路由上线（5.8-4）之间，Owner 没法签收任何一条。
- 修法：冻结之前不登真债；导出器挪进 3b；签收路由和冻结同一片上。

**S3 · SHOULD-FIX · §6.3、风险 4（尾注当落地证据不可靠）**
- `Work:` 本来就是从标题和正文提取出来的（infra `agent-config/scripts/git-hooks/lineage.sh:10`），只认尾注块并不能把「提到」和「修了」分开。
- core 里 TD-91 的修复 `2277054`（10-07）根本没有 `Work:` 尾注；10-15 以后 core 的提交多数是 `Work: unassigned`；research 的 `7fc3244` 一个提交写了五个 TD。
- `deploy_seen` 只读 platform 这一条发布线（`server/agentrt_sources.go:23,89`），Trade、Research、插件永远没有部署读数。
- 修法：尾注只当建议；非运行时仓库的段 = 声明提交 + 核实在 main 上 + `ci_seen`；明写「部署读不到」；观察窗从声明的部署时刻算起。

**S4 · SHOULD-FIX · §7.1 规则 13 / T7（防线导入）**
- 191 行防线引用了 223 个不同的 TD，其中只有 68 个还没结。另外 124 行建 `guarded_by` 边时找不到对应的债（外键不成立）。
- 草稿引用的「RATCHETS TD-371 那一行」不存在。
- T7 选 B 之后，`RATCHETS.md` 还在手写，等于又一处两边同时写，冻结和导出都没覆盖它。

**S5 · SHOULD-FIX · §5.3/§5.4（依赖规则不完整）**
- 「gate 被覆盖才算能开工」把「应用时要你批」当成了「开工前要你批」。200 行审批里大约一半是「要批」。也没有定义哪张审批单或哪个回答算覆盖了某个 gate。
- 没定义的去向：审批被拒、回答选了「不做」、计划步被 dropped 或改挂、挡路的债以 `duplicate` 关闭；`needs='landed'` 也不是五态里的一个状态。
- 跨种类的环不拒：`blocks(needs=closed)` 加上 `part_of`，会互相等成死锁。

**S6 · SHOULD-FIX · §1.1 第 46 行、规则 4、风险 3（数错了）**
- 有审批行的条目是 200 条，不是 109：其中 109 条能被渲染器的正则读到；87 条写成「）· 代价」，「·」前没有空格（例如第 1467 行 TD-286）；4 条写成「审批：」。
- 「141 条在页上不显示」这个数是对的，但原因是缺空格，不是冒号。照规则 4 写会漏掉 87 条；风险 3 说「141 条没审批行」也错，实际只有 50 条没有。
- 状态里还有 `待 Owner 改配置`、空串、`**2026-10-28…` 三种映射不到四种状态。
- 波次是 13 个（第 0 到 12 波），不是 12 个；状态写法是 18 种，不是 17。

**S7 · SHOULD-FIX · §2.2（表草图对不上 agentrt 自己的写法）**
- `watch_text_id` 没有 0009 的那种复合外键（`(text_id, issue_id) … DEFERRABLE`）。
- `debt_link.target_ref` 是多态文本，连债与债之间都没有外键；`after_part_ids bigint[]` 没有外键；`link_kind` 和 `target_kind` 之间没有 CHECK 约束。
- `UNIQUE(debt_id, repo)` 不允许同一个仓库前后两段（TD-91 推荐的 B 方案是 core 新增 → 插件切换 → core 删旧）；`landed_commit` 只能存一个提交。
- `duplicate_of` 存了两处，会漂。`debt_evidence` 只追加，却带着 `checked_*` 列。
- 缺 grants（照 0009:963-994 逐个写）；数据库层没有写者检查（像 `issue_writer_ok`），签收只有路由层管着。
- `legacy_imported` 能写 0009 排除名单以外的任何表（`event_may_write`），debt 表要加进排除名单，不然导入就有后门。
- `pending_decision`、`ratchet`、`accepted_gap` 没给表结构，但 T7、T8 推荐要新建表。
- database-design 规范管的是 Trade 各仓库（§6 要求写进 core 的 `DATABASE.md`），不该拿来当 agentrt 的依据。

**S8 · SHOULD-FIX · §4.3（私有正文能被直接读到）**
- `0003_grants.sql:13-14` 给了 `agent_reader` 全 schema 的 SELECT；0009:966-969 写明有 `pg_read_all_data` 的角色照样能读正文。
- 所以 `private` 和 Finance 的正文用 `agent_reader` 就能直接读到，`visibility` 只在 API 层生效。需要你明确定一下。

**S9 · SHOULD-FIX · §6.4（「验收永不写」做不到）**
- `test` 类的 `cmd` 是任意 argv。Landlock 只挡写文件；TD-377 还没修，执行者仍能读到令牌文件，可以拿它去调接口。
- 修法：限定可用的运行器和参数形状、断外网、标为依赖 TD-377，或者如实写明剩余风险。

**S10 · SHOULD-FIX · §4.1（双飞轮的防线写得太宽）**
- 平台非测试源码里已经大量出现这些项目键：`"data"` 68 行、`"ui"` 52 行、`"research"` 13 行、`"trade"`/`"finance"` 各 5 行（例如 `probe/trade_routes.go:43`、`landing_repos.go:23`）。照现在的写法，扫描防线第一天就会失败。
- 修法：扫描只覆盖 debt 相关的包，并避开 `data`、`ui` 这类太常见的键。
- §5.2 提到要读 `/health` 的 `core_sha`，那等于让平台学会 Trade core 的版本规则，不要做。

**S11 · SHOULD-FIX · §10/风险 1（迁移怎么上线没写）**
- `0011` 要改 `event` 表的约束，并替换 3 个共享的守卫函数（会加强锁，见 0009:34-35）。所以「不碰现有表、出问题停用路由就行」不成立，而且迁移只能往前、没有回滚。
- PROD 的迁移要你建 Job（`k8s/agentrt-migrate/README.md:25`），TD-411（发版缺迁移时控制器每 15 秒静默失败）还没结；也没安排先在 STG 演练一次导入。
- 备份可以直接核实，不用写〔推断〕：`k8s/data/logical-backup/README.md:70` 已经把 agentrt 列进 PROD 的备份目标，`:81-85` 要求迁移后跑一次备份和恢复演练。把这一步写进切片。

**S12 · SHOULD-FIX · §12（缺一个待定项）**
- 哪些债需要你签收？v3.6 的 `InboxPage` 和 `BoardHome` 里，台账这一项写着「If it fits none of the three classes, it should become automatic」。
- 草稿把你签收当作唯一的关闭路径，所有债都一样，和「Owner 只管三件事」冲突。

**N1 · NOTE**
- `render-tech-debt-page.py` 引用的是第 77 行，正则其实在第 76 行。
- 「6.6 的 preflight」应为 7.2。
- `landing-dev.yaml:9` 在 pages 下只放行 `*.tsx`，`.ts` 的视图模型要走卡。

**N2 · NOTE**
- TD-91 这个例子已经过时：core 0.58.0（`2277054`）已经让 `upsert_account_transactions` 返回写入数和跳过数并抛错，TD-91 现在是观察中。这一点反过来支持 T10 选 B。

**N3 · NOTE**
- 「Owner 已否定 Gitea Issues」找不到出处。
- 5.8-7 用「撞号 1」当基线，但 git 里量不到这个数（草稿自己也承认另一次登记没核实到）。
- infra CI 去核对 PROD 的事件哈希，会让 infra CI 依赖 PROD 在线。
- 抬地板算 tighten 还是 loosen 没写；如果算 tighten，任何人不用签名就能抬。
- reporter 不该能登记债（`api.go:109-110`）。

## 站得住的

- 台账数字基本都能复现：250 条（TD-85 到 TD-488，缺 154 个号）；标题 187 条超过 80 字（最长 267、中位 124）；格式 194/46；状态 104/54/53/25 加 14 种变体；过期观察 27 条、没写日期 24 条；62 条跨仓库，各仓库计数也对；21 条没有验收行；拍板一节 26 个编号中 15 个已不在条目里；77 条在波次里、173 条不在；签收一节 25 行对 25 条；改动它的提交 577 个和 49 个；防线 240 行，强度计数也对。
- 代码引用核对过，都对：issue 标题上限 80（`0009:108`、`issues.go:125`）、加锁建号（`issuesubmit.go:214-221`）、守卫的做法、`intake-gates`、`landing_repos`、硬底线、watch 只从计划规则来、尾注解析、Gitea 只读账号、签收只限 admin、`approvalhome`、B5 只发 platform。
- TD-473 那段写得诚实，没有声称 git 里有它其实没有的证据。
- T1 选 B、T2 选 A、按事件驱动推进、「能开工」算出来不存、Unknown 不推进、T9 选 B、T10 选 B，理由都成立。

VERDICT: FAIL
