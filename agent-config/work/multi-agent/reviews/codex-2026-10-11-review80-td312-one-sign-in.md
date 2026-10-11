# Codex 复核 80 — TD-312：Console 只留一处登录（`17136ba..56e7300`）

2026-10-11 15:33 CDT · 只读

统筹方处理：先改。2 处必须改的，都在页面一侧、服务端仍会拒绝：角色的缓存没有绑定到那一次登录（操作员 → 管理员 → 操作员之后，页面的闸把操作员当成管理员放行）；换号后旧令牌可能出现在报错里（模拟的回显场景）。这两处正是任务书里事先点名的两类，按规则给一轮修（`TASK-2.md`：每次换登录算一个新的「登录轮次」，角色只对那一轮有效；被拒时只显示 Console 自己的话）。下次复核再出现同类就停线，令牌在 Console 里的做法先出设计。

---

VERDICT: fix first

P1 · `console/src/hooks/PlatformAuthProvider.tsx:24`、`console/src/lib/decisionAuth.ts:94`：能力缓存未绑定实际查询令牌。
最小复现：operator → admin → operator。登录先更新存储，再使旧查询失效；查询函数读取新令牌，把 admin 能力写入 operator 缓存。切回 operator 时，缓存仍显示 admin，门闩放行 operator 令牌。
纯内存 QueryObserver 复现得到 `role=admin, gate=admin, allowed=fake-operator`；发送函数的头部比对也会通过。服务器仍会拒绝，未发现服务端越权。
最小修复：能力请求使用查询键对应的固定令牌；返回结果与该令牌绑定，禁止其他身份的缓存参与决定。

P1 · `console/src/lib/decisionAuth.ts:34`、`console/src/pages/DecisionHold.tsx:32`：换号或退出后，旧管理员令牌的响应过滤失效。
最小复现：沿用现有反射响应测试，以 A 发出请求，在响应前退出，再返回 `admin token required A`；过滤器只检查当前令牌，原文 A 会进入页面。
纯内存复现确认退出后返回未过滤原文；这是模拟响应场景，未观察到真实服务器泄露。
最小修复：在请求边界按发送时的令牌净化错误，再保存到状态；最简单是角色拒绝不展示原始详情。

P2 · `console/src/pages/DecisionHold.tsx:24`：未知角色没有恢复指引。
最小复现：能力查询失败；控件禁用，只显示 Unknown，没有登录、重试入口或下一步说明。
最小修复：未知状态也提供现有 Sign in 入口，并说明重新登录或重试能力查询。

其余核对：platform 提交仅修改 `console/`；infra 提交仅修改 `docs/SECRETS.md`；无新依赖，修改后文件均未超过 800 行。
源码与现有构建产物中，旧键只用于删除；没有旧令牌读取或发送路径。
决定请求使用同源相对路径与原有 Authorization 头；未发现令牌进入外链、图片、遥测或通知 relay。登录密码框保护未减弱。
operator 读取路径保留；列表失败仍显示 Unknown，没有把读取失败转换成空列表。
轮换文档包含浏览器、手机、本机工具配置、重启及 ADMIN 徽章检查；工具配置完整接线未能独立核验。

only a person looking at the page can check
手机与桌面的登录入口是否醒目、拒绝提示是否紧邻控件，以及轮换后每个浏览器的徽章是否显示 ADMIN；本次未打开页面。

验证限制：完成源码、构建产物检查及纯内存复现；未重跑完整测试或构建，React/jsdom 验证因 `SecItemCopyMatching` 失败未完成。
本机 PreToolUse 闸门拒绝了管理员配置名称搜索及模拟批准调用，理由是防止审批旁路；未绕过，改用不发送请求的门闩验证。
END OF REPORT