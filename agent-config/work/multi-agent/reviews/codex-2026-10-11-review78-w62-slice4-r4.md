# Codex 复核 78 — W-62 第四片第 4 轮：Console 的 Progress 页，三类问题各补兜底测试（`482e6ad..74ff6de`）

2026-10-11 14:47 CDT · 只读

统筹方处理：**停线**。复核 74 的 5 处关了 4 处、1 处部分关；新发现 2 处要在上测试环境前改的，落在这一轮之前说好的三类里的两类（被拦下的链接把一万字符的主机名原样显示；同名同事项但做法不同的两件被并成一件）。停线条件写在 `TASK-4.md` 里，复核明确回答成立，照办：分支 `w31/w62-slice4` `74ff6de` 不合并，不再补。原先写的退路「第 3 轮的第一笔提交单独发」不采用：复核 74 在那一笔里也留着一处上测试环境前要改的（`generated_from`），而且它没有「一个区块一个数」，发上去会让 Owner 在 Console 上看到两处需要他的清单。改为这一页整页重新出设计：照本机看板当天定下来的样子（OWNER-SURFACE 的 A1–A12），并把三类问题在结构上堵住。

---

VERDICT: fix first
STOP CONDITION: met

Review 74 的五项复核（路径均在 `console/src/pages/shell/progress/`）：

- #1 已关闭：`NeedsYouBlock.tsx:363`；缓存空列表后读取失败，复现显示 Unknown，不再显示全清。
- #2 已关闭：`NeedsYouBlock.tsx:120`、`:129`；`{now:true}`、空白 deadline/action 均显示 Not written，动作在代理区域。
- #3 部分关闭：`progressSummaryModel.ts:126`；重复项计为一条，但同 work/name、不同动作也被丢弃。
- #4 已关闭：`progressSummaryModel.ts:660`；alien 为 Unknown；gap/failed 保留琥珀色空闲说明。
- #5 已关闭：`ProgressPlan.tsx:251`；U+202E＋一万字符已清理限长，generated_from 位于代理标记内。

新发现：

- **P2 — before staging，第一类**：`ProgressNeedsYou.tsx:33`；动作链接设为 `https://`＋一万个 `a`＋`.example/path`，被阻止后的 `link not shown: …` 提示仍渲染 10024 字符，未标记代理文字。最小修复：hostname 用共享清理限长函数，并放入独立代理标记；补有效长 hostname 用例。
- **P2 — before staging，第二类**：`progressSummaryModel.ts:126`；owner_items 和 standing_items 各含 `{work:'Open',name:'Sign',now:true}`，动作分别为 Approve A、Run B，复现只剩 Approve A，N＝1。最小修复：保留动作不同的事项，仅合并能确认相同的重复项；补差异动作测试。
- **P3**：`__tests__/progressAgentText.test.tsx:53`；walk 确实递归，但 fixture 缺 `owner_all`、`owner_now`（含 urgency）、`usage.claude.windows[].label`；部分已有叶子也因分支而不显示。最小修复：增加分支 fixture，并断言预期叶子实际被渲染；有效链接结构另测。

其他核对：

- 第一类例外均使用固定标签、图标或状态判断；未知 step/group/exit/quota 值不回显原文。上述 hostname 不属于合法例外。
- 第二类表覆盖并断言全部 18 格；独立内存 SSR 重试通过。服务端 `stale:true` 同样使 Needs you 显示 Unknown、历史行且不显示全清；表测试本身未包含该状态。
- 第三类指定复现：Owner 首步但事项 not-yet → 琥珀；另一开放工作含未知状态 → Unknown；无步骤、finished 为字符串 → 琥珀；均未错误变红或变绿。240 组随机测试不包含无步骤或字符串 finished。
- 第四笔：`AgentWorkBoard.tsx:253`、`:280` 的 Freshness 仍随时钟更新，将整个文档标为 Last known 并淡化；其余摘要保留的是已标明的历史内容，因此未发现该时钟隔离引入 A5 矛盾。
- 范围仅 `console/`；无新增依赖；变更文件最大 718 行；diff 检查通过；未发现 P1。
- 验证使用实际模块内存执行和 SSR，UI 原语使用占位组件，generated_from 复现强制展开外层折叠；未运行完整 Vitest、浏览器、HTTP 或平台调用，未修改文件。

only a person looking at the page can check：

- 是否一眼看清待办数量、操作位置与回复方式；长文本、窄屏、颜色和展开交互是否清楚。

END OF REPORT