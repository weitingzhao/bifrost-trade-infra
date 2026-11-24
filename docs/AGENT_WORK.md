# 领活和交活：一条路（Station，2026-11-21）

给任何一个新来的成员：Claude、Codex 或别家 Agent，临时请来的也一样。只靠这页和它指到的东西，就能知道活从哪来、做完交到哪、交的时候带什么。
出处：参谋长给 Station 的第一轮任务书第 2 条；Crew、8.2 沟通台面、1 号计划 11-21 各自答了自己那一段，这页照它们的现状写，不替它们定。
规矩和硬边界不在这页，在根 `CLAUDE.md`（Codex 从 `AGENTS.md` 进去）。

办一件事要带什么（合入、以后还有发布窗口、建卡、发信），办之前查 [`scripts/station/`](../scripts/station/README.md)：`howto.py <工具>` 打印要带什么、缺了去哪拿；`precheck.py <检出目录>` 跑合入时同样的检查，先告诉你会因为什么被拒。要办的事不知道找谁，查能力目录 [`agent-config/CAPABILITIES.md`](../agent-config/CAPABILITIES.md)，或跑 `python3 scripts/station/howto.py find <关键词>`（例：`find 发信`）。

## 1. 活从哪来

**活由一条线的主人席位交给你，形式是一份任务书 `BRIEF.md`。** 没有任务书，你就不是来领活的。

- 主人席位自己挑活、自己请人（Crew 11-21）。各线管什么见 `agent-config/charters/`，谁坐哪个席位见 `agent-config/charters/seats.yaml`。
- 任务书用模板 [`scripts/agent-host/BRIEF.template.md`](../scripts/agent-host/BRIEF.template.md)。开头两行说明谁请的你、交回给谁：
  - `invited_by:` 请你的主人席位 id（`seats.yaml` 的 `id`）
  - `reply_to:` 交回的平台信箱地址，`thread:<那个主人的会话号>`
- Codex 由主人用 [`scripts/agent-host/dispatch.sh`](../scripts/agent-host/dispatch.sh) 起。它先在平台登记这件活（register external work），再让 Codex 读工作目录里的 `BRIEF.md`。登记只是让人看得见，不授予任何执行权限，也不算做完。
- 起之前，`dispatch.sh` 按任务书开头的 `invited_by`、`reply_to` 在工作目录写一张进门卡 `AGENTS.md`（[`codex-card.py`](../scripts/agent-host/codex-card.py)）：谁请的、交回给谁、要问人怎么办、六类不碰。Codex 每一轮都读它，所以开头、上下文被压缩之后、要停下来问人的时候，卡都在面前。任务书开头没写 `reply_to` 的，不起。
- 计划树（平台 `get_plan`、`get_plan_view`）是各线排活的地方，**不是领活的入口**：哪些步算「可接」、怎么认领，1 号计划还没定（11-21）。

## 2. 做的时候

- 你是谁、边界在哪：Claude 会话开头会收到一张身份卡（钩子 `seat-card.py`，Crew 出的卡）。不在席位表里的会话，收到的是进门路。
- 在 Mac mini 上起一个全新的 Codex（不经 dispatch.sh）用 `scripts/station/codex-fresh.sh <工作目录>`：直接 `codex exec` 的话平台 MCP 拿不到会话号，信箱交单会被拒（B6、A9 11-24 撞上）。
- 自己的克隆（A8 进门测试 11-24 缺的两条）：共享检出 `~/Desktop/stocks` 别动，在 `~/agent-work/<活的名字>/` 下自己克隆。从 Gitea 克隆：`git clone http://192.168.10.73:30300/bifrost/<仓库名>.git`（GitHub 只是只读镜像）。克隆完立刻接血缘钩子，否则提交缺 `Change-Id` 等尾注，推到 `ready/` 会被合入流水线拒，而且收不到拒信：`git -C <克隆> config core.hooksPath ~/Desktop/stocks/scripts/git-hooks && git -C <克隆> config bifrost.hooksDir ~/Desktop/stocks/scripts/git-hooks`（frontend、platform 这类自带 husky 的仓库只设 `bifrost.hooksDir`）。提交报 `Author identity unknown` 时，照共享检出里的 `git config user.name / user.email` 配上。
- 平台工具：先调 `whoami` 看自己能做什么。集群写操作、发布、进 main 照根 `CLAUDE.md` §3、§5。
- 卡住要问、要求助：发平台信箱给 `reply_to`。用 `send_message`，kind 填 `ask` 或 `help`。不要写共享笔记里的文件代替发信（8.2 的通道，出处 `agent-config/charters/8-2-comm-desk.md` §2）。
- 收信：`wait_for_messages`，读完 `ack_messages`。等信用门铃 `bifrost-platform/mcp/platform/src/doorbell.ts`。**Codex 已有门铃等信的代码支持**：platform main 的 TD-577（`cc59bf9`）优先读取 `CODEX_THREAD_ID`，再读 Claude、Cursor 的会话号（`mcp/platform/src/sessionId.ts:14–43`）。需运行更新后的本地代码，并让门铃与 MCP 收到同一个 Codex 会话号（`runtimeTools.ts:32–39`、`platformClient.ts:58–61`，均在同一目录）。门铃登记线程后等新信，收到后退出；自动续跑仍需宿主在退出时唤醒 Codex，例如调用 `codex exec resume`，不能把代码支持当成实际唤醒已验收（`doorbell.ts:2–5,90–138`）。实际 Codex 的登记、收信、恢复整条链仍待联测（11-22）。

## 3. 交回

**只有一个去处：请你的那个主人。**

1. 把报告写成工作目录里的 `REPORT.md`，内容照任务书「交单要什么」那一节写。
2. 发平台信箱：`send_message`，`to` 填 `reply_to` 里的地址，kind 填 `handover`。正文一屏以内，写做成了什么、证据（提交号、run 名）、没验什么，并写上 `REPORT.md` 的路径。
3. 经 `dispatch.sh` 起的 Codex，退出时包装器会自动把报告的摘要登记成 submitted。submitted 不等于做完。

不用另外告诉 Crew 你走了：Crew 从平台登记里读到这件活结束，自己在名册上补一笔。

## 4. 还没定的（照现状写，不要当成规矩）

- 谁把 submitted 变成做完、计划步的完成规则怎么绑：1 号计划没定。现在验收归 Audit，计划步的签收只有 Owner 能做。
- 按席位名寄信（`seat:<id>`，换人时没读的信转过去）：8.2 排着，做好之前用 `thread:`。
- 没有任务书、自己开的会话从哪领活：没定。现在先读自己那页章程，找主统筹。
