# LANE-A5 — 停掉 .50 夜间 LLM；PROD 不再依赖笔记本

ADR §3、§4。仓库：bifrost-platform（分支 `cursor/a5-platform`）、bifrost-trade-infra（分支 `cursor/a5-infra`）。

## 事实（10-07 实测）

- .50 有两个 launchd 任务，都是每天 03:00（本地时间）：
  - `com.bifrost.nightly-health-check`：向 runner `POST /run`，起一个 LLM agent，用 `~/.kube/bifrost-k3s.yaml`（k3s `default` 用户 = 集群管理员）；它连的 platform 是 STG `:30878`，连续多晚 `fetch failed`。
  - `com.bifrost.nightly-drift`：漂移扫描，发现问题会叫 Cursor 修；上次退出码 1。
  - 这两件事现在由 PROD platform-workers 的检查探测器（每 10 分钟）和只报告的 patrol autopilot（每 15 分钟）覆盖。
- 部署件在 bifrost-platform：`agent/deploy/com.bifrost.nightly-*.plist`、`agent/deploy/nightly-health-check.sh`、`agent/deploy/setup-mac-mini.sh`、`scripts/agent/deploy_mac_mini.sh`；.50 上还有 `~/bifrost-agent/nightly-drift.sh`、`nightly_drift.sh`。
- PROD platform-workers 有 `GIT_BRIDGE_URL=http://192.168.10.40:8785`——那是 Owner 的 Mac Pro。笔记本睡眠时 PROD 的 `git-bridge` 检查项变红。ADR §4：git-bridge 属于本机工具，不是 PROD 的功能。
- STG platform-api 运行中带 `AGENT_DEPLOY_ENABLED=1`、`AGENT_DEPLOY_REMOTE=vision@192.168.10.50`，但在 bifrost-trade-infra `origin/main` 的 `k8s/` 里找不到来源。

## 要做

1. platform：从部署件中移除两个夜间任务（plist、脚本、`setup-mac-mini.sh` / `deploy_mac_mini.sh` 里的安装段）。runner 本身保留。
2. 写卸载手册（报告里给原样命令，Owner 批准后执行）：在 .50（以及 .52，如果也装了）`launchctl bootout` 两个任务、把 plist 移到备份目录、保留日志与报告目录。
3. git-bridge：
   - infra：从 platform-prod / platform-stg overlay 去掉 `GIT_BRIDGE_URL`；
   - platform：未配置 `GIT_BRIDGE_URL` 时，`git-bridge` 检查项报 `unknown`，说明写「local-only (dev workstation)」，不报 fail；同样适用于 `mac-probe-bridge`。加测试。
4. 查清 STG 的 `AGENT_DEPLOY_*` 从哪来（Argo 来源、platform 仓库里的清单、或手工 `kubectl set env`），报告结论；在 git 里的就在分支上删掉。

## 不做

不 ssh 到 mini 上改任何东西；不 apply；不发版。

## 验收

- `git -C bifrost-platform grep -n "nightly-health-check\|nightly-drift" cursor/a5-platform -- agent scripts` 无输出；
- `cd bifrost-platform/api && go test ./internal/checklist/... ./internal/agentbridge/...` 通过；
- `git -C bifrost-trade-infra grep -n GIT_BRIDGE_URL cursor/a5-infra -- k8s/overlays/platform-prod k8s/overlays/platform-stg` 无输出。

## 要 Owner 批

在 .50 / .52 卸载夜间任务的命令；infra 与 platform 分支的合并与发布由 Claude Code 按流程申请。
