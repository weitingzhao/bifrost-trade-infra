# Codex 复核 57 — W-65 1B（Console）第 4 轮（`5f8444a..2c24a51`）

2026-10-11 08:16 CDT · 只读 · 分支 `w31/w65-1b`

统筹方的处置：可以合并。复核 51 的八处、53 的七处、55 的一处全部关闭。统筹方的验收通过（814 条前端测试、类型检查、构建、后端 54 个包）。提问入口的三个分支（`w31/w65-slice0` `6e95dae`、`w31/w65-1a` `da7b774`、`w31/w65-1b` `2c24a51`）都已就绪；platform 主线在等审批单 #7，发完之后依次合并。四轮的走势：必须改的 1 → 0 → 0 → 0，应该改的 7 → 4 → 1 → 0。

---

VERDICT: safe to merge

- Review 55 的 P2 — closed：`console/src/pages/question/useAnswerSend.ts:64`、`:72`；生命周期跨挂载保留，卸载不删除条目。
- Review 51 C — closed：内存探针重试 unknown→离开→返回，GET 失败或挂起均保持 unknown，新选择不能确认；`console/src/pages/question/answerSend.ts:169`、`:174`。
- Review 51 D — closed：内存探针重试缓存 answered→重新挂载→旧 open，缓存和 store 均保持已答；`console/src/pages/question/useAnswerSend.ts:41`。
- 挂载、重新挂载及切换 id 不重置 protected 状态；StrictMode 的 setup→cleanup→setup 按源码也只撤销 confirming；`console/src/pages/question/answerSend.ts:167`。
- 淘汰仅删除 idle；没有 idle 时允许超过 50，不会丢 unknown、sending、saved、closed 或 confirming；`console/src/pages/question/answerSendStore.ts:36`。
- snapshot 引用稳定，未发现无限重渲染路径；`console/src/pages/question/answerSendStore.ts:26`、`:58`。
- 卸载后 POST 成功／失败探针通过，结果只写回原请求 id；`console/src/pages/question/useAnswerSend.ts:94`。
- store/cache 均为空时首次 open 被接受；读取 B 不改变 saved A，内存探针通过；`console/src/pages/question/useAnswerSend.ts:42`。
- 未发现绕过 acceptQuestionRead 的生产代码缓存写入；React Query 接收的返回值同样经过该函数；`console/src/pages/QuestionPage.tsx:57`。
- 枚举实际在内存执行通过：原九事件 66,429 个前缀，十四事件 579,194 个前缀，深度均为五；leave/return 全程检查不变量；`console/src/pages/question/__tests__/answerSend.test.ts:151`、`:218`。
- 可发送性使用表单同一 selector；`console/src/pages/question/QuestionAnswerForm.tsx:52`。
- 使用共享 store 的测试均有 beforeEach reset；页面测试还在 cleanup 后 reset；`console/src/pages/question/__tests__/answerSend.test.ts:207`、`console/src/pages/__tests__/QuestionSendLifecycle.test.tsx:87`、`console/src/pages/__tests__/QuestionPage.test.tsx:68`。
- 范围确为单提交 5f8444a..2c24a51，八个文件全部在 console/；无新增依赖，最大改动文件 718 行；未发现新增 P1/P2。
- 整页 reload 会清空 store，这是已接受且明确说明的边界；两个标签页不在本轮范围。
- 验证限制：Vitest/jsdom 加载因 `SecItemCopyMatching failed -50` 中止；完成的是实际模块的内存探针（React 生命周期替身），未完成 DOM 测试或真实 StrictMode 运行。未写文件、调用 HTTP 或打开浏览器。

END OF REPORT