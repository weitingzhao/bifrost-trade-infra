结论：先改。平台读取器本身可以继续推进：没有发现退回管理员令牌的路径，离线编译、定向测试及两个 overlay 的本地渲染均通过。但切法尚不能证明 4.1 P0 要求的凭据边界；其中还有会导致 PROD 发布中断的迁移遗漏。以下区分已复现的问题、清单可证明的权限路径和未做的线上验证，不把后续切片尚未实现本身算成缺陷。

审查基线：infra `4d669f3e27d014e2ddd05d5c5d326b75aa942d34`，platform `9d332716d1e379f61c62f79757746ce029cceb27`。下文 `I/` 指 `/Users/vision-mac-trader/agent-work/td432-infra/`，`P/` 指 `/Users/vision-mac-trader/agent-work/td432-platform/`；`CUT` 和 `OWNER` 分别指 `I/agent-config/work/multi-agent/CUT-td432-gitea-credentials-2026-10-24.md`、`OWNER-STEPS-td432-2026-10-24.md`。平台现行写 ConfigMap 的调用链另按要求使用共享 checkout 的 `git show origin/main:<path>` 核对，版本为 `82b3e9d7`。

infra 的本地 `origin/main` 已到 `175d3641`，比共同基线 `17499739` 多四个 W-68 提交。因此要求的两点 diff 中出现监控文件“删除”；它们不是本分支五个提交的删除操作。核对共同基线后，本分支实际改动 13 个文件。没有据此误报回退 W-68，也没有更新远端引用。

**A：应先修正的问题**

**A1 · P1：S3b 的名字白名单必须覆盖 CREATE，当前切法漏掉了它。**

证据：`CUT:129` 只承诺拒绝白名单外的 UPDATE/PATCH/DELETE；`I/k8s/platform-rbac/00-clusterroles.yaml:91` 仍给两个平台身份 create/update/patch 任意 ConfigMap；`I/k8s/platform-rbac/40-admission.yaml:11` 起的现有策略没有 ConfigMap 规则。

失败场景：限制更新现有 `github-sync-scripts` 后，平台仍能在受保护对象缺失、重建或新增消费者时先创建同名 ConfigMap，把脚本交给后续特权工作负载执行。`resourceNames` 不能约束 create 正是需要准入的原因，不能在准入中再次漏掉 create。PATCH 在准入请求中按 UPDATE 检查，不是可直接填入 `operations` 的单独枚举。

最小修正：TD-434 使用 `CREATE/UPDATE/DELETE`，namespace 固定为 `cicd`，匹配两个平台 SA，`failurePolicy: Fail`，Binding 使用 `Deny`。CREATE/UPDATE 检查新对象名字，DELETE 检查旧对象；不要用调用方可写的 label 作为授权依据。对禁止名字分别测 create、update、patch，且测带生成名字的创建；允许名字要测初次创建和正常更新。DELETE 仍受现有 RBAC 约束，不应顺便给 STG 新增删除权限。TD-434 的完整允许名单及其他消费者见下文。

**A2 · P1：S8 搬走 Secret 后，PROD 仍能通过 Gitea Deployment 获得等价管理员能力。**

证据：`CUT:86` 接受 patch Deployment 的路径，并称 S8 后对管理员 Secret 失效；`CUT:134` 把“搬家、换令牌”作为收尾。实际 `I/k8s/platform-rbac/20-prod.yaml:229` 在 `cicd` 绑定 workload-actuator，`00-clusterroles.yaml:115` 允许 update/patch 任意 Deployment。`I/k8s/cicd/gitea/deployment.yaml:64` 使用 SQLite，`:82`、`:98` 将 `gitea-data` PVC 可写挂入 Gitea。现有工作负载准入 `40-admission.yaml:292` 针对 applier，并不限制平台 SA 修改 Deployment 的容器命令、镜像或挂载。

失败场景：PROD 平台修改 Gitea 容器命令或增加容器，直接访问 Gitea 数据库、配置和仓库内容；不需要再读取搬走的 `gitea-bootstrap`。它也能改 `cicd` 中其他高权限 Deployment 的执行内容。换 PAT 不会消除控制 Gitea 服务端的能力，因此不能据 S8 宣布“除未来 lander 外没有 main 写能力”。这是清单可证明的入口，本次没有在集群执行。

最小修正：从平台身份撤掉 `cicd` 任意 Deployment 的内容修改权，或在准入中将其严格约束为实际需要的重启注解、独立 scale 操作，禁止变更镜像、命令、SA、卷等执行内容。Gitea/Argo 等管理工作负载的升级另走受控身份。若 Owner 接受信任整个 PROD SA，必须明确降低 P0 的保证范围；不能继续保留现在的绝对验收结论。4.1 对“未来 lander 令牌由已批准 PROD 代码共享”的例外不等于接受平台继续管理 Gitea 服务端。

**A3 · P1：只限制平台写 ConfigMap 仍可被它启动的 Tekton 身份绕过。**

证据：`I/k8s/platform-rbac/40-admission.yaml:67`、`:76` 允许 PipelineRun 使用 `tekton-deliver`，没有将此身份绑定到具体流水线/可信步骤；`:123`–`:135` 的 TaskRun 规则仅要求引用 Task、SA 在名单中，连 `bifrost-applier` 也未限定为 apply-manifest。`I/k8s/cicd/tekton/rbac-deliver-stg.yaml:18` 给 `tekton-deliver` 任意 `cicd` ConfigMap 的 create/patch/update；`30-applier.yaml:47` 给 applier 修改 Task/Pipeline 的权限。`I/k8s/cicd/tekton/pipeline-ci-platform.yaml:169`–`:176` 执行候选提交的 Go 测试。

失败场景一：PROD 平台直接创建引用 `bifrost-ci-platform` 的 PipelineRun，把运行身份设成 `tekton-deliver`，候选测试就获得 ConfigMap 写权限。只匹配两个平台 SA 的 TD-434 策略不会阻挡该测试改 `github-sync-scripts`，随后同步任务带着管理员令牌执行它。

失败场景二：平台可以引用现有 Task 并选择高权限 SA。`I/k8s/cicd/tekton/task-refresh-dockerfile-cms.yaml:39`–`:40` 将参数直接插入 shell；离线提取 `revision` 赋值并代入无害标记，已复现参数变成 shell 命令执行。`task-git-clone-gitea.yaml:54`–`:55` 也采用这种插值。已有 Task 不是天然安全的执行入口。只钉死 mirror-sync 的主机不能修复这类入口。

最小修正：为 PipelineRun/TaskRun 建立“引用对象及具体步骤 → 允许 SA”的约束；运行候选测试的步骤只能使用无写权限身份。TaskRun 不应任意使用 applier，补齐其 workspace、podTemplate 等约束。脚本参数通过 env/argv 传入并校验，禁止文本插进 shell。对 `tekton-deliver` 的 ConfigMap 写也按真实职责收窄；否则它仍是白名单的间接旁路。通过实际 admission 反例确认这些组合被拒后，才能算 P0 关闭。

**A4 · P1：S7 漏迁移 PROD 发布的 check-source，S8 删除旧 Secret 将使发布卡住。**

证据：`CUT:44` 已列出 `pipeline-deliver-platform-prod.yaml`，但 `CUT:133` 的 S7 改动和验收没有迁移该消费者。`I/k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:111`–`:120` 的 check-source 仍从 `gitea-git-credentials` 取 username/password，且不是 optional。

失败场景：其他克隆和同步任务已经通过 S7 验收，S8 退役旧 Secret；下一次 PROD 平台发布在 check-source 注入环境变量时失败，还没机会执行 Git。保留旧 Secret 则又留下旧凭据及可挂载入口。

最小修正：把该 TaskSpec 明确加入 S7，改用 `gitea-ci-reader`，保留它已有的不落盘认证方式；验收必须含 PROD source gate。退役前扫描全部 Secret 引用，并更新依赖旧名字的管理脚本，例如 `I/scripts/k3s/run-deliver-platform.sh:31`、`run-deliver-prod.sh:23`、`run-deliver-stg.sh:39`。迁移 `rotate-admin-token.sh` 时，除了去掉写克隆密码，还要去掉 `:83`–`:84` 对两份旧 Secret 的强制读取及后续校验依赖，否则删旧 Secret/搬 namespace 后脚本自己也无法完成。

**A5 · P1：S8 需要明确撤销本次切换前的令牌；“换入新值并 check”不足以使旧副本失效。**

证据：`CUT:134` 的验收只写 `rotate-admin-token.sh check` 显示新令牌，`OWNER:176` 没写旧令牌撤销步骤。现有 `I/scripts/gitea/rotate-admin-token.sh:327` 明确要求暂不撤销旧令牌；其 `revoked` 分支 `:330`–`:340` 只验证固定历史泄漏文件中的 token，并不保证验证本次迁移前、已被平台和 CI 接触过的当前 token。

失败场景：新 Secret、RBAC、任务都已切换成功，但旧 PAT 已被复制进旧工作区、日志或其他地方；只替换 Secret 不撤销 Gitea 中的旧 token，它仍能推 main。即使历史泄漏 token 检查通过，也不能代替检查这次被替换的 token。

最小修正：S8 操作单写清：先确认所有新消费者工作正常，再由 Owner 在 Gitea 撤销这次替换的所有旧管理员/克隆 token，核对 token ID，验证旧凭据认证被拒、新凭据仍工作。检查结果不带令牌值。把既有旧 Pod、工作区和可能残留凭据的日志纳入收尾清单；撤销是边界成立的必要步骤，不能以删除文件或删除 Secret 代替。

**A6 · P2：令牌脚本在分页上限处成功退出，可能漏过可写仓库。**

证据：`I/scripts/gitea/put-reader-token.sh:127` 在第 20 页仍非空时直接 break，随后 `:137` 报告 can write none，`:139` 创建 Secret。

离线复现：stub 返回前 20 页只读仓库，第 21 页有可写仓库；原脚本退出 0、创建了假的 Secret，最后请求页为 20。当前组织规模可能尚未触发，但脚本宣称检查“所有可见仓库”，不应把未查完当作通过。

最小修正：保留上限也可以，但触顶且未证明已到末页时必须报“检查未完成”并拒绝写入；或依据可靠分页信息遍历到结束。新增“第 21 页存在可写仓库”的反例。缺少 `permissions` 时目前会拒绝写入，这一点离线验证通过，应保留。

**TD-434：最小修法和实际写入清单**

对两个平台 SA 在 `cicd` 的直接 ConfigMap 写，名字白名单的 ValidatingAdmissionPolicy 是合适的最小修法：保留已有 RBAC 功能，不引入新控制器，同时覆盖 RBAC 无法按名字限制的 CREATE 和 `release-*` 动态名字。它解决的是这一条直接入口；A2/A3 仍要单独收口，不能把“一条策略”当作整个 P0 的证明。

按平台 `origin/main=82b3e9d7` 实读，直接写入范围如下：

| ConfigMap | 调用链与动作 | 白名单处理 |
| --- | --- | --- |
| `lineage-thread-titles` | `api/internal/threadtitles/threadtitles.go:35` 定名，`:118`–`:125` create/update；`server/server.go:261` 使用 release namespace | 精确名；create/update |
| `bifrost-release-window` | `api/internal/delivery/window_store.go:169` create，`:179` update，`:193`、`:211` delete | 精确名；create/update；delete 只保留现有 PROD 授权 |
| `bifrost-release-policy` | `api/internal/releasepolicy/policy.go:25`；`write.go:54` → `delivery/release_policy_facts.go:55`–`:76` create/update | 精确名；create/update |
| `bifrost-release-freeze` | `releasepolicy/policy.go:26`；`write.go:84`、`:125` → 同一 writer | 精确名；create/update |
| `release-<run>` | `api/internal/releases/record.go:56`、`:245` 定前缀；`releases/service.go:205`、`:220`、`:226` create/update | `release-` 前缀；create/update，无删除需求 |

`platform-state-*` 使用 Pod 自己的 namespace（`server/server.go:126`–`:133`、`statefile/k8sstate/k8sstate.go:193`–`:202`），当前两个 overlay 没有把 `PLATFORM_STATE_NAMESPACE` 指向 `cicd`，无需扩大 cicd 白名单。`ib-gateway-config` 写在 `data`，也不在此名单。

Dockerfile ConfigMap 是另一个身份的间接写入：`delivery/supply_chain.go:409`、`:456` 起 `bifrost-refresh-dockerfile-cms`，SA 为 `tekton-deliver`；Task `:54`–`:68` 写五个固定名字：`bifrost-api-stg-dockerfile`、`bifrost-frontend-stg-dockerfile`、`bifrost-worker-stg-dockerfile`、`bifrost-platform-api-stg-dockerfile`、`bifrost-platform-console-stg-dockerfile`。这些不应加进平台 SA 的直接白名单；需按 A3 管住代理执行身份。

除已知的 GitHub 同步外，还找到以下有权限影响的消费者：

| 可被平台改写的输入 | 执行/消费位置 | 后果 |
| --- | --- | --- |
| `github-sync-scripts` | `I/k8s/cicd/github-sync/cronjob-reconcile.yaml:30`、`:64`、`:76`、`:89`；`task-github-sync.yaml:19` | CronJob 和 Task 都执行脚本，环境内有 Gitea 管理员 PAT、GitHub 写 token；脚本也可输出凭据供有 Pod log 读取权的平台取走 |
| `bifrost-apply-manifest-check`、`bifrost-actuation-policy` | `I/k8s/cicd/tekton/apply-manifest/pipeline.yaml:92`、`:188`、`:207`、`:214`–`:218` | 前者是实际执行的 shell，后者决定应用白名单；当前进程带克隆凭据和 applier 身份。只保护 policy、漏保护 checker 不够；即使 plan 也执行 checker |
| `gitea-backup-scripts-<hash>`、`gitea-backup-recipient` | `I/k8s/cicd/gitea-backup/kustomization.yaml:14`；`cronjob-backup.yaml:59`、`:72`、`:92`、`:112`–`:119` | 夜间任务执行可改脚本，能读 Gitea 全量数据和配置，并写备份。更换 recipient 能改变备份加密对象。没有 SA token、源 PVC 只读不等于数据安全；脚本仍可泄漏数据。`network-policy.yaml:22` 还允许公网 HTTPS 出站 |
| 五个 Dockerfile ConfigMap | `I/k8s/cicd/tekton/pipeline-deliver-platform.yaml:86`、`:108` 等 Kaniko 工作区 | 可控制构建命令与产物，接触共享克隆目录；必须保护，不因叫 Dockerfile 而当作普通状态 |
| `bifrost-release-freeze-check` | `I/k8s/cicd/tekton/task-release-freeze-check.yaml:329`、`:333` | 执行 Python 代码，掌握运行它的 SA，且能改变发布冻结闸门结论 |
| `argocd-cm`、`argocd-rbac-cm` | `CUT:77` 已列出的现行对象 | 是控制面配置输入，不是“记录”；不能放入平台状态白名单。本次未取得线上 Argo 配置，未把它们描述为已复现的令牌窃取路径 |

TD-434 验收至少应覆盖这些禁止对象，以及上述五类允许对象的正常调用。仅测试 `github-sync-scripts` 被拒、`lineage-thread-titles` 放行，覆盖不够。

**B：Owner 应知道的交付边界和未核实项**

凭据路径现状：

| 身份/执行位置 | 本稿之后仍需处理的路径 |
| --- | --- |
| STG 平台 | S4 移除直接 get admin Secret；S3b 前仍可改同步/备份/checker ConfigMap。新读取器不消除这些 RBAC 能力 |
| PROD 平台 | 当前分支仍有 admin Secret 绑定，待 S6；S6 后仍有 A2/A3 间接能力 |
| CI/default 与候选测试 | 即使 SA 不能 get Secret，clone Task 通过 SecretKeyRef 获得凭据并写入 `.git/config`（`task-git-clone-gitea.yaml:58`、`:68`、`:80`）；候选测试共享该工作区。S7 之前保持开放 |
| 同步/发布 Task、CronJob | 当前仍注入管理员/克隆凭据；S7 必须迁移全部消费者。旧 TaskRun/Pod 使用的已解析 TaskSpec、env 不会因为更新 Task 定义自动替换 |
| `tekton-trigger` | `rbac-trigger.yaml:30`–`:32` 仍读 cicd 全部 Secret，现有准入也没有匹配它。其直接可读对象与可启动任务需要纳入最终清单，不能只检查 default SA |
| applier | 可改 Task/Pipeline，当前可读旧克隆 Secret；更换读凭据并不自动收紧它的代码执行权限 |
| 06 执行/评审 | 源码将 Git token 放入专用 `gitEnv`（`P/api/cmd/agentd/main.go:247`–`:254`）；executor 环境有允许名单和业务键拒绝检查（`internal/agentd/executors.go:37`、`businesskeys.go:19`）。这不能证明运行中隔离、挂载、同 UID 文件可见性及 11 仓库保护规则，须在 4.1 P0 实测；本次没访问主机或凭据文件 |

作者在 `CUT:157`–`:163` 实际列了七项未核实，而不是 BRIEF 概述中的五项。本轮结论如下：

| 未核实项 | 本轮结果/后续要求 |
| --- | --- |
| 旧 clone credential 当前所属用户 | 未读取真实 Secret；继续按管理员凭据处理，不能因样例写 CI user 就降级 |
| Gitea 1.21 `/repos/search` 的 `permissions` | 未访问真实 Gitea，也没有本地 Gitea 源码可确认。现有测试自行构造该字段，不能证明服务端契约。离线确认字段缺失会拒绝写；交 Owner 批量建三份前，应先用第一份账号验证实际响应。若不提供此字段，逐仓 GET 查询有效权限，缺失仍拒绝，不能删校验绕过去 |
| 其他拉取镜像 | 未核；只读账号对 mirror-sync 的拒绝要作为预期失败展示并核对影响 |
| 11 仓库的分支/标签保护 | 未核；`primary-probe` 的历史成功不代替现有各仓库逐项验证，执行/评审身份须测 main、PR merge、标签、保护修改 |
| trigger 的 Secret 权限能否撤销 | 未实测 EventListener；需确认其真正依赖，若保留要写清信任范围和它的间接能力 |
| `.git` 是否进入镜像/构建过程 | 已补读 frontend/console Dockerfile：`Dockerfile.frontend-stg:13`、`:20` 及 `Dockerfile.platform-console-stg:8` 整目录 COPY 会把克隆目录的 `.git` 带进 builder（所读 Task 未见 context 根排除规则），后续 npm 脚本可读。最终 nginx stage 只复制 dist/config，不能据此声称最终镜像一定包含 `.git`；本轮未构建或检查现存镜像层。验收应扫工作区、构建上下文、产物和凭据初始化目录 |
| Pod 能否读 0400 挂载 | 本地渲染确认四个 Deployment 容器挂载正确，未指定 runAsUser；Dockerfile 最终 stage 没有 USER。只证明清单/镜像设计一致，没验证运行中 UID、准入变更及实际文件可读性 |

S7 还应核查 Tekton 自动凭据初始化：`I/k8s/cicd/gitea/secret.yaml.example:39` 有 `tekton.dev/git-0` 注解。本次没查真实 SA 的 Secret 关联，因此不能确认它是否还会写入容器 HOME 下的 `.gitconfig`/`.git-credentials`。只检查仓库 `.git/config` 不足以排除此路径。环境认证必须限定在可信 Git 子进程，测试/安装脚本的最终环境不能继承 `GIT_CONFIG_VALUE_*`、GIT_PASSWORD 等值。

S8 的“集群里除 Owner 外无人能读”也应收窄为可证明的威胁身份范围：`CUT:62` 已列出拥有跨 namespace Secret 读取权的集群控制器/备份身份；仅搬到无工作负载 namespace 不会撤销这些 ClusterRoleBinding。应逐项记录哪些属于必须信任的基础设施，以及平台不能改写或借用它们的依据。

切换顺序方面，STG 的 S1 → S2 → S3 → 验收 → S4 设计成立：旧代码忽略新 env，新代码读已挂载文件，验收后才撤旧权限，没有必然的“两个凭据都没有”的窗口。新代码在缺文件时直接报错，不会静默拿 admin。PROD 要把“overlay 与发布一起”写得更明确：先保证 reader Secret 和挂载已到位，再切新镜像，核对 api/workers 两边，最后 S6。仅检查卷对象存在不等于文件可读；`optional: true` 会让缺 Secret 的 Pod 仍启动。

两个 platform Argo 应用自动同步 infra main，PROD overlay 提交本身就会触发运行时变化，并不是 Console 批了 `start_pipeline_run` 才第一次生效。应逐片落地并标明批准覆盖的 overlay 提交，避免一次推整个 infra 分支造成步骤提前。S8 前必须让使用旧凭据的在途任务结束/被受控处理，防止删除 Secret 后新建的后续 Task Pod 卡住。

Owner 操作单 §1 的正向路径基本可粘贴：三个账号/模式映射正确，令牌 scope 是 repository/organization/user Read，user Read 用来核身份；脚本核账号非 admin、仓库权限和 Git 读/写握手。隐藏输入不会作为 shell 命令进入历史，关闭 xtrace，curl 认证走 stdin，Secret manifest 走 kubectl stdin；正常结果只打印键名。令牌仍会存在于浏览器/剪贴板、脚本内存、Kubernetes Secret 和 Pod 挂载中，不能把“不落文件”理解成不存在这些副本。未测试真实浏览器 UI，也未执行任何 Owner 命令。

“5 次、约 60 分钟”不准确：`OWNER:15/107/135/141/175/176` 已是六次独立交互，标出的分钟数合计约 63，尚未计 S3b、权限接口兼容性排障及完整验收。可以合并部分时段，但要写出怎么合并；目前 60 分钟只能算理想操作时间，不能作为关闭 P0 的确定工期。

4.1 的先后关系必须写成明确闸门：完成 TD-432 S1–S8、TD-434、A2/A3 的边界修正及执行/评审身份的逐仓验证，再交付 P0 的无凭据值证据矩阵。S4 的 `can-i=no`、S6 双环境 `no` 或本次单测通过都不能当作 P0 完成。至少不得据此开启 4.1 的 S2/S3 或发放真实 main 写权限；按本 BRIEF，4.1 启动前应先满足 P0。

**C：较小问题**

- `I/scripts/test_platform_rbac_secrets.py:78` 只解析 `kind: ServiceAccount` 的直接 subjects，漏掉 `system:serviceaccounts:<namespace>`、`system:serviceaccounts` 等 Group 授权，且只扫描 `k8s/platform-rbac/*.yaml`。离线加一个给 STG serviceaccounts 组的 admin Secret RoleBinding，检测器没有发现。现有清单测试通过可保留，但需扩展组解析和扫描范围，或收窄“任何绑定”的文字承诺；线上 SAR 和 admission 测试不可省。
- `OWNER:89` 的“删 Secret 重来”应明确仅限尚未有消费者的 S1。上线后轮换应先验证新 token，再原地替换 Secret；否则删除后脚本失败会让新读取器缺凭据。`OWNER:123`、`:161` 的恢复 admin 绑定也不能修复新代码的缺挂载问题；回退须区分旧镜像仍依赖 RBAC与 reader 本身失败。
- `CUT:130` 说“加 4 行”，实际 `check_platform_rbac.py:76`–`:78` 新增三行、双环境共六项，142→148 的总数正确；改文字即可。`CUT:85` 将 tekton-deliver 列作可建 run 的主体也应按其实际绑定复核，所读清单只给它 get/list run，并未给 create。
- 本地 bdev 平台读取器同样要求 `GITEA_READER_DIR`，当前操作单只部署两个集群 overlay；补充本地开发的预期错误状态或安全的 reader 配置方式，不要为兼容开发机恢复管理员回退。

**已做的验证与限制**

- 两个源 worktree 审查前后 `git status --porcelain` 均为空；没有修改它们、提交或更新引用。只在本目录创建报告和离线探针，Go 缓存按 BRIEF 使用共享 cache。
- `bash -n put-reader-token.sh` 通过；原有离线 RBAC 测试 2/2 通过。
- 将指定 platform 提交的 `api/`、`config/` 导出到本目录，Go 1.26.4 下 `go build ./...`、delivery 的 `go vet` 通过。执行原有 `TestGiteaReaderFromEnv`、`TestNewHandlerReadsTheReader`、`TestNoGiteaAdminTokenInPlatformCode`，以及新增无 socket 的 RoundTripper 探针，全部通过。后者核对读取路径有 reader 时仅使用 reader，缺 reader 时不请求 Gitea、不读取 Secret。
- 本地 `kubectl kustomize` 渲染 STG/PROD，通过四个 Deployment 的路径、只读挂载、Secret 名称、0400 模式检查；该命令仅渲染文件，没有调用集群。
- `probes/offline_checks.py` 使用假的 curl/kubectl 与假 token，没有 socket 或集群连接：正常创建、缺 permissions 拒绝通过；复现 A6 分页漏检、A3 的 shell 参数插值、C 的 Group 授权漏检。
- 未跑会开启 HTTP listener 的原始 token 集成测试/Go 全套测试；没有联网、MCP、SSH、真实 API/集群 dry-run、真实权限验证、部署或镜像检查。Gitea 1.21 行为、现存 Secret 的作用域、线上 admission/RBAC、06 的实际隔离情况仍需 Owner 后续验证。本报告中引用作者线上结果的部分未被本轮重新实测。

先改
END OF REPORT
