# TD-432 切法：平台与 CI 的 Gitea 凭证（2026-10-24，第 3 稿）

**一段话**：今天 STG、PROD 两个平台的服务账号都能读 `cicd/gitea-bootstrap`，平台把里面的 Gitea 管理员令牌当成读 Gitea 的凭证用；CI 每次克隆都把另一份凭证（历史上也是管理员的）写进工作目录的 `.git/config`，候选代码的测试读得到；镜像同步和 GitHub 同步两个任务也带着管理员令牌跑。实测下来，平台对 Gitea **只读**：唯一的写是对「拉取镜像」发 `mirror-sync`，而 11 个仓库 10-17 已全部转成主仓库，这条在现状下不会发出。所以目标很简单：每个环境一个只读账号、CI 一个只读账号，凭证以文件挂进 Pod，平台对任何 Secret 都不再有 RBAC；管理员令牌只留给 Owner 和引导。另外实测发现一条同级的间接入口：**STG 平台能改 `cicd` 里任意 ConfigMap**，其中 `github-sync-scripts` 每 15 分钟由带管理员令牌的任务执行一次。这条不关，撤绑定也挡不住 STG 拿到管理员令牌，列为必做片 S3b。

- 分支：infra `w31/td432-cut`（本文件、Owner 操作单、令牌脚本、两个 overlay 补丁、S4 的 RBAC 改动和防线）；platform `w31/td432-gitea-reader`（`giteaCredentials` 改读只读账号，带单测）。都没推送。
- 依据：infra main `17499739`、platform main `82b3e9d7`；线上只读实测 2026-10-24 01:0x（`KUBECONFIG=~/.kube/bifrost-k3s.yaml`）。
- Owner 共约 75 分钟、分 6 次（理想操作时间，不含排障）；第一次最长，约 35 分钟（建账号、令牌、Secret）；第 2 次约 8 分钟，可以紧接着第一次做：三条准入策略、CI webhook 过滤、清单应用流水线，各自先服务器端 dry-run 再应用。

## 0 第 3 稿改了什么（复核 545）

| 复核 | 处理 | 在哪 |
|---|---|---|
| F1 平台能用 `requireOnMain=false` 从分支应用 Task、Pipeline | 在受信的应用流水线里按渲染出的级别拒：C、D 级的 `apply` 不带 `requireOnMain=true` 就停（`k8s/cicd/tekton/apply-manifest/pipeline.yaml`，紧接在级别检查之后）。平台代码对 C、D 级一直传 `true`（`workactions/service.go:101`），正常的单不受影响。静态检查要求这一段在级别检查和 `kubectl apply` 之间。剩余：4.1 之后「在 main 上」不再等于「Owner 看过」，见 §5 | 操作单第 2 节第三条 |
| F2 Pod 模板能改主机解析（`hostAliases`、DNS） | 三处 Pod 模板（PipelineRun 的总模板、单步骤模板、TaskRun）只许 `nodeSelector`、`tolerations`、`affinity`，CRD 里另外 14 个字段都必须不出现；集群上的 Tekton CRD 是有类型的，没列的字段会被裁掉，所以这等于白名单。`--live` 读线上 CRD，多出新字段就报，要先决定归哪一边 | `40-admission.yaml`；`check_admission_guards.py` 的 `crd_pod_template_drift` |
| F3 没有 Deployment 放行用例；拒绝不核来源 | `--live` 用线上 `cicd/gitea` 整个对象（保留标签和注解）以 `kubectl replace` 做整对象更新，和平台先 GET 再 Update 一样：重启、扩缩、`bifrost.dev/session-desired-replicas` 注解放行；换镜像、暂停、改策略、改 `minReadySeconds`、改模板标签和注解、改自身标签和注解都要被拒。拒绝必须出自被测的那条策略（报文里带策略名），求值出错（`resulted in error`）算失败不算拒绝。另加 15 个交付步骤的放行用例、CI 每个步骤借 `tekton-deliver` 的拒绝用例、参数边界 11 例。测试里加了「被别的策略拒」会被报出的阳性对照 | `check_admission_guards.py`；`test_access_checks.py` |
| F4 Deployment 规则没冻住 `paused`、`strategy` 等 | 冻住 `paused`、`strategy`、`minReadySeconds`、`progressDeadlineSeconds`、`revisionHistoryLimit`；Deployment 自身的标签不许改，注解只许改 `bifrost.dev/session-desired-replicas`。`resourceVersion`、`generation`、`managedFields` 不比较 | `47-platform-deployments.yaml` |
| F5 参数字符收窄了合法 ref | 改为字母（含非 ASCII）、数字和 `._/:@+=-`，首字符不能是 `-`（防 `--upload-pack=` 这类选项）；`feature/fix=1`、`feature/修复`、256 字符放行，257 字符、`;`、`$(…)`、空格、前导 `-`、数组被拒 | `40-admission.yaml` 两处 |
| D 顺序：准入要在撤 STG 绑定之前 | 操作单把准入挪到第 2 节，第 3 节（撤 STG 绑定）写明第 2 节做完才做 | 操作单 |
| D 类型检查状态 | 线上现有 6 条策略都带 `status.typeChecking` 告警（例如 `bifrost-platform-pipelinerun` 引用的 `pipelineRef.bundle` 不在 CRD 里）。准入表达式运行时按无类型对象求值，告警不改变行为，10-09 以来 `--live` 都按预期；但新表达式的告警要读。只读身份读得到，Owner 应用后由我读 | §5 |
| D 防线 2 文字过时、S8 的令牌集合 | 改正为扫整个 `k8s/`；S8 先记下这次要吊销的令牌（名字、ID），`rotate-admin-token.sh` 里读旧 Secret 的地方（`:83`、`:84`、`:331`）列进 S8 的核对 | §3 S8、§4 |

CEL 仍没在本地编译过。参数正则用了 RE2 的 `\p{L}`、`\p{N}`（CEL 字符串里写成双反斜杠），Python 的 `re` 不支持，只能靠服务器端 dry-run 和 `--live` 验证。

## 0.1 第 2 稿改了什么（复核 542）

| 复核 | 处理 | 在哪 |
|---|---|---|
| A1 S3b 的名字白名单要管 CREATE | 准入策略 `k8s/platform-rbac/46-cicd-configmaps.yaml`：两个平台身份在 `cicd` 只能 create / update / delete 自己的五类 ConfigMap，`tekton-deliver` 只能写 5 个 STG Dockerfile ConfigMap；S3b 一行改写 | §3 S3b |
| A2 PROD 能改 `cicd` 里的 Deployment | 准入策略 `47-platform-deployments.yaml`：平台身份改 Deployment 只许动副本数和模板上的 `restartedAt` 注解；新片 S3c | §3 S3c |
| A3 平台能起的流水线和任务可以选高权限身份；参数直接进 shell | `40-admission.yaml` 加规则：`tekton-deliver` 只给列出的交付步骤，`bifrost-applier` 只给 `bifrost-apply-manifest`，其余一律 `default`；平台建的 TaskRun 只能 `default`，`tekton-deliver` 只给 `bifrost-refresh-dockerfile-cms`，不许 applier，工作区与 podTemplate 同 PipelineRun 的限制；参数值只许 `[A-Za-z0-9._/:@+-]`，`giteaBase` 必须是集群内 Gitea、`url` 必须指向它。平台代码另拒绝非分支、非标签名的 Dockerfile 刷新 revision（platform `0150b811`）。登记为 TD-436（身份）和 TD-435（参数进 shell，约 25 个文件 105 处；准入的字符白名单先兜住平台建的 run）；新片 S3d | §3 S3d；infra `f5f6581d` |
| A4 S7 漏了 PROD 发布的 `check-source` | S7 加：`bifrost-deliver-platform-prod` 的源检查改读 `gitea-ci-reader`；S8 删旧凭证前先核对所有读者都已迁走 | §3 S7、S8 |
| A5 S8 要吊销切换前的令牌 | S8 改为：换管理员令牌之后，逐个吊销切换前存在过的令牌（旧管理员令牌、旧克隆凭证的令牌），并用每个旧令牌各试一次请求，必须被拒 | §3 S8 |
| A6 令牌脚本在分页上限处静默成功 | 脚本读到空页才停，第 40 页还没读完就拒绝写入；加 `replace` 模式用于轮换；7 条测试 | infra `916f5c42` |
| TD-434 的验收太窄 | `--live` 对两个平台身份逐个试 9 个别的工作负载的 ConfigMap（同步脚本、apply-manifest 检查脚本、applier 白名单、冻结检查脚本、备份脚本和收件人、Dockerfile、两份 Argo 配置），都要被拒；平台自己的 5 类都要放行；`tekton-deliver` 写 Dockerfile 放行 | §3 S3b |
| B PROD 的顺序；Argo 自动同步 | S5 拆成两步：先只推 PROD overlay（推上 main 即由 Argo 生效，不是批单才生效），核对两个 Pod 里文件可读，再建发布单换镜像 | §3 S5 |
| B S7 的凭证初始化与在途任务 | S7 加：查 `tekton.dev/git-0` 注解与服务账号关联的 Secret（Tekton 会把它写进家目录的 `.git-credentials`）；验收扫工作区、构建上下文、产物和凭证初始化目录；凭证只给 git 子进程，测试和安装脚本的环境里没有；S8 前在途的旧任务跑完 | §3 S7、S8 |
| B S8「除 Owner 外无人能读」说过头 | 改成可证明的范围：平台、CI、执行、评审身份都读不到；集群级控制器和备份身份（§1.3）逐个写明为什么信任、平台为什么改不了也借不了 | §3 S8 |
| B 4.1 的闸门 | 写成明确条件，见 §3 末尾 | §3 |
| C 小问题 | 防线 2 改为扫整个 `k8s/`，并认 Group（`system:serviceaccounts:<ns>`、`system:serviceaccounts`、`system:authenticated`）和 `system:serviceaccount:…` 形式的 User，阳性对照各一；S4 的「加 4 行」改成 3 行；§1.4 第 3 行去掉 `tekton-deliver`（它只能 get/list run）；操作单的「删了重来」只限 S1，之后用 `replace`；本机 bdev 的行为写进 §2.1 | §1.4、§2.1、§3 S4、§4、操作单 |

每条准入规则在 `scripts/check_admission_guards.py --live` 里有拒绝和放行两类用例（Owner 跑，要能扮演平台身份）。CEL 本地没法编译，由 Owner 应用前的服务器端 dry-run 检查。

---

## 1 实测清单

### 1.1 平台代码：所有读 Gitea 凭证的地方（platform main `82b3e9d7`）

全部经一个函数：`api/internal/delivery/service.go:1292-1309` `giteaCredentials` 每次调用都向 API server 取 `cicd/gitea-bootstrap`（`:1148` 名字、`:1298` Get），有 `username` 就用它，否则把 `gitea_admin_token` 当用户名、`x-oauth-basic` 当密码（`:1305`）。`GiteaAccess`（`:1321-1328`）把同一对凭证交给其他包。

| # | 调用点 | 做什么 | Gitea 端点 | 最小权限 |
|---|---|---|---|---|
| 1 | `service.go:1195-1220` `Revisions`（`:1331` 标签、`:1378` 分支） | Delivery 页的分支、标签、共同 ref 列表 | `GET repos/{o}/{r}/tags`、`/branches` | 代码读 |
| 2 | `service.go:1455`、`:1471` `Compare` | 两个 ref 之间改了哪些文件 | `GET …/compare/a...b` | 代码读 |
| 3 | `ref_preflight.go:188`（`:117` commits，加分支、标签） | 起 run 前的 ref 预检 | `GET …/git/commits/{sha}`、分支、标签 | 代码读 |
| 4 | `request_refs.go:127` `signedPresent` | 建发布单前核签名 SHA 在不在 | 同上 | 代码读 |
| 5 | `mirrors.go:89`、`:105-115` `SyncMirrors`（`POST /api/v1/delivery/mirrors/sync`，`release.sh stg/prod` 先调它） | 先问是不是镜像（`:168`），是才 `POST mirror-sync`（`:195`），再等提交出现（`:216`） | `GET repo`、`POST …/mirror-sync`、`GET commits` | 读；`POST` 要代码写权限，**只对镜像发**。11 个仓库全是主仓库（`agent-config/gitea-primary.txt`），平台的镜像白名单正好是这 11 个（`k8s/cicd/tekton/apply-manifest/actuation-policy.yaml:218-230`），所以现状下不发 |
| 6 | `supply_chain.go:127-128` | 供应链页的「镜像凭证已配置」：为了判断「有没有」，把整个 Secret 读了一遍 | 无 | 不需要读 Secret |
| 7 | `release_policy_facts.go:82`、`:213` `PolicyFacts` | 发布策略的事实：文件（`:126` raw、`:147` contents）、main 头（`:178`）、标签（`:195`）、提交（`:208`） | 都是 `GET` | 代码读。**注意**：404 一律当「没有」（`:97-100`），所以没凭证时私有仓库的 404 会被当成「文件不存在」——草稿让它直接报错 |
| 8 | `server/server.go:272-276` → `lineage` | 提交血缘：组织的仓库（`lineage/gitea.go:110`）、分支（`:149`）、提交（`:183`）、文件（`mainevidence.go:51`）；对镜像仓库 `POST mirror-sync`（`gitea.go:77-83`，只对 `Mirror=true`） | `GET orgs/{o}/repos` 等；`POST` 同 #5 | 代码读 + 组织读 |
| 9 | `server/agentrt_heads.go:30-55`、`:105-149` | 执行运行时核对尝试分支和 main 头 | `GET {o}/{r}.git/info/refs?service=git-upload-pack` | 代码读（git HTTP） |
| 10 | `server/agentrt_prune.go:28`、`:50` | 分支清理要交给 agentd 的 `agent/**` 列表；main 上的结果 | 同 #9、#8 | 代码读 |
| 11 | `server/agentrt_assess.go:140` | 评估读台账文件 | `GET …/raw/…` | 代码读 |

不经平台的：06 上的 agentd 用它自己的账号（`cmd/agentd/main.go:249` `AGENTD_GIT_TOKEN_FILE`；账号 `agentd-agent-06`、`agentd-agent-06-stg`），见 §1.4 第 8 行。

**结论**：平台需要的只是「`bifrost` 组织所有仓库的代码读 + 组织读」，不需要任何写权限，更不需要管理员。

### 1.2 infra：引用 `gitea-bootstrap` 和克隆凭证的清单、任务、脚本（infra main `17499739`）

| 位置 | 用哪份凭证 | 做什么 | 实际需要 |
|---|---|---|---|
| `k8s/platform-rbac/00-clusterroles.yaml:95-104` ClusterRole `bifrost-platform-gitea-creds`；绑定 `10-stg.yaml:136-143`、`20-prod.yaml:136-143`（由 `scripts/gen_platform_rbac.py:186-187` 生成）；`scripts/check_platform_rbac.py:51` 期望两边都是 yes | `gitea-bootstrap` | 给 #1.1 的 `giteaCredentials` 用 | 删 |
| `k8s/cicd/tekton/task-gitea-mirror-sync.yaml:35-41`（令牌）、`:73-100`（调用） | `gitea_admin_token` | 问每个仓库是不是镜像、是才 `mirror-sync`、等提交 | 现状只读。**参数 `giteaBase`（`:18-20`、`:43`）由建 run 的一方给，令牌就发到那个地址**（§1.4 第 3 行） |
| `k8s/cicd/github-sync/task-github-sync.yaml:26-47`、`cronjob-reconcile.yaml:28-35`、`:61-68`（每 15 分钟，`:11`） | `gitea_admin_token` | `read-primaries.py` 读仓库的 `mirror` 字段；`sync.sh` 从 Gitea `ls-remote`/`fetch`（令牌走 `extraHeader`，`sync.sh:41`，不落盘），推到 GitHub | 对 Gitea 只读。脚本来自 ConfigMap `github-sync-scripts`（`task-github-sync.yaml:18-20`） |
| `k8s/cicd/tekton/task-git-clone-gitea.yaml:32-42`（注入）、`:54-82`（拼 `http://用户:密码@主机` 再 `git remote add origin` 或 `git clone`） | `gitea-git-credentials` | 每条 CI、deliver、build 流水线的克隆 | **凭证写进 `.git/config` 的 `remote.origin.url`**。同一个 `source` 工作区随后交给候选代码：`pipeline-ci-platform.yaml:43-81` 三次克隆、`:82-176` `go test ./...`、`:179-232` `npm ci` / lint / test / build；`pipeline-ci-python.yaml:43-89` 与 `pipeline-ci-frontend.yaml:37-103` 同样。要的只是代码读 |
| `task-refresh-dockerfile-cms.yaml:23-43`、`apply-manifest/pipeline.yaml:92-100`、`:155`、`:169` | `gitea-git-credentials` | 同样把凭证拼进 URL（bare clone、wget） | 代码读 |
| `pipeline-deliver-platform-prod.yaml:111-116`、`:235-237` | `gitea-git-credentials` | 已经用请求头传，不落盘 | 代码读 |
| `k8s/platform-rbac/30-applier.yaml`（`gen_platform_rbac.py:143-152`）Role `bifrost-applier-read` | `gitea-git-credentials` | apply-manifest 的克隆 | 改成 CI 只读账号 |
| `scripts/gitea/lib.sh:94-98`、`rotate-admin-token.sh`、`check-step1.sh`、`ensure-push-webhooks.sh`、`scripts/k3s/install-ci-webhooks.sh:30-49` | `gitea-bootstrap` | Owner 在自己 Mac 上跑的管理脚本 | 留着，这正是管理员令牌该在的地方 |
| `k8s/cicd/gitea/secret.yaml.example:13-43` | 两份 | 样例；写着克隆凭证的用户是 `<GITEA_CI_USER>` | 加 CI 只读账号的样例 |

**克隆凭证现在是谁**：`agent-config/RATCHETS.md:396` 记 10-17 20:3x `revoked` 通过时「both Secrets log in as admin」；`rotate-admin-token.sh:2-8`、`:21-25` 换令牌时也把新管理员令牌写进克隆密码。本次没重新实测（不读 Secret 数据），按「仍是管理员」处理。

### 1.3 线上绑定（只读实测）

- `python3 scripts/check_platform_rbac.py`（以服务账号身份发 SubjectAccessReview，只问不改）：**142/142 与清单一致**，包括 STG、PROD 都能 `get secret/gitea-bootstrap -n cicd`。`kubectl auth can-i --as` 用不了：只读身份没有 impersonate 权限，所以用 SubjectAccessReview（`bifrost-agent-read` 只授了这一个创建动词）。
- 线上能碰到这两个 Secret 的绑定（只看名字和 subjects）：

| 绑定 | 角色 | 主体 | 覆盖 |
|---|---|---|---|
| RoleBinding `cicd/bifrost-platform-gitea-creds-stg` | ClusterRole `bifrost-platform-gitea-creds` | `bifrost-platform-stg/bifrost-platform` | `gitea-bootstrap`，get |
| RoleBinding `cicd/bifrost-platform-gitea-creds-prod` | 同上 | `bifrost-platform-prod/bifrost-platform` | 同上 |
| RoleBinding `cicd/bifrost-applier-read` | Role `bifrost-applier-read` | `cicd/bifrost-applier` | `gitea-git-credentials`，get |
| RoleBinding `cicd/tekton-trigger-runs` | Role `tekton-trigger-runs`（`k8s/cicd/tekton/rbac-trigger.yaml:30-32`） | `cicd/tekton-trigger` | **cicd 里全部 Secret**，get/list/watch |
| 集群级（非平台身份，列全） | argocd-*、cnpg-manager、kube-prometheus-stack operator/grafana/kube-state-metrics、loki、cluster-state-backup、tekton 控制器与拦截器、traefik、helm-traefik(cluster-admin) | 各自 | 全部 Secret |

清单与线上一致：两条平台绑定都在、名字和 subjects 都对。

- 各身份在 `cicd` 能做什么（SubjectAccessReview，Y=允许）：

| 身份 | get gitea-bootstrap | get gitea-git-credentials | list secrets | create pods | create taskruns / pipelineruns | update tasks / pipelines | patch deployments |
|---|---|---|---|---|---|---|---|
| STG 平台 | **Y** | - | - | - | - / - | - / - | - |
| PROD 平台 | **Y** | - | - | - | Y / Y | - / - | **Y** |
| `cicd/default`（CI 任务 Pod 默认身份） | - | - | - | - | - / - | - / - | - |
| `cicd/tekton-deliver` | - | - | - | - | - / - | - / - | - |
| `cicd/tekton-trigger` | **Y** | **Y** | **Y** | - | Y / Y | - / - | - |
| `cicd/bifrost-applier` | - | **Y** | - | - | - / - | **Y / Y** | - |

- 两个平台身份对 `cicd` 的 ConfigMap：`update` 对 `github-sync-scripts`、`bifrost-actuation-policy`、`bifrost-platform-api-stg-dockerfile`、`gitea-backup-scripts-*`、`argocd-cm`、`argocd-rbac-cm` **全部 Y**（STG 和 PROD 都是；来自 `00-clusterroles.yaml:83-93` `bifrost-platform-state`，没有 resourceNames，`10-stg.yaml:127-134` 绑在 cicd）。PROD 还能 patch `cicd` 里的 Deployment（`gitea`、`argocd-server` 实测 Y），因为 `workload-actuator` 绑定覆盖的命名空间里有 `cicd`（`gen_platform_rbac.py:12-13`）。

### 1.4 间接入口：拿不到 Secret 也能用到管理员凭证的路

| # | 入口 | 谁能走 | 怎么拿到 | 现在 | 本切法 |
|---|---|---|---|---|---|
| 1 | 改 `cicd/github-sync-scripts`，等下一次推送或 15 分钟对账，任务带着 `GITEA_TOKEN`（管理员）和 `GITHUB_TOKEN` 执行改过的脚本 | STG、PROD 平台 | 读环境变量发出去 | **没挡** | **S3b**（TD-434）：准入白名单，平台只能写自己的 5 类 |
| 2 | 同一权限改 Dockerfile ConfigMap（STG 镜像构建）、`argocd-rbac-cm`/`argocd-cm`（Argo 权限）、`bifrost-actuation-policy`（applier 白名单） | STG、PROD 平台 | 供应链和权限，不直接是 Gitea 令牌 | 没挡 | S3b 一并：平台身份对它们一律被拒；Dockerfile 那 5 个只许 `tekton-deliver` 写，内容来自仓库里的 Dockerfile，见第 10 行 |
| 3 | 建 TaskRun 指 `bifrost-gitea-mirror-sync`，或建任一带 `giteaBase` 参数的流水线，把 `giteaBase` 设成别的主机：mirror-sync 把管理员令牌放进请求头发过去，克隆把克隆凭证拼进 URL 发过去 | PROD 平台（RBAC 允许；准入 `40-admission.yaml:22-35`、`:117-128` 只要求引用、不限参数）、`tekton-trigger` | 对方主机收请求头 | 只有平台代码拒绝调用方设 `giteaBase`（`params_test.go` 的 `TestMergeParamsCallerSetsOnlyRevisionSHAs`、`run_refusal_test.go` 的 `TestCIForbiddenParamRefusals`） | **S3d**：准入钉死 `giteaBase` 和 `url`、参数只许安全字符、身份按步骤配；S7 后 mirror-sync 不再带管理员令牌、克隆凭证是只读账号 |
| 4 | patch `cicd` 里的 Deployment，挂上 `gitea-bootstrap` 或换镜像 | PROD 平台 | 直接挂载 | 只有代码层（rollout restart 只改注解） | **S3c**：平台身份只能改副本数和 `restartedAt`；S8 再把 `gitea-bootstrap` 搬出 `cicd` |
| 5 | 改 `cicd` 里的 Tekton Task（如 mirror-sync 的脚本） | `bifrost-applier`（apply-manifest，单由 Owner 在 Console 批，清单来自 infra main） | 下次运行时读令牌 | 审批单 | 接受；S7 后任务不再带管理员令牌 |
| 6 | CI 测试读工作区 `.git/config` | 执行者写的候选代码 | 克隆凭证（按 §1.2 是管理员） | **没挡** | **S7** |
| 7 | `tekton-trigger` 读 cicd 全部 Secret | EventListener Pod（Tekton 的代码，不跑我们的代码） | 直接 get | — | 后续：只用 CEL 拦截器时这条规则应该不需要，要实测后再删 |
| 8 | 06 上 agentd 自己的账号 `agentd-agent-06(-stg)`：团队 `agentd-write` 有代码写，靠分支保护只放 `agent/**` | 06 上的执行与评审任务 | 不是管理员；能不能推 main 取决于每个仓库的保护规则 | 保护实测只在 `bifrost/primary-probe` 上做过（`OWNER-STEPS-gitea-primary.md` §1 第 8 条）；11 个仓库的规则这次没核（读规则要仓库管理员） | 不在 TD-432 范围；4.1 P0 清单另核 |
| 9 | Mac 上的 `bifrost-mbp`（团队 `maintainers`，能推 main） | Owner 的统筹会话，经 `push-main.sh` | 设计如此 | — | 不在「平台、执行、评审、CI」范围，如实列出 |
| 10 | STG 平台请求刷新 Dockerfile 时给一个分支名（平台 `0150b811` 只许分支或标签），`tekton-deliver` 把该分支里的 Dockerfile 写进 STG 的 Dockerfile ConfigMap，随后 STG 镜像按它构建 | 能推分支的执行任务（`agent/**`）+ 能请求刷新的 STG 平台 | 构建命令可控；构建步骤看得到克隆工作区（S7 前带克隆凭证） | 没挡 | §6 第 4 条：刷新只认 `main` 和发布标签；S7 后克隆凭证只读 |

---

## 2 目标状态

| 调用方 | Gitea 账号 | Secret（命名空间/名字，类型） | 谁能读到 | Gitea 权限 |
|---|---|---|---|---|
| STG 平台（platform-api、platform-workers） | `bifrost-platform-reader-stg` | `bifrost-platform-stg/bifrost-gitea-reader`，`kubernetes.io/basic-auth`（`username`、`password`） | 只经挂载：`/etc/bifrost/gitea-reader`（`GITEA_READER_DIR`），0400。任何平台身份都没有对它的 Secret RBAC。能在该命名空间建 Pod 或改 Deployment 的（Argo、PROD 平台的 workload-actuator）能挂载它——只读，接受 | 不是站点管理员；团队 `platform-readers`：All repositories，Code 读，其余 No Access；令牌范围 repository 读、organization 读、user 读（user 只为让脚本核对令牌是谁的） |
| PROD 平台 | `bifrost-platform-reader-prod` | `bifrost-platform-prod/bifrost-gitea-reader`，同上 | 同上 | 同上 |
| CI 克隆、GitHub 同步读 Gitea、mirror-sync 等提交、refresh-dockerfile-cms、apply-manifest 克隆 | `bifrost-ci-reader` | `cicd/gitea-ci-reader`，同上 | `cicd` 里能建 Pod 的都能挂载——只读，接受 | 同上 |
| Argo CD | `argocd-reader`（已有） | `cicd/repo-creds-gitea-bifrost` | 不变 | 不变 |
| agentd | `agentd-agent-06(-stg)`（已有） | 06 家目录 | 不变 | 不变；专用落地身份是 4.1 的事 |
| Owner、引导脚本 | `weitingzhao`（管理员） | `cicd/gitea-bootstrap`；S8 后搬到没有任何工作负载的命名空间 | Owner 的管理员 kubeconfig；集群里没有消费者 | 不变 |

- **为什么挂文件，不再给 RBAC**：平台对 Secret 零权限；令牌换了 kubelet 约一分钟内更新挂载，不用重启；每次读文件，不再每个请求打一次 API server；与现有的 `bifrost-chief-exam` 挂法一致（`k8s/overlays/platform-stg/platform-api-exam-set.patch.yaml`）。平台镜像没有 `USER`（`k8s/cicd/docker/Dockerfile.platform-api-stg`），以 root 运行，0400 读得到。
- **mirror-sync 的写**：现状一个镜像都没有，不需要。以后若有仓库重新变成拉取镜像，再单独建一个只对那几个镜像仓库有代码写的账号（镜像仓库本身拒绝推送）。只读账号对镜像发 `mirror-sync` 会得 403：平台把它报成该仓库同步失败，血缘把它记在 `MirrorSync` 里，都不会静默成功。
- **克隆凭证不落盘**：每条 git 命令用 `GIT_CONFIG_COUNT/KEY/VALUE` 传 `http.<主机>.extraHeader`，remote 地址不带用户名密码（`sync.sh:41` 和 `pipeline-deliver-platform-prod.yaml:235-237` 已经这样做）。

### 2.1 平台代码草稿（platform `w31/td432-gitea-reader`）

- 新文件 `api/internal/delivery/gitea_reader.go`：`giteaReaderFromEnv` 每次调用读 `GITEA_READER_DIR` 下的 `username`、`password`（单行、≤4096 字节、用户名不含 `:`）；没设、文件缺、为空都报错，错误只写文件名，不写内容。`giteaCredentials(ctx)` 改成返回 `(user, pass, err)`，不再拿 clientset，不再读任何 Secret。
- 只有服务器用的 `NewHandler` 装上这个读取器；`NewService` 默认匿名（测试和 promote 这类不读私有仓库的服务）。没有任何一条路径会退回管理员令牌。
- 各调用点没凭证时：列表、Compare、ref 预检报错并给 `Reachability: fail`（「问不到」，不是「不存在」，预检不会因此报 missing）；`signedPresent` 放行交给 run 自己的闸门（和 Gitea 不可达时一样）；`SyncMirrors`、`GiteaAccess` 返回错误，所以发布策略事实、血缘、执行运行时都报「没有 reader」而不是把 404 当「没有」；供应链页 `mirror_credentials_configured` 改为「reader 可读」，不再 Get Secret。
- 测试：`gitea_reader_test.go`——读取器的各种坏文件；`NewHandler` 装了读取器；假集群里放着管理员 Secret、没设 `GITEA_READER_DIR` 时，Gitea 一次都没被问到、API server 没被要过 Secret；设了之后每个请求带的都是 reader 的 basic auth；模块里任何非测试 Go 文件出现 `gitea-bootstrap` 或 `gitea_admin_token` 就失败。
- 本机 bdev 的 platform-api 没有 `GITEA_READER_DIR`：Delivery 的分支列表、血缘、发布策略事实都报「没有 reader」，这是预期。要在本机看真数据，用 STG 的只读令牌放进本机一个 700 目录（两个 0400 文件）并设这个变量；不为开发机恢复管理员回退。
- 已跑：`go -C api build ./...`、`go -C api vet ./internal/delivery/...`、`go -C api test ./internal/delivery/...` 全过；另跑 `internal/server`、`lineage`、`promote` 也过；`golangci-lint` 对改动文件无新问题。

---

## 3 切片与顺序

每片做完核对才开下一片。STG 的清单与发布按 CLAUDE.md §5「STG 发布 A」由 Agent 做；RBAC、Secret、Gitea 后台归 Owner；PROD 走审批单。

| 片 | 谁 | 做什么 | 验收（实测） | 回退 |
|---|---|---|---|---|
| **S1** 建账号和 Secret | Owner | Gitea 建团队 `platform-readers` 和三个账号、三个令牌；`scripts/gitea/put-reader-token.sh stg|prod|ci` 各跑一次（写之前用令牌逐条试：账号对、不是管理员、11 个主仓库只能读、推送握手被拒、搜得到的仓库没有一个可写） | 三次都以 `==> Secret … created` 结尾 | 删 Secret、删账号；此时还没人用 |
| **S2** STG overlay | Agent | 提交 `k8s/overlays/platform-stg/platform-gitea-reader.patch.yaml`（分支里已有），`push-main.sh` 推 infra，`gitops_sync_app bifrost-platform-stg` | 两个 Deployment 的 Pod 有 `gitea-reader` 卷；旧代码不读这个变量，行为不变 | revert 这个提交再同步 |
| **S3** 平台代码上 STG | Agent（复核后） | platform 分支复核 → `ci-platform` 绿 → `push-main.sh` → `bifrost-deliver-platform` | STG 上：`/api/v1/delivery/revisions?repos=bifrost-platform,bifrost-ui` 为 ok 且有分支标签；`/api/v1/delivery/supply-chain` 的 `mirror_credentials_configured` 为 true；血缘分支页 ok；以 main 头 SHA 做一次 ref 预检为 ok；日志里没有 `gitea reader:` | 当天往前修（Owner 10-19）；实在不行重部署上一版镜像 |
| **S3b** 收窄 cicd ConfigMap 写（TD-434） | Agent 写、Owner apply | `46-cicd-configmaps.yaml`：平台两个身份在 `cicd` 只能 create / update / delete `lineage-thread-titles`、`bifrost-release-window`、`bifrost-release-policy`、`bifrost-release-freeze`、`release-*`（删除不含 `release-*`）；`tekton-deliver` 只能写 5 个 STG Dockerfile ConfigMap、不能删。名单从平台代码逐处读出（文件头注释写了出处） | `check_admission_guards.py --live`：STG 平台写 `github-sync-scripts` 被拒、`tekton-deliver` 写它被拒、PROD 平台写发布窗口放行 | Owner 删这条策略 |
| **S3c** 平台改 Deployment 只许重启和扩缩 | Agent 写、Owner apply（与 S3b 同一次） | `47-platform-deployments.yaml`：平台身份对 Deployment 的 UPDATE 只许改副本数、模板注解 `kubectl.kubernetes.io/restartedAt` 和自身注解 `bifrost.dev/session-desired-replicas`；PodSpec、选择器、模板标签、其他注解、自身标签和五个发布设置都冻住 | `--live`：线上 `cicd/gitea` 整对象更新，重启、扩缩、会话注解放行，其余 8 种改动被拒且出自这条策略（§0 F3） | Owner 删这条策略 |
| **S3d** 平台起的 run 的身份和参数（TD-436、TD-435） | Agent 写、Owner apply（与 S3b 同一次） | `40-admission.yaml` 的新规则（见 §0.1 A3、§0 F2、F5）；应用流水线的 C、D 级拒绝（§0 F1） | `--live`：15 个交付步骤用 `tekton-deliver` 放行；CI 每个步骤和总模板借 `tekton-deliver` 被拒；参数边界 11 例；`giteaBase`、`url` 指向别处被拒；Pod 模板只放 `nodeSelector` 放行、带 `hostAliases`、DNS、`env` 被拒（三处位置）；TaskRun 用 applier 被拒、`tekton-deliver` 跑别的任务被拒、跑 `bifrost-refresh-dockerfile-cms` 放行；线上 CRD 的 Pod 模板字段和两张名单一致 | Owner 在上一个提交上重新 apply |
| **S4** 撤 STG 绑定 | Agent 提交、Owner 删 | 分支里已有：`gen_platform_rbac.py` 只给 PROD 生成这条绑定，`10-stg.yaml` 重新生成；`check_platform_rbac.py` 该行改成 STG no、PROD yes，加 3 行（两环境共 6 项）「平台读不到 `gitea-git-credentials`、`gitea-ci-reader`、自己的 `bifrost-gitea-reader`」；新防线 `scripts/test_platform_rbac_secrets.py` 接进 `make check-platform-rbac`。Owner `kubectl delete rolebinding bifrost-platform-gitea-creds-stg -n cicd`（`apply -k` 不会删已有对象） | `check_platform_rbac.py` 148/148（今天正好只差这一行：`FAIL stg get secret/gitea-bootstrap -n cicd: allowed=True, want False`）；STG 的 Gitea 页照常 | Owner 在上一个提交上 `kubectl apply -k k8s/platform-rbac`（新代码不用它，正常不需要） |
| **S5** PROD overlay 与发布 | Agent 推 overlay、建单；Owner 在 Console 批 | 两步。① 先只推 `k8s/overlays/platform-prod/platform-gitea-reader.patch.yaml` 这一个提交：PROD 的 Argo 应用自动同步 infra main，推上去就生效（不是批单才生效），Pod 重建后有挂载、旧代码不读。挂载写了 `optional: true`，所以要核对 Secret 在、两个 Pod（api、workers）里两个文件都读得到，不能只看卷对象。这一步属于 PROD 清单改动，按「批准按动作算」先在线程里问 Owner。② 再建发布单换新镜像，审批单前提：同一提交 `ci-*` 绿、STG 已核对、同仓库没有未结的发布单；批的范围写明是哪个镜像提交和哪个 overlay 提交 | ① 两个 Pod 里 `test -r` 两个文件为真；② PROD 上同 S3 的四项，api 和 workers 两边都看 | ① revert 那个提交；② 同 S3 |
| **S6** 撤 PROD 绑定和角色 | Agent 提交、Owner 删 | 生成器去掉 PROD 这条、`00-clusterroles.yaml` 删 ClusterRole；`check_platform_rbac.py` 该行改两边都 no；防线的 `EXCEPTIONS` 清空。Owner 删绑定和 ClusterRole | 两个平台身份对 `gitea-bootstrap` 都回 no；防线无例外通过 | 同 S4 |
| **S7** CI 与同步任务 | Agent 写、Owner 批 apply | 克隆任务改读 `gitea-ci-reader`、凭证走请求头、remote 不带凭证；mirror-sync 改读 `gitea-ci-reader`，并且只认 `gitea.cicd.svc.cluster.local:3000`（忽略调用方给的主机）；github-sync 任务和对账改读 `gitea-ci-reader`；`refresh-dockerfile-cms`、apply-manifest 改请求头；`bifrost-applier-read` 改指 `gitea-ci-reader`；`rotate-admin-token.sh` 不再把管理员令牌写进克隆凭证；**`bifrost-deliver-platform-prod` 的 `check-source` 也改读 `gitea-ci-reader`**（复核 542 A4：它今天挂的是 `gitea-git-credentials`，S8 删旧凭证会让 PROD 发布卡住）。另查 Tekton 的凭证初始化：`secret.yaml.example:39` 有 `tekton.dev/git-0` 注解，关联到服务账号的这类 Secret 会被写进容器家目录的 `.gitconfig` / `.git-credentials`；只走请求头时把关联去掉。凭证只给 git 子进程，测试和安装脚本的环境里不能有 `GIT_CONFIG_VALUE_*` 之类的值。Tekton 对象不归 Argo，经 `plan_manifest`/`apply_manifest` 由 Owner 在 Console 批 | 一次 CI 克隆后，工作区、构建上下文、产物和凭证初始化目录（家目录的 `.gitconfig`、`.git-credentials`）里都找不到令牌（克隆任务的测试在本机对 bare 仓库跑一遍，`grep` 整个 `.git`）；候选测试步骤的环境里没有凭证变量；mirror-sync、github-sync、对账各跑通一次 | 重新 apply 上一版任务 |
| **S8** 收尾（Owner 定） | Owner | 先记下这次要吊销的令牌（名字、ID；不靠 `rotate-admin-token.sh revoked` 里固定的历史集合），再等用旧凭证的在途 TaskRun 跑完（已解析的任务定义不会跟着改）；`rotate-admin-token.sh` 读旧 Secret 的几处（`:83`、`:84`、`:331`）和 S7 一起改掉；核对 `git grep` 整个 `k8s/` 不再有对象引用 `gitea-git-credentials` 和 `gitea-bootstrap`（Owner 脚本除外）；然后克隆凭证 `gitea-git-credentials` 退役；`gitea-bootstrap` 搬到没有工作负载的命名空间（Owner 脚本随之改）；**换一次管理员令牌，并逐个吊销切换前存在过的令牌**（旧管理员令牌、旧克隆凭证的令牌）——STG 平台此前一直读得到它们 | `rotate-admin-token.sh check` 显示新令牌；每个旧令牌各发一次 `GET /api/v1/user` 都回 401；平台、CI、执行、评审身份都读不到 `gitea-bootstrap`；§1.3 的集群级控制器和备份身份逐个写明为什么信任、平台为什么改写不了也借用不了它们 | — |

**分批进 main**（复核 542 B：两个平台的 Argo 应用自动同步 infra main，整支分支一次推上去会让 S2、S5 的挂载提前生效）：

| 批 | 内容 | 推上去会发生什么 |
|---|---|---|
| A | 本文件、操作单、复核与回应；令牌脚本和测试；三条准入策略（`k8s/platform-rbac` 只由 Owner 手工 apply）和 `check_admission_guards.py`；CI webhook 过滤（`trigger-trade-ci.yaml`）和应用流水线的 C、D 级拒绝（`apply-manifest/pipeline.yaml`），这两个也只由 Owner 手工 apply；RBAC 防线（例外表暂含 STG、PROD 两条，到 S4、S6 各删一条）；台账与防线登记 | 集群不变；Owner 可以开始操作单第 1、2 节 |
| S2 | STG overlay 一个提交 | STG 平台两个 Pod 重建、挂上只读凭证（旧代码不读） |
| S4 | `gen_platform_rbac.py`、`10-stg.yaml`、`check_platform_rbac.py` 改 STG 为 no；防线删 STG 例外 | 集群不变，Owner 删绑定后才生效；在那之前线上核对会报这一行 |
| S5 ① | PROD overlay 一个提交（先问 Owner） | PROD 平台两个 Pod 重建、挂上只读凭证 |
| S6、S7 | 各自的提交 | 见上表 |

**4.1 的闸门**：TD-432 的 S1–S8、TD-434、TD-436 和 TD-435 的准入兜底都完成，执行与评审身份在 11 个仓库逐个验证过（main、合并、标签、改保护规则都被拒），才交 4.1 P0 的证据矩阵。S4、S6 的 `can-i` 为 no 或这批单测通过，都不算 P0 完成，不据此开 4.1 的 S2、S3，也不发真实的 main 写权限。

顺序的理由：Secret 先于代码（代码上线就要读）；overlay 先于代码（旧代码不读这个变量，可以先挂）；STG 核对后才撤 STG 绑定；S3b 必须在宣布「STG 拿不到管理员令牌」之前完成；PROD 同理；CI 那一片独立，可以和 S4–S6 并行，但要在 S8 换令牌之前。

---

## 4 防线

1. **平台代码**（`blocking`，随 `ci-platform`）：`TestNoGiteaAdminTokenInPlatformCode` 扫 `api/` 下所有非测试 Go 文件，出现 `gitea-bootstrap` 或 `gitea_admin_token` 就失败；`TestWithoutReaderGiteaIsNotAskedAndNoSecretIsRead`、`TestReaderIsTheOnlyCredentialSent` 锁住「没有 reader 不发请求、不读 Secret；有 reader 只发 reader」。在 main 上这条扫描会失败（`service.go` 里有两处名字）。
2. **RBAC 清单**（`manual`：infra 没有 CI）：`scripts/test_platform_rbac_secrets.py` 读整个 `k8s/`，认 ServiceAccount、`system:serviceaccount:` 形式的 User 和 `system:serviceaccounts[:<ns>]`、`system:authenticated` 组，任何 `bifrost-platform-*` 命名空间的服务账号经任何绑定能 get/list/watch 拒绝名单里的 Secret 就失败。名单：`cicd/gitea-bootstrap`、`cicd/gitea-git-credentials`、`cicd/gitea-ci-reader`、两个 `bifrost-gitea-reader`。例外表只许变短：现在 STG、PROD 各一条，S4 后只剩「PROD 读 `gitea-bootstrap`，到 S6」，一条例外不再匹配也失败。阳性对照：拿 main 的 `10-stg.yaml` 跑，报出 `('bifrost-platform-stg', 'cicd', 'gitea-bootstrap')`。接进 `make check-platform-rbac`。
3. **线上核对**（只读身份可跑）：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_platform_rbac.py
```

   S4 之后期望 `ok: 148 permission answers match`。Owner 的管理员 kubeconfig 可以直接问：`kubectl auth can-i get secret/gitea-bootstrap -n cicd --as=system:serviceaccount:bifrost-platform-stg:bifrost-platform` 回 `no`（PROD 同理，S6 之后）。
4. **准入用例**（第 2 稿已写）：`check_admission_guards.py --live` 覆盖 S3b、S3c、S3d 的拒绝与放行，`giteaBase` 已由准入钉死；**后续**：克隆任务的 `.git/config` 测试（S7 一起）；TD-435 按文件把参数改走环境变量（准入的字符白名单只兜住平台建的 run，触发器和 Owner 建的不经过它）。

---

## 5 没能核实的事

- `gitea-git-credentials` 现在是谁的：按 10-17 的记录是管理员，本次没读（不读 Secret 数据）。
- Gitea 1.21 的 `GET /repos/search` 结果带不带 `permissions`：令牌脚本依赖它；不带时脚本拒绝写入并列出全部仓库（宁可停）。没对真 Gitea 跑过；操作单让 Owner 先做 `stg` 一个，脚本过了再建另外两个。
- `bifrost` 组织里除 11 个主仓库外还有没有拉取镜像（`primary-probe`、`repo-template` 等）：有的话血缘的 `refreshMirrors` 会对它发 `mirror-sync` 并得 403，记在 `MirrorSync` 里，不影响其他功能。
- 11 个仓库现行的分支和标签保护（读规则要仓库管理员权限，只读账号和本线程都读不到）。
- `tekton-trigger` 的 Secret 读权限能不能删（EventListener 只用 CEL 拦截器时按 Tekton 文档不需要；没实测）。
- 镜像里会不会带进 `.git`：抽查 infra、platform、api、research、market-data 的 Dockerfile，没有 `COPY .`，也都没有 `.dockerignore`。复核 542 补读了 frontend 和 console：`Dockerfile.frontend-stg:13`、`:20`、`Dockerfile.platform-console-stg:8` 整目录 COPY，克隆目录的 `.git` 会进构建阶段，之后的 npm 脚本读得到；最终 nginx 阶段只拷 dist 和配置。现存镜像层没查。S7 后 `.git` 里没有凭证，这条就只剩代码可见。
- 平台 Pod 以 root 运行（0400 能读）只按 Dockerfile 没有 `USER` 推断，没看运行中的 Pod；S2 的验收在 Pod 里实读一次。
- 准入的 CEL 没在本地编译过（没有 apiserver）；Owner 应用前的服务器端 dry-run 会报语法错误，类型告警写在策略的 `status.typeChecking`，应用后由我读。线上现有 6 条策略已有类型告警（运行时按无类型对象求值，不改变行为）。
- 4.1 之后「在 main 上」不再等于「Owner 看过」：运行时能自己把一部分改动合进 platform、infra 的 main。应用流水线的 C、D 级只认 main，到那时要再加一道（例如 C、D 级只认 Owner 推的提交，或只认带签名的提交），在 4.1 的切法里定。

## 6 要 Owner 定的

| # | 事 | 推荐 | 备选 |
|---|---|---|---|
| 1 | 只读账号每个环境一个，还是一个共用 | **每个环境一个**（4.1 P0 第 3 稿也这么写；STG 的泄漏只换 STG 的） | 一个共用：少建一个账号、一个令牌，约省 5 分钟 |
| 2 | S3b（cicd ConfigMap 写）算不算 TD-432 | 已定：登记为 TD-434（P1），与 TD-435、TD-436 一起作为 4.1 P0 的前提（统筹线程 10-24） | — |
| 3 | S8 搬家并换管理员令牌 | **做**；STG 平台一直读得到它，S7 之后换一次 | 只换令牌不搬家：入口 §1.4 第 4、5 行对管理员令牌仍在 |
| 4 | Dockerfile 刷新能用哪些 revision（§1.4 第 10 行） | **只认 `main` 和发布标签**：平台代码和准入同改，Delivery 页的刷新按钮只给这两类 | 维持「任何分支或标签」：执行任务推的分支能决定 STG 镜像怎么构建 |
