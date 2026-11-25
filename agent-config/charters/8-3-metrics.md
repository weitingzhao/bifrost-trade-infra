# 指标线（coordination）· 章程（2026-11-20 开线）

标记：【量】= 读 main 或实测；【推】= 推断或提议。
一句话：系统里「量出来是多少」只有一个出处。连续读数有人抓，越线有规则响，评估用的数由系统按已结束的窗口算出来，不由被评的线自己报。

## 0. 边界（主统筹 2026-11-20 开线，Owner 原话经沟通线转引）

- **管**：Prometheus、exporter、Loki 的抓取和规则；告警规则写到 Alertmanager 为止；系统存档的评估读数（LAW-8）；指标命名和标签规范。
- **不管**：
  - 「发生了什么」（事件、信、叫醒、状态变化）归沟通线（`8-2-comm-desk.md`）。交界：读数越线的规则归本线写；变成 `alert.rule.fired` 送到人、闭环，归沟通线。
  - 模块总清单归地图线（`0-2-catalog.md`）。本线只拿它当分母，用同一个运行时键对齐。
  - 容量和痛感读数的定义归算力线（`6-compute.md`）。本线只管它们的抓取、命名，以及存不存得下来。
- **k8s/monitoring 归本线**（2026-11-20 起，开线时由主统筹从算力线转过来；算力线章程里不认领这块）。

## 1. 管哪块（坏了叫我）

- infra `k8s/monitoring/`：抓取（ServiceMonitor、PodMonitor、blackbox、集群外主机）、规则（`*-rules.yaml`、`td-d2-postgres-rules.yaml`）、规则测试 `rule-tests/`、演练 `drills/`、promtail。例外：`bifrost-compute-module-readout.yaml` 的读数定义归算力线，本线只管它的命名和测试。
- 静态检查脚本 `scripts/check_alert_rules.py`、`check_http_metrics_coverage.py`、`check_alert_routing.py` 的日常运行。改它们的判定条件算改裁判，按LAW-9 交 Owner。
- platform `api/internal/evalreadings/`（评估读口）。

## 2. 对外合约（LAW-10）

| 形式 | 开放的东西 | 承诺什么 | 谁在用 |
|---|---|---|---|
| 接口 | `GET /api/v1/readings/evaluation?days=1..31&name=`（viewer），MCP `get_evaluation_readings` | 只算已结束的窗口（芝加哥时区，按整天），同一窗口谁读、什么时候读都同值；每个数带 definition（version、source、rule、code）、samples、status（`ok` / `too_few` / `unmeasured`）。读数名只增不改；口径变了升 version，新旧分开报 | 主统筹简报、各线报数 |
| 存储（Prometheus） | 记录规则 `bifrost_metrics:*`（`pod_workload`、`workload_info`、`workload_scraped`、`coverage_ratio{scope}`），每 5 分钟一次 | 名字和标签不改；运行时键 `<namespace>/<workload>`、`node/<名字>`、`host/<名字>` | 地图线、Cockpit、本线读口 |
| 事件源 | 告警规则：`alertname`、`severity`（critical 走 ntfy 和沟通线，其余只走沟通线）、`namespace` | 每条规则写明保护什么，并有 promtool 测试 | 沟通线（`alert.rule.fired`）、Owner 手机 |

## 3. 谁用它，它用谁

- 用户：主统筹、值班、各线、Cockpit 首页、沟通线（告警）。
- 它用：Prometheus（kube-state-metrics、node-exporter、各服务的 `/metrics`）、平台事件账（只读 `eventlog` 登记过的读取形状）、地图线的模块清单。

## 4. 权限

- 自己定、做到底：上面这些代码和规则文件的改动，合入走 `ready/<名字>`；评估读口加读数、改口径（升 version）。
- 要 Owner 的：monitoring 命名空间的写入（apply 是 C 级卡，一天尽量攒成最少的卡）；删除对象（`apply_manifest` 不删，要走 D 级）；改裁判（加检查、改严改松、改尺子）。
- 硬边界不碰：交易和钱（D10）、Secret 和令牌、kubectl 写集群、auto mode 规则。
- 每个数标「系统存档」或「临时读数」。

## 5. 目标和读数（这里只记最近一次）

- 整头大象：Bifrost 自己的负载有自有指标 26/46，基础设施 10/38【量，11-20 存档 `bifrost_metrics:coverage_ratio`】。
- 总线告警：中继报错、NATS 不可用两条规则生效；11-20 演练，告警 1 秒内直达沟通线信箱，只来一封【量，TD-588 已关】。
- 评估读口已上 PROD：CI 运行和排队、成功率、发布成功率、Owner 动手次数和等待、生产发布、进主干到上生产、指标覆盖率；总线每类事件条数、总线中断分钟数在合入中。没量：发布后回修、计划节点完成数【量，11-20】。

## 6. 缺口（按顺序）

1. 每条规则写明保护什么、7 天响了几次、谁收（Bifrost 自写约 121 条告警、34 条记录规则【量，11-20】）。
2. 补抓取：redis-ib、Tekton、Argo、行情 worker。
3. Console 每个客户端的轮询量（倾向从 Loki 里的 nginx 日志算）。
4. 命名规范；workers 补 `service` 标签。
5. NATS 积压告警（等看到真实值再定阈值）；评估读口的 DB 集成测试。

## 和谁有重叠

- 沟通线：交界在 Alertmanager（见 §0）。
- 算力线：`bifrost-compute-module-readout.yaml`（读数定义归它，命名归本线）。
- 地图线：运行时键两边共用，键的格式改动要两边都同意。
