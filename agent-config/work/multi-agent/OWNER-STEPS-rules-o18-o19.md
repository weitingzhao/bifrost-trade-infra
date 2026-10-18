# Owner 操作单：规则签名（O18 签名密钥、O19 签 STG 初始规则）

起草 2026-10-14 21:25（统筹线程）。依据：你 20:10 回的「规则 A」；提案 `PROPOSAL-agentrt-rules-2026-10-14.md`；设计 v5 §5.2「规则」、§5.7 O18–O19；规则目录说明 `agent-config/agentrt-rules/README.md`。

**这张单解决什么**：运行时只认你签过的规则。没有规则时一律最严：不派活（`concurrency`）、所有 mission 都等你（`standing-envelope`）。Gate A 的 6 道基准题要 mission 自己成立、任务能派出去，所以要你签 8 份初始规则。

**前提（我这边的，做完会告诉你）**：规则代码合进平台主线并发到 STG（复核 186 在跑；STG 发版等你回「STG 发布」那一题）；STG 上登记了主机 `mbp-dev`（等你回「主机登记」那一题）。

**怎么回**：每一步做完在线程里回一句（写在每步末尾）。

---

## 第 1 步　签名密钥和它的指纹（O18）

发版策略（W-31 S0-8，10-10 起在等）和规则用**同一把**密钥：平台编译进去的是它的指纹（公开的，不是秘密）。私钥只在你的机器上，带口令或 Touch ID。

1. 没有就生成（已有会跳过，不会覆盖）：

```bash
test -f ~/.ssh/bifrost_release_owner || ssh-keygen -t ed25519 -C bifrost-release-owner -f ~/.ssh/bifrost_release_owner
```

2. 看指纹：

```bash
ssh-keygen -lf ~/.ssh/bifrost_release_owner.pub
```

做完回：「指纹 SHA256:……」（把输出里 `SHA256:` 开头那一段贴进线程；它是公开的）。

**之后我做**：把指纹写进 `bifrost-platform/api/internal/releasepolicy/anchor.go`（信任锚变更，不会被自动批准），推主线、发 STG；PROD 那一次随 2.2 的发布单（O20）由你在 Console 上批。

**10-15 已做**：11:26 你回了指纹 `SHA256:pzjcenBSbCbgIoqamoQLsvlxELfp4ikcLbvp164Eel8`；11:27 编进平台主线 `9f1afb5`。12:2x 那把密钥的口令找不回（签第一份时卡在口令），你换了新密钥 `SHA256:HQBmsFUm1mh0JHKwiG/AOJesGSRNNZF+waMq4BI1M7k`，12:26 编进平台主线 `28e63c1`；旧的从没签过任何东西。**新口令存在密码管理器「bifrost 签名密钥口令」**。`allowed_signers` 不建了：没有任何程序读它，平台只认编进去的指纹。

## 第 2 步　签 STG 的 8 份初始规则（O19）

**要等 STG 发完带指纹的版本再签**（我会在线程里说「可以签了」）：脚本先让 STG 读一遍、签完由 STG 验签，STG 上还没有指纹时每份都会被拒。

草稿在 `bifrost-trade-infra/agent-config/agentrt-rules/stg/`，平台的解析器已逐份读通。建议值（签前可改，改了就是你签的版本）：

| 文件 | 内容 |
|---|---|
| `standing-envelope-dev.yaml` | 开发租户；最多到 `branch`；一个 mission 最多 40 次尝试、48 小时；执行者 codex、cursor、deterministic（cursor 10-15 加的）；主机 `mbp-dev`；有效期到 2027-01-15（3 个月） |
| `concurrency.yaml` | 每台主机同时 1 个尝试 |
| `budget-dev.yaml` | 没写预算的 mission 取 40 次 / 48 小时；单次尝试最长 3600 秒 |
| `routing-dev.yaml` | 先能力后额度；池用到 90% 不再派（2.4 才读） |
| `capability-facts.yaml` | 你定过的 4 条：Cursor 不修复核发现；核心代码只由 Claude 写、只由 Codex 只读复核；确定性检查不评审同厂商 |
| `job-implementer.yaml` | 实现岗：codex 正式；cursor 试用（能领活、受观察，10-15 改：Gate A 基准题「Cursor 写、Codex 复核」要它）；claude 资格考试中（不派） |
| `job-verifier.yaml` | 验收岗：deterministic 正式 |
| `job-reviewer.yaml` | 评审岗：codex 正式；claude 资格考试中 |

在你的终端里跑这一条（每份会问一次口令或 Touch ID，共 8 次；脚本先让 STG 只读地读一遍，读不通就不签；输出写进文件，线程里我读）：

```bash
cd ~/Desktop/stocks && for f in capability-facts job-verifier job-implementer job-reviewer concurrency budget-dev routing-dev standing-envelope-dev; do bash bifrost-trade-infra/scripts/agentrt/rule.sh sign bifrost-trade-infra/agent-config/agentrt-rules/stg/$f.yaml || break; done > /tmp/agentrt-rules-sign.txt 2>&1; echo "exit=$?" >> /tmp/agentrt-rules-sign.txt
```

脚本用 STG 的操作员令牌 `PLATFORM_STG_OPERATOR_TOKEN`（环境变量或 `bifrost-trade-infra/.env`）；没有它会在文件里写「missing PLATFORM_STG_OPERATOR_TOKEN」并停下，不会签任何东西。签名文件 `*.yaml.sig` 留在草稿旁边，不进仓库也没关系（公开签名不是秘密，但每次重签都会变）。

做完回：「规则签好了」。我读 `/tmp/agentrt-rules-sign.txt` 核对 8 份都生效，然后删掉这个文件。

---

## 之后

- 规则生效后：Gate A 的 T35（规则集）在 STG 上经接口再跑一遍；6 道基准题的 mission 落在常备授权内自动成立。
- 收紧（降预算、去掉执行者或主机、降级候选）任何人都能做、不用你签；放宽（加执行者、提预算、延期）要你重签新版本。

## 2.3 参谋长回话要的三份规则，和 STG 的规划岗位（10-18）

参谋长回话（2.3 第 4 片）：你在 Console 的 Chief 页或经信箱发给 `seat:chief_of_staff` 的话，控制器把它变成一个 brief 任务，交给 06 上的 Claude（只读），它的答复发回给你。要你签三份：

1. `stg/standing-envelope-dev.yaml` 第 5 版（放宽）：STG 的常备授权加上 `exec:claude`。没有它，STG 上的 brief 任务没人能领，mission 一直等你。
2. `stg/job-chief_of_staff.yaml` 第 1 版：参谋长岗位，候选只有 Claude（试用）。
3. `prod/job-chief_of_staff.yaml` 第 1 版：PROD 同一份。PROD 平台还没有回话的代码，在那之前这条规则不起作用；先签好，PROD 发版时不用再等它。

三份都已用平台自己的解析器在本机读过。每条命令先让平台读一遍，读不通就停、不签；签名要你的签名密钥口令（密码管理器里「bifrost 签名密钥口令」）。逐条跑，前一条成功再跑下一条：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/agentrt-rules/stg/standing-envelope-dev.yaml
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/agentrt-rules/stg/job-chief_of_staff.yaml
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/agentrt-rules/prod/job-chief_of_staff.yaml --env prod
```

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/agentrt/rule.sh sign /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/agentrt-rules/stg/job-planner.yaml
```

第四份（10-18 11:4x 补）：`stg/job-planner.yaml` 第 1 版，和 PROD 的规划岗位逐字相同（只有生效日期不同）。STG 一直没有它，所以 STG 上的目标派不出去；有了它，你在 STG Console 给的目标由 Claude 只读地规划，能在 STG 上看到读文件、搜索的动作流，也能量一次叫停。

跑完不用回，我用 `rule.sh show` 核对四份都生效。
