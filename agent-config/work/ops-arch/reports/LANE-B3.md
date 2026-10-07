# LANE-B3 报告

PROD 地址：`http://192.168.10.100:30876`（kube-vip VIP + NodePort）。
依据 `k8s/overlays/platform-prod/nodeport-prod.patch.yaml`，30876 是 PROD platform-api（STG 是 30878）。
2026-10-07 只读核实：

- `curl -sS -m 5 http://192.168.10.100:30876/health` → HTTP 200，JSON `status` 为 `ok`，`service` 为 `bifrost-platform-api`
- 同一路径在 `192.168.10.73` 与 `192.168.10.70` 也是 HTTP 200。VIP 不把客户端钉死在单节点上
- `http://ops.bifrost.lan/health` → HTTP 301，那是 Console，MCP 不走它

没有改共享 checkout。两个 worktree 已在推送后删除。报告没有推。

## 改动

- bifrost-platform · 分支 `cursor/b3-platform` · `40187953eb7c2e4754259316d091ce2ec15fb466`（父提交 origin/main `46464410bf841f6865eda3daabea60ab181a9940`）
  - `mcp/platform`：B 级写在 `MCP_WRITES=on` 时直调；C/D 级改为 `POST /api/v1/approvals` 并返回申请号，不打原路由。默认 `MCP_WRITES` 未设置或 `off` 时写请求不发出。
  - 全量 server 新工具：`request_action`、`get_request`、`list_requests`、`wait_for_request`。请求头 `X-Bifrost-Session` 取 `CLAUDE_CODE_HOST_SESSION_ID`，否则 `CURSOR_CONVERSATION_ID` / `CURSOR_SESSION_ID`，否则主机名。
  - `MCP_BRIDGE_FOCUS=local`：只注册 `platform_mcp_health`、`list_dev_sessions`、`get_dev_session_logs`、`restart_dev_session`、`get_local_git_bridge`。重启 git-bridge 走 dev-session 直调（不经过写门闩）。
  - `MCP_BRIDGE_FOCUS=approve`：只注册 `approve_request`、`reject_request`、`list_pending`。`approve_request` 的 body 固定 `{"channel":"chat"}`。
  - Cursor 模板 `config/cursor-mcp-bridges.json` 改到同一 VIP，加上 `bifrost-local`，没有 `bifrost-approve`。令牌只写 `${PLATFORM_*_TOKEN:-}`。
- bifrost-trade-infra · 分支 `cursor/b3-infra` · `f89e1bc0864f60203e2501ee9d2cf1d0e26f9096`（父提交当时的 origin/main `d227dc5aa02038104658e985fa1fe564e1cc7f37`）
  - `agent-config/.mcp.json`：平台 server 与 viewer server（redis / postgres / prometheus）以及 trade 目录 URL 指向 VIP。`bifrost-platform` 与 `bifrost-kubernetes` 的 `MCP_WRITES` 为 `off`。新增 `bifrost-local`（`127.0.0.1:8780`）和只在 Claude 侧的 `bifrost-approve`（`PLATFORM_TOKEN_ENV_KEY=PLATFORM_ADMIN_TOKEN`）。
  - Cursor 模板 `agent-config/cursor/mcp.servers.json`：与 Claude 相同，但没有 `bifrost-approve`。
  - 两侧 parity：`workspace-v14` → `workspace-v15`（`CLAUDE.md` 与 `cursor/rules/workspace.mdc`）。`AGENT_FACTS.md` `agent-facts-v9` → `agent-facts-v10`。
  - `claude/auto-mode/release-permissions.json` 的 `permissions.ask` 增加 `mcp__bifrost-approve__approve_request` 与 `mcp__bifrost-approve__reject_request`。`apply-auto-mode.sh` 的说明写明它不写 `permissions.ask`。没有执行任何 apply 脚本。

## 防线

- `bifrost-trade-infra/agent-config/scripts/check_mcp_cutover.py`
  - 除名为 `bifrost-local` 的 server 外，command/args/env 不得出现 `127.0.0.1` / `localhost`
  - `bifrost-approve` 只允许出现在 Claude 的 `.mcp.json`；Cursor 模板有它就失败
  - `*_TOKEN` 的值必须是 `${...}` 插值，脚本不打印这些值
  - `--self-test` 覆盖「好配置 / Cursor 侧出现 approve / 非 local 指向 loopback / 字面量令牌」
- `bifrost-platform/mcp/platform/src/writeGate.test.ts`
  - `C/D write tools return an approval id and do not call the direct route`
  - `does not call fetch while writes are off`
  - `B tier calls the route itself when writes are on`
  - `approve_request posts channel chat and is not a full-server tool`
- 没有改 `TECH_DEBT.md` / `RATCHETS.md`。上面两条要由 Claude Code 登记进台账。

## 门禁

- 在 platform worktree 的 `mcp/platform`：`npx tsc -b` → exit 0；`npx tsc --noEmit` → exit 0；`npm test`（`node --import tsx --test src/*.test.ts`）→ 10 passed，0 failed，exit 0
- `python3 agent-config/scripts/check_mcp_cutover.py --self-test` → `self-test ok`，exit 0
- `python3 agent-config/scripts/check_mcp_cutover.py --cursor <platform worktree>/config/cursor-mcp-bridges.json` → `mcp cutover check ok`，exit 0
- parity：把工作区根的 `CLAUDE.md` / `.cursor` / `.claude` / `scripts` 指到本 infra 提交后跑 `bash scripts/check-agent-config-parity.sh` → exit 0，`Cursor 20 · Claude 20`，spine D10 = BLOCKED。共享 checkout 上的同一脚本也是 exit 0，但它读的仍是未合并的 `workspace-v14`（本道没有改共享 checkout）

## 验收

平台行为（检出 `40187953eb7c2e4754259316d091ce2ec15fb466`，`mcp/platform` 有 `node_modules` 之后）：

```bash
git -C bifrost-platform fetch -q origin && git -C bifrost-platform rev-parse origin/cursor/b3-platform
# 40187953eb7c2e4754259316d091ce2ec15fb466
cd bifrost-platform && git checkout 40187953eb7c2e4754259316d091ce2ec15fb466 -- mcp config/cursor-mcp-bridges.json
cd mcp/platform && npx tsc -b && npm test
```

预期：`tsc -b` exit 0；`npm test` 10 passed。其中 C/D 用例的 fetch 只打到 `/api/v1/approvals` 且响应 `id` 为 `apr-test`；`approve_request` 的 body 是 `{"channel":"chat"}`，`index.ts` 里没有 `approve_request`。

配置（检出 `f89e1bc0864f60203e2501ee9d2cf1d0e26f9096`，旁边有对应的 platform 文件时）：

```bash
git -C bifrost-trade-infra fetch -q origin && git -C bifrost-trade-infra rev-parse origin/cursor/b3-infra
# f89e1bc0864f60203e2501ee9d2cf1d0e26f9096
python3 bifrost-trade-infra/agent-config/scripts/check_mcp_cutover.py --self-test
python3 bifrost-trade-infra/agent-config/scripts/check_mcp_cutover.py \
  --cursor bifrost-platform/config/cursor-mcp-bridges.json
bash scripts/check-agent-config-parity.sh
```

预期：前两条打印 `self-test ok` / `mcp cutover check ok` 且 exit 0。parity exit 0。合并前在共享 checkout 上跑 parity 仍是 v14 对 v14，也会 exit 0；要看到 v15，根上的治理符号链接得指向这个 infra 提交。

健康检查（不需要令牌）：

```bash
curl -sS -m 5 -o /dev/null -w '%{http_code}\n' http://192.168.10.100:30876/health
```

预期：`200`。

## 要 Owner 批

1. 应用 Claude 用户级 `permissions.ask`（本道没有执行）。合并 `cursor/b3-infra` 之后，由 Owner 自己跑：

```bash
bash bifrost-trade-infra/agent-config/claude/auto-mode/apply-release-permissions.sh
```

脚本会把 `release-permissions.json` 里尚缺的 `allow` / `ask` 合并进 `~/.claude/settings.json`（已有条目不重复）。新的两条是 `mcp__bifrost-approve__approve_request` 和 `mcp__bifrost-approve__reject_request`。`apply-auto-mode.sh` 不写 `permissions.ask`，不用为了这两条去跑它。
auto mode 下这两条 ask 会不会真的弹出允许对话框，payload 在仓库里不能证明，必须 Owner 应用之后当场看一次。

2. B1 的审批 API 在 PROD 上线之后再开写。先确认目录在：

```bash
curl -sS -m 10 -o /dev/null -w '%{http_code}\n' http://192.168.10.100:30876/api/v1/actions
```

预期从现在的非 200 变成 `200`。然后只把下面三处里 `bifrost-platform` 与 `bifrost-kubernetes`（`cursor-mcp-bridges.json` 里的名字是 `bifrost-platform` 与 `bifrost-kubernetes-bridge`）的 `MCP_WRITES` 从 `off` 改成 `on`，重启 MCP 进程。不需要改代码。

- `agent-config/.mcp.json`
- `agent-config/cursor/mcp.servers.json`
- `bifrost-platform/config/cursor-mcp-bridges.json`

本机正在用的 `~/.cursor/mcp.json` 不在仓库里，本道没有改它。Cursor 要跟着切的话，按 `cursor/mcp.servers.json` 改那份活配置（不要加 `bifrost-approve`）。

`on` 之后：B 级直调原路由；C/D 级 `POST /api/v1/approvals`，返回体里的 `id` 就是申请号，原写路由不会被调用。`reason` 自动写成 `mcp:<工具名>`。要自带理由和回滚说明，用 `request_action`。

3. 非回环地址不读 `bifrost-platform/.env`。启动 Claude / Cursor 的进程环境里要有 `PLATFORM_VIEWER_TOKEN`、`PLATFORM_OPERATOR_TOKEN`、`PLATFORM_ADMIN_TOKEN`（值不要进仓库，也不要贴进配置）。没有的话，PROD 上的读会 401。`bifrost-local` 仍是回环，可以继续回落 `.env`。

## 后续

- `bifrost-platform/api/internal/mcp/catalog_test.go` 的 `stdioMirroredTools` 仍含 `list_dev_sessions` / `restart_dev_session` / `get_dev_session_logs`，且不含四个 `request_*` / `wait_for_request`。该测试不读 TS 文件，所以 Go 测试仍然绿。本道不改 `api/`（B1 的目录）。全量 server 的 `reg()` 与 `PLATFORM_STDIO_TOOL_NAMES` 已互相对齐，都是 75；console 的 `mcpStdioParity.test.ts` 只扫 `index.ts` 的 `reg(`，本道没改 console（B2）。
- `bifrost-approve` 不看 `MCP_WRITES`。B1 还没上 PROD 时，`approve_request` 会打到尚不存在的审批路由（预期 404），不会执行集群写。
- 没有被 preflight 拦住。没有推 main，没有 deliver / kubectl apply / 写库。
