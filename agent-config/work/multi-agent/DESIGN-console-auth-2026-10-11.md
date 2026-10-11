# Console 的登录令牌：一个模块持有，改状态的请求只从它的闸门发出（TD-312 的设计）

状态：**停线**（2026-10-11 16:54 CDT）。第三稿，三次复核（85、89、90），必须改的 2 → 1 → 1；第三稿是设计预算里记录在案的那一次延长，复核 90 仍有 1 处必须改的（lint 规则对几个文件整份豁免，见 `reviews/codex-2026-10-11-review90-console-auth-design-r3.md`），按事先写下的条件停。本文**不是**可以照着实现的设计；重开要 Owner 一句话。以下是第三稿原文（并入了复核 89，逐条去向见第 14 节）。
输入：`agent-config/TECH_DEBT.md` 的 `### TD-312`、`### TD-313`；已停的分支 `w31/td-312`（`56e7300`、`22b9358`，是材料，不是基线）和 `~/agent-work/td-312/` 里的任务与报告；复核 80、83、85、89（`~/agent-work/td-312/REVIEW-80.md`、`~/agent-work/codex-review-{83,85,89}/REPORT.md`）；`bifrost-platform` main `17136ba` 的 `console/src/api/{client,approvals,questions,cluster,clusterActuation,agentProgress,delivery}.ts`、`console/src/lib/platformAuth.ts`、`console/src/components/UserMenu.tsx`、`console/eslint.config.js`、`console/public/sw.js`、`console/nginx.conf`、`api/internal/actuation/auth.go`、`api/internal/approvals/{handler,service,resolve,execution}.go`、`api/internal/questions/{handler,transition}.go`、`api/internal/server/{server,questions_wire,actions_wire,auth_routes_test}.go`、`api/internal/actions/coverage_test.go`、`api/internal/operatorplane/plane.go`、`api/internal/delivery/{handler,release_window}.go`、`api/internal/cluster/data_clone.go`、chi v5.2.1 的 `tree.go`；infra 的 `k8s/cicd/tekton/pipeline-ci-platform.yaml`、`docs/SECRETS.md`；`OWNER-SURFACE-2026-10-11.md`（B3、C1、C3）。只读了文件：没有调用接口，没有打开页面，没有读凭证。文中的数和行号都取自 `17136ba` 的非测试源码。路径：`console/`、`api/` 开头的相对 `bifrost-platform/`；`agent-config/`、`k8s/`、`docs/` 开头的相对 `bifrost-trade-infra/`。
已定、本文不重新讨论（Owner 2026-10-11）：服务端三个角色（viewer、operator、admin）不变；Console 只有右上角一处输入令牌，它显示当前是哪个账号；任何页面不再要令牌。页面文字用英文、句首大写，不说 I、me。

## 1. 诊断：两类发现都来自「每个调用点要自己记得」

复核反复出的 P1 是两类：（甲）决定可以在没有 admin 会话时通过页面的闸门；（乙）令牌有路径被显示或记录。分支上的做法是每个调用点各自做对：发送前自己查角色，出错后自己清理文字。漏一处就是一个 P1。`17136ba` 上这样的调用点有多少：

| 量到的事实 | 数 |
|---|---|
| 设置 `Authorization` 的地方 | 5 个文件 9 处（`api/` 下的 `client`、`approvals`、`questions`、`cluster`、`agentProgress`） |
| 带登录令牌的调用 | `authedFetch` 19 个文件 37 处；`authHeaders()` 配裸 `fetch` 3 处；另有问题读取和角色读取。合起来约 50 条路由。裸 `fetch(` 共 30 个文件 86 处，其中 24 个文件只做不带令牌的读取 |
| 把 `Error` 的 message 显示到页面 | 约 51 个文件 73 处；`parseError` 把服务端的 `error`、`detail`、`hint` 原样拼进 message |
| 用 `localStorage` 的文件 | 13 个：2 个存令牌，11 个存界面偏好和本地状态 |
| 门禁 `ci-platform` 对 Console 跑什么 | 只有 `npx tsc --noEmit`；ESLint、vitest、构建都不在（TD-313）。`go test ./...` 在 |

由此得到四条约束。一，令牌的值只存在于一个模块的闭包里，模块不导出它。二，登录合并成一处之后，admin 令牌随所有带令牌的调用发出；（乙）类要在整个带令牌的面上过同一个边界。三，能挡住「忘了」的检查必须真的在门禁里跑。四（复核 89）：凡是要人把路由归类才安全的设计，归错一次就是一个（甲）类 P1；所以不设「决定路由」这一类，闸门按方法走，角色要求从服务端的真实路由器来。

## 2. 一个模块：`console/src/lib/session/`

它是唯一读写存储键的代码，唯一设置 `Authorization` 的代码，唯一发出带令牌请求的代码。入口只有 `index.ts`，全部公开面：

```ts
export type Epoch = number & { readonly __brand: 'Epoch' }    // 不透明：只比相等；每个标签页自己递增；不由令牌派生
export type Identity = { kind: 'signed-out' } | { kind: 'checking' } | { kind: 'not-accepted' } | { kind: 'unknown' }
  | { kind: 'role'; role: 'viewer' | 'operator' | 'admin'; principal: string | null }
export function signIn(token: string): boolean                  // false：本地拒收；任何情况下都不回显
export function signOut(): void
export function recheck(): void                                 // 「Try again」：先对账存储，再为当前纪元重读角色
export function subscribe(listener: () => void): () => void     // 本页的变化和别的标签页的变化都通知
export function getSnapshot(): { readonly epoch: Epoch; readonly identity: Identity; readonly kept: 'browser' | 'this-tab' }
export function request<R extends PlainRoute>(route: R, params: ParamsOf<R>, opts?: { signal?: AbortSignal }): Promise<Outcome<DataOf<R>, FieldsOf<R>>>
export function decide<D extends RecordRoute>(route: D, params: ParamsOf<D>): Promise<Decided<D>>   // 四条审批和问题路由：同一个闸门，多一次发送后的重读
```

**路由表是封闭的。** 调用方给的是路由名和参数对象，不是路径，也不是 URL；模块没有任何接受路径的入口。表在 `lib/session/routes.ts`，只被模块导入。每一条写明：它对应清单（第 5 节）里的哪一条方法和模式；每个参数的类型（锚定的模式、枚举或有界整数；模式的字母表不含 `/`、`\`、`%`、`?`、`#`，也匹配不了 `.` 和 `..`）；声明的查询键；请求正文的字段；路由限定的请求头契约；成功时的投影、成功判据、是否允许 204；拒绝时的字段契约（第 4 节）。**表里没有角色，也没有「这是不是决定」的标记**；四条审批和问题路由只多一个 `after` 字段，写明发送后重读哪条记录，它决定行为，不决定安全。请求头契约今天两条：问题路由的 `X-Bifrost-Session: owner-console`；`startPipelineRun` 的 `X-Agent-Session-ID`，值来自一个带模式的参数（服务端用它记启动归属，`delivery/handler.go:105`）。调用方不能设置任何别的头。审批的 id 是 `^appr_[0-9a-f]{16}$`，问题的 id 是 `^q_[0-9a-f]{16}$`。URL 在模块里由模板和校验过的参数拼出，**发送前再核一次**：用 `new URL(…, location.origin)` 解析，要求源相同、没有用户名和片段、`pathname` 与拼出的字符串逐字节相同并且匹配这条路由的模式、查询串等于声明键的规范序列化。任何一条不成立，或者路由名不在表里、参数不合类型，结果就是 `not-sent`，没有请求。

React 一侧只有 `hooks/useSession.ts`（`useSyncExternalStore(subscribe, getSnapshot)`）。现有 20 处 `usePlatformAuth()` 保留，只剩由 `Identity` 派生的 `canOperate`、`canAdmin`、`role`、`principal`、`recheck`。`lib/platformAuth.ts`、`operatorToken()`、`authHeaders()`、`authedFetch()`、`fetchAuthCapabilities()` 删除；`api/client.ts` 只留一个不碰令牌的 `orThrow(outcome)`，把非 `ok` 的结果变成 message 是 Console 句子的错误，给现有的查询用。模块内部四条规则：

1. **每个入口先对账。** `signIn`、`signOut`、`recheck`、`request`、`decide`，以及 `storage`、`pageshow`、`visibilitychange` 三个事件的处理，第一步都是读存储并和当前纪元抓住的令牌比较（读的三种结果见第 8 节），不同就开新纪元。绕过模块写存储（包括在开发者工具里手改或清空）、手机上后台标签页漏掉的 `storage` 事件，都在下一个入口被发现。
2. **开新纪元的只有一个内部函数**，一次做完：纪元加一；抓住新令牌；身份置为 `signed-out`（空令牌）或 `checking`；作废上一纪元的在途请求（读取中止，改状态的请求不中止但结果按 `unknown` 或 `discarded` 处理）；通知订阅者。壳层收到通知后取消并重置全部查询。
3. **一个页面里只有一个能发送的实例。** 模块在导入时到 `globalThis` 上用 `Symbol.for` 键登记自己的实例号；已经有登记时，后来的实例不初始化，所有发送返回 `not-sent other-instance`，并整页重载一次。每次发送之前核对登记的还是自己。开发时被热更新：`import.meta.hot.dispose` 清掉监听器、计时器、在途请求和登记，随后整页重载。Strict Mode 和挂两个 provider 只是多订阅，不会重复初始化。
4. **令牌进来只有一个口，出去没有口。** `signIn` 只收 16 到 512 个可见 ASCII 字符（`docs/SECRETS.md` 的生成方式 `secrets.token_urlsafe(32)` 给出 43 个字符），所以构造请求头不会抛出带令牌的异常。登录框是不受控的 `type="password"` 输入：提交时读一次、立刻清空。出站固定 `mode: 'same-origin'`、`redirect: 'error'`、`cache: 'no-store'`；请求正文由模块按表里的字段从参数拼出，参数里含有当前令牌就不发；读取 15 秒超时，改状态的请求 30 秒超时。模块不写日志（`no-console: error` 已在 `console/eslint.config.js` 里，源码里 `console.*` 是 0 处）。

## 3. 角色属于一次登录

- 角色由模块读，调用方读不了：`GET /api/v1/auth/capabilities` 用当前纪元抓住的令牌发出，10 秒超时；答案到达时纪元已经变了就丢弃。答案只存在模块里，和纪元存在一起；不进查询缓存，令牌和它的任何派生值都不做缓存键。
- 何时读：开新纪元时；`recheck()`；标签页可见期间每 60 秒；标签页变为可见时；当前纪元的任何请求收到 401 或 403 之后（同一时刻最多一个在途，两次之间不少于 5 秒）。
- **401 作废确认。** 当前纪元的请求收到 401，而清单说这条路由接受已确认的那个角色：这个确认刚被服务端否定，立刻作废，身份回到 `checking` 再重读，读不到答案就是 `unknown`，不会留在 `ADMIN`（服务端的角色中间件拒绝时回的是 401，`actuation/auth.go:138`、`:165`）。403 是策略拒绝（例如 `server/actions_wire.go:75` 的 `approval required`），只触发重读，不作废。
- 答案按下表变成身份。严格匹配，`principal` 只在匹配 `[A-Za-z0-9._-]{1,64}` 时保留：

| 服务端答案（HTTP 200 的 JSON） | 身份 |
|---|---|
| `authenticated: false`，存储里有令牌 | `not-accepted` |
| `authenticated: true`，`role: 'admin'`，`can_operate: true`，`can_admin: true` | `role admin` |
| `authenticated: true`，`role` 是 `operator`（`can_operate: true`，`can_admin: false`）或 `viewer`（两个都是 `false`） | `role operator`、`role viewer` |
| 以上都不是：缺字段、类型不对、角色不在三个之内（例如 `executor`、`reporter`）、角色和布尔对不上 | `unknown`，即使之前确认过 |
| 没拿到可用的答案：超时、网络失败、非 200、不是 JSON | 本纪元已有确认过且没被作废的身份就保留；没有就是 `unknown` |

- 最后一行的理由：服务端始终是最终判断，过时的确认最多换来一次 401，而那次 401 会作废它；手机网络抖一下不应该把徽章打成未知。没拿到答案的重读不会把任何身份升成角色。`checking` 最长 10 秒，之后不是角色就是 `unknown`。`unknown` 只有一种，出路固定两个：`Try again`（`recheck()`）和 `Sign in`。任何状态都不假定是 admin。

## 4. 请求只返回封闭的结果；能离开模块的类型

`request` 和 `decide` 不抛出。`fetch` 的异常、`Response.text()` 的异常、`JSON.parse` 的异常、投影函数的异常都在模块里接住，**异常对象的 message 不读、不存、不返回**。正文由模块自己读成文本、自己解析成 JSON。

```ts
type NotSent = { kind: 'not-sent'; identity: Identity
  why: 'sign-in-changed' | 'unconfirmed' | 'role' | 'route' | 'params' | 'url' | 'token-in-text' | 'other-instance' }
type Outcome<T, F = never> =
  | { kind: 'ok'; data: T }                                     // 2xx，成功判据成立；data 是这条路由的投影
  | { kind: 'refused'; status: number; code: RefusalCode; fields?: F }   // 这一次提交没有被接受
  | { kind: 'network' } | { kind: 'discarded' }                 // 没拿到 HTTP 响应（含超时）；登录变了、被取消、或被作废（第 5 节）
  | { kind: 'malformed'; status: number; why: 'not-json' | 'shape' | 'echo' } | NotSent
type Decided<D> = { sent: Sent; after: Outcome<RecordOf<D>> | null }   // after：发送结束后模块重读到的记录；没发出时是 null
type Sent = { kind: 'ok'; replayed: boolean } | { kind: 'refused'; status: number; code: RefusalCode } | NotSent | { kind: 'unknown' }
type RefusalCode = 'role' | 'forbidden' | 'not-found' | 'expired' | 'already-decided' | 'changed' | 'not-open' | 'input' | 'busy' | 'reported-failure' | 'other'
```

**能离开模块的类型**（这一段是复核 85、89 接受的写法，原样保留）：

- **错误路径**（`refused`、`network`、`malformed`、`not-sent`、`unknown`）：状态码、封闭的码、这条路由的拒绝字段契约。契约字段的类型只有：锚定模式的 id、枚举、布尔、有界整数、时间戳，以及它们的有界列表。**没有文字类型**：服务端的 `error`、`detail`、`hint`、`message` 没有任何一种类型能装着离开模块。
- **成功路径**：这条路由的投影。投影新建一个对象，只取表里声明的字段，没声明的丢掉，不返回也不展开解析结果本身。字段类型是上面那些，加上 `text(maxBytes)`。`text` 只用于记录本身就是文字的字段（审批的理由和摘要、问题的正文和答案、Pod 日志、Progress 文档里的字），每个 `text` 字段在表里点名。成功响应里的 `message`、`detail` 一类状态文字不是记录，不投影。
- **回显检查不是边界，只是绊线**：投影之后，输出里任何字符串含有这次请求发出时的令牌原样，整个响应变成 `malformed echo`。它只认原样；编码过、拆开、截断、改了大小写的都过得去。保证不建立在它上面。

能保证的是来源：浏览器和运行时产生的文字（异常 message）不离开模块；错误正文里契约没点名的东西不离开模块；离开模块的每个值都来自表里点名、类型有界的字段。不能保证的是内容：点名的 `text` 字段和有模式的短字段里，服务端放了什么就显示什么。这是记录在案的残余。

**每条路由的响应契约要有 fixture（片 1 的验收，V5）。** 每条路由存一组脱敏的真实响应：正常、空、可选字段缺失、HTTP 200 里的业务失败、204、HTML 错误页。fixture 由服务端测试生成，或从 STG 录下后脱敏，来源写在文件旁；不接受手写的。断言：200 里成功判据不成立时结果是 `refused reported-failure`，不显示成功；204 只在表里声明了的路由上是 `ok`；HTML 和错误 JSON 只产生固定的结果。

`RefusalCode` 由模块里一张表得出，键是（路由、状态码、服务端 `error` 字段的整串或表里声明的锚定前缀）。401 不看正文，是 `role`；403 没有表项时是 `forbidden`；表里没有的一律 `other`。表里的每个字符串由测试对着 Go 源码的字面量核对（`console/src/api/__tests__/approvals.test.ts` 已经这样读 Go 源码）。**`refused` 的意思是「这一次提交没有被接受」，不是「什么都没变」**：审批和问题的处理会先清扫并落盘过期状态，再回 409；别的通道也可能已经决定。页面能显示的只有 Console 自己的句子，状态码可以跟在后面：

| 成员 | 页面显示 |
|---|---|
| `ok`；`discarded` | 投影出来的记录；`discarded` 不显示任何东西，页面按当前登录重读 |
| `refused` `role`、`forbidden` | `The sign-in was not accepted for this. HTTP 401.` 加 `Sign in`；`The platform does not allow this here. HTTP 403.` |
| `refused` `not-found`、`expired`、`already-decided`、`changed`、`not-open` | `This request no longer exists.`；`This request has expired.`；`This request was already decided.`；`This request changed after the page loaded. Read it again before deciding.`；`This record is no longer open for that.` |
| `refused` `input`、`busy`、`reported-failure`、`other` | `The platform did not accept what was sent. HTTP 400.`；`The platform is limiting requests. Try again in a minute.`；`The platform reported that this did not succeed.`；`The platform did not accept this. HTTP 409.`（5xx 时：`The platform reported an error. HTTP 500.`） |
| `network`；`malformed` `not-json`、`shape`、`echo` | `Could not reach the platform.` 加 `Try again`；`The platform's answer could not be read. HTTP 200.`；`The platform's answer was discarded because it repeated the sign-in token. Replace that token.` |
| `not-sent` `unconfirmed`、`role`、`sign-in-changed` | `Who is signed in is not confirmed yet. Nothing was sent.`；`This needs the <NEEDED> sign-in. You are signed in as <ROLE>. Nothing was sent.`；`The sign-in changed in this browser. Nothing was sent.` |
| `not-sent` `token-in-text`；其余 `not-sent` | `The text contains the sign-in token. Remove it and try again.`；`This could not be sent from this page.` |

**这对片 1 的代价，直说。** 今天 37 处 `authedFetch`（19 个文件）在被拒绝时显示服务端写的原因，约 73 处把它渲染出来。片 1 之后，这些页面在被拒绝时显示按码选的固定句子和状态码，直到那条路由有字段契约；成功时的 `message` 同样换成固定句子和带类型的字段。片 1 就写好的拒绝契约只有一条：`data-clone` 的 409 保留 `missing_tables`（服务端已有这个字段）。「发布窗口被谁占着」服务端只写在一句自由文字里（`delivery/release_window.go`），片 1 的做法是拒绝之后读 `GET /api/v1/delivery/release-window`，从它的成功投影里显示持有者和到期时间。其余只存在于自由文字里的原因，要恢复就得让服务端给出带类型的字段；那是服务端改动，逐条提给 Owner，不在片 1。

## 5. 闸门按方法走；角色要求来自服务端的真实路由器

**每一个不是读取的请求走同一个闸门（复核 89 的 P1）。** 方法不是 GET 或 HEAD 的请求，不管是哪条路由、从 `request` 还是 `decide` 发，发送前在一个同步段里做完这些，中间没有 `await`：（1）核对实例登记，对账存储，变了就开新纪元，`not-sent sign-in-changed`；（2）当前纪元的身份必须是确认过的 `role`，`checking`、`unknown`、`not-accepted`、`signed-out` 都是 `not-sent unconfirmed`；（3）这个角色必须在清单为这条路由记下的接受集合里，否则 `not-sent role`；（4）参数、URL、正文里的令牌三项检查；（5）用当前纪元抓住的令牌发出。所以身份没确认时，没有任何改状态的请求离开浏览器；表项怎么写都不影响这一条。页面上的 `maySend`、`canOperate` 只决定控件的样子，不是闸门。

**GET 还能做什么。** GET 和 HEAD 带着当前纪元的令牌发出，不查身份。理由：页面在角色确认之前就要读列表和记录，角色读取本身也是一个 GET，拦住它们整个页面会空白到确认为止；服务端按令牌决定能读什么；纪元变了响应就丢弃。会改状态的 GET 是服务端的缺陷，不在本设计之内；清单测试能做的是把接受集合里没有 viewer 的 GET 逐条列出，要求带理由登记，没登记就失败（今天有几条，本文没有数）。

**清单从真实路由器生成，不手写。** `api/internal/server/` 下新增一个 Go 测试，照 `auth_routes_test.go:44–89` 的做法走真实的路由器（`srv.Router().(chi.Routes)` 加 `chi.Walk`；`actions/coverage_test.go:28` 也这样走）。chi 的 `Walk` 会把 `Group` 和 `With` 挂的中间件一起交出来（`tree.go:879`），而服务端的角色要求都是这样挂的：`auth.Require(min)` 和 `auth.RequireAny(roles…)`（`actuation/auth.go:133`、`:149`），审批和问题的 `Mount`、`server.go` 的各组、L-1 路由的 `register`（`operatorplane/plane.go:130`）都是。测试服务器用一份临时的认证文件，五个角色各一个假令牌；对每条路由，把它的中间件链包在一个哨兵外面，带每个角色的令牌和不带令牌各发一次，到得了哨兵的角色就是这条路由的接受集合。这是按行为判断，不按函数名（`auth_routes_test.go:21–32` 写明了按名字匹配会被内联打坏）。结果 `{method, pattern, accepts}` 写进 `console/src/lib/session/route-manifest.json` 并提交；路由器和文件不一致，测试失败；`go test ./...` 已经在门禁里。路由集合随配置变（问题路由在 `questionRuntime == nil` 时不挂，`server/questions_wire.go:58–62`；L-1 路由在设了 `OPERATOR_PLANE_URL` 时改成转发，`server/server.go:161–195`），所以清单取两种配置的并集，并断言审批、问题、patrol 的路由都在里面、改状态的路由不少于现有测试的下限 40 条。

**Console 怎么用清单。** 模块在运行时从清单取每条路由的接受集合，表里没有地方写它；清单里找不到的表项，运行时就是 `not-sent route`。Console 的测试要求：表里的每条路由在清单里有方法相同、模式相同的条目（代理路由是被清单里的通配模式覆盖）；清单里没有的表项失败；带 `body` 标记的表项失败。服务端新增一条改状态的路由：Go 测试先失败，重新生成清单后通过，Console 这边不用改表，那条路由从那一刻起按服务端的要求过闸门。「归错类」没有可以发生的地方。

**走不到的三样（清单比字面弱的地方）。** 它们都只会让服务端比清单更严，后果是发出去被拒绝，不是闸门放错：

1. 处理器函数体里按角色做的判断。今天只有一处是授权：`POST /approvals/claim` 在 `approvals/handler.go:231` 读角色，`approvals/execution.go:484` 的 `claimRunners` 按角色决定能领什么。其余读 principal 的地方只用于署名和审计（`opsagent/handler.go:71`、`questions/handler.go:109`、`delivery/handler.go:104`、`promote/handler.go:42`、`agentgovernance/skillrun.go:59`、`cluster/data_clone.go:1002`）。清单测试另做一次静态扫描：`actuation` 包之外读 `Principal` 的 `Role`、或调用 `Authenticate` 的每一处，必须登记在测试里的一张表中，写明 `attribution` 或 `authorization`，没登记就失败；登记为 `authorization` 的路由在清单里带 `body` 标记，Console 的表不许收。
2. 包在处理器外面、不是中间件的函数：`s.guard` 和 `s.guardIB`（`server/actions_wire.go:40`、`:86`）按审批档位回 403。
3. 通配的代理路由（`server/server.go:526–530`，例如 `/plugins/market-data/api/*`）：清单里是一条通配模式，下游插件自己的规则看不到。

**四条审批和问题路由多出来的行为**（不是它们安全的原因）。「结果未知」：请求已经交给 `fetch`，但拿到的既不是合格的 2xx，也不是 4xx——网络失败、30 秒超时（之后服务端可能仍在执行，`console/nginx.conf` 的 `proxy_read_timeout` 是 300 秒）、5xx、2xx 但正文不可读、响应到达时纪元已变。模块为每条记录记一个代次，`decide` 在发送开始和结束时各加一；对这条记录和它所在列表的读取，开始和结束时代次不同，结果就是 `discarded`，所以发送之前或期间开始的 GET、查询缓存里的旧 `pending` 都不能当恢复的依据。发送结束之后（`ok`、`refused`、`unknown` 都一样）`decide` 自己发一个新的 GET 读这条记录，绑定当时的纪元，不经过查询缓存，结果放在 `after` 里。页面收下记录只走一个函数（问题页已有 `acceptQuestionRead`，审批页照做）：已经显示终态的记录不被非终态的读取替换。

**发送之后的句子只陈述记录（V4）。** 页面不说这次提交造成了什么，只说记录现在是什么、谁、哪个通道、什么时候，这些都取自记录的字段：`The record shows <STATUS>, decided through <channel> at <time>.`；问题是 `The record shows answered by <by> through <channel> at <time>.`。`sent` 是 `ok` 时前面加 `The platform accepted this submission.`，`replayed` 为真时改成 `The record already held this answer.`；`refused already-decided` 时前面是 `This request was already decided.`。页面上没有「你的决定已保存」这类话。`after` 不是 `ok`（重读失败或超时）就仍然是未知：不提供任何决定控件，显示 `The result is not known. The decision may have been applied.` 和 `Check again`。重读到的记录仍然可以决定时（审批 `pending`、未关闭的 `unknown`、问题 `open`），控件回来，加一句 `The record still shows <STATUS>. The earlier attempt was not applied, or has not finished.`。再点一次不会重复执行，靠的是服务端：approve 在执行动作之前，在同一次存储更新里让记录离开 `pending`——平台 runner 落成 `running`，外部 runner 落成 `approved`（`approvals/service.go:409`、`:419`，`approvals/execution.go:68`）——已决定的记录再决定回 409。

## 6. Owner 和 operator 在点之前看到什么

徽章在右上角，句子紧挨控件；两处读同一个快照。条件不满足时控件仍然显示，但不发送。右上角菜单里写 `Signed in as <principal> · <ROLE>`；输入框只在这个菜单里，所有 `Sign in` 都是打开它（分支上的 `lib/signInRequest.ts` 可以照用）。句子里的角色由实际身份填入。Needs you 顶部加一行：admin 时是 `This browser can submit decisions.`，否则是下表的句子；它只说明这个浏览器现在发得出决定，不说明服务端会接受，也不说明别的通道的状态（C1）。记录页不再问令牌（B3）。

| 状态 | 徽章 | 控件旁的句子 | 出路 |
|---|---|---|---|
| admin | `ADMIN` | 没有句子，控件可用 | — |
| operator 或 viewer | `OPERATOR` 或 `VIEWER` | `Deciding needs the admin sign-in. You are signed in as <ROLE>.` | `Sign in` |
| 没有登录 | `SIGNED OUT` | `Deciding needs the admin sign-in. Nobody is signed in.` | `Sign in` |
| 正在确认（最长 10 秒） | `…` | `Checking who is signed in…` | `Sign in` |
| 角色未知 | `UNKNOWN` | `Could not confirm who is signed in.` | `Try again`、`Sign in` |
| 令牌已被替换，角色读取先发现 | `NOT ACCEPTED` | `The sign-in at the top right was not accepted. It may have been replaced. Sign in again.` | `Sign in` |
| 点了之后服务端以 401 拒绝 | 先是 `…`；重读的答案决定它变成 `NOT ACCEPTED`、实际的角色，或者读不到答案时的 `UNKNOWN`。不会停在 `ADMIN` | `The sign-in at the top right was not accepted as admin. It may have been replaced. Sign in again. HTTP 401.` | `Sign in`；`UNKNOWN` 时另有 `Try again` |
| 登录在这个浏览器里变了，没有发出 | 新的身份 | `The sign-in changed in this browser. Nothing was sent.` | 按新身份 |
| 网络失败（读记录或读角色） | 不变 | `Could not reach the platform.` | `Try again` |
| 结果未知 | 不变 | `The result is not known. The decision may have been applied.` | `Check again` |

**operator 页面的变化，直说。** 它们的每个改状态的操作（节点、工作负载、交付、插件）现在都要等身份确认。正在确认时按钮旁是 `Checking who is signed in…`，点了得到 `Who is signed in is not confirmed yet. Nothing was sent.`，通常一次往返、最长 10 秒；角色确认不了时是 `Could not confirm who is signed in.` 加 `Try again` 和 `Sign in`，在那之前这个浏览器发不出任何操作。今天这些按钮已经由 `canOperate` 控制，它在角色读到之前同样是假；变的是这条规则从每个页面搬进了模块，页面漏掉也发不出去，以及 401 之后已确认的身份会作废。

## 7. 怎么保证没人能「忘了」

| 层 | 挡住什么 | 今天在门禁里吗 |
|---|---|---|
| 类型（tsc） | 令牌没有导出；旧的导出已删除，残留的用法编译不过。`request` 和 `decide` 没有路径参数，路由名是表的键。显示结果的 `switch` 用 `never` 收尾 | 在 |
| Go 测试（片 1 新增，在 `api/internal/server/`） | 清单和真实路由器一致；函数体里读角色的每一处都已登记；接受集合里没有 viewer 的 GET 都已登记；不带令牌能到达的改状态路由为 0（现有的 `TestEveryMutatingRouteRequiresARole`） | `go test ./...` 在 |
| ESLint（`console/eslint.config.js`，只用核心规则） | `no-restricted-globals` 和 `no-restricted-properties`：`fetch`、`XMLHttpRequest`、`EventSource`、`WebSocket`、`navigator.sendBeacon`、`localStorage`、`sessionStorage`（含 `window.`、`globalThis.` 写法），对 `src/**` 生效。`no-restricted-imports`：`@/lib/session/` 之下除入口以外的文件，以及用相对路径导入入口。两张冻结名单关掉对应规则：仍有不带令牌的裸 `fetch` 的文件、11 个用 `localStorage` 存别的东西的文件。模块目录和测试文件豁免 | 不在 |
| 源码扫描和契约测试（vitest，用 TypeScript AST，照 `lib/__tests__/noMutationInEffect.test.ts` 的做法） | 模块目录之外：没有等于两个存储键的字符串；没有等于 `authorization`（不分大小写）的字符串或属性名；没有以 `Bearer ` 开头的字符串或模板；没有 `addEventListener('storage'`；没有针对上一行规则的 `eslint-disable`。旧键在模块里只出现一次，在 `removeItem` 的参数里。路由表对清单（第 5 节）；`text` 字段的清单和条数对着基线；错误路径的契约里没有 `text`；表里没有角色字段。`public/sw.js` 仍然不处理 `/api/` | 不在 |

**门禁是片 1 的前置条件（TD-313），顺序写死：**（1）Owner 把加了 `npm run lint`、`npx vitest run`、`npm run build` 的流水线定义应用到集群；（2）在 main 上证明它会拦：一个故意让 Console 测试失败的提交被 `ci-platform` 判失败，下一个提交恢复后判成功，记下 main 的 SHA、流水线定义的版本、两次 run 的名字；（3）在这之后才产生片 1 的第一个候选。今天不存在已经生效的保证；即使实现了，tsc 也只约束类型。这些检查挡的是忘记，挡不住有意绕过（例如运行时拼出键名）。实现时登记进 `agent-config/RATCHETS.md`。

## 8. 存储与迁移

- **读存储有三种结果**：读到值；键不存在；读取失败（抛异常）。键不存在就是没有登录，开 `signed-out` 的新纪元。**读取失败既不当作没变，也不当作退出了别处：模块放下令牌**，开 `signed-out` 的新纪元，进入「只在本标签页」方式（`kept: 'this-tab'`）。
- **只在本标签页的方式**：`signIn` 写存储失败、写后读回不一致、上一条发生、或 `signOut` 删除失败时进入。令牌（可以是空的）只在闭包里，**不对账存储，不处理 `storage` 事件**；菜单里写 `This sign-in lasts until this tab is reloaded.`。离开它只有两个口：`signIn` 时写入并读回成功，或者重载。
- **`signOut` 删不掉存储里的值时**：本标签页进入空令牌的「只在本标签页」方式，直到显式登录或重载。之后的 `recheck`、定时的角色读取、可见性事件、任何请求，都不会把存储里那个旧令牌再拾起来（V6）。存储里的值可能还在，重载后会被读到（第 13 节）。
- **页面级的旧键 `bifrost-ops-approval-token`**：模块初始化时删除，之后每次收到这个键的 `storage` 事件再删一次。任何代码都不读它。
- **登录键保持 `platform_operator_token`，值的格式不变。** 理由：已登录的浏览器（包括手机）发版当天不用重新输入 admin 令牌；还开着旧版的标签页和新版标签页继续通过同一个键看到彼此的登录变化；改名会把旧值留在原处，旧标签页还会把它写回来。代价：名字里是 operator，里面可能是 admin 令牌。
- **发版时开着的标签页**：Console 没有懒加载分包（`lazy(` 0 处），旧标签页完整运行旧代码直到重载；service worker 对页面是 network-first，联网重载就是新版。旧标签页的页面级令牌被新版删掉后，它的决定会像没存过令牌那样要求输入；在旧标签页里再输入会写回旧键，新版标签页收到事件再删。发版说明和 `docs/SECRETS.md` 写一句：发版后重载所有开着的 Console 标签页。

## 9. Owner 接受的取舍，直说

- **以 admin 登录期间，这个浏览器发出的每一个带令牌的请求都带着 admin 令牌**：约 50 条路由，包括每 60 秒一次的角色读取。此前只把 admin 令牌填进页面输入框时，它只随四个决定调用发出，另有三个文件的读取在没有登录令牌时回退到它（`api/approvals.ts`、`api/questions.ts`、`api/agentProgress.ts`）。
- **仍然限制暴露面的**：只发往同源、表里有的路由，浏览器不跟随重定向；不进 URL，不进请求正文；不进 React state，不进查询键和查询缓存，不进日志；模块不导出它，所以其余的裸 `fetch` 带不上它；service worker 不处理 `/api/`（`public/sw.js`）。
- **这个设计不防**：在页面里运行的脚本（XSS、被污染的依赖、浏览器扩展）——它能直接读 `localStorage`，也能包住 `fetch`，而 `console/nginx.conf` 今天没有下发 CSP；共用或没锁屏的设备——登录一直保留到点 `Sign out`；浏览器开发者工具、导出的 HAR、代理和服务端日志里的请求头。

## 10. 测试

令牌用一个显眼的哨兵值。断言不逐例手写：对生成的矩阵里每一格做同一组检查。每一格用 `vi.resetModules()` 重新导入模块，模块没有只给测试用的导出。复核 80、83、85、89 的每条发现各留一条具名测试。

- **模块层矩阵（不渲染页面，全量）**：角色答案（没有令牌、读取中、三个角色、`authenticated: false`、缺字段、矛盾的布尔、未知角色、非 200、非 JSON、超时）× 令牌变化的时机（不变；点之前在本页 `signIn` 或 `signOut`；别的标签页改了且事件已到；别的标签页改了但事件没到；绕过模块直接写存储；请求在途时变）× 网络层的每种结局（合格的 2xx；2xx 非 JSON；2xx 形状不对；401；403；表里有的 409；500；`fetch` 以 message 含令牌的 `TypeError` 拒绝；`AbortError`；超时；`text()` 以含令牌的异常拒绝；投影抛出含令牌的异常；重定向）× **表里每一条改状态的路由**，外加一条记录读取。每一格断言：哨兵不在返回值、`getSnapshot()`、模块全部导出的深度遍历、`console.*` 的任何参数（spy）、`unhandledrejection`、任何请求的 URL 和正文、除登录键之外的任何存储键里；**发出过改状态的请求，当且仅当发送那一刻的身份是当前纪元确认过的角色，并且这个角色在清单为那条路由记下的接受集合里**；每个发出的请求的方法和 `pathname` 正好匹配清单里的一条，带 `mode: 'same-origin'`、`redirect: 'error'`、`cache: 'no-store'`。
- **清单的阳性对照（复核 89）**：（a）Go 侧：测试里给路由器多挂一个包，它注册一条 admin 的改状态路由；清单测试失败，重新生成后通过。（b）Console 侧：用那份重新生成的清单，路由表不改；给模块一条指向新路由的表项，不写任何角色信息，在 `checking`、`unknown`、operator 三种身份下调用，请求数为 0；admin 确认后发出。（c）对一条不是那四条的改状态路由（例如节点 drain），在 `checking` 时调用，请求数为 0。（d）表项指向清单里没有的路由、或带 `body` 标记的路由，Console 的测试失败。
- **路径（甲，复核 85）**：身份是 `checking`、`unknown`、operator，存储里放着 admin 令牌。对每条改状态的路由，把 id 换成 `.`、`..`、`./x`、`x/../y`、`%2e`、`%2f`、`%5c`、`a/b`、`a\b`、`a?b=1`、`a#b`、带空字节的串、完整的 URL、`//host/x`、大写十六进制、编号、数组和对象；路由名换成表里没有的串和一条路径；查询里加没声明的键；请求头参数里放换行。每一种都是 `not-sent`，`fetch` 调用数为 0。
- **令牌的变形（乙，复核 85）**：把令牌的原样、base64、百分号编码、十六进制、拆进两个字段、截断、改大小写这七种形式，放进拒绝正文的 `error`、`detail`、`hint`、`message` 和没声明的键，放进成功正文里没声明的键，放进异常的 message。断言七种形式都不在任何输出里，并且后六种的结果不是 `malformed echo`：拦住它们的是类型和契约，不是绊线。对照（记录已知的限度）：改了大小写的令牌放进一个点名的 `text` 字段，它会原样出来；这条测试断言的就是这个现状。
- **契约和 fixture（V5）**：错误码表对 Go 字面量；每条路由的 fixture 六种情形（第 4 节）；同一个答案重放（200、`replayed: true`）是 `ok`；不同的答案（409）是 `refused already-decided`；过期（409）是 `refused expired`，随后重读到的记录是 `expired`；别的通道已决定（409）是 `refused already-decided`。
- **恢复和文案（V4，页面测试）**：查询缓存里有旧的 `pending`；发送之前开始、之后才到的 GET；发送期间开始的 GET；原来的 POST 在超时之后才完成——四种情形下页面都不凭旧读取恢复控件。别的通道先决定、相同答案重放、不同答案冲突——三种情形下页面显示的是记录里的状态、通道、时间和署名，文中没有 `saved` 也没有把结果归于这次提交的话。重读失败或超时：仍是未知，没有决定控件，有 `Check again`。
- **存储和实例（V3、V6）**：同标签页 `localStorage.clear()`；初始化时读取抛异常；读得到之后变成抛异常；`signIn` 写入抛异常；`signOut` 删除抛异常之后依次触发 `recheck`、60 秒定时器、`visibilitychange`、一个改状态的请求，令牌始终是空的，请求数为 0。同一页面导入模块的第二个副本：它的所有发送都是 `not-sent other-instance`；第一个实例退出后第二个副本仍发不出。生产构建的产物里登录键的字面量只出现一次。挂两个 provider、Strict Mode 双渲染、热更新后旧实例的监听器和计时器为 0。
- **页面层矩阵（真实的壳层、QueryClient、请求页、问题页和一个 operator 页；成对缩减）**：每种身份 × 每种决定；admin × 每种网络结局 × 每种决定；每种令牌变化时机 × approve；operator 页在 `checking` 和 `unknown` 时点操作。每一格断言哨兵不在 `document.documentElement.outerHTML`、每个 `input` 和 `textarea` 的 `.value`、`QueryCache` 与 `MutationCache` 的全部内容（含 error）、问题发送 store、`document.title`、`location.href` 里；条件不满足的格子里改状态的请求数为 0；显示的句子是第 4、5、6 节的原文，角色词与实际身份一致；401 之后徽章不是 `ADMIN`；登录提交后输入框为空。

## 11. 分片、验收、代价、停止条件

| 片 | 内容 | 上线后 PROD 上有什么 |
|---|---|---|
| 1，一起交付，分两批复核 | **批 A（模块和清单）**：`api/` 下的清单测试和它的两张登记表（不改服务端行为）；`lib/session/`、清单文件、审批、问题、Progress、角色读取的表项、`useSession`、登录框和徽章、第 7 节各层检查、模块层测试。**批 B（调用点迁移）**：其余约 40 条路由的表项、投影和 fixture；37 处 `authedFetch` 和 3 处 `authHeaders` 改成按路由名调用；请求页、问题页、Needs you 改走 `decide`；删掉页面级输入框、旧键和旧导出；页面层测试 | Owner 的决定完整落地：一处登录，徽章显示账号，任何页面不问令牌。身份没确认时没有改状态的请求离开浏览器；错误路径上没有服务端文字 |
| 2 | 给需要的 operator 路由逐条补拒绝字段契约（服务端要先给出带类型的字段的，逐条提给 Owner）；裸 `fetch` 名单收缩 | operator 页面在被拒绝时重新显示具体原因，来源是带类型的字段 |

**片 1 的具名验收**：V1 清单测试和它的阳性对照（第 10 节 a、b、d）；V2 身份未确认时任意改状态路由零请求（第 10 节 c 和矩阵）；V3 一个页面只有一个能发送的实例；V4 发送之后的句子只陈述记录；V5 每条路由的响应 fixture 六种情形；V6 退出后不再拾起存储里的旧令牌；V7 STG 上用手机完整走一遍批准，逐项看入口在不在、句子是否紧挨控件、控件是否真的可点，并把每个 operator 页面走一遍。

**片 1 的代价**：约 50 条路由各写一条表项、一个成功投影和一组 fixture；约 20 个文件里 40 处调用点要改；operator 页面在被拒绝时失去服务端写的原因，成功时失去服务端的状态文字，换成固定句子（第 4 节末）；operator 的操作要等身份确认（第 6 节末）。风险：投影写得比真实响应严，页面就从能用变成 `malformed`，由 V5 和 V7 两道一起挡。A 可以单独复核，不能单独上线；B 延误则整片不发，PROD 上不出现两个令牌入口。

**前置和顺序**：TD-313 按第 7 节的三步完成；上 PROD 之前先实测会话里的批准通道——这次发版改的正是批准发版的那条路，上线后如果决定发不出去，下一张单（回滚或修复）要靠那个通道，而它还差一次真单实测（OWNER-SURFACE 的 C1）。

**停止条件（先写下）**：实现的复核额度是两轮，从完整的 A+B 候选在已经验证过的门禁上通过之后算起；批 A 可以先单独复核，不占起点。复核发现（甲）或（乙）类的 P1 时，先回答「第 7、10 节的哪一道检查本该拦住它」：补上那道检查并让它在修复之前失败，再修代码，算一轮。第二轮之后仍有这两类 P1，或者实现中发现必须改服务端的行为、必须加依赖、必须给模块加导出才能做完，就停下，回到本文。

## 12. 以后再做，现在不做：降低设备上的风险

短期会话、锁定、敏感操作之前重新认证，三者一起降低共用或没锁屏的设备带来的风险；单独哪一样都不解决它。passkey（Touch ID、Face ID）是「重新认证」的一种做法，也让令牌只留给机器，但它本身不结束设备上已经存在的会话。这些都是架构级的改动，由 Owner 决定，本文不设计。它们需要：服务端新增注册和登录的路由（WebAuthn 的挑战与验证）和每台设备的公钥凭据存储；登录后签发短期会话，取代浏览器里长期保存的 admin 令牌；批准这一类动作之前再认证一次；Console 在 HTTPS 和固定主机名下访问（WebAuthn 只在安全上下文里可用，凭据绑定域名；Console 现在用什么地址访问，本文没有核实）；设备丢失时的恢复（至少登记两台设备，另留一条只在终端里可用的应急途径）；审批记录里「谁批的」从令牌的 principal 变成人。

## 13. 留给 Owner 的决定；本文按推荐定下的；不保证的

**Owner 的决定（两项，都不挡片 1）**
1. **要不要做第 12 节那一组（短期会话、锁定、敏感操作前重新认证，passkey 是其中的做法）。** 选项：做，单独立项、单独设计；不做，admin 令牌继续长期留在浏览器里。推荐：做，排在片 1 上 PROD 之后。在那之前设备风险是明说的取舍，没有被解决。
2. **admin 登录在一个浏览器里保留多久。** 选项：一直到点 `Sign out`（今天的行为）；关掉标签页就失效（手机上每条通知开一个新标签页，每次批准都要重新粘贴令牌）；闲置若干小时后失效（只在闲置之后要重新粘贴）。推荐：保持今天的行为，作为明确接受的取舍，等第 1 项落地再收紧。

**本文按推荐定下、统筹方或 Owner 可以推翻的**：片 1 在 `api/` 下加一个测试和它的登记表，不改服务端行为；成功响应里的状态文字不投影；登录键不改名；没拿到答案的重读不降级已确认的身份，401 除外；存储读取失败就放下令牌；`signIn` 的长度下限 16（手工造的更短的令牌会登不上）。没有不可避免的服务端行为改动，没有新依赖。

**不保证的**
1. 第 9 节「不防」的三条；旧标签页在重载之前仍是旧行为。
2. 点名字段的内容。`text` 字段（审批理由、问题正文、日志）和有模式的短字段（`principal`、名字）里，服务端放了令牌或它的变形，页面就会显示；绊线只认原样。
3. 清单看不到的三样（第 5 节）：函数体里的判断靠登记表，登记表靠静态扫描认得出的写法；处理器外面的包装和下游插件的规则不在清单里。它们让服务端比清单严，不让闸门放错。GET 不过身份检查。
4. TD-313 完成之前，第 7 节后两层不拦合并；各层都不拦有意绕过。
5. 服务端的行为是读源码得出的，没有实测：令牌被替换后回 401 `admin token required`（TD-312 也写了未测）；approve 在执行之前让记录离开 `pending`；已决定的记录再决定回 409；同一个答案重放回 200。这些如果不成立，页面靠发送后的重读纠正显示，但「再点一次不会重复执行」就不成立。
6. 存储写不进去时，`signOut` 只对本标签页生效到重载为止；存储里的值要等能写的时候再删，或者由 Owner 清浏览器数据。
7. 句子和入口在手机、桌面上是否醒目、是否紧挨控件、是否可点，测试不覆盖，只有人看页面才能确认（V7）。

## 14. 复核 89 逐条

| 发现 | 怎么改的 | 在哪 |
|---|---|---|
| P1 新增挂载处的决定路由被标成 `action` 就漏过（甲） | 去掉会标错的那个分类：每个非 GET 请求过同一个闸门，身份没确认就不发；角色要求不手写，来自从真实路由器生成的清单；清单看不到的三样逐条写明；四个阳性对照 | 第 1、2、5、7、10 节 |
| P2 `signOut` 删除失败后可能重新拾起旧令牌 | 进入空令牌的「只在本标签页」方式，不再对账存储，直到显式登录或重载；验收覆盖 `recheck`、定时器、可见性事件和改状态的请求（V6） | 第 8、10 节 |
| P2 两个 bundle 或不同模块标识可能有两个实例 | `globalThis` 上登记实例号，后来的实例拒发并重载，每次发送前核对；构建产物里登录键只出现一次（V3） | 第 2、7、10 节 |
| P2 恢复读取不能证明是这次提交造成的 | 发送之后的句子只陈述记录的状态、通道、时间和署名；`replayed` 单独一句；重读失败仍是未知；三条页面测试（V4） | 第 4、5、10 节 |
| P2 走遍 STG 盖不住约 50 条投影 | 每条路由六种情形的脱敏 fixture，来源是服务端测试或 STG 录制；200 里的失败是 `reported-failure`；204 要声明（V5） | 第 4、10、11 节 |
| P2 TD-313 的顺序没写死 | 三步：Owner 应用；在 main 上用一红一绿证明并记下 SHA、定义版本、两次 run；之后才出候选；额度从通过该门禁的完整 A+B 候选算起 | 第 7、11 节 |
| P3 `X-Agent-Session-ID` 会悄悄丢掉；`§5` 的状态名不对 | 保留，作为路由限定、带模式的请求头契约；状态名改成平台 runner `running`、外部 runner `approved` | 第 2、5 节 |

复核 85 那一轮改了什么（第二稿，保留至今）：调用方只给路由名和带类型的参数，URL 在模块里拼并在发送前核对；拒绝正文透传删除，错误路径没有文字类型，成功走逐路由投影，回显检查降为绊线。
同一轮还定了：`refused` 只表示这次提交没被接受；恢复读取由模块在发送后做；存储读的三种结果；门禁列为前置；设备风险写成明确的取舍。
