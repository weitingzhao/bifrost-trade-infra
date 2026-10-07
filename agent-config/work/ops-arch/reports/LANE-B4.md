# LANE-B4 报告

## 改动

- bifrost-trade-infra · `cursor/b4-infra` · `38e752e3e824cbf42524787f6f64f7b0b625fab3`
  - 新 ClusterRole `bifrost-platform-node-drain`（`pods/eviction` create、`poddisruptionbudgets` get/list/watch），只绑 PROD ServiceAccount。`10-stg.yaml` 没改。
  - STG `platform-workers`：`PLATFORM_DATA_CLONE_SCHEDULER=off`、`PLATFORM_PATROL_LOOP=off`。
  - PROD `platform-api` 与 `platform-workers` 从 Secret `bifrost-platform-unifi`（`optional: true`）读 `UNIFI_HOST` / `UNIFI_USER` / `UNIFI_PASS`。Secret 不进仓库。
  - `apply-platform-role-tokens.sh` 的 webhook（含 `WEBHOOK_ONLY=1`）改写 PROD reporter 令牌。
  - `bifrost-alerting-rules.yaml` 的 `BifrostAlertmanagerWebhookFailing` 注解改为 PROD platform-api。
- bifrost-platform · `cursor/b4-platform` · `388d43118a2a6f10e732fa3ed25b95d324d7564b`
  - 两个开关默认开；`off` / `0` / `false` / `no` 不启动数据克隆调度器和 patrol 循环。
  - `POST /api/v1/ops-agent/alertmanager` 改为 reporter 及以上。审计记下实际角色。

## 防线

- `scripts/check_platform_rbac.py`：B1 分级表里每个 B/C/D 动作一条断言（PROD 能、STG 不能）。非 API 动词的动作列在 `NON_K8S`，从表里删掉会失败。`kube-system` 里 delete pods 仍是两边都不许。
- `scripts/check_platform_maintenance.py`：STG `platform-workers` 两个开关必须是 off；PROD 不得把它们关掉。
- `scripts/check_alert_routing.py` · `assert_token_source`：webhook 必须由 `webhook_token` 写入 `PLATFORM_PROD_REPORTER_TOKEN`，不得再写 operator / STG operator。`LIVE=1` 的 `assert_live_bearer` 改对 reporter Secret 的摘要。
- Go：`TestLoopEnabledDefaultsOn`、`TestStartDataCloneSchedulerOffLeavesStoresUnset`、`TestStartSkipsWhenPatrolLoopOff`、`TestAlertmanagerWebhookIsReporterOrAbove`。

## 门禁

- `cd api && go build ./...` → exit 0
- `go vet ./...` → exit 0
- `go test ./...` → exit 0（各包 ok，无 FAIL）
- `PATH=/usr/bin:$PATH make check-platform-maintenance` → exit 0
- `PATH=/usr/bin:$PATH make check-alert-routing` → exit 0（静态；未跑 `LIVE=1`）
- `PATH=/usr/bin:$PATH make check-platform-rbac` → **exit 2**（配方里的脚本 exit 1）。138 条里 5 条不一致，全是 PROD 还没有 drain 规则：
  - `drain_node` create `pods/eviction`（data、bifrost-prod、kube-system）
  - `drain_node` list `poddisruptionbudgets.policy`（bifrost-prod）
  - `poweroff_node` create `pods/eviction`（data）
  - STG 上述全是 no，符合预期。其余 B/C/D 的 Kubernetes 动作 PROD 已是 yes、STG 已是 no。
  - `kubectl apply -k k8s/platform-rbac` 之后同一条检查应变成 exit 0。

## 验收

```bash
PATH=/usr/bin:$PATH KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_platform_rbac.py
```

预期（RBAC apply 之后）：exit 0，输出含 `22 B/C/D actions, PROD can, STG cannot`。apply 之前：exit 1，且只有上面 5 条 PROD drain 失败。

```bash
PATH=/usr/bin:$PATH python3 scripts/check_platform_maintenance.py
```

预期：exit 0，输出含 `STG data-clone scheduler and patrol loop off`。

```bash
PATH=/usr/bin:$PATH python3 scripts/check_alert_routing.py
```

预期：exit 0。`LIVE=1` 要等 webhook Secret 换成 reporter 之后才是 exit 0。

```bash
cd bifrost-platform/api && go test ./internal/config/ ./internal/cluster/ ./internal/patrol/ ./internal/server/ -count=1 -run 'TestLoopEnabledDefaultsOn|TestStartDataCloneSchedulerOffLeavesStoresUnset|TestStartSkipsWhenPatrolLoopOff|TestAlertmanagerWebhookIsReporterOrAbove'
```

预期：exit 0。

## 要 Owner 批

顺序：先有新 platform 镜像（路由认 reporter），再换 webhook 令牌。先换令牌、镜像还是旧的，Alertmanager 会 401。STG 两个开关也要新镜像才生效；旧镜像会忽略这两个环境变量，所以先合 infra 是安全的。本道没有 apply、没有发版。

1. 建 UniFi Secret（三个键在本机 `bifrost-platform/.env` 里，非空；命令不打印值）：

```bash
python3 - <<'PY'
import os, pathlib
src = pathlib.Path("/Users/vision-mac-trader/Desktop/stocks/bifrost-platform/.env")
want = ("UNIFI_HOST", "UNIFI_USER", "UNIFI_PASS")
found = {}
for line in src.read_text().splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    if k in want:
        found[k] = v.strip().strip('"').strip("'")
missing = [k for k in want if not found.get(k)]
if missing:
    raise SystemExit("missing " + ",".join(missing))
out = pathlib.Path("/tmp/bifrost-platform-unifi.env")
out.write_text("".join(f"{k}={found[k]}\n" for k in want))
os.chmod(out, 0o600)
print("wrote key names only:", ",".join(want))
PY
KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n bifrost-platform-prod create secret generic bifrost-platform-unifi \
  --from-env-file=/tmp/bifrost-platform-unifi.env \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f /tmp/bifrost-platform-unifi.env
```

Secret 要在 Pod 起来之前就有。`optional: true`，没有它 Pod 能起，但 `network/*` 仍报 `UNIFI_USER and UNIFI_PASS required`，建完需要再滚一次才读得到。

2. 合并 `cursor/b4-infra`。Argo 会改 STG / PROD 的 platform Deployment（STG 两个开关、PROD 的 UniFi env）。不要在共享 checkout 里切这个分支。

3. RBAC 手工 apply（`k8s/platform-rbac` 不归 Argo）：

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch origin cursor/b4-infra
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra worktree add --detach /tmp/b4-apply origin/cursor/b4-infra
KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl apply -k /tmp/b4-apply/k8s/platform-rbac
PATH=/usr/bin:$PATH KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 /tmp/b4-apply/scripts/check_platform_rbac.py
```

4. platform `cursor/b4-platform` 合入并发版之后，再更新 webhook 令牌（脚本不打印值；`.env` 没有 `PLATFORM_PROD_REPORTER_TOKEN` 时，从集群 Secret `bifrost-platform-reporter-token` 拷）：

```bash
cd /tmp/b4-apply
KUBECONFIG=~/.kube/bifrost-k3s.yaml WEBHOOK_ONLY=1 scripts/k3s/apply-platform-role-tokens.sh
```

5. 告警注解不在 Argo 里。只 apply 这一份 PrometheusRule（不要跑 `make k3s-apply-monitoring-scrape`，那个脚本还会删别的命名空间里的旧 monitor）：

```bash
KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl apply -f /tmp/b4-apply/k8s/monitoring/bifrost-alerting-rules.yaml
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra worktree remove /tmp/b4-apply
```

## 与 B2 的重叠

B2 在 PROD platform-api / platform-workers 上加 `APPROVAL_NOTIFY_URL`、`APPROVAL_NOTIFY_TOKEN`，令牌来自 Secret `bifrost-platform-approval-notify`。

B4 没有改 PROD 的 `platform-workers-env.patch.yaml`，也没有写 `APPROVAL_NOTIFY_*`。UniFi 三个键只在新文件 `k8s/overlays/platform-prod/platform-unifi-env.patch.yaml`。

两边都会改 `k8s/overlays/platform-prod/kustomization.yaml` 的 `patches` 列表。rebase 时两行都留：B2 的 notify patch，加上 B4 的 `- path: platform-unifi-env.patch.yaml`。

STG 的 `platform-workers-env.patch.yaml` 只有 B4 在改（B2 的范围是 PROD）。

## 后续

- 新 RBAC 只补了 **drain_node** 和 **poweroff_node**（`pods/eviction` + PDB list）。其余 B/C/D 的 Kubernetes 动作 PROD 本来就能做、STG 本来就不能做。
- `wake_node`、`market_data_heal`、`unifi_apply` 不走 API server（SSH、插件 HTTP、UniFi API）。`join_node`、`stack_install`、`stack_upgrade` 是宿主机脚本，要建 Namespace、CRD、ClusterRole。那等于集群管理员，和 TD-204 写明不授予的范围冲突，没有加。D10 的 `refuseDaemonScaleUp` 没动；RBAC 仍然不能按 Deployment 名字排除 daemon。
- `LIVE=1 make check-alert-routing` 在 webhook Secret 仍是 operator 令牌时会失败。静态检查已经通过。
- 无新的 D10 缺口。
