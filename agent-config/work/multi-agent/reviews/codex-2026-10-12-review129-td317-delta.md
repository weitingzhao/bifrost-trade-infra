VERDICT: safe to merge
发现：本次两个末提交（platform fb1bd6f；client a9fe6c6）未发现 P1/P2/P3；无需修复。
1. 无新增误隐藏或误 superseded 序列：api/internal/agentthreads/view.go:24、28 仅收窄判定；已结束者保持 idle，最新静默者及无 sidebar 者仍可成为 Owner 项。
2. 裁决 2 在现有接线下成立；未找到同一桌面线程的真实跨 vendor 后继场景。vendor 标识宿主客户端，切换模型不改变 vendor；继承 sidebar 的另厂商命令是独立作业。
3. 是：agent-config/scripts/thread-heartbeat.js:218 与 api/internal/agentthreads/threads.go:284 均为 ^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$；无效值省略 sidebar。
4. 是，逐项实植于副本：删除 TurnEnd 排除、vendor 限制、mark 状态复核、客户端校验，分别使 TestEndedSessionStaysIdle、TestSidebarAcrossVendorsDoesNotSupersede、TestMarkRechecksCurrentState、原 sidebarFieldFollowsEnvironment 的离线断言失败（退出码均为 1）。
验证：恢复副本后 11 个定向 Go 测试及客户端离线断言通过；整包 Go 测试受本地监听权限限制，未完成；未运行需联网的客户端测试部分。
END OF REPORT
