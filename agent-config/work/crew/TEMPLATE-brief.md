# 需求说明模板（brief）

> 第 1 版，2026-10-23（W-31 BI-1 切片 3）。对照平台 bifrost-platform main `c5ad80c2`；下文 `路径:行` 指 `bifrost-platform/api/internal/agentrt/` 下。
> 依据：`DESIGN-crew-intake-2026-10-22.md` §7.1（需求说明和方案分开，需求说明只由提出人确认）、§4.3（B 与「作废」）。
> 公开仓库：下面的例子是虚构的。真实问题的需求说明只存在运行时里，不进 git、不进产物。

## 放在哪、谁确认、怎么算版本

- **谁写**：业务参谋（过渡期统筹线程执笔），读完问题里被服务人的原话和她的 Agent 的理解之后，用自己的话写。
- **怎么存**：crew 工具 `draft_brief`（路由 `POST /api/v1/agentrt/issues/{id}/brief`；入参 `issue_id`、`expected_version`、`text`、`idempotency_key`）。
  存成 `issue_text` 的一行，kind `brief`，`to_requester = true`；同一事务里作废所有开着的问，开一问新的 `confirm_brief`，绑这一版（`store/issuebrief.go:28-81`）。
- **谁看、谁确认**：被服务人经她的 Agent 读到全文（`get_updates` 的 `confirm_brief` 那条，`get_issue` 的 `open_ask.text`），她答「是这样」或「不是」，由 Agent 逐字转述（`relay_user_response`）。
  Agent 自己的提议没有被服务人：由 Owner 在决策卡上确认（`request_owner purpose=confirm_brief`），全文在 Console 只读问题页。AI 的意见、Agent 的判断都不算确认（§7.1）。
- **B 是什么**：这段文字逐字节的 sha256（`store/issues.go` 的 `textSHA`，`store/issuebrief.go:64`）。平台不做任何规范化：多一个空格就是另一个 B。
- **改一个字就是新的一版**：所有开着的问作废，要她重新确认；分类、优先级、复核、Owner 的决定都绑在 B 上，换版后都不再算数，要重新走（§4.3「作废」）。
  有在途工作、或开着试用（`ready_to_try`）或答疑（`check_answer`）的问时，`draft_brief` 被拒：交付过程中不原地换范围（`store/issuebrief.go:47-52`）。

## 写法

- **短**：整份通常 6–12 行。她要能一口气读完、用「是 / 不是」回答。一份只写一个问题；说的是两件事，就拆成两条问题。
- **用她的语言写**：她平时和她的 Agent 用什么语言，正文就用什么语言。下面的栏目名保持英文，席位和工具按栏目名找段落。
- **用自己的话，不引原话**：她的原话已经在问题里，有自己的位置。需求说明里不引号引用、不整句照搬，也不用几乎逐字的转述。
  这样它才能在需要时放进席位的任务书（`RULES-seat-brief.md`）。
- **For 写角色，不写名字**：例如「这个页面的使用者」。不写人名、显示名或 `person:` 编号。
- **不写账户内容**：持仓、成交、金额、盈亏都不写。写「哪个页面、什么现象、什么时候」。
- **Done when 写她能看到的**：在哪个页面、看到什么或能做到什么，就说明解决了。不写工程验收（那在方案和 mission 里），也不写「她满意」。
- **范围外要写**：她可能以为包含、其实不做的，写进 Out of scope。改选股方法这类要 Owner 定的事，写进 Constraints（「这一条不改方法；要改方法另提」），不在需求说明里替 Owner 答应。

## 模板（复制 text 块）

把下面 text 块里的内容复制成 `draft_brief` 的 `text`，替换尖括号。没有内容的可选栏写 `none`。

```text
For: <who this is for, by role; no name>
Problem: <what goes wrong or is missing, on which page or feature; one to three sentences in your own words>
Done when: <what the person will see or be able to do, and where, that tells them it is solved>
In scope: <what this covers>
Out of scope: <what it does not cover, especially what they might expect it to>
Constraints: <limits that hold, for example "no change to how scores are computed"; or none>
Open questions: <what is still unknown and who answers it; or none>
```

## 例子（虚构）

```text
For: the person who screens stocks on the Stock screen page
Problem: On a narrow browser window, the last column of the results table is cut off, so its values cannot be read without widening the window.
Done when: On the same narrow window, every column of the results table can be read, by scrolling sideways if needed, with the header staying in line with its column.
In scope: the results table on the Stock screen page.
Out of scope: other tables; which columns are shown; how the results are ranked.
Constraints: no change to the screening method; tried first on the test site.
Open questions: none
```

## 交出去之前

1. 对照问题里她的原话（`get_issue_full` 的 texts）：没有一句被搬进来。
2. 没有名字、账户内容、令牌、截图、本机路径。
3. Done when 能让她在页面上自己判断，用「是 / 不是」回答。
4. 范围外写了她可能以为包含的东西。
5. 用 `get_issue_full` 读到的 `version` 作 `expected_version`；一个写一个幂等键，重试同一个写才复用。
