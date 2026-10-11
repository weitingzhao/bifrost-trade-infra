# Codex 复核 82 — TD-310 信任锚第 2 轮：解冻只解它点名的那一次（platform `a55b2cc..9b73489`，infra `7082197..e498f5c`）

2026-10-11 15:45 CDT · 只读

统筹方处理：先改，这是规则里的最后一轮。复核 79 的两处关了；又找到两种不经 Owner 新签名解冻的办法（已有编号历史时，后来手写的无编号冻结被忽略；应急重置清掉了编号的连续性），外加上线顺序没写、CI 里交叉校验可能被跳过。四次发现出自同一个性质：冻结的身份取自会重复、会被重置的状态。所以最后一轮不再补规则，改根子（`TASK-3.md`）：身份用永不重复的随机值；平台记住的是「最后见到的那一次冻结是谁」，闸只在它亲自验过那一次的解冻签名时放行；冻结协议带版本号，脚本和平台对不上就拒绝；写下改对象形状时唯一安全的上线顺序。下次复核再找到一种，就停线，密钥不上线，协议先出设计。

---

VERDICT: fix first
ANOTHER WAY TO LIFT WITHOUT A FRESH SIGNATURE: found

P2 — `api/internal/releasepolicy/engine.go:225`、`api/internal/releasepolicy/policy.go:287`：已有编号历史会忽略后来无编号的冻结。
复现：冻结 A（id=1、T1）→ 签名解冻并保留对象 → Owner 手写冻结 B（无 id、T2>T1）→ 平台读到 B → 恢复 A 的解冻对象。B 的 `(id=0,T2)` 不会更新历史；A 命中 `sameFreeze`，平台重新放行，无针对 B 的签名。此复现需要直接写 ConfigMap，属于 brief 指定的手写对象场景。
最小修复：独立记录无编号冻结的阻断状态，不能因已有较大 id 而忽略它；补上述回归测试。

P2 — `api/internal/releasepolicy/write.go:158`、`api/internal/releasepolicy/engine.go:239`，infra `docs/RELEASE.md:163`：break-glass 清掉了编号的全部连续性。
复现：固定 `Now=T`，A（id=1）取得有效解冻签名 → 按文档清空冻结对象及两边历史 → 新冻结 B 再获 id=1、同一 T → 重交 A 签名；前缀、验签及当前 resourceVersion 均通过。实际发生需同秒重置或时钟重复；普通较晚时间的重置不会通过旧签名。
最小修复：保留所有写入方共享、恢复时不清零的编号高水位；若允许整体丢失，则签名必须绑定不会复用的冻结身份。

P2 — infra `docs/RELEASE.md:202`、`scripts/release/freeze_schema.json:26`：缺少本次 schema 与平台升级顺序，可能卡住所有发布。
复现：先部署新平台，冻结后正常解冻；旧 Task 因多出 `freeze_id` 拒绝解冻对象，发布平台自身修复版本也被挡。最小修复：明确先手动更新 Task/程序 ConfigMap，再升级全部平台写入方，过渡期间禁止冻结。

P3 — infra `k8s/cicd/tekton/pipeline-ci-platform.yaml:83`：`test-api` 只等待 `clone`，不保证 sibling infra 已存在。
复现：`clone-infra` 比 Go 测试慢，`anchor_test.go:48` 跳过交叉校验，错误但格式合法的指纹仍可能通过 CI。最小修复：`runAfter: [clone, clone-infra]`。

Review 79：同秒重放原复现已关闭（`write.go:119,198`，A 后的 B 获更大 id）；解冻竞态已关闭（`release_policy_facts.go:79,88`，B 更新后 A 的条件写拒绝）；锚测试部分关闭（`anchor_test.go:71,75` 能发现错误指纹，CI 顺序仍缺）。
两个原复现均重新静态推演；未执行 Go 测试。上述残留发现命中本轮“再修一轮”条件；下一轮再次发现此类问题即按 brief 停线，锚继续不发布。

以下十二种组合按“冻结/解冻对象由对应平台版本生成”、历史一致计算；“允/拒”是 Tekton 结果：

| Task | 平台 | 从未冻结 | 冻结 | 已解冻 |
|---|---|---|---|---|
| 旧 | 旧 | 允 | 拒 | 允 |
| 旧 | 新 | 允 | 拒 | 拒（误阻断） |
| 新 | 旧 | 允 | 拒 | 拒（误阻断） |
| 新 | 新 | 允 | 拒 | 允 |

没有组合会直接放过 `frozen=true`；新 schema 接受从未冻结形状，拒绝无 id 的解冻形状。旧平台读取新版解冻文本也会拒绝，不能在混合版本期间启用冻结。
正常多副本竞争、历史落后但对象仍保留 id、对象不存在时并发创建均受条件写保护；冻结冲突会重新读并分配，解冻不重试；`freeze_id=1` 不会匹配 `10`（`policy.go:239`）。
`release.sh:713–728` 从同一状态响应取 id 与时间并显示后签名；无 id 时在签名前退出。未发现它会签另一冻结；状态随后变化会被平台拒绝。`Install` 的冲突不留下永久锁，重新提交会重新读取，也不会覆盖读取之后出现的新策略。
验证：14 个纯读取 Python 测试通过，实跑新旧 schema 矩阵并计算公钥指纹与常量一致；未调用 HTTP、平台或集群，未写文件。

安全 rollout 顺序：修复上述问题后，在当前从未冻结形状下暂停发布及冻结操作；Owner 先手动更新 freeze-check Task 与程序 ConfigMap，随后升级 STG/PROD 全部平台写入方并更新脚本，确认版本一致后恢复操作。现有 `docs/RELEASE.md:202–207` 只写检查流水线的安装顺序，没有写这次平台/schema 升级顺序。
END OF REPORT