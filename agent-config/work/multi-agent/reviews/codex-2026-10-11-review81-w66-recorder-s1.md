# Codex 复核 81 — W-66 记录器第一片：事件日志、纯折叠、发布视图、防线（infra `20077b3..e0ebd54`，platform `dce6fe9`）

2026-10-11 15:44 CDT · 只读

统筹方处理：先改，第 2 轮。1 处必须改的（一条封好链但类型不对的事件让整次折叠抛异常，违反 V1、V5）和 11 处应该改的；六千多行第一次被复核。任务书 `TASK-2.md` 把它们归成五类；停线条件：下次复核再找到任何让 `fold` 或 `publish_view` 抛异常的输入就停线，改成在一个边界上把原始事件解析成定型的事件。复核对报告里 11 处「设计没写清」的读法逐条给了意见，照它的办。

---

VERDICT: fix first

以下路径除另注外均相对 `agent-config/scripts/recorder/`。

- **P1 — `validate.py:210`：非法类型使整次折叠崩溃。** 一条完整封链的 `note(by=[])` 即触发 `TypeError: unhashable type: 'list'`，没有 `defects`，违反 V1/V5。闭集字段在集合查询前应逐项检查类型，包括嵌套字段。

- **P2 — `commands.py:140`：`declare --replaces` 必然失败。** 新声明之前先校验 `step_superseded`，新 `by_step` 尚不存在，实际返回 `by_step_missing`。在同一批追加中先声明、再取代，保持整批验证和写入。

- **P2 — `fold.py:343`、`fold.py:433`：未开始的被取代步骤仍在列表里。** `open → declare A → declare B → supersede A(by_step=B)` 后 A 仍是 `waiting`；两张表都要求移除并计入 `withdrawn`。删除额外的 `not step.by_step` 条件。
  四事件反例：`open → declare A → supersede A(by_step=A) → close`，无缺陷，却同时输出 `ball=nobody` 和 `A=waiting`；现有 V12 断言确实失败。另应拒绝自我取代。

- **P2 — `fold.py:81`：按墙钟排序会覆盖最新失败轮次。** 三条工作事件建立待批观测，再追加确认轮次 `ended_at=100`、失败轮次 `ended_at=95(error=timeout)`；`now=101` 仍输出 `can_act=yes`。最新轮次应按追加顺序确定，回拨只参与时间可信度判断。

- **P2 — `fold.py:474`、`fold.py:716`：失败轮次刷新“最后读到”的时间。** `pending@90 → confirmed@100 → timeout@150` 输出 `last_seen.at=150`，实际成功读取没有更新。应使用该对象最后成功确认的时间，不能借用任意最新轮次。

- **P2 — `publish.py:87`：最终发送字节没有被最终计量。** `_fit` 之后才加入 `reduced`、`full_at` 等。复现：30 件工作各 20 个 running 步骤，name/who 各 80 ASCII 字符、command/note 各 200，title 80，第一件含 3364 条 `unknown_field` 缺陷；第 4 级输出 **204831 字节**。将缩减元数据纳入每次计量，并验证最终编码。

- **P2 — `publish.py:49`：host 校验不等同于平台校验。** `publish_view(fold([],[],1), "board\n")` 保留该 host；Python 的 `$` 允许末尾换行，平台会拒绝。改用 `fullmatch`。

- **P2 — `fold.py:658`：无关日志排列改变同一审批的期限。** 两份日志的 `sampled_at=10`、`seq=3`、状态均 pending，期限分别 50/60；交换日志顺序，输出期限从 60 变 50。独立日志的 seq 不能消除平局；增加稳定的跨日志排序及明确的平局规则。

- **P2 — `estimate.py:75`：结束时回拨仍进入用时样本。** `open → declare → start@100 → finish(exit=0)@90` 的结束事件在回拨区间，但 `_anomalous` 返回 False，样本为 −10 秒。检查结束事件及运行跨越的回拨区间，拒绝异常用时。

- **P2 — `commands.py:132`：记录类永远没有声明时估算。** `declare(kind=release, watch=record)` 跳过 `usual_for`，即使手写发布用时存在也不写 `usual_s`，真实发布不会进入 slow，也没有预计。记录类应采用手写回退值。

- **P2 — `fold.py:765`：无关笔记重置球的等待起点。** `open@1 → note@100`，球始终是 `coordinator/ended_awaiting_check`，但 since 从 1 变 100。设计要求使该归属成立的事件时间；按命中原因追踪来源。

- **P2 — `test_fields.py:468`、`test_enumerate.py:27`：验收漏掉关键输入。** 类型变异总是把首个字符串字段 `type` 改成数字，实际重复测试未知事件，没有逐字段测试。32 字母覆盖事件类型，但没有带 `by_step` 的取代；延长到 5 也不会覆盖上述 V12 反例。逐字段增加类型变异，并扩充字母及具名反例。

验证：只读方式执行了默认 **33825** 序列、53 个纯函数具名测试、纯度静态检查、发布边界测试和八份夹具字节比对，均通过；上述反例另行复现。完整磁盘写入、并发及 Go 测试未重跑。

源码核对：锁覆盖修尾与整批追加；坏链、满日志拒绝追加。未发现范围外改动、非测试网络或子进程调用、状态裁决出口或将引语拼成机器代码。防线实现了指定扫描及匹配反例，但仍会漏掉设计已承认的别名、复制及范围外消费者。

平台夹具测试经 `put` 调用真正的 `HandlePut`；依赖测试检查六包的传递依赖。`RECORDER_FIXTURES` 未设置时明确调用 `t.Skip`，普通非 verbose 的成功输出不会展示跳过原因。

报告的歧义解读逐项：① clock 字段名可接受，但报告描述的比较方向写反；②记录状态词可接受，时间取法错误，见上；③保留最近 feed 合理，但应先跨工作按时间排序；④中文类别映射合理；⑤所有球带 since 合理，取整份日志 max_at 不合理；⑥ V8 检查本工作条目合理；⑦轮次放观察者日志正确；⑧ feed_cut 正确；⑨摘要不带 steps_total 正确；⑩ last_at 作为排序辅助合理，但已关闭工作应按关闭时间排序；⑪ commands 被移除时设置 full_at 正确。

END OF REPORT