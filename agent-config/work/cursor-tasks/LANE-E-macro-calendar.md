# LANE-E — 宏观日历补 2027 CPI 与非农（TD-180，research）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不写库）。报告写到 `cursor-tasks/reports/LANE-E.md`。
分支：`cursor/e-research`（bifrost-research，从 `origin/main` 新开）。

## 背景

`bifrost-research/src/bifrost_research/scheduler/data/macro_calendar.csv` 有 FOMC 到 2027，但 CPI 只到 `2026-12-10`（:35），
没有任何 Employment Situation（非农）日期。10-06 从本机访问 bls.gov 返回 403，所以当时没填。
从 11-05 起 macro_calendar 的 asset check 会告警（剩余不足 30 天）。

## 要做

1. 从 BLS 官方发布日程取 2026 年剩余与 2027 年全年的 CPI 和 Employment Situation 发布日（08:30 ET）。
   bls.gov 若仍 403，试官方的其他入口（同站的 schedule 页 / ICS / 年度 release calendar PDF）；
   **只用 BLS 官方来源**，不要用财经网站转抄。取不到就停下，在报告里写清试过哪些 URL、各自返回什么。
2. 按现有行格式追加（`date,time,country,event,period`），事件名沿用文件里已有的写法（CPI 用 `CPI`；非农先看 asset 与读方代码认哪个名字，没有约定就用 `NFP`，并在报告里写明读方是否需要跟着改）。
3. 报告里列出来源 URL 与抓取日期，每行日期能对回来源。
4. 防线：已有（asset check 剩余 < 30 天告警）。另加一个单测：CSV 里每个序列（FOMC / CPI / 非农）最后一个日期 ≥ 当前日期 + 180 天，避免下一次又悄悄耗尽。
5. 门禁：`make lint && make test`，退出码分开记录。

## 不做

不 bump 版本、不推 main、不发版（Claude Code 合并后随下一次 Research 发布上线）。
