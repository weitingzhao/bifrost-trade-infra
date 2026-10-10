# 规则放宽提议：观测类清单变更随策略自动执行

- **状态**：草案，等 Owner 定。放宽规则要 Owner 签名（ADR §5、§12.4）；在签之前现行规则不变。
- **日期与起草**：2026-10-10，Claude（W-31 决策线程）。Owner 当天说「规则放宽也起草」。

## 要解决的问题

现在 `apply_manifest` 的级别只看命名空间。给监控加一条告警规则和改一个 Deployment 都是 C 级，都要 Owner 点批准。告警规则这类变更可回滚、不碰业务、不碰权限，不在 Owner 的三件事（定目标、定规则、不可逆的事）里。

## 提议的规则

一次 `apply_manifest` 同时满足下面全部条件时，按 B 级直接执行，不等 Owner：

1. **对象种类**全部在这张清单里：`PrometheusRule`、`ServiceMonitor`、`PodMonitor`、`ScrapeConfig`，以及带 `grafana_dashboard` 标签的 `ConfigMap`。
2. **命名空间**全部是 `monitoring`。
3. **只新建或更新**，plan 里没有删除；对象不超过 20 个。
4. **不改变谁会被叫醒**：plan 里新增或改动的告警规则没有 `severity: critical`。critical 会推到 Owner 手机，仍是 C 级。
5. **提交在 main 上**，该提交的 CI 通过（告警规则测试 `make check-alert-rules` 在 CI 里）。
6. **策略有效**：这一条作为发版策略里的一个条件（`apply_observability`），和策略一起签名、一起 90 天到期；过期或冻结时回到 C 级。

判断只用 plan 的结构化结果（对象种类、命名空间、动作、规则里的 severity 字段），不做文本匹配。任何一项读不出来、认不得，就按 C 级处理。这一点是 R01（DDL 分类器按文本猜）的教训。

## 明确不在范围内

- Alertmanager 的路由和接收人；
- Deployment、StatefulSet、Job、CronJob；
- RBAC、NetworkPolicy、Secret、CRD；
- Tekton 的 Task 和 Pipeline（发布链）；
- `monitoring` 以外的任何命名空间；
- 任何删除；
- 全部 D 级动作。

按这条规则，W-38 的告警规则本身是 critical，仍要 Owner 批；W-42 的 RBAC 和 Tekton Task 也仍要批。它放掉的是今后的 warning 级规则、抓取配置和看板。

## 执行之后

- 每次自动执行都进「记录」，带 plan 编号和提交号；
- 执行失败推送给 Owner；成功不推送；
- 回滚：对上一个提交重新 plan 和 apply，同样自动。

## 证据

- 最近两天 `apply_manifest` 的 4 张 C 级单（都是 market-data 的 Deployment），Owner 分别在 17 秒、14 秒、31 秒内批准，另一张因 run 重名失败。批准没有带来改动或驳回。
- 这一类（观测对象）目前还没有一张单走过审批，W-38 是第一张。所以这条提议的依据是变更的性质，不是历史数据。

## 选项

| 选项 | 内容 | 代价 |
|---|---|---|
| **A（建议）** | 上面的规则 | 一条写错的 warning 规则会自动上线；靠 CI 里的规则测试和回滚兜底 |
| B | A，再加「在 `cicd` 里新建 ConfigMap（不覆盖已有的）」 | `cicd` 里有发布链的配置，新建的 ConfigMap 可能被流水线读到 |
| C | 不放宽 | Owner 继续逐张点 |

## 实现（Owner 选 A 或 B 之后才派）

- platform：`classifyApply` 读 plan 摘要里的对象种类、动作和 severity；策略引擎加 `apply_observability` 条件；测试覆盖每一条排除项和「读不出来按 C 级」。
- infra：策略模板加这一条件；`docs/RELEASE.md` 说明。
- 独立复核：交 Codex 审分类逻辑，和 W-55 同样的做法。
