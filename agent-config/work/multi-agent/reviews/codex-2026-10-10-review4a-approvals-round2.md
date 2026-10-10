PART A VERDICT: ready after fixes

审查 refs：platform `origin/w31/s0-0-int@7f6d81e`；infra `origin/w31/s0-0-int@9c5f973`。已核对分支指向。以下行号属于指定提交；除明确注明的内存检查外，证据均为静态调用链检查。

原问题的修复状态：

| 项目 | 判断 | 代码依据 |
|---|---|---|
| A1 对象收养 | **部分修复** | `actions/identity.go:63–80` 要求完整 approval ID、attempt、params hash；仍未核对 spec，见发现 1。 |
| A2 delivery 执行链 | **已修复原问题** | `delivery/service.go:266–268、384–405`；`delivery/handler.go:89–98`；`server/actions_wire.go:425–429`。注册 executor 测试覆盖实际 handler 链。 |
| A3 租约过期 | **部分修复** | `approvals/execution.go:149–200、311–323` 阻止 grace 后重排并记录续租错误；重复 unknown 和结果持久化仍有缺口，见发现 3、4。 |
| A4 提醒认领 | **已修复崩溃后永久占用问题** | `approvals/notice.go:89–149、350–363` 增加 claim ID、60 秒 expiry 和匹配检查。混合版本及慢 relay 的边界见发现 2、7。 |
| A5 脱敏 | **部分修复** | 审批审计详情统一经过 `service.go:594–605`；delivery error 先脱敏再裁剪。旁路日志、执行器审计仍有遗漏，见发现 5。 |
| A6 推送白名单 | **已修复原问题** | `actions/describe.go:32–67、247–270`；`approvalnotify/notify.go:148–155` 在发送时重新过滤历史记录。 |
| A7 规范行 | **已修复所列问题** | `approvals/line.go:10–16、75` 转义 U+2028/2029，并说明短摘要边界；MCP `registerApprove.ts:143–151` 移除 D 行的 `approval_line`。 |
| 首次 unknown 推送 | **已修复原遗漏** | `approvals/service.go:431–436` 统一消费首次执行事件；handler 不再针对 failed 单独补发。 |

1. **P1 — A1：annotations 匹配仍可收养不同 spec 的对象。**  
   **Ref：** platform `7f6d81e`。  
   **位置：** `api/internal/actions/identity.go:63–80`；`workactions/service.go:305–318、374–378、503–507`；`delivery/service.go:364–373、392–400`。  
   **证据：** `Adopt` 只接收 annotations，没有预期或实际 spec。三个身份字段全部匹配便返回成功，最终审批可以成为 `executed`。更直接的证据是 `workactions/adopt_identity_test.go:121–130`：测试只改 annotations，保留 `readyPlan` 的 `mode=plan` spec，却要求 Apply 收养成功。对象被修改、或另一平台版本根据相同参数构建不同 spec，均未被检测。未运行该 Go 测试。  
   **最小修复：** GET 和 AlreadyExists 共用身份及预期 spec 校验，比较稳定的执行字段，排除服务端默认值；不匹配进入 unknown。增加“身份完全匹配、spec 不匹配”的反例测试。

2. **P1 — 新旧 API 共用审批状态文件，滚动发布不安全。**  
   **Refs：** platform `7f6d81e`、旧 main `11ebb8c`、round 1 `ea232d3`；infra `9c5f973`。  
   **位置：** 旧 main `api/internal/approvals/types.go:18–35`、`store.go:48–72`、`service.go:185–227`；新版本 `store.go:47–55、73–82`；round 1 `notice.go:104–127`；infra `k8s/overlays/platform-prod/replicas-ha.patch.yaml:12–20`。  
   **证据：**
   - 当前 main 的旧 API 解码后重新序列化，会丢掉 `number`、`last_number`、runner、execution、deliveries、approved line 等新字段；旧批准路径还允许仅凭 channel 执行，没有新版本的回显和租约保护。
   - 即使只混跑 round 1 与 round 2，旧 `Delivery` 类型也会丢掉 `claim_id` 和 `claim_expires_at`。新 worker 随后把它当过期认领；旧 finish/release 又按 kind 删除认领，能删除新 worker 的 claim。
   - 新版本可以解码旧记录；反方向的写入破坏不能靠 CAS 冲突重试解决。部署仍允许 API 新旧 Pod 重叠。  
   **最小修复：** 本次升级采用明确的停止旧审批写入、排空在途执行、停止旧 worker、再启动新版本的切换流程，确保没有混合 writer；若必须保持滚动发布，先部署保留未知字段且兼容新状态机的过渡版本。补双版本交错写入验收。

3. **P2 — 续租和执行完成仍会重复推送 unknown。**  
   **Ref：** platform `7f6d81e`。  
   **位置：** `api/internal/approvals/execution.go:285–304、186–193`；`notice.go:281–301`。  
   **证据：** renew 超过 grace 后存储 unknown 并立即消费 `approval.unknown`。随后同一执行器返回 uncertain，`finishPlatform` 在已经 unknown 的分支再次产生该事件。此路径不设置 `LateResult`，通知消费层也没有该事件的去重检查。正常首次超时测试未覆盖这个顺序。  
   **最小修复：** 仅在实际进入 unknown 时发出通知；已经 unknown 时可以更新错误详情，但不重复产生转换事件。测试 renew → uncertain finish 的顺序，要求一次通知。

4. **P2 — `finishPlatform` 存储失败会丢失执行结果，并返回未落盘的成功。**  
   **Ref：** platform `7f6d81e`。  
   **位置：** `api/internal/approvals/execution.go:171–172、204–211`；`service.go:433–438、493–507`。  
   **证据：** 写回失败时，只给内存中的 `out.Error` 加存储错误，仍返回已计算的 status、result 和 events。成功执行因此可以返回 HTTP 200 / `executed`，但持久化记录仍为 running；成功响应的 `decisionBody` 还不返回该存储错误。后台 retry 路径同样消费这些未提交事件，没有保留结果以便重新写回。  
   **最小修复：** 将持久化错误显式返回，禁止把未提交转换当成功事件消费；保留并重试同一 lease 的结果写入，不能重新执行动作。增加“执行成功后最终状态写入失败”的验收。

5. **P2 — A5 的统一脱敏边界仍有旁路。**  
   **Ref：** platform `7f6d81e`。  
   **位置：** `api/internal/approvalnotify/notify.go:287–289`；`delivery/handler.go:81–87`；`actuation/audit.go:67–89`；`server/server.go:200`。  
   **证据：** notify 的失败闭包先把原始 transport error 写入 slog，再生成脱敏 Delivery。注册 delivery executor 使用带 audit 的真实 handler，该 handler 在审批统一审计之前把 `resp.Message` 原样写入 audit；`AuditLog.Record` 又原样保存并输出 detail。Kubernetes/client 错误包含 `token=SYNTHETIC_SECRET` 时，这些旁路不会经过审批的 Redact。  
   **最小修复：** slog 写入前脱敏；执行器 handler 的审计详情也必须经过脱敏边界，或在审批执行上下文中由统一审计负责。用带 audit 的注册 executor 测试，检查持久化审计和日志。

6. **P2 — uncertain create 分类仍遗漏非 timeout 的响应丢失。**  
   **Ref：** platform `7f6d81e`。  
   **位置：** `api/internal/delivery/service.go:402–409、1081–1086`；`workactions/service.go:217–242`；`server/actions_wire.go:464–474`。  
   **证据：** 分类只识别 Kubernetes timeout/server-timeout 和 context cancellation/deadline。Create 返回 `io.EOF`、`io.ErrUnexpectedEOF` 等响应中断错误时，会走普通失败路径；这些错误不能证明创建没有发生。HTTP 504 映射不能补救，因为 delivery 将这种错误包装为 502。未模拟真实网络中断。  
   **最小修复：** 在 create 边界保留传输不确定性，必要时按确定性名称读取并核验对象；仍无法确定时进入 unknown。增加“对象已创建，响应以 EOF 丢失”的注册 executor 测试。

7. **P3 — 提醒恢复提供重试能力，不能保证外部严格一次送达。**  
   **Ref：** platform `7f6d81e`。  
   **位置：** `api/internal/approvalnotify/notify.go:47、291–296、306–308`；`approvals/notice.go:73–82、213–221、350–363`。  
   **证据：** HTTP client 超时为 10 秒，小于 60 秒认领租期，正常慢请求不会一直占用认领。但 relay 已接受请求、响应超过 10 秒时，客户端记录失败并释放 claim，下一轮可以再次发送。请求没有稳定投递去重 ID。无 expiry 的旧 claim 在新版本中立即可重领，因此能恢复崩溃遗留，也可能与仍在发送的旧 worker 重复。  
   **最小修复：** 明确记录这种重试语义；若要求外部一次送达，relay 接受并去重稳定的 approval/kind 投递 ID。旧 claim 的迁移同时排除仍活跃的旧 worker。

确认 sound 的部分：

- 没有 annotations、只有部分 annotations、任一身份字段不匹配，均不能被审批执行路径收养；完整 ID 和 hash 没有为 label 长度而截断。
- delivery 与 workactions 共用 `ObjectName`；注册 executor 保留 context 中的 approval、attempt 和 hash。`start_pipeline_uncertain_test.go:98–161` 覆盖该实际调用链，未只测试 `work.Apply`。
- release-window 的 `who` 检查仍在创建及收养之前：`delivery/service.go:231–234`；`release_window.go:172–180`。
- grace 后 transient refusal 不再重排；成功或明确失败的迟到结果仍可按原 lease 完成一次。
- 当前注册 handler 中，504 的明确产生位置是 delivery 的 uncertain 分支。全局“504 → unknown”偏保守，当前未发现另一个实际 504 producer 导致误分类；它也不能代表所有不确定创建错误。
- 发送时的逐动作白名单会过滤历史 `args`、`command` 和 passthrough key。没有清单的动作仍通过 action、tier、summary 和已有 env 说明请求；例如 CNPG backup 和 owner command 有独立摘要。
- 脱敏规则没有普遍删除普通 approval ID、hash 或 run name。unknown 推送目前不显示 `Item.Error`，并固定称为 executor lease 丢失，无法准确说明创建超时或对象冲突；属于通知文案及信息量限制，应显示实际脱敏原因。
- Console 契约测试检查真实 `HandleList` 的 `{"approvals": out}`，不是 tautology。**已运行内存检查**：原源码匹配；把该 envelope 改成 `{"items": out}` 后不匹配。它仍是源码契约检查，不是 HTTP 集成测试。
- **已运行 MCP 原 map 分支的内存检查**：D 行有 ID、无 ID 两种情况下都不返回 `approval_line`；C 行保留它。
- 新 API 配旧 Console 时，缺少 canonical line/hash 的 pending 批准返回 409，形成暂时不可批准，不会降级执行。此结论不覆盖发现 2 的混合 API writer。

未检查：没有运行完整 Go/build/vet/race、MCP/Console 验收、Owner 执行器脚本、真实 relay/手机送达、集群或滚动发布演练；没有运行存储故障、网络 EOF、worker 崩溃的动态复现。未读取凭证目录、env/token 文件或 kubeconfig，未切换分支、写文件、提交、推送或调用平台/集群写接口。