| 二轮项 | 判定 | 修订设计与指定代码的核对 |
|---|---|---|
| R2-A1：通用写者映射损害 viewer 既有能力 | **closed** | §5.2，`DESIGN.md:475–479`：保留旧角色的 `writer()` 映射和 agentd 的 `actorOf()` 分支，intake 独立走 `intakeWriter()`；阶梯失败即关。与 platform `api/internal/agentrt/agentrtapi/propose.go:28–41`、`controls.go:18–24,105–111`、`rules.go:81–91`、`api.go:96–100,157,163` 相容。`controls_test.go:39,74–77` 的 viewer 身份和暂停契约被明确保留，`rules_test.go:51–53` 的 viewer 收紧入口也不再被写者映射挡住。 |
| R2-A2：决策卡及自动评估泄露私有文字 | **not closed** | §5.3，`DESIGN.md:502–512` 的固定模板、受限只读问题页、禁止文字答复和跳过评估，覆盖了新版本的两条原泄露路径：platform `api/internal/questions/types.go:133–139` 的通用投影及 `api/internal/server/questions_wire.go:268–301` → `api/internal/agentrt/store/assess.go:508,537–555` 的复制。但五选项模板不符合实际卡片输入契约（R3-A1）；§4.6 又允许旧卡片写者继续接受文字，私有答复仍会公开（R3-A2）。不能确认整个入口已闭合。 |
| R2-A3：显示状态错误释放产品名额 | **closed** | §4.3/4.4，`DESIGN.md:345–358,392–398`：产品锁内按存在 `ended_at IS NULL` 关联的不同问题计数；非终态全部占位；首批禁止在途时暂缓、换需求或合并。与 platform `api/internal/agentrt/store/kernel.go:85–90,101–124` 的状态机、`propose.go:393–405` 的 proposed/awaiting_owner/active 分支及 `close.go:86–93` 的终态路径相符。§4.2 的终态触发器负责结束关联，显示状态不能释放名额。 |
| R2-A4：否定核对或旧范围的试用回答仍能结案 | **closed** | §4.2/4.3，`DESIGN.md:237–294,306,364–371`：工作和问都绑定 B；试用问的复合外键包含 B；结案检查当前 B、最新未作废试用问及该问最新一条 `close_check.result = supports`。换 B 后旧问不能结案，旧 B 的工作不能发新 B 的试用问；在途或开放试用期间禁止原地换范围。此前两个反例均被这些明确谓词拒绝。对照 platform `api/internal/agentrt/store/accept.go:23–32,87–104`，现有工程验收不会代替这些业务判定；修订已单独补齐，未依赖通用外键自动完成。 |
| R2-A5：无事件的 served 更新被守卫拒绝 | **closed** | §4.2/4.6，`DESIGN.md:190–196,299–302,314–315,422`：0009 明确同签名替换 `only_liveness`，保留 attempt/host 分支，仅允许完整、严格前进且无其他字段变化的 served 更新；acked、配置和撤销仍须事件。对应 platform `api/internal/agentrt/migrations/0002_guards.sql:115–132,193–217` 的实际调用顺序；配对非空 CHECK 补齐 NULL 边界，显式授权也覆盖 `0003_grants.sql:13–35` 只授权已有对象的限制。 |
| R2-A6：旧二进制与真实发布链不相容 | **not closed** | §4.2/4.6/5.2，`DESIGN.md:307–315,434–455,475` 已修对终态关联和鉴权：数据库触发器复用旧 `kernel.go:119–123` → `event.go:130` 的事件与 UPDATE；`intake_tokens:` 不被旧 `api/internal/actuation/auth.go:66–68,98–102` 读取。也如实区分迁移拒绝、运行时 WARN、PROD 只打 note。但“降级只剩路由消失和元数据可见”（`DESIGN.md:761,802`）仍不成立：旧写者能向通用卡片库写入私有答复，见 R3-A2。该问题与 R2-A2 是同一缺口，不重复计数。 |

本表的 closed 仅指设计层已回答该项，不代表实现、测试或上线验收通过。本次为 Review 518 的第三轮窄确认，按 Ops 模式离线核对 `ROUND2-REPORT.md`、`ROUND2-RESPONSE.md` 与修订稿。platform 证据固定为 `36481b9002a93d25f978b4eaad1253c58c6b4e6f`，infra 固定为 `266b286332913149472b850640fa4fdc8b864e50`，均经 `git show` 读取；未以共享工作树的在制改动作证据。`DESIGN.md` 与该 infra 提交的 `agent-config/work/crew/DESIGN-crew-intake-2026-10-22.md` 字节一致，SHA-256 为 `66d2547c32a485885da2e96b5aa86c9ce2f867802e3bb31a8839302aaf4eb31d`。

## 六项修法带来的新 A

### R3-A1 — 五选项优先级卡不符合现有卡片输入契约，首批必经入口无法开卡

设计：§5.3 `DESIGN.md:505–506` 明定优先级卡有 `p1 / p2 / p3 / later / decline` 五个选项，且不能用自由文字替代；§4.6 `:425` 的卡片改动清单只扩展工作号、答复限制、WorkID 传递和评估过滤，没有扩展选项上限。§8 `:649` 与切片 2（`:706`）把定优先级放在这个入口，直接 priority 路由要到切片 6（`:674`）。

代码：platform `api/internal/questions/canonical.go:153–157,358–375` 只接受零个或 2–4 个选项；超限返回 `options must be none or 2 to 4`。`api/internal/server/questions_wire.go:156–184` 把卡片选项逐个传入创建请求，`:189–191` 将 400 判为卡片本身无效，重试不能解决。

离线复现：在固定提交的缓存副本中，只临时模拟设计已列出的 `workIDPattern` 接受 `BI-n`，其余创建逻辑不改；以运行时实际使用的 `session=agentrt, principal=agentrt, role=operator` 调用 `Service.Create`。四选项对照返回 **201**，设计中的五选项返回 **400**，错误正是上述选项上限。普通问题因而无法取得 §4.3 第 3 条要求的优先级证据。常备例外不能替代所有普通问题的入口。

交 Owner 两个选项：**A（推荐）**，将 BI 优先级模板改成兼容现有上限的明确两步选择，两步均绑定当前 B，最终确定后才写 priority 证据；**B**，明确扩展卡片选项契约到至少五项，并把创建、显示、答复键、旧版本读取和契约测试纳入本次接线。两者均保留全部业务选择，不用 `none + 文字` 承载第五项。

### R3-A2 — 允许旧卡片写者继续运行，会重新打开文字答复泄露路径

设计：§4.6 `DESIGN.md:451` 明确允许旧二进制读写 BI 卡，承认它允许 `none + 文字`，却以“卡上本来只有编号和中性选项”判断文字隔离仍成立。这个判断只覆盖开卡内容，没有覆盖随后写入的答复。§5.3 `:506` 所需的拒绝逻辑只存在于计划中的新版本。

代码：platform `api/internal/questions/transition.go:109–120` 在 `allow_text=false` 时仍接受 `option=none` 的非空文字；`:45–54` 原样存入 `Question.Answer.Text`。`types.go:96–104,133–139` 不从公开投影移除它；`handler.go:21–25` 的卡片列表和详情允许 viewer 及以上读取，`transition.go:232–270` 不查问题读者名单。旧 Console 的 `console/src/pages/question/QuestionAnswerForm.tsx:131–146` 还始终显示 “None of these”，选择后要求补充文字，因此这是正常界面可以走到的路径。

离线复现：把一张仅含中性信息、`work_id=BI-518`、`allow_text=false` 的合成卡写入测试文件，模拟新版本已经开卡；随后完全使用指定旧版本的内存 HTTP 路由和文件存储。admin 提交 `none + 合成私有澄清文字` 返回 **200**；不相关会话分别用 viewer、reporter、operator 令牌访问已知卡号和 `status=all` 列表，六次读取均返回 **200** 且含该文字。没有调用真实服务、发送通知或使用真实原话。

因此，旧进程并存或回退后，Owner 若在卡上解释需求、引用原话，文字就进入通用读接口；即使新 intake 谓词拒绝把该答复当成证据，也已经泄露。恢复新版本后，现有公开投影仍会读出这条已保存的答复。数据库终态触发器和独立令牌键不能保护这个文件存储。I-D8 的流水线拒旧版也不能单独解决设计自己指出的滚动并存、Argo 或手工回退路径（`DESIGN.md:439,762`）。

交 Owner 两个选项：**A（推荐）**，先交付兼容补丁版本，使所有卡片写者都具备 BI 卡禁止文字答复的保护；全部切换后才启用 BI 开卡，并把该兼容版本设为这些写者允许回退的最低版本，明确覆盖流水线以外的回退路径。**B**，保留回退到当前旧版本的能力，但隔离旧写者对 BI 卡存储的访问；不能隔离时，回退期间停止卡片写入，明确接受这段不可答卡时间。不能只靠界面提示或拒绝入证据。验收须加入“新版本开卡 → 旧写者答文字 → 通用读取”的交叉探针，要求在写入前拒绝；§4.6 当前列出的四个探针没有这一项。

## 范围外

- 无新增范围外观察；未评审已确认的 §7.5，未重新提出 B/C 项。

首批缩减确认：不 join、每问题一个在途 mission、仅接单前合并、只做一种本机桥、outbox 后移、试点先于 Console 五视图，这些缩减本身未重新打开首轮或二轮 A。上述两项来自六条 A 的修法及其兼容安排。

检查与限制：完成了设计字节核对，以及指定代码的写者映射、卡片输入/答复/读取、自动评估、mission 状态机、事件守卫、授权和迁移发布链静态核对。共享缓存中三个 `TestReview518*` 探针通过，验证的是上述现有行为及旧鉴权配置忽略 `intake_tokens:`，不是未来 intake 实现通过验收。优先级探针首次误用外部 HTTP 身份进入保留的 agentrt 会话，被正确返回 403；改为实际运行时的 Service 调用后得到上述 201/400 对照。

另在内存中执行了指定 infra 提交的 PROD 迁移比较函数，以合成迁移清单替代目录和 health 读取：同版本退出 0；候选多 0009、库缺 0009 退出 1；旧候选、库多 0009 退出 0 且仅 note；已执行字节不符退出 1。与修订稿对当前发布链的陈述一致，未运行整条流水线。

未做：0009 尚不存在，不能执行其 DDL、真实 PostgreSQL 触发器/并发/锁序或新旧二进制连 0009 库的交叉验证；未运行 Go/前端全套测试或新全路由矩阵；未验证 PROD 现场流水线、Secret、V1–V9、外部产品能力、她 Mac 的连通性及真实 Dots 试点。没有网络、集群、数据库、MCP、SSH、提交或发版操作。仅写本目录 `REPORT.md` 及共享缓存中的固定提交副本和离线探针。未闭合项已以上述选项交 Owner 决定，不要求第四轮。

先修：R2-A2、R2-A6 未闭合；处理 R3-A1（五选项卡被现有输入契约拒绝）与 R3-A2（旧卡片写者重新引入私有文字泄露）。
END OF REPORT
