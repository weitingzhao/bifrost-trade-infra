VERDICT: fix first
A FALSE STATEMENT OR A CHANGED COMMAND: found
RULES THAT ONLY LACK A TEST: 3

（复核 130 · Claude 子代理 · 提交 b370002。本文件由统筹方按复核方交回的内容存盘——子代理的 Write 工具拒绝写报告文件，它没有绕过；证据在 `~/agent-work/claude-review-130/`。）

它在自己的副本和事件根上从命令行实测：约 38 次 run、45 次 fold、11 次 observe、约 25 次记账。
- 折叠文档说错的：没找到（退出码、信号、Owner 事项开合、since 都对）。
- `run` 改变被包命令的行为：找到 3 条可复现的命令序列。
- P1-1 runtime.py：继承来的「忽略」被盖掉——`nohup` 起的包装器收到 HUP 时子进程被杀。修法：继承的处置是 SIG_IGN 时不装处理函数。
- P1-2 runtime.py：记账出错（写不出的名字、坏的工作 id、锁忙）时子进程没起，违反「每种情况都起」。修法：`except Exception`，`_work_dir` 挪进 try。
- P2-1：子进程的输出进了运行目录下两个文件，包装器什么都不说。修法：起子进程前在 stderr 写一行步骤 id 和输出目录。
- P2-2 3 号以上描述符被关；P2-3 只转发 TERM / INT / HUP；P2-4 对包装器 kill -9 或组杀后子进程成了没人记的孤儿（使用规矩：只对包装器发 TERM）；P2-5 一次心跳写失败就不再记账。
- P2-test：INT / HUP 的转发、观察的 record 分支与截断、绑定记录的 since，缺测试。
- P3 若干（运行目录被删、观察遇锁忙的回溯、STATUS.md 过时等）。
七条规则：1、2、4、5、6、7 met；3 partly。复核 113 的三处答错都修好了（重跑了它的复现脚本）。三份夹具只多了报告里说的字段。没有任何东西读它的输出做决定。
使用规矩：fold 之前先 observe；停被包的任务只对包装器发 TERM。

统筹方的后续（2026-10-12）：「先修」的三条（P1-1、P1-2、P2-1）已修，各带一条测试，其中两条把错种回去确认被拦；`STATUS.md` 改成现状。其余按复核的意见留待以后。提交 84f4139。
END OF REPORT
