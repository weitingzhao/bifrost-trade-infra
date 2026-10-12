VERDICT: fix first
A SEQUENCE FOR (a)–(d): found
RULES THAT ONLY LACK A TEST: 1
P1 — api/internal/agentthreads/config.go:163、console/src/api/agentThreads.ts:158：普通 CLI hook 可由 BIFROST_HEARTBEAT_THREAD=run-owner 指定合法 id（scripts/thread-heartbeat.js:224；threads.go:253）；turn_start(T,1)，随后静默 10 分钟加 1 秒且主机存活，status=silent，却不进 Needs you、不推送。(a) 成立。最小修复：先建立并验证 run- 是包装运行专用命名空间，再按前缀过滤；不可把现有普通线程误判为包装运行。
P2-test — api/internal/agentthreads/threads.go:342、threads_test.go:604：超时起点不可被进度拍延后，仅缺测试；before_tool(T,1,1800s)@0 → headless-progress(T,2)@1m → @32m+1s 应 silent。植入 t.At=at 后原指定测试仍 PASS；副本新增 TestReview124GuardBoundaries/anchor-and-order 抓住错误。最小修复：补 At 不变及原截止时间之后 silent 的断言；当前实现正确。
P2 — api/internal/agentthreads/config.go:200、watch.go:139、threads.go:539：run-x turn_start@0，主机心跳@0，@11m 主机丢失；Owner 主机推送仍把该运行列为 mid-turn，未彻底兑现「从 Owner 项排除」。最小修复：仅过滤 Owner 主机消息中的包装运行，保留协调者线程列表和真实主机丢失告警。
1. 能；idRe 接受 run-owner，普通 hook 从环境覆盖或 session_id/conversation_id 取 id，未验证包装来源；该普通线程仍在列表，但从 Needs you 和静默推送隐藏。包装 run 也接受无 run- 前缀的环境覆盖（scripts/thread-heartbeat.js:1255），所以前缀不是可靠类型判据；需统一生产者约束及已有记录处理。
2. 是；handler.go:138 → view.go:19/61 保留已有 thread/status/quiet_seconds/threshold_seconds，活主机下 status=silent。Needs you 静默总数已过滤；watch.go:403 的全线程指标与 Status/In progress（agentThreads.ts:148）仍统计它们，属观测；HostView 本身无线程计数，主机摘要仍夹带运行（上述 P2）；满容量拒绝计数也仍包含运行占用，属实际容量告警。
3. 不新增乱序问题；Apply 在守卫前校验旧 turn、Seq 和 key（threads.go:329–336），守卫保存 Seq。progress(T,2) 后 real after_tool/turn_end(T,3) 接受；重复 Seq=2 拒绝；较小序号的迟到事件仍按原契约拒绝。客户端按每线程锁分配递增序号（scripts/thread-heartbeat.js:753/767）。副本新增测试验证上述行为及过期、异 turn、非进度事件。
4. 两个 Go 变异实际验证：去前缀过滤 → TestSilentHeadlessRunIsNotAnOwnerItem FAIL；去守卫 → TestProgressBeatKeepsDeclaredToolTimeout FAIL。Console 去过滤将让 fixture 两条 silent 都计入总数，指定测试的「1 waiting for you」及 run 行不存在断言必败（NeedsYouPage.test.tsx:258–285）；仅静态核验，简报未授权运行 Console 测试。自植变异见 P2-test。
5. 无请求/响应字段、路由或存储 schema 变更；五文件 diff 只有过滤、Apply 分支与测试。完整包重跑因 TestPinLookTextIsPostedUnchanged 的 httptest 监听端口被沙箱拒绝而中止；两项原指定测试和副本 Review124 测试定向 PASS，未把整包宣称为 PASS。
核验范围：提交 faae0e6；原源码只读，变异和新增测试仅在本目录 api-copy，变异均已恢复；无网络、集群、凭据读取或其他 agent。
END OF REPORT
