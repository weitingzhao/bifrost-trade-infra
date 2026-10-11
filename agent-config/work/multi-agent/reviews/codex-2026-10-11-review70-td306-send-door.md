# Codex 复核 70 — TD-306 最后一轮：发送那道门整条扣下（`da7b774..d7802d0`）

2026-10-11 13:28 CDT · 只读

统筹方处理：可以合并。没有必须改和应该改的；三处次要的和「别的推送出口没有这道检查」记成 TD-311。合到当前主线时与 TD-307 的测试有一处冲突，已解，合并结果重跑验收。

---

VERDICT: safe to merge
未发现本差异引入的 P1/P2；以下 P3 可后续处理，没有阻止合并的理由。

P3 — `api/internal/notice/hide.go:85`：隐藏字符集合仍不完整。
最小复现：标题含 U+2800、U+3164、U+FFA0、U+17B4/U+17B5 或 U+206A–U+206F 时，HasHidden 返回 false。
最小修复：补充这些码位及测试；可同时补充 U+180B–U+180D/U+180F、U+E0100–U+E01EF。未发现这些遗漏能改变服务器动词或编号；TASK-5 指定的集合全部覆盖，tag 字符已覆盖。

P3 — `api/internal/notice/hide.go:118`：日志 id 并非全部由服务器生成。
最小复现：线程键 `claude/agent-written-text` 或普通代理自报主机名，在扣留推送时原样进入日志。
最小修复：对线程/主机标识使用服务器生成的摘要。现有检查会清空含隐藏字符或非法 UTF-8 的 kind/id；普通代理文本仍可进入，新日志也未做秘密脱敏。既有 watcher 已记录这些标识，因此不是本轮新增的 P1/P2。

P3 — `api/internal/approvalnotify/door_test.go:146`：大语料验证的是 Posted，没有验证假继电器收到的内容。
最小复现：仅在 Send 的序列化阶段修改干净正文，大语料测试仍会通过；线程和问题的大语料测试同样如此。
最小修复：增加有界的 Send→假继电器语料检查，并逐字段注入。当前每种通知的扣留测试确实断言假继电器收到的标题、正文、URL 和优先级。

上游核对：指定 redactor、MCP canonical、问题契约、审批类型及 console 的差异为空。
Compose、Message、HostMessage、noticeTitle/noticeBody 及其组合逻辑未改变；没有标题或正文输出改变的 composer。
“所有输入相同”的依据是组合代码及依赖未变；测试只提供固定样例和有限语料证据，并非全输入证明。createdNotice 仅新增发送元数据。

入口核对：审批六种 kind、问题、线程、主机和发布策略通知均经过 notice.Send。
它不是整个仓库唯一推送门：`api/internal/alertrelay/relay.go:398` 的 publish 独立发送 ntfy；Alertmanager、心跳恢复/缺失及直接调用 `/alerts/notify` 均无该谓词。
peer relay 监视在 `scripts/agent/peer_watchdog.sh:40` 直接 curl ntfy，正文来自配置 URL 和时间；上述路径本轮未改，不覆盖于本轮代理通知门。

回退核对：审批零编号使用服务器生成的 appr_id；问题使用服务器编号 Qn；线程/主机使用固定 `Look · thread`，不带线程键或主机名。
正文固定；回退缺失或自身触发谓词时使用 `Notification withheld`。点击 URL 保持服务器 id 深链或固定页面。
非法 UTF-8 在 JSON 编码前对实际待发送的标题/正文检查；上游已替换成 U+FFFD 的输入维持原行为。

投递核对：accepted/failed/skipped、重试、提醒日程及去重逻辑未改；去重键不使用回退标题，不会把不同审批合并。
race 无空语料或跳过循环：差分随机段为 40,000，干净语料为 4,000，Short 模式仍为 24；非 race 保留 200,000/100,000。
未重跑测试：遵守只读及禁止 HTTP 调用限制；协调者的 race 通过结果未作为本人实测时间。
无新增外部依赖；notice 仅依赖标准库，未引入 actions、approvals 或 questions。
END OF REPORT