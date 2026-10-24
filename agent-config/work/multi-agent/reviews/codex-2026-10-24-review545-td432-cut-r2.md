结论：**先改**。第 2 稿修复了 ConfigMap 的 CREATE 漏口、常规 CI 借用 `tekton-deliver`、独立 TaskRun 借用 applier，以及令牌分页的静默成功。常用发布请求的离线对照没有发现必然被拒的情况。但新规则仍允许绕过固定 Gitea 地址，也没有把 applier 的输入限制为可信来源；此外，现有验收无法发现“一律拒绝 Deployment 更新”这样的严重回归，不能直接作为启用 Fail/Deny 的放行依据。

审查基线：infra `c735a215cfd7ca34cfc0afeabebaa73954a8bf6c`，platform 分支 `0150b811b19ad3c1224b71aefb1f016cb3aee4c6`。本机 platform 的 `origin/main` 已是 **`7fe719fa3961891df1065df20463b34ee950bfaf`**，不是稿中引用的 `82b3e9d7`；按 BRIEF 用该引用的 Git 内容核对今日调用，没有 fetch 或 checkout。

下文 `I/` 为 `/Users/vision-mac-trader/agent-work/td432-infra/`；`P/` 为 `/Users/vision-mac-trader/agent-work/td432-platform/`；`M/` 为上述 platform `origin/main` 的文件路径，其只读导出位于本目录 `snapshots/platform-main/`。`CUT`、`OWNER` 分别为 `I/agent-config/work/multi-agent/CUT-td432-gitea-credentials-2026-10-24.md`、`OWNER-STEPS-td432-2026-10-24.md`。这是 Ops 模式的只读复审，不是实施或上线验收。

收尾检查时发现源 infra 的 CUT 另有一段未提交的“分批进 main”补充，两个 HEAD 都未变；这不是本轮写入。该补充与分片推送的建议一致，不改变本报告的准入结论。**CUT 行号仍对应指定提交**，固定版本已保存至 `snapshots/infra/agent-config/work/multi-agent/`，避免与正在编辑的文件混淆。

**需修正的发现（按重要性排列）**

**F1 · P1 · B/D：限定 applier 的流水线名称，仍不等于限定其执行来源。**

证据：`I/k8s/platform-rbac/40-admission.yaml:100`、`:107` 对 `bifrost-apply-manifest` 放行 `bifrost-applier`；`:131` 只检查参数字符、类型和地址，没有限制 `mode`、`requireOnMain` 的组合。`I/k8s/cicd/tekton/apply-manifest/pipeline.yaml:25` 的 `requireOnMain` 默认是 `false`，`:146` 仅在调用方传 `true` 时检查 main 祖先关系；`:188` 检查清单后，`:207` 就以 applier 执行 apply。

反例：PROD 平台 SA 直接创建引用该 Pipeline 的 PipelineRun，模板 SA 设为 `bifrost-applier`，参数为 `mode=apply`、`repo=bifrost-trade-infra`、候选分支的 40 位 `commit`、该分支中的 `k8s/cicd/tekton/...yaml`、正常 `giteaBase/giteaOrg`、`requireOnMain=false`。这些参数全部满足新准入。假定发布未冻结，它可以修改 `cicd` 的 Task/Pipeline；这些对象正是其他规则信任的“已存在任务”。

这不是仅凭名字推测：`30-applier.yaml:47` 授予 Task/Pipeline create/patch/update，`apply-manifest/actuation-policy.yaml:105` 允许这两类；本轮用无害 Task 清单和假的 kubectl 运行原始 `apply-manifest-check.sh`，实际返回 **C**、exit 0。现有 `40-admission.yaml:434` 的 applier Tekton 规则限制 hostPath/privileged，却不限制普通脚本或 SecretKeyRef。先改一个可信 Task，再引用它运行，就能重新取得任意脚本执行入口。相关离线材料：`candidate-apply-pipelinerun.json`、`checker-input.json`、`checker-result.json`。

因此 `CUT:106` 的“单由 Owner 在 Console 批，清单来自 infra main”目前只是正常平台代码路径的保证，不能用来证明原始平台 SA 的能力边界。这里采用的威胁模型与上一轮 A2/A3 相同：检查持有该 SA 的代码能做什么，而非只检查 UI 正常按钮。

最小修正：在可信 apply Task 内根据渲染出的目标独立强制来源检查，至少修改 `cicd` 的执行定义时必须来自允许仓库的 main，并且不能由 `requireOnMain=false` 关闭。准入同步约束敏感 apply 参数；需要保留候选清单的 plan/开发验收时，应明确允许的范围。不能只加一个调用方可以自行填写的“已批准”label。如果还要证明实际 Owner 审批，应另核对可信审批证据；main 归属本身也不等于审批。补“候选 Task 清单直接 apply 被拒、正常已批准 main 清单可应用”的用例。

**F2 · P1 · B：固定 URL 字符串，没有固定请求实际到达的主机。**

证据：`40-admission.yaml:44`、`:54` 的两级 PipelineRun Pod 模板和 `:192` 的 TaskRun Pod 模板，仅禁止 volumes 与 hostNetwork；没有限制 `hostAliases`、DNS 设置。`:135`、`:201` 只比较 `giteaBase`/`url` 的字符串。

反例：PROD 平台建立 `taskRef.name=bifrost-gitea-mirror-sync`、SA 为 `default` 的 TaskRun，不传参数，使用 Task 的正常 Gitea 默认地址，但在 `spec.podTemplate.hostAliases` 把 `gitea.cicd.svc.cluster.local` 指向另一个可达主机。新规则全部放行；Task 的 `:35` 注入管理员令牌，`:73` 把它作为请求头发往这个名字。该任务用明文 HTTP，无法靠服务器证书识别替换。相同字段也能放在 PipelineRun 的总模板或单步骤模板。离线请求见 `host-alias-taskrun.json`，其中使用文档示例 IP，未发送请求。

S7 换成 reader 后仍应关此口：它继续允许把只读凭据发到另一台主机；用于 Dockerfile 刷新时，还会破坏“内容来自内部 Gitea”的来源假设。只把任务里的主机字符串写死也不能抵御 Pod 的主机解析覆盖。

最小修正：三处 Pod 模板采用实际需要的字段白名单，至少拒绝 `hostAliases` 和可替换解析目标的 `dnsConfig/dnsPolicy`；保留当前的 nodeSelector、tolerations 等调度设置。加三种位置的反例，以及真实调度模板的正例。线上 Tekton CRD、Webhook 和网络可达性本轮未核实，因此这是清单和调用链证明的漏口，不是假称已经完成凭据外发复现。

**F3 · P1 · A/C/D：部署准入没有正常更新正例，静态通过和 policy dry-run 不能证明上线安全。**

证据：`I/scripts/check_admission_guards.py:265` 只生成“更换 Gitea 镜像被拒”这一种 Deployment 请求；没有重启、完整对象 scale、`deployments/scale`、无模板注解时添加注解、保留已有其他注解的放行用例。`dry_run` 在 `:359` 统一使用 client-side `kubectl apply --dry-run=server`，没有覆盖平台真实的 GET → typed Update，也不是 SSA。`:352` 只要 stderr 含 `ValidatingAdmissionPolicy` 就算 denied，没有核对策略名、消息及是否是求值错误。

离线阳性对照：只在本目录副本中把 `47-platform-deployments.yaml` 第一条验证改为 `false`，使所有匹配的 Deployment 更新都应被拒。**静态检查仍 exit 0，相关 15 项测试仍全过**，结果保存于 `mutation-results.json`；随后已恢复副本。现有 live 的那个负例也无法区分这个错误实现与正确实现。它同样可能把表达式运行错误导致的 Fail/Deny 误当成“成功保护镜像”。

最小修正：增加完整的正常重启/扩缩和 metadata/defaulting 正例，使用实际 GET 得到的对象，以平台相同方式做 dry-run Update，并补 strategic/merge patch、SSA 与 scale 子资源。负例要求返回**指定 policy/binding 的指定验证消息**，把类型错误、求值错误、其他策略拒绝、RBAC 拒绝分别报告。用于证明准入的反例应先确认该 SA 在 RBAC 上允许该操作。

`OWNER:136` 的 policy server dry-run 可查对象结构及表达式合法性的一部分，但没有运行其匹配的业务请求，也不能替代资源类型检查状态。Kubernetes 类型检查结果另在 `status.typeChecking.expressionWarnings`，本机依赖 `k8s.io/api@v0.32.3/admissionregistration/v1/types.go:162`、`:176` 明确区分这一状态。`OWNER:139` 的“没有 error 就真正应用”过于乐观。应先检查类型状态、用覆盖完整的请求核对预期，再启用硬拒绝；必要时先以隔离的验证环境或临时 Warn/Audit 绑定核对。不能在没有 Deployment 正例的情况下把整包 Fail/Deny 生效当作测试前置条件。

**F4 · P2 · B：Deployment 规则并未实现“只能改副本数和 restartedAt”。**

证据：`47-platform-deployments.yaml:39`、`:43`、`:48` 只冻结 PodSpec、selector、模板 labels 和其他模板 annotations。它不检查 Deployment 的 `spec.paused`、`strategy`、`minReadySeconds`、`progressDeadlineSeconds`、`revisionHistoryLimit`，也不限制顶层 metadata。

反例：保持上述受检字段原样，设置 `spec.paused=true`，新规则通过，正常 rollout restart 将不能引起新一轮 rollout；改 strategy 为 Recreate 同样通过。这没有证明能换容器代码，但违反了 `CUT:151` 的声明，也会影响发布行为。

最小修正：明确冻结其余 Deployment spec 字段；顶层 metadata 只放行平台确有需要的注解等变化。保留 `M/api/internal/devsession/provider_k8s.go:158` 的 desired-replicas 记录需求。不要用整个 `object == oldObject` 补洞，否则 resourceVersion、generation、managedFields 等正常变化又会导致误拒。补 paused/strategy 反例。

**F5 · P2 · A：参数字符白名单收窄了现行合法 ref 契约。**

证据：`40-admission.yaml:134` 的白名单不含 `=` 和非 ASCII 字符。`M/api/internal/delivery/service.go:1161` 的现行 revision 校验允许这些字符；`ref_preflight.go:35`、`:45` 能按分支/标签名确认它们；`run_spec.go:27` 会原样把 ref 放进参数。

例子：`feature/fix=1` 是合法 Git 分支名，本轮本地 `git check-ref-format` 通过。`feature/修复` 也是平台现行校验和构造器可接受的输入。对这两个值调用真实 `validateRevision`、`platformRunInputs`、`buildPipelineRunSpec` 均通过，得到的 PipelineRun 却被新参数条件拒绝，材料见 `edge-run-shapes.json`。前提是相应仓库确有该 ref；本轮没有查线上分支，**不声称今天已有哪次发布因此失败**。

最小修正：按参数语义校验，避免全局字符集代替 Git ref 契约；完成 env/argv 传参后保留合法 ref，或将已确认存在的各仓库 ref 解析为 SHA 后提交 run。若有意只支持这套字符，应同步 API/界面可选项并明确这次兼容性变化。平台分支 `P/api/internal/delivery/supply_chain.go:419` 的刷新限制只覆盖刷新 TaskRun，不能代替其他 PipelineRun 的兼容处理。

**A：现行写入路径逐项对照**

下表“通过”指按所读清单和当前构造器满足规则，**不代表已在 API server 实测**。所有 API 创建动作仍先受现有 RBAC 约束。

| 现行请求 | 真实形状/调用位置 | 新规则结果 |
|---|---|---|
| `bifrost-ci-platform/frontend/python` PipelineRun | `M/api/internal/delivery/ci_run.go:56`：40 位 revision、main/uiRevision 或固定 repo；default、amd64 模板、临时 PVC | 通过；不使用数组或对象 params |
| `bifrost-deliver-stg` | `run_spec.go:54`：只有 prepare、rollout、gitops-sync 设 `tekton-deliver`，其余 default | 三组均在 `40:110` 白名单，常规参数通过 |
| `bifrost-deliver-prod` | `run_spec.go:61`：同三步骤；逐仓 `*Revision`，由 `params.go:55` 合并 | 三组均在 `40:113`，常规 ref/SHA 通过 |
| `bifrost-deliver-platform` | `run_spec.go:68` → `service.go:1528`：rollout、gitops-sync；Pipeline 存在 agentrt-migrate 时再加它 | 三组均在 `40:116`；不是漏掉迁移步骤 |
| `bifrost-deliver-platform-prod` | 同一构造器：rollout、gitops-sync；Pipeline 存在 check-source 时再加它 | 三组均在 `40:119`；check-source 允许，agentrt-schema 仍用 default |
| `bifrost-deliver-research` | `run_spec.go:74`：rollout-research、verify-research、gitops-sync 为 deliver | 三组均在 `40:122`；revision、tag 常规值通过 |
| build-stg、build-frontend-stg、build-market-data、build-flex-query、build-ib-gateway、build-research-dagster；smoke/其他 Pipeline fallback | `service.go:508`、`:577`，`preflight.go:12`：字符串 revision/image/tag，default 或省略 SA，PVC/emptyDir | 所读现行请求通过；测试导出的 16 个仓库内 Pipeline 含 research-pine、clone-frontend-smoke。flex-query 的分支按同一 builder 分支另行静态核对 |
| plan/apply-manifest PipelineRun | `M/api/internal/workactions/service.go:278`：bifrost-applier，mode/repo/path/commit/giteaBase/giteaOrg/requireOnMain 均为字符串 | 正常路径通过；`giteaBase` 配置确实带 `/bifrost`（`config/actuation-policy.yaml:9`），不是根 URL。能力边界见 F1 |
| 独立 mirror-sync TaskRun | `M/api/internal/delivery/supply_chain.go:405`、`:447`：default、amd64 模板，无显式 params/workspace | 通过。Task 自身 `mirrorRepos` 默认值有空格，但不是平台提交的 params |
| 独立 refresh-dockerfile-cms TaskRun | `supply_chain.go:409`、`:456`：deliver、source PVC、revision 字符串 | main/常用分支通过；P 分支新增 ref 形状校验后也满足新字符条件。来源信任仍待 CUT §6 #4 决策及 F2 修正 |
| PipelineRun 删除 | `M/api/internal/delivery/service.go:394` | PR/TR policy 只匹配 CREATE/UPDATE；DELETE 不受它们阻挡，RBAC 仍决定能否删 |
| `lineage-thread-titles` ConfigMap | `M/api/internal/threadtitles/threadtitles.go:35`、`:123`：Create/Update，正文可有任意标题字符 | 精确名通过；参数正则不会检查 ConfigMap data |
| `bifrost-release-window` | `M/api/internal/delivery/window_store.go:176`、`:186`、`:200`、`:232`：Create/Update/Delete，过期清理也走 Delete | 精确名通过；DELETE 用 oldObject。只有 PROD 有该名字的 delete RBAC（`45-release-window.yaml:15`） |
| `bifrost-release-policy` / `bifrost-release-freeze` | `releasepolicy/policy.go:25`、`:26` → `delivery/release_policy_facts.go:60`：Create/Update，签名和多行文本在 data | 两个精确名通过；不会被参数长度限制误拒 |
| `release-<run>` 记录 | `M/api/internal/releases/record.go:56`、`releases/service.go:220`、`:226` | Create/Update 的前缀匹配通过；现行记录器无删除需求 |
| platform-state-*、agentrt | `statefile/k8sstate` 取 Pod 本身 namespace；当前 overlay 没改到 cicd。`server/agentrt_*` 和 `internal/agentrt` 未找到独立 cicd PR/TR/CM/Deployment writer | 不需要扩宽 cicd CM 名单。agentrt 的 CI/发布观察是读取；STG 数据迁移是下表的交付任务 |
| 平台 rollout restart | `M/api/internal/cluster/actuation.go:112`：GET 完整 Deployment，改模板 restartedAt，再 typed Update | 受 47 约束，正常应通过；不是直接发 kubectl patch。API server 默认化/版本差异未实测，见 F3 |
| 平台 scale、devsession stop/start | `actuation.go:140`、`:154`：改 replicas 后 Update；`devsession/provider_k8s.go:158` 先写顶层 desired-replicas 注解 | 正常应通过；顶层 metadata 未冻结。`kubectl scale` 的 scale 子资源不匹配 47，正常可用，不能通过它换 PodSpec |

交付流水线的内部动作也逐个核对了：

| 流水线内部步骤 | 实际运行/请求身份及操作 | 是否被新规则拦截 |
|---|---|---|
| 五条 `pipeline-deliver-*.yaml` 的所有子 TaskRun | 由 **Tekton controller** 创建。其 `spec.serviceAccountName` 是 Pod 使用的 SA，不是 admission 的 `request.userInfo.username` | 子 TaskRun 不匹配平台/tekton-deliver 身份条件，允许内嵌 TaskSpec、解析出的 PVC 工作区；不能误把新的独立 TaskRun 限制套到这些对象上 |
| Trade STG/PROD prepare | `tekton-deliver`；`task-prepare-deliver-stg.yaml:69`–`:80` create/apply 三个 API/frontend/worker Dockerfile CM | 三个名字都在 46 的五项名单，允许；它的并发检查只读 runs |
| 独立 Dockerfile 刷新 | `tekton-deliver`；`task-refresh-dockerfile-cms.yaml:54`–`:68` create/apply 五个 CM | 全部允许；client-side apply 的 last-applied annotation 不参与 CM 授权 |
| platform 的 stage Dockerfile / build / promote-images | default；stage 只读挂载 CM、写 workspace 文件；Kaniko/镜像提升写 registry | 没有被误认成 CM API 写入 |
| Trade rollout / platform rollout / research rollout | `tekton-deliver`，相应 task 中执行 `kubectl rollout restart/status`；research verify 读 Deployment | 47 只匹配两平台 SA，不匹配 deliver；正常通过。deliver 在 cicd 没有任意 Deployment patch 权限 |
| 各 gitops-sync | `tekton-deliver`，patch Argo Application；platform 另钉两个镜像 digest | 不属于新增 CM/Deployment 限制；原有 Application policy 的 digest pin 例外仍在，未被这次改动删除 |
| platform STG agentrt-migrate | `tekton-deliver`；`task-agentrt-migrate-stg.yaml:52` 生成 `bifrost-platform-stg` 的 Job，Job 用 default、无 SA token | 不是 cicd Deployment/CM/Run 写；步骤身份白名单已包含它 |
| platform PROD check-source / agentrt-schema | 前者 deliver，后者 default；检查来源、历史 run 和数据库，不改 cicd CM/Deployment | 身份配置正确；check-source 的旧克隆 Secret 必须按 S7 迁走 |
| freeze-check、mirror-sync、clone、tests、pin-check、verify 等其余步骤 | 默认 SA；冻结/窗口读取、Git/测试/registry/HTTP 工作。Task 可能挂载 CM/Secret，但没有新 CM 写 | 当前流程不会被这三组新增约束误拒；挂载可信性和候选代码凭据问题仍由 S7/F1/F2 处理 |

参数边界的明确结论：平台 Go API 的 `Params` 是 `map[string]string`（`delivery/types.go:126`），现行生成器也都写字符串；本轮所读 cicd 清单中没有发现 array/object 的现行顶层参数。**若直接提交 array 或 object value，新规则必拒**，`type(p.value)==string` 不会把它们放行。不能称其兼容“所有合法 Tekton 参数”。同理，空格、逗号、`=`、非 ASCII、超过 256 的显式 value 都会被拒。现行常用 SHA/main、镜像/tag/地址符合限制；合法 ref 的具体收窄见 F5；未找到现行固定生成的 >256 参数。apply path 的代码契约未设相同长度上限，未来较长合法路径也需对齐。

`mirrorRepos` 的空格、任务脚本、多行签名，以及内部任务间的结果替换，不应因看见字符超集就直接报为发布必坏：必须先判断它们是否真的出现在受检身份提交的 `spec.params` 中。当前平台没有显式提交 mirrorRepos；控制器产生的子 TaskRun 也不匹配。线上 Webhook/default-service-account/参数默认化配置尚须在真实请求测试中确认。

**B：授权主体、操作和漏测项**

| 策略组 | 匹配身份与实际 RBAC | CREATE/UPDATE/DELETE、缺字段及子资源结论 |
|---|---|---|
| PR/TR（40） | 匹配 STG、PROD 平台与 cicd/tekton-deliver；当前只有 PROD 平台拥有 create/delete Run（`00-clusterroles.yaml:170`、`20-prod.yaml:272`）。STG/deliver 没有 Run create。`tekton-trigger` 有 create（`rbac-trigger.yaml:17`），却明确不匹配；Tekton controller 也不匹配 | CREATE/UPDATE 检查新对象；DELETE 不匹配。generateName 不改变引用/身份条件。status 子资源未匹配，所读平台 RBAC 也没授 status 写。缺 pipelineRef/taskRef 会被首条拒绝，后续字段访问即使报错也会 Fail，不是 fail-open。省略 params、SA、workspace 会使对应可选检查通过，必须另审可信默认值及 F1 |
| cicd CM（46） | 匹配两平台和 deliver，与直接宽 CM 写授权吻合；applier/Owner/控制器不匹配。applier 的 cicd 角色只给特定 CM get 和 Tekton 定义写，不能把注释“Owner and applier”理解为其已有任意 cicd CM 写权限 | CREATE/UPDATE 检查 object.name；DELETE 检查 oldObject.name，避免 object=null。generateName 在验证前生成实际 name；`release-` 生成名可按预期通过，外来前缀仍拒。平台可删四个精确名的 policy 许可比 RBAC 宽，但当前 RBAC 最终只让 PROD 删 window。release-* 与 deliver 的全部 DELETE 被策略拒绝。ConfigMap 没有可借用的 scale/status 写入口 |
| Deployment（47） | 所有 namespace 的两平台 SA；PROD 的 cicd workload-actuator 有 update/patch 和 scale，STG 没有。Argo/Owner/applier/deliver 不匹配 | 主资源 UPDATE；PATCH/已有对象的 apply 按 UPDATE 检查合并后的对象。未匹配 CREATE，但平台没有 cicd Deployment create，不能靠 SSA 创建绕过。scale 子资源只携带副本数，不是 PodSpec 旁路；status 未匹配但平台没有其写权限。没有 DELETE 授权。PodSpec/selector/labels/模板其他 annotations 能挡住直接换镜像/挂 Secret，但 F4 的其他字段还开放 |

对 `object` 与 `oldObject`：47 没有比较顶层 metadata/status，因此普通 resourceVersion、generation、managedFields、last-applied 变化本身不会触发拒绝。规则看到的是 API server 处理后的完整对象，不是 PATCH 的稀疏文档。存储读取和请求默认化通常会让相同 PodSpec 可比较；若 typed client 丢失服务端新增字段，或 mutating webhook 真改了 PodSpec，严格等号仍会拒绝。当前依赖是 Kubernetes Go API v0.32.3，实际服务端版本、特性、已存字段和 Webhook 本轮未查，不能把这一部分说成已经验证兼容。

`--live` 仍缺以下用例，不能只补更多对象名字：

1. 用真实平台构造器产生五种 deliver、三种 CI、完整 plan/apply、两个 standalone TaskRun 请求；覆盖全部 15 个 deliver 步骤组合。现有 deliver 正例仅 rollout 一个步骤。
2. 直接 TaskRun 的参数非法类型/字符、`url` 别的主机与正确主机、array/object、长度 256/257、合法边界 ref；hostAliases/DNS 的三个位置；CI 每个实际候选步骤选高权限 SA 的反例。现有 `ci-as-deliver` 例子用的是泛称 `test`，真实 pipeline 的 Go/console 步骤也应测。
3. CM 显式 CREATE、UPDATE、PATCH、DELETE、generateName；四个精确平台名、release 前缀、五个 Dockerfile 均有正例，外来名字有相应负例。当前统一 apply 会依据对象是否存在只覆盖 CREATE 或 UPDATE 之一，**不会同时覆盖两者，也不覆盖 DELETE/generateName**。精确名 DELETE 的 RBAC 拒绝不能证明 policy 的 oldObject 分支正确。
4. Deployment 正常 restart/scale/顶层 devsession 注解、scale 子资源、已有其他模板注解及无注解两种情况；不同 patch/SSA/typed Update；镜像、命令、SA、卷、labels、其他注解和 F4 字段的反例。
5. 断言拒绝来自指定规则，记录类型/求值错误。现有 `test_access_checks.py` 的生成用例断言只能证明“代码产生过请求”，不能证明 CEL 接受或拒绝得对；F3 的 mutation 已说明这一点。
6. F1 的高权限 PipelineRun 及候选 Task 清单链；trigger 身份未覆盖需要在最终证据矩阵中明确作为信任边界或另行收紧，不能因为策略列了三种身份就声称覆盖所有能建 run 的主体。

**C：CEL 静态检查结论**

没有找到可以负责任断言“这批新增表达式一定编译失败”的语法错误；**也没有完成 CEL 编译**。本机未发现可用的 apiserver/CEL 编译器及线上 Tekton CRD，未下载依赖。

- `46:49` 的 name 变量先定义再使用，`deliver` 同样如此，没有前向引用。DELETE 的三元表达式选择 oldObject，非 DELETE 选择 object，不应在 DELETE 时读取 null object。
- `40:133`、`:199` 的 `type(value)==string` 是类型比较；`.matches` 不是对数组无条件执行。数组/对象值应得拒绝，不能把拒绝非字符串误报成语法错误。缺 value 的非法请求会由 schema/表达式错误拒绝，不会静默变成 true。
- `47:43` 先比较 labels 存在性；模板 annotations 的两向检查会拒绝增加、改变或删除非 restartedAt 项。允许从无 annotations 增加 restartedAt，或仅移除 restartedAt，符合其声明的例外。
- `has()` 的存在性守卫、字符串键索引、map 的 `.all(k, ...)` 在这些新增表达式中没有看到明显语法问题。Tekton 资源的具体 schema/type-check 告警和运行时求值仍须由实际 API server 核对。
- 需修正的是“policy dry-run 无 error 即已完成类型/业务兼容验证”的交付说法，见 F3。不要把本轮 Python 条件对照称为 CEL 编译或服务端准入验收。

**D：对 review 542 与第 2 稿切法的结论**

| review 542 项 | 本轮签收程度 |
|---|---|
| A1 / TD-434 | 实现层已补 CREATE/UPDATE/DELETE，名字来源正确，包含两个平台和 deliver；实际操作矩阵验收仍欠缺，见 B |
| A2 | 直接修改 Gitea PodSpec 的入口被 47 的等号限制；正常重启放行未做 live 验证，其他 Deployment 字段承诺未实现（F3/F4） |
| A3 | CI 不再能选 deliver 模板/任意步骤，独立 TR 不能借 applier；shell 字符注入有兜底。但 F1/F2 表明“引用名 + SA + 参数字符”尚未关闭间接能力 |
| A4 | S7 明确加入 PROD check-source，S8 明确扫描消费者，方向正确。仍须把管理脚本的旧 Secret **读取/检查依赖**列进验收：`rotate-admin-token.sh:83`、`:84` 和 `:331` 不会因为停止写 clone token 自动消失；现行脚本仍是旧版，不将尚待 S7 实现本身另报为本次代码缺陷 |
| A5 | 已写明撤销切换前旧管理员/克隆令牌并逐个验证 401；这次不是只换值或只检查历史泄漏 token。细化 S8 操作单时须先记清本次旧 token 的身份/ID和需要验证的集合，不能依赖现有 `revoked` 子命令固定历史 blob 的集合 |
| A6 | 已修复。第 40 页仍非空时失败；第 21 页有可写仓库、查不到末页、缺权限、正常分页、replace 正反例在离线测试中通过 |
| B 的 S5 拆分 | 接受：先单独获准推 PROD overlay，Argo 自动生效，核对 api/workers 挂载，再批同一已验 STG 提交的发布，之后 S6。不要一次推整个分支提前触发两个 overlay。Pod 文件实读需 Owner 的可执行身份或受控验证途径；普通 Agent 不应临时在平台 namespace 用 kubectl exec |
| B 的 S7/S8 | 接受凭证初始化、git 子进程环境、在途 TaskRun 和工作区检查方向；S8 的撤销是必要条件。S7 后还要验证 PROD check-source 与完整发布路径，不能只跑一次 CI clone |
| B 的范围和 P0 | 收窄到平台/CI/执行/评审及明确受信任控制器，比“除 Owner 外无人能读”准确。`CUT:159` 的顺序门槛合理，但须把 F1/F2 的修复及真实准入矩阵作为 TD-435/436 完成条件；`can-i=no`、本轮单测、S4/S6 都不能关闭 P0 |
| C 的 RBAC 检测器 | `test_platform_rbac_secrets.py:68` 已识别 SA/User/Group，`:111` 扫整个 k8s，相关正控通过。它仍是仓库清单检测，不是线上完整授权证明；`CUT:168` 仍写只读 platform-rbac/*.yaml，与实现及 §0 不一致，改文案即可 |
| C 的回退/本地开发/数量 | 删除 Secret 只限 S1、使用后 replace、新旧镜像分开回退、本地 bdev 无 reader 的预期都已说明；S4 行数及 tekton-deliver 建 run 的错误已更正 |

还有一处顺序应改：`CUT:150`–`:153` 明确 S3b/c/d 在 S4 前，`OWNER:107` 却先让 Owner 删 STG 绑定，`:131` 才做准入，而且只说“同一天”。最小修正是将 2b 移到删除绑定之前，并明确验证通过才进 S4；如果保留当前顺序，应明确仍处于未关闭间接入口的过渡期。更要避免宣称 S3b 单独完成就已使 STG/PROD 拿不到管理员能力。

`CUT:198` 的 Dockerfile revision 决策仍未落地：形状像分支/标签不等于可信 main/发布标签。不能把 `0150b811` 视为已经落实该推荐；最终 P0 验收要写明选了哪种信任范围，发布标签还需核其写保护。S8 的集群级控制器信任例外和 trigger 读 Secret 也必须在证据矩阵中逐项列明。

“6 次、约 70 分钟”只能作为分组后的理想操作预算。S5 已明确需要 overlay 授权和 Console 发布批准两次不同动作；把同日几个动作视为一个时段可以，但不能让数字掩盖这些步骤。第 2 稿已不再承诺排障和全量验收都能在这个时长内完成，这一点接受。

**实际验证、材料及限制**

- 仅在本目录导出指定 Git 内容和创建验证材料；源 worktree 未编辑、未提交、未更新引用。未访问网络、集群、MCP、SSH，未读取任何真实凭据。
- 默认 `/opt/homebrew/bin/python3` 缺 pytest/PyYAML，初次命令失败；随后复用已有 core venv 的解释器，未安装软件。副本上原始 `test_access_checks.py` 与 `test_platform_rbac_secrets.py`：**15 passed，6 subtests passed**；`python3 scripts/check_admission_guards.py`：exit 0，包含本地 kustomize 渲染。
- 按 BRIEF 的三个测试文件完整执行：**22 passed，24 subtests passed**。原 token 测试会启动 loopback HTTP server；为遵守“no network”，仅在副本添加 `snapshots/infra/conftest.py`，用文件 IPC 的 fake curl 调用**原测试的同一个 HTTP handler**，保留断言、脚本和 fake kubectl，且禁用 Python socket。此结果验证脚本分支及假响应契约，不等于真实 curl/HTTP/Gitea/集群集成测试通过。
- `snapshots/platform-main/api/internal/delivery/review545_test.go` 在当前 main 的真实构造器上导出 16 种 run 和两个合法边界 ref；`go test ./internal/delivery -run '^TestReview545'` 通过。`GOPROXY/GOSUMDB` 关闭，使用已有缓存，无网络、无 Kubernetes client。输出见 `run-shapes.json`、`edge-run-shapes.json`。
- `offline_probe.py` 对照新条件、保存无害反例，并实际运行原始 apply checker；结果见 `offline-results.json`。其中 Python 谓词是辅助推演，**不是 CEL 引擎**；实际 checker 接受候选 Task 类型是独立执行所得。
- `mutation-results.json` 保存了 Deployment “全部拒绝”变体仍通过静态和 15 项测试的证据；只改过副本，已恢复。
- 未运行 `--live`、服务器 dry-run、线上 typeChecking/CRD 检查、真实发布/重启/scale、真实 Gitea 权限和 token 撤销、11 仓库保护验证、06 主机隔离、镜像内容与现存 Pod/工作区检查。报告中的线上状态只引用作者记录，不作为本轮实测。没有运行 Go 全套测试。

先改
END OF REPORT
