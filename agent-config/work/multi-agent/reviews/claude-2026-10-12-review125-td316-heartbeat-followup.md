VERDICT: safe to merge
A CASE THAT IS REPORTED WRONGLY OR BREAKS THE CONTRACT: not found
RULES THAT ONLY LACK A TEST: 1

（审查 125，是审查 120 的增量；对象 56b719b。本文件由统筹方按复核子代理交回的内容存盘——子代理的 Write 工具拒绝写报告文件，它没有绕过；这里存的是它自己给的「每条一行」的版本，全文在统筹线程的记录里，证据在 `~/agent-work/claude-review-120/delta-125/` 的 `base/`、`main/`、`mut-*/`、`logs/`、`mutate.js`。）

发现：
- P2-test：助手起不来（spawn 抛错或 error 事件）时不吃掉增长（thread-heartbeat.js:651、:656、:1164），这条没有测试；植入后整套照过，实测那样一拍都不发。它从 544af4d 就在，审查 120 时漏了没植入。最小修法：同一个预加载加一个让第一次 TRY spawn 抛错的计划，断言恰好一拍。
- P3：等待改回 100ms 后，上限 100ms 的同步等待整套照过，每次未答的查看停约 105ms；test.js:973 的 1000ms 这个界限是审查 120 按 2000ms 定的。
- P3：`progressExitDuringTryWait` 的 1000ms 余量偏小，负载约 10 时原版实测到过 812ms；放到 1500ms 仍抓得住植入 (c)。
- P3：`progressRealGiveupOneBeat` 的子进程活 6000ms，现在 1500ms 就够。

| 植入 | 改了什么 | 哪条测试失败 |
|---|---|---|
| (c) | 等助手改成同步，上限 2000ms | `progressExitDuringTryWait`（test.js:973，1989ms） |
| (d) | 取消时不杀助手 | `progressHeldLockFreedOnExit`（test.js:1021，turn_end 缺失） |
| (e) | 真实放弃报成锁忙 | `progressRealGiveupOneBeat`（test.js:1059） |
| (a) | 去掉回退 | `progressRealGiveupOneBeat`（test.js:1059） |
| (c100) 自选 | 同步等待，上限 100ms | none |
| (s) 自选 | 助手起不来也吃掉增长 | none |

1. 没找到报错或破坏契约的情形。
2. 审查 120 的三条 P2-test 都关了，(c)、(d)、(e) 各有点名的测试失败。
3. 丢拍仍然修好了，拍晚一个间隔加 100ms（实测 1116ms 对 1000ms 间隔）；连续未答会再晚，没有「最多一个间隔」的上限。子进程在间隔内退出时这一拍不发，可以接受。
4. 同线程 hook 等 1.7 秒的问题没了：本版最多 192ms（对照 93ms），main 上同一探针是 2054ms。
5. 删桩和删那三行没有改变行为，旧桩用例管的东西现在由真实路径的用例管。
6. 可以直接装在 main 的版本上。

测试运行：整套 7 次，一次一个；另有单包装进程探针 20 次，真实助手计时两轮各 200 次，没有加负载。复核方的探针出过一个错（把没起来的助手记成 pid 0，两次 kill(0) 杀掉了探针自己那条命令的进程组），只影响它自己的命令，已修。
END OF REPORT
