# Codex 复核 65 — W-66 调度脚本第二版，重开后第 2 轮，也是最后一轮（`2ef2721..0a54279`）

2026-10-11 12:22 CDT · 只读 · 分支 `w31/w66-lane-v2`

统筹方的处置：**这条线停**。复核 62 的三处具体复现都关了，但同一类问题又找到五处必须改的：删改测试的「允许不变」清单里放进了决定通过含义的字段（任务书和配置的摘要、lane 的编号、轮次上限、判词）；放行出口仍然信已经盖上的判词；放错步骤的集合被忽略；提交与树的对应只查相邻一步；开轮不查预算和上一轮的终态。这是这条线第五次复核、第五次在「证据不支持却能通过」上不闭合。停线条件是开工前写下的，照此执行：分支不合并。教训第 77 行；下一步的建议写在 W-66 下面。

---

VERDICT: fix first

范围：`2ef2721..0a54279`。全程只读；复现使用内存文件系统、真实摘要校验和重新封好的事件链。

Review 62：三个 P1 的原始复现均已拒绝：intent 的五种错误消费集合、基线未知字段及缺仓库集合（`agent-config/scripts/lane/fold.py:278、322、457、513`）；重复开轮（`:186`）；双仓库原地改树（`:496`）。这些具体复现已关闭，同类问题仍部分未关闭。原 P2 仅部分关闭，见下。

- **P1：allow-list 豁免了决定通过含义的证据。** `agent-config/scripts/lane/test_mutate.py:48`；`agent-config/scripts/lane/evidence.py:162`。
  最小复现：通过夹具中单独改 `config_sha256` 或 `brief_sha256` 为另一摘要、改 `lane_id`，重封事件链，仍 `passed`、问题列表为空。intent 文件的 `consumed` 改成 `{}`，同步其摘要和 manifest，事件保持正确，也仍通过。
  最小修法：解析并校验 intent；绑定其身份、任务书、配置、固定脚本、消费集合与事件及 manifest。移除这些字段的笼统豁免。

- **P1：实际放行仍信判词戳记，mutation 测试检查了另一字段。** `agent-config/scripts/lane/state.py:157`；`agent-config/scripts/lane/commands.py:506`；`agent-config/scripts/lane/test_mutate.py:542`。
  最小复现：合法通过判词后追加未知事件并重封链，`decide_result=unknown`，但 `state=passed`，`pass-set` 仍输出集合。另把退出码 9 那轮的 `verdict.result` 改成 `passed`，状态也通过，重算仍是 `step_failed`。
  最小修法：保留历史判词，但重算不通过或 fold 无效时禁止当前放行；测试同时断言状态及 `pass-set`，取消 `result` 豁免。

- **P1：已知字段放在错误步骤上，其携带集合被忽略。** `agent-config/scripts/lane/fold.py:46、325、329`。
  最小复现：verify 的 `step_recorded` 添加 `pinned={"repo":{"tree":TA}}` 或同形 `sha_set`；review 添加同形 `pinned`，重封链后均仍 `passed`。
  最小修法：按步骤限制字段；禁止其他步骤携带这些集合，或完整验证每份携带集合。

- **P1：提交与树的一致性只检查相邻起点。** `agent-config/scripts/lane/fold.py:491`；`agent-config/scripts/lane/decide.py:451`。
  最小复现：双 change 仓库第二轮，甲正常前进，乙从 `(C,TC)` 固定回基线提交 `(A,F)`，其中 `F≠TA`；消费和检查均配套，仍 `passed`，乙还被免除 bundle。
  最小修法：逐仓库保留已知 commit→tree 映射，覆盖基线及历轮；同一提交不得出现另一树号。

- **P1：fold 没有验证开轮的预算和前轮终态。** `agent-config/scripts/lane/fold.py:246`；`agent-config/scripts/lane/test_mutate.py:54`。
  最小复现：第二轮通过夹具把 `max_rounds` 改为 1，仍通过；baseline 夹具把前轮判词改为 `passed`，后续开轮及第二轮仍通过。`inputs` 改成非空也通过，违反规格 §3 的“第一片只允许为空”。
  最小修法：fold 开轮要求前轮为合法否定终态且预算未耗尽；校验 `inputs=[]`，撤销相关豁免。

- **P2：AST 防线仍依赖变量名，且漏检布尔表达式。** `agent-config/scripts/lane/test_mutate.py:77、140`。
  四个原阳性对照均命中；`x = exp and act`、`if required:`、`if folded.start_of(1):` 均漏检。最小修法：覆盖 BoolOp 及期望值别名/来源，并加入这些阳性对照。
  fold 也不是唯一读取入口：`agent-config/scripts/lane/query.py:257、263` 仍读原始起点种类/基线；`agent-config/scripts/lane/state.py:152` 的输出集合仍取原始事件。应统一使用 Folded。

allow-list 逐项结论：`brief_path、brief_copy、brief_sha256、config_path、config_sha256、pinned_files、lane_id、max_rounds、inputs、result` 涉及绑定或合法性，不能这样豁免；`argv、cwd、env_names、toolchain` 描述实际执行对象和环境，也须绑定，当前 corpus 未包含 intent 内容。
`at、created_at、started_at、ended_at、lstart、pid、driver_pid、limit_seconds` 不决定本片通过条件；时限只标 overdue。
`title、reason、notes、note、operator、how、evidence、text、p1、p2、p3` 属说明、记名或展示；规格未让其文本内容产生肯定判词，其中 `evidence` 是人工补记文字，并非通过证据集合。

原 mutation 循环在等价内存夹具上复跑：`20786 / invalid 16885 / failed 2269 / allowed 1632`，与报告一致。manifest 摘要、输出/bundle 摘要、判词摘要映射和哈希链会重封；枚举无随机抽样，但不覆盖 intent 内容、错误步骤上的已知字段，且忽略实际放行出口。九夹具覆盖三种仓库形状的首轮、第二轮和 baseline 重开；没有“两 change 加一 context”的组合。
新提交配相同树号在 change 仓库合法（规格 §3）；context 改提交应失败。重复开轮、前段乱序、未知字段/种类已拒绝，但判词后的缺陷仍可放行。
未运行需落盘的完整 217 项测试；非测试代码未发现进程启动调用。**“complete start evidence”未关闭；本轮存在 P1，应停止该 lane。**

END OF REPORT