# Codex 复核 83 — TD-312 第 2 轮：角色绑定到一次登录；被拒时不显示服务端原文（`56e7300..22b9358`）

2026-10-11 15:59 CDT · 只读

统筹方处理：**停线**。复核 80 的两处必须改的都关了；又找到一处同类的——决定请求的网络异常和成功响应的解析异常没有经过过滤，异常文字被存进状态并显示（模拟场景：异常文字里带着令牌）。停线条件写在 `TASK-2.md`，复核明确回答成立，照办：分支 `w31/td-312` `22b9358` 不合并。Owner 2026-10-11 定的目标（Console 只在右上角登录一处）不变，改成先出令牌模型的设计：令牌只由一个模块保管、不对外给出值；请求只返回封闭的几种结果，不带任何来自网络的文字；角色的核对在发送时由那个模块自己做。设计在写，过 Codex 复核后再实现。

---

VERDICT: fix first
STOP CONDITION: met

Review 80 三项：
- P1 缓存串号：已关闭。`console/src/hooks/PlatformAuthProvider.tsx:45` 按纪元查询、捕获令牌并丢弃迟到答案；`console/src/lib/decisionAuth.ts:93` 在发送前复核纪元及活令牌。
- P1 退出后反射旧令牌：原复现已关闭。`console/src/lib/decisionAuth.ts:51` 将 401/403/角色拒绝转换为状态标记；其它 HTTP 错误按发送时令牌净化。
- P2 未知角色死路：部分关闭。`console/src/pages/DecisionHold.tsx:28` 仅给查询失败提供两个入口，其它未知状态仍缺恢复控制。

新发现：
P1 · `console/src/api/approvals.ts:159`、`:165`：网络异常和成功响应的 JSON 解析异常绕过净化。
最小复现：以模拟管理员令牌 A=`ADMIN_A!` 发起决定，返回 HTTP 200、正文为非 JSON 的 A；解析异常可包含 A，经 `console/src/pages/ApprovalsPage.tsx:578` 保存，`:607` 渲染。resolve 同样经 `:594` 保存、`:242` 渲染。
网络拒绝若异常消息含 A，也走相同未过滤路径；换号或退出不改变结果。此为源码追踪的模拟响应场景，未观察真实服务器泄露。
最小修复：在捕获发送令牌的请求边界覆盖 fetch 与 JSON 解析异常，返回固定安全提示；保留决定结果未知的处理语义。
因此触发预先约定的停止条件：该 lane 应停止，先设计 Console 令牌模型。

P2 · `console/src/pages/DecisionHold.tsx:28`、`console/src/lib/decisionAuth.ts:141`：未知状态的恢复入口不完整。
最小复现：能力接口 200 返回 authenticated=true、role=admin、can_admin=false；门禁为 unknown，但没有 Try again 或 Sign in。
缺失 role 且 can_admin=false 时，`:142` 将其归为 known/UNKNOWN，仅有 Sign in，没有重试。
最小修复：将缺失或矛盾角色统一视为未知，并为持续未知状态提供两个恢复入口；两者不得发送决定。

P2 · `console/src/lib/platformAuth.ts:13`、`:23`：同标签页直接改令牌或 clear override 不启动新纪元。
最小复现：挂载后直接调用 setter 换成 operator；没有同页 storage 事件，门禁因活令牌不匹配而阻止发送，但重试仍查询旧纪元捕获的令牌（`console/src/hooks/PlatformAuthProvider.tsx:79`）。
最小修复：所有令牌写入、清除统一通知认证状态并启动纪元；重试前校准存储身份。

其余核对：operator→admin→operator、迟到答案及重试竞态经源码追踪未发现非管理员令牌通过门禁；查询键不含令牌。
双标签页切为 operator 后，事件处理前发送复核已阻止旧门禁放行；事件处理后进入新纪元，读取使用 operator 令牌。
Strict Mode 回拨要求相同令牌且仅首次执行，未找到借此将 admin 能力转给 operator 的路径；导航及热更新未做运行验证。
问题回答的网络/解析异常不保存原始消息（`console/src/pages/question/useAnswerSend.ts:137`）；401/403 丢弃正文，500 按发送令牌净化。
operator 列表读取保留；失败仍是 Unknown（`console/src/pages/shell/needs-you/useNeedsYou.ts:30`）。范围仅 `console/`，无新依赖，修改文件最大 640 行。
验证限制：内存 DOM 初始化报 `SecItemCopyMatching failed -50`，未能重跑真实 provider/query client；采用源码追踪。未写文件、调用 HTTP、打开页面或读取凭据。

only a person looking at the page can check
手机及桌面的提示、登录和重试入口是否醒目，拒绝提示是否紧邻操作控件；本次未打开页面。
END OF REPORT