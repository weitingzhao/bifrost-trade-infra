# 领域 7 租户接入 · 章程（占位席位，2026-11-14；只读，没改任何东西）

基准：platform `origin/main`。【量】= 我读代码得到，带出处；【推】= 推断。路径都在 `bifrost-platform/api/internal/` 下。

## 1. 管哪块代码和哪些表
- 【量】`domains-review.md` 说的 0.36 万行没有点名包。我按「平台怎么接业务应用」找到五个包：`marketdata`（1179 行）、`flexquery`（707）、`research`（334）、`tradeagent`（137）、`ibgateway`（1680）。五个加起来 4037 行（不含测试），对不上 0.36 万，所以包的划分是【推】，要 biz-align 确认口径。
- 边缘四个包【推】：`satellite`（902，Mac 薄客户端总线）、`topology`（353）、`placement`（367，被 cluster、delivery 引用）、`probe/trade_routes.go`（Trade 网关路由表）。它们也带租户知识，但被运维、发布共用，不一定算本领域。
- 【量】这五个包里没有建表语句，也不 import store；只有 `server/server.go:37-60` 引入它们。表：无。
- 租户的"声明"不在代码里而在配置：`config/environments.yaml`（每个环境的 NodePort、库名、namespace、token 环境变量名）和 `config/topology.yaml`。

## 2. 对外露的口子
- 【量】只读状态：`GET /plugins/{ib-gateway,market-data,flex-query,research}/status`、`/research/status`、`/plugins/ib-gateway/self-heal`、`/watchlist/union`、`/trade-agent/{domains,catalog}`（`server.go:432-478, 563-564`）。
- 【量】代理：`/plugins/market-data/api/*`、`/plugins/flex-query/api/*`、`/plugins/research/api/*`、`/research/*`；写类 POST 在 `server.go:599-604`（IB 控制走 `guardIB`，market-data 删除走 `guard`）。
- 【量】MCP：`tradeagent.ServerName = "mcp-server-trade"`，目录里的工具都是只读 GET（`tradeagent/catalog.go:11,68`）。
- 租户要给平台什么【量】：一个健康地址（如 `/health`）、`environments.yaml` 里的环境条目、能被代理的 API。**没有统一的"租户注册"格式**：每个租户一个包、一套手写常量。

## 3. 谁用它，它用谁
- 用户【推】：Console（只读看板）、Agent 经 MCP 查 Trade 健康、发布流程读 placement 和 Trade 路由表做冒烟。
- 它用谁【量】：`cluster` 服务（集群读取）、`probe`、`audit`。不用 store，也不用别的领域，这点干净。
- **违反「平台不知道业务」的地方（根 CLAUDE.md §1）**【量】：
  - `probe/trade_routes.go:41-47` 写死 api-monitor/account/market/research 的进程名、端口 8765/8769/8772/8773。
  - `marketdata/config.go:10-11` 写死 `polygon-worker-stocks/options`、`plugin-market-data` namespace。
  - `ibgateway/operator_cmd.go:12-15` 写死 Redis 键 `ib:operator:cmd`、`ib:account:snapshot:v1`——这是 IB 协议和 Trade 的 daemon 命令流，平台不该认识。
  - `tradeagent` 整个包就是 Trade 专属；`placement/evaluate.go:55` 写死 `bifrost-stg`。
- 【推】换一个新应用接入，今天要新写一个包、改 `server.go` 接线、改 probe 常量。验证测试「clone 到别的集群、指向别的应用」过不了。

## 4. 现在的状态与缺口
- 【量】没人动：`tradeagent`、`satellite` 最后改动 10-04，`marketdata`、`flexquery`、`ibgateway` 10-07/08，`research` 10-29；近 90 天提交数 4–12 个，都是零散改动。`topology`、`placement` 11-13 才动过，只有 1 个提交。
- 【量】没有专属测试之外的防线；没有「租户声明」的校验，也没有对应的路由表或 MCP 工具清单自动生成。
- 缺口【推】：①缺一个通用租户声明（名字、健康地址、可代理前缀、可写动作）把上面常量搬进配置；②`ibgateway` 的 Redis 命令流知识应归 Trade 或插件，平台只保留 `reconnect_all`（根 CLAUDE.md §3 允许的唯一一条）——需 Owner/统筹确认，不是我能定的；③Finance 等新租户接入要走哪条路，没有文档。
- 没量到的：这五个包内部的调用关系、`satellite` 是否真属本领域、Console 页面具体读了哪些口子。

下一步：占位，没有活。有人要接新租户时，从缺口①开始。
