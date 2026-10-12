# Codex 复核 100 — TD-310 冻结协议第一片：规则写成代码、有限模型、清单文件（分支 `w31/td-310-s1`，platform `daad692`、infra `3893968`）

2026-10-11 19:19 CDT · 只读

统筹方处理：按第一片开工前写下的条件停线（复核的那一个问题得到的回答是「找到反例」），分支不合并、留着接着用；先修订设计，再做第 2 轮。反例：Python 的判定接受 `NaN` / `Infinity`，把不是合法 JSON 的正文当成完整的空清单；Go 拒绝。另有 7 处应该改的，其中两处同样实在：`metadata.remainingItemCount` 为 1 的空清单两边都放行；Go 的读取跟随重定向。规则本身（有记录即冻结，一次完整成功的 LIST 返回零条才算未冻结）没有被推翻；洞都在「什么算一次完整、成功的 LIST」上——设计没有给它下定义，任务书靠列举坏情形把它「写精确」，列举总会漏（教训第 92 行）。修订的方向：只定义可以接受的那一种形状，封闭世界——顶层键恰好是 `apiVersion`、`kind`、`metadata`、`items`，`metadata` 的键只许 `resourceVersion` 和空的 `continue`，严格 JSON，数字不转换，不跟随重定向，读取函数对任何输入都给出结论、不抛异常；不在这个形状里的一律 `unreadable`。实测：本集群（v1.35.5+k3s1）一份真实 LIST 的顶层键和 `metadata` 键正是这几个。修订由 Cursor 起草（当天 Claude 每周额度 91%），Codex 复核。统筹方自己的重跑（`~/agent-work/td-310-s1/VERIFY.md`）：模型两遍状态数 963、转移数 134,984 一致；竞态检查通过；种下的 7 处故意错误全部被测试拦住；唯一不过的是时间——这个包在 CI 的限制下 66.6 秒，超过 60 秒的余量，第 2 轮一并压。重跑没有发现复核找到的那个反例：我种的错误都在 Go 一侧和清单上，没有想到 Python 解析器的默认宽松——验收和独立复核各自拦住了对方拦不住的。

---

VERDICT: fix first
COUNTER-EXAMPLE TO THE RULE: found

- **P1 — infra `scripts/release/freeze_gate.py:99`**：HTTP 200，正文 `{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{},"items":[],"x":NaN}`，实测返回 `clear`；这不是合法 JSON，更不是完整、良构的空 LIST。`Infinity` 同样放行，Go 会拒绝。最小修复：禁止 `parse_constant` 接受非 JSON 数值，并加入共享向量。

- **P2 — platform `api/internal/releasefreeze/read.go:26`**：`MaxRetries(0)` 不禁止 HTTP 重定向。默认 client-go 客户端遇到 `302 Location: /elsewhere` 后继续 GET；第二处返回空 FreezeList，即得到 `clear`，Python 则拒绝 302。最小修复：提供受约束的客户端构造，禁止重定向、环境代理与不安全 TLS，固定 CA；增加“两次请求／错误路径”反例测试。

- **P2 — 两侧 `decision.go:127`／`freeze_gate.py:115`**：200 空列表携带 `metadata:{"remainingItemCount":1}` 仍返回 `clear`；Python 已实测。响应明确表示仍有剩余记录，不能证明完整性。最小修复：拒绝与完整 LIST 矛盾的分页元数据，并加入共享向量。

- **P2 — infra `scripts/release/freeze_gate.py:100,172`**：5000 位整数触发未捕获的 `ValueError`；截短 Content-Length 正文触发未捕获的 `http.client.IncompleteRead`，均已离线复现。没有返回约定的 `unreadable`。此外 socket timeout 是单次操作超时，持续缓慢发送可超过总计 10 秒。最小修复：统一捕获解析／传输异常，并实施总读取期限。

- **P2 — infra `scripts/release/freeze_lift.sh:26`**：UID 未经 JSON 转义。输入 `x"},"preconditions":null,"ignored":{"uid":"x` 生成重复 `preconditions`；普通解析后前置条件变成 null，破坏过期 UID 保护。最小修复：用 JSON 编码器生成正文，测试引号、反斜杠及重复键注入。

- **P2 — infra `k8s/release-freeze/crd.yaml:24`**：根 schema 未要求 `spec`；只有名字、没有 spec 的记录可绕过 who/reason/at 必填约束，模型却拒绝该内容类。静态测试也未检查根 required。最小修复：根添加 `required: ["spec"]`，补缺 spec 的负例。

- **P2 — platform `api/internal/releasefreeze/model_engine_test.go:439`**：读始终使用当前 `next`，`lin` 仅用于命名。最小缺失行为是读在写前线性化、在写后返回；两个标签并未验证不同快照。最小修复：显式保存读快照并安排返回，按线性化状态验证 S/L/U。

- **P2 — platform `api/internal/releasefreeze/model_engine_test.go:289`**：owner-reference 阴性对照中的 sweep 直接移除记录，不经过仍开启的删除准入；因此其反例来自模型额外赋予的删除能力。最小修复：清扫走真实授权／准入规则，并明确修订该阴性对照的故障前提。

核对结果：变更路径在允许范围内，无新增依赖、发布路径导入或超过 800 行的文件；记录策略原文、RBAC、墓碑及删除保护符合指定文本，未发现现有部署引用。模型计数有固定断言；随机测试源码让两侧读取同一 TLS 服务，Python 覆盖 501 条序列，但未实际重跑证明。

验证限制：Python 的三个纯向量测试通过；68 个向量两份逐字节相同，摘要与常量一致。Go 被只读沙箱禁止创建临时目录；当前 Python 缺 pytest/PyYAML，完整验收未运行。未写文件、未调用平台或集群 API。

必须回写设计：输出格式、严格 JSON 与分页完整性契约、墓碑 guard 的精确匹配、双副本摘要机制均应明确；POST 接线与两个 Task 延后符合本片范围，但须修正设计 S1 范围，并澄清读线性化及清扫阴性对照前提。

END OF REPORT
