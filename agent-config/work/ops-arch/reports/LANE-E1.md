## LANE-E1

- 做了什么：给 PROD/STG 的 platform-workers 加了 PodMonitor（没有 Service，Deployment 注释写明不往 workers 路由）。platform-workers 的后台循环在成功一轮后写入 `bifrost_maintainer_last_success_timestamp_seconds{maintainer}` 和 `bifrost_maintainer_runs_total{maintainer,result}`（手写 exposition，没有新的 Prometheus 客户端）。PrometheusRule 覆盖原先 `detected_by: none` 里能对上的 CronJob 和这些循环。集群内每晚 07:00 UTC 只读对账，结果写成 ConfigMap `monitoring/maintainer-reconcile-clean`（集群里没有 Pushgateway）。漂移大于 0 时删掉这张 ConfigMap，告警看 `kube_configmap_created`。
- 分支：
  - bifrost-platform · `cursor/e1-platform` · `5c4040ee3847799770f960d73e58ebc2ccef2dfd`
  - bifrost-trade-infra · `cursor/e1-infra` · 实现 `46c5b25b1cb636890c5ce10dcfef27592ea8cc5f`，本报告是其后的提交（分支 tip）
- 派发 / 审批：没有碰。`internal/checklist/dispatch.go`、`executeDispatch`、husbandry-sync 派发路径、approvals 端点、审批令牌、`RequestActionButton` 都没改。`prober.go` 只在探测合并成功或失败时记了维护者指标（第 3 阶段若也改这个文件，合并时会撞）。
- 防线：`make check-maintainers` 要求 `detected_by` 里的告警名真实存在，并要求 `k8s/monitoring/maintainer-reconcile/MAINTAINERS.yaml` 与 `agent-config/MAINTAINERS.yaml` 逐字节相同。`scripts/check_alert_routing.py` 仍把真正的备份告警 `BifrostPostgresBackup*` 送进现有寻呼路由；维护者存活告警在 LANE-E1R 改名为 `BifrostMaintainer…` 之后不进这条路由，severity 都是 warning，走默认 PROD webhook（记账）。`reconcile.py --self-test` 覆盖干净、缺 series、`none:` 不要求 series、常驻 launchd 停了算漂移、间隔任务两次运行之间不算漂移、多出来的 schedule。
- 门禁：
  - platform `api/`：`go build ./... && go vet ./... && go test ./...` → exit 0（全部包 ok）。第一次编译失败是 `route` 字面量少了 `viewer` 字段，已补 `false`。第一次全量测试只失败 `storedurability.TestNoNewStoreUnderHome`（`launchd/list.go` 读本机 LaunchAgents），已写入非存储原因的允许名单。第二次全量测试通过。
  - `make check-maintainers` → `ok 42 maintainers; static; no-alert 15`
  - `python3 k8s/monitoring/maintainer-reconcile/reconcile.py --self-test` → `self-test ok`
  - `PATH="/usr/bin:$PATH" python3 scripts/check_alert_routing.py` → exit 0，`Watchdog and 14 paged alert kinds`（Homebrew Python 3.14 没有 PyYAML，用的是系统 Python）
  - `kubectl kustomize k8s/monitoring` 与 `kubectl kustomize k8s/monitoring/maintainer-reconcile` → exit 0。没有 apply。
  - console 和 mcp 没改，没跑它们的门禁。
- platform 的 husky 钩子在新 worktree 里不执行（仓库里已写明）。超长文件检查没有跑到主检出，也没有改基线、没有 `--no-verify`。`Change-Id` 是提交后、推送前补进 `5c4040e` 的。infra 的 `core.hooksPath` 正常带上了 `Change-Id`。
- 仍没有活性信号的维护者（15 个，`detected_by` 都以 `none:` 开头并写了原因）：
  - `platform/stg/data-clone-scheduler`、`platform/stg/patrol-autopilot`：STG overlay 把这两条循环关掉，没有成功 series。对它们做 `absent()` 会一直告警。
  - `plugin/market-data-api-queue-sampler`：采样线程在 market-data-api 里，不在本道的两个仓库。
  - launchd `.50`/`.52` 的 operator-plane、peer-watchdog、remediation-runner，以及 `.52` 的 hermes-gateway：peer watchdog 只轮询对端 `:8781/health` 并拉起 `com.bifrost.remediation-runner`，它自己不是 PrometheusRule。这些标签没有心跳 series。夜间对账会看标签集合，以及常驻进程是不是在跑；这是另一条信号，没有写进它们的 `detected_by`。
  - mac-pro 五条（platform-api、git-bridge、event-radar-watch、local-services、claude-scheduled-tasks）：`none: 开发机，不是生产维护者`。
- 没做的：
  - `release_policy_expiry_check` 这条循环不在这棵树上（LANE-RP）。helper 里留了常量 `LoopReleasePolicy`，没有放进 `Loops()`，也没有告警。RP 落地后要用它自己的 MAINTAINERS id 调 `maintainer.Success`。不在清单里的 series 会被夜间对账当成多出来的。
  - 没有重跑 `check_maintainers.py --live`（会连集群和两台 mini）。清单里的 launchd 标签若和机器上不一致，第一次夜间对账会显示漂移。
  - 没有发版、没有 apply、没有写数据库、没有 `release.sh`、没有起 pipeline。
- 要 Owner 批（本道没有执行）：

```bash
# 监控清单不在 Argo 里。从含本分支的 bifrost-trade-infra 检出。
kubectl apply -f k8s/monitoring/bifrost-platform-workers.yaml
kubectl apply -f k8s/monitoring/bifrost-maintainer-rules.yaml
kubectl apply -k k8s/monitoring/maintainer-reconcile

# 给夜间任务一个能读 launchd 的令牌。reporter 高于 viewer。
# 不建这张 Secret 时，任务仍对账集群，并把 launchd 记成未读（算漂移）。
# 令牌从标准输入读，不出现在进程参数里（LANE-E1R）。
kubectl -n bifrost-platform-prod get secret bifrost-platform-reporter-token \
  -o jsonpath='{.data.PLATFORM_PROD_REPORTER_TOKEN}' | base64 -d \
  | kubectl -n monitoring create secret generic maintainer-reconcile-auth \
    --from-file=token=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -

# operator-plane 的只读端点 GET /api/v1/agent/launchd 要在两台 mini 上重新部署才生效。
# 用已修好的 deploy_mac_mini.sh，从干净的 main 检出跑。没部署前，夜间对账把 launchd 记成未读。
```

platform 镜像要先发到 PROD/STG workers，gauge 才会出现。在那之前，PROD 循环的 `absent()` 会以 warning 记账。LANE-E1R 起，备份重试和清扫的存活告警叫 `BifrostMaintainer…`，不再匹配呼人路由。patrol 的 cert-expiry 技能一周才跑一次，第一次成功前 `absent()` 会一直在。CronJob `maintainer-reconcile` 第一次干净通过之前，`BifrostMaintainerReconcileDrift` 会响。platform-api 的 `/metrics` 仍会探四个插件；`PLATFORM_ROLE=workers` 的 `/metrics` 只出进程指标和维护者指标（LANE-E1R）。
- 验收：在 infra 该分支上 `make check-maintainers` 预期 `ok 42 maintainers; static; no-alert 15`。`PATH="/usr/bin:$PATH" python3 scripts/check_alert_routing.py` 预期 exit 0。在 platform 该 SHA 的 `api/` 里 `go test ./internal/maintainer ./internal/launchd ./internal/operatorplane` 预期 ok。
- 后续：第 3 阶段合并 `prober.go` 时保留 `maintainer.Success` / `Failure`。不要和 D1 的分支一起推。无新的技术债条目。
