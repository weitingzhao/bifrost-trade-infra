# 实施设计：R5:5.5-12 所有执行者的活都登记进运行时（神经系统 S1）

状态：**只写设计，不实施**（第 7 稿：范围按统筹裁定收窄；Codex 七轮复核，第 7 轮 PASS，其唯一应该改项已收口；最终处置见附录，各轮细节留在复核文件里，不进本稿）。§「要 Owner 定」的 O1–O7 已由 Owner 在统筹线程 2026-11-03 18:45 CST 定：全部按推荐（O1 选 B，O2–O7 选 A）。不建表、不发令牌、不改钩子、不登记任何东西。
上游：`agent-config/work/multi-agent/DESIGN-nervous-system-and-brain-2026-11-02.md`（第 4 稿；§13 的 12 项 Owner 2026-11-02 全部按推荐，含 N11 A、N14 A、N15 (i)、N16 A）。上游只定方向；身份规则、权限白名单、接口字段仍请 Owner 签（上游 `:8`）。
范围：上游 §11.1 的 S1 一行——钩子自动登记、无计划上下文记 Unlinked、Unlinked 薄读面（§5.3）、装 PreCompact 与 SessionStart（N16）、SS0-P（不含会话表 DDL）与 SS0-S（校准，上游 `:713-714`）。出门条、读回注入、收录回执、本机动作流是 S2、S3、S10、S5。**本稿裁掉的**（§11）：收集员的标题读写、Codex 会话逐个绑定、世代与来源尾注、squash 的来源保留、非受管会话的分母。
核对基线：platform main `277363a4`，infra main `fa7e2e2`。`api/…`、`console/…`、`mcp/…` 指 platform；`agent-config/…`、`scripts/…`、`k8s/…` 指 infra。带 `文件:行` 的说法都对这两个提交核过；写「未核实」的没有。

## 0. 会改变做法的核实结果

| # | 事实 | 证据 |
|---|---|---|
| 1 | 今天的钩子只发线程心跳到 statefile，不写运行时，不带会话头 | `agent-config/scripts/thread-heartbeat.js:73`、`:918`；`api/internal/agentthreads/store.go:15`；`api/internal/server/agent_threads_wire.go:33` |
| 2 | 写运行时的是两个手动脚本（派活令牌 + 会话头）和 MCP；MCP 的会话头取 `CLAUDE_CODE_HOST_SESSION_ID`，没有就取 Cursor 会话号，再没有就退回**主机名**——不读 `CLAUDE_CODE_SESSION_ID` | `scripts/agent-host/dispatch-codex.py:63`、`:177-179`；`mcp/platform/src/index.ts:585`；`mcp/platform/src/sessionId.ts:14-20` |
| 3 | 心跳 `work` 只收「大写前缀-短编号」；标题里的字样不算绑定 | `api/internal/agentthreads/threads.go:287`；`thread-heartbeat.js:207-212`；`CUT-session-stream-2026-10-26.md:79` |
| 4 | Coverage 的「未登记」只数运行时里的 `thread:*` 主体，钩子会话不在分母 | `api/internal/agentrt/store/planviewsnapshot.go:156-157`；`agent-config/TECH_DEBT.md:3463` |
| 5 | 登记必带 root/节点，legacy dev 树允许、业务树拒；事件只限登记者；`linked` 可改绑；终态后只收 `linked`；说明七个业务字段加 `v`、`kind` 封闭；同 run key 换内容 409；工作号由主体和 run key 定 | `api/internal/agentrt/store/externalwork.go:182-184`、`:204`、`:247-249`、`:261`、`:302-305`、`:340`、`:389`、`:144-160`、`:273`、`:281` |
| 6 | 主体种类 CHECK 封闭；未知前缀被拒 | `api/internal/agentrt/migrations/0009_issues.sql:39-41`；`api/internal/agentrt/store/propose.go:112-121`、`:143-147` |
| 7 | 角色六种加 intake；reporter 名字自由；`limitedReporter` 只看角色和 `seat:` | `api/internal/actuation/auth.go:42-48`、`:70`、`:77-83`、`:377-390`；`api/internal/agentrt/agentrtapi/reporter.go:13-15` |
| 8 | `limitedReporter` 不是白名单：controls、tighten 可达；问题路由在自己的组里单独挂；标题、进度、skill-runs、Alertmanager 在 reporter 组；当前 reporter 可达的 POST/PUT 15 条 | `api/internal/agentrt/agentrtapi/api.go:123`、`:189`、`:201`；`api/internal/server/server.go:408`、`:490-497`、`:518-524`；`api/internal/questions/handler.go:27-32`；`api/internal/server/route_reach_check_test.go:68-90`、`:143-150` |
| 9 | TD-370 认令牌名不认值；普通令牌能用会话头造任意线程名，头的正则不含 `@` | `api/internal/agentrt/agentrtapi/propose.go:28-30`、`:42`；`store/propose.go:32`、`:66-88` |
| 10 | 令牌配置在 overlay、Deployment 补丁、Secret；apply 脚本只写三个角色；`LoadAuth` 启动时读一次；STG overlay 文件 Agent 可推，Secret 不可 | `k8s/overlays/platform-prod/config/platform-auth.yaml:34-38`；`platform-api-role-tokens.patch.yaml:38-48`；`scripts/k3s/apply-platform-role-tokens.sh:91-99`；`server.go:121-122`；`agent-config/CLAUDE.md:222-227` |
| 11 | 钩子现状：Claude 六事件、Cursor 九键（含 `sessionEnd`）、Codex 用户级四事件要 trust；没有 SessionStart/PreCompact；`worktree-lease.py` 未接线 | `agent-config/claude/settings.json:3-71`；`cursor/hooks.json:4-47`；`codex/README.md:10`、`:39-45`；`claude/hooks/worktree-lease.py:18` |
| 12 | 心跳事件枚举封闭；非 waiting 的 reason 被清空 | `threads.go:332-334`、`:340-341` |
| 13 | 线程号不是会话号：先取 `BIFROST_HEARTBEAT_THREAD`（`run` 包装器导给子进程），再取厂商 `session_id`；key 恢复会铸 `<会话>:n`；`session` 发送前被删；map 键 `vendor/thread` | `thread-heartbeat.js:244-247`、`:270-273`、`:735-742`、`:761`、`:1234`、`:1280`；`threads.go:281` |
| 14 | gate 是 JSON 文件，不是目录 | `thread-heartbeat.js:366`、`:390-394` |
| 15 | 主机名三个来源：两个脚本取 OS 短名，handin 取 `HANDIN_HOST` | `thread-heartbeat.js:144`；`host-heartbeat.js:72`；`handin.sh:51` |
| 16 | 线程列表从全局标题库按 UUID 补 `title`，不看主机；心跳本身也带 `title`，客户端自动填、服务端只规范化后存；键是 `vendor/thread`：同 vendor 同线程号在别的主机不能无 key 再建，别的 vendor 可以，行逐出后可重占；标题永不删除；标题写入只校验 UUID 和长度 | `api/internal/agentthreads/handler.go:120-127`；`view.go:73`、`:87`；`thread-heartbeat.js:249-255`；`threads.go:281`、`:301`、`:476-478`；`recorder.go:160-166`；`api/internal/threadtitles/threadtitles.go:165-177`、`:181-183` |
| 17 | 标题钩子只读 reporter 令牌，用独立的 `PLATFORM_LINEAGE_URL`；没有令牌客户端不发；两个 URL 各有默认值 | `agent-config/claude/hooks/report-thread-title.js:53-56`、`:120-125`；`thread-heartbeat.js:140-142`、`:912-914` |
| 18 | handin 的件在 Live work 里；`squash` 用 `commit-tree` 重写说明，只保留来源提交的短号列表，`Claude-Session` 尾注丢失；尾注只有侧栏号（无 Desktop 时是 CLI 号），没有世代 | `handin.sh:212-218`、`:327-345`；`planviewsnapshot.go:138`；`agent-config/scripts/git-hooks/lineage.sh:4-7`、`:39-45` |
| 19 | 尾注解析器未导出、每键取第一个值；`GET /plan/{id}` 不返回验收项，验收项在采用文档 `items[].acceptance` | `api/internal/lineage/trailers.go:36-60`；`api/internal/agentrt/agentrtapi/plan.go:59-70`；`api/internal/agentrt/planview/document.go:59` |
| 20 | plan-view 读端封闭（含 `coverage`、`external`）；线程读端宽松；线程视图不输出 sidebar/key/turn/seq；`GET /agent/threads` 返回全部主机；plan-view 与 events 原样返回外部工作 note | `console/src/api/planSnapshotSchema.ts:12-14`、`:54-61`、`:87`；`console/src/api/agentThreads.ts:7-25`；`view.go:65`；`handler.go:114-139`；`planviewsnapshot.go:219-241`；`agentrtapi/reads.go:108-116` |
| 21 | 产物按内容寻址，只记第一个上传者（`ON CONFLICT DO NOTHING`）；通用产物读不查归属；登记与工作读取的回复只有五个字段，没有登记时间 | `0001_core.sql:39`；`store/write.go:88`、`:101`；`reads.go:16-46`；`externalwork.go:70`、`:225-227` |
| 22 | 六种线程状态；保留 72 小时默认可配；容量先逐出已结束行 | `threads.go:85-100`、`:469-476`；`config.go:43`、`:48` |
| 23 | 注册脚本锁忙立即失败；派活包装器 `state.json` 没有登记时间；包装器把除派活令牌外的整个环境传给子进程；心跳脚本的 `token()` 同时供 `publishProgress` 用 | `register-claude-work.py:154-158`；`dispatch-codex.py:158-159`、`:231-242`；`thread-heartbeat.js:131`、`:881`；`agent-config/scripts/progress-publish.js:18`、`:47` |
| 24 | Claude 2.1.302 的 `--no-session-persistence`、`--forward-subagent-text` 有实测记录；子线程运行中发现是待验证协议 | `CUT-session-stream-2026-10-26.md:55`、`:108-112` |

## 1. 收集员主体

### 1.1 写法

| | (i)-A `collector:<host>` 种类 | (i)-B `thread:collector@<host>` |
|---|---|---|
| DDL | 迁移 0012 重建 `actor_actor_kind_check`；Owner 签 | 无 |
| Go | `kindOf`、`CheckWriter`、`ensureWriter` 认新种类；非 thread 种类要先登记（`store/propose.go:162-163`） | `writer()` 加一个分支（§1.2） |
| 命名空间 | 天然独立 | `@` 在会话头正则之外（§0 第 9 条），任何令牌造不出 |
| TD-370 | 不适用 | 首写绑定给收集员令牌（`store/propose.go:186-230`） |
| 副作用 | 无 | 占 `ThreadsPerDay` 一个名额（`:136`）；旧 Coverage 查询排除 `thread:collector@` |
| 粗估 | 2–2.5 人日 + DDL | 1–1.5 人日 |

**推荐 B。** 性质全有，省一次 PROD DDL；S11 迁库时再升 A。

### 1.2 推导与令牌

- 推导（`agentrtapi/propose.go:28-44` 加分支，放在席位分支前）：角色 reporter 且名匹配 `^collector:[a-z0-9-]{1,32}$`（照 `intakeName`，`auth.go:57`）→ 主体固定 `thread:collector@<host>`，**不读会话头**；其余令牌推导不变。`LoadAuth` 对 `collector:` 加名字校验（照 agentd，`auth.go:199-203`）。
- 令牌名 `collector:<host>`，角色 reporter；`<host>` 等于本机 agentd 主体的主机号（`handin.sh:51` 的默认值）。铸：`.env` 加 `PLATFORM_{STG,PROD}_COLLECTOR_<HOST>_TOKEN`；apply 脚本的循环加键；两份 overlay 的 `platform-auth.yaml`、两份 Deployment 补丁各加一条。平台仓库的 `config/platform-auth.yaml` 不动。
- 存：用户配置目录 `.config/bifrost/collector.token`（600），环境变量 `PLATFORM_COLLECTOR_TOKEN` 覆盖。换：换值不换名；`.env` → apply → `rollout_restart_deployment` → 换文件。
- 环境配对：STG 演练前跑 `collector-audit.js --preflight`，`PLATFORM_HEARTBEAT_URL` 与 `PLATFORM_COLLECTOR_TOKEN` 成组、同环境，打印脱敏诊断，不齐不起会话（没有令牌客户端根本不发，§0 第 17 条，不能指望 401）。

### 1.3 白名单：一个挂点，覆盖全部模块

挂点：`/api/v1` 路由器的 `Use`（`server.go:403`），在所有子模块之前。中间件自己 `Authenticate`；主体名以 `collector:` 开头时，方法加路径不在允许表就 403。普通 reporter、席位、agentd 不经过它。`abilitiesOf`（`controls.go:78-90`）对收集员只报表内能力。

| 允许 | 条件 |
|---|---|
| `POST /agentrt/external-work`、`POST /agentrt/external-work/{id}/events` | §1.4 |
| `PUT /agentrt/artifacts/{id}` | 只许 `other` 且过 `ValidateExternalDescription`（`api.go:641-644`、`:663`）；S2 再放出门条 |
| `GET /agentrt/whoami` | — |
| `GET /agentrt/external-work/{id}` | **记录级归属**：note 的登记者等于收集员主体，否则 403 |
| `GET /agentrt/artifacts/{id}` | **记录级归属**：`created_by_actor_id` 等于收集员主体（`0001_core.sql:38`），否则 403；说明内容已被别人先传过的，收集员读不到，用本机副本 |
| `POST /agent/threads/heartbeat`、`POST /agent/hosts/heartbeat` | `host` 等于名里的主机，否则 403 并审计（照 `handler.go:52`）；收集员的心跳带 `title` → 400，客户端在收集员模式下不填（§0 第 16 条） |
| `GET /agent/threads` | 整份响应只含**本主机**：线程、`hosts[]` 只留本主机一条，全局拒收计数不给；线程行**不带 `title`**（标题库按 UUID 全局补齐、无主机归属，§0 第 16 条）；加 `?sidebar=`、`?session=` 过滤（§3.3）；普通 viewer 不变 |

其余全拒，含 `PUT /lineage/transcript-title`、`plan-view`、`events`、`tasks*`、`plan*`、问题路由、controls、tighten、rules、missions、messages、plan 提议、`PUT /agent/progress`、skill-runs、Alertmanager。S3 的决定读回另加带主机过滤的路由，到时再入表。
负测 `CollectorRouteSurface`：`chi.Walk` 遍历当前路由器，收集员令牌对每个方法加路由断言，允许表之外全 403；`route_reach_check_test.go` 加 `collector:h1` 主体行，对照其余主体可达性不变。

### 1.4 「自己的主机 / 会话 / 工作」

| 检查 | 规则 |
|---|---|
| 主机 | 取自令牌名。心跳 `host` 不等 → 403。登记的 `host` 由服务端写 |
| 工作 | 登记者主体相同（`externalwork.go:340`）；读同上表 |
| 会话身份 | 登记必带 `vendor`（`claude\|cursor\|codex`）、`session`、`epoch`（正整数）；可选 `sidebar`。`session` 的含义按登记者：钩子登记（claude、cursor）是**原始厂商 `session_id`**，不是传输线程号（§0 第 13 条）；Codex 包装器登记（§2.5）是**包装器的 run key**，不是厂商会话号，服务端只校验形状与不可变，读者不得把它当厂商号。**每条事件**必带同样三个字段，且与登记时不可变的三元组全等；`linked` 只改 root/节点/任务。缺、空、null、任一不同都拒：400 `identity_required` / 409 `identity_mismatch`。`source_run_key` 固定 `<vendor>:<session>:<epoch>` |

只对收集员主体生效；MCP 的登记不变。残余（N15 (i) 已接受）：同主机同令牌显式填上目标的完整三元组去碰别人的工作，拒不了。

### 1.5 负测

| 名 | 做法 → 期望 |
|---|---|
| `CollectorRouteSurface` | §1.3 |
| `CollectorDerivation` | 普通 reporter 带头 `collector@h1`/`collector-h1`，席位、agentd、operator 带任意头 → 今天的推导（`collector@h1` 被 `ThreadActor` 拒）；收集员无头/换头 → 恒为 `thread:collector@h1` |
| `CollectorNameReserved` | 只有名为 `collector:h1` 的令牌能以 `thread:collector@h1` 写 |
| `CollectorOwnRecordsOnly` | h1 读 h2 收集员的工作 → 403；读 h2 的说明 → 403；读 MCP 登记者的工作与说明 → 403；读自己的 → 200（阳性对照） |
| `CollectorThreadsNoTitle` | h1 的线程列表：只含 h1；h2 有 `claude/<UUID>` 标题、h1 登记 `codex/<UUID>` → 响应无 `title`；行逐出后重占 → 仍无 `title`；viewer 的列表照旧有 |
| `CollectorTitleRefused` | 收集员 `PUT /lineage/transcript-title` → 403；收集员心跳带 `title` → 400，statefile 与 viewer 响应都没有新标题；reporter 心跳带 `title` 照旧 |
| `CollectorRegisteredAt` | 登记回复与 `GET /external-work/{id}` 都带 `registered_at`；同幂等键重放、恢复读取返回同一个时间 |
| `ForeignWork_IdentityRequired` | 登记或事件缺/空/null 任一字段；`linked` 缺三元组 → 400 |
| `ForeignWork_IdentityMismatch` | 同 session 不同 epoch；同 session 不同有效 vendor；会话 B 的三元组给 W_A → 409 |
| `ForeignWork_ReplayOtherIdentity` | 同幂等键同 seq 换三元组重放 → 409（`externalwork.go:380-383`） |
| `ForeignWork_OtherToken`、`…OtherHostBeat` | 403 |
| `ForeignWork_Residual` | 同主机同令牌、填 B 的完整三元组碰 W_B → 接受（阳性对照） |

## 2. 启动、登记、世代

### 2.1 来源

| 来源 | 可信程度 | 做法 |
|---|---|---|
| 新启动器 `scripts/agent-host/dispatch-claude.py`（§2.2） | 程序性（不是对抗性，同 N14） | 写说明与启动记录、导出环境、起 `claude` |
| `dispatch-codex.py` | 同上 | 改用收集员令牌登记（§2.5）；这条登记**就是** Codex 会话在运行时的记录 |
| handin | 运行时任务 | 不经收集员；§5 |
| Desktop 侧栏开的会话、手起的 `claude` | 无 | 不登记，Unlinked；事后 `bind`（§2.4）。标题、对话里的编号不当上下文 |

### 2.2 Claude 启动器（新交付件）

`scripts/agent-host/dispatch-claude.py`（照 `dispatch-codex.py` 的结构，`:176`）：
1. 铸 `launch_id`（UUID，只是进程启动的身份），建 `.cache/bifrost/external-work/launches/<launch_id>/`；
2. 验收编号与 `plan_version` 由统筹用自己的令牌从采用文档的 `items[].acceptance`（`document.go:59`）读出，显式传给启动器（`--acceptance-ref` 可重复、`--plan-version`）；启动器只持收集员令牌。写完整说明 JSON（`v`、`kind` 固定；`task`、`executor` claude、`provider` anthropic、`repo`、`branch`、`acceptance_refs`、`estimate_minutes` 由命令行给；缺一项拒绝启动，不编）；
3. 写启动记录 `launch.json`：`launch_id`、`vendor`、`host`、`started_at`、`root`、`node`、`plan_version`、说明摘要、`sessions: []`；
4. 导出 `BIFROST_LAUNCH_ID`、`BIFROST_PLAN_ROOT`、`BIFROST_PLAN_NODE`、`BIFROST_WORK_DESCRIPTION`；环境里没有 `CLAUDE_CODE_HOST_SESSION_ID` 时导出 `CLAUDE_CODE_HOST_SESSION_ID=launch-<launch_id>`（Desktop 开的保留原值）：钩子的 `sidebar`（`thread-heartbeat.js:220-226`）、MCP 的会话头（§0 第 2 条）、提交的 `Claude-Session` 尾注（`lineage.sh:39-42`）由此归到同一个号，无侧栏号的 CLI 入口才能满足 `HookAndMcpWriteSameSession`；exec `claude`（交互或 `-p`，参数原样透传，不上传）；
5. 钩子每建立一个 `(session, epoch)` 就追加进 `launch.json.sessions[]`；子进程退出后 `sessions` 仍空 → 这次启动是漏报缺口（§9），不是「没启动」；
6. `--unlinked` 模式：不给计划上下文、不写说明，只写启动记录；是无上下文路径的受管样本（§9）。

### 2.3 世代（只服务登记，不服务交付判定）

一件外部工作 = 一个 `(vendor, session, epoch)`。`epoch` 是每个 `(vendor, session)` 的单调计数，存 `.cache/bifrost/external-work/<vendor>/<session>/epochs.json`，`flock` 下 `max+1`。
- 分配：SessionStart source=startup/clear → 新会话号、`epoch=1`；resume → `max+1`；compact → 不变；SessionStart 丢失 → 第一个钩子事件分配。
- 解析：按钩子输入的 `session_id` 找 `epochs.json`，再用钩子进程的父进程号对 `{epoch, ppid}`（父进程号是否稳定在 S1-0 核，**未核实**）；对不上取该会话当前世代并记 `identity: current_fallback`。重复的 SessionStart（同 `session_id`、source、ppid）不新建。迟到的 SessionEnd 解析到已结束的世代就丢并计数；只能 `current_fallback` 的迟到结束不执行，记缺口。

| 事件 | 会话号 | 世代 | 做什么 |
|---|---|---|---|
| SessionStart startup / clear | 新 | 1 | 有上下文就登记 + `started`；追加进 `launch.json.sessions[]` |
| SessionStart resume | 同 | max+1 | 旧世代未结束先 `cancelled`；再登记新世代 |
| SessionStart compact | 同 | 同 | 只发 `session_start` 心跳 |
| PreCompact | 同 | 同 | 发 `precompact` 心跳 |
| SessionEnd（任何 reason） | 同 | 按解析 | `submitted`，不带 `exit_code`（`externalwork.go:51`） |
| 进程被杀 | — | — | Running → Unconfirmed；下次 resume `cancelled`；否则 S5/S11 对账 |

**状态目录、唯一写者、恢复**：独立目录 `<vendor>/<session>/<epoch>/`（`state.json`、`wrapper.lock`、待发事件），不动 gate 文件（§0 第 14 条）。唯一写者 = 持 `wrapper.lock` 的进程：Claude 是 `register-claude-work.py`（钩子触发；锁忙等最多 2 秒，`:154-158`），Codex 是包装器，`bind` 共用目录。请求体、工作号、seq、待发事件存 `state.json`，重试重放同一请求体（`dispatch-codex.py:95-112`）。结束意图先持久化，`ended` 等服务端 ACK；无 ACK 无后续钩子 → 审计记**结束缺口**，resume/bind 补发。外部 `heartbeat`：`UserPromptSubmit`、`Stop` 各一次，工具事件 30 秒最多一次；空闲超 60 秒显示 Unconfirmed（`planviewsnapshot.go:255`），Live 行加 `idle since`。钩子 5 秒截止（`thread-heartbeat.js:77-81`）：登记在 SessionStart 同步做，超时留待发。

### 2.4 事后绑定

`register-claude-work.py bind --session <CLI 号> --epoch <世代> --root … --node … --description <文件>`：同一说明来源，同一目录，之后钩子接着写。不能用 MCP 的 `register_external_work`：它以 `thread:<侧栏号>` 登记，收集员加不了事件（`:340`）。脚本今天只收 `local_` 会话号（`:69`），要放开。

### 2.5 Codex：包装器登记就是记录，钩子线程不逐个绑定

`dispatch-codex.py` 改用收集员令牌（文件或 `PLATFORM_COLLECTOR_TOKEN`，不再用 `BIFROST_DISPATCH_TOKEN`），登记带 `vendor=codex`、`session=<run key>`、`epoch=1`；服务端写 `host`；包装器仍是唯一写者，退出时 `submitted`（`:303`）。Codex 钩子的线程心跳照发（主机、原始 `session_id`），在线程列表里显示为 `unsupported`（`server_note=codex_binding_after_s1_0`），**S1 不把它和包装器的登记逐个对上**：包装器启动前不知道 Codex 的会话号，环境又整体继承给子进程（§0 第 13、23 条），任何自报关联都能被嵌套会话抢占。逐会话绑定等 S1-0 记下 Codex 钩子实际收到什么之后再定。迁移前的旧包装器登记没有 `host`（`externalwork.go:53-80`）→ `unknown`。

## 3. Unlinked 列表

### 3.1 连接键与判定

键 `(host, vendor, session, epoch)`，`session` 是原始厂商 `session_id`，传输线程号另存。心跳加可选 `session`、`epoch`（`wireBody` 不再删 `session`，`:273`）；旧客户端 `session=线程号`、`epoch=0`。服务端按键记 `first_seen_at`（每个世代各一个）。

| 情况 | `binding.state` |
|---|---|
| 运行时有同键的最新外部工作 | `linked`（带工作号、root、节点、工作状态；旧世代数放 `history`） |
| 没有；`client_bind.state` 为 unlinked、缺省或 linked（客户端自报不算数） | `unlinked` |
| 没有；`client_bind.state=refused` | `refused`（reason 从封闭集） |
| vendor 是 codex 的钩子线程 | `unsupported`（§2.5） |
| 旧包装器记录（无 host）、运行时读失败 | `unknown` |

`client_bind {state: unlinked|refused|linked, reason, at}` 是客户端诊断，reason 封闭：`no_context`、`no_description`、`node_rejected`、`not_dev_tree`、`register_failed`、`token_missing`、`identity_fallback`、`no_vendor_session`；随线程保留与清除，不参与权限。`server_note` 是服务端诊断（`codex_binding_after_s1_0`、`runtime_unreadable`、`legacy_no_host`）。查询形状同 `snapshotExternal`（`planviewsnapshot.go:218-219`），缓存 10 秒；旧 Coverage 查询排除 `thread:collector@`。

### 3.2 去重与计数

`coverage.sessions` 按键去重（key 恢复的 `<会话>:n` 算一个，当前行取 `at` 最新）；返回 `{linked, unlinked, refused, unsupported, unknown, scope}`，五个数之和等于保留期内去重后的会话数；原四个键不动。交付检查的结论不进平台（§5）。resume 的新世代用新世代的 `first_seen_at` 算时延。

### 3.3 API 与 Console

推荐 **B**：`GET /agent/threads` 每条加 `binding`、`client_bind`、`server_note`、`first_seen_at`、`compactions`、`session`、`epoch`、`host_id_source`、`token_kind`；加查询参数 `?sidebar=<侧栏号>`、`?session=<原始厂商会话号>`（服务端匹配，响应仍不输出 sidebar，§5 用）；读端宽松（§0 第 20 条）。登记回复与 `GET /external-work/{id}` 加 `registered_at`（取 note 的 `RegisteredAt`，重放与恢复不变，§0 第 21 条），`dispatch-codex.py` 的 `state.json` 由此记登记时间。A（新路由）与 C（只放 plan-view）不取：多一个接口 / 按 root 放不进。plan-view 的 `coverage` 两组数按 §7 两步发。读权 viewer（`server.go:500`）；收集员只得本主机且无 `title`。
Console：Work → Plan → Live，Finished today 之后加 `Unlinked sessions · n`：厂商 · 主机 · 会话短号（`agentThreads.ts:112-116`）· 六种状态 · 首次看到 · 最后事件 · 原因；`unsupported` 的 Codex 线程另成一行计数。不显示标题；`tool` 是字符串，只在详情。Status 页不动。Coverage 行三组数。Phone：换行、44px、不靠颜色。

## 4. 钩子（N16 A）

### 4.1 Claude

`agent-config/claude/settings.json` 加三项，都调 `thread-heartbeat.js hook claude`；SessionEnd 设 `timeout`（默认共享 1.5 秒，提案 `:9`、`:42`）。

| 事件 | 心跳 | 做 | 不做 |
|---|---|---|---|
| SessionStart | 新枚举 `session_start`，`reason`=source | 登记线程（不开回合）；§2.3 | 不注入；stdout 空 |
| PreCompact | 新枚举 `precompact`，`reason`=trigger | 记一拍，服务端按 seq 去重计 `compactions` | 不阻止；不写出门条 |
| SessionEnd | `turn_end` | §2.3 的结束协议，脱离子进程 | 不传正文 |

服务端：枚举加两个（`threads.go:332-334`）；reason 清空规则改为 `waiting_owner`、`session_start`、`precompact` 保留（`:340-341`）；`session_start` 不改 `OpenedTurn`/`TurnStartedAt`；`precompact` 不改工具超时与 waiting。`worktree-lease.py` 不在 S1 接线。

### 4.2 Cursor、Codex 与缺口

| 入口 | SessionStart | PreCompact | SessionEnd | S1 |
|---|---|---|---|---|
| Claude | 文档有 | 文档有 | 文档有 | 全装；S1-0 实测 |
| Cursor | `sessionStart`（`worktree-lease.py:21` 按此名读；未核实） | 未核实 | 已接（`hooks.json:47`） | 装 `sessionStart`，重跑 `install-hooks.py` |
| Codex | 未接，厂商能力未核实 | 同左 | 未接，厂商能力未核实（表里四项只说明适配，`thread-heartbeat.js:119-125`） | 不装；线程显示 `unsupported` |

「未核实」只能由 S1-0 的真实触发证据改写。缺口清单由审计脚本输出（宿主心跳的 `vendors.wired` 只证明命令存在，`host-heartbeat.js:212-219`）。

### 4.3 主机身份、令牌与 parity

- 一个来源：`.config/bifrost/host-id`，`BIFROST_HOST_ID` 覆盖；`thread-heartbeat.js`、`host-heartbeat.js`、`register-claude-work.py`、`dispatch-*.py`、`handin.sh` 都读；都没有才退回 OS 短名 / 默认值。心跳带 `host_id_source: file|env|hostname`（客户端诊断）；`token_kind` 由服务端从认证主体填。
- `host-heartbeat.js` 改读收集员令牌，没有再退回 reporter。`thread-heartbeat.js` 的 `token()` 按用途选：心跳路由用收集员令牌，`publishProgress` 仍用 reporter 令牌（§0 第 23 条；`PUT /agent/progress` 对收集员是拒的）。`report-thread-title.js` **不动**（§0 第 17 条），标题路径整条留在 reporter 令牌上；收集员模式的心跳不填 `title`。
- Parity：改 `claude/settings.json` 同改 `cursor/hooks.json`、`codex/README.md`（`agent-config/CLAUDE.md:274`）；parity 第 5 项加「Claude 三事件、Cursor 两事件都接了心跳」，Codex 现有检查不放松（`check-agent-config-parity.sh:193-196`）；不改规则文字不 bump；完整 parity 对交付布局跑（`CLAUDE.md:280`）。

## 5. 交付时没登记的活由系统指出

只用今天就有的尾注，不加尾注、不改 squash、不改 amend 规则。

| 步 | 做法 |
|---|---|
| handin `squash` | 对来源区间 `base..head` 的每个提交读 `Claude-Session`（现解析语义：每提交一个值，`trailers.go:36-60`；侧栏号，无 Desktop 时是 CLI 号，`lineage.sh:39-45`），去重后存进任务的状态目录 |
| 查询 | 对每个值先 `GET /agent/threads?sidebar=<值>`，没命中再 `?session=<值>`（原始厂商会话号，不是传输线程号，所以 `run` 包装器改号、key 恢复改号都不漏，§0 第 13 条） |
| 结论 | 五态到结论，按这个顺序判，先命中的为准：① 任一匹配线程 `linked` → 已登记（同侧栏号下另有 `unlinked` 也一样，见下方残余）；② 没有 `linked`，含 `unsupported`（Codex 钩子线程，包装器可能已登记但对不上）或 `unknown` → **不确定**；③ 全部是 `unlinked`/`refused` → **未登记**；④ 没有线程、读失败、提交没有尾注 → **unknown**。只有 `linked` 能判已登记。例：A=`linked`、B=`unlinked` → 已登记；A=`unlinked`、B=`unsupported` → 不确定；A、B 都是 `unlinked` → 未登记 |
| 指出 | `squash` 与 `run` 各在 stderr 打一行每个会话的结论；`run` 把结论写进本机 `unregistered_sessions.json`，不拦；平台侧不写 note |
| 读面 | 无：S1 平台不收这个结论，指出只在交件时的终端输出与本机文件 |

**残余，写明**：没写过提交的会话交件时查不到；squash 之后的提交没有尾注（§0 第 18 条），所以检查只在 `squash` 读来源区间时做，`run` 只回放结果；返工再次 squash 以第一次 squash 的提交为来源时没有尾注 → unknown；粒度是「这个号有没有登记或关联」：同 CLI 号的多个世代不区分，**同一侧栏号经 `/clear` 对应的多个 CLI 会话也不区分**（`Claude-Session` 优先写侧栏号，`lineage.sh:39-42`），其中一个 linked 就判已登记，另一个未登记的 CLI 会话查不出；Codex 会话一律不确定。拦是 S4。

## 6. 契约改动清单

| # | 改动 | 种类 | Owner 签 |
|---|---|---|---|
| 1 | 新主体 `collector:<host>`：两份 overlay yaml、两份补丁、Secret 与 `.env` 各两键、apply 脚本 | 新凭据；`k8s/**` | O2 |
| 2 | 主体推导、保留命名空间、全模块白名单中间件、记录级归属读、线程列表对收集员去 `title` 并限本主机 | Go，无 DDL | O1、O7 |
| 3 | 外部工作：收集员必带不可变三元组（钩子登记用原始厂商会话号，Codex 包装器登记用 run key，§1.4）、可选 `sidebar`，服务端写 `host`；事件全等校验；登记回复与 `GET /external-work/{id}` 加 `registered_at`；派活包装器改用收集员登记 | 扩展 D-PV2 A（N11 ①）；plan-view `external` 与夹具 | O3 |
| 4 | 心跳：枚举 `session_start`、`precompact`；字段 `session`、`epoch`、`client_bind`、`host_id_source` | 公开接口 | O5 |
| 5 | `GET /agent/threads` 加 `binding`、`client_bind`、`server_note`、`first_seen_at`、`compactions`、`session`、`epoch`、`host_id_source`、`token_kind`、`?sidebar=`、`?session=`，收集员的响应只含本主机且无 `title`；收集员心跳拒 `title`；plan-view `coverage` 加 `sessions`（五态守恒） | 公开接口；两步发 | O5 |
| 6 | 钩子接线三处 | 治理文件 | O4 |
| 7 | `thread-heartbeat.js`、`host-heartbeat.js`、新 `dispatch-claude.py`、`register-claude-work.py`、`dispatch-codex.py`、`handin.sh`（读尾注与查询）、parity 脚本、审计脚本 | `agent-config/scripts/**`、`scripts/**` | 他推 |
| 8 | （只在 A）迁移 0012 | DDL | 要 |

没有 DDL（按推荐）；没有新 MCP 工具；没有新尾注；不改 `lineage.sh`、`report-thread-title.js`。

## 7. 顺序与谁推

先签 O1–O7 再做。STG 由 Agent（`CLAUDE.md:222-227`），PROD 走审批单（`:228-230`）。

| 序 | 件 | 谁 | 依赖 |
|---|---|---|---|
| 0 | 签 O1–O7 | Owner | — |
| 1 | P-a 主体、白名单、归属读、主机绑定 | platform，经运行时；PROD 审批单 | 0 |
| 2 | P-b 外部工作三元组与校验；新字段全部 `omitempty`，在 P-c1 上 PROD 前不产生带新字段的记录 | 同上 | 0 |
| 3 | P-c1 读端：plan-view `coverage`、`external` 新字段可选；线程类型加字段 | 同上 | 0 |
| 4 | P-c2 出字段：心跳枚举与字段、投影、coverage、Live 节、`?sidebar=` | 同上；在 P-c1 上 PROD 之后 | 3 |
| 5 | I-a STG overlay | Agent `push-main.sh`；Secret 数据 Owner | 1 |
| 6 | I-b PROD overlay、`.env`、Secret | Owner | 1 |
| 7 | I-c 钩子脚本、接线、parity、宿主心跳迁移 | Owner | 4、6 |
| 8 | I-d 启动器、登记脚本、包装器迁移、handin 检查 | Owner | 7 |
| 9 | 本机：host-id、令牌、`install-hooks.py`、重启心跳 | Owner 一条命令 | 7 |

混合版本：「旧读端」指 P-c1 的 Console；P-c1 之前打开的标签在 P-c2 后整页失败，刷新即好，写进发布说明。验收跑「P-c1 读端 + P-c2 接口」与「P-c2 读端 + 字段缺省」。向后兼容不等于免签。

## 8. 切片

| 片 | 内容 | 测试 | 粗估 |
|---|---|---|---|
| S1-0 能力校准（SS0-S） | 来源 × 输入格式 × 运行模式清单：Claude 钩子（SessionStart ×4、PreCompact ×2、SessionEnd 各 reason、Stop、SubagentStart/Stop、UserPromptSubmit、PostToolUseFailure、Notification）、Claude `-p` stream-json（含 `--no-session-persistence`，`CUT:55`）、forked skill（`--forward-subagent-text`，结束后交付 → delayed）、子线程运行中发现（`CUT:108-112`）、Codex 交互钩子**实际收到的字段**（决定逐会话绑定怎么做）、Codex `exec --json` JSONL（含 `--ephemeral`，`CUT:51`）、Cursor 钩子与 `cursor-agent -p` stream-json（`CUT:93-99`）；Start 丢失、Stop-only、无 `session_id`、未知结构、钩子父进程号是否稳定 | `SourceCapabilityWitness`：每个观测到的来源一份夹具，逐字段对脚本输出，live/delayed/unavailable 分类；未知结构只记占位；未观测记未核实 | 2 |
| S1-1 身份 | 推导、保留名、白名单中间件、记录级归属、主机绑定、`whoami` | `CollectorRouteSurface`、`…Derivation`、`…NameReserved`、`…OwnRecordsOnly`、`…TitleRefused`、`ForeignWork_OtherHostBeat`；`HookAndMcpWriteSameSession` 第一半（两种先后） | 1.5 |
| S1-2 契约 | 三元组、校验、run key、P-c1 读端与夹具 | `ForeignWork_Identity*`、`…ReplayOtherIdentity`、`…Residual`；`BindingAtomicity`（重复登记同工作；并发只成一条；中断重放幂等；同 run key 换内容 409；`linked` 换节点、带 `task_id` 仍同一工作）；`HookAndMcp…` 第二半：有侧栏号（Desktop）、无侧栏号由启动器补 `launch-<id>`、同主机两个 CLI 会话各归各、两种写入先后，都按 `sidebar` 查到同一关联，主机名相同不算；`CollectorRegisteredAt` | 1.5 |
| S1-3 读面 | 枚举、状态机、`first_seen_at`、`compactions`、`token_kind`、投影、去重、coverage、`?sidebar=`、Live 节 | 投影五态、`CollectorThreadsNoTitle`、key 恢复后仍 linked、同号不同厂商分开、多世代取当前、运行时不可读、守恒；枚举/reason/不开回合/不扰等待/重发不重复计；Console 五态、空态、离线态、P-c1 读端对 P-c2 响应；渲染测试：用真实响应渲染 `PlanLiveWork`，断言 Live、Finished today、Unlinked 各行按稳定身份出现 | 1.5 |
| S1-4 钩子与世代 | 事件表、`session`（原始厂商号）/`epoch`/`client_bind`/`host_id_source`、状态目录、原子世代、结束协议、节流心跳、宿主心跳令牌与 host-id、接线、parity | 生命周期夹具：startup、同秒两次 resume、重复 SessionStart、compact、迟到 SessionEnd 跨 resume、Start 丢失、嵌套在 `run` 包装器下；锁竞争；结束意图持久化、ACK 丢失记缺口；5 秒退出；host-id 缺失诊断；收集员模式不填 `title`；`token()` 按用途选凭据，`progress-publish.js` 仍走 reporter | 1.5 |
| S1-5 启动器与脚本 | `dispatch-claude.py`、`bind`、包装器迁移、handin 读尾注与查询、README | 启动记录与 `sessions[]` 回填；说明缺项拒启；真实启动但 `BIFROST_HEARTBEAT=off` → 审计报缺口；`--unlinked` 真实启动 → Unlinked 节可见；包装器登记 → Live 行；bind 幂等；handin 对 linked / 未登记 / 无尾注三态，squash 后的提交 → unknown | 1.5 |
| S1-6 STG 演练与证据 | §9：四类入口各走一遍完整生命周期 | — | 1 |

合计 10.5 人日，不含 Owner 等待、发布窗口、复核轮次。

## 9. 验收（§11.2 S1 的可跑检查）

**分母在被测钩子之外**：

| 入口 | 分母来源 | 身份 | 首次服务端事件 | 目标列表 | 结束 |
|---|---|---|---|---|---|
| `dispatch-claude.py`（有上下文） | `launch.json`（启动器自己写的） | 该启动的 `sessions[]` 每一条 | 线程该世代的 `first_seen_at` | plan-view `working[]`（`planviewsnapshot.go:121`）且 Console Live 行（`PlanLiveWork.tsx:78`）；`binding` 只作绑定率 | `finished_today`（`:124`）且 Console Finished today 行（`:93`） |
| `dispatch-claude.py --unlinked` | 同上 | 同上 | 同上 | `/agent/threads.binding.state=unlinked` 且 Console Unlinked 节 | — |
| `dispatch-codex.py` | `state.json` 新增 `registered_at`（取 note 的 `registered_at`） | 工作号 | note `registered_at` | `working[]` 且 Console Live 行（按工作号） | `finished_today` 且 Console 行 |
| handin、agentd | `attempt_leased` 的 `at` | 尝试号 | 同左 | `working[]` 且 Console Live 行（按尝试号） | `finished_today`（`:147`）且 Console 行 |
| Desktop 开的会话、手起的 `claude` | **没有分母**（S1 的缺口，列进缺口清单） | 四元键 | `first_seen_at` | Unlinked 节 | — |

**受管启动内的 `/clear`**：生产审计看不到没上报的后续会话，只能看到 `sessions[]` 里有的；STG 演练由驱动脚本**先记下**计划的转换（startup → `/clear` → 结束），再对照 `sessions[]` 与目标列表，少一条就是该次启动的缺口；用例含「A 上报成功、同进程 `/clear` 到 B、B 全部钩子关闭」→ 必须报缺口。

审计脚本 `agent-config/scripts/collector-audit.js`（只读）。两个覆盖率分开：**启动覆盖率** = 有至少一条送达会话记录的 launch / 全部 `launch.json`（`sessions` 为空的算漏报，分母独立于钩子）；**演练转换覆盖率** = 目标列表里观测到的转换 / 驱动脚本预记的转换（startup、`/clear`、结束各算一条，只在 STG 演练有）。时延样本按 `sessions[]` 的每一条算。生产里没上报的后续 `/clear` 是未知范围，启动覆盖 100% 不等于会话覆盖 100%；时延 = 首次事件到**出现在目标列表**，两类各 100% ≤ 60 秒——从启动记录出现起每 5 秒轮询，记第一次出现，120 秒超时记失败；目标列表漏项、plan-view 读失败、Console 解析失败都算失败；渲染由 S1-3 的组件测试对同一响应断言，加 STG 浏览器人工核对；结束同样轮询；绑定率 = linked / (linked+unlinked+refused)，`unsupported`、`unknown` 单列；结束缺口 = 有结束意图无 ACK；缺口清单 = 入口 × 三钩子 × 有/无/未核实，加「无分母的入口」「未上报的 `/clear`」两行；阈值、窗口、零分母 N/A 在 S1-6 前冻结。

**命令到测试**：Go `go -C api test ./internal/agentrt/... ./internal/agentthreads/... ./internal/server/... -run 'Collector|ForeignWork|HookAndMcp|BindingAtomicity|RouteReach' -count=1 -v`（设 `AGENTRT_TEST_PG`、`AGENTRT_TEST_REDIS`、`AGENTRT_TEST_REQUIRED=1`；核对每个 RUN、无 SKIP）；JS `node --test agent-config/scripts/thread-heartbeat.test.js agent-config/scripts/host-heartbeat.test.js agent-config/scripts/collector-audit.test.js`（含 `SourceCapabilityWitness` 夹具）；Python `python3 -m pytest -q scripts/agent-host/tests`；handin `bash agent-config/scripts/landing/test_handin.sh`；parity `bash scripts/check-agent-config-parity.sh`；Console `npm --prefix console run lint && npm --prefix console run build && npm --prefix console test`。

**钩子装好**：STG 一个启动器起的 Claude 会话，启动、`/compact`、`/clear`、结束；`compactions==1`、`first_seen_at` 非空、Live 行 60 秒内出现、结束后 Finished today 出现、`launch.json.sessions` 两条；一个 `--unlinked` 会话 → Unlinked 节；一个 `dispatch-codex.py` 运行、一次 handin 交件、一个 agentd 尝试各验 Live 与 Finished today 行；Codex 钩子线程显示 `unsupported`。Cursor `sessionStart` 一次。
**§11.4 第 3 条证据**：审计按分母逐会话输出入口、起点、首次事件、读面、秒数、统筹动作数（0）；存 `agent-config/work/multi-agent/EVIDENCE-s1-<日期>.md`，主机名、标题、会话号换占位符。

## 10. 风险

| 风险 | 对策 |
|---|---|
| 同主机显式冒用完整三元组（N15 残余） | 接受；每会话密钥留后续 |
| 无启动器的 resume，父进程号不稳定时迟到结束归错世代 | S1-0 核；不稳定则该路径 `current_fallback` 记缺口 |
| 结束 ACK 丢失且无后续钩子 | 记结束缺口，resume/bind 补发 |
| 旧 reporter 令牌仍能报任意主机、写任意标题 | 既有风险，登记技术债；`token_kind` 服务端填，审计可见 |
| 投影扫全部外部工作 note | 缓存 10 秒；TD-445 同类 |
| plan-view 读端封闭 | P-c1 先于 P-c2；P-b 不先产生新字段 |

## 11. 范围外（含本稿裁掉的）

出门条与上传权（S2）；决定记录与注入（S3）；会话表 DDL 与正文采集（S11）；本机动作流（S5）；外部尝试与自动派复核、交付时「拦」（S4）；每会话密钥；放宽说明契约；`worktree-lease.py` 接线；Cursor/Codex 压缩钩子。
**裁掉的**：收集员读写任何标题；Codex 会话逐个绑定（S1-0 之后定）；世代尾注、来源尾注、squash 与 amend 的来源保留；平台侧的交付 note 与 `coverage.handins`；非受管会话的分母；Status 页标题读面。

## 要 Owner 定

**已定（Owner，统筹线程 2026-11-03 18:45 CST）：全部按推荐，O1 选 B，O2–O7 选 A。** 实施按这些选项做；PROD 发布仍另走批准。

| # | 问题 | 选项 | 推荐 |
|---|---|---|---|
| O1 | 收集员主体 | A：`collector:<host>` 种类 + DDL；B：`thread:collector@<host>`，无 DDL | **B** |
| O2 | 铸令牌 | A：§1.2；B：复用 reporter 令牌 | **A**（B 无主机绑定、无固定名） |
| O3 | 外部工作契约扩展（N11 ①具体字段） | A：收集员必带不可变三元组（钩子登记用原始厂商会话号，Codex 包装器登记用 run key）、每条事件全等校验、可选 `sidebar`，服务端写 `host`；回复加 `registered_at`；派活包装器改用收集员登记，旧记录 unknown；B：只加可选 `session` | **A** |
| O4 | 钩子接线 | A：Claude 三项（SessionEnd 带 timeout）+ Cursor `sessionStart`；B：只装两项 | **A**（没有 SessionEnd 工作永不结束） |
| O5 | 公开接口加枚举与字段 | A：§6 #4、#5（心跳两枚举四字段、收集员拒 `title`；线程列表字段与 `?sidebar=`、`?session=`，收集员整份响应只含本主机；`coverage.sessions` 五态守恒），plan-view 两步发；B：只加线程 `binding` | **A** |
| O6 | 交付时的处置 | A：handin 读现有尾注、查平台、终端与本机文件指出，不拦、不写平台；B：未登记拒交 | **A** |
| O7 | 收集员白名单与读范围 | A：§1.3：写只有登记、事件、说明、不带标题的心跳；读只有 `whoami`、自己的工作、自己的说明、只含本主机且无标题的线程列表；B：继承 limitedReporter | **A** |

## 统筹定

- C1 S1 不向 Unlinked 会话注入任何内容。
- C2 空闲显示 Unconfirmed，加 `idle since`；不起脱离心跳。
- C3 环境变量名 `BIFROST_LAUNCH_ID`、`BIFROST_PLAN_ROOT`、`BIFROST_PLAN_NODE`、`BIFROST_WORK_DESCRIPTION`、`BIFROST_HOST_ID`。
- C4 SS0-S 夹具钉当前 Claude Code 版本号；父进程号解析能否用由 S1-0 定。
- C5 Unlinked 行不显示标题。
- C6 审计脚本与证据文件位置如 §9。
- C7 切片按 §8；S1-0 先于协议冻结；平台 P-c1、P-c2 分两次发；顺序不代签 O 项、不代替审批单。
- C8 不改规则文字不 bump parity-id。
- C9 投影缓存 10 秒；状态目录独立于 gate 文件。
- **C10 标题**：收集员的线程读不带任何标题，也不写标题；标题整条留在今天的 reporter 路径，其风险是债不是 S1。理由：标题永久、线程行短命，没有持久归属就没有安全的跨主机规则。
- **C11 Codex 别名**：撤掉别名协议；Codex 会话的运行时记录就是包装器的登记；钩子线程只按主机和会话显示，不逐个绑定；逐会话绑定等 S1-0 记下 Codex 钩子实际收到什么再定。理由：包装器启动前不知道会话号、环境整体继承，先到先得会被嵌套会话抢占。
- **C12 世代与来源尾注**：撤掉 `Claude-Epoch`、`Bifrost-Source`、squash 来源保留；交付检查只读现有 `Claude-Session`，无尾注一律 unknown。理由：每加一种来源机制都在 amend、再 squash 上开新口子，S1 只要「指出」。
- **C13 `/clear` 分母**：受管启动的分母是启动器自己的记录；启动内没上报的 `/clear` 算该次启动的缺口；非受管会话 S1 没有分母，列为缺口。理由：分母不能来自被测钩子。
- **C14 契约、切片、附录按裁定同步**；附录只留最终处置，轮次历史在复核文件里。

## 未核实

- Cursor 的 `sessionStart` 与压缩钩子、Codex 的 SessionStart/PreCompact/SessionEnd 与钩子实际字段、各家当前版本的钩子输入字段、Claude 当前版本在 `--no-session-persistence` 下的钩子行为、子线程运行中发现、钩子父进程号是否稳定：都归 S1-0。
- agentd 与席位的 Secret 键历史上怎么写入。
- 所有粗估人日。

## 附录：第 1–4 轮复核意见的最终处置

每轮的原文、反例探针和逐条回应在复核目录；这里只记最终去向。

| 轮 | 项 | 最终处置 | 在哪 |
|---|---|---|---|
| 1 | M1 封闭权利；M2 保留命名空间 | 白名单 + 全模块挂点 + 记录级归属；`@` 分隔符 | §1.1–1.5 |
| 1 | M3 必填会话；M7 连接键 | 不可变三元组，每条事件全等；`(host, vendor, session, epoch)` | §1.4、§3.1 |
| 1 | M4 生命周期；S1 唯一写者 | 世代计数、状态表、`wrapper.lock`、SessionEnd 不带 `exit_code` | §2.3 |
| 1 | M5 完整输入；M6 主机身份 | 启动器 + 显式验收引用；`host-id` 文件 + `host_id_source` | §2.2、§4.3 |
| 1 | M8 分母与 SS0 | 启动器记录为分母；SS0-S 全量校准 | §8 S1-0、§9 |
| 1 | M9 混合版本；M10 授权顺序 | P-c1 / P-c2 两步；先签后做，PROD 走审批单 | §7 |
| 1 | S2、S3、S4、S6、S7 | 封闭 reason 与 `server_note`；Unlinked 无标题、证据换占位符；§4；§0；10.5 人日 | §3.1、§3.3、§4、§0、§8 |
| 1 | S5 squash 尾注 | **裁掉**：不改 squash，无尾注一律 unknown | §5、C12 |
| 2 | M1 挂点、标题范围；M5 包装器主机 | 全模块挂点，标题**裁掉**；收集员登记，逐会话绑定**裁掉** | §1.3、§2.5、C10、C11 |
| 2 | M2、M3、M4、M6 | 三元组全等；`dispatch-claude.py`；`flock` 计数 + 会话号 + 父进程号；来源 × 格式 × 模式 | §1.4、§2.2、§2.3、§8 S1-0 |
| 2 | M7 全部来源解析；S1–S7 | **裁掉**，只读现有尾注；其余已并入各节 | §5、C12 |
| 3 | M1、M2、M3 | **裁掉**（标题别名、工作号串会话、历史世代作证）；无尾注一律 unknown | C10、C11、C12、§5 |
| 3 | M4、M5、S1–S4 | SS0-S 输入格式；四类入口各验 Live / Finished / Unlinked；预检成组、状态表、CLI-only 来源、本主机线程 | §8 S1-0、§9、§1.2、§3.1、§5、§1.3 |
| 4 | M1、M4、S2 | **裁掉**（标题逐出重占、squash 世代、pending） | C10、C12、C11 |
| 4 | M2、M3、M5、S1 | 读只剩自己的记录与本主机线程；启动记录只作分母；§9 四类入口；原始厂商会话号 | §1.3、§2.2、C13、§9、§1.4 |

## 附录 E：第 5 轮复核意见的处置

| 项 | 处置 | 在哪 |
|---|---|---|
| M1 线程列表补他机标题 | 采纳（C10）：收集员的线程响应不带 `title`，不写标题；核实 `handler.go:120-127`、`view.go:73`、`:87` | §1.3、§1.5、O7 |
| M2 首个别名可被嵌套抢占 | 采纳（C11）：撤别名协议；Codex 线程 `unsupported`，逐会话绑定等 S1-0；核实 `dispatch-codex.py:158-159` | §2.5、§3.1 |
| M3 `/clear` 后漏报从分母消失 | 采纳（C13）：分母是启动器记录，演练驱动先记转换；非受管无分母列缺口 | §2.2、§9 |
| M4 amend 拼错来源元组 | 采纳（C12）：撤 `Claude-Epoch`，不改 `lineage.sh` | §5、§6 |
| M5 再次 squash 丢来源 | 采纳（C12）：撤 `Bifrost-Source`，不改 squash；squash 后的提交一律 unknown，残余写明 | §5 |
| S1 清单与附录指向撤回方案 | 采纳：§6、§7、§8、附录全部按裁定重写；`TitleOwnHost` 改 `TitleRefused` | 全文 |
| S2 记录级读负测 | 采纳：`CollectorOwnRecordsOnly`（他机工作、他机说明、MCP 登记者的工作与说明 → 403；自己的 → 200）；归属查 note 登记者与 `created_by_actor_id` | §1.3、§1.5 |
| N2 `server_note` 枚举未同步 | 采纳：枚举改为 `codex_binding_after_s1_0`、`runtime_unreadable`、`legacy_no_host` | §3.1 |

## 附录 F：第 6 轮复核意见的处置

全部采纳，无部分、无拒绝；都在现有范围内，不恢复别名、尾注或 squash 来源。

| 项 | 处置 | 在哪 |
|---|---|---|
| M1 无侧栏号时钩子与 MCP 归不到同一会话 | 核实 `sessionId.ts:14-20` 退回主机名、`thread-heartbeat.js:220-226`。启动器在没有 `CLAUDE_CODE_HOST_SESSION_ID` 时导出 `launch-<launch_id>`，钩子 `sidebar`、MCP 会话头、提交尾注同号；测试矩阵补无侧栏号、同主机两个 CLI 会话、两种先后；手起的 `claude` 仍退回主机名，是无分母入口的既有缺口 | §0 第 2 条、§2.2 第 4 步、§8 S1-2 |
| M2 收集员读不到 `registered_at` | 核实 `externalwork.go:70`、`:225-227` 回复五字段。登记回复与 `GET /external-work/{id}` 加 `registered_at`，重放与恢复不变；`CollectorRegisteredAt` | §0 第 21 条、§1.5、§3.3、§6 #3、O3 |
| S1 Codex 包装器的 `session` 含义 | `session` 按登记者定义：钩子登记是原始厂商号，包装器登记是 run key；写进 §1.4、#3、O3 | §1.4、§6、O3 |
| S2 交付判定的五态映射与回退 | 按顺序判：任一 `linked` → 已登记；没有 `linked` 时含 `unsupported`/`unknown` → 不确定；全部 `unlinked`/`refused` → 未登记（第 7 轮 S1 收口了混合候选的优先级，§5 给了固定输入的唯一预期）；查询先 `?sidebar=` 再 `?session=`（原始厂商号）；残余补侧栏号跨 `/clear` 这一层 | §5、§3.3 |
| S3 心跳自带 `title` | 核实 `thread-heartbeat.js:249-255`、`threads.go:301`。收集员心跳带 `title` → 400，客户端收集员模式不填；`CollectorTitleRefused` 加心跳路径 | §0 第 16 条、§1.3、§1.5、§4.3 |
| S4 覆盖率混用会话数与启动数 | 分成启动覆盖率（launch 为分母）与演练转换覆盖率（预记转换为分母）；生产后续 `/clear` 列未知范围 | §9 |
| N2 三处精度 | #16 键的精确说法；#21 改 `0001_core.sql:39`、`write.go:88`、`:101`；#23 改「除派活令牌外」 | §0 |
| N4 两项边界 | 收集员的线程响应整份只含本主机（`hosts[]` 一条、无全局计数）；`token()` 按用途选凭据，`progress-publish.js` 留 reporter | §1.3、§4.3 |
