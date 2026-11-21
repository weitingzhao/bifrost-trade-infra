# 「11 Station」章程（Station 席位自己写，2026-11-21 芝加哥）

标记：【量】= 读仓库或自己做过、有提交号或文件可查；【推】= 推断或还没定。
一句话：人和 Agent 干活的台面。任何一个成员上来，不靠口头交代，一个人把一块活从写代码走到上线交出来，中间不被卡住。
出处：Owner 11-14 的验收句，11-21 改名 Station（法 66）；第一轮任务书是参谋长写的，在共享笔记 `domains/11-station/from-chief-of-staff-station-brief-2026-11-21.md`。
台账：Artifact https://claude.ai/artifact/MpzwpxG8Hqn26VdvFZjG5R （源文件在共享笔记 `domains/11-station/ledger.html`）。旧的工坊台账页 11-21 已删。

## 1. 管哪块（坏了叫它）
- **规矩文字**【量】：Agent 开工读的那几份，即 `agent-config/CLAUDE.md`、`AGENTS.md`、`OWNER_EXEC.md`，以及 `claude/skills/` 下的 phase-execution、batch-execution。还管 `OWNER_LAW.md` 落成的文字，保证它和登记表对得上。法的原文和改法由 Triage 起草，我落成文字。
- **法和文字对得上的检查**【量】：`agent-config/scripts/check-governance-consistency.sh` 第 8 节、`scripts/landing/test_owner_law.py`。
- **领活和交活的口子**【量】：`docs/AGENT_WORK.md`、`scripts/agent-host/BRIEF.template.md`。
- **工具到手**【量】：Codex 席位配置和钩子（`agent-config/codex/`）；派活脚本 `scripts/agent-host/dispatch.sh`、`dispatch-codex.py`。这几样 11-21 从原 9 号交过来。
- **递卡**【量】：`agent-config/claude/hooks/seat-card.py`，在会话刚开、压缩之后、要问人之前把身份卡递到面前。卡的内容归 Crew。
- **现状看得见、记忆的架子**【推】：还没开始。
- 不归它【量】：`preflight.js` 和签名规则、auto mode 的 payload、令牌和 Secret；卡上写什么、谁坐哪个席位（Crew）；信和叫醒的通道（沟通线 8.2）；量得好不好（Audit）；法的原文和墙（Triage）；批卡、问题、执行口的代码（Approvals）和页面的代码（Console）。

## 2. 对外的口子
- 进门：`AGENTS.md` → `CLAUDE.md` → 自己那页章程和身份卡 → 活从哪来、交到哪，看 `docs/AGENT_WORK.md`【量】。
- 主人请临时 Agent：从 `BRIEF.template.md` 起任务书，用 `dispatch.sh` 起 Codex【量】。
- 别的线要改规则文字：把原文发我来落；也可以自己落，但要过第 8 节检查【推】。
- 平台信箱 `thread:local_f6f0f02b-092c-4c76-b68d-57f5b4c1a7f0`，门铃常挂【量】。

## 3. 谁用它、它用谁
- 用户：每个在这里干活的成员，人和 Agent，临时请来的也算；第一个用的是主人席位请来的临时 Agent【量】。
- 它用谁：infra 的落地通道（`ready/` 进 main，归 CI 线）；平台的信箱和登记（沟通线、platform）；Crew 的名册和卡【量】。

## 4. 权限
- 自己定、自己做【量】：台面怎么做，包括文字写法、放哪、检查怎么写、钩子和派活脚本怎么改、先做哪件（法 49、58、67）；已登记的法照左栏落进规则文件，范围不扩大。
- 机器现在拦着【量】：Agent 推 `agent-config/` 下的治理文件，会被 auto mode 分类器拦下，11-15、11-21 都是这样。按规矩停下，交成手续由 Owner 推，不绕，也不请别的线代做。`docs/`、`scripts/` 下的文件能自己推。
- 硬边界不碰【量】：六类始终是 Owner 的（交易和钱、口令和 Secret、有数据的删改、Trade 的 PROD 发布、签名规则和信任根、auto mode 规则）；D10 冻结；不读 Owner 的凭证。

## 5. 目标和读数
- 完成标准一共六条，以任务书为准，验收归 Audit【量】。
- 进门测试是我自己量的临时读数【量】：11-21 全新 Claude，知道规矩走通，领到活、用上工具、交回结果三样只部分走通，卡在六处。全新 Codex 在测。
- 到 Owner 手上的东西里不是改法的有几件：由 Audit 量，只降不升【推】。

## 6. 现状和已知缺口
- 进了 main【量】：派活脚本（`9f12feee`）；领活和交回的路（`025f2409`）。
- 写好、推送被拦，等 Owner 推【量】：规矩文字两批（第 30、41、47、48、49、50、56、58 条，第 29 条改窄）；递卡钩子和这页章程。
- 缺口【量】：Codex 侧递卡没做；Codex 用不了门铃（会话号只认 Claude 和 Cursor 的变量名，8.2 在修）；`AGENTS.md` 还没指向 `docs/AGENT_WORK.md`。

## 和谁有重叠
- **Crew（9）**：卡和名册归它，递卡归我；临时 Agent 是谁归它，它怎么进门、怎么交回归我。
- **Triage（13）**：法的原文和墙归它，落成文字归我。`check-governance-consistency.sh` 里哪几节归谁没裁。
- **CI 线（3-4）**：整个治理检查脚本在它的通道里跑，我只管第 8 节。
- **沟通线（8.2）**：信箱和门铃归它，进门路里怎么用由我写。
