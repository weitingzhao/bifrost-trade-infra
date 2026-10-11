# Console 的 Progress 页：整页设计（W-62，替代已停的第四片）

状态：**暂停**（2026-10-11 16:38 CDT）。第二稿，两次复核（84、87）各 5 处必须改的，没有收敛；本文**不是**可以照着实现的设计。设计预算里延长的那一次留着。重开时换做法：所有判断放进一个纯函数、输出封闭的结构，页面只照着画、拿不到原始数据；只对调度脚本（W-66）产出的格式做。原因见 `LESSONS-from-practice.md` 第 86 行和 `reviews/codex-2026-10-11-review87-console-progress-v2-design-r2.md`。以下是第二稿原文（并入了复核 84，逐条去向见第 11 节），留作材料。
输入：`OWNER-SURFACE-2026-10-11.md`（A1–A12、B1–B5、C1–C3、D1–D3，本文只引编号）；本机原型 `~/agent-work/status/` 的 `index.html`、`board2.py`、`status.publish.json`（15:38 那一份）；分支 `w31/w62-slice4`（`74ff6de`，不合并）；复核 67、69、74、78、84；`LESSONS-from-practice.md` 第 80、84 行；`api/internal/agentprogress/`、`api/internal/approvals/`；`DESIGN-lane-recorder-2026-10-11.md` 第 3–6、10 节（下称记录器设计）；`agent-config/TECH_DEBT.md` 的 TD-312；`console/` 的 ESLint、TypeScript 配置和主线上的 `progress/`、`needs-you/`。只读了文件：没有调用任何接口，没有打开任何页面，没有读任何凭证。
路径约定：`console/`、`api/` 开头的相对 `bifrost-platform/`；`agent-config/` 开头的相对 `bifrost-trade-infra/`；新代码在 `console/src/pages/shell/progress/` 之下，文中写成 `progress/`。
已定、本文不重新讨论：Console 只读这份文档，不写；审批和提问的状态只认平台上的记录；页面的标签和句子用英文、句首大写，别人写的字按原文显示；页面不说 I、me，统筹线程写成 `the coordinator`，Owner 写成 `you`；Console 只有右上角一处登录，本页没有令牌输入框（TD-312）。

## 1. 范围、不做的事、需求覆盖

这一页是 Owner 的工作界面：需不需要他、要他的每件事在哪办和怎么回、事情走到哪、之后是什么。它按原型 10-11 定下来的样子整页设计一次，再分片实现。四轮复核里反复出现的三类问题（文档里的字没清理就显示或被织进页面的句子；数据缺失、失败、过期或重复时报平安或给出一个数；颜色说得比数据多）在第 2 节用结构堵住。本页不批准也不回答（决定在那条记录自己的页面上做）；不改服务端（用到的都是现有只读接口，`owner_all`、`graph` 等是服务端原样保留的未知键）；不生成状态（步骤状态、`owner_all`、球在谁脚下由发布方给）。

| 要求 | 在哪 | 缩减，或不在本页时归哪 |
|---|---|---|
| A1 | 4.0 的次序、4.6；4.1 的首屏规则 | — |
| A2、A3 | 4.2、4.3、4.6；4.7 | — |
| A4 | 4.2（片数、夜晚数带范围和依据、日历时间那一句）、4.7（自上次以来） | 由平台读台账归 P5 |
| A5 | 2.2、第 3 节；4.3 每步标来源和进程类别 | 状态由事件生成归 P6 |
| A6 | 4.6、4.7 | 程序化来源归 P8 |
| A7 | 4.1；侧栏、手机图标、Needs you 页的标题和本页用同一个计数函数 | — |
| A8 | 4.3、2.3 | 收窄：声明类的「等你」最多琥珀（第 9 节） |
| A9 | 4.2、4.3、4.5 共用 `schedule` 一个函数 | — |
| A10 | 4.4 | 逐条动作靠 `events[]`，它是切到记录器形状的条件（第 3 节） |
| A11 | 4.5 | 收窄：完整历史不在平台上（第 9 节） |
| A12 | 4.8 的空位 | 等 Owner 给五项成果 |
| B1 | 第 9 节的留痕；本页不产生请示 | 规则在 ADR §12.2 |
| B2 | 4.1 的四个标记和排序 | 记录上的「卡住什么、办完多久」等 P3 加字段，之前显示 `Unknown` |
| B3 | 4.1：每一行都有直达；线程、主机、容量三种各有办法 | — |
| B4 | 不在本页 | 理由怎么写归建单方（W-61）；本页只显示记录的 `summary` |
| B5 | 4.1 的八行 | 收窄：命令正文不上 Console（第 9 节） |
| C1、C2 | 不在本页 | 通道状态归 P2；提醒归 P3 的通知，本页不发提醒 |
| C3 | 4.1：状态只认记录，行上写去哪里点 | — |
| D1 | 4.1 的绑定表：确认终态才消失 | — |
| D2 | 4.7 的 `Handled in the last 24 hours`（接住了） | 开始、做完、核对归 P4 |
| D3 | 不在本页 | 反馈的回执归 P7（W-65） |

## 2. 三条结构规则

页面上有几十处显示文档里的字、十几处读状态、好几处定颜色，每一处都要记得；四轮 24 处问题由此而来。下面三条把「记得」换成「拿不到」。

### 2.0 围栏
`progress/boundary/` 是唯一接触原始数据、网络、DOM 和颜色的地方。它对围栏之内只有一个出口 `boundary/index.ts`（导出的名字是 `boundary/PUBLIC.ts` 里的一张固定清单）；另有一个只给壳层的出口 `boundary/shell.ts`（计数，和给 Needs you 页的记录行），不在允许清单里。`progress/` 下除 `boundary/`、`legacy/`、测试之外的文件是「围栏之内」：`model/*.ts` 和各块的 `*.tsx`。每个文件不超过 800 行。`console/eslint.config.js` 给围栏之内加一个配置对象，全部是非类型感知的规则：

- **导入是允许清单，按解析后的路径判。** 本地规则 `progress-fence/allowed-imports`（`console/eslint-rules/progressFence.js`，以本地插件注册，不加依赖）检查 `import`、带来源的 `export`、`import()`、`require`：把说明符解析成路径（`@/` 别名、相对路径、包名），只放行 `react`、`react/jsx-runtime`、围栏之内的文件、`boundary/index.ts`，以及 `src/lib/shell/consoleRoutes.ts` 的 `approvalHref`、`questionHref`、`formatShellHash`、`HOME_ROUTE` 四个名字。其余一律报错：`@/api/**`、`@/hooks/**`、`@/components/**`、`@bifrost/ui`、`lucide-react`、`@tanstack/react-query`、`legacy/**`、`boundary/` 的内部文件，以及解析到它们的任何相对路径。
- **转导出和间接路径**由 `fence.graph.test.ts` 管：用 TypeScript 自己的解析（`ts.preProcessFile`、`ts.resolveModuleName`）从每个围栏之内的文件沿导入和转导出走到底，断言离开围栏的每条路都经过 `boundary/index.ts` 或止于允许清单，`boundary/index.ts` 实际导出的名字等于 `PUBLIC.ts`。
- **围栏之内不读网络、存储和 DOM**：`no-restricted-globals` 拦 `fetch`、`XMLHttpRequest`、`WebSocket`、`EventSource`、`localStorage`、`sessionStorage`、`indexedDB`、`window`、`document`、`navigator`、`location`、`history`、`globalThis`；另拦 `textContent`、`innerText`、`innerHTML`、`outerHTML`。数据只从边界交出的 `Read` 来；路由和滚动由 `boundary/dom.ts` 提供。
- **没有类型上的后门**：`consistent-type-assertions` 设为 `never`；`no-explicit-any`（已有）；`ban-ts-comment` 全禁；`linterOptions.noInlineConfig: true`。
- **`no-restricted-syntax`**：`dangerouslySetInnerHTML`；`aria-label`、`aria-description`、`aria-valuetext`、`title`、`alt`、`placeholder`、`label`、`value` 这些属性的值只能是字符串字面量（属性也是显示；要用引语作无障碍名称，用 `aria-labelledby` 指向 `<AgentTextView>` 的元素）；`style` 属性；`color`、`fill`、`stroke`、`variant`、`tone`、`lamp`、`status`、`intent` 这些属性；颜色类名（2.3）；`*.tsx` 里的算术和计数（`+ - * / %`、`++`、`+=`、`.length`、`.size`、`.reduce`）；`Object.keys`、`Object.entries`、`Object.values`、`for…in`（键不当标签用）；页面文字里的 `I`、`me`、`my`。

**阳性对照** `zone.selftest.test.ts`：用 ESLint 的 API 对一组样例（路径放在围栏之内）跑 lint，每段都必须报错，至少包括：引 `@/hooks/useAgentThreads`；按相对路径引 `api/approvals`；引 `legacy/` 里的文件；`export * from '@/api/agentThreads'`；`<HealthLamp lamp="green" />`；`denseTagClass('success')`；`aria-label={x}`、`title={x}`；`className="text-red-600"`；`style`；`<path stroke="red">`；`fetch(…)`；`x as string`；带 `eslint-disable-next-line` 的任一违规；`.length`；`Object.keys(x)`。另有两段必须通过：`as const`，和一个只用边界出口的干净组件。

**S1-0，片 1 第一个小时的验证。** 在真实仓库里：写出真实的 `contract.ts`（真实的不透明类，加带品牌的叶子、含 `UNKNOWN` 的联合、元组、索引签名、导出函数的返回类型各一个样例），`tsc -b` 通过且每条 `@ts-expect-error` 都被用上；注册本地规则和全部选择器，阳性对照全红、两段阴性对照全绿；图测试在三个样例文件上跑通。规则：有一样做不到，先改机制（改本文第 2 节，那一部分重新复核），不加局部豁免、不加允许清单条目、不用行内关闭；一小时内找不到机制，片 1 停线。

### 2.1 文档里的字：`AgentText`
**机制。** 组合子的清单是封闭的，没有产出裸字符串或裸数的，也没有「字典」：`record` 只收固定的键，文档里的键名不会成为页面上的字。

| 文档或记录里的值 | 组合子 | 页面模型里的类型 | 显示的出口 | 缺失或不合规 |
|---|---|---|---|---|
| 别人写的字 | `text(origin, role)` | `AgentText`，不透明对象 | 只有 `<AgentTextView>` | 缺失或清理后为空 → `NOT_WRITTEN`；不是字符串 → `UNKNOWN` |
| 代码 | `code(VALUES)` | 字面量联合 | 页面按代码写自己的话 | 不在清单里 → `UNKNOWN`，原文不回显 |
| 数 | `num(kind)`，`kind` 定范围和写法（第 3 节） | `Num<K>`，不透明对象 | 只有 `<NumView>` | 缺失、非有限、越界、该是整数而不是 → `UNKNOWN` |
| 时间 | `instant()` | `Instant`，不透明对象 | 只有 `<TimeView>`、`<Tick>` | 收 Unix 秒和 RFC 3339；早于 2020-01-01、晚于读到时刻 60 秒以上、解析不了 → `UNKNOWN` |
| id | `id(PATTERN)` | 带品牌的字符串 | 只有 `WorkItemId`（`W-n`、`TD-n`）和 `HostName` 会显示；审批、提问、步骤、等待的 id 只做 key 和拼链接 | 不匹配 → `UNKNOWN` |
| 布尔 | `flag()` | `boolean` | 页面的话 | 其它 → `UNKNOWN` |
| 数组、对象 | `list(item, cap)`、`record(fields, refine)` | `Listed<T>`（2.2）、对象 | — | 不是数组 → 这一部分未知；超过 `cap` 的丢弃并记数；单项不合规 → 一行 `Unreadable item`；`refine` 判矛盾，矛盾的那一项整项 `UNKNOWN` |

`AgentText` 只能由 `text()` 构造，构造时做完清理（去掉 C0 和 C1 控制符、bidi 控制符 U+061C / U+200E–200F / U+202A–202E / U+2066–2069、零宽字符 U+200B–200D / U+2060 / U+FEFF、标签字符 U+E0000–E007F，再把连续空白并成一个空格）和限长（按码点，`role` 定上限：`title` 120、`line` 240、`paragraph` 600，超出的截断并以 `…` 结尾）。字符串存在 `agentText.tsx` 模块私有的 `WeakMap` 里；对外只有类型、`<AgentTextView>`、`sameAgentText(a, b)`（按清理后的字比较）和 `agentTextKey(a)`（清理后的字的散列，做 key）。`toString()`、`toJSON()` 返回常量 `[agent text]`。`<AgentTextView value lines>` 把字放进 `data-agent-text` 标着来源的元素，统一的引语样式，`overflow-wrap: anywhere`；`lines` 是 1、2 或 `all`，超出的用 `Show more` 展开。审批、提问、线程记录里的字（`summary`、`reason`、问题正文、线程标题）同样是 Agent 写的，走同一个 `text()`。

**为什么忘不了。**（1）组件手里没有裸字符串：没有产出它的组合子，围栏之内不能断言类型、不能引任何原始来源（2.0）。（2）`AgentText`、`Num`、`Instant` 都不是 `ReactNode`、`string`、`number`：直接放进 JSX 或属性是编译错误。（3）拼接和模板字符串只得到常量，页面的句子里织不进文档的字；页面的话是组件里的字面量，引语只能作为并排的另一个元素出现。（4）属性只收字面量；链接只由 Console 按校验过的 id 拼。

**强制它的那一条：`boundary/contract.ts`，由 `npm run build` 里的 `tsc -b` 编译。** `AgentText`、`Num`、`Instant`、`Count`、`Listed` 赋给 `ReactNode`、`string`、`number` 各是一条 `@ts-expect-error`；`Assert<Wide<…>>` 断言两样东西——两张字段表推出的页面模型类型，和 `model/index.ts` 每个导出的返回类型——里面没有宽 `string`、宽 `number`、也没有字符串索引签名。另有运行时的清扫测试 `leafSweep.test.tsx`：夹具由字段表生成（每个 `text()` 叶子填一段各不相同的 U+202E 加一万字符加 `<script>`），把每块在每种折叠状态下渲染一遍，断言带标记的文本节点都在 `[data-agent-text]` 之内且不超过上限、没有任何属性含标记、输出里没有 `[agent text]`。

### 2.2 读取状态：`Read<T>` 和盖了封条的数据
**机制。** 每个来源在 `boundary/sources.ts` 里是一个 `Read<T>`：`loading | failed(error, last?) | stale(last, why) | ok(value)`。它不透明，唯一的入口是 `read.match({ loading, failed, stale, ok })`，四个键必填。分支交出来的不是「一个见证加一份数据」，而是**盖了封条的数据本身**：边界从同一次回答解析出的页面模型树，树上每个对象和列表各有一张封条（存在边界私有的 `WeakMap` 里，别处造不出来），写着来源、读取的代数和完整性。列表是不透明的 `Listed<T>`：只有 `map`、`filter`、`sort`，都保留封条；没有下标、没有长度、没有公开的构造函数、没有空值。几个来源的列表用 `Listed.join(…)` 合成 `Parts`，每一部分各带自己的封条；没读到的来源只能经 `Read.part(read)` 变成一个带来源名和原因的「未知部分」。**没有把各来源合成一个最差状态的操作**：一个来源不好，只影响它自己的那一部分（4.0）。

三样东西只收盖了封条的值，不存在单独的见证参数：

- **数**：`count(listed 或 parts) → Count`，只由 `<CountView>` 显示。每一部分的封条都是当前的而且完整 → `exact(n)`；否则 `atLeast(k)`，k 是当前那些部分的行数（可以是 0），同时带着「哪些部分不知道、为什么」，显示成 `At least 2` 加点名。算出来的数只有 `derive(inputs, kind, fn, range)` 一条路：输入是 `Num`，结果的封条是各输入的合取，`NaN`、无穷、越界是 `UNKNOWN`。
- **报平安**：`allClear(parts) → AllClear | null`，只在 `exact(0)` 时非空；`Nothing needs you` 只由 `<AllClearLine proof>` 显示。
- **颜色和裁决**：`tone(evidence)`，证据由盖了封条的节点构造（2.3）。

**当前**的意思：使用那一刻，封条的代数是该来源最新的一代，且该来源现在是 `ok`。`sources.ts` 是五个来源唯一的存放处，围栏之内调不了查询，所以一个来源没有第二份读数。**完整**的意思：包络合规；列表确实是数组；没有超过上限被边界丢掉的项；发布方截过的话给了合规的总数（第 3 节）。单项解析失败不破坏完整：它留成一行，照样计数。封条不是当前的，没结束的步骤的状态、能不能办、球在谁脚下一律显示 `Unknown`，颜色是中性的；结束了的步骤和引语照常显示，套一个 `As of 14:02. Not the present.` 的框。

**文档过期的定义**（下面四条都满足才是 `ok`，否则 `stale`，`why` 是对应的代码）：

| 条件 | 说明 |
|---|---|
| 服务端的 `stale` 不是真 | 收到超过 5 分钟（`document.go` 的 `StaleAfter`） |
| `age_seconds + generation_lag_seconds +` 本页自收到回答以来走过的秒数 ≤ 有效期 | 量的是生成时间。有效期取文档的 `observations_valid_s`（30 到 600 之间才认），没有就是 180（记录器设计第 4 节）。走过的秒数取单调时钟和设备时钟两个差值里大的那个，只会偏向过期 |
| `generation_lag_seconds ≥ −30` | 生成时间在服务端的将来，不认 |
| 包络的 `age_seconds`、`generation_lag_seconds`、`generated_at`、`stale` 都在而且合规 | 缺一个或不合规是 `failed(shape)`，不默认成 0，得不到当前的封条 |

从 `ok` 变 `stale` 由一个定时器在到期那一刻触发一次；页面回到前台时立即重读。读取失败的原因代码是 `http`、`timeout`、`shape`；`document: null` 是 `failed(never_published)`。审批、提问、线程、登录能力：刷新失败是 `failed(error, last)`；距上次成功超过 60 秒而没有新结果是 `stale`。

**为什么忘不了。** 组件不写满四个分支取不到数据。拿「新读到的来源」去配一份缓存的旧数组或一个空的默认值，这件事写不出来：`count`、`allClear`、`tone` 没有见证参数，只认数据自己的封条；普通数组不是 `Listed`，旧的 `Listed` 的封条不是当前的。重复不在显示点处理：记录按平台的 id 去重，声明类事项从不合并。

**强制它的那一条：`readMatrix.test.tsx`。** 用例由 `SOURCES × STATES` 生成（五个来源各取 `loading`、`failed` 无上一份、`failed` 有上一份、`stale`、`ok`，其余来源为 `ok`，再加两两同时不 `ok`），对整页断言 4.0 那张表：不 `ok` 的来源有自己的提示，别的来源的行都在，数不是 `exact`，没有 `AllClear` 的字，出自那个来源的数据没有颜色。同一个文件里有三条点名的反例：保留第 1 代的 `Listed`，发布第 2 代后对旧的调 `count`、`allClear`、`tone`，分别得到 `atLeast`、空、中性；把普通数组、空数组强行（测试里经 `unknown`）交给 `count` 和 `allClear`，得到 `atLeast(0)` 和空，同样的调用在 `contract.ts` 里是 `@ts-expect-error`；同一来源经两个组件读，得到的是同一代。

### 2.3 颜色：`tone(evidence)`
**机制。** 带状态颜色的东西只存在于 `boundary/tone.tsx`：`<ToneDot>`、`<ToneChip>`、`<ToneBar percent>`、`<ToneLamp>`、`<ToneIcon>`、`<ToneEdges>`（图的连线，SVG 属性在这里面）。围栏之内引不到组件库（2.0），拿到的中性原语来自 `boundary/ui.tsx`：`PlainButton`、`Skeleton`、`Separator`、`Glyph`、`cn`，它们把库组件上带颜色的参数固定住，不向外暴露。`Tone` 是带品牌的类型，只能由纯函数 `tone(evidence)` 得到；证据由 `evidence.step(node)`、`evidence.ownerItem(row)` 这样的构造函数从盖了封条的节点构造，封条不是当前的，结果恒为中性。`Tone` 带色相（`green`、`amber`、`red`、`blue`、`neutral`）和强弱（实、弱）；`blue` 只表示「排在接下来」（A9），不表示好坏。颜色只表示状态：原型里用来区分任务的色相不用。证据的种类是封闭的，下表是全部；片 1 只实现 `ownerItem` 和 `deadline` 两种，其余随它的块加入：

| 证据 | green | amber | red | blue | neutral |
|---|---|---|---|---|---|
| `step`：步骤状态，加是否超过往常用时 | `running` 且没超 | `slow`、`quiet`、`gap`、`running` 但超了 | `failed`、`dead` | 它那件事里下一个要开始的 `waiting` | `done`、其余 `waiting`、`unknown`、认不出的状态 |
| `ball`：没有步骤在跑时球在谁脚下 | `agents`；`nobody`，且证明见下 | `coordinator`；`owner` 但只有声明作依据 | `owner`，且证明见下 | — | `unknown` |
| `ownerItem`：他的一件事或一步 | — | 现在能办（实）；还没轮到（弱） | — | — | 状态不知道的 |
| `deadline`：最晚时间 | — | 记录的到期或声明的期限在 6 小时内 | 记录的到期在 2 小时内 | — | 其余、没有期限、`Not written` |
| `planItem`：计划里的一项 | 现在在跑 | 在等他 | — | 排在接下来 | 没有排到（弱，画成空心） |
| `pool`：一个额度池 | — | `over` | `exhausted`，且 `resets_at` 还没到 | — | 其余裁定、读数缺失、读数是上个窗口的 |
| `trouble`：有没有出问题 | 证明见下 | 有 `slow`、`quiet`、`gap` 或超时的步骤 | 有 `failed`、`dead` 的步骤 | — | 说不出 |
| `freshness`：文档的新旧 | `ok` | — | `stale`（本页自己量的） | — | `loading`、`failed` |
| `noteAge`：统筹线程那行字多久前写的 | 15 分钟内 | 更久 | — | — | 没写 |

**球对他亮红，要这几样同时成立**：文档、审批、提问、线程四个来源的封条都是当前的；没有步骤是 `running`、`slow`、`quiet`，也没有步骤是 `unknown`；清单里有一件「现在能办」的**记录类**事项；文档把一件没关闭的工作绑在这条记录上，或 `ball.holder` 是 `owner`。只有声明类事项作依据时是琥珀色，并写 `Declared by the coordinator: waiting on you`。`deadline` 的红只凭记录自己的 `expires_at`。**亮绿要证明的**：`nobody` 要文档当前、`works` 完整且没有 `UNKNOWN` 的项、每件事都已关闭、文档没有 `incomplete`、`reduced`、被截掉的开着的工作；`trouble` 的绿要文档当前、每个步骤的状态都认得出、没有上表琥珀和红的情形。证明不了的一律中性加 `Unknown`。

**为什么忘不了。** 围栏之内引不到任何带颜色的组件或类名生成函数；选择器拦字符串和模板里的颜色类名（`text|bg|border|ring|fill|stroke|outline|decoration|from|via|to` 接 `red|rose|orange|amber|yellow|lime|green|emerald|teal|sky|blue|indigo|destructive|warning|success|primary`，以及任意值写法里的 `#`、`rgb(`、`hsl(`、`oklch(`、`var(--`）、`style` 属性和颜色属性（2.0）；`Tone` 伪造不了。新加一处要上色的地方，只能选一种已有的证据，或给上表加一行。

**强制它的那一条：`tone.table.test.ts`。** 上表逐格写成用例（每种证据的每个取值乘当前和不是当前两种封条），并断言不是当前时全为中性、红和绿的每条证明条件各缺一样时都不亮。写不出颜色这一半由 2.0 的阳性对照保证，其中点名了 `HealthLamp` 和 `denseTagClass`。

## 3. 数据来源和字段

| 来源 | 接口（都是现有的只读接口） | 间隔 |
|---|---|---|
| 进展文档 | `GET /api/v1/agent/progress` | 本页 15 秒；别的页面 30 秒（侧栏的数要它） |
| 审批 | `GET /api/v1/approvals?status=open`；文档绑定了而不在这份列表里的 id，逐个 `GET /api/v1/approvals/{id}`，一轮至多 10 个 | 15 秒，回到前台时立即 |
| 提问 | 提问列表；文档绑定了而不在列表里的 id，逐个按 id 读 | 同上 |
| 线程 | 线程列表：沉默的线程、失联的主机、容量拒绝 | 同上 |
| 登录能力 | `GET /api/v1/auth/capabilities` | 60 秒 |

五个来源都用右上角那一处登录的会话读。**边界从没降级过的回答正文解析**：`sources.ts` 只用 `authedFetch` 取回 JSON，当作 `unknown` 交给字段表；不经过 `parseAgentProgress`、`parseApprovalList`、`useAgentThreads` 这些现有解析，因为它们会过滤字段、丢掉 `wid` 和 `graph`、把缺失的 `age_seconds` 和 `generation_lag_seconds` 当成 0、悄悄丢掉形状不对的行。

**先按形状归一，再谈缺失。** 文档带布尔的 `fold_complete` 就是记录器形状，用 `schemaRecorder.ts`；否则是今天的形状，用 `schemaBoard.ts`。两张表各自映射到同一个页面模型，表内不向另一种形状的字段回退：记录器的字段在而不合规，就是 `UNKNOWN`，不会被一个旧字段盖住。

| 页面模型里的概念 | 记录器形状读 | 今天的形状读 | 这种形状里没有时 |
|---|---|---|---|
| 声明类事项；它绑定的记录 | `owner_all[]` 里 `source: declared` 的；`ref{kind, id}` | `owner_all[]` 里没有合规 `approval.id` 的；`approval.id`（事项上和步骤上） | 声明这一部分未知；没有绑定 |
| 声明类能不能办、最晚 | `can_act`；`deadline`、`no_deadline` | `now`；`deadline`、`deadline_text` | `unknown`；`Not written` |
| 卡住什么、办完之后 | `holds_up[]`、`blocks_text`、`blocks_nothing`；`effect_s`、`after_text` | `blocks`、`blocks_text`；`takes` | `Not written` |
| 在哪办、怎么做、怎么回、建议 | `where` 的代码、`commands_count`、`reply_words`、`reply`、`reply_needed`、`advice` | `where`（引语）、`actions[].text`、`reply`、`advice`；不读 `cmd`、`link` | `Not written` |
| 工作的身份、编号、关没关 | `work_id`、`work_ref`、`closed_claim` | 在文档里的位置、`wid`、`finished` | 没有编号的工作不参与计划的上色；当作开着 |
| 步骤的身份、先后、最近看到 | `step_id`、`after`（步骤 id）、`waiting_on[]`、`last_seen{…}` | 位置、数组的次序、`last`（时间）；工作上的 `after` 是一段引语 | 不显示 |
| 步骤状态 | 八种（含 `unknown`）加 `reason` | 八种（含 `gap`） | `UNKNOWN`；页面认九个值 |
| 怎么结束、来源、进程类别 | `ended_how`（`Exited 0` / `Reported finished by coordinator` / `Record: Succeeded`）、`source`、`kind` 加 `command` | 没有 `ended_how`；`manual` → `Kept by hand`，否则 `Read from files` | `Finished, how not recorded` |
| 往常用时、预计 | `usual_s`、`overdue`、`eta_unsure` | `usual_min`、`eta_end`、`overdue`、`sure` | 没有预计，不画进度条 |
| 球 | `ball{holder, why, since, basis}` | 4.3 的表 | `Unknown` |
| 被截掉的总数 | `owner_all_cut`、`steps_total`、`omitted`、`works_total`、`omitted_works`、`state_counts`、`reduced`、`incomplete` | `earlier_done` | 不声称完整 |
| 两种形状都带的附加块 | `roadmap`、`graph`、`queue`、`usage`、`coordinator`、`recent`、`feed`、步骤的 `events[]` | 同左 | 有名字的缺失块（见下） |

**逐字段的组合子。** 没列出的字段不读（包括 `owner_now`、`owner_items`、`standing_items`、`needs_you`、`owner_next`、`verdict`、`level`、`published`、步骤的 `label`、`usage.by_consumer` 这种键名不固定的对象）。

| 区域 | `text` | `code` / `flag` | `num(kind)` / `instant` / `id` |
|---|---|---|---|
| 包络 | — | `stale` | `age_seconds`、`generation_lag_seconds`（seconds）；`received_at`、`generated_at`；`host` |
| 今天：`owner_all[]`（上限 50） | `name`、`work`、`not_before`、`takes`、`advice`、`where`、`reply`、`deadline_text`、`blocks`、`blocks_text`、`approval.summary`、`actions[].text` | `now`、`actions[].done` | `approval.number`（requestNumber）；`at`、`deadline`、`since`；`approval.id` |
| 今天：`works[]`（30）和 `steps[]`（20） | `title`、`short`、`goal`、`risk`、`after`；步骤的 `name`、`who`、`note`、`doing` | 步骤的 `state`；`finished`、`sure`、`needs_owner`、`parallel`、`hold`、`manual` | `round`、`earlier_done`（count）、`usual_min`（minutes）、`overdue`（seconds）；`end`、`started`、`ended`、`last`、`eta_start`、`eta_end`；`wid`、步骤的 `approval.id` |
| `events[]`（每步 30） | `text`、`out` | `kind`（八种）；`done`、`live`、`failed` | `exit`（exitCode）、`ms`（ms）、`added`、`removed`（count）；`at` |
| `roadmap` | `goal`、`note`、`uncovered_exit`、`generated_from`、`stages[].name`、`stages[].what`、`groups[].name`、`groups[].items[]`、`detail[].name`（边界拆成编号和标题）、`est.blocked`、`est.sure`、`est.note`、`est.as_of`、`pace.basis`、`pace.owner_wait`、`delta.since`、`delta.lines[]`、`exit[].text` | `stages[].state`、`groups[].state`、`exit[].state`；`exit[].owner` | `est.done`、`est.total`（sliceCount）、`est.mine`（slices）、`est.owner`（times）、`pace.per_night`（rate）；`generated_at` |
| `graph[]`（60）、`queue[]`（30） | `id`（只用来对名字，不显示）、`title`、`who`、`owner_name`、`done_with`、`becomes`、`deps[].on`、`deps[].why`、`after`、`why_waiting` | `kind`；`done`、`needs_owner` | `wid` |
| `usage.pools[]`（12）、`coordinator`、`recent[]`、`feed[]`（50） | `vendor`、`role`、`label`、`note`、`rate_basis`；`doing`、`next`、`note`；`recent[]`；`feed[]` 的 `work`、`step`、`who`、`text` | 池的 `id`（已知池的清单）、`verdict`；`sublimit`；`feed[].state` | `used`、`elapsed_pct`、`left_pct`、`projected`、`spare_pct`（percent）、`window_h`、`left_h`（hours）、`allow_per_day`、`rate_per_day`（rate）、`watchers`（count）；`resets_at`、`runs_out_at`、`read_at`、`coordinator.at`、`feed[].at` |
| 记录器：顶层和 `ball` | — | `fold_complete`；`ball.holder`、`ball.why`、`ball.basis`、`reduced`、`incomplete[]`、`full_at` | `observations_valid_s`（seconds）、`logs_unread`、`owner_all_cut`、`omitted_works.*`、`works_total.*`（count）；`ball.since`、`observer.last_round_at` |
| 记录器：`owner_all[]` | `title`、`advice`、`reply`、`reply_words`、`blocks_text`、`after_text`、`not_before_text` | `source`、`ref.kind`、`can_act`、`can_act_basis`、`reason`、`where`、`deadline_source`、`commands_at`、`last_seen.ref_state`；`reply_needed`、`no_deadline`、`blocks_nothing` | `effect_s`（seconds）、`commands_count`（count）；`deadline`、`last_seen.at`；`wait_id`（8 位十六进制）、`ref.id`、`holds_up[]`、`works[].work_id` |
| 记录器：`works[]`、`steps[]`、摘要 | `title`、`goal`；步骤的 `name`、`who`、`note`、`quote`、`command`、`superseded_text`、`reason_quote` | `source`、`closed_claim`、步骤的 `state`、`reason`、`ended_how`、`started_how`、`kind`、`watch`、`usual_basis`、`unknown_reasons[]`；`log_full`、`eta_unsure`、`gap`、`was_seen_dead`、`output_large`、`last_seen.alive` | `usual_s`、`overdue`、`silent_s`（seconds）、`exit_code`（exitCode）、`last_seen.output_bytes`（bytes）、`steps_total`、`omitted.*`、`state_counts.*`、`withdrawn`、`defects_count`、`unknown_reasons_omitted`、`log_invalid_at`（count）；`started`、`ended`、`last_seen.at`；`work_id`、`work_ref`、`step_id`（8 位十六进制）、`after`、`waiting_on[]`、`superseded_by` |

`Num` 的种类、范围和写法：`requestNumber` 1–999,999 的整数，写成 `#7`；`sliceCount`、`count` 0–100,000 的整数；`slices`、`times` 0–10,000，一位小数（今天的 `est.mine`、`est.owner` 就是小数）；`rate` 大于 0 到 10,000，一位小数；`percent` 0–1,000，取整加 `%`，条宽夹到 100；`seconds` 0–604,800、`minutes` 大于 0 到 10,080、`hours` 0–8,760、`ms` 0–86,400,000，都写成时长；`exitCode` 0–255；`bytes` 0 到 2 的 53 次方。`work_id` 的字符集本文没有核对，以记录器片 1 的夹具为准，S1-0 不含它，片 2 开工时核对。

**截断后的总数，两份设计同一条规则。** 发布方截过而给了合规的总数（`owner_all_cut`、`steps_total` 和 `omitted`、`works_total` 和 `omitted_works`、今天的 `earlier_done`），合计 = 列出的加没列出的，是确切的，没列出的作为单独一项写明（`2 not listed here — on the local board (host)`），不并进任何分类；这就是记录器设计第 4、5 节「页面只显示这一个和」的做法。没有总数、总数不合规、或是边界自己按上限丢的，合计是下界。

**附加块由谁继续发，缺了显示什么。** `roadmap`、`graph`、`queue`、`usage`、`coordinator`、`recent` 和在跑步骤的 `events[]` 不是记录器折叠的产物，由发布方在 `fold --publish` 之外照今天的做法并进同一份文档，直到 P5、P8 把它们搬进平台。**这是切到记录器形状的条件**（片 5），不是可以接受的损失：少了 `events[]`，A10 退成每步一行，就不切。文档里缺哪一块，那一块显示有名字的缺失块，不留空：`Plan — not in the document`、`Order — not in the document`、`Quota — not in the document`、`Live — no per-action events in the document`。

## 4. 页面，逐块

### 4.0 骨架，和各来源各种状态下显示什么
次序和原型一致：状态条 → Needs you → 两张大图 → 成果图的空位 → 现场 → 谁等谁 → 小仪表 → 各段。状态条是一行，写五个来源各自的读取状态和登录身份。每一块对它读的每个来源分别 `match`；一个来源不好，只换掉它自己那一部分，所以任何状态下每一部分都显示三者之一：行、一条提示、或经过证明的空。

| 来源 | `loading` | `failed`，没有上一份 | `stale`，或 `failed` 而有上一份 | `ok` |
|---|---|---|---|---|
| 登录能力 | `Checking sign-in…` | `Sign-in state: Unknown` | 同左 | 4.1 的登录提示。**只影响这一句**，不影响行、数、颜色 |
| 审批、提问、线程（各自独立） | Needs you 里它那一部分是一行 `Reading requests…`；别的来源的行照常；数是下界 | 它那一部分是一条提示 `Could not read requests (timeout)` 加 `Retry`；别的来源的行照常；数是下界并点名 | 上一份的行留在 `Last read 14:02 — state unknown` 小节里，不上色、不计入 n；提示和 `Retry` 照有 | 它的行 |
| 文档 | Needs you：记录的行照常（没有 Agent 的说明），声明那一部分是 `Reading the progress document…`；其余各块是同高的骨架 | Needs you：同左，换成提示加 `Retry`（`never_published` 时是 `No progress document has been published`）；其余各块显示这条提示 | Needs you：上一份的声明行留在 `As of 14:02 — state unknown` 小节里，不计入 n；其余各块把上一份套进 `As of` 框（2.2） | 各小节所写 |

4.3 的那张图：文档不好时按上表最后一行；审批、提问、线程有一个不好时，图照常画，只有关于他的判断降级——球不会是红色，`Some work waits on you` 那一行换成 `Whether anything waits on you is unknown — requests could not be read`。

### 4.1 Needs you（A7、B2、B3、B5、D1）
**一份清单，按部分合并。** `model/ownerQueue.ts` 的一个纯函数把四个来源的列表 `join` 成 `Parts`，页面上列他的事的只有这一块：

- **记录类**，状态完全由记录决定：审批按现有 `groupOpenApprovals` 的三组（`pending` 且没过期、要他决定的；已批准、要他在终端跑而还没跑的；状态是平台的 `unknown`、要他说明发生了什么的，写成 `Result unknown`，不和读不出的 `Unknown` 混）；`open` 的提问；沉默的线程、失联的主机、容量拒绝。
- **声明类**：`owner_all` 里没有绑定合规记录的每一项各出一行，带 `Declared by the coordinator, not a record`，没有链接。身份是记录器的 `wait_id`，没有就是它在清单里的位置；声明类之间从不合并。
- **文档里绑定了记录的项**自己不出行，只把 Agent 的说明挂到那条记录的行上，标成 `Agent's note`。它绑定的记录不在开着的列表里时，不能当成已经了结：按 id 读一次，照下表办（与记录器设计第 4 节绑定等待的表、第 6 节的 `Unknown record` 一致）。

| Console 读到的 | 这一项 |
|---|---|
| 在开着的列表里，属于三组之一；或提问 `open` | 就是那条记录的行，现在能办 |
| 按 id 读到，确认终态：审批 `executed`、`failed`、`rejected`、`expired`；提问 `answered`、`withdrawn`、`expired` | 了结，不在清单里；进 `Handled in the last 24 hours`。他办完，至多一次刷新后这一行就没了（D1） |
| 按 id 读到，不再需要他：审批 `approved`（由平台执行）、`running` | 不在清单里；记录还在走 |
| 按 id 读到 404 | 留在清单里：`Unknown record`，不显示成待批，没有链接，归入 c |
| 列表或按 id 的读取失败、超时、还没读完，或这一轮超过了 10 个 | 留在清单里：`Unknown — request #7 could not be read`，带上一次读到的状态和时间，有去那条记录的链接，归入 c |
| 文档给的 id 格式不合规 | 按声明类出一行，并标 `Unknown record` |

**一个数，全 Console 共用。** `ownerCount(parts)` 是唯一的计数函数，本页、侧栏的数、手机图标和 Needs you 页的标题都用它。Needs you 页列出的三组审批、提问和线程也改从同一次读取、同一个分组函数拿（经 `boundary/shell.ts`，这个出口只给壳层，围栏之内引不到），所以它标题上的数和它列出的行出自同一处。四个来源的部分都是当前且完整时，标题是确切的 N，下面一行 `You can do now a · Not your turn yet b · Unknown c`，N = a + b + c；发布方截过清单时再加一项 `Not listed here d`（第 3 节）。a 是现在能办的，b 是声明类里还没轮到的，c 是**认得出是哪一件、但状态不知道**的行（上表后三行、`Unreadable item`、声明类读不出 `can_act` 的）。有任何一部分不知道时，不凑 N = a + b + c：标题是 `At least n`（n 只数当前那些部分的行），下面写 `Known so far:` 加已知各类的数，再逐个点名不知道的部分和原因；不知道的来源不折成 c。文档不是当前的时候，两处显示的都是记录的数作下界。侧栏写成 `2+`（下界是 0 时写 `0+`），不单独出现问号；手机图标只能是一个数，下界大于 0 时显示它，等于 0 时清掉。页面别处没有任何可以读成「要他办几件」的数。

**排序和首屏**（B2、A1）：现在能办的在前，其中有记录期限的按到期先后，其次是写明卡住别的事的；然后是 c；最后是还没轮到的。默认只展开第一件现在能办的；其余每件两行（状态、种类加编号、标题；`Where` 和 `How` 的摘要）；超过三件时其余收在 `Show 4 more` 之后（那个数是 `Count`）。

**每一行**展开后八行，次序固定，每行都在，缺了就写明：

| 行 | 记录类（页面的话，来自记录） | 声明类（引语，或记录器的代码） |
|---|---|---|
| `Advice` | 文档有就显示成 `Agent's note`，没有就不显示 | `advice`；缺 → `Not written` |
| `When` | 不显示 | 还没轮到的才有：`not_before_text` / `not_before`；缺 → `Not written` |
| `Where` | `In this Console` 加去那条记录的链接（`approvalHref`、`questionHref`）；能力不是 admin 时在链接之前写 `Deciding needs an admin sign-in. Sign in at the top right.`。线程、主机、容量：`In the conversation thread`，链接去 Needs you 页它那一组 | 记录器的代码 → `In the conversation thread` / `In this Console` / `In your own terminal`；今天是引语；缺 → `Not written` |
| `How` | 按组：`Open the request and approve or reject` / `Approved. It has not run yet.` / `Open it and say what happened.`；提问：`Open the question and answer. Answering approves nothing.`；线程：`Open the thread on <host> and look`；主机和容量沿用 Needs you 页现有的句子（主机名是校验过的 id，数是 `Num`） | `actions[].text` 逐条；有命令时 `2 commands on the local board (host)`；缺 → `Not written` |
| `Reply` | `No reply needed. This row changes when the record changes.` | `reply`；`reply_needed: false` → `No reply needed`；缺 → `Not written` |
| `After` | `Unknown`（记录上还没有这个字段，P3） | `effect_s` → `About 10 min after you act`；`after_text` / `takes`；缺 → `Not written` |
| `Latest` | `Expires 18:40, in 3 h 10 m`；没有期限的记录 → `No deadline` | `deadline` 同样的写法；`no_deadline` → `No deadline`；`deadline_text` 是引语；缺 → `Not written` |
| `If not done` | `Unknown`（P3） | `holds_up[]` → `Holds up 2 steps` 加步骤名（引语）；`blocks_nothing` → `Holds up nothing (declared)`；`blocks`、`blocks_text` 是引语；缺 → `Not written` |

块尾一个收起的说明 `Where to act and how to reply`：三个地方各一句。**空**：`AllClear` 成立时显示 `Nothing needs you. Nothing is scheduled for you later.`；确切的 a 为 0 而 b 大于 0 时显示 `Nothing to do now` 和下面的 b 行；其余情形不写任何「没有」。

### 4.2 Plan: where we are（A2、A4、A9）
读 `roadmap`。从上到下：阶段条（当前阶段写名字，引语）；三段条（已上线、在做、没开始的件数，`count` 给）；图例（四种颜色各几件）；在做的每一项一行：色点（`planItem` 证据）、工作项编号、标题（引语，1 行）、片数条、`2/5`；底部 `≈ 9.5 slices left · ≈ 2 nights (1–3)`，范围是 0.75 到 1.5 倍（`derive`），后面一句页面的话 `Calendar time depends mostly on how long items wait on you`，`pace.owner_wait` 作为引语跟在下面，依据（`pace.basis`）在 4.7。

`planItem` 的取值由 `model/schedule.ts` 的一个函数给，4.3、4.5 用同一个：这项的编号下有非 Owner 的步骤在 `running`、`slow` → 现在在跑；否则清单里有一件现在能办的事绑在这个编号的工作上 → 在等他；否则它在 `queue[]`、在没做完的 `graph[]` 里，或它的工作开着而没有步骤在动 → 排在接下来；否则没有排到。`est.blocked` 只作为引语显示，不决定颜色。一项编号下既有在跑的又有等他的，取在跑：等他的那件事在 4.1。

| 情形 | 显示 |
|---|---|
| 文档里没有 `roadmap`；`roadmap` 或 `groups` 类型不对 | `Plan — not in the document`；`Plan: Unknown` |
| 某项没有 `est`，或 `est` 缺字段 | 那一项 `?/?`，没有条；底部改成 `Partial: 3 items without an estimate`，不给夜晚数 |
| 矛盾：`done > total`、负数、`total` 为 0 而 `done` 不为 0 | 那一项 `Unknown`，没有条；合法的 `0/0` 照常 |
| `per_night` 缺失、不合规，或算出的夜晚数超过 365 | 不给夜晚数，写 `Pace: Unknown` |

### 4.3 Running now · after（A5、A8、A9）
读 `works[]` 和每件事的 `steps[]`，以及 `queue[]`。标题旁一个数：在跑的步骤数（`count`）。**每条在跑的事一行**：编号、短标题和步骤名（引语，各 1 行）、谁在做（引语，不配图标）、来源（`From events` / `Kept by hand` / `Read from files`）、进度条（已用对往常用时，`step` 证据上色）、右侧预计做完的时间或 `Late 4 min` 或状态的名字；记录器的进程类步骤另有一行 `Process · <kind> · <command>`（类别是代码，命令行是引语）。下面接一串 `After ▸ … ▸ You: … ▸ 2 more`：这件事后面还在 `waiting` 的步骤，至多三步，他的那一步用 `ownerItem` 证据上色。后面没有步骤时写 `No later step in the document`；只有这件事已经关闭（记录器合规的 `closed_claim`，今天的 `finished: true`）才写 `This piece of work is closed (declared by the coordinator)`。再下面是 `Queued, not started`：开着而没有步骤在动的工作，和 `queue[]` 的每一项，各写 `Waits for` 加引语。

**没有步骤在跑时，先写球在谁脚下**（A8）。记录器形状用 `ball` 的代码；今天的形状按下表算，自上而下取第一条命中的。两种得到的 `owner` 都还要过 2.3 的证明：

| # | 条件（今天的形状） | 球 | 页面的话 |
|---|---|---|---|
| 1 | 有非 Owner 的步骤是 `running`、`slow`、`quiet` | `agents` | 不出这一行，直接列在跑的 |
| 2 | 有步骤的状态认不出，或 `works` 读不出、不完整 | `unknown` | `Unknown — a step's state could not be read` |
| 3 | 有开着的工作含 `gap`、`dead`、`failed` 的步骤，或它第一个没做完的步骤是 `waiting` 而不是他的 | `coordinator` | `Stopped — the coordinator has the ball, for 25 min`（时长从最近一个 `ended` 起算，没有就不写） |
| 4 | 剩下的开着的工作，第一个没做完的步骤都是他的；其中有一步绑定的记录在清单里现在能办 | `owner` | `Stopped — waiting on you. See Needs you above.` |
| 5 | 同上，但没有一条记录作证 | `coordinator`（琥珀） | 声明说现在能办：`Declared by the coordinator: waiting on you`；否则 `Stopped — not your turn yet` |
| 6 | 没有开着的工作，且 2.3 里 `nobody` 的证明成立 | `nobody` | `Queue finished` |

球在统筹线程脚下不等于没有他的事：这一行后面只有在清单里「现在能办」的数是确切的 0 时才写 `Nothing for you to do now`；确切而大于 0 时写 `You have items to do — see Needs you above`；说不出时写 `Whether you are needed is unknown — see Needs you above`。**矛盾**：步骤是 `running` 却带 `ended`，或 `started` 晚于读到时刻 60 秒以上 → 那一步的状态是 `Unknown`，不画条。`works` 缺失 → `Unknown`，不写 `Queue finished`。

### 4.4 Live: what is happening now（A10）
一个固定高度的面板（桌面 320 px，手机 260 px），同时在跑的步骤再多也不长高。读每个 `running`、`slow`、`quiet` 步骤的 `events[]`，没有就读 `quote`、`last_seen`、`doing`。上面一排标签：`All 3`（`count`），然后每个在跑的步骤一个（编号加短标题，引语 1 行，右侧 `12 s ago`）。`All` 把各步骤最近 15 条按时间倒序合在一起，至多 40 行，每行开头是它的工作项编号；点一个标签只看那一步的最近 30 条。每一行：时间、种类的图形（来自代码；认不出的种类用一个中性的点）、正文（引语，2 行，可点开）、`run` 的结果（`exit 0 · 2.4 s`，页面的话加 `<NumView>`；`out` 是引语）。

- **原地更新**：标签和行都用稳定的 key（`step_id`，没有就是编号加步骤的位置；行再加时间、种类和 `agentTextKey`）。标签的次序是首次出现的次序，新的排在末尾；标签里会变的只有那段时长，是一个 `<Tick>` 文本节点。选中的、或指针和焦点所在的标签，它的步骤结束后原位保留并标 `Ended`，离开后的下一次刷新才移走。选中项是文档之上的状态。新行插在顶部；他往下滚过，就保持他的位置。
- **状态**：没有步骤在跑 → `No step is running`，下面是 `feed[]` 最近 6 条，标 `Latest activity`；在跑的步骤没有 `events[]` → `Live — no per-action events in the document` 加它最后一行输出；步骤是 `quiet`、`slow` 时标签按 `step` 证据上色（原型里「超过 2 分钟变色」是本页自定的阈值，不用）；文档不是当前的 → 整块进 `As of` 框。

### 4.5 What follows what，和全部计划（A11）
总览里的图：四列 `Just finished`、`Now`、`Next`、`Later`（第三层及以后并在这一列）。`Just finished` 里每条开着的线一张卡（它在跑，或有别的事在等它），列它最近结束的两步（按 `ended`）；文档里一步都没有而截断计数大于 0 时写 `Finished steps are not in the document`。其余节点是开着而有步骤在动的工作，加 `graph[]` 里没做完的每一项；一项已经开始（`becomes` 对上一件在动的工作）就不画两次。层数 = 它还在等的事里最大的层数加一。连线表示「等它」，原因（`why`，引语）写在等的那张卡上。节点的颜色用 `schedule` 的结果；连线是中性的，一端是他的事时用 `ownerItem` 证据。

- **对上名字**用 `sameAgentText`（记录器形状按 id）。对不上的依赖不画线，卡上写 `Waits for` 加引语加 `(not on this picture)`。**成环**的几项放进最后一列，标 `Order unknown`。
- **布局不量 DOM**：卡片等高（标题 1 行、原因 1 行），连线端点是（列，行）的纯函数，由 `<ToneEdges>` 画。等高放不下的内容有出口：点一张卡，图下方的详情条显示它的全文和它在等的每一件及原因；卡片高度不变。
- **全部计划**是一条路由 `#progress?view=plan`（现有的 `formatShellHash(id, query)` 写法，由 `boundary/dom.ts` 听 `hashchange`），进历史，浏览器的后退回到总览原来的位置。内容：每一层不合并；每条线文档里有的每一步，最新的在上，并按第 3 节写明 `27 earlier steps are not in the document — full history is on the local board (host)`；整件做完的工作各一行可展开；有估算而还没排进先后的项；之后的阶段；做完的标准；已上线的清单（收起）。
- **状态**：`graph` 缺失 → 只画前两列，写 `Order — not in the document`。没有任何节点时，只有文档当前、`graph` 在而且完整、没有被截掉的开着的工作，才写 `Nothing is scheduled`；否则写 `No scheduled work in the document` 并点名缺的那一样。图下一行 `The order after "Now" is declared by the coordinator`，记录器形状里先后由事件给时去掉。

### 4.6 小仪表（A1、A2、A6）
| 仪表 | 读 | 显示 | 证据 |
|---|---|---|---|
| `Trouble` | 全部步骤 | 三盏灯加一句：`2 stuck or failed — handled by the coordinator` / `1 slower than usual` / `None` / `Unknown` | `trouble` |
| `Quota` | `usage.pools[]`（不含 `sublimit` 的） | 每池一条细条（已用，加一道表示窗口已过比例的刻线）和 `Claude 5h 16%`；下面 `Read 5 h ago`；读数缺失或越界 → 那一池 `Unknown` | `pool` |
| `Coordinator` | `coordinator.at`、`doing` | 一盏灯、`Written 4 min ago`、那行字（引语，1 行）；缺 → `Not written` | `noteAge` |
| `Sync` | 文档这个 `Read` | `12 s old · from <host>`；过期时 `Last published 14:02. The coordinator's machine may be asleep.` | `freshness` |
| `Finished recently` | `recent[]` | 最新的一条（引语，1 行）加 `8 listed`。不显示「今天做完 n」：发布方只留最近 8 条 | 无 |

五个等高，各自点开对应的那一段。

### 4.7 各段（A3），和 4.8 成果图的空位（A12）
各段全部默认收起，收起的内容不挂载。次序：`Each piece of work`（在动的工作各一张卡：做完的步骤并成一行可展开，其余步骤逐个，带状态、来源、用时、预计；没有步骤在动也不在等他的工作各一行；做完的工作合成一行）→ `Plan and estimate`（每项的估算、把握、依据，`delta.lines` 即自上次以来变了什么，没算进去的）→ `Quota and usage` → `The coordinator` → `Activity` → `Finished recently` → `Commit lineage` → `Code health`（最后两段是现有的页面，点开才挂载）。Needs you 块尾另有收起的 `Handled in the last 24 hours`，只读记录（现有的 `recentlyHandledApprovals`、`recentlyHandledQuestions`，点开才读 `status=all`）。成果图的位置在两张大图之下、现场之上，名字 `outcomes`，路由参数预留 `view=outcomes`，文档顶层键预留 `outcomes`；Owner 定下五项成果之前，这个位置什么都不渲染。

## 5. 手机（360–430 px）

内容和次序与桌面相同，单列。

- **状态条和 Needs you**：状态条两行。收起行：状态和种类一行，标题一行，两个标记换到第三行；展开后标签在上、内容在下；去记录的链接是一整行的按钮。
- **两张大图**上下排。计划的每一项一行，片数条在下一行；在跑的每一行，进度条在名字下面，`After` 那一串至多两步加 `3 more`，可换行。
- **现场**高 260 px；标签在它自己的条里横向滑动，页面本身不横向滚动。**谁等谁**不画线：按列的标题分组的竖排清单，每张卡下面逐条写出它等的每一件和原因（不截断）。**小仪表**两列，`Quota` 占整行。

可点的东西高度不小于 44 px；没有只有悬停才看得到的内容；引语在容器内任意处断行。页面根节点隐藏横向溢出只是兜底，它不证明内容够得着：够不够得着由第 7 节在三个宽度上走查。

## 6. 性能与跳动

- **每秒的时钟**：沿用现有的 `progressClock.tsx`。订阅它的只有叶子：时长的文字、在跑那几行的进度条、现场标签上的时长、`Sync` 的新旧。
- **过期**：到期那一刻由定时器触发一次，读了文档的块各重绘一次。
- **刷新**：五个来源各自刷新。一块只在它读的来源变了时重绘：Needs you 读四个来源，哪一个变了它都会变；4.3 读文档和清单；其余各块只读文档。`sources.ts` 按原始子树的身份缓存解析结果，没变的子树给出同一个对象，`memo` 的块不重绘。本页之外，文档每 30 秒读一次（约 100 KB），为的是侧栏的数。
- **不跳**：现场面板定高；骨架和成品同高；小仪表等高；图不量 DOM；Needs you 只在数据变化时变高。展开和选中的状态在文档之上（沿用 `progressFold.tsx`）。
- **测试** `tick.test.tsx`：每块登记自己的重绘次数，推进 3 秒时钟后每块的次数不变；登记表必须包含 `blocks.ts` 导出的每一块。

## 7. 只有人能核对的（测试环境上走一遍）

1. 桌面 1280×800：打开 10 秒内，说得出现在需不需要你、在跑什么、有没有出问题、计划走到哪；Needs you 有三件事时两张大图仍在第一屏。
2. 手机，360、390、430 三个宽度各走一遍：页面不能左右滑；长的工作项编号和标题不被切掉；展开的说明正常换行；谁等谁的每张卡上，它等的每一件和原因都读得到；现场的标签条能滑到最后一个；每个可点的东西用拇指点得中。
3. 有一张真实待批的单时：最上面的数和侧栏的数相同；每行读一遍就知道去哪；点链接到那张单；批了之后 15 秒内这一行消失、两处的数一起减一。
4. 用非 admin 的身份登录：链接之前就写着需要 admin 登录；本页没有令牌输入框。
5. 让发布方停 4 分钟：出自文档的内容进 `As of` 框、颜色变中性；记录的行还在、还带颜色；数变成 `At least n`，侧栏是 `n+`；`Sync` 是红的；没有报平安的话。
6. 现场：两步同时在跑时看一分钟，新的一行出现在最上面，面板高度不变，点标签时它不会从手指下面换走。
7. 谁等谁：点 `Full plan`，再按后退，回到原来的位置；桌面上点一张卡，图下方出现它的全文。
8. 颜色：计划里的绿、蓝、琥珀、空心和「在跑」那一栏对得上；「球在你脚下」的红只在有一条真实记录等你、而且没有步骤在跑时出现（失败的步骤、用完的额度、过期的同步、快到期的单各有各的红）。

## 8. 分片

每片是一次实现、统筹方验收、独立复核，一到两轮；每片带它新加的块在手机上的形态；每片之后页面都可以发。**停线条件都是可判定的**：（1）`npm run lint`、`npm run build`、`npm test` 有一样不绿，或要靠 `boundary/`、`legacy/` 之外的豁免才绿；（2）本片点名的反例和阳性对照缺一条或不过；（3）第 7 节里属于本片的走查条目有一条不过；（4）第二轮复核里还有一处落在三类问题里、位置在围栏之内的发现。成立就停下改本文的机制，不加第三轮；修复轮不加范围。

| 片 | 交付 | 不含 |
|---|---|---|
| 1 围栏、三条规则、Needs you | **S1-0**（2.0）。`boundary/` 的公共部分：组合子、`owner_all` 两种形状和四个记录来源的字段表（含带 `owner_all_cut`、`commands_count` 的夹具）、`AgentText`、`Num`、`Listed` 和封条、`Read`、`tone` 的 `ownerItem` 与 `deadline` 两种证据、`ui.tsx`、`contract.ts`；本地 lint 规则、阳性对照、图测试、`leafSweep`、`readMatrix`（含三条反例）、`tone.table`；状态条；4.1 整块；侧栏、手机图标、Needs you 页标题改用 `ownerCount`，`useNeedsYou.ts` 的三组和提问、线程改从 `boundary/shell.ts` 取（Needs you 页加一行指向本页的提示，写声明类有几件或不知道；它的行怎么画不变）。**同一片里从主线删掉**：`ProgressNeedsYou.tsx` 整个文件（`NeedsYouNow`、`RequestChipLink`）；`AgentWorkBoard.tsx` 里显示 `ownerNextLine(doc.owner_next)` 和 `Nothing is waiting for you.` 的那一块及 `NeedsYouNow` 的挂载；`api/agentProgress.ts` 的 `OwnerNow`、`OwnerNext`、`ownerNextLine` 和 `owner_now`、`owner_next`、`needs_you` 的解析；`stepStateLabel` 的 `waiting for you`、`not your turn yet` 两个返回值改成中性的 `Your step`，`ProgressWorks.tsx` 里对应的两个上色分支删掉；`partOfReference` 里读 `owner_now` 的分支。其余旧文件搬进 `progress/legacy/`，原样留在新块之下 | 两张大图、现场、图、小仪表；其余七种证据；`Handled in the last 24 hours` |
| 2 两张大图和小仪表 | 4.2、4.3、4.6；`schedule.ts`；`step`、`ball`、`planItem`、`pool`、`trouble`、`freshness`、`noteAge` 七种证据；文档其余字段的两张字段表，连同按记录器设计第 5 节手写的各级缩减夹具（含只剩 `state_counts` 的摘要）；删 `legacy/` 的 `ProgressRunning`、`ProgressPlan` | 现场、图、各段 |
| 3 现场和各段 | 4.4、4.7；`tick.test.tsx` 覆盖全部块；删空 `legacy/`，连同只给旧组件用的解析。Needs you 页的 `ApprovalRow` 上那一行 `Agent-reported: …`（`partOfLine`，把引语拼进页面的句子）改用边界导出的 `<PartOfNote>`：标签加两段引语 | 图、全部计划 |
| 4 谁等谁和全部计划 | 4.5（路由、详情条、手机上的清单）；成果图的空位 | A12 的内容 |
| 5 记录器形状的验收 | 条件：记录器片 1 生成的夹具进了平台仓库；发布的文档带第 3 节列的附加块和 `events[]`。拿夹具跑本页全部测试；确认记录器设计第 5 节要的三样在 PROD | 推送来源的切换（记录器片 2） |

**`legacy/` 的清单是固定的，只减不增。** 片 1 之后恰好十个文件：`AgentWorkBoard.tsx`、`ProgressWorks.tsx`、`ProgressRunning.tsx`、`ProgressPlan.tsx`、`ProgressQuota.tsx`、`ProgressUsage.tsx`、`ProgressActivity.tsx`、`progressModel.ts`、`progressPart.ts`、`quotaModel.ts`。`legacy.ratchet.test.ts` 断言目录里的文件集合等于清单，清单的长度不超过测试里写的数（10，片 2 之后 8，片 3 之后 0）。

## 9. 已定的选择，和现有代码的去留

下面各条由统筹方按推荐定下并留痕（ADR §12.2 第 15 条）；Owner 说右列那句话就改。留给 Owner 的只有一件：A12 的五项成果和各自的级别。

| 定了什么 | 放弃了什么，为什么 | 怎么推翻 |
|---|---|---|
| **一个数，全 Console 共用**：侧栏、手机图标和本页用同一个计数函数。文档是当前的，数的是需要他的记录加声明类事项；不是当前的，两处都显示记录的数作下界（`At least n` / `n+`），不出现两个不同的数，也不单独出现问号 | 第一稿的「侧栏只数记录」：那样有声明类事项时两处的数不同，违背 A7。代价：那台电脑不发布的时候侧栏是 `n+` | 「侧栏只数记录」或「去掉侧栏的数」 |
| **命令正文不上 Console**，那一行写 `n commands on the local board (host)`。这是对 B5 在 Console 上的收窄 | 把命令发进平台：持 viewer 身份的都读得到。步骤上的 `actions[].cmd` 今天仍被发布（15:38 那一份里 2 条），本页不读 | 「在 Console 上显示命令」，那时另出一个受控的显示出口 |
| **完整的历史不在平台上**：全部计划页写明有几步不在文档里。这是对 A11 的收窄 | 平台保存历史：是新的存储和接口，归 P5、P6 | 「历史提前做」 |
| **声明类的「等你」最多琥珀**，对他的红色要有一条真实记录作证。A8 因此收窄，已告诉 Owner | 原型里声明的 `now` 也亮红：10-11 那条过期的「卡在你」就是这样来的 | 「声明的也亮红」，改 2.3 的证明 |
| **文档里的链接不显示成链接**；凡是绑定了可信记录 id 的行，都留着去那条记录的直达链接 | 分支上的 `actionLink` 和可信主机名单：今天文档里的链接只有 Console 自己的首页 | 「文档可以给链接」，要另出受控的出口 |
| 过期线用 180 秒，量生成时间 | Console 现在的「收到 5 分钟、偏差 2 分钟」：记录器设计把 180 秒列为切换的前提 | 改 2.2 那张表的一个数 |
| 只读 `owner_all`，不退回旧的四个字段；本页不放批准和回答的按钮 | 按名字去重（复核 74、78 的两处都出在合并上）；把记录的卡片嵌进本页 | 各一句话 |
| 不显示「今天做完 n」；不用颜色区分任务；「谁在做」不配图标 | 原型的三处：截断后的数；颜色的第二种含义；要从引语里认出厂商 | 各一句话 |
| 不加依赖 | 图不用布局库（`@xyflow/react` 在 `package.json` 里而 `src` 没有引用）；解析不用校验库（组合子约 150 行）；导入检查用本地规则和 TypeScript 自己的解析 | — |

**留下的**（按文件内容搬进新的片，不拣分支的提交）：`progressClock.tsx`、`progressFold.tsx`（它们用定时器和 DOM，放进 `boundary/`，经出口用）；`progressPart.ts` 的清理和按码点限长的算法；分支上经复核关掉的数值规则，改写成 `num` 的范围、`record` 的 `refine` 和 `derive` 的范围；`quotaModel.ts` 的池读数和裁定对照；分支上 18 格的读取状态表和 240 组随机的空闲用例，作为 `readMatrix` 和 `tone.table` 的种子；`needsYouGroups.ts` 的分组规则，在边界里对着原始正文重写，现有用例照搬，Needs you 页改用这一份，原来的 `groupOpenApprovals` 和 `waitingCount` 删掉。**丢掉的**：`progressSummaryModel.ts`、`NeedsYouBlock.tsx`、`ProgressSummary.tsx`、`AgentText.tsx`（它收 `string`）、`partOfLine`、`actionLink`、`waitsOnOwner(blocked)`、`readApprovalToken` 的读取退路。分支 `w31/w62-slice4` 不合并。

## 10. 风险与不保证

- **机制仍未编译。** 第 2 节的类型和选择器是按工具链版本写的；S1-0 是它们第一次真跑，做不到就改机制，不绕。
- **三条规则挡的是「忘了」，不是「判断错」，也不是有意绕路。** `tone` 那张表、字段表里一个字段登记成代码还是引语，都可能错，它们各在一个文件里，靠复核。在 `boundary/` 里加一个出口（要改 `PUBLIC.ts`）、让 `derive` 的计算函数无视输入而返回外面数出来的数、在模型里自己拼一个对象冒充结果，都做得到。
- **声明类的「等你」不会是红色**；真的只等他而那件事没有记录时，他看到的是琥珀色、一句话和 Needs you 的数。
- **那台电脑不发布时**，侧栏是 `n+`；手机图标只能显示一个数，下界为 0 时是空的，和「确切的 0」看起来一样。壳层的 `boundary/shell.ts` 把记录的原始行交给围栏之外的 Needs you 页，那一页仍是原来「每处各自记得」的写法，不在本设计的三条规则之内。
- **记录器设计要跟着补两句**（本轮只改了本文）：附加块和 `events[]` 是切换形状的前提；截断总数的规则按第 3 节的写法。`work_id` 的字符集没有核对。
- **文档给什么，本页才有什么。** 今天的形状只有 `earlier_done` 一个截断标记；今天的 `where` 是一段话，页面认不出它是三个地方里的哪一个。
- **时钟。** 过期偏向过期；`Expires … in 3 h` 用设备时钟，设备时间错了它跟着错。「一次刷新内自己变」是至多 15 秒。
- **手机上的版式没有自动测试**，只有第 7 节的走查。**片 1 到片 3 之间**，`legacy/` 里的十个旧文件仍是「每处各自记得」的写法；它们是主线上已在 PROD 的那一版。
- **TD-312 还在途中。** 本页只依赖「右上角登录后读得到身份」；它定型前片 1 用现有的能力接口，不碰审批令牌那个存储键。

## 11. 复核 84 逐条

| 发现 | 去向 |
|---|---|
| 必须改 1：围栏仍能拿到原始文本 | 2.0：导入改成按解析后路径判的允许清单；转导出由图测试管；围栏之内不读网络、存储、DOM；属性只收字面量。阳性对照点名了 `useAgentThreads`、相对路径、`legacy`、转导出 |
| 必须改 2：见证没有绑定数据 | 2.2：没有见证参数，封条在数据上，带代数和完整性；`readMatrix` 里三条点名的反例 |
| 必须改 3：颜色有普通出口 | 2.0、2.3：围栏之内引不到组件库；带颜色的组件、图形、SVG 属性都在 `tone.tsx`；阳性对照点名了 `HealthLamp`、`denseTagClass` |
| 必须改 4：取最差状态遮住已知的 | 2.2 取消合成最差状态；4.0 的表；4.1 按部分合并，失败的来源有自己的提示和重试，不知道的来源不折成 c |
| 必须改 5：不在开着的列表里不等于了结 | 4.1 的绑定表：确认终态、不再需要他、查无记录、读取失败四种分开，后两种留行并显示 Unknown |
| 应该改：核心契约未验证 | 2.0 的 S1-0，和「先改机制、不加豁免」的规则；第 8 节把它列为片 1 的第一项 |
| 应该改：动态键、带品牌的数、逐字段清单 | 2.1（没有字典组合子，`Num` 是不透明对象，只有 `<NumView>`）；第 3 节的逐字段表和 `Num` 的种类；2.0 禁 `Object.keys` 一类 |
| 应该改：现有解析会降级 | 第 3 节：从没降级过的正文解析；2.2：包络缺失或不合规得不到当前的封条 |
| 应该改：回退不是迁移契约 | 第 3 节：先按形状归一，表内不跨形状回退；截断总数一条规则；第 8 节片 2 带缩减夹具。**不保证**：记录器设计那边的两句还没有写（第 10 节） |
| 应该改：三句话各自的证明 | 4.3（`Nothing for you to do now`、工作关闭）、4.5（`Nothing is scheduled`） |
| 应该改：需求覆盖表 | 第 1 节；A1 的首屏、A4 的范围和日历时间、A5 的来源和进程类别、A11 的刚做完两步、B2 的排序、B3 的三种办法分别在 4.1、4.2、4.3、4.5 |
| 应该改：完整状态矩阵的归约 | 4.0 的表；`readMatrix` 照它断言 |
| 应该改：未来缺附加块；A10 | 第 3 节：谁继续发、缺了显示什么；`events[]` 是切换的条件 |
| 应该改：手机 | 第 5 节；第 7 节第 2 条在三个宽度上走查；4.5 的详情条 |
| 应该改：片 1 | 第 8 节：删除清单、固定的 `legacy` 清单和棘轮测试、片 1 只有两种证据、可判定的停线条件 |
| 应该改：决定 | 第 9 节：共享一个数；命令和历史写成收窄并留了推翻的话；去掉了「记录化后两个数必然相等」的说法；绑定记录的行保留直达 |
| 次要：验收措辞 | 第 6 节（一块在它读的来源变了时重绘）；第 7 节第 5、8 条 |
