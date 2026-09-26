# DESIGN_CONTRACTS.md — 三域设计契约

> **CANONICAL** — 本文件是正本（工作区根 `/stocks`）。`design/trade/DESIGN_CONTRACTS.md` 是随设计包导出的镜像；两份不一致时，以更新日期新的为准并立即覆盖旧的（P1=A，2026-09-15）。本版 2026-09-23 由 Claude Code 按 P1=A 从镜像同步：正本停在 2026-09-16、镜像已到 2026-09-22，补回 **§14.6 密集表列宽** 与 **§14.7 方向色回归绿/红**（app 侧早已按 §14.7 施工），并新增 **§15 业务价值高于视觉**（Owner 2026-09-12 裁定升格入契约）。2026-09-23 晚再次同步：Package 2026-09-23.6 的镜像已收回 §15，并新增 **§14.8 身份色棘轮** 与 **§16 页面精修原则**——两份此刻逐字一致。 2026-09-23 夜第三次同步：Package 2026-09-23.8（Rev .29）回 app 侧 ASK，§14.4 实体色表按 §14.8 归一（第 3、6 条改写，§5/§8 身份色枚举补 token 名）——正文与镜像逐字一致，镜像页首这一行仍是旧说明。 2026-09-26：新增 **§15.6–15.9 业务优先**（Owner 裁定：有数据就要放 · 先交付强的 · 缺数据先分权限还是 Bug · 取舍总原则），目前只在正本、尚未回流镜像。同日第四次同步（Owner 放行）：镜像 Rev .74（2026-09-25）的 §17 交互模式标准、§16.10–16.14 与 §8/§14.7 token 落地改写已收进正本，正文除 §15.6–15.9 外与镜像逐字一致。

放置位置:**读取路径不变** —— 工作区根 `/stocks/DESIGN_CONTRACTS.md`(与 `AGENT_FACTS.md` 平级)。三个 Design 项目(Ops / OLTP / OLAP)都挂载此目录,每次开会话先读本文件。

> **2026-09-23 起,根上那一份是符号链接**,实体在 `bifrost-trade-infra/agent-config/DESIGN_CONTRACTS.md`(与 `CLAUDE.md` / `AGENT_FACTS.md` 同一治理层,纳入 infra 版本控制与 CI)。此前正本裸放在工作区根,而根不是 git repo —— 代价是 §14.6 / §14.7 在正本里丢了一周没人发现。链接重建命令见 `bifrost-trade-infra/agent-config/README.md`。

本文件**只写跨域的东西**。各域内部的布局决策、候选方案取舍、待建屏顺序留在各自的 `*-handoff.md`,不上升到这里。

事实来源:`bifrost-trade-frontend`(完成度最高,已成立的词表与路由以它为准)、`bifrost-ui`(共享 token)、`bifrost-research/CLAUDE.md`(三域定位)。

---

## 0. 域的切分(一句话各一条)

| 域 | Design 项目 | 负责 | 不负责 |
|---|---|---|---|
| Ops(控制面) | Ops: Platform 优化 | 数据质量的**判定与处置**:freshness / completeness / schema / distribution 四维,重跑、回补、暂停下游 | 不做挖掘、不做回测 |
| OLTP(执行) | OLTP: Trade 优化 | 订单、持仓、实时盈亏、风控闸门;贴着交易动作的浅探索 | 不做全表扫描、不做夜批 |
| OLAP(研究) | OLAP: Research 优化 | 队列式决策流、深挖掘、特征库、回测、预测 | 不判定数据质量(只渲染 Ops 的判定);不触交易执行(D10) |

计算只在一边:marts / features / engines 全在 Research 域。**UI 在哪不改变计算归属** —— `bifrost-trade-frontend` 的 Research 区消费 Research API `:8795`,它是 OLAP 的消费面,不是 OLTP 抢活。

> 域切分回答「计算与数据归谁」。它**不**回答「界面长什么样」——那条轴见 §11。

---

## 1. 视觉词表分配(禁止交叉)

**严重度色 — 四态 lamp。** 来自 `bifrost-ui/src/styles/bifrost-ui.css`:

```
--color-lamp-green  #16a34a
--color-lamp-yellow #ca8a04
--color-lamp-red    #dc2626
--color-lamp-gray   #64748b
```

**暗 / 亮同值**(2026-09-25 裁定,回 app 侧 Q4):lamp 四色两个主题都取上表的包值;Trade 暗色遗留的 `#facc15` / `#94a3b8` 作废。

铁律(来自 `lampTone.ts`,已在 Trade 落地):**无读数是灰,永远不是红。** 刻意的安全姿态(如 D10 下 daemon 不运行)必须是灰,红只留给真实故障。灰色 lamp 不发光。

**方向色 — 全域一致(2026-09-12 修订,见 §11.9)。**

```
--color-profit      green  #4ade80   盈利 / 上涨
--color-loss        red    #f87171   亏损 / 下跌
--color-unrealized  orange #fb923c   未实现,整列,不分正负
(2026-09-16 §14.7 更正:teal/orange 退役,方向色回归行业绿/红)
```

只给**有符号数字**:P&L、涨跌、Θ、净额、delta、OOS 收益、有符号柱。不给标签、边框、背景,也不表示买卖方向。

**红色的两个用法按形态与色值分开**(§14.7 第 2 条):方向红 `#f87171` 只落在带符号的 mono 数字上;严重度红 lamp-red `#dc2626` 只落在圆点 / tag 上,两者不共用载体。(2026-09-25 更正:此处原写「红色只有一个含义:真实故障」,是 §11.9 时期的旧句,与上表矛盾。)这条对三域同时生效——同一个 P&L 数字在 Trade、Workbench、Ops 里必须同色。属 §11.3 不可分项。

> 写法 `var(--color-profit, #4ade80)` 等:token 自 `@bifrost/ui@0.4.13` 起由包声明(暗 `:root, .dark` / 亮 `[data-theme='light']`),fallback 只保首帧。
>
> ~~2026-09-12 补记:`shell-registry.js` 注入 `sr-tokens-css`~~ —— **2026-09-25 已删(Rev .31)**,包内声明接管。

**未实现盈亏 — 整列橘色,不分正负(2026-09-16 更正,见 §14.7;原 §11.12 撤色处置作废)。**

```
已实现盈亏   --color-profit #4ade80 / --color-loss #f87171   有符号,着方向色
未实现盈亏   --color-unrealized #fb923c,整列橘、不分正负 + UNREALIZED 标记
```

未实现盈亏既不走 up / dn,也不走黄。**撤掉方向色本身就是那个信号**——一笔没平的仓,今天是赚是赔不是结论。黄色自此只表示 degraded。

**warn 色(如 EARNINGS T-6、thin-chain 旗)**:`#fbbf24` on `#7c530f`。

**Workbench 视觉 tokens(候选 A「终端析析」,种子 `workbench-a.dc.html`)**

```
ground  #0b0a10 · surface #151221 / #12101c · raised #0f0c18
line    #241f33 / #2c2542 / #3b3452
ink     #e6e4ef · soft #c9c4da · mute #8b84a3 · faint #615a78
accent  紫罗兰 #a78bfa(on-accent #16112b)
字体    Geist(文本)+ JetBrains Mono(数字/标识,tabular-nums)
字号    标题 21px/600 · 正文 13px · micro 9-10px uppercase .06-.1em
```

紫罗兰是**实验室模式**的标记,不是某个域的品牌色(理由见 §11.2)。Trade 沿用它现有的 `@bifrost/ui`;Ops 的新屏以 `@bifrost/ui` 为底,不引入紫罗兰。

**身份色不可分**:ticker = lime(`--sk-ticker`)、合约 = sky 族(`--sk-contract`),三域一致。紫罗兰**不得**用于标 ticker——否则同一只票在边界两侧长得不一样,全站唯一的那个 join 就断了。

---

## 2. 两条纽带契约(约束三方)

### 2.1 数据出处徽章

每屏页眉必带 `ASOF <session>` + 质量旗,例:

```
ASOF 2026-09-10        ⚑ THIN-CHAIN · judged by Ops
```

- **判定永远来自 Ops / 服务。** Workbench 与 Trade 只渲染,不自行判定数据是否可信。
- 徽章**必须可点**,深链回 Ops Console 对应决策项。
- 批失败时,ASOF 变为 `<上一 session> · HOLDING`,旗变为 `⚑ BATCH FAILED · judged by Ops`,且页面显示**上一日队列并说明**,而不是把旧队列装成新的。
- asof 徽标与质量旗是**同一个组件的两半**(`AsofTag`,props `asof` / `expected` / `sessions` / `flag` / `judgedBy` / `href`),不要分开实现——否则又会出现「有 asof 没归属」。

### 2.2 Copilot 段落必须署名

```
COPILOT DRAFT · <PROVIDER> · grounded in features asof <date>
```

- provider 是真实 provider(`ANTHROPIC` / `DEEPSEEK-CHAT` / `HEURISTIC` …),模型离线时写 `HEURISTIC`,不隐藏。
- LLM **只写依据**。分数与信号来自 `features.*`,不得由 LLM 生成或改写。
- `asof` 日期与页眉徽章一致;批失败时两处同步回退。

---

## 3. 深链路由表(三域唯一需要对齐的接口)

环境变量(已在 Trade 落地,`src/lib/opsConsole.ts`):

```
VITE_OPS_CONSOLE_URL   默认 http://127.0.0.1:5180
Research API           :8795
```

| 从 | 元素 | 到 | 语义 |
|---|---|---|---|
| Workbench / Trade Research | 页眉质量旗 | Ops Console · 对应决策项 | 「这个判定是谁下的」 |
| Workbench Today | 批失败横幅 CTA | Ops Console · Needs you | 「谁来重跑」 |
| Ops Console | Needs you 行 | Trade · 对应执行页 | 「要动手了」 |
| Workbench Today | 候选 → Add to watchlist | Research `watchlist` | 候选晋升 |
| Workbench Today | 候选 → Open in Trade | Trade · order intent(**advisory,D10 不下单**) | 跨域交棒终点 |
| Trade 判定视图 | `open in lab →` | Workbench 对应实验室页 | 模式交棒(§11.7) |
| Workbench 实验室 | `open in trade →` | Trade 对应判定视图 | 模式交棒回程 |

**设计稿里跨域链接写成普通 `<a href>` 指向对方项目的 DC 文件名**,旁边标注目标域。链接断了 = 契约没对齐,设计稿本身即验证。

---

## 4. Trade 已成立的结构(另两域不要重新发明)

- **Seat rail**:Research 分三姿态 —— Autopilot(无人值守)/ Copilot(按需)/ Workbench(动手)。一页只属于一个 seat,落到别的 seat 的页面时 rail 自己跟过去(`seatForRoute`)。
- **没有不可点的分组标题**:home 行既是标题也是页面(Portfolio 模式)。
- **fold 行落在第一个子页**,home 行落在自己的页面。
- 这套导航语法若 Ops / Workbench 需要多层菜单,直接沿用,不另起。

---

## 5. 已知重叠与处置

判据以 **§11.1 的操作性 / 探索性**为准,完整归属表见 **§11.7**。本节只登记具体重叠的处置结论。

| 重叠 | 处置 |
|---|---|
| Workbench Screener ↔ Trade `Stock Explorer` / `Stock Screener` / `Contract Screener` | 见 §11.11:按**返回什么**先分两类,再按模式分两面。不是合并成一个,也不是保留四个 |
| Workbench Today(队列式决策流) | **保留在 Workbench**,Trade 无对应物 |
| Workbench Signals ↔ Trade `Signal Health` / `Lens Coverage` | Signal Health 是**测量**,归 Trade 现有页;质量**判定**归 Ops;Workbench 只消费 |
| Symbol 页 | 拆为 Trade 判定视图 + Workbench 实验室(§11.7),受 §11.8 三条同源约束 |

---

## 6. 推进顺序（已过期）

2026-09-11 的排序已移除(过期状态快照,原文见设计项目导出历史,不在本包);当前施工顺序以 `IMPLEMENTATION-BRIEF.md` 的 build order 为准。

---

## 7. 工作区文件规约(哪些文件该在 `/stocks`,哪些不该)

**只有两类文件常驻 `/stocks` 根:**

| 文件 | 性质 | 谁写 |
|---|---|---|
| `DESIGN_CONTRACTS.md` | 长期契约,三域共读,随决策更新 | Design 会话起草 → Owner 放置 / Claude Code 写入 |
| `DESIGN_STATUS.md` | 看板:三域各自的已建 / 在建 / 待建 + 最近变更日期 | 同上 |

**交接包(`*-HANDOFF-*.md`)不入 `/stocks`。** 它们是一次性任务简报,用完即弃;堆在工作区里几个月后就是过期指令,会和契约混淆。交接包只走**聊天附件**:Owner 下载后直接拖进目标会话的对话框。

**契约补丁同理。** 单节草稿(如 `DESIGN_CONTRACTS-11.md`)合并进本文件后即删,不与本文件并存——两份文件就是两个真相。

判据一句话:**会被反复读的进仓库,只读一次的走附件。**

> Design 会话无法写入挂载目录,只能产出文件供 Owner 下载放置;Claude Code 可直接写入。因此 `DESIGN_STATUS.md` 的实际写入方由 Claude Code 承担,Design 会话负责提供该更新的内容。

---

## 8. 设计系统与 token 分层

**`bifrost-ui/ds-bundle` 挂为三个 Design 项目的设计系统。** 它已含 tokens、40+ 组件(HealthLamp / DenseDataTable / PageShell / ShellNavSidebar …)、guidelines 与逐组件截图。一致性由**继承**获得,不靠三个会话各自商量。

**当前挂载:`@bifrost/ui@0.4.14`(2026-09-25 同步)**。色彩 / 主题 token 与 README 已和本契约一致。语义色另有单独入口 `@bifrost/ui/styles/semantic`(7 个色值,暗 / 亮两套);**Trade 只引这一份**,不整份引 `bifrost-ui.css`(后者含未分层的 body / 滚动条 / `.shell-*` 规则)。

**口径优先级(冲突时自上而下取第一个)**:
1. 本文件正文——设计裁定(含尚未进包的试验口径)
2. `@bifrost/ui` 包(token 值 · 组件行为 · README / guidelines)——**已固化口径的正本**
3. `shell-registry.js`——原型层:skin ramp、层色、`SCOPE_STYLE`,以及**试验中、尚未进包**的 token;`DIRECTION` 仅作棘轮镜像,须与包值一致
4. 原型页面实际渲染

**进包规则(提升到 DS)**:新 token / 组件 / 变体先在 registry 或页面里试,写进本契约定稿;**两个控制台都会用的**在 HANDOFF 单列「提升到 `@bifrost/ui`」,由 `stocks/bifrost-ui` 实现 → 升版 → 同步回 Design;同步后删 registry 里的对应临时写法。**镜像刷新**:`DIRECTION` 的值只能经 HANDOFF「提升到 `@bifrost/ui`」一节变更——只改 registry 会让 app 棘轮报红;包升版后由 app 侧跑 `npm run sync:design-nav` 刷新镜像。Trade 专属的留在本契约,交 `bifrost-trade-frontend`。Design 侧的 Bifrost Dense UI 项目是代码镜像,**不手改**。

> **历史 · 2026-09-25 补记(Rev .30)· 已收口(Rev .31,0.4.13 同步后)**
>
> **现状**:Design 侧挂载的包是 `@bifrost/ui@0.4.11`(同步于 2026-09-10);源码 `stocks/bifrost-ui/package.json` 已是 **0.4.12**,`_ds_needs_recompile` 标记仍在。Design 设计系统选择器显示「empty」是该条目缺预览卡的展示问题——组件、tokens、README 实际完整,84 页均加载、77 页直接使用 `BifrostUI.*`。
>
> **优先级(冲突时自上而下取第一个)**:
> 1. 本文件(`DESIGN_CONTRACTS.md`)正文
> 2. `shell-registry.js`(`DIRECTION` / `SCOPE_STYLE` / 注入的 `sr-tokens-css` 与 `--sk-*` 变量)
> 3. 原型页面实际渲染
> 4. `@bifrost/ui` 的 README / guidelines / 包内默认 token 值
>
> 第 4 层只提供**组件结构与 core token**(间距、圆角、字号阶、DenseDataTable 等组件行为)。它的色彩与主题叙述已落后,下列各点**以第 1–2 层为准,不得按 README 实现**:
>
> | README / 包内现状 | 现行口径 | 出处 |
> |---|---|---|
> | 「dark-only,无亮色主题」 | 暗 / 亮两套主题,均走变量 | §14.8 · registry `DIRECTION` |
> | 「唯一强调色 lime `--primary: #a3e635`」 | 强调色 = 紫 `--sk-accent`(Package .3 起);lime 只给 ticker 身份 | §14.4 第 6 条 · §14.8 |
> | 身份色未入包 | `--sk-ticker` / `--sk-contract` / `--sk-instance` | §14.4 · §14.8 |
> | 盈亏 / 未实现色未入包 | `--color-profit` / `--color-loss` / `--color-unrealized`(`#fb923c`) | §1 · §14.7 |
> | 方向色未入包 | `--color-up` / `--color-down` | §11.9 |
>
> **收口路径(app 侧,`@bifrost/ui` 源码 owner)**:上表 token 入 tokens 层(semantic)→ README §1 改写主题与强调色两段 → 重建 ds-bundle、清 `_ds_needs_recompile` → 重新同步到 Design。完成后本补记降为历史,registry 的对应注入改为 fallback。
>
> **收口结果(Rev .31)**:上表 9 个 token 已在 0.4.13 包内,暗 / 亮值与 registry `DIRECTION` 逐一核对一致;README §1 已改写。registry 删 `sr-tokens-css`,skin 注入不再写这 6 个色 token(仅保留包内没有的 `-rgb` 三元组)。上表与上列旧优先级作废。

### 三层 token,偏好只允许落在第三层

| 层 | 内容 | 共享性 |
|---|---|---|
| **core** | 间距、圆角、字号阶、栅格 | 三域完全一致,不得覆盖 |
| **semantic** | lamp 四态、**方向色 profit / loss / unrealized**(§14.7;up / dn 已退役)、危险 / 成功、焦点环、身份色 | 三域完全一致 —— 严重度与方向的语义是普适的 |
| **brand / domain** | ground / surface 配色、正文字体、密度档 | 各域自定,但必须在本文件声明 |

**已声明的第三层偏离:**

- **OLAP Workbench 的紫罗兰终端皮肤是有意为之**(候选 A,种子 `workbench-a.dc.html`),不是漂移,**不要把它「修正」回 `ds-bundle` 默认皮肤**。它的正当理由是**实验室模式**,不是「OLAP 是另一个域」(见 §11.2)。
- Ops 与 Trade 使用 `ds-bundle` 默认皮肤,无偏离。

~~方向色 teal / orange 只在 OLAP 存在~~ —— **2026-09-12 作废**:方向色已升为全域 semantic(§1 / §11.9),不再是第三层偏离。

~~待入 tokens 层~~ —— **已入包(0.4.13;0.4.14 起在 `styles/semantic`)**:`--color-profit` / `--color-loss` / `--color-unrealized`。页面的 `var(--color-profit, #4ade80)` fallback 只为首帧。

任何域可以换 ground 配色与正文字体,**不得重新定义红色的含义,不得自造间距阶,不得改动方向色、身份色与数字格式**(完整清单见 §11.3)。

---

## 9. 设计产出落点与晋升通道

```
/stocks/design/{oltp,olap,ops}/   ← 设计产出(草稿 / 候选 / 定稿)
         ↓  仅限被采纳的
/stocks/bifrost-ui/src/           ← 组件库:已实现、已认可的组件
```

**设计稿不进 `bifrost-ui`。** 组件库被三个应用 import,灌入未采纳的探索会污染它。`bifrost-ui` 只接收晋升后的**实现代码**(由 Claude Code 编写),不接收设计稿。

Owner 把各会话的最新设计放进对应子目录;历史版本保留在 Design 项目里,不必全部同步。

---

## 10. 给 Claude Code 的交接

**真正的交接物是决策与 tokens,不是 HTML。** HTML 是佐证,文字才是契约。

每个设计告一段落时,在 `/stocks/design/<domain>/` 下放两样:

| 文件 | 内容 |
|---|---|
| `IMPLEMENTATION-BRIEF.md` | 采纳了哪些屏、每屏的数据来源(表 / 端点)、交互规则、tokens 与偏离声明、**明确不做什么** |
| `*.dc.html` | 对应设计稿,作为视觉佐证 |

`IMPLEMENTATION-BRIEF.md` 须写明:本设计遵循 `/stocks/DESIGN_CONTRACTS.md`,以及它属于哪个域、复用 `ds-bundle` 的哪些组件。

> 建议在工作区根 `CLAUDE.md` 加一节指向本文件与 `/stocks/design/`,Claude Code 便会自动读到,无需每次口头说明。未加之前,交付时补一句:「读 `/stocks/DESIGN_CONTRACTS.md` 和 `/stocks/design/<domain>/IMPLEMENTATION-BRIEF.md` 再动手」。

---

## 11. 一套 core + semantic,两个 mode 皮肤

> 本节修订 §1 的方向色、§5 的判据、§8 的第三层偏离。起草:OLTP Session(2026-09-12),合并自两份独立分析,结论一致。

### 11.0 一句话

**一套 core + semantic,两个 mode 皮肤,一条 symbol join 穿过去。**

### 11.1 分歧的轴不是域,是模式

`Research / Portfolio / Trade` 是**业务域**(§0),不是**使用模式**。按它切设计系统等于在错误的轴上下刀——因为每个域里都同时存在两种模式:

| 模式 | 特征 | 三个域里各自的例子 |
|---|---|---|
| **操作性** | 瞟一眼就要读懂;每天形状必须一样;不容歧义;键盘优先 | Research 的 daily brief、signal health、ratings 排名 · Portfolio 的 positions / risk · Trade **全部** |
| **探索性** | 坐下来一段时间;宽;容忍延迟;鼓励调参 | Research 的 surface 拟合、calibration、回测编写 · Portfolio 的深度归因(偶尔) |

**模式可以有不同皮肤,域不可以。**

行业参照:机构台面基本都是一套。研究、组合、执行共用同一套字体、同一套严重度色、同一套键盘语法;研究与执行的差别体现在**密度和布局**,不在**配色语义**。原因很具体——一个交易员一小时要在它们之间切换几十次,如果同一个红色在两处含义不同,那是真会下错单的。

行业里出现两套的场合,几乎都不是设计选择,而是**组织 / 供应商边界**:研究在 Jupyter / Streamlit / Grafana,执行是买来的 OMS。没有人因为「研究和交易气质不同」去主动做两套。

### 11.2 紫罗兰皮肤的正当理由,改写

§8 已声明 OLAP Workbench 的紫罗兰皮肤「是有意为之」。**保留这个结论,更换它的理由。**

- ~~理由(旧):OLAP 是另一个域。~~ 这个理由**弱**:用户是同一个人、同一本账、同一套语义。按它推下去,Trade 的 Research 区也该变紫罗兰,而那是错的。
- **理由(新):实验室模式。** 这个颜色告诉你「你在 lab 里,这里不会下单」。

新理由同时解释了它**为什么不该蔓延到 Trade**——Trade 里每一屏都可能下单,lab 色在那里是谎。

**两条附加约束**(否则 §11.2 会反噬 §11.5):

1. **边界必须是一次明确的跨越**,不能是环境色慢慢变。进 lab 要有明显动作与持久标识(模式徽标常驻),出 lab 同理。渐变的 ground 色只会兑现「像换了个软件」这个代价,却拿不到「我知道我在 lab」这个收益。
2. **lab 皮肤只许动 §11.4 的清单**。碰到 §11.3 任何一项即为违约。

### 11.3 绝对不可分(跨模式必须逐项一致)

1. **四态 lamp 语义** —— 尤其**无读数是灰,不是红**。未探测 ≠ 故障。
2. **方向色** `--color-profit` / `--color-loss` 与未实现 `--color-unrealized`(§1、§14.7)。
3. **身份色**:ticker = lime(`--sk-ticker`)、合约 = sky 族(`--sk-contract`)。紫罗兰**不得**用于标 ticker。
4. **数字格式与等宽字体**:精度、千分位、正负号位置、`tabular-nums`、对齐方式。
5. **asof 徽标 + 质量旗 + `judged by Ops` + 回 Ops 的深链**(§2.1)。三者是一个组件的三半,不许只实现其中一半。
6. **Copilot 署名行**(§2.2)。
7. **破坏性操作样式**。
8. **键盘语法**:⌘K / ⌘J 及同族。
9. **未实现盈亏不占色相通道**(§11.12)—— 未实现的有符号数字不着 up / dn,也不着黄,走中性墨色 + 标记。

### 11.4 可以分

- ground / surface / raised 配色
- 密度档(行高、cell padding 档位,但**不是**间距阶本身)
- 图表与表格的占比
- 常驻 chrome:执行侧每屏带 book 日内 P&L 与 gate;lab 不需要
- 正文字体族(数字族**不可**,见 §11.3.4)

### 11.5 为什么不做两套完整 DS(成本,写下来备查)

**一、期权的核心对象在三个域里反复出现。**

| 对象 | Research 里 | Trade 里 | Portfolio 里 |
|---|---|---|---|
| Option chain | 发现候选 | 下单选腿 | 持仓映射 |
| Greeks 表 | 单腿敏感度 | 成交前影响 | 组合聚合 |
| Payoff 图 | 假设推演 | 下单确认 | 现有持仓叠加 |
| Term / skew | 结构研究 | 选到期 | 到期日风险墙 |

两套 DS 意味着 **option chain 要建两次**。而且它一定会漂——不是可能,是一定。半年后同一个 delta 在一侧是 `0.42`、另一侧是 `.4200`,红绿定义还差一档。

**二、数字外观的一致性是信任属性,不是审美偏好。** 即使数值同源(已有「一处算、一处引」的约定),`tabular-nums`、正负号着色、精度、asof 标记这些**表现层**约定一分家,用户就会看到「两个不一样的 +$959」,然后开始不相信任何一个数。

**三、落地成本翻倍。** 两份组件库、两倍实现量(Claude Code 阶段尤其贵),以及跨域交棒那一刻看起来像换了个软件——而那一刻恰恰是整个系统里最重要的动作。

### 11.6 合法分叉的正面边界

判据:**tokens 与域组件全域唯一;DS 分叉只允许发生在 persona 分叉处。**

- **Ops 过线** —— 读者是 SRE 不是交易员,会话是排障不是决策,输出是重跑不是订单。这类分叉是业内常态,合法。
- **Research 不过线** —— 读者还是那个交易员。只分 mode 皮肤,不分 DS。
- **Quant workbench 是边界情形** —— 若将来出现「写代码、跑 notebook、读 SQL、会话以小时计」的真研究员面,它才够资格作为第二个 persona;即便那样,它也必须继承 core + semantic。

实现形状(与 §8 三层 token 是同一件事的两个说法):

```
core + semantic tokens        全域唯一,不得覆盖
        ↓
期权域组件                     全域共享 —— chain / Greeks grid / payoff /
(chain, greeks, payoff, …)     expiration ladder / AsofTag / ContextBar
        ↓
surface 组合                   ← 分化只允许发生在这一层
(路由、布局、密度档、mode 皮肤)
```

**方向**:域组件从 OLTP 已成熟的 Research 页**向上提取**为共享层,OLAP 消费它并在 token 之上加 lab 扩展。反方向(OLAP 定义新 DS、OLTP 的 Research 迁过去)会把已过审的东西重做一遍,还要承担两套数字格式的长期漂移。

### 11.7 归属表:按模式重新分类,不重画

OLTP 的 Research 已成熟、OLAP 刚起步,这个不对称指向一个省力动作:**不要重画,重新分类。**

| 留在 Trade shell(操作性) | 归 Workbench lab(探索性) |
|---|---|
| **Symbol 判定视图**:verdict 条 + 我在这只票上的腿 + surface 拟合的**读数**(残差表、resid 散点——它们是判定的依据,见 2026-09-14 裁定) + 出口到 Compare / Plan | **Symbol 实验室**:surface **重拟合**、参数调整、calibration、what-if |
| Ratings 排名、Screener 结果、Events、History 的**读数**(IV rank、vol cone 结论) | History 的**方法**:窗口选择、分位定义、拟合方式的探索 |
| Decision Inbox 的「等你处理」摘要 | Workbench Today 的候选队列(队列式决策流,§5 已定归它) |
| Copilot 面板(按需问、写入卡) | Autopilot 的策略编写与 persona eval |
| Signal Health / Lens Coverage 的**测量**(判定归 Ops) | 回测编写与模型探索(`Backtest`、`Discover Model`) |

这样 §5 的重叠全部化解,两边都不损失已有工作。Symbol 判定视图与 Symbol 实验室不是重复,是 **verdict 与 lab 的分工**,中间靠 lime ticker + `open in lab` / `open in trade` 链接连起来。

**移交 ≠ 重画。** 归 lab 的页只动 §11.4 允许的那几项(ground / surface、密度档、lab 徽标),并按 §11.8.3 去掉 order intent 出口。因为 DS 共享,移交是换壳,不是重设计——这正是一套 DS 换来的收益。

### 11.8 模式交棒的同源约束

§11.7 把 Symbol 拆成两页,这引入了一次跨 shell 交棒——而那正是系统里最重要的动作。因此额外三条(对所有 verdict ↔ lab 对页生效):

1. **verdict 数字同源**:两侧显示的同一个结论(rating、IV rank、VRP、resid)必须一处算、一处引,不各自计算。
2. **lab 结论回 Trade 必须带 asof**,且沿用 §11.3.5 的完整徽标(含质量旗与归属)。
3. **lab 侧不得出现 order intent 出口**。要下单必须先跨回 Trade——这就是紫罗兰在告诉你的那件事(§11.2)。

否则 `open in lab / open in trade` 会退化成两个各说各话的页。

### 11.9 方向色:红色一词二义的修正

> ⚠ **2026-09-16 被 §14.7 取代**:teal / orange 退役,方向色回归行业绿 / 红。本节保留作决策记录;红色二义的新解法见 §14.7 第 2 条。

**原状**:§1 曾规定 teal / orange 仅 OLAP 使用、Trade 沿用 emerald / red。**这意味着同一个 P&L 数字在边界两侧是不同颜色。** 一个人一天切换几十次,这是真实的误读源。

**已采纳并执行(Owner 签字,2026-09-12):全域统一用 teal / orange 表示方向,红色只留给严重度。**

这不是折中,是改进。原状里 red 同时承担「下跌」与「故障」两个含义,而 §1 的铁律要求红色专属真实故障。把方向色拆出去,红色的语义才干净:

```
方向(全域)   --color-up  teal   #2dd4bf
              --color-dn  orange #fb923c
严重度(全域) lamp-green / yellow / red / gray —— 红只表故障,未探测是灰
```

**两个 token 需进 `@bifrost/ui` tokens 层(core 之上、semantic 之内)。** 在它们落地前,页面写 `var(--color-up, #2dd4bf)`:今天渲染正确,token 就位后 fallback 自动失效,无需回头改页面。

**迁移已完成(OLTP 侧)**:100 处(52 up / 48 down),覆盖 24 个文件。迁移能精确执行是因为两个通道在该 Session 里本来就没混用——方向一律走 `var(--color-emerald-400)` / `var(--color-red-400)` 两个 token,严重度一律走 lamp 的裸 hex(`#16a34a` / `#ca8a04` / `#dc2626` / `#f87171`)。因此这次替换只动 token 名,没有一处严重度着色被波及。

**OLAP / Ops 侧待办**:Workbench 已在用 teal / orange,只需把字面值换成两个 token;Ops 无方向色,无需动作。

**备选(未采用)**:OLAP 放弃 teal / orange,两边都用 emerald / red。未采用的理由见上——那样红色仍然一词二义。

`check-legacy-css.sh` 棘轮:禁止**任何**新增 `text-emerald-*` / `text-red-*`;方向走 up / dn,严重度走 lamp-*;禁止 `lamp-red` 出现在无符号数字上。

### 11.10 §2.1 / §2.2 合规状态（历史快照）

2026-09-12 审计快照已移除(过期状态快照,原文见导出历史,不在本包);AsofTag 已落地(judgedBy 可为 Ops 或 Research,见 §2.1)。

### 11.11 四个筛选入口的收敛

现状四个入口:Trade 的 `/research/screener`、`/research/explorer`、`/research/contract-screener`,以及 Workbench Screener。§5 原写「合并为 Explorer 的重设计」,但没说谁拥有合并后的那一个。

**先按「返回什么」分两类——这是期权业务里真实存在的区别,不能合:**

| | 返回 | 出口 | 归属 |
|---|---|---|---|
| **Contract Screener** | 具体合约(到期 · 行权 · C/P) | order intent | **Trade,操作性。** 已成熟,不动 |
| **Symbol Screener** | 标的清单 | watchlist / candidate | 见下 |

**`/research/screener` 与 `/research/explorer` 折成一个 Symbol Screener**(两个入口本就是同一件事的两半)。它再按模式分两面,沿用 §11.7 Symbol 的同一套办法,不引入新概念:

- **结果面(Trade,操作性)**:已保存筛选的**每日结果**。每天形状一样,瞟一眼就读懂,出口是 watchlist 与 Symbol 判定视图。过滤条件在这里是**只读摘要行**,不是筛选面板。
- **编写面(Workbench lab,探索性)**:新建与调参。宽、容忍延迟、鼓励试错,出口是「保存为筛选」。现有的 Workbench Screener 直接充当这一面,不再是第二个入口。

**一个 URL,两张面,一条 lime ticker 穿过去。** 约束三条:

1. **已保存筛选是一个对象、一个 id**,两面读同一个,否则会出现两份「我的筛选」清单。
2. 过滤器**词表**由 lab 侧拥有(§6.3 的「吸收 Workbench Screener 的过滤器设计」即指此),Trade 侧只渲染摘要,不复制面板。
3. 编写面无 order intent 出口(§11.8.3)。

因此 §6 第 3 项从「Explorer 重设计」降级为「Explorer 折进结果面」——工作量小得多,且两边都不重画。
### 11.12 未实现盈亏:第三处一词二义

> ⚠ **2026-09-16 被 §14.7 取代**:未实现回归整列橘色(老 Trade System 原样)。本节保留作决策记录。

> 起草:实现侧回执(`bifrost-trade-frontend`,2026-09-12)提出缺口,设计侧判定。

**原状**:P&L 在生产里有**三**个状态,不是两个。已实现盈利 `--color-profit`、已实现亏损 `--color-loss`、未实现盈亏 `--color-unrealized`(`unrealizedPnlColorClass()`,14 个文件)。未实现盈亏**整体是黄色,不分正负**——这是刻意的。

**问题**:light 模式下三个业务色与 lamp 三态是**逐字相同的十六进制值**:

```
--color-profit      #16a34a  ==  --color-lamp-green
--color-loss        #dc2626  ==  --color-lamp-red
--color-unrealized  #ca8a04  ==  --color-lamp-yellow
```

不是「接近」,是同一个值。所以 §11.9 诊断的「红色一词二义」实际是**三处一词二义**,那一节只修了其中两处。方向色换成 teal / orange 之后红绿干净了,**黄色仍然同时是「未实现」和「degraded」**。

**处置:不占色相通道(撤色,不是换色)**

未实现的有符号数字照常显示数值、符号与 `tabular-nums`,但**不着方向色**,走 `--sk-soft` 中性墨色,并带 `UNREALIZED` 标记。

**理由**

1. **业务判断原样保留。**「未实现不分正负」要说的是**这不是一个结论**。本包表达「不是结论」的既有手法就是**扣住结论**——「没有 n 就没有率」在低于样本下限时只给计数、不给比率,用的是同一条原则。撤掉方向色比换一个色相更准确地说出同一件事:数字照给,颜色不表态。
2. **不需要新色相。** lamp 四态、ticker lime、contract sky,以及五层 accent(lime / stone / blue / rose / violet)已占满可用色相。再挤一个进去,要么撞层 accent,要么落在辨识度不足的余量里。§13「模式不占色相通道」是同一条思路:未实现是一种**状态**,不是一种**方向**。
3. **黄色回归单义。** `lamp-yellow` 自此只表示 degraded,§11.9 起的修正在第三个通道上闭合。

**为什么不选 c(未实现也走 up / dn)**:那等于宣布浮盈浮亏是结论,推翻一条已在生产里跑了很久的业务判断。Owner 已定——业务比设计重要,不因设计没覆盖而改业务。本处置不动业务通道,只换它的渲染。

**标记形态**:`DenseTag` 的 `category` variant,文案 `UNREALIZED`;已实现 / 未实现混排的表改用列头区分,不逐行加标。同一张表里不要两种都用。

**实现侧改动(一处,非全域重画)**

- `src/index.css`:194–196(light)/ 338–340(dark)—— `--color-unrealized` 指向中性墨色,不再指向 `--color-warning`
- `src/utils/dailyChange.ts`:103–112 —— `unrealizedPnlColorClass()` 返回中性类;注释 `site-wide yellow, not green/red` 改为 `site-wide neutral — colour is withheld, not assigned`
- 数值、正负号、`tabular-nums` 不变

**验证**:`--color-unrealized` 与 `--color-lamp-yellow` 不再解析到同一个值;`grep -n '#ca8a04'` 只在 lamp / warn 语境命中。


---

## 12. 设计所有权:两个会话,不是三个

> 起草:OLAP Session(2026-09-12),Owner 批准合并。本节把 §11.6 的 persona 判据推到组织层面。

### 12.1 判据:按「什么东西一起变」切,不按系统名字切

§11.6 已经判过 persona:

- **Ops 过线** —— 读者是 SRE,会话是排障,输出是重跑。
- **Research 不过线** —— 读者还是那个交易员,只分 mode 皮肤。

「不过线」的意思是 OLTP 的 Research 区与 OLAP 的 lab 是**同一个 persona 的两种模式**。同一个 persona、同一套 DS、同一棵导航树、同一套键盘语法,由两个设计会话分别拥有没有依据。

### 12.2 所有权

| 一起变的东西 | 所有者 |
|---|---|
| core + semantic tokens、期权域组件、§11.3 八条不可分项、导航树、键盘语法、`AsofTag` | **Bifrost Design**(合并后的 Trade + lab 会话) |
| 一屏的内容、数据源、布局、模式归属 | 同上(跟 repo 走,但同一所有者) |
| 数据质量的判定与处置(四维完整度、doctor、处方) | **Ops Design**,独立 |

**Ops 兼任审查方。** 合并后 Trade 与 lab 之间不再有互审,而这一轮所有真正花钱的错都是接缝错误(方向色两侧不同、`judged by Ops` 一侧全缺、History 把 percentile 叫 rank、四个筛选入口无人拥有)。Ops 的读者、会话、输出都不同,由它定期拿本文件逐条审 Trade + lab,补上失去的那只眼睛。

审查节奏:每完成一批屏,Ops 侧跑一次契约审计,只查 §11.3 八条 + §2 两条纽带 + §11.8 三条同源,不评价视觉。

### 12.3 合并不取消的三类工作

配色统一之后剩下的**不是**「只有配色」。以下三类仍是持续的设计判断,只是从跳会话往返变成同一所有者的内部判断:

1. **模式归属**(§11.7):每加一个功能都要判一次它归操作性还是探索性。
2. **lab 无 order intent 出口**(§11.8.3):功能约束,决定每个出口按钮写成什么。
3. **同源约束**(§11.8.1):两侧显示同一个结论必须一处算、一处引。

### 12.4 合并的已知代价与对策

| 代价 | 对策 |
|---|---|
| 上下文预算:Trade 侧原型数量大,单会话会遗忘另一侧 | 交接文件纪律**更重要而非更不重要**;每批屏收尾必产 `IMPLEMENTATION-BRIEF.md` |
| 失去互审 | Ops 兼任审查方(§12.2) |
| 两个 repo 分别演进 | 屏的数据来源与实现落点仍按 repo 记录在 brief 的路由表里 |

### 12.5 lab 路由(已注册 2026-09-12.3)

合并同时把五个 lab 页写进 `shell-registry.js`。命名规则:**有对面页的挂在对面页的路由干上**(配对关系写在 URL 里),lab 独有的页落在 `/research/lab/` 下。

| 路由 | 页 | 对面 |
|---|---|---|
| `/research/lab/today` | 候选队列(Lab 的 home 行) | 无 |
| `/research/lab/screener` | Screener 编写面 | `/research/screener` 结果面 |
| `/research/lab/symbol` | Symbol 实验室 | `/research/symbol` 判定视图 |
| `/research/lab/history` | History 方法层 | `/research/history` 读数面 |
| `/research/lab/calibration` | 28 条契约状态表 | 无 |

三条约束:**不得放在 `/docs/` 下**(`isSystemRoute` 会把整条侧栏换成 System 树;2026-09-15 收敛后 System 树里已无 Ops runtime 页);侧栏里 lab 行带的是中性的 `lab` 模式标而不是徐罗兰徐弽色 badge(§11.2:lab 色不蔓延到 Trade chrome);§11.11 的「一个 URL两张面」在实现上是**同一个已保存筛选对象、同一个 id**,面由路由末段区分。

---

## 13. 分层皮肤(2026-09-12 并入)

皮肤按**层**分,不按**模式**分。层由路由决定,由 `shell-registry.js` 的 `applySkin()` 注入;页面文件不携带任何层。

**可以按层变的**:中性色阶(ground / surface / line / ink 四档)与 accent。
**不得按层变的**:方向色 `--color-profit` / `--color-loss`、未实现 `--color-unrealized`、严重度 lamp 四态、身份色(ticker lime / 合约 sky / 品牌 mark)、数字格式与 `tabular-nums`。**阶段感只住 chrome 通道**(accent、选中态、链接、面板底色),永不碰数据语义(§14.7)。

**模式不占色相通道。** Lab 用虚线边框加角标表达,原紫罗兰皮肤退役并交给复盘层。"我在哪一层"和"我在什么模式"共用一个通道必然歧义。

**lime 的两个角色按元素区分**:`<button>` / `<a>` 上是可操作元素,取 `var(--sk-accent)`;`<span>` / `<svg>` 上是身份或图表标记,保持字面值。按类名后缀枚举不是规则,会持续漏。

**正文色下限 4.5:1。** `--sk-faint`(3.15:1)只用于描边与条形填充;`#dc2626`(4.04:1)只用于 lamp 点与边框,文字用 `#f87171`。

**产品 UI 用英文。** 中文只在设计文档与评审对话里。任何一个标签不得双语混排。

### §13.1 正文色的层依赖(2026-09-12 补)

正文色的合法性**取决于它坐在哪一层 surface 上**,不是一个绝对值。同一个 `--sk-mute` 在 ground 上 5.17:1、在 surface 上 4.37:1 —— 后者不合法。

因此 `--sk-mute` 与 `--sk-mute2` **取同一个值**:凡是只在一层 surface 上合法的色阶,就是多出来的一档。四档正文(ink / soft / mute / 以及不可作正文的 faint)在 ground、surface、raised 三层上一律合法,页面不需要知道自己坐在哪一层。

机检必须覆盖 surface 一层,只测 ground 会漏掉 DS 组件 —— `applySkin` 把 `--muted-foreground` 指向 `--sk-mute`,所以这一档的失败会被所有 DS 组件继承。

---

## 14. 并入条款（2026-09-15 收拢）

### 14.1 未授权是 empty,不是 failed
401 且客户端无凭据 = 灰 EmptyState(「Research user not set — Set user」,无 Retry——重试改变不了「没设用户」);有凭据仍 401(失效)才是 failed(红 + Retry)。「not set」与「expired」是两种空,不共用文案。未授权是关于读者的事实,不是关于系统的事实。

### 14.2 同数一处计算(升格自 Shell Spec 原 §19)
同一个数在两处出现,必须一处计算、一处引用,互相深链。范例:Backing & Model 算,Risk 引;registry 派生计数,文档引。

### 14.3 §7 注记
不建 `DESIGN_STATUS.md`;「已建/在建/待建」看板由 app 的 `/docs/design-adoption` 承担,设计包只需维护 HANDOFF 的 Rev/Package 双号。

### 14.4 实体标记(entity token)——一个金融实体只有一种样子

> 起草:设计侧自查(2026-09-16)。Owner 当日裁定三项口径(点击行为 / 合约格式 / symbol 色)。
> **修订 2026-09-23(Rev .29,回 app 侧 ASK)**:色列按 §14.8 身份色棘轮归一——Symbol/Stock → `--sk-ticker`、合约 → `--sk-contract`、Instance → `--sk-instance`;第 3、6 条随之改写。色值正本在 §14.8 + registry `DIRECTION`;本节仍是字形 / 格式 / 点击行为的正本。app commit `87db5b9` 的做法正确,不回退。
> **动机**:Portfolio 五页完成后自查发现,同一个 symbol 出现过 lime 粗体 / 白色粗体 / lime 等宽 / sky 等宽四种;
> 同一张期权合约出现过 `DAVE 280C` / `280C` / `DAVE Call 280` / `DAVE 261120C00270000 CALL 270` 五种格式;
> instance 出现过 `#118` / `#156 #156` / `/ #79` / `Book →` 四种。这不是业界做法——终端类产品(TWS、Bloomberg)
> 的通行做法恰恰是**一个实体一种呈现、一种点击行为**,全产品复用。

**五个标记,颜色只承担一件事:说明这是哪一类实体。位置不承担含义(同 §11.3「variant 载意义」)。**

| 实体 | 字形 | 色 | 点击 | 正本页 |
|---|---|---|---|---|
| **Symbol** `NVDA` | 等宽 700 `tabular-nums` | **`--sk-ticker`**(暗 lime `#a3e635` / 亮 `#3f6212`) | **打开当页右侧一格的 Symbol 面**;跨页只走一格内的显式链接 | Positions(策略轴)· Accounts(券商轴) |
| **Option 合约** `NVDA 20NOV26 245C` | 等宽 `tabular-nums`,**整体一色** | **`--sk-contract`**(暗 `#7dd3fc` / 亮 `#075985`) | 打开该合约的检视面 | Positions / Ledger |
| **Stock** | 同 Symbol 标记 | 同 Symbol | 同 Symbol | Accounts |
| **Instance** `#160` | 等宽 700 | **`--sk-instance`**(violet `#c084fc`) | 打开实例面 | Trade Ledger(链接在此产生) |
| **Strategy / Opportunity** `Covered Call 10% OTM` | sans 600,**不着色** | ink | 按它筛选 | Trade Ledger |

**六条硬约束**

1. **日期一律 `DDMMMYY`**:`20NOV26`。禁止 `11/20/26` / `2026-11-20` / `20261120` 混用——
   包括合约标记内部、Expiry 列、roll 路径与 fill 摘要。
2. **合约格式唯一**:`SYM DDMMMYY 行权价+C/P`。券商原文 OCC(`NVDA 261120C00245000`)**只进 `title` 悬停**,
   不进正文——它是给对账用的,不是给阅读用的。
3. **合约整体走 `--sk-contract`,不给里面的 symbol 单独着色**:合约是一个标识符,不是「symbol + 修饰」。
   裸 symbol 才用 `--sk-ticker`。(原「整体 ink」与旧 sky `#38bdf8` 作废,2026-09-23,§14.8 第 2 条)
4. **点击不跳页**:symbol 点击打开**当页**右侧一格。离开当页永远是一格里的显式动作
   (`Its lines → Positions`),不是点 ticker 的副作用。没有 Symbol 面的页面,symbol 仍用同一个标记,
   只是不可点(无 hover 下划线)——**样子不因可点性而变**。
5. **账户标识**:正本是账号 `U17123565`(等宽 mute);角色词 `Host` / `Secondary` 只作限定词(sans mute),
   禁止 `HOST` / `SEC` 全大写缩写。
6. **lime 只给 ticker 身份,不给强调**。强调/操作色自 2026-09-23(Package .3)起为紫(`--sk-accent`),
   lime 从强调通道空出后成为 ticker 身份色——ticker 不能读成正文(Stocks 风格轮裁定)。
   本条原文「lime 是全站唯一强调色、不用于实体」的前提随强调色换紫失效,作废。

**已执行**:Performance / Positions / Backing & Model / Accounts / Trade Ledger 五页已按本节回扫
(2026-09-16,Rev .4)。Accounts 因此新增 Symbol 面(原来点 symbol 会直接跳页)。

### 14.5 收益必须扣除外部现金流(Owner 裁定 2026-09-16)

**余额变化不是收益。** 入金抬高余额但没有赚到任何东西,所以收益只能算在**投资收益**上:

```
投资收益 = 期末净清算 − 期初净清算 − 入金 + 出金
```

**正本口径两条:**

1. **表头收益走时间加权(TWR)**:`Π (1 + r_子期) − 1`,**在每一笔外部现金流处切子期**。
   这是行业比较基准(对指数、对同类账户)的通行做法,也是本产品的房规。
2. **无日净清算序列时用 Modified Dietz 兜底**:`收益 ÷ (期初 + Σ 权重 × 流量)`,
   权重 = 该流量在账内的剩余天数比例。与 TWR 相差通常在几个基点内,除非有一笔既大又早的流量。

**什么算外部现金流**:入金、出金(Transfer & Pay 的 `deposit` / `withdrawal`)。
**什么不算**:股息、利息、证券出借收益、券商各项费用与代扣税 —— 它们发生在账户内部,
属于收益的一部分,留在投资收益里。

**三条执行约束**

- **一处计算、多处引用(§14.2)**:外部现金流这个数在 Performance 的 Reading chip、
  十一项指标条、Summary 面与 Return basis 面板出现四次,必须来自同一次归集;
  现金事件的正本是 Transfer & Pay 的 `account_transactions`。
- **未接通必须写出来**:生产侧目前**没有**任何地方扣除它。Performance 的 Return basis 面板
  标 `⚠ designed · not wired`,Transfer & Pay 的 Downstream 段同时写出「已裁定」与「未接通」。
  在接通之前,**不得**把现有收益数字说成已扣除。
- **接通那一版要声明数字会变**:收益率口径改变会改动历史展示值,HANDOFF 必须在那一版写明。

### 14.6 密集表必须声明列宽与最小宽度(2026-09-16 施工反馈立条)

> 起草:Claude Code 施工反馈(2026-09-16,Transfer & Pay 上线后实测)。
> **动机**:Transfer 明细表七列一个宽度声明都没落地 → 浏览器均分 → 每列 193px。
> Description 列 **15 行里 13 行被截断**,最糟一行需要 452px;同时永远只放三个字符的 `Ccy` 列
> 也拿着 193px。规格原本存在(原型 `.tp-clip { max-width: 340px }`、两张表的 `min-width: 980/1040px`),
> 但**只活在原型的内联 style 里**,施工文档一个字都没提 —— 所以它被当成排版细节漏掉了。

**原型里表格的 `min-width` 与列的 `max-width` 是施工规格,不是排版细节。**

1. **一张表只有一列是长文本承载列**(Description / What / Note)。其余列的内容长度是有界的
   (日期 9 字符、`Ccy` 3 字符、金额定宽)。均分等于把有界列的富余宽度从唯一需要宽度的那一列抢走。
2. **施工时给 `colgroup` 百分比**,按各列实测内容需求分配;长文本列吃剩余宽度。百分比由施工侧按
   实际字体与数据实测,原型不规定。
3. **`min-width` 照搬原型数字,作为下限。** 这些数字是按该表各列内容需求求和得出的,不是视觉近似值:
   一张 12 列的表在 1080px 以下就该**横向滚动**,而不是继续压缩列宽。低于下限滚动,不截断。
   **下限只是下限**:施工侧按真实数据实测后可上调(By symbol 实测内容和为 680px > 原型 660px 即此例),
   或让唯一的长文本列在下限处截断并带 `title`(第 4 条)。不得下调。
4. **截断必须有全文兜底**:任何 `text-overflow: ellipsis` 的单元格必须同时带 `title`。
   截断是显示策略,不是数据丢失。
5. **三列以下的表不受本条约束**(摘要块、两列键值表按内容自然宽即可)。

**存量清单**(2026-09-16.11 逐表重测,三列以上的表共 **26 张**,全部已带 `min-width`):

| 页 | 张数 | `min-width` |
|---|---:|---|
| Trade Ledger | 5 | `1180 · 1160 · 1080 · 820 · 660`(另 2 张三列表按第 5 条豁免) |
| Accounts | 5 | `1080 · 1020 · 1000 · 660 · 620` |
| Backing & Model | 9 | `1040 · 1020 · 980 · 620 · 460 · 380` + **新增** `460`(Per-leg CAR)· `460`(Stress · this symbol)· `320`(Option legs · Greeks) |
| Performance | 4 | **全部新增**:`820`(Audit,十列)· `720`(Cash statement 明细,九列)· `620`(On the fly,六列)· `560`(日现金明细,六列) |
| Positions | 3 | **全部新增**:`1160`(Contract 子表,十四列)· `940`(Lines 主表,九列)· `480`(Risk profile 场景,五列) |

旧稿的「约 30 处(Ledger 7 · Accounts 6 · Backing 8 · Performance 3 · Positions 4)」是错的:
计数把非 `<table>` 元素上的 `min-width`(如 `<span style="min-width: 104px">`)也算成了表,
而 Performance / Positions 两页当时**一处都没有**。本轮 10 张缺下限的表已补齐,无豁免项。
Audit 表的 `820` 按十列(`showOpen` 打开)算,收起成九列时下限不变。
Transfer & Pay 的 2 处已按本条修完(app `b366795`:`colgroup 12/12/12/12/12/7/33` + 两张表 `min-width`,
Description 193px → 446px,截断 13/15 → 2/15)。

### 14.7 方向色回归行业绿/红,未实现回归整列橘(2026-09-16 Owner 裁定,取代 §11.9 / §11.12 的着色处置)

> 起草:Owner 实测反馈(Accounts 落地后)。美股期权交易的行业习惯——绿涨红跌、橘 = 未实现——
> 是交易员频率最高的一次读取;§11.9 为「红色单义」把主通道挪去 teal/orange,代价被低估。

1. **三个 semantic token,全域、全阶段固定,任何页不得改写**:

   ```
   --color-profit      #4ade80   盈利 / 上涨(已实现,有符号)
   --color-loss        #f87171   亏损 / 下跌(已实现,有符号)
   --color-unrealized  #fb923c   未实现,整列橘、不分正负(老 Trade System 原样)
   ```

   `--color-up` / `--color-dn` 退役;`#fb923c` 的含义自此从「下跌」改为「未实现」。
   落地前原型写 `var(--color-profit, #4ade80)` 等 fallback(§11.9 的过渡写法照旧)。

2. **红色二义的新解法:形态分工 + 色值分离**(替代 §11.9 的「换色相」)。
   lamp 色只出现在圆点 / tag 形态;方向色只出现在带符号的 mono 数字上。
   lamp-green `#16a34a` / lamp-red `#dc2626` 保持饱和深值,P&L 用亮值 `#4ade80` / `#f87171`——
   同屏不同形、grep 不同值。禁令:lamp-* 不得着数字;profit / loss 不得着圆点或 tag。
   IB / TWS / Bloomberg 均如此并行,行业读法本身不混淆。

3. **橘与 degraded 琥珀同法分工**:琥珀 `#fbbf24` 只在 lamp / tag,橘 `#fb923c` 只在数字。
   `UNREALIZED` 标记(§11.12 形态)保留——颜色回来了,标记继续把话说全。

4. **阶段感只住 chrome 通道**:accent、选中态、链接、面板底色可随阶段变(Research 紫灰…;Trade 的 accent 现为紫 `--sk-accent`,lime 只作 ticker 身份色),
   数据语义色(方向、未实现、lamp、身份色 ticker lime / 合约 sky)永不随阶段变。

5. **图表方向填充同步**:payoff 图涨跌区、stress 柱等用 profit / loss 的低饱和填充
   (`color-mix(… 16–20%, transparent)`),图和数字说同一种语言。图例式的资产类别 hue(§6.1 豁免)不变。

6. **铺开状态**:Performance 已按本节重刷作样板;Positions / Backing / Ledger / Accounts /
   Trade Desk / Risk Stress / Review Fit 待 Owner 看样后铺开。棘轮脚本追加:禁新增 `var(--color-up` / `var(--color-dn`。

7. **Owner 补裁(2026-09-17,答施工回执)**:
   - **图形要素上的未实现二选一**:橘 = 未实现只约束**数字**(列、KPI、曲线上的读数)。散点 / 气泡等
     图形要素若需要保留涨跌信息,**拆 U 绿 / U 红**(取 `--color-profit` / `--color-loss`)并在图例标明
     是未实现(如 `U · unrealized`);否则整体橘。不得无标注地把未实现混进方向色。Positions 的
     未实现气泡图按前者落地。
   - **`--color-unrealized` 全站唯一色值 `#fb923c`**:Trade Desk 的 U 列从 `#ea580c` 统一过来;
     任何域不得自带第二个未实现橘(lamp 的饱和深值分工照 §14.7 第 2 条,不受影响)。

### 14.8 身份色棘轮（2026-09-23,双主题后的强制条款）

主题成对之后,实体身份色必须走变量——裸 hex 在亮主题下不翻转,同一实体就会在不同页/不同主题下长两个颜色。

1. **三个实体 token,正本在 `@bifrost/ui` 包内(0.4.13 起;0.4.14 起为 `styles/semantic`;此前为 registry `DIRECTION[theme]` + `applySkin`)**。`DIRECTION` 留作棘轮镜像,值须与包一致:
   `--sk-ticker`(暗 #a3e635 / 亮深绿)· `--sk-contract`(暗 #7dd3fc / 亮深蓝)· `--sk-instance`(暗 #c084fc / 亮深紫)。
   写法一律 `var(--sk-ticker, #a3e635)`(fallback 只为首帧)。方向/未实现同理走 `--color-profit|loss|unrealized`。
   **完整配方不只是颜色**(2026-09-23 补):Symbol 标 = JetBrains Mono · 700 · `tabular-nums` · ticker 变量;
   Contract 标 = Mono · `tabular-nums` · contract 变量,字号随上下文。页内定义 `.-sym` 类或直接写全配方,不得只给颜色。
2. **两个历史色相作废**:contract 的旧 sky `#38bdf8` 一律归一到 `--sk-contract`;instance 紫不得写 accent 紫 `#a78bfa`(那是操作色),必须走 `--sk-instance`。
3. **豁免(仍是字面量)**:右栏模块色(Autopilot lime · Book blue · Copilot violet · Market teal —— 工具身份,不随主题)· lamp 四色 · 品牌标。
4. **棘轮审计**(与白天清账同一把尺):扫全库 `.dc.html` 中不在 `var(--…,` 兑底位的 `#a3e635 #7dd3fc #38bdf8 #c084fc #a78bfa`;命中逐个判归属(实体→换 var · 模块色/lamp→豁免 · accent 误用→换 `--sk-accent`)。新页面裸写这五个值作实体墨 = 审计不过。
   **tint 填充同尺**(2026-09-23 二轮):方向/实体色的半透填充必须写 `rgb(var(--color-profit-rgb, 74 222 128) / α)` 形;暗中性微线必须写 `color-mix(… var(--sk-line|surface) α%, transparent)`;裸暗三元组(全通道 <90,黑色 scrim/阴影除外)= 审计不过。
   现状:全库已清零(壳件 + 72 页 + tint 二轮);豁免清单见 CLEANUP。
5. **图表图层可借身份色**(Owner 2026-09-25,Performance 图层 1b):当一条图层恰是某类实体的汇总(Options 层 = 全部合约 · Stocks 层 = 全部股票)时,取该实体墨(`--sk-contract` / `--sk-ticker`);不属于实体的图层(FI 现金流 · Cash-like)用中性墨 + 虚线,且同图内每条灰线取不同档(`--sk-soft` / `--sk-mute` / `--sk-faint`;`--sk-mute2` 在部分皮肤里与 `--sk-mute` 同值,不作区分用)。图层线不得取方向色、lamp 色或 `--sk-accent`;Total 下的面积区按 0 轴分色——水上 profit、水下 loss 低饱和填充(§14.7 #5),线本身永不红绿。

---

## 16. 页面精修原则(北极星,Owner 2026-09-23 定)

> 样板页:`Portfolio Positions.dc.html`(Rev 2026-09-23.21)。每页按本节逐条过,**不求一次铺完,慢慢推进**;进度表在 CLEANUP「页面精修进度」。

**16.0 底线(不可谈判)**:不削减任何业务能力,只降低心智理解负担。不为美化而美化;任何「更好看」若要以删能力、藏风险、合并口径为代价,一律不做。与 §15「业务价值高于视觉」同源。

**16.1 先列清单,再动手**:改一页前逐条写出它的能力(控件、过滤、下钻、推导、跳转、写操作、四态)。改完逐条对账,缺一条即回滚。清单写进该轮 DECISIONS 条。

**16.2 一页一个锚点**:页首给 1 行英雄读数(28–34px mono,最多 4–5 个)。只「提升」页面上已有的读数,不新造指标;提升后原位置不留第二份。读数卡保留原有的等级/推导入口(`?`)。严重档(如 level ≥3)只染描边,不染底。

**16.3 说明进 tooltip,诚实留在屏上**:解释性文字(页描述、分区说明、口径注脚、设计依据)移入对应控件的 `title`,**一句不删**。例外——下列信息必须可见:估算 vs 券商口径、未定价/未测量不算安全、数据陈旧、未接通。判据:藏起来是否会让人误读数字?会,就留。

**16.4 字阶三层**:页标题 22 · 分区 h2 15/600 句式(不用大写小标签)· 英雄读数 28–34 · 表格与正文 12–13。分区说明进 h2 的 `title`。

**16.5 同一行等高,不留空腔**:并排面板用 `display:flex; flex-wrap:wrap; align-items:stretch` + 各项 `flex: 1 1 <基准宽>; min-width:0`,不用 `repeat(auto-fit, …)` 网格(三项两列必然剩孤格)。可伸缩内容(图表区、读数格)随行高撑满;图表点位用百分比定位才可伸缩。

**16.6 材质分层**:环境光地面 → 实心数据卡(10px 圆角、最淡线阶外框、4% 顶内高光)→ 玻璃 chrome(侧栏/toast/sticky 表头/弹层)→ dock。**玻璃只给悬浮物,数据面永远不透明。**表内行分隔线保留(可扫性),面板外框降到 line0。

**16.7 动效克制**:入场 5px 上浮渐显 ≤ 400ms,同组错开 40ms;hover 上抬 ≤ 1px;`prefers-reduced-motion` 下全关。不做循环动画,不做装饰性动效。

**16.8 颜色只走变量**:所有中性色、方向色、身份色、tint 填充按 §14.8 棘轮;实体标用完整配方(不只颜色)。

**16.9 主题中立**:页面不得假设某个主题(暗 / 亮 / 自动)。凡页面里写死的色值、阴影底色、玻璃底色,都要能在四种组合下成立。

**16.10 统一页头 `_Shell PageHead`(Owner 2026-09-25)**:每页页头只用这一个共用件,不再手写 `<h1>` 或直接用 DS `PageHeader`。
- **第 1 行**(≥36px):标题 22/700(§16.4,单行不折,最多占 45%)· `ⓘ`(页说明,悬停显示、点击钉住,Esc / 点外关闭;说明**不上屏**,一句不删)· **时间戳位永远有**(有会话 → `ASOF`,`_Part AsofTag`;只有抓取时刻 → `FETCHED`,§4.6 不伪造 ASOF;参考页 Docs/Settings → `REV`;数据页无读数 → `ASOF —` 灰,§11.3.1)· 右侧 meta(计数,mono)+ 操作按钮(DS `Button`,主操作 ≤1 个)。
- **第 2 行**(可选,32px):下划线 Tab,当前项用 `--sk-accent` 下划线(§1「一个视图一个激活物」)。页面级视图切换放这里;**筛选 / 账户范围不进页头**,放页头下方工具条。
- 页头以一条 `line0` 细线收尾。高度只有两档:无 Tab 43px · 有 Tab 75px。
- 窄屏时**时间戳位永不收缩**(§16.3:陈旧 / 未接通必须可见);先让 meta 省略,再让标题省略(最多占 45%)。时间戳文字用短标签(如 `⚠ FEED NOT WIRED`),整句放 `title`;按钮文字 ≤ 20 字符,完整去向放 `title`。
- **例外:主语页**(Research › Symbol):以主语(symbol · 名称 · 价格 · Verdict)为页头,不再加页名标题;不广播页头事件,面包屑末级照常显示。
- **例外:长文文档页**(`/docs/*` 中以文章为主体的页:Index · Audit · Capability · Gaps · Progress · Research Menu,及 System › Discover model):保留文档排版,导语留在正文;不广播页头事件。判据:页面主体是连续正文而不是数据面。
- **Face 开关**(Reading / Method)放页头下方工具条首位,不进页头。
- 操作按钮可带状态色(`ink` / `border`,如 Refresh 的 polling 琥珀 / 完成青色),带状态色的按钮 `aria-live=polite`。
- 定稿后提升到 `@bifrost/ui` 的 `PageHeader`(加 `info` / 时间戳位 / `tabs` / 带状态的 `actions`)。

**16.10a Symbol 仍是例外,改成四层头(Owner 2026-09-25)**:不进 `_Shell PageHead`。页头从上到下:主语(symbol 26 · 名称 · 价格 · 涨跌 · 持有)→ Verdict(判定 + Send to · Plan this)→ 依据一行(灰字:lens 概述 · from 来源 · 入选理由)→ 控件行(Reading / Method · snapshot · ASOF · 本次解读的动词)。lamp 行退役,状态灯只在 Tab 上;← n of N → 走 Symbol 列表坞的 Source 列表(Shell Spec §5a.11)。

**16.12 面包屑不重复页名(Owner 2026-09-25)**:页名只在页头做主角。
- 顶栏面包屑的**上级可点**(`crumbsFor()` 给每级解析 `to`:同名路由且前缀一致 → 该路由;顶层组 → 层页;解析不到的组名保持纯文字)。
- **末级(当前页名)在页头可见时收起**,连同它前面的 `›`;页头滚出视口后淡入(≈200ms)。`_Shell PageHead` 用 IntersectionObserver 广播 `bifrost:pagehead`(`in` / `out`),并写 `<html data-pagehead>`;TopBar 据此收放。
- 没有换 `_Shell PageHead` 的页不广播,末级照常显示——过渡期没有页面会看不到自己的名字。
- §5a.5「h1 = ROUTES `label` = 面包屑末级」仍成立:名字的来源不变,只是同一时刻只出现在一处。
- 已知:窗口 < 1440 时顶栏本就会折成两行,末级淡入会让顶栏多占一行;在目标宽度下不发生。

**16.13 新鲜度按数据类型写(Owner 2026-09-25)**:时间戳位回答「现在能不能信它」。**平时安静,出问题才显眼**——新鲜 = 中性灰字(不用绿:全站绿灯等于没有信号);陈旧 = 琥珀;未知 = 灰 `—`;红色不用于新鲜度(§1)。文字写**距今多久**,精确时刻与出处进 title。判定对**交易时钟**做(RTH = 周一至周五 09:30–16:00 ET):盘外没有东西算陈旧。

| 类型 `fresh-kind` | 例 | 文字 | 陈旧判定 | 盘外 |
|---|---|---|---|---|
| `stream` 实时流 | Live | `LIVE · 0s` / `STALE 12s` | RTH 内 > 5s | `CLOSED · 16:00`(最后一笔 = 上一个收盘) |
| `snapshot` 抓取快照 | Positions · Accounts · Backing | `FETCHED 2m ago` / `STALE 18m` | RTH 内 > 5m | 1h 内照写距今;更久 `CLOSED · 16:04` |
| `run` 定时运行 | Daily Brief | `RUN 07:05` / `DUE 07:05` / `LATE · due 07:05` | 过了排期 15 分钟仍没跑 | 同左(排期本身带时刻) |
| `session` 会话 | Performance · Research 各读数页 | `ASOF 2026-09-10` / `· HOLDING` | 不是应到的会话(`_Part AsofTag`) | 同左 |

页面只传 `fresh-kind` · `fresh-at`(毫秒时刻)· `fresh-src`(出处)· `fresh-due`(run 的排期,`HH:MM` ET);距今、颜色、交易时钟由 `_Shell PageHead` 统一算(stream 每秒、其余每 15 秒重算)。市场时钟 helper 在 registry `MARKET`(`inRTH` · `lastClose` · `etToday` · `etClock`);节假日原型未建模,app 侧按交易日历实现。**原型只有一个时钟**(`MARKET.now()`):默认锚在最近一个交易日 09:59:41 ET(故事线的盘中时刻),从页面加载起走;页头、StatusBar、数据同读这一个时钟(§14.2)。localStorage `bifrost.clockShift` = `real` 用真实时间,= 毫秒数则在锚点上偏移(如 `22000000` 预览收盘后)。已迁移:Live · Positions · Backing · Accounts · Risk › Exposure · The Book · Daily Brief;session 类照旧走 `_Part AsofTag`。**同一份数据只有一个时刻**(§14.2):Positions / Backing / Accounts / Exposure 读的是同一份券商快照,原型里共用 `MARKET.brokerSnapshotAt()`;Accounts 的 Refresh 完成后该时刻前移。**例外**:Corporate Actions 的时间戳位显示的是馈源接通状态(`⚠ FEED NOT WIRED`),不是时刻,保留 `fetch-label` 写法。

**16.14 数据置信度(Owner 2026-09-25,样板阶段;取代 §16.13 的单源写法作为目标形态)**:页面要回答的不是「什么时候更新的」,而是「这页的数现在能不能拿来做决定」。它由两件事决定——**本页依赖哪些源**,以及**本页拿来做什么**。

- **数据源表**(registry `DATA.SOURCES`):每个源声明名称 · 提供方 · 自己的应到周期 · 判定方(Ops / Research,§2.1:Trade 只呈现,不判定)。状态七种:`ok` · `bydesign`(按设计就是旧的,如 OI 盘中永远 T-1)· `delayed`(权限属性,如 Massive 分析链 15 分钟延迟——不是陈旧)· `stale` · `quality`(如 THIN-CHAIN)· `down` · `unknown`。
- **页面依赖**(`DATA.DATA_PAGES`):分「决定本页」与「参考」两组,并声明用途档位——**execution**(要实时报价 + 当前账本)· **monitoring**(分钟级即可)· **research**(收盘会话足够,延迟链可用)。同一个源,对不同档位的「够用」不同:`delayed` 对 research 是 0,对 execution 的关键源是 1。
- **四层呈现**:
  1. **全局** StatusBar:交易时段(PRE / RTH / POST / CLOSED)+ 数据灯(全部源最差态)→ 点开是全站数据源面板。
  2. **页头**置信度标签:健康 = 灰字、无点,写最关键源的读数(execution:`QUOTES LIVE · POS 2m`;research:`ASOF 2026-09-24`);降级 = 琥珀 + 卡住的那个源(`POSITIONS STALE 18m` · `+N` 表示还有几个);故障 = 红(`OPTION QUOTES DOWN`,红色少数合规用法,§1)。点开 = 本页每个源的周期 · 读数 · 状态 · 判定方。
  3. **数字**:依赖降级源的列在列头副行标 `≈ quotes` / `≈ snapshot`,点名被污染的数,而不是整页可疑。
  4. **动作**:execution 档的动作在关键源降级时确认一次,列出是哪个源、读数多少。
- **不显示的页**:数据全是系统自身状态的页(Inbox · Book · Autopilot · Copilot · Plans · Playbook · Desk · Alerts · Today · Events · Orchestration · System Status)不显示标签——不依赖外部源,给时间什么也说明不了。`ASOF —` 只留给「本该报告却没报告」。
- 样板:Positions(execution · 多源 · 第 3 层列标)· Trade Expiration(execution · 第 4 层 Create plans 确认)· Stock ratings(research)· StatusBar 数据灯。原型预览:任一样板页的置信度弹层底部「Preview」切三个场景(Healthy / Snapshot stale · thin chain / IB quotes down;localStorage `bifrost.dataScenario`)。

**16.11 页面不横向滚动(Owner 2026-09-25)**:目标最小窗口 **1440px**(含侧栏)。页面滚动容器一律 `overflow-y: auto; overflow-x: hidden`。放不下的宽表在**卡片内**横向滚动,首列固定:表的包裹层加 `data-sr-hscroll`(registry 统一提供 sticky 首列样式)。网格列不用固定 px(用 `minmax(0,1fr)` 或 §16.5 的 flex 写法);`white-space: nowrap` 只给数字、代码和标签,不给说明文字。

---

## 17. 交互模式标准(Owner 2026-09-25 立,分批推进)

> 与 §16 同轮做:精修一页时顺带过本节六条。顺序:状态 → 表格 → 工具条 → KPI → 弹层 → 间距。每类:规则 → 共用件 → 样板页 → 分批迁移(每批 8–10 页),进度在 CLEANUP「交互模式对齐」。

**17.0 盘点基线(2026-09-25,76 页)**——定标准的依据,迁移完成后复扫对照:
- 状态:加载 / 失败态几乎为零(仅 Home Events 有 down 态);EmptyState 22 处,被筛空多数没有 Clear 动作;外包 padding 10 / 12 / 14 三种。
- 表格:原生 `<table>` 约 60 页 · DenseDataTable 约 15 页;声明列宽 29 页;`data-sr-hscroll` 2 页;`table-layout: fixed` 3 页。
- 筛选:SegmentControl 2 页,其余自绘 chip / pill(29 页);搜索框 3 页;没有统一的 Clear。
- 弹层:DS Dialog / Sheet / Popover 0 处;24 页自绘 overlay / drawer。
- 圆角:6px 187 · 5px 157 · 3px 90 · 4px 47 · 2px 42 · 8px 27 · 其余 6 种;面板多走 `var(--radius)`(= 10px)。
- 间距:gap 8 / 6 / 10 / 12 为主,另有 5 / 7 / 9 / 3 / 1 等;padding 组合 > 14 种。

### 17.1 七种非就绪状态(`_Part State`,已建)

| kind | 何时 | 呈现 | 动作 |
|---|---|---|---|
| `loading` | 首次加载 | 骨架,300ms 后才出,形状同内容;页头 / 工具条 / 表头 / 导航不等数据 | — |
| `failed` | 取数失败,没有旧数据 | 红 lamp + 红标题;detail 写原因 · 时刻 · 「以下没有被评估」 | Retry |
| `stale` | 刷新失败,有上一份 | **条带**(strip)压在数据上方,琥珀;数据保留 | Retry |
| `empty` | 查询成立,结果为零 | 灰;写清与「全部安全」的区别 | 结束它的动作(去定义 / 去创建) |
| `filtered` | 筛选把结果筛空 | 灰;写「N 项被 M 个筛选移除」;表头与工具条保留 | Clear filters |
| `signedout` | §14.1 无凭据 | 灰 | Set user(无 Retry) |
| `notwired` | 设计已定、馈源未接 | 灰;必须可见(§16.3) | — |

1. **失败落在包住它的最小范围**:一个源坏只占依赖它的面板;导航、静态说明照常。多个面板读同一个源时,只报一次(放在主面板),其余面板让位,不重复。
2. **刷新不出骨架**:已有数据再拉时,由页头时间戳位表达;刷新失败走 `stale` 条带,不清屏。
3. **失败 ≠ 空**:失败文案必须说明「没有被评估」,防止读成「没有问题」;空态必须说明「没有定义」与「有余量」的区别。
4. **文案**:标题说是哪件事(`Couldn't load the limit book`),detail 说原因 + 时刻;错误码写进 detail,不单独出码。
5. **声明与预览**:页面在 `_Shell PageHead` 传 `states="loading,failed,…"` 声明它实现了哪些态;原型里 ⓘ 弹层底部可逐态预览(localStorage `bifrost.viewState`,按路由;Retry 在原型里回到 Ready)。
6. 只有 `failed`(红)和 `stale`(琥珀)带色;其余全部灰(§11.3.1)。
7. **`filtered` 的动作必须结束这个状态**:复位**所有**能把本列表筛空的轴(状态 · 账户 Include/Exclude · 范围 · 搜索),不只复位触发的那一个;`title` 写清复位了哪些。

样板:Risk Overview(loading · failed · stale · empty)。

### 17.2 表格列宽与截断(扩 §14.6;registry 列型预设已建)

| 列型 | 例 | 对齐 | 截断 |
|---|---|---|---|
| entity | symbol · 合约 · 实例 | 左 | **永不**;nowrap,宽随内容 |
| num | 价格 · 数量 · Greeks · % | 右(表头也右),mono tabular | **永不** |
| tag | 状态 · Kind | 左 | 不截;按最长标签定宽 |
| text | 说明 · 备注 · 理由 | 左 | 唯一可省略的列:`minmax` 伸缩,省略号 + `title` 全文 |
| act | 行尾操作 | 右 | 固定宽 |

- **写法**:`<table data-sr-table>` + 每个 `th` / `td` 标 `data-sr-col="entity|num|tag|text|wrap|act"`。表头字号、单元格 padding(DS `--table-cell-py/px`)、行线、首尾列 12px 内缩、num 右对齐等宽,全部由 registry 统一给;页面不再自带 `xx-th` / `xx-td` 类。`wrap` = 允许折行的长说明(最小 220px);`text` 省略时必须带 `title`。
- 缺值由页面在 renderVals 里写成 `—`(不靠 CSS 补:模板空洞会留空文本节点,`:empty` 不生效);分组 / 小标题行用 `colSpan` 合并,不留空的带类型单元格。
- 用 DS `DenseDataTable` 的表同样标 `data-sr-col`(列型规则是全局属性选择器)。
- 每表声明 `min-width`(§14.6);放不下走 `data-sr-hscroll` 首列固定(§16.11)。
- 空单元格写 `—`(灰);未知 ≠ 0。
- 表头单行不折;排序标记统一在文字右侧。
- 行点击 = 打开详情(Inspector);实体标点击 = 实体面(§14.4);两者不得落在同一处。

### 17.3 筛选栏 / 工具条(registry `data-sr-toolbar` 已建)
- 位置:页头下方(§16.10),高 32px,用页面 gap 与页头隔开。
- 顺序(左 → 右):Face 开关 → 范围(账户)→ 视图(DS `SegmentControl`,不自绘 pill)→ 筛选(`IncludeExcludeToggle` / `DenseTagButton`)→ 搜索 · 弹性空白 · 行数 `N of M` → `Clear`(有生效筛选才出现)→ 次要动作(导出 / 密度)。
- 筛选状态写进 URL hash 查询串,深链可复原。
- 被筛空走 17.1 `filtered`。
- 窄屏时换行,不横向滚动;搜索框最先收成图标。
- **写法**:容器 `<div data-sr-toolbar>`(高度由内容撑开,不设 min-height——它是网格项,写死最小高会让换行溢出 · padding 5/10 · 无框 · 圆角 12 · raised2 实底(粘顶时要盖住内容),registry 统一给;Rev .73 并入 1a);内部 `data-sr-tb="label"`(大写小标签)· `"sep"`(竖分隔)· `"meta"`(右对齐计数)。不用共用 DC:各页工具条内容差异大,容器与词表统一即可。
- **Clear**:DS `Button` ghost sm,文字 `Clear N`(N = 生效筛选数),`title` 列出复位了哪些;复位规则同 §17.1 第 7 条。样板 Positions。
- 状态读数条(Live 的流状态、Today 的时钟)沿用同一容器,但不放筛选。

### 17.4 KPI 数字条(registry `data-sr-kpi` 已建)
- 两级:英雄读数(§16.2,28–34 mono,每页 ≤ 5)· 面板读数(20 mono)。其余数字进表。
- 结构:标签(11/600,sentence case,在上)→ 数(mono tabular)→ 副行(对照 / 变化 / 口径)。
- 未知写 `—` 灰;估算加 `≈` 前缀;严重档只染描边(§16.2);方向色只给有符号数(§14.7)。
- 单位跟在数后(小一号),标签里不重复。
- 点击只做一件事:下钻到算它的地方(§14.2),或筛选本页;去向写在 `title`。
- **写法**:三级——英雄卡 `data-sr-kpi="hero"`(30)· 面板读数 `data-sr-kpi-v="panel"`(20)· 读数条 `data-sr-kpi="strip"`(页面地面上的独立框)/ `"strip-inset"`(面板内的一行,不加第二层框)+ 子项 `data-sr-kpi="stat"`(16)。hero 与 strip 用 1a 材质(无框 · 圆角 12 · ink 4% 填充,Rev .73);页面只可用 `border-color` 表达状态(如琥珀 = ≥3/4),不得画装饰框。内部 `data-sr-kpi-l` 标签 · `data-sr-kpi-v` 数 · `data-sr-kpi-s` 副行。字号、字重、等宽由 registry 给,页面只写颜色。
- 样板:英雄卡 Positions;读数条 Risk Margin;面板读数 Risk Overview。

### 17.5 弹窗与侧滑面板(按用途选容器)
- 需要确认的写操作(发单 / 删除 / 不可撤销)→ DS `ConfirmDialog`;execution 档叠加 §16.14 第 4 层的源降级确认。
- 看一个对象的详情且不离开列表 → 右侧 Sheet(`_Part Inspector`),宽 480 / 720 两档,URL 带 `?inspect=`。
- 编辑表单 → Sheet,不用 Dialog:编辑时要看得到背后的数据。
- 轻量说明、单个筛选的选项、置信度 → Popover(锚定触发器,宽 ≤ 480)。
- 表内一行多看几列 → `DenseTableDetailRow` 行内展开。
- 共同:同时最多一层浮层(Popover 可在 Sheet 内);Esc 关最内层;点外关 Popover,不关 Sheet(防误触丢输入);玻璃材质只给这些浮层(§16.6)。
- **写法**(registry,2026-09-25):`data-sr-scrim`(遮罩;`="center"` 居中放确认框)· `data-sr-sheet="sm|md|lg"`(480 / 600 / 920:查看详情 / 编辑表单 / 带预览的新建)· `data-sr-toast`(底部居中一行,玻璃,`role=status`)。sheet 带 `role="dialog" aria-modal="true"`,危险确认用 `role="alertdialog"`。
- **点外关不关**:编辑类 Sheet(表单)点遮罩**不关**,只认 Esc / Cancel / ✕;查看类抽屉点外可关;确认框点外 = 取消(安全方向)。
- 盘点(2026-09-25):自绘浮层 40 处 = 提示条 23 · 编辑 Sheet 6(Desk 5 · Plans 1)· 查看抽屉 1(Autopilot Console)· 确认框 1(Desk Emergency flatten)· 外框自有 3(TopBar 右栏 / 浮窗)。Popover 类(页头 ⓘ / 置信度)在 `_Shell PageHead` 内,已统一。

### 17.6 卡片、间距与圆角
- **Rev .62 起材质按 1a**:面板 / 卡片圆角 12 · 按钮与输入框 8 · 标签胶囊 999;下一条的 10 / 6 / 4 三档是 1a 之前的值,以 HANDOFF Rev .62 为准,待本节整体改写。
- 圆角三档:面板 / 卡片 `var(--radius)`(10px)· 内嵌控件与 chip 6px · 标签与小徽标 4px。另有两个例外:色条 / 进度条 1–2px;浮层(popover / toast)8px。其余值退役。
- 间距阶 **2 · 4 · 6 · 8 · 10 · 12 · 16 · 24**(2026-09-25 按盘点修订:6 与 10 在密集界面里用量第二、第三,保留;奇数值与 14 / 18 / 20 / 22 退役):页面内边距 16 · 面板间 gap 12 · 面板内边距 12(表格区 0,单元格自带 padding)· 面板标题行 8 / 12 · 控件组 gap 6。
- 面板标题行:h2 15/600(§16.4),右侧 meta + 链接;说明进 `title`。
- 迁移方式:机械替换(脚本),每批复扫 17.0 的分布。
- **执行结果**(2026-09-25,84 个文件,仅模板内联样式与页内 `<style>`;JS 生成的样式与 Palette Study 未动):gap 3→4 · 5→6 · 7/9→8 · 11/13/14→12 · 15/18→16 · 20/22→24;padding 同表(14→12);圆角 3→4 · 5/7→6 · 9/11/12→`var(--radius)`;另 46 个面板 / 卡片类的 6px 外框圆角 → `var(--radius)`。结果:圆角 12 种 → 6 种(1 · 2 · 4 · 6 · 8 · 10),gap 14 种 → 8 种主值。

### 17.7 屏上文案与字体(Rev .74)
- **屏幕说读数与动作,不说设计。** 不引用设计文档(§ 号、Vision §、裁定、Ruled 日期),不讲本页「不是什么」、为什么这样布局、旧版怎样;不写「this page is wrong first」这类给实现者的口径,改写成「X is the source」。读法图例(灰 = 无读数、琥珀 = ≥ 阈值)是读数说明,保留。
- **D10** 是产品里的执行冻结名,作为状态词可以出现(`⛨ D10 BLOCKED`);不作为引文括注。
- **等宽只给逐位比较的内容**:数、合约、标识、公式。整句说明、图例、提示一律正文字体,哪怕句中带数字。
- **字号只用整数**(§5 dense scale);9px 只给坐标轴刻度,不给句子。
- **大写加字距只给每个面板头的一个 caption**;KPI 标签、表内标签用 sentence case(§17.4)。

---

## 15. 业务价值高于视觉(Owner 裁定 2026-09-12,2026-09-23 升格入契约)

> 起草:Claude Code(2026-09-23,走 design/trade 落地第 N 轮时提出)。
> **动机**:Owner 2026-09-12 就裁定过「设计里没有 ≠ 该删」,但这条只活在 app 侧的路由注释里,
> **本契约一个字都没写**,所以设计侧从来不知道自己有这个义务。代价是可量的:到 2026-09-23,
> `/docs/design-adoption` 有 4 页停在 `moving`,其中 3 页的能力去向要么弱于原页、要么设计里
> 根本没有对应——而 HANDOFF 从未被要求交代这些。

**设计可以重新分配能力,不可以丢弃能力。** 页面好不好看是设计的事,能力在不在是业务的事,
后者永远优先。本节约束三方,判据可机械执行。

### 15.1 「设计里没有」不等于「应该删」

设计包是**重画**,不是**清点**。app 有、设计没有,最常见的原因是这个能力被拆进了别的页面,
而不是它被判了退役。因此任何一侧得出的结论只能是**「去向待确认」**,不能是「应退役」。

**删页面 / 删菜单行一律由 Owner 肉眼决定;改位置、改归属、改标签不受此限。**

理由是不对称:**多一行菜单是噪音,少一个能力是丢功能,而且丢的时候没有人会收到告警。**

### 15.2 溶解一页时,设计必须交一张去向表

当设计决定某一页不再独立存在(合并 / 拆散 / 降为 tab / 移交),`HANDOFF.md` 必须给出该页
**每一项能力**的一行去向:

| 能力 | 去哪一页 | 以什么形态 | 强 / 平 / 弱 |
|---|---|---|---|

- **「以什么形态」要具体到列 / 面板 / tab / 筛选器**,不得写「合并进 X」。
- 写不出目的地的那一项,**直接写「未安置」并说明原因**,不要省略。**省略等于静默删除。**
- 一项能力不只是一页,也可以是一列、一个聚合、一种分组、一条注解。

### 15.3 验收判据:不得弱于被替代的页

替代页**达到或超过**原页的业务能力,替代才算成立。逐项比对,三种结论:

| 结论 | 处置 |
|---|---|
| **强于或等于** | 替代成立,原页进入 Owner 的删留决定 |
| **弱于**(少列 / 少分组 / 少注解 / 少一种读法 / 少一个筛选轴) | **设计继续打磨,原页不下线**;差在哪写进 HANDOFF |
| **设计里根本没有** | 走 §15.4 |

**少一个维度算弱,不算简化。** 简化的前提是那个维度经 Owner 判定不需要——由 Owner 说,不由设计说。

比对做在**元素级**,不是数据源级。「两页调同一个端点」只证明数据同源,不证明能力等价
(2026-09-23 实例:SEPA Daily Core 与 Stock ratings 同源,但后者没有 IV %ile、PCR OI、
Setup/Pivot 计数与 Pool 筛选四样)。

### 15.4 设计里根本没有的能力:问,不要默认丢弃

设计包里搜不到对应能力时——**搜名字,也搜它的数据,不只搜路由**——写进回执问,
要求三选一的明确答复:

1. **补进设计**(给出补在哪一页的哪个位置)
2. **判定不需要**(附理由,由 Owner 确认)
3. **暂挂并记为未安置**(留在去向表里,不消失)

**不得以「设计稿里没画」为由默认它退役。**

### 15.5 验收方式

app 的 `/docs/design-adoption` 有 `moving` 一档,记录「设计要它搬家、目的地还没到位」的页。

**一页停在 `moving` 而 HANDOFF 给不出 §15.2 的去向表,就是本节没被满足。**
这一档的页数可以作为本契约的执行指标。

### 15.6 有数据就要放(Owner 2026-09-26)

> Owner 裁语:「有数据肯定要放。设计并不知道你有什么数据,设计永远是给业务让路的,
> 同时是在满足业务的前提下美化。」

设计稿画的是设计知道的东西;**设计不知道 app 手里有什么数据**。所以「设计稿里没画」
不能成为一个有数据、且回答本页业务问题的读数缺席的理由。**在不在页面上,由数据定;
放在哪、长什么样,由设计定。**

- **判据**:某个 store / 端点**实测**有数(写明请求与返回条数),且它回答了这一页的某个
  业务问题 → 放。设计没画位置时,app 先按本页已有的面板语言放进去,再回执请设计定形。
- **反过来同样约束**:页面上写「unmeasured / owed / 没有 store 保存」之前,必须实测过
  Research、市场数据插件、Trade 三侧的相关端点,**包括 history 类端点与按日期参数**,
  并把探测写进走查笔记。写错一句「没有」,等于替业务删掉一个能力,而且没人会收到告警。
  (2026-09-26 实例:Scenario 面写「regime 历史只有当天」,`/research/forecast/terrain/history`
  实有 30 个交易日;Dealer 面写「max pain 30 日没存」,插件 `/market/analytics/max-pain/compute/history`
  实有 55 个交易日。)

### 15.7 同一能力两处都有:先交付强的,全部可见后再分主次(Owner 2026-09-26)

- 设计指定的新去处比旧处弱(§15.3 判「弱」)时,**先把强的那一版交付出来**——把旧处的
  元素补进新去处,而不是接受更少的列、更少的读法。
- **先全部表现出来,再分主次。** 折叠、收起、降到二级面是主次问题,可以后做;
  缺席不是主次问题,是丢失。
- 实例:全宇宙排名的去处是 Ratings › Underlyings,那么 IV Radar 的全表列、Benchmarks、
  |Rank−50| 两端、VRP 低端榜、斜率极值明细都补进 Ratings,而不是因为「设计说放 Ratings」
  就接受 Ratings 现在的列。

### 15.8 数据缺席先分原因:订阅权限,还是 Bug(Owner 2026-09-26)

一个能力「没数据」时,先查清原因,再定去留。判定要有证据(端点、表、作业状态、
订阅说明),不能拿页面上已有的一句「unmeasured」当证据。

| 原因 | 处置 |
|---|---|
| **订阅权限**(供应商计划不含,如期权 tape 403 / D-RLA-4) | 接受。能力留座并写明原因(§15.4 暂挂),不拿替代数据冒充 |
| **Bug / 作业停跑 / 代码路径没实现** | 修。修好之前留座并写「因 X 暂缺」,不以「没数据」为由移除 |
| **数据本身是推测**(scaffolding、低置信) | 如实标注,显不显示由 Owner 定 |

### 15.9 取舍总原则:业务优先(Owner 2026-09-26)

设计美观、页面精简、代码整洁与业务能力冲突时,**业务能力赢**;美化发生在业务被满足之后。
§15.1–15.8 都是这一条的展开。拿不准时,选让交易者看到得更多、判断得更准的那一个。
