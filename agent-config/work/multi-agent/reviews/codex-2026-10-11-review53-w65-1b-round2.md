# Codex 复核 53 — W-65 1B（Console）第 2 轮（`af015d6..50cf157`）

2026-10-11 06:14 CDT · 只读 · 分支 `w31/w65-1b`

统筹方的处置：先改，给第 3 轮（没有必须改的，应该改的从 7 处降到 4 处，按 ADR §12.2 第 15 条自动多给一轮）。四处新的应该改的是同一个毛病出现四次：「现在能不能发送」由好几处各自决定，互相可以被抢先。第 3 轮不逐条打补丁，改形状：每个问题 id 一个纯函数的状态机管发送的全过程，再穷举事件序列断言不变量。另外统筹方的验收里有一条测试在机器忙时偶发失败（799 条里 1 条，重跑通过），一并交第 3 轮查原因。

---

VERDICT: fix first

- A — closed。`console/src/pages/QuestionPage.tsx:107` 按 id 重建表单；`console/src/pages/question/QuestionAnswerForm.tsx:157` 只发送快照的 id、选项和文字。A→B 路径不再沿用 A 的选择。
- B — closed。`console/src/pages/question/QuestionAnswerForm.tsx:52`、`:88`、`:235`：完整重复快照；选中项 label/detail、数量、recommended 变化会在同次渲染撤销确认；终态不可发送。仅另一选项变化时保留确认，符合指定条件。
- C — partly closed。`console/src/pages/question/QuestionAnswerForm.tsx:164`：网络丢失后重读失败会禁用，Check again 只 GET，成功 POST 后 GET 失败有已答回退；但响应解析异常仍允许重发。
- D — partly closed。`console/src/pages/QuestionPage.tsx:70`、`:111`：结果按 id 写缓存，晚到 A 的结果不会写 B；answered 继续刷新。但晚到的 open 可覆盖已答结果。
- E — partly closed。`console/src/api/questions.ts:537`：检查与 href 使用同次解析，原制表符复现已堵住；查询串中的第二个 `#` 仍漏检。
- F — closed。`console/src/pages/QuestionPage.tsx:78`、`:97`：来源提示覆盖所有状态；显示问题或答案文字时保密提示保留。
- G — closed。`console/src/pages/shell/needs-you/useNeedsYou.ts:97`：刷新失败为 Unknown；徽标无数字，旧行留在错误提示下，不显示 Nothing needs you right now。
- H — closed。`console/src/api/questions.ts:109`、`:197`、`:220`：原 body/mine/deliveries 错类型均拒绝；逐项对照 Go 字段，未发现仍接受错误类型的字段。三个指针字段的 null 按缺失处理。

P2 — `console/src/pages/question/QuestionAnswerForm.tsx:164`：POST 已保存但 200 响应 JSON 截断，`response.json()` 抛 SyntaxError；未进入 unknown，finally 后确认恢复。最小修复：非明确拒绝的 POST 异常均先进入 unknown，成功重读前禁用发送。
P2 — `console/src/pages/question/QuestionAnswerForm.tsx:179`、`console/src/pages/QuestionPage.tsx:70`：POST 成功，随后的 GET 返回旧 open，直接恢复可发送表单；或后台 GET 先读取 open、在已答缓存写入后才返回，将其覆盖。最小修复：立即保存 POST 答案，取消在途读取，并禁止已知终态被 open 降级。
P2 — `console/src/pages/question/QuestionAnswerForm.tsx:132`：丢响应后重读成功且 open，但选中项 label 已改变；返回记录被丢弃，旧确认仍可发送。最小修复：先将重读记录写入对应缓存，让快照校验撤销旧确认。
P2 — `console/src/pages/question/QuestionAnswerForm.tsx:259`：结果 unknown 且重读失败后，后台刷新改变选中项；快照被清空，Check again 因 active 为 null 永远不读。最小修复：核实请求使用独立保存的问题 id，不依赖确认快照。

P3 — `console/src/api/questions.ts:491`：`#progress?x=#approvals` 先截查询串，第二个 `#` 未被拒绝。最小修复：截断前检查完整 fragment 的第二个 hash。
P3 — `console/src/pages/question/QuestionRecord.tsx:32`、`:58`：允许链接显示 link_text 加目的地，但没有标为 agent text；完整 URL 有 noopener noreferrer，hash 无新窗口 target。最小修复：添加明确来源标签。
P3 — `console/src/pages/__tests__/QuestionPage.test.tsx:261`：断言没有 evil.example anchor，但输入从未包含该地址，属空检验。最小修复：提供对应恶意 link，或删掉无关断言。

测试静态核对：A–H 的新增断言能针对旧实现失败；30 秒刷新、手机高度和扩展脚本文字检查在基线已通过，报告已承认。D 测试未覆盖导航后的晚到结果或 open 覆盖已答竞态；没有发现仅验证自身 mock 的核心修复断言。
链接逐路径核对：tab/CR/LF、大写、前导斜杠、单次编码字母/hash、前导空格和查询串前第二 hash 的禁用目标被拒；混合大小写/空白危险 scheme、外域、userinfo 指向 evil、尾点、IDN、非默认端口均不可点击。双编码与 fragment 内反斜杠未归一成禁用路由，仍可成为 hash 链接。
范围：三个指定提交只改 `console/`；无新增依赖，最大改动文件 576 行。
验证限制：未运行测试、修改文件、调用 HTTP 或打开浏览器；复现按源码路径重试。内存探针因 `SecItemCopyMatching failed -50` 未执行，未计为通过。

END OF REPORT