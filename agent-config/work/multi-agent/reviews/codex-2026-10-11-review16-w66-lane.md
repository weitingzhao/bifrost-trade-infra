VERDICT: fix first

- **P1：失败或崩溃仍可通过。** `outcome_after_exit` 只在 implement 检查退出码；verify 输出 `pass` 后退出 7 仍进入审查，review 写出首行后退出 9 仍进入 `passed`。已用内存调用复现。应同时要求成功退出和完整有效报告。证据：[lane.py:351–374](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:351)。

- **P1：没有同轮、同提交及报告来源约束。** verdict 只记录 round，没有 SHA；review 分支也不检查本轮 verify 是否通过。日志以追加模式打开，报告未清理、未验证生成时间，默认验收还读取共享的 `workspace/verify.txt`。旧文件或实现者预写的 verdict 可以被接受。应绑定 round、提交和独立受保护的产物。证据：[lane.py:271](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:271)、[316–369](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:316)、[lane-config.json:3](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane-config.json:3)。

- **P1：同一 lane 没有互斥锁。** 两个 `run` 可同时读取旧状态并启动同一步，混写同一日志和报告；固定的 `lane.json.tmp` 也会发生竞争，rename 不能保证并发更新正确。应在读取、执行和状态提交全程持有 lane 锁。证据：[lane.py:51–64](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:51)、[454–460](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:454)。

- **P1：预算授权可自签。** `extend` 仅检查 `--by/--reason` 非空，实现步骤可调用它并冒充 Owner，每次耗尽后继续延长；`run` 自身不验证预算或扩展记录，直接修改 JSON 也能绕过。who/why/when 虽有记录，却没有可信授权边界。证据：[lane.py:387–396](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:387)、[486–501](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:486)。

- **P1：路径能注入 shell 命令。** 模板直接替换后交给 `sh -c`；默认双引号不能阻止路径中的 `$()`、反引号或引号闭合。workspace、brief、report 路径均受影响。id 有字符限制，title 未进入命令。应使用 argv 参数传递。证据：[lane.py:99–103](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:99)、[319–326](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:319)、[lane-config.json:2–4](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane-config.json:2)。

- **P2：崩溃恢复不能可靠接续。** 子进程先启动再保存 PID，窗口内崩溃会留下未登记进程，重跑再次启动；已有 PID 的恢复只检查存活，不读取完成记录，成功结束也被判 vanished。PID 复用则可能等待无关进程。证据：[lane.py:165–174](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:165)、[325–347](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:325)、[398–405](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:398)。

- **P2：stall/abandon 留下继续运行的实现者。** 无日志更新便进入 stalled，但进程继续运行；stalled 不允许 `run` 接续，abandon 也只改状态。文件显示停止或失败时，代码仍可能被修改。证据：[lane.py:199–200](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:199)、[387–402](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:387)、[506–515](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:506)。

- **P2：queue 会隐藏最需要人工处理的 lane。** 只收录 ready/changes_requested，并始终标记 `needs_owner=false`；over_budget 和 stalled 完全消失。status 也只回显磁盘状态，不核对进程，崩溃后可长期显示运行中。证据：[lane.py:538–548](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:538)、[610–620](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:610)。

- **P2：verdict 解析既可误收也可误拒。** verify 会接受代码块内引用的独立 `VERDICT: pass`；review 遇到 BOM 或首行空白则拒绝有效报告。三种情况均已内存复现。应使用带明确字段和完成标记的结构化结果。证据：[lane.py:220–226](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:220)、[365–374](~/agent-work/w66-lane/bifrost-trade-infra/agent-config/scripts/lane/lane.py:365)。