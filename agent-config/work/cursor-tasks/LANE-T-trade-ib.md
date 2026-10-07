# LANE-T — IB / 账户数据链（bifrost-trade-core、bifrost-trade-worker、bifrost-trade-api、bifrost-platform-plugin、少量 infra）

先读 `cursor-tasks/README.md`（**特别是「第 2 轮」一节：一律只推分支**）。每项的 Claim / Evidence / Fix / Ratchet 见台账 `### TD-n`。报告写到 `cursor-tasks/reports/LANE-T.md`。分支：各仓库 `cursor/t-<仓库简称>`（起点 origin/main）。core 只开一个分支、**按下表顺序**改，版本号一次性 bump（改公开接口：TD-91）。

**D10 硬边界**：只做只读数据路径。不碰下单、不扩容 daemon、不写 `ib:operator:cmd`。

| 顺序 | 项 | 要做的 | 注意 |
|---|---|---|---|
| 1 | **TD-91** P1 | `upsert_account_transactions` 写库失败要抛错（或返回 (written, skipped) 由调用方抛）；flex 插件跟着改 | 改公开接口：core bump，列出下游（flex 插件）兼容下限 |
| 2 | **TD-105** | DEV/STG operator 流：READ_ONLY_OPS / PROD_ONLY_OPS 改为显式白名单，测试断言 ALL_OPS 里每个 op 恰好属于一个集合 | 只改判定集合，不新增任何 op |
| 3 | **TD-212** | worker account_push：摘要缺 NetLiquidation、或持仓由非空变空但快照没标「读取成功」时拒写并 warning；插件侧读失败时不输出该键 | |
| 4 | **TD-211**（方案 A） | IB 插件只读调用 reqOpenOrders / reqExecutions，结果放进快照；core 只在键存在时写 open_orders（缺键 ≠ 空） | **只读 API**；任何下单 / 改单 / 撤单函数都不碰 |
| 5 | **TD-104** | gateway 三个健康 hash 写 `updated_at=time.time()`（按存活信号存时间戳的规则）；trade-api 的服务行改指向 `data/ib-gateway` Deployment，去掉已退役的 systemd 行 | 记忆 feedback_liveness_as_timestamps.md |
| 6 | **TD-240**（方案 B） | 先只读确认 `contract_quote_live` 在 DEV / STG / PROD 与代码里**还有没有读取方**（grep 各仓库 + 只读查询）。**有读取方 → 不删，停下写报告**；没有 → 删掉镜像、`_on_ticker*` 回调和写入路径 | |
| 7 | **TD-236 / TD-125** | 删插件对 `ib:account:stream` 的 XADD 与常量、core 里的 key 和注释、Console 目录里的流，两份 redis_ib_keys.json 一起改；退役的 TIBM 期 verify 脚本挪到 `scripts/archive`，删两个 flex_ops SQL 与 CLAUDE.md 提及 | redis-ib 上 `DEL` 那个 key 是 Owner 步骤，写进报告 |
