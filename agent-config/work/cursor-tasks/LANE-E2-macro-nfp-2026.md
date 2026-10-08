# LANE-E2 — 把已核对的 2026 非农写进宏观日历（TD-180 的前半，research）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不写库）。报告写到 `cursor-tasks/reports/LANE-E2.md`。
分支：`cursor/e2-research`（bifrost-research，从 `origin/main` 新开）。

## 背景（LANE-E 已经查过，不要重查）

LANE-E 2026-10-07 查证并由 Claude 2026-10-08 独立复核：**BLS 的 2027 全年日程尚未发布**（`/schedule/2027/home.htm` 404，官方 ICS 全文无 `2027`，`empsit.htm` 最后一行是 Dec. 04, 2026）。所以 TD-180 的 2027 部分等 BLS，不在本道范围。

但 LANE-E 同时核对出两行**官方已发布的非农**，因为当时那条「最后日期 ≥ 今天+180 天」的防线会红而没有写入。那条防线是错的（BLS 只提前约 14 个月排期），已作废。日历从来没有过非农，这是 TD-180 Claim 的一半，现在就能补。

**本机 `urllib` 直连 bls.gov 一律 403**（Access Denied）。要核对就用能打开页面的浏览器会话读同一官方 URL；不要从财经网站转抄。

## 要做

1. 在 `src/bifrost_research/scheduler/data/macro_calendar.csv` 追加两行。**表头是 `event_date,release_time_et,country,indicator,notes`**（不是别处写的 `date,time,country,event,period`）：

   - `2026-11-06,08:30,US,NFP,October 2026`
   - `2026-12-04,08:30,US,NFP,November 2026`

   指标名用 `NFP`：文件里没有非农的既定名字。来源 `https://www.bls.gov/schedule/news_release/empsit.htm` 与 `https://www.bls.gov/schedule/2026/home.htm`，两处一致。**写入前自己再核一次这两个日期**，核不上就停下写报告，不要照抄本文件。
2. 读方 `event_calendar.py` 的 `MACRO_IMPORTANCE` 只有 `FOMC rate decision` 与 `CPI`，其余指标重要度为 1。**要不要把 `NFP` 加进 `MACRO_IMPORTANCE`，由你判断并在报告里写明理由**：加了它和 CPI 同等突出，不加就以重要度 1 出现。两种都可接受，但要给出依据（看这个字段在页面上实际怎么用），不要两边都不选。
3. 防线：单测断言 CSV 里**每个序列（FOMC / CPI / NFP）至少有一个未来日期**（用注入的"今天"，不要用真实时钟 —— 见 `feedback_dates_from_the_clock` 的教训）。**不要**写「最后日期 ≥ 今天+180 天」，那条在正常年份也会红。
4. 门禁：`make lint && make test`，退出码分开记录。

## 不做

不 bump 版本、不推 main、不发版（Claude Code 合并后随下一次 Research 发布上线）。不碰 2027（BLS 还没发）。
