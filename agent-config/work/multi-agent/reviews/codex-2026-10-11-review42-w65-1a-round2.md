VERDICT: fix first

复核提交：`4fe6c07`（相对 `82ce71f`）。

Review 37 的四项 P2：

- **已关闭：记录字节上限。** `api/internal/questions/clean.go:87`、`notify.go:95` 先清理，再按 JSON 编码长度截断。原 18,318 字节输入在内存模型中降至 **11,068 字节**；最大记录测试补了控制字符、引号、反斜杠和非 BMP 字符。
- **已关闭：Go/TS 规范化差异。** `api/internal/notice/redact.go:10`、`mcp/platform/src/questionCanonical.ts:13` 使用相同显式字符类。23 个 TS 共享向量通过；NBSP 与普通空格现在生成不同的正确 key。
- **已关闭：存储失败后的虚假过期审计。** `api/internal/questions/notify.go:38` 检查更新结果，失败只记录 `question.store` 并返回。失败分支内存模型确认文档不变、无过期审计；回归用例位于 `limits_test.go:300`。
- **已关闭：尾随 JSON。** `api/internal/questions/canonical.go:98` 要求第二次 Decode 为 EOF；三个解析器均复用它。内存模型拒绝 `{"text":"yes"}{"action":"release"}` 及撤回、ack 的同类输入；回归用例位于 `http_test.go:108`。

**本次 diff 新增 P2：相邻 AWS key 漏脱敏。** [redact.go:25](~/agent-work/w65-1a/bifrost-platform/api/internal/notice/redact.go:25) 和 [questionCanonical.ts:16](~/agent-work/w65-1a/bifrost-platform/mcp/platform/src/questionCanonical.ts:16) 消耗右侧分隔符，第二次匹配无法再把它作为左边界。输入 `AKIAAAAAAAAAAAAAAAAA ASIABBBBBBBBBBBBBBBB`，实际 TS 输出为 `[redacted aws key] ASIABBBBBBBBBBBBBBBB`；旧规则会遮盖两者。共享 Go 脱敏器同样受影响，可能把明文带入存储或通知。应保留可复用的边界，并补相邻 key 回归测试。

契约目录 `api/internal/questions/testdata/contract/` **没有改动**；新增的是 canonical 目录的九个边界向量，均对应本轮修复。

已确认边界保持：回答仍仅 admin（`handler.go:33`）；`answer.by` 仍来自令牌 principal，仅新增清理和编码截断（`handler.go:109`、`transition.go:49`）；无动作字段；本地导入图双向隔离通过；MCP 写模式检查及 guard 未改动。未发现新增 P1，新增 P2 为上述一项。

全程只读，无 HTTP、平台或集群调用。执行了实际 TS 内存探针；Go 行为采用源码核对与内存模型，未运行需要写临时文件的 Go 测试。
END OF REPORT