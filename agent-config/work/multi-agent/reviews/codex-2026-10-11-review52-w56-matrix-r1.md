# Codex 复核 52 — W-56 第 1 步 A 片，缩小范围后的第一轮（`66d9742..713ca39`）

2026-10-11 05:49 CDT · 只读 · 分支 `w31/w56-matrix`

统筹方的处置：先改。三处必须改、七处应该改，加上统筹方自己发现的一处（测试往源码目录里写 17 个文件），全部进第 2 轮任务书。第 2 轮的总规则：重放不信录制包里任何它自己能核对的东西；核对不了的要么以 2 退出，要么成一行 `unknown-surface`，不许变成一个更小的数。

---

VERDICT: fix first

审查范围：`66d9742..713ca39`；以下路径均相对 `scripts/release/prod_matrix/`。反例只在内存中构造，未修改文件、访问集群或调用 HTTP API。

- **P1 — 发现清点不完整且回放不核对完整性。** `collect.py:256`、`identities.py:146`：只采集每组首选版本；回放不根据 `/api`、`/apis` 验证应有的发现命令。
  最小复现：删除录制包的 `/apis/traefik.io/v1alpha1` 命令，回放仍退出 3，未知面计数从 37/16/25 降为 34/15/25；根发现命令标为失败也被忽略。最小修复：采集全部在供版本，并验证根发现成功及全部预期发现路径齐全。

- **P1 — 未确认授权链的身份被当作有效拒绝处理，固定风险行会消失。** `classify.py:232`、`classify.py:267`：未知 uid/extra 的拒绝直接计数后丢弃；固定身份中的 masters 和匿名没有独立保留风险行。
  最小复现：直接回放已提交的全拒绝夹具，masters 输出行数为 0；授权链未确认仍有 `asked-not-allowed: 294`。最小修复：按规格 §3 将受未知上下文影响的授权行标为 `unknown-surface`，并独立保留全部固定风险记录。

- **P1 — webhook 内容变化不触发棘轮。** `ratchet.py:167`：摘要只取 `spec`，而 webhook configuration 的规则在顶层 `webhooks`。
  最小复现：把 `ValidatingWebhookConfiguration.webhooks[0].failurePolicy` 从 `Fail` 改成 `Ignore`，生成行完全相同。最小修复：按种类摘要实际生效字段，覆盖 validating/mutating webhook。

- **P2 — 错误问题未在发送前被拒绝。** `exceptions.py:159`、`prod_measure.py:73`：仅检查缺失的子资源，而且检查发生在所有问题发送之后；普通资源、版本、作用域和动词未核验。
  最小复现：发现只有 `configmaps`，显式问题写成 `ConfigMap`，拒绝答案仍正常回放、退出 3。最小修复：发送前及回放时验证全部问题与发现清单一致；修正 `prod_targets.json:572` 的 ephemeralcontainers `create`，假发现也应反映真实支持的动词。

- **P2 — 中间缺页与畸形列表可被当作完整清点。** `identities.py:103`、`identities.py:125`。
  最小复现：三页列表删掉中间页，仍退出 3；删除 RoleList 的 `items` 也被视为空列表。最小修复：逐页保存请求的 continue 并核对连接及页数；缺少必需列表字段直接退出 2。

- **P2 — 重试答案绕过校验，成功重试的发现又会被误判失败。** `classify.py:120`、`identities.py:85`。
  最小复现：追加两个同 id、带 `retry_of`、哈希错误的答案，仍退出 3；发现请求先 503 后成功，回放却读取失败主记录并退出 2。最小修复：给每次尝试独立编号，验证重试关系、请求哈希和答案，统一选择最终成功尝试。

- **P2 — 棘轮并非逐行相等。** `ratchet.py:278`、`prod_ratchet.py:39`：差异最终使用集合判断。
  最小复现：`diff(['a','b'], ['b','a'])` 和 `diff(['a'], ['a','a'])` 都返回空列表，检查因此通过。最小修复：任何文本序列不相等都返回失败，保留顺序及重复次数差异。

- **P2 — 预算与固定输出契约未完整执行。** `prod_measure.py:64`、`collect.py:125`、`classify.py:185`。
  最小复现：450 个 SA 算出 22295 问时，清点已执行且首行是 question count；追加 501 条读取记录仍可回放退出 3；最后一次请求跨过墙钟期限也不再检查。最小修复：按契约在请求前完成预算核验，将计数放在固定两行之后，回放核验实际请求数，并在请求完成后检查截止时间。

- **P2 — 风险例外不精确匹配全部维度。** `exceptions.py:64`。
  最小复现：node-root 例外填 `scope: namespaced`、`namespace: wrong`，`match_risk` 仍返回真。最小修复：为风险行声明规范目标维度，匹配 scope 和 namespace，拒绝不适用的非空维度。

- **P2 — 单一声明只覆盖外壳。** `schema.py:122`、`schema.py:269`、`schema.py:414`：请求/回答声明成任意 JSON；固定记录必填字段又在条件校验中另列一份。
  最小复现：给 `reviews[0].request` 加未知键，回放仍退出 3。最小修复：在 schema 中声明 SAR 请求及各类固定记录的条件字段，由同一声明生成验证和字段表。

- **P3 — 测试与文档不足以支撑报告。** `test_reviews.py:280` 重复检查 `doubled`，没有检查构造的 `repeated`；T40 只测顶层负例。已知源码目录写入问题见 `test_reviews.py:312`。`README.md:1` 未说明棘轮不渲染 kustomize generators/patches、不展开 Helm values，也不扫描 `k8s/` 外的清单。

验证：12 个无写入测试通过，包含禁止 subprocess/socket 的回放；独立计算的首个请求哈希与 `q-e7486020dee855bc` 一致，README 字段表也一致。未重跑会写源码目录的完整测试集。采集命令未见 impersonation、Secret 对象读取或业务写入；使用 GET、whoami、SelfSubjectAccessReview 和 SubjectAccessReview。

**reviews 40/44/47 的同类问题仍存在，但落点已缩小到清点与证据完整性。** 正常回放没有 `refused`，也不会退出 0；空名字拒绝仍保留 `names-not-enumerated`。第一轮主动声明未问全是正确的，删除发现记录、缺页或错误问题却仍被正常处理，则继续制造了不具备的完整性。

END OF REPORT