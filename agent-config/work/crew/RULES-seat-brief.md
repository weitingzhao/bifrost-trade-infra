# 交出去的材料：裁剪规矩（席位、执行者、产物、卡）

> 第 1 版，2026-10-23（W-31 BI-1 切片 3）。对照平台 bifrost-platform main `c5ad80c2`；下文 `路径:行` 指 `bifrost-platform/api/internal/agentrt/` 下，另注明的除外。
> 依据：`DESIGN-crew-intake-2026-10-22.md` §4.4 末条（mission 的标题、目标、任务书是裁剪过的材料）、§5.3（读的边界、Owner 的决策卡）、§十三（落地记录）；
> 平台 crew 工具的说明 `ISSUE_DATA_NOTE`（平台仓库 `mcp/platform/src/issueTools.ts:16-17`）：「A person's words are hers: they stay on the issue routes. Never copy them into a mission, a task, an artifact, a message or a card; a mission's material is what the work needs, written by the crew.」
> 谁守：crew（统筹线程、席位、建设负责人）。这份规矩是约定，平台挡不住 crew 自己往外抄；平台挡的是外面的人读问题（§5.3）。

---

## 一、为什么要裁剪

问题的文字（她的原话、她的 Agent 的理解和提议、需求说明、方案、复核报告、她的回答、席位核对的摘录）全在 `issue_text`，只有问题读者名单里的令牌经 `/agentrt/issues*` 读得到（§5.3）。

下面这些地方，viewer 及以上的令牌和 agentd（执行者）都读得到，有的还会被检索、被 AI 评估、被带进每个席位任务的「运行时现状」：

| 去处 | 谁读得到 | 依据 |
|---|---|---|
| mission 的标题、目标、成功标准 | 有 read 能力的令牌（viewer、reporter、operator、admin、agentd）；在途 mission 的标题和目标还进每个席位任务的 `runtime_now` | `agentrtapi/api.go:96`、`:139`；`store/snapshot.go:129-131` |
| 任务书（`propose_tasks` 的 spec 产物） | 同上；执行者照它干活 | `agentrtapi/api.go:136-137` |
| 任何产物（`put_artifact`） | 同上，可按正文检索；同样的字节只存一份，元数据留第一次的 | `agentrtapi/api.go:136-137`；`store/write.go:52-56` |
| 发给席位的消息（`send_message` 给 `seat:chief_of_staff`） | 正文是产物；正文整段成为那个 brief mission 的目标，首行成为它的标题和任务标题 | `store/brief.go:149-150`、`:181` |
| 卡（决策卡、问题卡） | viewer 及以上读卡片库；开着的卡进 AI 评估 | `../questions/handler.go:21-25`；§5.3 |
| 公开仓库（提交说明、台账、WORK.md、LESSONS、记忆、报告、测试夹具） | 任何人 | 12 个仓库全部公开 |

所以凡是从问题拿到这些地方去的东西，都是 crew 重写过的**裁剪材料**。

## 二、能放什么、不能放什么

**能放**：

- 问题号 `BI-n`；需求说明的 B、方案的 D（sha256 全长，或前 12 位）；产品键；类别和级别。
- 页面和功能（例如 `Research › Stock screen` 的哪一块）；现象（crew 自己的话：看到什么、预期什么）；日期；环境；提交号；mission、任务、卡的编号。
- crew 自己实测的证据：命令、接口返回的形状、日志行，不含账户内容。
- 产品档案里公开的条文（方法线、已知限制），照抄并注明出处。
- 按 `TEMPLATE-brief.md` 写的当前需求说明全文，以及按 `TEMPLATE-design.md` 写的方案里相关的段落：先过第四节的清单（模板本来就不许引原话、写名字、写账户内容）。
- 她的回答的结论（verdict）和 crew 对它的中性描述，见第三节「席位核对」。

**不能放**：

- **她的原话**：任何长度、任何语言；翻译、几乎逐字的转述也不行。
- **外部 Agent 的理解、提议、备注的原文**：里面常带她的话或她生活里的事。和工程有关的部分，用 crew 自己的话重述。
- **人名、显示名、`person:` 编号**。要说为谁，写角色（「这个页面的使用者」）。
- **账户内容**：持仓、成交、数量、金额、价格、盈亏、余额。说哪个页面、什么现象。
- **令牌、口令、截图、本机路径**（`other` 类产物会扫本机路径，`store/localpath.go`）。
- **复核报告全文**、方案全文里和这件工作无关的部分：写结论、轮次和用得上的段落。
- **业务结论当成功标准**：mission 的成功标准只写工程（任务验收通过、某接口返回某形状），不写「她满意」「她确认」（3.2-1 第 3 步）。

## 三、按去处

| 去处 | 写什么 | 注意 |
|---|---|---|
| **席位分级**（`send_message` 给 `seat:chief_of_staff`，kind `ask`，正文 ≤ 8 KiB，`store/messages.go:15`） | 首行：`BI-n classification: <页面>: <现象>`；问题号和 B；当前需求说明（过清单）；建设负责人的实测证据；产品档案相关条文（Screening 是第五节 S1 那条线和第七节相关条）；要它答：类别（guidance / improvement / method_change / data_not_shown / fault / out_of_scope）、级别（small / medium / large）和理由、有没有已有能力 | 首行会成为 mission 和任务的标题。席位的答复是那个 brief 任务的报告，`classify_issue` 的 `seat_report` 就填它的 artifact id（库里核对必须是 brief 任务的报告，`migrations/0009_issues.sql:818-820`）。答复本身也是产物，所以它也不该引原话；它本来就看不到 |
| **席位核对**（结案前；同样经 `send_message`） | 首行：`BI-n close check: ask <ask_id>`；那一问的用途、环境、提交；她的结论（verdict）；crew 用自己的话概括她的回答里关于页面和现象的那部分，不逐句转述（虚构的例：「对试用那一问答 confirmed；说那一列在窄窗口里能读全了；没提别的问题」）；当前需求说明的 Done when；要它答：这份记录能不能支持结论 resolved / partial | 原话的摘录写进 `record_close_check` 的 `excerpt`：它存在 `issue_text`，只有 crew 读得到（`store/issueevidence.go:157-170`）。不写进消息 |
| **mission**（`take_issue` 的 mission 定义） | 标题 `BI-n: <工程上要做的事>`；目标：改什么、在哪、为什么（问题号、B 前 12 位、页面和现象）、交付到哪；成功标准：工程验收；repos、max_action、预算 | 承诺正文（`commitment`）存在 `issue_text`（kind `note`），只有 crew 读，可以写得更细，但同样不引原话（`store/issuetake.go:140`） |
| **执行者任务书**（`propose_tasks` 的 spec） | 要改的仓库、文件、接口；方案里相关段落（过清单）；验收命令；问题号和 D 前 12 位 | 执行者要更多，就回到 crew 来要；不给执行者任何能读问题路由的令牌 |
| **产物**（`put_artifact`） | 不放问题的任何文字 | 问题的文字永远不以产物上传（§5.3：按正文哈希去重，一旦上传就藏不回去） |
| **Owner 的决策卡** | 不写：`request_owner` 只收问题号、用途、版本和字母个数，卡由运行时按固定模板生成（`store/issuecard.go:60-98`、`:104-113`） | 不用 `ask_owner` 问业务问题的任何事：线程问到的回答不增加授权（W-65），卡片库对 viewer 开放、进 AI 评估。卡上答不了的（例如谢绝的理由），在统筹线程里说 |
| **给 Owner 的消息、计划备注** | 问题号、状态、在等谁、下一步 | 正文都是产物，同上 |
| **公开仓库** | 问题号、哈希、状态、crew 的工程描述 | 不写原话、名字、`person:` 编号、账户内容；测试夹具用明显虚构的句子 |

给提出方的回音（`reply_to_requester`）不在这张表里：它存在 `issue_text`，标了 `to_requester`，只有她的 Agent 和 crew 读得到。但它会经她的 Agent 送到外部 AI 厂商那里，所以同样不写账户内容、令牌、口令（§十二 第 3 条）。

## 四、交出去之前的清单

每次把材料放进上面任何一处之前，逐条过一遍：

1. **原话**：对照 `get_issue_full` 的 `texts`（kind `words`、`response`、`reading`、`proposal`、`note`），材料里没有一句是从那里搬来的，换个说法也不行。
2. **引号**：材料里每一处引号、引用块，都是 crew 自己的话或产品档案的原文。
3. **人**：没有人名、显示名、`person:` 编号。
4. **账户**：没有持仓、成交、数量、金额、价格、盈亏、余额。
5. **秘密**：没有令牌、口令、截图、本机路径。
6. **版本**：写了问题号和 B（或 D）的前 12 位，读的人能对上是哪一版。
7. **成功标准**：mission 和任务的成功标准只写工程。
8. **卡**：没有自己写的字；没有用 `ask_owner` 问业务问题的事。
9. **首行**：发给席位的消息，首行是中性标题（问题号、用途、页面、现象），因为它会成为 mission 和任务的标题。

有一条过不去，就改到过得去再交；拿不准就不放，在统筹线程里问。

## 五、和设计的不同

`DESIGN-crew-intake` §5.3 和 §7.3 当时写的是，席位分级的任务书里放「当前需求说明和线程选的几句原话」。落地的 crew 工具说明（`ISSUE_DATA_NOTE`，平台仓库 `mcp/platform/src/issueTools.ts:16-17`）收紧为原话一律不出问题路由，本规矩按落地的写。
代价：席位分级、席位核对看到的是 crew 的描述，不是她的原话，核对的质量取决于描述是否如实。补偿：需求说明是她本人确认过的那一版；核对时的原话摘录记在 `record_close_check` 的 `excerpt` 里（crew 经 `get_issue_full` 读）；Owner 在 Console 只读问题页看得到她的原话和每一问的回答（平台仓库 `console/src/pages/IssuePage.tsx:128-134`、`:196-202`），能对照 crew 的描述。
