# LANE-U2 — @bifrost/ui 未用导出 + 宏观面板文案（bifrost-ui、bifrost-trade-frontend）

先读 `cursor-tasks/README.md`（**特别是「第 2 轮」一节：一律只推分支**）。每项的 Claim / Evidence / Fix / Ratchet 见台账 `### TD-n`。报告写到 `cursor-tasks/reports/LANE-U2.md`。分支：`cursor/u2-ui`、`cursor/u2-fe`。

| 项 | 要做的 |
|---|---|
| **TD-239** | 用 knip 或 ts-prune 以 Trade frontend 与 Ops Console 两个消费方为入口扫 bifrost-ui；删没有使用者的导出；为 Design 有意保留的标注原因。两个消费方的 tsc / build 都要过 |
| **TD-182**（只做现在这半） | EventRadarDashboard 宏观缺口的空状态文案改为写明「consensus 不在订阅里（权限缺口）」，不再说 CSV forward_flag；加测试 |
