# Codex 复核 67 — W-62 第四片：Console 的 Progress 页总览在前（`6524330..5040f32`）

2026-10-11 12:25 CDT · 只读

统筹方的处置：先改，给第 2 轮。八处应该改的、一处次要的，没有必须改的。共同点：页面在数据缺失、矛盾或还在加载时显示了一个看起来正常的结果（绿色的「现在就能办」、满格的进度条、从不完整的估算算出的夜晚数）。统筹方这一轮没能在本机预览里看实际页面（浏览器面板拒绝打开），复核末尾列的「只有人看页面才能确认」的三项，上测试环境后请 Owner 看。

---

VERDICT: fix first

- **P2 — `console/src/pages/shell/progress/ProgressSummary.tsx:98`**：申请能否办理仍取自文档 `now`。最小复现：`now:true`，审批列表加载中、无对应申请，或真实 pending 已过期，均显示绿色 “You can do this now”；有效 pending 配 `now:false` 则显示尚未轮到。修复：申请行的标记、排序和计数统一由真实状态及 `expires_at` 决定；加载中／未知显示 Unknown，过期不能显示可办。

- **P2 — `console/src/pages/shell/progress/ProgressSummary.tsx:118`**：新文字未限长、未清理控制／bidi 字符；`not_before` 还直接拼进 Console 的状态句，位于 “Agent's note:” 之前。复现：填入 10,000 字符加 U+202E，全部保留，可撑长首屏并把操作链接推远。修复：复用 `boundDocumentText`，将所有代理说明置于明确标记的独立区域。React 转义可阻止 markup 成为元素，但不能解决冒充和布局问题。

- **P2 — `console/src/pages/shell/progress/AgentWorkBoard.tsx:159`**：摘要支持新待办，详情仍只读 `owner_now`；新待办的 `actions` 没有任何显示入口。复现：仅提供 `owner_items:[{name:"Sign",now:true,actions:[{text:"签署规则"}]}]`，点 Needs you 打开空详情，还显示 “Nothing is waiting for you.”。修复：摘要、详情及空态共用新旧待办归一化结果，并沿用已有安全 action 渲染。

- **P2 — `console/src/pages/shell/progress/progressSummaryModel.ts:184`**：矛盾估算被画成正常进度。复现：`est:{done:9,total:2}` 显示 `9/2` 和绿色 100% 条；`done:1,total:0` 显示空条而无错误提示。修复：校验 `done <= total`，矛盾数据显示 Unknown；保留合法 `0/0` 的处理。

- **P2 — `console/src/pages/shell/progress/progressSummaryModel.ts:227`**：总估算把缺失字段当作零贡献。复现：两个未完成事项，一个 `mine:2`，另一个只有 `total:10`，仍显示总计 2 片，并据此计算晚数。修复：部分缺估算时显示 Unknown 或明确标记为部分小计，不能作为整体剩余时间。

- **P2 — `console/src/pages/shell/progress/ProgressSummary.tsx:271`**：Running now 未显示预计完成时间。复现：正常 running 步骤带有效 `eta_end`，右侧仍为空。修复：在无等待／失败／超时提示时显示 `eta_end`，缺失则明确显示 Unknown。

- **P2 — `console/src/pages/shell/progress/progressSummaryModel.ts:315`**：Trouble 不随实际超时变琥珀色。复现：`state:"running",started:一小时前,usual_min:10`，运行条已琥珀色，Trouble 仍绿色。修复：让一个独立计时子组件使用与运行条一致的 `pastUsual` 判定，跨阈值更新灯色。

- **P2 — `console/src/pages/shell/progress/progressSummaryModel.ts:298`**：荒唐通常用时被当成有效数据。复现：运行一小时、`usual_min:1e100`，摘要显示绿色 0% 条；未来 `started` 也被夹成正常 0%。修复：校验合理时间范围，无效值显示 Unknown，而非正常运行比例。

- **P3 — `console/src/pages/shell/progress/__tests__/progressSummary.test.tsx:454`**：`<script>` 测试遗漏 `not_before`、`takes`（standing）、`sure`、`as_of` 和 action 字符串，且只断言整体包含一次 XSS。修复：逐字段参数化断言文字显示及无新增元素；补 loading／未知申请、矛盾估算和缺项总计用例。计时测试只证明摘要外壳和 Plan 未重绘，未覆盖摘要所有子块。

已核对：范围仅改 `console/`，无新依赖，变更文件均未超过 800 行；approved refetch 会移除摘要行。折叠状态保存在文档外，摘要跳转使用代码固定 ID，文档字段不能选择跳转目标。上述模型边界已用实际模块在内存中复现；未重新运行完整构建或测试套件。

只有亲自看页面的人能检查：

- 1280×800 下真实样本是否一屏回答所有问题；A1 测试只数三个容器，无法证明高度。
- 360 px 下长文字、三段数量、运行行是否完整可读，操作入口是否可见，触摸目标是否足够。
- 点击摘要展开后是否滚到正确位置，以及字号、颜色和视觉重点是否符合原型。

END OF REPORT