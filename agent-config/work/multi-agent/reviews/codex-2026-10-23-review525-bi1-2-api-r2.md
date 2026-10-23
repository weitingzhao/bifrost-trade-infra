> 复核 525（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/bi1-2-api`。报告里的 `probes/`、`artifacts/` 证据在本机 `~/agent-work/codex-review-525/`，不进仓库。

# Review 525 — W-31 BI-1 切片 2，第二轮窄范围确认

结论：**A1、A2、B1、B2 均关闭；未发现修复引入的新 A。** 这里的关闭是本轮源码、测试内容及离线探针的审查结论，不表示已独立执行真库验收。

审查对象：`/Users/vision-mac-trader/agent-work/bi1-2`，HEAD `c5ad80c2caba48e976ab1b79aee6c49cff91c2ea`；仅审查 `dd29f64e..c5ad80c2` 的三个修复提交，并按 `ROUND1-RESPONSE.md` 确认已接受的修法。以下源码路径相对该工作树。第一轮已接受的范围、直接 DML 防御深度事项及另行安排的导入不重开。

## 关闭表

| 项目 | 判断 | 代码依据 | 测试依据与本轮执行情况 |
|---|---|---|---|
| A1：切换身份后保留私密正文 | **closed** | `console/src/pages/IssuePage.tsx:227`；`console/src/api/issues.ts:172`；`console/src/hooks/PlatformAuthProvider.tsx:44` | 提交的 `console/src/pages/__tests__/IssuePage.test.tsx:155`、`:176` 覆盖三种身份退出路径及旧响应晚到；本轮原缓存探针复跑不再复现，独立安全探针 **4/4 通过** |
| A2：Owner 谢绝卡无法由 crew 完成结案 | **closed** | `api/internal/agentrt/store/issueclose.go:104`、`:161`、`:184`；`api/internal/agentrt/store/issueshown.go:67`、`:75` | `TestOwnersDeclineOnHisCardLetsTheCrewDecline`（`store/issuereview524_test.go:116`）及 `TestOwnersDeclineOnARealCardCloses`（`server/agentrt_issuedecline_test.go:19`）；本轮审读且编译通过，**未执行真库测试** |
| B1：卡片收尾后仍显示等待 Owner | **closed** | `api/internal/agentrt/store/issueshown.go:25`、`:50`；`store/issueread.go:140`、`:253`、`:310`；`store/issues.go:418` | `TestIssueShowsTheOwnerOnlyWhileHisCardIsOpen`（`store/issuereview524_test.go:49`）；本轮审读且编译通过，**未执行真库测试** |
| B2：未来 cursor 被登记为 served | **closed** | `api/internal/agentrt/store/intakeupdates.go:50`、`:67`、`:150`、`:164`；`agentrtapi/intake.go:267` | `TestAFutureCursorIsRefused`（`store/issuereview524_test.go:183`）、`TestIntakeUpdatesRefuseAFutureCursor`（`agentrtapi/issuereview524_test.go:15`）已审读、编译；独立离线控制流探针通过，**未执行真库/HTTP 集成测试** |

## A：无未关闭项，无新增 A

### A1 — 身份隔离和晚到响应的防线成立

查询 key 现在包含当前 token，发请求使用同一个 token，并把 React Query 的取消信号传到 fetch；匿名时禁用查询并显示 signed-out。Provider 在身份变化时取消、移除所有 issue 查询；页面也清理其他身份的查询，并设 `gcTime: 0`。新身份不会读取旧身份的缓存，取消后的旧响应不能重新填回。

按简报原样复跑第一轮的缓存探针，失败发生在切换 viewer 后仍要求找到私密标记的旧断言处，见 [artifacts/cache-round1.txt](artifacts/cache-round1.txt)。这说明原漏洞断言已不成立；它本身不能证明其后尚未执行的 sign-out 断言安全。

因此另用实际 `PlatformAuthProvider`、`IssuePage` 和 React Query 执行了 [probes/cache-safe.node.test.tsx](probes/cache-safe.node.test.tsx)：admin→viewer、admin→trade-satellite、sign-out 均检查切换后立即及请求结束后的 DOM/缓存无旧正文；旧请求即使忽略 abort 并晚到，也检查 signal 已取消、DOM/缓存不能回填。四例全部通过，见 [artifacts/cache-safe.txt](artifacts/cache-safe.txt)。非读者请求确实使用新 token，sign-out 不再发 issue 请求。

### A2 — 只增加落实 Owner 当前 B 谢绝决定的结案路径

新分支在锁住问题、检查版本后查询证据。`issueshown.go:67` 先选**本问题、当前 B 上最新的 priority 检查**，再要求其结果为 `declined`、记录者为 `controller`、有 question_id 且通道为 `console`。没有证据、旧 B、rule 通道或后续 priority 已覆盖谢绝时，均不能通过该分支。原有 Owner 本人、她自己的 withdrawn 回答及 agent 自提议的规则保留。

结案沿用现有 `close_issue`：`issueclose.go:177` 作废未答 asks，`:184` 把依据卡号写进 close 事件，`:203` 写入 `closed/declined`。结案前，`issueshown.go:75` 为读者生成 crew 的下一步提示；Console 在 `console/src/pages/IssuePage.tsx:157` 展示它。stdio 的 `close_issue` 参数允许不传 ask（`mcp/platform/src/issueTools.ts:157`），说明也已明确这一用法（`registerIssues.ts:132`）。这符合协调者选定的“crew 落实 Owner 决定”，无需 Owner 再直接调用 admin API。

测试内容确实检查业务结果：store 测试覆盖无证据、rule、旧 B、后续 p2 覆盖、next 提示、closed/declined、asks 作废及 close 事件中的卡号；真实卡测试从人的问题经真实 question store 的 Decline、控制器证据和 crew close，检查结案及提出方的 closed 更新（`api/internal/server/agentrt_issuedecline_test.go:70`、`:100`、`:124`）。没有把“只记下一条 declined 检查”算作完成。

**未发现线程或 agent 经现有接口自行制造这份新依据的路径。** 核对的入口链如下：

- crew HTTP 写入仍由 `writer()` 从认证身份确定 actor；operator 是 `thread:<session>`，intake 在这里被拒（`api/internal/agentrt/agentrtapi/propose.go:28`）。`mountIssues` 没有暴露任意 `RecordOwnerEvidence` 或事件追加接口（`agentrtapi/issues.go:38`）。
- `RecordOwnerEvidence` 只接受 Owner 直接决定或 controller 转录卡片（`store/issueevidence.go:204`）；线程及外部 agent 不满足此入口。新增的 close 依据进一步只接受 controller、Console 的卡片记录。
- 控制器从已登记卡片读取答案，非 Console 或无效选项先作不计数收尾，随后才生成 controller 证据；写证据时再次核对当前 B（`store/issuecarddecide.go:94`、`:99`、`:113`；`store/issueevidence.go:245`）。
- 对外回答路由要求 admin，答案通道固定为 Console；规则使用独立入口，BI 卡仍拒绝规则回答。请求也不能冒用 runtime session 来创建卡片（`api/internal/questions/handler.go:33`、`:105`；`questions/transition.go:105`）。相关卡片创建、规则拒答及真实路由测试本轮通过。

该结论针对受支持的 HTTP、stdio 和运行时规则路径；不把第一轮已接受的直接 DML 防御深度事项重新升级为本轮缺陷。

## B：两项均关闭

### B1 — 读取结果和列表过滤使用同一显示规则

`issueshown.go:25` 使用同问题流里的开卡记录和随后同卡号的收尾记录判断是否仍有卡；`:50` 只在接单前状态且有未结卡时显示 `owner_deciding / owner`。无卡而存储状态仍为 owner_deciding 时，按当前 B/D 的证据推导步骤；未完成 brief 确认且确认 ask 仍开着时，继续等待被问的人，其余等待 crew。active、parked、closed 等状态沿用存储值。

crew 列表、过滤、全文、intake 自有列表/读取及成功写入响应均接入此规则（关闭表列出主要位置）；`afterOwnerCard` 的写入收尾也按同一证据逻辑处理（`store/issuecarddecide.go:234`）。新增测试覆盖最后一张卡过期、规则答案不计数、两卡只收尾一张、确认仍未答及普通 reply 的返回状态，不再只检查 note 数量。

**可见范围没有扩大。** viewer、trade-satellite、匿名等非读者仍在 `RequireIssueReader` 处被挡住（`agentrtapi/issues.go:38`）。已授权 intake 客户端读自己范围内的问题时，`state/waiting_on` 会得到纠正，这是它能看到的预期变化；没有新增卡片内容、证据正文或全文权限。`IssueSeen` 仍先执行 `intakeTx` 和 `intakeSees`，文字筛选未改（`store/issueread.go:243`）；`MyIssues` 的产品、绑定人/自提议条件仍在（`:315`）。派生 SQL 只输出状态枚举，子查询均关联当前问题。

### B2 — 未发放的未来位置在回执之前被拒绝

`IntakeUpdates` 在处理 ack 前先检查输入 cursor，实际读取时再检查一次；首次只允许 `0.0`，之后不允许超过该客户端已有 served。非法位置映射为 HTTP 400 `bad_cursor`。空页且 next 等于 from 时不再登记输入值；推进 served 只能使用实际查询返回的位置或计算得到的 horizon。已有 ack 不超 served、向前推进的约束保留。

新增真库/HTTP 测试检查 max-int cursor、带 ack 的非法输入、served/acked 不变，以及随后合法回音仍能送达。独立 [probes/cursor_guard_test.go](probes/cursor_guard_test.go) 通过 overlay 调用生产 `IntakeUpdates` 和 `handedCursor`，验证首次位置、相等/较旧/同事务较新/较新事务的边界、未来 cursor 在 ack/读取之前被拒，以及只由计算出的 horizon 推进 served，结果见 [artifacts/cursor-guard.txt](artifacts/cursor-guard.txt)。这是合成 DB 的 Go 控制流验证，不是 PostgreSQL 锁、触发器或 SQL 执行证明。

## C：验证记录与限制

本轮没有其他 C 项，也未发现修复扩大访问权限、泄露她的文字、破坏 Owner 决定或改变既有结案谓词的新增 A。

实际完成的离线验证：

- 原第一轮缓存探针复跑及四个安全断言用例，结果如上；提交的 Console 八例已审读，未声称执行过完整 Vitest。
- Go 全包 `go test ./... -run '^$' -count=1` 通过，包含新增测试的编译，**不等于功能测试全通过**，见 [artifacts/go-compile.txt](artifacts/go-compile.txt)。
- 卡片创建身份、只收选项、规则拒答、真实 questions 路由及其他卡片既有回答行为的选定测试通过，见 [artifacts/question-tests.txt](artifacts/question-tests.txt)。
- 全路由角色遍历、公开自省、运行时规则拒答及固定撤回理由的选定测试通过，见 [artifacts/server-tests.txt](artifacts/server-tests.txt)；旧角色 writer 表测试通过，见 [artifacts/writer-tests.txt](artifacts/writer-tests.txt)。这些 HTTP 测试使用内存 recorder，没有监听端口。
- 游标 overlay 探针通过；Console `tsc --noEmit` 和三个修复提交的 `git diff --check` 通过。

**未检查：** 真 PostgreSQL/Redis、数据库触发器和并发锁、A2/B1/B2 的真库集成用例、完整 Console Vitest/构建、真实浏览器及部署/回滚。未启动数据库、监听端口、联网或访问集群；未使用 MCP/SSH，未提交或修改被审实现。探针、日志及临时文件只写本目录，Go/npm 缓存使用指定共享缓存。被审工作树前后 `git status --short` 均为空。

通过：A1、A2 已关闭；无未关闭 A 项。
END OF REPORT
