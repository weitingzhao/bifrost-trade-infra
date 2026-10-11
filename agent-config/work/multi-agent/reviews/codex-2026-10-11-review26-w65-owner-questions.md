VERDICT: sound with changes

仅做静态只读评审；platform HEAD 为 `eb49c19`，与设计基线一致。未调用 HTTP、平台或集群，未读取凭证，未修改文件。下文 P 指 `bifrost-platform/`，I 指 `bifrost-trade-infra/`。

- **P1 — 答案可能永远回不到线程（§4、§5、§8）。** 下一回合只调 `list_questions(mine)`，默认却只列 `open`，已经 `answered` 的记录不会出现；终态还会按 300 条和 800 KiB 裁剪，与“读到之前一直在记录里”矛盾。现有裁剪确实删除最旧终态：P `api/internal/approvals/store.go:233`、`:417`、`:432`。
  第一片必须明确查询“自己的 open + answered 未确认记录”，并规定未确认答案的保留期、满额行为和丢失后的可见提示；不能依靠模型记住编号和下回合主动补查。

- **P1 — 16 KiB 请求体并不能保证存储上限（§2、§4）。** `requester` 沿用的头部取值没有长度限制：P `api/internal/approvals/handler.go:264`；它不在请求体预算内。`deliveries` 只限条数，未限定所有字符串大小；现有通知客户端对 relay 的 channel/target 直接存入：P `api/internal/approvalnotify/notify.go:375`。
  因而“一条 open 最坏约 16 KiB、永远放得下”没有成立依据。补齐所有持久化字段的字节上限，并检查最终序列化大小；现有审批 marshal 在无终态可删时仍返回超限文档（P `api/internal/approvals/store.go:233`），不能照搬为硬上限。
  每小时配额也不能按可裁剪记录统计：压力裁剪可能删掉一小时内的创建记录，随后又能建。独立保留有界的小时计数，配额、去重和创建须在同一次 update 中判定。

- **P2 — 内容哈希漏掉会改变问题含义的字段（§2、§5、§6）。** 哈希只含 title/body/options/allow_text，遗漏 recommended、urgency、meanwhile、work_id、link、ttl 等；同 key 改这些内容仍可能被当作重放，新 key 则可能错误复用别项工作的旧答案。
  分开定义“同 key 的完整请求指纹”和“重复问题指纹”，明确清理、默认值、规范序列化及去重作用域；默认 key 也要允许撤回或过期后开启新一轮。验收覆盖改推荐项、改工作项、清理后等价内容和终态重问。

- **P2 — 共享 reporter 可伪造已读，影响交付证明（§5、§8、§10）。** 文档承认冒名撤回，却遗漏冒名 ack：任何 holder 都能填别人的 session，令 Owner 看见“线程已读”。还可冒名提问、占用另一线程额度；viewer 可读所有文字答案。
  现有线程心跳虽共用 reporter，却用独立 key 保护已有线程（P `api/internal/agentthreads/threads.go:46`）。第一片至少记录真实 principal 与自报 session，把文案改为“收到 Agent 的读取确认”；是否加入问题管理凭证、是否接受全 viewer 可读，应列入 Owner 决策。

- **P2 — “答案不是批准”的平台隔离方向正确，但现状描述过强（§3.5）。** 没发现答案直接成为平台或 MCP 授权的现有路径；类型、严格解码、独立存储和不注册回答工具能维持隔离。
  但直接 C/D “照旧 403”、MCP “一定先建待批单”不准确：签名发布策略可自动放行 C 级调用（P `api/internal/server/actions_wire.go:69`、`api/internal/server/release_policy_wire.go:94`），审批创建也可返回 `call directly`（P `api/internal/approvals/service.go:162`），MCP 随后直调（P `mcp/platform/src/platformClient.ts:112`、`:127`）。
  应写成“答案不增加任何授权；动作仍遵守既有人工审批或签名策略”。shell 的“线程里点头”仍靠 Agent 理解规则（I `agent-config/CLAUDE.md:217`）；将问题答案复制进线程也不能变成批准，规则要明确禁止这种转换。W-31 前不能宣称全路径机械保证。

- **P2 — 依赖隔离测试与拟复用通知包冲突（§2、§3.2、§7、§12.11）。** `questions` 调 `approvalnotify.Redact` 或发送函数，会传递依赖 `actions`：P `api/internal/approvalnotify/notify.go:40`。按 `go list -deps` 验收必失败。
  抽出不依赖动作的清理与通知传输包；测试同时检查 questions 的传递依赖和执行路径的文件引用。import 图本身不能证明同包文件、运行时 HTTP 或 Agent 规则完全隔离。

- **P2 — 并发机制可复用，胜者与过期语义需精确（§2、§5、§12）。** flock 与 ConfigMap resourceVersion 重试属实（P `api/internal/statefile/statefile.go:139`、`api/internal/statefile/k8sstate/k8sstate.go:123`）；胜者是先成功提交者，不一定先到者。
  每次 mutate 重跑都应重新取服务端时间，按 `now >= expires_at` 判定，并重置返回值和审计事件；现有审批会在锁外固定 now（P `api/internal/approvals/service.go:358`）。补 answer/withdraw、answer/expire、双设备、锁等待跨过截止时间及响应丢失重试测试。
  sweep 后拒绝操作仍须保存 expired 和审计，不能因返回业务错误把 sweep 回滚；重复 answer 返回已存答案、重复 ack 不改时间。确认按钮发送期间禁用，409 显示服务端答案，网络超时先 GET 核对。

- **P2 — 自动 ack 与写关闭模式存在未定义行为（§6、§8）。** `wait_for_answer` 在返回前 ack，不证明模型已收到或理解；ack 失败也不应吞掉已经读到的答案。`MCP_WRITES=off` 时轮询不得顺带写 ack。
  `platformSend` 本身绕过写闸门（P `mcp/platform/src/platformClient.ts:138`）；所有问题写工具须显式检查模式，验收不能只测 `planWrite`。会话 id 映射是第一片前置条件：当前 MCP 最后回落 hostname，且没有 Codex 会话分支（P `mcp/platform/src/sessionId.ts:14`）。

- **P2 — 通知“两次”是两类通知机会，不是最多两次到达（§7、§10）。** 现有提醒失败释放 claim、超时重领，明确可能重复到达（P `api/internal/approvals/notice.go:67`）；认领后回答或撤回，也可能已有通知在途。
  明确投递语义、重试次数和终态竞态；发送不能放入会重跑的 mutate。若要求严格去重，需要持久消息标识及 relay 支持，否则验收只能保证终态不新发起通知。

- **P2 — Console 应保留独立问题页，并保护更紧急的请求（§7、§13.2）。** 当前 Needs you 是链接列表，分组描述基本准确（P `console/src/pages/shell/needs-you/NeedsYouPage.tsx:188`、`console/src/pages/shell/needs-you/ApprovalRow.tsx:33`）。
  Answer 排在 Decide 后仍会把 Run in a terminal、Check 推到下方；建议所有审批相关组先显示，问题组独立计数并限制初始展示条数。Q 编号、文本渲染和完整确认步骤值得保留，但不能阻止措辞被人理解为批准。
  本机 guard 只检查工具输入文本，不能可靠识别已打开页面上的坐标点击或当前 DOM（I `agent-config/scripts/agent-guard/preflight.js:299`、`:338`）；独立 hash 便于防误操作，不能当权限边界。
  链接禁止规则要解析并规范化目标，覆盖旧审批别名 `#maintenance?id=`，而非只匹配两个字面 hash（P `console/src/lib/shell/consoleRoutes.ts:241`）。新问题路由目前也确实未注册（`:223`）。

- **P3 — 其余现状核对基本属实（§4、§5、§7、§14）。** 审批独立 JSON、未知字段保留、500 条终态及 15 秒 workers 轮询属实（P `api/internal/approvals/store.go:18`、`:83`、`:417`；`api/internal/server/server.go:348`、`:364`）。
  审批读取 viewer、创建 operator、决定 admin；角色不足返回 401 属实（P `api/internal/approvals/handler.go:24`；`api/internal/actuation/auth.go:133`）。
  MCP 通常取 operator，令牌文件键不含 reporter，但未钉角色时可回落进程里的 admin（P `mcp/platform/src/tokenResolve.ts:6`、`:26`），§14.3 应保留这一条件；trade-satellite 是 operator（P `config/platform-auth.yaml:24`）。
  Decide/Check 来自 `approvalnotify.kindVerb`，Look 来自线程通知；relay 接受任意非空标题正文及点击地址（P `api/internal/approvalnotify/notify.go:161`；`api/internal/agentthreads/threads.go:504`；`api/internal/alertrelay/relay.go:288`）。手机仅保存审批令牌的读取回落可复用（P `console/src/api/approvals.ts:157`）。

- **P3 — §13 六项建议：** ① A 独立存储，避免审批形状和容量耦合；② 甲 独立问题页，保留确认且减少误操作；③ 乙 默认 24 小时、允许 1–168 小时，服务端截止时间权威；④ 甲 撤回并标 Agent 自述，不能补造 Owner 答案；⑤ 甲 图片暂留线程，身份与保密尚未解决；⑥ 丙 首片不做词表，固定提示始终显示，词表漏报和误报不值得形成安全暗示。
  另需 Owner 定：未确认答案保留承诺、冒名撤回/ack 的接受范围、所有 viewer 可读文字答案，以及去重是否仅限同一 requester/work。以上目前被当作实现细节或已接受风险，实际影响产品承诺。

- **P3 — §11 第一片偏大，按现状不宜承诺两轮通过。** 保留独立存储、状态机、必要配额与幂等、鉴权、五个工具、独立回答页、Needs you 入口及固定提示；把到期提醒、词表、丰富 Recently handled 展示延后，Progress、钩子、图片继续后置。
  §12 补全上述容量、未读回取、冒名 ack、四类竞态、off 模式全部写入口、通知提交边界及独立页面路由测试。轮询可作为首片运输方式，但“取回哪些记录、何时确认、保留多久”必须由程序契约持有。

END OF REPORT