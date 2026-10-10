PART B VERDICT: ready after fixes

审查 refs：platform API/workers `8e4c0da`，Console `1116e7a`，infra `bfee81f`；均与指定远端分支一致。仅读取指定提交和差异，并执行内存 mock；没有 checkout、文件写入、提交、推送或平台/集群调用。

| 项目 | 判断 | 依据 |
|---|---|---|
| B2 恢复登记 | 部分修复 | nonce 重试、旧记录迁移和服务端清理后的恢复已实现；密钥清除及并发恢复仍有缺口。 |
| B3 顺序与回合 | 部分修复 | 普通分配有跨进程锁，wrapper 共用分配；锁回收存在竞争，新回合首事件丢失后无法恢复。 |
| B4 推送认领 | 已修复原缺口 | 认领有 ID 和两分钟期限，成功后才标记发送；崩溃后的认领可重试。外部送达仍可能重复。 |
| B6 容量 | 部分修复 | 首登记执行上限，优先清理终态，满容量返回 429 并计数；拒绝没有进入 Owner 的监控视图。 |
| B5 expected hosts | 已修复配置后的路径 | 从未上报的预期宿主显示 `never_reported`，计入 Needs You。 |
| B5 精确接线匹配 | 部分修复 | 已解析 JSON 和比较 realpath，但仍接受无效命令，并读取 Cursor 不加载的项目配置。 |
| P3 宿主时限文案 | 已修复 | 包注释明确为约 3–4 分钟，而非硬性三分钟内。 |

**发现（P2 须在 PROD 前修复；P3 为说明或边界修正；未发现 P1）。**

1. **C1 — P2：两分钟窗口结束后，登记明文密钥不保证被清除。**  
   **Ref / 位置：** platform `8e4c0da`，`api/internal/agentthreads/recorder.go:80–90、260–269、314–322`；`threads.go:173–177`。  
   **证据：** `RegisterKey` 被序列化进 statefile。清除只发生于后续 `Admit` 或有缓冲事件的 `Flush`；空 `Flush` 提前返回。所有 reporter 停止后，周期 flush、GET 和 watcher 都不会清除该明文，因而可以无限期留存。新增测试 `threads_test.go:744–750` 是先提交过期请求，再检查清除，未覆盖无人继续上报的路径。静态证据，未运行 Go 复现。  
   **最小修复：** 周期清理不能因缓冲为空而跳过；仅在存在过期密钥时写入。增加登记后停止所有上报、推进时间并运行周期清理的测试。

2. **C2 — P2：迟到恢复响应会覆盖新记录，多个旧 409 会连续废弃当前记录。**  
   **Ref / 位置：** infra `bfee81f`，`agent-config/scripts/thread-heartbeat.js:475–509、537–550`。  
   **已复现：** 在内存文件系统中，先将 `same` supersede 为 `same:1`，再处理 `same` 的迟到发钥响应；`saveIssuedKey` 找不到对应 active 记录后，回退到当前记录，把旧密钥写进 `same:1`。再次处理针对 `same` 的旧失败事件，`supersedeActive` 又将 `same:1` 废弃，创建 `same:2`。  
   请求完成路径没有核对请求的 thread ID、nonce 和当前记录身份。正常并发响应即可造成错误密钥、重复登记及额外静默记录。  
   **最小修复：** 在锁内按请求的 ID 和 nonce 条件更新；迟到响应不得回退修改当前记录。旧记录已经 superseded 时，旧 409 不得再次 supersede 当前记录。

3. **C3 — P2：合法新回合的 `turn_start` 丢失后，后续事件持续被拒绝。**  
   **Ref / 位置：** platform `8e4c0da`，`api/internal/agentthreads/threads.go:355–364`；infra `bfee81f`，`thread-heartbeat.js:460、537–554、615–621`。  
   **证据：** 客户端先持久化新 UUID，再通过 detached 请求发送 `turn_start`。如果这次请求丢失，服务端仍保留旧回合；新 UUID 的 before/after/end 均因不是 `turn_start` 返回 `older turn refused`。客户端仅恢复 `unknown key`，没有补发回合开始的路径。因此该回合可以始终不上报，服务端继续显示上一回合，上一回合若已结束则保持 idle。静态证据，未做网络复现。  
   **最小修复：** 保存未确认的回合开始事件，并在确认前保证重试及发送顺序；处理该 409 时恢复当前合法回合，不能放宽已结束回合的拒绝规则。正常重启且 gate 完整时，序号继续增长；回合 UUID 本身不依赖客户端时钟。

4. **C4 — P2：死锁回收可能删除另一个进程刚取得的活锁。**  
   **Ref / 位置：** infra `bfee81f`，`agent-config/scripts/thread-heartbeat.js:385–405、421–427、435–437`。  
   **证据：** 检查旧 PID 和删除锁目录之间没有原子保护。两个竞争者都判定旧锁失效后，一个删除并取得新锁，另一个仍会按先前判断删除新锁，随后进入同一临界区；退出时也无持有者核验。  
   **已复现范围：** 内存 mock 注入“失效检查后，竞争者已替换锁”的交错，实际函数删除活锁并进入临界区。未运行真实多进程崩溃测试。  
   **最小修复：** 使用进程退出自动释放的跨进程锁，或实现具备所有权保护、不会删除继任者锁的回收协议；增加两个竞争者同时回收死锁的测试。

5. **C5 — P2：wired 仍可误报，effective config 的筛选也不完整。**  
   **Ref / 位置：** infra `bfee81f`，`agent-config/scripts/host-heartbeat.js:74–76、154–172、181–190`；`agent-config/README.md:95–96`。  
   **已复现：** 在 realpath 的内存 mock 下，以下两条均返回 `true`：
   - `echo node /mock/scripts/thread-heartbeat.js hook cursor`
   - `node /mock/scripts/thread-heartbeat.js ignored hook cursor`

   前者只输出文本；后者让脚本进入无效 mode。匹配器在任意 token 位置寻找 `node`，并独立寻找 `hook cursor`，没有验证实际调用位置和参数顺序。另有静态缺口：它读取项目 `.cursor/hooks.json`，却不排除仓库文档明确说明 Cursor 拒绝加载的符号链接配置。  
   **最小修复：** 严格验证支持的调用形式及紧随脚本的 `hook <vendor>` 参数；按厂商实际加载规则筛选配置。增加上述命令和 Cursor 符号链接配置测试。Codex trust 目前明确未检查，不能把 wired 理解为已受信任并执行。

6. **C6 — P2：容量拒绝会留下 Owner 看不到的新线程监控缺口。**  
   **Ref / 位置：** platform `8e4c0da`，`api/internal/agentthreads/recorder.go:183–185`、`handler.go:59–61、99–106`、`watch.go:386–391、434–437`；Console `1116e7a`，`console/src/pages/shell/needs-you/useNeedsYou.ts:24–44`；infra `bfee81f` 的 `k8s/monitoring/`。  
   **证据：** 满容量拒绝确实返回 429，并递增 process-local Prometheus counter；但拒绝记录不保存、不进入列表，也不进入 Needs You。hook 忽略该响应。指定 refs 的监控配置没有消费该新增 counter 的告警。300 个正常活跃线程占满时，第 301 个线程无法被监控，其后停止也没有可供 watcher 判断的记录。计数可通过 `/metrics` 查询，当前 Owner 页面不会提示这项缺口。静态证据。  
   **最小修复：** 将容量拒绝接入 Owner 可见的告警或监控降级状态，保留拒绝数量及最近发生时间；无需突破容量上限保存完整线程。

7. **C7 — P3：安全说明需要准确描述 nonce 和明文窗口。**  
   **Ref / 位置：** platform `8e4c0da`，`api/internal/agentthreads/threads.go:10–14、34–40`；`recorder.go:125–134、226–233`。  
   **证据：** 包注释的位置易于发现，且“共享 reporter token 可以报告任意宿主、登记任意新线程”的核心边界准确。但“Only the hash is stored”与实际存储 `RegisterKey` 不符；“没有线程 key 就不能更新”的绝对表述遗漏了 nonce 恢复及无 hash 旧记录迁移。  
   实际边界是：持有 reporter token 且知道某线程 nonce 的第二方，在窗口内可以重放并取得同一 key；nonce 没有绑定 reporter principal。客户端 nonce 为 32 个随机字节，没有发现可预测生成路径，也未尝试猜测攻击。  
   **最小修复：** 明确 nonce 在窗口内也是恢复凭据，说明临时明文存储及迁移例外，并修正清除保证。

8. **C8 — P3：仍有两处“一次／不延迟”的绝对文案不成立。**  
   **Ref / 位置：** platform `8e4c0da`，`api/internal/agentthreads/threads.go:1–2`、`watch.go:146–160、190–204`；infra `bfee81f`，`thread-heartbeat.js:16–18、413–430、686–687`。  
   **证据：** 外部推送成功后、完成标记写入前崩溃，认领到期会再次推送；通知调用没有传递稳定去重 ID。新实现解决了永久漏发，提供的是可重试送达，不能保证外部严格一次。  
   hook 虽然失败退出 0，但同步锁等待可达约两秒，首次登记还会同步等网络；同步等待期间三秒 JS timer 不能执行。“never blocks or slows a tool call”不准确。  
   **最小修复：** 文案说明可能重复及有限等待；若要求严格一次，向 relay 提供稳定去重 ID。若要求三秒硬上限，应避免同步等待，并使用不受墙钟回拨影响的计时。

**确认 sound 的部分：**

- B1 和剩余 B5 已明确划为独立凭证绑定 lane。当前共享 token 持有者可以伪造宿主 alive、wired、token-ready，也可以大量登记新线程；这些行为不会直接授予交易或集群写权限。
- 新登记不会删除旧线程。superseded 标记保存在客户端 gate；服务端旧记录仍会独立显示静默或宿主丢失。因此更换 ID 本身不能直接隐藏旧问题，但能制造重复记录并占用容量。
- B4 的 claim ID、期限、完成及释放身份检查已落实。发送前崩溃不再永久抑制提醒；正常成功后的重复轮询不会再次发送。超过 `PushWithin` 的旧问题仍按既有规则只标记、不推送。
- 容量路径保护仍在监控的身份，首登记和宿主登记都有上限及明确错误。另需保留准确边界：`threads.go:403–414` 的 72 小时 retention 仍会删除 mid-turn 线程，“永不删除 mid-turn”只对容量腾位成立。
- expected hosts 路径完整：API `threads.go:530–545、743–759`，Console `agentThreads.ts:115–124`、`HostHeartbeatRow.tsx:8–24`、`useNeedsYou.ts:27、44`。合法拼错的名字或另一个上报名会形成两个独立身份，预期名字继续显示 never reported；非法名字则被静默丢弃。配置应采用 host script 实际生成的短主机名。指定 infra 清单没有设置该环境变量，部署后的预期宿主清单未验收。
- 无 reporter token 时宿主脚本确实不能报告；注释已明确依赖 expected hosts 显示从未上报的宿主。
- Console 测试已改为等待 loaded 文本，并检查 `Loading…` 消失，未削弱等待线程和宿主显示断言。
- hook 异常路径退出 0、无 stdout，没有发现失败返回权限拒绝的路径。宿主脚本不是工具调用钩子，其网络失败也退出 0。
- 文件读取的 reporter token 没有被脚本新增到 argv 或环境；detached argv 只有文件路径。gate 和发送文件使用 0600，目录使用 0700，plist 不含 token。显式提供的 `PLATFORM_REPORTER_TOKEN` 会随普通子进程环境继承。没有发现脚本新建 world-readable token 文件的路径。

**未检查：** 未运行完整 Go/build/vet/race、Node 文件测试、Console 构建或浏览器验收；这些不是本次内存检查的通过项。未检查实际 harness、launchd、权限模式、部署配置、真实网络故障或手机送达。没有读取 Owner 凭证目录、env/token 文件、`.env` 或 kubeconfig。仅 C2、C4 的指定内存交错和 C5 命令匹配标为复现，其余结论来自代码审查。