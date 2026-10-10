# S0-0「批准后由系统执行」：方案（W-37，只写方案，未实施）

- **状态**：方案草案，2026-10-10，W-37（W-31 第 0 步第 1 波第 4 步）。等 Owner 定第 6 节的 7 张决策卡。**实现要等 S0-8（W-42）合进 platform main**（`STEP0-PLAN` 0.4 节：`cursor/rp-platform` 也改 `approvalnotify/notify.go` 和 `approvals/service.go`）。
- **范围**：TD-286（审批体验）、TD-287（gpu-server 电源归同一个执行者）、TD-267（暂时性拒绝不消耗批准）合成一份方案；写清与 S0-8、TD-285（卡 4 = A）、TD-276、W-44、W-47 的接口。不改代码、配置、集群；不建审批单；不改 STEP0-PLAN、WORK.md、TECH_DEBT.md（第 8 节列出建议登记的内容，交台账维护线程）。
- **依据**：`STEP0-PLAN-2026-10-08.md` 第 0、0.1（D-19、D-21）、0.3（卡 1–4、手机端）、0.4（卡 A/B/C、顺序）节；`HANDOVER-step0-2026-10-08.md`「归第 0 步的新事项」第 1、2 条；设计 v4 第 9、17、18、19 节；ADR §1、§3、§5、§6、§12.2、§12.3、§12.8；TD-267、TD-276、TD-283–TD-287、TD-290；`design/uploads/ASK-ops-needs-you-and-team-rules-2026-10-10.md`（W-47）。
- **证据基线**：platform `origin/main` 75be701；infra `origin/main` 32c03f8；`origin/cursor/rp-platform` f957cfd。下文 `文件:行` 都指这几个提交。另有两项现场实测（10-10）：`ops.bifrost.lan` 的证书、动作目录计数。

---

## 0. 一页摘要

**现在**：Agent 用 `request_action` 建单 → Owner 在聊天、手机或 Console 批 → 平台在 `approve` 这一步**同步**执行。38 个动作里，36 个批准后由平台自己的受限身份执行；`owner_run_command` 和 `rolling_reboot` 两个 D 级动作**只记录**，返回 `executed_by_platform: false`，由 Owner 在 Mac Pro 上手敲 `owner-run.sh` / `rolling-reboot.sh`，用的是 Owner 目录里的管理员 kubeconfig 和带口令的节点钥匙。另有 `poweroff_compute_node` 虽然「执行」了，但 PROD 的 Pod 里没有 SSH 身份，必然失败（TD-287）。通知只有「谁申请了什么动作、几级」，没有编号、参数、环境、过期时间；投递结果只进日志，不存到单上。暂时性拒绝（比如发布窗口被别人占着）会把单子直接打成 `failed`，Owner 的那次批准就作废了（TD-267）。

**目标**：
1. 批准只负责「决定」，执行交给执行者。执行者分两类：
   - **平台内**：已有，用平台自己的受限身份，执行目录里的 36 个动作；
   - **带外执行器（新）**：放在 .50，独立的 macOS 账户，**只往外连**平台去领已批准的单子，执行后回写结果。它执行 `owner_run_command`、`rolling_reboot` 和 gpu-server 的唤醒与关机（TD-287）。
2. 审批记录加三个中间状态：`approved`（已批，排队等执行）、`running`、`unknown`（执行者失联）。暂时性拒绝留在 `approved` 自动重试，不作废（TD-267）。
3. 每张单子加一个**短数字编号 `#n`**，再由动作目录生成一行英文摘要：环境、关键参数。通知里写清编号、动作、级别、环境、摘要、发起线程、过期时间，**每次投递的结果存到单上**。
4. 手机按 Owner 10-10 的决定，改用主屏幕网页应用 + 网页推送：订阅存在平台，由 .50 发出；ntfy 只留给严重告警。
5. 会话里回「批 #n」，走 Claude 侧 `bifrost-approve` 的允许弹窗，不改变 ADR §5「聊天文字不构成审批」。
6. **D10 不进这条路**：创建时 X 级照旧拒绝；带外执行器上没有任何能碰交易的凭证；它的 kube 身份被准入策略挡住 daemon 扩容。

**选型**：执行器推荐**扩展现有的 operator-plane**（同一个 Go 二进制，以执行者角色另起一个进程）。几个现成的标准件直接用：launchd、OpenSSH 的 forced-command、Kubernetes ValidatingAdmissionPolicy（已在用）、W3C Push API / VAPID（RFC 8030 / 8291 / 8292）。自己只造三样：领单与回写的循环（约几百行）、状态机的扩展、动作摘要。

**要 Owner 定的**：执行器放哪、用什么（卡 1）；执行器持有哪些凭证，这里要改 ADR §3（卡 2）；状态机与接口变更（卡 3）；`#n` 编号空间（卡 4，涉及 ADR §12.8）；网页推送的新依赖（卡 5）；执行输出存哪（卡 6）；新状态先放 statefile 还是等 PG（卡 7）。

**拆道**（全部在 S0-8 合并之后）：S0-0a 状态机与编号 → S0-0b 通知文案与投递记录 ∥ S0-0d 会话「批 #n」→ S0-0c 带外执行器（含 TD-287）→ S0-0e 网页推送（等 W-44 的主屏幕应用外壳）。

---

## 1. 现状：从申请到通知，逐环

### 1.1 申请

| 环节 | 现状 | 证据 |
|---|---|---|
| 入口 | MCP `request_action`（要 `MCP_WRITES=on`）→ `POST /api/v1/approvals`，operator 令牌 | `mcp/platform/src/index.ts:502`；`mcp/platform/src/approvalTools.ts`（`requestAction`）；`api/internal/approvals/handler.go:28-31` |
| 定级 | 按动作目录和参数定级：B 级回 400「call directly」，X 级回 403，只有 C、D 级建单 | `api/internal/approvals/service.go:71-88` |
| 记录 | `appr_` 加 16 位十六进制；参数归一化后算 `params_hash`；ttl 24 小时；发起方取 `X-Bifrost-Session` 头 | `service.go:94-106`、`service.go:272-278`；`types.go:12`、`types.go:18-35`；`handler.go:142-147` |
| 存储 | statefile 键 `approvals`（PROD 是 ConfigMap `platform-state-approvals`）；保留全部未结的单子，加最近 500 张已结的。写入用的是 `WriteFile`，**不是**带冲突重试的 `Update` | `store.go:14-18`、`store.go:56-73`、`store.go:81-98`；`statefile/statefile.go:119-123`（`Update` 已有，审批没用） |
| 副本 | PROD platform-api 只有 1 个副本，但滚动发布时会短暂并存两个 Pod | infra `k8s/overlays/platform-prod/replicas-ha.patch.yaml:1-20` |

### 1.2 审批（三个入口，同一张表）

| 入口 | 现状 | 证据 |
|---|---|---|
| 聊天（只有 Claude） | `bifrost-approve` 的 `approve_request`，`channel` 固定为 `chat`，用 admin 令牌；Claude 的「允许」弹窗就是那次点击。Cursor 侧按设计没有这个工具 | `mcp/platform/src/registerApprove.ts:10-16`；根 `CLAUDE.md` §7 |
| 手机 | ntfy 推送，点开跳 `http://ops.bifrost.lan/#approvals?id=<id>`（注意是 http；站点实际走 https 加 http 跳转） | `api/internal/approvalnotify/notify.go:54-55` |
| Console | `#approvals?id=` 详情页；参数显示的是格式化后的原始 JSON；卡 A 定了：首页只列单子，批准和驳回只在详情页 | `console/src/pages/ApprovalsPage.tsx:164-168`；STEP0-PLAN 0.4 节卡 A |
| 权限 | 读：viewer；建单：operator；批准、驳回：admin | `handler.go:21-37` |
| 规则 | 批的是什么就只执行什么（执行用存下的参数，并复核 hash）；一次批准执行一次；过期作废 | `service.go:175-180`；ADR §5 |

### 1.3 执行：谁执行

`approve` 在同一步里调 `actions.Execute`：成功记 `executed`，**任何错误**都记 `failed`；而 `failed` 不能再批（`already decided`）。

- 证据：`service.go:152-204`（执行在 180 行，181–191 行写状态）、`service.go:172-174`；`actions/execute.go:24-35`。
- C、D 级的直接调用被 `guard` 拦下（403），只有执行器上下文能通过：`server/actions_wire.go:20-63`。

**38 个动作**（10-10 在 75be701 上数 `catalog.go` 里的 `ID:` 是 38 个，0.1 节 D-21 写的是 39，以这次为准）全都注册了执行器（`actions_wire.go:148-363`）。分类：

| 类 | 动作 | 批准后 | 证据 |
|---|---|---|---|
| 只记录（D） | `owner_run_command`、`rolling_reboot` | 返回 `recorded: true, executed_by_platform: false`，外加一条让 Owner 手敲的命令。`commandRunner` 只在测试里装 | `actions/actuation.go:26-27`、`actuation.go:123-146`；`actions/rolling_reboot.go:10-32`；`catalog.go:346-350`、`catalog.go:405-412` |
| 执行了但必然失败（D） | `poweroff_compute_node`（以及 B 级直调的 `wake_compute_node`） | 从 platform-api 里 SSH，PROD Pod 没有 SSH 身份（TD-287） | `cluster/node_power.go:248-254`；`catalog.go:213-223` |
| 平台内执行（C / D，按参数定级） | 其余需要审批的：发 PROD 流水线、PROD 的 Argo 同步与回滚、PROD 命名空间里的重启和扩缩、cordon、drain、CNPG 备份与 WAL 修复、数据克隆、IB 模式与维护、UniFi 防火墙、插件删除、apply_manifest、PROD 的 create_job 与 data 的 probe 等 | 平台用自己的受限身份同步执行。**`ensure_*`、`sync_kubeconfig` 这几个 D 级在 W-33 收权之后还能不能成功，本次没有实测** | `actions_wire.go:148-363` |
| B 级 | 窗口持有、mirror 同步、删 run、删 Pod、plan、wake 等 | 不进审批，直接调 | `catalog.go`，各项 `Tier: TierB` |

按静态级别数：C 级 11 个，D 级 10 个，按参数在 B、C 之间变化的 7 个，纯 B 级 10 个。

### 1.4 Owner 手工的那一段

- `owner-run.sh <id>`：用 PROD viewer 令牌读单子，要求 `action == owner_run_command` 且 `status == executed`；核对命令的 sha256；要求在终端里输入 `yes`；用 `OWNER_KUBECONFIG`（默认 Owner 目录里的管理员 kubeconfig）执行 `bash -c`；结果追加到 Owner 目录的 `run-log.jsonl`。**结果不回写平台。**
  - 证据：infra `scripts/owner/owner-run.sh:14`、`:79`、`:118`、`:125`、`:130`。
- `rolling-reboot.sh --execute --approval <id>`：同样核对单子；节点钥匙带口令，每台机器问一次（约 2 分钟时限，HANDOVER「这一轮学到的」）；有锁，可以用 `--done` 续跑。
  - 证据：infra `scripts/k3s/rolling-reboot.sh:3-6`、`:27-32`、`:49`、`:53`。
- 10-09 到 10-10 的实际情况（HANDOVER 第 1 条）：凡是要管理员 kubeconfig 或节点钥匙的步骤，都是 Claude 给命令、Owner 手工执行、Claude 再核对。实例包括 Prometheus 的 helm upgrade（TD-289）、`rolling_reboot`、三次插件和 pine 构建的 `kubectl create`（TD-284）、ib-gateway 的手工 apply（TD-285）。

### 1.5 审计

- 平台审计（PROD statefile 键 `audit-audit-api-json`）记录这几种：`approval.create`（动作、级别、发起方）、`approval.approve`（渠道）、`approval.execute`（状态或错误）、`approval.reject`、`approval.expire`。证据：`handler.go:52-55`、`handler.go:114-122`、`handler.go:136-138`；`service.go:253`。
- 缺口：
  - Owner 手工执行的结果只在 Owner 本机的 `run-log.jsonl` 里，平台不知道；
  - 「只记录」的动作在审计里显示 `executed`，看起来像已经执行了（TD-286：10-10 Owner 批了 `rolling_reboot`，单子显示 `executed`，其实只是记录了批准）；
  - apply 只记审批单号和 `plan_id`，不记 run 名（0.1 节 D-12）。

### 1.6 通知

- 建单成功后调一次 `NotifyCreated`，**返回的错误被丢掉**（`_ =`）。批准、驳回、过期、执行结果都不通知。证据：`handler.go:58-64`；`notify.go:1-30`（包注释）。
- 文案只有 `<who> requested <action> (tier X). Open to approve or reject.`，没有编号、环境、参数、过期时间。证据：`notify.go:103-117`。
- 路径：platform → .50 operator-plane 的 alert relay（`POST /api/v1/alerts/notify`）→ ntfy.sh。relay 只回 `sent`，不知道手机有没有显示。证据：`alertrelay/relay.go:263-293`；`cmd/operator-plane/main.go:68-80`。
- 10-10 实测（TD-286）：4 条审批消息都到了 ntfy，Owner 的手机一条也没显示。

### 1.7 缺口清单

| # | 缺口 | 归到哪 |
|---|---|---|
| G1 | `owner_run_command`、`rolling_reboot` 没有执行者；结果不回平台 | 带外执行器（2.2、S0-0c） |
| G2 | gpu-server 电源：平台的两个动作没有 SSH 身份；01 上那个服务每次关机都失败，还打印成功 | 同上（TD-287） |
| G3 | 暂时性拒绝会作废批准 | 状态机（2.4、S0-0a，TD-267） |
| G4 | 没有短编号；通知看不懂；投递结果不存 | 2.7、S0-0a / S0-0b（TD-286） |
| G5 | 手机：跳浏览器、令牌丢、通知没有状态 | 2.7、S0-0e（v4 §19，Owner 已定主屏幕网页应用） |
| G6 | 会话里只能靠弹窗批，而且要知道长 id | 2.8、S0-0d |
| G7 | 「只记录」显示成 `executed`，语义错误 | 状态机（2.4） |
| G8 | 审批存储写入不带冲突重试，滚动发布时两个 Pod 并存 | S0-0a 改用 `statefile.Update` |

---

## 2. 目标形态

### 2.1 原则

- **批准只负责决定，执行交给执行者。**和 v4 §9「独立的队列资源，审批只负责决定」同一个方向；发布队列以后会把发版类动作从这里接走（4.1）。
- **执行者主动来领**，平台不往外推命令（ADR §1「平台不启动 Agent」的同一个思路）。.50 只往外连 PROD VIP，不开任何入站端口。
- **批的是什么就只执行什么，一次批准最多开始一次执行。**唯一的幂等键是审批单号。
- **能进目录的就进目录。**`owner_run_command` 是兜底；同类命令出现第二次，就提议做成一个具名动作（防线见第 8 节）。

### 2.2 两类执行者与路由

| 执行者 | 在哪 | 身份 | 执行哪些动作 |
|---|---|---|---|
| 平台内（已有） | PROD platform-api | 平台自己的受限 ServiceAccount，受 TD-271 的准入策略约束 | 目录里除下面 4 个以外的全部 C、D 级动作 |
| 带外执行器（新） | Mac mini .50，独立的 macOS 账户 `bifrost-exec`，launchd 常驻 | 卡 2 定的专用凭证 | `owner_run_command`（`runner=system` 时）、`rolling_reboot`、`poweroff_compute_node`、`wake_compute_node`（B 级，直调时由平台建一张自动批准的单子交给执行器，让它也有记录） |
| Owner 手工（保留为兜底） | Owner 的 Mac Pro | Owner 目录里的凭证 | `owner_run_command`（`runner=owner`），即需要执行器没有的凭证的命令（子系统管理员密码、节点 root shell 等，卡 2）。`owner-run.sh` 继续可用，执行后**回写结果** |

路由写进动作目录（每个动作多一个 `Runner` 字段：`platform` / `host` / `owner`），不靠运行时猜。

### 2.3 身份与权限边界

- **执行器的平台令牌**：新角色 `executor`，只能领单、续租、回写结果；不能建单，不能批，不能读别的接口。它和 viewer、operator、admin 三种令牌都分开。
- **凭证只放在 .50 的 `bifrost-exec` 账户里**（权限 600），不在 Mac Pro 上，Agent 所在的账户读不到。这比现在 Owner 目录只靠 preflight 文本拦截（ADR §5 已知的接受风险）更硬。具体放哪些凭证见卡 2。
- **节点上的事用 OpenSSH forced-command**：每台节点的 `authorized_keys` 写成 `restrict,from="192.168.10.50",command="/usr/local/sbin/bifrost-node-maint"`，脚本只接受 `poweroff`、`reboot`、`upgrade-reboot` 几个动词（从 `SSH_ORIGINAL_COMMAND` 读）；sudoers 只放这一个脚本。这样拿到钥匙也开不了 shell（TD-287 的修法，推广到滚动重启）。
- **kube 写操作**：执行器的 kube 身份同样受准入策略约束（2.11）。
- .52 不跑执行器（和 alert relay 一样只开一处，避免两边各执行一次）；.50 坏了，就由 Owner 手工切到 .52，或者退回 `runner=owner`。

### 2.4 状态机、幂等与重试

```text
pending ──approve──▶ approved ──claim──▶ running ──▶ executed
   │                   │  ▲                  │          failed
   │                   │  └─暂时性拒绝────────┘(未开始时)   unknown ──迟到的结果──▶ executed / failed
   ├──reject──▶ rejected
   └──ttl────▶ expired         approved 超过执行期限 ──▶ expired
```

- **`approved`**：已经批准，排队等执行者。平台内执行的动作，approve 时仍然当场试一次（大多数一步就到 `executed`，和现在一样快）；只有暂时性拒绝才停在 `approved`。
- **暂时性拒绝 vs 永久错误**（TD-267）：执行器返回带类别的错误。
  - 暂时性：发布窗口被其他仓库占着、CI 还没过、同一流水线有 run 在跑、执行器暂时连不上。
  - 永久性：参数错误、动作被准入策略拒绝、plan 不是 ready。
  - 暂时性的留在 `approved`，按退避重试，记下 `attempts` 和 `last_refusal`，直到执行期限（C 级默认 1 小时，可以由策略收紧；发布队列上线后，发版类按它的「排队超过 24 小时过期」，ADR §12.7）；**不需要再点一次**。永久性的记 `failed`。
  - 只有「还没开始」的拒绝才会重试。已经建出 run 或已经启动命令的，不自动重试。
- **领单（claim）**：执行器带上自己能执行的动作类别来领；平台用 `statefile.Update`（ConfigMap 的 resourceVersion 冲突重试）把单子从 `approved` 改成 `running`，写入 `lease_id` 和租约到期时间（60 秒，执行器每 20 秒续一次）。两个领单请求只会有一个成功。
- **执行器自己的日志**：开始执行之前，先把单号 fsync 写进本地日志。重启之后，凡是日志里有的单号都不再开始，所以同一个单号绝不会开始两次。
- **失联**：租约过期 10 分钟仍没有续租，单子记为 `unknown`，**不自动重试**（D 级命令执行一半时重跑，比停下更危险），并发通知。执行器恢复后补交结果：同一个 `lease_id` 交上来的结果，平台接受一次，把 `unknown` 改成 `executed` 或 `failed`。
- **超时**：`owner_run_command` 默认 30 分钟，可以在参数里写 `timeout_minutes`（进 hash）；`rolling_reboot` 默认 4 小时；超时先发 SIGTERM，30 秒后发 SIGKILL，记 `failed`（`timeout`）。
- **apply_manifest 的重试**依赖 TD-276（run 名不能只是 `apply-<plan>`），所以 TD-276 并进 S0-0a。

### 2.5 失败回报

- 单子上：`execution.exit_code`、`started_at`、`finished_at`、`attempts`、`last_refusal`、`error`（一行）、输出摘要（卡 6）。
- 发起的会话：`wait_for_request` 把 `approved`、`running` 当作非终态继续等，`unknown` 当作终态（`mcp/platform/src/pollRequest.ts:1`）。一次最多等 600 秒；会话超时后可以再等，不用 Owner 介入（「等待中的会话自动继续」）。
- Owner：`failed`、`unknown`、执行期限内没执行成功而过期的，推送一条（只推需要他看的，ADR §6「计数只算需要你」）；执行成功不推送，只在「记录」里能查到。

### 2.6 审计

沿用平台审计（同一个键，同样的格式），新增这些事件：

- `approval.queue`：暂时性拒绝，附原因；
- `approval.claim`：附执行者 id 和 lease；
- `approval.run.start`、`approval.run.finish`：附退出码、用时、输出的 sha256；
- `approval.unknown`、`approval.late_result`；
- `approval.notify`：每个渠道一条，附投递结果。

`owner-run.sh` 执行后也回写一次（以 `runner=owner` 记），这样平台审计里能看到 Owner 手工执行的结果，`run-log.jsonl` 退成本机副本。

### 2.7 通知与手机入口

**编号**：每张单子一个全局自增的 `#n`（卡 4）。`GET /approvals/{id}` 和批准、驳回接口同时接受 `appr_…` 和 `n`。

**摘要**：动作目录里每个动作带一个 `Describe(params)`，生成环境、一行英文摘要和 2–4 个关键参数。例如：

- `start_pipeline_run` → env `prod`，`bifrost-deliver-platform-prod @ <short sha>`；
- `apply_manifest` → env 取 plan 里级别最高的命名空间，`k8s/ib-gateway/overlays/live · 3 objects`；
- `owner_run_command` → env `host`，摘要用申请时的 `reason` 第一行。**命令全文不进通知**，只在应用里看。

**推送文案**（英文，UI 字符串规则；一屏看完，和 W-47 ASK 的字段一致）：

```text
#57 · D · owner_run_command · cicd
Delete retired ConfigMap bifrost-remediation-runner-stg-dockerfile (TD-290)
from W-37 (claude) · runs on: system · expires in 23h
```

- 不带秘密和账户内容（v4 §19）。
- 网页推送的载荷是端到端加密的（RFC 8291），苹果的推送服务看不到正文，但仍然只放上面这几样。

**投递记录**存到单上（`deliveries[]`），每个渠道、每个目标一条：渠道（`webpush` / `ntfy`）、目标（订阅端点的 hash）、时间、结果（`accepted` / 状态码 / 错误）。手机上的 service worker 收到推送、显示出来之后，回调一次 `POST /approvals/{id}/delivery-ack`（viewer 令牌），把这条记成 `shown`。这样就能区分三种情况：「推送服务收了」「手机显示了」「Owner 点开了」。10-10 那种「ntfy 收了、手机没显示」以后在单子上看得见。注意：回调要连到平台，不在家里的网络、也没连 VPN 时没有 `shown`，单子上照实显示「未回执」。

**通道**（v4 §19 的候选，Owner 10-10 已经定了，这里不重新提议）：

| 候选 | 状态 | 本方案里的位置 |
|---|---|---|
| 主屏幕网页应用（PWA）+ 网页推送 | **已定**为手机的固定入口 | S0-0e（推送）+ W-44（应用外壳、manifest、service worker） |
| A 厂商 App 远程操控参谋长 | 保留，作为对话的补充 | 不在 S0-0 |
| B 聊天应用里的机器人 | Owner 排除 | — |
| C ntfy + 网页逐项修补 | 退为严重告警通道；S0-0e 上线之前，S0-0b 先在 ntfy 上改文案和投递记录 | S0-0b |
| D 原生 iPhone 应用 | Owner 否决 | — |

- 推送路径：platform 建单 → 把消息和订阅列表交给 .50 的 relay → relay 用 VAPID 私钥（只在 .50）签名，发给各订阅的推送服务（苹果的 web.push.apple.com 等）→ relay 把每个目标的结果回给平台。.50 只往外连，不开入口。
- 订阅存在平台（新 statefile 键 `push-subscriptions`，避开 D-21 列的 5 个现有键；卡 7）。
- **前提**（Owner 做，不是决策）：
  - 10-10 实测，`ops.bifrost.lan` 的证书由 **mkcert 开发 CA** 签发（2028-10-12 到期，Traefik 默认 TLSStore，infra `k8s/system/traefik-tlsstore.yaml`）。iPhone 要先装这个根证书的描述文件，并在「证书信任设置」里打开完全信任，service worker 和推送才能用。
  - 批准时要连到平台，所以要配按需 VPN（v4 §19：WireGuard 的按需连接，或者 Teleport 每次手动点）。只收推送不用 VPN。
- 提醒：待批超过 4 小时、离过期还剩 2 小时，各提醒一次，不另外加频率。
- S0-8 的策略到期提醒走同一个 relay，同样记投递结果（审计里记，不挂在审批单上）。

### 2.8 会话入口：「批 #n」

- **Claude**：Owner 在会话里打「批 #57」→ Agent 调 `bifrost-approve` 的 `approve_request`（S0-0d：参数同时接受 `#n`）→ Claude 弹出「允许」→ Owner 点允许才算批。ADR §5 不变：聊天文字本身不构成审批，审批以记录为准，那一下点击才是批准。「驳 #57 原因」同理。
- **Cursor**：按设计没有 `bifrost-approve`（根 `CLAUDE.md` §7）。Cursor 会话里只给出编号和应用里的链接，由 Owner 在手机或 Console 上批。
- 等待中的会话：`wait_for_request` 同样接受 `#n`，批准从哪个入口来都一样。

### 2.9 Console（W-44 的事，这里只给字段）

卡 A 和卡 B 已经定了版式和分组。S0-0a 只在接口里增加这些字段：`number`、`env`、`summary`、`key_params`、`runner`、`requester_thread`、`work_id`、`execution{}`、`deliveries[]`。并且 `GET /approvals?status=open` 返回 pending、approved、running、unknown 四种。

- 「进行中」段（W-47 ASK 第 7 问，等 Design 回答）有了真实数据：`approved`、`running`。
- 「需要你」的计数仍然只算 `pending`，再加上 `unknown`（要 Owner 看的）。
- `ApprovalsPage.tsx` 和 `api/approvals*.ts` 归 W-44，S0-0 不碰。

### 2.10 C 级与 D 级

| | C 级 | D 级 |
|---|---|---|
| 自动批准 | 发版类可以被 S0-8 的发版策略自动批（只在平台一处判定，卡 2 = B） | **永远不自动批**（ADR §5） |
| 执行者 | 平台内 | 平台内，或者带外执行器 / Owner（2.2） |
| 暂时性拒绝 | 留在 `approved` 自动重试，直到执行期限 | 只有未开始时才重试；已开始的不重试，失联就记 `unknown` |
| 手机上批 | 详情页点一次 | 多一步确认。**形式等 W-47 的设计答复**（二次点按、长按或输入编号）；后端统一要求批准请求带 `confirm_number`，并且等于 `#n`，phone 和 console 两个渠道都校验，chat 渠道靠弹窗 |
| 通知优先级 | 普通 | 高 |

### 2.11 与 D10 的关系：交易执行永远不进这条路

- **建单**：X 级照旧回 403（`service.go:79-84`；`scale_deployment` 对 daemon 扩容定为 X，TD-222）。`owner_run_command` 的命令全文要过一份拒绝清单，命中就定为 X、拒绝建单。清单放在 actuation policy 的配置里（infra overlay 的 `config/`），**平台只认「命中清单就是 X 级」，不认识清单里的业务词**，这样平台保持通用（双飞轮）。清单内容和 `preflight.js` 同源：`ib:operator:cmd`、`place_order`、daemon 扩容、`daemon-scale-zero` / `daemon-observe-safe` 的改动。
- **执行**：执行器开工前再对同一份清单查一次。
- **凭证**：.50 上没有 IB、Redis-IB、业务库的凭证；TWS 只在两台 Win11 上。执行器的 kube 身份由准入策略（ValidatingAdmissionPolicy，沿用 infra `k8s/platform-rbac/40-admission.yaml` 的做法）拒绝把 `daemon` 扩容到 0 以上、拒绝修改 D10 守卫的两个 patch 所管的字段。
- **规则集**：D10 不在规则集里（ADR §5、§12.4），任何发版策略或执行器配置都解不开它。

---

## 3. 现成组件选型

### 3.1 执行器（卡 1）

| 选项 | 怎么做 | 好处 | 代价 |
|---|---|---|---|
| **A. 扩展 operator-plane（推荐）** | 同一个 Go 二进制，用 `OPERATOR_PLANE_ROLE=executor` 在 .50 的 `bifrost-exec` 账户下另起一个 launchd 进程，不监听端口，长轮询 `POST /approvals/claim` | 二进制、发布方式、互看 watchdog 都是现成的；operator-plane 本来就设计成「集群坏了也能活」（`cmd/operator-plane/main.go:1-12`），正好是修集群的命令需要的；凭证在独立账户里；只往外连 | 自造领单与回写的循环（约 300–500 行加测试）；.50 坏了要手工切；macOS 上 launchd 的独立账户要 Owner 用管理员身份建 |
| B. 集群内 Tekton 的「owner-exec」流水线 | 批准后，平台建一个 PipelineRun，用专用 ServiceAccount 执行命令；节点钥匙放 cicd 的 Secret | Tekton 自带日志、重试、超时；已经在用 | **集群坏了就执行不了**，而 `owner_run_command` 很多时候正是用来修集群的；把高权限放进一个平台能触发的命名空间，和 TD-271 / TD-272 是同一类风险，还要再加一层准入策略；节点钥匙进集群 Secret，和 ADR §2「看守集群的在集群外」相反 |
| C. 现成的作业平台（Semaphore UI、Rundeck、AWX）放在 .50 | 平台批准后，调用它的 API 起一个任务 | 自带任务历史、日志、权限、定时 | 多一套审批和状态库、多一个界面和登录，和「一张审批表」「状态放我们的」（ADR §12.2 第 7 条）冲突；是平台推过去的模式，要在 .50 开入站端口；Rundeck 和 AWX 很重。三个问题（ADR §1）里只有「Agent 用不用」能答「是」 |

暂不考虑：Gitea Actions 的 runner。等 S0-4c 之后 Gitea 做主、升级到 1.27 以上再看；即使那时用它，审批和状态仍在平台，它只能替换 A 里「跑命令」的那一小段。

### 3.2 各部件用什么

| 部件 | 采用 | 自造的部分 |
|---|---|---|
| 常驻与重启 | launchd（KeepAlive）+ 已有的互看 watchdog | plist 一份 |
| 账户隔离 | macOS 独立用户 | 无 |
| 节点动作的权限 | OpenSSH `restrict` + `from=` + `command=` forced-command；sudoers 只放一个脚本 | 节点上的 `bifrost-node-maint` 脚本（只有 3 个动词） |
| kube 写的边界 | Kubernetes ValidatingAdmissionPolicy（已在用，不引入 Kyverno 或 OPA） | 两三条规则 |
| 字段归属 | Server-Side Apply（TD-285 卡 4 = A，`--force-conflicts`） | 无（在 S0-13） |
| 推送 | W3C Push API + VAPID（RFC 8030 / 8291 / 8292），Go 库 `webpush-go`（MIT；卡 5，开工前核实维护情况） | 调用代码 |
| 主屏幕应用 | Web App Manifest + Service Worker（标准；W-44 做外壳） | 推送订阅和回执的几十行（S0-0e） |
| 状态 | 现有的 statefile（ConfigMap，带冲突重试的 `Update`） | 状态机、领单、编号计数器 |
| 审计 | 现有的平台审计 | 新增几种事件 |
| 以后的身份确认 | WebAuthn 通行密钥（v4 §19「以后可选」） | 不在本期 |

### 3.3 自造的只剩这些

1. 审批状态机的扩展和领单接口（平台，Go）；
2. 执行器的领单、执行、回写循环和本地日志（operator-plane 的一个新包）；
3. 动作摘要 `Describe`（每个动作几行）；
4. 节点上一个三个动词的 forced-command 脚本。

每 90 天复核一次（ADR §12.2 第 6 条）：如果 Gitea Actions 或别的执行器已经能接我们的审批，就把第 2 项换掉。

---

## 4. 接口、先后顺序与拆道

### 4.1 与 S0-8（W-42，RP 合并）

- `cursor/rp-platform` f957cfd 改的地方：
  - `approvals/service.go`：加 `AutoApprover`；C 级建单时，命中策略就回 400 `call directly` 并带上 `auto_approved_by`；加 `Pending()`；
  - `approvalnotify/notify.go`：抽出 `send()`、`Message`、`Notify()`，给策略到期提醒用；
  - `server/actions_wire.go` 的 `guard`：命中策略的直调放行，并写审计。
- S0-0 **在这之上做**，不改它的语义：
  - 命中策略的发版仍然不建单、没有 `#n`，审计里记命中的条款；
  - 通知改造基于 rp 的 `send()`；
  - `Pending()` 继续给提醒用。
- 所以 S0-0a 必须在 W-42 合并之后从 main 开分支。
- 以后的发布队列（v4 §9：「单子在队首，由队列持有窗口」）会接手发版类动作的 `approved → 执行` 这一段。S0-0a 的 `approved` 加重试是它的最小形态，字段集中在 `execution{}` 里，方便以后整体搬走。

### 4.2 与台账里的几条

| 条目 | 关系 |
|---|---|
| TD-286 | 本方案就是它的 Fix。验收（「下一张 C 级单在手机上显示 `#n`、动作和环境，Console 里能看到投递状态」）由 S0-0a + S0-0b 满足；Console 显示的部分要 W-44 接 |
| TD-287 | S0-0c 的一部分：WOL 由 .50 发（不需要凭证）；poweroff 走 forced-command 钥匙；退役 01 上的 `bifrost-gpu-power-manager.service`；平台的两个动作改成 `Runner: host` |
| TD-267 | S0-0a 的状态机直接解决（2.4）；防线就是 TD-267 写的 Go 测试 |
| TD-276 | 自动重试 apply_manifest 的前提，并进 S0-0a |
| TD-285（卡 4 = A） | 第 2 波 S0-13 单独做，**不依赖 S0-0**。关系有两点：① applier 加了 `--force-conflicts` 之后，「Owner 手工 apply」这一类 `owner_run_command` 会消失，执行器上的 kube 权限可以更小；② `owner_run_command` 建单时如果命令里有 `kubectl apply`、`kubectl create -f`、`helm upgrade`，就在单子上提示「请改用 plan_manifest / apply_manifest」，只提示，不拒绝 |
| TD-283、TD-284 | S0-12 把它们接到平台动作上之后，又少两类 `owner_run_command`。不依赖 S0-0 |
| TD-290 | 建议作为 S0-0c 的**第一次真实演练**：删 ConfigMap 走 `owner_run_command`（`runner=system`），由系统执行并回写结果 |

### 4.3 与 W-44、W-47

- W-47 ASK 第 5 问说「短编号 `#n`、投递记录、发起线程，S0-0 后端做完才有，请先留位置」。字段名以 2.9 节为准。
- D 级多一步确认的形式等 W-47 的答复；后端的 `confirm_number` 不受形式影响。
- service worker 和 manifest 归 W-44。S0-0e 只新增推送订阅和回执的几个文件，由 W-44 的外壳挂载。

### 4.4 顺序

```text
W-42 (S0-8) 合进 platform main
  └─▶ S0-0a 状态机 · 编号 · 摘要 · TD-267 · TD-276
        ├─▶ S0-0b 通知文案与投递记录（仍走 ntfy）
        ├─▶ S0-0d 会话「批 #n」
        └─▶ S0-0c 带外执行器 · TD-287（要卡 1、卡 2，加上 Owner 在 .50 和各节点上的准备）
              └─▶ S0-0e 网页推送（还要：W-44 的外壳已合并、iPhone 信任 mkcert 根证书、卡 5）
S0-13（TD-285）、S0-12（TD-283/284）：第 2 波，和上面互不依赖
```

一次只开一条改 `api/internal/approvals/` 的道；S0-0b 和 S0-0d 改的文件不重叠，可以并行。

### 4.5 子道

验收命令里的路径都相对工作区根。

| 子道 | 内容 | 文件范围 | 依赖 | 验收 |
|---|---|---|---|---|
| **S0-0a 状态机与编号**（platform、infra 少量） | 新状态 `approved` / `running` / `unknown`；`execution{}`；暂时性与永久性错误分类；编号计数器；`Describe`；`Runner` 字段；`executor` 角色和领单、续租、回写三个接口；`confirm_number`；`requester_thread`、`work_id`；存储改用 `statefile.Update`；TD-276；MCP 的 `wait_for_request` 认新状态；`owner-run.sh`、`rolling-reboot.sh` 认新状态并回写结果 | platform `api/internal/approvals/*`、`api/internal/actions/{execute,catalog,actuation,rolling_reboot}.go`、`api/internal/server/actions_wire.go`、`api/internal/actuation/`（角色）、`api/internal/workactions/service.go`（TD-276）、`mcp/platform/src/{pollRequest,approvalTools}.ts`；infra `scripts/owner/owner-run.sh`、`scripts/k3s/rolling-reboot.sh` 和各自的测试 | W-42 合并；卡 3、4、6、7 | `cd bifrost-platform/api && go build ./... && go test ./internal/approvals ./internal/actions ./internal/server ./internal/workactions -count=1`；`cd bifrost-platform/mcp/platform && npm run build && npm test`；`bash bifrost-trade-infra/scripts/owner/owner-run_test.sh`。新测试至少覆盖：暂时性拒绝之后单子仍是 `approved`、永久错误记 `failed`（TD-267 的防线）；两个并发建单拿到不同的 `#n`；两个并发领单只有一个成功；`unknown` 之后同一 lease 的迟到结果只接受一次；同一个 plan 两次 apply 生成两个不同的 run（TD-276） |
| **S0-0b 通知文案与投递记录**（platform） | 文案带 `#n`、级别、动作、环境、摘要、发起线程、过期时间；链接改成 https；结果通知（failed / unknown）；`deliveries[]`；relay 回每个目标的结果；4 小时和剩 2 小时的提醒 | `api/internal/approvalnotify/*`、`api/internal/alertrelay/relay.go`（只改返回结构）、`api/internal/approvals/handler.go`（存投递结果） | S0-0a | `cd bifrost-platform/api && go test ./internal/approvalnotify ./internal/alertrelay ./internal/approvals -count=1`（断言消息里有编号和参数、单子上有投递记录，即 TD-286 的防线）；STG 上建一张 C 级单：手机 ntfy 显示 `#n`、动作、环境，`GET /approvals/<n>` 的 `deliveries[0].result` 是 `accepted` |
| **S0-0c 带外执行器**（platform、infra） | operator-plane 的执行者角色：领单、本地日志、续租、超时、回写、拒绝清单复查；launchd plist（`bifrost-exec` 用户）；MAINTAINERS 登记加告警（执行器心跳过期）；节点 forced-command 脚本和安装说明；执行器 kube 身份的 RBAC 和准入策略；TD-287：WOL 和 poweroff 移到执行器，退役 01 上的服务 | platform `api/internal/ownerexec/`（新）、`api/cmd/operator-plane/main.go`、`agent/deploy/com.bifrost.owner-exec.plist`（新）、`api/internal/cluster/node_power.go`（改成路由到执行器）；infra `agent-config/MAINTAINERS.yaml`、监控规则、`scripts/node/bifrost-node-maint`（新）、`scripts/k3s/gpu-node-power-manager.sh`（退役）、`k8s/platform-rbac/`（执行器身份和准入策略） | S0-0a；卡 1、2；Owner 的准备（第 5 节） | `cd bifrost-platform/api && go test ./internal/ownerexec -count=1`（租约、日志防重、超时、结果重交）；`python3 bifrost-trade-infra/scripts/check_admission_guards.py --live`（执行器身份扩容 daemon 被拒）；实跑：Owner 只点一次批准，TD-290 的删除由系统执行，单子 `executed`、退出码 0，Owner 没敲命令；TD-287 的验收（空闲 30 分钟关机、Pending 的计算 Pod 能唤醒、日志里有 ssh 的退出码） |
| **S0-0d 会话「批 #n」**（platform mcp） | `approve_request` / `reject_request` / `get_request` / `wait_for_request` 接受 `#n` | `mcp/platform/src/{registerApprove,approvalTools}.ts` 和测试 | S0-0a | `cd bifrost-platform/mcp/platform && npm run build && npm test`；Claude 会话里打「批 #n」：弹出允许，批准后单子的 `channel` 是 `chat` |
| **S0-0e 网页推送**（platform、console 新文件） | 平台：推送订阅接口和 `push-subscriptions` 键、回执接口；relay：VAPID 发送；console：订阅和回执的模块，由 W-44 的 service worker 挂载；ntfy 只留严重告警 | platform `api/internal/push/`（新）、`api/internal/alertrelay/webpush.go`（新）、`console/src/pwa/push*.ts`（新） | S0-0b；W-44 外壳已合并；卡 5；iPhone 信任根证书 | `cd bifrost-platform/api && go test ./internal/push ./internal/alertrelay -count=1`；`cd bifrost-platform/console && npm run lint && npm run build`；在 Owner 的 iPhone 上：主屏幕应用收到 `#n` 推送，点开后在应用里打开 `#approvals?id=`，单子上的投递记录到 `shown` |

**整体验收**（对应 STEP0-PLAN 第 0 节 S0-0 的验收要点）：Owner 批一张 `owner_run_command`，系统自己执行并回写结果，全程不用 Owner 敲命令；通知里看得懂批的是什么。

---

## 5. Owner 要做的准备（不是决策，按卡 1、2 的结果才做）

1. 在 .50 上建 macOS 用户 `bifrost-exec`，把卡 2 选定的凭证放进它的目录（600）。Agent 不碰。
2. 各节点装 `bifrost-node-maint` 和受限钥匙。节点 root 要 Owner 的节点钥匙，可以用一张 `owner_run_command`（`runner=owner`）走一遍。
3. iPhone 装 mkcert 根证书的描述文件，并打开完全信任；把 Console 添加到主屏幕（W-44 之后）。
4. 按需 VPN：沿用 Teleport 手动点，或者换 WireGuard 的按需连接（v4 §19，D 级 UniFi 改动）。

---

## 6. 决策卡

### 卡 1：执行器放在哪、用什么

- **问题**：`owner_run_command`、`rolling_reboot` 和 gpu-server 电源要有一个系统执行者。放在哪、用什么做？
- **选项**：
  - A. 扩展 operator-plane，在 .50 的独立账户里以执行者角色另起一个进程，主动来领单（3.1 A）；
  - B. 集群内用 Tekton 流水线执行，节点钥匙放 cicd 的 Secret（3.1 B）；
  - C. 在 .50 部署现成的作业平台（Semaphore UI / Rundeck / AWX），由平台调用（3.1 C）。
- **推荐**：A。集群坏了它还活着，凭证不进集群，只往外连；自造的部分最少，又不多出第二张审批表。
- **不回复会怎样**：不做执行器。S0-0a、S0-0b、S0-0d 照样可以做（编号、通知、重试、会话批准都不依赖它）；`owner_run_command` 和 `rolling_reboot` 仍由 Owner 手敲；TD-287 不动。
- **属于**：定规则。这是新增一个会改东西的维护者，要先进 MAINTAINERS（ADR §7），放置也属于 ADR §3 的范围。

### 卡 2：执行器持有哪些凭证（要改 ADR §3）

- **问题**：ADR §3 写明 Mac mini「不该跑：常驻集群管理员凭证」，Agent 也不常驻写凭证（ADR §2）。执行器要执行 Owner 批过的命令，就得在 .50 上放写凭证。放哪些？
- **选项**：
  - A. **专用、受限的凭证**：
    - 一个专用的 kube 身份 `bifrost-owner-exec`（不是 Owner 的管理员 kubeconfig），由准入策略挡住 D10 相关的写；
    - 节点上只放 forced-command 钥匙（poweroff、reboot、upgrade-reboot）；
    - 子系统管理员密码（Gitea、UniFi、数据库属主）和节点 root shell **不放**，这类命令标 `runner=owner`，仍由 Owner 手工执行（结果回写）。
    - ADR §3 的 mini 一行改成：「宿主的独立账户里可以放执行器的专用凭证，范围由准入策略和 forced-command 限定；不放集群管理员和节点 root」。
  - B. 把 Owner 的管理员 kubeconfig 和节点钥匙（去掉口令）原样放到 .50 的独立账户里，几乎所有命令都能自动执行。
  - C. .50 不放任何写凭证：执行器只执行不需要凭证的事（WOL），其余仍由 Owner 手工执行。
- **推荐**：A。B 让 .50 变成全集群的单点钥匙，节点 root 也在上面；C 达不到 S0-0 的验收。A 能覆盖 10-09 到 10-10 里大部分手工步骤（helm upgrade、kubectl create、删对象、重启节点、gpu 电源）。剩下的子系统管理员类本来就该逐次找 Owner（ADR §1 第 3 条：密钥）。
- **不回复会怎样**：.50 上不放任何凭证（等于 C）。S0-0c 只做 WOL 和执行器骨架，其余照旧手工。
- **属于**：处理不可逆的事（密钥放在哪里），同时要改 ADR（定规则）。

### 卡 3：审批记录的状态机和接口变更

- **问题**：要支持「批准后排队、由执行者领取、失败可重试」，就得改审批的公开接口。改动是：
  - 新状态 `approved`、`running`、`unknown`；
  - 新字段 `execution{}`、`runner`、`requester_thread`、`work_id`、`deliveries[]`；
  - 新角色 `executor`，以及 `POST /approvals/claim`、`/{id}/heartbeat`、`/{id}/result` 三个接口；
  - 批准请求加 `confirm_number`（D 级）；
  - 「只记录」的动作不再显示 `executed`。
  
  下游要跟着改：Console 审批页、`approvalsServerContract.ts`、MCP 的 `pollRequest` 和 `bifrost-approve`、`owner-run.sh`、`rolling-reboot.sh`。
- **选项**：
  - A. **在同一张单子上扩展状态**，执行信息集中在 `execution{}` 子对象里；`approve` 对主机执行的动作返回 202 加 `approved`，对平台内执行的动作仍当场试一次；
  - B. 不加状态，用 `result.phase` 之类的子字段表达。兼容性最好，但 `executed` 仍然不代表「真执行了」，TD-267 也解决不干净；
  - C. 审批和执行拆成两种记录（审批只管决定，执行单独一个 statefile 键），提前做成发布队列的形状。
- **推荐**：A。改动集中，`execution{}` 以后可以整块搬进发布队列或 PG。C 更干净，但这一步就要同时做发布队列，超出第 0 步。
- **不回复会怎样**：保持现在的同步执行模型。TD-267 继续存在，`owner_run_command` 只能停在「记录」，S0-0c 做不了。
- **属于**：定规则。改变的是「一次批准执行一次」在暂时性拒绝和带外执行时的含义：批准在执行期限内保持有效，不用再点。

### 卡 4：短编号 `#n`

- **问题**：ADR §12.8 规定「只有一个编号空间：W-n」。审批单要不要有自己的短编号？怎么编？
- **选项**：
  - A. 审批单是另一类对象，单独有一个全局自增的 `#n`，只用来指审批单（`W-n` 仍是工作项唯一的编号）；计数器存在审批文件里，以后迁 PG 时接着往下编；
  - B. 按天重置（例如 `1010-3`）：好念，但跨天容易混；
  - C. 不加编号，显示长 id 的前 4 位十六进制：不新增编号空间，但念不出来，也有撞号的可能。
- **推荐**：A，并在 ADR §12.8 补一句「审批单用 `#n`，不是工作项编号」，`check_work_ids.py`（S0-2）不管 `#n`。
- **不回复会怎样**：S0-0a 不加编号字段，通知和会话仍用长 id；其他部分照做。
- **属于**：定规则（编号规则）。

### 卡 5：网页推送的实现与新依赖

- **问题**：Owner 已定改用网页推送，由 .50 发出。发送端怎么实现？
- **选项**：
  - A. platform 的 Go 模块引入 `webpush-go`（MIT），relay 用它发送；VAPID 私钥只放在 .50；
  - B. 不加依赖，用 Go 标准库自己实现 RFC 8291 的加密和 VAPID 的 JWT（Go 1.25 有 `crypto/ecdh` 和 `crypto/hkdf`），大约 200 行加密代码；
  - C. 在 .50 自建一个 ntfy 服务器，用它自带的网页推送和网页应用。
- **推荐**：A。加密代码不自己写（ADR §12.2 第 6 条）；B 是 A 的维护状态不合格时的退路；C 会变成第二个收件箱，而且不是我们的「需要你」页。开工前按 ADR §12.2 第 9 条核实：许可证、最近的维护情况、有没有遥测、读一遍源码。
- **不回复会怎样**：S0-0e 不做，手机继续用 ntfy（S0-0b 改过的文案加投递记录）。
- **属于**：定规则（新增外部依赖）。

### 卡 6：执行输出存在哪里

- **问题**：执行器跑的命令，输出里可能有秘密（比如 helm 打印的值、kubectl 显示的 Secret）。平台的审批记录和审计都在集群的 ConfigMap 里，viewer 令牌能读。输出存哪？
- **选项**：
  - A. 平台只存退出码、用时、输出的 sha256，再加最多 2 KB 的尾部，尾部先按常见的密钥格式打码；全文只留在 .50 的 `bifrost-exec` 账户里，保留 30 天；
  - B. 平台只存退出码、用时和 sha256，不存任何输出；
  - C. 平台存全文。
- **推荐**：A。失败时手机上能看到最后几行，判断要不要处理；全文不出 .50。打码只是兜底，命令本身应当避免打印秘密（建单时提示）。
- **不回复会怎样**：按最严的 B 做。
- **属于**：处理不可逆的事。秘密一旦进了 ConfigMap 和审计，就很难收回。

### 卡 7：新状态先放 statefile，还是等 PG

- **问题**：ADR §12.3 定了状态放 CNPG 的 `bifrost_platform`（S0-9，第 3 波才建）。S0-0 新增的状态（编号计数器、执行信息、推送订阅）放在哪里？
- **选项**：
  - A. 先放现有的 statefile：审批仍在 `approvals` 键，新开一个 `push-subscriptions` 键；运行时第 0 阶段建 `agentrt` 时，再按 database-design 规范整体迁到 PG；
  - B. 等 S0-9 建好 PG 再做 S0-0 的实现。
- **推荐**：A。审批本来就在 statefile 里，而且 v4 §9 要求「修数据库的那次发版也能走」，审批不该依赖 PG；B 会把 S0-0 推到第 3 波之后。
- **不回复会怎样**：S0-0 的实现等到 S0-9 之后。
- **属于**：定规则（状态放在哪里）。

---

## 7. 不在本方案

- 发布队列、钉提交号、自动回滚（v4 §9，第 0 步之外的并行轨道）。
- Console「需要你」页和「记录」页的版式（W-44、W-47）。
- 通行密钥（WebAuthn）确认、规则签名（v4 §19「以后可选」）。
- UniFi 上的 VPN 和防火墙改动（ADR §10，D 级，由 Owner 决定）。
- D10，以及任何实盘交易路径。观察中的 TD、LANE-N、LANE-M2。

## 8. 建议台账维护线程登记的内容（本道不改 TECH_DEBT.md 和 WORK.md）

- TD-286、TD-287、TD-267、TD-276 的状态里加一句「方案见 `work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md`，实现在 S0-0a–e」。
- 新防线（随 S0-0a）：`owner_run_command` 每 30 天的次数，按命令的第一个词分组；同一类出现 2 次以上就进「待你定」，提议做成具名动作。这一条登记进 RATCHETS.md。
- 0.1 节 D-21 的「动作目录 39 个」，在 75be701 上实测是 38 个。
- 子道 S0-0a–e 分 W-n 编号（由执行线程在 WORK.md 里分配）。
