# lane.py

`lane.py` 把一条派工链（实现 → 验收 → 复核）收成文件里的状态机。每个 lane 一个目录（默认 `~/agent-work/lanes/<id>/`，测试和调用用 `--root`）。`lane.json` 用带 pid 和随机后缀的临时文件再 rename 改写。每一次状态变化追加到 `events.jsonl`。

会改 lane 的命令（`run`、`next-round`、`extend`、`abandon`、`stop`）在读 `lane.json` 之前独占 `<lane>/lock`，写完才放开。第二个进程退出码 3，不改任何文件。只读命令（`status`、`queue`、`board`）不加锁。

命令模板在 `lane-config.json` 里，是字符串数组（argv），不是交给 shell 的一行字。占位符只替换某一个元素内部。以 `~/` 开头的元素由 lane.py 展开成家目录。

子进程经 `lane_runner.py` 启动。runner 在命令结束时把 `{"exit", "ended_at"}` 原子写入该次尝试目录的 `done`，所以 lane.py 中途消失，退出码还在。每次尝试用新目录 `round-<n>/<step>-<k>/`（`log`、`done`、`report`），不追加、不复用。

轮次上限是 `max_rounds` 加上已经记下的 extension 次数。`run` 在启动实现步骤前自己再查一次。`extend --by` 只接受 `coordinator`（整条 lane 只有一次）和 `owner`（必须是终端，并且把 lane id 再打一遍）。子进程环境里有 `LANE_STEP=<id>/<step>`；`extend`、`next-round`、`abandon` 看到这个变量就拒绝。

What this does NOT protect against: a process running as the same Unix user can still edit the lane directory. It stops accidents and a coordinator quietly extending; the real boundary needs the agents to run as another user or in a sandbox (ADR §12).
