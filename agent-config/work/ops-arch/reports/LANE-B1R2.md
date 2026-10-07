# LANE-B1R2

## Claim
成立。开工时读到的代码与验收描述一致：

1. `mcp/platform/src/writeGate.ts:23` 把未设置的 `MCP_WRITES` 当成 `off`，写请求不发出。
2. `mcp/platform/src/actionTiers.ts:202` 把所有 `start_pipeline_run` 标成 C；`:234`、`:242` 两个 ensure 标成 C；`sweep_failed_backups`、`sync_kubeconfig`、`update_data_clone_schedule`、`market_data_delete` 没有映射，会落到 `unlisted_write`。
3. `config/cursor-mcp-bridges.json` 里 `bifrost-platform` 与 `bifrost-kubernetes-bridge` 的 `MCP_WRITES` 都是 `off`。

`origin/main` 相对该分支没有新提交（merge-base 仍是 `46464410bf841f6865eda3daabea60ab181a9940`），没有 rebase。

## 改动
- 仓库：bifrost-platform
- 分支：`cursor/phase2-platform`
- 完整 SHA：`e6b825b9d549a8d935baeadf2f83f8e4580ee210`
- Change-Id：`Ie4597be64c2513d080a5ba47cacde112ef781c55`
- 起点：`816a80390c5a113484f253f94460888030c1401a`
- 只推了该分支，没有推 main。

`MCP_WRITES` 三态：未设置走原路由、不审批；`on` 先 `POST /api/v1/approvals`（400 `call directly` 再调原路由，201 只返回申请号和等待 Owner 的说明，403 返回拒绝原因）；`off` 不发任何写。`actionTiers.ts` 只保留「路由 → 动作 id + 参数」，四个缺口已补映射。没有映射的写在 `on` 时本地拒绝，不发送 `unlisted_write`。两个 Cursor server 的 `MCP_WRITES` 已改为 `on`。

## 防线
- `mcp/platform/src/writeGate.test.ts`
  - `unset calls the original route and does not ask for an approval`
  - `on plus call-directly calls the original route`
  - `on plus 201 returns the approval id and never calls the original route`
  - `on plus 403 returns the refusal and does not call the original route`
  - `an unmapped write is refused when on and does not call fetch`
  - `every mapping is a catalog id and every MCP-exposed catalog action is mapped`
  - `maps the four catalog routes that had no mapping`
- `api/internal/actions/catalog_json_test.go`：`TestExportedActionsCatalogMatchesCatalog`（对照 `config/actions-catalog.json` 与 `actions.Catalog()`）

## 门禁
- `cd mcp/platform && npx tsc -b` → exit 0
- `cd mcp/platform && npm test` → exit 0（18 passed，0 failed）
- `cd api && go test ./...` → exit 0
- cutover 检查 → exit 0，输出 `mcp cutover check ok`

`origin/main` 上没有 `agent-config/scripts/check_mcp_cutover.py`。实际跑的是 `cursor/b3-infra` 的 `27ecfaedc7698fcd279321270233eac33f146ced` 里那份脚本（连同该提交的 `.mcp.json` 与 `cursor/mcp.servers.json`，因为脚本总会再查这两份），命令：

```bash
python3 /tmp/b1r2-cutover/agent-config/scripts/check_mcp_cutover.py --cursor /tmp/cursor-b1r2-platform/config/cursor-mcp-bridges.json
```

## 验收
在 `cursor/phase2-platform` 的 `e6b825b9d549a8d935baeadf2f83f8e4580ee210` 上：

```bash
cd mcp/platform && npx tsc -b && npm test
```

预期：exit 0，测试全部通过（含 unset 直调、on+400 直调、on+201 只返回申请号、on+403 拒绝、on 时未映射写被拒绝）。

```bash
cd api && go test ./...
```

预期：exit 0，其中 `TestExportedActionsCatalogMatchesCatalog` 通过。

```bash
git -C bifrost-trade-infra show 27ecfaed:agent-config/scripts/check_mcp_cutover.py > /tmp/check_mcp_cutover.py
python3 /tmp/check_mcp_cutover.py --cursor bifrost-platform/config/cursor-mcp-bridges.json
```

预期：若只把脚本抽出来、旁边没有该提交的 `.mcp.json`，脚本还会报缺默认配置。在 `27ecfaed` 的 `agent-config/` 布局下跑 `--cursor` 指向本文件，预期 `mcp cutover check ok`、exit 0。`bifrost-platform` 与 `bifrost-kubernetes-bridge` 的 `MCP_WRITES` 均为 `on`。

## 要 Owner 批
没有。未做 deliver、PipelineRun、kubectl apply/delete、helm、release.sh、数据库写入、ssh 改远端，也没有改 `TECH_DEBT.md` / `RATCHETS.md` / `~/.claude/settings.json`。没有推 main。

## 后续
- `mcp/README.md:9` 仍写着未设置等于 `off`、以及本地 B 直调 / C/D 审批。本道不允许改 `mcp/platform/` 以外的 MCP 文档，README 还是旧说明。
- 下面这些 MCP 写工具不在 `api/internal/actions` 目录里，映射不能指向目录外的 id。`MCP_WRITES=on` 时它们会被明确拒绝，不再直调，也不发 `unlisted_write`：`ensure_bifrost_namespaces`、`record_operate_queue_execution`、`close_operate_queue_item`、`dismiss_operate_queue_item`、`report_checklist_signals`、`run_release_gate`、`sign_tier_b`。未设置 `MCP_WRITES` 时仍走原路由。Cursor 桥已经设成 `on`，这七个工具在 Cursor 上会拒绝，直到它们进入动作目录。
- 四个新映射还没有对应的 MCP 工具注册（`index.ts` / `stdioToolNames.ts`）。路由若被调用会进审批；目前没有工具入口。
- `restart_dev_session` 仍经 `platformSend` 绕过写门，本机 bdev 行为未改。
