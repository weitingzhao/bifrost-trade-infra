# Codex 复核 62 — W-66 调度脚本第二版，重开后第 1 轮（`aa61184..2ef2721`）

2026-10-11 11:24 CDT · 只读 · 分支 `w31/w66-lane-v2`

统筹方的处置：先改，给重开后的第 2 轮，也是这条线的最后一轮。复核 43 的那一处关了，但同一类问题（期望那一侧不完整或被后来的事件盖掉，仍能通过）第四次出现，这次是三处。第 2 轮不逐条补：期望值只由一个对事件链的严格折叠给出（每个事件对着已有状态校验，不补齐、不跳过、不取后者）；验收是一条对全部证据的删改测试——每个删改重新封好摘要后，结论都不能是通过。再有必须改的就停线。

---

VERDICT: fix first

审查范围：`aa61184..2ef2721`。Review 43 的原 P1 **已关闭**，但“complete start evidence”整体仍只是**部分关闭**。

- **P1：事件侧没有完整验证，intent 的期望消费集合被忽略。** `agent-config/scripts/lane/query.py:172`、`agent-config/scripts/lane/state.py:329`。
  最小复现：合法通过路径中，仅把 implement 的 `step_intent.consumed` 改为 `{"repo":{"tree":TA}}`，同步 intent 文件摘要；manifest 和 recorded 保持正确。
  经真实 `inspect_lane` 读取路径、有效哈希链和全部文件摘要校验，仍得到 `verdict_pending (passed)`，证据问题列表为空。空集合、错误 commit/tree、额外仓库、未知字段也可通过。
  同类遗漏：基线记录加未知字段仍通过；上一轮 pinned 少一个仓库会被补成 baseline（`query.py:279`）；不完整的 rejected 集合被跳过（`decide.py:446`）。
  最小修法：对每份事件携带的集合按完整 lane 仓库集合做闭合验证，再比较 intent、recorded、manifest；无效期望必须报 incomplete，不能忽略或补齐。

- **P1：后追加的事件能覆盖已经确定的期望起点。** `agent-config/scripts/lane/query.py:215`、`:293`。
  最小复现：保留首轮 baseline `(A,TA)`，追加同轮 `round_opened`，令 start_set 为 `(A,F)`；implement 的实际、expected、consumed 均写 `(A,F)`，后续证据合法，结果仍为 `passed`。
  最小修法：拒绝重复及乱序的 round_opened，并核对 start_set 与 baseline／上一轮完整 pinned 推导出的权威集合；不能 last-wins。

- **P1：提交号不变、树号改变的仓库仍可进入通过集合。** `agent-config/scripts/lane/decide.py:430`、`:437`。
  最小复现：两个 change 仓库，甲正常从 A 到 B；乙固定为基线提交 A，却把树从 TA 改为 F，verify/review 使用 `(A,F)`，乙无需 bundle，最终仍 `passed`。
  单仓库保持基线 commit 会被“produced no commit”拒绝，但多仓库的上述组合不会。
  最小修法：逐仓库检查固定 commit 与已知 baseline／start commit 相同时树号必须一致；集合与 bundle 判定均使用完整记录。

- **P2：守卫测试不能保证报告宣称的结构约束。** `agent-config/scripts/lane/test_decide.py:586`。
  最小复现：现有正则漏掉 `if exp.get("tree")`、`exp and act`、`x if exp else y`、`expected and act`，也不检查其他模块的 helper。
  最小修法：用 AST 检查比较及调用路径，并为这些违规写法加入阳性对照；补齐上述实际错误放行的行为测试。

原三处复现已重试：首轮、`--start baseline` 后均因树号不符失败（`decide.py:322`）；context 起始树与 pinned 树不同也失败（`:427`）。旧版基线事件没有 tree 被拒绝；JSON 重复键和重复 `--repo` 均被拒绝，但未知字段尚未在所有事件侧路径拒绝。

形状并非完全对称：主要比较经 same_set，实际侧先验证完整仓库集合，因此普通单侧漏仓库不会逃过循环；上述提交号单独比较及无效 rejected 的条件跳过仍是例外。

T31 的 137 个生成断言全部通过，没有现有反例误报 passed；但期望侧只直接修改 expected_start，没有覆盖事件链。缺少期望／consumed 单侧删仓库、空字符串树、跨仓库交换 commit/tree 和多仓库组合。额外探测中，单侧删仓库、空树和实际侧交换被拒绝，上述事件及组合反例则通过。

重复和乱序 attempt 仍被拒绝；后续空 pinned 保留先前集合；三个记录／建 lane 入口在空 LANE_EXEC 下均先拒绝，锁和修复调用为零。非测试代码未发现进程启动调用。

全程只读，禁用字节码写入；未运行需要落盘的完整 212 项测试。剩余问题仍包含同一种“期望侧不完整却放行”的漏洞，另有期望覆盖和提交／树一致性漏洞，不能宣布 complete start evidence 已关闭。

END OF REPORT