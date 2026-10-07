# LANE-S1 — Mac mini 上的 Agent 服务鉴权（bifrost-platform `agent/` + `scripts/agent/`）

先读 `cursor-tasks/README.md`（**特别是「第 2 轮」一节：一律只推分支**）。每项的 Claim / Evidence / Fix / Ratchet 见台账 `### TD-n`。报告写到 `cursor-tasks/reports/LANE-S1.md`。分支：`cursor/s1-platform`（起点 platform origin/main）。

| 顺序 | 项 | 要做的 | 注意 |
|---|---|---|---|
| 1 | **TD-206** P1 | git-bridge：非 GET 路由要 bearer 令牌（取 platform-auth.yaml），无令牌时只绑 127.0.0.1；`/commit` 改为显式 `paths[]` + `git add -- <paths>`，空列表拒绝；`/push` 只推当前分支对应的 ref | 记忆 git_bridge_watchdog_restarts.md：git 调用保持异步，别回到 execSync |
| 2 | **TD-207** P1 | remediation runner（:8781）与 Hermes 网关（:8782）：每个非 GET 路由要共享令牌（各 mini 的 .env 里的 runner token），platform-api 的 remediation 客户端带上；绑到非 loopback 且没有令牌时拒绝启动 | 令牌**只读 env 的键名**，不写值、不进仓库；部署脚本里只加「缺键就报错」的检查 |
| 3 | **TD-221**（剩余部分） | 修复执行器的 `ib_gateway_control` 工具去掉 `mode`（不能再把 PROD gateway 切到 mock） | 文字部分 TD-241 已做完 |
| 4 | **TD-96** | 只改草案 `/Users/vision-mac-trader/Desktop/stocks/REQUEST-td96-preflight-d10-2026-10-06/`：按台账 Fix 补 requests/httpx/wget/http(ie) 与 sed -i/tee/cp/kubectl patch 的匹配，并给 agent-guard/test.js 补对应用例草案 | **绝对不要改** `scripts/agent-guard/preflight.js` 本体（由 Owner 应用） |

部署到 Mac mini（.50 / .52）是 Owner 步骤：报告里写清楚每台要加的 .env 键名和重部署命令。
