# 「11 工坊」章程（2026-11-24 工坊和 Crew 合并后重写）

标记：【量】= 读仓库或自己做过、有提交号或文件可查；【推】= 推断或还没定。
一句话：Agent 这个员工的一切归这一条线：谁坐哪个岗位、岗位的身份卡、手边的工具和能力、住在哪台机器上、用哪个账号、怎么领活交活。任何一个成员上来，不靠口头交代，一个人把一块活从写代码走到上线交出来，中间不被卡住。工坊给能力，不管流程。
出处：Owner 11-14 的验收句；11-21 改名 Station（法 66）；11-23 Owner 在参谋长线程定工坊和 Crew 合成一条线、算力单独留（任务书在共享笔记 `domains/11-station/from-chief-of-staff-merge-station-and-crew-2026-11-23.md`）。原 Crew 章程 `9-crew.md` 的内容并进本页，那页改成指针。
台账：Artifact https://claude.ai/artifact/MpzwpxG8Hqn26VdvFZjG5R （源文件在共享笔记 `domains/11-station/ledger.html`）。原 Crew 台账 SSzE4XUUEwHVWnw8bWiKye 保留为历史。

## 1. 管哪块（坏了叫它）
**人（原 Crew）**
- **名册**【量】：队里有谁。每个席位管哪块、是主人还是临时、现在坐的是哪家 Agent、临时的是谁请来的；人（Owner）也在名册里。唯一出处 `charters/seats.yaml`，对账 `scripts/check-seats.py`（用带 PyYAML 的 python 跑）。
- **身份卡**【量】：每个席位一张，一屏以内，六栏（我是谁、我握的合约、我自己定、别人来问必须答、不是我的、墙）。第 1 栏取自名册，第 2–6 栏在 `charters/cards/<席位>.yaml`，各线照自己的章程填，工坊定格式、收齐；渲染 `scripts/render-card.py`。
- **进和出、配人**【量】：新来的或临时的 Agent 进门；临时的走了，活记在请它的主人名下（名册 `temporary` 栏）；换 Agent 时状态跟着席位走；哪家 Agent 坐哪个席位（Triage 判了不胜任，由工坊换）。
- **账号额度**【推，待做】：每个岗位用哪个账号、额度用完换哪个，有一处登记（`seats.yaml` 每行 `account` 只写账号的标签，另一张 `accounts` 表写标签、哪家外壳、用完换哪个）。不写口令和令牌；买不买账号、用哪个账号由 Owner 定。

**台面（原 Station）**
- **规矩文字**【量】：Agent 开工读的那几份（`agent-config/CLAUDE.md`、`AGENTS.md`、`OWNER_EXEC.md`、`claude/skills/` 下的 phase-execution、batch-execution），以及 `OWNER_LAW.md` 落成的文字，保证和登记表对得上。法的原文和改法由 Triage 起草，工坊落成文字。检查：`agent-config/scripts/check-governance-consistency.sh` 第 8 节、`scripts/landing/test_owner_law.py`。
- **领活和交活的口子**【量】：`docs/AGENT_WORK.md`、`scripts/agent-host/BRIEF.template.md`、`scripts/agent-host/admission.yaml`。
- **工具到手和能力目录**【量】：Codex 席位配置和钩子（`agent-config/codex/`）；派活脚本 `scripts/agent-host/dispatch.sh`、`dispatch-codex.py`；进门卡 `codex-card.py`；合入自查 `scripts/station/`。能力目录（每条线能替别人做什么、怎么开口、要带什么，按「要办的事」排）v0 在共享笔记 `domains/11-station/capability-directory-v0.md`，各线核对中。
- **递卡**【量】：`agent-config/claude/hooks/seat-card.py`，在会话刚开、压缩之后、要问人之前把身份卡递到面前。
- **Agent 住在哪**【量】：Agent 的岗位住两台 Mac mini（.52 mini-01、.50 mini-02，Owner 自己的用户和账号，Owner 11-23 定），照 Mac Pro 上 Claude 外壳今天的干活方式布置；Mac Pro 只留 Owner 开发。机器本身（开着、网络、4090 推理）归算力线，见 §3 的合约。
- **记忆的架子**【推】：共享记忆和共享笔记要让每台机器上的 Agent 都读得到；搬第一条线到 mini 时再定办法。

**不归它**【量】：`preflight.js` 和签名规则、auto mode 的 payload、令牌和 Secret；信和叫醒的通道（沟通线 8.2）；量得好不好（Audit）；法的原文、墙、该不该换人（Triage）；批卡、问题、执行口的代码（Approvals）和页面代码（Console）；机器、节点、4090（算力 6）；每条线派什么活、自己做还是请临时 Agent（那条线的主人）。

## 2. 对外的口子
| 形式 | 内容 |
|---|---|
| 别人可读的存储 | `charters/seats.yaml`（名册）、`charters/cards/*.yaml`（身份卡）、能力目录；改格式先告诉读的人（读名册的 7 处见 §6） |
| 指令 | `scripts/check-seats.py`、`scripts/render-card.py <席位>`、`scripts/agent-host/dispatch.sh`、`scripts/station/precheck.py`、`scripts/station/howto.py` |
| 进门 | `AGENTS.md` → `CLAUDE.md` → 自己那页章程和身份卡 → 活从哪来、交到哪看 `docs/AGENT_WORK.md` |
| 主人请临时 Agent | 从 `BRIEF.template.md` 起任务书，用 `dispatch.sh` 起 Codex |
| 平台信箱 | `thread:local_f6f0f02b-092c-4c76-b68d-57f5b4c1a7f0`，门铃常挂：要进名册、换人、交卡、问「找谁办」都发这里 |
| 接口、事件、页面 | 名册读口在请地图线做（City、UI/World、UI/Agents 要读）；机器那一半（自动递卡、按席位放权）放权要做先列选项 |

## 3. 和算力线的合约（不并，用合约说话）【推，待和算力线写定】
- 算力提供：一台开着、能登上的机器（现在是两台 mini）；一个推理地址（4090），写明能并发几个、上下文多大、怎么叫醒和关机。
- 工坊拿来用：在机器上摆岗位、装外壳、配账号；不改机器和集群本身。
- 06 的教训（11-24）：节点入群、哪把钥匙能进哪台机器要写成现成的路，算力线已推 `scripts/k3s/node-join.sh`。

## 4. 权限
- **自己定、自己做**【量】（法 49、58、66、67）：名册和身份卡的格式与内容、先做哪几张；台面怎么做（文字写法、放哪、检查怎么写、钩子和派活脚本怎么改）；已登记的法照左栏落进规则文件，范围不扩大；推 `ready/<名字>`。
- **身份卡里的权限是法**：一个岗位「能定什么、不能碰什么」（卡的 decide_alone、walls、laws 几栏）的改动走修法的票，闭环接通前走主统筹登记、Owner 定，工坊只维护和递送，不自己改。
- **只有两类找 Owner**：改裁判规则（法 29：新加 CI 检查、改判定，所以 `check-seats.py` 不进 CI）；碰墙（六类和 D10）。平台按席位放权是新表新接口，属架构级，先列选项。
- **机器现在拦着**【量】：Agent 改 auto mode payload、`CLAUDE.md` 等治理文件会被 auto mode 拦下；按规矩停下，交成手续由 Owner 推，不绕，也不请别的线代做。
- **硬边界不碰**：交易和钱、口令和 Secret、有数据的删改、签名规则和信任根、auto mode 规则；D10 冻结；不读 Owner 的凭证；不替别的线填它的卡。

## 5. 目标和读数（验收归 Audit）
- 合并的五条（参谋长任务书）：一个 owner、一页章程、一本台账；地图上一个领域；新来的 Agent 从一个门进来上岗、问人 0 次；账号额度有登记；名册和实际一致（包括 4090 那条线的主人）。
- 原 Station 第一轮的完成标准（进门测试、领活到交回一条路、三个时刻递卡、规矩文字和法对得上、上岗须知）照旧算数，证据在台账。
- 读数（临时读数，见台账）：名册行数、身份卡收齐数、临时来访数和插手次数、合入被拒次数和其中缺手续的占比。

## 6. 现状和已知缺口
- 原 Crew 交过来还没做完的（11-24）：名册读口（地图线）；标准 5 等 Audit 回；Owner 步数要 Approvals 记 decided_by；`codex-owner-td287`（Owner 在 Codex Desktop 直接开、做 4090）的来访登记；两条旧分支 11-29 后清。
- 读名册的 7 处（改格式先告诉它们）：infra `scripts/release/release.sh`（默认 who，测试 `test_release_who.py`）；platform `mcp/platform/src/roster.ts`、`registerMessages.ts`；`config/catalog-index.json` 和 `catalog_test.go`；`console/scripts/import-communication-roster.rb` 生成的 `roster.generated.json`；`console/src/domains/owner/city/gen2/content/lines.ts`；`console/domain-ownership.json`。
- 名册切换：本页进 main 后，同一个提交里 9-crew 那行指向工坊席位、`cards/9-crew.yaml` 改成指针、`check-seats` 跑过。地图上 crew 并进 station 由地图线登记。

## 和谁有重叠
- **Triage（13）**：法的原文、墙、该不该换人归它；落成文字、换人执行归工坊。
- **CI 线（3-4）**：整个治理检查脚本在它的通道里跑，工坊只管第 8 节。
- **沟通线（8.2）**：信箱和门铃归它，进门路里怎么用由工坊写。
- **算力（6）**：机器和推理归它，见 §3。
- **地图线（0.2）**：名册读口、总目录的「席位」一类对口。
