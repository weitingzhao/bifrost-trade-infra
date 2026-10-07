# LANE-B3R — infra 侧 MCP 切换收尾 + 审批接口的拦截规则

仓库：bifrost-trade-infra，在 `cursor/b3-infra` 上继续（先 rebase 到 origin/main）。

## Owner 决定（2026-10-07）

聊天里批准**保留**（`bifrost-approve` + `permissions.ask`），接受「本机 Agent 理论上能读到 admin 令牌」的风险，先用 preflight 的文本拦截挡一挡；以后不放心再收权。见 ADR §5「已知的接受风险」。

## 要做

1. **写开关**：`.mcp.json` 与 Cursor 模板里 `bifrost-platform`、`bifrost-kubernetes` 的 `MCP_WRITES` 直接设为 `on`。原因：这个分支要等 B1R 在 PROD 上线之后才合并；如果先以 `off` 合并，所有线程的写工具（起流水线等）会在中间断掉。
2. **令牌来源**：配置里不再要求进程环境里有令牌——MCP 进程会从 `~/.config/bifrost/mcp-tokens.env`（600）读（B1R 实现）。在 `.mcp.json.README.md` 写清：这个文件放哪三个键、权限 600、怎么从现有 `bifrost-platform/.env` 生成（命令不打印值），以及 Mac mini 上的线程以后同样需要它。
3. **preflight 拦截**（`agent-config/scripts/agent-guard/preflight.js`，两侧共用）：拦截 Agent 的 Bash / 浏览器 / 其他非 MCP 工具调用中出现的
   - `/api/v1/approvals/<id>/approve`、`/reject` 的直接请求（curl、wget、fetch、浏览器打开 `#approvals` 并点击等）；
   - 读取或引用 `PLATFORM_ADMIN_TOKEN`、`mcp-tokens.env`；
   放行 `mcp__bifrost-approve__*` 工具本身。拦截提示写明原因（ADR §5）。按 CLAUDE.md §7 同步 parity（preflight 是共用实现，只需同步说明与 parity-id），跑 `bash scripts/check-agent-config-parity.sh`。
   - 测试：preflight 现有测试框架里加用例（直接 curl approve → 拦；读 mcp-tokens.env → 拦；`mcp__bifrost-approve__approve_request` → 放）。
4. `check_mcp_cutover.py` 增加：`MCP_WRITES` 必须是 `on`（合并时的状态），且 `bifrost-approve` 只在 Claude 侧。

## 门禁与验收

preflight 测试、`check_mcp_cutover.py --self-test`、parity 检查。报告给出验收命令。

## 不做

不改 `~/.claude/settings.json`、不运行任何 apply 脚本、不创建令牌文件、不推 main。
