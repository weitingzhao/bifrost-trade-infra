# LANE-B1 — 动作目录 + 申请单 / 审批 API

ADR §5。仓库：bifrost-platform，分支 `cursor/b1-platform`（从最新 origin/main 开）。接口照 README「接口约定」实现。

## 事实

- 角色：`api/internal/actuation/auth.go`：viewer < reporter < operator < admin。Owner 持 admin；Agent 拿 viewer / operator。
- 写操作现在是一批分散的端点（MCP 的写工具对应它们）：起流水线、删流水线运行、Argo sync / rollback、rollout restart、scale、delete pod、cordon / uncordon / drain / 关机 / 唤醒 / 加入节点、触发 CNPG 备份、`repair_cnpg_wal_store`、数据克隆、market-data heal、IB 重连 / 模式切换、UniFi 防火墙 apply、stack add-on 安装 / 升级。
- 平台状态用 `api/internal/statefile`（PROD 落 ConfigMap `platform-state-<key>`，TD-196）；审计用 `actuation.AuditLog`。
- D10：daemon 扩容已由 TD-222 的闸门拒绝；不要削弱它。

## 要做

1. `api/internal/actions`：动作目录（id、级别、说明、参数校验、执行函数），覆盖上面所有写端点。级别按 ADR §5，按参数定级的规则：
   - 发流水线：`*-prod` 管线 C，其余 B；Argo：PROD 应用 C，其余 B；rollout restart：`data`、`bifrost-prod`、`bifrost-platform-prod` 命名空间 C，其余 B；
   - scale：C（daemon 扩容仍是 X）；cordon / uncordon C；drain、关机、加入节点、`repair_cnpg_wal_store`、UniFi apply、add-on 安装 / 升级：D；
   - delete pod、删流水线运行、唤醒节点、market-data heal、IB 重连：B；触发备份、数据克隆：C。
   写不清楚的写进报告，由 Claude Code 定。
2. `api/internal/approvals`：申请单存储（statefile key `approvals`，未结全留、已结留最近 500 条）、创建 / 列表 / 详情 / 批准 / 拒绝、24 小时过期、`params_hash`（规范化 JSON 的 sha256）。批准时由平台按**存下来的参数**调用动作的执行函数，结果写回申请单。
3. 把 C / D 级的原有直调端点改为「没有已执行的对应申请就 403」——直调路径从此只有 B 级还能直接走；C / D 只能通过批准执行。不要删端点，MCP 现在还在用（B3 会改调用方式）。
4. `GET /api/v1/actions` 列出目录。
5. 审计：创建、批准（含 channel）、拒绝、过期、执行结果各一条，`requester` 取 `X-Bifrost-Session`。

## 防线

测试至少覆盖：C / D 直调 403；批准要求 admin（operator 被拒）；批准后执行的是存下来的参数（创建后篡改无效）；一次批准只执行一次；过期不能批；X 级创建即 403；目录覆盖所有写路由（遍历路由表，写方法的路由必须在目录里或在明确的豁免清单里——这条是以后新写端点不漏登记的防线）。

## 门禁与验收

`cd api && go build ./... && go vet ./... && go test ./...`（退出码分开看）。报告给出：目录的完整列表（id → 级别），以及验收命令 `go test ./internal/actions/... ./internal/approvals/...`。

## 不做

不发版、不改 MCP、不改 Console（B2 / B3 做）。
