# Codex 复核 49 — W-65 1A 第 3 轮（`4fe6c07..acfb854`）

2026-10-11 05:00 CDT · 只读 · 分支 `w31/w65-1a`

统筹方的后续（05:10）：报告末尾「补充」里的三种写法，拿主线 `8b3259a` 的 `approvalnotify.Redact` 和分支的 `notice.Redact` 各跑一遍，主线遮住、分支不遮（实测）。「父提交已存在」指本分支第 2 轮，不是主线。已加第 4 轮；教训第 71 行。

---

VERDICT: safe to merge

复核范围：`4fe6c07..acfb854`；未发现本次 diff 新增的 P1/P2，契约文件未改。

- 脱敏：review 42 的相邻 key 问题已关闭；空格、换行、逗号分隔均能连续脱敏。
- 内存验证：9 个脱敏向量、23 个 canonical 向量通过；24,389 个 ASCII 组合差分未发现旧版隐藏而新版保留的秘密，包含引号、首尾、重叠和 `token=` 链。
- Go/TypeScript 的共享规则和扫描流程静态一致；slice-zero 通知 pin 及 Compose 未改，固定输入的脱敏结果保持一致。
- sweep：测试统一注册 `Close()`，取消后等待 questions goroutine 返回，随后才清理 TempDir。
- workers 启动条件及零延迟首轮未变；Answer 仍在事务中先处理过期，不会因 sweep 间隔而接受过期问题。
- 空库读取不创建文件或锁；已有问题过期时，读取仍按原语义持久化过期状态。
- 生产主程序未接入 `Close()`；目前随进程退出停止，没有新增生产停扫路径。

补充：Unicode 兼容恢复并不完整，`Baſic abcdefgh`、`Bearer abcdefgK`、`tokenſuffix=s3cr3tvalue` 仍保留明文；这些遗漏在父提交已存在，不计为本次新增 P2。
验证限制：遵守只读约束，未运行会写缓存或临时文件的 Go 测试；Go 行为和通知完整输出为静态核对。

END OF REPORT