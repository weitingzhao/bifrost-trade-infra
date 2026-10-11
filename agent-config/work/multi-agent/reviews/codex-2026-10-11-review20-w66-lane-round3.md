VERDICT: fix first

审查提交：`a28c826`。**仍有 P1，不应合并；按 brief 应停止合并并重新考虑设计。**
以下路径均相对 `agent-config/scripts/lane/`。

发现：

- **P1：`stop → retry` 绕过复核结论和轮次限制。** `fix first` 后执行 `stop`，`apply_request` 把 `changes_requested` 改为 `failed`；`retry_block` 对 review 不检查既有结论，允许同一轮再次复核，直到获得通过，无需 `next-round` 或 extension。依据：`lane_steps.py:430、460、703、713`，`lane.py:225`。应保留并强制检查本轮已有的否决结论。
- **P1：恢复可能误杀复用 PGID 的无关任务。** `pgid_of` 无条件信任旧 `started.json`，不核对记录身份或进程启动时间；原进程组早已退出、编号被其他任务复用后，恢复仍向该编号发送 TERM/KILL。新建 attempt 目录不能解决延迟恢复时的编号复用。依据：`lane_steps.py:347、354、695、98`。回收前必须证明当前进程组属于该次尝试。
- **P1：未跟踪文件检查受 Git 配置影响。** `status --porcelain` 未显式指定 `--untracked-files`；配置 `status.showUntrackedFiles=no` 时，未跟踪源码不会出现，四处内容检查均可能放行并最终 `passed`。依据：`lane_steps.py:212、239、464、532`。应显式启用未跟踪文件检查。
- **P2：启动崩溃窗口仍存在。** Popen 成功后、PID 持久化及 runner 注册前若司机死亡，恢复找不到 PGID，直接记 `reaped=true` 并结束该步；延迟注册的 runner 随后仍能执行命令。依据：`lane_steps.py:624、639、697`，`lane_runner.py:55、58`。需让启动握手与恢复协调，阻止已关闭尝试继续 exec。
- **P2：验收 FAIL 无法进入下一轮。** exit 0 加 FAIL 被判为 `failed`，retry 要求走 `next-round`，但后者仅接受 `changes_requested`；`run` 也直接返回。依据：`lane_steps.py:499、728、734`，`lane.py:127`。应让有效 FAIL 进入可推进下一轮的状态。
- **P2：正常退出留下的组员无法再被停止。** 组长退出后直接判定并关闭步骤，没有检查或结束残留进程组；后续 `stop/abandon` 只处理开放步骤，先前的后台子进程会被漏掉。依据：`lane_steps.py:681、691、423、435`。正常完成也需处理该尝试的剩余组员。

Review 17 逐项确认：

- P1 `done` 覆盖真实退出码：**closed**；`lane_steps.py:681、691、548`，只使用 `proc.wait()` 返回值。
- P1 相同 HEAD 不代表相同内容：**not closed**；`lane_steps.py:212`，未跟踪文件仍可被配置隐藏。
- P2 驱动期间不能 stop/abandon：**closed**；`lane.py:179、188`，`lane_steps.py:675、677`，已加入请求轮询。
- P2 只确认组长死亡：**closed**；`lane_steps.py:64、74、86`，终止路径检查整个进程组。
- P2 启动崩溃窗口：**not closed**；`lane_steps.py:624、639、697`。
- P2 queue 隐藏司机死亡的 lane：**closed**；`lane.py:404`，`lane.py:293`。
- P2 verify 结论未限定 stdout：**closed**；`lane_steps.py:523、533`，`lane_steps.py:626、627`。

验证：完成静态审查，并用纯内存 mock 确认 stop/retry 绕过、FAIL 状态死路、旧注册记录优先和无 PID 恢复误报已回收；未运行会写文件的测试套件，未修改文件或调用平台/集群。

END OF REPORT