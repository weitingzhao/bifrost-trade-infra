# LANE-B1R2 — MCP 侧收尾：没设开关时保持原行为、级别以 API 为准

仓库：bifrost-platform，在 `cursor/phase2-platform`（`816a8039`）上继续。只改 `mcp/platform` 与 `config/cursor-mcp-bridges.json`，不动 `api/`、`console/`。

## 为什么（Claude Code 验收 B1R，2026-10-07）

1. **过渡期会断写工具**：`mcp/platform/src/writeGate.ts:23` 把没设置的 `MCP_WRITES` 当作 `off`，写请求一律不发。MCP 是各会话从共享检出里直接加载的（`.mcp.json` 跑 `npx tsx …/bifrost-platform/mcp/platform/src/index.ts`），不经过发版。platform main 一合并、谁把共享检出更新了，而 infra 的 `.mcp.json` 还没有 `MCP_WRITES`，所有线程的起流水线、同步等写工具立刻失效。
2. **级别在 MCP 里抄了一份而且不对**：`actionTiers.ts:202` 把所有 `start_pipeline_run` 当 C（API 对 B 级回「call directly」）；`:234`、`:242` 两个 ensure 当 C（API 是 D）；`sweep_failed_backups`、`sync_kubeconfig`、`update_data_clone_schedule`、`market_data_delete` 没有映射，变成 API 不认的 `unlisted_write`。
3. `config/cursor-mcp-bridges.json` 里两个 server 的 `MCP_WRITES` 仍是 `off`，`check_mcp_cutover.py --cursor` 不通过。

## 要做

1. `MCP_WRITES` 三态：
   - **没设置**：保持合并前的老行为——写工具直接调 `PLATFORM_API_URL` 上的原路由（今天的本机行为），不走审批；
   - `on`：走审批感知流程（下一条）；
   - `off`：不发任何写。
2. **级别只以 API 为准**：`on` 时每个写工具先 `POST /api/v1/approvals {action, params}`：
   - `400` 且 `error: "call directly"` → 直接调原路由；
   - `201` → 返回申请号与「等待 Owner 批准」的说明，不调原路由；
   - `403` → 返回禁止原因（X 级 / D10）。
   删掉 `actionTiers.ts` 里写死的级别，只保留「工具名 → 动作 id + 参数」的映射。
3. 补齐映射：上面 4 个动作；任何没有映射的写工具在 `on` 时**明确拒绝**并说明，不发 `unlisted_write`。
4. 跨语言防线：导出一份动作 id 清单（例如 `config/actions-catalog.json`，由 Go 测试校验它与 `api/internal/actions` 的目录一致），TS 测试校验每个写工具的映射都指向清单里的 id、清单里每个由 MCP 暴露的动作都有映射。
5. `config/cursor-mcp-bridges.json` 两个 server 的 `MCP_WRITES` 改为 `on`。

## 测试与验收

- `mcp/platform`：`npx tsc -b && npm test`，新增用例：没设置 → 直调原路由；`on` + API 回 400 call directly → 直调；`on` + 201 → 返回申请号且没调原路由；`on` + 403 → 拒绝；未映射写工具在 `on` 时拒绝。
- `api`：清单一致性的 Go 测试；`go test ./...`。
- `python3 bifrost-trade-infra/agent-config/scripts/check_mcp_cutover.py --cursor bifrost-platform/config/cursor-mcp-bridges.json` → ok。

报告写到 `reports/LANE-B1R2.md`。不推 main、不发版。
