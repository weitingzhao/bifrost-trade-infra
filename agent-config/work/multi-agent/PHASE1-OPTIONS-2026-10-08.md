# 多 Agent 协作 第 1 期：发布队列的接口与存储（方案，待 Owner 选）

> **已收进设计 v4（2026-10-08）**：Owner 选了方案二与编号 ①；发布队列见 `DESIGN-agent-runtime-2026-10-08.md` 第 9 节，编号见第 10 节和 ADR §12.8。本文保留作历史。


2026-10-08，多 Agent 协作线程写。依据：ADR §12（12.4 规则、12.5 编号）。按 CLAUDE.md §5，新路由和新状态存储都算架构级改动，所以先列方案和推荐，Owner 定了再写 Cursor 任务。

---

## 1. 第 1 期范围（与方案无关）

- 发布窗口的权威从 Mac Pro 迁进 PROD platform；`release.sh window / hold` 改为调平台。
- 窗口变成队列，并发为 1；批准时钉住提交号；批准与执行分开（TD-267）；主机进程靠租约续约。
- 每个「工具 × 主机」一个令牌；窗口持有者按令牌主体认，不按请求体里的 `who`。
- Console ⑤ 显示队列。本机 Console 的审批页标明「本机环境」，给一个跳到 PROD 的链接。
- 工作项编号规则（第 5 节）及其防线。

## 2. 现状（读码所得，bifrost-platform origin/main 634e305）

| 事实 | 证据 |
|---|---|
| platform 没有数据库，`api/go.mod` 里没有 SQL 驱动 | `api/go.mod` |
| 状态存在 statefile 里：每个键对应命名空间里的一个 ConfigMap `platform-state-<key>`，上限 900 KiB，**后写覆盖**；api 与 workers 两个 pod 同时写同一个键会丢掉一次修改 | `api/internal/statefile/k8sstate/k8sstate.go` 头注释 |
| 审批在 approve 里**同步执行**；执行出任何错都记 `failed`，之后再 approve 返回 409 `already decided` | `api/internal/approvals/service.go` 的 `approve`（`actions.Execute` 与 `execErr` 分支） |
| 审批只收 C / D 级：B 级返回 400「直接调」，X 级 403 | `approvals/service.go` 的 create |
| 过期是惰性的，只在 list / get / approve / reject 时检查，没有后台循环 | `approvals/service.go` `expireLocked` |
| 窗口来自 ConfigMap `cicd/bifrost-release-window`（键 `window.json`）。没有窗口时只拒 research 与插件构建，Trade 与 platform 的 deliver 照样放行 | `api/internal/delivery/release_window.go` `decideReleaseWindow`、`guardedPipelineRepos` |
| 持有者比对的是请求体里的 `who` 字符串，从不和令牌主体对照 | 同上；`delivery/handler.go` |
| 令牌按 `{name, role, token_env}` 配在 `platform-auth.yaml`。加一个 `cursor@pro` 不用改代码；审计记的是 `principal.Name` | `actuation/auth.go`、`k8s/overlays/platform-prod/config/platform-auth.yaml` |
| MCP 从令牌文件只能读 3 个固定键，按工具分令牌要改 | `mcp/platform/src/tokenResolve.ts` |
| 后台循环用 `PLATFORM_ROLE=workers` 门控；PROD 的 api 与 workers 各 1 副本 | `config/role.go`、`server/server.go` |
| 手机推送：`approvalnotify` 只在建单时推；RP 分支加了通用的 `Notify(Message)` | `api/internal/approvalnotify/notify.go`、`cursor/rp-platform` f957cfd |
| `release.sh stg|prod` 在 Mac Pro 上用 Owner 的 kubeconfig 直接建 PipelineRun | `bifrost-trade-infra/scripts/release/release.sh` |

---

## 3. 三个方案

### 方案一：审批单就是队列

- **接口**：沿用 `/api/v1/approvals`，加状态 `approved`（已批、排队）→ `running` → `executed | failed`，再加 `stale`（需重批）。approve 只记决定，由 workers 里的执行器按批准时间取下一张。窗口另加 `/api/v1/release/window`，管租约。
- **存储**：现有的 `platform-state-approvals`，补上按版本写入（见方案二）。
- **好处**：改动最少，Console ④ 是现成的。
- **问题**：
  - 审批单只收 C / D 级。发 STG、research 与插件构建这些 B 级发布进不了队列，只能留一条旁路，队列就不是唯一通道了，和 Owner 定的「强制只在发布队列」矛盾。
  - 审批状态机是所有 C / D 动作共用的（DDL、drain 等），为发版改它会波及别的动作。
  - 主机上跑的 `release.sh` 没有可执行的「动作」，塞不进审批单。

### 方案二：队列单独成资源，审批只做决定（推荐）

- **接口**（只在 PROD 生效；STG 和本机 platform 只读或拒绝）：

  | 路由 | 权限 | 作用 |
  |---|---|---|
  | `GET /api/v1/whoami` | viewer | 返回令牌主体、角色、会话头 |
  | `GET /api/v1/release/queue` | viewer | 在队与最近结单，外加当前窗口 |
  | `POST /api/v1/release/queue` | operator | 提单 `{kind: run\|hold, what, env, pipeline?, revision, work, reason}`，返回单子；C 级且没命中策略时同时建一张审批单 |
  | `GET /api/v1/release/queue/{id}` | viewer | 单张 |
  | `POST /api/v1/release/queue/{id}/cancel` | 提单人或 admin | 撤单 |
  | `POST /api/v1/release/queue/{id}/renew` | 持有者（带 `lease_id`） | hold 单续约 |
  | `POST /api/v1/release/queue/{id}/finish` | 持有者 | hold 单结束，带结果 |
  | `GET /api/v1/release/window` | 匿名可读 | 由当前在执行的单子派生 |

- **两种单子**：
  - `run`：平台执行的发版动作，由 workers 执行器调用现有的 `start_pipeline_run` 或 Argo 同步；
  - `hold`：主机进程排到队首时领到 `lease_id`，自己执行，按时续约，结束时 finish。
- **状态**：`waiting_approval` → `queued` → `active` → `done | failed`，旁支有 `stale`（钉住的 SHA 已不是目标分支头）、`expired`（排队超过 24 小时）、`cancelled`、`lost`（租约断了，且它起的 run 已结束）。
  - 执行器约每 15 秒看一次队首。前提不满足就留在 `queued` 并写 `blocked_reason`，不消耗批准。前提包括：窗口空、没有同仓库的 run 在途、该 SHA 的 CI 已 Succeeded、批准或策略有效。
- **审批的分工**：审批单仍是「决定」的唯一记录，聊天、手机、Console 三个入口不变。发版类动作批准后不再同步执行，而是放行对应的队列单。非发版的 C / D 动作仍按原来的路径执行。
- **存储**：
  - statefile 新键 `release-queue`（ConfigMap `platform-state-release-queue`）。只留在队的单子和最近 200 张结单，长期历史靠审计与 release record。
  - 给 statefile 加**按版本写入**（ConfigMap 的 `resourceVersion` 比较后写，冲突就重读重算），api 与 workers 两个 pod 才不会互相覆盖。审批存储顺带用上。
  - 窗口对象 `cicd/bifrost-release-window` 改成**只由平台写**，内容格式不变，流水线第一个 task 不用改读法。所有 deliver 流水线改成没有窗口就拒（今天 Trade 与 platform 的 deliver 没窗口也放行）。
- **好处**：
  - B / C 级的发布、平台执行的和主机执行的，都走同一条队列，强制点只有一个；
  - TD-267 从结构上解决；
  - 不加外部依赖；
  - 状态留在 PROD 命名空间的 ConfigMap 里，已在集群状态备份范围内。
- **代价**：
  - ConfigMap 不适合放长期历史，有 900 KiB 上限；
  - 要改 statefile 这层共享代码；
  - platform PROD 的 ServiceAccount 要多一条写 `cicd` 里那个 ConfigMap 的权限（Owner apply）；
  - 续约每 30 秒写一次，只在有 hold 单在执行时发生。

### 方案三：队列单独成资源，存 Postgres

- **接口**：同方案二。
- **存储**：在 CNPG 上新建 `bifrost_platform` 库，用事务加 `FOR UPDATE SKIP LOCKED`。
- **好处**：并发语义最干净，历史可以随便查。
- **问题**：
  - platform 第一次依赖数据库，要加新驱动、新凭证、迁移，还要走数据库设计流程。
  - Postgres 出故障时发布通道跟着停，而修 Postgres 往往要先发版，这违反 §2 第 1 条「按什么坏了它还得活着放置」。
  - platform 本身负责修 CNPG（`repair_cnpg_wal_store`），修理者不该依赖被修者。

## 4. 推荐方案二

只有它能让队列成为**所有**发版的唯一通道，又不加外部依赖。方案一卡在 B 级发布和主机发布进不了审批单；方案三把发布通道绑在它要修的数据库上。

### 4.1 与方案无关、第 1 期都要做的

- **身份**：
  - `platform-auth.yaml` 为每个「工具 × 主机」加一条，第 1 期是 `claude@pro`、`cursor@pro`、`grok@pro`，角色都是 operator。Secret 的值由 Owner 建。
  - MCP 的令牌文件允许按工具配置键名。
  - 队列里的持有者记为「令牌主体 + 会话头」。请求体里的 `who` 只做显示用。
- **`release.sh`**：
  - `window` 改读平台；
  - `hold` 改成提 hold 单、等到队首、可被信号打断的续约循环、退出时 finish；
  - `stg|prod|dev` 先提 hold 单（钉住 SHA），轮到了再走原来的步骤。
  - 连不上 PROD platform 时直接拒绝；只有 Owner 能带 `--owner-break-glass` 走旧的本机窗口文件路径（preflight 拦 Agent 使用这个参数，平台恢复后补录）。
- **MCP 工具**：`whoami`、`request_release`、`get_release_queue`、`cancel_release`。`start_pipeline_run` 起 deliver 流水线时改为提单，返回单号。
- **推送**：复用 `Notify`，在这些时候推：要批、需重批（SHA 变了）、过期、租约断了、失败。
- **Console**：做成独立组件加数据 hook（`ReleaseQueuePanel`，以及本机审批页的环境横幅），不改外壳，由 ops-arch 第 3 阶段的新外壳挂载，做法同 RP 横幅。
- **防线**：
  - Go 测试：暂时性前提让单子留在队里；永久错误判失败；SHA 变了转 `stale`；租约断了但 run 在跑时不放窗口；两个写者并发写同一个键不丢更新；
  - shell 测试：`hold` 收到 SIGTERM 后几秒内 finish；
  - `check-release-chain.py`：每条 deliver 流水线的第一个 task 都读窗口，且没有窗口就拒。

### 4.2 已知的边界

Mac Pro 上的 Agent 今天还拿着管理员 kubeconfig，理论上能绕过队列直接建 PipelineRun。第 1 期用两道补：流水线第一个 task 没窗口就拒；preflight 拦 Agent 直接 `kubectl create` deliver 的 PipelineRun。彻底的办法是收回管理员凭证，那是 ops-arch 第 5 阶段的事。

---

## 5. 工作项编号：两个方案

**问题**：`LANE-<字母>` 由各计划目录自己起。Grok 在 `cursor-tasks/` 派的 `LANE-A2`、`LANE-C` 与 `ops-arch/` 的同名道重复。`lineage.sh` 与进度接口（`cursor/d1-platform` 里的 `progress/parse.go`，还没合并）都按 `LANE-[A-Z0-9]+` 字面匹配，`WORK.md` 的 W-9 又拿 `LANE-C` 当匹配键。实测撞名的提交：platform 1cf4d2c（Grok 的 A2）与 infra 470a14e（ops-arch 的 A2）；infra 92b4b0f、059e307（还债台账）带 `LANE-C` / `LANE-A2`。ops-arch 第 3 阶段分支上的提交没有 `Work:` 尾注（husky worktree 不跑钩子），所以历史上的误归属只有这几条。

### 方案 ①：一个号段（推荐）

- 新工作项一律用 `W-n`，Cursor 道也一样。道文件命名为 `W-<n>-<slug>.md`，尾注写 `Work: W-n`。
- **发号处**：第 2 期之前是 `WORK.md`，协调者先在 infra main 上加条目再派活。两个人同时拿同一个号时，后推的那个 push 会被拒（不是快进），rebase 后取下一个号。第 2 期起改由平台在认领时原子发号。
- **旧 `LANE-*`**：冻结为别名，只在唯一时有效。`LANE-A2`、`LANE-C` 两个作废，在 `WORK.md` 里不再作为任何条目的匹配键；相关条目改靠 TD-n / W-n 匹配。
- **防线**：`scripts/check_work_ids.py` 进 infra CI，检查四件事：
  - `### W-n` 不重号；
  - 所有 `匹配` 别名全局唯一；
  - 作废名单里的别名不出现在 `匹配` 里；
  - `agent-config/work/**` 下新出现的 `LANE-*.md` 不在冻结名单里就失败。
- `lineage.sh` 与进度接口的正则不用改。

### 方案 ②：保留 LANE，加计划前缀

- 每个计划一个前缀，登记在 `WORK.md`，例如 `LANE-OA-C`（ops-arch）、`LANE-DEBT-A2`（还债）、`LANE-MA-1`（本议题）。各计划线程自己发号。
- 要改 `lineage.sh` 和进度接口的提取正则。
- **问题**：发号的仍是多个人，前缀本身也要防撞；第 2 期的认领要的是单一编号空间，到时还得再迁一次。

**推荐 ①**：ADR §8 本来就规定只有一个工作项登记，认领也需要唯一编号；根因是多处各自发号，①直接去掉了这个根因。

---

## 6. 与在途分支的关系（需要 Owner 定顺序）

| 分支 | 状态 | 与第 1 期的关系 |
|---|---|---|
| LANE-RP：`cursor/rp-platform` f957cfd、`cursor/rp-infra` 9ad2baa | 做完、未合；`OwnerKeyFingerprint` 为空，合并后在 Owner 签发前什么都不会自动批 | 队列的「批准来源」之一。两条分支改的正是第 1 期要改的地方：`actions_wire.go` 的 guard、approvals 的 `SetAutoApprover`、`release.sh`、Tekton 的 release-window task。**建议 RP 先合，第 1 期从它开始**；需要有人验收 RP |
| LANE-M2：`cursor/m2-infra` 2440e54（TD-269） | 做完、未合、未验收；属于 Grok，暂停期间本线程不碰 | 第 1 期把 `hold` 重写成续约循环，M2 的修法会被覆盖。两条路：M2 照常等 Grok 恢复后验收合并，第 1 期在它之上改；或者 M2 不再合，由第 1 期关闭 TD-269 |
| LANE-D1：`cursor/d1-platform` a7b8681（进度接口） | 未合 | 方案 ① 不用改它的正则，只改 `WORK.md` |
| ops-arch 第 3 阶段：`cursor/phase3-platform` | 未合，在重写 Console 外壳 | Console 部分做成独立组件，由后落地的一方挂载 |
| ops-arch B1R 的审批代码 | 已在 PROD | 方案二会改 approvals 的「发版类动作批准后执行」这一段。开工前确认 ops-arch 没有同时在改它的道 |

## 7. 要 Owner 定的

1. 第 1 期选哪个方案：一、**二（推荐）**、三。
2. 编号选哪个：**①（推荐）**、②。
3. RP 由本线程验收、合并，作为第 1 期的起点？M2 走哪条路？
4. Grok Bot 在 Mac Pro 上靠什么执行命令（决定第 3 期迁到 mini 的难度，也决定第 1 期给它发 MCP 还是 HTTP 的令牌）。
