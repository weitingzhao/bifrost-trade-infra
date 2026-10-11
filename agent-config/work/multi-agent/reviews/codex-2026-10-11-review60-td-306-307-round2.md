# Codex 复核 60 — TD-306 / TD-307 第 2 轮（`ac68be6..8f3079b`），基线是主线 `8b3259a`

2026-10-11 10:08 CDT · 只读 · 分支 `w31/td-306-307`（已放弃）

统筹方的处置：先改；这个分支放弃，第 3 轮从 `da7b774` 另起分支 `w31/td-306-b`，用掉统筹方的一次延期。统筹方在复核回来之前已经拿主线和分支实测出同样的两处（见教训第 74 行）：共享的脱敏函数被改弱了，它还用在审计记录和存下来的文档上。复核建议合并两次脱敏的区间；没有采纳——那又是在脱敏函数里动手。第 3 轮的规则：脱敏函数一个字节不碰；一段文字里有隐藏字符就整段不显示，没有的就和线上逐字节一样；发送的那道门只检查、不改写。复核另指出 `alertrelay` 直接发布、不经这道门：那是告警规则写的文字，不是 Agent 写的，不在范围内。

---

VERDICT: fix first

- **P2 · `api/internal/notice/push.go:12`**：先替换会破坏第二次识别所需的原文。最小复现 `Bearer abcdefgh\u202eijkl`：main 原文输出 `Bearer [redacted]\u202eijkl`，main 清洗后输出 `Bearer [redacted]`，PushText 却输出 `Bearer [redacted]ijkl`，尾段上手机；再次 PushText 仍不变。最小可靠修复：在替换前分别识别原文、清洗原文的脱敏区间，映射并合并区间后统一替换。
- **P2 · `api/internal/notice/redact.go:291`、`mcp/platform/src/questionCanonical.ts:287`**：新增控制字符终止条件降低 Redact 的保护范围。`token=\u200babc` 在 main 为 `token=[redacted]`，新 Redact 原样返回，暴露完整 `abc`；`token=abc\u200bdef` 则露出后缀。最小修复：恢复 main 的值终止条件，把清洗保护放在上述区间合并中。两项均无法仅回退 `43031f6` 消除；第一项属于三步组合缺陷，第二项由 `8f3079b` 引入。

下面每行依次为 main Redact(原文)、main Redact(清洗原文)、PushText；`\u200b`、`\u202e`、`\t` 表示实际码位。`Aₙ` 表示恰好 n 个 A，标题与正文旗标在这些输入上输出相同。
| 输入 | main 原文 | main 清洗后 | PushText |
|---|---|---|---|
| `token=s3cr3\u200btvalue` | `token=[redacted]` | `token=[redacted]` | `token=[redacted]` |
| `token=\u200bs3cr3tvalue` | `token=[redacted]` | `token=[redacted]` | `token=[redacted]` |
| `token=s3cr3tvalu\u200be` | `token=[redacted]` | `token=[redacted]` | `token=[redacted]` |
| `token=s3\u200bcr3tval\u200bue` | `token=[redacted]` | `token=[redacted]` | `token=[redacted]` |
| `password=abc\tdef` | `password=[redacted]\tdef` | `password=[redacted]` | `password=[redacted]` |
| `password=\tabcdef` | `password=\t[redacted]` | `password=[redacted]` | `password=[redacted]` |
| `password=abcde\tf` | `password=[redacted]\tf` | `password=[redacted]` | `password=[redacted]` |
| `password=ab\tcd\tef` | `password=[redacted]\tcd\tef` | `password=[redacted]` | `password=[redacted]` |
| `Bearer abcdef\u202eghijkl` | `Bearer abcdef\u202eghijkl` | `Bearer [redacted]` | `Bearer [redacted]` |
| `Bearer \u202eabcdefghijkl` | `Bearer \u202eabcdefghijkl` | `Bearer [redacted]` | `Bearer [redacted]` |
| `Bearer abcdefghijk\u202el` | `Bearer [redacted]\u202el` | `Bearer [redacted]` | `Bearer [redacted]l` |
| `Bearer ab\u202ecdefghij\u202ekl` | `Bearer ab\u202ecdefghij\u202ekl` | `Bearer [redacted]` | `Bearer [redacted]` |
| `AKIAA₈\u200bA₈` | `AKIAA₈\u200bA₈` | `[redacted aws key]` | `[redacted aws key]` |
| `AKIA\u200bA₁₆` | `AKIA\u200bA₁₆` | `[redacted aws key]` | `[redacted aws key]` |
| `AKIAA₁₅\u200bA` | `AKIAA₁₅\u200bA` | `[redacted aws key]` | `[redacted aws key]` |
| `AKIAA₂\u200bA₁₂\u200bA₂` | `AKIAA₂\u200bA₁₂\u200bA₂` | `[redacted aws key]` | `[redacted aws key]` |

Review 59：两个具体 P2 复现已关闭，见 `agentthreads/threads.go:496`、`approvalnotify/notify.go:164`；重算分别得到 `xbearer [redacted]`、`x×80 + " [redacted aws key]"`，裁切前已隐藏。总体清洗保护仅部分关闭，见新 P2。
原 P3 已关闭：`notice/redact_linear.go:115`、`:262` 预计算运行长度并计入扫描；重跑 TS 的 n=1000/2000/4000 得到 48160/96160/192160 步。计数仍不是所有正则工作的逐项计量。
保护规则应逐字符隐藏 main 在原文及清洗原文中隐藏区域的并集；当前组合不满足。`push_property_test.go:161` 只检查完整 SECRET，故后缀泄露仍能通过，幂等也不能证明安全。
线性扫描本身未发现新增泄露：重叠 xoxb、ghp、eyJ、长词内前缀、末尾匹配及 ſ/K 的 Go/TS 处理对应；Go 非法 UTF-8 按 RuneError 边界处理，TS 无等价原始字节输入。
252,197 条差分输入主要覆盖 keyword/Bearer/Basic；随机生成器不生成 JWT/AWS/GitHub/Slack，后者只有少量固定样例，缺少系统重叠、控制符及非法 UTF-8 覆盖。
调用链：六种审批、Look/Host、Answer 的可显示文本均在裁切前及组合后处理；Runner 经标签转换后统一处理，Send 再处理标题正文，通用 Notify 也覆盖。ClickURL 不处理；既有 `alertrelay/relay.go:294`、`:398` 直接发布及 Alertmanager 路径不经 PushText。
本轮钉住期望未修改；问题存盘清洗路径、canonical 向量及 25 个 contract 文件未改，notice 生产依赖无 actions/approvals/questions。仅做只读源码核对与内存 TS 复现；未运行需写缓存的 Go/npm 全套测试，无 HTTP 调用。
END OF REPORT