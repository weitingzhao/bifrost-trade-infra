# Codex 复核 74 — W-62 第四片第 3 轮：Console 的 Progress 页（`4a65662..482e6ad`）

2026-10-11 14:03 CDT · 只读

统筹方处理：没有必须改的。复核 69 的 7 处关了 6 处、1 处部分关；新发现 5 处应该改的，全部标了「上测试环境前要改」，其中 4 处落在这一轮才加进去的三条（一个区块一个数、在哪办怎么回、球在谁脚下）上。应该改的没有比上一轮少，不满足自动加轮；统筹方按推荐加第 4 轮（上限五轮）并留痕：5 处归成三类，每类补一条兜底测试。停线条件写在 `TASK-4.md`：下次复核在这三类里还有「上测试环境前要改」的，就把第 3 轮的第一笔提交单独发，三条另出设计。

---

VERDICT: fix first

Part 1 — review 69（按原顺序）：
- P2 #1 已关闭：`console/src/pages/shell/progress/progressSummaryModel.ts:108`；pending 忽略文档 not_before，五种结束状态均移出列表；`ProgressNeedsYou.tsx:215` 提供真实申请入口。
- P2 #2 已关闭：`console/src/pages/shell/progress/NeedsYouBlock.tsx:149`；真实申请的 After／If not done 为 Unknown，文档 blocks／takes 不再写进事实句或决定颜色。
- P2 #3 部分关闭：`console/src/pages/shell/progress/ProgressPlan.tsx:52`；无估算 name 已清理限长，Waiting on／Confidence 已分离；`:211` 仍将未清理的 generated_from 拼入 Console 句子。
- P2 #4 已关闭：`console/src/pages/shell/progress/progressSummaryModel.ts:372`；完整 doing 估算加缺 detail 的 todo 事项，复现得到部分小计且无晚数。
- P2 #5 已关闭：`console/src/pages/shell/progress/progressSummaryModel.ts:453`；`per_night:1e-308` 复现为 Unknown。
- P3 #1 已关闭：`console/src/pages/shell/progress/progressPart.ts:59`；198 个 a＋emoji＋尾字符完整保留，无孤立代理项。
- P3 #2 已关闭（源码核对）：`console/src/pages/shell/progress/__tests__/progressSummary.test.tsx:511`；使用 StrictMode 和稳定基线；独立计时复现因 jsdom 崩溃未完成。

新发现：
- P2 — **before staging**：`console/src/pages/shell/progress/NeedsYouBlock.tsx:281`、`AgentWorkBoard.tsx:238`；先缓存空 Owner 列表，再让进度查询失败，页面同时出现 `Progress: Unknown` 和 `Nothing needs you now`。最小修复：将进度读取状态传入该块，失败时禁止当前全清声明。
- P2 — **before staging**：`console/src/pages/shell/progress/NeedsYouBlock.tsx:110`、`:138`；输入 `{now:true}` 或空白 deadline_text／action.text，Latest 写 `No deadline`，How to do it 留空；动作也未置于标记的代理区域。最小修复：缺失或清理后为空统一写 `Not written`，文档动作放入 Agent's note。
- P2 — **before staging**：`console/src/pages/shell/progress/progressSummaryModel.ts:81`；同一事项同时出现在 owner_items 和 standing_items、未提供 owner_all 时，复现计数为 2。最小修复：后备来源合并时按稳定身份去重，保留无法识别身份的事项。
- P2 — **before staging**：`console/src/pages/shell/progress/progressSummaryModel.ts:594`、`:601`；开放工作只有未知状态 `alien`，另有可办事项时，复现红色 `Stopped — waiting on you`，无法证明该工作等他。gap／failed 又被归为 running 并跳过空闲说明。最小修复：先校验状态，只以 running／slow 判断正在运行，其余按 L 的规则给出说明。
- P2 — **before staging**：`console/src/pages/shell/progress/ProgressPlan.tsx:211`；generated_from 输入 U+202E＋一万字符，展开计算依据后仍原样进入 `Generated from …`。最小修复：用同一清理限长函数，并将代理文字放入独立标记区域。

其他核对：
- 仅一个 Needs you 实例；owner_all 优先，无名事项仍计数；N＝a＋b＋c；真实申请加载／失败时保留 Unknown，不显示全清。
- 无工作／全部结束为绿；Owner 可办为红、未轮到为琥珀；agent waiting 为琥珀；works 缺失／非数组为 Unknown。
- ended 缺失显示 Unknown，未来 ended 显示 `for 0 min`；时钟订阅隔离已核对源码，未独立验证运行时重渲染。
- 范围仅 `console/`，无新增依赖，变更文件最大 689 行；diff 检查通过，工作树无改动；未发现 P1。
- 验证使用实际模块内存执行及服务端渲染；部分渲染用占位 UI 原语、强制展开折叠。未运行完整测试，无 HTTP／浏览器／平台调用。

only a person looking at the page can check：
- 是否一眼看清有几件事需要你，以及每件在哪里操作、如何回复。
- 长文本下真实操作入口是否仍显眼；窄屏布局、颜色和展开交互是否清楚。

END OF REPORT