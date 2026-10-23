# 方案模板（design）

> 第 1 版，2026-10-23（W-31 BI-1 切片 3）。对照平台 bifrost-platform main `c5ad80c2`；下文 `路径:行` 指 `bifrost-platform/api/internal/agentrt/` 下。
> 依据：`DESIGN-crew-intake-2026-10-22.md` §4.3（D 与接单谓词第 4–6 条）、§5.3（卡上只有字母）、§7.1–7.2、§十三（522 A3：D 包括决定表）。
> 公开仓库：下面的例子都是虚构的。真实问题的方案只存在运行时里，不进 git、不进产物。

## 放在哪、怎么算版本

- **谁写、什么时候**：建设负责人（过渡期统筹线程执笔），在需求说明已确认之后（§7.1）。小级不写方案；中级、大级要写（`intake-gates` v1 第 4 条 `design`）。
- **怎么存**：crew 工具 `put_design`（路由 `POST /api/v1/agentrt/issues/{id}/design`；入参 `issue_id`、`expected_version`、`text`、`idempotency_key`，`decisions` 可不给）。
  存成 `issue_text` 的一行，kind `design`，`to_requester = false`：只有问题读者名单里的 crew 令牌和 Owner（Console 只读问题页 `#issue?id=BI-n`）读得到。提出方的 Agent 读不到，卡上也没有。
- **D 是什么**：平台把决定表和正文渲染成一份规范文档再存，D 是这份文档的 sha256（`store/issuedesign.go:84-97`、`:176`、`:200`）。`put_design` 的回答里 `design_sha256` 就是 D。
  照下面的格式写，规范文档就是你交的字节。
- **改一个字就是新的 D**（表或正文都算）：绑旧 D 的复核和 Owner 的决定都不再算数，要重新复核、重新上卡（§4.3）。需求说明换版（新的 B）也一样，证据绑的是 (B, D)。
  正文第一行写上它所依据的 B，需求说明一换版，方案就必须重交，不会出现旧方案配新需求说明。
- **会被拒的时候**：需求说明还没确认（`store/issuedesign.go:190-192`）；问题有在途工作（`:193-195`）；问题已结束或暂缓。
- **复核**：中级、大级交另一家复核（作者是 Claude 就由 Codex 复核，反之亦然），只给它需求说明和方案。报告最后一行以「通过」或「先修」开头，`record_review` 从末行读结论，不由线程填（`store/issuedesign.go:234-254`）。
  轮次从 1 起、每次加一；满两轮还是「先修」，由 `request_owner purpose=review_dispute` 开卡，Owner 选 Proceed / Stop / Another round，只有 Another round 才允许第 3 轮（`:256-264`、`:330-342`；`store/issuetake.go:334-361`）。

## 头部：决定表

方案正文的**第一个字节**就是决定表的第一行：前面不能有标题、空行或 BOM。规则（`store/issuedesign.go:44-51`、`:99-130`）：

1. 第一行逐字是 `Decisions (each point the Owner decides: the options under which the work goes on):`。换行一律 LF。
2. 每个决定点一行：`D<n>: <字母>, <字母>`。列的是**能让工作继续的那几个字母**，不是全部选项。字母按字母序，用「逗号加一个空格」分开，每个只出现一次；决定点按编号升序，D1、D2… 各一次。
3. 没有要 Owner 定的点，表里只写一行 `none`。表不能是空的（空表解析失败）。
4. 表的最后一行后面紧跟一行，只有 `---`。表里不能有空行。正文从 `---` 的下一行开始；正文里再出现 `---` 不影响（只认第一次）。
5. 每个决定点有 2–4 个选项，从 A 起连续编（A、B、C、D）。Owner 的卡只给 A 起的那几个字母（`store/issuecard.go:76-80`）；开卡时 `request_owner` 的 `letters` 就是选项个数，表里能继续的字母必须在这几个之内（`:125-127`、`:175-179`）。
6. 每个字母什么意思，写在正文的「Decisions」一节，和头部一致。卡上只有字母，Owner 在只读问题页对着这一节选。
7. 表里列了点，接单时就要求每个点都有 Owner 本人在当前 (B, D) 上选了能继续的字母，**不论级别**（`store/issuetake.go:227-234`、`:363-377`）。所以只把真正要 Owner 定的点放进表；大级里架构级的点必须列（`intake-gates` v1 第 6 条 `owner_decisions`）。
8. 不另传 `decisions` 参数：表在正文头部就够了。两边都给时必须一致，否则拒（`store/issuedesign.go:162-172`）。

每个决定点，`put_design` 之后由业务参谋 `request_owner purpose=design_decision decision=D<n> letters=<选项个数>` 开一张卡（卡由运行时按模板生成，不收任何文字，§5.3）。

## 模板：有要 Owner 定的点

把下面 text 块里的内容原样复制成 `put_design` 的 `text`，再替换尖括号。头部两行的形状不要改，只改编号和字母。

```text
Decisions (each point the Owner decides: the options under which the work goes on):
D1: A
D2: A, B
---
Design for BI-<n> · product <key> · class <medium|large>
Brief: <64 hex: the sha256 of the confirmed brief this design answers>

## Decisions

### D1 — <the question the Owner answers, one line>
A — <what it means and what happens next>. Lets the work go on.
B — <what it means and what happens next>. Stops here.
Recommended: A, because <one line>.

### D2 — <the question, one line>
A — <...>. Lets the work go on.
B — <...>. Lets the work go on.
C — <...>. Stops here.
Recommended: <letter>, because <one line>.

## Approach
<How the brief's "Done when" is reached, in a few sentences.>

## What changes
- Repositories and files: <...>
- Data: <tables, columns, jobs; "none" if none>
- Interfaces: <routes, tools, pages; "none" if none>

## Risks and limits
- <risk>: <how it is contained>

## Slices
| # | What | Estimate | Needs from the Owner |
|---|---|---|---|
| 1 | <...> | <...> | <...> |

## Verification
- Engineering: <the tasks' verify commands and review>
- Trial for the person served: <environment>, <what to try>, <where>, <what counts as good>

## Out of scope
<As in the brief, plus anything this design leaves for later.>

## Unverified facts
<What this design assumes and has not measured; "none" if none.>
```

## 模板：没有要 Owner 定的点

中级常见：有方案、要复核，但没有架构级的点。

```text
Decisions (each point the Owner decides: the options under which the work goes on):
none
---
Design for BI-<n> · product <key> · class medium
Brief: <64 hex: the sha256 of the confirmed brief this design answers>

## Decisions
None: nothing in this design is the Owner's to decide.

## Approach
<...>

## What changes
- Repositories and files: <...>
- Data: <...>
- Interfaces: <...>

## Risks and limits
- <...>

## Slices
| # | What | Estimate | Needs from the Owner |
|---|---|---|---|
| 1 | <...> | <...> | <...> |

## Verification
- Engineering: <...>
- Trial for the person served: <environment>, <what to try>, <where>, <what counts as good>

## Out of scope
<...>

## Unverified facts
<...>
```

## 例子（虚构）

一条虚构的 Screening 问题：结果表的一列在窄窗口里看不全。头部只有一个点，A 能继续：

```text
Decisions (each point the Owner decides: the options under which the work goes on):
D1: A
---
Design for BI-<n> · product screening · class medium
Brief: <64 hex>

## Decisions

### D1 — where the narrow-window layout lives
A — in the page's own table settings, front end only, undone by one revert. Lets the work go on.
B — in the shared UI library, which changes every table that uses it. Stops here: it needs its own design.
Recommended: A, because it touches one page and is easy to undo.
```

## 正文各节

| 节 | 写什么 | 不写什么 |
|---|---|---|
| 第一、二行 | 问题号、产品、级别；依据的需求说明 B（64 位） | — |
| Decisions | 每个点一小节：一句话的问题；2–4 个选项，各自的意思和后果，标明「Lets the work go on」或「Stops here」，必须和头部一致；推荐和一句理由 | 「以上都不是」之类的开放选项（卡只收字母，§5.3） |
| Approach、What changes | 怎么做到需求说明的「Done when」；改哪些仓库、文件、表、接口、页面 | 她的原话；账户内容 |
| Risks and limits | 风险和怎么收住 | — |
| Slices | 顺序、粗估、每片要 Owner 做什么 | — |
| Verification | 工程验收；给被服务人的试用：环境、试什么、在哪、什么算好（之后照抄进 `reply_to_requester ready_to_try`） | 「她满意」写成工程验收 |
| Out of scope、Unverified facts | 照需求说明的范围外；没实测的假设 | — |

方案里的段落以后要放进执行者的任务书时，先过 `RULES-seat-brief.md` 的清单。
