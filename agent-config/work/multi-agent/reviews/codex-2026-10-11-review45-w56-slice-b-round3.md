VERDICT: fix first

本轮 `1841f69..239f100`：**没有剩余 P1；恢复文档仍有两个 P2。**

- **P2：恢复证据不足时没有安全分支。** [docs/RELEASE.md:180](~/agent-work/w56-slice-b/bifrost-trade-infra/docs/RELEASE.md:180) 依赖此前 status 输出和最后一次成功审计，但 status 未保证保存，审计仅保留最近 500 条（平台 `api/internal/actuation/audit.go:39,88,199`）。对象丢失且记录不足时，无法判断此前是否冻结；旧 status 也未绑定最新冻结。应明确：证据不足就停止发布，由 Owner 带外建立新冻结，之后重新签名解冻，不能推断为从未冻结。
- **P2：恢复示例没有编码 YAML 字符串。** [docs/RELEASE.md:185](~/agent-work/w56-slice-b/bifrost-trade-infra/docs/RELEASE.md:185) 先删除对象，再将 `${WHO}`、`${REASON}`直接插入双引号。平台允许原因 `hold "prod"`，该示例会生成无效 YAML，创建失败后对象保持缺失，旧闸门又将 404 视为未冻结。应先用 JSON/YAML 序列化生成并验证恢复对象，再执行替换。

Review 41 四项结论：

- **P1 解冻死锁：closed。** `scripts/release/freeze_schema.json:9,16,25` 接受平台实际三种形状，移除了 `seq`，接受 `unfreeze.sig`。
- **P2 恢复与中断安装：not closed。** `docs/RELEASE.md:166–174` 已写清中断状态；`:180–202` 的恢复部分仍有上述两项问题。
- **P2 已知缺口仅按消息匹配：closed。** `scripts/release/freeze_chain.py:443–454` 校验仓库、流水线、任务、定义摘要及解析日期，拒绝未来或超过最大日龄的记录。
- **P3 CI 表述：closed。** `docs/RELEASE.md:225` 明确该检查为 manual；本轮未发现自动调用入口。

实际写入行为：

- 已读参考 writer 和真实实现。[release_policy_facts.go:74](<workspace>/bifrost-platform/api/internal/delivery/release_policy_facts.go:74) 执行 `cm.Data = data` 后 Update，**替换整个 data**，保留 metadata。
- 初始→冻结→解冻→再冻结→再解冻：冻结两次均正确拒绝，其余正确放行；不会残留 `who/reason` 或解冻字段，也不会重现原死锁。
- 冻结后重新 apply 初始化清单：通常保留冻结附加键，却将 `frozen` 改成 `"false"`，形成混合形状，检查正确拒绝；解冻后重新 apply，解冻形状仍完整，检查放行。
- annotations/labels 变化不影响判定；有权限者仍可 edit/patch/replace data。额外键、缺字段、错误值均正确拒绝；直接重置成裸 `"false"` 会放行，这是文档 `:231` 已明确留给后续片的直接写入边界。
- 恢复写入步骤明确为 Owner-only、带外；末尾 plan 是验证。恢复为冻结时被拒正确，签名丢失后先恢复冻结再重新签名也保守安全，但上述证据与编码缺口尚未解决。

验证：34 个只读相关测试通过；手工 checker 退出 1，仅报告 flex-query 已知缺口（age 0 days）。
默认手工检查失败、仓库与集群暂时不同，本身不阻止合并，也不代表闸门已上线；文档已要求按顺序安装并暂停发布。**修复上述 P2 后可合并；本轮未应用任何对象，也未调用平台或集群。**

END OF REPORT