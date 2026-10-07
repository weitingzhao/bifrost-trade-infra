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
