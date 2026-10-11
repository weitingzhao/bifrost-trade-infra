# Codex 复核 61 — TD-306 第 3 轮（`da7b774..e7a4935`），基线是主线 `8b3259a`

2026-10-11 10:44 CDT · 只读 · 分支 `w31/td-306-b`

统筹方的处置：**这条线停**。还有一处必须改（把空白归一化放在脱敏之前，会让私钥块的脱敏提前结束、露出尾部）和两处应该改（检查隐藏字符的位置在上游已经清理和截断之后；隐藏字符的集合不全）。停线条件是第 3 轮开工前写下的，照此执行：分支 `w31/td-306-b` 不合并。其中只动测试的那个提交（对比测试加下限和各类命中数，复核认为没问题）单独摘到 `w31/td-307-b`，随提问入口一起进主线，关掉 TD-307 的 (b)。TD-306 留在台账，条目里写明三轮试过什么、下一次怎么做。我的验收在这一轮是通过的；这三处都是复核找到的。教训第 75 行。

---

VERDICT: fix first

P1 — `api/internal/notice/push.go:24`：规范化可使 PEM 脱敏提前结束，泄露原来隐藏的尾部。
复现：`PushField("-----BEGIN PRIVATE KEY-----X-----END\nPRIVATE KEY-----QQQQQQQQ", true)` 输出 `[redacted private key]QQQQQQQQ`；main oracle 对原文只输出 `[redacted private key]`。正文模式把该 LF 换成 TAB 或 FF，同样泄露。
最小修法：先检查原始整字段是否应扣留；否则先对原文 `Redact`，再规范化输出，并更新测试合同；保持 redactor 不变。
模式核对：PEM 的 `[A-Z ]` 和 `PRIVATE KEY` 区分字面空格；其内容匹配所有字符，`$` 无多行模式。其余六条没有区分这些空白的字面空格、换行或非跨行 `.`。普通 PEM 标题能隐藏，伪结束标记是反例。

P2 — `api/internal/approvalnotify/notify.go:165`、`api/internal/questions/notify.go:56`、`api/internal/agentthreads/threads.go:503`：扣留检查发生在上游已丢失隐藏字符之后，不能保证原始字段整段扣留。
复现：`noticeItem` 将 Summary=`safe token=s3cr3\u200btvalue` 先变成 `safe token=[redacted]`，Compose 展示原字段前缀；Error=`public\nhidden\u202e` 被 `noticeItem` 先截成 `public`。
Answer 的原始 Title=`quota\u202e` 经 canonical `clean` 后成为 `quota`，新函数无法扣留；Beat Title=`strings.Repeat("a",160)+"\u202e"` 也会先截掉隐藏字符，再展示前缀。
最小修法：在原始字段首次被清理、脱敏或截断前保存推送扣留标志，并让通知使用它；保留 canonical/redactor 的现有合同。

P2 — `api/internal/notice/push.go:58`：隐藏字符集合不足，发送门使用同一集合，无法补救。
复现：Title=`to\u00adken=QQQQQQQQ` 不扣留、不脱敏，发送门接受；软连字符可让手机显示为 `token=QQQQQQQQ`。
U+00AD、U+034F、U+115F/U+1160、U+180E、U+2061–U+2064、U+FE00–U+FE0F、U+E0000–U+E007F 均可能隐藏字符或影响呈现，在本保守合同下应扣留；目前全部缺失。TASK-3 明列的集合则完整。
最小修法：扩充共享谓词并逐码点测试。另加 UTF-8 有效性检查；当前 Go range 将无效序列视作 U+FFFD 而放行，不配对 surrogate 应在 JSON 解码替换前拒绝。

核对结果：指定两个 redactor 文件的 diff 为空；新 wrapper 的规范化仍改变了实际匹配，见 P1。
直接检查 Compose、Look、host、Answer 的输出字段路径，未发现其他未经 PushField 的 agent 字段；审批 fallback ID 为服务器生成，Tier 只选择固定文本。
对真正到达 PushField 的已列隐藏字符，整段替换发生在裁切前；摘要复用和 host 线程名路径均处理，裁切不会切开已知 marker。
`notice.Send` 拒绝而不修复；服务器正文含 TAB 也会返回 `unclean text` 和 failed delivery，且不发 HTTP。审批 Send 吞掉 error 但保存失败投递，创建仍返回 201，Console 可见；Look/host 收到错误后释放 claim 重试。
测试：clean 测试对 200,000 个 seeded 输入逐字节比较 `Redact(normalised)`，并非原文 oracle，所以不能发现 P1；dirty 测试是 200,000 个确定性组合，只覆盖列出的集合。
逐 kind 表覆盖六种审批、Look、host、Answer，但直接构造对象，漏测上游清理链；混合隐藏字符样本也掩盖了 U+180E 缺失。
pins 确实只改 Decide/Check 的摘要为 marker；差分测试增加 enforced≥200,000 和五类命中断言。
审查保持只读、无 HTTP；未运行会写缓存或调用本地 HTTP 的 Go 测试。PEM 反例用读取 oracle 模式的内存 Python 复现；Alertmanager 直推与 click URL 按 brief 排除。
END OF REPORT