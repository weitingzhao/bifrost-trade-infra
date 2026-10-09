# LANE-W33 报告

第 5 阶段收口第一批。代码在两条功能分支，未推 main、未合并、未发版、未部署 mini、未 apply、未 helm upgrade、未写数据库。`api/internal/approvals/` 未改。`scripts/agent-guard/` 未改。D10 仍是 BLOCKED。

`~/.hermes` 不删。里面的 key 由 Owner 决定怎么处理。

实测命名空间和任务书里的「data」不一致，清单按实测写：research 在 `research`（`research-api`），market-data 在 `plugin-market-data`，flex-query 在 `plugin-flex-query`，ib-gateway 在 `data` 且镜像是 digest、没有 tag。这三边都没有 STG Deployment，页面文案是英文 `No STG`，不是破折号。

`check-agent-config-parity.sh` 测的树是 `/tmp/cursor-w33`：`bifrost-platform` 指向 platform worktree，`.cursor` / `.claude` / `CLAUDE.md` / `AGENT_FACTS.md` 指向工作区根。exit 0，spine D10 = BLOCKED。新鲜度警告是 worktree 的 `.git` 是文件、脚本在 `repo/.git/FETCH_HEAD` 找不到 fetch 记录，不是 checkout 落后。

pre-commit 的 code-health 看到 platform 超长文件 12，基线 13，exit 0。基线没有在本道降到 12：infra 若先于 platform 合并，主检出上的旧文件数会顶破新基线。两边都进 main 之后再把 `OVERSIZED_PLATFORM_BASELINE` 改成 12。

## 1. mini 清场

### 改动

- bifrost-platform · `cursor/w33-platform` · `9a0d1eded11fbfb9669f2ff52500cd242826bb62`
  - `scripts/agent/deploy_mac_mini.sh`：不再 scp 管理员 kubeconfig；每次部署删除远端 `~/.kube/bifrost-k3s.yaml` 并去掉 `export KUBECONFIG=`（`--strip-kubeconfig` 可单独跑，幂等）。`config/.env` 只同步 `NTFY_URL`、`NTFY_TOPIC`、`ALERT_RELAY_TOKEN`，外加现有的 PROD viewer。不再安装 runner，不再 rsync `agent/remediation`，不再 `npm install`。bootout 并删除 `com.bifrost.remediation-runner`、`com.bifrost.hermes-gateway`、`ai.hermes.gateway`、`ai.hermes.dashboard` 的 plist。不再 rsync `mcp/platform`，不再改 Hermes 配置。`~/.hermes` 保留。冒烟只查 operator-plane `/health` 和 .50 告警中转。
  - 删除 `scripts/agent/deploy_hermes_gateway.sh`、`scripts/agent/tool_smoke.sh`、`scripts/agent/tool_smoke_test.sh`。
  - `Makefile` 构建 operator-plane 时 `-X main.version=<12 位 git SHA>`。`/health` 返回 `version`。

### 防线

- `scripts/agent/test_deploy_mac_mini_secrets.py`：同步清单没有 `CURSOR_API_KEY`、operator、admin、`REMEDIATION_RUNNER_TOKEN`、`GIT_BRIDGE_URL`；脚本没有 scp kubeconfig；`--strip-kubeconfig` 跑两次仍幂等。
- 既有 `test_deploy_mac_mini_relay.py`、`test_deploy_mac_mini_viewer.py`。

### 门禁

- `python3 scripts/agent/test_deploy_mac_mini_secrets.py` → 3 passed
- `python3 scripts/agent/test_deploy_mac_mini_viewer.py` → 6 passed
- `python3 scripts/agent/test_deploy_mac_mini_relay.py` → 6 passed
- `bash -n scripts/agent/deploy_mac_mini.sh` → exit 0

### 验收

```bash
git -C /tmp/cursor-w33/w33-platform grep -n 'CURSOR_API_KEY\|scp .*bifrost-k3s' scripts/agent/deploy_mac_mini.sh
```

预期：无匹配。

### 要 Owner 批

重部署本身在「上线顺序」第 4 步，要批。本段没有单独的集群写命令。

### 后续

- `agent/remediation` 与 `agent/hermes-gateway` 源码树还在仓库里，部署脚本已经不再安装。plist 源文件也还在，部署时会删远端已安装的那份。
- `~/.hermes` 未删。

## 2. peer-watchdog

### 改动

- 同上 platform SHA。`scripts/agent/peer_watchdog.sh` 探 `${PEER_URL%/}/health`，不通则 `launchctl kickstart -k gui/$(id -u)/com.bifrost.operator-plane`。告警中转监视未改。部署脚本里参数名仍是 `PEER_URL`，值改为对端 operator-plane `:8783`。

### 防线

- 脚本注释与 kickstart 目标。没有单独的新测试文件；`bash -n` 通过。

### 门禁

- `bash -n scripts/agent/peer_watchdog.sh` → exit 0

### 验收

```bash
git -C /tmp/cursor-w33/w33-platform grep -n 'com.bifrost.operator-plane' scripts/agent/peer_watchdog.sh
```

预期：kickstart 那一行命中 `com.bifrost.operator-plane`，没有 `remediation-runner`。

### 要 Owner 批

无。随第 4 步重部署生效。

### 后续

无。

## 3. runner / Hermes 退出，patrol 留在 PROD

### 改动

- 同上 platform SHA。
  - 删除 `api/internal/remediation`、`api/internal/hermesgateway`、`/remediation/*`、`GET /api/v1/agent/hermes/health`、MCP `get_remediation_health` 与 `list_remediation_jobs`（stdio 现为 48）。
  - `agentbridge` 探 `PLANE_HEALTH_URLS` 上两台 operator-plane 的 `/health`。JSON 字段名 `runners` / `remediation_runner` 保留，service 为 `operator-plane`。夜间报告固定为 remediation runner retired。
  - skill 结果改由 `api/internal/agentgovernance/outcome.go` 读写，路径与旧 jobs 目录相同，治理不再 import remediation。
  - operator-plane 只提供 `GET /agent/bridge`、`/agent/deploy`、`/agent/launchd`。`/patrol/*` 由 platform-api 自己挂上，读 workers 写入共享状态的记录，api 进程不 `StartBackground`。三个写路由（enable / trigger / webhook）也留在 api，mini 不需要 PROD operator 令牌。
  - Console 删掉 runner 界面与 Hermes health 行。Mini 卡片显示两台 operator-plane 的 status 和 version。`console/scripts/cluster-failure-triage.ts` 不再请求 `/remediation/health`。
- bifrost-trade-infra · `cursor/w33-infra` · `8262696e12f0e5891e6366010903d70d810eb49d`
  - 两个 overlay 删除 `platform-runner-token.patch.yaml` 及 api/workers 上的 `REMEDIATION_RUNNER_*`。`OPERATOR_PLANE_URL=http://192.168.10.50:8783` 保留。
  - `apply-platform-role-tokens.sh` 不再写入 `REMEDIATION_RUNNER_TOKEN`。
  - 删除 `k8s/cicd/docker/Dockerfile.remediation-runner-stg`，Tekton dockerfile ConfigMap 任务与 `run-deliver-platform.sh` 去掉对它的引用。
  - 两份 `MAINTAINERS.yaml` 逐字节一致：删掉 `.50` / `.52` 的 `com.bifrost.remediation-runner` 和 `.52` 的 `com.bifrost.hermes-gateway`；两条 peer-watchdog 的 `what` 改为「看对端 operator-plane」。

### 防线

- `api/internal/server/server_test.go` · `TestRetiredRoutesAre404`（remediation 路由与 `GET /api/v1/agent/hermes/health`）、`TestPatrolReadsSharedStateInsteadOfProxy`。
- `api/internal/operatorplane/route_table_test.go` · `TestPlaneRouteTableHasNoOperatorRoutes`。
- `api/internal/mcp/catalog_test.go` 与 `mcp/platform` 的 action catalog ratchet（工具数 48）。
- `scripts/check_alert_routing.py` · `assert_runner_token_retired`。
- `make check-maintainers`。

### 门禁

- `cd api && go build ./... && go vet ./... && go test ./...` → exit 0
- `cd mcp/platform && npm test` → 20 passed
- `cd console && npm run lint && npm test && npm run build` → lint 0 error（3 条既有 flex-query warning），683 tests，build exit 0
- infra `make check-maintainers` → exit 0（42 maintainers）
- `cmp agent-config/MAINTAINERS.yaml k8s/monitoring/maintainer-reconcile/MAINTAINERS.yaml` → exit 0
- `kubectl kustomize k8s/overlays/platform-prod` 与 `platform-stg` → exit 0

### 验收

```bash
git -C /tmp/cursor-w33/w33-platform grep -n 'HandleList\|patrol' api/internal/server/server_test.go | head
```

预期：`TestPatrolReadsSharedStateInsteadOfProxy` 在。设了 `OPERATOR_PLANE_URL` 时 `GET /api/v1/patrol/skills` 不进代理，返回共享状态里的记录。

`python3 scripts/check_maintainers.py --live`：mini 重部署之前预期有 remediation-runner 与 hermes-gateway 漂移；重部署之后预期 drift 0。本道没有跑 `--live`。

### 要 Owner 批

无（上线时的重部署和 Secret 见顺序第 4、7 步）。

### 后续

- 架构目录、checklist、`agentTaskCatalog` 里仍有 “Remediation runner” 历史文案，不是客户端。信号 id `engineer.remediation-runner` 保留，避免 checklist 对不上；界面标签已是 operator-plane。
- `index.css` 里 `.remediation-step-dot` 仍被 `materialFrames.test.ts` 要求存在，未删。
- `ops-context.yaml` 里提到 `:8781` 的两段是 spine 历史 note，与 platform 源文件必须逐字节一致，所以留着。

## 4. rolling_reboot

### 改动

- platform 同上 SHA。动作目录增加 `rolling_reboot`，D 级，没有自己的 HTTP 路由。批准时执行器只返回命令，不 SSH、不 kubectl。审批 id 从批准请求的 chi 路由参数读取。`api/internal/approvals/` 未改。
- infra 同上 SHA。`scripts/k3s/rolling-reboot.sh --execute` 必须带 `--approval <id>`。开跑前用已有的 `PLATFORM_PROD_VIEWER_TOKEN` 做 `GET /api/v1/approvals/<id>`，要求 action 为 `rolling_reboot`、status 为 `executed`、未过期，否则拒绝，不 cordon。工作日规则仍只在 `--execute` 里。默认 dry-run。

### 防线

- `api/internal/actions/rolling_reboot_test.go` · `TestRollingRebootCatalogEntry`
- `config/actions-catalog.json` 含 `rolling_reboot`（按 id 排序）
- `scripts/k3s/test_rolling_reboot_plan.py`：缺审批、action 不对、不是 executed、已过期都拒绝。既有工作日测试仍在。

### 门禁

- `go test ./internal/actions/` → exit 0（含在 api 全量里）
- `python3 -m unittest scripts/k3s/test_rolling_reboot_plan.py` → 15 tests，exit 0

### 验收

```bash
python3 -m unittest scripts/k3s/test_rolling_reboot_plan.py
```

在 infra worktree 里跑。预期：exit 0。缺审批、action 不对、不是 executed、已过期的用例都是脚本拒绝，不 cordon。

批准之后平台返回的命令是：

```bash
bash scripts/k3s/rolling-reboot.sh --execute --approval <id>
```

### 要 Owner 批

动作本身上线后，每次真重启仍走现有审批。本道不执行。

### 后续

执行者今天仍是有节点 SSH 的人。第 3 步（另派）之后只有 Owner。

## 5. ⑤ 版本

### 改动

- platform 同上 SHA。新增 `config/running-images.yaml` 与 `GET /api/v1/releases/running-images`。应用名不写进 Go。缺的环境返回 `absent: true` 与 `No STG` / `No PROD`。agent 行读两台 plane 的 `/health` `version`。
- infra 同上 SHA。`sync_platform_k8s_config.sh` 复制该文件；两个 overlay 的 `configMapGenerator` 列出 `config/running-images.yaml`；`check_ops_context_parity.py` 的 `check_running_images` 要求两份副本与 platform 源逐字节一致。副本已放进两个 overlay。
- Console `releaseView`：research、Plugins（market-data）、Mac mini agent 用这个端点。Platform 与 trade 仍用原有 release records。

### 防线

- `api/internal/releases/images_test.go` · `TestRunningImagesReadsConfigAndMarksMissingSTG`
- `console/src/pages/shell/releases/__tests__/releaseView.test.ts`：`absent: true` 显示 `No STG`
- `scripts/check_ops_context_parity.py` · `check_running_images`
- `agent-config/RATCHETS.md` 「Releases 正在跑的镜像清单两份副本一致」

### 门禁

- `go test ./internal/releases/` → exit 0
- `PLATFORM_ROOT=/tmp/cursor-w33/w33-platform python3 scripts/check_ops_context_parity.py` → exit 0（55 decisions，D10=BLOCKED）

### 验收

```bash
PLATFORM_ROOT=/tmp/cursor-w33/w33-platform python3 scripts/check_ops_context_parity.py
```

预期：exit 0。research / market-data / agent 没有 stg 条目，所以 STG 列是 `No STG`。

### 要 Owner 批

无。随 platform 发版进 ConfigMap。

### 后续

ib-gateway 镜像没有 tag，单元格显示 `sha256:` 开头的 digest。

## 6. 待重启信号

### 改动

- infra 同上 SHA。
  - `k8s/monitoring/bifrost-node-reboot-required.yaml`：monitoring 命名空间 DaemonSet，busybox，只读 hostPath `/var/run`，每 5 分钟。指标 `bifrost_node_reboot_required{node}` 与 `bifrost_node_reboot_required_since_seconds{node}`（文件 mtime；文件不在则为 0）。不在节点上安装任何东西。
  - `bifrost-node-reboot-podmonitor.yaml`、`bifrost-node-reboot-rules.yaml`。告警 `BifrostNodeRebootPending`，severity warning，expr 用 `1209600`，`for: 15m`（防抖，不是 14 天阈值）。不呼人。
  - `MAINTAINERS.yaml` 没有 `signals` 段，`check_maintainers.py` 也不接受别的顶层键。信号写在两份文件头注释里，不是一条 maintainer。
- platform 同上 SHA。Console 节点表在两条 PromQL 都成功且 `node` 对上、值为 1 时显示 `Reboot pending (since YYYY-MM-DD)`。查询走已有的 `GET /api/v1/telemetry/promql`。失败则该格留空。

### 防线

- `scripts/check_alert_routing.py` · `assert_reboot_pending_unpaged`
- `console/src/components/cluster/__tests__/rebootPending.test.ts`
- `agent-config/RATCHETS.md` 「节点待重启超过 14 天只记账」

### 门禁

- `PATH="/usr/bin:$PATH" python3 scripts/check_alert_routing.py` → exit 0
- `kubectl kustomize k8s/monitoring` → exit 0
- console `npm test` 含 rebootPending，exit 0

### 验收

```bash
PATH="/usr/bin:$PATH" python3 scripts/check_alert_routing.py
```

预期：exit 0，且规则文件在 `k8s/monitoring/*.yaml`（该脚本不递归子目录）。

### 要 Owner 批

见上线顺序第 5 步。本道没有 apply。

### 后续

无。

## 7. Grafana

### 改动

- infra 同上 SHA。`scripts/k3s/values-kube-prometheus.yaml`：`root_url: https://ops.bifrost.lan/grafana/`，`serve_from_sub_path: true`。`allow_embedding` 与 anonymous Viewer 保留。NodePort 30883 保留；子路径打开后，这条 NodePort 的路径也会多一层 `/grafana/`。
- PROD `ops-ingressroute.yaml` 增加 `Host(ops.bifrost.lan) && PathPrefix(/grafana)` → `monitoring/kube-prometheus-stack-grafana:80`，priority 100，高于 Console 的 10。STG 网关未改。
- 两个 overlay 的 `PLATFORM_GRAFANA_URL=https://ops.bifrost.lan/grafana`。`clusters.yaml` 的 observability URL 同步改了。
- platform 同上 SHA。`opsToolRackCatalog.ts` 回退地址改为 `https://ops.bifrost.lan/grafana`。builder 测试加了 https 用例。

### 防线

- `console/src/lib/architecture/__tests__/opsToolRackCatalog.test.ts` 的 https 用例。
- IngressRoute 的 priority 注释写明 Traefik 数字越大越先匹配。

### 门禁

- `kubectl kustomize k8s/overlays/platform-prod` → 渲染出 priority 100 的 `/grafana` 路由；STG 仍只有 `stg.ops.bifrost.lan`
- console `npm test` → exit 0

### 验收

```bash
kubectl kustomize k8s/overlays/platform-prod | awk '/PathPrefix..grafana/,/priority:/'
```

预期：看到 `PathPrefix(\`/grafana\`)` 与 `priority: 100`。

### 要 Owner 批

helm upgrade，见下。本道没有执行。

```bash
KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}" \
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version 88.1.3 \
  --namespace monitoring \
  --create-namespace \
  --timeout 10m \
  --values scripts/k3s/values-kube-prometheus.yaml
```

版本钉在 `scripts/k3s/install-kube-prometheus-stack.sh` 的 `CHART_VERSION=88.1.3`。在合并后的 infra 检出里跑。

### 后续

NodePort `http://192.168.10.73:30883/` 在 helm upgrade 之后要改成 `http://192.168.10.73:30883/grafana/`。

## 上线顺序

每一步都由 Claude 执行。代码分支是 `cursor/w33-platform`（`9a0d1eded11fbfb9669f2ff52500cd242826bb62`）和 `cursor/w33-infra`（`8262696e12f0e5891e6366010903d70d810eb49d`）。

1. 合并两条分支。不要 Owner 批（本报告验收通过之后）。
2. STG 发布，Owner 过目。要 Owner 批。
3. PROD 发布。要 Owner 批。
4. 重部署两台 mini（撤 runner、hermes、kubeconfig）。要 Owner 批。在合并后的 platform 检出里：

```bash
PEER_SSH=vision@192.168.10.52 PEER_URL=http://192.168.10.52:8783 \
  scripts/agent/deploy_mac_mini.sh vision@192.168.10.50
AGENT_ROLE=standby PEER_SSH=vision@192.168.10.50 PEER_URL=http://192.168.10.50:8783 \
  scripts/agent/deploy_mac_mini.sh vision@192.168.10.52
```

`PEER_RELAY_URL` 不传，远端已有的中转地址会保留。`~/.hermes` 不会被删。

5. apply 待重启 DaemonSet、PodMonitor、告警。要 Owner 批。在合并后的 infra 检出里：

```bash
kubectl apply -f k8s/monitoring/bifrost-node-reboot-required.yaml \
  -f k8s/monitoring/bifrost-node-reboot-podmonitor.yaml \
  -f k8s/monitoring/bifrost-node-reboot-rules.yaml
```

6. helm upgrade Grafana。要 Owner 批。命令见第 7 节，原样执行。STG 网关不要改。
7. 去掉 runner 令牌。要 Owner 批。它不是单独的 Secret，而是 `bifrost-platform-role-tokens` 里的 `REMEDIATION_RUNNER_TOKEN` 键。不要删整个 Secret。合并后的 `scripts/k3s/apply-platform-role-tokens.sh` 只写 viewer / operator / admin，重跑会把这个键换掉：

```bash
scripts/k3s/apply-platform-role-tokens.sh
```

8. 对账。不要 Owner 批。重部署之前预期 runner 与 hermes-gateway 漂移；第 4 步之后预期 drift 0：

```bash
python3 scripts/check_maintainers.py --live
```
