VERDICT: fix first
A SEQUENCE FOR (a)–(e): found
RULES THAT ONLY LACK A TEST: 2
路径以下均相对被审仓库；反例测试在本目录 api/internal/agentthreads/review127_test.go，输出在 review127-test-output.txt。
P2 · platform api/internal/agentthreads/view.go:90：同一 sidebar T，A 在 0 分钟 turn_start，B 首拍在 1 分钟 turn_end（未开回合）；12 分钟 A 未被取代，却由较新的 idle B 代表 T，静默列表及 Due 都漏掉 A（a）。最小修法：没有存活会话时，未被取代的 silent 优先于 idle。副本已复现。
P2 · platform api/internal/agentthreads/watch.go:218：A 静默 11 分钟，Due 选出 A；B/T 随即 turn_start；claim 只复核 A 的时间戳，仍推送已存活的 T，随后 B 的静默可再推一次（c）。最小修法：claim 的事务内重新判断整个 T 的静默资格及代表会话。副本已复现旧推送。
P2 · platform api/internal/agentthreads/view.go:65：Claude A 和 Cursor B 都携带 sidebar T 并开回合；都安静 11 分钟，得到两张 T 卡片及两项 push（c）。最小修法：以 sidebar 标识线程统一聚合、取代判断；不要额外按 vendor 拆开。副本已复现。
P2 · platform api/internal/agentthreads/threads.go:285：显式 sidebar=""、" "、null 均通过校验并返回 202，而空 thread 不符合 idRe（e）。最小修法：区分字段缺席与显式空值/null；出现时完整应用线程 id 规则。独立注册的三例已在副本复现。
P2 · platform api/internal/agentthreads/view.go:121、watch.go:402：A/B 同时活着只返回一个代表，且不返回 session id；协调者及 Status 看不到另一会话/host/tool，状态指标也从两会话变一线程。最小修法：保留协调者所需的会话视图，Owner 聚合单独处理；具体接口安排需另获批准。
P2-test · infra agent-config/scripts/thread-heartbeat.test.js:1634：只有 CURSOR_SESSION_ID 存在时的末级回退未测；现有测试只验证它被更高优先级覆盖。最小补法：清空前两变量，断言该变量单独生效。
P2-test · platform api/internal/agentthreads/store.go:23：没有 sidebar 新旧记录升级/回滚的兼容测试。最小补法：旧记录经新版读取、新记录经旧版读取并重写后再升级，核对原有字段及新元数据丢失行为。
1. wrapped run 会继承并携带协调者 sidebar（infra thread-heartbeat.js:1264）；平台按实际 run- id 排除取代及折叠，仍单列给协调者，不能维持桌面 T 存活、不能藏在 T 下、不能重进 Owner 卡片/推送。两个 Cursor 变量有 sessionId.ts:4 及既有测试/文档引用，但未找到真实环境测量，不能据此证明 Cursor 实际提供它们。
2. Status 与协调者共用 handler.go:138 的折叠列表，单个会话不可见；Open thread 已支持 lineage.session 匹配；lineage 自己来自 /api/v1/lineage，未改；指标改为折叠计数，容量仍按原始 maxThreads=300 会话计数，被取代记录未结束也仍占槽。因此响应语义及指标均超出单纯增加可选请求字段，不能声称“其余不变”。
3. store.go:23 的 json.Unmarshal 能读取无 sidebar 的旧记录（空值/false）；旧版同样忽略新增字段，新记录原有键、序号、回合等能读；旧版重写会丢失 sidebar/opened_turn，再升级须后续心跳恢复，不能保证折叠状态保留。此项为代码核查，未执行旧版。
4. 客户端 diff 只在 beatFor 返回和 run base 上附加字段；无三个变量时不修改对象及 JSON 顺序，锁、序号和 5 秒 hook deadline 路径未动，正常 hook 仍静默退出 0。客户端测试做新旧对象去掉 sidebar 后的字节比较，并非运行旧版本比对；本次只读核查，未重跑 Node/Console。
5. 实测四个报告中的 Go 植入：跳过校验→TestOptionalSidebarValidatedLikeThreadID；提前取代→TestSupersedeNeedsAnotherTurnAndSilence；空 sidebar 互关→TestSessionWithoutSidebarStillGoesSilent；不折叠→TestOwnerListsTheThreadOnce，均失败。客户端两个植入按断言检查会分别使 progressSpawnFailureDoesNotConsumeGrowth、sidebarFieldFollowsEnvironment 失败，未实跑；自植入“run 加入折叠组”也使 TestOwnerListsTheThreadOnce 失败，已恢复副本。
6. 附录已按源码落实：预加载分别模拟 spawn throw/error，下一次尝试要求 exactly one after_tool；progressExitDuringTryWait 上界改为 1500 ms（test.js:1056），同步等待约 1980 ms 仍越界。未独立测量耗时。
验证：副本原有 Go 包测试通过（跳过新增反例及监听端口两例）；四个新增反例测试按预期失败。受沙箱限制未运行 TestPinLookTextIsPostedUnchanged、TestHiddenFieldsAreWithheldAtTheRelay；未跑整套 API。无网络、集群、凭据访问；仅写本目录，原仓库未改。
END OF REPORT
