结论：**先改**。本补丁有一项已离线复现的兼容性回归：C/D 级从较旧 main 提交申请 apply 时，即使该路径的渲染完全没变，只要包含可跳过的现存 Namespace，也会被新增比较误拒。B、C 项未发现另一项确定的新阻断问题。

范围仅为 infra `b8e313b01f26d20ee981bbfcb6c958e3652916b1..e889aa681a50a3cd712061a8e620e25bdc8f5f0b`；已读 review 546 及作者回应。平台对照使用本地 `origin/main=7fe719fa3961891df1065df20463b34ee950bfaf`，未 fetch。以下 infra 行号均指补丁终点；本目录 `snapshot/` 保存了该提交的固定副本，`platform-main/` 保存了所用平台文件。

**R1 · P2 · A：比较的两侧处于不同处理阶段，误拒未变的旧 main 提交。**

[pipeline.yaml:234](/Users/vision-mac-trader/agent-work/codex-review-548/snapshot/k8s/cicd/tekton/apply-manifest/pipeline.yaml:234) 新增的比较使用 `/tmp/normalized.json` 和 `/tmp/head-normalized.json`。但前者在第 213 行已经经过 checker，而 [apply-manifest-check.sh:197](/Users/vision-mac-trader/agent-work/codex-review-548/snapshot/k8s/cicd/tekton/apply-manifest/apply-manifest-check.sh:197) 会原地删去已经存在且标签符合要求的 Namespace。后者仅经过 `render`，仍含这些 Namespace。

离线反例：同一仓库、同一路径，两份归档中的对象完全一致，均为 `Namespace/plugin-market-data` 加该 namespace 下一个 ConfigMap；模拟 Namespace 已存在、标签符合、对象没有 Argo tracking，提交是 main 的祖先。真实 checker 输出 C，并从候选 List 中删去 Namespace；main 头 List 则保留它。最终 `cmp` 不同，退出 1，未进入 apply，错误却称路径在 main 头发生了变化。改用 main 头 SHA 时跳过比较，成功。把夹具中的 namespace tier 改为 D，也重现同样结果。

这符合当前平台可发起的正常请求：`workactions/service.go:101` 对 C/D 传 `requireOnMain=true`，没有要求计划提交就是最新 SHA；当前允许的 market-data、flex-query 仓库 `k8s/base/kustomization.yaml` 都包含 `namespace.yaml`。不需要路径内容真的变过：计划后 main 只增加一个无关提交即可触发。没有读取线上计划或 Gitea，故不声称已发生生产失败。

建议在 checker 改写前保存完整候选渲染，与完整 head 渲染比较；apply 继续使用 checker 检查、删去 Namespace 后的文件。也可明确对两侧做完全相同的处理，但不要为比较而取消现有 Namespace 标签检查。补一个“main 前进、渲染不变、含现存 Namespace”的成功用例，以及内容确实改变的拒绝用例。

复现脚本：[offline_pipeline_probe.py](/Users/vision-mac-trader/agent-work/codex-review-548/offline_pipeline_probe.py)。结果：[pipeline-probe/results.json](/Users/vision-mac-trader/agent-work/codex-review-548/pipeline-probe/results.json)；`C-old-with-namespace/tmp/` 保留了比较两侧的实际 JSON。没有修改被审代码。

**A：其余 apply 路径与 shell 判断。**

| 场景 | 本轮结论 |
|---|---|
| B，从分支，`requireOnMain=false` | 离线通过；一次 render、不 clone、不访问 `/tmp/main.git`。 |
| C，从 main 头 | 离线通过；一次 render，包括含现存 Namespace 的情况。 |
| C，从较旧 main，渲染未变且没有 Namespace | 离线通过；两次 render，比较相同。 |
| C，从较旧 main，含现存 Namespace | R1：即使渲染未变也误拒。 |
| C，从较旧 main，渲染确实改变 | 离线拒绝，未进入 apply。 |
| C，`requireOnMain=false` | 在读取 bare clone 之前拒绝，没有因 clone 不存在而误走比较。 |
| plan，`requireOnMain=false` | 离线通过；不进入 head 比较，仍执行 checker 和 diff。 |
| D | 用改为 D 的离线 policy 复现了未变通过、改变拒绝和 R1；当前真实 policy 只有 B/C，不能称为现存 D 请求的实测。 |

来源名单与当前平台对齐：平台 `config/actuation-policy.yaml` 和挂载源文件逐字节相同；`giteaOrg=bifrost`、`giteaBase=http://gitea.cicd.svc.cluster.local:3000/bifrost` 均由平台的 Delivery 配置传入。awk 对当前五仓库、当前无首尾斜杠的 prefixes，执行的是与 [RepoAllowed:174](/Users/vision-mac-trader/agent-work/codex-review-548/platform-main/api/internal/actuationpolicy/policy.go:174) 一致的“等于前缀或以 `前缀/` 开头”。例如 `k8s` 不会放行 `k8sx`。错误 org、base、repo、path 的离线用例都在 clone/render 前退出。当前配置下没有发现新检查挡住平台正常来源。

不过 awk 是对当前 YAML 排版的解析，并非通用 YAML 等价实现：Go 会去掉 prefix 首尾 `/`，awk 不会；引号、缩进改写也可能改变其读值。当前文件没有这些情况，所以不据此另报现存兼容性故障。

`sh -n` 通过。`render` 的 `$1/$2/$3` 是函数位置参数；`archive/url/host_path/root/target` 虽是全局变量，第二次覆盖后也不会把 apply 切到 head 文件：后续 apply、results 仍使用候选的固定文件。`head` 变量不会遮蔽 `head -n 1` 命令。两次归档目录和输出文件分开。`set -u` 所需的 `REQUIRE_ON_MAIN` 当前平台始终传入；C/D 在其为 false 时先拒绝，只有 true 且 clone 成功才能到 `rev-parse`。

对于来源保证：在两次渲染及规范化成功、所比较的 main 头固定的前提下，没有找到 C/D 把不等于该仓库该路径 head 结果的对象送入 apply 的新路径；旧版流水线定义若与 head 不同，会被比较挡住。这里信任的是 policy 允许的仓库及其 main，并非只信任 infra。`head` 是 clone 时读到的快照，后续未重新读取远端；不能把它解释为与 apply 瞬间不断前进的远端 main 原子同步。

有一个沿用旧实现的 shell 限制需要保留：第 209 行 `kubectl create ... | jq -s ...` 在 `set -eu` 下只检查最后一个命令的状态；前端失败但已输出部分合法 JSON 时，jq 仍可能成功。不要把 `set -e` 说成已验证完整规范化成功。建议先单独写 JSON、确认 kubectl 成功，再 jq；本轮没有把这个既有管道问题当成已证明的新增越权链。

**B：Deployment 元数据及拆分参数 validation。**

- `47-platform-deployments.yaml:95` 同时检查 finalizers、ownerReferences 的存在性及值，覆盖新增、删除、改变成员/内容；没有再看到 review 546 所报顶层 finalizer 漏口。平台现有 rollout restart、scale、devsession stop/start 都 GET 后修改各自目标字段，再 Update，保留这些 metadata。因此新增这条规则没有静态上必拒的现行平台动作。`resourceVersion/generation/managedFields` 没加入等号比较，正常服务端维护不受本条限制。
- `40-admission.yaml:155` 和 `:242` 把原先“字符规则 AND 地址规则”拆成两条，成功集合没有改变：普通参数仍需是符合正则的 string；`giteaBase` 仍须完全等于固定地址，`url` 仍须是该固定前缀下的 string。revision 空字符串允许，空 giteaBase/url 拒绝。错误地址如果还含分号等非法字符，会先违反字符规则，不能期待地址规则的消息。
- 本补丁没有新增可让原先禁用参数通过的分支。Deployment 结论是代码与表达式对照；实际服务端默认化、Webhook、CEL 元数据暴露及旧 typed client 对线上字段的保留情况，仍须 server dry-run/live 验证，见末尾限制。

**C：每组负例的首个失败 validation 与消息。**

用完全替换 I/O 的夹具收集了 **113 个请求：67 个负例、46 个正例**。67 个声明的消息片段各自只匹配目标策略中的一条 validation；再按请求内容逐组检查前面的 validation，未发现本补丁把预期消息指向较后规则的确定错误。下表序号从 1 开始，均为该策略内的序号，不能用“策略名正确”代替这些顺序判断。

| 负例组 | 策略 / 首个失败项 | 声明的消息是否对应 |
|---|---|---|
| inline、resolver PipelineRun | `bifrost-platform-pipelinerun` #1 | 是：pipelineRef / resolver / inline。 |
| Secret workspace PipelineRun | 同上 #2 | 是：workspaces。 |
| hostPath、host-alias 总模板、DNS 步骤模板 | 同上 #3 | 是：podTemplate。 |
| CI 总模板借 deliver、8 个 CI 步骤借 deliver | 同上 #6 | 是：delivery steps；前面的通用 SA 名单允许 tekton-deliver，故不是 #4。 |
| gitea-base PipelineRun | 同上 #8 | 是：固定 Gitea；该错误 URL 的字符合法，#7 通过。 |
| param 的长度 257、分号、命令替换、空格、前导 dash、object、array | 同上 #7 | 是：plain strings；参数名是 revision，后面的地址规则不先拒。 |
| applier TaskRun、非 refresh 的 deliver TaskRun | `bifrost-platform-taskrun` #3 | 是：run as default；两个 SA 名字均通过 #2 的通用名单。 |
| host-alias、env mirror TaskRun | 同上 #5 | 是：podTemplate。 |
| semicolon TaskRun | 同上 #6 | 是：plain strings。 |
| url-other-host TaskRun | 同上 #7 | 是：固定 Gitea；字符规则通过。 |
| PROD/STG 各 9 个外来 ConfigMap | `bifrost-cicd-configmap-writers` #1 | 是：platform own ConfigMaps。 |
| deliver 写 github-sync-scripts | 同上 #2 | 是：STG Dockerfile ConfigMaps；deliver 通过 #1。 |
| applier hostPath Deployment | `bifrost-applier-pod-spec` #1 | 是：hostPath。 |
| applier Grafana SA Deployment | 同上 #3 | 是：namespace SA 名单；monitoring 通过前面的 host 检查。 |
| application-sources | `bifrost-platform-application` #1 | 是：sync operation / targetRevision。 |
| application-kustomize、错误 registry/tag/额外字段、platform-pin、deliver-pin-research | 同上 #2 | 是：kustomize；克隆现存 Application 后没有改 #1 比较的字段。 |
| Deployment image | `bifrost-platform-deployment-restart-scale` #1 | 是：pod spec。 |
| Deployment template-label / template-annotation | 同上 #2 / #3 | 是。 |
| Deployment pause、strategy、min-ready | 同上 #4 | 是：rollout settings。 |
| Deployment own-label、own-annotation | 同上 #5 | 是：session-desired-replicas / own labels。 |
| Deployment finalizer、owner-reference | 同上 #6 | 是；前五条保持不变。 |

若一个请求同时失败两条，应按前面的失败项判断主要拒绝来源，不能要求后面的目标消息必然作为首条报出。例如 PipelineRun 同时带 hostAliases 和恶意参数，首项是 #3；错误 giteaBase 同时含分号，首项是 #7，而非 #8。本轮现有参数用例与模板用例分别构造，没有这种已确认的交叉误配。完整的 1.35.5 报错聚合/显示行为未在本轮实测。

46 个正例包括 normal PR、refresh TR、amd64 PR/TR、正确 URL、空 revision、五个 Dockerfile CM、两个平台各五个自有 CM、15 个 delivery 步骤、六个合法 revision 参数、digest pin，以及 Deployment restart/scale/session annotation。按本次涉及的规则未见必拒项。它们仍只是准入正例，例如 normal PR 缺少实际 apply 所需的参数，并不代表流水线可以成功执行。

`live_object(keep_metadata=True)` 现在保留 resourceVersion、uid、finalizers、ownerReferences 等，只去掉 managedFields，修复了 546 指出的 metadata 丢失。新的“改完完全相同就报错”能阻止无变化负例假通过；固定 timestamp/image 等极端情况下仍可能触发这个诊断，届时是夹具没有产生变化，不应误判生产策略坏了。声明策略和消息的检查及两个错误来源阳性对照有效，但其单测没有执行 CEL。

收集脚本：[offline_admission_cases.py](/Users/vision-mac-trader/agent-work/codex-review-548/offline_admission_cases.py)；逐例请求及目标消息：[admission-cases.json](/Users/vision-mac-trader/agent-work/codex-review-548/admission-cases.json)。这些是静态映射证据，不是伪装成 live 的准入验收。

**D：较小项。**

- CI 的五条 filter 恢复 `refs/heads/` 前缀判断，只向任务传入已校验的 after，消除了 546 所报 `=`、汉字分支名再次被 webhook 拒绝的问题。github-sync 仍限制它实际传下去的 ref。
- CRD 漂移检查新增字段消失与 preserve-unknown/additionalProperties 检查，是有用补强；本轮没有线上 CRD 供执行。静态字符串检查仍只能防漏接，不能代替条件求值。
- Owner 操作单现在显示 Python 退出码，并要求 FAIL 时停止，修复方向正确。建议写成“任何非零退出码都停止”，覆盖脚本自己定义的 exit 3 等情况；第 129 行“普通字符的分支名”仍是旧概述，应与新的 CI / github-sync 分工一致。
- CUT 已标明首稿历史 SHA 和第二稿字符集，回应文件也明确 main 比较未做端到端验证；不能再将本轮静态通过用作 R1 的覆盖证据。

**验证及未检查范围。**

- 固定副本中，使用现有 core venv 的 Python 执行 BRIEF 指定两份 pytest：**16 passed、2 subtests passed**；未安装依赖。
- 同一副本执行 `python3 scripts/check_admission_guards.py`：**exit 0**，包含本地 `kubectl kustomize`；没有 `--live`，没有使用 kubeconfig。
- 提取的完整 shell `sh -n` 通过；15 组离线流程运行使用真实 shell、jq、checker，git/wget/apk/kubectl 全部是本目录的假命令。归档、读 namespace、tracking、git 祖先关系和 head 均为夹具；没有声称测试了实际 clone、Gitea、kubectl 规范化或真实 apply。Namespace 两侧处理不一致由真实 checker 和真实比较直接复现。
- 未访问网络、集群、MCP、SSH，未提交，未编辑源 worktree；结束时源 worktree 干净且 HEAD 仍为 `e889aa68`。本轮文件、临时目录、测试缓存均指定在本审查目录，未使用任何 kubeconfig。
- 未验证：实际部署的策略/CRD/RBAC、1.35.5 服务端 CEL 编译和错误显示、mutating Webhook、真实 typed Update/kubectl replace、SSA managedFields/冲突、Gitea 当前权限及远端 ref、main 在任务期间前进的并发行为、Owner 操作、令牌切换和实际发布。尤其不能仅凭旧客户端 API 注释或已有 typeChecking 告警，就断言本次 finalizers 表达式在服务端一定成功或一定失败。

先改
END OF REPORT
