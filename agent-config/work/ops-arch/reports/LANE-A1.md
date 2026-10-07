# LANE-A1 报告

仓库 `bifrost-trade-infra`，分支 `cursor/a1-infra`，完整 SHA `53b527bb5e398f64aae5be62402e046c6480c4b8`（`origin/cursor/a1-infra` 已是这个 SHA）。起点 `origin/main` `470a14e197b68bacc39a062f7867bf5461e39097`。未推 main，未 helm upgrade，未 kubectl apply。worktree `/tmp/cursor-a1-infra` 已删除。

## 1. 默认 receiver 改指 PROD

- 改动：bifrost-trade-infra · `cursor/a1-infra` · `53b527bb5e398f64aae5be62402e046c6480c4b8`
  - `scripts/k3s/values-kube-prometheus.yaml`：`bifrost-ops-agent` 的 webhook 改为 `http://platform-api.bifrost-platform-prod.svc.cluster.local:8780/api/v1/ops-agent/alertmanager`。文件中不再出现 `bifrost-platform-stg`。
  - `scripts/k3s/apply-platform-role-tokens.sh`、`docs/SECRETS.md`、`k8s/monitoring/kustomization.yaml`：webhook bearer 改为 PROD operator token（`PLATFORM_PROD_OPERATOR_TOKEN`）。PROD platform-api 的 operator 角色读的是这个环境变量（`k8s/overlays/platform-prod/config/platform-auth.yaml`）；现行 Secret `monitoring/alertmanager-webhook-auth` 仍是 STG operator token，只改 URL 会 401，审计里不会出现 `ops-agent.alertmanager`。`WEBHOOK_ONLY=1` 只改这一份 Secret，不重写 role-token Secret。
- 防线：`scripts/check_alert_routing.py` 函数 `assert_webhook_targets`、`assert_token_source`、`self_test`（静态）；`assert_live_bearer`（只比较 SHA-256，不打印令牌，仅 `LIVE=1`）
- 门禁：
  - `make -C /tmp/cursor-a1-infra lint` → 退出码 2（`No rule to make target 'lint'`）
  - `make -C /tmp/cursor-a1-infra test` → 退出码 2（`No rule to make target 'test'`）
  - `make -C /tmp/cursor-a1-infra check-alert-routing` → 退出码 2（配方 Error 1：`/opt/homebrew/bin/python3` 3.14.5 没有 PyYAML）
  - `PATH="/usr/bin:$PATH" make -C /tmp/cursor-a1-infra check-alert-routing` → 退出码 0
  - `/usr/bin/python3 scripts/check_alert_routing.py` → 退出码 0，`ok (values-kube-prometheus.yaml): Watchdog and 10 paged alert kinds ... default receiver is platform-api.bifrost-platform-prod.svc.cluster.local`
- 验收：`git clone --branch cursor/a1-infra --depth 1 git@github.com:weitingzhao/bifrost-trade-infra.git /tmp/a1-accept && git -C /tmp/a1-accept rev-parse HEAD && PATH="/usr/bin:$PATH" make -C /tmp/a1-accept check-alert-routing` → 预期 SHA `53b527bb5e398f64aae5be62402e046c6480c4b8`、退出码 0、输出含 `default receiver is platform-api.bifrost-platform-prod.svc.cluster.local`。本机默认 `python3` 没有 PyYAML，所以验收命令把 `/usr/bin` 放在 PATH 前面；解释器自带 PyYAML 时可以去掉这个 PATH。
- 要 Owner 批：见文末「要 Owner 批」。只改 URL 而不改 bearer，PROD 会 401。
- 后续：`k8s/monitoring/bifrost-alerting-rules.yaml:486` 注解仍写着去查 STG platform-api；本道按约定不改这个文件。

## 2. 呼人匹配加上 BifrostClusterStateBackup.*

- 改动：同上 SHA。`scripts/k3s/values-kube-prometheus.yaml` 里既有的 `owner-ntfy` 名字匹配改为 `Bifrost(PostgresBackup.*|PostgresWalArchiveStalled|LogicalBackup.*|MinIONas.*|ClusterStateBackup.*)`，`continue: true` 不变。`severity=critical` 那条路由未改。
- 防线：`scripts/check_alert_routing.py` 的 `PAGED` 与 `SYNTHETIC_PAGED`（`BifrostClusterStateBackupFailed` / warning）。LANE-A2 的 PrometheusRule 不在本分支，合成名保证这条路由现在就被走到：必须到达 `owner-ntfy`，并且仍到达 `bifrost-ops-agent`。`self_test` 覆盖同一条。
- 门禁：与第 1 项同一次静态检查，退出码 0（10 类被呼告警，含这条合成名）。
- 验收：与第 1 项同一条命令，退出码 0。
- 要 Owner 批：同一条 helm upgrade（路由在 values 里，不在 NetworkPolicy 里）。
- 后续：无后续。A2 的规则文件落地后，`PAGED` 会把真实规则名一并纳入，不必再改匹配式。

## 3. NetworkPolicy：monitoring → bifrost-platform-prod:8780，去掉 STG

- 改动：同上 SHA。`k8s/monitoring/alertmanager-webhook-network-policy.yaml` 的 namespace 选择器从 `bifrost-platform-stg` 改为 `bifrost-platform-prod`，pod 选择器仍是 `app.kubernetes.io/name: platform-api`，端口 TCP 8780。DNS 与 `192.168.10.50:8783` 未改。
- 入站：`kubectl get networkpolicy -n bifrost-platform-prod` 为空；仓库里该命名空间也没有 NetworkPolicy。没有入站策略，所以没有另加一条放行。PROD `platform-api` Pod 标签已是 `app.kubernetes.io/name=platform-api`，出站选择器对得上。
- 防线：`scripts/check_alert_routing.py` 函数 `assert_egress_policy` / `policy_allows_prod`。静态读文件；`LIVE=1` 读集群里的 `monitoring/alertmanager-webhook-egress`。
- 门禁：静态检查退出码 0。`LIVE=1` 在未 apply 前失败，见第 5 项。
- 验收：与第 1 项同一条静态命令，退出码 0。
- 要 Owner 批：文末 kubectl apply 这一份 NetworkPolicy（monitoring 不在 Argo 上）。
- 后续：无后续。

## 4. AlertmanagerClusterFailedToSendAlerts 是哪个 receiver

- Claim：成立，但失败的不是 STG webhook。本项不改路由。
- 改动：无代码。调查只读。
- 证据（2026-10-07 约 18:57Z，`KUBECONFIG=~/.kube/bifrost-k3s.yaml`）：
  - 正在 firing：`AlertmanagerClusterFailedToSendAlerts`（critical）、`AlertmanagerFailedToSendAlerts`（warning，`integration=webhook`，`reason=clientError`）、`BifrostAlertmanagerWebhookFailing`（critical）。
  - `alertmanager_notifications_failed_total` 没有 receiver 标签。非零的只有 `integration="webhook"`：`reason="clientError"` 为 50，`reason="other"` 为 1。其余 integration 全是 0。
  - Pod `alertmanager-kube-prometheus-stack-alertmanager-0` 自启动以来的 `Notify for alerts failed`：`owner-heartbeat` 38 次，`owner-ntfy` 12 次，合计 50。`bifrost-ops-agent` 为 0。
  - 两条错误都是 `unexpected status code 404: 404 page not found`。`owner-heartbeat/webhook[0]` 每分钟一次（Watchdog）；`owner-ntfy/webhook[0]` 是 critical，包括 `AlertmanagerClusterFailedToSendAlerts` 自己和 `BifrostAlertmanagerWebhookFailing`。
  - 运行中的 URL（Secret `monitoring/alertmanager-kube-prometheus-stack-alertmanager` 的 `alertmanager.yaml`，只看 url 行）：`owner-ntfy` → `http://192.168.10.50:8783/api/v1/alerts/alertmanager`，`owner-heartbeat` → `http://192.168.10.50:8783/api/v1/alerts/heartbeat`，`bifrost-ops-agent` → STG platform-api。状态 API 把这三条都打成 `<secret>`。
  - `GET http://192.168.10.50:8783/health` → `{"status":"ok","service":"bifrost-operator-plane","autopilot":false,"alert_relay":false,"contained_panics":0}`。不带令牌的 POST `/api/v1/alerts/heartbeat` 与 `/api/v1/alerts/alertmanager` 都是 `404 page not found`，不是 401。`bifrost-platform/api/cmd/operator-plane/main.go:69` 只在 `ALERT_RELAY=on` 且配置完整时才 `relay.Mount`。中转没挂上，所以是 404 而不是令牌错误。
- 结论：这条 critical 不是 STG 那条 webhook。本道把审计 webhook 改到 PROD 之后，它不会自己消失。`owner-heartbeat` / `owner-ntfy` 按约定没有改。
- 防线：无（只读调查）。
- 门禁：无。
- 验收：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n monitoring logs alertmanager-kube-prometheus-stack-alertmanager-0 -c alertmanager --since=1h | grep 'Notify for alerts failed'` → 预期 err 前缀只有 `owner-heartbeat/webhook[0]` 和 `owner-ntfy/webhook[0]`，状态码 404；没有 `bifrost-ops-agent`。
- 要 Owner 批：没有（不要为了这条去改呼人路由或在 .50 上开 `ALERT_RELAY`，除非另开一道）。
- 后续：`bifrost-platform/api/cmd/operator-plane/main.go:69` .50 上 operator-plane 的 `alert_relay` 为 false，呼人与心跳 webhook 404，这就是 `AlertmanagerClusterFailedToSendAlerts`。`agent-config/RATCHETS.md:34` 仍写 `LIVE=1` 因状态接口打码而按接收器名对照 values 文件；本道改为读 Secret 里的明文 URL，台账那一句要改，本道按约定不改 `RATCHETS.md`。

## 5. check_alert_routing.py：静态与 LIVE=1

- 改动：同上 SHA。`scripts/check_alert_routing.py`。Makefile 目标 `check-alert-routing` 未改，`LIVE=1` 仍传 `--live`。
- 断言：任何 receiver URL 不得含 `bifrost-platform-stg`；根路由的默认 receiver 必须是 `platform-api.bifrost-platform-prod.svc.cluster.local:8780/api/v1/ops-agent/alertmanager`；出站策略允许 PROD platform-api TCP 8780 且不得再写 STG 命名空间；写 webhook Secret 的脚本行必须是 `PLATFORM_PROD_OPERATOR_TOKEN`。状态 API 的 URL 是 `<secret>`，`self_test` 会拒绝被打码的 URL。`LIVE=1` 读 Secret `alertmanager-kube-prometheus-stack-alertmanager` 的 `alertmanager.yaml`（里面是 `bearer_token_file`，不是令牌本身）和 NetworkPolicy `alertmanager-webhook-egress`。
- 防线：`self_test`（PROD URL 必须通过；含 `bifrost-platform-stg` 的 URL 必须同时报 STG 与「不是 PROD host」；`<secret>` 必须报 masked）、`assert_webhook_targets`、`assert_egress_policy`、`assert_token_source`、`assert_live_bearer`。
- 门禁：
  - 静态：`PATH="/usr/bin:$PATH" make check-alert-routing` → 退出码 0
  - 默认 `python3`：`make check-alert-routing` → 退出码 2（没有 PyYAML）
  - `KUBECONFIG=~/.kube/bifrost-k3s.yaml PATH="/usr/bin:$PATH" LIVE=1 make check-alert-routing` → 退出码 2（配方 Error 1）。这是 apply 之前的预期失败，七条：
    - live config 仍含 `bifrost-platform-stg`
    - receiver `bifrost-ops-agent` URL 含 `bifrost-platform-stg`
    - 默认 receiver 的 host 仍是 `platform-api.bifrost-platform-stg.svc.cluster.local`
    - `alertmanager-webhook-auth` 不是 PROD operator token
    - `BifrostClusterStateBackupFailed` 只到达 `bifrost-ops-agent`，没有呼人（线上路由还没有新匹配）
    - 线上 NetworkPolicy 仍写着 `bifrost-platform-stg`
    - 线上 NetworkPolicy 还不允许 `bifrost-platform-prod` platform-api TCP 8780
- 验收：apply 之后，在该 SHA 的检出里执行 `KUBECONFIG=~/.kube/bifrost-k3s.yaml PATH="/usr/bin:$PATH" LIVE=1 make check-alert-routing` → 预期退出码 0，输出以 `ok (live Alertmanager):` 开头。审计：`curl -fsS http://192.168.10.73:30876/api/v1/audit | python3 -c 'import json,sys; d=json.load(sys.stdin); rows=d.get("records", d if isinstance(d, list) else []); hits=[r for r in rows if isinstance(r, dict) and r.get("action")=="ops-agent.alertmanager"]; print(len(hits)); raise SystemExit(0 if hits else 1)'` → 预期退出码 0 且计数大于 0。审计在 platform-api 进程内存里，helm 重启 Alertmanager 后下一次通知才会写入；Watchdog 不走这条 webhook。
- 要 Owner 批：见下。
- 后续：与第 4 项相同。`RATCHETS.md:34` 的 LIVE 描述过时。

## 要 Owner 批

先出站策略，再 bearer，最后 helm。不要加 `--wait`（gpu-server 待机，node-exporter 会停在 5/6；chart 历史 revision 13 就是这样被标成 failed 的）。chart 钉在已部署的 `88.1.3`。

```bash
set -euo pipefail
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
WT=$(mktemp -d)
git clone --branch cursor/a1-infra --depth 1 git@github.com:weitingzhao/bifrost-trade-infra.git "$WT"
test "$(git -C "$WT" rev-parse HEAD)" = "53b527bb5e398f64aae5be62402e046c6480c4b8"
kubectl apply -f "$WT/k8s/monitoring/alertmanager-webhook-network-policy.yaml"
ENV_FILE=/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/.env \
  WEBHOOK_ONLY=1 \
  "$WT/scripts/k3s/apply-platform-role-tokens.sh"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update prometheus-community
helm upgrade kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 88.1.3 \
  --namespace monitoring \
  --timeout 10m \
  --values "$WT/scripts/k3s/values-kube-prometheus.yaml"
```

`WEBHOOK_ONLY=1` 只写 `monitoring/alertmanager-webhook-auth`，不重写 `bifrost-platform-stg` / `bifrost-platform-prod` 的 role-token Secret，也不打印令牌。`.env` 用共享检出里已有的那份（不在 git 里）。不要跑不带 `WEBHOOK_ONLY=1` 的全量 `make k3s-apply-platform-role-tokens`，除非同时打算按 `.env` 刷新两份 role-token Secret。

apply 之后：

```bash
KUBECONFIG="$HOME/.kube/bifrost-k3s.yaml" PATH="/usr/bin:$PATH" LIVE=1 make -C "$WT" check-alert-routing
```

预期退出码 0。这不会消除 `AlertmanagerClusterFailedToSendAlerts`。
