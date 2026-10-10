# 第 9 步：Console 被删 UI 清单（STG 过目用）

Owner 在 STG 上按本页过一遍，就是 ADR §6 的「删除前过目」。过目通过后集成分支 `w31/console-int` 才快进进 platform main、再发 PROD（步骤见 `STEP0-PLAN-2026-10-08.md` 0.7 节）。

- 只列**屏幕上看得到**的删除与搬家；纯重排（W-45）和零引用死代码（W-43a）各占一行说明。
- 每项写「在哪看」：STG Console 上的位置。要留的项直接回「留 W-xx 第 n 项」，在集成分支补回后重发 STG。
- W-31 线程 2026-10-10 按各道提交说明和 diff 整理（W-46 `26caf11` `fae4dc4`，W-44 `86b709f`，W-45 `611cc3e`，W-43a `7fef876`）；W-43b 交回时把它的清单补进第 5 节。

## 1. W-46（S0-19 清理 B）

| # | 删掉的东西 | 原来在哪看 | 理由 |
|---|---|---|---|
| 1 | 「Copy for Agent」/「Diagnose with Agent」按钮 | Status 的 observability、IB、Research Engine、IB Flex、Massive overview 与 coverage matrix | ADR §6 退役 Console 派 Agent；6 个 `*AgentPack` 生成器一起删（Research 的 findings 分析保留） |
| 2 | 「Generate Agent Pack」（页头、维度标签、domain / metric 按钮、行操作）和 Lower baseline 里的「Copy for Agent」 | Code Health | 同上；维度标签保留为普通标签 |
| 3 | Agent Protocol 按钮与链接 | Network、Status 健康区 | 同上 |
| 4 | 「Agent Fix」/「Fix」行操作，以及让人去按 Agent Fix 的提示语 | Infrastructure 的 triage 表 | 同上 |
| 5 | 已关闭的网络升级记录（目录标签和流表） | Status 健康区（Infrastructure 里保留） | 已关闭的事项不放 Status |
| 6 | Backup 面板的 escape-hatch 演练那一半 | Backup | 后端端点已删（404） |
| 7 | Mission 的 Agent 信号、Engineer 舰队格不再给 git-bridge 打分 | ① Mission | git-bridge 是笔记本工具（ADR §4），PROD 上一直判 unavailable、把 Agent 涂红 |
| 8 | Daily Ops 检查清单删去 runners-ha、git-bridge、mac-probe-bridge 三项（含残留的 hermes-tooling） | Status 检查清单；Autopilot 少了 git-bridge、runners-ha 两条修复路线 | runner 舰队与笔记本工位已退役；状态文件只留目录里还有的项 |

## 2. W-43a（S0-16a 只删零引用的死代码）

没有可见变化：删的 17 个文件在 Console 里没有任何引用（W-43a `7fef876`）。不用过目，列在这里只为完整。

## 3. W-44（S0-17 外壳与「需要你」）

| # | 删掉或搬走的东西 | 原来在哪看 | 现在在哪 |
|---|---|---|---|
| 1 | Maintenance 页 | `#maintenance` | 首页改为 `#needs-you`；`#maintenance`、`#maintenance?id=` 保留为别名，跳到新页 |
| 2 | 侧栏「Ask for Agent」入口（`NavAgentAskSlot`） | 侧栏底部 | 删除（ADR §6） |
| 3 | `#agent-protocol` 跳转 | 地址栏 | 删除 |
| 4 | 行内审批对话框（`RequestActionButton` 里直接批准） | 各页的请求按钮 | 改成「Open request」链接，批准 / 驳回只在 `#approvals?id=` 详情页（卡 A） |
| 5 | Autopilot 页签 | Maintenance 页内 | 原样搬进 `#records` 的 Patrol 标签（卡 C） |

## 4. W-45（S0-18 ⑤ Releases 三段式）

没有删除功能，只重排：原来的「In-flight and failed runs」和「Recent releases」两张表拆成 Needs you / In progress / History 三段，History 默认收起，「Built from」等列都在。被后来成功覆盖的失败 run 从 In progress 移到 History。过目时确认 History 展开后信息齐全即可。

## 5. W-43b（S0-16b 删孤儿）

W-43b 交回时由 W-31 线程按它的提交说明补齐。动手前已定的范围（STEP0-PLAN 0.4 节「16b 清单补充」、卡 10 = A）：

- 「Agent Fix」字样残留（15 个文件，含 Mission 板、反馈、检查清单目录、舰队格、注意力批量与修复目录）；
- `cicdBootstrapCatalog.ts` 里 escape hatch 的「Implemented」改成实际状态；
- 后端网页 SSH 终端 `api/internal/console`（`POST /console/ws-ticket`、`GET /console/hosts`、`GET /console/ws`）和 xterm 依赖；
- `.console-operator-dock__*` 样式、`verify-operate-queue-wave3b.mjs`。

## 6. 过目结果

| 日期 | 结果 | 要留的项 |
|---|---|---|
| | | |
