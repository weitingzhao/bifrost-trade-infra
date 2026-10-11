# Codex 复核 63 — W-56 A 片，重开后第 1 轮（`924a320..5812f3d`）

2026-10-11 11:44 CDT · 只读

统筹方的处置：先改，再给一轮。复核 56 的六处全部关闭，没有必须改的，两处应该改的进第 2 轮。

---

VERDICT: fix first
路径均相对 `scripts/release/prod_matrix/`；审查范围为 `924a320..5812f3d`。

56-1 — closed：`classify.py:129,209`、`attempts.py:47`；失败末次 SAR、先成功后失败的合法链均退出 2，不再计作确定拒绝。
56-2 — closed：`collect.py:136,143`；端到端复验确认 transport 实收到 `limit=500` 和下一页 `continue=t1`。
56-3 — closed：`collect.py:159`；503→503→200 的第三次尝试指向第二次，生成的包可重放。
56-4 — closed（原复现）：`collect.py:142,162`、`attempts.py:163`；开始时间在发送前，超墙钟返回先进入内存 attempts，再退出 2；编号缺口退出 2。
56-5 — closed：`identities.py:228`、`attempts.py:70`；ClusterRoleBinding 引用 ghost namespace、`continue=0` 和 subject namespace=0 均退出 2。
56-6 — closed：`README.md:21`；已明确说明未签名、可同步重算摘要，以及真实性和完整性的证明限制。

P2 — `classify.py:175,179`、`identities.py:219`：失败的辅助读取仍被忽略。最小复现：仅把样例 `attempts[0].result.ok` 改为 false，或把权限自检末次状态改为 503；无需重新封存，仍退出 3、输出完全相同。最小修复：分链后对所有末次尝试调用 `group_result`，包括 whoami 和权限自检；对应变异必须断言退出 2。
P2 — `classify.py:129,130`、`schema.py:470`：SAR 正文未与请求方法、端点绑定。最小复现：仅清空一条 review 的 `request.path`，仍退出 3、计入原拒绝数；改成 GET 或 namespaces 端点也如此。最小修复：review 必须是 POST 到 SAR 端点并使用规定参数，否则退出 2；保持 spec 哈希规则。

正文访问审计：生产路径解释响应正文均经 `group_result`；其他直接访问用于摘要核对或测试。问题在于部分请求组根本没有结果检查。
`group_result` 对 ok=true/status=503、ok=false/status=200、status=true、缺 status 均退出 2；先成功后失败的末次链也退出 2。

端到端测试断言 transport 实收请求；漏带 token、错误 token 均被 fake 拒绝。请求数与尝试数一致，编号、重试指针和发送前后时间配对通过。
冻结时钟后，用同一 FakeApiserver→collector 路径重新生成默认样例，与提交的 bundle 完全相等：319 请求、319 尝试；无需手工修改。
样例重放退出 3，共 339 行，固定汇总正确，没有 `refused`。

独立重跑 T42：结构 6006＝5686 退出 2＋320 保留；值 1418＝1219 退出 2＋199 保留，断言失败 0。
199 的具体组成：129 个把原本空字符串再置空，无害；2 个改 caller 元数据，不影响分类；27 个把九条辅助读取的 ok／状态改为失败，应退出 2；41 个清空 SAR 路径，应退出 2。
这 199 个输出确实逐字相同，但后两类的“不变”是缺陷，不能作为正确性证据。
其中没有改变 allowed 正文、清空 verb 列表或一致重命名 namespace 的变异；单节点正文修改被摘要拦截，一致重命名不属于当前变异操作。
另验重新封存的 anonymous 允许回答：拒绝数 49→48，产生允许行；未确认 SA 的允许回答仍为 context-unconfirmed，输出不变合理。review 内部仍只抽样 41/294。

尚未证明真实集群行为：工具没有对 live apiserver 运行过。
首次现场运行必须核对调用身份、实际读/SAR 权限、Owner 确认的认证授权链、真实发现与清点引用、跨页 token／410、kubectl 错误和超时映射、实际重试请求数，以及完整运行的吞吐和预算。

验证：47 个不同测试通过，涉及临时文件的关键测试改用内存适配；未重跑完整 60 项及全树 ratchet。未修改文件、访问凭据、调用 HTTP 或集群；目录含 ignored 状态为空。
未发现新 P1；上述两项 P2 仍属 40／44／47／52／54／56 的证据与结论不一致问题，不能只归结为未签名 bundle 和未测 live。
END OF REPORT