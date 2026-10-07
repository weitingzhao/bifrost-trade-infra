# LANE-T2 — Trade Ops 读不到 IB Gateway 状态（TD-104 后续）+ 报价镜像单独开关（TD-240 方案 A）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支 `cursor/t2-<简称>`，不发版、不写库、不 apply）。报告写到 `cursor-tasks/reports/LANE-T2.md`。

## TD-104 后续（线上实测 2026-10-07 17:20 UTC，ib-gateway 0.4.0 + trade-api d7cdc3f 已上 PROD）

ib-gateway 三个健康 hash 已经带 `updated_at`（实测 6.5 秒前）与 `git_sha`，但 PROD trade-api
`GET /api/monitor/ops/market-ingest/services` 的三行 IB 仍是：
`process_active=inactive`、`redis_control_updated_at=null`、`k8s_replicas=0`、`k8s_ready=0`（`runtime_status=active`）。

已确认的一个原因：`kubectl auth can-i get deployments/ib-gateway -n data --as=system:serviceaccount:bifrost-prod:api-ops` → **no**。
要做：
1. 找到 api-ops（以及 STG/DEV 对应 SA）的 RBAC 清单（bifrost-trade-infra），加一个 `data` 命名空间里只读 `deployments` 且 `resourceNames: [ib-gateway]` 的 Role + RoleBinding（get 足够就只给 get）。只推 infra 分支。
2. 查清 `process_active` / `redis_control_updated_at` 为什么读不到：trade-api 读健康 hash 用的是哪个 Redis（Trade 的 redis-live 还是 redis-ib）、哪个账号；redis-ib 的 ACL 是否允许它读 `bifrost:health:ws_ib_*`。只读排查（`kubectl auth can-i`、读代码、只读 redis 命令用 trade-api 自己的连接方式），不改 ACL；需要改 ACL 的写成「要 Owner 批」。
3. 防线：一条测试或检查，保证 IB 三行在「hash 新鲜 + Deployment ready」时判为 active，并且 RBAC 清单里有这条只读权限（可扩展 infra 已有的 check 脚本）。

## TD-240 方案 A（Owner 10-07 选定）

`contract_quote_live` 仍有读取方（见 `cursor-tasks/reports/LANE-T.md` 的 TD-240 节），不能删。改为：给只做观测的 STK 报价镜像单独一个开关 `daemon.quote_mirror`，**不再挂在 `mock_hedging` 下**。
- 只读/观测路径：镜像只写 `contract_quote_live`，**不得**新增或触碰任何下单、改单、对冲、`ib:operator:cmd`、`POST /control/*` 路径（D10）。
- 默认值保持当前线上行为（PROD 现在不写这张表），即默认关；打开它是 Owner 的一次配置动作，写进报告。
- 仓库：bifrost-trade-worker（daemon）为主，必要时 core。改公开接口照常 bump 并列下游。
- 防线：测试断言 `mock_hedging=false` 且 `quote_mirror=true` 时镜像写表、且不调用任何下单/对冲函数；`quote_mirror=false` 时不写。

## 顺带（TD-207 后续，10-07 部署 .50 时发现）

`bifrost-platform/scripts/agent/deploy_mac_mini.sh` 的「Post-deploy tool smoke」用匿名 `curl` 调 runner 的 `GET /smoke`，
TD-207 之后 `/smoke` 要令牌，所以部署输出「could not parse smoke results」。改为从 `${PLATFORM_LOCAL}/.env` 取
`REMEDIATION_RUNNER_TOKEN` 作为 bearer（不打印值），401 时明确报「token rejected」而不是 parse 失败。platform 分支 `cursor/t2-platform`。

**注意（10-07 追加）**：`deploy_mac_mini.sh` 里 `ALERT_RELAY` / `PEER_RELAY_URL` 的处理已由另一个会话改好（4646441：保留主机现值、--disable-alert-relay 才关）。本道只改 tool smoke 那几行，**不要碰** relay 相关的环境变量逻辑；若冲突，停下写进报告。

**注意（10-07 再追加）**：platform main 已由另一个会话快进到 4646441（含 894a88f 的 A5 与 A8 的 relay 保留逻辑）（LANE-A5：从 agent/deploy 与 deploy_mac_mini.sh 删掉 03:00 nightly 段）。platform 分支起点用最新 origin/main，在它之上改 deploy_mac_mini.sh 的 tool smoke。
