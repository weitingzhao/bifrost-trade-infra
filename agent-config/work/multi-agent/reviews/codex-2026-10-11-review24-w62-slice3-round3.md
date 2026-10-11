VERDICT: fix first

审查提交：`971b467`，相对 `a815998`。

1. **done**：过期配额行只保留标签与 “Reset due”；usage、bar、tick、pace、chip 和 note 均隐藏。`console/src/pages/shell/progress/ProgressQuota.tsx:91`。
2. **not done**：共享清洗函数已覆盖全部指定字符（`progressPart.ts:34`），但动作链接的回退标签仍可显示未清洗的文档文本。
3. **not done**：名称 120、urgency 200、动作字段 200、默认六项及 “N more” 已实现；真实请求行仍在首位（`ProgressNeedsYou.tsx:234`）。动作链接回退路径绕过长度限制。
4. **done**：Activity 使用 Console 状态措辞，`note` 不显示状态词。`console/src/pages/shell/progress/ProgressActivity.tsx:36`。

**P2 — 动作链接回退绕过清洗和长度限制。** `console/src/pages/shell/progress/ProgressNeedsYou.tsx:48` 只处理 `text` 和 `link_text`；两者为空或清洗后为空时，`console/src/api/agentProgress.ts:618`、`:635` 使用原始 `link` 作为标签。
内存复现：仅含控制字符的两个文本字段，搭配 `#` + U+200F + 5000 个字符，产生 5017 字符的可见标签，且仍含 U+200F；受信任 URL 回退也产生 5042 字符标签。
建议对最终显示标签应用共享清洗与长度限制，同时保留目标地址提示。

Review 22 已关闭项未发现回归：卡片仍描述真实请求；已决定或过期请求继续隐藏催办内容；既有步骤状态逻辑未修改。证据：`ProgressNeedsYou.tsx:118`、`:230`、`:278`。
本次 diff 未发现其他 P1/P2。完成静态审查、内存复现和 diff 检查；未运行会写缓存的测试套件。

END OF REPORT