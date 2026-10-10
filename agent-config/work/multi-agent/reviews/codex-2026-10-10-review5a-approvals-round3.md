PART A VERDICT: ready after fixes

审查 refs：platform `origin/w31/s0-0-int@292ac31`；infra `origin/w31/s0-0-int@9c5f973`，已核对分支指向。以下路径和行号均属于指定提交，证据均为静态代码检查，未做动态复现。

未发现仍存的 P1，**不触发自动重试与创建恢复部分的拆分条件**。剩余三个 P2 应在 PROD 前修复。本结论接受 BRIEF 已确定的发布约束：旧、新审批 writer 不重叠；没有验证该发布流程的实际执行。

上轮报告发现 1–7 的状态：

| 发现 | 状态 | 本轮代码依据 |
|---|---|---|
| 1：匹配 annotations 即收养 | 已修复 | `actions/identity.go:60–72`；`workactions/service.go:295–304、351–374、470–532`；`delivery/service.go:363–393`。GET 已存在和 AlreadyExists 都拒绝收养，包括身份完全匹配的对象。 |
| 2：混合版本 writer | 部分修复 | `approvals/store.go:1–2、55–118、194–240` 保留文档和 Approval 顶层未知字段，并写明不得混跑版本；嵌套字段仍有遗漏，见下文。部署半由协调者处理。 |
| 3：重复 unknown 通知 | 已修复所列路径 | `approvals/execution.go:209–266` 区分已经 unknown 与本次进入 unknown；renew 后 uncertain finish 不再重复发事件。另有零通知路径，见下文。 |
| 4：最终写失败丢结果、返回成功 | 部分修复 | `approvals/execution.go:131–188、274–286`；`service.go:434–445`。失败返回 500、无未提交完成事件，并保留结果；读取故障仍会提前删除结果。 |
| 5：日志与执行器审计未脱敏 | 已修复 | `approvalnotify/notify.go:294–297、334`；`actuation/audit.go:72、98`；`delivery/handler.go:88`；`workactions/handler.go:35–44`。 |
| 6：EOF 等 create 错误误判 | 已修复 | `actions/createclass.go:22–49`；所有本批创建恢复路径均调用它。新增注册 executor EOF 测试；未运行。 |
| 7：提醒可能重复送达 | 已修复说明要求 | `approvals/notice.go:63–69`；`approvalnotify/notify.go:67–68` 明确重试可能重复送达。没有增加 relay 去重。 |

剩余发现：

1. **P2 — 部分 (a)：读取故障会删除已经保留的执行结果。**  
   **Ref / 位置：** platform `292ac31`，`api/internal/approvals/execution.go:178–181`；`api/internal/approvals/notice.go:309–314`。  
   **证据：** `finishPlatform` 最终写失败后将结果放进 `held`。下一轮 `flushHeld` 调用 `s.find`，而 `find` 把存储读取错误转换为 `ok=false`；`flushHeld` 随即执行 `forgetFinish`。因此，即使租约仍有效，一次短暂读取故障也会永久丢掉已完成结果。存储恢复后无法重试该完成写入，记录最终按租约规则成为 unknown。不会因此再次执行动作，但不满足“保留结果，只重试写入”的要求。  
   **最小修复：** 读取接口区分错误与记录不存在；读取出错保留 `held`。仅在成功读到记录不存在、租约已更换或状态已完成/过期时删除。补“最终写失败 → 下一轮读失败 → 恢复后完成写入”的测试，执行次数仍为一。

2. **P2 — 部分 (d)，影响 (a)/(b)：未知字段保留不覆盖 Execution 和 Delivery。**  
   **Ref / 位置：** platform `292ac31`，`api/internal/approvals/store.go:101–113、222–240`；`api/internal/approvals/types.go:75–113`。  
   **证据：** `parseApproval` 只收集 Approval 顶层未知键；`execution` 和 `deliveries` 都被视为已知键，其内部按固定结构解码。`Execution`、`Delivery` 没有未知字段容器，随后 `json.Marshal(a)` 会删除嵌套未知键。例如输入中的 `execution.new_flag` 或 `deliveries[0].new_flag`，即使只更新另一条审批，也会在整份文件重写时消失。顶层保留测试没有覆盖这个情况。  
   **最小修复：** 为 Execution 和每条 Delivery 增加原始未知字段保留，或递归合并已知字段与原始对象。测试未修改记录中的两类嵌套字段保持原值。无版本重叠的发布约束降低了本次风险，但不能把当前实现描述为完整的未知字段保留。

3. **P2 — 部分 (a)/(b)：结果接口有进入 unknown 却不通知的路径。**  
   **Ref / 位置：** platform `292ac31`，`api/internal/approvals/execution.go:693–715、756–759`；`api/internal/approvals/handler.go:239–240`。  
   **证据：** 当 running 租约超过 grace、尚未被 sweep/renew 处理时，同一租约提交 `started=false` 和有效 refusal：代码生成 `approval.unknown`，将 unknown 存入文件，并设置 409 的 `bad`。函数随后直接返回 `*bad`，没有携带 `evs`；handler 消费到空事件。后续 sweep 看到已经 unknown，也不会补发。因此该转换产生零次通知。此遗漏在 round 2 已存在，本轮仍未覆盖。  
   **最小修复：** 成功存储后返回 `bad` 时也附上本次已提交事件。补上述顺序的 handler 测试，要求一个 unknown 通知，后续请求不重复通知。

确认 sound 的部分：

- **创建结果：** 在本批受审的 PipelineRun/Job 创建恢复路径中，未发现平台没有收到本 attempt 的 Create 成功却报告 executed 的路径。已有对象一律 unknown；Create 的 EOF、reset、timeout、5xx 和未分类错误一律 uncertain。迟到成功仍要求同一 lease 的实际执行结果。
- **确定拒绝列表：** 只有 APIStatus 的 400、403、404、422，以及排除 AlreadyExists 的 409。未发现这几个直接创建拒绝分支会把已成功创建误判为可重试拒绝；当前调用点也没有先把 Create 错误包装为 Transient 再绕过分类器。
- **存储入口：** 更新、编号、pruning、retry loop、claim/heartbeat/result 和通知记录都通过 `store.update → parse → prune → marshal`。保留下来的记录及文档顶层未知字段随该链保留；嵌套例外见发现 2。
- **最终写失败：** 调用者收到 HTTP 500，包含存储错误、审批 ID 和可读取的持久化状态；不会得到未落盘的 executed 成功。正常恢复路径只重试完成写入，不再次调用动作；超过 grace 后变为 unknown。
- **通知与脱敏：** renew → uncertain finish 的重复通知已消除。unknown 推送现在显示脱敏后的实际原因。通知失败日志和执行器审计详情在输出前经过统一脱敏。
- **规范行与聊天审批：** U+2028/U+2029 转义和完整 params hash 校验保留；MCP tier D 列表仍删除 `approval_line`，服务端仍拒绝 tier D 的 chat 批准。
- **与 round 2 比较：** 未发现本轮增加误执行或重复创建风险。取消收养、扩大 uncertain 分类和最终写失败返回错误都更保守；新保留结果机制的读故障缺口见发现 1。

未检查：未运行 Go build/vet/test/race、MCP/Console 验收、真实网络或存储故障测试、relay/手机送达、worker 崩溃及发布切换演练。新增测试只阅读了源码，不声称通过或已复现。未读取凭证目录、env/token 文件或 kubeconfig；未 checkout、创建 worktree、写文件、提交、推送或调用平台/集群写接口。