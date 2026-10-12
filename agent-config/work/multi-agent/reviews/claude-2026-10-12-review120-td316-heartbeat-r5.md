VERDICT: safe to merge
A CASE THAT IS REPORTED WRONGLY OR BREAKS THE CONTRACT: not found
RULES THAT ONLY LACK A TEST: 3

（本文件由统筹方按复核子代理交回的全文存盘：子代理的 Write 工具拒绝写报告类 .md，它没有绕过。证据在 `~/agent-work/claude-review-120/` 的 `base/`、`mut-*/`、`inst/`、`probes/`、`logs/`、`mutate.js`。）

审查 120 · 对象 544af4d（6fea8f5..544af4d）· 路径相对 agent-config/scripts/ · 只在 claude-review-120/ 里跑和改。工作树未动（HEAD 仍是 544af4d，git status 为空）。没连真实平台，没读令牌文件。

唯一问题的回答：none found。

P2-test-1 · thread-heartbeat.js:676–699 等助手回音必须是异步的。植入 (c) 改成同步等待，整套测试通过。探针 S8（助手不答，子进程在等待 500ms 后退出）：原版 turn_end 在退出后 47ms；植入后事件循环停 2007ms，turn_end 晚 1529ms。现有用例里助手都是立刻回答。
P2-test-2 · thread-heartbeat.js:706–713、1138–1146 子进程退出时取消并杀掉助手。植入 (d)，整套通过。给 cancel() 加日志跑整套：调用 0 次（对照：两个探针各记到 1 次）。探针 S4（助手已拿到 flock 但没答，子进程退出）：原版 turn_end 48–84ms；植入后 turn_end 没发出（等 2018ms 后锁超时）。
P2-test-3 · thread-heartbeat.js:674、1181 真实放弃不吃掉增长。新用例（test.js:897）用的是 :619–631 的桩，在助手启动前就返回。植入 (e) 把真实放弃标成 lock-busy，整套通过；探针 S2：原版放弃后下一次查看发一拍，植入后一拍都不发，也就是本次修的缺陷回来了。
三条的最小修法是同一个：测试用 NODE_OPTIONS=--require 预加载包住 child_process.spawn 让 TRY 助手变慢（probes/slowperl.js 可直接用，hookIgnoresProgress 已有同样做法），加三个用例：助手不答且子进程在等待中退出 → turn_end 在退出后 1000ms 内；助手持锁未答且子进程退出 → turn_end 发出；第一次不答第二次正常 → 恰好一拍。之后 :619–631 的桩可以删。
P3 · :674 助手已拿到 flock、包装进程还没看到回答的最长时间从 100ms 变成 2000ms。探针 S6（人为在 flock 和写回答之间加延迟）里同线程的 hook：本版等 1669ms，6fea8f5 等 128ms；两版都是退出码 0、无输出、在 5 秒期限内。没有自然复现。只留重试、等待保持 100ms 也能修掉丢拍，那一拍会晚一个间隔。
P3 · :638、:653、:709–711 的 acquired 走不到：finish(held) 之后调用方在同一个微任务里同步放锁并清掉引用，cancel() 只会碰到未结算的尝试。去掉这三行（植入 k）S4 行为相同。无害。
P3 · test.js:972–973 新界限比旧的少抓两类：子进程退出之前的慢（别的用例有 4000ms 总上限），以及退出后约 1.4–1.7 秒的有上限等待。该用例仍要求助手在约 380ms 内回答，否则 after_tool 不出现而失败（旧版是 100ms）。

| 植入 | 改了什么 | 哪条测试失败 |
|---|---|---|
| (a) | 去掉 :1182 的回退，放弃吃掉增长 | progressGiveupRetriesGrowth，test.js:902，少了 after_tool |
| (b) | stop() 不中止，run 等在途进度 POST | progressEdges，test.js:973，「2659ms after the child exited」 |
| (c) | 等助手改成同步循环，上限仍 2000ms | none |
| (d) | cancel() 只结算，不杀助手 | none |
| (e) 自选 | 真实放弃计时器报 lock-busy | none |
| (g) 自选 | 锁忙也不吃掉增长 | progressEdges，test.js:1086 |
| (h) 自选 | 盖章成功后也回退 | progressBeats，test.js:808，12 个 after_tool，期望 3 个 |
| inst | 原版加 cancel() 日志 | 通过；cancel() 调用 0 次 |

1. 是异步。5ms 的 unref 定时器轮询；有对照的 6 次探针在 1500–2000ms 等待中包装进程没有超过 60ms 的停顿（第一次 S1 无对照，有 4 次 107–314ms，其中 3 次发生在没有尝试在途时）。子进程退出即取消并杀助手，turn_end 在退出后 28–171ms。等待期间不会有第二次查看：定时器要等这次尝试结算才重新上（:1184、:1203、:1211）；S2、S3 里 2 号助手在 1 号被杀 1000ms 后才启动。
2. 没找到。没拿到锁的结束都杀助手（:655），拿到锁的由调用方同步放（:1183、:1200、:1017）。S3、S4、S5 结束后锁空闲、无存活助手。S7（等待中 SIGKILL 包装进程）：助手启动完后因 stdin 关闭自己退出，每 300ms 采样锁一直空闲。
3. 不会重复：回退只在没拿到锁时发生，那时既没盖章也没 POST；S2、S5 真实放弃后恰好一拍，植入 (h) 说明重复拍有测试抓。退出后不发：回退和重新上定时器都要求 !stopped && isAlive()；S3、S8 退出后无拍。
4. 会失败：植入 (b) 实测 2659ms，超过 1800。按构造下限是 3000 − 500 = 2500ms。不再抓的见上面第三条 P3。
5. 会：植入 (a) 失败，事件是 turn_start, turn_end。它只验证了调用方，没验证真实放弃（P2-test-3）。
6. 安全。LOCK_HELPER、holdFlock、releaseHelper、saveGate、hook()、main()、sendDetached、节流函数与 main 分支点 d0694c3 逐字相同，stampBody 是原样提取。本提交只动 beginTryHold 和 startProgressBeats，只有 run 走得到。新环境变量要 NODE_ENV=test 才读。

测试运行：整套 9 次（原版 1，植入 a b c d e g h 各 1，带日志的原版 1），一次一个。另有单包装进程探针 22 次。期间负载 5.8–7.9。
END OF REPORT
