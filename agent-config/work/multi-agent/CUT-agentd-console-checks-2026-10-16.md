# 切法：agentd 能跑 Console 的检查（W-31 2.2 补强，2026-10-16 晚）

台账：`WORK.md` 第 2 轮 2.2「（补强，10-16 晚提到 2.3 之前）agentd 工作区能跑 Console 的检查」。
定这件事的地方：`WORKMODE-owner-chief-of-staff-2026-10-15.md` 第三节第 3 条。

## 为什么

接下来界面的活多。现在一句目标只能落到 `bifrost-platform`，确定性检查只有 `go -C api build`、`go -C api vet`：
Agent 改了 Console，检查照样过，坏了也看不出来；Codex 在沙箱里没网，`npm ci` 装不了依赖，连测试都跑不了。

## 摸底（10-16 23:2x–23:5x 实测）

- agentd 每次尝试的工作区是 `<root>/tasks/<任务>/a<n>`，是平台仓库在基准提交上的干净克隆（`api/internal/agentd/workspace.go`）。
- Console 依赖 `@bifrost/ui`，写的是 `file:../../bifrost-ui`：从 `console/` 算上去，正好落在 `<root>/tasks/<任务>/bifrost-ui`。
  `bifrost-ui` 的 `prepare` 会在 `npm ci` 时顺带编译出 `dist`。CI 也是这么装的（`Dockerfile.platform-console-stg`：先 `bifrost-ui` 里 `npm ci`，再 Console 里 `npm ci`、构建），`ci-platform` 默认取 `bifrost-ui` 的 `main`。
- agentd 以 `bifrost-agentd` 用户跑（LaunchDaemon），PATH 含 `/opt/homebrew/bin`，node 25 和 npm 都在，能联网；不用另装东西。
- 执行者的沙箱（Codex `workspace-write`）没网；确定性检查由 agentd 自己跑，有网。
- 任务说明由 agentd 的 `ParseSpec` 严格解析（`DisallowUnknownFields`）：新字段要先让 agentd 认得，平台才能发。
- 签过的规则（`standing-envelope:dev` v2 等）不限仓库名，这次不用重签。

## 做法

1. **平台仓库的检查照 CI 来**：`store.Repos["bifrost-platform"]` 的检查从 Go 两条扩成：
   Go build、Go vet，加上 Console 的 `npm --prefix console run lint`、`npm --prefix console test`、`npm --prefix console run build`
   （`build` 里含类型检查）。不另设「选 Console」：选 `bifrost-platform` 就同时覆盖 API 和 Console，和 CI 对每个提交都跑两边一致。
   代价：只改 Go 的任务也要多跑 Console 那几分钟；检查总时限 900 秒够用（本机实测约 4–5 分钟）。
2. **任务说明加两样**：
   - `siblings`：要放在任务目录旁边的仓库和分支（这里是 `bifrost-ui` 的 `main`）。agentd 从拉任务仓库的同一个 Gitea 克隆，每次尝试前更新到分支头，把提交号写进尝试记录。
   - `setup`：执行者开工前、由 agentd 自己在工作区里跑的准备命令（有网，不在沙箱里）：`npm --prefix ../bifrost-ui ci`、`npm --prefix console ci`。
     确定性检查和评审的尝试，用被检查任务的说明里的同一套准备步骤。
   `node_modules` 在 `.gitignore` 里，不会弄脏工作区，也不会进检查点的补丁。
3. **先发 agentd，再发平台**：新 agentd 认得新字段，不带这些字段的任务照旧跑；装好以后平台才开始在说明里带上它们。
   agentd 是 LaunchDaemon，重装要管理员权限，由你在终端里跑一条命令（统筹线程写好，可原样运行）。

## 不做的

- 不给目标表单加「选 Console」：上面第 1 条已经覆盖；以后真有只跑 Console 的需要再加。
- 不把 `bifrost-ui` 钉在某个提交：和 CI 一样取 `main`，提交号写进记录，出了问题能追。
- 旁边仓库和 `node_modules` 的磁盘清理：工作区本来就留着给抢救用，清理策略另记一条（一次尝试约多 300 MB）。

## 验收

- 单元测试：`ParseSpec` 认得两个新字段；准备步骤失败时尝试以「准备失败」结束、带输出尾部；旁边仓库的克隆和更新；检查和评审的尝试也跑准备步骤。
- 改坏版本：去掉准备步骤、去掉旁边仓库、平台不带新字段，各自有测试变红。
- STG 走查：在 Console 提一句只改 Console 的小目标，走到 accepted；检查的 `verify.json` 里能看到 Console 的 lint、test、build 都跑过。
  再提一句故意让 Console 测试失败的（或复用一次失败的尝试）确认检查会退回。
- 复核：Codex 复核，规矩同前（停线规矩、窄确认）。
