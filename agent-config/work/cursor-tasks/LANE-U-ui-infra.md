# LANE-U — @bifrost/ui 构建与版本、Redis 清单（3 项）

先读 `cursor-tasks/README.md`。报告写到 `cursor-tasks/reports/LANE-U.md`。按下面顺序做（TD-235 最小、最独立）。

| 项 | 仓库 · 分支 | 一句话 | 注意 |
|---|---|---|---|
| TD-235 | bifrost-ui · `cursor/td-ui-build`（起点 origin/main） | `build` 先 `rm -rf dist`（`prepare` 每次 npm install 都跑），两个 dev server 白屏，tsc 失败就一直白 | 建到 `dist.tmp`，成功才原子 `mv`；防线：一个脚本测试，tsc 失败时旧 dist 仍在 |
| TD-234 | bifrost-trade-infra + bifrost-platform · `cursor/td-ui-pin`（infra 起点 origin/main，platform 起点 origin/td-l6） | Ops Console 用的 @bifrost/ui 没有版本：ui 推送不跑 platform CI，deliver 构建任意 ui main 且不记录 SHA | Tekton 清单改动只推分支（Argo 会同步 main）。PROD 照「STG 钉给 PROD」的模式从 STG run 的 clone-ui 提交钉 uiRevision |
| TD-238 | bifrost-trade-infra · `cursor/td-redis`（起点 origin/main） | 三个环境的 Redis 开着 `--appendonly yes` 却没有卷；noeviction 但无 maxmemory，唯一上限是 OOMKill | 按台账 Fix 的第一种（声明为易失：去 appendonly、`--save ""`、maxmemory 略低于容器上限）。**只推分支**——上线会重启三套 Redis（含 PROD），由 Owner 批 |

不起任何 PipelineRun，不 `kubectl apply`。
