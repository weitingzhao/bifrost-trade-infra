# Codex 复核 56 — W-56 第 1 步 A 片第三轮（`83782de..924a320`）

2026-10-11 07:52 CDT · 只读 · 分支 `w31/w56-matrix`

统筹方的处置：**这条线停**。还有一处必须改（末次提问失败时，程序仍读它的正文、算成确定的拒绝）和五处应该改。开工前写下的停线条件是「第三轮复核还有必须改的就停，不再延」，照此执行：分支停在 `924a320`，已推送，不合并。统筹方自己的核对：52 条测试连跑两遍通过、源码目录干净；删改测试的全量 24,593 个，24,264 个退出 2，329 个一行不少，0 个失败——结构上的删改拦得住，这一轮漏的是「值」和「采集器真正发出去的请求」。重开的任务书已备好（`~/agent-work/w56-matrix-r1/TASK-4.md`），Owner 说「清点程序继续」才开。教训第 73 行。

---

VERDICT: fix first
以下路径均相对 `scripts/release/prod_matrix/`；复核范围为 `83782de..924a320`，以规格 §18 为准。
A — partly closed：`attempts.py:90,200`；无链覆盖和畸形发现已拒绝，但读取字段的严格校验仍有遗漏，见下文。
B — closed：`classify.py:213`；精确例外不能吸收未确认上下文的允许回答，四类固定行仍打印。
C — closed：`ratchet.py:141`；完整 CRD spec 已摘要；schema 和 served 两个反例均改变输出。
D — closed：`exceptions.py:202`；错误 ConfigMap 名称仍被拒绝，ephemeralcontainers 使用 patch。
E — partly closed：`attempts.py:150,185`、`identities.py:197`；缺页、重复终页、缺 items、缺目标 namespace 已拒绝；ClusterRoleBinding 引用仍漏检。
F — partly closed：`attempts.py:90`、`collect.py:150`；合法两次尝试可回放，采集器生成的三次尝试仍违反链规则。
G — closed：`ratchet.py:342`；基线换序和重复行均产生差异。
H — partly closed：`prod_measure.py:56,69`、`collect.py:132`；两道预算及身份去重正确，墙钟超限仍丢失已发送尝试。
I — closed：`exceptions.py:28,82`；错作用域不匹配，cluster 非空 namespace 被拒绝。
J — partly closed：`schema.py:468`、`attempts.py:144`；metadata/spec 可保存回放，但部分被读取字段仍以真值判断代替类型验证。
K — closed：`test_reviews.py:287`、`README.md:23`；原重复断言、测试位置和棘轮范围问题保持修复。
54-P1 清点缩小 — closed（原复现）：`attempts.py:125`、`identities.py:204`；无链追加覆盖及删除 data 均退出 2；重新计算摘要的限制另述。
54-P1 上下文被例外吸收 — closed：`classify.py:213`；T45 复现仍为 context-unconfirmed。
54-P2 尝试折叠与混计 — partly closed：`attempts.py:84`、`collect.py:132`；读/SAR 分开计数、不折叠，但超时返回后仍缺记录。
54-P2 重试契约 — partly closed：`collect.py:150`；两次合法，503→503→200 的第三次指针错误。
54-P2 响应 metadata/spec — closed：`schema.py:468`；重新封存后退出 3。
54-P2 CRD 摘要 — closed：`ratchet.py:149`；两个原值变更均被捕获。

P1 — `classify.py:209,227`：忽略末次 SAR 的 `ok/status_code`。最小复现：仅把 committed bundle 一条 anonymous denied 记录改为 `ok=false,status_code=503`，不改正文或摘要，仍退出 3、计入 49 条确定拒绝，且没有对应未知行；成功 allowed 后追加失败 denied 的合法链还会丢失原行键。最小修复：解释正文前检查末次结果，失败必须退出 2 或产生 unknown-surface。
P2 — `collect.py:131,189`：分页参数未传输。内存 transport 实收 `/api/v1/namespaces`，记录却声称带 `limit=500,continue=t1`；真实分页会反复请求首屏。最小修复：对实际 GET 路径编码 params，并测试 transport 收到下一页 token。
P2 — `collect.py:150`：第三次重试仍指向首次。503→503→200 生成 `(1,None),(2,1),(3,1)`，回放退出 2。最小修复：每次指向紧邻的上一尝试。
P2 — `collect.py:132,142`、`attempts.py:95`：审计记录不完整。模拟请求返回时墙钟已超限，发送 1 次却记录 0 条；最后编号增加 10 仍退出 3。起止时间也都在返回后生成。最小修复：发送前取开始时间，返回后先记结果再检查墙钟，并验证编号从 1 连续。
P2 — `identities.py:197`、`attempts.py:144`：引用及读取类型漏检。ClusterRoleBinding 指向不存在的 `ghost` namespace 可退出 3；`metadata.continue=0` 重新封存后也退出 3。最小修复：纳入 ClusterRoleBinding 引用，验证原始字段类型后再处理空值。
P2 — `README.md:19`：没有明确说明 bundle 未签名、摘要可同步重算。最小修复：写明摘要只检测未同步修改，不能证明原始响应真实性或完整性。

链复现：无 retry_of、自指、向前指、跨请求、重复 attempt、未引用附加页均退出 2；失败末次读取退出 2；编号缺口退出 3；请求哈希确实重新计算（read 为请求，SAR 为 spec），改请求保留旧哈希退出 2。
旧表重试结果（删除／重复／重排／截短，＝表示输出计数不变）：根发现 `2/2/3＝/2`；版本发现 `2/2/3＝/2`。
分页 `2/2/3＝/2`；命名空间列表 `2/2/3＝/2`；身份列表 `2/2/3＝/2`；评审 `2/2/3＝/2`；读取重试 `3＝/2/3＝/2`。
补充：重复中页和终页均退出 2；groups=[null]、空 body、空 spec 均退出 2；截短已被成功重试取代的旧记录可退出 3且计数不变。
值变更：删除引用的 namespace 由交叉检查拒绝；删除 SA 而保留问题由 unexpected answer 拒绝；删除显式问题所需资源/动词由 discovery 检查拒绝。
重新封存后删除未问的 pods/status：332→328 行、named-subresource-not-asked 25→21，退出 3；同步改 continue 两侧退出 3且输出完全相同；删未问动词也被接受。修改 allowed 同样可改变分类。
上述自洽内容替换属于未签名 bundle 的证明限制；删未引用 namespace，或同步删 SA 及其问题，也不能仅靠包内数据证明原清单完整。
T42 已独立重跑：6006/24593，5677 个退出 2、329 个保持；seed=56，非 review 记录全部覆盖、review 内部覆盖 41/294，断言确实比较原行键包含关系、三项计数和固定行数。
抽样可复现且覆盖全部记录种类，但没有失败末次 SAR、采集器实际分页及三次重试场景；没有把抽样结果当作全量证明。
预算复现：下界超限发送 0 次；450 个 SA 的确数超限仅发送 15 次身份读取，无 discovery/SAR；重复 anonymous 后下界仍为 98。
采集调用范围仍仅身份/发现读取、SelfSubjectReview、SelfSubjectAccessReview、SubjectAccessReview；未见 impersonation、Secret 正文读取或主动采集凭据，但“一次请求一条真实记录”仍不成立。
基线保持 548 行，Secret 仅摘要、ConfigMap 仅键名，未发现明文凭据；CRD 两项反例在内存验证。为遵守禁读凭据目录要求，未重跑全树 ratchet 扫描。
验证：30 项原测试通过，另 7 项改用内存回放适配后通过；完整 52 项未重跑。源码及 ignored 状态为空；未修改文件、访问集群或调用 HTTP。
40／44／47 类问题仍存在于失败 SAR 被当作确定拒绝及采集尝试记录；不能仅归为未签名 bundle 的限制。本轮仍有 P1，按 brief 应停止该 lane。
END OF REPORT