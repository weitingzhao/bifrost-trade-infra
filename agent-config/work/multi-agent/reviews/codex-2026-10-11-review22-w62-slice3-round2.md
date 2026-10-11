VERDICT: fix first

发现：

- **P2 — 过期配额仍展示旧窗口用量和进度条。** `ProgressQuota.tsx:91、104` 只在 `unknown` 时隐藏它们；`reset_due` 仍显示 `used 40%`、填充条和 elapsed 刻度，结合页面“room to spare”的说明会继续暗示可用额度。应在重置已到期时仅展示池名和 `Reset due`。现有 `progressQuota.test.tsx` 还明确要求保留旧用量，需要一起修正。
- **P3 — Needs you 的 bidi 清理不完整。** `progressPart.ts:34` 漏掉 U+061C、U+200E、U+200F；直接运行现有函数已确认三者均保留。它们仍可改变 Agent-reported 行中的文字、数字和标点顺序，应补齐清理。

Review 19 逐项复核（路径均相对 `console/src/pages/shell/`）：

- **P1 卡片描述与打开请求不一致：closed。** `progress/ProgressNeedsYou.tsx:87、195`：编号、摘要、主按钮来自按 id 找到的真实请求；未找到时无编号、主按钮。
- **P2 Part of 将代理文本当事实且无边界：not closed（部分修复）。** `needs-you/ApprovalRow.tsx:69` 已独立标注并限制一行；`progress/progressPart.ts:45` 限制 120 字符，但 bidi 清理仍有上述遗漏。
- **P2 请求状态不刷新：closed。** `progress/ProgressNeedsYou.tsx:66、96`：按文档间隔轮询、聚焦刷新，并计算本地过期。
- **P2 列表不可读仍催办／已决定仍保留计时和指令：closed。** `progress/ProgressNeedsYou.tsx:178、195、209`：不可读时无主按钮、计时、行动；非 pending 仅保留真实请求行和状态。
- **P2 无效或过期配额显示健康结论：not closed（部分修复）。** `progress/quotaModel.ts:53` 已处理无效数据；`progress/ProgressQuota.tsx:91、104` 仍展示过期窗口图示。
- **P3 池行无限展开：closed。** `progress/ProgressQuota.tsx:117`：默认最多 12 行，提供 Show N more。
- **P3 每秒重绘步骤条：closed。** `progress/ProgressWorks.tsx:139`：StepBar 已不订阅时钟，按文档时间计算。

步骤状态要求已落地：`agentProgress.ts:493` 和 `progress/progressModel.ts:4、14、280` 区分 waiting/gap/Owner 状态，并限制 Running now、Now、Live。
真实请求行位于 Agent's note 之前；未发现文档摘要重新充当请求摘要或 HTML 注入。备注仍无长度限制，可拉长卡片并挤走后续请求。
验证采用静态审查和内存执行字符清理函数；未运行完整测试套件，未修改文件或调用平台／集群。

END OF REPORT