# LANE-A2 — LANE-A 的契约测试会空过：给 json tag 数加下界（TD-261 收尾，platform console）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不 apply、不改 `TECH_DEBT.md` / `RATCHETS.md`）。报告写到 `cursor-tasks/reports/LANE-A2.md`。
分支：**`cursor/a-platform`（已存在，LANE-A 的那条）**。在它上面**追加提交**，不要新建分支、不要 rebase、不要 force-push、不要合 main。

起点：`cursor/a-platform` 的当前 tip `3bd067f234003a267f24950f71e83ea80bc20133`。

## 背景

LANE-A 做对了一件关键的事：`console/src/api/__tests__/approvals.test.ts` 在**运行时读** `api/internal/approvals/types.go` 与 `handler.go`，解析 `Approval` 的 json tag 逐个比对夹具，并断言 handler 发 `approvals` 而非 `items`。这条防线是真的。

但它有一处会**空过**：

```ts
function approvalJsonTagsFromGo(source: string): string[] {
  const block = source.match(/type Approval struct \{([^}]+)\}/s)?.[1] ?? ''
  …
}
```

正则匹配不到时 `block` 是 `''`，`tags` 是空数组，`for (const tag of …)` 循环体一次都不执行，**测试照样绿**。
触发条件不罕见：结构体改名、换行重排、字段里出现嵌套大括号（`[^}]+` 遇到第一个 `}` 就停）。
也就是说：这条防线正是为了「测试陪着错误形状一起绿」而建的，而它自己有同一个毛病。

## 要做

1. 给 tag 数加**下界**：解析出的 tag 少于一个合理数量就直接失败，并在失败信息里说清是「Go 结构体没解析出来」而不是「夹具少字段」。
   下界取多少由你定（现在 `Approval` 的 json 字段大约十几个），**但不要写成等于当前数量** —— 那会让每次给 Go 加字段都要改测试。`> 8` 这类保守下界就够。
2. **补一条反例测试**：喂一段**找不到 `Approval` 结构体**的假 Go 源码给 `approvalJsonTagsFromGo`（或它的可测包装），断言这种情况**会红**。
   这条是本道真正的交付物 —— 证明空过的路被堵上了。为此可能需要把那个函数从测试文件里导出成一个小模块，可以改。
3. 顺手核一件事（查到就修，查不到就在报告里写「不成立」）：`[^}]+` 这种正则在字段里有嵌套大括号（比如 `map[string]any` 后面跟结构体标签里的 `{`）时会截断。看一下当前 `Approval` 有没有这种字段；有的话换一个不靠「第一个右大括号」的解析方式。

## 门禁

`cd console && npx tsc -b && npm run lint && npx vitest run && npm run build`，退出码分开记录。
LANE-A 那轮是 809 passed，本道之后应该多出反例那一条。

## 边界

- **只推 `cursor/a-platform`，不合 main。** platform main 必须停在 **a7ecb08**，直到 platform PROD 审批单发出。
- 只改 `console/`。不要碰 `api/internal/approvals/`（那是审批服务本身）。
- 不要碰 `console/src/api/releasePolicy.ts`、`ReleasePolicyBanner.tsx`、`useReleasePolicy.ts`（LANE-RP 的文件）。
- 不要去点或打任何审批接口，不要读 `PLATFORM_ADMIN_TOKEN` 或 `~/.config/bifrost/mcp-tokens.env`。

## 验收（Claude Code 会照跑）

把 `types.go` 里的 `type Approval struct {` 临时改个名，`npx vitest run` 必须**红**；改回来必须绿。
