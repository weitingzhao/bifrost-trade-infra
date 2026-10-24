# 统筹搬出 Owner 的电脑、Mac mini 重新分工：设计（W-31 第 4 轮 4.4）

> 状态：设计稿，**不实施**。2026-10-23 23:4x – 10-24 00:xx CDT 起草（统筹线程派出的子代理）。
> 依据：第 4 轮草案（Claude Doc「小牛牛包工队全面盘点 2026-10-23」第 4 轮草案页，4.4 与 D3）；Owner 10-23 23:3x「D2 A、D3 A、D4 A，其余按推荐」——D3 A = 先出设计，比较「.52 上独立账户常驻的统筹会话」和「统筹并进运行时的参谋长席位」，他看完定。
> 已签边界：`ADR-ops-architecture.md` §3、§4、§5、§10、§12.3、§12.5；`RUNTIME-PLACEMENT-2026-10-11.md` §11；W-67、W-68（`WORK.md`）。
> 事实来源：mini 上的只读 SSH（10-23 23:45 CDT，不读会话记录内容、不读凭证文件）；本机只读命令；厂商官方文档（链接在第 11 节，查于 10-23）。没量过的写「未核实」，并指到第 11 节的测量项。

## 0. 一页看完

- **推荐**：先做 **方案 A1**——在 `.52` 上建一个标准（非管理员）macOS 账户 `bifrost-coord`，在它的图形会话里跑 Claude 桌面应用，统筹会话开 Remote Control；Owner 在 MacBook（桌面应用或 claude.ai/code）和手机（Claude App）上跟它说话。长期按退出条件并进参谋长席位（**方案 B**）。A1 的几项关键假设量不过时退到 **A2**（同一账户里无界面的命令行常驻）。
- **为什么不是直接 B**：参谋长今天只读、只交文本（不能跑命令、不能合入、不能发版），而且只跑在 06 一台上；B 要等 4.1（运行时自动进 main）、4.3（按应用的发版策略）落地，再补第 5 节表里那几样，粗估 2–3 周以后。A1 约 3 天能用，满足本项的两条验收。
- **和 10-12 被否的 W-67 不同**：那次要在跑带外的 mini 上改 sudoers、按账户杀进程、建测试账户跑一千行带管理员权限的脚本；这次只建一个标准账户、收紧一处目录权限、加一个限额卷，没有跨账户的信号和提权，执行面（agentd）仍在 06（第 3 节）。
- **顺手发现的两处现状问题**（第 1.2 节）：两台 mini 只有一个账户 `vision`（管理员），带外操作面、看门狗和 Claude 应用都在它里面，已经是 ADR §3 写的「带外与 Agent 共用账户」；`/Users/vision` 是 `drwxr-x---`、组 `staff`，带外的 `config` 目录 755、几份 env 文件 644——任何新建的标准账户（默认也在 `staff` 组）今天就读得到它们。建账户之前必须先收紧。
- **要 Owner 定的**：第 10 节七条，D3-1（A1 还是 B 还是 A2）是主问题。

## 1. 现状

### 1.1 统筹线程今天在哪、做什么

| 事 | 怎么做的 | 跑在哪 | MacBook 合盖时 |
|---|---|---|---|
| 跟 Owner 对话 | 桌面应用 Code 里的本地会话（侧栏 `local_accccb4e…`） | MacBook | 停 |
| 派工 | 子代理（Agent 工具）、`start_session` 起子会话、夜班会话 + `detach_session`（记忆 feedback_continuous_operation）；运行时的 mission / 任务经 MCP 提 | MacBook | 停 |
| 复核 | `codex exec -C ~/agent-work/codex-review-<n>`（记忆 agent_disk_hygiene）；独立的 Claude 子代理 | MacBook | 停 |
| 合入与推 main | 手工 cherry-pick（TD-383），`push-main.sh`；Gitea 身份 `bifrost-mbp`（非管理员，令牌在钥匙串，`CUT-gitea-primary` 9.4） | MacBook | 停 |
| 发版 | `release.sh`、MCP `start_pipeline_run`、PROD 建审批单 | MacBook → PROD 平台 | 停 |
| 台账、记忆 | infra 的 `agent-config/`；记忆在 `~/.claude/projects/-Users-vision-mac-trader-Desktop-stocks/memory/`（240 个文件、2.2 MB，**只在本机**） | MacBook | — |
| 后台盯梢 | Monitor、后台 Bash；夜里用 `caffeinate`；回合结束后机器会进维护睡眠（记忆 overnight_watchers_freeze_when_mac_sleeps） | MacBook | 冻住 |

- 工作目录 `~/agent-work` 58 GB、868 项（10-23 实测）；MacBook 本身 24 GB 内存、10 核、macOS 26.6.2。
- MCP：`.mcp.json` 9 个 server，其中 `bifrost-approve` 钉 admin 令牌（`AGENT_FACTS.md` MCP 表），`bifrost-local` 指本机 bdev。令牌从 `~/.config/bifrost/mcp-tokens.env` 读（只说位置，未读内容）。
- 量：10-09 到 10-23 platform + infra 的 main 1966 个提交，统筹线程（含子代理）89.8%，包工队执行者 0.66%（盘点文档第一节）。也就是说：**今天合盖等于整个项目停**。
- 参谋长席位不是常驻会话：06 上 claude 执行者跑的 brief / plan 任务（`CUT-chief-of-staff-thin-2026-10-15.md`、`CUT-chief-exam-2026-10-19.md` §2）。

### 1.2 两台 mini（10-23 23:45 CDT 只读实测）

| 项 | `.50` ops-mac-agent-02（主） | `.52` ops-mac-agent-01（备） |
|---|---|---|
| 硬件 / 系统 | Mac mini M4 10 核 16 GB · macOS 26.5.1 · 开机 72 天 | 同 · 26.5.1 · 72 天 |
| 内存空闲 / 数据卷空闲 | 72% / 114 GiB | 76% / 142 GiB |
| 账户 | 只有 `vision`（admin 组）| 只有 `vision`（admin 组） |
| 带外 | `com.bifrost.operator-plane`（`vision` 的 LaunchAgent，工作目录 `/Users/vision/bifrost-agent`，`*:8783`）、`com.bifrost.peer-watchdog`；告警中转只在这台 | 同（无告警中转） |
| 其他进程 | Claude.app 3.6556.2（在 `vision` 里，挡系统睡眠） | 同；另有 `screensharingd`（当时有人远程连着）；OrbStack.app 还装着（10-23 已停） |
| 睡眠与开机 | `sleep 0`、`autorestart 1`（断电恢复后自动开机） | `sleep 0`、**`autorestart 0`**（断电后不自动开机）、`powernap 1` |
| 整盘加密 | FileVault On | FileVault On |
| 远程 | SSH（Remote Login）开；装着 Chrome 远程桌面 | 同；屏幕共享开着 |
| 命令行工具 | 无 `claude`、`codex`、`cursor-agent`、`tmux`、`tailscale`；node v22.23.0、go、gh | 同；node **v26.3.1**（两台不一致） |
| 工作区 | `~/Desktop/stocks` 1.4 GB，infra 停在 10-05、platform 10-04；无 `~/agent-work` | 2.9 GB，同样停在 10-05 / 10-04 |
| 会话记录 | `~/.claude/projects/-Users-vision-Desktop-stocks` 8 个文件，最近一次写入 10-22 21:49 | 11 个，最近 10-23 19:51（内容未读）；桌面应用目录下有 `claude-code`、`claude-code-sessions` |
| 权限（关键） | `/Users/vision` `drwxr-x---+ vision:staff`；`bifrost-agent/config` 755，里面四份 env 文件（含两份备份）644，只有 `env.sh` 是 600；`~/.kube`、`~/.claude` 755 | 同；三份 env 文件（含一份备份）644 |

和已签文档的出入：ADR §3 写 mini 的宿主是「独立系统账户」，`AGENT_FACTS.md` L-1 表还列着 8781（修复执行器）、8782 / 9119（Hermes），都已不在跑；`check_hardcoded_paths.py` 基线里剩下的 16 处都是 mini 的 `/Users/vision` 路径（两份 mini 的 plist 13 处、`deploy_mac_mini.sh` 1 处、测试 2 处，`agent-config/scripts/hardcoded-paths-baseline.txt`）。

### 1.3 厂商能力（官方文档，查于 2026-10-23）

| 能力 | 文档怎么说 | 对本设计的意义 |
|---|---|---|
| Remote Control（Claude Code） | 会话在本机跑，claude.ai/code 和 Claude 手机 App「是一扇窗」；只出站 HTTPS、不开入站端口；Pro / Max / Team / Enterprise 可用、不支持 API key；桌面应用里 `/remote-control` 或设置「Connect new sessions to Remote Control」；断网时交互会话一直重试、恢复后自己连上，server 模式约 10 分钟后退出；连着时对话记录存在 Anthropic 服务器上；可推送到手机（「Push when Claude decides」「Push when actions required」）；Pro / Max 可自己打开「Require trusted devices」 | A 的对话入口。Pro 起就有；池名的例子写作 `claude:owner-max:weekly`（`PLAN-round2-2.4` ①），套餐按 Max 估，未核实 |
| 桌面应用 SSH 会话 | Claude Code 跑在远端；合盖、断网、退出应用后任务继续「until it finishes, needs you, or reaches one of the limits」；但登录凭证**只在桌面应用开着且连着时续期**，过期任务就停；要通宵就「Keep your computer awake…with the lid open」，否则改用云端会话 | **满足不了合盖一夜**：不能用 MacBook 的桌面应用经 SSH 驱动 .52 |
| 云端会话（claude.ai/code） | 跑在 Anthropic 的云上，从 GitHub 克隆 | 到不了局域网里的平台、Gitea、集群；不能当统筹 |
| Channels（研究预览） | MCP server 把事件推进一个开着的命令行会话；自建的要 `--dangerously-load-development-channels`；有发送者白名单 | 以后可让平台把「Owner 在 Chief 页留言、卡被回答」推给统筹，替代轮询；本轮不用 |
| ChatGPT 桌面应用当主机 | 「Control this Mac or PC」配对手机；主机要「awake, online, and signed in to the same account」，可开「Keep this Mac awake」；可以是专用常开的 Mac；远程任务用主机上的 MCP、插件和本机工具 | 太太的接业务桥可以放在一台常开的 Mac 上，前提见 6.1 |

## 2. 三个方案

- **A：.52 上独立账户常驻的统筹会话。** 新建标准账户 `bifrost-coord`，统筹会话常驻在里面；执行面（agentd）照旧在 06。两种形态：
  - **A1（推荐先做）**：`bifrost-coord` 保持一个后台图形会话（快速用户切换；控制台仍是 `vision`），里面跑 Claude 桌面应用，统筹会话开 Remote Control。和今天的用法一样，`start_session`、`detach_session`、子代理都在。
  - **A2（A1 量不过时的退路）**：同一账户，无图形登录；系统级 LaunchDaemon（`UserName=bifrost-coord`）拉起 `tmux` 里的 `claude --remote-control`。开机解锁后自己起来，但没有桌面应用的会话工具，登录凭证能否不靠钥匙串、Remote Control 认不认长期令牌都未核实（M6）。
- **B：统筹并进运行时的参谋长席位。** 不再有常驻统筹会话；Owner 只和 Console 的 Chief 页（以后加推送）说话；派工、复核、合入、发版都由运行时按规则做，参谋长席位（06 上的 claude 执行者）出计划和回答。要补的见第 5 节。
- **C：过渡（只解决一半）。** 统筹留在 MacBook，现在就给它开 Remote Control；Owner 在手机上能说话，但合盖照样停。零成本，可在 A1 就绪前当天做；不满足合盖验收，不作为方案推荐。

### 2.1 逐项比较

| 项 | A1 .52 桌面应用 | A2 .52 命令行常驻 | B 参谋长席位 | C MacBook + RC |
|---|---|---|---|---|
| 要装什么 | 一个标准账户；Claude 桌面应用（应用已在 `/Applications`）；Codex 命令行（过渡期复核）；Homebrew 的 node 钉到同一大版本；工作区按 6.3 的脚本拉起；一个限额 APFS 卷 | 同 A1，再加 `tmux`、一份 LaunchDaemon plist（要管理员装） | 不装新机器；平台和 agentd 加能力（第 5 节） | 无 |
| 账户与凭证 | `bifrost-coord` 里：Owner 本人登录的 Claude、Codex；viewer / operator（PROD、STG）令牌，**不放 admin**；reporter 令牌；只读 kubeconfig `bifrost-agent`；新 Gitea 账号令牌（第 4.2 节） | 同 A1；Claude 登录可能要改成长期令牌文件（M6） | 都在 06 和平台里；Owner 不再有会话持有 operator 令牌 | 不变（含 admin） |
| 隔离 | macOS 账户隔离（uid、家目录 700）；标准账户无 sudo；收紧 `vision` 家目录；限额卷防占满根盘 | 同 A1 | 06 的 agentd 沙箱（按用户出站规则、Landlock 写墙、AppArmor），席位只读 | 不变（同一用户下靠 preflight 文本拦截，ADR §5 已接受的风险） |
| Owner 怎么交互 | MacBook：桌面应用或 claude.ai/code 里的 Remote Control 会话；手机：Claude App；在外不用 VPN（经 Anthropic API）；兜底：屏幕共享进 `.52` 的 `bifrost-coord` 会话 | 同 A1，少一个屏幕共享看界面的兜底 | Console Chief 页（在外要 UniFi VPN，ADR §10）；推送要等 2.5 / W-52 | 同 A1，但 MacBook 合盖就断 |
| 夜里 | `.52` 不睡（`sleep 0`）；盯梢不再冻住 | 同 | 06 不睡 | 合盖即停 |
| 断电 | 恢复后要：自动开机（`.52` 现在 `autorestart 0`，要改）→ FileVault 解锁（macOS 26 可经 SSH 解锁，M4）→ `bifrost-coord` 图形登录（屏幕共享，Owner 做）→ 恢复会话 | 解锁后自己起来 | 06 断电恢复后 agentd 自启 | — |
| 掉线 | 外网断：交互会话一直重试、恢复后自动连上；局域网断：本机工作照做，平台调用失败照报 | server 模式 10 分钟后进程退出，靠 launchd 重拉（M6） | agentd 租约到期回队列 | — |
| 和带外层的信任边界 | 同机不同账户；统筹账户里没有任何带外的凭证、没有到 `vision@` 的 SSH 钥匙；不能给 `vision` 的进程发信号 | 同 A1 | 不碰 mini | 不涉及 |
| 磁盘 | 限额卷 80 GiB 放 `agent-work`（`.52` 空闲 142 GiB）；4.6 的生命周期规则同样适用 | 同 | 06 的盘（TD-415） | 本机 58 GB 照旧 |
| 成本 | 无新硬件、无新订阅；`.52` 本来 7×24 开着；Owner 约 45 分钟（分两三次） | 同，外加一次管理员装 plist | 开发 2–3 周（依赖 4.1、4.3）；Owner 签规则若干次 | 0 |
| 回退 | MacBook 上重新开统筹线程；`.52` 退出应用、作废令牌、删账户和卷 | 同 | 恢复常驻统筹会话 | 关掉 RC |
| 多久能用 | 设计定后约 3 天（第 8 节） | 再加约 1 天 | 2–3 周以后 | 当天 |
| 满足 4.4 两条验收 | 两条都满足（待 M1–M3 量） | 待 M6 | 合盖一条满足；手机一条要等推送和 VPN | 只满足手机一条 |

## 3. 和 10-12 被否的方案（W-67）有什么不同、风险怎么控

10-12 的设计（`DESIGN-host-minimal-2026-10-12.md`）把 mini 当 **Agent 执行主机**：守护进程账户 + 槽位账户，一条「守护进程可以变成槽位账户」的 sudoers，`kill -TERM -1` 按 uid 清进程，禁槽位的定时任务，开机守护进程；为了证明这条边界成立，要建测试账户、跑三个共 1,003 行的脚本。安全复核 122 点出 34 条危险命令、10 处中途放弃清不掉的残留，结论是这些不该在跑带外操作面的机器上做（`LESSONS-from-practice.md` 第 110 条）。

| | W-67（10-12，否） | 本设计 A |
|---|---|---|
| 跑什么 | 一池用完即弃的执行任务（三家执行者），要求任务之间隔离 | 一个长驻的统筹会话（加它的子代理）；执行者仍在 06 |
| 改系统的地方 | 两个账户、sudoers、开机守护进程、禁定时任务、按账户发信号、`RLIMIT_NPROC` | 一个标准账户（系统设置里点，或一条 `sysadminctl`）；`chmod 700 /Users/vision`；一个限额卷；`.52` 的 `autorestart 1`。没有 sudoers、没有跨账户信号、统筹账户没有 root |
| 要证明的边界 | 槽位之间、槽位与守护进程之间（难，否决项多） | 统筹账户读不到、改不了、杀不了带外账户的东西。用的是系统自带的用户隔离，不是我们写的 |
| 在 mini 上的验证 | 管理员权限的一千行脚本 | 只读检查，一屏以内（第 8 节 S0）；会改东西的测试只在统筹账户自己的文件里做 |
| 和 ADR §3 | 执行面放 mini（后来 10-17 改去 06） | §3 的 mini 一行本来写着「参谋长常驻（形态另定）」；统筹就是参谋长的过渡形态。另外把 Claude 应用从 `vision` 挪出去，**修掉**今天「带外与 Agent 共用账户」的偏离 |

**剩下的风险和控制**：

1. **统筹账户被诱导或出错去碰带外**：家目录 700、无 sudo、无 `vision@` 钥匙；验收 V3 用 `test -r`、`sudo -n true`、`kill -0 <operator-plane 的 pid>` 证明三样都被拒。preflight 加一条：统筹账户里拒绝 `ssh vision@`、拒绝写 `/Users/vision`（文本拦截，防误用不防绕过）。
2. **抢资源让带外饿死**：限额卷封住磁盘；同时跑的重活（`go test`、`codex exec`）不超过 2 件、`nice -n 10`；`memory_pressure` 空闲低于 30% 时不派新复核（照 `disk-guard.sh` 的做法）。带外前后各量一次健康基线（V3）。
3. **统筹持有的令牌被拿走**：比今天小——今天 MacBook 上同一用户还有 admin 令牌（ADR §5「已知的接受风险」），`.52` 上不放 admin、不配 `bifrost-approve`；审批只在 Console 和手机。Remote Control 打开「Require trusted devices」，防别人用 Owner 的 claude.ai 账号操纵这个能跑命令的会话。
4. **网络位置**：统筹在运维区（ADR §10，靠凭证收口），和今天的 MacBook 一样，不是退步；按用户的出站规则（pf 支持 `user` 条件）以后再加，不在本轮。
5. **一台机器两种角色**：`.52` 是带外备机。带外主机 `.50` 保持干净；`.52` 坏了，带外有 `.50` 接，统筹有 MacBook 回退（第 8 节回退）。

## 4. 方案 A 的细节

### 4.1 账户与文件布局（`.52`）

| 账户 | 类型 | 放什么 |
|---|---|---|
| `vision` | 管理员；Owner 登录用；控制台会话 | 带外操作面（备）、看门狗；**退出并取消开机启动 Claude.app**；家目录改 700 |
| `bifrost-coord` | 标准；后台图形会话 | 工作区 `/Users/bifrost-coord/stocks`（**不放 Desktop**：Desktop 受 macOS 隐私保护，launchd 起的进程读它会 EPERM，记忆 vite_eperm_desktop_privacy）；`~/agent-work` 链到限额卷 `/Volumes/coord-work`；`~/.claude/projects/<工作区>/memory`；`~/.config/bifrost/`（600） |

工作区路径换了：钩子都用 `$CLAUDE_PROJECT_DIR`（`claude/settings.json`），硬编码路径有防线，不受影响；用户级 `~/.claude/CLAUDE.md` 要写新路径（6.3 的脚本生成）。

### 4.2 凭证清单

| 放 | 用途 | 怎么来 |
|---|---|---|
| Claude 登录（Owner 本人） | 统筹会话、Remote Control | Owner 在 `bifrost-coord` 的图形会话里登录一次（两步验证在他手机上） |
| Codex 登录 | 过渡期的复核（4.6） | Owner 登录一次；Cursor 不装，用 06 |
| `mcp-tokens.env`：PROD viewer、PROD operator、STG operator 三个键 | MCP | **建议每台一把新的 operator 令牌**（单独作废；令牌表支持多把，`DESIGN-host-minimal` D3）。加令牌是 Secret 变更，D 级，Console 审批（D3-4） |
| reporter 令牌 | 线程标题、心跳 | 同上，每台一把 |
| 只读 kubeconfig `bifrost-agent` | 只读查集群 | Owner 拷一份 |
| Gitea 新账号 `bifrost-coord-52`（非管理员）的令牌 | 推分支、`push-main.sh` 推 main | 照 `bifrost-mbp` 的做法（`CUT-gitea-primary` 9.4）：Owner 建账号、加进 main 的推送白名单、发令牌存进 `bifrost-coord` 的钥匙串 |
| `agent_reader` 口令（可选） | 只读查库 | 能用 MCP 就不放 |

**不放**：admin 令牌和 `bifrost-approve`；`bifrost-local`（bdev 只在 MacBook）；`~/.bifrost-owner*`；管理员 kubeconfig；任何 `.env`；到 `vision@.50/.52`、节点、NAS 的 SSH 钥匙；带外的 ntfy topic 和中转令牌；TWS / IB 的任何东西。mini 的事实改从 W-68 B4 ① 的主机监控读，不再 SSH 进 `vision`。

### 4.3 会话形态与对话入口

- 统筹会话在工作区根起（加载 preflight 和记忆）；**只给统筹会话本身开 Remote Control**（`/remote-control` 或会话的开关），不开「所有新会话自动连」，免得子会话刷满 Owner 手机上的列表。
- **MacBook**：按文档，Remote Control 会话能在 claude.ai、手机 App 和桌面应用里看和操作；在 MacBook 桌面应用侧栏里怎么显示未实测（M1）。最稳的入口是浏览器开 claude.ai/code 里那一条。
- **手机**：Claude App → Code → 这条会话；在 `/config` 打开两种推送。在外用蜂窝网也能说话（Remote Control 只走 Anthropic API）；Console 仍要 UniFi VPN。
- **权限弹窗**：统筹照旧跑 auto mode（用户级规则由 Owner 用 `apply-auto-mode.sh` 在 `bifrost-coord` 里应用一次）；剩下的弹窗经「Push when actions required」到手机。审批单仍只在 Console（ADR §5）。
- **新增的留存**：连着 Remote Control 时对话记录存在 Anthropic 服务器上。统筹读过的问题原文（`get_issue_full`）会进记录。Owner 接受或不接受（D3-6）。

### 4.4 夜里、断电、掉线、崩溃

- **存活信号**：`bifrost-coord` 装主机心跳（`scripts/com.bifrost.host-heartbeat.plist`）和线程心跳钩子。注意 `CUT-online-status-2026-10-23.md` §1.1：老心跳路由 `GET /api/v1/agent/threads` 的 hosts 一半 10-21 起没人写、计划 10-28 删；统筹的存活要接到 agentrt 的在线状态（3.5，PROD #148）或保留线程心跳那一半。接哪条在 S1 定，**未核实**删的是不是整条路由。
- **会话崩溃或应用更新重启**：应用更新会结束正在跑的回合（未核实能否关自动更新，M5）；恢复办法是重开会话、`claude --continue` 一类续上；状态在仓库和运行时里。静默超过 10 分钟推送一次（照 ADR §12.9 第 9 条）。
- **断电**：`.52` 改 `autorestart 1`；FileVault 在 Apple 芯片、macOS 26 上可以经 SSH 解锁（Apple 安全指南，第 11 节链接），解锁后是否自动进入图形会话未核实（M4）；`bifrost-coord` 的图形登录由 Owner 屏幕共享做。另一台 mini 的看门狗发现 `.52` 失联就经 `.50` 的中转呼 Owner。两台都断（整屋断电）时统筹停，等恢复——和 06、集群一样。
- **掉线**：外网断，模型调用停，恢复后自己连；局域网断，Git 和平台调用失败照报，不重试写操作。

### 4.5 磁盘与缓存（和 4.6 生命周期的衔接）

- 限额卷 `coord-work`（APFS，配额 80 GiB，建议值）只放 `agent-work`；根盘留给系统和带外。
- 复核共用缓存 `~/agent-work/.cache`（Go、npm），做法照记忆 agent_disk_hygiene；4.6 的「工作目录登记属于哪件活、活结束就删、认不出主人只报不删」同样装在 `.52`，盘的余量进 W-68 B4 ① 的监控，低于下限停派新活。
- MacBook 的 58 GB 不搬：切换前把在途分支推到 Gitea，`.52` 从 Gitea 新开 worktree；MacBook 上的旧目录按 4.6 的一次性清理处理。

### 4.6 执行在哪跑（ADR §3「执行面不放 mini」的有期限例外）

统筹今天自己跑测试（推 main 前的整套）和 Codex 复核。搬到 `.52` 后有两种做法：

- **甲（推荐）**：作为有期限的例外，统筹在 `.52` 上照旧跑测试和只读复核（`codex exec` 沙箱 read-only），限额照 3.2；**期限**：4.1 上 PROD、复核能走运行时的复核任务为止，届时统筹只编排。
- 乙：从第一天起测试和复核全派 06。做不到：运行时今天只接 platform、infra（`store/repos.go:68`），设计文档的复核没有对应的任务种类。

## 5. 方案 B：参谋长要补什么

**现在能做的**（`CUT-chief-of-staff-thin`、`PLAN-round2-2.4` ④、`CUT-chief-exam` §2、`CUT-online-status` §1.1）：席位是 06 上的 claude 执行者，钉死空 MCP、只给 Read / Grep / Glob，只交一段文本；三条路径——给目标 → 规划任务（控制器把结果落成 mission、任务、决策卡、决定记录）；信箱 / Chief 对话 → brief 任务，答案发回 Chief 页（对话前文是最近 10 条）；定时简报 8:00、21:00 和卡住提醒；`POLICY_ALERT` / `CANNOT` 两种协议行。资格考试有离线考场。**06 掉线时参谋长也掉线**。

| 统筹的活 | 参谋长现在 | 要补的 | 依赖 |
|---|---|---|---|
| 派工 | 规划任务拆任务、控制器路由 | 返工或卡住后重新规划；跨 mission 排队；多仓库、多产品 | 4.2 |
| 复核 | 运行时的评审岗管代码任务 | 方案和设计文档的复核任务；停线规矩的轮次进控制器（代码任务已有「最多两轮」） | — |
| 合入 | 不能 | 运行时自动进 main | **4.1** |
| 发版 | 不能 | STG 合入后自动发；PROD 按每个应用的发版策略，健康检查不过自动回滚 | 4.1、**4.3**（W-56 门槛） |
| 跟 Owner 对话 | Chief 页一问一答，分钟级；不推手机；只记得最近 10 条 | 推送到手机；回答时延目标（例如 3 分钟内）；运行时里的长期记忆（决定、教训、台账摘要）；把 Owner 的回答变成计划变更或规则提议的结构化出口 | 2.5 / W-52 推送 |
| 台账与记忆 | 不能写 | 台账（TECH_DEBT、WORK、LESSONS）改成运行时数据，或由 infra 仓库里的实现任务写 | 4.2（infra 已可派） |
| 看现场 | 只看快照 | 快照加集群与主机的事实层摘要；统筹的动作进运行时（4.5） | 4.5 |
| 上岗 | 考试第 2、3 轮只差判分误判 | 新能力进考卷，资格流水线自动发卷 | 4.8 |
| 后备 | 只在 06 | 第二个能跑席位的主机，或 B5 | W-68 B5 |

粗估：4.1（3–4 天）、4.3（实现 3–4 天）之后，再补上表 5–7 天；把握低。**并入的退出条件**（三条都成立才撤 A）：① 一周里进 main 的代码提交一半以上由运行时自己做完并合入（第 4 轮第一个衡量数）；② 参谋长带新能力通过资格考试；③ 连续一周，Owner 的对话 90% 以上在 Chief 页完成，没有因为「只有统筹线程能做」而回到统筹会话。

## 6. 一起回答的问题

### 6.1 太太的接业务桥能不能放 mini

现状（`DESIGN-crew-intake-2026-10-22.md` 第六节、V1–V3）：桥是只注册 7 个接业务工具的 stdio MCP，令牌只能碰接业务路由；她的桌面应用能挂本机 MCP（V1 大部分已核实）；Dot 的定时可能在云端电脑上跑，云端连不到她 Mac 上的桥（V2 部分核实）；她的 Mac 在 `192.168.20.x`，连得到平台（V3）。Owner 的约束：不方便登录她的 Mac Air；她的 Mac Air 可能关机。

- **能，有条件**。ChatGPT 文档支持把一台常开的 Mac 当主机（第 1.3 节），远程任务用主机上的 MCP。放法：`.52` 上再建一个标准账户 `bifrost-p2`，后台图形会话里跑 ChatGPT 桌面应用，**登录她的 ChatGPT 账户**（她或 Owner 屏幕共享时由她在手机上过两步验证），只装接业务桥和 intake 令牌（600）；Codex 配置照 V1 的 read-only 沙箱。**不放 `.50`**。
- **风险**：这等于让一个外部厂商驱动的 Agent 在运维区的一台机器上有命令执行能力（她 Mac 上本来就有，但她的 Mac 不在运维区）。账户里只有桥和令牌；网络上它够得着运维区能到的一切，靠凭证收口。所以是 D 级的放宽，Owner 定（D3-5）。
- **上机之前要量**（在她的 Dot 里问或试，统筹不动手）：I1 Dot 的定时 / 云端任务能不能调用「连接的电脑」上的 MCP（能，才值得搬；不能，放 mini 只省了 Owner 登录她 Mac 的麻烦）；I2 主机上的 MCP 调用要不要每次在主机或手机上点允许；I3 同一个 ChatGPT 账户同时连她的 Mac Air 和 mini 时任务落在哪台；I4 从 `bifrost-p2` 账户不带令牌能到哪些局域网接口（照 W-6 的口径，只看状态码）。
- **推荐**：先按原设计放她的 Mac Air 做切片 4；I1 为「能」再搬 `.52` 的 `bifrost-p2`。两种放法桥的代码相同。

### 6.2 06 坏了，mini 能不能临时接活（W-68 B5）

**不推荐 mini 当 agentd 的后备。** agentd 的约束靠 Linux：systemd 单元、按用户的 nftables 出站、Landlock 写墙、AppArmor（`scripts/agent-host/` 下的 `bifrost-agentd*.service`、`agent-egress.nft`、`bifrost-codex.apparmor`）；macOS 上都没有，岗位的「边界类」要求（ADR §12.5）做不到；ADR §3 也写执行面不放 mini。06 坏了时 A 方案的情形：运行时的任务留在队列里（租约到期回队列），Console 1 分钟内显示主机掉线（3.5）；`.52` 上的统筹照常对话、规划，在 4.6 甲的例外内自己做小的测试和复核。B5 的三条路（Mac Pro 冷备、gpu-server 唤醒冷备、再买）仍由 Owner 在 W-68 定；若要 mini 当应急执行面，要另出一份 macOS 隔离设计（`sandbox-exec` 或虚拟机），不在本轮。

### 6.3 工作区一条脚本在新机器上拉起（ADR §12.9 第 1 条）

今天没有：根目录的链接重建命令写在 `agent-config/README.md` 第 45–85 行，要手抄。做成 infra 的 `scripts/workspace/bootstrap.sh` 加 `agent-config/workspace.yaml`：

- `workspace.yaml`：12 个仓库的 Gitea 地址和分支、根目录白名单（链接与目标）、工具链版本（node 大版本、go、python）、要装的命令行（claude、codex）、Owner 要放的文件清单（只写路径和权限，不写值）。
- `bootstrap.sh apply`：幂等。克隆或快进仓库 → 建根目录链接 → `sh scripts/git-hooks/install.sh` → 装 MCP 的依赖 → 生成用户级 `CLAUDE.md`（新路径）→ 列出缺的凭证文件和权限（不读内容）。不跑 `sudo`，不改系统设置。
- `bootstrap.sh check`：只读，逐项报 PASS / 缺；带一个阳性对照（故意缺的一项必须报出来，记忆 empty_scan_needs_a_positive_control）。
- 新节点测试 = 在 `.52` 的 `bifrost-coord` 里从零跑一遍，再在 MacBook 上跑 `check` 应全 PASS。

### 6.4 记忆怎么跟着走

记忆按工作区绝对路径存，路径换了就是另一份。选项：甲（推荐）切换时把 MacBook 的记忆拷进 `.52`，`.52` 为准；MacBook 上之后的会话（咨询、设计）用一份只读副本，由 Owner 在 MacBook 开会话前拉一次（脚本在 6.3 里加 `pull-memory` 子命令，经 MacBook → `bifrost-coord@.52` 的 SSH，方向是信任高的一边读信任低的一边）。乙：记忆进私有 Gitea 仓库（ADR §12.9 第 3 条的 `bifrost-private`，还没建），两边都写、靠 git 合并。丙：记忆进运行时（ADR §12.5，B 时代）。

## 7. mini 的新分工

| 机器 · 账户 | 跑什么 | 凭证 | 不跑 |
|---|---|---|---|
| `.50` · `vision`（管理员） | 带外操作面（主）、告警中转（ntfy）、看门狗 | 带外自己的配置 | Claude.app（退出）、任何 Agent、统筹、外部厂商的 App |
| `.50` · `bifrost-exec`（以后，W-50 搁置中） | 带外执行器 | 专用受限 kube 身份 `bifrost-owner-exec` | 同上 |
| `.52` · `vision`（管理员） | 带外操作面（备）、看门狗 | 同上 | Claude.app（退出）；OrbStack 卸载（Owner 10-23 已说） |
| `.52` · `bifrost-coord`（标准） | 统筹会话（Claude 桌面应用 + Remote Control）、它的子会话与子代理、过渡期的 Codex 复核、主机心跳 | 第 4.2 节的表 | agentd、bdev、admin 令牌、带外的任何东西 |
| `.52` · `bifrost-p2`（标准，**有条件**，6.1） | ChatGPT 桌面应用（太太的账户）、接业务桥 | intake 令牌 | 其他一切 |
| 06 | 不变：PROD、STG 两个 agentd | 不变 | — |
| MacBook | 开发、驾驶舱；切换后统筹线程归档，只在回退时重开 | 不变 | 任何被夜里依赖的东西 |

`AGENT_FACTS.md` L-1 表随 S5 改：去掉 8781、8782、9119，加上 `.52` 的统筹账户；`.50` / `.52` 的主机名和「主 / 备」写清（主机名 `ops-mac-agent-02` 是 `.50`，容易看反）。

## 8. 切片与验收

| 片 | 做什么 | 谁 | 多久 |
|---|---|---|---|
| S0 量 | 第 11 节 M1–M8；先量带外的健康基线（两台 `:8783` 的健康检查、看门狗状态、中转发一条测试） | 统筹方只读；建账户之后的几项在 `bifrost-coord` 里量 | 半天 |
| S1 工作区即代码 | 6.3 的 `workspace.yaml` 和 `bootstrap.sh`，含测试与阳性对照；存活信号接哪条路由（4.4）在这片定 | 统筹方写、Codex 复核 | 1 天 |
| S2 `.52` 准备 | Owner：`vision` 家目录 700、`autorestart 1`、建 `bifrost-coord`、建限额卷、图形登录并登录 Claude 和 Codex、开推送和受信设备、放令牌与 kubeconfig、建 Gitea 账号、跑 `apply-auto-mode.sh`；统筹方：在新账户里跑 `bootstrap.sh apply` 和 `check` | Owner 约 45 分钟，分两次 | 半天 |
| S3 演练 | `.52` 上起统筹会话，MacBook 统筹线程不动：走一条真的小活（派一次复核、`push-main.sh` 推一次 infra、STG 发一次）；Owner 从手机说一句话 | 统筹方；Owner 说一句话 | 半天 |
| S4 切换与一夜 | MacBook 统筹写交接（在途清单、等待项、分支已推）、拷记忆；`.52` 接手；MacBook 统筹线程归档；当晚合盖 | 统筹方；Owner 合盖、早上看一眼 | 一夜 |
| S5 收尾 | 两台 mini 的 `vision` 退出 Claude.app；ADR §3 / §4 的 mini 行、`AGENT_FACTS.md` L-1、`MAINTAINERS.yaml`（统筹会话登记为维护者并对应告警）、硬编码路径基线、台账 | 统筹方；Owner 退出 App 时顺手 | 半天 |

**验收**（每条写观察和过的标准）：

- **V1 合盖一夜**：MacBook 22:00 前合盖到 07:00 后（证据：MacBook `pmset -g log` 这段时间是睡眠）。过：这段时间里 Gitea 上有带 `.52` 统筹会话 `Claude-Session` 尾注的提交或运行时事件；07:00 时 Console 的 Progress 是当前的（不过期）；`.52` 的主机存活全程不超过门槛；夜里派出的活早上有结果（通过、返工或停线都算有结果，「没人接」不算）。
- **V2 手机说一句话**：Owner 在家外（蜂窝网）用 Claude App 对统筹会话说一句话。过：会话空闲时 5 分钟内收到回答；会话正忙时回答随当前回合结束到达，并且推送到了手机。
- **V3 带外不受影响**：S0、S4 后、S5 后三次健康基线相同；在 `bifrost-coord` 里，对 `vision` 的三个路径 `test -r` 都失败、`sudo -n true` 失败、`kill -0 <operator-plane 的 pid>` 返回无权限。
- **V4 回退能用**：S3 里演练一次：`.52` 的统筹退出，MacBook 上新开统筹线程只凭仓库和交接文件接上，10 分钟内说清在途的事。

**回退**：MacBook 上在工作区根开新统筹线程；`.52` 统筹会话归档、退出应用；Console 作废 `.52` 的 operator 和 reporter 令牌，Gitea 停用 `bifrost-coord-52`；Owner `sysadminctl -deleteUser bifrost-coord`、删限额卷。`vision` 家目录 700 和 `autorestart 1` 保留（本来就该这样）。

## 9. 推荐与理由

**A1 现在做，B 作为终点、按第 5 节的退出条件并入；A1 的 M1–M3 不过就换 A2；C 可以今晚就开（只为手机能说话）。**

1. 只有 A 能在第 4 轮第一波里满足 4.4 的两条验收；B 依赖的 4.1、4.3 自己还在做，而统筹不搬，第 4 轮其余各项（包括 4.1）夜里照样停。
2. A1 和今天的工作方式一样（桌面应用、子会话、夜班会话、子代理），换的只是机器，最少意外；A2 少了桌面应用的会话工具，登录方式也没核实。
3. A 不碰执行面、不碰带外的配置，比 10-12 的方案小一个量级，还顺手修掉两处现状问题（`vision` 账户里的 Claude.app、`staff` 组能读带外配置），并把 admin 令牌从 Agent 所在的机器上拿掉。
4. 「能力用厂商的，状态放我们的」（ADR §12.2 第 7 条）：Remote Control 只是对话的窗口，状态仍在仓库和运行时；以后 B 接手时没有要迁的厂商状态。

## 10. 待 Owner 定

| # | 事 | 选项 | 建议 | 在哪办 · 怎么回 |
|---|---|---|---|---|
| D3-1 | 统筹放哪 | A1 / A2 / B / 先 C | **A1**，B 作终点，C 今晚可开 | 统筹线程里回「D3-1 A1」 |
| D3-2 | ADR §3 的 mini 行加「`.52` 的标准账户 `bifrost-coord` 里常驻统筹会话（参谋长的过渡形态）」；执行面不放 mini 的有期限例外（4.6 甲，到 4.1 上 PROD、复核走运行时为止） | 同意 / 只同意前一半（测试复核全派 06，统筹在那之前做不了合入前的整套） | 同意 | 同上，「D3-2 同意」 |
| D3-3 | 收紧 `vision` 家目录到 700（两台都做），`.52` 改 `autorestart 1` | 做 / 不做 | 做；建账户前必须先做 | 他在 mini 的终端里跑（命令随 S2 给，不带占位符） |
| D3-4 | `.52` 用新的 operator / reporter 令牌，还是拷 MacBook 那把 | 新的（Secret 变更，D 级） / 拷 | 新的：`.52` 出事只作废它 | Console 审批单 |
| D3-5 | 太太的桥放 `.52` 的 `bifrost-p2`（6.1） | 先 Mac Air、I1 过了再搬 / 直接 `.52` / 永不放 mini | 先 Mac Air | 统筹线程 |
| D3-6 | Remote Control 连着时对话记录存在 Anthropic 服务器上（含读过的问题原文）；打开「Require trusted devices」 | 接受并打开 / 不接受（那就只能屏幕共享进 `.52` 说话，手机一条验收做不到） | 接受并打开 | claude.ai 设置里他自己开；线程里回「D3-6 接受」 |
| D3-7 | 记忆跟着走（6.4） | 甲 `.52` 为准、MacBook 只读副本 / 乙 私有仓库 / 丙 等 B | 甲 | 统筹线程 |

另外要他本人做、不是选择题的：S2 的几步（建账户、登录各家、建 Gitea 账号、放令牌、跑 `apply-auto-mode.sh`）；S4 当晚合盖、早上看一眼；S5 退出两台 mini 上 `vision` 里的 Claude.app；`.52` 的 OrbStack 卸载（10-23 已说要卸）。

## 11. 没核实的事实与上机前要量的

| # | 量什么 | 不成立时 |
|---|---|---|
| M1 | `.52` 上 Remote Control 会话在 MacBook 桌面应用里怎么出现、能不能在里面直接说话；手机 App 能否看到并推送 | 只用 claude.ai/code 和手机，不影响验收 |
| M2 | `vision` 在控制台、`bifrost-coord` 经快速用户切换在后台登录时，屏幕共享断开后 `bifrost-coord` 的桌面应用和会话照跑；`.52` 现在 3 个登录会话里有没有别人 | 不成立 → A2 |
| M3 | `bifrost-coord` 后台会话里钥匙串保持解锁，Claude 登录不掉 | 不成立 → A2 |
| M4 | 断电恢复：SSH 解锁 FileVault（Apple 芯片、macOS 26 支持）后，是否自动进入某个用户的图形会话；`bifrost-coord` 是否需要「FileVault 已启用」才能登录 | 只影响断电恢复用时，不否决 |
| M5 | 桌面应用自动更新会不会在夜里重启、能不能延后 | 记进回退手册；不否决 |
| M6 | （A2 才需要）无图形登录时 Claude 的登录放哪（`claude setup-token` 的长期令牌）、`claude remote-control` 认不认这种令牌 | A2 不可行 |
| M7 | 老心跳路由 10-28 删的是 hosts 一半还是整条（`CUT-online-status` §1.1） | 统筹存活改接 agentrt 在线状态 |
| M8 | `.52` 有没有接 UPS；断电恢复的实际用时 | 写进 W-68 B4 ② |

太太那边的 I1–I4 在 6.1。

**官方文档（查于 2026-10-23）**：
- Claude Code Remote Control：https://code.claude.com/docs/en/remote-control
- Claude Code 桌面应用（SSH 会话、断开时的限制、Remote Control 设置、Dispatch）：https://code.claude.com/docs/en/desktop
- Claude Code Channels：https://code.claude.com/docs/en/channels
- ChatGPT / Codex 远程连接（把常开的 Mac 当主机）：https://learn.chatgpt.com/codex/remote-connections ；电脑使用：https://learn.chatgpt.com/codex/use-cases/use-your-computer-with-codex
- FileVault 经 SSH 解锁（Apple 平台安全指南）：https://support.apple.com/guide/security/sec8447f5049/web
- 查不到的：ChatGPT 文档里没有写 Dot 的云端定时能不能调用连接的电脑（I1）；Claude 文档里没有写桌面应用的自动更新能否关（M5）。

## 12. 和已签文档要改的地方（随 Owner 定的结果在 S5 改）

1. ADR §3 的 mini 行：写明宿主账户与统筹账户分开，`.52` 的统筹会话是参谋长的过渡形态；有期限的执行例外（D3-2）。ADR §4 的 mini 一列「MCP / Claude 线程连接：应急子集」改成 `.52` 统筹账户连 PROD 与 STG 的 viewer / operator，不连 admin。
2. `AGENT_FACTS.md` L-1 表、`.mcp.json.README.md` 第 110 行（「mini 上的线程同样三个键」→ 两个 operator 和一个 viewer，**不含 admin**；与 `DESIGN-host-minimal` 文末第 8 条的不一致一并消掉）。
3. `RUNTIME-PLACEMENT-2026-10-11.md` §11「统筹搬过去 → 搬到 mini」指向本文。
4. W-67 的验收（「本机合盖一整夜……」）由本项接手；W-67 本身保持搁置或关掉，由统筹方定。
5. `LESSONS-from-practice.md` 第 1、106、110 条的「机制」一栏，S4 验收过后补上落在哪。
