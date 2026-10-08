# LANE-E3 — 非农行没有主题：主题正则不认 `NFP`（TD-265，research）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不写库、不改 `TECH_DEBT.md` / `RATCHETS.md`）。报告写到 `cursor-tasks/reports/LANE-E3.md`。
分支：`cursor/e3-research`（bifrost-research，从当前 `origin/main` 新开；LANE-E2 的两行 NFP 已在 main 上）。

## 背景（台账 `### TD-265`）

LANE-E2 把两行非农写进了 `macro_calendar.csv`（`2026-11-06` / `2026-12-04`，指标名 `NFP`）。
`pipeline.py:357` 的主题正则认 CPI 和 FOMC 的写法，**不认 `NFP`**，所以这两行的 theme 是空的，不会归进利率路径那一组。同一条正则也用于事件雷达入库时的分类。

结果：宏观日历里能看到非农，但「下次利率决议」的主题视图里少了对它影响最大的那一项。

## 要做

1. 把非农加进主题正则：`NFP`，以及拼写形式 `Employment Situation`（如果事件雷达会摄入那种写法 —— **先查清楚再加**，查的结果写进报告）。
2. 顺带核一遍：`macro_calendar.csv` 里**现有的每一个指标**是不是都能解析出非空主题？有别的漏网的一并修，报告里列出来。
3. 防线：表驱动测试 —— `macro_calendar.csv` 里出现的每一个指标都解析出非空主题。这样以后再加指标忘了配主题会当场红。
   注意这条正则同时供事件雷达分类用，测试里把两个用途都盖到。
4. 门禁：`make lint && make test`，退出码分开记录。`PYTHONPATH` 把本分支 worktree 的 `src` 放最前面。

## 不做

不 bump 版本（随下次 Research 发布上线）、不推 main、不发版、不写库。不碰 `k8s/`（Research 的 Argo 直连 GitHub，推 `k8s/` 等于改运行时）。
