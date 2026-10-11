# Codex 复核 88 — 调度脚本（记录器）第一片第 2 轮：原始事件在一处变成有类型的事件

2026-10-11 16:36 CDT · 只读 · infra `e0ebd54..8f33f71`，platform `17c0c87`（分支 `w31/w66-recorder`）

统筹方处理：按第 2 轮之前写下的条件停线。第二行是 `found`：三种输入仍让计算抛异常——`now = 10**400`（溢出）、标题里一个孤立的代理码（发布时编码失败）、嵌套一万层的一行（JSON 解码递归过深）。另有 11 处应该改的。不再逐个堵：输入处理重新设计，写进 `DESIGN-lane-recorder-2026-10-11.md`——对外只有全函数入口，逐行隔离加整次兜底，任何异常都变成一条缺陷记录或一份写明「算不出来」的合规文档，兜底被触发的次数本身进测试（在回归集、枚举、变异上必须是零）。设计过复核后第一片做第 3 轮，分支接着用。统筹方自己的验收是过的（99 条测试两遍 65 秒和 44 秒；九个夹具过了平台真实的校验；Go 全套按 CI 的限制通过）——验收过而复核停线，说明验收脚本没有覆盖「任意字节」这一类，重新设计里要补进验收。实现方定的十一条「设计没写」的规则，复核认可 ①–⑧ 和 ⑪，不认可 ⑩（观察者日志上的缺陷没有出口），⑨ 存疑，一并写进设计。

---

VERDICT: fix first
ANOTHER INPUT ON WHICH FOLD OR PUBLISH RAISES: found

以下路径除另注外，相对 `agent-config/scripts/recorder/`。停线条件已触发，应停止本轮补丁并重新设计输入处理。

Review 81 的十二项：
1. 已关闭：`validate.py:224`；真正封链的 `note(by=[])` 返回 `bad_type`，不再抛异常。
2. 部分关闭：`commands.py:137`；声明先于取代、整批校验成功，但崩溃后的半批无法恢复，见下。
3. 已关闭：`fold.py:343`、`validate.py:800`；未开始的被取代步骤计入 withdrawn，自我取代被拒且折叠忽略。
4. 已关闭：`fold.py:90`；确认@100 后追加失败@95，最新失败轮获胜。
5. 部分关闭：`fold.py:477`；普通失败轮不再刷新 last_seen，但矛盾轮次仍刷新，见下。
6. 已关闭：`publish.py:131`；原 204831 字节复现现在为第 5 级、8640 字节。
7. 已关闭：`publish.py:48`；`host="board\n"` 被移除，新增夹具字节匹配。
8. 已关闭：`fold.py:677`；期限不同的同采样时间观测成为 unknown；不同 seq 不破平局。
9. 部分关闭：`estimate.py:75`；结束@90、开始@100 被排除，但跨越其他事件的回拨区间仍进入样本。
10. 已关闭：`commands.py:132`；record 类调用手写回退，不取进程样本；磁盘入口未重跑。
11. 部分关闭：`fold.py:845`；note 不再刷新 since，但重复记录观测仍刷新，见下。
12. 部分关闭：`test_types.py:162`、`test_enumerate.py:27`；逐字段变异和带 by_step 的字母已加入，但全部变异日志断链后绕过读入路径。

新发现：
- **P1 — `fold.py:66`、`validate.py:52`：大整数仍使折叠崩溃。** 最小复现 `fold([], [], 10**400)` → OverflowError；封链 work_opened 的 `at=10**400`、观察轮的同类时间也抛。最小修复是在任何浮点转换和算术前定义并检查数值范围，统一处理 now 与事件数字。
- **P1 — `validate.py:55`、`publish.py:107`：孤立代理码使发布崩溃。** 封链首事件 `work_opened(work_id="w1", title="\ud800", at=1)` → fold 成功，publish_view 抛 UnicodeEncodeError。最小修复是在边界拒绝孤立代理码并记录缺陷。
- **P1 — `events.py:109`：JSON 解码异常漏出边界。** 正确摘要封口的 `{"seq":1,"prev_sha256":"","unknown":` 加 10000 层数组 → load_bytes 抛 RecursionError。最小修复是限制解码深度，并覆盖首次解析和 `_seq_hint` 的异常路径。
- **P2 — `test_types.py:164`：1980 个变异没有经过有效封链输入。** 实测全部 `invalid_seq=2`，随后第 167 行返回原始字典；“72 个合法居民”中的 seq=0/-1 也不是合法链序号。最小修复是重建正确前缀、禁止失败回退，分别测试链字段和事件字段，并覆盖真正的观察者日志。
- **P2 — `commands.py:170`、`repair.py:39`：边界之后仍读原始字典。** `open→declare none A→start(run=X)→无效重复 start(run=Y)→finish`，finish 选择 Y 后返回 run_mismatch。最小修复是从锁内分类后的 Step 取 run_id；修尾的已记录集合同样从有效事件生成。
- **P2 — `events.py:176`、`repair.py:98`：两行追加没有批次恢复语义。** 声明 B 行完整、取代 A 行只写半行时死亡，读入留下 A/B 两个 waiting；修尾只删残行，不撤销 B 或补取代。最小修复是一个封口事件表示整个批次，或增加可恢复的批次提交标记。
- **P2 — `estimate.py:72`：跨回拨区间的运行仍作为样本。** `start@100→note@90→finish(exit=0)@120`，backwards 含 note，但 `_anomalous=False`。最小修复是检查开始至结束之间的整个事件区间。
- **P2 — `fold.py:850`、`fold.py:883`：since 仍随重复观测漂移。** 同一运行记录在 10/20 两次观测，started_at 均为 5，since 从 10 变 20；同一 pending 审批也如此。最小修复是按原因连续成立的起点计算，覆盖 in_flight/unknown 等分支。
- **P2 — `validate.py:573`、`fold.py:477`：矛盾观察轮刷新成功时间。** 确认@100 后，轮@150 将同一键同时放入 confirmed 和 failed(timeout)，last_seen.at 变 150。最小修复是要求键唯一且两集合互斥；该轮无效并留缺陷。
- **P2 — `fold.py:90`：观察者缺陷被静默丢弃。** `observer_round.failed=[{"key":[],"error":"timeout"}]` 被忽略，输出没有缺陷条目，违背无效事件须留记录的契约。最小修复是输出 `observer.defects`。
- **P2 — `fold.py:534`：不同工作的 declared 等待互相覆盖。** 两工作同 wait_id，一项 yes、一项 not_yet，合并状态使用后一项，球错误成为 coordinator。最小修复是以 `(work_id, wait_id)` 标识 declared 等待。
- **P3 — `fold.py:801`、`validate.py:801`、`test_regressions.py:801`：超过 800 行。** 分别为 980、1034、1117 行；按解析、归约和测试主题拆分。
- **P3 — 平台 `api/internal/agentprogress/recorder_fixtures_test.go:19`：验收与提交血缘。** 普通跨包测试仍隐藏跳过提示；slice 1 可接受已知 CI 缺口，但合并前须补 Change-Id，并取得带夹具的真实验收结果。

设计沉默处逐项：①拒绝 U+202E、②摘要格式、③v 严格整数、④exit 显式 null 无效、⑤自我取代无效，均合理且须补文档。
⑥平局比较状态/期限/编号且忽略 seq、⑦works 按 work_id、⑧feed 的稳定次序，均合理且须补文档；不同采样时间取较晚者，换日志顺序实测不变。
⑨fold_incomplete 的 since 取最新非笔记事件，不能代表不完整开始时间，应省略或提供来源；⑩观察者缺陷无条目不可接受；⑪关闭排序退回 last_at 可作兼容规则。
取代环 A→B→A 当前允许、两步均 withdrawn；作为标记语义可以接受但须明确。跨工作不存在的 by_step 返回 by_step_missing。

验证：71 项无磁盘写入测试通过，29.64 秒，包含 37060 条枚举和1980项变异；旧夹具及新增 host 夹具字节匹配。磁盘、并发和 Go 验收未完成：只读沙箱禁止临时文件，Go 报创建构建目录失败。
范围：四个 infra 提交仅改 recorder；平台提交仅改指定测试文件；未发现非测试网络或子进程调用，未进行 HTTP/平台/集群操作，工作树无修改。
必须补入设计：上述十一项裁定、数值与 Unicode/深度边界、观察者缺陷出口、批次崩溃语义、逐原因 since、跨异常区间样本排除及工作内等待身份。
END OF REPORT
