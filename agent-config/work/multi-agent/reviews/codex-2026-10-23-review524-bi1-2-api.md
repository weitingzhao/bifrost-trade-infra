> 复核 524（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/bi1-2-api`。报告里的 `probes/`、`artifacts/` 证据在本机 `~/agent-work/codex-review-524/`，不进仓库。

# Review 524 — W-31 BI-1 切片 2，第一轮

结论：**先修 A1、A2。** 发现 2 项 A、2 项 B，无 C。鉴权矩阵及后端文字隔离的主要接线成立；Console 的登录切换会泄露已经加载的私密正文，Owner 的「谢绝」卡也尚未完成设计承诺的动作。

审查对象为 `/Users/vision-mac-trader/agent-work/bi1-2`，HEAD `dd29f64ecc1bf8e0d5386c460598014f6495d7a5`，比较基线 `bb2efaeb5d6622f574399763f26214ee1c265305`。下文源码路径均相对该工作树；DESIGN 指简报指定的 `DESIGN-crew-intake-2026-10-22.md`。已核对最终决定、切片 1b/1 的落地说明及相关复核，不重开 Owner 保留为 B 的直接 DML 防御深度事项。

## A：STG 前必须修

### A1 — 换成非读者或退出登录后，问题页仍显示前一身份的私密正文

**位置：** `console/src/pages/IssuePage.tsx:219`、`:245`；相关接线 `console/src/hooks/PlatformAuthProvider.tsx:40`、`:85`。**设计：** §5.3「问题路由的读者」「只读问题页」、I-D7 A、§十二第 1 项。

问题查询的 key 只有 `['agentrt', 'issue', id]`，组件也只按问题号重新挂载，没有使用当前登录身份。`setToken` / `signOut` 清除 capabilities，并失效几组既有查询，但没有处理这组新查询。因此，admin 成功打开问题后，在同一 Console 切到 viewer、trade-satellite 或匿名，页面继续从原查询取出全部正文；服务端的 readers 检查没有机会执行。页面保持挂载时，这不只是一帧旧内容，而是持续显示，直到另外的行为触发重读或页面被卸载。

**独立离线复现已通过：** [probes/cache.node.test.tsx](probes/cache.node.test.tsx) 加载实际 `PlatformAuthProvider`、`IssuePage` 及 React Query，模拟只有 admin 能读问题的服务端。依次打开问题、切成 viewer、退出登录后，两次均仍能在 DOM 找到私密标记；问题 API 总调用次数仍为 **1**。结果见 [artifacts/cache-probe.txt](artifacts/cache-probe.txt)。这是当前实现的泄露复现，探针通过不代表安全要求通过。

**修法与验收：** 将问题查询和显示绑定登录身份；身份变化时立即撤下旧正文，取消旧请求并清除该身份的私密缓存，避免晚到响应重新填回。查询应接收并使用取消信号。补实际 Provider 下的 admin→viewer、admin→trade-satellite、sign-out，以及旧请求延迟完成的测试，断言新身份下 DOM 与查询结果均没有旧正文。仅增加一次 invalidate 仍可能在重读期间显示旧数据。

### A2 — Owner 点「谢绝」只记证据，人的问题没有被谢绝，也无法由 crew 接着结案

**位置：** `api/internal/agentrt/store/issuecarddecide.go:110`、`:113`；`api/internal/agentrt/store/issueevidence.go:294`、`:298`；后续拒绝点 `api/internal/agentrt/store/issueclose.go:152`。**设计：** §一 Owner 能「谢绝」、§2.2「只有 Owner」、§4.3 结案谓词、§八切片 2 的最小入口、§十一 X=A。

优先级第一步的 `c` 选项是「Decline」，但控制器只调用 `RecordOwnerEvidence(Priority="declined")`。后者写一条 priority check，保留旧 priority，并将显示状态恢复到相应工作步骤；它没有写 `conclusion=declined`、没有结束问题，也没有产生给提出方的 closed 更新。例如，一个已确认、已分级的人的请求会继续显示 `classified / waiting_on=crew`。

这不能靠 crew 后续的正常工具补完：`close_issue(conclusion=declined)` 对人的问题只接受 `w.Actor == "owner"` 或她自己的 withdrawn 回答，**不接受当前 B 上这张 Owner 卡的 declined 证据**。stdio crew 使用 operator→thread，故仍被拒；Console 在本切片又只有只读问题页。Owner 必须另行直接调用 admin API，才能完成他刚刚已经在卡上做过的决定，违反「切片 2 起在现有卡片页完成谢绝」的最小入口。

此处没有声称 declined 会被当作允许开工：现有接单谓词确实拒绝这条优先级。缺口是谢绝动作、最终结论和提出方回音没有落地。

**测试没有证明这个动作完成：** `api/internal/agentrt/store/issuecard_test.go:231` 的 later/decline 分支只断言 `issue_check.result` 和卡片数量，未检查 `state/conclusion`，也未让 operator 执行后续 close 或检查 get_updates。

**修法与验收：** 让运行时在验证 Owner 卡及当前 B 后完成谢绝的结案路径，并保留卡号与答者作为依据；或使 crew 的结案路径严格引用这份当前版本的 Owner 谢绝证据。不得放宽为线程自行谢绝。真库测试应从人的问题出发，经真实卡片回答，验证最终 `closed/declined`、开问作废及提出方收到 closed 更新，并覆盖旧 B 和 rule 通道拒例。

## B：应修

### B1 — 卡片过期等无证据收尾后，问题仍谎报「等 Owner」

**位置：** `api/internal/agentrt/store/issuecarddecide.go:82`、`:192`；`api/internal/agentrt/store/issueread.go:79`。**设计：** §4.3 显示状态表、§八 waiting_on。

卡过期、撤回、无效回答等路径调用 `settleIssueCard`，只追加 settled note，不调整 issue 的 `owner_deciding / waiting_on=owner`。后续遍历已把卡认作 settled，不再修正；列表和页面又直接读 issue 行。因此，唯一一张优先级卡过期后，会出现「没有待答卡，却一直在等 Owner」。普通 addition 或 plain reply 也不会自动重算状态，所以实施者 choice 8 所称「直到 crew 下一次写」并非普遍成立。

这不改变证据授权，列 B。可在读取时依据当前未结卡推导显示状态，或实现受约束的状态收尾；不要因为控制器不能写某一现有事件类型，就把错误显示留作既定行为。补最后一张卡过期、无效回答及多卡仅关闭一张的断言。现有 `TestCardAnswersThatDoNotCount` 只查 note/证据数量，抓不到此回归。

### B2 — 任意未来 cursor 可被登记为 served，再被回执，破坏回音续读

**位置：** `api/internal/agentrt/store/intakeupdates.go:53`、`:135`；`api/internal/agentrt/store/eventcursor.go:138`；回执检查 `api/internal/agentrt/store/intake.go:266`。**设计：** §2.1 cursor/回执约束、§4.3 不跳过回音、§3.3 丢游标后的恢复。

请求里的 cursor 只验证为两个非负 int64，未验证它是本客户端已经取得的续读位置。当输入 `9223372036854775807.0` 时，查询返回空页，`EventsAfter` 的 default 分支原样返回该 cursor，随后 `MarkServed` 将它登记为最大 served。下一次 ack 同值便不会超出 served。此后不带 cursor 的读取从这个未来回执点开始，正常回音将一直被跳过，服务端回执也不再表示真实送达的范围。

**离线探针：** [probes/cursor_probe_test.go](probes/cursor_probe_test.go) 通过 overlay 调用实际 `ParseEventCursor`、`EventsAfter`、`MarkServed`，给出 horizon=100 的合成查询结果，确认空页仍返回并登记调用方的未来值。见 [artifacts/cursor-probe.txt](artifacts/cursor-probe.txt)。这证明 Go 控制流；未执行 SQL，数据库部分依据现有 served/acked 约束静态核对。影响仅限该客户端自己的送达/回执，未扩大读取权限，列 B。

应拒绝超出客户端已发放位置的输入 cursor，或采用可验证的续读令牌；不要把未验证的输入原样认证成服务端水位。增加 HTTP/真库反例，并验证非法 cursor 不改变 served/acked、后续合法回音仍能读取。现有乱序测试使用服务器返回的合法 cursor，不覆盖这一输入。

## 已核实的边界、兼容性和测试效力

- **角色和旧行为：** `writer()` 对旧角色的唯一相关变化是前置拒绝 intake；`actorOf()` 未改。实际 `TestWritersOfEachRole` 通过。未知角色低于 viewer、`tokens:` 闭集及独立 `intake_tokens:` 均符合 §5.2，故改变 `TestAnUnknownRoleIsTreatedAsViewer` 的期望有设计依据。读者名单同时检查 token 名和 operator/admin 角色；所有 18 条 crew 路由统一经过该中间件，7 条 intake 路由只接受 intake。
- **全路由测试不是拿 400/503 冒充鉴权拒绝：** 它确实用每条路由的 middleware 包裹哨兵，配置 noDB 以越过 configured 检查。我将同一份遍历测试放到本目录提取的 **真实 bb2efaeb 源码**上独立执行；得到 1,164 行旧角色矩阵，与提交的 `testdata/route_reach_base.txt` **逐字一致**，证据为 [artifacts/baseline-reach.txt](artifacts/baseline-reach.txt)。候选的矩阵和公开 capabilities 测试亦通过，仅 operator/admin 增加各 18 条 crew 路由。当前公开自省扫描对现有调用点有效，但不是任意未来认证写法的形式化证明。
- **后端文字边界：** 新全文读取只查询 issue 专用表；intake 的 IssueSeen/MyIssues/update filter 按产品及绑定人/自提议限定，身份、撤销和重放检查复用 holdsSessionTx/agentSees。get_updates 的文字查找要求同问题及 `to_requester`。通用单流、latest、after 三种 `/events` 都有 issue:/intake: 隐藏条件；产物检索没有新增通向 issue_text 的关联。静态未发现新的正文外流到错误、日志、通用产物或 MCP 非读者响应；前端 A1 是这一结论的明确例外。
- **卡片边界：** HTTP 请求不能使用 runtime 保留 session；BI work_id 又仅由 runtime session 开卡。模板输入为编号、用途、决定点、字母数量及哈希，未接受调用方正文；BI mission 也用相同中性模板。assessment 与 rule 的列表均跳过 BI 卡，卡片库自身仍拒绝文字、none 和规则回答，撤回理由仍为固定句。改变 slice-1b 规则循环测试的期望有依据：从「尝试后被拒」改为「不列给规则」，底层拒绝仍保留测试。未发现本切片削弱最低回退版本的文字防线。
- **Owner 答案：** 真实 questions answer 路由和 Service 都要求 admin，通道只能 console，控制器只接受选项键；证据/确认路径再检查当前 B/D 或当前 ask。优先级的 Take 分支确实先开 p1/p2/p3 第二张卡，第一步不写 p1/p2/p3 证据。两步都有 B；A2 是 Decline 分支的业务效果缺口。
- **游标顺序：** 页与 xmin 水位在同一条查询，按 `(txid,event_id)` 排序，过滤位于 LIMIT 前，短页推到水位。现有 `TestIntakeUpdatesKeepLateCommits` 确实构造两个不同流、先分配小 event_id 后提交的事务，检查旧事务未结束时均不返回、结束后按顺序读到两条；它是有效的乱序控制流测试。其合成回复用 `text_id=0`，故该测试本身不证明真实文字 join，投影须与另一组 to_requester 测试合看；二者仍都不覆盖 B2。
- **旧版本：** 新切片未改迁移字节。859fbfd9/ca645deb 的 AuthFile 仅读 tokens，独立 intake_tokens 不会加载为旧阶梯上的 viewer；新卡没有私密正文，1b floor 的 answer/rule/withdraw 防线仍适用。旧版可能评估中性卡、看见 issue 元数据及缺少新路由，是设计已接受的降级。新增事件字段是可选 JSON 字段，未静态发现旧消费路径因此破坏完整性。**本次没有执行真旧/新二进制与数据库的交叉探针，不能据此宣称 rollout/rollback 已实测。**
- **写路由豁免：** 新增豁免枚举与实际写路由匹配，仍保留 readers/intake 鉴权及 store 谓词；仅记录运行时状态，take 使用既有 mission 授权路径，未新增集群执行旁路，符合本切片范围。

## 实施者的 choices / design notes

仅列需要纠正的一项组合：**choice 8 + design note 1** 将 B1 的错误状态当成可接受限制。没有专用 card-open/closed 事件不意味着可以持续显示不存在的 Owner 等待；读时推导可使用已经记录的中性 card note。该限制并非 Owner 的决定，不能据此标记状态显示完整交付。其余 choices / notes 未发现足以另立问题的设计冲突。

## §十第 2 行完成表

表中 done 表示代码接线完成且已按上述边界审读，不表示本环境重跑过真库验收。

| 第 2 行项目 | 状态 | 核对结果 |
|---|---|---|
| `/agentrt/issues*` 与问题读者名单 | done | 18 条路由统一检查角色和 token 名 |
| intake 角色、阶梯失败即关 | done | 位于 viewer 以下；未知角色同样失败即关 |
| tokens 闭集、intake_tokens 新键 | done | 新加载校验和旧配置形状测试；旧二进制不识别新键 |
| writer 保持旧行为、intakeWriter | done | 旧映射静态一致，角色表测试通过 |
| agent 身份、范围、撤销及重放检查 | done | 写、读、幂等重放均接入现有检查 |
| hiddenFrom 前缀效果 | done | stream/latest/after 均隐藏 issue:/intake: |
| get_updates 与 receipts | partly | 合法游标顺序及投影接线完整；B2 可污染续读/回执 |
| 全路由闸门效果、公开自省、旧角色矩阵 | done | 候选测试通过；独立重建基线逐字相同 |
| 本机 stdio crew 工具 | done | 工具注册、参数及路由接线；5 个新增工具测试通过 |
| request_owner 中性模板、BI 卡身份及选项限定 | done | 四用途及 BI mission 走模板，保留 1b 防线 |
| 优先级两步 X=A | done | Take 后开第二卡；仅第二步写 p1/p2/p3 |
| 跳过 AI assessment 和 rule | done | 两处列表均过滤，底层拒绝仍在 |
| 读 Owner 答案、记录证据及完成其动作 | partly | 当前版本证据路径存在；A2 谢绝未结案，B1 收尾显示不完整 |
| Console 一页只读问题页 | partly | 全文、哈希、决定表、三类声音和卡链接存在；A1 登录切换泄露 |

**§十三额外承接项：BI-1 旧记录导入 missing。** 本切片没有 legacy_imported 导入入口/脚本，也没有保留 BI-1 编号的交付证明。实施报告已披露，应作为未完成事项安排受控导入和编号验收，不能将之计作 slice 2 已全数完成。`intake/clients` 属切片 4、I-D8 流水线收紧属 infra，本次不因此另开缺陷。

## 本次独立验证及限制

- 离线 `go test ./... -run '^$' -count=1` 通过：全包测试编译及空测试集，见 [artifacts/go-compile.txt](artifacts/go-compile.txt)，**不是全量功能测试通过**。
- 实际执行通过：actuation 包全测；questions 中 BI 卡/文字防线相关测试；agentrtapi 的旧角色 writer 表测试；server 的全路由、自省、规则拒答及固定撤回理由测试；真实基线权限遍历；MCP 新增 5 项测试；Console 和 MCP 的 `tsc --noEmit`；`git diff --check`。
- A1 的 React/JSDOM 实际组件复现和 B2 的 Go overlay 控制流探针均已执行；二者使用合成文本及数据。Node 探针通过本目录的 TypeScript loader 加载源码，未改实现。未将这些结果冒充完整 Console Vitest 或浏览器视觉验收。
- **未执行：** PostgreSQL/Redis 套件、迁移与触发器真实执行、真库锁与并发、真实 questions+数据库集成测试、旧二进制交叉测试、完整 Console 构建/测试及部署验收。没有尝试启动数据库或监听端口，没有网络、集群、MCP 或 SSH 操作。实施者及 CI 的数据库通过声明只作为交付方声明；测试内容的证明范围已单独审读。
- 被审工作树前后 `git status --short` 均为空；未提交、未改实现。报告、源码覆盖层、基线提取及临时文件只在本目录，缓存仅用简报指定共享缓存。

先修：A1（登录切换泄露私密正文）、A2（Owner 谢绝卡未完成谢绝结案）。
END OF REPORT
