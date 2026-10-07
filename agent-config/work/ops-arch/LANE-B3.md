# LANE-B3 — MCP 改连 PROD（先读后写）+ 聊天里批准的工具

ADR §4、§5。仓库：bifrost-platform `cursor/b3-platform`（`mcp/`）；bifrost-trade-infra `cursor/b3-infra`（`agent-config/`）。接口照 README「接口约定」。

## 事实（2026-10-07 实测）

- `agent-config/.mcp.json` 的 6 个 MCP server 全部 `PLATFORM_API_URL=http://127.0.0.1:8780`（Owner 笔记本上的 platform-api，集群管理员 kubeconfig、本地状态停在 09-29）。PROD platform-api：NodePort 30876（各节点与 VIP 192.168.10.100 均可试），Console 走 `ops.bifrost.lan`。
- `mcp/platform/src/platformClient.ts` 默认用 `PLATFORM_OPERATOR_TOKEN`；三个只读桥用 `PLATFORM_TOKEN_ENV_KEY=PLATFORM_VIEWER_TOKEN` 钉住 viewer（TD-225，见 `.mcp.json.README.md`）。
- dev-sessions（bdev）与 git-bridge 是 Owner 笔记本上的东西，不属于 PROD。
- Cursor 侧有自己的 MCP 配置（`~/.cursor/mcp.json`），双轨规则见根 `CLAUDE.md` §7。

## 要做

1. **地址**：选一个单节点故障也能用的 PROD 地址（优先 VIP + NodePort；验证可达后写进报告）。`.mcp.json` 里平台类 server 改指 PROD。新增 `bifrost-local`（只指 127.0.0.1:8780），只暴露 dev-sessions 与本机 git-bridge 相关工具。
2. **分两步切**，用环境变量控制，不用改代码：
   - 读：viewer server（redis / postgres / prometheus）与所有只读工具先切 PROD；
   - 写：B1 在 PROD 上线后再切（报告里写清怎么切）。写工具改为：B 级直接调；C / D 级改成「创建申请 → 返回申请号」，不再直调。
3. **新工具**（`bifrost-platform` server）：`request_action`、`get_request`、`list_requests`、`wait_for_request`（轮询到 executed / failed / rejected / expired 或超时）。请求头带 `X-Bifrost-Session`（取 `CLAUDE_CODE_HOST_SESSION_ID`，没有就取 Cursor 的会话标识或主机名）。
4. **聊天里批准**：新 server `bifrost-approve`，只有 `approve_request`、`reject_request`、`list_pending`，令牌钉在 `PLATFORM_ADMIN_TOKEN`（TD-225 同样的钉法），`channel: "chat"`。**只进 Claude 的 `.mcp.json`，不进 Cursor 侧配置。**
5. **Claude 用户级权限**：在 `agent-config/claude/auto-mode/` 的 payload 里加 `permissions.ask`：`mcp__bifrost-approve__approve_request`、`mcp__bifrost-approve__reject_request`（每次都要 Owner 点「允许」）。只准备 payload、改 `apply-auto-mode.sh` 的说明，**不执行**（auto mode 规则只能 Owner 应用）。报告里写明需要实测：auto mode 下这条 ask 是否真的弹窗。
6. 双轨：Cursor 侧对应的配置说明 / 模板同步（不含 `bifrost-approve`），两侧 parity-id 按 §7 处理，跑 `bash scripts/check-agent-config-parity.sh`。
7. 防线：
   - 配置检查：除 `bifrost-local` 外没有 server 指向 127.0.0.1；`bifrost-approve` 只出现在 Claude 侧；
   - MCP 测试：C / D 级写工具返回申请号而不是直调；`approve_request` 只在 approve server 里。

## 门禁与验收

`mcp/platform`：`npx tsc -b && npm test`（按该目录现有脚本）；infra：parity 检查。验收命令写进报告。

## 要 Owner 批

应用 Claude 用户级权限 payload；切换写操作（B1 上线后）。
