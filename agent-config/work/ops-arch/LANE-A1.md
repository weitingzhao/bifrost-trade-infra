# LANE-A1 — 告警改道：warning 送 PROD，STG 退出告警链路

ADR §7。仓库：bifrost-trade-infra，分支 `cursor/a1-infra`。

## 事实（Claude Code 10-07 实测）

- Alertmanager 路由：Watchdog → `owner-heartbeat`；`severity=critical` 与名字匹配 `Bifrost(PostgresBackup.*|PostgresWalArchiveStalled|LogicalBackup.*|MinIONas.*)` → `owner-ntfy`；**其余全部（所有 warning）→ 默认 receiver `bifrost-ops-agent`**，它的 webhook 是
  `http://platform-api.bifrost-platform-stg.svc.cluster.local:8780/api/v1/ops-agent/alertmanager`——STG 的 platform，7 天无人访问。
- 该端点在 platform 里只做诊断 + 写审计（`api/internal/opsagent/handler.go` `HandleAlertmanager`），不派发任何动作。
- 当时正在报 `AlertmanagerClusterFailedToSendAlerts`（critical）：6 小时 11 次 webhook 发送失败，原因未查。
- 配置源：`scripts/k3s/values-kube-prometheus.yaml`；出站策略：`k8s/monitoring/alertmanager-webhook-network-policy.yaml`；防线：`scripts/check_alert_routing.py`（`make check-alert-routing`，`LIVE=1` 走运行中的路由）。

## 要做

1. 默认 receiver 改指 PROD：`platform-api.bifrost-platform-prod.svc.cluster.local:8780/api/v1/ops-agent/alertmanager`。配置里不再出现 `bifrost-platform-stg`。
2. 呼人匹配加上 `BifrostClusterStateBackup.*`（LANE-A2 的告警名）。
3. NetworkPolicy：monitoring → bifrost-platform-prod:8780 放行；若 bifrost-platform-prod 有入站策略，同样放行 monitoring。去掉对 STG 的放行。
4. 查清 `AlertmanagerClusterFailedToSendAlerts` 是哪个 receiver 失败（只读：Alertmanager 日志、`alertmanager_notifications_failed_total`），写进报告；如果是 STG 那条，本道改完自然消失。
5. 防线：`check_alert_routing.py` 增加断言——任何 receiver 的 URL 不得含 `bifrost-platform-stg`；默认 receiver 必须指向 `bifrost-platform-prod`；静态与 `LIVE=1` 都要覆盖。

## 不做

不执行 helm upgrade、kubectl apply。不改 platform 代码。不改 critical / 备份呼人的既有路由。

## 验收（报告里给出原样命令）

- 分支上 `make check-alert-routing` 通过；
- Owner 批准并 apply 后：`LIVE=1 make check-alert-routing` 通过，且 PROD platform 审计出现 `ops-agent.alertmanager` 记录。

## 要 Owner 批

helm upgrade 的完整命令（**不加 `--wait`**：gpu-server 是待机节点，node-exporter 永远 5/6）。
