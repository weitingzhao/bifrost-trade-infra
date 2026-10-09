# LANE-W33BR — W-33 返工：apply_manifest 的注入与绕过、准入策略的四个缺口

登记：`agent-config/WORK.md` 的 W-33（匹配 LANE-W33BR）。来源：Claude 10-09 验收 LANE-W33B（platform `c7a4821`，infra `e5b04b4`）。**合并和 apply 之前必须修。**

门禁本身全过：platform go build / vet / test，MCP 20，Console lint、682 个测试和 build；infra 的静态检查、`owner-run_test.sh`、TD-270 的三个测试也都过了。问题出在门禁没有覆盖的地方：Agent 能不经审批，借 B 级动作拿到 C 级、D10 或集群管理员的效果。

分支：在原分支上接着提交，不 rebase，不 force push。

- bifrost-platform · `cursor/w33b-platform`（现在是 `c7a4821`）
- bifrost-trade-infra · `cursor/w33b-infra`（现在是 `e5b04b4`）

先读：`LANE-W33B.md`、`reports/LANE-W33B.md`、本文件。

## 一、流水线脚本可以被参数注入（最严重）

**事实**：

- `k8s/cicd/tekton/apply-manifest/pipeline.yaml` 的脚本里写的是 `repo="$(params.repo)"`、`path="$(params.path)"`、`commit="$(params.commit)"`。Tekton 先把参数**按文本替换**进脚本，shell 再解析，所以脚本里对 commit 的正则检查发生在注入之后；
- Go 侧 `actuationpolicy.RepoAllowed` 只查路径前缀和 `..`，不限字符。`k8s/base/$(任意命令)` 能通过；
- 计划是 B 级，不用审批。

**后果**：任何拿着 operator 令牌的调用方都能以 `bifrost-applier` 的身份执行任意命令，不经审批就写 C 级命名空间（research、data、monitoring、bifrost-prod，以及 cicd 里的 Tekton 定义）。

**修法**：

1. 脚本里不再出现 `$(params.`：所有参数用 step 的 `env`（`value: $(params.x)`）传进去，脚本只读环境变量；
2. Go 侧：
   - repo 只允许 `^[A-Za-z0-9._-]+$`；
   - path 只允许 `^[A-Za-z0-9._/-]+$`，不能以 `/` 开头，不能有空段，不能有 `.` 或 `..` 段；
   - mode 只能是 plan 或 apply；
   - 脚本里用同样的字符集再查一遍。
3. 防线：
   - Go 测试：含 `$`、反引号、引号、空格、`;`、换行的 repo 和 path 都被拒；
   - 静态测试：流水线的 script 里没有 `$(params.`。

## 二、策略检查能被绕过，而且检查的不是实际 apply 的那份内容

**事实**：

- `apply-manifest-check.sh` 用 awk 逐行找顶格的 `kind:` 和两格缩进的 `namespace:`；
- 单文件路径是原样 `cp` 过去的。文档如果写成 flow 风格（`{kind: Deployment, ...}`）或 JSON，就没有顶格的 `kind:` 行，`flush_doc` 直接返回：这个对象不检查，不计入级别，也不参与 daemon 判断；
- 但 `kubectl apply -f /tmp/rendered.yaml` 照样会 apply 它。

**后果**：例如一个文件里放一份正常的 bifrost-dev ConfigMap，再用 flow 风格藏一个 bifrost-stg 的 `daemon` Deployment。计划算出来是 B 级，执行也是 B 级，不经审批就写进了 STG 的 daemon（D10）。

**修法**：

1. 渲染后先规范化成一份 JSON：`kubectl create --dry-run=client -o json -f rendered.yaml`，或者 kustomize 加 yq 转 JSON，结果是 List；
2. 用 jq 逐项检查 kind、apiVersion 的 group、`metadata.namespace`、name。任何一项缺 kind 或 namespace 就失败；
3. **apply 的就是这份规范化后的文件**，`objects.json` 也从同一份文件生成。
4. **「归 Argo 管」看活对象**：逐项 `kubectl get`（NotFound 跳过），带 `argocd.argoproj.io/tracking-id` 注解的就拒绝。现在只看渲染结果里有没有这个注解，而 git 里的清单从来不带它，所以这一步现在等于没查。
5. 防线：shell 测试的夹具要覆盖以下几种，全部被拒；正常的 kustomize 输出通过：
   - flow 风格文档；
   - JSON 文档；
   - 没有 namespace 的文档；
   - 用 flow 风格藏起来的 daemon Deployment；
   - 一份 List。

## 三、准入策略（TD-271 修法）的四个缺口

**1. Tekton 的远程解析器是开着的。**

- 实测：`tekton-pipelines-resolvers/resolvers-feature-flags` 里 git、bundles、cluster、hub 四个都是 true；
- 现在的策略只要求 `has(object.spec.pipelineRef)`。`pipelineRef.resolver: git` 能从任意 URL 拉一条 Pipeline 来跑，等于内联 spec；
- 修法：要求 `pipelineRef.name` 存在，且 `resolver`、`params`、`bundle` 都不存在。TaskRun 的 `taskRef` 同样处理。

**2. 工作区和 podTemplate 没限制。**

- 实测：现有的 PipelineRun 全部带 `taskRunTemplate.podTemplate`，工作区全部是 `volumeClaimTemplate`；
- cicd 里有 `argocd-initial-admin-secret` 和 `argocd-secret`（Argo 管理员）。平台身份建一个 run，用 `secret` 类型的工作区绑上它们，或者在 podTemplate 里挂 hostPath，就能拿到管理员；
- 修法：
  - 工作区只允许 `volumeClaimTemplate` 和 `emptyDir`；
  - `taskRunTemplate.podTemplate` 和 `taskRunSpecs[].podTemplate` 不能有 `volumes`、`hostNetwork`；
  - 先实测现有 run 的 podTemplate 用了哪些字段，报告里列出来。

**3. applier 写出来的 Pod 规格完全没受限制。**

- B 级命名空间（bifrost-dev、bifrost-stg、bifrost-platform-stg）不用审批。在那里写一个带 hostPath、privileged、hostNetwork 或 hostPID 的 Deployment，就拿到了节点 root，进而拿到集群管理员；
- `serviceAccountName` 也没限制。实测 monitoring 里有几个账号绑着能读**全集群 Secret** 的 ClusterRole：`kube-prometheus-stack-grafana`、`kube-prometheus-stack-operator`、loki 等；
- 修法：新增一条 ValidatingAdmissionPolicy，匹配 `system:serviceaccount:cicd:bifrost-applier`，覆盖 Deployment、StatefulSet、DaemonSet、Job、CronJob 的 Pod 模板：
  - hostPath、hostNetwork、hostPID、hostIPC、privileged、`capabilities.add` 一律拒绝，只有 monitoring 例外（节点级的 DaemonSet 在那里，而且 monitoring 是 C 级、要求 main 上的提交）；
  - `serviceAccountName` 必须在按命名空间列的白名单里。白名单从允许路径下的现有清单实测得出，写进 `actuation-policy.yaml` 的 `admission`；绑着能读 Secret 的角色的账号永远不进白名单。
- 平台身份建的 Job 和 Pod（`bifrost-platform-job-sa`）也加同样的 host 和 privileged 限制，作为纵深防御；
- cicd 里 applier 写的 Tekton Task 和 Pipeline：先实测现有的 Task 有没有用 hostPath 卷或 privileged。没有，就一并拒绝；有，就在报告里列出来，不改。

**4. Argo Application 的策略漏了两处。**

- Argo 在 `spec.sources`（多来源）存在时会忽略 `spec.source`，加一个 `sources` 就绕过了现在的比较；
- `source.kustomize`、`source.helm`、`source.plugin`、`source.directory` 里能写内联补丁和参数，现在没比较；
- 修法：
  - 要求 `has(object.spec.sources) == has(oldObject.spec.sources)`，存在时两边相等；
  - 上面四个子字段逐个比较：存在性相同，存在时相等。

**防线**：`check_admission_guards.py --live` 加上下面这些反例，全部要被拒绝：

- 带 resolver 的 run；
- 用 secret 工作区的 run；
- podTemplate 里挂 hostPath 的 run；
- applier 写的 hostPath Deployment；
- applier 写的、用 grafana 账号的 Deployment；
- 加了 `spec.sources` 的 Application；
- 改了 `source.kustomize` 的 Application。

不带 `--live` 时，用静态方式核对：这些规则都在策略文件里。

## 四、其余要改的

1. **镜像白名单匹配得太宽**：现在规则是「出现在开头或任意一个 `/` 之后」，所以 `evil.example/x/bifrost-research:1` 也能过。
   - 白名单改成带 registry 的完整前缀，只匹配开头。例如 `192.168.10.73:30500/bifrost-research:`；Docker Hub 的镜像写全称，或者在代码里明确展开简写；
   - 加测试。
2. **计划的身份没核对**：`Summarize` 接受 cicd 里任意一个 PipelineRun 名。要核对 `pipelineRef.name` 是策略里的流水线、标签 `bifrost.io/trigger=platform-api` 和 `bifrost.io/mode=plan`、参数 `mode=plan`；不符合就不算 ready。
3. **探针级别收紧**：bifrost-prod 和 bifrost-stg 的探针改成 C 级。Monitor 的 `/control/*` 在这两个命名空间里能直接访问，B 级等于不经审批就能碰 D10。这是收紧，道文件原写 B。
4. **apply 白名单和 30 天实测对齐**：报告里给一张表，列出每条实测路径的去向：允许、改用 `gitops_sync_app`，或者走 `owner_run_command`。
   - `k8s/overlays/{stg,prod,platform-stg,platform-prod}` 归 Argo 管，从白名单里拿掉；
   - `k8s/platform-rbac` 里只有 RBAC 和准入策略，applier 本来就写不了，拿掉；
   - bifrost-research 仓库的 `k8s` 是 Argo 应用 bifrost-research 的路径，拿掉，除非实测证明有不归 Argo 管的子路径；
   - 30 天里 apply 了 73 次的 `k8s/orchestration/dagster.yaml`：查清楚在哪个仓库、归不归 Argo 管，不归才加进来。
5. **`owner-run.sh`**：要求标准输入是终端（`[ -t 0 ]`），这样 `echo yes |` 管道过不去。加测试。
6. **合并顺序**：infra 分支同时改了两个 platform overlay 的 configMapGenerator，哈希一变，合进 main 就会滚动重启 PROD 的平台 Pod。照 W-33 的做法拆开：
   - 第 1 部分：STG overlay 和其余改动；
   - 第 2 部分：PROD overlay，单独一个提交，等 Owner 批了 PROD 再合。

   报告的「上线顺序」按这个写。

## 五、只读数据库账号（Owner 10-09 已回「数据库照做」）

- LANE-W33B 停在两个列名命中上：`research.copilot_bridge_event` 的 `input_tokens` 和 `output_tokens`，都是 integer 类型的用量计数，不是凭证；
- Claude 10-09 放宽条件又扫了一遍（列名再加 auth、cookie、session_key、bearer、dsn、connection string，外加名字像 config、settings、headers、env、params、options、meta 的 json 列），只多出策略和回测参数的 jsonb 列，也不是凭证；
- Owner 已确认，照 `LANE-W33B.md` 第五节原样做：`agent_reader` 加入 `pg_read_all_data`，建 DB 步骤文件，改 role-matrix，写 AGENT_FACTS 那一行。

## 门禁

LANE-W33B 的全部门禁，另加：

- `python3 scripts/check_admission_guards.py`；
- 流水线脚本的 shell 测试（第二节的那组夹具）；
- `bash scripts/owner/owner-run_test.sh`。

## 报告

写 `agent-config/work/ops-arch/reports/LANE-W33BR.md`。每节写：

- 改动（仓库 · 分支 · 完整 SHA）；
- 防线、门禁；
- 验收；
- 实测结果：podTemplate 用到的字段、各命名空间的账号白名单、Task 里有没有 hostPath 或 privileged、白名单路径的对照表。

「上线顺序」按第四节第 6 条拆开写。TD-271 维持「在做」，等 `--live` 通过再说。

报告从 origin/main 另开 worktree 提交，推 main 用同一条命令：
`bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`

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
