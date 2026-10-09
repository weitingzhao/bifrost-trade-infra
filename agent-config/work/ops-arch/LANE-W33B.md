# LANE-W33B — 第 5 阶段收口，第二批（第 2 步：Agent 的写收进动作目录）

登记：`agent-config/WORK.md` 的 W-33。依据：同目录 `W33-credentials-2026-10-08.md`「〇」节第 5 条：五个通用动作，外加一个只读数据库账号。新增这些动作属于新增公开接口，Owner 10-08 已同意；只读账号的 DDL 执行前仍要 Owner 逐次批。

本道是方案 A 的第 2 步。第 3 步（Mac 上的 Agent 换只读）依赖本道，之后另派，见文末「不在本道」。

> **派给 Cursor 之前，先由 Owner 定下面「〇」节的五件。** 定了以后把「待定」改成「已定」，并删掉没选的选项。

仓库与分支（都从最新 origin/main 开独立 worktree）：

- bifrost-platform · `cursor/w33b-platform`
- bifrost-trade-infra · `cursor/w33b-infra`

先读：`W33-credentials-2026-10-08.md`、`LANE-W33.md`、`reports/LANE-W33.md` 和 `reports/LANE-W33R.md`、`README.md` 的「范围」「给 Cursor 派道」「Cursor 共用规则」、`k8s/platform-rbac/00-clusterroles.yaml` 的头注释。

## 〇、要 Owner 定的五件（待定）

### 1. 兜底的 `owner_run_command` 由谁执行

10-08 的决定写的是「Owner 批后由平台用管理员身份执行」。那是 Claude 的推荐原文，现在发现它和 TD-204 冲突：平台要执行任意命令，就得重新持有集群管理员。

- **A（推荐）只记录审批，Owner 执行**：做法和 `rolling_reboot` 一样。平台记下原样命令和它的哈希，批准后返回「请执行 `bash scripts/owner/owner-run.sh <id>`」。脚本用 viewer 令牌读审批，核对动作、状态、时效和命令哈希，回显命令，Owner 输入 `yes` 后用 Owner 目录里的管理员 kubeconfig 执行。平台始终不拿管理员身份。
- B 平台用管理员身份执行：推翻 TD-204，平台的任何漏洞都等于集群管理员。
- C Mac 上常驻一个持管理员凭证的执行器，自动执行已批准的单子：它和 Agent 在同一台机器、同一个用户下，只能靠 preflight 的文本匹配挡住 Agent。

### 2. `apply_manifest` 由谁执行

- **A（推荐）固定的 Tekton 流水线加专用身份**：平台在 cicd 起一个固定的流水线 `bifrost-apply-manifest`，用新建的 ServiceAccount `bifrost-applier` 执行。`bifrost-applier` 只在白名单命名空间里有白名单资源类型的写权限：不能动集群级对象，不能动 RBAC，不能写 Secret。平台自己的 ServiceAccount 不扩权。
- B 平台进程内渲染，用平台自己的身份 apply：平台的 ServiceAccount 要拿到白名单命名空间里的大面积写权限；Go 侧还要引入 kustomize 库，这是新的外部依赖。
- C 把常用路径收成 Argo Application：apply 变成「合 main 加 `gitops_sync_app`」，后者已经在动作目录里。插件、Dagster、Tekton、monitoring 各要建 Application，改动面最大，还和架构方向里的「插件归位」重叠。

**审批量提醒**：research 和插件只有 PROD 一套部署，按规则是 C 级。按 30 天实测，这类 apply 约 210 次（同一任务里的反复 apply 也算在内），平均每天约 7 次审批。如果嫌多，以后用 W-31 的规则集放宽（例如「main 上的提交、只改镜像 tag」自动批），本道不做。

### 3. Agent 在应用 Pod 里的 exec（决定第 3 步的只读角色，也决定本道的 `env_from`）

30 天实测 3,027 次 `kubectl exec`：

- `psql` 1,569 次，由本道的只读数据库账号接走；
- research 命名空间 599 次、插件命名空间 405 次，大多是在应用 Pod 里跑 python 查数据或调本地接口，少数是手动跑一次调度槽或引擎；
- 另有 93 次 `kubectl cp` 把脚本拷进 Pod 再执行。

选项：

- **A（推荐）第 3 步的只读角色保留 `pods/exec`，但只在 research、plugin-market-data、plugin-flex-query 三个命名空间**（`kubectl cp` 也走 exec），其余命名空间不给。Agent 仍能借这些 Pod 的数据库凭证写 Golden Source 和插件自己的表，但它不是集群管理员。这一条作为接受的风险写进 ADR。本道的 `run_probe_pod` 只在这三个命名空间允许 `env_from`。
- B 收掉所有 exec：本道再加一个 `run_in_workload` 动作，在指定 Deployment 里执行 git 里某个提交的脚本。临时脚本要先提交，调试摩擦大。
- C 只读角色完全不给 exec，读数据只走 HTTP 端点：研究和插件的调试基本停摆。

### 4. 发版链怎么摆脱管理员 kubeconfig

实测：cicd 里的 `argocd-application-controller` 是全集群管理员。谁能在 cicd 建 PipelineRun，谁就能指定 cicd 里任意一个 ServiceAccount 来跑任意步骤。所以第 3 步不能给 Agent「在 cicd 建 PipelineRun」这种看似很窄的权限。`release.sh` 现在直接用 kubectl 建 PipelineRun、写发布窗口的 ConfigMap，DB 步骤也用 `kubectl exec psql`。

- **A（推荐）单开一道 LANE-W33C，等本道验收后再写**：建 run 改走平台的 `start_pipeline_run`。PROD 的 pinned run 带多仓库 SHA 参数，`start_pipeline_run` 要扩展成可以带参数（只接受流水线声明过的参数）。窗口 ConfigMap 改由平台写。PROD 的 DB 步骤走本道的 `owner_run_command`。这样也顺带推进 W-31 发布队列的验收：当天所有 run 都进 PROD 审计。
- B 第 3 步之后，发版由 Owner 亲手跑 `release.sh`：每天几次发版都要 Owner 在终端里执行。
- C 留给 W-31 的发布队列：第 3 步要等 W-31，而 W-31 在等瘦身完成，两边互相等。

### 5. TD-271（平台身份经 Tekton 和 Argo 间接等于集群管理员）放不放进本道

本道把 Agent 的写都收到平台上。如果平台身份本身就等于管理员，第 3 步只是把风险从 Mac 挪到了 platform-api。

- **A（推荐）放进本道第四节**：用 ValidatingAdmissionPolicy（Kubernetes 自带，不是新依赖）和收窄的 Argo AppProject 把这两条路堵上。上线时 apply 由 Owner 批。
- B 单独排期：本道照做，在 TD-271 修好之前，第 3 步不开始。

## 事实（2026-10-09 实测；platform main `0bf5285`，infra main `a23aae3`）

- **动作目录**：`api/internal/actions/catalog.go` 现在有 29 条（B 10、C 10、D 9）。只有 C、D 级需要审批，直接调用返回 403，批准后由 executor 执行（`actions.RegisterExecutor`）。`rolling_reboot` 是「只记录、不执行」的先例：`api/internal/actions/rolling_reboot.go`。
- **平台身份**（TD-204，`k8s/platform-rbac/`，不归 Argo，手工 apply）：
  - 两个环境都有全集群只读（不含 Secret）；
  - PROD 另有：Bifrost 命名空间里的 rollout restart、scale、删 Pod，节点 cordon 和 drain，data 里的 CNPG Backup，cicd 里建和删 PipelineRun / TaskRun，改 Argo Application；
  - 没有 Job 的 create 权限，也不能在任何命名空间建 Pod。
- **TD-271**（本道登记）：
  - `kubectl auth can-i --as=system:serviceaccount:bifrost-platform-prod:bifrost-platform`：`create pipelineruns -n cicd` 为 yes，`patch applications -n cicd` 为 yes；
  - `clusterrole/argocd-application-controller` 的规则是 `*/*/*`；
  - 5 个 Argo Application 都在 AppProject `default`，它的 sourceRepos 是 `*`，destinations 是 `*`；
  - `tekton-trigger` 也能在 cicd 建 PipelineRun，`tekton-deliver` 也能 patch Application。
- **30 天 Agent 写操作**（按每次调用去重，Mac 上全部会话）：
  - `apply`：插件 `k8s/base` 约 84 次，`k8s/orchestration/dagster.yaml` 73 次，`k8s/cicd/tekton` 24 次，`k8s/monitoring` 约 21 次，`k8s/ib-gateway/overlays` 7 次，另有零散的 `k8s/data/logical-backup`、`k8s/platform-rbac`、`k8s/cicd/gitea`；还有 63 次 apply 或 create 临时文件、27 次 heredoc；
  - `create job --from=cronjob` 18 次：monitoring/maintainer-reconcile 6、cicd/tekton-pipelinerun-ttl 5、data/logical-backup-drill 3、data/logical-backup 2、bifrost-prod/position-snapshot-capture 1、kube-system/cluster-state-backup 1；
  - `run --image` 104 次：research 和插件的应用镜像、minio、redis、curl、alpine/k8s；
  - `delete` 215 次：pod 约 80、job 56、pipelinerun 14、configmap 6、pvc 4、cronjob 2、networkpolicy 2 等；
  - `exec` 3,027 次，见〇第 3 件。
- **数据库**：CNPG `bifrost-postgres`，PG 17.9，2 个实例。局域网入口是 NodePort `30432` 指向主库，已在 `check_data_lan_exposure.py` 的白名单里。现有的 `role_matrix_reader` 只能连库，查不了表。DB 步骤的格式见 `scripts/release/db-steps.d/2026-10-07-td85-role-matrix-reader.md`。
- **旧文字**：platform `console/src` 里还有 30 个文件提到 remediation runner、hermes、`:8781` 或 `:8782`，例如 `lib/environments-catalog.ts:200`（「Dual Mac Mini Remediation Runners…」）、`components/control-room/RocketSubsystemsGrid.tsx:35`、`lib/control-room/dailyOpsChecklistCatalog.ts:226`、`lib/agent/agentTaskCatalog.ts`、`lib/agent/agentScopes.ts`。
- **TD-270**：见 `TECH_DEBT.md` 的 TD-270。

## 要做

按〇节的推荐写。Owner 选了别的选项时，Claude 先改这一节再派道。

### 一、策略配置（平台不认识具体应用）

所有白名单都写进 platform 的新配置文件 `config/actuation-policy.yaml`，代码里不出现具体的命名空间、仓库或镜像名。照 W-32 的教训，这几处一起改：

- `scripts/sync_platform_k8s_config.sh` 的同步清单；
- 两个 overlay 的 `configMapGenerator`；
- `check_ops_context_parity.py` 的副本比对。

内容：

- `apply_manifest`：
  - 允许的仓库和路径前缀；
  - 每个命名空间的级别：B 是 `bifrost-dev`、`bifrost-stg`，其余允许的命名空间是 C；
  - 允许的资源类型；
  - cicd 只允许 Tekton 的定义类对象（Pipeline、Task、TriggerTemplate、TriggerBinding、EventListener）。
- `create_job_from_cronjob`：允许的命名空间和级别，加一个禁止清单。
- `run_probe_pod`：
  - 允许的镜像（含 tag 前缀，例如内部 registry 的 `bifrost-research:`、`bifrost-market-data:`，以及 minio、curl）；
  - 允许的命名空间和级别；
  - 允许 `env_from` 的命名空间（〇第 3 件 A：research、plugin-market-data、plugin-flex-query）。
- `cleanup`：允许的命名空间。

**kube-system 和 cicd 不能起 Job，也不能起探针 Pod**。在那里起 Pod，就能用那里任意一个 ServiceAccount，cicd 里有集群管理员。`kube-system/cluster-state-backup` 的手动触发走 `owner_run_command`。

### 二、五个动作（platform）

每个动作都在 `catalog.go` 登记，用 `Classify` 按参数算级别，并注册 executor。C、D 级照现有流程：直接调用返回 403，走审批。

1. **`apply_manifest`**：两段式。
   - **计划**：`POST /api/v1/actuation/manifests/plan`，B 级，参数 `repo`、`path`、`commit`（完整 SHA）。平台以 `mode=plan` 起 `bifrost-apply-manifest`：
     - 从集群内 Gitea 取这个提交；
     - `kubectl kustomize`（单文件就直接读）渲染；
     - 做策略检查：命名空间、资源类型、是否归 Argo 管（活对象带 Argo 的跟踪标记就拒绝，提示改用 `gitops_sync_app`）、D10（见下）；
     - 跑 `kubectl diff --server-side`。

     返回计划 id（就是 run 名）。计划结果（对象清单，以及每个对象是新建、修改还是不变）写进 run 的 results，完整 diff 在日志里。
   - **执行**：动作 `apply_manifest`，参数只有 `plan_id`。
     - 级别取计划里所有命名空间中最高的那个；
     - C 级要求提交在 Gitea 的 main 上可达；
     - executor 先核对计划 run 成功、策略检查通过，再以 `mode=apply` 起同一条流水线，用 `kubectl apply --server-side --field-manager=bifrost-applier` 执行；
     - 不做 prune。要删的对象走清理类动作，或者走 `owner_run_command`。

     审批单显示计划摘要和计划 run 的日志链接。
   - **D10**：渲染结果里出现名为 `daemon` 的 Deployment 就判 X 级，不能申请。复用现有的 `refuseDaemonScaleUp` 口径，不另写一套。
2. **`create_job_from_cronjob`**：参数 `namespace`、`cronjob`。
   - 平台照 CronJob 的 `jobTemplate` 生成 Job，效果同 `kubectl create job --from`：名字 `<cronjob>-manual-<时间>`，带 `cronjob.kubernetes.io/instantiate: manual`，标签写明申请人；
   - 级别按策略配置：PROD 业务命名空间和 data 是 C，其余是 B；
   - 命中禁止清单的直接拒绝。
3. **`delete_finished_jobs`**（清理类）：参数 `namespace`，加 `names` 或 `label_selector` 二选一。
   - 只删带 Complete 或 Failed 条件的 Job，`propagationPolicy: Background`；
   - 也删本道探针留下的 Pod（带 `bifrost.io/probe=true` 标签）；
   - B 级。

   PipelineRun 和 Pod 的删除已经有 `delete_pipeline_run`、`delete_pod`，不重复做。PVC、CronJob、NetworkPolicy、命名空间的删除走 `owner_run_command`。
4. **`run_probe_pod`**：参数 `namespace`、`image`、`command`、`args`、可选的 `env_from`（同命名空间里一个 Deployment 的名字）、`timeout_seconds`（不超过 900）。
   - 用 Job 实现：`backoffLimit: 0`、`ttlSecondsAfterFinished: 3600`、`activeDeadlineSeconds`、`automountServiceAccountToken: false`；用 default ServiceAccount；设资源上限；带 `bifrost.io/probe=true` 标签；
   - `env_from` 只复制那个 Deployment 第一个容器的 `env` 和 `envFrom`，而且只在策略允许的命名空间里可用；
   - 镜像不在白名单里就拒绝；
   - 级别：B，data 命名空间是 C（data 里的 Redis 没有密码，见 TD-205；D10 的 operator 流就在那里）；
   - 日志走现有的 Pod 日志路由。
   - 探针一启动就连网会被 NetworkPolicy 竞态拒绝，起步先等策略生效再连，做法照 `wait-pg`。
5. **`owner_run_command`**：D 级，参数 `command`（原样的 shell 命令）、`reason`。
   - 平台只记录审批，不执行。批准后返回 `{recorded: true, executed_by_platform: false, command, command_sha256, message}`，写法照 `RollingRebootResult`；
   - infra 新增 `scripts/owner/owner-run.sh <approval-id>`：
     - 用 viewer 令牌读 `GET /api/v1/approvals/<id>`；
     - 要求动作是 `owner_run_command`、状态是 executed、批准时间不超过 24 小时，并且命令的哈希一致；
     - 回显命令，要求输入 `yes`；
     - 用环境变量 `OWNER_KUBECONFIG` 指定的 kubeconfig 执行（第 3 步把它定到 Owner 目录）；
     - 结果追加到 `~/.bifrost-owner/run-log.jsonl`；
   - 脚本头注释写明：只给 Owner 用，Agent 不运行。

MCP：B 级的三个计划和动作（`plan_manifest`、`create_job_from_cronjob`、`delete_finished_jobs`、`run_probe_pod`）加工具；C、D 级照旧走 `request_action`。Console 的审批卡片显示 `apply_manifest` 的计划摘要，以及 `owner_run_command` 的原样命令。

### 三、infra：执行身份与流水线

- **`bifrost-applier`**：cicd 里新建这个 ServiceAccount。新 ClusterRole 只列策略允许的资源类型，verbs 是 get、list、create、patch、update；每个允许的命名空间绑一个 RoleBinding。和 `gen_platform_rbac.py` 一样，绑定从命名空间清单生成，**清单和 platform 的 `actuation-policy.yaml` 只有一份来源**，另一份由检查脚本比对，不一致就失败。
- **流水线**：`k8s/cicd/tekton/pipeline-apply-manifest.yaml`，两种模式 `plan` 和 `apply`。镜像用现有 Tekton 任务已经在用的 `alpine/k8s:1.31.4`，不新加镜像。
- **平台身份扩权（只限 PROD）**：
  - batch/jobs 的 create 和 delete，只绑在策略允许起 Job 或探针的命名空间；
  - pods 的 list 已经有了；
  - 不给 pods 的 create。探针都用 Job 起。
- `check_platform_rbac.py` 加上能做和不能做的断言：
  - 能：在 research 建 Job、在 bifrost-dev 删 Job；
  - 不能：在 kube-system、cicd 建 Job，建 Secret，建 RoleBinding；
  - `bifrost-applier` 能 patch research 的 Deployment，不能写 Secret，不能动 RBAC，不能碰 kube-system。

### 四、TD-271：堵住平台身份的两条间接提权路径（〇第 5 件 A）

- **ValidatingAdmissionPolicy**（`k8s/platform-rbac/` 下新文件，同样手工 apply）：
  1. 平台身份在 cicd 建的 PipelineRun / TaskRun 必须用 `pipelineRef` / `taskRef`，不能内联 spec；所有 `serviceAccountName`（包括 `taskRunTemplate` 和 `taskRunSpecs`）必须在白名单里，`argocd-*` 永远不在；
  2. 用 `bifrost-applier` 的 PipelineRun 只能引用 `bifrost-apply-manifest`；
  3. 平台身份建的 Job 和 Pod，`serviceAccountName` 必须在白名单里（默认只有 `default`）；
  4. 平台身份和 `tekton-deliver` 改 Argo Application 时，只能改同步操作（`operation`）和 `targetRevision`，不能改 source 的 repo 和 path、`project`、`destination`。

  白名单按实测填：现有流水线模板用到的 ServiceAccount、现有 CronJob 模板用到的 ServiceAccount。`tekton-trigger` 不走平台，不在本道收，报告里写明它也有同样的能力，后续登记。
- **Argo AppProject `bifrost`**：
  - sourceRepos 是 5 个 Application 现在用的仓库；
  - destinations 是它们现在的命名空间；
  - 集群级资源白名单是它们现在实际部署的类型（从 Application 的资源树实测）。

  5 个 Application 迁进这个项目。`default` 项目收窄成空（不删）。
- 新检查 `scripts/check_admission_guards.py --live`：用 `--dry-run=server --as=<身份>` 逐条验证，期望如下：
  - 内联 spec 的 PipelineRun 被拒；
  - 用 argocd ServiceAccount 的 run 被拒；
  - 平台身份在 research 建 SA 不在白名单里的 Job 被拒；
  - 改 Application 的 source 被拒；
  - 正常的 `pipelineRef` run 放行；
  - 同步操作放行。

  不带 `--live` 时检查策略文件本身（kustomize 渲染、白名单和清单一致）。

### 五、只读数据库账号（infra）

- 新的 DB 步骤 `scripts/release/db-steps.d/2026-10-xx-w33-agent-reader.md`，带 sql、verify、rollback 三个文件，格式照 TD-85 那份：
  - 角色 `agent_reader`：LOGIN，不是超级用户，加入 `pg_read_all_data`；
  - 角色级设置：`default_transaction_read_only = on`、`statement_timeout = '120s'`、`idle_in_transaction_session_timeout = '60s'`，`CONNECTION LIMIT 8`；
  - 四个库只给 CONNECT；
  - 回滚只收回 CONNECT 并设 NOLOGIN，不删角色。
- **开工先实测**：在四个库里找列名像 token、secret、password、api_key 的表，结果写进报告。有命中就停下回报，不改用别的授权方式。`pg_read_all_data` 收不回单张表。
- `k8s/data/role-matrix/expected.yaml` 加 `agent_reader`，四个库都只有 connect，没有 grants（按「没写就是禁止」），这样每天的对账会盯住它不能写。
- 密码不进 git，也不进集群：Owner 设好后写进 Mac 的 `~/.pgpass`（600），只这一行。报告里写清楚 Owner 要执行的两条命令。
- `AGENT_FACTS.md` §8c 加一行：数据库只读查询用 `agent_reader`，经 `192.168.10.73:30432` 用 psql 连接，不再 `kubectl exec psql`。

### 六、顺带两件

- **旧文字**：Console 里提到 remediation runner、hermes-gateway、Nous Hermes 的用户可见文字，删掉或改成现状：mini 跑 operator-plane（带外面）和 peer-watchdog，.50 负责告警中转。只为 runner 服务、现在没有引用的目录和类型（`agentTaskCatalog.ts`、`agentScopes.ts` 等，先确认零引用）一起删。

  完成后，下面这条 grep 只能命中退役测试和明确写着「已退役」的地方，报告里列出剩下的命中：

  ```bash
  grep -rniE 'remediation runner|remediation-runner|hermes|:8781|:8782' console/src api/internal mcp
  ```
- **TD-270**：照台账的修法，两个 data-clone store 改用 `statefile.Update`，每次读都重读；防线用两个 store 实例的测试，写法同 `patrol/store_share_test.go`。修完按台账的签收流程写回验收结果，状态改成「待你签收」。

## 防线

- `catalog_test` 和 `coverage_test` 覆盖五个新动作。级别测试：
  - `apply_manifest`：dev / stg 是 B，research 是 C，计划里出现 daemon 是 X；
  - `run_probe_pod`：data 是 C；
  - 不在白名单的镜像或命名空间被拒；
  - `env_from` 在不允许的命名空间被拒。
- `owner_run_command`：
  - 测试断言 executor 只返回命令、不执行（注入一个会失败的执行器，确认没被调用）；
  - `owner-run.sh` 的测试：状态不对、过期、哈希不符都拒绝。
- `check_platform_rbac.py` 的新断言；`check_admission_guards.py`；`check_actuation_policy.py`（或并进现有检查）：applier 的命名空间清单和 platform 的策略配置一致。
- `check_ops_context_parity.py` 覆盖 `actuation-policy.yaml`。
- role-matrix 的检查覆盖 `agent_reader`。
- TD-270 的两个 store 测试。
- RATCHETS.md 登记以上新增防线。

## 门禁

- platform `api/`：`go build ./... && go vet ./... && go test ./...`
- platform `mcp/platform`：`npm test`
- platform `console/`：`npm run lint && npm test && npm run build`
- infra：
  - `make check-platform-rbac`（不带 LIVE）
  - `python3 scripts/check_admission_guards.py`
  - `kubectl kustomize k8s/platform-rbac`
  - `kubectl kustomize k8s/overlays/platform-prod`
  - `kubectl kustomize k8s/overlays/platform-stg`
  - `python3 -m unittest k8s/data/role-matrix/test_check_role_matrix.py`
  - `PLATFORM_ROOT=<w33b-platform worktree> python3 scripts/check_ops_context_parity.py`
  - `bash agent-config/scripts/check-agent-config-parity.sh`
- `scripts/owner/owner-run.sh` 的测试。

## 报告

写 `agent-config/work/ops-arch/reports/LANE-W33B.md`，格式按 README：

- 每节写：
  - 改动（仓库 · 分支 · 完整 SHA）；
  - 防线、门禁；
  - 验收（一条命令加预期）；
  - 要 Owner 批的（原样可执行的命令）；
  - 后续。
- 附「数据库实测」：疑似凭证列的结果。
- 附一张「上线顺序」清单，供 Claude 执行，每一步注明要不要 Owner 批。参考顺序：
  1. 合并；
  2. apply `k8s/platform-rbac`，包括 applier、VAP、Job 权限（Owner 批）；
  3. 迁 AppProject（Owner 批）；
  4. `check_platform_rbac.py --live` 和 `check_admission_guards.py --live`；
  5. 在 cicd apply 流水线定义；
  6. STG 发布，Owner 过目。STG 只观测，executor 只在 PROD 生效：STG 上能看到新动作，直接调用会被拒绝；
  7. PROD 发布（审批）；
  8. PROD 冒烟：
     - 对 bifrost-dev 里一个无害的 ConfigMap 走一遍「计划、执行」；
     - 从 `monitoring/maintainer-reconcile` 起一次 Job；
     - 起一个 curl 探针；
     - 清理它们；
     - 提一张 `owner_run_command`，然后驳回；
  9. DB 步骤（PROD DDL，Owner 批）；
  10. Owner 设密码，写 `~/.pgpass`；
  11. 用 `agent_reader` 跑一次只读查询，并试一次写入，确认被拒。

报告从 origin/main 另开 worktree 提交，推 main 用同一条命令：
`bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`

## 不在本道（之后另派）

- **LANE-W33C 发版链**（〇第 4 件 A）：`release.sh`、插件和 research 的发布脚本改走平台。本道验收后再写。
- **第 3 步**：Mac 上的 Agent 换只读 kubeconfig，按〇第 3 件定的 exec 范围；管理员 kubeconfig 和 `bifrost_deploy` 搬到 Owner 专用目录，preflight 按路径拦；ADR 写进接受的风险。
- `tekton-trigger` 能在 cicd 建 PipelineRun（TD-271 的同类），报告里登记，不在本道修。

## 不做

- 多 Agent 运行时：任务与租约、Agent 主机守护进程、交互总线、推理网关、额度账本；
- 发布队列（本道不改 `release.sh`）；
- RP 发版策略（`cursor/rp-*` 两条分支不合）；
- 认领与待办箱；
- 工作项编号规则；
- Grok Bot 相关的任何事（它暂停中：不验收 LANE-N / LANE-M2，不收尾它的台账）。
- 不改 `api/internal/approvals/` 的审批语义（删除已退场功能的调用方除外；新增动作只走现有的审批流程）。
- 不发版、不 apply、不写数据库、代码不推 main。
- 不碰 `scripts/agent-guard/`（preflight 闸门）。
- 暂缓、不在瘦身范围：TWS 自动重启、交易区迁移、网络分区。
