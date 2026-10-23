> 复核 523（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/bi1-1-data-r2`。报告里的 `probes/`、`tests.jsonl` 等证据在本机 `~/agent-work/codex-review-523/`，不进仓库。

# Review 523 — W-31 BI-1 切片 1，第二轮窄确认

结论：**通过；A 项无。** A1、A2、A3、A7、A8、A6-scope 已关闭，未发现这些修复带来的新 A。B1 的主要反例已补，但尚未兑现逐分支覆盖，保留为 B。**同意**将 A4、A5、A6-limits 降为 B。

审查对象：`/Users/vision-mac-trader/agent-work/bi1-1`，HEAD `ac68cf36f5ac1656ceadf508be1961b8e6835c45`；仅核查相对 `31d0efead4b78e60e065cced7c18b4271ffae2ae` 的两次修复提交及必要调用链。下文 `api/...` 路径相对于该工作树；表格内 `store/`、`migrations/` 分别缩写 `api/internal/agentrt/store/`、`api/internal/agentrt/migrations/`。设计路径缩写为 `DESIGN`：`/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/crew/DESIGN-crew-intake-2026-10-22.md`。

## A：无

没有发现本轮修复破坏设计保证、泄露原话、引入死锁或损害既有数据的新 A。不重开第一轮已接受的范围。

## 关闭表

下表“关闭”依据代码与测试内容核对；真库测试未由本次环境重跑，验证边界见 C。

| 第一轮项 | 判定 | 代码与证明它的测试 |
|---|---|---|
| A1：BI mission 普通卡旁路 | **关闭** | `api/internal/agentrt/store/issuetake.go:46` 移除 Ask 参数，`:93` 固定传 nil；封外 mission 留在 proposed，返回 waiting。`store/missiondecide.go:44` 在生成卡、查询规则和调用 Ask 前拒绝 BI-。`store/issuereview522_test.go:35` 验证 proposed、无 question_id，另一条带 Ask 的内部路径拒绝、Ask 零次且事务不留 mission；`store/issues_test.go:604` 验证等待、占名额及停止后释放。这里只关闭切片 1 的旁路，安全开卡仍按回应留在切片 2。 |
| A2：自提议使用 fault_small | **关闭** | `api/internal/agentrt/store/issuetake.go:194` 增加 ServedPerson 非空条件。`store/issuereview522_test.go:63` 验证 Owner 确认 brief 后的 small/fault 自提议仍缺优先级，Owner 定 p2 后正常接单且不走例外；人的正例保留在 `store/issues_test.go:549`。 |
| A3：决定表不进入 D | **关闭** | `api/internal/agentrt/store/issuedesign.go:162` 解析正文自带的规范头、核对额外参数；`:176` 形成完整规范文档，`:200` 对文档整体哈希，`:208` 整体入 issue_text。`store/issuetake.go:344` 从该文字读取决定点。`store/issuereview522_test.go:89` 覆盖同正文删点、改 Proceed 后 D 改变和旧证据失效、正文规范头与参数不一致拒绝、正文自带表得到同一 D、缺失决定点拒绝。 |
| A7：两轮后直接第三轮 pass | **关闭** | `api/internal/agentrt/store/issuedesign.go:326` 检查上一轮加一，`:333` 要求第三轮起有当前 B/D、上一轮之后的 Owner another_round。`migrations/0009_issues.sql:787` 同时执行轮次与授权检查。接单端 `store/issuetake.go:324` 对第三轮及以后再次核对复核前的有效授权；fix 后 proceed 则须在该复核之后。`store/issuereview522_test.go:143` 覆盖跳轮、重复、无授权第三轮（store 和直接 SQL）、旧 D 授权失效及当前 D 授权后的第三轮接单。两轮 fix 后 Owner proceed 的原测试保留在 `store/issues_test.go:504`。 |
| A8：作废时改写答复来源 | **关闭** | `api/internal/agentrt/migrations/0009_issues.sql:702` 比较去掉 superseded_at 后的整行，答者、通道、said_at 等均不能随作废改变。`store/issuereview522_test.go:182` 覆盖已答问改答者/通道、已答及未答问改 said_at 被拒，以及只作废的正例。 |
| A6-scope：范围、撤销 | **关闭** | `api/internal/agentrt/migrations/0009_issues.sql:426` 的 intake_sees 统一要求未撤销、产品在范围内，以及绑定人或自己的提议；`:492` 用于 issue UPDATE，`:635` 用于文字 INSERT。`store/issuereview522_test.go:204` 先验证合法写，再验证缩产品范围及撤销后的文字和纯 UPDATE 均拒绝；纯 UPDATE 用例独立于文字插入，确实能检查 UPDATE 守卫。 |
| B1：守卫负向测试逐项覆盖 | **未关闭（B，主要缺口已补）** | `api/internal/agentrt/store/issueguards_test.go:27` 使用 runtime 连接、合法事件和直接 SQL，事件本身写不进去会使测试失败；`:159` 补正文 writer/kind/hash，`:242` 补旧 B/D 和错误报告种类，`:305` 对七表逐一验证 legacy_imported 排除。仍有独立守卫分支未见反例，详见 B1。 |

## B：保留给 Owner 的非阻塞项

### B1 — 测试矩阵不能支持“每个守卫分支均覆盖”的声明

这是第一轮 B1 的剩余部分，不是新 A。新增矩阵方向正确，且匹配分支自己的错误文字，能避免把别处的拒绝当成该防线生效；但至少还缺以下两个独立分支：

- `api/internal/agentrt/migrations/0009_issues.sql:681`：已有 brief 时，needs_info 也必须携带当前 B。矩阵 `store/issueguards_test.go:177`、`:181` 的 needs_info 都带非空 B，分别在错人、出生即作废处先拒绝；`:185` 测的是非空旧 B。尚无“正确人、正确事件、有效绑定文字，但 brief_sha256=NULL”的反例。needs_info 的 NULL 本身符合表 CHECK（迁移 `:220`），所以不能用该 CHECK 代替这条守卫测试。
- `api/internal/agentrt/migrations/0009_issues.sql:580`：duplicate_of 只设置一次。矩阵 `store/issueguards_test.go:152` 都是首次设置；原 `store/issueclose_test.go:305` 只验证一次正常合并与禁止重开。尚无对已经合并的问题，用正确 issue_merged 事件保持结论不变、将 duplicate_of 换成另一同人同产品开放问题的反例。

这两处实现中的守卫仍在，未发现对应功能破口；缺的是删除这些分支会被针对性测试抓住的证据。Owner 可选择补这两条并对照剩余分支核完矩阵，成本是测试补充与真库执行；或接受当前覆盖进入 STG，成本是尚不能声明逐分支防线齐备。3279 项通过的总数本身不能消除缺测。

### A4、A5、A6-limits 的重分类裁决：同意

**A4：同意保留为 B。** `DESIGN:338` 明确由 take_issue 在一个事务里计算接单谓词，`:346` 明确产品锁和计数；`:331` 对 active 的数据库要求明确写成按事件类型挡。`DESIGN:307` 对 issue_work 的库约束点名事件、当前 B，`:313` 的 BI 提交检查点名关联行。它没有承诺数据库重新计算全部接单证据与产品名额。当前 `api/internal/agentrt/migrations/0009_issues.sql:742` 的边界与这些点名约束一致。正确类型事件加完整关联的恶意 runtime DML 仍不受完整谓词保护，不能称为已修复，但不应据此将设计扩写成新的 A。

**A5：同意保留为 B。** `DESIGN:361` 将结案表标为 close_issue 的“程序检查”；`:300` 的库级基础规则则是事务内事件、允许类型及命名。当前 `api/internal/agentrt/migrations/0009_issues.sql:569` 只守结论变化的事件与不可改写规则，不检查全部业务结案依据。它仍允许第一轮指出的正确类型 DML 旁路，但设计没有把整张结案谓词表承诺为 SQL 防线。

**A6-limits：同意保留为 B。** `DESIGN:624`、`:625` 要求日限，`:420` 要求 Agent 身份在读写和重放前检查；没有要求日限由触发器计数。`api/internal/agentrt/store/intake.go:291` 明确由 store 在 writer 锁下按最近 24 小时事件计算；`store/intake_test.go:137` 覆盖提交及自提议限额、重放仍返回原响应。直接 DML 越限属于额外数据库防御；范围和撤销则按回应明确接受的 scope 部分修复，见关闭表。

这一判断也与 `DESIGN:442`、`:444` 的旧二进制列表和 §十二第 12 行（`:812`）一致：数据库必须保障旧路径仍结束关联、独立 BI mission 被拒，intake 令牌旧版读不到；这不是“持 runtime 身份的新写者可以任意伪造新事件仍无法越过全部谓词”的承诺。§十二第 7 行（`:807`）所说提交时再查，结合 §4.2 的具体实现要求，是 BI mission 必须有关联行的检查，不是数据库证明 Go 函数确实执行过。

Owner 的现有方案因此可以保留：完整业务谓词和日限由受信任运行时计算，数据库强制已列约束。若选择把上述三个 B 都下沉到数据库，需要统一可强制的写入入口、接单产品锁和计数、结案证据检查及日限串行化，并维护与 Go 的一致性和直接 DML 测试；收益是 runtime 写入错误时也有更强兜底，代价是新增实现和维护范围。保留现状的代价是受信任运行时可用正确事件类型绕过这些应用谓词。这是 Owner 的防御深度选择，不新增 A。

## C：本次验证及限制

- **独立执行通过**：离线 `go build -mod=readonly ./...`、`go vet -mod=readonly ./...`、`go test -mod=readonly ./... -run '^$' -count=1`。最后一条只编译测试并启动空测试集，不代表真库测试通过。`git diff --check 31d0efea..ac68cf36` 通过。
- **独立离线探针通过**：本目录 `review523_probe_test.go`，由 `probe-overlay.json` 叠加到 store 包；四项测试及六个授权子例均通过。调用实际 askMission 验证拒绝发生在任何 I/O 前；验证规范文档哈希和参数冲突；调用实际 takePredicate 验证自提议拒例、人的故障正例；调用实际 issueEvidence 验证无授权、旧 D、rule 通道、授权早于第二轮或晚于第三轮均不能让第三轮 pass 生效，当前 D 的适时 Owner 授权可以。查询结果是合成数据，**不证明 SQL 执行或锁行为**。
- **未重跑**：PostgreSQL/Redis 集成套件、迁移安装与 ACL、触发器实际执行、真库并发和旧/新二进制交叉探针。遵照简报，没有再次尝试启动 PostgreSQL 或绑定 Redis，也没有网络、集群、SSH 或 MCP 操作。实施者的 `AGENTRT_TEST_REQUIRED=1`、3279 pass、无数据库测试跳过是交付方提供的结果，不冒充本次独立执行。
- 审查前后被审工作树均无改动；未提交、未改实现。迁移修复只在尚未应用的 0009 内，本次差异未触及 0001–0008。所查新增读取没有增加 FOR UPDATE 或流锁，未静态发现新的锁序环；没有现场数据，不能据此宣称部署迁移已验证。

通过（A 项：无）
END OF REPORT
