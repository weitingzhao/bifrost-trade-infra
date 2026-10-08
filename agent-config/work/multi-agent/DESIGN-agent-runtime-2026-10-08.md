# 多 Agent 长任务协作运行时：现状分析与设计草案（v3）

- **状态**：讨论稿 v3（2026-10-08，多 Agent 协作线程）。**整体未经 Owner 确认，不落地。**
- **Owner 已定（10-08 第三、四轮）**：
  1. 运行时放进 platform（H1）；
  2. Redis 只在平台内部，Agent 不直连；
  3. 推理网关放进 platform；
  4. **无人值守的业务管线不走订阅额度**；
  5. 本地 GPU 是做杂活的补充，对 Stocks 自身开发基本没帮助，但能给业务 LLM 分析做补充；
  6. 运行时**同时服务开发和业务**，路由偏好以后可以配置；
  7. 这个运行时是 Ops Platform 在多 Agent 时代的工作重心，和「Ops Platform 瘦身」线程（ops-arch）配合推进。
- **v3 相对 v2 的变化**：
  - 本地 GPU 退出开发的主路径，改为两个租户共用的杂活执行者；
  - 新增「租户」（开发 / 业务）和推理网关（5.5）；
  - 新增路由偏好（5.6）；
  - 新增与瘦身线程的分工（第 13 节）。
- **v2 吸收了 Owner 当天的第二轮反馈**：
  1. 本地 GPU 是现成的闲置资源，要当主力用；
  2. Redis 应该担当交互的核心；
  3. DeepSeek / OpenAI 的 API 额度留给 Trade 业务，运行时不用；
  4. 需要什么软件都可以装（Codex 也行）；
  5. 工作区根目录的 md 文件已经乱到无法协作。
- **输入**：
  - `Research-workspace/openai_multi_agent_architecture_research_2026-10-08/`。研报用 `[P]`/`[I]`/`[D]`/`[U]` 区分证据，本文照用；研报所述事件在本线程模型的知识截止之后，无法独立核实。
  - Owner 转来的 OpenAI 任务简报。
  - ADR §12 与 `PHASE1-OPTIONS-2026-10-08.md`。
- **与 ADR §12 的关系**：本文把 §12 的「四样东西」推广成一个运行时。认领、待办箱由任务租约与交互总线取代；发布队列保留，作为对外副作用的闸门。讨论定了再改 §12。

---

## 1. 结论先行

1. **为什么要做**：单家厂商的月度额度不够用了，但几家的订阅额度加起来，调度得当根本用不完。这个运行时的价值是**把活分到有余量的地方**，并且不出错；以后连 Trade System 的业务 LLM 工作也一起调度。
2. **一个内核，两个租户，四类算力**：
   - 租户：**开发**（Stocks 自己的工程工作）和**业务**（Trade / Research 的 LLM 分析）；
   - 算力：
     - 订阅制 Agent：Claude Code、Cursor、Codex（ChatGPT 会员），以后可能有 Grok；
     - 本地 GPU 上的开源模型：只做杂活；
     - 按 token 计费的 API：DeepSeek、OpenAI，只给业务租户兜底，而且只经过推理网关；
     - 确定性执行者：跑验收命令，不用模型。
3. **两条硬规则**：
   - **无人值守的业务管线不走订阅额度**（Owner 已定）。订阅额度只用于开发，以及 Owner 本人在场、亲手发起的业务分析。
   - **业务 API 键只放在推理网关里**。所有 Agent 的环境里都没有这些键，业务进程也只拿到网关地址。
4. **协调者 = 领规划任务的席位**：规划是一种任务（`role=plan`），由控制器（代码）在合适的时刻生成；同一 mission 同时只有一张在租约中。规划者不存状态，谁有资格谁接班，Grok、Claude、Codex 或本地模型都可以。
5. **PostgreSQL 是唯一的事实来源，Redis 是交互总线**：
   - PG 管任务状态、租约、事件、产物与审计（compare-and-swap、`SKIP LOCKED`、可重放）。
   - Ops 自己新起一个 Redis（`redis-agents`，开 AOF），管实时的那一半：每个 Agent 一个信箱（Streams + 消费组）、唤醒信号、在线状态、冷却、叫停广播。Redis 丢了可以从 PG 的 outbox 重建。
   - **Agent 不直连 Redis**，只经过平台 API / MCP，所以身份永远由服务端打戳。研报里那场事故的根子，正是 Agent 自己搭的、没有宿主控制的留言板 `[P]`。
6. **协调不再经过文件**：任务说明、报告、预注册、验收结论、交接、洞见，全部是运行时里的**类型化记录**，正文按内容哈希存放。git 只放治理文档与代码；工作区根目录对 Agent 只读；worktree 由 `agentd` 在自己的目录里建和删。
7. **权威在代码**：状态只由控制器改；作者不能自验；Agent 之间的消息只算数据；范围、预算、副作用上限都写在 Owner 批准的 mission 清单里。
8. **放置（H1，Owner 已定）**：
   - 内核与推理网关都放进 PROD platform-api（Go）；
   - 状态存 CNPG 新库 `bifrost_platform`（schema `agentrt`）；
   - `redis-agents` 放在 PROD platform 命名空间，只给平台内部用；
   - `agentd` 跑在 Agent 主机上；
   - 发布队列仍放 statefile，不依赖 PG 和 Redis。
9. **先单 Agent 基线，后并发**：第 0 阶段全局 1 个租约，对每一类执行者分别测「已关闭技术债的回放」。Gate A（T01 / T02 / T08 / T10）不过，就不做无人值守。

---

## 2. 用例与概念对照

| 研报概念 | 今天的对应物 | 本设计中 |
|---|---|---|
| Mission Owner | Owner | 批 mission、批范围扩张与副作用、签收 |
| MissionManifest | 计划文件、ADR、WORK.md | `MISSION.yaml`，按 sha256 走现有审批单批准 |
| Mission Controller | **没有**（Grok 加文件凑合） | `agentrt` 控制器 |
| Planner | Grok（Der）、各计划线程 | `role=plan` 席位 |
| Explorer / Builder | Cursor 道、Claude 实现 | `implement` / `research` 任务，按级联路由分给执行者 |
| Verifier | Claude 照报告重跑验收 | 确定性命令（不用模型）；需要评审时换另一家 |
| Curator | 记忆、TECH_DEBT、交接简报（各家互不可读） | `curate` 任务，**默认交给本地模型**；洞见包经 MCP 对所有厂商可读 |
| Policy Monitor | preflight、auto mode、审批、RBAC | 控制器 + `agentd` + 审批 / 发布队列；钩子退为第一道 |
| 黑板 / 留言 | md 文件、SendMessage、`~/der-relay` | PG `agentrt.event` + Redis 信箱 |
| 产物 | 散在根目录的 REPORT / PREREG / REVIEW | `agentrt.artifact` + `artifact_blob`（内容寻址） |
| 预算 | 额度用完才知道 | 按厂商的月度与窗口额度账本，以实测为主 |

- **开发租户**（先做）：跨厂商的工程协作。
- **业务租户**（后做），分三种发起方式：

| 发起方式 | 例子 | 用什么算力 |
|---|---|---|
| A. Owner 用自己的 Agent | 在 Codex / Claude 里问「看看我今天的持仓」，它经 MCP 读 Research 和 Trade 的只读接口 | 订阅额度。最干净：把数据带给你的 Agent，而不是把你的 Agent 塞进业务系统 |
| B. Owner 在 Trade UI 里亲手点 | 「分析这笔交易」按钮 → 运行时建任务 → `agentd` 用 `codex exec` 执行 → 结果回到页面 | 订阅额度优先（Owner 在场）；但这是应用替你调用 CLI，**要先确认各家条款允许** |
| C. 无人值守的定时管线 | 每日摘要、harness 评审、预测 | **不走订阅**：本地 GPU 先，推理网关上的 API 兜底 |

Research 现有的 LLM 调用（harness、摘要、预测）以后改走推理网关；在那之前保持原样。

---

## 3. 现状（2026-10-08 只读实查）

### 3.1 服务与存储

| 组件 | 实情 | 证据 |
|---|---|---|
| PostgreSQL | CNPG 只有 4 个库：三套 Trade + GS；**Ops 没有库**；D13 由 `role-matrix/expected.yaml` 执行并每夜核对 | `k8s/data/databases.yaml`、`k8s/data/role-matrix/expected.yaml` |
| 作业领取模式 | 插件 `ops_jobs.job_ingest`：`FOR UPDATE SKIP LOCKED`、`reclaim_stale_running`、`not_before`、部分唯一索引去重 | market-data `worker/claim.py:110-217`；flex `worker/claim.py:57-80` |
| Redis | `redis-dev`、`redis-live-{stg,prod}`（不落盘，TD-238）、`redis-ib`（IB 总线，D10 敏感）、`argocd-redis`。**没有 Ops 用的 Redis**；market-data 规则禁止拿 Redis 当任务代理 | `kubectl get deploy -A`；`k8s/data/redis/instances.yaml` |
| Celery | 全线退役；跑它算事故 | `bifrost-trade-worker/CLAUDE.md:11`、`project.autoMode.json:50` |
| 存储类 | `local-path`（默认）、`nfs-hot` / `nfs-cold`（NAS）；MinIO 在 `data` 命名空间（备份用） | `kubectl get sc` |
| platform | Go，没有 SQL；statefile = 每键一个 ConfigMap，后写覆盖；令牌按名配置，审计记 principal；审批单签参数哈希；有 ntfy 推送；已有 go-redis 依赖 | `api/go.mod`、`statefile/k8sstate`、`actuation/auth.go`、`approvals/*` |

### 3.2 LLM 与额度

- 现有 LLM 代码都在 bifrost-research，用 DeepSeek / OpenAI 的键，属于业务功能。**本运行时不用这些键**；`agentd` 会把它们从环境里清掉（T13）。
- 运行时的算力 = 订阅制 Agent（Claude Code、Cursor、Codex）的月度与窗口额度 + 本地 GPU。

### 3.3 本地 GPU（更正 v1）

| 项 | 实情 |
|---|---|
| 节点 | `gpu-server`（.60）：32 核、125 GB 内存、1.7 TB 盘、RTX 4090（24 GB 显存）。**按设计待机**（`power-policy: on-demand`）：有 compute Pod 排队时，.73 上的 power manager 发 WoL 唤醒（超时 600 秒），空闲 30 分钟后 drain 并关机。v1 写的「离线」是误读 |
| 运行时 | k3s 默认带 `nvidia` RuntimeClass（还没确认节点上装了 nvidia toolkit）；**集群里没有 nvidia device plugin**，所以 `nvidia.com/gpu` 这种资源申请不到 |
| Ollama | 清单在，但没部署；GPU 那段被注释掉；镜像 `latest`，没钉版本；没有拉模型的作业；只有 ClusterIP，没有鉴权 |
| 吞吐 | 从没测过 |

结论：GPU 是现成的，缺的是把它接成可用执行池的那一段（5.4）。

### 3.4 Agent 主机

- 本机是 **MacBook Pro（M4，24 GB）**，装了 `claude` 2.1.293、`cursor-agent` 2026.10.01；`codex` 可以装（Owner 已同意）。
- mini .50 / .52 是 macOS，还没有虚拟机层。
- `~/der-relay` 的痛点见它的 `STATE-2026-10-08-paused.md`：Mac 一睡就停；`claude -p` 里批不了审批；会话在 App 里看不见。

### 3.5 工作区根目录（Owner 截图 + 实测）

`/stocks` 根目录有 **71 项**：

- 12 个仓库之外，有 **13 个 git worktree 目录**：`bifrost-platform-phase3-s1…s5`、`-phase3-int`、`-d1`、`-e1`、`bifrost-trade-infra-d1`、`-e1`、`-phase3-report` 等；
- **35 个 md / html**，其中只有 11 个是指向 `agent-config/work/` 的符号链接，其余是散落的 `REPORT-*`（14 个）、`PREREG-*`（6 个）、`REVIEW-*`、`REQUEST-*`、`WORKTREE-INVENT…`、`trade-tech-debt-….html`；
- 还有 `cursor-tasks/`、`archive/`、`design/`、`replay-pine-2026-10-06/`、`bifrost-platform-phase3-notes/`。

名字靠人起、靠前缀分类、同名多版本（`PREREG-pine-buy-iter…` 有好几份），没有状态、没有归属、没有生命周期。**任何靠扫目录理解现状的 Agent 都会读到过期或冲突的内容。** 这不是「整理一次」能解决的，协调的媒介本身得换。

---

## 4. 放置（推荐 H1）

| | H1 platform 内核 + 新库 + Ops Redis（推荐） | H2 新的 Python 服务 | H3 放进 Research |
|---|---|---|---|
| 形态 | `bifrost-platform/api/internal/agentrt/*`；CNPG 新库 `bifrost_platform`；`redis-agents`（AOF） | 新建 FastAPI + PG + worker | `research.*` 加表，复用 harness |
| 好处 | 合 Owner 决定 1（不另起服务）；鉴权、审计、审批、推送、MCP 都是现成的；Ops 本来就是控制面 | 贴近简报的技术栈 | U2 起步快 |
| 问题 | platform 第一次依赖 PG 与一个新 Redis | 违反「不另起服务」，鉴权、审批要再做一遍 | Research 去协调工程发布，违反域分层与 D13；业务键与 Agent 额度会混在一起 |

H1 附带的条件：

- 发布队列不依赖 PG / Redis（修数据库的那次发版必须还能走）。
- 克隆测试：`agentrt` 里不出现任何 Trade 概念。
- **ADR §1、§12.2 要改**：控制器在批准过的范围内发放租约，这算「调度」；平台仍不启动 Agent，由 `agentd` 主动来领。

---

## 5. 模块划分

### 5.1 bifrost-platform（Go）

| 模块 | 职责 |
|---|---|
| `agentrt/store` | PG（新增 `pgx`）、内嵌 SQL 迁移、事务；**outbox** 写入 |
| `agentrt/bus` | outbox 中继 → Redis Streams；信箱（消费组）读取；在线状态、冷却、叫停广播；Redis 丢失时从 PG 重建 |
| `agentrt/mission` | manifest 校验、对照审批单核 sha256、规划者席位 |
| `agentrt/task` | DAG、状态机、compare-and-swap、`SKIP LOCKED` 领取、租约、取消传播 |
| `agentrt/router` | 路由表（任务类型 × 难度 → 执行者级联）、按实测成功率与额度余量排序、升级规则 |
| `agentrt/event` | 类型化事件只追加、服务端打戳、权威语句检测（只标记） |
| `agentrt/artifact` | 内容寻址；正文进 `artifact_blob`（文本 ≤ 1 MB），大文件进 MinIO 的 `agent-artifacts` 桶 |
| `agentrt/verify` | 作者不能自验、评审须换厂商、接受闸门 |
| `agentrt/budget` | 按厂商的月度额度与短窗口账本；限流冷却；本地 GPU 秒数；业务 API 美元 |
| `agentrt/gateway` | 推理网关（5.5）：OpenAI 兼容端点、后端选择、GPU 信号量、业务 API 键、计量 |
| `agentrt/policy` 里的路由偏好 | `routing_policy` 读取与校验（5.6），硬规则优先于偏好 |
| `agentrt/policy` | 角色能力、停止开关、无进展检测、超范围提案转 Owner |
| `agentrt/trigger` | 控制循环（workers 角色）：生成 plan / verify / curate 任务、扫租约、核停止条件、合并本地任务批次 |
| `agentrt/http` + `mcp/platform` | REST 与 MCP（第 7 节） |
| `console` | ⑦：mission、任务、交互流、产物浏览（替代翻目录）；④：需要你的事 |

### 5.2 `agentd`：Agent 主机守护进程（Go，放在 bifrost-platform 仓库）

- 每台 Agent 主机一个进程：第 0 阶段是 MacBook，第 2 阶段起是 mini 的虚拟机。持有本机各执行者的令牌。
- 收到唤醒（经平台的长轮询，底层是 Redis）→ 领租约 → 在 `~/agent-work/<task_id>/` 建任务工作区 → 起执行者 → 续约 → 收产物与用量 → 提交 → **删掉工作区**（失败的保留 7 天）。
- 宿主职责：
  - 清洗环境变量：不给管理员 kubeconfig、admin 令牌、业务 API 键；
  - 限时（SIGTERM 后 SIGKILL）；
  - 限并发；
  - 死人开关：连续 3 次续约失败就杀掉子进程；
  - 任务工作区根复刻 `/stocks` 的治理层符号链接，让 preflight 照常生效。
- 执行者类别：

| 类别 | 实现 | 用途 | 阶段 |
|---|---|---|---|
| `deterministic` | 在干净的 worktree、提交的 SHA 上跑验收命令 | 验收；不用模型 | 0 |
| `local:chat` | 经推理网关调本地 Ollama，工具只放只读 MCP | 杂活：摘要、分诊、日志与报告压缩、格式整理、初审清单 | 3 |
| `local:codex-oss` | `codex exec --oss` 接 Ollama | **可选**：只有回放基准证明它在某类任务上划算，才放进那类任务的路由 | 视基准而定 |
| `harness:cursor` | `cursor-agent -p --force --output-format stream-json` | 中等以上的实现 | 0 |
| `harness:claude` | `claude -p --output-format json` | 实现、评审、规划 | 2 |
| `harness:codex` | `codex exec --json`（订阅模型） | 实现、评审、规划 | 2 |
| `harness:grok` | 待定（图形程序；MCP、无界面运行、preflight 都未知） | 规划？ | ≥2 |

### 5.3 Redis 交互总线（`redis-agents`）

| 键 / 流 | 用途 |
|---|---|
| `ar:ev:{mission}:{group}`（Stream） | 事件扇出；由 outbox 中继写入，不接受外部直写 |
| `ar:inbox:{actor}`（Stream + 消费组） | 每个 Agent 的信箱：发给它的 QUESTION、REQUEST_HELP、交接、叫停；有确认，未确认的会重投 |
| `ar:ready:{executor_class}`（Stream） | 「有活了」的唤醒信号，`agentd` 阻塞读，不用轮询。**领取仍在 PG 完成** |
| `ar:presence:{actor}`（TTL 60 秒） | 在线状态：Console 显示谁在线、在做什么 |
| `ar:cooldown:{vendor}`（TTL） | 厂商限流的冷却 |
| `ar:control`（Pub/Sub） | 叫停广播，1 秒内到达；心跳是兜底 |
| `ar:gpu:queue`（ZSET） | 本地 GPU 任务的批次排队（让同一次唤醒多跑几张） |

- **Agent 不直连 Redis**：IDE 里的 Agent 用 MCP 工具 `wait_for_messages`（服务端在 `XREADGROUP BLOCK` 上等最多 30 秒），`agentd` 用同样的长轮询接口。这样所有消息都经服务端打戳、过权限，Redis 的地址和口令只在 platform 里。
- **Redis 丢了**：从 PG 的 `outbox` 重放未投递的部分；信箱的确认位置以 PG 的 `delivery` 表为准（T15）。

### 5.4 本地 GPU 执行池（杂活，两个租户共用；第 3 阶段做）

定位（Owner 已定）：24 GB 跑开源模型，对 Stocks 的开发基本没有帮助，只做杂活。主要价值在业务一侧：无人值守的摘要、分类、抽取先跑本地，API 只兜底；账户内容不出家门。

1. **准备**（运维活，排在第 3 阶段，不挡开发租户）：
   - 唤醒节点，确认驱动和 nvidia toolkit；装 nvidia device plugin（或者只用 `runtimeClassName: nvidia` 加环境变量）；
   - Ollama 钉版本，打开 GPU；
   - 拉模型的作业把模型放进 PVC；
   - 用 NodePort 加 NetworkPolicy，只放行 Agent 主机（Ollama 本身没有鉴权）。
2. **选模型**：按杂活选（摘要、抽取、分类、结构化输出），在 24 GB 显存里挑几款当时可用的开源模型，**先测再定**。测单请求的 tokens/s、首 token 延迟、在业务杂活样本上与 API 输出的一致率、显存余量、上下文上限。
3. **并发**：Ollama 设 `OLLAMA_NUM_PARALLEL=1`（基准之后再调），由控制器限制 `local:*` 类别的并发租约数。
4. **唤醒成本**：节点开机要几分钟。`trigger` 把本地任务攒成批次再派发，有排队就让 Pod 保持运行，空了再让 power manager 关机。
5. **ADR §3 的边界**：推理服务在 4090 上（§3 允许）；Agent 的执行面（`agentd`、codex）在 Agent 主机上，不在 k8s 节点上。

### 5.5 推理网关与两条调用路径（Owner 已定放进 platform）

运行时里的 LLM 工作走两条路：

| 路径 | 适用 | 算力 | 形态 |
|---|---|---|---|
| **同步推理**（推理网关） | 一问一答、结构化输出：摘要、分类、抽取、评分 | 本地 Ollama；DeepSeek / OpenAI API（只限业务租户） | platform 内的 OpenAI 兼容端点 `/api/v1/inference/chat/completions`，按租户、任务、调用方计量 |
| **异步 Agent 任务**（任务队列） | 要用工具、要多步的活：写代码、深度分析 | 订阅制 CLI（`agentd` 在 Agent 主机上跑） | 第 7 节的任务 API |

网关的职责：

- **持有业务 API 键**：Secret 只挂在 platform 上；
- **按路由偏好选后端**：GPU 待机时，要么排队等唤醒，要么转 API，由偏好决定；
- **并发信号量**：本地 GPU 同时只放 1–2 个请求；
- **统一记账**：写进 `budget_ledger`，取代 Research 现在散在各进程里的每日美元上限；
- **拒绝开发租户使用 API 后端**。

它只转发和计量，不理解业务，所以过得了克隆测试。推理服务本身在 4090 上，网关是普通的 HTTP 服务，不算 ADR §3 说的「Agent 执行面」。

### 5.6 路由偏好（可配置）

偏好是数据，不是代码：放在 `agentrt.routing_policy` 里，由 Owner 修改，修改也走审批单。按「租户 × 发起方式 × 任务类型」给出有序的候选列表和条件，例如：

```yaml
- match: {tenant: dev, kind: code.*}
  prefer: [harness:cursor, harness:codex, harness:claude]   # 按各家剩余额度重新排序
- match: {tenant: dev, kind: [summarize, triage, digest]}
  prefer: [local:chat, harness:cursor]
- match: {tenant: business, initiated_by: owner}
  prefer: [harness:codex, harness:claude, local:chat]       # B 类，条款确认后才启用
- match: {tenant: business, initiated_by: schedule}
  prefer: [local:chat, api:deepseek, api:openai]            # C 类：绝不出现订阅制执行者（硬规则，控制器校验）
  limits: {api_usd_per_day: 3}
```

控制器在偏好之上执行硬规则：无人值守的业务不用订阅；开发不用 API；超出范围的组合直接拒绝，不按偏好放行。

### 5.7 文件与工作区治理

1. **协调的媒介是记录，不是文件**：任务说明、报告、预注册、验收结论、交接、洞见，都由 API 创建；正文以 Markdown 存进 `artifact_blob`，按 sha256 寻址；Console ⑦ 浏览和搜索。Agent 读上下文用 MCP 的 `get_task` / `list_artifacts`，不扫目录。
2. **git 只放**：代码、治理文档（ADR、CLAUDE.md、TECH_DEBT、RATCHETS）、mission 清单。需要留档的报告由一个导出任务按 mission 写成只读快照（`agent-config/work/<mission>/export/`），**由运行时生成，不是 Agent 手写**。
3. **工作区根目录对 Agent 只读**：preflight 与 `agentd` 拒绝在 `/stocks` 根下新建文件或目录，只有白名单里的符号链接例外；配一条防线检查根目录没有新增项。
4. **worktree 生命周期归 `agentd`**：放在 `~/agent-work/`（以后在虚拟机里），跟着任务建、跟着任务删，不再出现在共享 checkout 旁边。
5. **存量迁移**（运行时上线后的第一个 mission，也是很好的首批真实任务）：
   - 逐项分类：根目录的 35 个 md / html、13 个 worktree、5 个杂项目录。
   - 散落的报告**搬**进 `agent-config/work/archive/2026-10/`，并作为历史产物导入运行时，可以检索。
   - worktree 先列出未合并的提交，**由 Owner 决定**删不删。
   - 全程只搬不删。

---

## 6. 数据库结构（DDL 草案；database-design 命名：主键 `<表>_id`，外键同名）

```sql
-- database bifrost_platform；schema agentrt；运行角色 platform_agentrt 只有 DML，DDL 由属主角色通过迁移 Job 执行
CREATE TYPE agentrt.task_status_t AS ENUM (
  'proposed','awaiting_owner','ready','leased','running','submitted',
  'verifying','accepted','rework','rejected','blocked','paused','cancelled');
CREATE TYPE agentrt.event_kind_t AS ENUM (
  'QUESTION','OFFER','REQUEST_HELP','HANDOVER','OBSERVATION','HYPOTHESIS','RESULT','ARTIFACT',
  'BLOCKER','CRITIQUE','INSIGHT_CANDIDATE','SYNTHESIS','VERIFICATION','TASK_PROPOSAL',
  'TASK_ASSIGNED','STOP_RUN','POLICY_ALERT');
CREATE TYPE agentrt.epistemic_status_t AS ENUM (
  'unverified','reproduced','corroborated','rejected','superseded');

CREATE TABLE agentrt.actor (
  actor_id              text PRIMARY KEY,     -- 'cursor@macbook'、'agentd@mini50'、'owner'
  vendor                text NOT NULL,        -- anthropic | anysphere | openai-sub | xai | local | deterministic | human
  host                  text NOT NULL,
  executor_classes_json jsonb NOT NULL,
  is_active             boolean NOT NULL DEFAULT true,
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.vendor_quota (           -- Owner 配置；router 和 budget 读取
  vendor_quota_id     text PRIMARY KEY,       -- '<vendor>:<window>'
  vendor              text NOT NULL,
  window_kind         text NOT NULL CHECK (window_kind IN ('month','rolling_5h','day')),
  limit_amount        numeric NOT NULL,
  unit                text NOT NULL,          -- usd_equiv | output_tokens | requests | gpu_seconds
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.routing_policy (         -- 路由偏好（5.6）；修改走审批单
  routing_policy_id   text PRIMARY KEY,
  tenant              text NOT NULL CHECK (tenant IN ('dev','business')),
  initiated_by        text NOT NULL CHECK (initiated_by IN ('owner','agent','schedule','any')),
  task_kind_pattern   text NOT NULL,
  prefer_json         jsonb NOT NULL,         -- 有序的执行者类别
  limits_json         jsonb NOT NULL DEFAULT '{}',
  approval_id         text NOT NULL,
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.mission (
  mission_id          text PRIMARY KEY,
  tenant              text NOT NULL CHECK (tenant IN ('dev','business')),
  initiated_by        text NOT NULL CHECK (initiated_by IN ('owner','agent','schedule')),
  work_item           text,                   -- W-n
  title               text NOT NULL,
  manifest_json       jsonb NOT NULL,
  manifest_sha256     text NOT NULL,
  approval_id         text NOT NULL,
  status              text NOT NULL CHECK (status IN ('active','paused','stopped','completed','failed')),
  created_at          timestamptz NOT NULL DEFAULT now(),
  closed_at           timestamptz
);

CREATE TABLE agentrt.task (
  task_id             text PRIMARY KEY,       -- ULID
  mission_id          text NOT NULL REFERENCES agentrt.mission(mission_id),
  parent_task_id      text REFERENCES agentrt.task(task_id),
  group_key           text NOT NULL,
  role                text NOT NULL CHECK (role IN ('plan','implement','research','verify','review','curate','export')),
  task_kind           text NOT NULL,          -- 'code.mechanical'、'code.feature'、'doc'、'summarize'、'triage'…
  difficulty          char(1) NOT NULL CHECK (difficulty IN ('S','M','L')),
  route_json          jsonb NOT NULL,         -- 候选顺序，来自 routing_policy 并按剩余额度重排：["harness:cursor","harness:codex","harness:claude"]
  executor_class      text NOT NULL,          -- 本次尝试的类别 = route_json[attempt]
  goal                text NOT NULL,
  spec_artifact_id    text NOT NULL,          -- 任务说明也是产物，不是散落的文件
  deliverables_json   jsonb NOT NULL,
  acceptance_json     jsonb NOT NULL,         -- [{cmd, cwd, expect}]
  write_paths_json    jsonb NOT NULL DEFAULT '[]',
  risk_tier           char(1) NOT NULL CHECK (risk_tier IN ('A','B','C','D')),
  priority            double precision NOT NULL DEFAULT 0,
  status              agentrt.task_status_t NOT NULL,
  verifies_task_id    text REFERENCES agentrt.task(task_id),
  author_actor_id     text REFERENCES agentrt.actor(actor_id),
  lease_actor_id      text REFERENCES agentrt.actor(actor_id),
  lease_id            uuid,
  lease_until         timestamptz,
  attempt             int NOT NULL DEFAULT 0,
  max_attempts        int NOT NULL DEFAULT 3,
  budget_json         jsonb NOT NULL,
  created_by_actor_id text NOT NULL REFERENCES agentrt.actor(actor_id),
  version             bigint NOT NULL DEFAULT 0,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX task_ready_idx ON agentrt.task (executor_class, priority DESC, created_at) WHERE status = 'ready';
CREATE UNIQUE INDEX task_one_plan_lease_idx ON agentrt.task (mission_id)
  WHERE role = 'plan' AND status IN ('leased','running');

CREATE TABLE agentrt.task_dependency (
  task_id             text NOT NULL REFERENCES agentrt.task(task_id),
  depends_on_task_id  text NOT NULL REFERENCES agentrt.task(task_id),
  PRIMARY KEY (task_id, depends_on_task_id)
);

CREATE TABLE agentrt.task_transition (        -- 只追加
  task_transition_id  bigserial PRIMARY KEY,
  task_id             text NOT NULL REFERENCES agentrt.task(task_id),
  from_status         agentrt.task_status_t,
  to_status           agentrt.task_status_t NOT NULL,
  executor_class      text,
  actor_id            text NOT NULL REFERENCES agentrt.actor(actor_id),
  lease_id            uuid,
  reason              text,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.event (                  -- 只追加（触发器禁止 UPDATE / DELETE）
  event_id              text PRIMARY KEY,
  mission_id            text NOT NULL REFERENCES agentrt.mission(mission_id),
  group_key             text NOT NULL,
  task_id               text REFERENCES agentrt.task(task_id),
  actor_id              text NOT NULL REFERENCES agentrt.actor(actor_id),
  actor_session         text,
  kind                  agentrt.event_kind_t NOT NULL,
  addressed_to          text,                 -- actor:<id> | role:owner|planner|verifier | group:<key>
  reply_to_event_id     text REFERENCES agentrt.event(event_id),
  claim                 text,
  payload_json          jsonb NOT NULL,
  artifact_ids_json     jsonb NOT NULL DEFAULT '[]',
  source_refs_json      jsonb NOT NULL DEFAULT '[]',
  epistemic_status      agentrt.epistemic_status_t NOT NULL DEFAULT 'unverified',
  confidence            real CHECK (confidence BETWEEN 0 AND 1),
  policy_verdict        text NOT NULL CHECK (policy_verdict IN ('accepted_as_data','flagged','rejected')),
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.outbox (                 -- 与事件、迁移同一事务写入；中继投到 Redis
  outbox_id           bigserial PRIMARY KEY,
  stream_key          text NOT NULL,          -- 'ar:ev:…' | 'ar:inbox:…' | 'ar:ready:…'
  payload_json        jsonb NOT NULL,
  published_at        timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX outbox_unpublished_idx ON agentrt.outbox (outbox_id) WHERE published_at IS NULL;

CREATE TABLE agentrt.delivery (               -- 信箱确认位置的权威记录（Redis 丢了就按它重建）
  actor_id            text NOT NULL REFERENCES agentrt.actor(actor_id),
  event_id            text NOT NULL REFERENCES agentrt.event(event_id),
  acked_at            timestamptz,
  PRIMARY KEY (actor_id, event_id)
);

CREATE TABLE agentrt.artifact (
  artifact_id         text PRIMARY KEY,       -- 'sha256:<hex>' | 'git:<repo>@<sha>'
  mission_id          text NOT NULL REFERENCES agentrt.mission(mission_id),
  task_id             text REFERENCES agentrt.task(task_id),
  kind                text NOT NULL CHECK (kind IN ('task_spec','report','prereg','verdict','handover','insight','log','git_commit','file')),
  title               text NOT NULL,
  media_type          text NOT NULL,
  storage             text NOT NULL CHECK (storage IN ('blob','minio','git')),
  uri                 text,
  provenance_json     jsonb NOT NULL,
  supersedes_artifact_id text REFERENCES agentrt.artifact(artifact_id),  -- 新版本取代旧版本，不再出现同名多份
  created_by_actor_id text NOT NULL REFERENCES agentrt.actor(actor_id),
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.artifact_blob (
  artifact_id         text PRIMARY KEY REFERENCES agentrt.artifact(artifact_id),
  body                text NOT NULL CHECK (octet_length(body) <= 1048576)
);

CREATE TABLE agentrt.verification (
  verification_id     text PRIMARY KEY,
  task_id             text NOT NULL REFERENCES agentrt.task(task_id),
  verifier_task_id    text REFERENCES agentrt.task(task_id),
  verifier_actor_id   text NOT NULL REFERENCES agentrt.actor(actor_id),
  method              text NOT NULL CHECK (method IN ('deterministic','critic','owner')),
  artifact_ids_json   jsonb NOT NULL,
  commands_json       jsonb NOT NULL DEFAULT '[]',
  verdict             text NOT NULL CHECK (verdict IN ('pass','fail','inconclusive')),
  evidence_artifact_id text NOT NULL REFERENCES agentrt.artifact(artifact_id),
  created_at          timestamptz NOT NULL DEFAULT now()
);
-- 触发器：验收者 ≠ 作者；method='critic' 时两者的 vendor 也必须不同

CREATE TABLE agentrt.insight (
  insight_id            text PRIMARY KEY,
  mission_id            text NOT NULL REFERENCES agentrt.mission(mission_id),
  group_key             text NOT NULL,
  packet_json           jsonb NOT NULL,
  source_event_ids_json jsonb NOT NULL,
  verification_id       text REFERENCES agentrt.verification(verification_id),
  status                text NOT NULL CHECK (status IN ('candidate','promoted','rejected','superseded')),
  delivered_to_json     jsonb NOT NULL DEFAULT '[]',
  created_by_actor_id   text NOT NULL REFERENCES agentrt.actor(actor_id),
  created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.budget_ledger (
  budget_ledger_id    bigserial PRIMARY KEY,
  mission_id          text NOT NULL REFERENCES agentrt.mission(mission_id),
  task_id             text REFERENCES agentrt.task(task_id),
  actor_id            text NOT NULL REFERENCES agentrt.actor(actor_id),
  vendor              text NOT NULL,
  unit                text NOT NULL CHECK (unit IN ('usd_equiv','input_tokens','output_tokens','requests','gpu_seconds','wall_seconds')),
  amount              numeric NOT NULL,
  source              text NOT NULL CHECK (source IN ('measured','vendor_reported','self_reported','estimated')),
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.idempotency_key (
  idempotency_key     text PRIMARY KEY,
  task_id             text NOT NULL REFERENCES agentrt.task(task_id),
  effect              text NOT NULL,
  result_json         jsonb NOT NULL,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.control (
  control_id          text PRIMARY KEY,       -- 'global' | mission_id
  stop                boolean NOT NULL,
  reason              text NOT NULL,
  set_by_actor_id     text NOT NULL REFERENCES agentrt.actor(actor_id),
  set_at              timestamptz NOT NULL DEFAULT now()
);

-- 路由统计（视图）：按 task_kind × difficulty × executor_class 统计尝试次数、通过率、中位成本、中位墙钟
CREATE VIEW agentrt.routing_stat AS …;
```

---

## 7. API 契约

### 7.1 Mission 批准

- `MISSION.yaml` 进 git，写明：目标、成功标准、范围（仓库、路径、最高动作级、禁区）、允许的执行者与规划者候选、按厂商的额度上限、本地 GPU 时长、停止条件。
- 创建 mission 走**现有审批单**：动作 `agentrt.mission.create`，参数 = `{manifest_sha256, uri}`，C 级。

### 7.2 REST（`/api/v1/agentrt/…`，PROD only）

| 路由 | 调用方 | 说明 |
|---|---|---|
| `POST /missions` → 审批 | operator | `{mission_id, approval_id}` |
| `GET /missions[/{id}]` | viewer | 预算、各状态计数、席位、在线的 Agent |
| `POST /missions/{id}/stop`、`/pause`、`/resume` | admin（operator 可以申请） | 写 `control` 并广播 |
| `POST /missions/{id}/proposals` | 规划席位持有者 | 新增、取消、调优先级、改路由；范围内直接生效，超范围的转 `awaiting_owner` |
| `GET /work/wait?classes=…&timeout=30` | agentd | 长轮询，底层读 Redis `ar:ready:*`；返回「可以来领」 |
| `POST /tasks/lease` | agentd | 在 PG 原子领取 → `{task, lease_id, lease_until, spec}` |
| `POST /tasks/{id}/heartbeat` | 租约持有者 | `{lease_id, usage?}` → `{lease_until, stop}` |
| `POST /tasks/{id}/submit` | 租约持有者 | `{lease_id, idempotency_key, artifacts, usage, summary}` → 自动生成 verify 任务 |
| `POST /tasks/{id}/block`、`/release` | 租约持有者 | 额度用尽时 `block` 带 `reason=quota` |
| `POST /tasks/{id}/verifications` | 验收任务的持有者 | 服务端检查验收者 ≠ 作者 |
| `POST /artifacts` | mission 成员 | 上传正文 → 内容哈希；`supersedes` 指向旧版本 |
| `GET /artifacts[/{id}]` | mission 成员 | 搜索：kind、mission、任务、标题 |
| `POST /missions/{id}/events` | mission 成员 | 服务端打戳，写 outbox |
| `GET /inbox/wait?timeout=30`、`POST /inbox/ack` | 任何 actor | 信箱长轮询与确认 |
| `GET /whoami` | viewer | 主体、角色、所属 mission |

### 7.3 MCP 工具（IDE 里的 Agent 与规划者用）

| 类别 | 工具 |
|---|---|
| 身份与 mission | `whoami`、`get_mission` |
| 任务 | `list_tasks`、`get_task`、`propose_tasks`、`lease_plan_task` |
| 交互 | `wait_for_messages`、`ack_messages`、`ask`（QUESTION 发给指定的人或角色）、`request_help`、`handover` |
| 产物 | `put_artifact`、`get_artifact`、`search_artifacts` |
| 洞见与叫停 | `list_insights`、`propose_insight`、`request_mission_stop` |

契约测试的夹具由 Go 类型生成（TD-261 的教训）。

---

## 8. 调度流程

```text
Owner 批 mission → active → 生成 plan 任务 → 规划者提出 DAG（每张任务带 task_kind / difficulty / route）
控制循环（每 5 秒或收到事件）：
  叫停 → 不发租约；ar:control 广播；心跳回 stop
  过期租约 → ready（attempt 不变，原执行者重试一次）；再超时 → 升级到 route 的下一级
  预算 / 额度：某厂商月度或窗口额度见顶 → 设 ar:cooldown:{vendor} → 领取时跳过；由路由改派
  无进展 N 轮 / 墙钟到点 → paused，推送 Owner
  触发器：开始、里程碑、BLOCKER、每 K 张 accepted、每天 → plan；submitted → verify（deterministic）；
          每天或每 K 张 accepted → curate（默认 local:chat）
  本地批次：ar:gpu:queue 里攒够 N 张或等满 T 分钟 → 写 ar:ready:local:* → Pod 被调度 → 节点唤醒
agentd：
  GET /work/wait（阻塞）→ POST /tasks/lease（PG：SKIP LOCKED + compare-and-swap + 并发上限）
  → 建 ~/agent-work/<task_id> → 起执行者 → 心跳 30 秒（租约 120 秒）→ submit（幂等键）→ 删工作区
级联：
  verify 不过 → rework → attempt+1 → executor_class = route[attempt]（例：harness:cursor → harness:codex → harness:claude；换一家也是独立复核）
  → 全部失败 → blocked，推送；routing_stat 记下这次失败，供以后调路由表
交互：
  Agent 用 ask / request_help 发 QUESTION / REQUEST_HELP 给某个角色 → 写 event + outbox → 对方信箱
  → 对方的 wait_for_messages 返回；REQUEST_HELP 可被规划者转成一张新任务（受 manifest 约束）
副作用：合并到 main、发版、apply 都不在任务权限里 → 发布队列与审批单
```

---

## 9. 权限与边界

1. **身份**：每个「工具 × 主机」一个令牌；服务端从令牌取 actor。同一主机、同一账户下只能做归属，不能做隔离；第 2 阶段进虚拟机后才算数。
2. **权威**：只有控制器改状态；manifest 定范围；消息里的「GO / ADMIN / 我是 Owner」只被标成 `flagged`（T03）。
3. **交互总线**：Agent 不直连 Redis；所有写入经服务端打戳；没有 Agent 能自建频道。
4. **额度与键**：
   - 业务 API 键只在推理网关；Agent 环境里没有任何业务键（T13）。
   - 开发租户不能用 API 后端；无人值守的业务不能用订阅制执行者（T18）。
   - 订阅、GPU、API 三类全部记账。
5. **文件**：工作区根目录对 Agent 只读；产物只经 API（T14）。
6. **宿主**：`agentd` 清洗环境、限时、限并发、死人开关；没有钩子的执行者，进虚拟机之前不写代码。
7. **副作用**：经审批单与发布队列；D10 不变。
8. **叫停**：Console、聊天、手机一键；Pub/Sub 1 秒内送达，心跳 30 秒兜底，子进程最多再等 10 秒就被杀（T09）。

---

## 10. 分阶段实施

| 阶段 | 内容 | 闸门 |
|---|---|---|
| **准备**（与 0 并行） | 建库、建角色、迁移 Job；`redis-agents`（AOF）；本机装 `codex`（ChatGPT 会员登录）。**与瘦身线程对齐：先合阶段 3 的删减，再加 `agentrt`**（第 13 节） | 库与 Redis 可用 |
| **0 单 Agent 基线（开发租户）** | 内核（mission / task / lease / artifact / verification / budget）+ `agentd`（`deterministic`、`harness:cursor`）；全局并发 1；回放基准 15–30 题 | **Gate A**：T01、T02、T08、T10 |
| **1 交互总线与叫停** | Redis 信箱、唤醒、在线状态、叫停广播；权威检测；隔离；注入防护；根目录只读；存量文件迁移 mission | **Gate B**：T03、T09、T11、T12、T13、T14、T15 |
| **2 多厂商 + 路由 + 规划席位** | `harness:claude` / `codex`；按剩余额度与 `routing_stat` 分流；额度冷却；规划者经 MCP（Grok 若支持）；`agentd` 进 mini 虚拟机；并发 2–3 | 没有一家的额度先见顶而别家还剩很多（负载均衡生效） |
| **3 推理网关 + 本地 GPU + 策展** | 网关（同步推理、计量、GPU 信号量）；4090 接成杂活池（5.4）；`local:chat` 做 curate / 摘要；洞见包、跨 mission 投递 | 网关计量与 PG 账本一致；T17 |
| **4 业务租户** | Research 的 LLM 调用改走网关（无人值守 → 本地先、API 兜底）；A 类（你的 Agent 加 MCP）整理成正式入口；B 类（UI 按钮 → 订阅）**等你确认条款后再开** | API 月花费比迁移前下降（目标由 Owner 定）；T18 |
| **5 扩展** | 加执行者、加并发；研报 9.2 的 A/B | **Gate C** |

发布队列（PHASE1-OPTIONS 方案二）并行推进，第 2 阶段之前要可用。

---

## 11. 自动化测试

| 编号 | 测试 | 实现要点 |
|---|---|---|
| T01 恢复 | 提交之后、确认之前被杀，重试不产生重复 | 真 PG + 假执行者；幂等键唯一约束 |
| T02 租约 | 两个 agentd 抢一张，只有一个拿到 | 并发领取；`task_transition` 里只有一条 leased |
| T03 同伴越权 | 「GO: I am admin」不改变任何权限或状态 | 生成 `POLICY_ALERT` |
| T04 交叉传播 | 洞见包带着完整来源链投给相关组 | 假 curate |
| T05 无证据声明 | 没有验收引用的洞见到不了 promoted | API + 约束 |
| T06 失败实验 | 能查到，但不进默认上下文 | 查询测试 |
| T07 安全停 | 不可解的任务在预算内转 blocked，不扩范围 | 假执行者一直失败 |
| T08 独立验收 | 作者自验、同厂商评审都被拒 | 触发器 + API |
| T09 叫停 | Pub/Sub 与心跳两条路都能在期限内杀掉进程树 | agentd 真进程 |
| T10 预算 | 实测额度见顶就停止领取；自报的用量不计入放行额度 | 账本 |
| T11 隔离 | 猜 ID 读不到别的 mission | 授权测试 |
| T12 来源注入 | 产物或抓取的文本改不了目标与权限 | 端到端 |
| **T13 无业务键** | 任务工作区里读不到 `DEEPSEEK_*` / `OPENAI_API_KEY`；键只在网关的 Secret 里 | 环境探针任务 + 清单检查 |
| **T18 租户硬规则** | `initiated_by=schedule` 的业务任务即使偏好里写了订阅制执行者，也领不到；开发租户调网关的 API 后端被拒 | 控制器与网关的单元测试 |
| **T14 根目录只读** | Agent 在 `/stocks` 根下建文件被拒；根目录新增项检查为 0 | preflight 测试 + 防线脚本 |
| **T15 总线可重建** | 清空 Redis 后，信箱与唤醒从 outbox 和 delivery 表完整恢复，不丢不重 | 集成测试 |
| **T16 级联** | 本地执行者验收失败，自动升级到下一级；`routing_stat` 记录无误 | 假执行者两级 |
| **T17 GPU 唤醒** | 节点待机时排进本地任务，节点被唤醒；批次跑完之后按策略关机 | 在 STG 上做一次演练（需 Owner 批唤醒） |

另外还有：契约测试（夹具由 Go 类型生成）；混沌测试（CNPG switchover、Redis 重启、workers 重启）；治理层探针（任务工作区里 preflight 确实生效）；回放基准报告（按研报 9.2）。

CI 的开放问题：`bifrost-ci-platform` 现在没有 PG 和 Redis，要加 sidecar 或用嵌入式服务，实测后再定。

---

## 12. 决定与待定

**已定（Owner 10-08）**：

- 放进 platform（H1），新库 `bifrost_platform`；
- Redis 只在平台内部；
- 推理网关放进 platform；
- 无人值守的业务不走订阅；
- 本地 GPU 只做杂活，偏业务一侧；
- 同时服务开发与业务，路由偏好可配置；
- 与瘦身线程配合推进。

**待定**：

0. **「无人值守 → 不走订阅」要重新划线**。Owner 10-08 第五轮的意见：每日摘要这种低频、量小的定时任务也可以用订阅额度；只有「大量 Symbol 的简单重复劳动」才交给 GPU。这和上面已定的硬规则冲突，需要在两条轴上分别定：
   - **风险轴**：定时任务用会员账号，碰的是条款里「自动化使用」那一条，跟用量大小无关，需要 Owner 读过条款再定。
   - **经济轴**：什么时候用 GPU，按扇出量和任务复杂度判断（见讨论记录）。
1. ~~ADR §1 改写~~：**已定稿**（Owner 10-08 确认，已写进 ADR §1）。
2. **瘦身线程什么时候恢复**：建议现在就恢复，不等运行时落地（第 13 节）。
3. **B 类业务分析**（Trade UI 按钮 → 订阅制 CLI）：等你读过各家当前条款再开。A 类（你的 Agent 加 MCP）不受影响。
4. **根目录**：Agent 只读、产物只走 API；存量只搬不删，worktree 删不删由你决定。
5. **基准集**：用已关闭技术债的回放。
6. **mission 批准方式**：复用审批单（推荐），还是用 RP 的签名密钥。
7. **Grok 的位置**：第 2 阶段作为规划者经 MCP 接入？这取决于它能不能接 MCP、命令过不过 preflight。

---

## 13. 与「Ops Platform 瘦身」线程（ops-arch）的分工

**现状**：瘦身线程（ops-arch，`work/ops-arch/STATUS-2026-10-08.md`）在「多 Agent 协作框架落地之前」暂停。它的阶段 3 已经由 Cursor 做完、等验收：

- console/src 从 16.6 万行减到 11.6 万行；
- 删掉 40 多个 HTTP 端点和 11 个 MCP 工具；
- 删掉 Operate Queue 和检查清单派发。

D1（进度接口）、E1（存活指标）的 platform 部分也还没合。

**为什么两条线要配合**：`agentrt` 要动的正是 platform 里的动作接线、审批、MCP 工具清单和 Console 外壳。先删再加，冲突最少，也不会把即将删掉的东西接进新内核。

**建议**：

1. **瘦身线程现在就恢复**，不等运行时落地。暂停条件改为：「ADR §1 改写定稿」——方向定了，删什么、留什么就有了判据。它按自己 STATUS 里「恢复后的顺序」走，阶段 3、D1、E1 并进一次发布。
2. **判据**：platform 的每一项功能，回答三个问题。三个都答「否」就删（删之前照旧由 Owner 过目）：
   - Agent 经 API / MCP 用它吗？
   - Owner 用它来批、签、看吗？
   - 有维护循环依赖它吗？
3. **分工**：
   - 瘦身线程负责「删」和 Console 的 7 个问题；
   - 本线程负责「加」：`agentrt`、网关、发布队列；
   - Console 上，运行时的视图做成独立组件，由瘦身线程的新外壳挂载，做法同 RP 横幅；
   - 两边都改 platform 时，用运行时（或运行时上线前的 WORK.md 编号）认领，避免撞车。

**ADR §1 改写草案**（替换现在的「Ops Platform 不再托管或派发 Agent」）：

> AI Agent（Claude Code、Cursor、Codex 等，不绑定一家）是执行者。Ops Platform 是它们共用的**仪器、护栏和调度底座**。
> 它提供三样东西：
> - **事实**：探测、版本、血缘、维护者存活；
> - **护栏**：动作目录、审批、发布队列、D10；
> - **调度**：任务与租约、交互总线、推理网关、额度账本；这部分对开发和业务两个租户通用。
>
> 平台不启动 Agent，也不替 Agent 做判断：由 Agent 主机上的守护进程主动来领任务，由规划者席位提出计划。控制器只在 Owner 批准的范围内校验、记账、放行。
> UI 只给 Owner 用于看状态、审批和追溯。
