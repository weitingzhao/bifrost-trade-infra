# platform 分支清理空跑清单 — 2026-10-19 21:4x

Owner 10-19 21:3x「已合并的 62 条分支先空跑 prune 列清单给我」「分支照建议」。数据：`scripts/prune-merged-branches.sh --repos bifrost-platform`（空跑）对 Gitea `origin`；判「已合并」按 Change-Id，没有 Change-Id 的按标题，所以比按祖先算的 62 条多 5 条（3 条 cursor 分支、2 条 agent 分支的提交以另一个哈希进了 main）。

## 要删的 67 条（内容都已在 main）

`--apply` 先把每个要删的引用打成 bundle、写名字和 sha 清单到备份目录，再删；恢复一条：`git push origin <sha>:refs/heads/<name>`。

| 分支 | 最后提交 |
|---|---|
| `agent/t_01M50FZ523HZTGYJA0VB6BNE7N/a2` | 2026-10-15 mcp: the token file may hold the STG operator token for a server pinn |
| `agent/t_01M54G35C3ZVJYGQ07SZY93A39/a1` | 2026-10-17 agentd: test a relative link out of the root and a link inside an old |
| `cursor/a-platform` | 2026-10-08 LANE-A2: guard Approval Go struct parser against empty pass |
| `cursor/a5-platform` | 2026-10-07 Stop shipping the 03:00 Mini jobs and mark unset workstation bridges  |
| `cursor/a8-platform` | 2026-10-07 Keep the remote alert relay unless the deployer sets it. |
| `cursor/b-platform` | 2026-10-08 LANE-B: pass who through MCP start_pipeline_run (TD-262) |
| `cursor/b1-platform` | 2026-10-07 Add an action catalog and approval API so C and D writes run only aft |
| `cursor/b2-platform` | 2026-10-07 Let the console decide an approval and page the Owner when one is cre |
| `cursor/b3-platform` | 2026-10-07 Send C/D MCP writes through approvals and keep laptop tools off PROD. |
| `cursor/b4-platform` | 2026-10-07 Stop STG maintenance loops and accept reporter on the alert webhook. |
| `cursor/e1-platform` | 2026-10-08 Skip plugin probes on workers /metrics. |
| `cursor/p2-platform` | 2026-10-07 Read plugin freshness from the plugin HTTP APIs. |
| `cursor/phase2-platform` | 2026-10-07 Let MCP writes follow the approvals API instead of a second tier list |
| `cursor/phase3-platform` | 2026-10-07 Remove the unmounted bus, operator-plane, and patrol-log pages. |
| `cursor/phase3-s1` | 2026-10-07 Retire checklist dispatch and the phase-3 backend surfaces. |
| `cursor/phase3-s2` | 2026-10-07 Point the Ops Console shell at seven questions. |
| `cursor/phase3-s3` | 2026-10-07 Assemble Status, Maintenance, and Progress from the existing console  |
| `cursor/phase3-s4` | 2026-10-07 Compose the Data, IB, and Infrastructure shell pages from the existin |
| `cursor/phase3-s5` | 2026-10-07 Answer Releases with versions, runs, and a rollback request. |
| `cursor/rp-platform` | 2026-10-07 Run a tier C release without a manual approval when the Owner's signe |
| `cursor/t2-platform` | 2026-10-07 Send the runner token on the post-deploy tool smoke request. |
| `cursor/w-platform` | 2026-10-07 TD-259: the market-data freshness probe reads /market/coverage/freshn |
| `cursor/w32-platform` | 2026-10-08 Delete the console agent protocol catalog (W-32 LANE-W32). |
| `cursor/w33-platform` | 2026-10-08 W-33 LANE-W33: retire the mini runner and keep patrol on PROD. |
| `cursor/w33b-platform` | 2026-10-09 W-33 LANE-W33BR: reject injected manifest paths and wide image prefix |
| `cursor/w33c-platform` | 2026-10-09 W-33 LANE-W33C review: callers may set only pinned revision params (W |
| `cursor/w33d-platform` | 2026-10-09 W-33 LANE-W33D: read UniFi credentials from the Owner env file. |
| `cursor/w33r-platform` | 2026-10-08 Share patrol state across api and workers. |
| `w31/ci-green` | 2026-10-10 refactor(api): split three files over 800 lines, no behavior change ( |
| `w31/console-int` | 2026-10-10 Merge origin/main into w31/console-int (W-53 firewall baseline, build |
| `w31/guard-2-platform` | 2026-10-12 feat(delivery): the production platform pipeline's source check runs  |
| `w31/guard-3` | 2026-10-12 test(server): the fake production pipeline declares what the real one |
| `w31/guard-5-pin` | 2026-10-12 fix(delivery): after the sync a ref must be seen present; today's cal |
| `w31/guard-6-one-signin` | 2026-10-13 fix(console): saving the same sign-in again reads the role again; a f |
| `w31/platform-next` | 2026-10-10 Merge remote-tracking branch 'origin/w31/w61-approval-page' into w31/ |
| `w31/s0-0-all` | 2026-10-10 Merge origin/w31/w54-fix-console into w31/s0-0-all (W-54, W-57) |
| `w31/s0-0-int` | 2026-10-10 approvals: drop an unused fake-client import so vet passes |
| `w31/td-306-d` | 2026-10-11 fix(notice): a push whose text carries hidden characters is sent as s |
| `w31/td-307-b` | 2026-10-11 test(notice): the differential test asserts its floor and per-class h |
| `w31/td-310` | 2026-10-11 fix(releasepolicy): a freeze is refused when no trust anchor could li |
| `w31/td-310-s1` | 2026-10-12 test(releasefreeze): byte classes over a generated family of chunking |
| `w31/td-316-platform` | 2026-10-12 test(agentthreads): the host-lost message test uses a titled wrapped  |
| `w31/td-317-platform` | 2026-10-12 fix(agentthreads): an ended session stays idle; only a session of the |
| `w31/td-318` | 2026-10-12 test(console): the question-page tests no longer race the clock (TD-3 |
| `w31/td-325-console` | 2026-10-13 test(console): an approved request is read until it is final; a late  |
| `w31/w43a-s0-16a` | 2026-10-10 W-43a S0-16a: delete Console dead code with no importers |
| `w31/w43b-s0-16b` | 2026-10-10 chore(console): W-43b S0-16b delete orphans left by W-44/W-46 |
| `w31/w44-s0-17` | 2026-10-10 feat(console): W-44 S0-17 shell — Needs you home, one verdict, Reco |
| `w31/w45-s0-18` | 2026-10-10 W-45 (S0-18): split Releases into Needs you, In progress, and History |
| `w31/w46-s0-19` | 2026-10-10 console: remove rendered Agent-dispatch leftovers (W-46 S0-19) |
| `w31/w48-s0-0a` | 2026-10-10 approvals: tier D is approved on Console only; chat approval returns  |
| `w31/w49-s0-0b` | 2026-10-10 approvals: pushes carry #n and a summary, every delivery is stored (W |
| `w31/w51-s0-0d` | 2026-10-10 mcp: note that the API also refuses tier D over chat (W-51 S0-0d) |
| `w31/w54-fix` | 2026-10-10 W-54/W-57: wipe expired register keys on an empty flush |
| `w31/w54-fix-console` | 2026-10-10 W-54/W-57: show an hour-old capacity refusal as history |
| `w31/w54-s0-21` | 2026-10-10 W-54 (S0-21): agent thread list is viewer-level |
| `w31/w54-s0-21-console` | 2026-10-10 W-54 (S0-21): read agent threads with the viewer token |
| `w31/w61-approval-page` | 2026-10-10 feat(console): approve rows and request outcomes in plain words (W-61 |
| `w31/w61-needs-you` | 2026-10-10 feat(console): Needs you shows what to run, what to check and what wa |
| `w31/w61-notify-resolve` | 2026-10-10 fix(approvals): a resolved record keeps its place; the MCP gate refus |
| `w31/w62-progress` | 2026-10-10 fix(agentprogress): redact any value under a secret key; links only t |
| `w31/w62-slice2` | 2026-10-11 feat(console): an unknown request shows what is known and its sibling |
| `w31/w62-slice3` | 2026-10-11 fix(console): an action link's fallback label is sanitised and bounde |
| `w31/w65-1a` | 2026-10-11 fix(notice): the redactor hides everything the previous one hid, incl |
| `w31/w65-1b` | 2026-10-11 fix(console): the answer's send lifecycle is kept per question outsid |
| `w31/w65-slice0` | 2026-10-11 refactor(notice): text cleaning and the relay transport in a package  |
| `w31/w66-recorder` | 2026-10-12 test(agentprogress): the redaction bound is checked against the rule  |

## 留着的 43 条

- **23 条 `agent/` 不满 24 小时**（10-19 的尝试，含 M-9 的；脚本的年龄下限）：明天再跑一次会按同一规则判。
- **20 条 `agent/` 不在 main**：10-15 到 10-18 STG 上探针、走查、基准的尝试分支，没有收下的结果要合；按 TD-383 的修法由运行时在 7 天后清理，现在不手删。
- **10 条旧施工分支不在 main**（10-07 到 10-11），逐条看过：
  - `cursor/n-platform`（TD-268）：今天 M-9 合进的 `868d4e8e` 做了同一件事 → 可删；
  - `w31/td-313-gate-proof`：故意失败的门禁证明加它的回退，净改动 0 个文件 → 可删；
  - `w31/td-306-307`、`w31/td-306-b`、`w31/td-306-c`、`w31/w62-slice4`：同一件事后来经 `w31/td-306-d`（`416ac90b`）、`8b3259ae` 合进 main，这几条是中间轮次 → 可删；
  - `w31/td-310-anchor`、`w31/td-312`、`w31/w55-ddl-allowlist`、`cursor/d1-platform`：没找到对应的合并，可能还有没落地的改动 → 先留，逐条对完再说。

## 怎么删

在终端面板跑。脚本跑的时候会按同一规则重新判一次：今天跑删的就是上面 67 条；过了 24 小时再跑，会多出 M-9 那几条已合进 main 的 `agent/` 分支。上面「可删」的 6 条旧分支不在脚本的范围里，另行处理。

```
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/prune-merged-branches.sh --repos bifrost-platform --apply
```
