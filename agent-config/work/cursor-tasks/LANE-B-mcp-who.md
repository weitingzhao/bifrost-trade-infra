# LANE-B — MCP 的 `start_pipeline_run` 不传 `who`，经 MCP 的发布永远满足不了策略条件（TD-262，platform）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不 apply、不改 `TECH_DEBT.md` / `RATCHETS.md`）。报告写到 `cursor-tasks/reports/LANE-B.md`。
分支：`cursor/b-platform`（bifrost-platform，从当前 `origin/main` 新开）。

## 背景（台账 `### TD-262`）

Owner 签名的发布策略（LANE-RP，分支已就绪、尚未合并）有一条 `window_held_by_requester`：申请方必须持有发布窗口。
MCP 工具 `start_pipeline_run` 的入参只有 `name` / `revision` / `tag`，**不传 `who`**，所以引擎无法把调用方和窗口持有者对上 —— 经 MCP 发起的发布**永远**落到人工审批，而那正是这套策略要消掉的瓶颈。

本会话 2026-10-08 实际验证过：持着窗口经 MCP 发 platform PROD，仍然只拿到一张待决单据。

## 要做

1. 给 MCP 工具 `start_pipeline_run` 加 `who` 入参，透传到 platform-api。
   - 文件在 `mcp/platform/src/`（`index.ts`、`actionTiers.ts`、`stdioToolNames.ts`、`writeGate.test.ts` 一带）。
   - `who` 的值由调用方给，**不要**在 MCP 侧自己推断主机名或用户名去填 —— 自报的身份等于没有身份，服务端照样要拿它和窗口比。
2. 服务端**保持**要求 `who` 等于窗口持有者，不要为了让它通过而放宽。缺 `who` 时的行为：**拒绝，并说清缺什么**，不要静默退回人工审批（静默退回正是这条债藏了这么久的原因）。
3. 防线：一条测试断言不带 `who` 的 `start_pipeline_run` 被拒且错误里点明 `who`；一条断言 `who` 与窗口持有者不一致时被拒。
4. 门禁：`cd api && go build ./... && go vet ./... && go test ./...`；`cd mcp/platform && npx tsc -b && npx vitest run`（按该目录现有脚本）。退出码分开记录。

## 边界

- **和 LANE-RP 有逻辑依赖、无文件重叠**：RP 碰的是 `api/internal/releasepolicy/`、`api/internal/approvals/service.go`、`approvalnotify/`、console 的 release-policy 组件；本道碰 `mcp/platform/src/` 和 `start_pipeline_run` 的服务端入口。
  RP 合并可能在本道之前或之后 —— **不要依赖 `releasepolicy` 包里的任何符号**，本道只负责把 `who` 送到，条件判定归 RP。碰到 RP 的文件就停下写报告。
- 不要去点或打任何审批接口，不要读 `PLATFORM_ADMIN_TOKEN` 或 `~/.config/bifrost/mcp-tokens.env`。
- 不推 main、不发版、不 apply。

## 验收（Claude Code 会照跑）

合并后 `git -C bifrost-platform grep -n "who" origin/main -- mcp/platform/src` 至少一行在 `start_pipeline_run` 的入参定义里；不带 `who` 的调用被拒而不是生成待决单据。
