> 复核 521（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/bi1-1b-card-text-guard`。报告里的 `.review/` 证据在本机 `~/agent-work/codex-review-521/.review/`，不进仓库。

本轮结论：**通过**。A1、B1 均已关闭，未发现本次修复引入的新问题。新增发现：**A 无、B 无、C 无**。

审查范围仅为 `bifrost-platform` 的 `b7f7d520c0825d9417d35384dd37c332a3d91129..ca645debff6d545ef7ad6e3fa9762921f9dad4b3`，已读第一轮报告并检查全部四个变更文件。以下源码路径相对 `~/agent-work/bi1-1b`，行号取目标提交。未重开第一轮已接受的结论。

1. **A1：closed（已关闭）。** `api/internal/questions/transition.go:148`、`:153`、`:166`、`:172`；`api/internal/questions/issuecard.go:57`。

   撤回理由仍先经过原有解析、清洗、必填和长度校验；不存在、非 open、非 requester 的卡仍按原顺序拒绝。成功撤回时，BI 卡只把固定的 `issueCardWithdrawn` 存入 `Withdrawal.Reason`，返回体也由这份已经替换理由的卡生成。调用者的 reason 没有被转存到其他字段。审计事件的 extra 仍为空，审计只记录身份、动作、目标和状态，不携带 reason（`transition.go:175`、`:177`；`api/internal/questions/service.go:224`、`:241`）。

   三条入口都收敛到这个方法：HTTP 在 `api/internal/questions/handler.go:76`；MCP `withdraw_question` 只转发 `{ reason }` 到该路由（`mcp/platform/src/questionTools.ts:142`、`:149`）；运行时 `agentRuntimeWithdraw` 将理由编码后调用同一个 `Service.Withdraw`（`api/internal/server/questions_wire.go:365`、`:370`）。未发现独立的撤回写入分支。

   冲突重试也成立：`kept := reason` 在 apply 闭包内，每次根据本次重新读取的卡判断 BI，不会复用上一次尝试的判定，也不会覆盖闭包外的原始理由。`Service.apply` 每次重跑清空结果和事件（`service.go:181`–`:188`）。隔离探针实测五种情况均通过：BI→BI 重试、非 BI→BI 重试、BI→非 BI 重试，以及并发胜者已回答／已撤回。最终 BI 结果、存储和审计均无特征文字；终态冲突返回正确的 409，未返回第一次尝试的成功体，也未追加未提交的撤回审计。证据：[conflict.log](.review/conflict.log)、[探针源码](.review/review521_test.go)。其中 work_id 改变仅用于验证闭包重新判定，不表示当前存在修改 work_id 的生产入口。

   提交自带的测试还核对了进程内 runtime session、reporter HTTP 路由、完整撤回响应及存储、审计事件、viewer 的详情／all／withdrawn 读取，以及理由校验、错误 requester、找不到卡和重复撤回（`api/internal/questions/issuecard_test.go:390`、`:425`）。运行时真实接线的新测试已静态审读（`api/internal/server/agentrt_issuecard_test.go:94`），未运行 server 包。

2. **非 BI 撤回与 `b7f7d520` 一致。** `api/internal/questions/transition.go:166`–`:172`。

   非 BI 的 `kept` 就是原先经过相同解析的 `reason`，没有其他生产逻辑改动。另用只读 Go overlay，将目标树的 `transition.go` 替换为准确的 `b7f7d520` 版本做旧侧对照；其余可执行生产代码在本次 diff 中未变化。

   共比较 **2,856 组**：4 种非 BI work_id（空、W、TD、LANE-BI），6 种入口／身份（进程内 runtime、进程内 thread、HTTP reporter／operator／admin／viewer），7 种状态或场景（open、answered、withdrawn、expired、missing、错误 requester、另有到期卡），17 种理由输入，包括清洗、中文、边界长度、空值、类型错误、未知字段、尾随 JSON 和超大请求。

   两侧状态码、完整响应字节、操作前后原始存储和审计字节**全部一致**。夹具固定 question ID 和业务时钟；另一个双方共用的 overlay 仅固定审计自动生成 ID／时间所用的时钟，使原始审计可直接逐字节比较，未删除审计字段或重新序列化审计。两份完整快照字节也完全相同，SHA-256 均为 `a6de1171deff3f23a11f597f50ffb1958b2eb1f34f5393847cff0b51e6866c39`。证据：[比较结果](.review/matrix-comparison.txt)、[旧侧日志](.review/old-matrix.log)、[新侧日志](.review/new-matrix.log)、[旧侧快照](.review/old-withdraw-matrix.json)、[新侧快照](.review/new-withdraw-matrix.json)。

3. **B1：closed（已关闭）。** `api/internal/questions/issuecard_test.go:51`、`:60`、`:73`、`:84`、`:222`。

   `snapshot` 保存存储和审计的原始字符串；`unchanged` 对两者分别做逐字节比较，`openUntouched` 再确认卡仍 open 且无 Answer／Withdrawal。BI 回答拒绝、合法答案重放、已答卡上的文字／none 拒绝、另一个选项的 already-answered、规则拒绝、HTTP 回答拒绝及新增撤回拒绝／重复撤回均调用这些检查（`:152`、`:175`、`:184`、`:190`、`:208`、`:333`、`:370`、`:452`、`:463`、`:474`）。HTTP 回答的多次拒绝在循环结束后统一比较快照。

   非 BI 回答矩阵扩为 **56 个组合**，固定业务时钟，检查状态码、完整错误或成功响应、Answer 的全部字段、原始存储、唯一新增审计的全部业务字段及原有审计记录；每个成功组合继续核对重放和 already-answered 的完整响应，并确认存储、审计字节不变（`:266`–`:306`）。成功新增审计仅豁免自然生成的 ID 和时间。另有 6 个非 BI 撤回成功组合复用完整响应／存储／审计断言（`:494`）。

   原样重用第一轮的审计变异：让被拒回答额外写入 `question.refused`。目标提交的新测试现在失败，明确报“the audit log changed”，覆盖 BI 直接回答、work_id 变体、规则和 HTTP 路由，以及非 BI 拒绝／already-answered；不再像第一轮那样漏检。证据：[audit-mutant.log](.review/audit-mutant.log)、[覆盖层](.review/audit-mutant-overlay.json)。这次失败是预期的变异检出。

验证与限制：

- 按 BRIEF 设置 `GOCACHE=~/agent-work/.cache/go-build`、`GOMODCACHE=~/agent-work/.cache/go-mod`；同时关闭模块网络下载，并把所有临时目录设在本报告目录内。
- `go test ./internal/questions/... -count=1` 在已有的 `TestHiddenFieldsAreWithheldAtTheRelay` 因本机端口监听被沙箱拒绝而中断（`door_test.go:104`，`bind: operation not permitted`）。仅跳过该项后重跑同包其余测试，**通过**，包括本次全部 questions 测试。证据：[完整运行日志](.review/questions-full.log)、[其余测试结果](.review/questions-rest.log)。
- 五种冲突重试探针通过；新旧非 BI 对照通过；第一轮审计变异按预期失败；`git diff --check b7f7d520..ca645deb` 通过。
- 未运行 server 包（包括新增运行时撤回测试）、数据库集成测试、MCP 测试、全仓 build/lint、真实 Kubernetes 冲突或部署验证；本轮仅静态核对运行时与 MCP 接线，冲突验证使用本地模拟后端。未联网、访问数据库／集群、调用 MCP、SSH 或提交；未修改被审查工作树，结束时其 `git status --short` 仍为空。所有新增报告、覆盖层、日志和临时文件只写在当前目录，Go 缓存只写在指定共享缓存。

通过：A 项无。
END OF REPORT
