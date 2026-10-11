# Codex 复核 64 — TD-306 重开后第 1 轮（`da7b774..b0e4c97`，分支 `w31/td-306-c`，已放弃）

2026-10-11 12:20 CDT · 只读

统筹方的处置：先改；这个分支放弃。我的验收在这一轮没过（竞态检查 600 秒没跑完；审批记录多了一个字段，Console 的契约测试挂了），复核另找到四处入口仍然先清理后判断。「在每个入口判断」意味着要动每个入口、审批记录和接口形状，对一条只有一句话的债来说面太大。最后一轮改成最小的做法：只在推送离开进程的那一道门上判断，文字里有隐藏字符就整条换成只有服务端文字的通知，上游一行不动（分支 `w31/td-306-d`）。

---

VERDICT: fix first

P2 — `api/internal/notice/jsonhide.go:23`、`api/internal/approvals/handler.go:67`：原始检查与入口解码规则不同，可漏判不配对 surrogate。
复现：创建 cordon_node，name=`n`，使用 `"Reason":"public\uD800"`；结构体解码接受大写键，hold 却只查 `reason`，通知显示 `public�`。标准请求后追加 ` {}` 也会被入口接受，却使原始检查返回空 hold；heartbeat/result 同样受影响。
最小修复：让原始检查和业务解码共用同一 JSON 文档及字段匹配规则，并拒绝尾随文档。

P2 — `api/internal/approvals/notice.go:85`、`api/internal/notice/jsonhide.go:36`：数组参数未在清理前判定，surrogate 检查也不遍历数组。
复现：ensure_kubeconfig_secret 的 `namespaces=["bifrost-stg\u2028"]` 经 `normalize.go:210` trim 后，env/key param 显示 `bifrost-stg`；改为 `["public\uD800"]` 则显示替换字符，均不是 marker。
最小修复：递归检查原始数组成员，记录并传递其派生 summary/env/key-param 的 hold，避免依靠清理后的字符串反推来源。

P2 — `api/internal/approvals/handler.go:287`、`api/internal/threadtitles/threadtitles.go:167`：另外两条真实入口仍先 trim，再判断。
复现：SessionHeader=`cursor\u2028`，通知显示 `cursor`；ReportTranscript title=`quota\u2028`，Look 显示 `quota`。`noticeHoldFrom`/`applyLineageTitle` 接到的已不是原值。
最小修复：在 header 和 lineage 标题首次进入时保存 hold，并传到通知链。

P2 — `api/internal/agentthreads/threads.go:357`、`api/internal/agentthreads/view.go:60`：隐藏字段原文直接进入 Console 列表。
复现：正常 heartbeat 的 title=`safe token=s3cr3\u200btvalue`，或 160 个 `a` 后加 U+202E；Validate 保留原文并跳过裁切，列表 MarshalJSON 原样输出。host 列表同样如此（`view.go:97`）。
最小修复：列表输出按 hold 显示 marker；保留内部身份键时，另行生成安全展示值，并独立执行长度限制。Look/host 通知本身已有 marker 保护。

P3 — `api/internal/actions/describe.go:175`：用字符串相等判断 fallback，意外改变审批摘要和 approval_line。
复现：cordon_node name=`n\nsecond`，reason=`Cordon node n\nsecond`；旧摘要保留两行，新摘要只剩第一行。
最小修复：显式记录是否使用 reason fallback，保持原 Describe 行为。

Review 61：P1 已关闭（`notice/field.go:63–67`）；原始值判定 P2 部分关闭；隐藏集合 P2 的码位/无效 UTF-8 检查已补齐，但 JSON 入口仍有上述漏洞。
按源码链重算：fake-end PEM 得到完整 `[redacted private key]`；标准入口的 ZWSP Summary、RTL Error、超长 RTL title、软连字符字段均扣留；标准完整 JSON 的无效 UTF-8/不配对 surrogate 有 hold。
顺序仍未全面满足：`agentthreads/threads.go:359–360` 先 trim 再 Field；审批 reason/params 也先 trim/Normalize。问题路径仍在 `questions/clean.go:16–17` 先 strip 再 Redact，按 brief 已停止该部分。
clean 测试确实逐字节比较 `normalise(redactAt8b3259a(raw))`（`field_test.go:34–48`）；差异分支为 ſecret/ſEcret 的普通及 TAB 等号形式，共四种。
审批 hold 不参与 params_hash/approval_line 计算，不能由请求体直接设置；list/get 新增 `notice_hold`，零值 struct 仍输出 `{}`。Console/MCP 现有解析可容纳；旧记录加载为零值，旧 binary 会保留未知字段，回滚可读。
发送门只拒绝、不改写；已检查固定服务器文案无 TAB。审批/问题保留记录并存失败投递；heartbeat 保留记录、计失败并释放 claim。
但永久拒绝仍会按循环重试：heartbeat 每 30 秒重试，审批 reminder 全失败后也释放 claim；没有针对 `unclean text` 的终止处理。
两个冻结源码逐字节相同；25 个 contract 文件及 canonical vectors 无 diff；notice 生产依赖未引入 actions/approvals/questions。
验证仅含只读源码、git blob 比较及内存 Python 复现；未运行会写缓存或调用 HTTP 的 Go/npm 测试，未改文件、未调用 HTTP。

END OF REPORT