# 第 2 阶段验收（Claude Code，2026-10-07）

| 道 | 结论 | 分支 · SHA | 重跑 | 要处理的 |
|---|---|---|---|---|
| B1 | **返工** | platform `cursor/b1-platform` `d61fc70d` | `go test ./internal/actions/... ./internal/approvals/...` ok | ① `actions_wire.go:46` `HasExecuted` 让一次批准变成同参数永久直调放行（护栏漏洞）；② Research 单环境即生产，`bifrost-deliver-research` 按名字规则被定成 B；③ 三个暂定 IB 级别；④ 删失败备份、装监控组件、改 kubeconfig、改克隆计划、插件 DELETE 还在豁免清单 → `LANE-B1R.md` |
| B2 | PASS | platform `cursor/b2-platform` `ccdf2005`；infra `cursor/b2-infra` `b7d29bc8` | Approvals 页面 3 测试 ok；`alertrelay`、`approvalnotify` ok | 接线一行进 B1R |
| B3 | **返工** | platform `cursor/b3-platform` `40187953`；infra `cursor/b3-infra` `f89e1bc0` | （设计复核） | ① 以 `MCP_WRITES=off` 合并会让所有线程的写工具中断，改为 B1R 上线后以 `on` 合并；② 令牌要在进程环境——改为 600 的令牌文件兜底；③ 聊天批准的 admin 令牌本机可读：Owner 选方案 B 接受风险，加 preflight 拦截 → `LANE-B3R.md` |
| B4 | PASS | infra `cursor/b4-infra` `38e752e3`；platform `cursor/b4-platform` `388d4311` | 4 个 Go 测试 ok；`check_platform_maintenance` ok；`check_alert_routing` ok；`check_platform_rbac` 5/138 不一致（全是 PROD drain，apply 前预期） | 无 |

## 上线顺序（每步要 Owner 批）

1. B1R 验收 → platform main → STG → PROD。
2. 合 `cursor/b2-infra`、`cursor/b4-infra`（两边都改 PROD overlay，键不重叠）→ Argo。
3. 建 Secret `bifrost-platform-approval-notify`、`bifrost-platform-unifi`；`kubectl apply -k k8s/platform-rbac`；`WEBHOOK_ONLY=1` 换成 reporter 令牌；.50 用新 `deploy_mac_mini.sh` 重部署 operator-plane（加 notify 入口）。
4. B3R 验收 → 合 infra main；Owner 建 `~/.config/bifrost/mcp-tokens.env`（600）并应用 `permissions.ask`；实测聊天里批准是否弹窗。

## 台账待登记（Claude Code）

`TestWriteRoutesAreCataloguedOrExempt`（新写端点必须进目录或豁免清单）、`check_mcp_cutover.py`、preflight 审批拦截 → `RATCHETS.md`。

## 返工验收（2026-10-07）

| 道 | 结论 | 分支 · SHA | 重跑 |
|---|---|---|---|
| B1R | API / Console **PASS**；MCP 侧要再修 | platform `cursor/phase2-platform` `816a8039` | `go build/vet/test ./...` 全过；漏洞修复：`executorContextKey` 未导出，直调 C/D 一律 403；`ProdPipeline` = deliver-prod / deliver-platform-prod / deliver-research（另核：build-research-dagster、build-research-pine、build-market-data、build-flex-query、build-ib-gateway 都只到 kaniko，B 级正确）；Approvals 页面 3 测试、`mcp/platform` 14 测试 ok |
| B3R | **PASS**（依赖 B1R2 修 Cursor 模板） | infra `cursor/b3-infra` `27ecfaed` | preflight 85/85（含审批绕过拦截与放行）；`check_mcp_cutover.py` ok；`--cursor` 对 platform 模板 fail（MCP_WRITES=off，B1R2 修） |

MCP 侧问题：没设 `MCP_WRITES` 时默认不发写（共享检出一更新就会断所有线程的写工具）；级别在 MCP 里抄了一份且与 API 不一致；4 个动作没映射 → `LANE-B1R2.md`。

## B1R2 验收（2026-10-07）

PASS。platform `cursor/phase2-platform` `e6b825b9`（在 `816a8039` 之后，基于 main `4646441`）：`mcp/platform` tsc + 18 测试 ok；`api` `go test ./...` ok（含 `config/actions-catalog.json` 与目录一致的测试）；`check_mcp_cutover.py --cursor`（取自 `cursor/b3-infra`）ok；`writeGate.ts`：没设 `MCP_WRITES` → `legacy`（原路由直调），`on` → 审批感知，其余 → 不写。七个写工具不在目录（ensure_bifrost_namespaces、operate queue 三个、report_checklist_signals、run_release_gate、sign_tier_b），`on` 时明确拒绝——前两类第 3 阶段处理，后两个第 3 阶段退场。

**第 2 阶段可以上线**：步骤见上文「上线顺序」。
