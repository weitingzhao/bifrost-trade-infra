# LANE-M — TD-85 的防线：数据库角色矩阵（infra、core）

先读 `cursor-tasks/README.md`（**特别是「第 2 轮」一节：一律只推分支**）。TD-85 的 Claim / Fix 见台账 `### TD-85`，
防线描述见 `RATCHETS.md` 里 TD-85 那一行（现在是 `no`）。报告写到 `cursor-tasks/reports/LANE-M.md`。
分支：`cursor/m-infra`（以及要动 core 时 `cursor/m-core`）。**本道不写任何数据库、不 apply 任何对象。**

TD-85 的验收已 PASS（2026-10-07，eaf68ac），只差这条防线。防线建好、Claude Code 验收后 TD-85 进「待你签收」。

## 要做的

1. **期望矩阵** `k8s/data/role-matrix/expected.yaml`（或同类位置，和检查脚本放一起）：对 `bifrost_dev`、`bifrost_stg`、`bifrost_prod`、
   `bifrost_golden_source` 四个库，逐个登录角色写：
   - 能 CONNECT 的库集合（显式授予或经 PUBLIC 都算 —— 检查要把 PUBLIC 展开算进去）；
   - 每个 schema 上的 CREATE，以及该 schema 下表的 INSERT / UPDATE / DELETE 集合（按 schema 汇总即可，不必逐表）。
   矩阵按 **D13 应该是什么** 写，不是抄现状。
2. **只读检查脚本**（Python 或 SQL + 小脚本均可）：连每个库，读 `pg_database.datacl`、`pg_namespace.nspacl`、
   `information_schema.role_table_grants`（或 `has_table_privilege` / `has_schema_privilege` / `has_database_privilege`），
   和矩阵逐格比对，打印差异，差异非空退出码 1。用 `PGOPTIONS=-cdefault_transaction_read_only=on`。
3. **每日 CronJob**（`data` namespace，清单放 `k8s/data/role-matrix/`，**只推分支**）：跑脚本，结果作为指标上报
   （例如 Pushgateway 或文本文件 + 现有 exporter 均可，选现有监控栈里最省事的那条路），再加告警
   `BifrostDbPrivilegeDrift`（`k8s/monitoring/` 里现有规则文件的写法）。Job 要抄现有一次性 Job 的 `wait-pg` initContainer
   （NetworkPolicy 竞态，见 `k8s/data/logical-backup`）。只读凭据用现有只读角色；没有合适的就在报告里写「要 Owner 批：建只读角色」。
4. **release-check 接入**：`scripts/release/release-check.sh` 的 before 阶段能本地跑同一个脚本（读 kubeconfig，exec 进 CNPG 只读查询）。

## 已实测的事实（另一个 Claude 会话 10-07 16:4x UTC，只读）—— 写矩阵时照用

- **analytics_writer 仍有 schema CREATE**：`raw_market` `analytics_writer=UC/data_writer`、`raw_broker` `analytics_writer=UC/bifrost`、
  `ops_jobs` `analytics_writer=UC/postgres`（ops_jobs 可能是 Research 跑 `ensure_month_partitions` 需要 —— 读 research 代码确认）。
  `raw_market` / `raw_broker` 上的 CREATE 与 D13 冲突：**矩阵照 D13 写成「无」**，所以矩阵一上线这两格会红。
  另写 db-step（`scripts/release/db-steps.d/` 的格式，含 rollback SQL 与 verify SQL）撤这两处 CREATE，**不执行**，列进「要 Owner 批」。
  `ops_jobs` 的 CREATE 若确为 Research 所需，矩阵里写「有」并注明原因。
- **GS 的 CONNECT 列**：只靠 PUBLIC 才能连 GS 的登录角色只有 `market_reader`（无任何 Secret / ConfigMap / workload / .env 使用）和
  `streaming_replica`（复制不查库级 CONNECT）；其余 11 个都有显式 CONNECT。PUBLIC 的 CONNECT 已于 10-06 收回（eaf68ac），
  所以 `market_reader` 现在连不上 GS —— 矩阵写「无」，报告里说明。
- **已有的局部防线**：core `tests/test_brokerage_view_grants_db.py::test_data_writer_gets_nothing_in_raw_broker`（756bdb5，负对照）
  守住「db-init 不授 data_writer raw_broker」。报告里写进 TD-85 防线的「靠什么」一栏，和新检查并列。

## 门禁与验收

- 脚本的单元测试：用编造的 acl 字符串测解析与比对（PUBLIC 展开、`=T` 只有 TEMP 不算 CONNECT、继承角色）。
- 报告里给一条验收命令：本地对 PROD 集群只读跑一次检查，预期**只**报上面两处 analytics_writer CREATE（以及你核实后新发现的差异，逐条列出）。
- 要 Owner 批：apply CronJob 与告警（Argo 路径）、撤 analytics_writer CREATE 的 db-step、如需新建只读角色。
