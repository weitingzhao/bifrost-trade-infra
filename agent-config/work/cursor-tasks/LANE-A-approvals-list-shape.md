# LANE-A — Console 的审批列表解析错了字段，而页面测试 mock 的也是那个错字段（TD-261，platform）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不 apply、不改 `TECH_DEBT.md` / `RATCHETS.md`）。报告写到 `cursor-tasks/reports/LANE-A.md`。
分支：`cursor/a-platform`（bifrost-platform，从当前 `origin/main` 新开）。

## 背景（台账 `### TD-261`）

Console 的审批列表解析 `{items}`，而 API 实际答 `{"approvals": [...]}`，所以**无论有多少待决单据，列表永远是空的**。
页面自己的测试 mock 的也是 `{items}`，于是测试一直过，针对的却是 API 从不发送的形状。

这条不是小事：Console 是 Owner 决定 C 级发版的三条路之一（聊天、手机、Console），第三条等于不可用。

实测形状（2026-10-08，本会话经 MCP 读到的真实返回）：

```
{"approvals":[{"id":"appr_…","action":"start_pipeline_run","tier":"C","params":{…},
  "params_hash":"…","status":"pending","reason":"mcp:start_pipeline_run","rollback":"…",
  "requester":"…","created_at":"…","expires_at":"…","decided_at":"0001-01-01T00:00:00Z"}]}
```

## 要做

1. 改 `console/src/api/approvals.ts`：解析 `approvals`。顺带核对**其余字段名**是否也对得上上面这份真实返回（`status` / `tier` / `params_hash` / `expires_at` / `decided_at` 等），对不上的一并修，报告里逐个列出改了哪些。
2. **测试夹具必须从服务端类型生成，不要再手写字面量** —— 这是这条债的根因。做法由你定（从 Go 的响应类型导出 JSON schema / 用一份 `testdata` 夹具两边共用 / 生成 TS 类型），在报告里说明你选了哪条路和为什么。要达到的效果：两边形状再漂移一次，测试就红。
3. `decided_at` 的零值 `0001-01-01T00:00:00Z` 不要显示成一个 1 年的日期 —— 待决就显示待决。
4. 门禁：`cd console && npx tsc -b && npm run lint && npx vitest run && npm run build`，退出码分开记录。

## 边界

- **只改 console 侧**。不要改 `api/internal/approvals/`（那是审批服务本身，另有会话在动，而且改它要重新验安全属性）。
- 不要去点、不要去打任何审批接口，不要读 `PLATFORM_ADMIN_TOKEN` 或 `~/.config/bifrost/mcp-tokens.env`。只改解析代码和测试。
- 和 LANE-RP 无文件重叠（RP 碰的是 `console/src/api/releasePolicy.ts`、`ReleasePolicyBanner.tsx`、`useReleasePolicy.ts`）。碰到这三个就停下写报告。
- 不推 main、不发版。

## 验收（Claude Code 会照跑）

合并后 `git -C bifrost-platform grep -n "items" origin/main -- console/src/api/approvals.ts` 无命中；新测试在把响应字段换成 `items` 时会红。
