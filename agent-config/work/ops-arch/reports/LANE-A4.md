# LANE-A4 报告

## LANE-A4

- 改动：bifrost-trade-infra · main · `16b9716a49c8c24cbdea52e758fc4885899bd481`（38 个文件迁入 `agent-config/work/`，并更新 `agent-config/README.md` 的布局表与重建符号链接命令）。本报告是紧随其后的文档提交，不计入下面的 38。
- 防线：没有可行的 CI 防线。符号链接在工作区根，工作区根不是 git 仓库，infra CI 看不到这些链接是否还在。恢复路径写在 `agent-config/README.md` 的「重建符号链接」命令里。
- 门禁：纯文档，没有 Python / TypeScript / Go 改动，未跑 `make lint`、`tsc`、`go test`。
- 验收：
  - `ls -l /Users/vision-mac-trader/Desktop/stocks/PLAN-phase0-foundation-2026-10-05.md` → 符号链接指向 `bifrost-trade-infra/agent-config/work/PLAN-phase0-foundation-2026-10-05.md`
  - `git -C bifrost-trade-infra ls-files agent-config/work | grep -v '^agent-config/work/ops-arch/' | wc -l` → `38`（与下面的清单条数相同）。原始 `git ls-files agent-config/work | wc -l` 还包含已有的 `ops-arch/`（本报告也在其下），所以大于 38。
- 要 Owner 批：没有。三个扫描命中文件留在工作区根，内容没有改写。
- 后续：
  - 推送后，共享 checkout 里同内容的未跟踪副本已移开，并 fast-forward 到当时的 `main`。开工前该 checkout 对 `bifrost-trade.code-workspace` 的本地修改还在，没有纳入本次提交。
  - `cursor-tasks/LANE-F-flex-txid-writer.md` 在本道扫描之后出现（mtime 2026-10-07 14:07），是别的会话新写的。没有搬，也没有提交。
  - `cursor-tasks/` 没有整目录换成一条符号链接：下面三个命中文件，加上后出现的 `LANE-F`，必须仍是工作区根上的普通文件。干净文件各自 `mv` 后 `ln -s`。

### 扫描命中（留下，未搬）

| 文件 | 行 | 原因 |
|---|---|---|
| `cursor-tasks/LANE-O-orphans.md` | 9 | 金额模式 |
| `cursor-tasks/reports/LANE-O.md` | 33 | 金额模式 |
| `cursor-tasks/reports/LANE-O.md` | 45 | 金额模式 |
| `cursor-tasks/reports/LANE-D.md` | 112 | 金额模式 |
| `cursor-tasks/reports/LANE-D.md` | 181 | 同一金额正则命中 awk 字段引用；该文件已因第 112 行留下 |

未命中、已搬：令牌、密码、带密码的连接串、kubeconfig 正文、ntfy topic、余额、持仓数量。`REVIEW-system-architecture-2026-10-05.md:23` 有账户号，按 `AGENT_FACTS.md`「账户号不是秘密」放行，该行没有余额或持仓数量。若干文件只引用 `KUBECONFIG` 路径，不是 kubeconfig 正文。

### 已搬文件（38，不含 ops-arch）

- `LEDGER-pine-tradingview-gaps.md`
- `PLAN-phase0-foundation-2026-10-05.md`
- `REQUEST-symbol-paired-ddl-2026-10-06.md`
- `REQUEST-td96-preflight-d10-2026-10-06/README.md`
- `REQUEST-td96-preflight-d10-2026-10-06/preflight.current.js`
- `REQUEST-td96-preflight-d10-2026-10-06/preflight.diff`
- `REQUEST-td96-preflight-d10-2026-10-06/preflight.proposed.js`
- `REQUEST-td96-preflight-d10-2026-10-06/test.current.js`
- `REQUEST-td96-preflight-d10-2026-10-06/test.final.js`
- `REQUEST-td96-preflight-d10-2026-10-06/test.proposed.js`
- `REQUEST-w3-archive-before-delete-2026-10-05.md`
- `REVIEW-architecture-discussion-round1-2026-10-05.md`
- `REVIEW-system-architecture-2026-10-05.md`
- `REVIEW-trade-system-completeness-and-backtest-2026-10-04.md`
- `cursor-tasks/LANE-D-docs-inventory.md`
- `cursor-tasks/LANE-D2-db-prepare.md`
- `cursor-tasks/LANE-G-governance-docs.md`
- `cursor-tasks/LANE-M-db-role-matrix.md`
- `cursor-tasks/LANE-P-platform.md`
- `cursor-tasks/LANE-R1-release-chain.md`
- `cursor-tasks/LANE-R2-research-marketdata.md`
- `cursor-tasks/LANE-S1-agent-security.md`
- `cursor-tasks/LANE-S2-platform-api.md`
- `cursor-tasks/LANE-T-trade-ib.md`
- `cursor-tasks/LANE-T2-ib-status-and-quote-mirror.md`
- `cursor-tasks/LANE-U-ui-infra.md`
- `cursor-tasks/LANE-U2-ui-frontend.md`
- `cursor-tasks/README.md`
- `cursor-tasks/reports/LANE-D2.md`
- `cursor-tasks/reports/LANE-G.md`
- `cursor-tasks/reports/LANE-P.md`
- `cursor-tasks/reports/LANE-R1.md`
- `cursor-tasks/reports/LANE-R2.md`
- `cursor-tasks/reports/LANE-S1.md`
- `cursor-tasks/reports/LANE-S2.md`
- `cursor-tasks/reports/LANE-T.md`
- `cursor-tasks/reports/LANE-U.md`
- `cursor-tasks/reports/LANE-U2.md`
