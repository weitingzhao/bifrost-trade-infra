# Codex 复核 69 — W-62 第四片第 2 轮：Console 的 Progress 页（`5040f32..4a65662`）

2026-10-11 13:00 CDT · 只读

统筹方处理：没有必须改的，应该改的从 8 处降到 5 处，按 ADR §12.2 第 15 条自动加一轮（`~/agent-work/w62-slice4/TASK-3.md`），同一轮里加进 Owner 当天下午的三条要求（A7、A8、B5）。

---

VERDICT: fix first
A — 部分关闭：`console/src/pages/shell/progress/progressSummaryModel.ts:101`；加载／缺失申请为 Unknown，无绿色闪现；有效 pending 忽略文档 now，本地过期显示 Expired、计数为零；blocks／takes 和详情仍依赖文档。
B — 部分关闭：`console/src/pages/shell/progress/ProgressPlan.tsx:40`；主要字段已清理限长，但无估算分支漏掉 name，仍有代理文字拼入 Console 句子，截断可能破坏代理对。
C — 部分关闭：`console/src/pages/shell/progress/ProgressNeedsYou.tsx:370`；仅 owner_items 时动作可见、旧空态消失；同时提供 owner_items／owner_now 只显示一次，但摘要和详情未统一真实状态过滤。
D — 已关闭：`console/src/pages/shell/progress/progressSummaryModel.ts:246`；9/2、1/0、负数、非整数均为 Unknown，无正常进度条；合法 0/0 保留。
E — 部分关闭：`console/src/pages/shell/progress/progressSummaryModel.ts:295`；原缺字段复现显示部分小计、不算晚数；整个未完成组缺 detail 时仍被漏算。
F — 已关闭：`console/src/pages/shell/progress/progressSummaryModel.ts:441`；有效 eta_end 显示时间，缺失为 Unknown，等待／失败／逾期保留提示。
G — 已关闭：`console/src/pages/shell/progress/ProgressSummary.tsx:418`；独立 TroubleGauge 订阅时钟，实际模型跨阈值由 green 变 amber；静态外壳不订阅时钟。
H — 已关闭：`console/src/pages/shell/progress/progressSummaryModel.ts:429`；非有限、非正、超过七天的 usual_min，以及超前 61 秒的 started，均为 Unknown。
I — 部分关闭：`console/src/pages/shell/progress/__tests__/progressSummary.test.tsx:510`；逐字段脚本测试及主要边界测试已补，但固定要求初始渲染次数为 1 依赖未启用 StrictMode。

P2 — `console/src/pages/shell/progress/ProgressNeedsYou.tsx:375`：有效 pending 配 not_before，摘要显示可办，详情却显示 “Not your turn yet”；approved 后摘要移除，详情仍保留动作，且新卡没有真实申请入口。最小修复：详情复用申请状态／期限判定和 RequestCard，统一过滤或弱化已结束申请。
P2 — `console/src/pages/shell/progress/progressSummaryModel.ts:222`、`:230`：有 approval.id 时仍把文档 blocks／takes 写成 “Holding up…”／“Takes effect in…” 并给阻塞提示上色。最小复现：pending 申请加任意 blocks／takes。最小修复：真实记录缺字段时显示 Unknown，把文档说明放入明确标记的代理区域。
P2 — `console/src/pages/shell/progress/ProgressPlan.tsx:40`：无估算事项的 name 不经过清理；输入 U+202E 加一万字符，原文仍进入详情。`:64`、`:65` 也继续将代理文字拼入状态句。最小修复：所有分支先清理 name，代理说明独立标记。
P2 — `console/src/pages/shell/progress/progressSummaryModel.ts:295`：doing 组有完整的一片估算，todo 组有 items:['b'] 但没有 detail，仍输出完整 “1 slices left” 和 “1 nights”。最小修复：将未覆盖的开放事项计入缺估算项，禁止据此计算晚数。
P2 — `console/src/pages/shell/progress/progressSummaryModel.ts:285`：完整估算 mine:1、owner:0、pace.per_night:1e-308，实际渲染出 “Infinity nights”；除法结果有限，但乘十舍入溢出。最小修复：校验舍入及范围计算结果，溢出显示 Unknown。
P3 — `console/src/pages/shell/progress/progressSummaryModel.ts:15`（调用 `progressPart.ts:59`）：198 个 a 加 emoji 和尾字符，截断留下孤立 U+D83D。清理确实先于截断，bidi 已去除。最小修复：按 Unicode 码点截断，补代理对边界测试。
P3 — `console/src/pages/shell/progress/__tests__/progressSummary.test.tsx:510`：将测试包进应用使用的 StrictMode，初始计数可为 2，固定 “1” 断言失效。最小修复：记录稳定后的基线，再断言 tick 前后不变。

已核对三笔提交范围：仅七个 console/ 文件，无新增依赖，变更文件最大 529 行；工作树无改动。
验证采用实际模块的内存执行和服务端渲染；未运行完整测试套件。额外 jsdom 计时验证因运行时崩溃未完成；未调用 HTTP API、平台或集群，也未打开浏览器页面。
END OF REPORT