PART A VERDICT: ready after fixes

审查 ref：platform `origin/w31/s0-0-int@ea232d3`；infra `origin/w31/s0-0-int@9c5f973`，均与 BRIEF 一致。以下行号属于指定提交。除明确注明“已复现”外，证据来自静态调用链检查。

原发现的修复状态：

| 原发现 | 判断 | 代码依据 |
|---|---|---|
| 1 创建超时与重复执行 | **部分修复** | `workactions/service.go:194–330、353–380、473–547` 已实现审批尝试命名与 uncertain 错误；仍有无条件收养及 delivery 路径遗漏，见 A1、A2。 |
| 2 租约过期 | **部分修复** | `approvals/execution.go:238–274、547–585` 修复了 renew/result，但 `finishPlatform:128–169` 仍可越过过期检查，见 A3。 |
| 3 规范审批行 | **已修复核心缺陷** | `approvals/line.go:14–46、59–90`；`service.go:375–405`；MCP `registerApprove.ts:59–64、104–112`。剩余显示限制见 A7。 |
| 4 脱敏顺序与持久化 | **部分修复** | `execution.go:600–601` 先脱敏再截尾；`service.go:522` 与 `handler.go:198` 脱敏拒绝原因。其他存储路径仍有遗漏，见 A5。 |
| 5 推送参数白名单 | **部分修复** | `actions/describe.go:181–205` 排除了新建单的 passthrough 参数，但将全部声明参数视为可推送参数，见 A6。 |
| 10 原子提醒认领 | **部分修复** | `approvals/notice.go:86–101` 原子认领，失败释放，delivery 上限 20；崩溃后的认领没有恢复，见 A4。 |
| 12 Tier D 合并约束 | **已修复** | `service.go:380、445–468` 保留 D-chat 拒绝；MCP `registerApprove.ts:91` 对批准、驳回均拒绝 D。服务端仍接受 phone/console 标签及 D 驳回，这是原方案已接受的边界。 |

1. **A1 — P1：同名对象未经身份核验就被收养，审批可错误报告执行成功。**  
   **Ref：** platform `ea232d3`。  
   **位置：** `api/internal/workactions/service.go:321–329、353–377、476–484、537–544`；`api/internal/approvals/execution.go:209–210`。  
   **证据：** GET 同名 PipelineRun 或 Job 成功便返回成功；AlreadyExists 也被视为成功。没有核对完整审批 ID、attempt、参数 hash、对象 spec 或执行结果。手工创建的同名对象可以被收养；代码也无法区分名称碰撞来自哪个审批。PipelineRun 返回正常 `apply_run`，Job/probe 返回 `adopted:true`，审批最终为 `executed`，即使该对象正在运行、已失败或执行了其他参数。没有复现集群碰撞。  
   **最小修复：** 创建时记录完整审批身份和参数 hash，收养时核验身份及预期 spec；GET 和 AlreadyExists 共用核验路径。不匹配进入待核实状态，不能报告本审批已执行。

2. **A2 — P2：`start_pipeline_run` 没有接入确定性命名和 unknown 分类。**  
   **Ref：** platform `ea232d3`。  
   **位置：** `api/internal/delivery/service.go:263、347–350`；`delivery/handler.go:75–89`；`server/actions_wire.go:243–247、413–428`。  
   **证据：** 该动作仍使用 `pipelineName + now.Unix()`。创建超时被 handler 编成 HTTP 502；`interpretAction` 将其变成普通错误，丢失 Kubernetes 错误类型，审批最终为 `failed`。因此 unknown 对 workactions 的 PipelineRun、CronJob Job、probe Job 可达，却对该 delivery PipelineRun 不可达。这里没有自动重排，但错误地报告失败会诱导人工再次执行已创建的 run。  
   **最小修复：** delivery 创建链使用审批 attempt 身份，并将创建结果不确定性保留到审批状态机；增加覆盖真实注册 executor 的超时测试，而非只测试 `work.Apply`。

3. **A3 — P1：平台执行结果仍可重排已超过 unknownGrace 的租约。**  
   **Ref：** platform `ea232d3`。  
   **位置：** `api/internal/approvals/execution.go:112、128–169`。  
   **证据：** `finishPlatform` 的写事务未调用 `lapseRunning`。若记录仍为 running、时钟已超过 `LeaseExpiresAt + unknownGrace`，它仍按 transient 错误调用 `requeue`。结果取决于 renew/sweep 是否先运行，与已修复的 HTTP result 路径不一致。后台续租还丢弃 renew 的错误和拒绝结果。未运行调度停顿复现。  
   **最小修复：** 在 `finishPlatform` 的同一写事务、同一 `s.clock()` 下先执行过期转换；过期后 transient refusal 不得重排。后台续租应记录错误及租约丢失。

4. **A4 — P2：worker 崩溃会永久抑制该种提醒。**  
   **Ref：** platform `ea232d3`。  
   **位置：** `api/internal/approvals/notice.go:64–83、94–96、281–305`。  
   **证据：** `claimed` delivery 在发送前持久化；`notified` 只看 kind，不区分 claimed、accepted 或年龄。进程在认领后、发送前退出，或发送后无法完成存储，后续 worker 永远认为该提醒已经发过。另一种到期提醒可能仍发送，但不能恢复丢失的这次提醒。  
   **最小修复：** 认领使用有限租期及 claim ID，过期可重新领取，完成/释放必须核对 claim ID。若要求外部投递也严格一次，relay 需要接受稳定的去重 ID。

5. **A5 — P2：delivery 错误和审计详情仍绕过 Redact。**  
   **Ref：** platform `ea232d3`。  
   **位置：** `api/internal/approvalnotify/notify.go:267–269、295–307`；`approvals/notice.go:132–147`；`approvals/service.go:573、590–599`；`approvals/execution.go:373–375、465–466`。  
   **证据：** relay 返回的 `Delivery.Error` 只经过 oneLine/clip，随后原样进入审批 delivery 和审计。relay 顶层错误及 transport 错误也没有统一脱敏。另一个确定路径是合法的 `executor_id:"token=SYNTHETIC_SECRET"`：验证允许，claim 审计直接拼接原值，审计层不负责 Redact。  
   **最小修复：** delivery 错误在截断前脱敏；审批审计详情在最终写入边界统一脱敏。执行所需的原始参数应与展示、审计字段分别处理。

6. **A6 — P2：声明参数不是秘密安全的推送白名单。**  
   **Ref：** platform `ea232d3`。  
   **位置：** `api/internal/actions/catalog.go:429–435`；`actions/describe.go:181–205、225–226`；`approvals/notice.go:18–22`；`approvalnotify/notify.go:210–224`。  
   **证据：** `run_probe_pod.args` 是声明参数，会成为 key param。例如 `["--password","SYNTHETIC_SECRET"]` 被拼成 `--password,SYNTHETIC_SECRET`；对值执行 Redact 无法识别该形式，随后进入推送。旧版本已存储的 passthrough `key_params` 也未在发送时重新过滤；`api_key` 的裸值仍可被复制到通知。  
   **最小修复：** 增加逐动作、专供通知的安全键清单，排除 args 等可承载秘密的字段；每次发送都过滤，包括历史记录。自由文本先脱敏，再摘要裁剪。

7. **A7 — P3：规范审批行仍有显示和唯一性限制。**  
   **Ref：** platform `ea232d3`。  
   **位置：** `api/internal/approvals/line.go:38–46、72–76`；`mcp/platform/src/registerApprove.ts:143–144`。  
   **证据：** U+2028/U+2029 不属于 `unicode.IsControl`，也不在 bidi 清单中，仍原样输出；因此“一行”显示承诺不完整。12 个 hex 字符只有 48 位，不能数学保证不同参数集永远产生不同显示行；未构造实际 hash 碰撞，服务端完整 hash 比较仍提供保护。MCP 的 D 分支最后展开 `...rec`，会重新带回 API 已提供的 `approval_line`，与“D 没有这一行”的说明不符；工具自身仍拒绝 D。  
   **最小修复：** 显式转义 Unicode 行分隔符；准确描述短摘要的边界；D 列表返回前明确移除审批行。

确认 sound 的部分：

- 规范行只有一个服务端生成实现；反斜杠、换行、控制字符和 bidi 转义，MCP 严格比较，服务端检查完整 params hash 并保存 `ApprovedLine`。
- Console `ApprovalsPage.tsx:215–220` 和 MCP 都发送 `approval_line`、`params_hash`。手机通知链接进入同一个 Console 页面，也使用这条提交链；未发现独立 phone 客户端实现。
- 旧客户端只发送合法 `channel` 时，pending 审批返回 **409**，不执行。API 先升级、Console 尚旧时会暂时无法批准，但不会降级绕过回显检查。
- renew/result 使用同一服务时钟，原租约只能提交一次最终迟到结果；renew 存储错误传播为 HTTP 500。
- 合并保留了 D-chat 服务端拒绝、MCP 的 D 批准/驳回拒绝及渠道信任说明。A2、A3 是执行链覆盖遗漏；另一个集成遗漏是 `service.go:432` 丢弃首次平台执行事件，而 `handler.go:163–165` 只补 failed 通知，**首次创建超时进入 unknown 时没有 unknown 推送**。这是 P2；最小修复是统一消费 `runPlatform` 返回的事件，避免针对单一状态补发。

未检查：未运行完整验收、race、Console 构建或真实手机送达；未模拟 Kubernetes、存储故障和 worker 崩溃。Owner 脚本读取被项目闸门拒绝，未绕过，故 infra 的 Owner 执行器租约实现未签收。

PART B VERDICT: ready after fixes

审查 ref：platform API/workers `94f2192`、Console `33dc71c`；infra `92a844c`，均与 BRIEF 一致。

原发现的修复状态：

| 原发现 | 判断 | 代码依据 |
|---|---|---|
| 6 线程归属 | **部分修复** | `agentthreads/recorder.go:67–107` 阻止没有密钥的后来者，但首次登记仍可抢占，密钥生命周期也有缺口。 |
| 7 长超时完成事件 | **已修复所述路径** | infra `thread-heartbeat.js:207–240` 保留调用身份并强制发送匹配的完成事件；API 非 before-tool 事件清除 timeout。内存纯函数检查通过。 |
| 8 乱序 | **部分修复** | `threads.go:234–235` 忽略旧序号；客户端序号分配没有跨进程原子性，turn ID 也未参与服务端判定。 |
| 9 Notification | **已修复** | infra `thread-heartbeat.js:164–168` 只映射明确等待通知；其他通知忽略。内存检查确认 `auth_success` 不改变状态。 |

1. **B1 — P2：首事件可以抢占不属于 reporter 的线程，宿主状态也可伪造。**  
   **Ref：** platform `94f2192`。  
   **位置：** `api/internal/agentthreads/recorder.go:74–96、110–117`；`handler.go:69–82`；`threads.go:243、267–278`；`server/server.go:460–466`。  
   **证据：** reporter 可以任意填写 vendor/thread/host。先提交首事件就获得线程密钥，没有与认证 principal 或预登记宿主绑定。真实会话随后收到 409。宿主 heartbeat 完全没有宿主专用 capability；任一 reporter 都能刷新别人的 Host.At 或填写假的 wired/token 标志，隐藏宿主丢失告警。  
   **严重性：** 这是监控真实性缺陷，不直接授予交易或集群写权限，但违背“只报告自己的线程”目标。  
   **最小修复：** reporter principal 绑定允许的宿主，并限制宿主 heartbeat；线程登记同时核验宿主和会话归属。宿主身份应由受控配置登记，不能再用另一个“先到先得”机制。

2. **B2 — P2：密钥丢失、响应丢失、旧记录升级及保留期清理都会使线程无法恢复上报。**  
   **Ref：** platform `94f2192`；infra `92a844c`。  
   **位置：** `agentthreads/recorder.go:76–99`；`threads.go:283–287`；`thread-heartbeat.js:292–303、405–416`。  
   **证据：**
   - 服务端成功登记，但首响应丢失：客户端没有 key，后续重试一直 409。
   - 本地 key 文件丢失：同样无法重新登记。
   - 升级前已有线程没有 KeyHash：代码明确拒绝，而非迁移。
   - 服务端 72 小时后清理线程，本地仍保留 key：携 key 的新线程又被拒绝，脚本不清除或恢复登记。
   
   **最小修复：** 增加经过 B1 归属校验的登记恢复、密钥轮换和旧记录迁移路径；明确区分遗失密钥、登记已过期与错误持有者，不能简单允许匿名重置。

3. **B3 — P2：序号分配不是原子的；会话重启路径也没有一致处理 turn ID。**  
   **Ref：** infra `92a844c`；platform `94f2192`。  
   **位置：** `thread-heartbeat.js:325–332、405–416、432–456`；`agentthreads/threads.go:234–259`。  
   **已复现：** 在内存 mock 文件系统中，从 seq=10 连续交错调用两次原分支 `stamp`，两个事件都获得 **seq=11**。两个 hook 进程可读同一旧值，后写覆盖先写；服务端会忽略其中一个事件，可能丢掉 turn_end 或新回合事件。  
   `run` 重用 `BIFROST_HEARTBEAT_THREAD` 时，启动仍无 key、固定 seq=1，不读取已有 gate。服务端 turn ID 只是存储字段，未拒绝旧回合的新序号事件。不同线程 ID 的同厂商第二会话分别保存 gate，正常互不影响；相同 ID 则共享上述竞争。  
   **最小修复：** 每线程用跨进程锁保护序号及 turn ID 分配，wrapper 共用相同登记逻辑；服务端检查回合转换规则。客户端时钟仅用于节流，静默计时使用服务端时钟，这一点正确。

4. **B4 — P2：发送前永久标记已通知，worker 重启仍可能漏掉宿主丢失推送。**  
   **Ref：** platform `94f2192`。  
   **位置：** `api/internal/agentthreads/watch.go:118–143、215–238`；`threads.go:435–443`。  
   **证据：** `claimHost` 在发送前写入 `LostNotifiedFor`；worker 在此后、notify 前退出，重启后 `HostsDue` 永远跳过同一次 loss。线程静默推送也有相同窗口：`watch.go:152–178、186–199`。正常发送成功后的重启不会重复，正常失败会 unclaim，但崩溃不会执行 unclaim。  
   **最小修复：** 区分有租期的发送认领与完成标记，重启后恢复未完成发送；外部严格一次投递需 relay 去重 ID。

5. **B5 — P2：“无 token 可见”和 wired 真实性没有实现完整。**  
   **Ref：** infra `92a844c`。  
   **位置：** `agent-config/scripts/host-heartbeat.js:54–72、81–105`。  
   **已复现：** 在纯内存 mock 中，包含 `thread-heartbeat.js`、`hook cursor` 两个子串的非法配置被判定 `wired:true`；无 token 时 report 生成了 `token:false`，但 `main` 实际发出 **0 次请求**。从未成功上报的无 token 宿主不会出现在 Console。代码还可能把仓库模板当成生效配置，不检查 hook 命令实际目标或 Codex trust。  
   **最小修复：** 宿主 heartbeat 使用独立、宿主绑定的凭证，上报各 vendor 的 reporter 凭证可用性；解析实际生效配置并检查命令、目标及信任状态。预登记宿主应能显示从未上报。

6. **B6 — P2：容量清理会删除仍活跃的监控身份，首次登记写入也未严格执行上限。**  
   **Ref：** platform `94f2192`。  
   **位置：** `agentthreads/recorder.go:87–92、139–146`；`threads.go:283–318`。  
   **证据：** 300 线程、50 宿主按最后上报时间删除最旧记录，未保护中途线程或丢失宿主。删除线程也删除 KeyHash，现有客户端随后落入 B2。首次登记直接写入，没有 prune；仅有新登记、没有 buffered 事件时，Flush 会提前返回，300 上限不生效。后端超过 900 KiB 会拒绝写入，但这不能替代业务容量处理。  
   **最小修复：** 每次写入实施上限，优先回收终态；容量不足时明确拒绝新登记，保留仍监控的线程及宿主身份。

确认 sound 的部分：

- 密钥只在首次成功登记响应返回；statefile 存 hash，公开 View 明确移除 key/hash/seq/turn ID，拒绝审计不写密钥。
- key 文件及发送文件使用 0600，key 目录和发送目录使用 0700；detached 子进程参数只有文件路径。文件读取的 reporter token 没有被脚本新增到 argv 或环境中；显式输入的 `PLATFORM_REPORTER_TOKEN` 仍会按普通进程环境继承。
- `permission_prompt`、`idle_prompt`、`elicitation` 映射到 waiting_owner；auth_success 等其他通知忽略。waiting 不触发 session-silence 推送，这是既定行为；宿主 lost 判断优先于 waiting，所以等待线程不能隐藏已登记宿主的死亡。宿主仍活着时，等待线程自身崩溃不会触发静默告警。
- 正常路径每个宿主 loss 一次推送，返回时不推送；Console 显示 host age、lost/alive、未监控 vendor 和等待原因，Needs You 计入 silent threads 与 lost hosts，排除 waiting。
- 静默默认阈值及宿主阈值均可配置。实际宿主告警使用严格 `>3m`，再加最长约 10 秒 flush 和 30 秒 watcher 周期；包注释“within 3 minutes”并非硬上限，属 **P3 文案修正**。
- hook 异常退出 0、无 stdout；首登记允许约 1 秒同步等待，整个 hook 设置 3 秒 deadline。host script 网络失败退出 0。launchd plist 不包含 token，安装器不自动加载任务。

未检查：没有运行完整 Go/race、真实 harness、launchd、Console 浏览器、网络故障或实际权限模式验收。内存检查只验证上述纯函数及 mock 行为，没有访问凭证、写文件、切换分支或调用平台/集群接口。两部分均需修复所列缺口后重新验收；不能将现有正常路径测试通过视为覆盖崩溃恢复和归属边界。