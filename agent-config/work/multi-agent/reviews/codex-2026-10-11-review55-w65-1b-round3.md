# Codex 复核 55 — W-65 1B（Console）第 3 轮（`50cf157..5f8444a`）

2026-10-11 07:18 CDT · 只读 · 分支 `w31/w65-1b`

统筹方的处置：先改，给第 4 轮（应该改的从 4 处降到 1 处，没有必须改的；一条线最多五轮）。剩下的一处：状态机的状态存在组件实例里，切到别的问题再切回来就重置了。第 4 轮把它放到组件之外、按问题 id 保存。数据层面服务端的重放规则已经兜住（同样的答案回 200 `replayed`，不同的回 409 并带已存的答案），所以这是页面承诺的问题，不是会写错记录的问题。我的验收在这一轮通过（806 条测试）。

---

VERDICT: fix first

评审 53 的七项：
- P2-1 — closed：`console/src/pages/question/useAnswerSend.ts:100–113`，截断的 200 进入 unknown；重读失败不会恢复确认。
- P2-2 — partly closed：`console/src/pages/question/answerSend.ts:146`，同次挂载内旧 open 不覆盖终态；重新挂载仍有漏洞，见下。
- P2-3 — closed：`console/src/pages/question/useAnswerSend.ts:77`、`answerSend.ts:134`，丢响应后重读的新选项进入缓存，旧确认不再可发送。
- P2-4 — closed：`console/src/pages/question/useAnswerSend.ts:135`，Check again 使用问题 id，快照清空后仍可 GET。
- P3-1 — closed：`console/src/api/questions.ts:525–528`，完整 fragment 先检查第二个 hash，再截查询串。
- P3-2 — closed：`console/src/pages/question/QuestionRecord.tsx:33`，允许链接显示 `Agent-provided link:`、原标签文字和目的地。
- P3-3 — closed：`console/src/pages/__tests__/QuestionPage.test.tsx:250`、`:263`，输入现含 evil.example，断言不再为空检验。

评审 51：
- C — partly closed：`console/src/pages/question/useAnswerSend.ts:55`，当前挂载内 unknown 已锁住，但离开后返回会丢失该状态。
- D — partly closed：`console/src/pages/QuestionPage.tsx:144`，跨 id 结果不污染当前表单；重新挂载后终态保护会丢失。
- E — closed：`console/src/api/questions.ts:507–573`，固定点解码有界、反斜杠归一、检查与 href 同源；源码复核未发现仍可点击的禁用目标或外域。

P2 — `console/src/pages/question/useAnswerSend.ts:55`、`console/src/pages/QuestionPage.tsx:144`：生命周期仅存在于组件实例，按 id 重建组件会清除 unknown/saved/closed。
最小复现：A 的 POST 丢响应、重读失败→unknown；切到 B 再回 A，让 GET 失败或挂起。缓存仍是 open，重新选择即可确认，无需成功重读。另一条：缓存已 answered，重新挂载后旧 open 被接受并覆盖它。
证据：内存探针得到 `unknown → 重新初始化 → confirming，sendable=true`；实际 `acceptQuestionRead` 探针得到缓存 `answered → open`。
最小修复：将生命周期提升为跨挂载、按 id 保存的状态，所有旧请求回调访问同一状态；补 A→B→A、发送期间卸载及缓存终态遇旧 open 的测试。

枚举：直接在内存执行原测试，两项通过；确实检查全部 66,429 个非空前缀，九个输入不同，使用页面同一 selector。
覆盖缺口：没有枚举 choose、cancel、无答案的 postRejected；focus 仅单测，未覆盖离开再返回或组件重建。不变量 5 的缓存接线也不在纯 reducer 枚举内。
接线：成功 GET 均经过 acceptQuestionRead；缓存读与额外发送条件仍在 hook/form。GET 事件 id 来自响应记录，POST 回调 id 来自请求快照。
双击：同步更新 sendRef 可阻止第二次发送；StrictMode 本身没有发送 effect。卸载后的旧回调仍会写共享缓存，缺少跨实例状态协调。
重读 open 后重新选择、确认合理：`api/internal/questions/transition.go:32–40` 对相同答案返回 200 replayed，不同答案返回含已存答案的 409。
偶发测试：`console/src/pages/shell/needs-you/__tests__/questionsNeedsYou.test.tsx:138–142` 等待全部审批组和 lineage 后才断言，原因可信；修复包含真实同步等待，也增加了超时。未独立复跑 30 次。
范围：十个改动文件均在 console/；无新增依赖，最大改动文件 714 行，无超过 800 行的改动文件。
验证限制：未写文件、调用 HTTP 或打开浏览器；React 探针因 `SecItemCopyMatching failed -50` 中止。其余页面复现按源码路径复核。
自动审批审查拒绝了包含链接和模拟 POST 的探针命令，理由是审批页地址触发“审批旁路”规则；未绕过，链接部分采用源码复核。

END OF REPORT