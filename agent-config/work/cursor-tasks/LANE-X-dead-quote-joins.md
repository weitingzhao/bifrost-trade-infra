# LANE-X — 四处永远取不到数的报价 JOIN：先量，再决定（TD-260，core · worker · frontend）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不写库、不做 DDL）。报告写到 `cursor-tasks/reports/LANE-X.md`。
分支：`cursor/x-core`、`cursor/x-worker`、`cursor/x-frontend`（各从 `origin/main` 新开；哪个不需要改就不要建）。

## 背景（台账 `### TD-260`）

TD-240（已上 PROD）删掉了 `raw_broker.contract_quote_live` 的**全部写入方**。Owner 决定**保留表**，所以 core 里还剩四处读：

- `src/bifrost_core/portfolio/model/core.py:65` — `LEFT JOIN … cq … AND fresh_quote_sql('cq')`
- `src/bifrost_core/portfolio/reader/accounts.py:441` — `LEFT JOIN … ip`
- `src/bifrost_core/portfolio/reader/executions.py:1592` — `LEFT JOIN … cql`
- `src/bifrost_core/portfolio/services/short_legs.py:46` — `FROM … q`

四处都过 `fresh_quote_sql(alias)`＝`updated_at >= now() - make_interval(secs => LIVE_QUOTE_MAX_AGE_SEC)`。
PROD 表里最新一行是 **2026-03-28**，所以这四处**永远匹配不到行**。不是坏了，是一条看起来活着、却不可能返回报价的读路径。

## 这条道的重点是「先量」，不是先删

**不要**上来就删 JOIN。先逐处回答两个问题，把答案写进报告：

1. 这处 JOIN 喂的是哪个 API 字段、最终是页面上的哪一列？（顺着 core → api → frontend 找到页面）
2. 报价为 NULL 时，那一列现在**显示什么**？是 `0`、`—`、空白，还是别的？在 `:5173` 对 DEV 实际看一眼，把看到的字面写进报告。

只读查询可以用 `PGOPTIONS=-c default_transaction_read_only=on`。

## 量完之后，逐处二选一

- **页面已有活的来源**（`GET /quotes` 直接读 Redis）→ 删掉这处 JOIN 和它喂的死字段。
- **没有别的来源** → JOIN 留着，但页面要说清这个读数没有人供，**不能显示 0**（0 是一个计数，「没有人写这个」不是）。按该页现有的「没有数据」措辞写，不要新造一套。

**两处都不要给这张表加写入方** —— Owner 2026-10-08 选了 B（删镜像）。如果你量完觉得某处确实需要盘中报价，**停下写进报告**，列出 2–3 个方案和你的推荐，不要自己接写入。

## 一定要做的一件小事

`bifrost-trade-worker/CLAUDE.md:61` 还写着 `contract_quote_live`（来自 Redis 报价）是 daemon 的写入。这句已经不成立，改掉（分支 `cursor/x-worker`）。这一条不依赖上面的测量结论。

## 防线

留下来的那些处：一条测试断言报价为 NULL 时该列读作「没有供给」而不是 `0`。删掉的那些处：TD-240 已有的三条删除测试已经挡住写入方回来，不用再加。报告里写清测试名，或写明为什么某处做不了。

## 门禁

core / worker `make lint && make test`（worker 测试的 `PYTHONPATH` 要把本分支的 `src` 放在 core 的 `src` 前面，否则会测到共享 checkout 的 editable 安装）；
frontend `npx tsc -b && npm run lint && npx vitest run && npm run build`。退出码分开记录。
core 若改了公开接口，按 `.cursor/rules/versioning.mdc` bump 并在报告里列下游；**删公开函数不是 patch**（上一轮 core 因此定在 0.59.0，不是 0.58.2）。

## 不做

不删表、不写 DDL、不发版、不推 main。
