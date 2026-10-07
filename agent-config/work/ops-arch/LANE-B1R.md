# LANE-B1R — platform 集成分支：B1 修复 + B2 接线 + B3 / B4 的 platform 部分

仓库：bifrost-platform，新分支 `cursor/phase2-platform`，从最新 origin/main 开，依次合入 `cursor/b1-platform`、`cursor/b2-platform`、`cursor/b3-platform`、`cursor/b4-platform`（rebase 或 cherry-pick，解决冲突），再做下面的修改。目标：**一条分支、一次全量门禁、一次发版**。

## 为什么（Claude Code 验收，2026-10-07，见 VERIFY-phase2.md）

## 要做

1. **护栏漏洞（必须）**：`api/internal/server/actions_wire.go:46` 用 `HasExecuted(action, hash)` 放行直调——一项 C / D 动作只要被批准执行过一次，之后相同参数的直调就永久放行。改为：**C / D 级的直调端点一律 403**；批准后的执行走内部路径（执行函数直接调用 handler，带一个只有审批执行器能设置的内部上下文标记，HTTP 请求无法伪造）。删掉 `HasExecuted` 的放行用途。测试：同一参数批准执行一次后，再直调仍是 403；内部执行路径不受影响。
2. **流水线定级**：「会改动生产工作负载」的流水线都是 C，不只是名字以 `-prod` 结尾的。Research 只有一个环境（就是生产），所以 `bifrost-deliver-research` 是 C；逐个核对 `cicd` 里的 Pipeline（只读 `kubectl -n cicd get pipelines`，看它们最后是否 rollout / gitops-sync 生产命名空间），把结论写成 `ProdPipeline` 的显式清单 + 测试；只构建镜像、不部署的是 B。
3. **三个暂定级别**：`ib_self_heal` → **B**（PROD 的 IB 自动修复循环本来就在自动做这件事）；`ib_mode`、`ib_maintenance` → **C**。去掉 `Provisional`。
4. **从豁免清单移进目录**：`POST /cluster/postgres/backups/sweep-failed` → C；`POST /cluster/addons/metrics-server/ensure`、`…/kube-prometheus-stack/ensure` → D；`POST /cluster/sync-kubeconfig`、`POST /cluster/kubeconfig-secret/ensure` → D；`PUT /cluster/data-clone/schedule` → C；`DELETE /plugins/market-data/api/*` → C。其余豁免项不动（发布门、vision、build-phase、migrate-streams 的 gate / signoff 等第 3 阶段退场）。
5. **B2 接线**：在 `POST /api/v1/approvals` 的处理函数里，申请单落库、写 201 之前调用 `approvalnotify.NotifyCreated`（代码见 LANE-B2 报告「B1 接线」一节）。测试：创建申请会调用 notify；notify 失败不影响 201。
6. **MCP 令牌来源**（B3 跟进）：`mcp/platform` 的令牌在进程环境没有时，从 `~/.config/bifrost/mcp-tokens.env`（只认权限 600 的文件）读 `PLATFORM_VIEWER_TOKEN` / `PLATFORM_OPERATOR_TOKEN` / `PLATFORM_ADMIN_TOKEN`；钉角色的规则（TD-225）不变——每个 server 只读它被钉的那一个键。日志与错误里不打印令牌。测试覆盖：环境优先、文件兜底、文件权限不是 600 时拒绝读取。
7. **B3 报告的后续**：`api/internal/mcp/catalog_test.go` 的 `stdioMirroredTools` 与 TS 侧的实际工具对齐（`dev-sessions` 三个工具只在 `bifrost-local`；四个 `request_*` / `wait_for_request` 在全量 server）。
8. **目录计数**：报告给出 `GET /api/v1/actions` 的完整列表与计数（B1 报告写 24 条，Cursor 汇总写 35 条，以实际为准）。

## 门禁与验收

`api`：`go build ./... && go vet ./... && go test ./...`；`console`：`npx tsc -b && npm run lint && npx vitest run && npm run build`；`mcp/platform`：`npx tsc -b && npm test`。退出码分开看。报告给出验收命令（至少：`go test ./internal/actions/... ./internal/approvals/... ./internal/server/...`、Approvals 页面测试、`mcp/platform` 的 `npm test`）。

## 不做

不推 main、不发版。分支 `cursor/b1-platform` 等保持原样（作为历史）。
