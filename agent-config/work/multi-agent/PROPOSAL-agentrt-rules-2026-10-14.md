# 运行时规则的正文怎么写（要你定，Gate A 前）

**为什么现在要定**：设计 v5 规定规则一律从签名正文 `body_text` 解析执行、解析器闭合（不认识的字段就拒），但没写正文长什么样。这是你亲手签名的东西，属于新的公开格式，按规矩交你定。它挡着三件事：mission 落在常备授权内才能自动成立（6 道基准题要用）；你签初始规则（O19）；规则路由（提议、签名、收紧，T35）。

**怎么回**：线程里回「规则 A」（或 B、C），对下面第 2 节的字段有改动就直接写。

---

## 1. 正文的格式

| 选项 | 是什么 | 好处 | 代价 |
|---|---|---|---|
| **A（建议）** | YAML，和你现在签的发版策略同一种写法；签名用 `ssh-keygen -Y sign`，namespace `bifrost-agentrt-rule`（和发版策略的两个 namespace 分开，拿发版签名来这里无效） | 你签过发版策略，读写方式一样；平台已有同一套验签和信任锚，复用 | YAML 有歧义写法（比如 `no` 当布尔），解析器要严格：只认列出的字段、类型写死、不认锚点和合并键 |
| B | 规范 JSON（和事件哈希用的同一个编码器） | 没有歧义，机器比较最直接 | 人读、人改都费劲，你签之前不容易看清 |
| C | 每行一个 `键: 值` 的纯文本 | 最简单 | 嵌套的东西（候选名单、预算）写不下，要另造规矩 |

签名覆盖的头部五项（`rule_id`、`rule_version`、`direction`、`effective_at`、`expires_at`）写在正文里，验签后解析出来和数据库列比，不等就拒（设计 v5 已定）。`body_json` 由解析结果生成，不能由调用方填。

## 2. 各类规则写什么（按选项 A 的写法）

都以头部五项开始，下面只列各类自己的部分。没有某类规则、规则过期、或解析失败时，按右栏的「最严默认」执行。

| 规则 | 正文写什么 | 平台怎么用 | 最严默认 |
|---|---|---|---|
| `standing-envelope:dev` 常备授权 | `tenant: dev`；`max_action: branch`（只许 none / branch，C 级动作永远不在里面）；`budget: {max_attempts, max_wall_hours}`（一个 mission 的上限）；`executors: [...]`、`hosts: [...]`（已登记的才算） | 提议 mission 时比对：全部落在里面就自动 `active`，在 ⑦ 通知你；任一超出（业务租户、C 级、预算超、新执行者或主机）就停在 `awaiting_owner` 并生成一张决策卡（`owner_duty: goal`） | 没有这条规则：所有 mission 都要你批 |
| `concurrency` 并发 | `per_host: 1`（第 2 轮固定 1） | 领活时每台主机最多几个活着的尝试 | 0（不派活） |
| `budget:dev` 预算 | 默认的 mission 预算 `{max_attempts, max_wall_hours}`；单次尝试的硬时限 `attempt_hard_limit_s` | 提议 mission 没写预算时取这个；T10 用完就不再派 | 0（不派活） |
| `job:<岗位>` 岗位说明书 | `tenant`；`text`（说明书正文，给执行者看的）；`candidates: [{executor, provider, model_pattern, status}]` | 签名时写 `job`、`job_candidate` 行；分流只在这些候选里挑 | 没有候选：这个岗位的任务没人能领 |
| `capability-facts` 能力事实 | `facts: [{executor, provider, kind: cannot/must_not/only/prefer, subject, scope}]`，`source: owner` | 签名时写 `capability_fact` 行；分流排除和偏好 | 没有事实：不额外排除 |
| `routing:dev` 分流 | 选择顺序（先能力后额度，设计 v5 已定）和额度阈值（池用到多少就不再派） | 分流读它 | 额度未知的池不派 |

**收紧怎么判断**（不带签名也能立即生效，设计 v5 已定；判不出是收紧就按放宽处理、要签名）：常备授权和预算只降不升，执行者和主机名单只减不增；并发只降；候选只能从 `active` 降到 `probation` / `demoted` / `retired`，不能新增或升级；能力事实只能加 `cannot` / `must_not`，不能删；有效期只缩不延。

## 3. 你怎么签

和发版策略一样，在你自己的终端：

```bash
bifrost-trade-infra/scripts/agentrt/rule.sh sign standing-envelope-dev.yaml
```

脚本做三件事：本地严格解析一遍（解析不过就不签）；`ssh-keygen -Y sign -n bifrost-agentrt-rule`；把正文和签名交给 `POST /api/v1/agentrt/rules/{rule_id}/sign`。平台验签、解析、比头部、生成 `body_json`、写 `rule_signed` 事件和对应的表行，一个事务。脚本和初始规则的草稿在你回了格式之后由我写好；初始规则的数值（预算多少、候选哪些）草稿里给出建议值，你签前可改。

## 4. 我没定、你回格式时顺带定的

- 常备授权里的预算上限：建议一个 mission 40 次尝试、48 小时墙钟（6 道基准题每题大约 4 次尝试：实现、确定性验收、评审，再留一次返工）。
- `standing-envelope` 的有效期：建议 3 个月，到期前 7 天在 ⑦ 提醒（和发版策略的到期提醒同一套）。
