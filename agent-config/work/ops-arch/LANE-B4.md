# LANE-B4 — PROD 权限补齐、STG 关掉残留维护、UniFi 凭证进 PROD、告警 webhook 改用 reporter

ADR §4、§7、§10。仓库：bifrost-trade-infra `cursor/b4-infra`；bifrost-platform `cursor/b4-platform`。

## 事实

- PROD platform 用 ServiceAccount + `k8s/platform-rbac/`（`scripts/gen_platform_rbac.py` 生成，`make check-platform-rbac` 逐条问 apiserver）。MCP 切到 PROD 之后，Claude 日常的写操作（起流水线、Argo sync、rollout、cordon 等）都会由 PROD 的身份执行。
- 第 1 阶段 A3 发现：STG platform-workers 里数据克隆调度器在跑（默认源 `bifrost_prod`，调度 ConfigMap 不存在所以今天不复制），STG 的 patrol 在跑且 `PATROL_MODE` 不是 report（STG 没有技能目录）。ADR：STG 只观测。
- UniFi：平台连 UniFi 的凭证（`UNIFI_HOST`、`UNIFI_USER`、`UNIFI_PASS`）只在 Owner 笔记本 `bifrost-platform/.env`；PROD 读 `network/*` 报「UNIFI_USER and UNIFI_PASS required」。Owner 决定：平台保留可写权限，任何改动走审批（UniFi apply 在 B1 里是 D 级）。仓库里还有 `mcp/unifi`。
- 告警 webhook（`/api/v1/ops-agent/alertmanager`）现在要求 operator，Alertmanager 拿着 PROD operator 令牌（A1）。它只写诊断与审计。
- `k8s/monitoring/bifrost-alerting-rules.yaml:486` 的注解还写着去 STG platform-api 查。

## 要做

1. **RBAC**：按 B1 的动作目录核对 PROD ServiceAccount 能执行每一个 C / D / B 级动作（缺的补进 `gen_platform_rbac.py` 生成的规则），STG 一个都不能执行；`check_platform_rbac.py` 增加对应断言。
2. **STG 关维护**：platform 加环境开关（默认开、STG overlay 关）：数据克隆调度器、patrol 后台循环；`check_platform_maintenance.py` 增加断言「STG 两者都关」。
3. **UniFi 凭证进 PROD**：PROD platform-api / workers overlay 从 Secret `bifrost-platform-unifi`（`optional: true`）读三个变量；报告写出 Owner 建 Secret 的命令（值从本机 `.env` 读，不打印、不进仓库）。
4. **告警 webhook 改用 reporter**：路由改为 reporter 及以上即可；`apply-platform-role-tokens.sh WEBHOOK_ONLY=1` 改写 PROD reporter 令牌；`check_alert_routing.py` 的令牌来源断言同步；不改路由与呼人规则。
5. 修 `bifrost-alerting-rules.yaml:486` 的注解（指向 PROD）。

## 防线

`make check-platform-rbac`（PROD 能、STG 不能，逐动作）；`check_platform_maintenance.py`（STG 维护全关）；`make check-alert-routing`（reporter 令牌来源）；platform 开关的 Go 测试。

## 门禁与验收

Go 全量 + infra 三个 check。验收命令写进报告。

## 要 Owner 批

建 UniFi Secret；合并 `cursor/b4-infra`（Argo 会改 STG / PROD 的 Deployment）；RBAC 手工 apply；webhook 令牌更新。
