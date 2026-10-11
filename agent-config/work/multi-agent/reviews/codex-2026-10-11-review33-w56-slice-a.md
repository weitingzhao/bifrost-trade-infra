VERDICT: fix first

只读审查提交 `666048d`；未运行生成器、测试或集群命令，未修改文件。以下路径相对于 `scripts/release/`。

- **P1 — 实际存在错误的 `refused`。** `admission_effects.yaml:9` 把整个 `spec.source` 标为拒绝，但 `k8s/platform-rbac/40-admission.yaml:232` 只锁部分子字段，明确允许 `source.targetRevision`。PROD platform SA 和 tekton-deliver 可通过 PATCH 修改它，对应两行仍会标为拒绝。应拆成具体受保护字段。

- **P1 — 准入适用性不确定时仍可判为拒绝。** `prod_write_admission.py:129,156,269` 把未知 matchCondition、未知 namespace 标签视作匹配；`:71` 未读取 `failurePolicy`、`paramKind/paramRef`，`:209` 忽略 objectSelector。条件为 false、参数缺失且 Allow、或 Ignore 下发生求值错误时，请求可以通过，effects 却仍产生 `refused`。不确定情形应保留为 `unclassified`。[官方语义](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)

- **P1 — 默认 STG、运行时可指向 PROD 的流水线漏行。** `prod_write_dag.py:36,122` 用默认值替换参数后只搜索 PROD 字面量。仓库 `pipeline-deliver-platform.yaml:25,118` 的镜像参数可覆盖为 `bifrost-platform-api:prod`，无需修改 Pipeline，两个构建任务却没有矩阵行。应分析参数可达性并读取 PipelineRun 覆盖值。

- **P1 — freeze 祖先不等于必经成功检查。** `prod_write_dag.py:91,155,168` 仅凭任务名称认定 freeze，再因存在 runAfter 祖先而删行；没有检查 `when` 或 `onError: continue`。freeze 被跳过或失败被忽略后，后续写任务仍可能执行。应证明检查实际执行且成功，否则保留行。[Tekton 跳过语义](https://tekton.dev/docs/pipelines/pipelines/#guarding-a-task-only)

- **P1 — `finally` 和命令式步骤漏行。** `prod_write_dag.py:23` 完全不读取 `finally`；`:70` 不读取 step 的 `command/args`。finally 中的 PROD rollout、或名称普通且通过命令参数执行写入的 inline taskSpec 都可能消失。finally 还可能在 freeze 失败后执行，必须单独分析。

- **P1 — 未推导借用强身份的权限。** `prod_write_rbac.py:245,300` 只匹配直接规则。`impersonate users/serviceaccounts/groups` 因没有对应 target 可完全消失；具备必要绑定写权限的 `bind/escalate` 主体也不会扩展到可获得的 PROD 权限。创建 Pod、Job、PipelineRun 后使用更强 SA 的路径同样未推导。应结合准入限制计算身份可达权限。[Kubernetes 权限提升说明](https://kubernetes.io/docs/concepts/security/rbac-good-practices/)

- **P1 — ServiceAccount 没有继承组权限。** `prod_write_rbac.py:95,266` 将 Group 与 SA 分开存储，未合并 `system:authenticated`、`system:serviceaccounts`、`system:serviceaccounts:<ns>` 的授权；ServiceAccount 对象本身也不用于枚举身份。仅经组获得写权限的 SA 会遗漏。`system:masters` 的超用户授权也不能依赖普通绑定推算。[官方说明](https://kubernetes.io/docs/concepts/security/rbac-good-practices/)

- **P1 — 泛资源 target 丢掉按名称授权。** `prod_write_rbac.py:295` 要求 `target.name` 命中 resourceNames，但 `prod_targets.yaml:55,70,206` 等泛目标没有 name。例如只允许 patch `platform-config` 的规则会完全漏行。应枚举受限名称或保留名称约束，而非将空名称当作不匹配。

- **P1 — 目标清单缺少真实 PROD 控制面。** `prod_targets.yaml:3` 至文件末没有 namespace/labels、Secrets、SA/token、nodes、NetworkPolicy/PDB、Quota/LimitRange、CRD、webhooks、AppProject 或仓库凭据目标。当前 PROD SA 的 node patch、applier 的 NetworkPolicy/PDB/SA 写权限已因此遗漏；`pods/exec` 也缺席，且 GET exec 可执行写命令。应列出这些写面，无需读取 Secret DATA。

- **P1 — 输入不完整仍标为 measured。** `prod_write_matrix.py:112,133,353` 对不存在目录、缺文件、缺资源类别没有完整性检查；`prod_write_rbac.py:260` 把缺失 roleRef 定义当作空规则。删掉绑定文件即可静默缩小矩阵；剩余行获得例外后可错误通过。仓库扫描范围 `:40` 还遗漏已有 `k8s/cicd/argocd/rbac-cicd-namespace-bindings.yaml`。应验证导出清单完整性，并拒绝未解析的授权引用。

- **P2 — 例外可无限扩大且永不过期。** `prod_write_matrix.py:178,190` 只检查 expiry 非空，不解析日期或比较当前日期；三个匹配维度均接受 `*`。一个全通配、已过期条目即可覆盖全部写行。应拒绝通配并要求精确匹配、有效日期及未过期。

- **P2 — 聚合角色循环会丢权限。** `prod_write_rbac.py:216,236` 在循环中返回空并缓存不完整结果。例如 A 聚合 B、C，B 聚合 A，C 提供 patch：B 会被缓存为空，无法得到控制器最终传播的 C 权限。应计算单调不动点；dump 中已有的聚合 rules 也不应在证据不足时直接丢弃。

另行核对：其余 10 个仓库 `refused` 行有当前策略支持；PATCH 按 UPDATE 匹配正确，Warn/Audit-only binding 不产生拒绝。通配匹配仍需分开实现：RBAC 与准入规则语义不同，`prod_write_admission.py:196` 直接复用 RBAC matcher 会错误扩大准入覆盖。[RBAC 实现](https://github.com/kubernetes/kubernetes/blob/master/pkg/apis/rbac/helpers.go)

END OF REPORT