# 切法：Agent 完整会话时间线（2026-10-26）

状态：**第 2 稿**，Work 597 修订 Work 591，逐项回应 Review 593（3 B、4 C）；Owner 已选完整时间线 A，其余架构选择见 §10「待 Owner 定」。本次只改设计与回复，不实施、不提交、不发布。

## 1. 目标、顺序与完成含义

Owner 在 `ops.bifrost.lan` 看见每个运行中会话说了什么、厂商实际暴露的 reasoning/thinking、命令与工具调用、输出、文件变更，以及明确的等待原因；可回看完整时间线。采集来自运行会话的系统，不靠 Agent 手写进度。正文离开宿主机前过滤，只有 Owner 的 admin 身份可以读。

已定顺序：**PV1（Work 588）后实施；不成为 4.1 的前置**。这里的 PV1 是计划视图切片，D-PV1 是架构选择，两者不混用。沿用 D-PV1 A、D-PV2 A、D-PV3 A，不再重选。`I/agent-config/WORK.md:550` 记录 Owner 10-24 的选择；本次 BRIEF 补充 10-26 的完整流 A 和排期。

这是平台通用观测能力，属于 Ops；不改变调度、验收、发布授权或任务完成规则。时间线中的“测试通过”是发言；只有原有验证事实能改变 PV1 的进度。

“完整”指支持来源在有效保留期内、厂商实际输出且通过过滤的完整事件序列。隐藏 reasoning、过滤、上限、缺失、版本不支持必须各自占位，不能把摘要或日志尾称为完整。厂商不提供的内容不推测、不解码、不补写；有界存储与无限历史不相容，超过上限显示明确缺口。

## 2. 本地证据基线

2026-10-26 只读核对。`P/` = 工作区 `bifrost-platform/`，HEAD `ed8bb2276d423085014d80fddebfe2937c60f3be`；`I/` = infra 的 `w31/session-stream` worktree，第 2 稿基于 `c706768ec1d1227d88a671d5b9ecb4e75b61a519`。以下是本地代码与文档，不代表已部署版本。没有查询平台、集群、NAS 或厂商推理 API，也没有读取真实会话正文、凭证或 Owner 目录；第 2 稿补查公开官方文档。

| 证据 | 已有行为 | 对本切法的约束 |
|---|---|---|
| `P/api/internal/agentd/executors.go:270`、`:410` | runtime 分别运行 `codex exec --json`、`claude -p --output-format stream-json` | 复用进程出口，无需 Agent 主动报告 |
| `P/api/internal/agentd/run.go:417` | stdout/stderr 合写本机 `log.txt`，0600；另启 action collector | 当前混流可能有非 JSON 行，需适配和缺口记录 |
| `P/api/internal/agentd/confine.go:21`、`:29`、`confine_linux.go:44` | attempt 共用 UID，现有 wall 只限制写；Codex 还有不同的 sandbox 路径 | **已确定不提供跨会话读隔离**，不能以独立 HOME、worker 或 0600 代替 §8.1 改造 |
| `P/api/internal/agentd/run.go:417`、`:425`、`disk.go:88`、`deliver.go:560`、`:574` | raw log 持续追加；settle 会 sweep 整个 `.out` | 必须增加有界捕获及 §6.1 EOF/offset 转交，净化 spool 生命周期独立于 `.out` |
| `P/api/internal/agentd/actions.go:18`、`:64`、`:159` | 丢弃消息和 reasoning；两秒读一次；pending 最多 200，取走后清空 | 不是可靠全量传输队列，不能直接扩大它 |
| `P/api/internal/agentd/actions.go:296`、`:317`、`:345` | Codex 命令/文件变更；Claude tool_use；Cursor tool_call | 可以复用字段经验，完整正文仍须新适配；Cursor 注释明确有未实测项 |
| `P/api/internal/agentd/actions_test.go:58`、`:84` | fixture 有 `agent_message`、`reasoning`、`aggregated_output`、`file_change`、Claude text/tool_result | 证明代码认过的结构，不证明今日厂商会全量输出 |
| `P/api/internal/agentd/scrub.go:23`、`:45`、`:72`、`:136` | 命令 target 的凭证、私钥、路径掩码；搜索 pattern 有例外 | 不能原样用作任意正文过滤器，尤其不能保留搜索例外 |
| `P/api/internal/agentd/handtext.go:11`、`:34`、`:55` | TD-382：报告/评审/日志尾改写本机路径；仍违规的报告行 withheld；patch 不走这里 | 只证明路径处理；不等于 env、凭证文件、diff 全面过滤 |
| `I/agent-config/TECH_DEBT.md:2812` | TD-382 的历史实证和验收记录；原拒收上报不带 attempt ID | 新上传必须有精确 session/attempt/epoch，拒收不能误归另一次尝试 |
| `P/api/internal/agentrt/actions/actions.go:1`、`:36`、`:125` | actions 只存 Redis，TTL 24 小时，约 500 条；每 beat 50 条、target 400 字符 | 不能成为新时间线历史权威 |
| `P/api/internal/agentrt/agentrtapi/api.go:110`、`:148`、`:158`、`:163` | 通用 read 接受 viewer/reporter/operator/admin/agentd；artifact、actions、events 在其中 | 新正文不能塞进这些公开于 Agent 的读面 |
| `P/api/internal/agentrt/agentrtapi/messages.go:60` | actions 支持 after/limit/last；无 Owner 专属门禁 | 复用分页概念，不复用权限 |
| `P/mcp/platform/src/registerMessages.ts:43` | `get_attempt_actions` 明示 24 小时动作流 | 不把新正文透传给该 MCP |
| `P/api/internal/agentrt/migrations/0001_core.sql:29`、`:196` | artifact/body 在 PG，单件 1 MiB；event 按 stream 序号及哈希链追加 | 可借鉴追加事务，不能将时间线正文写入既有通用 artifact/event |
| `I/agent-config/claude/settings.json:3`、`:41`、`:51`、`:61`、`:71` | UserPromptSubmit、Pre/PostToolUse、Notification、SubagentStop、Stop 已接心跳 | hooks 提供自动发现和时点，但不是完整聊天记录 |
| `I/agent-config/scripts/thread-heartbeat.js:12`、`:26`、`:101` | headless 包装器、限时 hook、厂商事件映射；文件增长才报进度 | 保留原语义，增加独立 collector 活性，不能把它当会话正文源 |
| `I/agent-config/claude/hooks/report-thread-title.js:62`、`:105` | 从 hook 的 transcript_path 增量读完整 JSONL 行，目前只提取标题 | 本地 transcript 适配有接入点；不能直接上传整文件 |
| `I/agent-config/codex/README.md:10` | 未 trust 的 Codex hook 静默跳过 | Mac `codex exec` 以父进程 JSONL 捕获为主，不能只信 hook |
| `I/agent-config/work/multi-agent/CUT-plan-view-2026-10-24.md:262`、`:275`、`:291`、`:304` | D-PV2 A：窄登记、run key、external_work_id、启动前登记；原范围不采正文 | 本项增设私有正文流，沿用登记对象，不回改 PV1 的公开正文边界 |
| `P/api/internal/actuation/auth.go:282`、`:306` | 精确角色门禁和 Bearer principal；admin 是角色 | 单看 admin 不能区分 Owner 浏览器与持 admin 令牌的工具 |
| `P/api/internal/actuation/audit.go:19`、`:39`、`:68` | 审计有 actor/role/action/target；仅留最近 500，持久化错误不回传 | 新查看审计须可靠落盘，不能只调用现有 Record 就宣布审计可靠 |
| `I/scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader-verify.sql:12` | agent_reader 继承 pg_read_all_data | 仅撤销表 SELECT 不是足够的数据隔离证明 |
| `I/k8s/overlays/platform-prod/platform-agentrt-env.patch.yaml:44` | runtime PG 是控制面库 bifrost_platform | 禁止把本文内容混入 Trade/Research 数据库 |
| `I/k8s/data/minio/service.yaml:1`、`:25` | 现有 MinIO Service 指向 NAS，配置是 HTTP 9000 | NAS 可作为候选；新桶、窄凭证、TLS、容量须实际验证 |
| `I/k8s/data/minio/nas/README.md:1`、`:49` | 现用途是 PG 备份；历史有 NFS/磁盘故障及回滚约束 | 新内容不得共用备份桶或用正文流挤满备份空间 |
| `I/agent-config/scripts/agent-guard/preflight.js:833`、`:910` | Owner 凭证目录与非许可 kubeconfig 有本机闸门 | 这里只据规则定义过滤分类，不读敏感目录来生成样例 |

CLI 基线：初稿及 Review 593 实测 `codex-cli 0.163.0-alpha.11.2`；`codex exec --help` 确认 `--json` 输出 JSONL，`-o` 只保存最后消息，`--ephemeral` 不落会话文件。第 2 稿核对 [OpenAI 非交互模式文档](https://learn.chatgpt.com/docs/non-interactive-mode#make-output-machine-readable)：事件包括 thread/turn/item/error，item 包括 message、reasoning、command、file change、MCP、web、plan。文档没有保证每次 file change 有 diff，也没有提供完整内部推理；字段仍由 SS0-S 对固定版本的合成样本验证。

初稿与 Review 593 在本地 platform 的 `api/`、`mcp/` 搜索尚未找到 `register_external_work`，所以本文使用 PV1 已批准的设计契约作为依赖，不把 Work 588 的在制实现当成当前 main 的能力。SS0-P 必须以它的实际合入版本校准字段和绑定事务。

Claude 版本证据更新：初稿遇到 Keychain 错误；Review 593 随后成功实测 **2.1.302** 及 `--forward-subagent-text`、`--include-hook-events`、`--include-partial-messages`、`--no-session-persistence`，第 2 稿引用该结果，不冒称再次运行 CLI。已复核 [headless 文档](https://code.claude.com/docs/en/headless#follow-subagent-messages)：子线程 text/thinking 需显式 `--forward-subagent-text`，以 `parent_tool_use_id` 关联；prompt 启动的 forked skill 可能结束后才集中交付。当前 executor 未加该开关，必须改造后验证。已复核 [SubagentStart](https://code.claude.com/docs/en/hooks#subagentstart) / [SubagentStop](https://code.claude.com/docs/en/hooks#subagentstop)：Start 给 agent_id 和主 transcript；子 transcript 路径在 Stop 给出。运行中发现路径的候选协议见 §4.1，不能将 Stop 后补读算实时覆盖。

## 3. 对象与自动关联

### 3.1 一个工作对象，多次会话

新增 `session_id` 是观测会话 ID，不是第二个 task，也不伪造 runtime attempt。关系：

```text
PV1 plan_node ── runtime task ── attempt_id + epoch ── session_id
             └─ external_work_id + source_run_key ── session_id
                                                   └─ child session_id
```

已绑定 session 有一个 canonical `work_ref`：`runtime_attempt` 或 `external_work`，以及可空的 `parent_session_id`。`Unlinked` 的 `work_ref=null`、binding_revision=0，不虚构 external_work，也不计入 PV1 工作数；可信上下文到达后，平台在同一事务校验授权、写唯一 binding 并递增 revision，原 session/seq 不变。平台从已认证的来源和既有绑定派生 tenant、host、actor、plan_node、task、attempt；客户端不得自填他人的身份。外部 run key、vendor session ID 不含路径，必要时在本机做带密钥的稳定映射；映射表留宿主机，不上传 transcript_path、PID 命令行或 cwd。

`(tenant, host_id, source, source_run_key, source_epoch)` 唯一，注册重试返回同一 session。resume 延续 vendor 会话但启动新 `source_epoch`；fork 创建 child session；runtime 重试产生新 attempt/session，仍挂同一 task。多对一的工作关系允许多个子 Agent，不合并它们的 source_seq。

### 3.2 启动和恢复

| 来源 | 自动登记与关联 | 恢复/异常 |
|---|---|---|
| agentd on 06 | launch 已知 attempt_id、epoch、host；在本机建立固定绑定，再开采集 | 观测补传与执行租约分离；旧 epoch 只能补 §6.1 已封口水位以内、未过 24 小时 TTL 的历史，不获得新执行权 |
| Mac `codex exec` | PV1 包装器先 `register_external_work`，保存其 external_work_id/source_run_key；同一父进程接 JSONL，向 collector 提交绑定 | 登记失败按 PV1 不静默启动新任务；执行中上传失败只断观测，不终止任务 |
| Claude 统筹线程 | SessionStart/首个已接 hook 唤醒 collector；从可信 launcher 的工作上下文复用/登记 external_work | 不能把标题或发言中的 Work 字样当授权绑定；缺 root/node 时先自动记录 `Unlinked` 会话，继续探测上下文 |
| Claude 子 Agent | SubagentStart/Stop、parent_tool_use_id 或已验证的 transcript 父子关系自动建 child session；继承 work_ref | 不从任意目录名猜父会话；无法证实时标 `Parent unconfirmed`，不能漏掉此会话 |
| 外部工作转 runtime | 由 PV1 原子 linked 事件关联既有 task，时间线记录 binding revision | 原 external_work_id 作为 alias 保留；PV1 聚合只计一份工作，不复制历史 |

SessionStart/SubagentStart/PostToolUseFailure 的固定版本行为由 SS0-S 确认；已有配置并未接齐这些 hook。新增 hook 只通知本地 collector，不自行联网发送原载荷。系统级安装一次；每件工作的登记、结束、父子关系和重放自动完成。

collector 每 30 秒对账受管 launcher、已注册 PID/启动时间、hook 心跳及本地增量文件水位；只取最小进程活性，不采环境或完整 argv。发现无绑定/无权限/禁用持久化的活会话也在 Owner 列表占位，给出 coverage 原因。首轮安装自动发现允许范围内的在跑会话，从安装水位起标 `Capture started late`；不默默回传整盘旧记录。

目标覆盖已配置的 06 agentd 与 Mac 工作区 Claude/Codex 入口；**当前 06 读隔离不成立，原生同进程子线程也未满足每 session 隔离，不能直接启正文**。来源清单分列 event capability 与 isolation capability，任一不合格仅占位。任意其他应用、其他 OS 用户、绕过所有入口且无可见文件的进程不在可证覆盖内。Owner 页必须显示 detected/capturing/unlinked/unsupported 数量；这些缺口阻止“所有受管会话已覆盖”的验收结论。

## 4. 每个来源采什么

统一先生成 typed envelope，再过滤所有可能携带正文的字段；不透传 vendor 原 JSON。tool 结果是数据，不是指令。

| 来源 | 输入与事件映射 | 明确的边界 |
|---|---|---|
| runtime Codex | JSONL 中 thread/turn 生命周期；`item.*` 的 `agent_message`→message、`reasoning`→reasoning_summary、`command_execution`→tool start/end/output、`file_change`→file_change | 当前代码只提取命令/退出码/路径；不是每次 file_change 都有 diff；reasoning 的含义和完整性按版本能力标识 |
| Mac Codex | 同上，父包装器捕获 stdout，stderr 单独进入受限 diagnostics；prompt 也在本机过滤后记录 | 不用 `-o` 充当时间线；不读内部隐藏推理存储；MCP/web/plan 已有文档依据，但字段只有 SS0-S 验证后入词表，未知种类只记占位 |
| runtime Claude | stream-json 的 assistant text、已暴露 thinking、tool_use、user tool_result、result；记录调用 ID 和父调用 ID | 固定 2.1.302 基线，接入须显式添加 `--forward-subagent-text`（仍遵守原 tool pins）；其他三个开关按实际需要验证，不假定 tool_result 有 exit_code；forked skill 可为 delayed |
| Mac Claude 主线程与子线程 | 主线程按已核验 transcript 增量 tail；子线程采用 §4.1 的 Start 发现 + Stop 对账候选；headless 优先 stream-json | 当前同进程子线程读隔离尚不支持；即使能读事件也不能启正文。无运行中事件源只标 `Delayed`，始终无源标 `Unavailable` |
| runtime Cursor/其他执行器 | 对现有 Cursor stream-json 增加版本化适配；deterministic executor 捕获其命令、输出、退出码 | 本地注释未实测的部分不能标已覆盖；未支持厂商给 `Unsupported source`，SS7 的“所有 runtime”验收前必须补齐 |
| 平台运行事实 | lease、任务状态、审批/问题引用、限流/退出/失联 | 与厂商事件并列但标 source=platform，不把观测事件当调度事实 |

对 thinking/reasoning 只展示厂商正常接口/正常 transcript 已交给用户的可见文本，标 `Vendor-exposed reasoning` 或 `Reasoning summary`。`redacted_thinking`、signature、encrypted_content 等不传正文，不尝试解密；保留 `Not exposed by vendor`。不能承诺 OpenAI/Anthropic 的完整内部思考。

实时目标：已封闭、已过滤的事件从宿主机观察到 API 可读，p95 ≤ 3 秒（设计目标，未实测）。未封闭的流式文本先显示 `Message in progress`。为防密钥跨 delta 泄露，拼成完整逻辑消息/工具结果再过滤；长内容必须有独立安全边界，否则到限额只出 withheld。可安全解析的工具 start 先到，result 后到；不把较快的显示优先于过滤。

文件变更同时区分 `reported_by_tool` 与 `observed_diff`。工具成功只证明厂商报告改动；在工具边界/结束时对当前受管 checkout 取有界、只读 diff，可补 Bash 修改、删除、重命名和二进制标记。仅比较本次会话基线和允许路径，不上传全仓、未跟踪敏感文件或全文件快照；共享 checkout 的并发修改标 `Attribution unconfirmed`，不冒称由该会话所改。diff 的新增、删除、上下文、文件名全部过滤；敏感文件整份 diff withheld，二进制/图片不传原体。

### 4.1 Mac 交互式子线程的运行中发现（C3）

这是一条待固定版本合成实验验证的适配协议，不是厂商稳定路径保证：受管 launcher 先登记主 session 的受限 transcript 根和进程启动身份；collector 对经本地身份通道核验的 SubagentStart 保存 `(parent, agent_id, start)`。仅在这个主 session 的允许目录中，用固定版本路径映射寻找 `subagents/agent-<agent_id>.jsonl`；不遍历用户全目录、不从正文猜父子。打开后核验 regular file、目录归属/inode、路径不经 symlink 越界，并将文件内可用身份字段与登记关联比对；只有该版本的路径/身份组合已通过伪造、串线和更换 inode 夹具才 tail。

候选尚未出现或不能唯一核验时，立即显示 child 元数据和 `Live source unavailable`，不读相邻文件；Stop 到达后核对 `agent_transcript_path` 与既有映射，再补读并标 `Delayed`。禁用持久化或只在结束时产出文件的模式不能宣称 3 秒实时；没有合法文件则 `Unavailable`。Start 通知丢失、Stop 先到、重复 agent_id、resume 和多层 parent_tool_use_id 各有对账夹具。**该路径仅解决事件发现**；§8.1 的每 session 读边界、taint 和容量门槛仍同时适用，原生同进程主/子不能借此升级为支持。

## 5. 宿主机出口过滤

### 5.1 信任边界与固定顺序

```text
vendor process / allowed transcript
  → typed source adapter (bounded memory)
  → normalize + provenance/taint + complete logical record
  → deny sensitive file/block/line; rewrite safe repo path
  → scan normalized final serialized bytes
  → sanitized spool (collector-only identity; 0600/0700 are additional controls)
  → authenticated TLS upload
  → platform second scanner → durable commit → live notification
```

原始文件分两类：厂商 transcript 与 **agentd 自己创建的 log.txt**；后者必须从无界追加改为 §6.2 的有界捕获，不能以“厂商管理”排除责任。collector 不额外复制 raw spool、不上传 raw 文件、不把解析错误行写进诊断日志。输入文件只开 allowlist 范围内、所属正确执行身份的 regular file；核验 inode/打开后的对象，不跟任意 symlink，不接受任意 hook 指定路径、远程挂载或文件入口中的 FIFO。受管 launcher 显式交付的 stdout/stderr pipe 是另一种已认证入口。换 inode、截断、半行、重复 hook 都有 source_epoch/watermark 处理。

过滤策略版本随受管 collector 发布；工作中的 Agent 不能通过项目文件关闭它。失败、超时、未知结构、未知字符编码均 fail closed：元数据 placeholder 可以出机，正文不能出机。正常工作进程不被过滤失败杀掉。路径与规则也从受信配置加载，不因事件正文声称“这是测试”而放行。

### 5.2 过滤矩阵

| 类别 | 主机端处理 | 例外与验证要求 |
|---|---|---|
| bearer/basic/cookie、JWT、已知厂商 token 前缀、连接串口令、URL query 凭证 | 命中所在逻辑行整行 deny；JSON 字段或 shell 引号不能可靠分行则整条正文 deny | 不保留 token 前几位或尾几位；不复用 scrub 的搜索 pattern 例外 |
| password/secret/token/api-key/private-key/access-key/auth 等字段及 env assignment | 递归检查键和值、headers、嵌套 JSON/YAML、shell 引号及拼接；拒绝完整值所在行/对象 | 名字看似安全但有高风险长串也 deny；正常 SHA 只在验证后的 typed hash 字段放行 |
| PEM/SSH/PGP 私钥、证书私钥块、base64 编码的凭证材料 | 整块直到 END，缺 END 则余下整记录 deny；无法安全解析的 opaque 高熵块 deny | 不先逐行发送 BEGIN 之前或 key 中间片段 |
| `.pgpass`、kubeconfig、token/credential/auth 文件、`.env`、Secret YAML、admin 文件 | 按工具输入路径与来源 taint 拒绝整个读取结果/写入内容/diff；内容识别兜底识别 pgpass 五段、kube users/token/client-key-data、Docker auth 等 | 即使结果不再带文件名也拒；相对路径、别名、符号链接、路径大小写/分隔变体一并测 |
| `env`/`printenv`/`set`、进程环境、配置整包、终端诊断 dump | 整条输出 deny；无法判断是否混入 dump 的复合命令结果整条 deny | 不用“逐项 mask 后大部分留着”来处理未知变量 |
| 正常仓库内路径 | 经可信 checkout 映射到 `{repo, relative_path}`；仅允许规范化后仍在受管 repo 的非敏感路径 | 不上传原根；过滤 `../`、URI、转义形式、patch header 与 stderr 中路径 |
| 本机 home/tmp/root/Windows/UNC/Volumes 路径、Owner admin 区、备份/NAS 私有区 | Owner 路径或敏感路径所在行整行 deny；其他不能确证安全的本机路径也 deny | 不保留用户名、basename、宿主目录结构；只在确证普通 repo 路径时改写，不把 `$HOME/...` 当已安全 |
| 消息、用户 prompt、thinking、工具参数/结果、stdout/stderr、diff、标题/错误/URL | 同一策略，无“普通文本”旁路；标题/标签也只取通过检查的内容 | 内部元数据中的 kind/source/version/IDs 另有封闭词表和长度限制 |
| JSON/URL escapes、ANSI/OSC、CR、Unicode 分隔、跨 delta、可疑编码 | 标准化后扫描，再扫描序列化结果；有限解码深度/长度；有歧义 deny 原记录 | 禁止为寻找秘密去读取真实凭证文件；不执行载荷或联网解析 URL |

placeholder 只含 `reason_code`、规则版本、被替代事件/行范围及计数，例如 `Withheld · sensitive_file`；不含命中的原文、路径、token、未过滤 hash 或可还原片段。过滤是有版本的有限识别器，不声称能识别任意恶意隐写；发现未知格式时以禁正文优先。占位区间合并及数量上限见 §7.1，不能靠无限写 placeholder 维持完整性。

### 5.2a 已知敏感输入的传播规则（B2，按 D-SS7 A 草拟）

使用持久的 `clean → tainted` 状态，不只给单个 tool_result 打标签。关联键是本地 vendor conversation + context lineage，跨 source_epoch/session_id 保持；工具有 call_id 到结果的映射。敏感路径的读取、env dump、敏感 prompt、内容命中或无法判定的输入在可能进入模型上下文时就置 tainted；**先 fsync taint/checkpoint，再允许该因果链的任何正文入净化 spool**。有敏感读调用但结果未回、工具来源缺失、事件乱序无法证明先后时先置 tainted，不等后续消息复述再识别。

tainted 后，该上下文后续的 assistant text、thinking、工具参数/结果、diff、标题、compact summary、用户追加自由文本均整条 withheld，仅传固定词表元数据。短 token、路径片段及无标签复述不依赖 regex/熵检测。已经发出的、可证明早于敏感输入的安全事件保留；在途尚未出机且因果不明的正文转占位。扫描若晚发现已出机事件，走 §5.4 incident，不能谎称传播规则追回了它。

子线程继承输入上下文的 taint；子线程触敏后，在任何回报交给父线程前向父传播，再扩展到可能收到它消息的后代/同伴。若运行时无法给出可靠的消息交付顺序，则整棵已连接 conversation tree 在首个命中时一起 taint；未知跨线程传递也按整个已连接组处理。无可靠输入观测/顺序屏障的来源不启正文。独立且没有共享上下文/消息的 clean 会话不受牵连。

resume、fork、compact、collector/主机重启不清除 taint。状态与 source offset、上下文关系保存在 collector-only 控制区；状态丢失、损坏或配额满即对该 lineage 禁正文，不能默认为 clean。解除只允许新建无历史/摘要/工具结果导入的全新上下文，由可信 launcher 证明无继承关系；Agent 声称“秘密已忘记”、新 epoch、Owner 点继续或删除原文件都不能解除。无法证明时继续 withheld，旧 lineage 终止且不再允许 resume 后按保留策略销毁本地状态。

推荐不建立敏感值字典，只持久化有界 taint 位、ID 与关系，避免再保存秘密。每 host 最多 4,096 个 active/replay lineage、每 lineage 最多 256 条关系；越界将关联组折叠为整体 tainted，无法安全记账则关闭该 host 正文。字典匹配的可选增强及可靠性不足时的同样回退见 D-SS7 B。

### 5.3 阳性对照：SS1-F 的不可替代验收

测试夹具在隔离临时目录生成**无效假秘密**，不读本机凭证：每次生成不同的 canary 值，分别放入假 bearer/JWT/API key、PEM 多行块、假 `.pgpass`、假 kubeconfig 的 client-key-data、假 token 文件、env dump、Owner 路径形状、diff 删除行和 thinking。还放一个普通 `PUBLIC_MARKER` 与正常仓库文件名。

把同一夹具走 Codex JSONL、Claude hook+transcript、runtime log 三个真实 adapter 入口，包含跨 JSON escape、UTF-8/chunk 边界拆开的 secret。让 collector 真正生成待发送 batch；在**主机出口 transport stub** 截获所有 bytes，遍历 sanitized spool、压缩解码后的发送体、诊断日志与 API 拒收回执。预期：假秘密及其编码形式零命中，Owner/本机路径零命中，每类风险有 withheld，PUBLIC_MARKER 正常通过，源序号没有静默消失。

增加跨事件夹具：假敏感文件放短而无前缀的假值 → Read 结果 withheld → assistant 无标签复述/路径片段 → thinking/命令参数 → compact/resume/collector 重启 → 子线程回报再由父线程复述。最终出口不得出现短值及规范编码；所有受污染自由文本应有 `Withheld · tainted_context`。命中前的正常 marker 及另一独立 clean 会话中的 marker 必须通过，不能以整机全丢代替传播规则。单独移除跨事件传播（保留路径与 regex）后，同一测试必须变红；另测删除 taint 状态后 fail closed。

阴性对照保证不是“全部丢掉所以零泄露”；mutation 对照临时移除关键规则或把过滤器接到上传之后，**同一测试必须变红**。这才证明真实出口经过过滤，不接受只单测 regex。SS1-F 未通过前不开放正文上传。本文设计了该证明方法，**本次没有实现或运行它，没有记为 PASS**。

### 5.4 漏检发现与清除

检测入口：平台独立二次扫描、策略升级后的保留期回扫、Owner 的 `Report sensitive content`、本机 canary 自检/异常计数。平台扫描是补救，不能替代出机前过滤；平台发现内容意味着这次主机边界已经失败，应记录为 incident，不能称“安全拦截”。告警仅带 opaque ID、规则、来源版本，不带样本或公共 ntfy 正文。

处理次序：

1. 立即 quarantine 受影响 session/策略版本，阻止 API、SSE 和 blob 读取；暂停该来源正文上传，仍允许固定健康元数据。首个检测点同步立 read fence，不等待后台清理。
2. 在 session 锁下增加 purge generation 并写 `redaction_requested`/`redacted` tombstone；按 §7.2 将请求 seq 范围扩展至整个 segment，列 requested/effective 范围、reason、policy_version、发起身份、状态；不存原文。Owner 审计记录谁可能看过。
3. 幂等 purge worker 删 NAS 对象、所有旧版本/复制副本（若错误启用）、暂存对象、内存缓存；主机删已净化 spool 中对应范围并持久化禁止重放标记。Redis 本设计不放正文，仍清相关通知/游标。浏览器收到 invalidation 清页面、查询缓存和内存；页面刷新重新鉴权。
4. 修复规则后回扫同版本全部受管主机/保留期对象，重新跑阳性与 mutation 对照；只重传重新净化后的替代事件，保留原 seq tombstone，不覆盖原事件。
5. 只有各受影响位置返回删除证据，且所有读取路径无法再读旧正文，才标 `Purge verified`。主机离线、NAS 不通则 `Purge pending`，持续禁止读取；不能宣布物理清除完成。

推荐桶不启 versioning、Object Lock、正文备份或复制，避免不可删除副本；PG/WAL/备份只含无正文的 envelope/tombstone。**NAS 卷级快照、宿主备份、同步副本也在清除范围内**，不能只检查 S3 versioning。若现有备份卷无法排除新桶，A 必须使用可独立管理快照的存储位置；不能删除共享 PG 备份来完成会话清除。该条件无法满足时先不启正文，回 D-SS1 选项重新落实可删除的存储。若后来启正文备份，必须另定删除传播和备份恢复隔离，恢复时先重放 purge ledger 再开读；未验证不得启用。已经看见/复制的内容无法收回，若是真凭证，Owner 另行轮换；collector 不读真实凭证或擅自轮换。厂商原始 transcript 不归平台删除，若需处置由 Owner 按原来源处理。

## 6. 传输、可靠性与背压

拟新增 `/api/v1/agentrt/session-streams` 命名空间。注册返回 source 绑定与短期 append capability；token 仅准指定 tenant/host/session/epoch，不能 GET 正文、列会话、写别人的流或修改 PV1 完成状态。agentd 从既有 host 身份取得授权；Mac collector 用独立安装的窄写入凭证，不借 admin/审批 token，不把凭证继承给子进程。

默认每 1 秒或满 200 events/256 KiB（未压缩）发送一批。TLS 校验服务端身份；不能因现有 VIP/MinIO 使用 HTTP 而降级传正文。平台再校验 schema、source grant、归属、filter_version、长度和内容，错误仅返回 code/expected sequence，不回显原文。

每条含 `source_id/source_epoch/source_seq`、vendor 可用的 event/item/call ID、`observed_at`；平台加 `received_at` 和每 session 单调 `seq`。source_id 由注册分配，平台事件用自己的 source_id，不能与厂商序号相撞。同源序号同净化内容重试幂等，不同内容 409 并 quarantine；乱序缺前段返回 expected source_seq，发送方重排重试。正常到达不按机器时钟排序；跨子 session 仅展示合并视图并保留各自顺序，不声称全局因果全序。

一次 batch 的写入顺序（B3）：二次扫描 → **PG 事务锁 session，先验 grant、generation、幂等键及连续水位，并预留全部字节/对象/元数据额度** → 持久化唯一 upload reservation 与随机 object_key → 用该 reservation 写不可变对象 → 第二个事务在同一 session 锁下重验 generation/grant/水位，追加 envelope/manifest 并将 reservation 转 committed → commit → ACK → Redis 通知。每 session 只准一个未决正文 reservation，重试用同一 batch ID、内容校验值和同一 key；已提交重试直接返回原 ACK，异内容 409。校验值仅在私有索引，不作公开正文指纹。

PG 不可用或预留失败时，**不得发新 object PUT**；对象成功而第二事务失败时保留 reservation 与计费，不另生随机 key。恢复先核验同 key 对象再完成/撤销；不能因超时把未查明的对象额度释放。对象失败不能 ACK；临时、in-flight、orphan 和已删但未确认物理回收的数据都计入 cap，删除确认后才释放存量额度，日写入额度不返还。后台一天内 GC 是清理目标，不是容量防线。读时缺对象显示 `History unavailable` 并告警；purge 也扫描 reservation/暂存前缀，不能只删已引用对象。D-SS1 B 使用同等预留/admission 约束，正文与索引可改为单 PG 事务。

正文拒收返回固定 reason 和该批序号，不无穷重发相同坏批；collector 用同一 source_seq 范围补交无正文 withheld/gap 控制记录，平台明确允许“未提交的被拒批→占位”转换。已经 commit 的批不得换内容。每次 ACK/健康 POST 可带仅属于该 source 的 purge fence/策略升级指令；离线恢复必须先同步 fence 再重放 spool，避免清掉后又上传。

Redis **只放 session_id、committed_seq、generation 等通知，不放正文**；通知 TTL 10 分钟、每环境最多 10,000 项。Redis 丢失可从 PG 水位重建；API 可改短轮询 PG，历史不丢。慢 SSE 客户端缓冲最多 256 KiB，超出发 `resync_required` 并断开，让客户端从持久化游标补读，不让慢客户端拖垮 ingest。

净化传输队列仅持久化净化结果与水位（fsync 后推进 source offset，收到 durable ACK 后删对应 spool），与有界 raw 捕获分开计量。默认每 session 128 MiB、每 host 1 GiB、最老 24 小时，内存队列每 host 8 MiB；另保留每 host 16 MiB 固定元数据应急区。503/断网指数退避 1–60 秒加 jitter；429 按 Retry-After；401 刷新窄身份，连续失败标 `Upload blocked`；不把失败正文写进重试日志。

达到限额后继续排空 vendor pipe，停止接收新正文，合并记录 `gap{source range, reason=spool_full|expired|oversize}`；先保护既有未 ACK 内容，不默默覆盖旧数据。应急区也满时置本机持久故障位，恢复后报告 `Coverage unknown since ...`，不编造精确丢失数量。磁盘读/过滤/网络线程都与租约心跳分离；collector 坏了不续租、不撤销租约、不阻止 4.1 发布。

### 6.1 封口、补传与本地清理（C1）

执行租约只管执行。观测 grant 属于独立 collector；结束时可信捕获器记录 `seal{attempt, epoch, source_id, final_offset, final_source_seq, ended_at}`，其本机服务身份认证，执行进程无权签发。封口后只能补 `source_seq ≤ final_source_seq` 的历史，不能再追加执行活动；新 attempt/epoch 获独立流。平台离线时 seal 本地 fsync，恢复先同步 fence，再提交 seal 并换取 replay grant；服务器用既有结束事实校验，无法校验只收固定 gap，不凭旧执行 token 重开 append。

每条 spool 从本地首次捕获起最多 24 小时（重启/重试不刷新），结束封口后的 replay grant 最晚 ended_at+24h 失效，取两者较早值。时间回拨/无法证明年龄时拒正文补传。正文 grant 到期仍允许 collector 在 session 元数据 90 天期限内，通过独立固定 schema 的 `seal/gap` 归档通道报告封口范围内丢失区间；每 session 合并更新一份终结摘要，不接受正文/任意字符串。过 90 天只更新已预分配的 host coverage 故障计数，不重建过期 session。所有 replay/归档都检查 purge generation。

净化 spool、taint、seal 与 offset journal 存在 collector-owned 根，**位于 attempt `.out` 和 worktree 之外**。进程 EOF 后捕获器先冻结输入水位；settle/sweep 前必须拿到本地 handoff receipt：到 final_offset 的内容已净化 fsync，或捕获器已持久化对应缺口。最多等本地交接 5 秒，超时由可信 launcher 写 `tail_handoff_failed` 固定缺口再清 raw；这个 5 秒不是网络补传窗口。无需等平台 ACK，任务可结束，独立 collector 继续补传。无法写 receipt 时置预分配故障位并禁止 sweep 这份 raw，有限 raw 配额仍生效；由独立清理器重试，任务完成事实不回滚。补传、清理和租约不得共用阻塞线程。

### 6.2 原始捕获的硬上限（B3）

agentd 不能再把 stdout/stderr 直接无限写普通文件。受信捕获器持续排空 pipe，内存不足直接丢弃并计缺口；raw ring 每 session 64 MiB、每 host 512 MiB（stdout/stderr 合计），单原记录最多 1 MiB。写之前预留配额，分块轮转；即使 collector 落后也不超限，覆盖未处理块前先记 offset gap，半条逻辑记录整条 withheld，不拼接丢失边界两侧。capture diagnostics 每 host 8 MiB 固定轮转，禁止原文。collector 崩溃由 launcher 的有界 drain 接管或保持排空丢弃，不让 pipe 填满冻结任务。

厂商自写 transcript/cache 也是捕获范围内的容量风险：受管 session 状态目录须有同等 64 MiB/session、512 MiB/host raw 配额，和 agentd ring **共用**预算而非各领一份；不能可靠轮转的版本优先禁持久化并用受管事件管道。Mac 交互式无受管目录配额/可验证无损轮转时标 `Unsupported · raw_capture_unbounded`，不启该来源正文，也不擅自截断 Owner 原文件。不能把本设计的限额声称覆盖未接管的存量厂商文件。接管前只记录其不支持状态，不复制导入。持续输出的丢失必须显式 gap，任务租约仍照常；厂商自身在目录满时可能退出属于能力实验必测项，不能宣称任务完全无影响。

## 7. 存储与保留（按 D-SS1 A 草拟）

正文：NAS MinIO 新的私有桶，每环境独立，例如 `platform-session-stream-prod`；与 PG 备份桶不同，独立前缀权限、容量、速率和生命周期。不直接用现有备份 root credential。只有平台专属服务身份读写，host 没有 S3 凭证；Console 不拿预签名 URL，所有读经 API 再鉴权与审计。NAS 源站也须 TLS 或受认证加密隧道，当前仓库 HTTP 配置不是已满足证据。

元数据：控制面 PG 的新私有 schema `session_stream`（待 Owner 批准 migration），不复用 `agentrt.artifact_blob`。拟定实体如下，字段是设计边界，不是已上线 schema：

| 实体 | 主键/约束与用途 |
|---|---|
| `session` | session_id；来源唯一键；parent_session_id；绑定 revision、结束状态、capture/capabilities、最后水位、purge generation；自由文本标题也放受保护 payload |
| `binding` | binding_id；session_id + revision 唯一；external_work_id 或 attempt_id/epoch 的精确引用；不能从 title 猜；外部登记按 PV1 真实持久协议校验 |
| `event` | event_id；(session_id, seq) 唯一；(session_id, source_id, source_epoch, source_seq) 幂等；枚举、时间、对象引用、净化后的校验信息；**不含消息、命令、路径、reasoning、搜索片段** |
| `segment` | segment_id；session_id、seq 范围、随机 object_key、字节数、有效期限、过滤版本；索引指向只追加的 payload |
| `upload_reservation` | session + source_epoch + batch_id 唯一；generation、固定 object_key、最大物理字节/对象数、状态；未确认回收不释放预算 |
| `redaction` | redaction_id；session/seq 范围、generation、删除进度及 fixed reason；只追加补偿记录 |
| `view_audit` | view_audit_id；认证 principal、会话/范围、动作、结果、时间、request_id；无正文/搜索词/敏感 URL |

内容事件和 segment append-only；重试不覆盖旧正文，更正以新事件和 supersedes 引用表达。session 的当前水位/活性是可重建投影。删除是明确例外：正文按到期或安全事件删除，但 tombstone/审计继续说明何时为何不可读。无需为了“不可变”把秘密永久保存。

默认：正文按 server received_at 保留 **14 天**，长会话同样滚动到期；不能用未来 observed_at 延长。session/envelope/清除记录/查看审计保留 **90 天**，无正文；未完成 purge 的最小 fence 不随 90 天删除，见 §7.1。每 session 总正文 128 MiB 或 100,000 内容事件（先到者），单逻辑原记录内存最多 1 MiB，净化后单事件最多 64 KiB；超大记录先完整过滤或整条 withheld，不能先截断再扫描。

每环境正文总 cap **20 GiB**、日摄入 **1 GiB**（不是 20 GiB/日）、metadata cap **2 GiB**；80% 提示，90% 限流，到分区硬上限按 §7.1 拒绝。容量默认是预算，不是测得的 NAS 余量；不自动删除未到期正文给新数据腾位置。生命周期作兜底，平台按 expires_at 立即拒绝读，到期删除任务的可见延迟目标 ≤ 1 小时。批/segment 统一最大 256 KiB、200 events；小对象同样消耗对象额度，SS2-Q 必须测物理开销，不能只量 payload 长度。

本地 spool 保留最多 24 小时与服务器 14 天不同；满额有缺口不承诺离线无限补齐。成本实测前只给算法：平均 20 个会话 × 20 MiB/天 × 14 天 ≈ 5.5 GiB 正文，另加索引、小对象和冗余。实际高于预算就显示受限，不以挤占备份卷维持“实时”。

### 7.1 全路径配额与控制容量（B3，按 D-SS8 A 草拟）

所有配额是并发原子预留，先分配后写；进程重启从 durable reservation 恢复，不将内存计数清零。字节数取存储分配单位向上取整，包含封装、索引、临时副本；未知上界拒绝。容量与条数任一耗尽即停止该类别 admission。推荐限额如下，SS2-Q 要以实际磁盘/对象/PG 分配量核验：

| 计量对象 | 硬边界与满额行为 | 释放条件 |
|---|---|---|
| host raw / sanitized / diagnostics / 控制区 | 512 MiB / 1 GiB / 8 MiB / 16 MiB；同 host 所有来源共享；最多 4,096 个 active/replay session | raw 轮转前有 gap；spool ACK/TTL；控制槽只在 seal/replay/fence 不再需要后回收 |
| host 控制区 16 MiB | 4,096 个每个 3 KiB 固定 session 槽 + 4 MiB host 故障/taint 及维护区；槽含 seal、taint、合并 gap、purge 水位 | 已分配槽可原位更新，不能无限 append；无空槽则拒新 capture，launcher 工作本身按既有规则运行 |
| 对象存量 | 20 GiB、100,000 objects/env；最多 128 个并发 reservation，单 session 一个；包括 committed、in-flight、orphan、临时及重试对象物理占用 | DELETE 后校验不存在且无旧 writer 再写才释放；删除失败仍占额，GC 故障只降可用性不突破 cap |
| 对象日写入 | UTC 日 1 GiB 的写入预算；每次可能产生物理写入的 PUT 前预留，包括重试；另限 10,000 PUT/day | 到日界重置速率预算；不能靠删对象退还；已存在对象核验复用不再 PUT |
| PG 普通元数据 | 2 GiB 中最多 1.25 GiB 给 session/binding/event/segment/reservation 及索引/膨胀；每 env 最多 10,000 个保留 session、1,000,000 个 event/control-range 行 | 到期分区删除并确认物理回收；预留不足拒注册/新批，已有 session 只更新预分配 coverage 槽 |
| 查看/拒绝审计 | 256 MiB 独立额度，最多 200,000 行；成功读及每个 SSE 批次必须预留 durable 记录才发正文 | 90 天到期回收；不足即拒绝新的列表/历史/body/SSE 内容交付，不牺牲审计继续读 |
| purge/fence/终结与拒绝计数 | 256 MiB 控制应急区；注册时为每 session 预分配 8 KiB 状态槽；额外最多 10,000 个 purge 工作项 | 仅确认全副本删完且旧 grant/replay 均失效后压缩为固定终态；离线未确认者长期占槽，满则拒新 session |
| PG 维护余量 | 余下 256 MiB 专用于分区回收/索引维护临时分配，正文/审计不得借用 | 物理回收确认；无维护余量不做需扩容操作，转只读/拒新 admission |

PG 2 GiB 指本功能 relation/index/膨胀/临时分配，不把共享 PG 的 WAL/备份藏在此数字中。D-SS1 A 启用前须提供专属限额 tablespace/卷或等效硬配额、单写服务 admission、以及 **WAL/归档/备份保留与磁盘硬上限** 的运维证据；仅有 SQL count 不够。共享实例无法为这些持续增长路径证明上限/保留与维护空间时，转 D-SS1 B/C 的隔离存储，不在共享盘上先上线。索引分区与 reserved slots 预建所用空间计入上表；WAL/归档应另列实际预算，不能据本稿臆测现有配置已满足。

withheld/gap 连续同因区间合并；原因交替或稀疏缺口耗尽每 session 256 个控制区间槽后，关闭该 session 新正文，用一个 `Coverage limited` 尾部范围概括后续并计数，不为每次丢弃新建一行。计数饱和写 `count_unknown`。session 注册先预留完整生命周期的控制槽，注册洪泛在分配前限速并拒绝。

不再承诺无界的“每次拒绝一行”：成功内容访问逐次 durable；拒绝按固定已认证 principal 槽或统一 anonymous 槽、固定原因、小时窗口汇总 count/first/last，不保存任意请求 ID/URL。正常额度耗尽后，仅原位更新应急聚合槽（每环境合计最多 1,024 个，包含 90 天历史）；未知 principal 进统一 overflow 槽，旧小时窗口合并成日/更粗范围，必要时整环境一个区间，标 `Audit detail reduced`，不声称保留 90 天逐小时明细。连聚合更新也失败时仍拒读，预分配故障位置 `Audit incomplete`，不声称拒绝审计完整。健康告警限速且无正文。

read fence 不依赖新建无限 tombstone：已有 session 控制槽含最高 generation/whole-session 禁读位。purge 工作项用尽时提升为整 session fence/purge，利用该 session 槽持久化进度；不能把正文/审计预算借给控制记录。磁盘/PG 故障无法更新 fence 时全局拒读/断 SSE，恢复先完成控制写入再开读。硬上限下可能长期拒绝新采集或读取，这是明确的可用性代价；清除与租约仍有各自预留资源和独立线程。

### 7.2 segment 清除与在途写入互斥（C2）

本稿选择**扩大到整个 segment 清除**，不做原地重写或安全事件搬迁。例如请求 seq 42 所在对象含 1–200，事务写 requested=42、effective=1–200 的 `Redacted · segment expanded`；这 200 条引用全部失效、保留无正文 tombstone，不能让 199 条还指向已删对象。Owner UI 显示扩大的范围和代价。段最大 256 KiB/200 events 限制附带损失；旧段不得重新激活，替代内容只能是新 seq。

purge 与 reservation/commit 共用 session 锁：先持久提高 generation、全 session read fence，取消旧 generation 的 reservation；所有 commit 必须重验 generation，旧批不能 commit。私有对象服务只接受仍有效的 reservation；PUT 前后都检查 generation。**事后拒绝 commit 仍不等于物理清除**：purge 等旧 PUT 结束或确认取消，扫描全部 reservation/key、暂存/multipart，再删和复核；未决 writer、NAS 离线或网络超时状态不明一直 pending。禁止仅因 reservation TTL 到期释放额度或标 verified。存储适配须有有界 PUT/取消与 late-write 对账，进程重启先恢复未决表，不启动已撤销写入。

相同 session 在 purge 中暂停新正文接收；可使用旧 grant 的每次 retry 先读 fence，不新建 key。旧 generation 全部 writer 已终止、主机 spool fence 已确认、全部对象删完后才解除未受污染部分的会话 fence；旧 seq tombstone 永久不能被重放覆盖（其元数据到期后也不得重新注册旧 run key）。已过 90 天而无法完成清除者保留最小撤销控制槽；满额停 admission。备份恢复先加载 ledger/撤销水位再开读写，不能通过恢复旧 reservation 复活对象。

回收完成 session 槽前撤销其 grant；已删除 session 的 append/seal/gap 一律拒绝，不自动 upsert。新注册必须对应受信 launcher 的新启动身份和当前有效 runtime/PV1 绑定授权，不接受旧 vendor ID 自报为新启动；每 host 保存单调 registration epoch 撤销下界，已回收范围不可再次登记。resume 另获新启动证明并继承旧 lineage taint/fence；本机旧状态缺失只能 metadata-only。离线 host 重新接入先同步撤销下界，不能靠等待 90 天清掉禁重放状态。

## 8. Owner 读权、Agent 隔离与审计

新列表、详情、分页、SSE、单个 payload、下载、搜索、错误和清除接口都先检查 `role=admin` **且 principal 是专门的 Owner session-view 身份**。其他 admin 工具身份也拒绝。默认不提供下载/全文搜索入口；将来新增同样适用门禁。现有共享 admin token 不能证明“是人”；启用前必须把 Owner 查看凭证与审批 MCP 身份分离，见 D-SS5。

| 调用者 | append | 列表/历史/SSE/body | 安全的进度事实 |
|---|---|---|---|
| Owner 专属 admin | 管理动作单列；不伪造来源 | 允许，可靠审计成功后才发内容 | 允许 |
| viewer/reporter/operator、任何 Agent/子 Agent、审批 MCP admin | 不凭角色自动允许 | 全部拒绝，包括自己和别人的新正文 | 只沿既有 PV1/任务接口读类型化状态 |
| 独立受管 collector 的 session grant | 只写所属 session/epoch；执行子进程不持 grant | 拒绝 | ACK、水位、固定错误 code |
| API ingest/read/purge 服务 | 服务端按职责细分 | 内部按职责；凭证不在 Agent 可读范围 | 不暴露内部下载接口 |

不能只藏 UI 导航。同步封住旧读面：

- 受保护 session 不向普通 `note`、message、artifact、thread title、通知、Loki、trace 或 CI 日志复制时间线正文。PV1 只接 `session_id`、绑定、活性/覆盖状态及可选深链，不复制 last-message/last-command。
- `get_attempt_actions` 与旧 `/attempts/{id}/actions` 对非 Owner 只能返回固定枚举/时间/退出状态或明确拒绝，不能返回 target 命令/路径字符串；Owner 可继续看标注 `Legacy actions` 的旧短流。旧条目也要受门禁，不能等 TTL 才算修好。
- 通用 `get_artifact`/搜索/导出不得再让 Agent 取得 raw `log_tail` 或伪装为 `other` 的 transcript；runtime 后续 log_tail 走私有存储，验收所需共享结果另提供过滤过、范围明确的 report/review/verify。它们是工作产物，不是整段会话转储；不能因“产物可读”而夹带聊天历史。SS5-R 必须对既有历史日志与新上传一起审计路由和标签。
- PG 私有 schema 需要独立非继承角色与强制访问控制；特别检查 pg_read_all_data、继承角色、MCP SQL、跨 schema 查询、备份下载。推荐正文只在私有 NAS 桶，PG 敏感元数据用 FORCE RLS/服务角色策略保护；Agent 无 bucket 或 Redis 管理凭证。仅 `REVOKE SELECT` 无法对抗已有全局读角色。具体 RLS/服务权限以负向实测为准。
- collector 本机输入/原 transcript 的 OS 隔离不由 HTTP ACL 解决。06 当前共 UID 且可读彼此输出是已知缺口；必须实施 §8.1，而非“先试同 UID worker，不行再隔离”。

每次列表/分页/读 body 在发字节前写 durable view_audit；SSE 每批内容先预留并提交 intended seq 区间，发送后记录 delivered/unknown，关闭、断线与续连也记，不能在长连接里无限追加正文却只记一次打开。拒绝访问按 §7.1 有界汇总身份/结果，不回显敏感参数；聚合/故障限制可见。成功读审计失败或配额不足返回 503，活动 SSE 停发并断开；缓存命中同样审计。审计证明平台交付行为与不确定范围，不声称证明人的眼睛看过哪一行。

UI 使用 `Cache-Control: no-store`，禁止 Service Worker/IndexedDB 持久化正文；SSE 用支持 Authorization header 的 fetch stream，不在 query 放 token。短期 Owner 会话需周期重新检查（目标 ≤ 30 秒）；权限撤销、purge generation 变化立即断流/清缓存，重连不复用失效授权。网络 HTTPS 身份不正确不连接。

### 8.1 宿主机身份分离与每 session 读边界（B1）

无论 collector 部署成哪种组件，都需同时满足：**collector 是独立服务身份；每个 session/attempt 的执行身份或读视图独立**。0600/0700 只有配合不同身份/强制读限制才有意义。collector 可读其获授权的捕获源；所有执行进程（含其 shell、工具、子进程）不能读 collector spool、append 安装凭证、其他 session 的 raw log/transcript 或通过进程调试/继承 FD 取得它们。collector 的本地 IPC 只接受 launcher 认证的来源绑定，不允许路径任意读、列目录或回显正文；执行进程不能选择他人的 source/session。

推荐 D-SS3-I A：06 每 attempt 使用独立 UID/容器身份和私有 mount/PID 可见范围，配套目录权限、禁止跨进程 ptrace/FD 访问、最小共享只读依赖，collector 留在独立服务域；Mac 每 session 使用受管隔离实例/独立账户或 VM launcher，凭证在 collector 服务域，不能把整个 Owner HOME 挂进去。新执行身份的厂商认证也须最小授权安装，不继承 collector/Owner 查看身份。身份回收前清理私有状态并撤销旧 grant；共享 checkout 只暴露业务文件，不能成为 transcript/spool 的共享出口。OS 账户、挂载、安装和迁移是新增工程/Owner 选择，不在本次执行。

备选 D-SS3-I B：独立 collector 不变，执行端用**每 session 强制只读可见范围**隔离整个执行树及进程访问；同 UID 只有在 OS 强制策略确实覆盖 read、目录枚举、FD/ptrace、子进程和所有 executor 的启动例外时才合格。当前 write-only Landlock 和 Codex 自身可写根声明均不满足这个条件；06/Codex 嵌套 sandbox 的兼容必须另证，不能移除现有 guard 来换取通过。

Mac 现有交互式主线程若与别的会话同账户、未受强制读约束，仅标 `Unsupported · session_read_isolation`，先迁到受管启动入口；不能靠 hooks 安装改变其权限。**原生同进程主/子线程无法用 OS 身份区分**，即使厂商转发了完整事件，当前也不支持按 child session 兑现本边界；整个相关会话组只能显示固定 coverage 元数据。要支持需厂商提供可验证的每子线程工具读限制，或改成独立隔离进程并通过受控消息通道交接结果；移植后再做父子来源/taint 验收。这里没有把“按厂商账户分开”或“把主子归成一组”当作跨会话隔离。

专属 `SessionReadBoundary`：同 host、同厂商同时启两个合成 A/B session，以 B 的真实工具/命令读取 A 的 raw log、厂商 transcript、净化 spool、append 凭证，四者全部失败；加测 symlink、目录遍历、进程 FD/调试和子进程逃逸。collector 仍能读取/上报 A；同样测独立子会话与父会话。只对通过的来源声明 supported，未通过的来源不启正文且阻止全 fleet 完成结论。测试不读取任何真实会话或真实凭证。

## 9. Console 页面/API 契约（待实现）

UI 实现留 Codex，视觉方案留 Design；此处只锁数据语义和验收。入口从 PV1 同一工作项打开 Sessions，也可从所有受管会话总览打开。总览显示运行中/等待中/观测异常；会话详情含固定高度 Live 区、可暂停跟随和历史分页、父子线程、文件变更。所有控件/状态 English，工作内容保持来源语言。

| HTTP | 返回/行为 |
|---|---|
| `POST /api/v1/agentrt/session-streams` | 受管来源登记；返回 session_id、绑定 revision、append grant、expected source_seq；无任何其他会话内容 |
| `POST /session-streams/{session_id}/events` | 固定 schema 批量追加；返回 durable committed_seq、expected source_seq、policy_version；不回传原事件 |
| `POST /session-streams/{session_id}/seal` | 仅 collector 身份提交 §6.1 封口及 EOF 交接事实；返回受水位/TTL/generation 限制的 replay grant，不续执行租约 |
| `POST /session-streams/{session_id}/gaps` | 仅 collector 固定 schema 归档封口内缺口；不收正文，不新增已过期 session，按 §7.1 合并/限额 |
| `GET /session-streams?state=active&external_work_id=...&attempt_id=...&cursor=...` | Owner 专属；session summaries、coverage、as_of、next_cursor；过滤参数不改变权限 |
| `GET /session-streams/{session_id}` | 绑定/父子、能力表、等待证据、采集健康、保留范围、水位、purge generation |
| `GET /session-streams/{session_id}/events?after=...&limit=200` | 按 session seq 升序的 events、next_cursor、high_watermark、earliest_available_seq、gap/redaction/expiry 信息；最大 500 条且响应体最大 1 MiB |
| `GET /session-streams/{session_id}/live` | SSE：`event`、`watermark`、`gap`、`redacted`、`resync_required`；Last-Event-ID 用持久化游标，不能用 Redis ID 作历史游标 |
| `POST /session-streams/{session_id}/redactions` | Owner 报敏感内容或平台 scanner 创建 incident；返回 incident_id/状态；正文不放理由字段 |

表中省略前缀的路径均位于 `/api/v1/agentrt` 下；这整套 namespace 是 D-SS6 的推荐方案。purge worker 是内部受限调用，不通过通用 Agent 动作获得正文。

响应骨架（值仅示意，非线上样本）：

```json
{
  "schema": "agentrt.session_stream/v1",
  "session_id": "ss_example",
  "work_ref": {"kind": "external_work", "external_work_id": "ew_example"},
  "binding_revision": 1,
  "parent_session_id": null,
  "source": "codex_exec",
  "capabilities": {"messages": "available", "reasoning": "summary", "patches": "metadata_only"},
  "execution": {"state": "running", "waiting_on": []},
  "capture": {"state": "live", "last_source_at": "2026-10-26T12:00:00Z", "lag_ms": 420, "coverage": "partial"},
  "high_watermark": 42,
  "earliest_available_seq": 1,
  "purge_generation": 0,
  "events": [{
    "seq": 42, "source_id": "src_example", "source_epoch": 1, "source_seq": 42,
    "observed_at": "2026-10-26T12:00:00Z", "received_at": "2026-10-26T12:00:00.420Z",
    "kind": "tool_finished", "call_id": "call_example",
    "payload": {"tool_name": "Bash", "exit_code": 0},
    "visibility": "filtered", "filter_version": "ss-filter-v1"
  }],
  "next_cursor": "opaque",
  "warnings": ["patch_body_not_exposed"]
}
```

kind 封闭词表：`session_started/session_ended`、`turn_started/turn_ended`、`message`、`reasoning_summary/vendor_thinking`、`tool_started/tool_output/tool_finished`、`file_change`、`waiting/resumed`、`error`、`withheld/gap/redacted`、`binding_changed`。正文以经过过滤的 payload 返回，服务端不允许 arbitrary vendor blob。partial 仅出固定 `Message in progress` 元数据；完整逻辑记录封闭且过滤后再追加 final 正文，用 item ID 关联，不能为 UI 增量效果发送未过滤 delta，也不能修改历史。

`execution.state` 与 `capture.state` 分开：活性心跳只说明 collector/进程活着，不能证明 Agent 有进展。明确 permission_prompt、approval/question ID、厂商 rate limit、tool 超时才能说明等待；长工具按实际 timeout 显示 `Tool running`。仅无输出则 `No recent output`，collector 断连则 `Observation stale`，不能猜为 `Stuck` 或 `Needs you`。每个 waiting_on 有 kind、since、事实来源、关联 ID，可无 Owner 动作。

cursor 绑定 tenant/session、过滤条件、schema 和 retention/purge generation，服务端校验签名与范围；不能改 cursor 越权。先取 snapshot 的 committed 水位再 subscribe，连接建立后从 durable cursor 补读消除竞态。过期范围返回 410 与仍可用起点；purge 后旧游标返回 redaction/reset；未认证 401、非 Owner 403、合法 Owner 查不到 404、不可用 503、序号冲突 409、格式拒绝 422、配额 429。没有数据、被过滤、已过期、采集缺失是四种不同状态。

## 10. 待 Owner 定

完整时间线 A、出机前过滤、Owner-only、PV1 后和不阻塞 4.1 已定，以下选择不重新打开这些要求。每项推荐仅用于本稿具体化，**不是实施授权**。

| 决策 | 可选方案（均不放宽已定边界） | 推荐与代价 |
|---|---|---|
| D-SS1 新存储 | A：NAS 私有独立桶 + PG 私有索引；B：独立 Ops PG 数据库/受配额实例存正文及索引；C：独立对象服务/实例 | **A**，以可删除快照、TLS、IAM、物理配额及 WAL/归档预算可证为前提；否则选 B/C。B 事务简单但正文备份 purge 更难；C 运维成本高。B 必须拒绝所有 Agent CONNECT，不能只新增 schema |
| D-SS2 保留与容量 | A：正文 14 天、无正文审计 90 天，正文不备份；B：正文 7 天、同 caps；C：正文 30 天并批准更大预算/删除方案 | **A**；容量耗尽仍 fail closed，不保证无限历史。正文存储灾难可丢历史；未完成 purge 最小 fence 不因 90 天到期撤销 |
| D-SS3-D collector 部署（原 D-SS3 拆分） | A：Mac/06 都由独立服务管理同一个 collector binary；B：06 由 launcher 管理独立服务身份的 collector 子进程，Mac 用服务 | **A**，生命周期独立于 agentd 重启/settle；B 进程少但故障恢复/身份降权交接复杂。两者都不把凭证放入执行进程 |
| D-SS3-I 会话读隔离（B1） | A：每 attempt/session 独立 OS/容器或 VM 身份及私有读视图；B：每 session 的强制 read/进程可见范围隔离整个执行树 | **A**，需 launcher、认证、目录迁移及账户回收，已进入 SS0-I 估时；B 可减少账户管理但跨 OS/executor 验证成本高。独立 collector 对两者都是前提 |
| D-SS3-S 同进程子线程（B1） | A：改为独立隔离进程并以受控消息通道交接；B：等待厂商可验证的每子线程工具读隔离，再接原生流 | **A 先做可行性验证**；改变启动/父子交接，须保持 PV1 和 tool pins；B 无可承诺交付日期。当前原生同进程模式尚不支持，选 B 不能将全覆盖标完成 |
| D-SS5 Owner 身份 | A：独立 Owner admin principal/短期凭证且不分发给 MCP/Agent；B：Owner 登录的后端 session/BFF | **A** 最小边界，需证明浏览器/凭证与 Agent 隔离；B 登录体验更完整但新增认证工程 |
| D-SS6 接口/旧路径迁移 | A：私有 session-streams API，旧 actions/log_tail 给 Agent 只留安全类型化摘要或拒绝；B：旧 actions/artifacts 全面 Owner-only，另建 Agent 安全状态 API | **A** 迁移面积较小，仍须封住全部历史旁路；B 边界直白但下游迁移多 |
| D-SS7 taint 处理（B2） | A：敏感输入后整个上下文 lineage 持续 withheld；B：同样的 lineage 防线，加本机有界敏感值匹配以帮助诊断/精确替换 | **A**，无需再存秘密，代价是触敏后的安全自由文本也不可见。B 只缓存被动观察到的值，不主动读凭证；每 lineage 最多 64 KiB/256 值、host 4 MiB、最长 24 小时且终止销毁；淘汰、重启丢失或匹配不可靠时仍回退 A，不能以“没匹配”解除 taint |
| D-SS8 容量/审计饱和（B3） | A：采用 §6–7 硬配额、拒绝审计聚合与满额拒读/拒采集；B：独立有界审计存储，所有已 admission 的拒绝逐条落盘，入口无审计槽即 fail closed，并单列磁盘预算 | **A** 组件少，明确不能保留洪泛下每次拒绝详情；B 提供更细拒绝证据但多一套运维/清除与容量边界。两者 raw、orphan、in-flight 和 purge 都必须预留计费 |

D-SS4 厂商暴露范围已并入固定契约：捕获正常提供的 text/summary/thinking，逐来源声明能力；先启通过验收的固定版本子集只是 rollout 顺序，能与最终全覆盖要求同时成立，不再作为互斥的 Owner 选项。隐藏/加密内部推理不属于待补功能。

排除理由：同 UID 的嵌入 worker/只按厂商分账户不隔离 session；只靠 hooks 发正文无法补齐历史；只判 admin role 无法区分 Owner 与审批 MCP；给 viewer actions 加全文违反 Owner-only。这些均不列为可选 C。复用同一 Go collector/filter binary 与测试语料，避免 Go/JS 两份规则漂移。组件/凭证通过受管流程安装，不改 guard 绕过限制；本稿不创建桶、表、账户或 token。

## 11. 切片、估时与各自唯一的验收

估时为熟悉仓库的工程人日，含自检，不含 Owner 等待、发布窗口、厂商额度或排队；不占 4.1 关键路径。架构决策不是 SS0 一个测试能代签的工作。每片有独立产物、依赖与主验收；拆分后的 ID 取代初稿 SS0/SS1/SS2/SS5 的合并片。

| 片 | 范围与依赖 | 估时 | 唯一主验收（拟建，尚未执行） |
|---|---|---|---|
| SS0-P | PV1 合入后冻结身份、Unlinked/绑定事务；依赖 PV1 | 1–2 日 | `BindingAtomicity`：重复注册、绑定冲突、事务中断及 external→runtime linked，仍是同一个工作/session 历史，不越权 |
| SS0-S | 厂商固定版本能力清单、合成 schema/运行中子源发现；独立于 OS 改造 | 1–2 日 | `SourceCapabilityWitness`：正常/禁持久化/Start 丢失/Stop-only/forked skill/未知结构，逐字段对源；delayed 不冒称 live |
| SS0-I | 独立 collector 身份 + 每 session OS 读隔离、安装与存量迁移；依赖 D-SS3-D/I、SS0-S | 5–8 日 | `SessionReadBoundary`：§8.1 同 host 同厂商 A/B 四项真实工具读失败，collector 正常；覆盖 launcher 与全部 executor 例外，只此片负责 OS 隔离验收 |
| SS1-F | typed adapter/filter、持久 taint/因果屏障；依赖 SS0-S、D-SS7 | 3–4 日 | `HostEgressCanary`：§5.3 跨块及读取→无标签复述→compact/resume/子线程全序列，独立 marker 通过；移除传播测试变红 |
| SS1-H | raw/spool 硬限额、EOF handoff、独立清理；依赖 SS0-I、SS1-F | 2–3 日 | `CaptureHandoffBound`：持续输出超 raw/spool cap，collector 落后于 settle 或崩溃；磁盘有界、无静默尾部损失、有 receipt/gap、租约继续 |
| SS2-D | 私有存储、reservation/commit/ACK、seal/replay；依赖 SS0-P、D-SS1/2、SS1-H | 2–3 日 | `DurableReplayCrashMatrix`：各事务/对象/ACK 边界中断，断网跨结束 10 分钟恢复；旧流只补封口内历史，新 attempt 正常；超过 24 小时仅固定 gap；清 Redis 不丢 durable 历史 |
| SS2-Q | 并发字节/对象/元数据/应急配额与到期；依赖 SS2-D、D-SS8 | 2–3 日 | `CapacityAdmissionMatrix`：对象写成后反复令 PG commit 失败并重放；只造 withheld/注册/拒绝洪泛；实际桶/PG/磁盘有界，purge/fence 与租约仍有资源，额度不足无 PUT |
| SS3 | 06 全部在用 executor 接入、绑定、日志私有化；依赖 SS0-I、SS1-H、SS2-Q、SS5-R | 2–3 日 | `RuntimeLeaseUnaffected`：双 attempt 加重试、collector 阻塞/拒收；租约不受阻，事件不串 attempt/epoch，历史 log_tail 不从旧路由漏出 |
| SS4-C | 隔离子进程启动/受控消息交接可行性及迁移适配；依赖 D-SS3-S、SS0-S/I、SS1-F | 5–10 日 | `IsolatedChildHandoff`：独立子进程的权限、父子调用、结果/taint 传播、取消与 resume 等价；若厂商/tool pins 无法支持，输出 unsupported 并重估，不能据此宣布完整子流交付 |
| SS4 | Mac 受管包装器/hooks/tail、自动发现、PV1/父子关联；依赖 SS0-P/S/I、SS1-H、SS2-Q、SS4-C、SS5-R | 3–5 日 | `ExternalAndChildIdentity`：重复 hook/换 inode/伪 agent_id/Stop 前发现/缺源/linked，身份唯一；live 与 delayed 符合源证据 |
| SS5-R | Owner 身份与旧 REST/MCP/artifact/SQL/对象旁路迁移；依赖 D-SS5/6、SS2-D | 2–4 日 | `OwnerReadRouteMatrix`：专属 Owner 允许、其他 admin/Agent 全路由负测；旧记录/错误/导出和数据库继承角色也不可绕过；本片不重做 OS 探针 |
| SS5-A | 独立 durable 查看审计、拒绝聚合与满额拒读；依赖 SS5-R、SS2-Q | 1–2 日 | `AuditBeforeBytes`：注入审计 commit 失败/满额，body/缓存/SSE 新批零字节交付；拒绝洪泛有界且不伪称逐次完整审计 |
| SS5-P | segment 扩大清除、generation/replay fence、全副本核验；依赖 SS2-Q、SS5-R/A、SS1-H | 2–4 日 | `SegmentPurgeRace`：1–200 混合段清 42，并发 PUT/补传与逐界面重启；扩大 tombstone 无悬空引用，旧秘密永不可读，late PUT/离线 host 未确认一直 pending |
| SS6 | Console 时间线/PV1 深链、浏览器撤权；依赖 SS3/4、SS5-R/A/P | 2–3 日 | `ConsoleResumeContract`：父子流、断网重连、乱序、到期/purge/撤权，四类空态与等待事实清晰；无持久正文缓存 |
| SS7 | STG 演练、容量/告警/回退、受管来源 coverage；依赖全部前片 | 2–3 日 + 24 小时观察 | `ManagedFleetWitness`：24 小时 launcher inventory 与 Owner session 对账，p95/断平台/NAS/Redis/满额恢复；未声明缺口即失败，unsupported 来源不能冒充全覆盖 |

推荐路径基础实现 **30–49 工程人日**，另列同进程子线程替代的 SS4-C **5–10 人日**，合计 **35–59 人日 + 24 小时观察**；独立安全/架构复核另留 **2–3 人日**，总预算 **37–62 人日**。包含 B1 隔离/迁移与 B2/B3 改造，不沿用初稿 13–21 日。SS4-C 是待证的可行性/适配预算，若需厂商新能力则全覆盖日期未知，不能用这个区间保证完成。选 D-SS1 C、D-SS3-I B、D-SS5 B 或 D-SS8 B 须按选定部署重估。

开发可先用本机合成数据与 transport stub 验证 SS0-S/SS1-F/存储协议，不等待真实会话迁移。**正文采集到共享环境的启用门槛**是：PV1 契约与 Owner 选择已定，该来源 SS0-I 隔离通过，SS1-F/H、SS2-D/Q、SS5-R/A/P 全过；不能先接真正文再补权限。feature flag 默认 off，随后 STG 假内容、Owner 低风险真会话、逐来源 fleet rollout。SS7 全覆盖必须逐个清零尚不支持项或诚实报告未完成；不会以 rollout 子集重新定义 Owner 目标。回退只停新正文采集/私有页面，保留 PV1/运行时；已存数据继续鉴权、到期与清除，不能退回 viewer 正文访问。

## 12. 本次验证与尚未验证

初稿的规则/spine/PV1、代码与 CLI 观察保留为基线；Review 593 的 CLI 实测已明确标来源。本次第 2 稿实际做了：读 BRIEF/Review 593、规则与 PV1 契约，核对 P 的 confine/run/disk/settle 代码与 HEAD，查三页官方文档；逐项改正文并做差异、引用、估时与覆盖自检。未运行模型会话，未改实现、schema、hook、collector、凭证或集群，未提交。

未验证：Work 588 最终接口/上线状态；固定版本真实 schema、thinking 可见比例、交互式/后台子源实时性；**新的** OS 读隔离（现有 06 不满足已由代码确定）、独立子进程适配可行性；taint/canary/mutation；NAS 新桶/TLS/IAM/容量和快照排除；PG RLS、WAL/物理配额、审计洪泛；durable ACK/10 分钟恢复/EOF 转交/purge race/备份恢复；实际 p95 与成本；浏览器、STG、PROD 与 24 小时覆盖。上表均是待实现验收，不是本次 PASS。

Owner 已选 A 不待再次确认；下一项是评审 §10 的具体选项（含 D-SS3 拆分与新增 D-SS7/8）和切片依赖。实现仍排 PV1 后，不阻塞 4.1；本次修稿不代替 Owner 定案，也不代替安全验收。
