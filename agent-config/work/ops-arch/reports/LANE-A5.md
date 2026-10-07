# LANE-A5 报告

只读核对（未改 mini、未 apply、未发版）。.50（ops-mac-agent-02，uid 501）两个任务都已加载：`com.bifrost.nightly-health-check`、`com.bifrost.nightly-drift`，plist 在 `~/Library/LaunchAgents/`。.52（ops-mac-agent-01，uid 501）只有 `com.bifrost.nightly-drift.plist`，未加载；没有 health-check plist。两边都有 `~/bifrost-agent/logs` 和 `~/bifrost-agent/reports`。

## 1. 停掉两个夜间 launchd 任务（部署件）

- 改动：bifrost-platform · `cursor/a5-platform` · `894a88f47d64683b88a495493116a8ade8fceb49`（基线 `79ed8dbb5b662b185f431ecdbe3e5558e2b6a84e`）
- 删了 `agent/deploy/com.bifrost.nightly-health-check.plist`、`agent/deploy/com.bifrost.nightly-drift.plist`、`agent/deploy/nightly-health-check.sh`、`agent/schedules/com.bifrost.nightly-agent.plist`、`scripts/agent/nightly_drift.sh`。`deploy_mac_mini.sh` 不再安装或 bootstrap 夜间任务，仍安装并拉起 `com.bifrost.remediation-runner`。`bootstrap_host.sh` 删掉了第 6 步（复制 nightly-agent plist）。`setup-mac-mini.sh` 本身没有安装段，只 exec `scripts/run_agent.py deploy`，所以没改它；`run_agent.py` 去掉了 `nightly` 子命令。验收 grep 会扫整个 `agent/` 和 `scripts/`，所以一并去掉了已禁用的 Hermes skill、`scan_layer3.py` 里对那条 stream 的对照，以及 runner 里专用于该 scope 的 autofix prompt。runner 的 plist、`server.ts`、`POST /run` 都还在。
- 防线：`agent/hermes-gateway/src/skills.test.ts` · `LANE-A5: deploy artifacts do not schedule the retired 03:00 jobs`（8 passed，exit 0）
- 门禁：在 worktree `api/` 里分开看退出码。`go build ./...` → 0；`go vet ./...` → 0；`go test ./...` → 0（56 个包 ok，0 fail）。Hermes `npx tsx --test src/*.test.ts` → 0（8 passed）。
- 验收：`git -C bifrost-platform grep -n "nightly-health-check\|nightly-drift" cursor/a5-platform -- agent scripts` → 无输出，exit 1
- 要 Owner 批：在 .50 / .52 卸载（下面整段原样执行）。合并与发版走 Claude Code，不要在这条道上 apply。
- 后续：`config/ops-context.yaml` 和 infra 两份 overlay 副本里仍有那条夜间 stream（不在 `agent/` `scripts/` 下，验收 grep 扫不到）。`api/internal/driftproposal/handler.go` 仍会发出原来的 autofix scope，runner 不再有专用 prompt，会落到通用 SRE prompt。mini 上的脚本还在（见下），runner 的 `POST /nightly/run` 只要文件还在就会执行它。

### 要 Owner 批 — 卸载命令

只移动 LaunchAgents 里的 plist。不删 `~/bifrost-agent/logs` 和 `~/bifrost-agent/reports`。bootout 对未加载的任务是空操作。

.50（两个任务都在跑）：

```bash
ssh -o BatchMode=yes vision@192.168.10.50 'bash -s' << 'EOF'
set -u
uid=$(id -u)
domain="gui/${uid}"
backup="${HOME}/bifrost-agent/backup/launchd-nightly-20261007"
mkdir -p "${backup}"
launchctl bootout "${domain}/com.bifrost.nightly-health-check" 2>/dev/null || true
launchctl bootout "${domain}/com.bifrost.nightly-drift" 2>/dev/null || true
for label in com.bifrost.nightly-health-check com.bifrost.nightly-drift; do
  src="${HOME}/Library/LaunchAgents/${label}.plist"
  if [ -f "${src}" ]; then
    mv "${src}" "${backup}/"
    echo "moved ${src}"
  else
    echo "no plist ${src}"
  fi
done
echo "kept ${HOME}/bifrost-agent/logs"
echo "kept ${HOME}/bifrost-agent/reports"
ls -ld "${HOME}/bifrost-agent/logs" "${HOME}/bifrost-agent/reports" "${backup}"
EOF
```

.52（只装了 drift plist，当前未加载；没有 health-check plist）：

```bash
ssh -o BatchMode=yes vision@192.168.10.52 'bash -s' << 'EOF'
set -u
uid=$(id -u)
domain="gui/${uid}"
backup="${HOME}/bifrost-agent/backup/launchd-nightly-20261007"
mkdir -p "${backup}"
launchctl bootout "${domain}/com.bifrost.nightly-health-check" 2>/dev/null || true
launchctl bootout "${domain}/com.bifrost.nightly-drift" 2>/dev/null || true
for label in com.bifrost.nightly-health-check com.bifrost.nightly-drift; do
  src="${HOME}/Library/LaunchAgents/${label}.plist"
  if [ -f "${src}" ]; then
    mv "${src}" "${backup}/"
    echo "moved ${src}"
  else
    echo "no plist ${src}"
  fi
done
echo "kept ${HOME}/bifrost-agent/logs"
echo "kept ${HOME}/bifrost-agent/reports"
ls -ld "${HOME}/bifrost-agent/logs" "${HOME}/bifrost-agent/reports" "${backup}"
EOF
```

磁盘上还留着脚本，卸载命令按规格没有动它们：.50 有 `~/bifrost-agent/nightly-health-check.sh`、`nightly-drift.sh`、`nightly_drift.sh`；.52 有 `~/bifrost-agent/nightly_drift.sh`。下次部署不会再拷回去。若要让 runner 的 `/nightly/run` 也找不到它们，把这些文件挪进同一个 backup 目录即可，日志和报告目录不要动。

## 2. git-bridge 不再是集群功能

- 改动：
  - bifrost-trade-infra · `cursor/a5-infra` · `8da7b1eda486f4bd9a50096e7fea31605020e1ed`（基线 `df66d0d4dee88881be291bc9fe2cba3ee9d8abeb`）。从 `k8s/overlays/platform-prod/platform-api-agent-bridge-env.patch.yaml`、`platform-prod/platform-workers-env.patch.yaml`、`platform-stg/platform-api-observability-env.patch.yaml`、`platform-stg/platform-workers-env.patch.yaml` 去掉 `GIT_BRIDGE_URL`。
  - bifrost-platform · 同一分支 `894a88f47d64683b88a495493116a8ade8fceb49`。`GIT_BRIDGE_URL` 或 `SATELLITE_PROBE_BRIDGE_URL` 未设置时，bridge 探针 error 为 `local-only (dev workstation)`，checklist 信号为 `unknown`，detail 为同一句，不再是 fail。
- 防线：`api/internal/checklist/prober_test.go` · `TestProberUnsetBridgesAreLocalOnly`；`api/internal/agentbridge/handler_test.go` · `TestHandleBridgeNotConfiguredProbesReturnStatus`（断言两个 bridge 的 Error）。overlay 没有 env 单测，infra 侧防线就是下面的 grep。
- 门禁：同上，`go build` / `go vet` / `go test ./...` 均为 exit 0。checklist 与 agentbridge 包单独跑也是 exit 0。
- 验收：`git -C bifrost-trade-infra grep -n GIT_BRIDGE_URL cursor/a5-infra -- k8s/overlays/platform-prod k8s/overlays/platform-stg` → 无输出，exit 1。`cd bifrost-platform/api && go test ./internal/checklist/... ./internal/agentbridge/...` → 两个包 ok，exit 0。
- 要 Owner 批：把 `cursor/a5-infra` 合进 infra `main` 等于改集群。Argo `bifrost-platform-stg` / `bifrost-platform-prod` 是 automated + prune + selfHeal，`GIT_BRIDGE_URL` 在 last-applied 里，合进去之后三方合并会从四个 Deployment 上拿掉它。旧镜像已经把 `not_configured` 记成 `unknown`；新文案 `local-only (dev workstation)` 要等 platform 镜像按流程发版才出现。这条道没有 apply、没有起 PipelineRun。
- 后续：`scripts/agent/deploy_mac_mini.sh` 仍给 mini 上的 operator-plane 写指向开发机 :8785 的 git-bridge 地址（`PLATFORM_LAN_HOST`，默认 .40）。那是带外平面，不在本道的 overlay 范围内。四个 Deployment 上都没有 `SATELLITE_PROBE_BRIDGE_URL`，probe bridge 已经是未配置。

## 3. STG `AGENT_DEPLOY_*` 从哪来

结论：不在 git 里，是 2026-07-19 的一次手工 `kubectl patch`，所以分支上没有可删的清单。

证据（只读，2026-10-07）：

- `kubectl kustomize k8s/overlays/platform-stg` 的渲染结果里没有 `AGENT_DEPLOY`。`origin/main` 的 `k8s/` 和 platform 仓库的部署清单里也没有 `AGENT_DEPLOY_ENABLED` / `AGENT_DEPLOY_REMOTE`（代码只读这两个环境变量；`.env.example` 里是注释掉的本机示例）。
- 活对象只有 `bifrost-platform-stg` / `platform-api`：`AGENT_DEPLOY_ENABLED=1`，`AGENT_DEPLOY_REMOTE=vision@192.168.10.50`。STG platform-workers、PROD platform-api、PROD platform-workers 都没有这两项。
- `--show-managed-fields`：这两项的 manager 是 `kubectl-patch`，时间 `2026-07-19T06:57:52Z`。`kubectl.kubernetes.io/last-applied-configuration` 里没有 `AGENT_DEPLOY`（有 `GIT_BRIDGE_URL`）。
- Argo app `bifrost-platform-stg` 源是 `bifrost-trade-infra` `k8s/overlays/platform-stg` @ `main`，状态 Synced，selfHeal + prune，`ignoreDifferences` 为空。strategic-merge 的三方合并不会删掉从未进过 last-applied 的 env，所以这次 patch 一直留着。

要 Owner 批（从 STG platform-api 拿掉；Argo 不会把它写回去，因为它不在 git 里）：

```bash
kubectl -n bifrost-platform-stg set env deployment/platform-api AGENT_DEPLOY_ENABLED- AGENT_DEPLOY_REMOTE-
```

后续：无。platform 代码仍在 `AGENT_DEPLOY_ENABLED=1` 时允许 Console 部署，那是本机 `.env` 的开关，不是这条 STG env。

## 阻塞

无。preflight 没有拦截。没有 ssh 改远程，没有 apply / delete / helm / release.sh / 数据库写入。共享 checkout 未改。worktree 已在推送后删除。
