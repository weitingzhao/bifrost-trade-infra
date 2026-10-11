VERDICT: fix first

- **P1 — 重复 attempt 能掩盖失败和否决。** [recorder.py:125](~/agent-work/w66-lane-v2/bifrost-trade-infra/agent-config/scripts/lane/recorder.py:125) 不检查步骤顺序、已有 attempt 或终局状态；[state.py:265](~/agent-work/w66-lane-v2/bifrost-trade-infra/agent-config/scripts/lane/state.py:265) 只取同一步的第一条记录。内存复现：implement 第一次退出 0、第二次退出 9，随后验收和复核成功，仍得到 `verdict_pending (passed)`；review 第一次通过、第二次 `rejects: true`，也得到同一结果。记录入口必须拒绝重复，读取端必须将重复或乱序事件判为无效，不能静默忽略负面事实。

- **P1 — 放行契约缺少启动前条件。** [decide.py:133](~/agent-work/w66-lane-v2/bifrost-trade-infra/agent-config/scripts/lane/decide.py:133) 不校验 implement 消费的起点；`RoundEvidence` 没有预期起点或启动前检查结果，[recorder.py:155](~/agent-work/w66-lane-v2/bifrost-trade-infra/agent-config/scripts/lane/recorder.py:155) 又固定写入空 `pre_checks`。内存复现：第一轮 implement 消费新提交集合而非目标基线，仍返回 `passed`。需将这些条件纳入证据和纯判定输入，缺失时拒绝通过。

- **P2 — 产物未按要求持久化。** [recorder.py:226](~/agent-work/w66-lane-v2/bifrost-trade-infra/agent-config/scripts/lane/recorder.py:226)、242、249 用 `write_bytes` 写 stdout、stderr、report、bundle，随后发布并同步 manifest，却没有先同步产物文件及相关目录。机器崩溃后可能留下已持久化的记账事件和未持久化的证据。应落实规格 §2“结束后 2”的同步顺序。

- **P2 — 残尾备份可能短写后仍被当作成功。** [fsutil.py:50](~/agent-work/w66-lane-v2/bifrost-trade-infra/agent-config/scripts/lane/fsutil.py:50) 忽略 `os.write` 返回长度。若发生短写，修复会发布不完整的残尾副本，随后截断原日志；副本摘要不匹配又使修复事件无法补记。应循环写完全部字节，再同步、rename 和截断。

- **P2 — 六关并非所有入口的唯一约束。** [commands.py:38](~/agent-work/w66-lane-v2/bifrost-trade-infra/agent-config/scripts/lane/commands.py:38) 将空值 `LANE_EXEC` 当作不存在；215、246 的参数检查先于第一关。实测同时设置 `LANE_EXEC` 并给出不存在的 brief，返回的是 `brief not found`。`new` 不调用转换表，记录器也不查表；预算没有规格要求的共用 `may_open_round`。应统一入口及优先级。

- **P2 — 第二轮 intent 仍绑定第一轮任务书。** [recorder.py:141](~/agent-work/w66-lane-v2/bifrost-trade-infra/agent-config/scripts/lane/recorder.py:141) 从 `lane_created` 取 brief，未取当前 `round_opened`，也未引用该轮已发布的任务书副本。换 brief 开第二轮后，记录的来源路径和摘要仍属于第一轮。应绑定当前轮的副本。

- **P2 — 验收覆盖少于规格声称的范围。** [test_decide.py:128](~/agent-work/w66-lane-v2/bifrost-trade-infra/agent-config/scripts/lane/test_decide.py:128) 的 T31 未逐项覆盖起点、启动前检查、消费集合错配、bundle 缺失、已否决集合及人工补记；T28 未覆盖全部缺参数及“已知但不是当前未决”的 attempt；T48 未覆盖 verify 记账边界；T53②没有删除截断否决的证据。T22 的网格和四步搜索存在且实跑通过，但仅调用 `consult`，没有覆盖实际入口绕表和重复记账。

- **P3 — 规格与实现选择需要明确统一。** 21 项选择中的第 3 项，建议保留 T23 的失败优先级：信号结束显示 `step_failed`，否决集合仍永久登记；证据丢失时按事件否决关闭。应据此改写 §4 新增的绝对短路句。对唯一合法 attempt，这个选择没有打开重判或通过路径；上述重复 attempt 缺口是另一问题。另需明确 `still-unknown` 后恢复证据是否允许通过：当前函数忽略该补记，可返回 `passed`，与放行契约“没有任何人工补记”的字面要求冲突。

其余核对：`decide` 是纯函数；正常唯一事件路径下，已有否定判词和关闭类补记不会因早期证据丢失而重开，T61 的实现成立。哈希、序号和前链检查具备，修复不删除换行结束的完整事件；读取采用头—探测—头及三次重试，空闲锁的旧标签在读取路径被忽略。真实双锁驱动与 T62 属于第二轮，本轮尚不能验收。

本次保持只读，完成静态审查及内存复现，实跑 T22；未重跑需要写临时文件的整套 41 项测试。

END OF REPORT