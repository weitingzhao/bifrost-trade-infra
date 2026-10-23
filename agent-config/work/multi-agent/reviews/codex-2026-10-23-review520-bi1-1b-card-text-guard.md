> 复核 520（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/bi1-1b-card-text-guard`。报告里的 `.review/` 证据在本机 `~/agent-work/codex-review-520/.review/`，不进仓库。

本轮结论：先修。发现 **1 项 A、1 项 B**；两个直接回答入口的 BI 防护有效，未发现非 BI 回答行为变化，但撤回理由仍能把文字写进 BI 卡并向 viewer 返回。

审查对象：`bifrost-platform`，`36481b9002a93d25f978b4eaad1253c58c6b4e6f..b7f7d520c0825d9417d35384dd37c332a3d91129`。已核对五个变更文件、相关调用者和设计 §5.3、切片 1b、Owner 的 Y=A 决定。以下路径均相对被审查仓库，行号取目标提交。审查未修改该工作树，未联网、连接数据库或集群、调用 MCP、SSH 或提交代码。

1. **A1 — 撤回仍可携带任意文字关闭 BI 卡，文字经通用读接口公开。** `api/internal/questions/transition.go:165`、`api/internal/questions/transition.go:166`；遗漏的防护范围见 `api/internal/questions/issuecard.go:13`。

   新检查只覆盖 `Answer` 和 `AnswerAsRule`。`Withdraw` 校验卡片为 open、session 等于 requester 后，直接把请求的 `reason` 存入 `Withdrawal.Reason`，没有 BI 检查。它确实不写 `Answer`，但属于 BRIEF 要求检查的“带内容关闭卡片”路径。`public()` 保留整个 withdrawal（`api/internal/questions/types.go:133`、`:157`），viewer 可读详情和 `status=all/withdrawn` 列表（`api/internal/questions/handler.go:21`）。

   已离线复现：按本提交测试相同的方法准备 `work_id=BI-7` 的 open 卡，调用 `Service.Withdraw(ctx, "agentrt", "agentrt", "operator", id, {"reason": 特征文字})`，得到 **200**；原始存储含特征文字，viewer 的详情、all 列表、withdrawn 列表均返回该文字。另一个 requester 为 `thread-a` 的 BI 夹具，经 reporter HTTP 撤回路由也得到相同结果。证据：`.review/new-probes.log` 中 `TestReview520Withdrawal`。

   运行时真实接线仍调用这个未防护入口：`api/internal/server/questions_wire.go:361`、`:370`；MCP 的 `withdraw_question` 也直接发送 `reason`（`mcp/platform/src/questionTools.ts:142`）。HTTP 对保留 session `agentrt` 的拒绝仍有效（`api/internal/questions/handler.go:105`），当前控制器撤回理由也由中性模板生成（`api/internal/agentrt/store/blockedclose.go:399`、`api/internal/agentrt/store/planresult.go:213`）。因此本复现并不证明普通 HTTP 客户端能撤回运行时自己的卡；它证明卡片库的 BI 禁文字边界在已有、可调用的关卡写入入口缺失，安全性仍依赖调用者选择理由。

   建议在 BI 的撤回路径写入前拒绝自由文本理由，或采用不接收调用者文字的固定中性撤回记录；保持非 BI 撤回行为不变。回归测试应覆盖运行时 requester、HTTP requester 和 viewer 读取，核对拒绝后的存储及审计字节。只隐藏读取字段不能满足“写入前拒绝”。

2. **B1 — 新测试没有证明审计不变，非 BI 矩阵也未完整断言原行为。** `api/internal/questions/issuecard_test.go:46`、`:55`、`:155`、`:195`、`:201`。

   `openUntouched` 比较了原始存储字节，但审计只检查不含 `question.answer`，没有保存并比较操作前后的审计；其他 action 的新增、删除、改写均可漏过。回答成功后的重放和拒绝分支也未比较审计。`TestOtherCardsAnswerAsBefore` 覆盖 40 个组合，但成功主要断言 status 和 `Answer.Text`，未核对选项、通道、答者、完整响应、原始存储及审计；拒绝也未比较完整错误或存储字节。server 层无数据库测试使用 nil audit（`api/internal/server/agentrt_issuecard_test.go:57`），不能补足这一点。

   已做隔离变异验证：仅用 Go overlay，让每次拒绝回答额外记录一条 `question.refused` 审计，不修改被审查文件。本次新增的六个 questions 测试仍全部通过（`.review/audit-mutant.log`）。建议直接比较审计前后字节，并为非 BI 固定完整结果，补入空白、重放和终态组合。

写入路径逐项核对如下。“无需”表示该路径不产生回答或自由文本关卡内容，不表示它经过了新增 guard。

| 路径 | 写入什么 | 覆盖情况 | 证据与判断 |
|---|---|---|---|
| Console／其他客户端 → Owner answer HTTP → `Service.Answer` | `status=answered`、`Answer.Option/Text/By/At/Channel` | 是 | `console/src/api/questions.ts:469`；`api/internal/questions/handler.go:91`；`transition.go:27`、`:45`、`:112`。解析成功后才赋值，BI 文字和 none 被拒。 |
| 进程内直接调用 `Service.Answer` | 同上 | 是 | `transition.go:13`、`:27`；没有另一条绕过 `parseAnswer` 的 Owner 回答写入。 |
| workers／controller → `store.AnswerByRule` → runtime bridge → `AnswerAsRule` | 规则答案；非推荐选项时把 why 存入 `Answer.Text` | 是 | `api/internal/agentrt/controller/controller.go:398`；`api/internal/agentrt/store/cardauto.go:178`；`api/internal/server/questions_wire.go:312`；`api/internal/questions/rule.go:77`。BI 在赋值前整条返回 409，包括无 why 的推荐选项。 |
| 规则成功后的 `ruleNote`，及历史规则答案的 `finishRuleAnswer`／`ensureRuleNoteOn` | PostgreSQL `agentrt.event` 的 note；必要时 ack | 新答案受前一行阻断；恢复路径无需 | `api/internal/agentrt/store/cardauto.go:182`、`:191`、`:247`、`:258`。新回答被拒时在 note 前返回；恢复路径不生成新的卡片答案或 Text。它也不能修复已经污染的历史答案。 |
| HTTP withdraw → `Service.Withdraw` | `status=withdrawn`、自由文本 `withdrawal.reason` | **否，A1** | `api/internal/questions/handler.go:67`；`transition.go:148`、`:165`。会保存、公开带内容的关卡记录。 |
| 运行时撤回：失效 blocked card／未采用的计划 → `agentRuntimeWithdraw` | 同上 | **否，同 A1** | `api/internal/agentrt/store/blockedclose.go:410`；`planresult.go:213`；`api/internal/server/questions_wire.go:366`、`:370`。已有固定模板调用者，卡片库本身不限制 BI 理由。 |
| MCP `withdraw_question` | 向 HTTP 转发 reason | **否，同 A1** | `mcp/platform/src/questionTools.ts:142`；`writeGate.ts:55`。本地拒绝 answer 不会拒绝 withdraw；服务端仍核对 requester。 |
| `Create`／`CreateForRule`；MCP ask；运行时 ask | 新卡标题、正文、选项等；不初始化 Answer 或 Withdrawal | 无需，本切片仍禁止开 BI 卡 | `api/internal/questions/create.go:25`、`:36`、`:78`；`canonical.go:41`、`:214`；`api/internal/server/questions_wire.go:178`。严格创建请求不接收 answer 字段，workIDPattern 未扩到 BI。后续 BI 开卡内容模板仍须单独验收。 |
| HTTP／运行时 `Ack` | 已有答案的 `ReadReceipt` | 无需 | `api/internal/questions/transition.go:201`、`:224`；`api/internal/server/questions_wire.go:387`。不接收或赋值答案文字。 |
| workers sweep；读接口触发 expiry sweep | open → expired | 无需 | `api/internal/questions/service.go:80`、`:122`、`:186`、`:211`。不生成回答或关卡文字。 |
| 创建后的通知回写 | `Deliveries` 的发送结果、错误等 | 无需 | `api/internal/questions/notify.go:19`、`:30`、`:91`。不接受回答、不改 Answer；通知不携带回答文字。 |
| question store／本地 statefile／Kubernetes state backend | 序列化整份 question document | 物理入口统一，不能代替字段约束 | `api/internal/questions/store.go:58`、`:97`；`service.go:181`；`notify.go:19`；`api/internal/statefile/statefile.go:123`；`k8sstate/k8sstate.go:123`。正常生产写入最终经 store.update；调用 mutate 的逻辑入口有 apply 和通知回写。store.update 不校验 BI 的回答／撤回字段。 |
| MCP answer 能力／通用写门 | 不提供回答工具；answer POST 本地拒绝 | 是，无额外答案写入 | `mcp/platform/src/questionTools.ts:70`、`:136`；`writeGate.ts:93`。拒绝发生在 legacy/off/on 模式分支之前。 |
| 计划导入、recorder 导入、迁移、seed、CLI | 创建普通决策卡，或写 PostgreSQL 的计划／事件／note；不导入 question Answer | 无需 | `api/internal/agentrt/store/planimportcard.go:112`；`recorderimport.go:155`；`planimport.go:229`；`api/cmd/agentrt-plan-import/main.go:1`；`api/cmd/platform-api/agentrt_migrate.go:53`。已查迁移 0001–0008、相关脚本和写入引用，未发现独立回答导入器或绕过 store 的生产 question 写入。测试中的改 work_id／原始文件夹具不属于生产入口。 |

正确性核对：`parseAnswer` 的新增检查位于类型、长度、通道及选项合法性检查之后，原 allow_text 分支之前。合法选项独立回答仍可写入；BI 的 none 无论是否带文字都被拒。非 BI 不进入新分支，其旧逻辑保持原样。`businessIssue` 在 trim 后按大小写不敏感的 `BI-` 前缀匹配，确实覆盖 `BI-0`、`BI-01`、`bi-x` 等比未来编号规则更宽的形式；原创建接口只收 W、TD、LANE，这不会改变历史合法非 BI 卡，`LANE-BI-1` 仍不匹配。

纯空白或被清洗掉的控制／零宽字符配合法选项会被接受，存储的 Answer.Text 为 `""`；none 配这些字符仍被拒。这不会留下可读文字。已有安全答案的相同选项重放为 200/replayed，存储和审计均不变；在已答 BI 卡上再提交文字，在重放／already-answered 判断前被拒。已过期卡仍按原顺序返回 expired。规则入口的 BI 整体 409 不阻止同一次规则循环继续处理其他卡。

“拒绝后整个存储和审计不变”有原有的 expiry 例外：`Service.apply` 在调用业务校验前 sweep 所有卡（`service.go:186`）。若另有卡到期，拒绝回答仍可同时保存过期状态并记录 `question.expire`。本轮额外探针确认：没有待过期卡时，BI 两个回答入口的拒绝均保持存储、审计字节不变；存在无关到期卡时发生上述 sweep。它不写入被拒文字，也不是本提交引入的非 BI 行为变化。

回滚底线与交叉探针：存储格式仍可被旧写者读取，没有通过 schema 或解析校验阻止交叉验证。用相同 BI 夹具、`allow_text=false`、`option=none` 加特征文字做进程内 HTTP 探针：覆回基线 `transition.go`／`rule.go` 的旧写者得到 **200，viewer 可读文字**；目标版本得到 **400，存储与审计字节不变，viewer 读不到该文字**。证据分别在 `.review/old-probes.log`、`.review/new-probes.log` 的 `TestReview520CrossProbe`。此验证使用只读源码的 Go overlay，不是真正的新旧发布二进制或多 Pod 验收。

所以“兼容版本起拒绝”对两个回答入口成立；真正运行兼容版本之前的写者仍会接受文字，最低版本限制必须靠发布与回退流程维持。当前提交只在 `issuecard.go:22` 注释声明底线，没有部署检查；所读 infra `docs/RELEASE.md` 和目标树的 `config/ops-context.yaml` 尚未记录这个 BI 底线。启用 BI 开卡前仍须补齐发布记录、核对 STG／PROD 每个 API 和 workers 写者均达到修复后的版本，并覆盖 Argo、手工镜像回退。新版本也不清除旧写者已经存入的文字，`Get/List/public` 仍会返回它；不得将本补丁解释为污染存储的清理措施。

验证结果：

- 按指定缓存运行 `go test ./internal/questions/... -count=1`，在已有 `TestHiddenFieldsAreWithheldAtTheRelay` 处因 `httptest.NewServer` 监听本机端口被沙箱拒绝而中断。随后仅跳过该测试运行同包其余测试，**通过**；本次新增的六个 questions 测试均包含在内。日志：`.review/questions-test.log`。
- 用只写在本报告目录的 overlay 做 520 组新旧非 BI 对照：4 种 work_id × 2 种 allow_text × 5 种状态／写入路径 × 13 种输入。比较状态码、完整响应、原始存储字节及审计内容，**全部一致**；审计仅剔除每次自然生成的 ID／时间。快照：`.review/old-matrix.json`、`.review/new-matrix.json`。
- 额外验证了 A1、空白清洗及安全重放、两个回答入口拒绝后的原始审计不变、expiry 例外、新旧回答交叉行为。审计变异实验确认 B1 可漏检。所有覆盖层和日志均在本目录 `.review/`，原工作树始终干净。
- `git diff --check` **通过**。未运行 server 包及其数据库集成测试（包括新增的 `TestRuleAnswerLeavesAnIssueCardOpen`、`TestCardRuleLoopLeavesAnIssueCardOpen`），未运行全仓 build/lint、MCP 测试或部署／多 Pod／真实回退验证；遵守 BRIEF 仅运行 questions Go 包和不访问网络、数据库、集群的限制。server 新测试已静态审读，真实规则 note／事务效果仍待其集成测试验收。

先修：A1（BI 卡撤回理由可存入并公开文字）。
END OF REPORT
