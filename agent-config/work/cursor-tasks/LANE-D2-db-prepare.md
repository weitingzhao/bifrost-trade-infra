# LANE-D2 — 数据库与 PROD 运维：只准备、不执行（infra、core、research、market-data、flex）

先读 `cursor-tasks/README.md`（**特别是「第 2 轮」一节：一律只推分支**）。每项的 Claim / Evidence / Fix / Ratchet 见台账 `### TD-n`。报告写到 `cursor-tasks/reports/LANE-D2.md`。**本道不写任何数据库、不 apply 任何对象**：只写 SQL / 清单 / 脚本 / 只读统计，推到分支 `cursor/d2-<简称>`。每项在报告里给出「Owner 执行步骤」（命令、预期输出、回滚）。

| 项 | 要准备的 |
|---|---|
| **TD-134** | CNPG 参数：checkpoint_timeout 15min、max_wal_size 4GB、wal_compression lz4（只需 reload）。改 Cluster 清单（分支），写出 apply 后核对 `SHOW` 的命令和一周 WAL 量的观测查询 |
| **TD-217** | 恢复演练：临时 Cluster（1 实例，从 bifrost-postgres 对象存储 bootstrap.recovery，targetTime 约 1 小时前，不同 serverName，只读凭据，独立 namespace）的清单 + 校验脚本（行数 / 最新时间戳对比）+ 清理步骤 |
| **TD-237** | 删除 data-warehouse：列出集群里要删的对象（只读 kubectl get）、删 `k8s/compute/warehouse` 清单（分支）、AGENT_FACTS :202 namespace 清单的改法 |
| **TD-103** | flex：解析器读 transactionID 属性（代码在分支）；回填 flex_transaction_id 的 SQL（先 dry-run 计数）；部分唯一索引 DDL（CONCURRENTLY） |
| **TD-107** | market-data：去掉 symbol_period_date；period_date_symbol 改为无条件幂等步骤（CONCURRENTLY），DDL 单独成文件 |
| **TD-160** | `DROP INDEX CONCURRENTLY features.event_radar_batch_collected, features.event_radar_importance` 的 SQL + 执行前后的 pg_index 核对 |
| **TD-148** | strategy_plan 的 source_kind CHECK 放宽加入 'lens'、'backtest_run'：三环境 DDL（约束名从 pg_constraint 读）+ core DATABASE.md 记录 |
| **TD-142** | **只列范围**：长期限 ATM IV 回填的 symbols × sessions × expiries 计数与预计行数、耗时（只读 GS） |
| **TD-172** | **只列范围**：2026-07-06..09-25 缺的 50–90 DTE 合约数 × sessions、vendor 回拉的请求量估算（只读） |

每个 DDL 文件跑 `grep -niE 'drop|truncate'` 并在报告里列出命中（TD-160 的 DROP INDEX 是预期内）。
