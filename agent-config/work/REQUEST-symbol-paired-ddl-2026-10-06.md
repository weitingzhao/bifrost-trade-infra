# DDL 请求：结算口径 `symbol_paired`（建议账本 S4 对照，方案 A）

> 2026-10-06 · Owner 已选方案 A（新增结算口径），本清单等 Owner 逐项点头后才执行。
> 库：PROD Golden Source（`bifrost_golden_source`）。D10 不涉及（只记录、只结算）。

## 1. 点名项（Owner 要的）

| # | 语句 | 作用 |
|---|---|---|
| 1 | `SET LOCAL lock_timeout = '5s'` | 拿不到锁 5 秒就放弃，不排队阻塞 |
| 2 | `ALTER TABLE research.suggestion_settlement DROP CONSTRAINT suggestion_settlement_basis_check` | 去掉旧的 basis 白名单（线上实测定义：model / model_stress / baseline_paired / actual） |
| 3 | `ALTER TABLE research.suggestion_settlement ADD CONSTRAINT suggestion_settlement_basis_check CHECK (basis IN ('model', 'model_stress', 'baseline_paired', 'actual', 'symbol_paired'))` | 同名约束，白名单多一个 `symbol_paired` |

2 和 3 在同一个事务里执行，中间没有「无约束」的可见窗口。

## 2. 自加项

无。不加列、不加表、不改权限、不动触发器。

## 3. 怎么执行

- 新模块 `bifrost_research.schema.migrate_symbol_paired`：不带参数只打印上面三条；`--apply` 先读当前约束定义，已含 `symbol_paired` 就什么都不做，否则执行并打印前后定义。
- 不放进每次都跑的 `schema.init`：账本 DDL 有测试守着「不出现 DROP」，这条一次性语句单独走。
- 方式：一次性 Job（`research` 命名空间，`analytics_writer`，即表的属主），镜像为带这个模块的新版本；或者在一次性 Pod 里跑同一条命令。按 CLAUDE.md，跑之前对要执行的 SQL `grep -niE 'drop|truncate'`——命中第 2 条，即本清单点名的那条。
- 时机：避开 22:30 ET 的 research_trading_day（账本结算在写这张表）。

## 4. 行为变化

- 表结构以外无变化；现有行全部满足新约束（新约束是旧约束的超集），ADD CONSTRAINT 的校验必过，表当前只有个位数行，锁持有时间可以忽略。
- 新代码上线后，Pine 建议会多一种结算行 `symbol_paired`：同一名字、同一结构和规则，入场日换成信号**之后** 7 个日历日内该脚本没触发的某个交易日（按建议 id 的哈希选出，可复现）；等这 7 天过完才写。只取之后：回放实测，信号之前的对照日会吃到触发信号的那段走势（对照 +4% vs 信号约 0%），之后的对照与信号持平。

## 5. 不可逆的地方

- 第 2、3 条本身可以反向执行（换回旧白名单）。
- **但一旦写入第一条 `symbol_paired` 行，就回不去了**：缩回旧白名单需要先删掉这些行，而账本的只追加触发器拒绝 DELETE。要回退只能停止写入（代码里去掉这个口径），已有的行留着。

## 6. 回滚

- 写入任何 `symbol_paired` 行之前：同一事务里 DROP 新约束、ADD 旧白名单的约束。
- 写入之后：只停写，不删行（见 5）。
