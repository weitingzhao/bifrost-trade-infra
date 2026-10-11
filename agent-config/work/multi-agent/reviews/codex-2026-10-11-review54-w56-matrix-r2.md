# Codex 复核 54 — W-56 第 1 步 A 片第二轮（`713ca39..83782de`）

2026-10-11 06:47 CDT · 只读 · 分支 `w31/w56-matrix`

统筹方的处置：先改，给第三轮（用掉统筹方的一次延期）。十一处里关了四处、七处关了一部分，新的必须改的两处。其中三处是规格自己的错，已在规格第 18 节改掉；第三轮改形状，不逐条补。第三轮复核还有必须改的就停线。

---

VERDICT: fix first
A — partly closed：`identities.py:159,235`；删版本发现记录已退出 2，但畸形根发现和被覆盖的清单仍可正常回放。
B — partly closed：`classify.py:245,256,294`；四类固定风险行保留、未知上下文的拒绝不再计数；允许回答仍可被例外吸收。
C — partly closed：`ratchet.py:182,295`；Webhook 的 Fail→Ignore 已改变摘要，但 CRD 的版本和 schema 仍不触发棘轮。
D — closed：`exceptions.py:171,202`、`prod_measure.py:80`；ConfigMap 拼写反例退出 2，采集发送零条 SAR；ephemeralcontainers 动词已修正。
E — partly closed：`identities.py:182,216,230`；缺中间页和缺 items 已退出 2，但重复终页、畸形条目及缺目标命名空间仍被接受。
F — partly closed：`identities.py:85,109`、`classify.py:157`；旧的重复编号反例退出 2，但合法 SAR 重试和采集器生成的读取重试无法回放。
G — closed：`ratchet.py:342`；换序与重复行两个原反例均产生非空差异。
H — partly closed：`prod_measure.py:56`、`collect.py:127`、`classify.py:206`；固定输出、墙钟后检查已修复；零请求契约及实际尝试计数仍有问题。
I — closed：`exceptions.py:28,82`；原 node-root 错作用域反例不匹配，cluster 非空 namespace 在加载时退出 2。
J — partly closed：`schema.py:154,167,428`；请求未知键已拒绝，固定记录统一声明；响应声明遗漏合法字段。
K — closed：`test_reviews.py:287`、`conftest.py:14`、`README.md:19`；重复断言、显式测试文件位置和文档边界均已修正。

以下路径均相对 `scripts/release/prod_matrix/`；问题包含本轮新增回归及未闭合项。
P1 — `identities.py:109,143,230`：清点仍能缩小。复现：追加不同 id 的 `/api/v1` 记录并删其 pods/status，行数 332→328；删 namespace 列表里的 data，332→312，均退出 3。最小修复：同一请求仅允许受验证的重试链；严格验证发现结构，并核对目标及所有引用的命名空间。
P1 — `classify.py:245`：未知上下文能被例外吸收。复现：把 example-sa 一问改为 allowed，加精确例外，得到 named-exception，context-unconfirmed 从 245→244。最小修复：在允许回答及例外匹配之前检查上下文，未知面不得被例外吸收。
P2 — `collect.py:143,204,301`、`classify.py:206`：记录混淆读取与提问，并折叠实际尝试。复现：10 个身份产生 490 问，实际 24 次读取，却录下 514 条 commands，回放报读取超限；两页读取只保留一条命令。最小修复：每次请求独立保存，分别核算读取与 SAR 尝试。
P2 — `classify.py:164`、`identities.py:96`、`collect.py:204`：重试契约自相矛盾。复现：合法 `q-…-r1` 被哈希编号校验拒绝；GET 503→200 经采集折叠后回放失败；读取重试指向自己却退出 3。最小修复：分离问题编号和尝试编号，要求引用严格更早的同请求记录，取消折叠。
P2 — `schema.py:167`、`collect.py:293`：响应声明与采集保存方式不兼容。复现：给录制 SAR 响应加入 metadata 或 spec，立即退出 2；采集器原样保存响应。最小修复：在统一声明中纳入并验证这些响应字段。
P2 — `ratchet.py:117,295`：CRD 生效内容未摘要。复现：改变 versions[0].served 或 openAPIV3Schema，扫描分支输出完全相同。最小修复：保留展开资源行，同时增加完整 spec 摘要。

证据删改复现如下；“重复”使用原 id，“↓”表示计数减少，“＝”表示不变。

| 记录种类 | 删除 | 重复 | 重排 | 截短 |
| --- | --- | --- | --- | --- |
| 根发现 | 2 | 2 | 3＝ | groups 改为 [null]：3＝ |
| 版本发现 | 2 | 2 | 3＝ | 空 body：2；删未问资源：3↓ |
| 分页 | 删中页：2 | 中页：2；终页：3＝ | 2 | 缺 items：2 |
| 命名空间列表 | 2 | 2 | 3＝ | 删除 data 条目：3↓ |
| 身份列表 | 2 | 2 | 3＝ | 空 body：2 |
| 评审 | 2 | 2 | 3＝ | 空 spec：2 |
| 读取重试 | 2 | 2 | 2 | 空 pages：2 |

修改请求但保留原哈希，退出 2；合法 SAR 重试也错误地退出 2。
预算解释不符合 §17 的“超限一个请求都不发”：450 个 SA 时先发 15 次身份读取，随后 22295 问退出 2；确实没有再发 discovery 或 SAR。
默认固定身份的下界正确，超限时零请求；但允许输入中重复同一用户会使下界虚高，复现为 147，而去重后只有 98。应统一去重，并用预先完整的身份输入完成零请求预算检查。
49 条 clean denial 全属于 anonymous：48 条显式问题加全通配，groups、空 uid、空 extra 均符合 §3；未发现其中有 D 应拒绝的畸形问题。
棘轮检查：aggregationRule、绑定主体换序、VAP及其绑定、Task/Pipeline、Application/AppProject 的 spec 均按预期保留或捕获；Role 规则换序、绑定 validationActions 换序会产生无语义变化的报警。步骤顺序仍保留。
基线核对：207 条原样保留，新增 341 条，共 548 条；ConfigMap 11 条只含键名，未发现明文 Secret 数据或 token，Secret 行仅含摘要。
验证：14 项无写入测试通过；在内存加载 713ca39 后，同批测试为 12 个断言失败、2 个错误，另复现了 D 的旧版退出 3。
清洁检查确实查询 git 状态，但看不到被忽略文件；重试负例只证明重复 id 被拒绝，T40 又会先因字段表变化失败。完整套件需写临时文件，本次未运行；最终源码状态干净。
40／44／47 的“声称具有实际上没有的完整性”类别仍存在，集中在清点、尝试记录及 CRD 摘要；不能合并放行。
END OF REPORT