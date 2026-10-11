VERDICT: fix first

只读复核 `80a7d41`；未修改文件、提交或调用平台/集群。复现 466 行：418 `unclassified`、48 `refused`，exit 1。27 个可只读执行的测试函数通过；未运行写文件测试。以下代码路径相对 `scripts/release/`。

Review 33 的十二项，按原报告顺序：

1. **P1，已关闭：父字段错误拒绝。** `admission_effects.yaml:9` 起拆成受保护子字段；`spec.source` 和 `spec.source.targetRevision` 已保持 `unclassified`，对应 CEL 在 `k8s/platform-rbac/40-admission.yaml:232`。
2. **P1，未关闭：准入适用性证明不足。** Deny、Fail、条件、参数、选择器检查已补，但 `prod_write_admission.py:191` 自行合成 Namespace 标签，绕过“标签实际读到”的要求。
3. **P1，未关闭：参数可达性仍漏报。** `prod_write_dag.py:100,145` 依赖参数名称关键词；内联步骤使用无约束 `$(params.dest)` 指定 namespace 的反例得到零行。
4. **P1，已关闭原项：freeze 适用条件。** `prod_write_dag.py:239,250,306` 按声明的 taskRef 检查 when/onError，并计算路径支配；finally 单独保留。
5. **P1，未关闭：finally/命令读取已补，未知写路径仍消失。** `prod_write_dag.py:315` 在步骤分类前要求能识别 PROD；依靠执行上下文访问 PROD、没有 PROD 字面量的 rollout 反例得到零行。
6. **P1，未关闭：借用权限闭包不完整。** `prod_write_borrow.py:50,75,162,286` 跳过派生规则；已复现“bind 获得 pod-creator → 创建 Pod → 借 writer SA”的 Deployment 写行缺失。
7. **P1，已关闭原项：SA 组权限。** `prod_write_rbac.py:277,339` 枚举 SA 并合并三个内置组；`:352` 补匿名身份；`prod_write_matrix.py:276` 补 masters 固定行。masters 被借用的问题见下。
8. **P1，已关闭：泛目标 resourceNames。** `prod_write_rbac.py:393` 保留受限名称并输出 `only:`。
9. **P1，未完全关闭：控制面目标已补，动态 class 目标在 dump 下仍缺证据。** `prod_targets.yaml:262` 起新增目标；但 `prod_write_load.py:21` 的导出集合没有 workloads，`prod_write_matrix.py:259` 无法发现 Deployment 引用的 priority/runtime classes。
10. **P1，未关闭：输入完整性。** `prod_write_load.py:129,151` 已扩大仓库扫描、检查文件/count/kind；`prod_write_rbac.py:319` 检查 roleRef。但导出成功状态没有验证，详见下。
11. **P2，已关闭：例外过宽、过期。** `prod_write_matrix.py:149,185` 拒绝通配、验证日期并精确匹配。
12. **P2，已关闭：聚合角色循环。** `prod_write_rbac.py:241` 使用单调闭包，dump 保留已展开 rules。

48 个 `refused` 的来源及证据：

- **数量增长不是新增拒绝规则：** Application 由每身份 4 个字段变成 10 个，两个直接身份共 20 行；PipelineRun/TaskRun 从各 2 个变成各 4 个，共 8 行；平台账号经两条路径借 tekton-deliver，额外复制 20 行。合计 **20＋8＋20＝48**，比原来增加 36。
- **P1：全部 48 行未满足本轮标准。** 它们均选择 `cicd`，但仓库扫描未读到该 Namespace；`prod_write_admission.py:189` 仍推定 metadata.name 标签。按 brief，应全部降为 `unclassified`。这是拒绝证据不合格，并不证明真实集群会允许这 48 种写。
- 当前策略确有 Deny、Fail、匹配的用户名条件，且无 objectSelector/参数；Application 子字段比较支持其效果声明。不过 `admission_effects.yaml:83,108` 的 `resolver` 仍是别名，应写成精确的 `pipelineRef.resolver`／`taskRef.resolver`。

性能及终止性：

- **P1：固定点计算发生组合膨胀。** `prod_write_borrow.py:137` 每轮重算所有身份，`:283` 复制 victim 的全部派生规则，再由 `:44` 线性扫描去重；重复候选也先进入 additions。仅 12 个 SA、20 条规则的内存反例，就产生 51,282 次 `_held` 调用，最终只有 3,024 条规则。
- 路径在 `:176,284,307` 被覆盖成第一跳，未发现路径无限增长或非单调步骤；有限输入最终会稳定。若 I 为身份数、U 为唯一 `(rule,scope)` 数、P 为每身份有限路径数，存储上界为 `I×U×(P+1)`，但候选生成和线性去重远超此规模。矩阵还在 `prod_write_matrix.py:223` 对每个身份×目标重新扫描规则。
- 修法：将可达权限与路径证据分开；用哈希集合、增量工作队列及反向借用边传播新增权限，保留实际执行身份。语义状态可限定为有限的 `(原主体,执行身份,rule,scope)`；路径存图，不枚举所有路径。缓存 RBAC/准入匹配。任何预算截断必须输出明确的 `unclassified: derivation truncated`，不能静默丢行。

导出缺口及新增问题：

- **P1：读取失败被当成测得为空。** `prod_write_load.py:187` 只验证 count；空列表＋MANIFEST count 0 会通过，并在 `prod_write_matrix.py:373` 标为 measured。现有空 webhook fixture 已验证会被接受。MANIFEST 应记录每条命令的成功/失败状态；Forbidden 必须拒绝输入或产生对应 `unknown-surface`，不能填零。
- **P1：借用写入用错准入身份。** `prod_write_matrix.py:227` 使用原主体匹配策略；`prod_write_borrow.py:284` 丢失最终执行身份。已复现原主体被策略拒绝、取得 token 的 SA 不匹配策略，却仍输出 `refused`。
- **P1：效果表未绑定实际 CEL。** `prod_write_admission.py:69,352` 只取消息/策略名，不验证当前表达式仍支持效果。内存中把策略 validations 全改为 `true`，仍得到 48 个 `refused`；restrict-serviceaccount 也会继续错误收窄。应绑定已审查表达式指纹，变化时降为不确定。
- **P1：仍有具体提权漏行。** `prod_write_borrow.py:218` 不处理 ClusterRole 经 RoleBinding 获得权限；`:208` 对 `system:masters` 的 impersonate 查不到可传播的全权限，已复现零行；`:256` 对多个 Role scope 只取第一个。
- **P1：未解析运行对象静默消失。** `prod_write_dag.py:369` 对找不到 Pipeline 的 PipelineRun 不输出未知行；TaskRun 虽可被仓库加载，却未进入 DAG 分析，且 `prod_write_load.py:21` 没有要求导出它。

END OF REPORT