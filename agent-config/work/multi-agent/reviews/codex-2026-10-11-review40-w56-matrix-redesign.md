VERDICT: sound with changes

只读审查完成；未修改文件，未调用平台或集群，未读取凭证、Secret 数据或 kubeconfig。新版方向成立，但以下 P1 必须先补进设计。

- **P1 — 一次拒绝只能证明该请求被拒，不能证明整个字段不可写。** [方案第 72 行](<workspace>/bifrost-trade-infra/agent-config/work/multi-agent/PLAN-w56-unattended-prod-2026-10-10.md:72)仍可能重现父字段误判：修改受保护子字段被拒，并不排除同一父字段下另一个子字段可写。“代表性写入”必须绑定精确字段路径、操作、API 版本、子资源、名字、新旧对象和完整身份；保持其他字段合法，分别覆盖允许变化和禁止变化、字段新增/删除、相关条件分支。存在可行的放行反例就不能把整行标为 `refused`；未覆盖的请求族保持 `unclassified`。不能用有限样本宣称任意 CEL 的全面封锁。

- **P1 — dry-run 证据范围和失效条件不足。** 只记录策略指纹不够：还要绑定 binding 的 Deny/Warn/Audit、参数、命名空间与对象标签、匹配条件、相关 webhook 配置及探针输入。Warn/Audit 本身不阻止写入；`matchConditions` 未被探针触发的分支没有测到。mutating webhook 可能改掉待测字段，应保存服务端返回对象；dry-run 不执行后续控制器，不证明真实请求与 dry-run 的外部行为相同。不支持 dry-run、匹配 `dryRun` 条件或依赖无法钉住的外部状态时，不能据此宣布真实写入被封。[准入官方语义](https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/)、[策略绑定语义](https://kubernetes.io/docs/reference/access-authn-authz/validating-admission-policy/)

- **P1 — “身份来自集群”不是完整身份枚举。** 第 72 行列出组，却没有定义如何测组及成员的完整身份上下文。证书/token 用户可仅经绑定组获权，用户名完全不出现在绑定中；多个组组合、UID、extra 还可能影响准入或授权 webhook。应保留“该组的任意成员”风险行，无法证明成员与条件范围就不清零。固定管理员、`system:masters`、匿名行有帮助，但仍须显式列出 k3s 管理凭证、节点身份和外部认证渠道；无需读取凭证内容。标准 SA token 在关联 SA 删除后会失效，不能直接认定它永久可用；外部认证及禁用相关验证的情况须另列边界。[SA token 验证](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/)

- **P1 — 仓库“三种原始行”棘轮允许权限面增长。** 第 74 行的既有通配规则可因新增 CRD 获得新权限；新增角色的聚合标签可扩大既有绑定角色；组成员增长无需改绑定；同名 task 的脚本也能改变副作用而不增加一行。基线必须记录 API 资源/子资源清单、角色标签和 aggregationRule、完整规则与名称约束、绑定作用域及主体、task 内容和实际 SA 选择方式，并覆盖准入依赖变化。外部组成员和集群漂移只能由现场复测发现，离线绿灯不能替代它。

- **P1 — 闭包的工作队列正确，但边的覆盖仍未定全。** 第 75 行只写“建 Pod / Job / run”：修改现有 Deployment/CronJob 的模板或 SA、`pods/exec`、读取可用凭证、修改任务定义，也能获得强身份。Pod dry-run 成功不证明 Job/Tekton 控制器之后一定生成同样的 Pod；控制器以自己的身份创建，随后准入可能再次拒绝。应把这些路径纳入，无法确认的边保留未知。impersonation 必须记录用户、组、UID、extra 的可用组合，不能把“可模拟组”当成普通用户名。[模拟身份语义](https://kubernetes.io/docs/reference/access-authn-authz/user-impersonation/)

- **P2 — bind / escalate 的保守行能避免旧算法漏报，但不能成为闭包终点。** 对全部在范围目标输出例外或未分类是合理的过度报告，且通常还需相应角色/绑定写权限才可利用。必须覆盖“范围外取得身份或修改控制面，再影响范围内目标”的路径；每行保留实际作用域、所需操作和后续能力。工作队列、前驱证据及截断失败解决了原来的组合膨胀方向问题，但一万次 SAR、10 分钟只是预算，尚无性能证明。

- **P2 — Owner 跑 dry-run 的选择正确，“只跑一次”不够。** 不新增常驻 impersonate 身份避免了新增强凭证，但 Owner 仍需在首次完整测量、C–F 应用后，以及身份、RBAC、API 资源、策略依赖或任务发生相关变化后复测，并有明确最长复查间隔。第 92 行退出只能证明某次快照；应记录时间、输入指纹和失效触发器，证据过期后重新出现未分类，不能长期沿用“零未分类”。

仓库事实核对：

- [check_platform_rbac.py:169](<workspace>/bifrost-trade-infra/scripts/check_platform_rbac.py:169)确实逐次创建 SAR，附 SA 三个内置组；默认运行就联网，`--live` 仅追加检查。调用身份只需 create SAR，不需 impersonate。它检查固定表，并非完整发现器。
- SAR 问的是 apiserver 的授权链，可能包含授权 webhook、Node authorizer，不仅是 RBAC；不验证凭证能否认证，也不回答准入。现有脚本第 193 行只转成 `bool(allowed)`，未区分缺失状态、无决定及 evaluationError；新测量器须保留这些状态，不能把无法判断当拒绝。`can-i --list` 也只能辅助发现，不应成为目标完整性的唯一证明。[SAR 定义](https://kubernetes.io/docs/reference/kubernetes-api/authorization-resources/subject-access-review-v1/)
- [check_admission_guards.py:191](<workspace>/bifrost-trade-infra/scripts/check_admission_guards.py:191)只有九个固定用例，使用 `kubectl apply --dry-run=server --as`；需可模拟两个指定 SA 的调用身份，另读 Application/AppProject。它没有覆盖任意动词、字段，也不保存策略指纹。第 275 行以错误字符串区分拒绝，且把目标账号的 RBAC Forbidden 也算 denied；这不能冒充有策略指纹的准入拒绝。无 impersonate 时最终 exit 3，明确跳过。
- [clusterrole-read.yaml:29](<workspace>/bifrost-trade-infra/k8s/agent-access/clusterrole-read.yaml:29)确有 VAP/binding、RBAC、CRD 等读取和 create SAR，无 impersonate；绑定给 `bifrost-access/bifrost-agent`，另绑定 `view`。文件确实缺 webhook 两类、priorityclasses、runtimeclasses 四类读取；这只能验证仓库声明，不能确认当前集群已应用或总权限仅缺这四类。

SAR 消除了自行实现组、聚合、通配和名称授权的错误，现场 dry-run 消除了离线猜测准入适用性的错误；但身份/目标遗漏、探针覆盖不足、状态失效、借用路径遗漏仍会漏报。流水线参数、finally、冻结支配等旧问题转交 B/D，并未由 A 自动解决；历史数量仍只能作为下界。

**两轮实现可以成立，但必须收紧第一轮。** 第一轮只做完整性清单、身份/目标上下文格式、SAR 原始结果采集与回放、精确基线棘轮、错误和预算处理；不输出准入 `refused`，不清零。第二轮再接 Owner dry-run 的字段级证据、失效规则和有界闭包；B 的输出接口未就绪时明确标缺失。新增 P1 是“单次拒绝扩大成字段封锁”和“原始行不变但权限面增长”，不能带进实现后再靠补丁追赶。

END OF REPORT