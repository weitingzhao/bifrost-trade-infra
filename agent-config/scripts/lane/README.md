# lane.py

`lane.py` 把一条派工链（实现 → 验收 → 复核）收成文件里的状态机。每个 lane 一个目录（默认 `~/agent-work/lanes/<id>/`，测试和调用用 `--root`）。`lane.json` 用带 pid 和随机后缀的临时文件再 rename 改写。每一次状态变化追加到 `events.jsonl`。

状态：`ready → implementing → verifying → reviewing → passed | changes_requested | over_budget | failed`。没有 `stalled`。某一步的 stdout 在 `--stall-seconds` 内没有变长时，司机继续等，并在该步记下 `stalled_since`（输出恢复就清掉）。`status`、`queue` 和 `board` 显示 `no output for N min`。除此之外什么都不改，直到有人 `stop`。

一步只在启动它的司机还活着时运行。`run` 启动、等待、下结论，不会接上早先某次 `run` 留下的子进程。`run` 若看到记为 `starting` 或 `running` 的一步，而锁在自己手里（没有活着的司机）：结束那个进程组，该步和 lane 都记为 `failed`（`the driver died during <step>`）。再跑是显式的 `lane.py retry <id> --by <who> --reason <why>`：同一轮里新开一次失败步骤的尝试，不消耗轮次。验收写出 FAIL、或复核是 `fix first` 时拒绝 retry，这两条走 `next-round`。

`stop` 和 `abandon` 在司机持有锁时不抢锁。它们原子写入 `<lane>/stop-request.json`（`what` 为 `stop` 或 `abandon`，加上 `by`、`reason`、`at`），最多等 15 秒。司机每次轮询（间隔不超过 1 秒）看到文件就结束进程组，记下是谁、为什么，并把 lane 设为 `failed`（`stopped by <who>`）或放弃。没有司机时它们自己拿锁直接做。两者在环境变量 `LANE_STEP` 已设置时仍然拒绝。`retry` 看到 `LANE_STEP` 也拒绝。

结束进程组：对整组发 TERM，用 `os.killpg(pgid, 0)` 轮询到 `ProcessLookupError` 或满 5 秒，再 KILL，再轮询 5 秒。步骤和事件记下 `reaped`（true 或 false）。为 false 时 `status` 和 `queue` 显示 `processes may still be running: pgid <n>`。组长已经死了也要这样做。

子进程经 `lane_runner.py <started.json> -- <argv…>` 启动。runner 先原子写入 `started.json`（`pid`、`pgid`、`started_at`；它是会话首进程，所以 pgid 等于 pid），再 `os.execvp` 变成那条命令本身。退出码是 `proc.wait()` 的返回值，不从文件里读。`done` 由 lane.py 在子进程结束之后写，只给看板用。5 秒内没有 `started.json` 就结束已经启动的进程，该步失败（`the step did not register`）。stdout 和 stderr 分开写在该次尝试目录的 `stdout.log` 和 `stderr.log`。验收结论只认 `stdout.log` 最后一条非空行。看板的 `progress` 是 `stdout.log`。

验收前、验收后、复核前、复核后，工作区和每个直接子工作树都要同时满足：`HEAD` 等于记下的那个，并且 `git status --porcelain`（包含未跟踪文件，不包含被忽略的文件）为空。否则失败，文案是 `uncommitted or untracked files in <repo> before verify` 或 `the work tree of <repo> changed during <step>`。`passed` 记下这些 head。

会改 lane 的命令在读 `lane.json` 之前独占 `<lane>/lock`。`stop` 和 `abandon` 在司机已经持锁时改走请求文件。第二个司机退出码 3。只读命令（`status`、`queue`、`board`）不持有锁；它们只探一下锁来分辨有没有司机。锁是空的、但状态仍说某步在跑时，`queue` 写 `the driver died during <step>: run lane.py run <id> to close it, then retry`，`status` 显示 `running (no driver)`，`status --check` 退出码 1。有活司机、并且输出还在增长的 lane 算忙，不进队列。状态是 `implementing` 但没有正在跑的步骤、也没有司机时，不算忙。

命令模板在 `lane-config.json` 里，是字符串数组（argv），不是交给 shell 的一行字。占位符只替换某一个元素内部。以 `~/` 开头的元素由 lane.py 展开成家目录。

轮次上限是 `max_rounds` 加上已经记下的 extension 次数。`run` 在启动实现步骤前自己再查一次。`extend --by` 只接受 `coordinator`（整条 lane 只有一次）和 `owner`（必须是终端，并且把 lane id 再打一遍）。子进程环境里有 `LANE_STEP=<id>/<step>`。

What this does NOT protect against: a process running as the same Unix user can still edit the lane directory. It stops accidents and a coordinator quietly extending; the real boundary needs the agents to run as another user or in a sandbox (ADR §12).
