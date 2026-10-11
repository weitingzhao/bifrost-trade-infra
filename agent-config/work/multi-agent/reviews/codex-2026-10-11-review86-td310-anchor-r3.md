# Codex 复核 86 — TD-310 信任锚第三轮（最后一轮）：冻结的身份是随机值，平台只认它见过被解开的那一次

2026-10-11 16:35 CDT · 只读 · platform `9b73489..6658550`，infra `e498f5c..3fdaa41`（分支 `w31/td-310-anchor`）

统筹方处理：按第三轮之前写下的条件停线。第二行是 `found`：一台没有读到新冻结的平台会接受上一次冻结的旧解冻对象（要直接改集群里的对象）；两个进程交错写状态文件，会把一次没解开的冻结降成「更早的」（不需要改对象）。分支不合并，密钥不编进平台，PROD 上冻结继续被拒绝。解冻协议先出设计：`DESIGN-release-freeze-protocol-2026-10-11.md`。决定和依据见 `PLAN-w56-unattended-prod-2026-10-10.md` 决定记录之六，教训第 86 行。统筹方自己的验收：按 CI 的限制 54 个包全过、九个点名测试都过；竞态检查那一遍在本机同时跑三路复核时超过 10 分钟的默认上限，不是发现了竞态。

---

VERDICT: fix first
ANOTHER WAY TO LIFT WITHOUT A FRESH SIGNATURE: found
NEEDS DIRECT WRITE TO THE CONFIGMAP: no

Review 82：
- **已关闭：无编号冻结被忽略。** `api/internal/releasepolicy/memory.go:165–185`。重新静态复现 A 冻结→签名解冻→读到无编号 B→恢复 A：B 成为 unidentified，A 被拒；对应测试在 `identity_test.go:22`。
- **已关闭：break-glass 后同秒复用编号。** `memory.go:91`、`write.go:117`。重新静态复现完整重置→同秒冻结 B→重交 A 签名：随机 id 不同，`write.go:195` 拒绝；对应测试在 `identity_test.go:74`。
- **部署顺序部分关闭。** infra `docs/RELEASE.md:192–195` 已要求先手工更新 Task/程序 ConfigMap，再升级全部平台；但脚本检查不能约束旧脚本或直接 API 调用。
- **CI 顺序在新定义中已关闭。** infra `pipeline-ci-platform.yaml:83,98` 等待 sibling 并设置 `BIFROST_CI`；集群应用前仍有跳过窗口。

**P2 — 漏读 B 的平台接受 A 的旧解冻对象。** `api/internal/releasepolicy/memory.go:149–163`、`policy.go:286–299`。
最小复现：冻结并签名解冻 A；STG 记住 A；PROD 冻结 B；STG 未读到 B；直接恢复 A 的解冻对象。STG 报未冻结，看到 B 的 PROD 仍拒绝。此复现**需要直接写冻结 ConfigMap**；空状态或状态丢失的新进程同样放行。
影响：STG 的 tier B `start_pipeline_run` 冻结检查通过；有效策略及其余条件满足时 C 级可自动批准（`server/release_policy_wire.go:81,146`）。新版 Tekton 只检查对象形状，也接受恢复后的 A；release window 是独立条件，并未证明 B 已解冻。
读取并非连续观察：状态/决策请求和 metrics scrape 会读；PROD workers 启用提醒时启动即读、随后每小时读；STG 默认关闭提醒（`server/metrics.go:53`、`server/release_policy_wire.go:19,64`、`releasepolicy/expiry.go:94`）。
最小修复方向：解冻判断必须依赖所有门禁共享、可证明当前冻结身份的权威记录；本地观察历史无法证明没有漏读。按停止条件，本 lane 停止，锚不发布，先写协议设计。

**P2 — 合并可把未解冻 B 降为 earlier；无需直接写冻结 ConfigMap。** `api/internal/releasepolicy/memory.go:281–295,432–438,449–458`。
最小复现：STG 正常产生 A 的有效解冻对象，PROD 共享记忆为空；PROD worker 读 A、算出 `next=A(lifted)`，暂停在状态 Update 前；PROD API 正常冻结 B、记录 B 并返回；worker 恢复，执行 `combine(B,A)`，A 胜出、B 进入 earlier，随后旧 A 的此次状态读取报未冻结（`engine.go:184`）。没有 B 的签名。
最小修复方向：不同身份且缺少因果顺序时应保留阻断，不能以“后提交的观察”认定更新；补上述受控交错测试，并纳入协议设计。

**P2 — 属性测试漏掉决定性调度。** `api/internal/releasepolicy/identity_test.go:312,352–364`。
模型的单向断言符合停止条件，允许时多拒绝不会失败；但每步都让两台引擎观察对象，重置也总是同时清两份记忆和对象。
最小遗漏序列就是 A→签名解冻 A→B（另一引擎不观察）→回滚 A→落后引擎决策；也不能生成上述共享状态交错或单边/部分重置。最小修复：独立安排各引擎观察、状态损坏和 Update 交错。

其他核对：`policy.go:274` 每次重新验签，不靠 lifted 位放行；大写 id 被拒，首尾空白被规范化，更长 id 按完整 token 比较，第二个 token 不替代第一个，等价时间格式仍须匹配签名正文。重复时间的无编号冻结继续阻断。只清 frozen_at、留下 id 仍阻断；记忆为 LIFTED 时换回 never-frozen 也拒绝，符合整份重置的 break-glass。
状态损坏/不可读使 Status 拒绝；缺失或空文件被视为空记忆。写记忆失败只记录警告（`engine.go:177–184`），没有可靠保存新冻结。ConfigMap 缺失/读取失败时 Status 拒绝，但既有 `FreezeSet` 在 `engine.go:250–252` 返回未冻结，tier B 检查并非故障即拒。
随机源返回错误时写入不发生；写冲突不重试，未发布 id 不进入记忆（`write.go:117–145`）。
混装期间，旧平台仍可写计数 id，新平台写随机 id，双方可因历史/解析不兼容长期拒绝；`release.sh:702` 只保护新版脚本的 freeze。unfreeze 不查版本本身不会绕过当前 id 验签，但不能保障混装可用，应遵守过渡期间禁冻/禁解冻。

**P3 — 操作说明仍给出已拒绝的签名格式。** `api/internal/actions/catalog.go:147`。
复现：按说明签 `unfreeze frozen_at=…`，平台拒绝。最小修复：补 `freeze_id=<id>`，与 `UnfreezePrefix` 一致。

CI 摘要已独立重算为 `fb1a9593…02cfd53c`，与 `freeze_effects.json` 一致。Go 测试因只读沙箱不能创建临时构建目录而未运行；约 23 秒的本地耗时不能证明 2 CPU 下整包满足 120 秒，需在实际 CI 验证。

本轮命中停线条件，Owner 当前不应部署锚。协议设计通过后，安全顺序应为：核对 never-frozen 及两边记忆的兼容状态、暂停冻/解冻；手工应用新版 freeze-check Task/程序 ConfigMap 和 CI Pipeline；再升级 STG、PROD 全部写入方并统一脚本。平台合并而新版 CI 尚未应用时，旧流水线可能保持绿色并静默跳过锚校验：它既不等待 clone-infra，也未设置 `BIFROST_CI`，并非必然转红。
END OF REPORT
