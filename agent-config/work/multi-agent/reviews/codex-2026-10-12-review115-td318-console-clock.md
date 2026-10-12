# Codex 复核 115 — Console 问题页的测试固定时钟（TD-318；platform `dd2cd9f`）

2026-10-12 07:54 CDT · 只读 · Cursor 实现、统筹方在 CI 镜像里重跑通过（814 条全过；改一条断言则在测试阶段失败）· 结论：可以合并。原因属实：样例数据的过期时刻写死在 2026-10-12T06:00:00Z，测试用真实时钟，过了这一刻 23 条必然失败。别的 Console 测试没有查到同样会到期的断言。

VERDICT: safe to merge
审查对象：dd2cd9f35c706815cef05b318b4646dc094f29bc；未发现阻止合并的问题，生产行为未改。
原因成立：api/internal/questions/testdata/contract/question-open.json:30 固定在 2026-10-12T06:00:00Z 过期；console/src/pages/shell/progress/progressClock.tsx:10、12 读取 Date.now()。
console/src/pages/QuestionPage.tsx:98 提供 NowClock；console/src/pages/question/QuestionAnswerForm.tsx:17、48、77 在 now >= expires_at 时禁用选项，无法选择生成 active，:115 的确认行不出现；ci-console-failed.log:940 的 23 条失败与此吻合。
console/src/pages/__tests__/QuestionPage.test.tsx:73、87 与 QuestionSendLifecycle.test.tsx:92、108 只伪造 Date，固定到 2026-10-11T12:00:00Z，并在 cleanup 后恢复；setTimeout/setInterval 与 waitFor 保持真实计时。
两文件所有 32 条用例均无需真实墙钟；QuestionPage.test.tsx:341 的过期用例使用 question-expired.json:5 的 status=expired，且该夹具 :30 的 2026-10-11T07:00:00Z 也早于固定时间，断言仍有效；没有现有跨越过期点用例被固定时钟掩盖。
git show dd2cd9f：仅上述两个测试文件各新增 7 行，没有改组件、夹具、断言、CI 或跳过测试。
独立运行限制：已在本目录 scratch/ 复制源码与现有依赖；Vitest 启动即报 SecItemCopyMatching failed -50、退出 139（含 runner/threads 尝试），未进入测试；Cursor 报称的 814/814 不计为独立验证。
其他 Console 日期风险清单（静态追踪日期与调用点，未发现另一个会因未来日期而失败或错误通过的断言）：
- console/src/components/__tests__/ReleasePolicyBanner.test.tsx:14：2026-10-15T11:00:00Z 无翻转；console/src/api/releasePolicy.ts:56、66 使用 valid/expired/remaining_seconds，不将 expires_at 与墙钟比较。
- console/src/pages/shell/progress/__tests__/progressQuota.test.tsx:66：已有 Date 固定与 :71 恢复；:101 的 2026-10-12T12:59:59Z、:91 的 2026-10-18T03:58:22Z、:131 的 2026-11-01T00:00:00Z 均无墙钟翻转。
- console/src/pages/shell/progress/__tests__/fixtures/sample-progress-w62.json:2193、2200、2207、2282、2180 的重置点（2026-10-11 10:39:59、10-12 12:59:59/13:00:00、10-15 12:00:00、10-18 03:58:22，均 UTC）由 progressSlice.test.tsx:7 消费；:66 固定 Date，均无翻转。
- 其余 progress 测试均固定 Date；releaseView.test.ts:285 显式传 now，ReleasesPage.test.tsx:206 与 approvalsApiFixture.ts:33 动态生成相对时间；ApprovalRow.test.tsx:24、cronSchedule.test.ts:34、flexEnqueueGuards.test.ts:24 显式传固定 now，均无日历到期故障。
- 非故障的未断言变化：dimensionsModel.test.ts:285、320 用固定 newest=2026-09-08 与墙钟计算 verdict（dimensionsModel.ts:95），在 2026-09-11T00:00:00Z 变 partial、09-15T00:00:00Z 变 thin；这些用例只断言规则文案/axis，未声称验证新鲜度等级；等级用例 :104 显式传日期。
END OF REPORT
