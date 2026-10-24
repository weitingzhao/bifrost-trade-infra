结论：**先改**。第三稿的 Pod 模板限制、参数转义和 C/D 级 apply 拒绝逻辑，按本轮所读代码没有发现会必然挡住现行正常请求的改动。545 的 F1 原始反例和 F2 已有实质修复。但 Deployment 仍允许改 finalizers，超出了“只许重启、扩缩和会话注解”的声明；验收也仍不能证明负例命中了同一策略中的目标校验。这两处应在交 Owner 操作前修改。

这是 Ops 模式的只读复审，不是上线验收。基线是 `td432-land-a` 的 **`b8e313b01f26d20ee981bbfcb6c958e3652916b1`**，相对 main `a4a8b68de65604b1edcfb963d4f78b774c45e11e`，并比较了 545 基线 `c735a215` 的指定文件。本批没有 overlay 和 S4 的绑定撤销；不能把本批合入等同于凭证迁移完成。

下文 `I/` 指本目录固定版本副本 `snapshots/infra/`；`M/` 指 review 545 的 `snapshots/platform-main/`，其来源仍是本机 platform `origin/main` **`7fe719fa3961891df1065df20463b34ee950bfaf`**。本轮用 `git show` 核对了引用的九个平台文件，均与该提交一致，见 `platform-source-check.json`。`CUT`、`OWNER` 分别指 `I/agent-config/work/multi-agent/CUT-td432-gitea-credentials-2026-10-24.md`、`OWNER-STEPS-td432-2026-10-24.md`。

**需要修改的发现**

**R1 · P2 · B：Deployment 的 finalizers 仍由 PROD 平台任意修改，F4 的严格能力声明尚未成立。**

`I/k8s/platform-rbac/47-platform-deployments.yaml:79` 开始的顶层 metadata 校验只比较 labels 和 annotations；前四条只比较 PodSpec、selector、模板 labels/annotations 和五个发布设置。五条都不读取 `metadata.finalizers`。

因此，PROD 平台拿到 `cicd/gitea` 后，保留 spec、labels、annotations，只增加合法的 `metadata.finalizers: [review546.example/hold]`，不会违反这五条规则。该身份已有 Deployment update/patch 权限：`00-clusterroles.yaml:115`、`20-prod.yaml:230`。finalizer 会改变删除时的生命周期，可能让后续删除停在 terminating；这不是重启、扩缩或会话状态记录。STG 没有这项 cicd 更新授权，不把它列为同样可做。

本轮保存了只改变 finalizer 的虚构对象，以及“所有被比较字段保持相同、五条表达式均未涉及 finalizers”的证据：`finalizer-only-deployment.json`、`offline-results.json`。这是规则和授权分析，没有向集群提交。

最小修正：冻结 finalizers；同时审视 ownerReferences 等其余可写 metadata，明确允许哪些变化，而不是把整个 metadata 等同比较。ownerReferences 还有 Kubernetes 自身的授权/准入条件，本轮**不声称**已证明可以借它让 GC 删除 Gitea。保留 resourceVersion、generation、managedFields 等正常服务端变化的处理，并补 finalizer 反例。若只打算保护 Pod 执行内容，则应明确收窄 CUT:166 的能力声明，不能继续称“UPDATE 只许改”那三个位置。

**R2 · P2 · C：验收只认策略名，仍不能确认命中了目标 validation；部分旧负例甚至不要求策略名。**

`I/scripts/check_admission_guards.py:337` 只查错误文本是否包含 `'<policy>'`，没有检查对应 validation 的 message。比如 `platform-deployment-image` 即使被“自身 annotation 变化”那条拒绝，也会算通过；`url-other-host-taskrun` 即使被同一 TaskRun 策略的其他校验拒绝，也会算通过。它们不能据此证明镜像冻结和 URL 限制分别生效。

本轮不改被审代码，替换其 I/O 为内存夹具：对全部负例返回**期望的策略名，但故意给出无关的 validation 消息**，对正例返回成功。原 `live()` 对 **103 个用例（63 个负例）返回空问题列表**，见 `offline_probe.py`、`offline-results.json`。这证明的是验收判定缺口，不是伪称执行过 CEL。

此外，`classify():434` 仍把目标身份的 RBAC Forbidden 当作 denied；未提供 policy 的旧负例会接受它。包括 `inline-pipelinerun`、`resolver-pipelinerun`、Secret workspace、hostPath、`deliver-writes-sync-script`、applier 两例及 Application 负例。当前仓库授权通常允许这些操作，不能说它们今天必被 RBAC 挡住；问题是脚本无法发现授权漂移造成的假通过。

最小修正：每个准入负例声明期望 policy/binding **和稳定的 validation 消息**；RBAC 拒绝与准入拒绝分开。保留现有求值错误检测，并补“同一策略、错误 validation 消息”的阳性对照。涉及真实对象的负例应确保确实改变字段，避免 `paused` 已为 true、`minReadySeconds` 已为 7 等情况变成无变化请求。

**A：第三稿对现行请求的兼容性**

以下“通过”是所读代码与规则的离线对照；没有实际 API server 请求。

| 改动 / 请求 | 判断与证据 |
|---|---|
| PipelineRun 总 Pod 模板、单步骤模板、直接 TaskRun 的调度设置 | `40-admission.yaml:44`、`:65`、`:217` 都禁止同一组 14 个字段；给定的 17 字段 CRD 中只剩 affinity、nodeSelector、tolerations。平台实际只设置 nodeSelector，兼容。显式 `hostNetwork: false` 或 `automountServiceAccountToken: false` 也会被拒，因为要求字段不存在，但所读平台构造器没有发这些字段。 |
| 既有 CI、五类 deliver、其他 build/smoke 请求 | 新增 Pod 字段限制不挡 nodeSelector。复用 545 从真实构造器导出的 16 组请求，重新用新正则核对其全部参数，均通过；本轮没有重新运行构造器。15 个 deliver 步骤的 SA 对应表没有在第三稿中缩减。 |
| 独立 mirror-sync / refresh-dockerfile-cms TaskRun | 平台的 amd64 模板符合限制；直接 mirror 没显式传 `mirrorRepos`，故任务默认值中的空格不触发平台请求的参数校验。刷新 revision 的普通分支、标签、SHA 符合新正则。 |
| rollout restart、普通 scale | `M/api/internal/cluster/actuation.go:112`、`:140` GET typed Deployment 后只改 restartedAt 或 replicas，再 Update。保留顶层 labels/annotations，符合 `47` 新校验。 |
| devsession stop/start | `M/api/internal/devsession/provider_k8s.go:149`、`:161` 写 `bifrost.dev/session-desired-replicas`；`:180` 读取后恢复 replicas。该注解已明确放行。没有发现正常路径会改 last-applied 或其他顶层注解。 |
| apply-manifest 的 plan | `M/api/internal/workactions/service.go:73` 传 `requireOnMain=false`；新拒绝仅检查 mode=apply，plan 不受影响。 |
| apply-manifest 的 B 级 apply | 同文件 `:101` 按最高 namespace tier 传 false；`pipeline.yaml:193` 对 A/B 放行。当前实际 namespace 表用 B/C，A 只是额外分支，不是现有请求。 |
| apply-manifest 的 C/D 级 apply、混合 namespace | 平台 `:88` 计算最高 tier，`:101` 对 C/D 传 true；流水线 `:146` 检查 main 祖先关系，`:188` 按渲染结果再算级别。与平台和 infra 的同一份 policy 对齐后，新拒绝不会挡正常 C/D 申请。daemon/X 的原拒绝仍由 checker 处理。 |
| 交付流水线产生的子 TaskRun | 由 Tekton controller 创建，不能把 Pod 将使用的 SA 当成 admission 请求身份。新增平台/tekton-deliver 身份条件不匹配 controller，子 TaskRun 的解析后模板不受这组限制误拦。 |

Deployment 的 typed GET/Update 仍有环境条件：平台依赖 `k8s.io/api v0.32.3`，给定服务端是 k3s v1.35.5。若现存 PodSpec 使用旧客户端未知的新字段，或 mutating webhook 改了被比较字段，严格等号可能拒绝。没有现存对象、Webhook 或新版服务端源码，不能把“静态兼容”说成“已验证全部线上重启正常”。

**参数正则：转义正确，RE2 有效，空值允许。**

`40-admission.yaml:159`、`:241` 是 YAML folded scalar；YAML 不再解码反斜杠。文件中每处 `\\p` 是两个反斜杠，CEL 普通字符串解码后给 RE2 一个反斜杠，最终模式为：

```text
^([\p{L}\p{N}._/:@+=][\p{L}\p{N}._/:@+=-]{0,255})?$
```

本轮以 Go `regexp` 实际编译并执行该模式：空字符串、main、40 位 SHA、`feature/fix=1`、`feature/修复`、`v0.24.0+build.1`、256 字符通过；257 字符、分号、命令替换、空格、前导 dash 不通过。外层 `?` 专门允许空值；非空为 1–256 个字符。空 `giteaBase`/`url` 仍被后面的地址条件拒绝。array/object 会被 `type(value)==string` 拒绝；给定 param value preserve-unknown-fields，不能据此误报为 CEL 的静态字符串字段类型冲突。

证据在 `param-regex.json`、`regex_probe.go`、`regex-results.json`。此验证检查了此类字符串的解码及 RE2 语法/匹配，**不是完整 CEL 编译或 Kubernetes 类型检查**。

**触发器：常用现存格式通过，但没有保持全部合法 ref 的原契约。**

`trigger-trade-ci.yaml:237` 起五条 CI 过滤要求 `refs/heads/[A-Za-z0-9._/+-]{1,200}`、小写 40 位 hex、非全零。`main`、常见的 `agent/<任务>/a1`、`w31/...`、`land/stg/...` 均匹配；普通提交、强推和合并后的 push 不因提交内容而被过滤。删除分支的全零 after 仍被排除。前三类之外的仓库仍按原 repo 名单路由，不应称为“所有仓库每次 push 都起 CI”。

`github-sync` 在 `:327`、`:328` 接受 main 或普通 `refs/tags/v...`；标签只走同步，不走 CI，与原行为一致。它没有非全零条件，所以 main/tag 删除事件仍可能触发一次同步任务；任务是否删除远端不是本次过滤器保证的事。触发器不认证发送者，40-hex 仅约束输入形状，不能证明发送者或该 SHA 的审批状态。

特别是，第三稿准入刚放行的 `feature/fix=1` 和 `feature/修复`，**在新 webhook 过滤处又会被拒**；组合 Unicode 字符、emoji 和超过 200 的 ref 也不在过滤集合内。没有查线上分支，不声称目前已有这些名字导致 CI 中断。若目标是保留平台现有合法 ref 契约，应同步处理过滤器/API，或明确产品支持的子集；CI 模板实际取的是 `body.after`，不应把 branch ref 的收窄混同为 SHA 输入校验必需。

**B：545 的 F1–F5 和 D 项签收**

| 项 | 本轮判断 | 依据 / 剩余 |
|---|---|---|
| F1：候选 Task/Pipeline + requireOnMain=false | **原始反例已修复；强来源边界仍部分** | checker 返回 C 后，新分支在 apply 前退出。本轮实际运行提取出的 shell guard，plan/B、C/D、true/false/空值组合符合预期。真实仓库、Gitea 和 main 检查没有运行。更强边界见下文。 |
| F2：hostAliases/DNS | **已修复（给定 CRD 下）** | 三处 14 字段逐一禁止，现有 nodeSelector 保留；包括 env、securityContext、runtimeClassName 等。未来 CRD 增字段仍需同步维护，这不是永久自动白名单。 |
| F3：没有 Deployment 正例、不核拒绝来源 | **部分** | 新增 11 个 replace 用例、3 个正例；另加完整 15 个步骤和 8 个 CI 步骤；求值错误不再直接当 denied。但 R2、下面 C 的请求形状/未覆盖操作仍在。 |
| F4：发布设置与 metadata | **部分** | paused、strategy、minReadySeconds、progressDeadlineSeconds、revisionHistoryLimit，及自身 labels/非例外 annotations 均已冻结；finalizers 漏口见 R1。 |
| F5：`=`、非 ASCII ref | **所报两个准入反例已修复；端到端契约部分** | 正则有效、例子通过；触发器又拒绝这两类 ref。`\p{L}`/`\p{N}` 也不等于所有合法 Git ref 字符，例如组合字符中的 Mark 和 emoji 仍拒绝。不能把它称为全量 Git ref 兼容。 |
| D：准入与撤 STG 绑定的顺序 | **文档已修复** | OWNER:107 的第 2 节先做三条策略和两个入口；第 3 节 :171 明确要求第 2 节完成且 STG 核对过。 |
| D：S5 overlay 与发布拆开 | **保留修复** | CUT:169、:174 把自动 Argo 生效、挂载核对、镜像批准分开；本批 A 没夹带 overlay。 |
| D：S7/S8、旧 Secret 读取、在途任务、撤销集合 | **操作计划已修复，实施未完成** | CUT:171–172 明列 check-source、凭证初始化、子进程环境、在途 TaskRun、rotate 脚本读取点、按本次 token 名字/ID 撤销及逐个 401；不能以本批测试替代执行证据。 |
| D：RBAC 检测器文字 | **已修复** | CUT:193 写整个 k8s、SA/User/Group；本批保留 STG/PROD 两条例外与 S4 尚未落地一致。 |
| D：Dockerfile refresh 可信 revision | **未定，未关闭** | CUT:224 仍留给 Owner 选 main/发布标签。当前仍可用候选 ref 刷新五个 Dockerfile CM；不要在 §4.1 P0 验收中把这条算成关闭。 |
| D：类型检查告警 | **本轮无法按服务端源码签收** | 本地查到 API/client-go v0.32.3，未找到 apiserver、Kubernetes 1.35 或 cel-go 的所需源文件。未下载。详细限制如下。 |

**F1 剩余的信任边界不能省略。**

1. 新代码强制的是“调用者指定仓库的 main 的祖先”，不是“固定 infra 当前受信定义”：`pipeline.yaml:122` 只检查 repo 字符，`:151` 构造该 repo 的 main；`:166` 还使用调用者给的 giteaOrg。`apply.repos/prefixes` 的五仓库名单在平台代码里执行，原始 SA 直接建 run 时，任务自身没有做同样的来源名单校验。固定 Gitea 主机并不自动固定可信仓库/路径。没有证明今天存在一个攻击者可写其 main 的可用仓库，不能将此写成已经成功的跨仓库利用。
2. applier 仍能改它自己的 Pipeline：`30-applier.yaml:47`、`:181` 授权，checker 允许 cicd/Pipeline，`40-admission.yaml:475` 只限制 hostPath/privileged 等。main 祖先 `a4a8b68` 中的同名 apply Pipeline 没有新 guard，本轮用原 checker 和虚构的“无 Argo 跟踪”读取结果检查它，确实返回 **C、exit 0**；该 SHA 是本批的祖先。于是新规则本身没有表达“不能回退 guard”。若 SSA 字段所有权允许覆盖，就能先退回旧定义，再重开旧的候选输入路径。

第二项是**已证实的策略/来源允许范围与尚未实测的可执行链**：当前线上 managedFields、SSA conflict 和实际安装历史未读，不能声称已经能够成功覆盖线上 Pipeline。字段所有权冲突也不应被当成持久授权边界。若 CUT 要证明原始平台 SA 不能恢复任意 cicd 执行输入，应把保护执行器本身及固定可信来源纳入边界，例如由独立准入限制这几个安全关键定义；若本轮只接受“选到的所有 main 历史都受信”，就应明确写出这个假设和剩余风险。`old-apply-pipeline.yaml`、`old-pipeline-checker-input.json`、`offline-results.json` 留存了离线证据。

作者关于类型检查的说法应区分两层：`status.typeChecking` 是告警状态，不等于策略创建失败；本地 `k8s.io/api@v0.32.3/admissionregistration/v1/types.go:162`、`:176` 能支持这一状态定义。**它不能单独证明 1.35.5 运行时怎样声明 object、怎样编译和求值。**在动态对象环境下，对不存在字段做 `!has(...)` 可以有合理含义；不应仅凭 `pipelineRef.bundle` 未定义告警就认定全部请求必坏。本轮没有所需服务端源码，既不把既有告警当作阻断事实，也不把“告警不影响行为”当作已核实的兼容性证据。应用后的每条新告警仍需结合实际正反例判断。

**C：`--live` 用例逐组判定**

| 用例组 | 静态预期与能证明什么 |
|---|---|
| inline、resolver、Secret workspace、hostPath、normal PR | 按当前 RBAC，PROD 能 CREATE；负例各违反 40 的相应检查，normal 能通过这些策略。旧负例没有指定 policy/message，不能保证错误来源。normal PR 缺 apply 流水线的必需参数，因此只是准入正例，不是能够完成实际 plan 的正例。 |
| CI 总模板/8 个步骤借 deliver、applier TR、deliver-other TR | 当前规则应拒绝；正例的 API 创建权属于 PROD，不依赖 STG/deliver 的 Run create。需按 R2 指定 validation 消息；它们不是“CI 真的执行过”的证据。 |
| 15 个 deliver 步骤正例 | 每个组合均在白名单，省略 params/模板时不会被其他本批规则挡住。用例来自 `deliver_steps()` 对**规则自身**的解析，不是独立地从真实构造器产生完整请求；覆盖了名单而非完整调用契约。 |
| amd64-template PR、amd64-mirror TR | 仅 nodeSelector，符合三处模板规则；其他策略也没有应拒字段。 |
| host-alias-template PR、dns-step PR、host-alias-mirror TR、env-mirror TR | 字段在禁止列表里，应被 Pod 模板 validation 拒绝，RBAC 本身允许 PROD 创建。三处都有覆盖，但不是每个禁止字段、每种位置的完整矩阵。 |
| gitea-base PR、url-other-host TR、url-gitea TR | 两个错误主机值都符合通用字符正则，因此应由地址条件拒绝；正确 URL 满足正则和前缀。现在只核策略名，没有核地址校验消息。refresh Task 没有使用名为 url 的输入，该正例能测公共参数策略，不能证明真实刷新任务按此 URL 运行。 |
| PARAM_CASES 的 11 例 | SHA、等号、汉字、tag、256 长度应通过；其余拒绝；给定 value schema 下 array 不应被当成普通 string。空值、object 值、直接 TaskRun 同组边界仍缺用例。 |
| 两平台的 9 类外来 CM、5 类自有 CM，deliver 的 2 类 CM | 当前两个平台均有 cicd CM create/update/patch，deliver 也有 Dockerfile 写所需权限；名字白名单给出的预期合理。`apply` 对已存在对象测 UPDATE、对不存在对象测 CREATE，未逐一覆盖二者，也没有 DELETE/generateName；只有第一个 Dockerfile CM 正例，不能称五个名字和所有操作都测过。 |
| Deployment 的 11 个 replace | 按表达式，3 个正例应允许，8 个负例应拒绝；但请求确实不是平台原样的 typed GET/Update，见下段。未覆盖 scale 子资源、strategic/merge patch、SSA、模板有/无其他注解两个状态以及 R1。 |
| applier hostPath / grafana SA；Application 的 source/kustomize/digest pin | 所读 RBAC 允许这些目标操作；当前表达式对构造的变化给出预期正反结果。多数旧负例仍接受任意 policy/RBAC 拒绝，应一起补目标消息。Application 从 live 对象构造有助于避免 repoURL 漂移的旧问题，但未在本轮取得 live 对象。 |

**特别回答 live `cicd/gitea` 不带 resourceVersion 的 replace。**

`live_object(..., keep_metadata=True)` 在 `:740–744` 只留下 name、namespace、labels、annotations；resourceVersion、uid、finalizers、ownerReferences 等都被删，status 也删。本轮用虚构的带 RV/finalizer 对象实际调用该函数，确认了此行为。平台真实客户端则保留 GET 回来的 ObjectMeta；所以“和平台先 GET 再 Update 一样”的描述不准确。

但也不能仅凭缺 resourceVersion 就断言 11 例都会先收到“resourceVersion required”：需要核实该 kubectl 的 Replace/helper 是否补齐 RV，以及 Deployment 的服务端 unconditional-update 行为；这些不是 CRD 普通更新的同一个问题。本轮没有找到这部分本地源代码，未作服务端请求，因此**没有把缺 RV 列为已证实的必失败原因**。本机 kubectl 的构建信息是 v1.34.1；给定服务端为 v1.35.5。

为核实客户端序列化，我尝试准备虚构 discovery cache/kubeconfig、禁网沙箱和 `replace --dry-run=client`；命令在执行前被工作区闸门拒绝（禁止指定其他 kubeconfig），未运行，也未改用真实身份重试。故本轮也不能确认该版本客户端对已有 last-applied annotation 的具体处理。推荐保留 GET 的完整 metadata，用与平台一致的 typed client `UpdateOptions{DryRun: []string{"All"}}` 生成验收请求；这能直接消除 RV、metadata 处理和客户端注解变更方面的不确定性。不要为迁就测试工具而宽放生产策略的其他 annotations。

**D：较小的问题**

- `test_ci_trigger_filters.py:39` 检查的是文字片段存在，未执行 CEL；将原过滤条件包在 `(... || true)` 中仍满足这种检查。`review_545_static():157` 同样主要检查 tier/refusal/apply 的文字顺序。它们适合防止整段漏接，不能证明条件有效；本轮原单测通过应按此解释。
- `crd_pod_template_drift():343` 说字段“exactly”一致，实际只报告新增字段和完全无 typed fields，不报告旧字段消失，也不检查 `additionalProperties`/preserve-unknown 是否改变。给定 17 字段且会裁未知字段的 schema 下可用；升级检查不应只看 properties 名单。
- `OWNER:124` 命令尾部的 `tail` 会遮蔽 Python 的退出码；要求读最后一行能识别多数失败，但建议保留检查退出码、失败立即停。对第一条策略组的 FAIL，目前 :127 只让回线程，后面还列有两条操作；宜明确“有 FAIL 就不要继续本节”。
- CUT:6、47 仍用旧 main SHA 标题，§0.1 还保留第二稿的旧 ASCII 字符集。这些有历史语境，但应明确标注历史基线，以免执行者将其当成第三稿现状。

**验证与未检查范围**

- 默认 `python3 -m pytest ...` 因系统解释器未装 pytest 失败；未安装依赖。用现有 core venv 的 python3，在本目录固定版本副本执行 BRIEF 指定的三个文件：**19 passed、6 subtests passed**。
- 同一副本执行 `python3 scripts/check_admission_guards.py`：**exit 0**，包含本地 `kubectl kustomize` 渲染；未使用 `--live`。
- Go RE2 编译/边界匹配通过；16 组旧的真实构造器参数夹具重新匹配全部通过。参数解码不是完整 CEL 编译。新增 shell tier guard 的 18 种组合按预期；旧 Pipeline 清单经原 checker 判为 C。测试中所需 kubectl 读取均为文件内虚构响应，没有真实 API I/O。
- 原 `live()` 仅在全部外部 I/O 被内存替身接管时调用，用于收集 103 个请求及验证拒绝分类器；**没有运行 live 准入验收**。
- 未访问网络、集群、MCP、SSH，未提交或编辑源 worktree。`td432-land-a` 收尾仍干净。持久报告、导出副本和离线证据都在本目录；使用了现有共享 Go 构建缓存。早期 Go 工具调用使用其默认临时目录，后续显式把 TMPDIR/GOTMPDIR 设到本目录；不将这说成严格验证过全过程只写两个目录。
- 未验证：1.35.5 服务端 CEL 编译/动态对象实现、线上 CRD 原文及默认化/Webhook、真实 kubectl replace 请求、RBAC 实际部署状态、SSA managedFields/冲突、当前 Gitea ref 与权限、发布/重启、令牌创建撤销和 S1–S8。BRIEF 给定的集群版本/CRD 字段作为输入事实使用，不标为本轮实测。未运行全套 Go 测试或令牌脚本的集成测试。

自动审批审查拒绝了上述虚构 kubeconfig 的客户端验证，理由是“这是 Owner 的凭证，写操作走平台动作或 owner_run_command；不要把 KUBECONFIG 指到规定路径以外”。该命令没有执行；没有绕过闸门。这项限制不影响已完成的代码、正则和离线脚本复审，但留下了 C 中明确列出的客户端行为未核实项。

先改
END OF REPORT
