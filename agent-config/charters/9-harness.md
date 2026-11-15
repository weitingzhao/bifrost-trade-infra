# 领域 9「Harness 接入」章程（9.1 Agent 能力线，2026-11-15）

标记：【量】= 我读到、量到的；【推】= 推断。

## 1. 管哪块
- **把别家 Agent（现在是 Codex，将来本地开源模型）接到我们的工作台，让它一个人从写代码走到上线。**
- 文件【量】：
  - 席位配置与钩子：infra `agent-config/codex/`（`README.md`；`bifrost-seat.config.toml`、`hooks.json` 的副本在共享笔记 `agent-parity/seat-config/`，已装在 `~/.codex/`）。
  - 派活包装器：infra `scripts/agent-host/dispatch-codex.py`（登记、心跳）；入口脚本 `~/agent-work/dispatch.sh` **在仓库外、只在本机**。
  - 对比与验收材料：共享笔记 `agent-parity/`（first-page、u01、seat-compute 的每轮题和报告、run-log）。
  - 席位台账：Artifact C342dhHB3NkJSXxdco5eFg（源文件 `agent-parity/ledger/index.html`）。
- 不归我：守卫脚本 `preflight.js` 本身（治理层/工坊）、平台登记和心跳的代码（领域 2）、Codex 在各线上做的活（归各线）。

## 2. 对外的口子
- 要让 Codex 做一件事：写 `BRIEF.md`（目标、边界、交单要什么）→ `RUN_KEY=<key> ~/agent-work/dispatch.sh <目录> <节点> "<任务>" none none -p bifrost-seat`【量，已跑 8 次】。
- 要让别的 Agent 接进来：读 `agent-config/codex/README.md` 和上面两份配置，照做（给能力不给步骤）【推：本地模型那条还没试】。
- Codex 与 Claude 会话互发消息：走平台 `send_message` / `wait_for_messages`【量，11-14 22:36 通】。

## 3. 谁用它，它用谁
- 用户：主统筹、值班统筹（要 Codex 接活的人）；Codex 算力席位（现在唯一用户）。
- 它用：平台登记/心跳/MCP（领域 2、platform）；`ready/` 合入链与发布窗口（CI 线/Ops）；守卫 `preflight.js`；Codex CLI 本身（版本 0.167.0-alpha.3.2）。

## 4. 权限
- 自己定自己做：写席位配置草稿、出题、读回验收、记三个数、改本席位台账和共享笔记。
- 机器现在拦着【量】：我改 CLAUDE.md、推 `ready/`、跑登记命令都被 auto mode 分类器拦过，要用户点头才过；Codex 过不了分类器，由 `preflight.js` 守，且钩子失败时放行（fail-open）【量，见 first-page】。
- 硬边界不碰：不做 Codex 的活、不给它步骤；不动 `~/.codex/config.toml` 全局、认证、`~/.config/bifrost/`；Trade、IB、Finance、数据库、D10；不自己建审批卡（交值班攒批，Owner 11-14 夜新规矩）。

## 5. 目标和读数
- 目标：任何一家 Agent 都能独立把一件整活从代码做到线上，不被卡住。
- 现在的读数【量】：每一块记三个数——**中途停几次、要人插手几次、token**。U01：0 / 0 / 107,610；第 1–6 轮见 `agent-parity/seat-compute/run-log.md`（第 6 轮 0 / 0 / 115,322）。基线是 11-14 下午 Claude 写步骤版：5 轮全停、每轮都改说明。
- 还没有、该有的数：**同一类活 Claude 与 Codex 的完整耗时对比**（现在只有两个孤立样本）；**没有门卡被拦的次数**（Codex 侧由钩子日志可算，【推】）。

## 6. 现状和已知缺口
- 做成了【量】：席位配置装好并被真跑证实；Codex 一个人推 `ready/`、等落地、占窗口、同步、读回；转录尾注已修；平台注册完成；6 轮算力工作交付。
- 缺口：
  - `dispatch.sh` 在仓库外，换机器就没了【量】；
  - `codex exec resume` 不能带席位配置，没法续接，一直走全新派活【量】；
  - 心跳在 Console 上是否可见没核；
  - 守卫 fail-open 与 Claude 侧分类器的不对称还在，只靠 preflight 一道【量】；
  - 本地开源模型（`--oss`）没试，**【推】先要一件小活当考题**；
  - Codex 报告容易过长（第 6 轮 173KB），出题时我要限篇幅。

## 主统筹裁定（11-15，duty/charter-overlaps-rulings）和我有关的两条
- **#17 Codex 经不经过 preflight：我核了现状——经过。**【量】Codex 每次 shell 调用和改文件都先过 `codex-pretooluse.js`，再转给同一份 `preflight.js`；三轮日志里钩子调用 U01 236 次、r5 179 次、r6 217 次（`dispatch-*.log` 里 pretooluse 的行数）。没有的是 Claude 那道 auto mode 分类器，Codex 不经过；钩子失败时放行（fail-open），哈希未 trust 的钩子会被静默跳过（`agent-config/codex/README.md:104`）。所以结论：**同一道硬边界，少一道分类器，且钩子本身没有「坏了就停」**。没量过的：钩子失败/超时那条路真被走到过几次。
- **#13 席位配置和钩子放 `agent-config/`**：归工坊收进去；我出「别家 Agent 需要的差异」——Codex 已有（`codex/README.md`）；本地开源模型那份还没有，等考题后补。
- 等信协议归 8.2、Codex 机器上怎么常驻归算力线：不归我，已去掉我这页上的相关表述。

## 和谁有重叠（裁后剩下的）
- **领域 2（登记与血缘）**：Codex 线程在 Console 上可见与否，登记/心跳代码归它，我只用；这一项仍没人核【推】。
- **工坊**：它管工作台本身，我管别家 Agent 接得进；配置文件归它收，差异归我。
- **算力线（6）**：Codex 做它的活，我出题、验收、记三个数；章程由 Codex 写、我收。
- **CI 线 / 值班**：`ready/` 合入链、攒批卡归它们，我是用户不是维护者。
