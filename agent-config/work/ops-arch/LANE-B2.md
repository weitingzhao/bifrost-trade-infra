# LANE-B2 — Console「待你批」页 + 手机推送

ADR §5（三个审批入口里的 Console 与手机）。仓库：bifrost-platform `cursor/b2-platform`；bifrost-trade-infra `cursor/b2-infra`。接口照 README「接口约定」，B1 还没合并时按约定写、用假数据测。

## 事实

- Console 的令牌来自 `console/src/api/client.ts` 的 `operatorToken()`（`getPlatformOperatorToken()`）。批准需要 admin 令牌。
- 手机推送走 Mac mini .50 的告警中转（`api/internal/alertrelay`，operator-plane 二进制，`ALERT_RELAY=on`），它把消息发到 ntfy；现在只有 Alertmanager 与心跳两个入口。
- Owner 原则：形式从简，不做 Face ID / passkey；Console 只是状态、审批和追溯。

## 要做

1. **Console**：新页面「Approvals」（hash `#approvals`，放在导航最上面一组，第 3 阶段重组时再定最终位置）：
   - 待批列表：谁申请（session）、动作、级别、参数（展开）、理由、回滚方式、剩余有效期；「批准」「拒绝（写原因）」两个按钮，调用时 `channel: "console"`；
   - 历史：最近 50 条已结的申请与结果；
   - 支持 `#approvals?id=<id>` 直接打开某一条（手机点通知时用），在手机宽度下可用；
   - admin 令牌：页面上有一个「设置审批令牌」的输入框，存浏览器本地（`localStorage`），只用于批准 / 拒绝；没有时按钮置灰并说明。
2. **推送**：
   - alertrelay 加 `POST /api/v1/alerts/notify`（与现有入口同一令牌校验）：`{title, message, click_url, priority}` → ntfy（`Click` 头带 `click_url`）；
   - 平台在创建申请时调用它，`click_url` = `http://ops.bifrost.lan/#approvals?id=<id>`；地址与令牌来自环境变量（`APPROVAL_NOTIFY_URL`、`APPROVAL_NOTIFY_TOKEN`），没配就不发、只记日志；
   - infra：PROD platform-workers / platform-api overlay 加这两个变量，令牌从新 Secret `bifrost-platform-approval-notify` 读取（`optional: true`），**不要**把令牌写进仓库；报告里写出 Owner 建 Secret 的命令（值从本机 `.env` 的 `ALERT_RELAY_TOKEN` 读，不打印）。
3. 防线：Console 页面的 vitest（待批渲染、无令牌置灰、直达某条）；alertrelay notify 的 Go 测试（令牌错误 401、ntfy 失败返回 502、`Click` 头）。

## 门禁与验收

Console：`npx tsc -b && npm run lint && npx vitest run && npm run build`；Go：`go build ./... && go vet ./... && go test ./...`。验收命令写进报告。

## 要 Owner 批

建 Secret；platform 发版；在 .50 重新部署 operator-plane（用已修好的 `deploy_mac_mini.sh`，它会保留 `ALERT_RELAY=on`）。
