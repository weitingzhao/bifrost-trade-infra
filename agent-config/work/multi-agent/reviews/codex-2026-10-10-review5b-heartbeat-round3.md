PART B VERDICT: ready after fixes

审查 refs：platform `b943ef0`、Console `ea0b5cd`、infra `eddf51c`，均与指定远端分支一致。未发现 P1；有三项 P2 须在 PROD 前解决。B1 与剩余 B5 的每宿主凭证 lane 未重复计入。

| 项目 | 判断 | 代码依据 |
|---|---|---|
| C1 周期清除明文钥 | 已修复 | `b943ef0`，`recorder.go:316–325、386–404`：空缓冲也清除过期钥，并在更新内复查。 |
| C2 响应绑定请求记录 | 已修复 | `eddf51c`，`thread-heartbeat.js:591–647`：匹配 ID、nonce 和非 superseded 状态，无当前记录兜底。内存复现通过。 |
| C3 未确认回合重发 | 部分修复 | 丢失开始事件可补发，但补发触发重新发钥时仍有错误，见发现 1。 |
| C4 跨进程锁 | 部分修复 | 新版之间采用 flock；新旧版本并存的升级路径不安全，见发现 2。 |
| C5 wired 判定 | 部分修复 | 原错误命令及 Cursor 符号链接配置已排除；仍有正常接线的假阴性，见发现 3。 |
| C6 容量拒绝可见性 | 已修复，附 P3 | counter、时间、API、Console 和一小时 Needs You 条件已接通；历史提示见发现 4。 |
| C7 安全文案 | 已修复 | `b943ef0`，`threads.go:10–27`：说明明文窗口、nonce 恢复凭据及无 hash 记录迁移。 |
| C8 送达及等待文案 | 部分修复 | 重复送达说明准确；五秒等待上限仍不成立，见发现 5。 |

**发现**

1. **P2 — 补发 `turn_start` 重新发钥后，后续事件仍使用旧钥，制造额外静默记录。**

   **Ref / 位置：** infra `eddf51c`，`agent-config/scripts/thread-heartbeat.js:706–746`；platform `b943ef0`，`api/internal/agentthreads/recorder.go:160–195`。

   **已复现（内存模拟）：** 客户端持有旧钥、回合未确认，服务端记录已经清理。补发开始事件重新登记 `s` 并收到新钥；`saveIssuedKey` 更新 gate，却没有更新待发送的 `body.thread_key`。随后 `before_tool` 仍带旧钥，收到 409，于是把 `s` supersede 为 `s:1`。服务端留下 `s=turn_start` 与 `s:1=before_tool` 两条记录。

   新登记的 `s` 已被客户端放弃，却仍会按静默规则显示并提醒 Owner；这是第三轮新增的恢复路径退化。

   **最小修复：** 补发获得新钥后，在确认请求记录匹配的条件下，把新钥同步到后续事件，再发送该事件。补充“旧钥＋未确认回合＋服务端记录已清理”的测试，断言只保留一个身份。

2. **P2 — 新旧锁协议共用路径，旧版长期运行的 wrapper 可以删除新版 flock 文件。**

   **Ref / 位置：** infra `eddf51c`，`thread-heartbeat.js:475–545、828–863`；旧版 `bfee81f`，同文件 `385–437`。

   **已复现（内存文件系统）：** 将新版持续保留的 `.lock` 文件模拟为超过五秒、其 inode 仍被新版 helper 锁住。实际旧版 `withThreadLock` 读取 `<lock>/pid` 失败，按文件 mtime 判为 stale，删除该文件、建立目录并进入临界区。删除路径不会释放新版 helper 对旧 inode 的 flock；此时新旧进程可以同时进入。

   `run` wrapper 可以跨越脚本升级长期存活，退出时仍执行已加载的旧锁代码。新版迁移函数也未核验旧目录持有者是否仍活着。

   **最小修复：** 将升级明确设为必须静止切换：所有旧版 hook、sender 和 `run` wrapper 退出后才启用新协议，并增加此项安装验收。若要求新旧并存，则需要共同遵守的迁移协议；仅换锁文件名不能解决互斥。

3. **P2 — 默认宿主心跳安装会把有效的 Claude 项目接线报告为未监控。**

   **Ref / 位置：** infra `eddf51c`，`host-heartbeat.js:70–92、205–219`；`com.bifrost.host-heartbeat.plist:7–17`；`install-host-heartbeat.js:23–25、41–46`。

   **已复现（内存配置）：** 工作区 `.claude/settings.json` 配有正确的绝对脚本调用。没有 `BIFROST_WORKSPACE` 时，`wired('claude')` 返回 false；设置工作区变量后返回 true。默认 plist 没有设置该变量，脚本也没有从自身位置发现工作区，因此漏读项目配置。

   另一个已复现的假阴性：Cursor 用户配置中的 `node ./scripts/thread-heartbeat.js hook cursor` 被按用户 home 解析；仓库文档说明该相对调用以工作区根为 cwd，见 `agent-config/README.md:95`。

   **最小修复：** 安装时把工作区明确写入 plist，或从脚本位置可靠发现工作区；按实际执行 cwd 解析用户级相对调用。增加默认 plist 环境及用户级相对路径测试。

4. **P3 — 容量恢复后，Status 仍永久显示现在时的 “monitoring is full”。**

   **Ref / 位置：** Console `ea0b5cd`，`AgentThreadsInProgress.tsx:12–18`、`api/agentThreads.ts:59–78`；platform `b943ef0`，`threads_test.go:1036–1038`。

   **证据：** counter 是累计值，后续成功登记不会清零。Needs You 在最后拒绝满一小时后退出，符合要求；Status 只检查累计值与时间是否存在，因此即使容量已经恢复，仍持续显示 “monitoring is full”。这是静态代码结论，未运行浏览器复现。

   **最小修复：** 过期后使用历史文案，例如 “monitoring previously refused …”；近期条件与历史累计值分别表达。

5. **P3 — 宣称的五秒 hook 上限仍低于代码允许的等待。**

   **Ref / 位置：** infra `eddf51c`，`thread-heartbeat.js:60–63、502–523、710–724、744–754、887–896`；`agent-config/README.md:98`。

   **证据：** Node 等待 helper 的期限实际为 `LOCK_WAIT_MS + 500`，即 2.5 秒。一次发钥响应还可以连续执行 `saveIssuedKey` 和 `markTurnConfirmed` 两次同步锁等待；期间没有让 timer 执行的事件循环机会。因此“3 秒加一次 2 秒锁等待＝真实五秒上限”不成立。未运行真实墙钟时限测试。

   **最小修复：** 使用共享的单调时钟 deadline，每次锁等待前检查剩余预算，并把预算传给 helper；或者删除硬上限承诺，准确描述多次同步等待。

**确认可靠的部分**

- 新版 flock 使用持续存在的同一 inode；新版竞争者不再删除继任者锁。正常释放会杀掉 helper；父进程退出关闭 stdin 后，持锁 helper会退出。等待中的 helper 也有超时。未发现普通新版退出路径永久留下持锁 helper 的代码。
- 未确认回合只保存确认标志及开始序号，没有引入无限增长的重发事件队列。同序号重发由服务端忽略，已离开的回合仍被拒绝。
- C2 的迟到发钥和重复旧 409 均在内存模拟中通过，不会修改新记录。
- 原 C5 两条无效命令已在内存模拟中返回 false；正确 Claude 调用及仓库 Codex 调用形式返回 true。Cursor 项目配置的符号链接筛选已加入。
- 周期清钥已接入 API 的十秒 flush；并发更新内再次检查，避免无变化写入。
- 容量拒绝仅保存一个累计整数和一个时间，存储规模为常数；API 返回它们，Needs You 只增加一个条件，并在一小时后退出。
- 推送认领、身份校验和失败重试未被第三轮削弱；“可能重复送达”的新文案符合实现。

**未检查**

未运行完整 Go、race、Node 文件测试、Console 构建或浏览器验收；未执行真实 flock 多进程、崩溃、launchd、网络故障或手机送达测试。标为“已复现”的结果仅来自指定提交代码的内存模拟。

没有 checkout、文件写入、提交、推送或平台／集群写操作；没有读取 Owner 凭证目录、env/token 文件、`.env` 或 kubeconfig。