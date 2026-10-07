# LANE-T 报告

八条里七条 Claim 在 `origin/main` 上成立并已推到分支。TD-240 按方案 B 停下，没有删表。没有 push main，没有 apply / PipelineRun / `release.sh stg|prod|dev`，没有写库，没有改 `TECH_DEBT.md` / `RATCHETS.md`。D10 只走只读数据路径：没有碰下单、改单、撤单、daemon 副本，也没有写 `ib:operator:cmd`。健康 hash 只加了 `updated_at`，没有加 SHA（SHA 归 LANE-R1 / TD-122）。

core 只有一个分支、一次版本号：`0.57.0` → `0.58.0`。公开接口变化是 `upsert_account_transactions` 的返回值从 `int` 变成 `(written, skipped)`，并且数据库错误向上抛。受影响下游：

| 下游 | 是否调用新返回值 | 兼容下限 |
|---|---|---|
| bifrost-platform-plugin-flex-query | 唯一调用方 | `bifrost-core>=0.58.0`（本分支已抬） |
| bifrost-trade-api | 不调用 | 仍是 `>=0.55.2` |
| bifrost-trade-worker | 不调用该函数；下一张镜像编进 core 0.58.0 后，账户快照的缺键语义会跟着变 | 仍是 `>=0.39.0` |
| bifrost-platform-plugin | 不 import core | 无 |
| bifrost-research | 无 | 无 |

插件 `tests/test_self_heal.py` 删了一处 `origin/main` 上就有的未使用 `patch` 导入。本机 ruff 0.15 跑 `make lint` 会因此失败，所以放进了插件那一次提交。

## TD-91
- Claim：成立（起点 `549a656` 的 `src/bifrost_core/portfolio/reader/accounts.py:1350` 返回 `len(rows)`，`:1353` 的 `except Exception` 记 warning 后返回 0。跳过的行也被算进写入数）
- 改动：
  - bifrost-trade-core · `cursor/t-core` · `4094ff7665ea2d7aa87d0c7e0860b54828c6a58d`
  - bifrost-platform-plugin-flex-query · `cursor/t-flex` · `7f31a86e025027264b0e45f5491eb09e0ca263b0`
- 防线：`bifrost-trade-core/tests/test_connect_helpers.py` 的 `test_upsert_account_transactions_connect_failure_propagates`、`test_upsert_account_transactions_cursor_error_propagates`、`test_upsert_account_transactions_counts_written_and_skipped`。`tests/test_money_writers_db.py` 把成功路径改成 `(written, skipped)`（`db` 标记，`make test` 不跑）。flex `tests/test_transactions_window.py` 的 `test_parsed_rows_with_nothing_written_fails_the_job`。没有往 infra `scan.sh` 加「except 后 return 0」的全库指标：那条扫的是别的道的文件，本道用上述测试当防线。
- 门禁：
  - core `make lint` → exit 0
  - core `make test` → exit 2：13460 passed，1 failed，1 skipped，111 deselected，2 xfailed，2 xpassed。失败的是 `tests/test_golden_black_scholes.py::test_core_matches_the_fixture`（本机 py_vollib 在若干格点上给出 nan，期望 0.0）。该提交没有改 greeks 或这个测试。本道三条 upsert 测试在 `test_connect_helpers.py` 里，78 passed 的那一组（含 redis 合同与 open-orders 缺键）是绿的
  - flex `make lint` → exit 0
  - flex `make test` → exit 0：158 passed，3 deselected，1 xfailed
- 验收：在 core `4094ff7665ea2d7aa87d0c7e0860b54828c6a58d` 上 `PYTHONPATH=src pytest -q tests/test_connect_helpers.py -k upsert_account_transactions`，预期 3 passed。flex `7f31a86e` 上 `PYTHONPATH=src pytest -q tests/test_transactions_window.py::test_parsed_rows_with_nothing_written_fails_the_job`，预期 passed，且 `pyproject.toml` 含 `bifrost-core>=0.58.0`
- 要 Owner 批：发版时 flex 镜像必须按 core 0.58.0 编（下限已写进 extra）。`BIFROST_CORE_REF` 本道没改。api / worker 的 pip 下限没有抬
- 后续：无后续

## TD-105
- Claim：成立（起点 `39eafe2` 的 `READ_ONLY_OPS` 是 `ALL_OPS` 减去 `disconnect_all` / `reconnect_all`，不是显式白名单）
- 改动：bifrost-platform-plugin · `cursor/t-plugin` · `4390a3f441e3eba76947cd1e3c86c7b2da739ff8`（与本道其余插件改动同一次提交）
- 防线：`tests/test_operator_streams.py` 的 `test_every_op_is_in_exactly_one_allowlist`（每个 `ALL_OPS` 操作恰好落在 `READ_ONLY_OPS` 或 `PROD_ONLY_OPS` 之一）。没有新增 op。`op_allowed_on_stream` 仍是：环境流只放行 `READ_ONLY_OPS`
- 门禁：插件 `make lint` → exit 0；`make test` → exit 0，79 passed
- 验收：在 `4390a3f441e3eba76947cd1e3c86c7b2da739ff8` 上 `pytest -q tests/test_operator_streams.py::test_every_op_is_in_exactly_one_allowlist`，预期 passed。`protocol.py` 里两个集合是字面量元组
- 要 Owner 批：没有（随插件镜像发布后生效）
- 后续：无后续

## TD-212
- Claim：成立（起点上插件在 `reqPositionsAsync` 失败时写 `positions: []`，summary 失败时只留账户号；worker 只要指纹变了就写；core 在 `seen_keys` 为空时删光持仓，并把空的 `NetLiquidation` 写进去）
- 改动：
  - bifrost-platform-plugin · `cursor/t-plugin` · `4390a3f441e3eba76947cd1e3c86c7b2da739ff8`
  - bifrost-trade-worker · `cursor/t-worker` · `60e37c99febc456e91b50eadc65c926debf446ee`
  - bifrost-trade-core · `cursor/t-core` · `4094ff7665ea2d7aa87d0c7e0860b54828c6a58d`（`accounts_sync.py`：`NetLiquidation` 用 `COALESCE` 留住旧 NAV；`positions` 键缺失或 `positions_ok is False` 时不 upsert、不删除）
- 防线：插件 `tests/test_account_snapshot_degraded.py` 的 `test_positions_read_failure_omits_the_positions_key`、`test_summary_read_failure_omits_net_liquidation`、`test_successful_reads_keep_positions_and_nav`。worker `tests/test_account_push.py` 的 `test_degraded_snapshot_is_not_written`（缺 NAV、非空变空且没有 `positions_ok`，都拒绝；`positions_ok is True` 的空簿仍写）。core 侧是 `accounts_sync.py` 的跳过条件，没有单独的 db 测试（`make test` 排除 `db`）
- 门禁：
  - 插件见 TD-105（79 passed）
  - worker `make lint` → exit 0；`make test` → exit 0，180 passed
  - core 见 TD-91
- 验收：worker `60e37c99febc456e91b50eadc65c926debf446ee` 上 `PYTHONPATH=<core 0.58.0 src>:src pytest -q tests/test_account_push.py::test_degraded_snapshot_is_not_written`，预期 passed。插件上 `pytest -q tests/test_account_snapshot_degraded.py -k 'positions_read or summary_read'`，预期 2 passed
- 要 Owner 批：worker 与插件要发一版才会在集群里生效。worker 进程内的「上一笔持仓非空」重启后丢失；core 在键缺失或 `positions_ok is False` 时不删持仓，用来挡住重启后的降级快照
- 后续：无后续

## TD-211
- Claim：成立（起点快照没有 `open_orders`；`ib_edge` 用 `data.get("open_orders") or []` 再 `write_open_orders`，缺键会被当成空簿并 TRUNCATE）
- 改动：
  - bifrost-platform-plugin · `cursor/t-plugin` · `4390a3f441e3eba76947cd1e3c86c7b2da739ff8`（只读 `reqOpenOrdersAsync` / `reqExecutionsAsync`；失败则快照不带这两个键。成交缓存调用 `wait_commission=False`，避免每圈睡 3 秒）
  - bifrost-trade-core · `cursor/t-core` · `4094ff7665ea2d7aa87d0c7e0860b54828c6a58d`（键在才写 `open_orders`；`last_execution_rows` 要键在且非空才写）
  - bifrost-trade-worker · `cursor/t-worker` · `60e37c99febc456e91b50eadc65c926debf446ee`（只改了 `CLAUDE.md`：订单仅在快照带键时落库）
- 防线：core `tests/test_write_failure_log_levels.py` 的 `test_missing_open_orders_key_is_not_an_empty_book`。插件 `tests/test_account_snapshot_degraded.py` 的 `test_open_orders_use_req_open_orders_only`、`test_fetch_open_orders_does_not_define_a_write`（源码里不得出现 `placeOrder` / `cancelOrder` / `reqModifyOrder`）
- 门禁：同 TD-91 / TD-105 / TD-212
- 验收：core 上 `PYTHONPATH=src pytest -q tests/test_write_failure_log_levels.py::test_missing_open_orders_key_is_not_an_empty_book`，预期 passed，且 sink 的 `write_open_orders` 调用次数为 0。插件上 `pytest -q tests/test_account_snapshot_degraded.py::test_fetch_open_orders_does_not_define_a_write`，预期 passed
- 要 Owner 批：没有额外动作。插件与 core 要一起发，否则旧 core 仍会把缺键当成空簿
- 后续：`reqOpenOrders` 只看见本 client id 的订单，手工在 TWS 下的单可能不出现。`reqAllOpenOrders` 仍是只读，但本道允许的调用只有 `reqOpenOrders` / `reqExecutions`，没有改用它

## TD-104
- Claim：成立（三个 `bifrost:health:ws_ib_{ingestor,account_agent,operator}` 写入没有 `updated_at`；trade-api 服务行写的是已退役的 systemd unit / `ib-operator`、`ib-market-gateway`、`ib-account-agent`）
- 改动：
  - bifrost-platform-plugin · `cursor/t-plugin` · `4390a3f441e3eba76947cd1e3c86c7b2da739ff8`（`writer.py` `_health_fields` 最后写入 `updated_at=time.time()`，调用方盖不住。合同 `health_hash_fields` 要求这三个 hash 带 `updated_at`，没有 `sha`）
  - bifrost-trade-api · `cursor/t-api` · `d980168569628e55bf6a645f96ce01465ecae1a3`
- 防线：插件 `tests/test_health_hash_updated_at.py` 的 `test_three_health_hashes_stamp_updated_at`。api `tests/test_market_ingest_platform_gateway.py` 的 `test_ib_rows_point_at_data_ib_gateway_not_retired_units`、`test_health_hash_without_updated_at_is_not_live`。`tests/test_ops_executor_kubernetes.py` 的 `test_retired_ib_unit_is_not_a_workload`（即使把退役 unit 放进 allowlist，也不去读 Deployment）。副本计数把行上的 `k8s_namespace=data` 传给 executor，因为 gateway 不在 trade 命名空间
- 门禁：
  - 插件见 TD-105
  - api `make lint` → exit 0；`make test` → exit 0，1015 passed，1 deselected
- 验收：api `d980168569628e55bf6a645f96ce01465ecae1a3` 上 `PYTHONPATH=<core src>:src pytest -q tests/test_market_ingest_platform_gateway.py::test_ib_rows_point_at_data_ib_gateway_not_retired_units tests/test_market_ingest_platform_gateway.py::test_health_hash_without_updated_at_is_not_live`，预期 2 passed。三行的 `k8s_namespace` 为 `data`、`k8s_deployment` 为 `ib-gateway`，且没有 `systemd_unit`
- 要 Owner 批：trade-api 与插件要发一版，`/ops/market-ingest/services` 才会按新行和 `updated_at` 判断。本道没有 rollout
- 后续：无后续。autorepair 里故意冻结的 `connected=true` 没有改

## TD-240
- Claim：方案 B 要求先确认还有没有读者。代码里还有读者，所以停下，没有删 `contract_quote_live`，也没有删 mirror / `_on_ticker*` / 写入路径
- 改动：无（没有分支、没有提交）
- 防线：不做删除，所以没有新测试。读者本身就是停手的证据
- 门禁：无代码变更，没有跑门禁
- 验收：在 `origin/main` 上能看到下列读者（本道 worktree 与起点一致，这些文件没改）：
  - core `src/bifrost_core/portfolio/model/core.py:3`（读持仓 + `contract_quote_live` + 账户摘要）
  - core `src/bifrost_core/portfolio/quote_freshness.py:1`（这行报价还算不算价格）
  - core `src/bifrost_core/portfolio/reader/executions.py:1563`（TD-140：新鲜行提供 `price_mid`）
  - core `src/bifrost_core/monitor/reader/market.py:146` 与 `common.py:180`（`GET /quotes` 的 OPT）
  - core `src/bifrost_core/persistence/postgres/postgres_sink.py:215` `write_contract_quote_live`
  - api `src/bifrost_api/market/routers/quotes.py:53` 与 `:141`（OPT 回落到这张表）
  - worker `src/bifrost_worker/daemon/app/contract_quote_live.py:1` 以及 `gs_trading.py:280`（写入；写入在 mock hedge 守卫里）
- 要 Owner 批：不要删。若仍要删，先去掉上面这些读者并另开一条，再谈表
- 后续：没有对 DEV / STG / PROD 做只读行数查询。代码读者已经要求停下，查行数不会改变这个结论

## TD-236
- Claim：成立（插件对 `ib:account:stream` 做 XADD；core 与插件各有一份常量；console catalog 把 R3 标成 redis-live 上的 stream；两份 `redis_ib_keys.json` 都列了这个键）
- 改动：
  - bifrost-platform-plugin · `cursor/t-plugin` · `4390a3f441e3eba76947cd1e3c86c7b2da739ff8`（去掉 XADD、`IB_ACCOUNT_STREAM_KEY` / `MAXLEN`）
  - bifrost-trade-core · `cursor/t-core` · `4094ff7665ea2d7aa87d0c7e0860b54828c6a58d`（去掉同名常量；两份 JSON 字节一致，并加上 `health_hash_fields`）
  - bifrost-platform · `cursor/t-platform` · `a9c35b11550bed6e1e837f2017fa822e0c9586fa`（R3 改为 redis-ib 上的 snapshot + notify）
- 防线：插件 `tests/test_health_hash_updated_at.py` 的 `test_account_snapshot_does_not_xadd_the_retired_stream`。core `tests/test_redis_ib_contract.py` 不再登记 stream 常量，并在设置 `BIFROST_PLATFORM_PLUGIN_ROOT` 时比对两份 JSON。`src` 里不再有 `IB_ACCOUNT_STREAM` 字符串常量（`redis_health_keys.py` 的注释仍写出退役键名，注释不进 AST 字面量扫描）
- 门禁：
  - core / 插件见上
  - platform console：`npx tsc -b` → exit 0；`npm run lint` → exit 0（19 条既有 warning，0 error）；`npx vitest run` → 118 files，801 passed；`npm run build` → exit 0。worktree 不在仓库旁边，构建前把 `/tmp/bifrost-ui` 指到工作区的 `bifrost-ui`，否则 `@source "../../../bifrost-ui/..."` 找不到 CSS。这不是本改动引入的
- 验收：`git grep -n IB_ACCOUNT_STREAM 4390a3f441e3eba76947cd1e3c86c7b2da739ff8 -- src tests/contracts` 与 core 同一提交的 `src`，预期都没有命中。platform `a9c35b11550bed6e1e837f2017fa822e0c9586fa` 的 catalog 键为 `ib:account:snapshot:v1, ib:account:notify`
- 要 Owner 批：在 redis-ib 上 `DEL ib:account:stream:v1`。本道没有执行这条删除。插件镜像发布后不再 XADD，旧键会留到 Owner 删
- 后续：无后续

## TD-125
- Claim：成立（TIBM 的 verify 脚本和 Makefile 目标还在 `scripts/` 顶层；flex 仍有 `scripts/drop_trade_flex_ops_legacy.sql` 与 `scripts/golden_source_flex_ops_compat_views.sql`，`CLAUDE.md` 点到它们。当前 gateway 的 `verify-ib-gateway*.sh` / `verify-redis-ib.sh` / `verify-trade-quotes-e2e.sh` 留在原处）
- 改动：
  - bifrost-platform-plugin · `cursor/t-plugin` · `4390a3f441e3eba76947cd1e3c86c7b2da739ff8`（16 个 verify 脚本与 `scripts/lib/tibm_prod_defaults.sh` 移到 `scripts/archive`；`ROOT` 改成 `../..`；cutover 改为 source `../lib/redis_operator_ping.sh`。Makefile 去掉对应目标。`verify-ib-gateway-program.sh` 改为直接跑归档后的 cutover 脚本，不再走已删的 make 目标。`scripts/lib/redis_operator_ping.sh` 与 `tibm_redis_acl.sh` 留在 `scripts/lib`）
  - bifrost-platform-plugin-flex-query · `cursor/t-flex` · `7f31a86e025027264b0e45f5491eb09e0ca263b0`（删掉上述两个 SQL；`CLAUDE.md` 去掉对它们的命令注释，并去掉 `flex_ops.*` DEPRECATED 那一行。`ensure_flex_ops_schema` 这个仍在用的函数没有删）
- 防线：插件 `tests/test_retired_tibm_scripts.py` 的 `test_retired_workload_names_stay_in_scripts_archive`。扫描仓库里 `.sh/.py/.md/.yaml/.yml`，`scripts/archive` 与测试文件自身除外。`scripts/sync-redis-ib-dev-compose-config.sh` 在允许名单里：它的 `consumer_group: ib-operator` 是 Redis 组名，不是 Kubernetes workload，core 已有测试说明它不是 gateway 的组
- 门禁：插件与 flex 见上
- 验收：在插件 `4390a3f4` 上 `pytest -q tests/test_retired_tibm_scripts.py`，预期 passed。`ls scripts/verify-trade-ib-w1-prod.sh` 应不存在，`scripts/archive/verify-trade-ib-w1-prod.sh` 应存在。flex 上两个 SQL 路径 `git cat-file -e 7f31a86e:scripts/drop_trade_flex_ops_legacy.sql` 应失败
- 要 Owner 批：没有集群动作。归档脚本里的 `make verify-trade-ib-*` 已经没有对应目标，那些脚本不再是现行步骤
- 后续：已经在 `scripts/archive/` 里的 `rollout-tibm-*.sh` 仍用 `dirname/..` 当仓库根（它们搬进去时就这样），本道把误改的三处还原了，没有修这批旧路径。`sync-redis-ib-dev-compose-config.sh` 的 consumer group 与 gateway 的 `ib-gateway` 组不同，是既有差异，没有改
