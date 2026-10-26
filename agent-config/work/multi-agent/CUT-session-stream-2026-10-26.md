# 切法：Agent 完整会话时间线（2026-10-26）

状态：设计稿；Owner 已选完整时间线 A，其余架构选择见 §10。Work 591，只交本文，不实施、不提交、不发布。

## 1. 目标、顺序与完成含义

Owner 在 `ops.bifrost.lan` 看见每个运行中会话说了什么、厂商实际暴露的 reasoning/thinking、命令与工具调用、输出、文件变更，以及明确的等待原因；可回看完整时间线。采集来自运行会话的系统，不靠 Agent 手写进度。正文离开宿主机前过滤，只有 Owner 的 admin 身份可以读。

已定顺序：**PV1（Work 588）后实施；不成为 4.1 的前置**。这里的 PV1 是计划视图切片，D-PV1 是架构选择，两者不混用。沿用 D-PV1 A、D-PV2 A、D-PV3 A，不再重选。`I/agent-config/WORK.md:550` 记录 Owner 10-24 的选择；本次 BRIEF 补充 10-26 的完整流 A 和排期。

这是平台通用观测能力，属于 Ops；不改变调度、验收、发布授权或任务完成规则。时间线中的“测试通过”是发言；只有原有验证事实能改变 PV1 的进度。

“完整”指支持来源在有效保留期内、厂商实际输出且通过过滤的完整事件序列。隐藏 reasoning、过滤、上限、缺失、版本不支持必须各自占位，不能把摘要或日志尾称为完整。厂商不提供的内容不推测、不解码、不补写；有界存储与无限历史不相容，超过上限显示明确缺口。

## 2. 本地证据基线

2026-10-26 只读核对。`P/` = 工作区 `bifrost-platform/`，HEAD `ed8bb2276d423085014d80fddebfe2937c60f3be`；`I/` = infra 的 `w31/session-stream` worktree，HEAD `833a2461fdea78b9f7ed6841ba0587b47fed009b`。以下是本地代码与文档，不代表已部署版本。没有查询平台、集群、NAS 或厂商 API，也没有读取真实会话正文、凭证或 Owner 目录。

| 证据 | 已有行为 | 对本切法的约束 |
|---|---|---|
| `P/api/internal/agentd/executors.go:270`、`:410` | runtime 分别运行 `codex exec --json`、`claude -p --output-format stream-json` | 复用进程出口，无需 Agent 主动报告 |
| `P/api/internal/agentd/run.go:417` | stdout/stderr 合写本机 `log.txt`，0600；另启 action collector | 当前混流可能有非 JSON 行，需适配和缺口记录 |
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

本机 CLI 观察：`codex --version` 返回 `codex-cli 0.163.0-alpha.11.2`；`codex exec --help` 明确 `--json` 将事件以 JSONL 写 stdout，`-o` 只保存最后消息，`--ephemeral` 不持久化 session。help 不枚举 event schema。消息/reasoning/命令/文件事件的进一步依据是上表仓库解析器和 fixture，因此仍须 SS0 锁定实测 schema。

本地 platform 的 `api/`、`mcp/` 搜索尚未找到 `register_external_work`，所以本文使用 PV1 已批准的设计契约作为依赖，不把 Work 588 的在制实现当成当前 main 的能力。SS0 必须以它的实际合入版本校准字段和绑定事务。

一次 `claude --help` 返回 `--forward-subagent-text`（print/stream-json 下转发子 Agent text/thinking，带 parent_tool_use_id）、`--include-hook-events`、`--include-partial-messages`、`--no-session-persistence`。随后版本/help 调用报 `SecItemCopyMatching failed -50`；本次未可靠取得 Claude 版本，未尝试修 Keychain。help 中列有开关不等于本机交互式主线程或每个模型都提供同样内容。本文没有用联网文档补齐这项未知。

## 3. 对象与自动关联

### 3.1 一个工作对象，多次会话

新增 `session_id` 是观测会话 ID，不是第二个 task，也不伪造 runtime attempt。关系：

```text
PV1 plan_node ── runtime task ── attempt_id + epoch ── session_id
             └─ external_work_id + source_run_key ── session_id
                                                   └─ child session_id
```

每个 session 有一个 canonical `work_ref`：`runtime_attempt` 或 `external_work`，以及可空的 `parent_session_id`。平台从已认证的来源和既有绑定派生 tenant、host、actor、plan_node、task、attempt；客户端不得自填他人的身份。外部 run key、vendor session ID 不含路径，必要时在本机做带密钥的稳定映射；映射表留宿主机，不上传 transcript_path、PID 命令行或 cwd。

`(tenant, host_id, source, source_run_key, source_epoch)` 唯一，注册重试返回同一 session。resume 延续 vendor 会话但启动新 `source_epoch`；fork 创建 child session；runtime 重试产生新 attempt/session，仍挂同一 task。多对一的工作关系允许多个子 Agent，不合并它们的 source_seq。

### 3.2 启动和恢复

| 来源 | 自动登记与关联 | 恢复/异常 |
|---|---|---|
| agentd on 06 | launch 已知 attempt_id、epoch、host；在本机建立固定绑定，再开采集 | 平台暂不可用先记录本地绑定；旧 epoch 仅准在结束后 5 分钟 drain 自己的尾部，不获得新租约 |
| Mac `codex exec` | PV1 包装器先 `register_external_work`，保存其 external_work_id/source_run_key；同一父进程接 JSONL，向 collector 提交绑定 | 登记失败按 PV1 不静默启动新任务；执行中上传失败只断观测，不终止任务 |
| Claude 统筹线程 | SessionStart/首个已接 hook 唤醒 collector；从可信 launcher 的工作上下文复用/登记 external_work | 不能把标题或发言中的 Work 字样当授权绑定；缺 root/node 时先自动记录 `Unlinked` 会话，继续探测上下文 |
| Claude 子 Agent | SubagentStart/Stop、parent_tool_use_id 或已验证的 transcript 父子关系自动建 child session；继承 work_ref | 不从任意目录名猜父会话；无法证实时标 `Parent unconfirmed`，不能漏掉此会话 |
| 外部工作转 runtime | 由 PV1 原子 linked 事件关联既有 task，时间线记录 binding revision | 原 external_work_id 作为 alias 保留；PV1 聚合只计一份工作，不复制历史 |

SessionStart/SubagentStart/PostToolUseFailure 的具体本机支持由 SS0 确认；已有配置并未接齐这些 hook。新增 hook 只通知本地 collector，不自行联网发送原载荷。系统级安装一次；每件工作的登记、结束、父子关系和重放自动完成。

collector 每 30 秒对账受管 launcher、已注册 PID/启动时间、hook 心跳及本地增量文件水位；只取最小进程活性，不采环境或完整 argv。发现无绑定/无权限/禁用持久化的活会话也在 Owner 列表占位，给出 coverage 原因。首轮安装自动发现允许范围内的在跑会话，从安装水位起标 `Capture started late`；不默默回传整盘旧记录。

默认覆盖已配置的 06 agentd 与 Mac 工作区 Claude/Codex 入口。任意其他应用、其他 OS 用户、绕过所有入口且无可见文件的进程不在可证覆盖内。Owner 页必须显示 detected/capturing/unlinked/unsupported 数量；这些缺口阻止“所有受管会话已覆盖”的验收结论。

## 4. 每个来源采什么

统一先生成 typed envelope，再过滤所有可能携带正文的字段；不透传 vendor 原 JSON。tool 结果是数据，不是指令。

| 来源 | 输入与事件映射 | 明确的边界 |
|---|---|---|
| runtime Codex | JSONL 中 thread/turn 生命周期；`item.*` 的 `agent_message`→message、`reasoning`→reasoning_summary、`command_execution`→tool start/end/output、`file_change`→file_change | 当前代码只提取命令/退出码/路径；不是每次 file_change 都有 diff；reasoning 的含义和完整性按版本能力标识 |
| Mac Codex | 同上，父包装器捕获 stdout，stderr 单独进入受限 diagnostics；prompt 也在本机过滤后记录 | 不用 `-o` 充当时间线；不读内部隐藏推理存储；MCP/web/其他 item 只有 SS0 schema 验证后入词表，未知种类只记占位 |
| runtime Claude | stream-json 的 assistant text、已暴露 thinking、tool_use、user tool_result、result；记录调用 ID 和父调用 ID | 目前 parser 丢弃 text/result；不能假设 tool_result 一定有 exit_code；只在字段确有值时显示 |
| Mac Claude 主线程与子线程 | hooks 负责 start/end/wait/tool 时点；collector 增量 tail 对应允许的 transcript JSONL 补齐 prompt、message、tool result、实际提供的 thinking；headless 可优先 stream-json | PostToolUse/Stop 单独不含全部会话；每个子线程需独立水位；无 transcript/权限不足时不猜正文 |
| runtime Cursor/其他执行器 | 对现有 Cursor stream-json 增加版本化适配；deterministic executor 捕获其命令、输出、退出码 | 本地注释未实测的部分不能标已覆盖；未支持厂商给 `Unsupported source`，SS7 的“所有 runtime”验收前必须补齐 |
| 平台运行事实 | lease、任务状态、审批/问题引用、限流/退出/失联 | 与厂商事件并列但标 source=platform，不把观测事件当调度事实 |

对 thinking/reasoning 只展示厂商正常接口/正常 transcript 已交给用户的可见文本，标 `Vendor-exposed reasoning` 或 `Reasoning summary`。`redacted_thinking`、signature、encrypted_content 等不传正文，不尝试解密；保留 `Not exposed by vendor`。不能承诺 OpenAI/Anthropic 的完整内部思考。

实时目标：已封闭、已过滤的事件从宿主机观察到 API 可读，p95 ≤ 3 秒（设计目标，未实测）。未封闭的流式文本先显示 `Message in progress`。为防密钥跨 delta 泄露，拼成完整逻辑消息/工具结果再过滤；长内容必须有独立安全边界，否则到限额只出 withheld。可安全解析的工具 start 先到，result 后到；不把较快的显示优先于过滤。

文件变更同时区分 `reported_by_tool` 与 `observed_diff`。工具成功只证明厂商报告改动；在工具边界/结束时对当前受管 checkout 取有界、只读 diff，可补 Bash 修改、删除、重命名和二进制标记。仅比较本次会话基线和允许路径，不上传全仓、未跟踪敏感文件或全文件快照；共享 checkout 的并发修改标 `Attribution unconfirmed`，不冒称由该会话所改。diff 的新增、删除、上下文、文件名全部过滤；敏感文件整份 diff withheld，二进制/图片不传原体。

## 5. 宿主机出口过滤

### 5.1 信任边界与固定顺序

```text
vendor process / allowed transcript
  → typed source adapter (bounded memory)
  → normalize + provenance/taint + complete logical record
  → deny sensitive file/block/line; rewrite safe repo path
  → scan normalized final serialized bytes
  → sanitized spool (0600, directory 0700)
  → authenticated TLS upload
  → platform second scanner → durable commit → live notification
```

原始 transcript/log 继续属于厂商自己的本机文件；collector 不新增一份 raw spool，不上传 raw 文件，不把解析错误行写进诊断日志。输入只开 allowlist 范围内、所属正确用户的 regular file；核验实际 inode/打开后的对象，不跟任意 symlink，不接受 FIFO、远程挂载或任意 hook 指定路径。换 inode、截断、半行、重复 hook 都有单独的 source_epoch/watermark 处理。

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

placeholder 只含 `reason_code`、规则版本、被替代事件/行范围及计数，例如 `Withheld · sensitive_file`；不含命中的原文、路径、token、未过滤 hash 或可还原片段。过滤是有版本的有限识别器，不声称能识别任意恶意隐写；发现未知格式时以禁正文优先。

### 5.3 阳性对照：SS1 的不可替代验收

测试夹具在隔离临时目录生成**无效假秘密**，不读本机凭证：每次生成不同的 canary 值，分别放入假 bearer/JWT/API key、PEM 多行块、假 `.pgpass`、假 kubeconfig 的 client-key-data、假 token 文件、env dump、Owner 路径形状、diff 删除行和 thinking。还放一个普通 `PUBLIC_MARKER` 与正常仓库文件名。

把同一夹具走 Codex JSONL、Claude hook+transcript、runtime log 三个真实 adapter 入口，包含跨 JSON escape、UTF-8/chunk 边界拆开的 secret。让 collector 真正生成待发送 batch；在**主机出口 transport stub** 截获所有 bytes，遍历 sanitized spool、压缩解码后的发送体、诊断日志与 API 拒收回执。预期：假秘密及其编码形式零命中，Owner/本机路径零命中，每类风险有 withheld，PUBLIC_MARKER 正常通过，源序号没有静默消失。

阴性对照保证不是“全部丢掉所以零泄露”；mutation 对照临时移除关键规则或把过滤器接到上传之后，**同一测试必须变红**。这才证明真实出口经过过滤，不接受只单测 regex。SS1 未通过前不开放正文上传。本文设计了该证明方法，**本次没有实现或运行它，没有记为 PASS**。

### 5.4 漏检发现与清除

检测入口：平台独立二次扫描、策略升级后的保留期回扫、Owner 的 `Report sensitive content`、本机 canary 自检/异常计数。平台扫描是补救，不能替代出机前过滤；平台发现内容意味着这次主机边界已经失败，应记录为 incident，不能称“安全拦截”。告警仅带 opaque ID、规则、来源版本，不带样本或公共 ntfy 正文。

处理次序：

1. 立即 quarantine 受影响 session/策略版本，阻止 API、SSE 和 blob 读取；暂停该来源正文上传，仍允许固定健康元数据。首个检测点同步立 read fence，不等待后台清理。
2. 追加 `redaction_requested`/`redacted` tombstone，列 session、seq 范围、reason、policy_version、发起身份、状态；不存原文。Owner 审计记录谁可能看过。
3. 幂等 purge worker 删 NAS 对象、所有旧版本/复制副本（若错误启用）、暂存对象、内存缓存；主机删已净化 spool 中对应范围并持久化禁止重放标记。Redis 本设计不放正文，仍清相关通知/游标。浏览器收到 invalidation 清页面、查询缓存和内存；页面刷新重新鉴权。
4. 修复规则后回扫同版本全部受管主机/保留期对象，重新跑阳性与 mutation 对照；只重传重新净化后的替代事件，保留原 seq tombstone，不覆盖原事件。
5. 只有各受影响位置返回删除证据，且所有读取路径无法再读旧正文，才标 `Purge verified`。主机离线、NAS 不通则 `Purge pending`，持续禁止读取；不能宣布物理清除完成。

推荐桶不启 versioning、Object Lock、正文备份或复制，避免不可删除副本；PG/WAL/备份只含无正文的 envelope/tombstone。**NAS 卷级快照、宿主备份、同步副本也在清除范围内**，不能只检查 S3 versioning。若现有备份卷无法排除新桶，A 必须使用可独立管理快照的存储位置；不能删除共享 PG 备份来完成会话清除。该条件无法满足时先不启正文，回 D-SS1 选项重新落实可删除的存储。若后来启正文备份，必须另定删除传播和备份恢复隔离，恢复时先重放 purge ledger 再开读；未验证不得启用。已经看见/复制的内容无法收回，若是真凭证，Owner 另行轮换；collector 不读真实凭证或擅自轮换。厂商原始 transcript 不归平台删除，若需处置由 Owner 按原来源处理。

## 6. 传输、可靠性与背压

拟新增 `/api/v1/agentrt/session-streams` 命名空间。注册返回 source 绑定与短期 append capability；token 仅准指定 tenant/host/session/epoch，不能 GET 正文、列会话、写别人的流或修改 PV1 完成状态。agentd 从既有 host 身份取得授权；Mac collector 用独立安装的窄写入凭证，不借 admin/审批 token，不把凭证继承给子进程。

默认每 1 秒或满 200 events/256 KiB（未压缩）发送一批。TLS 校验服务端身份；不能因现有 VIP/MinIO 使用 HTTP 而降级传正文。平台再校验 schema、source grant、归属、filter_version、长度和内容，错误仅返回 code/expected sequence，不回显原文。

每条含 `source_id/source_epoch/source_seq`、vendor 可用的 event/item/call ID、`observed_at`；平台加 `received_at` 和每 session 单调 `seq`。source_id 由注册分配，平台事件用自己的 source_id，不能与厂商序号相撞。同源序号同净化内容重试幂等，不同内容 409 并 quarantine；乱序缺前段返回 expected source_seq，发送方重排重试。正常到达不按机器时钟排序；跨子 session 仅展示合并视图并保留各自顺序，不声称全局因果全序。

一次 batch：先二次扫描 → 写不可变 NAS payload object 并确认成功 → PG 事务锁 session、验证幂等/水位、追加 envelope 和 manifest → commit → ACK committed cursor → 发 Redis 通知。写对象成功而 PG 失败产生无引用 orphan，后台一天内 GC；PG 成功而 ACK 丢失重发不重复。对象写入失败不能 ACK。事务只引用已存在且校验过的对象；读时缺对象显示 `History unavailable` 并告警，不能返回空列表。对象键是环境/session 的逻辑前缀加随机 ID，不使用正文 hash 作全局去重或暴露秘密指纹；purge 必须扫描该 session 的 orphan/暂存前缀，不能只删 PG 已引用对象。

正文拒收返回固定 reason 和该批序号，不无穷重发相同坏批；collector 用同一 source_seq 范围补交无正文 withheld/gap 控制记录，平台明确允许“未提交的被拒批→占位”转换。已经 commit 的批不得换内容。每次 ACK/健康 POST 可带仅属于该 source 的 purge fence/策略升级指令；离线恢复必须先同步 fence 再重放 spool，避免清掉后又上传。

Redis **只放 session_id、committed_seq、generation 等通知，不放正文**；通知 TTL 10 分钟、每环境最多 10,000 项。Redis 丢失可从 PG 水位重建；API 可改短轮询 PG，历史不丢。慢 SSE 客户端缓冲最多 256 KiB，超出发 `resync_required` 并断开，让客户端从持久化游标补读，不让慢客户端拖垮 ingest。

主机仅持久化净化结果与水位（fsync 后推进 source offset，收到 durable ACK 后删对应 spool）。默认每 session 128 MiB、每 host 1 GiB、最老 24 小时，内存队列 8 MiB；另保留 16 MiB 固定元数据应急区。503/断网指数退避 1–60 秒加 jitter；429 按 Retry-After；401 刷新窄身份，连续失败标 `Upload blocked`；不把失败正文写进重试日志。

达到限额后继续排空 vendor pipe，停止接收新正文，合并记录 `gap{source range, reason=spool_full|expired|oversize}`；先保护既有未 ACK 内容，不默默覆盖旧数据。应急区也满时置本机持久故障位，恢复后报告 `Coverage unknown since ...`，不编造精确丢失数量。磁盘读/过滤/网络线程都与租约心跳分离；collector 坏了不续租、不撤销租约、不阻止 4.1 发布。

## 7. 存储与保留（按 D-SS1 A 草拟）

正文：NAS MinIO 新的私有桶，每环境独立，例如 `platform-session-stream-prod`；与 PG 备份桶不同，独立前缀权限、容量、速率和生命周期。不直接用现有备份 root credential。只有平台专属服务身份读写，host 没有 S3 凭证；Console 不拿预签名 URL，所有读经 API 再鉴权与审计。NAS 源站也须 TLS 或受认证加密隧道，当前仓库 HTTP 配置不是已满足证据。

元数据：控制面 PG 的新私有 schema `session_stream`（待 Owner 批准 migration），不复用 `agentrt.artifact_blob`。拟定实体如下，字段是设计边界，不是已上线 schema：

| 实体 | 主键/约束与用途 |
|---|---|
| `session` | session_id；来源唯一键；parent_session_id；绑定 revision、结束状态、capture/capabilities、最后水位、purge generation；自由文本标题也放受保护 payload |
| `binding` | binding_id；session_id + revision 唯一；external_work_id 或 attempt_id/epoch 的精确引用；不能从 title 猜；外部登记按 PV1 真实持久协议校验 |
| `event` | event_id；(session_id, seq) 唯一；(session_id, source_id, source_epoch, source_seq) 幂等；枚举、时间、对象引用、净化后的校验信息；**不含消息、命令、路径、reasoning、搜索片段** |
| `segment` | segment_id；session_id、seq 范围、随机 object_key、字节数、有效期限、过滤版本；索引指向只追加的 payload |
| `redaction` | redaction_id；session/seq 范围、generation、删除进度及 fixed reason；只追加补偿记录 |
| `view_audit` | view_audit_id；认证 principal、会话/范围、动作、结果、时间、request_id；无正文/搜索词/敏感 URL |

内容事件和 segment append-only；重试不覆盖旧正文，更正以新事件和 supersedes 引用表达。session 的当前水位/活性是可重建投影。删除是明确例外：正文按到期或安全事件删除，但 tombstone/审计继续说明何时为何不可读。无需为了“不可变”把秘密永久保存。

默认：正文按 server received_at 保留 **14 天**，长会话同样滚动到期；不能用未来 observed_at 延长。session/envelope/清除记录/查看审计保留 **90 天**，无正文。每 session 总正文 128 MiB 或 100,000 事件（先到者），单逻辑原记录内存最多 1 MiB，净化后单事件最多 64 KiB；超大记录先完整过滤或整条 withheld，不能先截断再扫描。

每环境正文总 cap 20 GiB、日摄入 1 GiB、metadata cap 2 GiB；80% 提示，90% 限流，100% 停新正文并保留 gap。容量默认是预算，不是测得的 NAS 余量；不自动删除未到期正文给新数据腾位置。生命周期作兜底，平台按 expires_at 立即拒绝读，到期删除任务的可见延迟目标 ≤ 1 小时。避免每秒一个小对象：主机批内合并，平台以批/有界 segment 存储；SS2 必须测对象数量与 PG 写放大，必要时在 Owner 同意的 cap 内调整批频。

本地 spool 保留最多 24 小时与服务器 14 天不同；满额有缺口不承诺离线无限补齐。成本实测前只给算法：平均 20 个会话 × 20 MiB/天 × 14 天 ≈ 5.5 GiB 正文，另加索引、小对象和冗余。实际高于预算就显示受限，不以挤占备份卷维持“实时”。

## 8. Owner 读权、Agent 隔离与审计

新列表、详情、分页、SSE、单个 payload、下载、搜索、错误和清除接口都先检查 `role=admin` **且 principal 是专门的 Owner session-view 身份**。其他 admin 工具身份也拒绝。默认不提供下载/全文搜索入口；将来新增同样适用门禁。现有共享 admin token 不能证明“是人”；启用前必须把 Owner 查看凭证与审批 MCP 身份分离，见 D-SS5。

| 调用者 | append | 列表/历史/SSE/body | 安全的进度事实 |
|---|---|---|---|
| Owner 专属 admin | 管理动作单列；不伪造来源 | 允许，可靠审计成功后才发内容 | 允许 |
| viewer/reporter/operator、任何 Agent/子 Agent、审批 MCP admin | 不凭角色自动允许 | 全部拒绝，包括自己和别人的新正文 | 只沿既有 PV1/任务接口读类型化状态 |
| 受管 collector/agentd 的 session grant | 只写所属 session/epoch | 拒绝 | ACK、水位、固定错误 code |
| API ingest/read/purge 服务 | 服务端按职责细分 | 内部按职责；凭证不在 Agent 可读范围 | 不暴露内部下载接口 |

不能只藏 UI 导航。同步封住旧读面：

- 受保护 session 不向普通 `note`、message、artifact、thread title、通知、Loki、trace 或 CI 日志复制时间线正文。PV1 只接 `session_id`、绑定、活性/覆盖状态及可选深链，不复制 last-message/last-command。
- `get_attempt_actions` 与旧 `/attempts/{id}/actions` 对非 Owner 只能返回固定枚举/时间/退出状态或明确拒绝，不能返回 target 命令/路径字符串；Owner 可继续看标注 `Legacy actions` 的旧短流。旧条目也要受门禁，不能等 TTL 才算修好。
- 通用 `get_artifact`/搜索/导出不得再让 Agent 取得 raw `log_tail` 或伪装为 `other` 的 transcript；runtime 后续 log_tail 走私有存储，验收所需共享结果另提供过滤过、范围明确的 report/review/verify。它们是工作产物，不是整段会话转储；不能因“产物可读”而夹带聊天历史。SS5 必须对既有历史日志与新上传一起审计路由和标签。
- PG 私有 schema 需要独立非继承角色与强制访问控制；特别检查 pg_read_all_data、继承角色、MCP SQL、跨 schema 查询、备份下载。推荐正文只在私有 NAS 桶，PG 敏感元数据用 FORCE RLS/服务角色策略保护；Agent 无 bucket 或 Redis 管理凭证。仅 `REVOKE SELECT` 无法对抗已有全局读角色。具体 RLS/服务权限以负向实测为准。
- collector 本机输入/原 transcript 的 OS 隔离不由 HTTP ACL 解决。06 各尝试及 Mac Agent 不能读 collector spool/凭证；Mac 同用户下的原厂商 transcript 是否可被另一个 Agent 读仍须 SS0/SS5 验证。若不能用 sandbox/独立 OS 身份证明，不能声称满足跨会话防挖取，D-SS3 B 是必要后备。

每次列表/分页/读 body 在发字节前写 durable view_audit；SSE 记录打开、关闭、已授权/交付 seq 区间、断线和续连，每次补读也记；拒绝访问记尝试身份与结果，不能回显敏感参数。审计存储失败读接口 503，不无审计放行。缓存命中同样审计。审计只证明平台向谁提供了数据，不声称证明人的眼睛看过哪一行。

UI 使用 `Cache-Control: no-store`，禁止 Service Worker/IndexedDB 持久化正文；SSE 用支持 Authorization header 的 fetch stream，不在 query 放 token。短期 Owner 会话需周期重新检查（目标 ≤ 30 秒）；权限撤销、purge generation 变化立即断流/清缓存，重连不复用失效授权。网络 HTTPS 身份不正确不连接。

## 9. Console 页面/API 契约（待实现）

UI 实现留 Codex，视觉方案留 Design；此处只锁数据语义和验收。入口从 PV1 同一工作项打开 Sessions，也可从所有受管会话总览打开。总览显示运行中/等待中/观测异常；会话详情含固定高度 Live 区、可暂停跟随和历史分页、父子线程、文件变更。所有控件/状态 English，工作内容保持来源语言。

| HTTP | 返回/行为 |
|---|---|
| `POST /api/v1/agentrt/session-streams` | 受管来源登记；返回 session_id、绑定 revision、append grant、expected source_seq；无任何其他会话内容 |
| `POST /session-streams/{session_id}/events` | 固定 schema 批量追加；返回 durable committed_seq、expected source_seq、policy_version；不回传原事件 |
| `GET /session-streams?state=active&external_work_id=...&attempt_id=...&cursor=...` | Owner 专属；session summaries、coverage、as_of、next_cursor；过滤参数不改变权限 |
| `GET /session-streams/{session_id}` | 绑定/父子、能力表、等待证据、采集健康、保留范围、水位、purge generation |
| `GET /session-streams/{session_id}/events?after=...&limit=200` | 按 session seq 升序的 events、next_cursor、high_watermark、earliest_available_seq、gap/redaction/expiry 信息；最大 500 条且响应体最大 1 MiB |
| `GET /session-streams/{session_id}/live` | SSE：`event`、`watermark`、`gap`、`redacted`、`resync_required`；Last-Event-ID 用持久化游标，不能用 Redis ID 作历史游标 |
| `POST /session-streams/{session_id}/redactions` | Owner 报敏感内容或平台 scanner 创建 incident；返回 incident_id/状态；正文不放理由字段 |

后五行路径均位于 `/api/v1/agentrt` 下；这整套 namespace 是 D-SS6 的推荐方案。purge worker 是内部受限调用，不通过通用 Agent 动作获得正文。

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

kind 封闭词表：`session_started/session_ended`、`turn_started/turn_ended`、`message`、`reasoning_summary/vendor_thinking`、`tool_started/tool_output/tool_finished`、`file_change`、`waiting/resumed`、`error`、`withheld/gap/redacted`、`binding_changed`。正文以经过过滤的 payload 返回，服务端不允许 arbitrary vendor blob。partial→final 追加增量/终结事件并用 item ID 关联，UI 可合成展示，不能修改历史记录。

`execution.state` 与 `capture.state` 分开：活性心跳只说明 collector/进程活着，不能证明 Agent 有进展。明确 permission_prompt、approval/question ID、厂商 rate limit、tool 超时才能说明等待；长工具按实际 timeout 显示 `Tool running`。仅无输出则 `No recent output`，collector 断连则 `Observation stale`，不能猜为 `Stuck` 或 `Needs you`。每个 waiting_on 有 kind、since、事实来源、关联 ID，可无 Owner 动作。

cursor 绑定 tenant/session、过滤条件、schema 和 retention/purge generation，服务端校验签名与范围；不能改 cursor 越权。先取 snapshot 的 committed 水位再 subscribe，连接建立后从 durable cursor 补读消除竞态。过期范围返回 410 与仍可用起点；purge 后旧游标返回 redaction/reset；未认证 401、非 Owner 403、合法 Owner 查不到 404、不可用 503、序号冲突 409、格式拒绝 422、配额 429。没有数据、被过滤、已过期、采集缺失是四种不同状态。

## 10. 待 Owner 的架构选项

完整时间线 A、出机前过滤、Owner-only、PV1 后和不阻塞 4.1 已定，以下选择不重新打开这些要求。每项推荐仅用于本稿具体化，**不是实施授权**。

| 决策 | A | B | C | 推荐与代价 |
|---|---|---|---|---|
| D-SS1 新存储 | NAS MinIO 私有独立桶放正文 + PG 私有索引 | 独立 Ops PG 数据库放正文与索引，拒绝所有 Agent CONNECT；按日保留 | 独立新存储服务/新实例 | **A**：不把大正文打入 PG/WAL；新桶/IAM/TLS、PG migration、NAS 容量隔离仍要批准。B 事务简单，但 PG 负载及备份 purge 更难；C 运维成本最高 |
| D-SS2 保留与容量 | 14 天正文、90 天无正文审计；§7 caps，正文不备份 | 7 天、相同 caps；更小暴露和容量 | 30 天，扩大预算并设计备份删除 | **A**：两周排障窗口；不是永久档案，正文存储灾难可能丢历史；接受这一取舍后才启用 |
| D-SS3 collector 组件 | 06 嵌 agentd 的独立 worker；Mac 独立受管 `session-collector`，同一个过滤实现/版本，wrapper+hooks+tail | 每个来源独立 OS 账户/服务隔离，再统一协议 | 只在 hooks 里发送事件 | **A，须通过本机隔离验收**：不把 collector 能力交给模型；Mac 同用户隔离不成立则转 **B**。C 无法可靠补齐消息/崩溃尾部，不满足完整流 |
| D-SS4 厂商暴露范围 | 捕获其正常提供的 text、summary、thinking；能力和缺口逐会话声明 | 先只支持经固定版本实测的子集，未支持来源明确排队 | 无 | **A**：满足已选方向；SS0 确认各 CLI 版本再开正文。B 可作 rollout 策略但不能把缺来源说成总体验收完成。隐藏/加密内部 reasoning 不列为可选功能 |
| D-SS5 Owner 身份 | 独立 Owner admin principal/短期凭证，专门 allowlist；不分发给 MCP/Agent | Owner 登录的后端 session/BFF，服务端持专属身份 | 只判现有 admin role | **A** 作为最小新增边界；必须证明它与审批工具身份、Agent 可读文件/浏览器凭证隔离。B 更适合长期登录但增加认证工程；C 无法证明“只有 Owner”，不接受 |
| D-SS6 公开接口/兼容 | 独立私有 session-streams API；旧 actions/log_tail 给 Agent 只留类型化摘要或拒绝 | 将旧 actions/artifacts 全面改为 Owner-only，新建 Agent 安全状态接口 | 扩展原 viewer actions 塞全文 | **A**：迁移面积较小，但全部旁路需测试；B 边界更直白、下游迁移更多；C 违反已定访问边界，不接受 |

D-SS3 A 复用过滤规则与测试语料，不能 Go/JS 各维护一套会漂移的秘密列表；推荐同一 Go collector/filter binary 在 Mac 和 06 使用，由 wrapper/hook 通过本机受限通道喂数据。新组件的安装/凭证由受管流程完成，不修改 guard 绕过权限。NAS、认证、数据库新依赖的具体部署留实施单；本稿不创建桶、表或 token。

## 11. 切片、估时与各自唯一的验收

估时为熟悉仓库的工程人日，含该片自检，不含 Owner 等待、发布窗口、厂商额度或排队。顺序 SS0→SS1→SS2；SS3/SS4 接入后再 SS5/SS6→SS7。可以在评审中并行讨论，不占 4.1 的实施/发版关键路径。每片只有下面这个专属主验收能宣称它完成；其他片的绿灯不能替代它。

| 片 | 范围与依赖 | 估时 | 唯一主验收（拟建，尚未执行） |
|---|---|---|---|
| SS0 | PV1 合入后的真实 external_work 协议冻结；来源能力、版本和本机读隔离探针；D-SS1–6 定案 | 1–2 日 | `SourceCapabilityWitness`：同一受控任务在三类入口及 runtime 各启用厂商跑一轮，观察消息/工具/变更/父子/失败，逐字段对比源与期望表；拿不到就明确 unavailable。另以非本会话身份试读本地 transcript/spool，A 隔离不成立必须转 B，不能写 PASS |
| SS1 | 共用 typed adapter/filter、策略版本、净化 spool、拒绝诊断 | 2–3 日 | `HostEgressCanary`：§5.3 全入口假秘密 + 正常 marker + 跨块 + mutation，实查出口 bytes；任一 canary 出机或正常 marker 全丢即失败 |
| SS2 | 私有桶/索引/追加协议、ACK、配额、Redis 通知、到期基础 | 2–3 日 | `DurableReplayCrashMatrix`：在 object write/PG commit/ACK 三界面逐一断电重启并重放，再清空 Redis、模拟平台停机至 spool cap；最终每个事件恰好一份或显式 gap，历史可从 durable store 重建，硬盘不越 cap |
| SS3 | 06 agentd 接入所有在用 executor、日志尾私有化、源绑定 | 1.5–2.5 日 | `RuntimeLeaseUnaffected`：两次并发 attempt 加一次重试，collector 阻塞/平台拒收期间租约照续；流按 attempt/epoch 分开，消息/命令/变更各有证据，不能误归相邻尝试 |
| SS4 | Mac 包装器+Claude hooks/tail/子 Agent、自动发现与 PV1 同对象 | 2–3 日 | `ExternalAndChildIdentity`：一个 Codex 外部工作和一个 Claude 主/子线程经历 resume、collector crash、重复 hook、external→runtime linked；PV1 每个工作只计一次，所有会话有唯一流和正确父子，缺失 hook/transcript 可见 |
| SS5 | Owner 专属读、旧路由/SQL/Redis/对象旁路、查看审计、purge | 2–3 日 | `PrivateReadAndPurgeMatrix`：Owner A 能读并有 durable audit；全部非 Owner 身份从 REST/MCP/artifact/export/SQL/缓存/对象/本机尝试读均失败；故意让测试假秘密越过主机规则一次，平台检测后断活 SSE、清全副本、禁重放，旧游标读不到，离线主机显示 pending 而非 verified |
| SS6 | Console 最小可用时间线与 PV1 深链；视觉由 Codex/Design | 1.5–2.5 日 | `ConsoleResumeContract`：真实浏览器同时查看父子流，断网/重连/乱序/到期/purge/权限撤销后无重复漏行（显式 gap 除外）；四类空态可区分，真实等待和采集失联不混，页面缓存不留正文 |
| SS7 | STG 演练、限额与过滤告警、发布回退、所有来源验收 | 1–2 日 + 24 小时观察 | `ManagedFleetWitness`：在约定受管主机跑覆盖清单，连续 24 小时比较 launcher inventory 与 Owner 可见 session，安装前存量/运行中/已结束均有交代；测 p95、容量、到期、断 Redis/平台/NAS 后恢复，任何未声明缺口都失败 |

合计 **13–21 工程人日 + 24 小时观察**；独立安全/架构复核另留 1–2 人日（总预算 14–23），不把这份设计自检算独立复核。若需 D-SS3 B、D-SS5 B 或新加密入口，实施前重估，不偷偷吸收为小补丁。

上线门槛：PV1 契约已核对、选择已定、SS1/SS5 先过、受管来源 coverage 达标。feature flag 默认 off；先 STG 假内容、再 Owner 自己的低风险真会话，最后受管 fleet。回退只停新正文采集/私有页面，保留原 PV1 与运行时；已存数据继续鉴权、保留/清除，不能回退成旧 viewer 路由暴露正文。

## 12. 本次验证与尚未验证

已做：读规则、spine、PV1 决策/契约，检查本地 agentd/action/filter/auth/artifact/audit/MinIO 代码和配置，运行本机 CLI help/version；写设计与交叉引用自检。未改变任何实现、schema、hook、collector、凭证或集群；未提交。

未验证：Work 588 的最终实现接口/上线状态；三类来源今日真实 event schema、Claude 当前版本及 thinking 可见比例、交互式/后台子 Agent 完整性；Mac/06 当前 OS 读隔离；原始正文中的真实秘密识别率；阳性/mutation 对照；NAS 新桶/TLS/IAM/剩余空间；PG RLS/Agent SQL 旁路；durable ACK/清除/备份恢复；实际 p95、磁盘/对象成本；浏览器、STG、PROD 与 24 小时覆盖。它们是上表实施验收，不能以本次文档检查代签。

Owner 已选 A 的完整流方向不待再次确认；本稿已把待定选择具体化到可评审程度。下一项是审阅 D-SS1–6 与切片边界，实施仍排 PV1 后，不阻塞 4.1。
