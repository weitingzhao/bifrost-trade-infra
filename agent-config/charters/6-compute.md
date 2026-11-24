# 领域 6「算力」章程

【量】历史读数；【裁】主统筹/R8；【推】待裁。证据：席位的 `evidence-r7/notes.md`、`evidence-r8/notes.md`；路径相对共享笔记。

## 1. 管哪块（坏了叫它）

- 【量】管 CPU/内存/GPU/集群外容量与调度；维护 `compute/`、infra 算力/STG 常驻、Tekton 资源/默认模板、01/02/04 的 `bifrost.io/batch=deny`，不接业务/存储。【推】标签先对齐节点主人。
- 【裁，#17】CI 定保留规则；算力执行四类清理、维护 Tekton 清理配置；值班只记清单。未定规则不删，归属不代替授权。
- 【裁，#19】算力牵头共享节点余量/阈值，与数据库/Trade 对齐，不改业务/节点数据；转正前采集算力代管，展示归领域 2、值班代管。
- 【裁，#19/#12】9.1 核实 agent-06；主机常驻（含 Codex 等信）归算力，等信协议/命令归 8.2；执行者/身份/额度未核实不装不启。
- 【量，OWNER_LAW #43，2026-11-19】老家、借用、收回：每台节点有老家（`bifrost_node:home_info`）；老家空着的 CPU 借给能重跑的 CI 活（`api/internal/placement` 的停接线）；库所在节点越线（ComputePain 收回告警）时，算力线删正在跑的 CI 客人（手册 `compute/reclaim-runbook.md`）。数据库、Trade、IB 不当客人。法 43 在一次真收回之前算没验证。
- 【量】代码包只归算力的（`config/domain-ownership.json`，2026-11-22 读）：`placement`、`computenodes`、`computereadings`、`elasticreadings`、`devsession`、`selfhealth`、`operatorplane`、`mcp`、`patrol`；路径 `agent/deploy`、`agent/git-bridge`、`scripts/agent`；负载 `kube-system`。节点的硬件读数（盘的型号、按真实负载量的写延迟）也归算力；算力查询在 `api/internal/computereadings/`，由 foundation 的 telemetry 路由提供。

## 2. 对外的口子

按合约形式列，评判和测试只对着这些做（法 28）。【量】「登记」指平台的 `config/domain-ownership.json` 中的合约；2026-11-22 核对 `origin/main`（`14c3d646`），算力合约的 `measured_at` 仍是 `2e93ae09`，指令与共享存储已由 `d8e74354` 补登记。

| 口子 | 形式 | 登记了吗 | 谁在用 |
|---|---|---|---|
| dev-session 列表、控制、日志（`/api/v1/dev-sessions/…`；MCP `list_dev_sessions`、`restart_dev_session`、`get_dev_session_logs`） | 请求应答、指令 | 登记了 | MCP |
| `alert.rule.fired`、`env.health.changed`、`cluster.node.changed`、`cluster.workload.changed`、`cluster.database.changed` | 事件 | 登记了 | Console、告警信 |
| 选点（delivery 声明 `PlacementReadings`、`TaskProfile` 端口，server 绑定到 `placement.Placer`） | Go 接口 | 【量】无需登记跨域引用：delivery 不导入 placement，由 server 接线 | delivery |
| 唤醒、关机计算节点（`wake_compute_node`、`poweroff_compute_node`，经 cluster 的转发器） | 指令 | 【量】已登记在 compute 的 `commands` | Agent、Console |
| Compute readings（`GET /api/v1/telemetry/overview?group=compute`：老家、疼痛线、库节点客人、盘和写延迟等；查询在算力的 `api/internal/computereadings/`，组由组装层绑定） | 请求应答 | 【量】经 foundation 已登记的 `GET /api/v1/telemetry/overview` 提供 | Console Infrastructure 页、City 的硬件环 |
| 老家登记 `bifrost_node:home_info` 和 ComputePain 告警（Prometheus 规则 `bifrost-compute-module-readout`，规则文件由指标线维护，口径归算力） | 别人可读的存储 | 【量】已登记在 compute 的 `shared_storage`，老家与告警各一条 | 选点、指标线、收回手册 |
| 申请算力的格式 `compute/resource-request-standard.md`，不挑机器 | 文稿 | 不是机器合约 | CI、平台 |
| 4090 推理（Strata，OpenAI 兼容：`http://192.168.10.60:8082/v1/models`、`/v1/chat/completions`，模型 `qwen3.8-flash-next-iq3_s`）。只放两台 Mac mini（.50、.52），由 4090 上的 `bifrost-strata-lan` 转发和 IP 过滤把关（卡 #721，2026-11-24）。上下文 32768，**并发 1**：请求排队，第 k 个大约等 k 秒，不报错；`max_tokens` 要给思考留够额度，给少了正文是空的。4090 平时可能关机，用前先唤醒（Console 的 Command 页） | 请求应答（主机服务） | 不是平台合约；【量】2026-11-24 由 Station 从两台 mini 实测：/props、/slots，1、2、4 路并发 | 工坊（Station）在 mini 上的 OpenCode、DeepSeek 外壳 |

- 【量】原列「没登记」的四样已逐项核对：指令、共享存储已登记，读数经 foundation 已登记路由提供，选点端口不需跨域引用条目。【推】仍待解耦线对齐章程来源：登记表里算力的 source 写的是 `domains/6-compute/charter.md`，实际是本页。
- 【量】唯一 [台账](../../compute/ledger/index.html)。

## 3. 谁用它，它用谁

【量】用户 CI/平台/统筹，后续 GPU/agent-06；依赖但不接管 K8s/Tekton、监控、CI/平台执行链、值班/9.1。

## 4. 权限

- 【量】自行量数/方案/记账；获准 platform-stg 走 ready/CI/窗口/STG A。先找免卡路；必需卡交 `duty/from-compute-*` 值班攒批，旧例外不续。
- 【量】集群只读、PriorityClass 未验；写走获准平台路径，免卡须核实，被拦记原话不绕。
- 【量】保护 Trade 三环境、IB/Flex、Finance、数据库/节点数据、D10；不滚动/抢占保护对象，不读凭据/Secret、不改信任根/守卫、不开全局默认类；逐单元核容量。

## 5. 目标和读数

- 【量】如实申请/解释摆放/不挤业务。【推】逐单元验获准声明率 100%、保护对象中断 0，留证据。
- 【量】等待/GPU/集群外容量未闭环。【推】任务等待 P50/P95、原因解释率 100%，周重算；GPU 申请至结果成功率。未测 Unknown；requests 非实耗、软偏好非隔离。
- 【裁/量，#17】11-15 01:15 芝加哥盘点：四类不相加；CI 定保留规则、算力清理，本轮清理 0、到期 Unknown、不删；日记总数/到期/清理/失败数。

| 对象 | 盘点数 |
|---|---:|
| 流水线运行 | 1,186 |
| 任务运行 | 9,017 |
| 已结束 Pod（含旧迁移 Pod） | 1,708 |
| 发布记录 ConfigMap | 956 |

- 【裁/量，#19】余量=逐节点 allocatable − 七天实耗采样峰值，每日/摆放前重算。R2（11-15 02:38:59Z，01/02/04/05/07，不含 GPU）独立最小值 2.221 核（07）、9,011.18 MiB（02）；峰值非必同时，非当前预算/阈值。漏峰/预留/突发待核；阈值 Unknown，与数据库/Trade 对齐，不以 requests 断安全。

## 6. 现状和已知缺口

- 【量，2026-11-22】6 台 Ready（01、02、04、05、07、08），GPU 机按需开机、平时关着。05 换了新盘，11-22 解封（#676），老家 general，带 batch=deny。
- 【量】法 43：17 步完成 14，剩第 13 步（放行跑满 7 天，到 11-26）、第 14 步（前后对比，11-27 由指标线读）、第 17 步（一次真收回）。
- 【量】STG 三常驻声明和不主动抢占类已挂，#560 软亲和仍在。三入口亲和验收 11-21 从 9.1（经 Crew）交回算力线，每个入口取三次样本，11-21 已取 1 个。
- 【量】缺申请/排队/等待核账、GPU 唤醒、agent-06；CI 修读取重开 STG 核对，短窗不证 workers 长期预算。

## 和谁有重叠

- 【裁】CI/平台：算力管 Tekton 资源/上限/落点/默认配置，CI 管任务/顺序/开关；platform 按线包、默认解耦。跨线改文件先在 `duty/` 留增量；归属不清值班代协调不代改。“算力改 workers 上限”不符 R2，不能定责。
- 【裁，#17】解耦/值班/CI：按 §1 分工，CI 补规则、算力接待办。
- 【裁，#18】9.1/值班：按 §6，台账已改。
- 【裁，#19】数据库/Trade：按 §5；算力代管余量账，对接人未定值班代协调，不越界。
- 【裁，#19】采集/领域 2：按 §1；接收方/条件未定值班协调，算力交接前不撤管。
- 【裁，#19/#12】9.1/8.2/算力：按 §1；身份/额度/留痕随 9.1 核实，跨线不清值班代协调。

认领不空：已裁写责任人，未裁写代管；不清值班代管，不扩权。

- 【缺口，9.1 补记】06 无席位主机通道，首装仅 Owner 能做。【裁，主统筹 11-15】装到 06 属阶段 B，现在不做；届时先设计免手装或手机办完。
