# Claude 一侧的独立复核 116 — 线程心跳第 3、4 轮（Codex 实现；`origin/main...9d2ae4b`，随后增量 `9d2ae4b..6fea8f5`）

2026-10-12 08:27 与 09:05 CDT · 复核方是统筹线程派出的 Claude 子代理（实现者是 Codex）· 第 3 轮：先修（下面是统筹方的摘录）。第 4 轮增量：可以合并，条件是 `BIFROST_HEARTBEAT_PROGRESS` 只给没有钩子上报的一家（现在是 Codex）设，直到平台一侧的守卫上线；剩两条低概率的路——全机共用的节流文件被别的线程的钩子无锁覆盖时会丢掉「工具声明的时限」（6 个钩子刻意同时触发 50 轮丢 6 次）；包装器开头注册失败且平台回得慢时这条记录一直没写。平台一侧的修法 8 行：当前是声明时限未过的 before_tool 时，`headless-progress` 的拍只推进序号、不覆盖。另有几条计时类测试的上限在高负载下会抖动（这些测试不在 CI 里跑）。

(Review 116, Claude side, 2026-10-12 08:27 — the coordinator's extract; the reviewer's files are in `review-116/`.)

VERDICT: fix first. The hook contract is intact and the hook path is byte-for-byte what it is on main (six traced
scenarios identical). One conditional misreport and three missing tests:

P1 (conditional) — thread-heartbeat.js:1152–1153. The progress beat is an `after_tool`. When the wrapped agent's
own hooks report on the same thread (Cursor does, Codex does not), the beat lands after a hook's `before_tool` that
declared a timeout. The platform replaces the thread's last event with the later one and honours a declared timeout
only while the last event is `before_tool`; so a tool that declared 30 minutes and is quiet for 11 is shown as
silent (the threshold falls from 32 to 10 minutes). Reproduction: `review-116/probes/clobber.js`. Smallest fix,
tried by the reviewer (the reproduction disappears, the whole test file still passes): after taking the lock and
before `stampBody`, read the throttle state; if the thread has a pending declared timeout that has not run out,
skip this beat — `review-116/fix/pending-tool.patch` (8 lines).

P3 — three planted violations that no test catches: (c) removing `alive = false` and `stopBeats()` after the child
exits (a beat's sequence number can then follow `turn_end` and reopen the turn); saving the issued key
synchronously on the progress path (`saveIssuedKey(body, res.key)` at :1018); a hook that additionally reads
`BIFROST_HEARTBEAT_PROGRESS` and stats the file. Ready-made probes for the first two:
`review-116/probes/probes.js` (`noBeatAfterExit`, `keySaveDoesNotBlock`); the third is "a hook with the PROGRESS
environment behaves exactly as on main".

P3 — the interval has no bounds (`BIFROST_HEARTBEAT_RUN_BEAT_MS=3000000000` overflows the timer and beats every
millisecond; `0.01` likewise): clamp to 1000 … 2^31-1. The progress file is read with a synchronous `stat`
(a hung network mount would block): make it asynchronous.

Installing: safe with older wrappers and hooks running (same lock and nonce protocol); needs Node 20.3+ for
`AbortSignal.any`.
