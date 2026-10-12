VERDICT: safe to merge
A SEQUENCE FOR (a)–(d): found
RULES THAT ONLY LACK A TEST: 2

（审查 126：平台 origin/main..cf06d88，客户端 56b719b..a8486c6。本文件由统筹方按复核子代理交回的「每条一行」版本存盘——子代理的 Write 工具拒绝写报告文件，它没有绕过；全文在统筹线程的记录里，证据在 `~/agent-work/claude-review-126/`。）

找到的两条序列都不是这两处改动里的代码缺陷；新包装进程、新钩子、新平台都就位后的正常组合下没有找到。合并就是安装，条件是当时没有包装运行在跑。

- P2（安装顺序）：旧脚本启动的包装进程没有导出标记；换上新脚本后，它里面的钩子按自己的会话 id 上报，该代理一静默或被杀，Owner 会收到一条「stopped 11m ago」的推送。不改代码：合并前确认没有 `thread-heartbeat.js run` 进程。
- P3（残留，改动前后相同）：不是包装运行、却继承了两个变量的会话，仍被当成包装运行而对 Owner 隐藏。要收紧，可让标记带包装进程的 pid 并核对它还活着。
- P2-test-1：包装进程交给子进程的 id 若没加前缀，里面的钩子会报成普通线程，没有测试抓。修法：测试从不带前缀的 id 起。
- P2-test-2：主机消息的测试用的是没标题的运行，真实运行都有标题；只过滤无标题的错误实现能通过测试。修法：夹具里的运行加标题并断言标题不出现。
- P3：125–128 个字符的包装 id 加前缀后超长，平台拒收（默认 id 只有 40 个字符）；只含空白的覆盖值现在按会话 id 上报，是改善。
- P3：前缀写在五处；平台把前缀放宽成 `run` 没有测试抓，没有实际受害者；脚本头部注释没写新变量和保留的命名空间。

| 植入 | 改了什么 | 哪条测试失败 |
|---|---|---|
| k1 | 普通钩子重新接受 `run-` 覆盖 | `ordinaryHookCannotUseRunNamespace` |
| k2 | 包装进程不加前缀 | `wrappedRunPrefixesOverride` |
| k3 | 不导出标记 | `hookInsideWrappedRunKeepsRunID` |
| host | 主机消息不过滤 | `TestHostLostMessageOmitsWrappedRuns` |
| anchor | 进度拍挪动超时起点 | `TestReview124GuardBoundaries` |
| due | 静默的包装运行重新进推送 | `TestSilentHeadlessRunIsNotAnOwnerItem` |
| console | Console 不过滤 | NeedsYouPage 的新用例 |
| k6 自选 | 钩子无论有没有标记都不认 `run-` | `mapping` |
| hostalert 自选 | 只带包装运行的主机不发告警 | `TestHostLostMessageOmitsWrappedRuns/runs-only` |
| k4 自选 | 子进程拿到没加前缀的 id | none |
| title 自选 | 主机消息只过滤没标题的运行 | none |
| loose 自选 | 平台把前缀放宽成 `run` | none |

复核 124 的 P1、P2、P2-test 都已关闭。统筹方改过的那条测试（等三个 post、按序号排序）可靠，没有掩盖问题。
测试运行：客户端整套 6 次，Go 包 9 次，Console 单文件 2 次，一次一个；另有 18 次顺序探针。

统筹方的后续（2026-10-12）：P2-test-1、P2-test-2 已各补一处测试（infra 与 platform 分支上各一次只改测试的提交），并各种回 k4、title 确认被拦住。
END OF REPORT
