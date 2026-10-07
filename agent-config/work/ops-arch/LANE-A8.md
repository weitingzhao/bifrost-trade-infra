# LANE-A8 — 部署 Mac mini 时不许悄悄关掉告警中转

仓库：bifrost-platform，分支 `cursor/a8-platform`（从最新 origin/main 开）。

## 事实（2026-10-07 事故）

- .50 的 operator-plane 13:18（.50 本地时间）被重新部署，`~/bifrost-agent/config/env.operator-plane.sh` 被重写成 `export ALERT_RELAY=off`。告警中转从此关闭：Owner 的呼叫与心跳都 404，直到 14:17 Claude Code 手工改回 `on` 并重启。.52 的互看 watchdog 13:23 呼了 Owner（护栏起作用）。
- 原因：`scripts/agent/deploy_mac_mini.sh` 按**部署者本机**的环境变量生成远端配置；部署者没 export `ALERT_RELAY=on`，就写成了 `off`。.52 的 `PEER_RELAY_URL` 同理，只是那次碰巧还在。
- 另一条道 LANE-T2 也在改 `deploy_mac_mini.sh`（工具冒烟带 runner 令牌）。本道**只改告警中转相关的环境处理**，不碰别的段落；合并冲突由 Claude Code 处理。

## 要做

1. 部署者没有显式设置 `ALERT_RELAY` / `PEER_RELAY_URL` 时，**保留远端现有值**（先读远端的 `env.operator-plane.sh` / `env.local.sh`），而不是写默认值。
2. 要从 `on` 改成 `off`，必须显式参数（如 `--disable-alert-relay`），并打印醒目的警告。
3. 部署结束时打印每台的生效值，并核对：`.50` 的 `GET :8783/health` 必须 `alert_relay:true`，`.52` 的 `env.local.sh` 必须有 `PEER_RELAY_URL`；不满足就以非 0 退出，并说明怎么修。
4. 防线：给「生成远端配置」的那段逻辑加测试（bash 函数配假的远端文件，或抽成小脚本用 Python unittest 测），覆盖：未设置 → 保留 `on`；显式关闭 → `off` 并警告；远端没有文件 → 默认值并警告。

## 不做

不 ssh 改 mini、不部署、不发版。

## 验收

- 分支上新增的测试通过；
- `bash -n scripts/agent/deploy_mac_mini.sh` 通过；
- `git -C bifrost-platform diff origin/main...cursor/a8-platform --stat` 只涉及部署脚本与它的测试。
