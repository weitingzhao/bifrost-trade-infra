VERDICT: change first

只读审查完成，仓库 HEAD 为 `45169aa`；未修改文件、调用平台或集群、读取凭据。以下“关闭”仅指设计层关闭，现场前置仍须验收。第 1 步整体尚不能直接派实现，但可以先做只读矩阵分片。

五项旧 P1：
- **P1｜18-P1a 未关闭。** §3 第1步增加矩阵、审批核对和退出断言，但漏了实际写入身份与入口；“仅 Argo 能改 Deployment”又与保留 `tekton-deliver` 重启注解矛盾。须明确字段级例外，不能靠宽泛的“具名例外”归类退出。
- **P1｜18-P1b 未关闭。** §3 第1步明确了冻结前后处理，但第1–3步仍是“读冻结→发同步”，两者之间可插入冻结；第4步也只是“认领→发请求”，须定义冻结与实际副作用的串行边界。已认领但尚未发出的请求到底继续还是拒绝，应有唯一规则和并发验收。
- **P1｜18-P1c 未关闭。** §3 第4步已有权威 ConfigMap、CAS、期限及接管；第6步补了监督器接管。但 Git 非强制推送只比较分支头，不证明当前代次：旧执行者在 Git 认领后暂停，新持有者接管但尚未推送，旧推送仍可成功。现有演练暂停在认领前，漏了这个窗口；须规定在途 Git 写入排空、核销及接管规则。
- **P2｜18-P1d 设计层关闭。** §3 第6步契约①–⑦覆盖落盘确认、终态、重启判断、冲突冻结、独立权限和通知；§6.2补账户隔离与撤销。实现仍须把独立冻结与在途操作接续接到同一协议，不能冻结时递增代次后让正在收敛的操作无人能完成。
- **P2｜18-P1e 设计层关闭。** §3 第2步①②④⑤⑥固定受批准输入、执行镜像、Dockerfile、来源、目标、记录创建者和结果来源；删除、去标签、同名替换都有反例。第3步②也改为查询最新部署尝试，而非最新成功记录。

第 1 步的仓库核对：
- **P1｜矩阵漏了冻结的另一写入者。** [`rbac-deliver-stg.yaml`](<workspace>/bifrost-trade-infra/k8s/cicd/tekton/rbac-deliver-stg.yaml:12) 给 `tekton-deliver` 任意 `cicd` ConfigMap 的 create/patch/update；仅修两个平台账号的 TD-293，仍能直接解除冻结或改窗口。
- **P1｜点名 ConfigMap 不等于只能经冻结接口写。** PROD API 与绕过接口的请求使用同一个 SA；只做名称白名单仍允许直接写 `frozen=false`。须明确独立验证解除冻结授权的执行点，以及 create/update/patch/delete 的规则。
- **P1｜矩阵漏了 `bifrost-applier`。** [`30-applier.yaml`](<workspace>/bifrost-trade-infra/k8s/platform-rbac/30-applier.yaml:20) 允许它在 platform-prod 创建、更新、patch 工作负载和 ConfigMap，并改 `cicd` Pipeline/Task。`apply_manifest` 的实际执行者是它，不能仅列平台 SA；当前准入主要限制 Pod 安全与 SA，并未封住改镜像。
- **P1｜矩阵还须列间接部署入口。** `00-clusterroles.yaml` 的 workload-actuator 允许删 Pod、改 `deployments/scale`，node-drain 允许 eviction；可触发 `Always` 重拉 `:prod`。另有 Job/CronJob、ConfigMap、Service/IngressRoute 和构建定义写入，不能只枚举三个 Deployment 的普通 patch。
- **P2｜授权一次性消费尚未指定。** 首个只读 task 查“已批准、没用过”挡不住两个 run 并发消费同一单。现有审批服务会先 claim 成 running 再执行动作（`approvals/service.go:419–448`）；正常首个 task 未必还能看到 approved。须绑定审批参数哈希、确定的 run 身份及原子消费状态，覆盖创建成功但响应丢失。
- **P2｜七条缺冻结检查的流水线确实存在。** deliver-stg、deliver-prod、deliver-platform、deliver-platform-prod、build-stg、build-frontend-stg、build-research-pine 均无 release-window；TD-294 的清单正确。
- **P2｜现有检查覆盖也基本符合描述。** deliver-research、build-research-dagster、build-ib-gateway、build-market-data 引用 release-window；部分另有并行 validate 根任务，因此应断言所有产生副作用的 DAG 路径都受冻结任务支配。
- **P2｜现有 freeze task 不是完整的 fail-closed。** `task-release-window.yaml:195–205` 将 404 当空对象，缺失或非 true 的 frozen 值也放行；与“读不到按冻结算”不一致，不能直接照搬。
- **P2｜旧平台 PROD 链确实重新构建、重启、同步 HEAD。** `pipeline-deliver-platform-prod.yaml` 使用共享 Task `bifrost-rollout-platform-stg` 和 `bifrost-argocd-sync-platform-stg`，允许 namespace/application 参数；拆出的固定 PROD Task 尚不存在，这是待建项。
- **P2｜完整 SHA 同步和显式 prune 尚不存在。** Application 当前 automated/prune/selfHeal 均开启；`gitops/service.go:458–464` 和 `task-deliver-platform.yaml` 都发 HEAD，没有显式 prune。§7.1 应区分“新增接口实现”与“现场验证”，不能当现成功能。
- **P2｜apply 通道能力被高估。** 当前 `apply-manifest/actuation-policy.yaml` 与 applier RBAC 不允许 RBAC、准入策略或 Application；矩阵所称“后一类 C 级 apply 单”仅适用于允许的 Tekton 定义，安全策略仍需 Owner 通道。
- **P3｜TD 状态核对。** TD-271 已还债，策略实体在 `40-admission.yaml`；TD-272、293、294 未开始。`check_platform_rbac.py` 目前检查固定权限表，并默认调用 SubjectAccessReview；它既不生成全部写入路径，也不检查准入，更不是离线程序。

建议分片顺序；每片独立分支，第一轮审查实现和离线证据，修订后第二轮复核；两轮通过后才分别应用：
1. **P2｜A：先做只读矩阵生成器。** 汇总 RBAC 绑定、身份、资源/子资源、准入范围、Task DAG及间接写入；分开输出“仓库推导”和“现场测量”，未知项阻断退出。离线用漏身份、通配权限、缺绑定、缺策略反例验证；无集群应用；回退仅撤工具代码。应首先做，因不改变权限且能量化后续收口。
2. **P2｜B：补冻结任务与检查棘轮。** 七链加 fail-closed 根任务，旧 PROD 在首次 rollout 前复查；离线验证 DAG 支配关系及404、超时、畸形数据。Task/Pipeline 经 `plan_manifest` / `apply_manifest`；如需 RBAC，由 Owner D级应用。回退到修正后的冻结任务，不能恢复无冻结链；故障时暂停发布。
3. **P2｜C：收紧冻结/窗口写身份。** 同时处理两个平台 SA 和 `tekton-deliver`，列全合法 CM 写入，并落实解除冻结授权的独立检查。离线验证有效权限并集及准入正反例；RBAC、准入由 Owner 应用。失败时禁用相关写入口或暂停发布，不恢复任意 CM 写权限。
4. **P2｜D：封 run 绕路并绑定一次性批准。** 扩 TD-272，覆盖直接 TaskRun、解析器、SA选择及 applier 通道；固定目标 Task，审批消费绑定单次 run。离线做并发、重放、响应丢失和正常触发用例；准入/RBAC由 Owner，允许的 Tekton 定义走平台 apply，API变更走批准的发布。回退关闭受影响入口。
5. **P2｜E：建立人工完整 SHA 同步，关闭自动同步。** 先实现绑定批准、有效依赖差异、冻结串行规则和显式 prune；同片部署 Application字段保护，再关 automated、移除旧 gitops-sync及 Tekton同步权限。离线验证请求、CEL反例和渲染差异；Application、准入、RBAC由 Owner，Task更新走平台 apply。回退暂停同步、保留人工应急，不重开自动同步。
6. **P2｜F：封直接与间接 PROD 修改。** 收回平台 Deployment/scale权限，限制 applier、Pod删除/eviction及其他配置入口；仅保留绑定批准操作的旧链重启注解例外。离线断言字段差异和所有身份，重跑矩阵；RBAC/准入由 Owner，允许的任务定义走平台 apply。回退撤例外能力并停发布，不重新授予宽权限。

新增 P1：
- **P1｜冻结前的构建已经可能改变 PROD。** 旧链先覆盖 `:prod`，再查 rollout 冻结；即使 rollout 被拒，随后 Pod 重建仍可能拉到新镜像。须把“在途旧链发布标签”纳入冻结规则；若暂不能封住，Owner接受的残留必须明确包含这条，而不只是外部直接推 registry。
- **P1｜第1步的退出不能由分类替代控制。** 每条人工例外必须绑定身份、目标、字段、授权验证点和期限；“C级单”本身不是准入限制。至少补齐上述漏项、审批消费及冻结串行协议后，才能宣告第1步可整体实施。

END OF REPORT