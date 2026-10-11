# Codex 复核 72 — TD-310：没人能解开的冻结不许设（platform `6524330..96af54a`，infra `9841791..ec20a4d`）

2026-10-11 13:41 CDT · 只读

统筹方处理：可以合并。没有必须改和应该改的；一处次要的（`policy status` 在没有信任锚时没说冻结不可用）当场收了（infra `c1f960e`）。脚本和文档那一半 13:48 进 infra 主线（`3a9db04`）；平台那一半在 `w31/td-310`，随下一次平台发布。

---

VERDICT: safe to merge

P3 — `bifrost-trade-infra/scripts/release/release.sh:616`：`policy status` 在空锚时只提示 `nothing auto-approves`，没有说明冻结功能也不可用。
最小复现：将 `{"anchor_fingerprint":"","frozen":false}` 输入 `policy_print`，输出未提及冻结被拒绝。
最小修复：将空锚提示补为 `none compiled in: nothing auto-approves; freeze unavailable`，并更新输出测试。

未发现 P1/P2。专用 HTTP/action 路径最终进入 `Engine.Freeze`，空锚检查先于 ConfigMap 和冻结记忆写入；未发现自动设置冻结的 watchdog、失败处理或到期路径。
读取状态仍会记住已有冻结，这是保留原有防回放行为；既有冻结继续阻止发布，验签解冻逻辑未改。
CLI 离线替身验证通过：空锚、缺失字段、纯空白、读取失败均不发 POST；有锚正常发送。`--dry-run` 被参数检查拒绝，`policy install` 不发送冻结 POST。
应急文档的三个对象、顺序及 JSON patch 与代码一致；重置后的冻结对象通过 Tekton 判定。操作明确限 Owner 使用 cluster-admin，无实际凭证或机器专属路径。
密钥文档明确了两个修改位置、Owner 审核和平台发版要求，路径与签名命名空间符合实现。
父版离线验证确认 CLI 缺陷可复现；Go 新增拒绝测试按父版代码必失败，已有冻结兼容测试应仍通过。
受只读及禁止 HTTP 调用约束，未运行完整 Go/pytest 测试；完成 Bash 语法检查和无文件写入、无网络的离线验证。

END OF REPORT