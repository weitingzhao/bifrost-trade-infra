# Codex 复核 111 — 线程心跳第 2 轮（`ccf1454..d047dbb`）

2026-10-12 00:39 CDT · 只读 · Cursor 实现 · 结论：先修。靠钩子的父进程判断旧会话是否已死不可靠（父进程可能是一闪而过的 shell）；同步的存活扫描没有受预算约束；进展心跳的恢复路径仍会同步等锁。之后统筹方决定把「结束旧会话」从脚本里拿掉、改到平台一侧做。

VERDICT: fix first
A CASE THAT IS REPORTED WRONGLY OR BREAKS THE HOOK CONTRACT: found
审查对象 d047dbb（ccf1454..d047dbb）；路径相对 bifrost-trade-infra；只写本目录，未连接真实平台、未读令牌文件。
110-1 P2：部分关闭 · agent-config/scripts/thread-heartbeat.js:1205、1320；可信 CLI 父进程下 A→B→A 不再互关，保留 shell 时仍误关（见新发现）。
110-2 P2：部分关闭 · agent-config/scripts/thread-heartbeat.js:1299、1320；侧栏/旧线程锁探针均止于共享 1000 ms 且 B 发出；同步存活扫描未受子预算约束。
110-3 P2：关闭 · agent-config/scripts/thread-heartbeat.js:1148、1370；包装 A→B 仅发两条 start(run-wrapper)，不读写接续状态。
110-4 P2：关闭 · agent-config/scripts/thread-heartbeat.js:1334、1340；Stop 不清记录；失败 Stop 后进程消失，B 再补 end(A)，补发失败留记录供 C 重试。
110-5 P2：部分关闭 · agent-config/scripts/thread-heartbeat.js:1107、1129；LOCK_NB 盖章不阻塞，但 postRecover 的恢复/保存响应仍可同步等锁。
110-6 P3：关闭 · agent-config/scripts/thread-heartbeat.js:1157；sha256 加固定 .state/.lock，T.lock 不再碰撞 T 的锁文件。
P2 · agent-config/scripts/thread-heartbeat.js:1320、1189：存活循环无期限检查；6 条每次 200 ms 已超 1 秒，30 条耗尽总期限。contract-probes.js 注入同等同步耗时，真实退出计时 6365 ms、stdout/stderr 空、code=0，但 NEW 未发送。最小修复：逐项核对剩余子预算、ps timeout 取剩余时间，未检查项留待下次。
P2 · agent-config/scripts/thread-heartbeat.js:1205：直接假定 ppid 是 CLI；持久父进程通过 /bin/sh -c 'node hook; :' 连续 A→B→A，记录的是三个短命 shell，实发 start(A),end(A),start(B),end(B),start(A)。最小修复：取得并验证稳定 CLI 祖先进程/代际；无法确认时跳过接续。单命令 sh 在本机 exec，无此错报；不能声称所有 shell 都会误判。
P2 · agent-config/scripts/thread-heartbeat.js:1129、976、985：进度 POST 的 409 恢复经 supersedeActive→withThreadLock 同步等待；假 post 返回 unknown key、另一个进程持锁 1400 ms，80 ms 模拟退出回调实到 1431 ms。最小修复：进度路径的恢复、key 保存、确认写回也用可取消的异步/非阻塞锁，退出后停止后续恢复。
存活边界 · agent-config/scripts/thread-heartbeat.js:1187、1216：ps 不可用/超时保守留活，首次不可读不建记录；不同启动文本的 pid 复用能识别。未固定 locale/TZ、lstart 仅秒精度，格式变化/同秒复用仍可能误判；格式差异注入已复现，真实 ps 被沙箱禁止，不能宣称实机验证通过。
子代理：同一 CLI 内子代理直接启动的 hook 可共用 CLI pid；独立 CLI 有自己的 pid；有 shell 时是 shell pid。SubagentStop 映射 after_tool，不接续；本轮没有运行真实 Claude 子代理，不能证明所有载荷/父进程关系。
期限/锁序：旧状态锁释放后才取旧线程锁，未新增嵌套锁顺序；旧锁和 POST 的 clip 路径正确，但扫描/响应恢复不能因外层退出 timer 就视为有界。
进度复核：真实忙锁退出通知 91 ms；截断、替换后缩小再增长通过；在途 POST 不等待，end seq 更大，停止后不重启 timer；迟到 beat 被服务器序号拒绝。恢复锁阻塞例外见上。
服务器：api/internal/agentthreads/recorder.go:105、threads.go:323、config.go:99；旧 seq 忽略，同 turn 更高 seq 重复 end 保持 Idle（会刷新 At），旧 turn 拒绝；删除 open 合理。
问题1：ps 未知时留活、下次重试正确，代码可接受；同步扫描期限仍须修复。
问题2：旧文件没有 pid/代际，不能猜测迁移后关闭；弃读可接受，但必须说明旧记录不能补关，安装覆盖从新记录起算。
问题3：当前 id 限制与线程 gate 的合法身份一致，代码可接受；哈希安全不等于下游支持任意 id，无需此次扩接口。
问题4：确认成功后删除、删除失败重复 end 正确，代码可接受；无需每次无条件重发，重复并非完全无写入。
问题5：100 ms 未拿到就跳过可接受，进度拍不值得延长等待；代码只对初次取锁达标，恢复路径仍须修复。
问题6：多个旧会话必须共用 1 秒，不能每个再给 1 秒；意图正确，代码因未限时 ps 循环不可接受。
问题7：同 session 的新 turn_start 已建立新回合，不必先给自己补 end；代码可接受，应补同 session 换进程的明确测试。
现有测试：原样 node --test 在副本运行，listen EPERM 127.0.0.1，完整套件未 PASS；语法检查及原有无网络核心用例通过。单独 processLiveness 实跑因 /bin/ps EPERM 失败，未冒充通过。
真实子进程防线 · agent-config/scripts/thread-heartbeat.test.js:1069：有 spawn→查存活→kill→等 exit→查死亡，未见常规调度竞态；但依赖 ps 能用及 pid 不立即复用，不能称绝对无偶发性，缺少 shell/多记录慢 ps/进度恢复锁用例。
探针/变异：移植 review-110/review-copy/probes.js 的相关复现至新 API（旧 takeOverSidebar/closeSidebar 已删）；三项自主植入：增长 >→>=、失败补关仍删记录、误关同 session，假发送断言均抓住；完整现有套件的变异检出未验证。
复现证据：NODE_USE_SYSTEM_CA=0 node review-copy/{probes,contract-probes,progress-probes,progress-recovery-probe}.js（逐个执行）；日志为 probes.log、contract-probes.log、progress-probes.log、progress-recovery-probe.log、baseline.log、nonnetwork*.log。
安装：线程 flock/nonce 协议兼容，旧 wrappers/senders 与新版本同锁，重复 Stop 无 open 兼容障碍；旧原始状态不被迁移，补关覆盖不完整；本版另有上述阻塞/误关，当前不应安装，修复后可混跑但须注明旧记录覆盖缺口。
END OF REPORT
