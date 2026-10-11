VERDICT: fix first

复核提交 `74b2bcc`。发现以下问题：

- **P1 — `done` 覆盖真实退出码。** [lane_steps.py:406](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane_steps.py:406) 中 `wait_child` 丢弃 `proc.wait()` 的返回值；内存模拟中 runner 返回 9、`done.exit=0`，仍判成功。恢复路径也在确认进程结束前信任 `done`（:422、:440）。应核对真实退出码，并绑定 runner 的完成记录；这是 brief 特别要求检查的完成记录信任问题。

- **P1 — HEAD 一致不能保证验收的是该提交内容。** [lane_steps.py:458](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane_steps.py:458) 仅在 verify 前检查工作树；verify 修改已跟踪文件而不提交后，后续只比较 HEAD（:521），仍可 `passed`。内存模拟确认 review gate 接受脏工作树。应在验收后、复核前后重新检查内容一致性。

- **P2 — 正在运行时无法执行 `stop` / `abandon`。** [lane.py:109](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:109) 持锁等待整个 `drive`；两个停止命令也要求同一非阻塞锁（:190、:212）。持续输出的失控任务不会 stalled，停止命令只能退出 3。应让驱动在持锁期间接收停止请求。

- **P2 — 只确认组长死亡，可能留下子进程。** [lane_steps.py:83](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane_steps.py:83) 在 runner 死亡后直接返回，忽略同组中不响应 TERM 的后代；[lane.py:175](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:175) 在组长已死亡时完全跳过回收。应确认整个进程组退出；现有停止测试只检查组长 PID。

- **P2 — 启动崩溃窗口留下无法回收的实现进程。** [lane_steps.py:387](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane_steps.py:387) 启动 runner 后才持久化 PID（:402）。期间崩溃会留下 `starting/pid=None`；恢复将步骤关闭为 failed（:578），后续停止命令也找不到该进程。应在执行实际任务前完成身份登记。

- **P2 — `queue` 仍隐藏崩溃后待处理的 lane。** [lane.py:335](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:335) 只按状态白名单过滤，不检查进程；implementing/verifying/reviewing 即使进程已消失也被排除。[test_lane_enforce.py:613](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/test_lane_enforce.py:613) 甚至把没有运行步骤的 implementing lane 当作 busy。应根据实际运行情况列出待处理 lane。

- **P2 — verify 判词并非取自 stdout。** [lane_steps.py:389](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane_steps.py:389) 合并 stdout/stderr，再解析日志末行；仅 stderr 输出 `VERDICT: pass` 也能通过。应分别捕获两条流，按 stdout 判定。

上一轮九项结论（closed＝已关闭；not closed＝未关闭）：

- P1-1：**not closed** — lane_steps.py:406，真实退出码可被完成文件覆盖。
- P1-2：**not closed** — lane_steps.py:458、:521，目录与轮次隔离已补，提交内容绑定仍有缺口。
- P1-3：**closed** — lane.py:109；lane_state.py:200，锁覆盖读取、驱动和写回。
- P1-4：**closed** — lane.py:147；lane_steps.py:550、:560，预算和延长限制已实现。
- P1-5：**closed** — lane_state.py:104；lane_steps.py:387，使用 argv 和 `shell=False`。
- P2-6：**not closed** — lane_steps.py:387–402，启动身份登记存在崩溃窗口。
- P2-7：**not closed** — lane.py:175、:190、:212；lane_steps.py:85，停止与回收仍不完整。
- P2-8：**not closed** — lane.py:335，status 增加了进程检查，queue 仍隐藏失联 lane。
- P2-9：**not closed** — lane_steps.py:389、:480，格式校验已收紧，但解析流不符合要求。

验证：只读审查及内存模拟；未运行会创建文件的完整测试，未修改任何文件。
END OF REPORT