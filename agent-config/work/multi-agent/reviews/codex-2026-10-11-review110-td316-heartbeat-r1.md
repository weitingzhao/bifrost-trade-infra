# Codex 复核 110 — 线程心跳：后台运行报进展、同线程换会话时结束旧会话（TD-316、TD-317；infra 分支 `w31/td-316-317` `ccf1454`）

2026-10-11 23:56 CDT · 只读 · Cursor 实现 · 结论：先修。主要一处是任务书的规格错：同一个侧栏线程里两个会话都活着时会互相报结束。

VERDICT: fix first
A CASE THAT IS REPORTED WRONGLY OR BREAKS THE HOOK CONTRACT: found
审查对象：ccf1454；以下路径均相对 bifrost-trade-infra，未修改原工作树、连接真实平台或读取真实令牌。
P2 · agent-config/scripts/thread-heartbeat.js:1039–1042：同侧栏不同 session 无条件互相关闭；A、B 都活着时依次提交 A→B→A，实测补发 end(A)、end(B)，把仍运行的会话报为结束。最小修复：记录可验证的进程代际/存活信息，排除子代理与并行会话，仅对确认被替换的主会话接续；仅凭侧栏 id 和 session id 无法区分重启。
P2 · agent-config/scripts/thread-heartbeat.js:1007、1072、1123：侧栏锁或旧会话线程锁可消耗整个 hookDeadline；模拟任一锁占满 5 秒，B 的 allocateStamp 已无预算，turn_start 被丢弃。最小修复：两种旧状态操作共用较短子预算，为 B 盖章和发送保留时间；1113 行的网络预留判断不能限制同步锁等待。
P2 · agent-config/scripts/thread-heartbeat.js:1102、1058：状态记录 CLI id，但原 heartbeat 身份可能被 BIFROST_HEARTBEAT_THREAD 覆盖；设该变量为 R，A→B 实测 start(R)、end(A)、start(R)，关闭了未登记的 A，未按原线程 key/sequence 结束 R。最小修复：包装运行跳过接续，或记录并使用原事件的有效 session 身份。
P2 · agent-config/scripts/thread-heartbeat.js:1127–1141：Stop 在 detached POST 前写 closed；模拟 A 的 Stop 发送失败，B 不再尝试结束服务器上仍 open 的 A。最小修复：成功发送后才标 closed，并带 session/turn 代际检查，避免迟到成功覆盖下一回合。
P2 · agent-config/scripts/thread-heartbeat.js:975：进度定时器同步 allocateStamp/holdFlock 可阻塞事件循环至 2 秒；进度线程锁被占用、child 在等待中退出，exit 回调与 turn_end 被延迟。最小修复：进度盖章异步等待或无锁可用即跳过，结束时取消等待；这是代码路径推导，未做真实进程时序测量。
协议检查：原有线程锁实现、nonce/注册格式、事件映射未改；无侧栏 id 的 hook 路径保持原行为。新侧栏锁在取得线程锁前已释放，无嵌套反向锁死；会耗尽共享期限。新增异常被吞，未发现 stdout 或非零 hook 退出码的新路径。
P3 · agent-config/scripts/thread-heartbeat.js:1001、1007、1027：id 检查挡住路径穿越，但合法 id T.lock 的状态文件与 T 的锁文件同名；写前者会 rename 覆盖后者 inode，破坏 T 的互斥。最小修复：哈希 id 并为状态与锁使用固定不同后缀。缺失、损坏、不可写状态的普通异常会回落到新事件；锁超时例外见上。
进度检查：只在 size 增长时发；观测到下降会更新基线，随后增长可发。未观测到的截断/替换仍仅按大小判断，符合此接口。一次仅一个进度 POST；exit 清 timer、finally 不再 rearm，子进程退出码保留。
顺序检查：已分配的进度 seq 小于随后 end seq，两个 POST 可同时在途、到达顺序不保证；服务器 bifrost-platform/api/internal/agentthreads/recorder.go:105 忽略旧 seq，迟到旧 beat 不应重开回合。process.exit 可截断未完成的进度 POST。
现有测试：在 review-copy 原样执行 node --test；先遇 NODE_USE_SYSTEM_CA=1 的 SecItemCopyMatching，设为 0 后遇 listen EPERM 127.0.0.1。完整套件无法在此沙箱通过，不能宣称回归 PASS；语法检查通过。
原有无网络用例 mapping/timeouts/throttle/lateResponseDoesNotTouchTheCurrentRecord/lockPreparationConsumesTheBudget 在提取副本通过（nonnetwork.log）。diff 保留所有原用例及 main 调用，新增 A/B 用例覆盖 TASK 所列的基本场景。
缺少防线：并行/子代理、侧栏/旧线程锁占满预算、不可写侧栏、慢旧 POST/注册恢复、包装身份、失败 Stop、截断/替换、正在发送时 child 退出与进度锁阻塞；现有 signal/快退出测试把间隔设为 10 秒，未覆盖已有在途进度。
变异验证：副本植入增长 > 改 >=、忽略 open 标志、旧 end 改用新 session 三项；无网络函数级断言均抓住（probes.log）。原样基线同断言通过；现有集成断言也针对这三规则，但受监听限制，未实跑其变异结果。
复现：NODE_USE_SYSTEM_CA=0 node review-copy/probes.js；使用本地 VM、假发送函数和可控锁时钟，无网络服务器。输出包含 A/B/A 错报、两种预算耗尽、包装身份错关、失败 Stop、截断增长和三项变异结果。
问题 5：线程锁/nonce 层面兼容旧版本；功能层面不宜热替换，旧 Stop 不维护侧栏 open，新版本会再次关闭已结束回合。应等旧 wrappers/hooks/senders 全部退出后安装；无需为本提交迁移锁格式。
END OF REPORT
