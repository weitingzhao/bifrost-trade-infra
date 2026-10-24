# 统筹搬出 Owner 的电脑、Mac mini 重新分工：设计（W-31 第 4 轮 4.4）

> 状态：**第 2 稿**，设计，**不实施**。第 1 稿 `b995eef6`（10-23 23:5x CDT）经 Codex 复核 531「先改」，逐条回应在 `~/agent-work/codex-review-531/RESPONSE.md`；第 2 稿 10-24 CDT 起草。
> 依据：第 4 轮草案（Claude Doc「小牛牛包工队全面盘点 2026-10-23」第 4 轮草案页，4.4 与 D3）；Owner 10-23 23:3x「D2 A、D3 A、D4 A，其余按推荐」——D3 A = 先出设计，比较「.52 上独立账户常驻的统筹会话」和「统筹并进运行时的参谋长席位」，他看完定。
> 已签边界：`ADR-ops-architecture.md` §3、§4、§5、§7、§9、§10、§12.2、§12.3、§12.5；`RUNTIME-PLACEMENT-2026-10-11.md` §11；W-67、W-68（`WORK.md`）。
> 事实来源：mini 上的只读 SSH（10-23 23:45 CDT，不读会话正文、不读凭证文件）；本机只读命令；平台源码 `origin/main` `82b3e9d7`（本地 checkout，不代表线上版本）；厂商官方文档（第 11 节，查于 10-23）。没量过的写「未核实」并指到测量项。
> 用词：「第 4 轮 4.x」指第 4 轮的工作项；「本文 §x」指本文的节。

## 0. 一页看完

- **推荐 A1-mix**：`.52` 上建标准（非管理员）macOS 账户 `bifrost-coord`，后台图形会话里跑 Claude 桌面应用，统筹会话开 Remote Control；**它只做对话、派工和手工合入**。platform、infra 的整套测试和代码复核从第一天起交给分支 CI 和 06；只有本文 §4.6 列明的三类活在 `.52` 上本机执行，有固定到期日、由启动入口检查。长期按 §5 的退出条件并进参谋长席位（B）。
- **为什么不是 A1（全部本机）**：macOS 没有按用户的内存上限，限额卷也封不住系统卷上的全部写入（§4.5）；把重测试留在 mini 上，「带外不受影响」就只能靠事后看。证据也支持少放：本统筹会话 10-15 以来进 main 的提交 100% 在 platform（168）和 infra（414，其中代码 135）两仓，运行时已经接这两仓。
- **为什么不是直接 B**：参谋长今天只读、只交文本，只跑在 06 一台；B 要等第 4 轮 4.1（运行时自动进 main）、4.3（按应用的发版策略），再补 §5 表里的几样，开发约 11–15 天、再观察一周才能撤 A。B 还要改 ADR §12.5「参谋长跑在 mini 上」。
- **和 10-12 被否的 W-67**：避开了它最危险的那组命令（sudoers 委派、按 uid 全杀、改定时任务、管理员权限的大脚本）；没有自动解决的是同机资源、有效权限、云端撤销、回退归属，而且本机任务能接触的协调凭证比旧试点多（§3）。
- **两处现状问题**（§1.2）：两台 mini 只有管理员账户 `vision`，带外和 Claude 应用都在里面；`/Users/vision` 对 `staff` 组可读、带外的 `config` 目录 755、几份 env 文件 644——新建的标准账户默认在 `staff` 组，今天就读得到。建账户之前必须先收紧并核对有效权限。
- **要 Owner 定的**：§10 的十条，D3-1（放哪）是主问题。

## 1. 现状

### 1.1 统筹线程今天在哪、做什么

| 事 | 怎么做的 | MacBook 合盖时 |
|---|---|---|
| 跟 Owner 对话 | 桌面应用 Code 里的本地会话（侧栏 `local_accccb4e…`） | 停 |
| 派工 | 子代理、`start_session` 子会话、夜班会话 + `detach_session`；运行时的 mission / 任务经 MCP 提 | 停 |
| 复核 | `codex exec -C ~/agent-work/codex-review-<n>`（现有 476 个目录，编号到 534）；最近 120 份按 BRIEF 前 15 行粗分，约 86 份是方案 / 设计 / 规则，34 份是代码（关键词粗分，未逐份核对） | 停 |
| 合入、推 main | 手工 cherry-pick（TD-383），`push-main.sh`（在 `${TMPDIR}` 建干净验收树跑 code-health，`scripts/release/push-main.sh:525`；用 kubectl 读 CI，`:120`、`:469`）；Gitea 身份 `bifrost-mbp` | 停 |
| 发版 | `release.sh`（令牌只从环境或 infra `.env` 读 `PLATFORM_PROD_VIEWER_TOKEN` / `PLATFORM_PROD_OPERATOR_TOKEN`，`scripts/release/release.sh:62,109-114`）、MCP `start_pipeline_run`、PROD 审批单 | 停 |
| 台账、记忆 | infra `agent-config/`；记忆 `~/.claude/projects/-Users-vision-mac-trader-Desktop-stocks/memory/`（240 个文件、2.2 MB，**只在本机**） | — |
| 后台盯梢 | Monitor、后台 Bash、`caffeinate`；回合结束后机器会睡（记忆 overnight_watchers_freeze_when_mac_sleeps） | 冻住 |

- 本会话（`local_accccb4e…`）10-15 到 10-23 进 main 的提交：platform 168（夜里 22–07 点 42）、infra 414（夜里 139；除去 `agent-config` 文档 135），其余 10 个仓库 0。全工作区近 14 天 platform + infra main 提交 89.8% 来自统筹线程（含子代理）。**今天合盖等于整个项目停**。
- MCP：`.mcp.json` 9 个 server，`bifrost-approve` 钉 admin、`bifrost-local` 指本机 bdev（`AGENT_FACTS.md` MCP 表）。令牌在 `~/.config/bifrost/mcp-tokens.env`（只说位置）。
- 参谋长席位不是常驻会话：06 上 claude 执行者跑的 brief / plan 任务（`CUT-chief-of-staff-thin-2026-10-15.md`、`CUT-chief-exam-2026-10-19.md` §2）。

### 1.2 两台 mini（10-23 23:45 CDT 只读实测）

| 项 | `.50` ops-mac-agent-02（主） | `.52` ops-mac-agent-01（备） |
|---|---|---|
| 硬件 / 系统 / 开机 | M4 10 核 16 GB · macOS 26.5.1 · 72 天 | 同 |
| 内存空闲 / 数据卷空闲 | 72% / 114 GiB | 76% / 142 GiB |
| 账户 | 只有 `vision`（admin 组） | 同 |
| 带外 | `com.bifrost.operator-plane`（`vision` 的 LaunchAgent，`/Users/vision/bifrost-agent`，`*:8783`）、`com.bifrost.peer-watchdog`；告警中转只在这台 | 同（无中转） |
| 其他 | Claude.app 3.6556.2（在 `vision` 里，挡系统睡眠）；Chrome 远程桌面的 broker；`dev.orbstack.OrbStack.privhelper` 系统守护项 | 同；当时有屏幕共享连着；OrbStack.app 10-23 已停未卸 |
| 睡眠与开机 | `sleep 0`、`autorestart 1` | `sleep 0`、**`autorestart 0`**、`powernap 1` |
| 加密 / 远程 | FileVault On；SSH 开 | 同；屏幕共享开 |
| 命令行 | 无 `claude`、`codex`、`tmux`；node v22.23.0 | 同；node **v26.3.1** |
| 工作区 | `~/Desktop/stocks`，infra 停在 10-05 | 同 |
| Claude 会话痕迹（只看文件名与时间） | 项目目录 8 个文件，最近写入 10-22 21:49 | 11 个，最近 **10-23 19:51**；桌面应用有 `claude-code-sessions` 目录 |
| 权限 | `/Users/vision` `drwxr-x---+ vision:staff`（有 ACL，内容未读）；`bifrost-agent/config` 755，四份 env 文件（含两份备份）644，`env.sh` 600；`~/.kube`、`~/.claude` 755 | 同；三份 env 文件 644 |

出入：ADR §3 写宿主是「独立系统账户」；`AGENT_FACTS.md` L-1 表还列着 8781、8782、9119（已不在跑）；`check_hardcoded_paths.py` 基线剩下的 16 处都是 mini 的 `/Users/vision` 路径。

### 1.3 现有的失联通知（只读源码）

- **peer watchdog**（`bifrost-platform/scripts/agent/peer_watchdog.sh:94-119`）：对端 `/health` 失败就经 SSH 重启对端的 operator-plane，写 `STILL DOWN` 日志，**不发通知**；ntfy 那一支（`:15-20`、`:45-85`）只用于备机观察 `.50` 的告警中转。所以 `.52` 掉线今天不会呼 Owner。
- **线程心跳**（`agentthreads/threads.go:1-60`）：会话在回合中途静默 max(10 分钟, 声明的工具时限 + 2 分钟) 就经中转呼 Owner；回合之间不判。`/agent/threads/heartbeat` 不在 10-28 要删的两条路由里（要删的是 `/agent/progress`、`/agent/hosts/heartbeat`，`PLAN-T24-stg-2026-10-21.md` §2）；上报令牌是共用的一把，`host` 字段不绑主体。
- **agentrt 在线状态**（3.5，`controller/presence.go`）：只判轮询领活的 agentd 主机，30 秒判离线，告诉 Owner 的地方是 Chief 页，不推手机。统筹不是 agentd 主机。
- W-68 B4 ①（06、NAS、mini 的主机监控与 HostDown）在第 4 轮 4.9 里做，还没上线。

### 1.4 厂商能力（官方文档，查于 2026-10-23；行为照文档接受，依赖它的地方都列了测量）

| 能力 | 文档怎么说 | 本设计怎么用 · 测量 |
|---|---|---|
| Remote Control | 会话在本机跑，claude.ai/code 和手机 App 是窗口；只出站；Pro 起可用、不支持 API key；交互会话断网一直重试，server 模式约 10 分钟退出；连着时对话记录存 Anthropic 服务器；可推送（「Push when Claude decides」「Push when actions required」）；Pro / Max 可开「Require trusted devices」 | A 的对话入口 · M1、M9–M12 |
| 桌面应用 SSH 会话 | 合盖后任务继续直到做完、要人或到限；登录凭证只在桌面应用开着且连着时续期，过期就停；通宵要开盖、应用开着，否则用云端会话 | **因不能保证无人值守一夜而排除**（没测当前凭证的剩余寿命，不需要测） |
| 云端会话 | 跑在云上，从 GitHub 克隆 | 到不了局域网，不用 |
| Channels（研究预览） | MCP server 把事件推进开着的会话 | 本轮不用 |
| ChatGPT 当主机 | 「Control this Mac or PC」配对；主机要醒着、联网、同一账户登录，可开「Keep this Mac awake」；可以是专用常开的 Mac；远程任务用主机的 MCP 和本机工具 | 太太的桥，§6.1 · I1–I5 |

## 2. 方案

- **A1-mix（推荐）**：`.52` 的 `bifrost-coord` 账户，后台图形会话跑 Claude 桌面应用，统筹会话开 Remote Control。统筹只做对话、派工、手工合入、台账；整套测试走分支 CI（第 3 轮 3.4 ② 已做）和 06 的验证任务，代码复核走运行时的评审岗；本机执行只限 §4.6 的三类例外。
- **A1**：同一账户和形态，但统筹照今天的做法在本机跑整套测试和全部 Codex 复核。
- **A2（候选，未成形）**：同一账户，无图形登录，LaunchDaemon 拉起 `tmux` 里的交互式 `claude --remote-control`。只在 M2 / M3（后台图形会话、钥匙串）失败时考虑；它修不了 Remote Control 本身的问题（M1、M9）。要单独写清进程树、谁监督、Claude 退出怎么识别、会话怎么续、写操作怎么去重，再测停进程、断网、重启（M6）。
- **B**：统筹并进参谋长席位，没有常驻会话；见 §5。
- **C（过渡）**：统筹留在 MacBook，当天给它开 Remote Control；手机能说话，合盖照停。不作为方案推荐。

### 2.1 逐项比较

| 项 | A1-mix | A1 | A2 | B | C |
|---|---|---|---|---|---|
| 装什么 | 标准账户；Claude 应用（已在 `/Applications`）；限额 APFS 卷；`bootstrap.sh`；Codex（只为例外第 1 类） | 同 A1-mix，Codex 常驻 | 同，加 `tmux`、一份 LaunchDaemon（管理员装） | 平台、agentd 加能力 | 无 |
| 凭证 | §4.2 收口表；不放 admin、不发 `agent_reader` | 同，Codex 常驻 | 同；Claude 登录方式未定 | 都在 06 和平台 | 不变（含 admin） |
| 隔离 | macOS 用户隔离 + 收紧 `vision`；本机重活很少 | 同，本机重活多、无内存上限 | 同 A1-mix | 06 的沙箱，席位只读 | 不变 |
| Owner 怎么说话 | 桌面应用或 claude.ai/code 里的 RC 会话；手机 App；在外不用 VPN；兜底屏幕共享 | 同 | 同，少屏幕共享兜底 | Console Chief 页；在外要 VPN；推送要等 W-52 | 同 A，合盖即断 |
| 夜里 | `.52` 不睡；值守循环（§4.4） | 同 | 同 | 06 不睡 | 停 |
| 断电 | 自动开机（`.52` 要改）→ FileVault 经 SSH 解锁 → Owner 屏幕共享登录 `bifrost-coord` → 续会话 | 同 | 解锁后自起 | 06 自起 | — |
| 失联通知 | 线程静默呼叫（现有）+ B4 ① 主机监控（S4 门槛） | 同 | 同 | 06 掉线时参谋长也掉，平台告知在 Chief 页 | 线程静默照旧 |
| 与带外的边界 | 不同 uid；无 `vision@` 钥匙；本机例外任务与协调凭证同 uid（§3） | 同，同 uid 的执行更多 | 同 A1-mix | 不碰 mini | — |
| 磁盘 | 限额卷 80 GiB 收 `agent-work`、TMPDIR、构建缓存；系统卷上的会话记录与应用缓存只靠下限守 | 同，压力大 | 同 | 06 | 本机 |
| 成本 | 无新硬件和订阅（共用 Owner 的账户与额度，争用未测）；施工约 4 天 + 两夜观察；Owner 约 2 小时、分 4 次 | 施工约 3.5 天；资源验收更难过 | 再加约 1–2 天 | 开发 11–15 天 + 观察一周 | 0 |
| 回退 | §8 两级：停用回 MacBook / 最终销毁 | 同 | 同 | 恢复常驻会话 | 关 RC |
| 验收 | 待 M1–M3、M9–M12 | 同，另加资源验收 | 待 M6 | 合盖满足；手机要推送和 VPN | 只满足手机 |

## 3. 和 10-12 被否的方案（W-67）比

10-12 的设计（`DESIGN-host-minimal-2026-10-12.md`）把 mini 当 Agent 执行主机：守护进程账户 + 槽位账户、sudoers 委派、`kill -TERM -1` 按 uid 清理、禁槽位的定时任务；量测要在 mini 上建测试账户、跑 1,003 行管理员脚本。复核 122 点出 34 条危险命令和 10 处清不掉的残留，并反对把没测过的权限、可写面、云端会话撤销和资源控制说成已成立，要求改系统的试验先在可丢弃的环境做（`reviews/codex-2026-10-12-review122-w67-measurement-material.md`；`LESSONS-from-practice.md` 第 110 条）。

| | W-67（否） | A1-mix |
|---|---|---|
| 跑什么 | 一池用完即弃的执行任务 | 一个长驻统筹会话；执行者在 06；本机只有 §4.6 三类 |
| 改系统 | 两个账户、sudoers、开机守护进程、禁定时任务、按账户发信号 | 一个标准账户；`vision` 家目录 700 并核对 ACL；一个限额卷；`autorestart 1`；卸 OrbStack。无 sudoers、无跨账户信号 |
| 在 mini 上做的试验 | 管理员脚本 | 带外一侧只读清单；资源压力先在 MacBook 测，再在 `.52` 做有上限的代表负载；会改东西的测试只在 `bifrost-coord` 自己的文件里 |
| 本机任务能碰的凭证 | 槽位读不到守护进程的 reporter 令牌和钥匙，也没有 operator、kubeconfig（`DESIGN-host-minimal:110-115`） | **更多**：例外任务、子代理、Codex 和持有 PROD operator、Gitea main 令牌的统筹同一个 uid。600 隔不开同 uid，Codex 的只读沙箱也不禁止读文件 |
| 还没成立、要量的 | — | 有效权限（ACL、可写依赖、套接字、特权 helper）、资源隔离、云端会话与设备的撤销、回退的归属（§11） |

**剩下的风险和控制**：

1. **碰带外**：家目录 700、无 sudo、无 `vision@` 钥匙；S0a 列出带外依赖的全部路径并核对有效权限（V3）；preflight 在 `BIFROST_HOST_ROLE=coordinator` 时拒绝 `ssh vision@`、写 `/Users/vision`（文本拦截，防误用不防绕过）。
2. **资源**：见 §4.5；A1-mix 的意义就是不把重活放在没有内存上限的机器上。
3. **同 uid 的执行碰到协调凭证**：例外只放三类我们自己仓库里的活；是否把它们当可信、接受它们读得到令牌，是 D3-8。
4. **令牌外泄面**：比今天小——今天 MacBook 同一用户还有 admin 令牌（ADR §5 已接受的风险），`.52` 不放 admin、不启用 `bifrost-approve`；审批只在 Console 和手机。受信设备防别人用 Owner 的 claude.ai 账号操纵会话，但不替代主机内的凭证隔离。
5. **网络**：统筹在运维区（ADR §10），和今天的 MacBook 相同；按用户的出站规则以后再说。
6. **一机两角色**：`.52` 是带外备机；带外主机 `.50` 保持干净；`.52` 坏了，带外有 `.50`，统筹回 MacBook（§8）。

## 4. 方案 A1-mix 的细节

### 4.1 账户与文件布局（`.52`）

| 账户 | 类型 | 放什么 |
|---|---|---|
| `vision` | 管理员；控制台；Owner 用 | 带外（备）、看门狗；家目录 700；Claude 会话按 S0a 清单交接后才退出 |
| `bifrost-coord` | 标准；后台图形会话 | 工作区 `/Users/bifrost-coord/stocks`（不放 Desktop，launchd 起的进程读 Desktop 会 EPERM，记忆 vite_eperm_desktop_privacy）；`~/agent-work` 链到限额卷 `/Volumes/coord-work`；`~/.config/bifrost/` 目录 700、里面的文件 600 |

钩子用 `$CLAUDE_PROJECT_DIR`，路径换了不受影响；用户级 `~/.claude/CLAUDE.md`、`settings.json` 由 §6.3 的脚本生成。

### 4.2 凭证（按职责收口）

| 凭证 | 用途 · 是否过渡 | 怎么发、生效 | 怎么撤、怎么验证旧的被拒 |
|---|---|---|---|
| Claude 登录（Owner 本人） | 统筹会话、RC。必需。和 MacBook、06 共用一个账户和额度，不是新增容量 | Owner 在后台会话里登录一次 | claude.ai 设备列表里移除该设备、受信设备撤销（M12） |
| PROD operator，主体名 `coordinator-52` | 提任务、申请动作、发 STG（经 PROD 控制面）。宽角色，不是「只给协调」的权限 | 平台的令牌从鉴权配置和环境加载、启动时建表（`actuation/auth.go:147-202`、`server/server.go:117`）：在 PROD 鉴权 Secret 加一项（D 级，Owner），重启 platform-api；用 MCP `whoami` 核对主体名和角色 | 删这一项、重启；用旧令牌文件打一个需要 viewer 的读接口，只看状态码应为 401；MacBook 那把仍 200 |
| PROD viewer | 观测 | 同上（可与 operator 同批） | 同上 |
| STG operator | 只为调试 STG 运行时；STG 发版仍经 PROD | D3-4 定发不发 | 同上（STG 鉴权） |
| reporter | 线程心跳与标题（§4.4 的失联通知靠它）。每台一把便于单独撤，但心跳的 `host` 不绑主体（`agentthreads/threads.go:46-52`），不算每台身份 | 同上 | 同上 |
| `release.env`（只两键 `PLATFORM_PROD_VIEWER_TOKEN`、`PLATFORM_PROD_OPERATOR_TOKEN`，600） | `release.sh`、`push-main.sh` 的窗口查询。值和上两行同一把；**不拷 infra `.env`** | `settings.json` 的 `env` 设 `ENV_FILE`（`release.sh` 已支持，`:62`） | 随 operator 一起撤 |
| 只读 kubeconfig `bifrost-agent` | `push-main.sh` 用 kubectl 读 CI。**过渡**：push-main 改走平台查询、或第 4 轮 4.1 让运行时合入之后撤 | Owner 拷一份 | 删文件；平台侧不用动（同一身份 MacBook 也在用） |
| Gitea `bifrost-coord-52`（非管理员）令牌 | 推分支；推 platform、infra 的 main（白名单）。**过渡**：4.1 上 PROD、运行时自合一周后，撤出 main 白名单只留分支。infra 的 main 会触发自动同步，不是低影响凭证 | 照 `bifrost-mbp`（`CUT-gitea-primary` 9.4）：Owner 建账号、只加这两个仓库的写权限和 main 白名单、令牌进钥匙串 | Gitea 删令牌；`git ls-remote` 用旧凭证只看状态应失败 |
| Codex 登录 | 只为 §4.6 第 1 类；**随该类退出** | Owner 登录一次 | `codex logout`，并在 OpenAI 账户页移除设备 |
| `agent_reader` | **默认不发**；出现 MCP 做不了的具体查询再定 | — | — |

**不放**：admin 令牌；`bifrost-local`、`bifrost-approve`（§6.3 用用户级设置禁用并验证）；`~/.bifrost-owner*`；管理员 kubeconfig；任何 `.env`；到 `vision@.50/.52`、节点、NAS 的 SSH 钥匙；带外的 ntfy topic 和中转令牌；TWS / IB 的任何东西。mini 的事实改从第 4 轮 4.9（W-68 B4 ①）的监控读。

**问题全文**：`issue_readers` 认的是令牌名字（默认 `operator`、`admin`，`auth.go:115-127,225-228`），新主体 `coordinator-52` 不在名单上就读不到业务问题全文。加不加是 D3-5。

### 4.3 会话形态与对话入口

- 统筹会话在工作区根起；只给它本身开 Remote Control（不开「新会话自动连」，免得子会话刷满手机列表）。
- **MacBook**：按文档，RC 会话能在 claude.ai、手机 App 和桌面应用里看和操作；侧栏里怎么显示待 M1。最稳的是浏览器开 claude.ai/code。
- **手机**：Claude App → Code → 这条会话；`/config` 打开两种推送。在外用蜂窝网可以（RC 只走 Anthropic API）；Console 仍要 UniFi VPN。
- **权限弹窗**：统筹照旧跑 auto mode（Owner 在 `bifrost-coord` 里跑一次 `apply-auto-mode.sh`）；剩下的弹窗经「Push when actions required」到手机；统筹起的子会话要人时能否到手机待 M9。审批单仍只在 Console（ADR §5）。
- **留存**：RC 连着时对话记录存在 Anthropic 服务器，统筹读过的问题原文也在里面（D3-6）。

### 4.4 值守循环与失联通知（探测 → 判定 → 送达）

**问题**：统筹正常结束回合后没有任何东西再叫醒它，也没有东西判「该做却没做」；线程心跳只判回合中途的静默。所以无人在场时，统筹不结束回合：

- **值守循环**：在 Owner 不在场时（`bifrost-coord` 的 Stop 钩子判定：这是常驻统筹会话，且最近 20 分钟没有 Owner 的消息），钩子拒绝结束回合，要求统筹进入循环：`wait_for_messages(timeout_seconds=120)` → 查自己派出的任务和 mission → 推进 → 再等。单个阻塞工具不超过 10 分钟（Bash、Monitor 都按这个上限）。钩子是程序，不靠模型记着（ADR §12.2 第 13 条）；钩子在桌面应用的会话里能否这样用待 M13，不行就退到 `/loop 20m`，并记为较弱的一档。
- **探测与判定**：每次工具调用都经线程心跳钩子报到 PROD（`claude/settings.json` 的 PreToolUse / PostToolUse）；PROD 的 `agentthreads` 在回合中途静默 10 分钟时判定（现有，不加路由）。循环里每 2 分钟至少一次工具调用，所以「Claude 退出」「应用崩溃」「`.52` 断电或断网」都表现为回合中途静默。
- **送达**：PROD workers 经 `.50` 的告警中转发 ntfy 到手机（现有路径，`threads.go` 头注释；中转在 `.50`）。时限：约 10–11 分钟。
- **第二个独立观察者**：第 4 轮 4.9 的 B4 ①（集群 Prometheus 探 `.52`，HostDown → Alertmanager → 中转 → ntfy）。**S4 的门槛**：B4 ① 已上 PROD，且「`.52` 断网」演练在手机上收到。
- **剩下的洞**：`.50` 和中转一起挂时只剩 `.52` 的看门狗观察中转（现有）；整屋断电时都停。上报令牌共用，持有者能伪造心跳（现有的已知边界）。
- **维护者登记前移**：统筹会话按 ADR §7 在 S2 登记进 `MAINTAINERS.yaml`（维护什么、在哪、最高动作级、靠哪条告警发现它坏了），不放到 S5。

### 4.5 资源：磁盘、内存、带外的余量（待证明，不是已成立）

| 写入位置 | 放哪 | 怎么守 |
|---|---|---|
| worktree、复核目录、`push-main.sh` 的验收树（`${TMPDIR}`）、`go`/`npm` 缓存、例外任务的日志 | 限额卷 `coord-work`（APFS 配额 80 GiB）：`settings.json` 的 `env` 设 `TMPDIR`、`GOCACHE`、`GOMODCACHE`、`npm_config_cache` | 配额封顶；卷不在或 UUID 不对，例外入口拒绝启动 |
| Claude / Codex 的会话记录、应用缓存（`~/.claude`、`~/Library`） | 系统卷（MacBook 上这类累计约 2.7 GB） | **封不住**：入口检查系统卷余量 ≥ 40 GiB，低于就拒绝新的例外任务并经线程告诉 Owner；能否用 `CLAUDE_CONFIG_DIR` 挪到限额卷待 M14 |
| 内存 | — | **macOS 没有按用户的内存上限**。所以 A1-mix 不在 `.52` 跑整套测试；例外任务一次一件，`GOMAXPROCS=4`、`go test -p 2`；运行中每 10 秒采样，空闲内存低于 20% 或带外 `/health` 连续 3 次超过 2 秒，入口停掉这件任务（只停自己账户里它的进程组）并记录 |

**通过阈值**（V3）：带外 `/health`（两台 `:8783`）在代表负载期间 p95 < 500 ms、无失败；空闲内存 ≥ 30%；系统卷余量 ≥ 40 GiB。**怎么验**：代表负载（一次 `push-main.sh` 的扫描、一份设计复核、一次第 3 类的 `go build` 加单包测试）先在 MacBook 上量峰值内存、写盘量和用时，再在 `.52` 上跑一次，期间每 10 秒采样带外延迟；任何一项不过就停，不放例外。第 4 轮 4.6（分支、工作目录、磁盘的生命周期）的规则同样装在 `.52`。

### 4.6 本机执行的例外（ADR §3「执行面不放 mini」的有期限偏离）

| 项 | 内容 |
|---|---|
| 负责人 | 统筹席位的现任者（今天是这个统筹线程）；Owner 签名、续期 |
| 到期日 | **2026-11-07 00:00 CDT**（固定日期；先到期或下面的迁移条件先满足，先发生者为准） |
| 仓库 | 只 platform、infra |
| 第 1 类：设计 / 方案 / 规则文档的复核 | `codex exec` 只读沙箱，不构建、不跑测试；一次一件。**撤掉条件**：运行时能派「复核某提交里的某份文档」的任务，并有一件在 PROD accepted（M15） |
| 第 2 类：手工合入 | `push-main.sh`（code-health 扫描 + kubectl 读 CI）。**撤掉条件**：第 4 轮 4.1 上 PROD（写明 platform 版本），且运行时一周内自己合入过 ≥ 1 件 |
| 第 3 类：Claude 写核心代码时的本机检查 | 子代理改代码后的 `go build`、`go vet`、单个包的 `go test -run`；整套交给分支 CI 和 06。**撤掉条件**：06 上的 Claude 执行者能写文件（TD-371）且一件核心任务在 PROD accepted |
| 不在例外里 | 整套测试、`npm ci`、代码复核（走运行时评审岗；运行时若接不了「不是它产出的分支」的复核，代码复核暂归第 1 类，M15）、其他仓库、长驻服务 |
| 并发与资源 | 例外任务同时 1 件（另加 `push-main.sh`）；§4.5 的检查与中止 |
| 入口检查 | 包装命令 `coord-exec <类别> -- <命令>`：读 Owner 签名的例外记录（`ssh-keygen -Y verify`，用平台已钉的规则签名公钥，另用一个命名空间），核对到期日、类别、仓库、卷和余量；读不到、验不过、过期一律拒绝。preflight 在 `BIFROST_HOST_ROLE=coordinator` 时拒绝不经包装的 `codex exec`、`go test`、`npm test|ci`、`make test`、`pytest`；子代理和子会话走同一套钩子 |
| 续期 | 只有 Owner 重新签名；统筹不能把「依赖还没做完」当续期理由 |
| 剩下的洞 | 统筹能改 infra 里的包装和 preflight（和所有 preflight 一样防误用不防绕过）；要硬约束就把例外做成平台规则种类（规则词表是闭合的，要改平台），见 D3-2 |

## 5. 方案 B：参谋长要补什么

**现在能做的**（`CUT-chief-of-staff-thin`、`PLAN-round2-2.4` ④、`CUT-chief-exam` §2、`CUT-online-status` §1.1）：06 上的 claude 执行者，空 MCP、只给 Read / Grep / Glob、只交文本；给目标 → 规划任务落成 mission、任务、决策卡、决定记录；信箱 / Chief 对话 → brief，答案回 Chief 页（前文最近 10 条）；定时简报 8:00、21:00 和卡住提醒；`POLICY_ALERT` / `CANNOT`。**06 掉线时参谋长也掉线**。

| 统筹的活 | 参谋长现在 | 要补的 | 依赖 |
|---|---|---|---|
| 派工 | 规划拆任务、控制器路由 | 返工或卡住后重新规划；跨 mission 排队；多产品 | 第 4 轮 4.2 |
| 复核 | 评审岗管代码任务 | 文档复核任务；停线轮次进控制器 | — |
| 合入 | 不能 | 运行时自动进 main | **4.1** |
| 发版 | 不能 | STG 合入后自动发；PROD 按每个应用的策略，健康检查不过自动回滚 | 4.1、**4.3**（W-56） |
| 跟 Owner 对话 | Chief 页一问一答，分钟级，不推手机 | 推送；回答时延目标；运行时里的长期记忆；把回答变成计划变更或规则提议的结构化出口 | W-52 |
| 台账与记忆 | 不能写 | 台账改运行时数据，或由 infra 的实现任务写 | 4.2 |
| 看现场 | 只看快照 | 快照加事实层摘要；统筹动作进运行时 | 4.5 |
| 上岗 | 考试只差判分误判 | 新能力进考卷 | 4.8 |
| 后备 | 只在 06 | 第二台能跑席位的主机，或 B5 | W-68 |

**B 改的已签规则**：ADR §12.5 写参谋长「24 小时在线，跑在 mini 上」，`RUNTIME-PLACEMENT` §11 写「mini 管带外和参谋长」。选 B（或 A 达到退出条件后撤 `.52`），席位就只在 06 上：代价是 06 一台掉线时没有对话以外的协调者（对话入口在 Console，消息排队；告知在平台）。若 Owner 仍要一个不依赖 06 的协调入口，就要另定它放哪——这一条跟 D3-1 一起定。

**粗估**：4.1（3–4 天）、4.3（实现 3–4 天）之后再补上表 5–7 天，合计约 11–15 天开发；撤 A 还要满足下面三条并观察一周。**退出条件**：① 一周里进 main 的代码提交一半以上由运行时自己做完并合入；② 参谋长带新能力通过资格考试；③ 连续一周 Owner 90% 以上的对话在 Chief 页完成。撤之前还要把依赖会话上下文的待办和决定、记忆（§6.4）迁成运行时里可恢复的记录——RC 只是窗口，不会替我们迁。

## 6. 一起回答的问题

### 6.1 太太的接业务桥能不能放 mini

现状（`DESIGN-crew-intake-2026-10-22.md` 第六节、V1–V3）：桥是只注册 7 个接业务工具的 stdio MCP；她的桌面应用能挂本机 MCP；Dot 的定时可能在云端跑，连不到她 Mac 上的桥；她的 Mac 连得到平台。Owner 不方便登录她的 Mac Air，它也可能关机。

- **能，有条件**：`.52` 上另建标准账户 `bifrost-p2`，后台图形会话跑 ChatGPT 桌面应用、登录她的账户（两步验证在她手机上），只装桥和 intake 令牌；Codex 配置 read-only。**不放 `.50`**。
- **风险**：外部厂商驱动的 Agent 在运维区的机器上有命令执行能力；账户里只有桥和令牌，网络上靠凭证收口。D 级放宽（D3-10）。
- **要量**（在她的 Dot 里问或试）：I1 Dot 的定时 / 云端任务能否调用「连接的电脑」上的 MCP；I2 主机上的 MCP 调用要不要逐次允许；I3 她的 Mac Air 和 mini 同时连着时任务落在哪台；I4 从 `bifrost-p2` 不带令牌能到哪些局域网接口（只看状态码）；I5 `bifrost-p2` 和 `bifrost-coord` 同时后台登录、屏幕共享断开后两边都照跑。
- **推荐**：先按原设计放她的 Mac Air 做切片 4；I1、I5 都过再搬。它是独立的可选事项，不计入 A1-mix 的能力。

### 6.2 06 坏了，mini 能不能临时接活（W-68 B5）

**不推荐 mini 当 agentd 后备**：agentd 的约束靠 Linux（systemd、按用户 nftables、Landlock、AppArmor，`scripts/agent-host/`），macOS 上没有，岗位的边界类要求做不到；ADR §3 也不放。06 坏了时：运行时的任务留在队列，Console 30 秒判离线（3.5）；`.52` 的统筹照常对话、规划，例外内的小活照做。B5 的三条路仍由 Owner 在 W-68 定。

### 6.3 工作区一条脚本拉起（ADR §12.9 第 1 条），含统筹专用配置

infra `scripts/workspace/bootstrap.sh` + `agent-config/workspace.yaml`（12 个仓库、根目录链接、工具链版本、要装的命令行、Owner 要放的文件清单——只写路径和权限）。

- `apply`（幂等，不用 sudo）：克隆或快进仓库 → 建根目录链接（照 `agent-config/README.md` 第 45–85 行）→ `sh scripts/git-hooks/install.sh` → 装 MCP 依赖 → 生成用户级 `CLAUDE.md`、`settings.json`。**统筹专用的部分**（按 `--role coordinator`）：`settings.json` 写 `disabledMcpjsonServers: ["bifrost-local", "bifrost-approve"]`、`env`（`BIFROST_HOST_ROLE`、`ENV_FILE`、`TMPDIR`、缓存目录、`KUBECONFIG`）、Stop 钩子（§4.4）；Codex 的 `~/.codex/config.toml`（沙箱、审批、两个受信任目录换成新路径、每条钩子的 `trusted_hash`）、`hooks.json`、`AGENTS.md`（`codex/README.md`）。
- `check`（只读，逐项 PASS / 缺；带阳性对照）：实际加载的 MCP 清单里没有那两个、`whoami` 的主体名和角色、Bash 工具里看得到的环境变量**名字**、`release.sh window` 只读查询成功（不是鉴权错）、preflight 阳性（临时仓库里 `git add -A` 被拦）和阴性、`check-codex-guard.py --probe` 加一个阴性探针、限额卷 UUID 与余量。`check` 全 PASS 才进 S3。
- 新节点测试 = 在 `bifrost-coord` 里从零 `apply` 再 `check`；MacBook 上 `check`（默认角色）应全 PASS。

### 6.4 记忆和状态怎么离机

`.52` 上只此一份的东西：记忆、交接文件、没推的分支、复核报告。

- **推荐**：私有 Gitea 仓库 `bifrost-coord-state`（Owner 建，只给 `bifrost-coord-52` 写、MacBook 读）。`bifrost-coord` 里一个 LaunchAgent 每小时提交并推送记忆、交接文件（在途清单、等待项、最近决定）和复核报告；没推的分支每小时推到 Gitea 的 `coord/wip/*`。可接受的丢失窗口 1 小时。MacBook 上开会话前拉一次只读副本。
- 没选的：NAS（要给统筹 NAS 写凭证）；MacBook 定时拉（MacBook 夜里睡，窗口可能是一整夜）；直接进运行时（B 时代）。

## 7. mini 的新分工

| 机器 · 账户 | 跑什么 | 凭证 | 不跑 |
|---|---|---|---|
| `.50` · `vision`（管理员） | 带外（主）、告警中转、看门狗 | 带外自己的配置 | 任何 Agent、统筹、外部厂商 App；Claude.app 交接后退出 |
| `.50` · `bifrost-exec`（以后，W-50 搁置） | 带外执行器 | 专用受限 kube 身份 | 同上 |
| `.52` · `vision`（管理员） | 带外（备）、看门狗 | 同上 | Claude.app 交接后退出；OrbStack 卸载 |
| `.52` · `bifrost-coord`（标准） | 统筹会话（桌面应用 + RC）、子会话与子代理、§4.6 例外、状态同步 | §4.2 | agentd、bdev、admin 令牌、带外的任何东西 |
| `.52` · `bifrost-p2`（标准，**有条件**） | ChatGPT 桌面应用（太太的账户）、接业务桥 | intake 令牌 | 其他一切 |
| 06 | 不变：PROD、STG 两个 agentd；加上本来在 MacBook 跑的测试和代码复核 | 不变 | — |
| MacBook | 开发、驾驶舱；切换后统筹线程归档，回退时重开 | 不变 | 任何被夜里依赖的东西 |

## 8. 切片、验收与回退

| 片 | 做什么 | 动作性质 | 谁 · 多久 |
|---|---|---|---|
| S0a 建账户之前 | ① 两台 mini `vision` 里 Claude 会话的清单：只取会话标识、属主、最后活动时间、进程状态、用途（不读正文），由相关线程或 Owner 确认归属；未知的记「未完成交接」。② 带外依赖的路径、执行文件、配置、LaunchAgent、有效 ACL（`ls -le`）、特权 helper 的只读清单。③ 带外健康基线（两台 `:8783`、看门狗日志、中转发一条测试——**这一步会发通知**）。④ MacBook 上量代表负载 | ①② 只读；③ 发一条测试通知；④ 只在 MacBook | 统筹方 · 半天 |
| S1 写 | `bootstrap.sh`（含 `--role coordinator`、`check`）；`coord-exec` 包装与 preflight 的角色规则；Stop 钩子；状态同步 LaunchAgent；全部带测试与阳性对照 | 只写仓库 | 统筹方写、Codex 复核 · 1.5 天 |
| S2 `.52` 准备 | Owner：家目录 700（两台）、核对 ACL、`autorestart 1`、卸 OrbStack；建 `bifrost-coord`、限额卷（记下 UID、GeneratedUID、卷 UUID 进创建清单）；后台登录并登录 Claude、Codex；开推送、受信设备；放令牌（D 级单）、kubeconfig；建 Gitea 账号和 `bifrost-coord-state`；跑 `apply-auto-mode.sh`。统筹方：`apply`、`check`；登记维护者 | Owner 改系统；统筹方只在新账户里 | Owner 约 1.5 小时分 3 次；统筹方半天 |
| S0b 建账户之后 | M1–M3、M9–M15；`.52` 上的代表负载（§4.5） | 在 `bifrost-coord` 里；负载有中止条件 | 统筹方 · 半天 |
| S3 演练 | `.52` 起统筹会话，MacBook 统筹不动：派一件 06 的验证任务、一份第 1 类复核、`push-main.sh` 推一次 infra、STG 发一次；Owner 从手机说一句话；V4 的第一半 | 真活 | 半天 |
| S4 切换与两夜 | 门槛：B4 ① 已上 PROD 并演练过；`check` 全 PASS。MacBook 统筹写交接、推分支、同步记忆；`.52` 接手；MacBook 统筹线程归档。第一夜 V1；第二夜（或第一夜后半段）V1 的负对照 | — | 两夜；Owner 合盖、早上看 |
| S5 收尾 | S0a 清单上已交接的会话关掉后，两台 `vision` 退出 Claude.app 并取消自启；ADR、`AGENT_FACTS.md`、`.mcp.json.README.md`、硬编码路径基线；V4 的第二半 | — | 统筹方半天；Owner 退出 App |

**验收**：

- **V1 合盖一夜（有因果的任务链）**：22:00 前 MacBook 合盖到 07:00 后（MacBook `pmset -g log` 为证）。统筹在 22:00 前预先登记一条链：T1（06 上的实现或验证任务，预计 01:00 前结束）→ T1 结束后由 `.52` 统筹看结果并派 T2（另一家复核）→ T2 收下后统筹合入（`push-main.sh`）并起 STG 发布 T3。过：T2 的创建时间晚于 T1 结束、早于 07:00，创建者是 `.52` 统筹会话（`Claude-Session` 尾注 / 运行时 actor），T3 在 T2 收下之后；每步记任务号、会话号、主机、时间。只计这条链，不计其他提交或运行时自己发生的事件。
- **V1 负对照**：主机照常报活时，在值守循环中退出 Claude 应用（统筹方远程做，或 Owner 做）。过：11 分钟内手机收到「会话静默」；早上的交接写明这段中断。另做一次 `.52` 断网 15 分钟：线程静默和 B4 ① 两路都送到手机。
- **V2 手机说一句话**：Owner 在家外（蜂窝网）用 Claude App 对统筹说一句话。过：值守循环中 5 分钟内回答；在跑别的工具时 15 分钟内回答；超过 15 分钟算不过。另做一次：手机上答一个真实的权限请求（允许和拒绝各一次），统筹起的子会话的请求也能到手机（M9）。
- **V3 带外不受影响**：S0a、S0b 代表负载期间、S4 后三次健康基线达 §4.5 的阈值。在 `bifrost-coord` 里对 S0a 清单上每个路径核对有效读、写、遍历都被拒（不读内容）；`id` 不含 admin、`/etc/sudoers.d` 里没有指名它的文件（只看文件名）；对 operator-plane 先 `ps -p <pid> -o user=` 确认进程存在，再 `kill -0` 必须是「Operation not permitted」，「No such process」或其他错误算没测成。未知不算过。
- **V4 回退（两半）**：S3 时演练「停用回 MacBook」；S5 时演练「接管后 `.52` 不可读」：先在 `.52` 上产生新状态（一条记忆、一个没推的分支），等一次同步，然后不再访问 `.52`，MacBook 上新开统筹只凭 Gitea（`bifrost-coord-state`、`coord/wip/*`）和仓库，30 分钟内恢复并说清在途。恢复不了就不做最终销毁。

**回退分两级**：

- **R1 停用回 MacBook**（可逆）：`.52` 统筹先写交接、触发一次同步并核对 MacBook 能读到；MacBook 在工作区根开新统筹线程；`.52` 会话归档、退出应用；撤 Gitea main 白名单、Codex 设备。令牌先不删（留着排查），会话停用即可。
- **R2 最终销毁**（不可逆，Owner 做）：R1 之后至少 7 天、核对过离机副本完整；Owner 先把 `bifrost-coord` 家目录和限额卷导出一份加密归档放 NAS（留 30 天，取证用）；再按 S2 的创建清单（账户名 + UID + GeneratedUID、卷 UUID、Gitea 账号号、令牌主体名）逐项删除——对不上清单的不删；作废令牌并按 §4.2 验证旧的被拒。`vision` 家目录 700 和 `autorestart 1` 保留。

## 9. 推荐与理由

**A1-mix 现在做；B 作为终点，按 §5 的退出条件并入；M2 / M3 不过时 A2 另出设计；C 可以当天开（只为手机能说话）。**

1. 只有 A 能在第 4 轮第一波里满足 4.4 的两条验收；统筹不搬，第 4 轮其余各项（包括 4.1）夜里照样停。
2. A1-mix 比 A1 少放：重测试本来就能交给分支 CI 和 06（本会话的提交全在运行时已接的两仓），macOS 上又没有按用户的内存上限，把重活留在 06 比在 `.52` 上设计资源控制更可靠；例外三类各有撤掉条件和到期日。
3. 工作方式和今天一样（桌面应用、子会话、夜班、子代理），换的是机器；agentd 留在 06，mini 上的本机测试和复核只按 §4.6 列明的临时例外执行；不改带外的配置，修掉 `vision` 账户里的 Claude 和 `staff` 组可读两处现状问题，并把 admin 令牌从 Agent 所在的机器拿掉。
4. 状态放我们的（ADR §12.2 第 7 条）：RC 只是窗口；状态在仓库、运行时和 `bifrost-coord-state`。B 接手时仍要把会话里的待办和决定迁成记录（§5）。

## 10. 待 Owner 定

| # | 事 | 选项 | 建议 | 在哪办 · 怎么回 |
|---|---|---|---|---|
| D3-1 | 统筹放哪 | A1-mix / A1 / A2 / B / 先开 C | **A1-mix**；B 作终点（会改 ADR §12.5，§5）；C 当天可开 | 统筹线程回「D3-1 A1-mix」 |
| D3-2 | ADR §3 mini 行加 `.52` 的 `bifrost-coord`（参谋长过渡形态）；§4.6 的例外：三类、到期 2026-11-07、Owner 签名的记录由入口检查 | 签本地签名记录 / 要硬约束（加平台规则种类，改平台，晚几天） / 不要例外（第 1、3 类停，第 2 类没有就推不了 main） | 签本地签名记录 | 线程回 + 他签记录（命令随 S1 给） |
| D3-3 | 两台 `vision` 家目录 700 并核对 ACL；`.52` `autorestart 1`；卸 OrbStack（含特权 helper） | 做 / 不做 | 做；建账户前必须做 | 他在 mini 终端跑（S2 给命令） |
| D3-4 | 令牌：新主体 `coordinator-52`（PROD operator、viewer、reporter）还是拷 MacBook 那把；STG operator 发不发 | 新的 + 发 STG（只调试） / 新的、不发 STG / 拷 | 新的 + 发 STG | Console 审批单（Secret 变更，D 级） |
| D3-5 | `coordinator-52` 进不进 `issue_readers` | 进（`.52` 上能做接业务的分拣，原文进 RC 记录，见 D3-6） / 不进（接业务的活回 MacBook 或等席位） | 进，前提 D3-6 接受 | 同上一张单 |
| D3-6 | RC 连着时对话记录存在 Anthropic 服务器（含问题原文）；打开受信设备 | 接受并打开 / 不接受（只能屏幕共享说话，手机验收做不到） | 接受并打开 | claude.ai 设置里他自己开；线程回「D3-6 接受」 |
| D3-7 | 离机副本：私有 Gitea 仓库 `bifrost-coord-state`，每小时同步 | 建 / 改 NAS / 改 MacBook 拉 | 建 | Gitea 上他建；线程回 |
| D3-8 | 例外里的本机任务和协调凭证同 uid（Codex 只读沙箱也读得到令牌文件） | 接受（三类都是我们自己仓库的活） / 不接受（第 1 类复核也搬 06，等 M15） | 接受，到 2026-11-07 为止 | 线程回 |
| D3-9 | 统筹存活：值守循环（Stop 钩子 + 现有线程静默呼叫）还是新加平台路由「常驻会话在场」 | 值守循环 / 新路由（改公开接口） | 值守循环；M13 不过再议 | 线程回 |
| D3-10 | 太太的桥（§6.1） | 先 Mac Air、I1 和 I5 过了再搬 / 直接 `.52` / 永不放 mini | 先 Mac Air | 线程回 |

不是选择题、要他本人做的：S2 的各步；S4 两夜合盖、早上看；S5 退出两台 `vision` 里已交接的 Claude.app；R2 若发生由他做。

## 11. 没核实的与要量的

| # | 量什么 | 不成立时 |
|---|---|---|
| M1 | `.52` 的 RC 会话在 MacBook 桌面应用里怎么出现、能否直接说话；手机能看到、能推送 | 只用 claude.ai/code 和手机；手机不行则 V2 不过，A2 也救不了 |
| M2 | `vision` 在控制台、`bifrost-coord` 后台登录，屏幕共享断开后应用和会话照跑 | A2 候选 |
| M3 | 后台会话里钥匙串保持解锁、Claude 登录跨一夜续期 | A2 候选 |
| M4 | 断电恢复：家外怎么进来（UniFi VPN + SSH，用 `vision` 的口令，Owner 做）；SSH 解锁 FileVault 后是否自动进入图形会话；恢复后带外 LaunchAgent 和统筹都要核对；解锁之前 RC 救不了自己 | 只影响恢复用时 |
| M5 | 桌面应用更新：夜里会不会重启；重启后会话能否续上、子会话怎么恢复、最新产物和未决工具结果能否分辨 | 写进回退手册 |
| M6 | （A2）进程树、监督者、Claude 退出的识别、续会话、写操作去重；无图形登录时的 Claude 登录与 RC | A2 不可行 |
| M8 | `.52` 有没有 UPS、断电恢复的实际用时 | 写进 W-68 B4 ② |
| M9 | 手机在蜂窝网下答一次真实权限请求（允许、拒绝各一次）；统筹起的子会话要人时怎么到手机 | 夜里的活可能卡在弹窗：子会话改为不弹（权限规则）或只在主会话里做 |
| M10 | 外网断超过 10 分钟后同一会话恢复可交互；正在跑的工具结果怎么回收；平台写请求结果未知时先查状态、不重发 | 记进值守循环的规矩 |
| M11 | 套餐与额度：确认套餐、MacBook 和 `.52` 同时登录、额度用完时的告知与恢复 | 额度告急时统筹停派并告诉 Owner |
| M12 | 受信设备：新设备登记、未受信设备被拒、撤销设备后旧连接失效 | 不能当撤销手段，只靠移除设备和改口令 |
| M13 | Stop 钩子在桌面应用会话里能否拒绝结束回合并保持 RC 正常；回合长时间不结束时上下文压缩是否正常 | 退到 `/loop`；或 D3-9 改新路由 |
| M14 | `CLAUDE_CONFIG_DIR` 等能否把会话记录挪到限额卷（桌面应用是否认） | 系统卷只靠余量下限 |
| M15 | 运行时能否派「复核某提交里的某份文档」和「复核不是它产出的分支」的任务 | 第 1 类例外照留到到期 |

太太那边的 I1–I5 在 §6.1。

**官方文档（查于 2026-10-23）**：Remote Control https://code.claude.com/docs/en/remote-control ；桌面应用（SSH 会话与断开时的限制、RC 设置）https://code.claude.com/docs/en/desktop ；Channels https://code.claude.com/docs/en/channels ；ChatGPT / Codex 远程连接 https://learn.chatgpt.com/codex/remote-connections 、电脑使用 https://learn.chatgpt.com/codex/use-cases/use-your-computer-with-codex ；FileVault 经 SSH 解锁（Apple 平台安全指南）https://support.apple.com/guide/security/sec8447f5049/web 。查不到的：Dot 的云端定时能否调用连接的电脑（I1）；桌面应用的自动更新能否关（M5）。

## 12. 要改的已签文档与交接（随 Owner 定的结果在 S5 改）

1. ADR §3 mini 行：宿主账户与统筹账户分开，`.52` 的统筹会话是参谋长的过渡形态，§4.6 的例外与到期日；ADR §4 mini 一列的「MCP / Claude 线程连接」改成 `.52` 统筹账户连 PROD viewer / operator（和 STG operator，若 D3-4 发），不连 admin。选 B 时另改 ADR §12.5 与 `RUNTIME-PLACEMENT` §11（§5）。
2. `AGENT_FACTS.md` L-1 表；`.mcp.json.README.md` 第 110 行（「mini 上的线程同样三个键」→ 不含 admin；与 `DESIGN-host-minimal` 文末第 8 条的不一致一并消掉）。
3. `RUNTIME-PLACEMENT-2026-10-11.md` §11「统筹搬过去 → 搬到 mini」指向本文。
4. **W-67 的验收逐项去向**（`WORK.md` W-67「验收」）：本机合盖一夜、手机看进展 → 本项 V1、V2；手机批单 → 已有（Console + VPN），推送归 W-52；回答问题、留反馈并看到回执 → W-52 与第 4 轮 4.5；mini 失联 3 分钟内通知 → 第 4 轮 4.9（W-68 B4 ①），本项只做到线程静默约 11 分钟。W-67 本身由统筹方关掉或保持搁置。
5. `LESSONS-from-practice.md` 第 1、106、110 条的「机制」一栏，S4 验收后补落点。
