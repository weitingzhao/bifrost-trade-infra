# 第 4、5 阶段验收记录（Claude Code）

## 2026-10-08：LANE-D1、LANE-E1

| 道 | 结论 | 分支 · SHA | 重跑 | 状态 |
|---|---|---|---|---|
| D1 | PASS | infra `cursor/d1-infra` → **已合 main `b21f886`**（WORK.md W-1…W-30、`Work:` 尾注、`check_work_trailers.py`、渲染工作项分区、parity `shared-worktree-v4`）；platform `cursor/d1-platform` `a7b86813` | `lineage_test.sh` ok；`check_work_trailers.py --self-test` ok；`go test ./internal/progress/... ./internal/lineage/... ./internal/mcp/...` ok；`mcp/platform` 18 pass；共享检出 parity ok | platform 部分（`GET /api/v1/progress`、MCP `get_progress`）等 platform 发版顺序：P2 单独上 PROD → 第 3 阶段 → D1 / E1 |
| E1 | **返工（小）** | platform `cursor/e1-platform` `5c4040ee`；infra `cursor/e1-infra` `247af1be` | `go build/vet/test ./...` ok；`check-maintainers` ok 42 / no-alert 15；`reconcile.py --self-test` ok；kustomize ok | 三条存活告警名字匹配呼人路由（11→14，Sweep 的 absent 在镜像上线前就会呼）；workers `/metrics` 重复探插件；Secret 命令把令牌放进参数 → `LANE-E1R.md` |

## 2026-10-08：LANE-E1R

PASS。platform `cursor/e1-platform` `b291a09b`（`go build/vet/test ./...` ok；workers `/metrics` 不再探插件）；infra `cursor/e1-infra` `37c0e2d0` → **已合 main**（`check-maintainers` ok 42 / no-alert 15；`check_alert_routing.py` 呼人种类回到 11；存活告警改名 `BifrostMaintainer…`；Secret 命令改走 stdin）。

待办（要 Owner 批，等 E1 的 platform 镜像上线后再做，否则 absent() 先记一堆账）：`kubectl apply` PodMonitor、存活规则、`maintainer-reconcile` CronJob 与只读令牌 Secret；两台 mini 用干净 main 检出重部署 operator-plane（launchd 只读端点）。

## 2026-10-08：验收漏掉的 bug（B2）

PROD Console 的审批页显示「approvals: unexpected list shape」：`console/src/api/approvals.ts:87-92` 只认 `items` 键或裸数组，而 B1 的审批列表接口返回 `approvals` 键。B2 的测试用的是自编夹具，我验收时没拿真实接口形状去对。修法：接受 `approvals` 键，并加一条用真实接口形状的契约测试。TD-256 单独上 PROD 后由 Claude Code 在 platform main 修。
