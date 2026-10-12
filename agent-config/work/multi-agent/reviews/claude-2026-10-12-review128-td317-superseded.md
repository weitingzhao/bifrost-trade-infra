VERDICT: fix first
A SEQUENCE FOR (a)–(f): found
RULES THAT ONLY LACK A TEST: 1

（审查 128：平台 origin/main..f8d5235，客户端 origin/main...affaab3。本文件由统筹方按复核子代理交回的「每条一行」版本存盘——子代理的 Write 工具拒绝写报告文件，它没有绕过；全文在统筹线程的记录里，证据在 `~/agent-work/claude-review-128/`。）

- P1（f）：已正常结束回合的会话在 10 分钟后从 idle 变成 superseded，`in_turn_seconds` 从 0 变成非 0，并出现在 Status 的 In progress 列表和计数里；`view.go:22` 加一个 `t.Event == TurnEnd` 即可，加上后现有测试全过。(a)–(e) 没有找到。
- P2（规则盲区）：线程 shell 里起的没走包装的带钩子 CLI 继承了变量，会取代父会话；父会话卡死后这条线程没有任何 Owner 项，改动前会推送。走包装的运行不受影响。
- P2（客户端）：变量值原样发送，格式一旦不符合平台 id 规则，整条心跳被拒，线程从监控消失；现在的值符合。
- P2-test：mark 路径的状态复核没有测试。
- P3：键名大小写不同的显式空 sidebar 被当作缺席接受。
- P3：四个边界（同一时刻、恰好阈值、指标标签、空白变量）没有测试。
- P3：waiting_owner 也会变 superseded；取代者被容量淘汰后旧会话回到 silent；Console 里有一处第一版留下的匹配。
- 未测量：钩子进程里是否真有 `CLAUDE_CODE_HOST_SESSION_ID`，要靠一次真实重启验收。

植入：规则各有点名测试失败（quiet、runother、opening、anyevent、nosidebar、runself、vendor、due、claim、hostmsg、validate、listed、Console 六条、客户端 s 与 b1–b4）；没有测试失败的是 mark 和自选的 idle、sameinstant、atthreshold、gauge、b5。
其余各点：先后接替的会话都静默时只剩最新的一个 silent、推送一次；被取代后再发事件立刻回到 in_turn；带侧栏 id 的 run- 不取代也不被取代；claim 在事务里复核，不会饿死；新旧版本往返只在回滚时丢两个字段；Console 对 superseded 和未知状态都有点名测试；变量缺席时请求体逐字节相同。
测试运行：Go 包 22 次，Console 四个文件 7 次，客户端整套 7 次，一次一个；另有 7 次客户端抓包探针。

统筹方的后续（2026-10-12）：P1 已按上面的最小修法改，并加了「已结束的会话保持 idle」的测试；P2（规则盲区）裁定为只有同一厂商的会话才算接替（别的厂商带着同一个侧栏 id 的只可能是从线程 shell 起的活），并写明「从线程 shell 起带钩子的 CLI 一律走包装」；P2（客户端）改成不合规的值不带；P2-test 补了测试。四处各种回去确认被拦住。P3 只记不修。改动交 Codex 做只读确认（复核 129）。
END OF REPORT
