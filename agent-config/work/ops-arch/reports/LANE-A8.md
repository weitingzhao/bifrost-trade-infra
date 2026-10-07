## LANE-A8

- Claim：成立。`origin/main` 的 `scripts/agent/deploy_mac_mini.sh` 用部署者本机环境生成远端配置：未 export 时 `PEER_RELAY_URL="${PEER_RELAY_URL:-}"`（第 29 行）与 `ALERT_RELAY="${ALERT_RELAY:-off}"`（第 32 行），再无条件写入 `export PEER_RELAY_URL=`（第 200 行，`env.local.sh`）和 `export ALERT_RELAY=`（第 275 行，`env.operator-plane.sh`）。2026-10-07 部署者没设 `ALERT_RELAY=on`，.50 被写成 `off`。
- 改动：bifrost-platform · `cursor/a8-platform` · `46464410bf841f6865eda3daabea60ab181a9940`
- 防线：`scripts/agent/test_deploy_mac_mini_relay.py`（调用 `deploy_mac_mini.sh --resolve-relay-config`，不 SSH）
  - `test_unset_keeps_remote_on`：未设置 → 保留远端 `on` 和 `PEER_RELAY_URL`
  - `test_explicit_disable_writes_off_and_warns`：`--disable-alert-relay` → `off`，stderr 有醒目 WARNING
  - `test_explicit_off_without_flag_keeps_on`：环境里写 `off` 但没有该参数 → 仍保留 `on` 并警告
  - `test_no_remote_file_defaults_and_warns`：没有远端文件 → 默认 `off` / 空 URL，并警告
  - `test_unset_keeps_quoted_on`、`test_explicit_on_and_explicit_peer_url`
- 门禁：`python3 scripts/agent/test_deploy_mac_mini_relay.py` → 6 passed（OK）；`bash -n scripts/agent/deploy_mac_mini.sh` → exit 0。未跑平台全量 `make test`（改动只在部署脚本及其测试，验收不要求）。
- 验收：在该分支上
  - `python3 scripts/agent/test_deploy_mac_mini_relay.py` → `Ran 6 tests` 且 `OK`
  - `bash -n scripts/agent/deploy_mac_mini.sh` → exit 0
  - `git -C bifrost-platform diff origin/main...cursor/a8-platform --stat` 只有：
    - `scripts/agent/deploy_mac_mini.sh`
    - `scripts/agent/test_deploy_mac_mini_relay.py`
- 要 Owner 批：没有。未部署、未发版、未改 mini。分支已推 `origin/cursor/a8-platform`，`origin/main` 仍是 `894a88f47d64683b88a495493116a8ade8fceb49`。
- 后续：LANE-T2 也在改同一脚本的「Post-deploy tool smoke」（带 runner 令牌）。本道没动那一段（与 `origin/main` 逐字相同）。合并冲突由 Claude Code 处理。故意 `--disable-alert-relay` 会先写成 `off` 并打印警告，但部署结束仍核对 .50 `GET :8783/health` 的 `alert_relay:true` 和 .52 `env.local.sh` 里的非空 `PEER_RELAY_URL`，不满足就非 0 退出并打印修法——所以故意关掉不会被当成成功部署。
