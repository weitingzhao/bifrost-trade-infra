# 发布冻结协议：冻结是一条只能新建的记录，解冻是 Owner 把它删掉（TD-310 的设计）

> **状态（2026-10-12 12:55）：搁置。** Owner 当天定的方向是护栏先做、协作机制和全自动发布先放下（`WORK.md` W-31、W-56）。已经在主线上的是第一片（离线的判定和两份实现，没有接线）；正式环境照旧拒绝冻结。这份文档里 2026-10-12 的两轮修订——第一轮经复核 121 判「先修」（协议本身没找到错，问题在第 7.1 节给 Owner 的操作单），「之二」是按那次复核改的，**没有再复核过，也没有任何一条命令被执行过**。恢复时从复核「之二」开始；在那之前第 7.1 节不能照着做。操作单和两份任务书（准备片、S3a）在统筹方的工作目录里，没有派出。

状态：设计通过，可以实现（2026-10-11：复核 93、95 通过；片 1 的复核 100 之后修订第 3.2、6、8 节三次，复核 101、103、104，必须改的 1 → 1 → 0；L 只有一处定义）；六项决定不变。复核 95 留下的 6 个 P2、2 个 P3 已并入，逐条见第 11 节；复核 100、101、103 见第 12 节。没有代码，没有改集群；实现并验收之前，冻结保持被拒绝，和今天 PROD 上一样。
**「修订 2026-10-12」（复核 121 看过，结论是「先改」，见下一段）**：片 1 合并之后写第二片的操作单和第三片的任务书时，发现步 0–5 有 22 格没有命令、「建」怎样算成功没有写、「满 20 条」经门的读函数数不到。统筹方当天的四项裁定记在第 9 节 D7–D10，连同只读实测并入本文：「建成」以回读为准；「满 20 条」换成按字节算的上限，读不到时照样建；占位符留在仓库；步 0–5 每一格落成一条命令或一项 Owner 自己的观察。改到的段落都标着「修订 2026-10-12」，清单和「已知、延后」的表在第 13 节。没有改 L、H、传输各行，没有改第 6 节的模型。这一轮的实测是 2026-10-12 上午（CDT）用同一个只读身份做的 `kubectl get`、`kubectl api-resources`、`kubectl version` 和对它自己的 `kubectl auth can-i`，标作「实测 10-12」。
**「修订 2026-10-12 之二」（这一轮尚未复核）**：复核 121（`~/agent-work/codex-review-121/REPORT.md`）对上一轮修订的结论是「先改」。协议的逻辑它没有找到反例；问题在步 0–5 的操作：步 4 的临时 Pod 带着平台账号和 applier 账号的全部权限，没有期限，建失败时会删掉别人的对象；有几格把失败的查询当成了预期输出；步 5 的退路只恢复两个 Task；「单独一条记录装不装得下」没有定。统筹方当天的九项裁定并入本文：步 4 不在真实账号下起 Pod，改成四次 `can-i` 加探针账号下的一次真读；每一格先取结果和退出码、再判；拒绝的来源按策略名和规则原文认；CRD 把字段收短，空清单上建的一条总装得下；D10 加上复核方的条件。7.1 整节重写；其余改到的段落标着「修订 2026-10-12 之二」，清单在第 13 节。没有改 L、H、传输各行，没有改第 6 节的模型，没有改准入策略的三条规则。这一轮新做的只读查询，都用同一个只读身份：`kubectl api-resources`；`cicd` 里 ConfigMap、Pod、ServiceAccount、流水线、PipelineRun、TaskRun 的 `kubectl get`；ClusterRole、ClusterRoleBinding、RoleBinding 的 `kubectl get`。带 Owner 凭证的命令仍然没有任何人跑过。
输入：复核 79、82（`~/agent-work/td-310/REVIEW-{79,82}.md`）、86、93、95（`~/agent-work/codex-review-{86,93,95}/REPORT.md`）；实现方三轮报告（`~/agent-work/td-310/REPORT{,-2,-3}.md`）；分支 `w31/td-310-anchor`（platform `6658550`、infra `3fdaa41`，是材料，不是基线）；`PLAN-w56-unattended-prod-2026-10-10.md` 第 1 步；`TECH_DEBT.md` 的 TD-293、TD-310、TD-314；`LESSONS-from-practice.md` 第 85、86 行。
路径约定：`api/` 开头的相对 `bifrost-platform/`；`k8s/`、`scripts/`、`docs/`、`agent-config/` 开头的相对 `bifrost-trade-infra/`。
事实的标法：**实测** = 2026-10-11 16:45–17:30 CDT 用只读身份 `bifrost-access/bifrost-agent` 对集群做 `kubectl get`（RBAC、准入策略、ConfigMap、Tekton 对象、Application、Pod、节点），或读文件（给出 `文件:行`）；**假定** = 没量。「谁能做什么」是读角色和绑定算出来的（汇总在附录），没有向 apiserver 逐项提问，也没有试写。
已定、本文不讨论：谁都可以冻结，只有 Owner 能解冻；平台不含交易概念；D10 不在范围内。

## 0. 结论

三轮实现要证明的是「没有 Owner 针对这一次冻结的新表态，它解不开」。六个绕法的根比任务书写的还深一层：**「已解冻」被存成了一个值**（对象上的 `frozen=false` 加一段签名）。值可以被写回去、被重放、被两份记忆排错先后；进程的记忆正是为了补这一点才加的。本文的改法是让「已解冻」不再是一个值：

- 一次冻结 = 新建一个集群级对象 `Freeze`（专用资源类型 `freezes.release.bifrost.io`），名字是随机数。
- 冻结 ⇔ 这类对象至少有一个。放行只在 `clear`（3.2）。`frozen` 和读不到都是拒绝。
- 一条记录的一生只在一处写明，就是一条准入策略：建的时候元数据里只许有名字；任何修改都不放行；删除只对 Owner 的身份放行。准入对每一个身份的每一次请求都执行，所以「谁能让一条记录消失」不取决于一张 RBAC 的清单。RBAC 是第二层：平台账号只有 `create` 和 `list`，流水线账号只有 `list`。
- 解冻 = Owner 用他自己的集群凭证删掉那一条。没有记忆，没有合并，没有「最新一次」，没有解冻签名，没有可以放回去的旧状态。签名密钥只用于策略（第 4 节）。
- 旧对象 `cicd/bifrost-release-freeze` 在打开冻结之前被写成一块永远是「冻结」的墓碑；它在，还在读它的旧程序就只会拒绝（第 5 节）。

「没有」不是一个值：它不能被重放；要把它放回去只有删除一条路，而删除只有一个身份做得到。

## 1. 威胁模型（实测）

### 1.1 今天谁能写 `cicd/bifrost-release-freeze`

对象现状：`data` 只有 `frozen: "false"`（从未冻结的形状），没有 `immutable`；字段管理者只有 `kubectl-create`（10-10）和 `kubectl-patch`（2026-10-11T17:59:50Z，演练后 Owner 手工改回）。集群上有 6 条 ValidatingAdmissionPolicy，没有一条的规则匹配 `cicd` 里的 ConfigMap。webhook 配置只读身份读不到（Forbidden），**未测**。下表的权限三列和来源一列都是实测；最后一列里从文件读来的写了文件名。

| 身份 | 建 | 改 | 删 | 来源（绑定 → 角色） | Agent 不经审批够得着吗 |
|---|---|---|---|---|---|
| PROD 平台 `bifrost-platform-prod/bifrost-platform`（api 和 workers 是同一个账号） | ✓ | ✓ | – | RB `cicd/bifrost-platform-state-prod` → ClusterRole `bifrost-platform-state`：`cicd` 里**任意** ConfigMap，没有 `resourceNames` | 经接口：`release_freeze`、`release_unfreeze`、`release_policy_install` 都是 B 级（主线 `api/internal/actions/catalog.go:128–153`），今天因为没有锚、任何签名都验不过而被拒。直接拿到这个账号：推 infra 的 `main`，Argo 自动同步平台的 overlay（`automated: prune + selfHeal`），平台进程就被换掉，不经审批（ADR §5 已接受的风险） |
| STG 平台 `bifrost-platform-stg/bifrost-platform` | ✓ | ✓ | – | RB `cicd/bifrost-platform-state-stg` → 同一个角色 | 同上 |
| `cicd/tekton-deliver` | ✓ | ✓ | – | RB `tekton-deliver-argocd` → Role（任意 ConfigMap） | `start_pipeline_run` 对非 PROD 流水线是 B 级，run 可以点名这个账号（准入白名单 `default` / `tekton-deliver` / `bifrost-applier`，必须是具名流水线）。任务的脚本是固定的；参数能不能把一次写入带进脚本，**未测** |
| `cicd/bifrost-applier`（`apply_manifest` 的执行者） | – | – | – | 对这份对象只有 `get`；`bifrost-applier-cicd` 只管 Pipeline / Task / Trigger | 写不了这份对象（字段管理者里也没有它）。但它能改检查任务和流水线的定义；`apply_manifest` 到 `cicd` 是 C 级，要批 |
| Argo `argocd-application-controller` | ✓ | ✓ | ✓ | ClusterRoleBinding → `*` / `*` / `*` | 只能经 Application。AppProject `bifrost` 的目的地是六个命名空间（Trade 和平台各两个、`research`、`data`），不含 `cicd`，集群级只许 `Namespace`，所以推 `main` 够不着这份对象 |
| Argo `argocd-server` | ✓ | ✓ | ✓ | `cicd` 里的 Role，加 ClusterRole（对 `*` 有 `delete` / `get` / `patch`） | 要 Argo 自己的登录；平台的动作不经过它 |
| 系统组件：`cnpg-manager`、`kube-prometheus-stack-operator`、`tekton-triggers-controller`、`tekton-triggers-webhook`（全集群 ConfigMap 的增删改）；`helm-traefik`、`helm-traefik-crd`（cluster-admin）；垃圾回收器、命名空间控制器（删）；`root-ca-cert-publisher`（建、改） | 各异 | 各异 | 各异 | ClusterRoleBinding | 够不着：平台起的 Job 和 Pod 只能用白名单里的账号（准入策略 `bifrost-platform-job-sa`），`kube-system` 和 `cicd` 还整个被拒（`k8s/overlays/platform-prod/config/actuation-policy.yaml` 的 `deny`） |
| Owner 的管理员身份（假定是 k3s 默认的组 `system:masters`，他的 kubeconfig 没有读） | ✓ | ✓ | ✓ | `cluster-admin` | `owner_run_command` 是 D 级，平台不执行，由他自己跑 |

在 `cicd` 里起 Pod 的路（一个 Pod 可以用这个命名空间里任何一个账号）：直接建 Pod 的只有 `tekton-pipelines-controller`、`argocd-application-controller`、`cnpg-manager` 和两个 helm 账号。经 run：PROD 平台（准入限三个账号、具名引用、不许内联）；`tekton-trigger`（准入的匹配条件里没有它，TD-272 未还；留存的 502 个 PipelineRun 里有 27 个是内联规格，跑在 `default` 下）。

### 1.2 连带量到的五件事

1. **检查任务的程序在同一张表里。** `bifrost-release-freeze-check` 的程序和 schema 放在 ConfigMap `cicd/bifrost-release-freeze-check`；上表前三行的账号都能改它。同样处境的还有 applier 的检查程序 `bifrost-apply-manifest-check` 和 `bifrost-actuation-policy`，不归本文。
2. **PROD 平台账号离集群管理员只差一次 patch**（已记成 TD-314）。ClusterRole `bifrost-platform-workload-actuator`（`apps/deployments` 的 `update` / `patch`，没有名字限制）绑在 11 个命名空间上，其中有 `cicd` 和 `monitoring`；`cicd` 里的 Deployment 包括 `argocd-server`；没有准入策略限制这个账号改 Pod 模板。读出来的，没有试。
3. **同一类的第二条路**（已追加进 TD-293）。上表前三行那份「`cicd` 里任意 ConfigMap」的写权限也盖住 Argo 自己的配置：`argocd-cm`、`argocd-rbac-cm`、`argocd-cmd-params-cm` 都在 `cicd`（实测存在）。改它们能不能拿到 Argo 的管理权，没有试，也不该试。
4. **读旧对象的是四处，不是三处**：PROD 平台、STG 平台、Task `bifrost-release-freeze-check`，还有 Task `bifrost-release-window` 的 `freeze` 步骤（`k8s/cicd/tekton/task-release-window.yaml:187`，集群上同名任务也带这一步；它把 404 当未冻结）。
5. 其余现状：两份记忆（`platform-state-release-policy-freeze`，PROD、STG 各一份）都是 `{"frozen_at":""}`；策略对象 `cicd/bifrost-release-policy` 的 `data` 是空的；18 条流水线里 13 条发布类的唯一根任务是 `freeze-check`；留存的 run 只用过 `default` 和 `bifrost-applier` 两个账号，`cicd` 里一共 12 个 ServiceAccount；控制面只有一台（`ubt-k3s-01`，control-plane 兼 etcd），apiserver 是 v1.35.5+k3s1，Tekton 是 v1.6.0；没有名字带 `bifrost` 的 CRD。此刻没有未完成的 TaskRun；挂着旧程序 ConfigMap 的 Pod 有 8 个，都已结束。集群上的旧检查程序和主线的 `scripts/release/freeze_decision.py`（`239f100`）逐字节相同。

### 1.3 防谁，不防谁

- **L1　用平台接口的 Agent 或线程**（operator 令牌，B 级动作不经审批）。
- **L2　以平台账号身份运行的代码**：平台自己写错、两个诚实进程的竞态、漏读、重启，以及被换掉的平台进程。
- **L3　能改准入策略、它的绑定或 CRD，或者能冒充别人的身份**：`system:masters`、`argocd-application-controller`、`argocd-server`、`helm-traefik`、`helm-traefik-crd`，加垃圾回收器和命名空间控制器这两个系统控制器的账号（附录）。

**交付的保证覆盖**：L1 的任何接口调用；L2 里的写错、竞态、漏读、重启；L3 以外任何身份的任何请求，包括手写的对象，包括垃圾回收器的正常工作。**不覆盖 L3**：它本来就能直接发布、改流水线、改 RBAC，冻结拦不住它（第 9 节 D1）。**平台账号自己的权限**（写错的、或被换掉的平台代码用的就是它）：按 1.2 第 2、3 条，今天这个账号——连同 `cicd/tekton-deliver`——有两条读得出来的路升到 L3。两条都是打开 `create` 的前置：TD-314 和 TD-293 的收窄都排在第 7 节步 8，各带自己的只读核对。封住之后，这些账号在冻结记录上能做的只有建和读。声称到这里为止：有没有第三条借用的路，没有清点过（那是写入矩阵的事），所以本文不写「平台账号无论如何都解不开」。

## 2. 诊断的检验，和方案比较

### 2.1 六个发现各自来自哪里

| | 发现 | 要直接写对象吗 | 根源 |
|---|---|---|---|
| F1（复核 79） | 同一秒先后冻结 A、B，A 的解冻签名解开 B | 否 | 一个槽位先后装多次冻结，身份会重复 |
| F2（79） | 解冻验的是 A，写入盖掉了刚写上的 B | 否 | 对同一个槽位先读、再判、再写 |
| F3（82） | 记忆里有编号历史时，后来没有编号的冻结被忽略；放回 A 的已解冻对象就放行 | 是 | 记忆给事件排序；旧值可以放回 |
| F4（82） | break-glass 清掉计数，新冻结复用旧编号 | 否 | 身份从记忆派生，记忆可以被清 |
| F5（86） | 没读到 B 的平台，接受放回去的 A 的已解冻对象 | 是 | 进程没看过；旧值可以放回 |
| F6（86） | 合并两份记忆，把没解开的 B 记成「更早」 | 否 | 两份记忆之间没有因果先后 |

统筹方的诊断是「门凭一个进程记得自己看到过什么，来判断一个可变的对象」。检验结果：对 F3–F6 成立。F1、F2 和记忆无关，它们来自那句话的后半句——对象是可变的，而且「已解冻」是写在上面的一个值。记忆是为了补 F1、F2 这一类才加的，然后带来 F3–F6。所以要去掉的是那个值，不只是记忆。

### 2.2 方案

| | 靠构造成立的是什么 | 谁来执行 | Owner 要亲手应用 | 普通权限的 Agent 还能做什么 | 新进程 / 什么都没看过 / 两个进程抢 | 代价 |
|---|---|---|---|---|---|---|
| **A　只增记录，签名解冻**（ConfigMap，专用命名空间） | 冻结 ⇔ 有一条冻结记录缺少「验得过、点名它」的解冻记录；每次 LIST 现算 | RBAC；准入；每个门各自验签 | 命名空间、RBAC、准入策略、带验签工具和公钥的检查任务 | 多建冻结；建一条验不过的「解冻」（按冻结算） | 都是现读。但删掉一条冻结记录同样是解冻：A 有两条解冻的路，删除那条就是 B | 检查任务要会验 SSHSIG：现在的镜像是 `python:3.11-slim-bookworm`（实测），Python 标准库没有 Ed25519，镜像里有没有 `ssh-keygen` 未测。锚在平台和检查任务两处。另有两处特判：每个命名空间天生有 `kube-root-ca.crt`；命名空间不存在时 LIST 返回 200 和空表（都是实测） |
| **B　只建不改的记录，Owner 删除即解冻**（ConfigMap，专用命名空间） | 冻结 ⇔ 有记录；解冻 ⇔ 一次 DELETE。没有签名可以重放 | RBAC；准入；一个哨兵对象（防「命名空间没了读成空表」） | 命名空间、RBAC、准入策略、哨兵、检查任务 | 只能多建冻结 | 没有状态可缺 | 哨兵和 `kube-root-ca.crt` 两处特判进了判定规则 |
| **C　一个对象，里面一条哈希链** | 链内的先后不能改 | 每个门校验链 | RBAC | 把整份对象换回链的一个更短的前缀——那仍是一条合法的链 | 要发现回退，读的一方得记得见过的链头：又是每个进程的记忆（F5、F6） | 不可行 |
| **D　留着记忆，继续修** | 没有 | 平台代码 | 无 | 同今天 | 复核 86：本地的观察历史证明不了没有漏读；两份记忆没有因果序，合并规则无论怎么定，总有一种交错让没解开的那次输掉，或者让系统永远拒绝 | 三轮、六个发现，每一轮的修复都是下一轮发现的来源。不可行 |
| **E　B 的形状，放在专用的集群级资源类型上**（已定，第 9 节 D3） | 同 B。类型不存在时 LIST 不是 200；没有 `kube-root-ca.crt`；现有那些「全集群 ConfigMap」账号对新类型没有权限（附录） | 一条准入策略写全生命周期；RBAC 第二层；CRD 校验内容 | 一个 CRD、一条准入策略和绑定、两个 ClusterRole 和绑定、检查任务 | 只能多建冻结 | 没有状态可缺 | 一个没有控制器的 CRD；平台多一种读法。判定规则里没有哨兵和特判 |

B 和 E 相比 A 少掉的三样：(1) 解冻不能由 Agent 或平台转交，必须有人拿着能删除的集群凭证——今天的签名也是在他的终端上、用他磁盘上的密钥做的，10-11 那次演练最后就是他用管理员凭证手工解开的；(2) 没有一份可以离线验证的解冻凭据，留痕改由 `release.sh` 的发布日志承担；(3) 「人在场」：签名密钥如果带口令，签一次要他输入，kubeconfig 没有（密钥有没有口令，未测）。换来的：TD-310 最初那次事故（冻得上、解不开，因为平台里没有锚）不再可能；检查任务不需要任何密码学；规则短到两份实现没有地方分叉。

## 3. 设计

### 3.1 对象，和它的一生

**类型**（`k8s/release-freeze/crd.yaml`）：CRD `freezes.release.bifrost.io`，组 `release.bifrost.io`，`scope: Cluster`，一个版本 `v1`，没有子资源，没有控制器。根上一条 CEL 规则要求名字匹配 `^freeze-[0-9a-f]{32}$`；根 schema `required: ["spec"]`，没有 `spec` 的对象由 apiserver 拒绝。`spec` 必填 `who`（1–128 字符）、`reason`（1–500；「修订 2026-10-12 之二」改成 1–350）、`at`（`date-time`；「修订 2026-10-12 之二」另外写死成 20 个字符，两处的理由都在下一段），可选 `via`（至多 64，哪一个平台实例写的）。这四个字段只给人看，判定不读它们；名字里的 32 位十六进制由 `crypto/rand` 抽出，只为了两次冻结不撞名。静态测试的负例包括拿掉根上这个 `required`。「修订 2026-10-12」schema 里不写 `additionalProperties`。片 1 的 `k8s/release-freeze/crd.yaml:28` 在 `spec` 下把它设成了 `false`，和 `properties` 并排；这一行本文从没有要过，测试也不看它。Kubernetes 对 CRD 的 schema 有两条限制——`additionalProperties` 不能设成 `false`，也不能和 `properties` 同时出现（凭文档写的，没有在任何 apiserver 上试）——所以它很可能让步 1 当场被拒。处理：S2 之前的准备片去掉这一行并加一条测试（第 8 节）；步 0 的第一条集群命令就是这份 CRD 的服务端试算，被拒不花任何代价（7.1 的 0-1）。

「修订 2026-10-12 之二」**字段的上限，和为什么是这几个数。** `reason` 的上限从 500 改成 350。`at` 在 `date-time` 之外写死宽度：`minLength` 和 `maxLength` 都是 20，`pattern` 是 `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$`（UTC，到秒，年份四位）。`who`（128）和 `via`（64）不变。这样定是为了一句话成立：**清单是空的时候建一条记录，之后的 LIST 装得进 4096 字节**（3.2 的上限）。算术如下。CRD 的 `maxLength` 数的是码点（`k8s.io/kube-openapi` 的 `pkg/validation/validate/values.go:104–110`，`utf8.RuneCount`）。apiserver 写 JSON 时一个码点最多占 6 个字节：`<`、`>`、`&` 写成 `<` 这样的六个字节是实测 10-12；控制字符、U+2028、U+2029 也是六个字节，是照 Go `encoding/json` 的写法假定的；别的码点原样写，最多 4 个字节。三个字段最坏是 6 ×（128 + 350 + 64）= 6 × 542 = 3,252 字节。这一条里其余的全部——键、引号、名字、UID、两个时间、`at` 的 20 个字节、`managedFields`——由 E = 600 盖住（3.4；按实测的信封算是 549 到 551，条目自己的 `resourceVersion` 从今天的 8 位长到 32 位也只多 24）。空清单最多 150 字节（今天 126；`resourceVersion` 长到 L 允许的 32 位时正好 150）。150 + 600 + 3,252 = 4,002 ≤ 4,096，余 94。`reason` 留在 500 时是 150 + 600 + 6 × 692 = 4,902，装不下；`at` 不写死宽度时，`date-time` 允许任意多位的小数秒，E 就没有上界。没有写进 schema 的 `spec` 字段由 apiserver 裁掉（结构化 schema 的默认行为，假定），撑不大记录；标签和注解在建的时候被准入拒绝。这句话管的是经平台的函数建的、或者用 `kubectl create` 建的记录——两者的 `managedFields` 是量过的两种形状。自己挑一个很长的字段管理者名字去建的人可以超出 E（能建的只有 Owner、L3 和打开 `create` 之后的平台）；结果和下面的并发一样，是读不到，不是放行。**这句话不管并发**：几个调用同时在空清单上各建一条，每一条都装得下，合起来可以超过 4096。那以后门一直不放行、印的是读不到，直到 Owner 删掉几条——失败关闭，而且看得见（D8）。这两处改动由准备片做，连同一条从 schema 重算这道算术的测试（第 8 节）；片 1 钉着旧上限的测试（`scripts/release/test_freeze_manifests.py:195–201`）在同一个提交里改。

**一生**（`k8s/release-freeze/admission.yaml`）：

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata: {name: bifrost-release-records}
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - {apiGroups: ["release.bifrost.io"], apiVersions: ["*"], scope: "*", operations: ["CREATE", "UPDATE", "DELETE"],
         resources: ["freezes", "freezes/*", "policies", "policies/*"]}
  validations:
    - expression: "request.operation != 'UPDATE'"
      message: "a release record is never updated"
    - expression: "request.operation != 'CREATE' || !(has(object.metadata.ownerReferences) || has(object.metadata.finalizers) || has(object.metadata.labels) || has(object.metadata.annotations) || has(object.metadata.generateName))"
      message: "a release record carries a name and no other metadata"
    - expression: "request.operation != 'DELETE' || (request.userInfo.username == 'OWNER_USERNAME' && (!has(request.options.propagationPolicy) || request.options.propagationPolicy == 'Background'))"
      message: "only the Owner removes a release record, with a plain delete"
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: {name: bifrost-release-records}
spec: {policyName: bifrost-release-records, validationActions: [Deny]}
```

**这条策略说的三句话。** 建：客户端能写的元数据只有名字，不许带属主引用、finalizer、标签、注解、`generateName`（平台和手写都用 `create`，不用会加注解的 `apply`）；`uid`、时间、`managedFields` 是服务端写的，不在此列。改：一律不放行，包括只改元数据和任何子资源。删：只放行 Owner 那一个用户名，而且只能是普通删除——前台或孤儿式删除会由删除处理自己给对象加上 finalizer，之后摘它要一次「改」，而「改」不放行；这样的记录一直留在 LIST 里，结果是持续冻结（恢复办法见 3.4 末段）。规则只看 `propagationPolicy`，别的途径（例如已废弃的 `orphanDependents`，假定仍被接受）它不管，所以本文不写「不会卡住」。垃圾回收器的删被拒之后通常会重试，重试多少次也不会因此得到删除权。`policies` 是第 4 节的策略记录，同一条规则。

**在这个集群上能确认到哪一步。** 实测：`admissionregistration.k8s.io/v1` 已服务；现有 6 条策略都是 v1、`failurePolicy: Fail`、绑定 `Deny`，规则里用了 `request.userInfo.username`（服务账号写成 `system:serviceaccount:<命名空间>:<名字>`）和 `oldObject`，它们的类型检查认得 Tekton 这类自定义资源的字段。**没有一条现有策略匹配 DELETE，也没有一条管集群级的自定义资源**，这两点在本集群上没有先例。假定（v1 的成文行为，第 7 节步 2–3 逐条证明）：DELETE 时 `object` 为空、`oldObject` 是被删的对象；`deletecollection` 对每个对象各过一次同样的规则；集群级资源不会被 `namespaceSelector` 跳过；准入不管授权是怎么通过的，`system:masters`、垃圾回收器、命名空间控制器、Argo、Helm 和任何通配符角色的请求都要过；`request.options` 在规则里读得到。最后一条若在本版本写不出来，步 2 当场暴露（策略编译不过，按 `Fail` 全拒，合规的建也被拒）；那就去掉这半句，只靠工具固定用普通删除，损失的是可用性，不是安全：卡在删除中的记录仍然算冻结。

**策略做不到的。** 它管不了对它自己、它的绑定和 CRD 的修改（这类请求不过准入策略）；删 CRD 时 apiserver 清掉全部实例，不经准入（假定）；门看不见策略在不在。所以：能改这三样的身份就是 L3；策略有没有绑上、是不是真的在拒，由使用前的拒绝探针证明（第 7 节）：绑定不在的时候，策略连同它的 `failurePolicy: Fail` 什么都不拦；策略对象「看着正常」——`observedGeneration` 等于 `generation`、`expressionWarnings` 为空——任何时候都不能代替一次真的被拒。平时由一条只读的防线盯着——只读身份读得到策略、绑定和 CRD（实测有这三项读权限），比对集群上的对象和仓库文件一致；它只能发现对象被动过，证明不了还在拒。**规则里的 Owner 是谁：** 用户名认的是一份凭证，不是一个人——拿着同一张管理员证书的每一个持有者，规则都当作 Owner。他的 kubeconfig 我们没有读。他自己跑一条 `kubectl --kubeconfig <他的> auth whoami`（本集群支持这条命令，只读身份实测过），用户名和组都记下来，用户名填到 `OWNER_USERNAME` 的位置上；k3s 默认是 `system:admin`（假定）。「修订 2026-10-12」（D9；原文是「用户名填进 `OWNER_USERNAME`，文件在那之后才定稿」）填在仓库之外：仓库里的 `admission.yaml` 一直留着占位符，片 1 的测试照旧钉着它；当天由它渲染出一份填好的副本，先看差异——正好是带引号的占位符所在的两行规则——再应用这份副本，填好的文件不进 `main`（7.1 的 0-4、0-5）。上面那条只读防线因此比的是：集群上两条策略的表达式，等于仓库文件把 `'OWNER_USERNAME'` 换成同一个带引号的字面量之后的样子；那个字面量对不对，对照步 0 记下的用户名。同时核对两处来源：还有什么能以这个用户名通过认证（同一张证书的别的副本、另签的同名证书、令牌文件——看 k3s 服务端的认证配置，只读身份读不到）；谁被授予了 `impersonate`（今天是四个身份，附录）。今天这张管理员证书的持有者都算 L3，不在防范之内（D1）；将来换成专用身份（D4），这几样重新核对一遍。

| ClusterRole（都不带 `aggregate-to-*` 标签） | 对 `freezes.release.bifrost.io` 的动词 | 绑定给 |
|---|---|---|
| `bifrost-release-freeze-list` | `list` | 组 `system:serviceaccounts:cicd`（所有流水线账号，免得以后换账号时得到 403、全部被拒，10-11 发生过一次）；两个平台账号；`bifrost-access/bifrost-agent` |
| `bifrost-release-freeze-create` | `create` | 两个平台账号。这条绑定是「冻结」的开关：没应用它，平台建不出记录（第 7 节步 9 才应用） |

文件放 `k8s/release-freeze/`：不在 applier 的允许前缀里，也不在任何 Argo 应用的路径下，只能由 Owner 应用；这个目录和检查任务一起加进 `agent-config/release-policy/paths.json` 的 `no_trust_anchor_change`。「修订 2026-10-12」「检查任务」指 `k8s/cicd/tekton/task-release-freeze-check.yaml`。主线的路径表里有 `k8s/release-freeze/**` 和 `k8s/cicd/tekton/task-release-window.yaml`（`paths.json:151`、`:153`），缺的正是这个文件——步 5 之后装着门的程序的就是它。由准备片补上，并加一条测试：`k8s/release-freeze/` 下的每个文件和这两个 Task 文件，都被路径表盖住（第 8 节）。

「修订 2026-10-12」（实测 10-12，回答第 7 节步 4 和附录对不上的地方）`cicd` 的 12 个 ServiceAccount 是 `argocd-application-controller`、`argocd-applicationset-controller`、`argocd-dex-server`、`argocd-notifications-controller`、`argocd-redis`、`argocd-repo-server`、`argocd-server`、`bifrost-applier`、`default`、`tekton-deliver`、`tekton-pipelinerun-ttl`、`tekton-trigger`。其中两个凭通配符规则对新类型有 `list` 以外的动词：`argocd-application-controller`（`*`）、`argocd-server`（`get`、`patch`、`delete`）。上表的 RBAC 管不到它们，它们就是 1.3 的 L3；拦住它们改和删一条记录的是本节的准入策略，第 7 节步 3 对这两个账号各试一遍。它们建一条合规的记录是放行的——那只会收紧。其余 10 个，加上两个平台账号和只读身份，应用 `rbac-list.yaml` 之后对新类型只有 `list`。

### 3.2 一次完整、成功的 LIST

每一道门只做一件事：只有 `clear` 才放行。`frozen` 和 `unreadable` 都是拒绝；报哪一个、列出哪些记录，是给人看的，两份实现不必一致。跨实现的要求只有一条：对每一份应答的二进制判定相同。调用方把不是 `clear` 的结果同样当拒绝（B 级也是；今天的 `FreezeSet` 读失败时返回 false，主线 `api/internal/releasepolicy/engine.go:238–245`，随后 `server/release_policy_wire.go:146–166` 放行，第 9 节 D6 要改，S3 验收这一入口）。可以重读，放行只来自一次 `clear`。

`clear` ⇔ 传输每一条都成立，且正文的字节属于 L。L 只有下面这些产生式。实现里的识别器和测试里的识别器都从这里推导，本文不另写扫描器，也不另写一套正则。判定不调用通用 JSON：Python 不用 `json.loads`、`parse_int`、`parse_float`，Go 不用 `encoding/json`。不在 L 里就不是 `clear`。

W = 0x20、0x09、0x0A、0x0D 的零次或多次。q("…") 的引号是记号，s 是记号之间的 ASCII 字节；q(d) 的 s 是 d 推导出的字节；q(s) = 0x22、s 的每个字节、0x22。d = 0x30–0x39 的 1 到 32 个。结束 = 输入没有剩余字节。竖线隔开备选。
R = q("resourceVersion") W ":" W q(d)。C = q("continue") W ":" W q("")。
meta = "{" W R W "}" | "{" W C W "," W R W "}" | "{" W R W "," W C W "}"。
m = W q("apiVersion") W ":" W q("release.bifrost.io/v1") | W q("kind") W ":" W q("FreezeList") | W q("metadata") W ":" W meta | W q("items") W ":" W "[" W "]"。
top = "{" m W "," m W "," m W "," m W "}"，且四个 m 各用 m 的不同备选、四种备选都出现一次。L = W top W 结束。

产生式 d 是收窄（API 称该字段不透明），对不上 L 就不是 `clear`，失败关闭，由第 7 节步 4 的真读抓住。实测 2026-10-11，只读身份 `system:serviceaccount:bifrost-access:bifrost-agent`，apiserver `v1.35.5+k3s1`，`kubectl get --raw /apis/tekton.dev/v1/namespaces/kube-system/pipelines`：`Content-Type: application/json`，`Content-Length: 120`（含尾随 LF），无空格，正文 `{"apiVersion":"tekton.dev/v1","items":[],"kind":"PipelineList","metadata":{"continue":"","resourceVersion":"84135567"}}`。两个字面量换成冻结类型之后，整段（含尾随 LF）是 L 的句子。同一次 `kubectl get --raw /api/v1/namespaces` 里项的 `metadata.uid` 是小写 UUID（3.4 的模式用它）。

传输，每一条都是 `clear` 的条件，失败就是不 `clear`。恰好一次 GET，源 `https://kubernetes.default.svc`（端口 443），路径 `/apis/release.bifrost.io/v1/freezes`，查询为空，都不取自环境变量。两侧只使用 HTTP/1.1。Go：`TLSClientConfig.NextProtos` 只有 `http/1.1`，`ForceAttemptHTTP2 = false`，`TLSNextProto` 是空的非 nil map；测试断言请求行和 `Proto` 都是 `HTTP/1.1`，对端只出 h2 时不 `clear`。Python 只用 `http.client`（标准库没有 HTTP/2），同一测试看请求行。TLS 用该 Pod 的 `/var/run/secrets/kubernetes.io/serviceaccount/ca.crt` 校验证书链，主机名 / SAN 必须是 `kubernetes.default.svc`；令牌的 audience 只认证调用方。同一 CA、错误主机名 → 不 `clear`。实测（对 `192.168.10.73:6443` 握手，未读凭据文件）：SAN 含 `DNS:kubernetes.default.svc`，签发者 `CN=k3s-server-ca@1781402855`；`default/kubernetes` 是 `10.43.0.1:443`。Pod 里的 CA 文件是不是这个签发者，不在这里假定，由第 7 节步 4 的同一次读留下。请求头是 `Accept: application/json` 和 `Accept-Encoding: identity`。`Content-Encoding`：两侧都在读正文之前看响应头，有这个头就不是 `clear`，不解开。Go `DisableCompression = true`。不跟随重定向（3xx 不发第二次请求），不用环境变量里的代理。应答的字节——状态行、头部行、分帧——必须属于下一段的 H，不在 H 里就不是 `clear`。两侧的读函数都从拨出的连接上自己按字节读，这条路上不用会放宽写法的库函数：Python 不用 `http.client` 的解析、`int()`、`str.strip()`；Go 不用 `Client.Do`、`strconv.Atoi`、`strconv.ParseInt`、`strings.TrimSpace`、`strings.EqualFold`。零块之后直接断开不算读完（Python 的 `http.client` 自己不拒这种情形）。连接、响应头和正文共用 10 秒，从发起连接算到正文读完，不按单次套接字操作重置。正文超过 4096 字节不是 `clear`。传输向量两边都跑，只比二进制：带 `Content-Encoding: gzip`（正文哪怕碰巧在 L）、截断的 `Content-Length`、没有最后一块的 chunked、有零块而缺结尾空行的 chunked（复核 104；在目标的 Python 3.11 上也要跑）、正常结束且正文在 L 的 chunked（必须 `clear`）、100 / 102 / 103 之后 200 且正文在 L（必须 `clear`）、101、慢速滴流超过 10 秒、正文 4097 字节、连接阶段或响应头阶段拖满 10 秒。

应答的语言 H（第一片第 2 轮停线后补，2026-10-11）。此前只有正文有产生式，头部和分帧只有描述；两份实现各用语言自带的函数去读，统筹方造的 220 份原始应答里 41 份的二进制判定不同（一侧收下 `Content-Length: 1_26`、没有冒号的头部行、`0x7e` 的块长、用单个 LF 收束的尾部；另一侧收下名字后面带 0xA0 的 `Content-Encoding`）。H 只有下面这些产生式，记号同 L。CRLF = 0x0D 0x0A，SP = 0x20，HTAB = 0x09，DIGIT = 0x30–0x39，HEX = DIGIT、0x41–0x46、0x61–0x66，tchar = DIGIT、0x41–0x5A、0x61–0x7A 和 ``!#$%&'*+-.^_`|~`` 这 15 个字节，ftext = HTAB、0x20–0x7E。

行 = 不含 0x0A 的若干字节后跟 CRLF，连 CRLF 最多 1024 字节；下面每个以 CRLF 结尾的产生式都是一行。
status(c) = "HTTP/1.1" SP c CRLF | "HTTP/1.1" SP c SP ftext* CRLF，c 是三个 DIGIT。
field = tchar+ ":" ftext* CRLF。名字是冒号前的字节，比较时只把 0x41–0x5A 折成小写；值是冒号后的字节去掉两端的 SP 和 HTAB。
head(c) = status(c) field{0,64} CRLF，其中没有名字是 `content-encoding` 的 field。
response = ( head("100") | head("102") | head("103") ){0,8} head("200") body。
body 由 head("200") 的 field 决定，只有两种：
(a) 没有名字是 `transfer-encoding` 的 field，名字是 `content-length` 的 field 恰好一个，值是 1 到 4 个 DIGIT，十进制值 n ≤ 4096：body 是紧跟的恰好 n 个字节，正文就是这 n 个字节。
(b) 没有 `content-length`，`transfer-encoding` 恰好一个，值把 0x41–0x5A 折成小写后是 `chunked`：body = chunk* last trailer，chunk = size CRLF data CRLF（size 是 1 到 4 个 HEX、十六进制值 s ≥ 1，data 恰好 s 个字节），last = 1 到 4 个 0x30 后跟 CRLF，trailer = field{0,64} CRLF 且其中没有名字是 `content-encoding`、`content-length`、`transfer-encoding` 的；正文是各 data 相接，总长 ≤ 4096。没有 chunk 扩展。

`clear` 的传输条件里属于字节的这一部分就是：读到的字节以 H 的一个 response 开头，并且它的正文属于 L。response 之后的字节不读。读到 response 的最后一个字节之前连接结束或超过 10 秒，不是 `clear`。10 秒是一个绝对时刻，从发起连接算起：每一次底层读取（每一次 `recv` / `Read`）之前都按到这个时刻的剩余时间设超时，不是每次高层读取之前设一次——带缓冲的文件对象一次读会做多次底层读取，各自重新计时；判定为 `clear` 之后、返回之前，再核对一次没有超过这个时刻（复核 107：头立即到、正文的第一个字节第 6 秒到、其余第 12 秒到，Python 在第 12 秒答 `clear`，Go 在第 10 秒拒绝）。其余各条（一次 GET、源和路径、TLS、不跟随重定向、不用代理、一个总期限）照本段原文。这是收窄：RFC 9112 允许的 obs-fold、chunk 扩展、值里的 0x80–0xFF、`Transfer-Encoding` 与 `Content-Length` 并存、`gzip, chunked`、超过 1024 字节的行，在这里都不是 `clear`，失败关闭，由第 7 节步 4 的真读抓住（实测的那份应答只有 `Content-Type`、`Content-Length` 等普通头部，属于 H）。

测试：一份共享的原始应答向量 `freeze_http_vectors.json`，两个仓库字节相同、摘要写成常量。期望值由一个只在测试里用的识别器给出，它照上面的产生式写（按行的正则加分帧），不照任何一份实现写；文件必须等于它重新生成的结果。两份实现各自把每一条向量的字节交给自己的读函数，二进制判定必须等于期望值。向量至少含：统筹方第 2 轮的 220 份；每条产生式放宽一处的近失（符号、下划线、0x 前缀、两端的 0xA0 或 0x1C、没有冒号、名字里的非 tchar、值里的非 ftext、单个 LF、chunk 扩展、两个长度、长度与 chunked 并存、别的传输编码、trailer 里的分帧头部）；每个界限的两侧（1024 / 1025 字节的行，64 / 65 个 field，8 / 9 个临时应答，4 / 5 位 DIGIT，4 / 5 位 HEX，4096 / 4097 字节）。种错清单两边各含：上面每个界限放宽一格、每条近失对应的那条规则去掉。种错算被拦住，只在点名的测试确实失败时成立；编译不过或选不中测试不算。

同一份文件另有两组（第 3 轮复核 107 之后补）。时序：同样的字节、不同的送达时刻——一组「第几毫秒，哪些字节」的安排和一个预算，期望值是「这些字节是 `clear` 的应答，并且 response 的最后一个字节在预算之前送达」。两份实现都在会执行期限的内存连接上跑（Go `net.Pipe`，Python `socket.socketpair`），不联网。至少含：头快而正文的第一个字节在 0.6 个预算、其余在 1.2 个预算；只差最后一个正文字节；chunked 只差结尾的 CRLF；trailer 慢；1.2 个预算之前什么都没有；逐字节滴流；应答之后的字节迟到（必须 `clear`，并且不等它）。每条安排的关键时刻离预算至少 0.2 个预算，答复不得晚于预算之后 250 毫秒。字节类别：合法应答的一个位置上依次放 256 种字节，期望值是识别器给出的 256 位掩码；位置覆盖状态行、头部行、长度、传输编码、分块、trailer、临时应答里的每一类语法字节（复核 107 另植的「值里多放行 0x81」当时没有测试拦住）。

种错的运行器先在不种错的副本上跑点名的测试并要求通过，再种错：副本带上测试数据，放在测试找得到兄弟仓库的位置（第 3 轮 Go 一侧的副本没有带测试数据，新加的种错是因为读不到向量文件而失败的）。针对 H 的每一条种错写明它要翻转的那份应答的名字，失败信息里必须出现这个名字。被禁止的行为——第五个成员、重复的 `resourceVersion`、跟随重定向、按次计时——只存在于种错的替换文本里，生产代码不带。

可恢复的失败都返回「不是 `clear`」，不抛给调用方：Python 接住 `Exception`；Go 接住 error，并在调用读函数的那个 goroutine 里 `recover`。接不住的结束进程，不记成一次返回了 `unreadable` 的读：Python 的 `BaseException`（例如 `KeyboardInterrupt`）、Go 的运行时致命错误、别的 goroutine 里的 panic（含 HTTP 客户端自己拉起的）、进程被杀。调用方把「没有答 `clear`」当拒绝，包括进程没回来。Tekton：没有输出、非 0 退出，或没有退出（超时、被杀），都不放行；只有退出码 0 且第一行是下面 `clear` 那一句才放行。平台：`Decide`、`Evaluate` 和 B 级只在读函数返回 `clear` 时放行；没有把判定交回来（超时、进程没了）同样不放行。panic 的 `recover` 在读函数里，不在更外层。多种故障不必选同一个 token，二进制没有 token。注入测试只覆盖可恢复的那一类（传输错误、超时、`Exception`、调用 goroutine 的 panic），断言不逃逸且不是 `clear`。S2、S3 怎样验收无输出、非 0、超时和可恢复失败，见第 8 节。

测试要求一个独立写成的识别器，照上面的产生式写，不照实现写。种子 `310101`，共 678 条。属于 L 的 252 条：`top` 的 24 种选法 × `meta` 的三支 × d 的长度 1 和 32（一个 `0x31`，或 32 个 `0x31`）= 144 条紧凑正文；另对 3.2 那份换成冻结字面量、d 长度为 1 的骨架，产生式里每一处 W 各插入 `0x20`、`0x09`、`0x0A`、`0x0D` 之一（27 处，108 条）。近失 170 条，底是 118 字节的紧凑骨架：每字节换成 `0xFF`（118），`top` 五个槽和 `meta` 三个槽各加一个带逗号的 `"z":""`（8），33 位数字（1），6 个键和 4 个字符串值的引号内各插入一个 `\`（10），重复四个顶层键名和 `meta` 里两个键名（6），27 处各插入 `A`（27）。随机 256 条：`s ← 310101`，每字节 `s ← (1103515245·s + 12345) mod 2^31`，取 `(s >> 16) mod 256`，长度 0 到 255 各一条，连续取、不重置。三方每条一致；252 条必须接受；该识别器拒绝的不得答 `clear`。Python 跑全部，不是抽样。手写向量另含这些全文，三方都不得答 `clear`，不计入 678：`{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1","resourceVersion":"2"},"items":[]}`；`{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"continue":"","continue":""},"items":[]}`（两份 `continue`，即 `continue` 然后 `continue`）；`{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"continue":"","resourceVersion":"1","continue":""},"items":[]}`（两份 `continue`，三个成员）；`{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"resourceVersion":"1","continue":"","resourceVersion":"2"},"items":[]}`（三个成员）；`{"apiVersion":"release.bifrost.io/v1","kind":"FreezeList","metadata":{"continue":""},"items":[]}`（只有 C）。生成器、穷尽模型、整包分开计时，三次都要在实现报告里各有一行，整包目标见第 6 节。手写向量仍是两份逐字节相同的文件，`scripts/release/freeze_vectors.json` 和 `api/internal/releasefreeze/testdata/freeze_vectors.json`，同一个 SHA-256；兄弟检出在场则逐字节比较，`BIFROST_CI` 已设置而兄弟不在则失败。两边要相同的只有二进制。片 1 的摘要 `a5f19e65ba542bb7de6180462032991c10021467b6642a24dc88ba8ff4f6a3ee`（68 条，26716 字节）对的是旧表，按本轮重生成时文件和两处常量一起换。

不是 `clear` 时，门仍试着列出记录给人看。这层不必精确；这里失败只改显示的词（`unreadable (…)`），不改变拒绝。三句原文：`clear` 印 `未冻结：0 条记录`。`frozen` 印 `拒绝：发布已冻结（<n> 条记录）；解冻由 Owner 删除记录：release.sh unfreeze`，然后按名字排序每条一行 `<name>  who=<…>  at=<…>  reason=<…>`（值里的换行改成空格）。`unreadable` 印 `拒绝：读不到冻结状态（<token>），按冻结处理`。`clear` 且设置了 `PASSED_CUT_AT_PATH` 时，把当前 UTC（RFC 3339，到秒）写入该路径并印成第二行；拒绝时不写。第二行不参与比较。`uid` 和 `via` 不进这两行，交给 3.4；缺了或不是字符串则为空。不用客户端缓存、分页器、informer；这个包不引入 `k8s.io/client-go/tools/cache`、`tools/pager`、`informers`。测试断言实际发出的 URL 和空查询。不带查询的 LIST 是 Kubernetes 定义的「最新」读（假定）；本集群上的新鲜度未测，演练第 ② 步证。

「修订 2026-10-12」**记录多到装不下的时候。** 4096 字节的上限对有记录的 LIST 同样生效，而且是在读取那一层生效（`api/internal/releasefreeze/httplang.go:258–259`、`:289–290`，`scripts/release/freeze_gate.py:683`、`:715`）：超过上限的正文到不了列记录的那一层。这时门不放行（不变，失败关闭），但印的是「读不到冻结状态」，不是记录清单；状态接口的 `freezes` 是空的，`freeze_state` 是 `unreadable`。装得下几条取决于每条记录有多大。信封是实测 10-12 的：空 LIST 120 字节，换成冻结类型的两个字面量是 126 字节；读本集群上真实对象的 `managedFields`，`kubectl-create` 建的每条在字段清单之外占 133 字节，`platform-api` 建的占 131 字节。整条冻结记录未实测（类型还不存在），按这个信封算。apiserver 把 `<`、`>`、`&` 各写成 6 个字节（实测 10-12，读 `cicd` 里 Tekton Task 的原始 LIST：`<`、`>`、`&` 共 330 处，这三个字符原样出现 0 处；控制字符和 U+2028、U+2029 假定也是 6 个字节，没有量）。「修订 2026-10-12 之二」上一版这里按 `reason` 至多 500 算：三个字段都写满这类字符的一条约 4,701 字节，单独一条就超过上限。统筹方因此裁定把字段收短（3.1）。按收短之后的上限：最小的一条（`who`、`reason` 各 1 个字符，没有 `via`）约 533 字节，最多装 7 条；三个字段都写满 ASCII 的一条约 1,093 字节，最多 3 条；都写满中文（每字 3 字节）的一条约 2,177 字节，只装得下 1 条；都写满被写成 6 个字节的字符的一条约 3,803 字节，连空清单是 3,929 字节，仍然装得下；按上界算（E = 600、空清单 150）是 4,002，算术在 3.1。所以「零条的时候最大的一条也装得下」现在由 schema 保证；两条或更多装不装得下仍取决于内容，由 3.4 的规则管。E 是估计：第 7 节步 3 的探针给出第一份真实的数（7.1 的 3-2、3-19），但探针是 `kubectl` 发的；E 在平台自己建出第一条记录时签收（3.4）。清理不受这个上限影响：`release.sh unfreeze` 用 Owner 的凭证经 `kubectl` 列记录，不经过门的读函数。

「修订 2026-10-12」**说明模式。** `freeze_gate.py --explain` 做的是同一次读、同样严格，判定那一行（和 `PASSED_CUT_AT_PATH` 的第二行）原样在最前面，后面多印几行 `explain: 键=值`：Pod 所在的命名空间、请求行、校验过的主机名、用的 CA 文件和里面证书的主体、握手里对端证书的签发者、这个签发者在不在 CA 文件里、判定。不印令牌，不印任何请求头或应答头的值，不印正文。不带这个参数时，程序的输出和退出码与没有这个模式时逐字节相同。它由准备片加（第 8 节），第 7 节步 4 的真读用它留证据。Go 的读函数没有这个入口。

### 3.3 保证是关于一张快照的

- **性质的说法**：一个门的结论只对它读到的那张快照成立。冻结拦住的是「最后一次成功的读发生在记录建成之后」的每一次发布；最后一次读之后才建的冻结，拦不住已经放行的 run。
- **这个窗口有多长**：从检查任务读完，到这条 run 的最后一个有副作用的步骤。实测：留存的成功 run 里，发布类流水线从开始到结束的中位数是 0.5–5 分钟，最长 9.3 分钟（`bifrost-deliver-platform-prod`）；没有一条流水线自己设超时，上限是 Tekton 默认的 60 分钟。
- **回执要点名在途的 run**：冻结的回答里列出「还没结束、而它的 `freeze-check` 已经成功」的 PipelineRun（平台账号对 run 有读权限，实测）。今天的 `scripts/release/freeze_inflight.py` 只是一张行为表，不做清点；清点在 S4 建，验收见演练第 ⑦ 步。
- **为什么流水线开头的检查是第二次读**：平台在收到请求时读第一次，到 run 真正开始之间可以隔很久（排队、等批准）；检查任务在第一个有副作用的任务之前再读一次。它也是不经平台发起的 run 唯一的一次读；它用的账号和程序都和平台不同。**它要验的**是 3.2 的 `clear`。协议里没有签名，镜像不换（`python:3.11-slim-bookworm`，只用标准库）。程序改成写在 Task 的 `script` 里，不再从 ConfigMap 挂载：`cicd` 里的 Task 只有 applier（C 级，要批）、Tekton 控制器和 L3 能写（实测），1.2 第 1 条随之关闭。测试要求 Task 里的脚本和 `scripts/release/freeze_gate.py` 逐字节相同。Task `bifrost-release-window` 的 `freeze` 步骤删掉。「修订 2026-10-12」这两个文件的写法和来路：检查步骤是 Task 的第一个步骤（`spec.steps[0]`，现网这一步叫 `check`、镜像 `python:3.11-slim-bookworm`、`timeout` 20s，实测 10-12），名字、镜像和 `timeout` 都不变，不加 `onError`；它的 `script` 字段逐字节等于 `freeze_gate.py`。新文件里只有 Task，不再带 ConfigMap `bifrost-release-freeze-check` 那一段；`kubectl apply` 不会删集群上那份 ConfigMap，它留到步 10（步 5 的退路要它在）。两个文件由实现方按一份单独的任务书写在 infra 的分支 `w31/td-310-s2task` 上，从准备片合并之后的 `origin/main` 起（脚本要等于那时的 `freeze_gate.py`），同一个提交里改掉钉着旧样子的测试（`scripts/release/test_freeze_decision.py:309–324`、`scripts/release/test_freeze_manifests.py:76`、`:317`），加上「脚本逐字节相同」「第一步带 `timeout`、没有 `onError`」两条新测试；独立复核在分支上做。当天步 4 通过之后，统筹方把 `main` 快进到复核过的那个提交（7.1 的 5-0），Owner 再应用。在那之前它只在分支上：applier 对分支上的提交只能试算，往 `cicd` 应用是 C 级，而 C 级的应用要求提交在 `main` 的历史里（`api/internal/workactions/service.go:100`、`k8s/cicd/tekton/apply-manifest/pipeline.yaml:146–162`）——这就是「不提前进 applier 能应用的前缀」落到实处的样子。
- **给 W-56 第 4 步的方向**：计划里写的是「设冻结和认领是对同一个对象的比较交换」。记录只增之后改成「先写自己的，再读对方的」：执行方先写下认领，再 LIST 冻结，有记录就撤回；冻结方先建记录，再读认领、写进回执。细节归第 4 步的设计。

### 3.4 平台、`release.sh`、状态接口

**平台**（`api/internal/releasepolicy`）：新增一个只有两个函数的包——读（3.2，S1）和建（POST 一个只带名字和 `spec` 的对象，S3，不在 S1）。`Status`、`Decide`、`Evaluate`、B 级检查都改用它。删掉 `memory.go` 整个文件、`Deps.StatePath`、`evaluateFreeze`、`Unfreeze`、对 `cicd/bifrost-release-freeze` 的全部读写；`POST /api/v1/release-policy/unfreeze` 改成回 410；动作 `release_unfreeze` 从目录和 MCP 工具里去掉。平台对这类对象只发 LIST 和 POST，测试断言。`Freeze` 的做法在下一段（「修订 2026-10-12」）。不再要求有锚。解冻不走平台的任何通道，包括 `owner_run_command` 的 host 执行器：那样平台又成了能放宽的一方。

「修订 2026-10-12」**`Freeze` 怎样建一条记录，什么算建成**（D7、D8。原文是：先 LIST 一次只为数条数，已有 20 条或更多就不再加；读不到也照样往下建；403 和别的错分开报；不重试同一个名字；建成后再 LIST 一次。改掉的是两处：「满 20 条」经门的读函数数不到，换成按字节算的上限，见 3.2；POST 的应答丢了或含糊时原文没有说怎么报。「读不到也照样往下建」留着：冻结是急停，要偏向冻住。这一段在 10-12 当天改过两次，头一次把上限写成条数 N = 7、把读不到写成不建，统筹方随后改回，见 D8。）

1. **先读。** 用门的读函数（3.2）读一次，按读到的走三条路之一：
   - **读不到**（`unreadable`）：照样往下建。这时每个门本来也不放行。
   - **读到零条**（`clear`）：建，不看大小。
   - **读到一条或更多**：算「这次读到的正文的字节数 + 新记录的上界 U」。不超过 4096 就建；超过就不建，报「没有新增：清单满了」。

   不变式：大小只在已有记录的时候才看，所以「因为大小被拒」只发生在至少有一条记录的时候，也就是每个门本来就不放行的时候；这种拒绝不会让一个该冻住的状态冻不住。「修订 2026-10-12 之二」上一版在这里说，这条不变式只靠规则的形状，因为写满 `<`、`>`、`&` 的一条单独就超限。字段收短之后（3.1），零条时建的那一条之后也读得到：「零条不看大小」从「建了可能读不到」变成「建了就读得到」，除非同时还有别人在建。函数自己仍然不在空清单上做任何大小检查，那样会多出一种拒绝急停的理由。它在发请求之前只核对输入合不合 schema——`who`、`reason`、`via` 的码点数，`at` 的范围（第 2 步）——不合就不发请求，报「冻结没有写上」。

   新记录的上界 U = 1 + E + c(`who`) + c(`reason`) + c(`via`)。1 是它前面的逗号。c(s) 是 s 在 apiserver 写出的 JSON 里、引号之内占的字节数，照 Go 的 `encoding/json` 默认写法算（`<`、`>`、`&` 各 6 个字节是实测 10-12 的；其余转义是假定）。E = 600，盖住这一条里其余的全部——键、引号、`at`、元数据和 `managedFields`；按实测的信封算，这部分带 `via` 时是 549 到 551 字节，未实测，步 3 的探针核对（7.1 的 3-19）。为了这一步，读函数在读得到的时候把正文的字节数一并交回；判定不变。

   「修订 2026-10-12 之二」**E 是估计，不是量出来的。** 步 3 的探针用 `--field-manager=platform-api` 建、带着 `via`，为的是让它的信封尽量像平台的请求，但它仍是 `kubectl` 发的。3-19 只能说明估计没有离谱（量到的超过 600 就当场停），不签收。签收在平台自己建出第一条记录的时候，也就是步 10 演练的第 ② 步：记下那时 LIST 的字节数，减去空清单的字节数和三个字段内容的字节数，必须不超过 600。超过就停：撤掉 `create` 的绑定，调大 E，重算 3.1 的算术（余量只有 94 字节，不够就再收短 `reason`）。S3a 的测试不等这一步，它用假服务器覆盖最坏的转义、32 位的 `resourceVersion`、带和不带 `via` 这几个边界。

   这条规则挡不住的（「修订 2026-10-12 之二」改写。上一版的头一种是「零条时建一条单独就超限的记录」；字段收短之后，经平台和 `kubectl create` 都建不出这样的一条）：读不到时的盲建；几个调用同时建——各自读到零条或读不到，各建一条，合起来超过上限。这两种都可能让清单从此读不到。那以后门一直不放行，印的是读不到，直到 Owner 删掉一条或几条（`release.sh unfreeze` 列记录不经过门的读函数，3.2）——失败关闭，而且看得见（D8）。
2. **再建。** 名字用 `crypto/rand` 新抽，一次调用一个名字。恰好发一次 POST，对象只带名字和 `spec`，不带任何条件，客户端库自带的重试关掉——否则一次写上了而应答丢失的 POST 会被重发、得到 409，把「不知道」说成「没写上」。POST 经平台现有的 Kubernetes 客户端发出；在集群里那个客户端用的是 Pod 自己的 ServiceAccount 令牌和 CA（`k8s/overlays/platform-prod/sa-kubeconfig.yaml:9–25`），和门的读是同一个身份。POST 不决定成功。「修订 2026-10-12 之二」两处补全。**一个地址，不跟随重定向。** 这一次 POST 只发往一个地址：平台的集群配置里的 apiserver，路径 `/apis/release.bifrost.io/v1/freezes`，查询为空。应答是 3xx 时不发第二次请求，`Location` 指向哪里、带不带查询都一样；它归进第 3 步的「其余」，报未知，回读照做。client-go 的 REST 客户端自己不设 `CheckRedirect`，Go 的默认是跟随，307 和 308 还可以把 POST 连正文重发到新地址。所以建的函数拿平台的集群配置另起一个 HTTP 客户端，不跟随重定向、不重试；`rest.HTTPClientFor` 在某些配置下交回的是进程共用的 `http.DefaultClient`（`k8s.io/client-go` v0.32.3 的 `rest/transport.go:32–48`），不能在它上面改。「经平台现有的 Kubernetes 客户端」因此读作：同一份配置、同一个令牌和 CA，客户端是为这一次另起的。**`at` 的范围。** `at` 取调用时刻的 UTC，截到秒，写成 `2006-01-02T15:04:05Z` 的样子。年份在 1 到 9999 之内时它正好 20 个字符，合 3.1 的 `pattern`；之外不是，函数不发请求，报「冻结没有写上」。
3. **回读。** 再用门的读函数读一次。**建成 ⇔ 这一次读列出了刚才那个名字。** 没有列出时，POST 的状态码只用来选报哪一种失败：403 报「这个集群没有打开冻结」；别的 4xx 报「冻结没有写上」；其余——2xx 而回读看不到、5xx、没有应答、超时、回读自己读不到——都报「没有确认建成，状态未知，请再读一次」；其中回读自己读不到的那一种，多说一句：只要还读不到，门就不放行。5xx 和超时归进「未知」，是因为应答可能丢在写入之后。不管 POST 回的是什么，回读都做一次。任何情况下都不凭 POST 报建成。
4. **一个期限。** 第 2、3 步共用一个绝对的期限：从发 POST 起 10 秒，和读一样；过了期限才读完的回读不算。第 1 步是一次普通的读，有它自己的 10 秒。

回答里带第 3 步读到的全部记录；在途 run 的清单在 S4 加（3.3）。上面几句报错的话写的是意思，原文、语言和路由回的状态码在 S3b 定（第 13 节的表）。

**状态接口** `GET /api/v1/release-policy`：`frozen`（冻结或读不到都是 true）；`freeze_state`（`clear` / `frozen` / `unreadable`）；`freezes`（每条的 `name`、`uid`、`who`、`reason`、`at`、`via`）；`freeze_unreadable_reason`；`freeze_can_create`（平台对自己做一次 SelfSubjectAccessReview）；`freeze_protocol: 3`（分支上用过 2，主线没有这个字段）；`lift_command`。`freeze_reason` 保留，是各条记录拼成的一行，给还没更新的 Console 用。去掉 `frozen_at`、`freeze_id`、`unfreeze_command`。

**`release.sh`**：

- `freeze --reason <原因>`：读状态，要求 `freeze_protocol` 是 3 且 `freeze_can_create` 为真；POST；打印这次建的记录、当前全部记录和在途的 run；末行写「只有 Owner 能解开：`release.sh unfreeze`」。
- `unfreeze`：只给 Owner，不经平台（平台停着也能用）。要求环境变量 `BIFROST_OWNER_KUBECONFIG`，没有默认路径，等于只读身份那一份时拒绝。它 LIST **一次**，打印每条的名字、UID、`who`、`reason`、`at`；他点名其中几条，或者确认「上面列出的全部」；脚本只删这张清单里被选中的（名字，UID）对，一条一个请求，带 UID 前置条件，不用 `--all`、不用标签、不发整类删除；删完再 LIST 一次并打印还剩几条；把被删记录的全文和时间追加到发布日志。清单之后才建的冻结不在清单里，所以留着；同名而 UID 不同的（删了又被重建）得到 409，也留着。正文由 JSON 编码器生成，不拼接字符串，对象恰好是 `{"kind":"DeleteOptions","apiVersion":"v1","preconditions":{"uid":"<uid>"},"propagationPolicy":"Background"}`，经 `kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete --raw "/apis/release.bifrost.io/v1/freezes/$name" -f -` 送出。使用前名字必须匹配 `^freeze-[0-9a-f]{32}$`，UID 必须匹配 `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`（实测：上面那次命名空间 LIST 里项的 `metadata.uid` 是这个形状）。对不上就不发请求。测试覆盖引号、反斜杠、以及会插进第二个 `preconditions` 的注入：模式把它们拒绝；编码器另有一条绕过模式的用例，确认输出里 `preconditions` 只有一个键。片 1 用真实 `kubectl` 1.34.1 对假服务器录到的正文与这个对象相等（chunked）；真实 apiserver 认不认 UID 前置条件仍是第 7 节步 3，本修订没有重测。过期 UID：服务器回 409，对象还在。

- `policy status`：打印 `freeze_state`、每条记录一行、`freeze_can_create`、协议号。anchor 那一行不再提冻结。

**增长、清理、应急**：平时是零条，解冻就是清理，没有要定期回收的历史。冻结的历史在平台的审计里，解冻的历史在发布日志里。应急都是 Owner 的事，而且不改任何记忆，因为没有记忆：有人刷了几十条——同一个 `unfreeze`，确认「上面列出的全部」；读不到（CRD、策略或绑定被动过）——重新应用 `k8s/release-freeze/` 里的文件，它们是幂等的；检查任务坏了——从上一个提交重新应用那个文件。卡在删除中的记录（带着 `deletionTimestamp` 和 finalizer，仍在 LIST 里，仍算冻结）——Owner 临时调整准入（撤掉记录那条策略的绑定），摘掉 finalizer（`kubectl patch freeze <名字> --type=merge -p '{"metadata":{"finalizers":null}}'`），重新应用 `admission.yaml`，再把第 7 节步 2–3 的拒绝探针重跑一遍；绑定撤掉的那一小段只剩 RBAC 一层。原来的「不用签名解冻（break-glass）」那一节作废：日常的解冻就是它，而且从三个对象变成一个。

## 4. 策略的签名与重放

同一把密钥还签自动放行的策略。签名证明 Owner 说过一次，不证明这仍是他现在想要的。

**今天的代码**（主线 `17136ba`）。门每次读 `cicd/bifrost-release-policy`，验签名、`version == 1`、`signed_at` 不在未来 5 分钟之后、`expires_at` 没过（`api/internal/releasepolicy/policy.go:155–200`），不和任何更早的状态比较。`Install`（`write.go:31–60`）先验要装的这一份，再读已安装的那一份，只在后者满足 `old.policy != nil && !old.signedAt.IsZero()`（`write.go:45`：签名验得过、能解析、两个时间都解析得出；**不要求它仍然有效**）时，拒绝 `signed_at` 更早的新策略。`WriteConfigMap`（`api/internal/delivery/release_policy_facts.go:54–78`）自己再 GET 一次，把读到的对象换掉 `data` 后 Update：这次 Update 带的是**它自己那次读**的 `resourceVersion`，和 `Install` 做比较时读到的版本没有绑在一起。**所以今天重新装上一份旧的、已签名的策略是做得到的**，界限只有它自己的 `expires_at`（模板 90 天，脚本上限 366 天）。三条路：(1) 1.1 表里前三行的账号直接写这个 ConfigMap，不经过 `Install`；(2) 已安装的那份是空的或验不过时没有比较——今天集群上这份对象是空的，锚也是空的（`anchor.go:11`）；(3) 竞态：装 P1 的请求读到更旧的 P0、通过比较 → 另一个请求装上更新的 P2 → 前者的 `WriteConfigMap` 重新读到 P2，用 P2 的版本号把 P1 写上去，成功（分支上已改成把 `Install` 读到的版本号传给写入）。今天没有任何策略验得过，这个洞是潜在的；它要在第一份策略签出来之前关上（已定，第 9 节 D5）。

**本设计加的**（S5）：策略用同一个形状。资源类型 `policies.release.bifrost.io`，集群级，内容是 `text` 和 `sig`；生命周期是 3.1 的同一条准入策略；平台账号只有 `create` 和 `list`。但策略不像冻结那样天然单调——「哪一份生效」靠一个签过名的排序值，这里把它写死：

- **排序值**是签名正文里的 `signed_at`。**门**：在签名验得过的记录里，只要有一条的 `signed_at` 解析不出来 → 没有策略；取最大的那一条；最大值上有两条正文不同 → 没有策略；对选出的这一条再查版本、未来时间和过期，不过 → 没有策略，**不退到更早的那一条**。LIST 读不到 → 没有策略。验不过的记录不参与。
- **签名工具**（`release.sh policy sign`）：先 LIST 集群上的策略记录，再读本机的签名日志（每签一次追加一行 `signed_at` 和正文摘要，盖住签了但没装的那些）；新的 `signed_at` 必须严格大于两处的最大值。LIST 失败、日志读不了、或者时钟给不出更大的时间，就拒绝签名，不自动把时间往后挪。
- **向量**（门和工具共用一份）：时钟回拨——工具拒签；绕过工具签出的较小时间在门那里输给旧的那份，这正是工具必须拒签的原因。同一秒两份不同的正文——没有策略。最新的一份过期——没有策略，不回到更早的。时间解析不出来——没有策略。

于是：只要比它新的那条记录还在，旧签名重放多少次都不生效；拿掉新的那条要 Owner 的删除。撤回一份策略的办法是签一份更新的（`allow` 可以是空的），不是删除。**留着的**：Owner 自己删掉最新的一条之后，一份没过期的旧策略可以被重新建出来并生效，界限回到过期时间——规则是「不删最新的一条」；在另一台机器上签、又没装上集群的正文，本机日志盖不住；密钥泄露不在范围内。

## 5. 迁移和上线顺序

要搬的状态是零：旧对象是从未冻结的形状，两份记忆是空的，新类型一条记录都没有。难处在另一头：**换掉 Task 的定义，换不掉已经装载了旧程序的 TaskRun 和 Pod**。一个停在 GET 之前的旧程序，可以在第一条新冻结建成之后醒来，读到仍是 `false` 的旧对象并放行（复核 93 的序列）。

**构造：墓碑。** 所有读的一方都换到新协议之后、打开 `create` 之前，Owner 把旧对象写成集群上那份旧程序认作「冻结」的形状（实测它的 schema：正好 `frozen`、`frozen_at`、`who`、`reason` 四个键），并设成不可变：

```bash
kubectl -n cicd patch configmap bifrost-release-freeze --type=merge -p '{"immutable":true,"data":{"frozen":"true","frozen_at":"<当时的 UTC 时间>","who":"owner","reason":"tombstone: freezes moved to freezes.release.bifrost.io"}}'
```

没有东西解得开它。改：`immutable` 的 ConfigMap 谁都改不了内容、也摘不掉这个标记（假定，Kubernetes 的内建行为），所以 1.1 表里前三行那三个账号的写权限对它无效。删：`admission.yaml` 里的墓碑策略名叫 `bifrost-release-freeze-tombstone`，`failurePolicy: Fail`；只匹配 core 组 `v1` 的 `configmaps` 的 `DELETE`，`resourceNames: ["bifrost-release-freeze"]`，`namespaceSelector` 在 `matchConstraints` 下，标签 `kubernetes.io/metadata.name: cicd`；唯一一条校验是 `request.userInfo.username == 'OWNER_USERNAME'`；同名绑定 `validationActions: [Deny]`。否则那几个有全集群 ConfigMap 删除权的系统账号可以删了它再建一份 `false`。新平台的代码里没有这份对象。它永久留在集群上。四个旧读者各是各的情况：旧检查程序读到墓碑就按冻结拒绝（它读到 404 也拒绝）；旧的 `freeze` 步骤读到墓碑拒绝，但它把 404 当未冻结，所以对它管用的是墓碑**还在**；两个环境的旧平台读到墓碑按冻结拒绝，它的 `Unfreeze` 往不可变的对象上写会失败并返回错误，之后再读仍是冻结。所以要点是墓碑留着、删它要过准入，不是「删了也一样安全」。

| 时刻 | 检查任务的定义 | 平台 | 旧对象 | `create` | 还活着的旧程序读到 | |
|---|---|---|---|---|---|---|
| 今天 | 旧 | 旧 | `false` | 无 | `false`，放行；没有任何冻结存在 | 安全 |
| 新 Task 应用之后 | 新 | 旧 | `false` | 无 | 同上 | 安全 |
| 平台两个环境都换新之后 | 新 | 新 | `false` | 无 | 同上 | 安全 |
| 这时就打开 `create` | 新 | 新 | `false` | 有 | `false`，放行，而新类型上已有冻结 | **不安全：复核 93 的序列** |
| 新 Task 还没应用就写墓碑 | 旧 | 旧 | 墓碑 | 无 | 全部流水线被拒，平台发不了版 | 只是拒绝，没有放行；别这样排 |
| 排空、写墓碑之后 | 新 | 新 | 墓碑 | 无 | 冻结，拒绝 | 安全 |
| 再打开 `create` | 新 | 新 | 墓碑 | 有 | 冻结，拒绝 | 目标 |

**必须守的先后是一个偏序，不是唯一的一种排法。** 三条硬的：CRD、准入、只读的 RBAC 和使用前的检查，先于新 Task 和新平台；新 Task、两个环境的新平台、排空，先于墓碑；墓碑、TD-314、TD-293，先于 `create` 的绑定。TD-314 和 TD-293 可以更早关；墓碑写早了只造成拒绝，不造成放行。下面是照着做的一种排法：(1) 核对现状；(2) CRD、准入策略和绑定、只读的 RBAC，并做完使用前的检查——这时没有任何东西读新类型；(3) 新的两个 Task；(4) 平台发版，先 STG 后 PROD；(5) 证明没有旧程序还活着、每个平台副本都是新版；(6) 写墓碑；(7) TD-314 和 TD-293 的收窄；(8) `create` 的绑定；(9) 演练；(10) 清理旧的程序 ConfigMap 和两份记忆，墓碑不清。

顺序之外的三条约束：第 (4) 步上 PROD 之前不合并锚（否则旧平台会往旧对象上写冻结，而新的检查任务已经不读它）；墓碑之后没有「回到旧 Task」或「把平台回滚到这次发版之前」的退路，只能往前修，所以它排在至少一次 STG 发布和一次 plan run 走通之后；有人把第 (4) 步做在第 (2) 步前面，平台读不到、拒绝全部发布，补做第 (2) 步即可，那一步不经过流水线。分支 `w31/td-310-anchor` 上留用的：`newFreezeID`；指纹常量、`allowed_signers`、交叉核对的测试和 CI 的等待顺序（策略要用）；`Install` 带版本号的写。作废的：`memory.go` 的全部、冻结协议 2、解冻句子的格式、schema 里「已解冻」的形状。

## 6. 证明义务和测试

**要证的性质**，三条，都没有例外：

- **S（安全）**　新协议的门答 `clear` ⇒ 到它读的那张快照为止，每一条建成过的记录都已经被 Owner 的身份删掉。还活着的旧程序：`create` 一旦打开，它不再答 `clear`（靠「先墓碑、后 `create`」）。`create` 打开之前，新类型上的记录只可能出自 Owner 或 L3——步 3 的探针就是——旧程序本来不读它。
- **L（活性）**　没有任何记录，且传输每一条都成立，且正文属于 L ⇒ 每个新协议的门都答 `clear`，包括这一步才建出来、什么都没看过的进程。只有 S 的话，永远拒绝也能通过。TLS、状态或编码上的预期拒绝不是这条的反例。
- **U（读不到）**　传输有一条不成立，或正文不在 L ⇒ 不答 `clear`。给人看的 `frozen` 和 `unreadable` 不进入这三条。

**模型是有限的、可执行的。**

- 身份 5 个：O（Owner）、P（平台账号）、T（流水线账号）、G（垃圾回收器）、W（有通配符权限但不是 Owner，例如 Argo）。名字 2 个，每个名字最多两代 UID（删了重建）。
- 「建」的内容分 7 个等价类：合规；带属主引用；带 finalizer；带标签或注解；带 `generateName`；名字不合规；`spec` 不合规。
- 事件：建（身份 × 名字 × 7 类）；改（身份 × 名字 × `spec` / 元数据 / 子资源）；删（身份 × 名字 × UID 相符 / 过期 / 不带 × 普通 / 前台）；整类删（身份）；垃圾回收器清扫（走和其他删除相同的授权与准入，不是绕过）；读（门 ∈ PROD api、PROD workers、STG、新检查任务、这一步才建出来的门、还活着的旧检查程序）；读故障是两类，一次一种：正文不在 L，或传输有一条不成立；写墓碑；打开 `create`（守卫：墓碑已在，也就是第 7 节步 9 排在步 7 之后）。
- 状态：现存的记录（名字 → 第几代，连同内容等价类——被拒的建不改变状态，要能断言它被拒）；建删历史（每一代由谁建、由谁删）；旧对象（`false` / 墓碑 / 不存在）；`create` 开没开。一次读有一张显式快照：在一个点上线性化，返回可以排在其后的写之后。快照含四样：现存记录、建删历史、旧对象（`false` / 墓碑 / 不存在）、`create` 开没开。S、L、U 对这张快照断言，不对返回时刻的状态断言；旧程序的 S 也按线性化时的旧对象和 `create` 开关查（`create` 已开而旧对象仍是 `false` 时它不得答 `clear`）。测试把一次写夹在线性化和返回之间，写前和写后两个标签必须看到不同的快照。模型里的门调用真正的识别器：一次成功的空 LIST 是传输每一条都成立，加上 3.2 里换成冻结字面量后属于 L 的那份实测正文。一个名字的两代 UID 都用完之后，对它「建」的事件不再生成（不在图里，不是被拒），其余事件照常，所以图是有界的。
- 通过与否由这张固定的状态图和写明的断言决定，不靠抽样，也不靠人看：图由字母表和上面的界确定地生成；每个可达状态上把每个事件各执行一次，断言 S、L、U、「被拒的事件不改变状态」，以及每个事件的预期。预期：除「O、W 建合规的，以及 `create` 打开之后 P 建合规的」「O 带相符的 UID 或不带 UID 普通地删」「O 的整类删除（每个对象各过一次删除规则）」之外，一切写都被拒；G 和 W 的删，以及清扫，都是 RBAC 放行、准入拒绝。
- 3.1 的每条规则，谁依赖它。阴性对照只给有性质依赖的规则，每次去掉一条。L 和 U 不依赖 3.1：L 靠识别器对属于 L 的空列表答 `clear`；U 靠识别器对其余应答不答 `clear`。

| 规则 | 依赖 | 对照或纵深 |
|---|---|---|
| 删除的用户名必须是 Owner（清扫、W、整类删走同一条） | S | 只去掉这半句：W 的普通删除成功，新门对删之后的快照报 `clear` |
| 先墓碑、后打开 `create`（第 5 节的守卫） | S | 只去掉守卫：旧程序在 `create` 已开、旧对象仍是 `false` 时答 `clear` |
| `failurePolicy: Fail` 和绑定 | S 靠它们执行上一行 | 不单列：拿掉它们和拿掉用户名是同一个违例 |
| 建时不许属主引用、finalizer、标签、注解、`generateName` | 无 | 纵深。属主引用不是 S 的前提：清扫走删除准入。复核 100 那条违例，是模型让清扫绕过了仍开着的准入 |
| 不许 UPDATE；删除必须是普通删除 | 无 | 纵深：这两种都不让记录消失，门不会因此报 `clear`。普通删除保的是可用性 |
| 名字格式；根上必填 `spec` | 无 | 纵深：漏进 LIST 的坏记录仍算冻结。必填 `spec` 是为了 apiserver 和模型拒绝同一类内容 |
| RBAC 不给 `delete` | 无 | 纵深，第二层。W 有通配符，S 不靠这张表 |
| `policies` 走同一条准入 | 无 | 冻结的 S、L、U 不读策略记录，归第 4 节，不另设对照 |

- 另跑随机长序列，对象是两份真实的实现：Go 的引擎对着一个假的 HTTP 服务器，Python 程序作为子进程读同一个服务器。默认 2000 条、每条 40 步（未设置 `FREEZE_MODEL_SEQUENCES`）；全量 5000 条由该变量打开。另加一个每次不同并打印出来的种子。重放此前出现过的每一个请求体，包括旧协议的解冻签名（发到已经是 410 的接口，以及当成记录内容去建）。时间待实测，不按条数线性折算。目标是 `GOMAXPROCS=2` 下整包低于 40 秒；生成器、穷尽模型、整包各记各的时间，实现报告贴实测的 `ok` 行。片 1 在同样的 `GOMAXPROCS=2`、单包超时 120 秒下整包 66.6 秒（统筹方的复跑，本修订没有重测），超过统筹方留的 60 秒余量。穷尽搜索不抽样，也不为了时间把字母表缩小。

**零违例只证明这个有限模型。** 它说的是「如果集群这样放行和拒绝，性质成立」。集群是不是真的这样，由第 7 节证明：模型里每一类被拒的事件，在那里都有一条对应的检查。假服务器和 dry-run 证明不了的只有两件，要靠在集群上受控地做一遍：垃圾回收器的真实行为（步 3），LIST 的新鲜度（演练第 ② 步：建完立刻发 run，必须被拒）。两份实现的一致是二进制判定：3.2 的向量、生成器和照产生式另写的识别器。生成器、穷尽模型、整包三次计时分开验收，缺一次不算通过。

**演练**（Owner 在场，输出写进文件）：① 两个平台的状态和一次 plan run 都是未冻结。② 线程经 PROD 平台冻结 A，立刻发起：PROD 状态、**这期间什么都没读过的 STG** 的状态、一次新的 plan run、一次 `start_pipeline_run`，四处都拒绝。③ Owner 以平台账号的身份对 A 做 dry-run 的删和改，被拒。④ 经 STG 平台再冻结 B；Owner 只解 A；四处仍拒绝；重启 PROD 的 api 和 workers，仍拒绝。⑤ Owner 解 B：四处放行，一次 STG 发布跑完。⑥ Owner 手写一条合规的记录：四处拒绝；删掉：放行。⑦ 一条 STG 流水线过了检查之后再冻结：它跑完，新的被拒，**回执里点了它的名字**。⑧ 暂停的旧程序：把存下来的旧检查程序（`239f100` 的 `scripts/release/freeze_decision.py`，集群上那份的原样）对着现网的旧对象跑，在有冻结和没有冻结时各一次，两次都必须拒绝。

## 7. Owner 亲手做的

启用 `create` 的前置，按序（复核 95 的末行）：
1. ✓ 已办（2026-10-11）：Owner 定 D1、D2、D4、D6，都按推荐。
2. S1 通过。
3. CRD、两条准入策略和各自的绑定逐项实测通过，探针已删除。
4. 只读的 RBAC 核验通过；真读在各自的 Pod 里答 `clear`，CA 与主机名由这次读留下。「修订 2026-10-12」是四次，都用 `freeze_gate.py` 的说明模式（两个流水线账号、两个平台账号）；Go 读函数自己的第一次真读是 S3b 在 STG 上的验收（D10）。「修订 2026-10-12 之二」不再是四次：四个身份各问一次 `can-i list`，答案都必须是 `yes`；真读一次，在探针账号的 Pod 里，仍用说明模式。读在真实的工作负载里走得通，流水线账号的由步 5 证明（7.1 的 5-4、5-5），平台账号的由 S3b 的 STG 验收证明（D10）。
5. 两个 Task 和两个环境的平台都读新协议，旧程序排空。
6. 墓碑不可变，删除保护通过。
7. TD-314 和 TD-293 的提升路径都封住。
8. 再开 `create` 并演练；失败就撤掉绑定，墓碑保留。

CRD、准入、RBAC、Task 的定义只有他应用。两次坐下来，中间隔着平台的一次发版。每一步后面是证明它生效的检查；有一格不符就停，不往下做。`--as` 的检查只有他能跑（只读身份不能冒充）。退路：步 5 之后流水线有问题，从上一个提交重新应用那两个 Task 文件（旧对象这时还是 `false`，旧的程序 ConfigMap 还在），CRD、策略、绑定留着无害。**写下墓碑（步 7）之后，不能回滚到旧 Task，也不能把平台回滚到 S3 之前，只能往前修。**「修订 2026-10-12 之二」两处补充。这条退路恢复的只是两个 Task；步 5 用的那次 STG 发布已经发出去的东西它不管，那是另一步，而且今天只能前修（7.1 步 5 末尾）。「两次坐下来」之间多一次短的：平台新版上了 STG、还没上 PROD 的时候，他手建一条记录、看 STG 拒绝、再删掉（D10 的第 ③ 条）。

| 步 | 做什么 | 生效的证明 |
|---|---|---|
| 0 | 不改东西。「修订 2026-10-12」当天第一条集群命令是 CRD 的服务端试算，被拒不花任何代价 | 「修订 2026-10-12」7.1 的 0-1 到 0-7：CRD 的服务端试算通过；旧对象的 `data` 是 `{"frozen":"false"}`（「修订 2026-10-12 之二」并且没有 `immutable`，没有别的顶层字段：不可变的旧对象之后写不成墓碑）；`release.sh window` 没有窗口；`kubectl auth whoami` 读到的用户名和组都已记下；由仓库文件渲染出的副本和它只差带占位符的两行（原文是「用户名填进了策略文件」，D9）；同名认证的来源由 Owner 自己看过并记下；`impersonate` 的授予方仍是那四个（3.1） |
| 1 | `crd.yaml`：先 `kubectl apply --dry-run=server`（「修订 2026-10-12」已在步 0 做过），通过后正式应用 | 「修订 2026-10-12」7.1 的 1-1 到 1-3：`Established` 为 `True`；类型出现在 `api-resources` 里，不分命名空间。这一步还没有 `list`，不做空 LIST 的真读 |
| 2 | `admission.yaml`（两条策略和各自的绑定）：同样先 dry-run 再应用。「修订 2026-10-12」应用的是步 0 渲染出的副本 | 「修订 2026-10-12」7.1 的 2-1 到 2-6（「修订 2026-10-12 之二」多出的一格是 2-5：当天第一次拒绝的原文先看一遍、留在文件里）。两条策略的 `observedGeneration` 等于 `generation`，`expressionWarnings` 为空——这只说明对象在，算数的是下面每一次拒绝。「修订 2026-10-12」实测 10-12：集群上在用的 6 条策略有 5 条的 `expressionWarnings` 不为空；所以这一项不为空时把原文记下、照常做下面的探针，由探针判，不单独算不符。「修订 2026-10-12 之二」记下的警告是一条待核实的事，不是可以忽略的噪声：事后由统筹方逐条说明它是对动态类型的推断警告还是真错，连同正反两面的探针一起留档（第 13 节的表）。`kubectl create --dry-run=server`：合规的放行；带属主引用、带 finalizer、带标签、带注解、带 `generateName`（同时写着合规的名字，否则先被 CRD 拒）的各被**记录那条策略**拒；名字不合规、缺 `spec`、缺 `reason` 的被 CRD 拒。怎么认是哪一条拒的：报文里同时有策略名 `bifrost-release-records` 和那条规则自己的 `message`；只有策略名、正文是表达式求值出错的不算；`is forbidden: User … cannot` 是 RBAC，`is invalid` 是 CRD（报文样式是假定，第一次拒绝时对一下）。「修订 2026-10-12 之二」后半句改掉：RBAC 的拒绝认完整的 `User "…" cannot <动词> resource` 这一句，不认 `is forbidden` 三个词——准入的拒绝也可以带它们（`k8s.io/apimachinery` v0.32.3 的 `pkg/api/errors/errors.go:209–217`）；`is invalid` 也不能单独认作 CRD，准入策略的拒绝默认也是这个原因（凭 API 文档，未实测）。CRD 的拒绝认的是：不带策略名，带着出错的字段。报文样式仍是假定，所以 2-5 先把当天第一次拒绝原样看一遍，对不上就先改要找的字，再判 |
| 3 | 真建一条探针记录 `freeze-` 加 32 个 `0`。这时没有任何门读新类型，它不影响发布 | 「修订 2026-10-12」7.1 的 3-1 到 3-19。「修订 2026-10-12 之二」三处：探针用 `--field-manager=platform-api` 建、带着 `via`，让它的信封尽量像平台的请求；「探针没被动过」比的是建出来时留的快照（`resourceVersion`、`generation`、元数据、`spec`），不只是 UID 和删除时间；3-19 量到的字节数只是对 E 的估计，不签收（3.4）。拒绝照上一行的认法数。比原文多六格：建出探针后量一次 LIST 的字节数（3.4 的上界 E 拿它核对）；`--as` Argo 控制器的改；`--as` `argocd-server` 的删和改（这两个账号凭通配符有这些动词，3.1）；试算做完后数一遍拒绝并确认探针没被动过；带错 UID 的删得 409、对象还在（3.4 说过真实 apiserver 认不认 UID 前置条件在这一步证）。原文：对探针做 dry-run，拒绝都要来自记录那条策略（认法同步 2）：Owner 改 `spec`、加标签——拒；`--as` Argo 控制器、`--as` 垃圾回收器的删——被策略拒，不是被 RBAC 拒；`--as` Argo 控制器不带请求体的原始 DELETE（`kubectl delete --raw '/apis/release.bifrost.io/v1/freezes/<探针>?dryRun=All'`）——被策略拒；`--as` Argo 控制器对整类 `kubectl delete --raw '/apis/release.bifrost.io/v1/freezes?dryRun=All'`——拒；Owner 的前台删除、孤儿式删除——各拒；Owner 的普通删除——放行；Owner 自己不带请求体的同一条原始 DELETE——放行（规则里 `options` 缺省的那一支只有他的请求走得到，这一格证明它不是求值出错）。再真做一次带属主引用的建——拒，两分钟后 LIST 仍只有探针。最后用 3.4 那条带 UID 的命令真删探针，LIST 为空。**这一建一删通过之前，什么都不接线**（步 5 和 S3 都在它后面） |
| 4 | `rbac-list.yaml`。can-i 通过之后、步 5 接线之前，做真读（「修订 2026-10-12」四次，原文写的是两份；「修订 2026-10-12 之二」一次，在探针账号下） | 「修订 2026-10-12 之二」整格再次重写，7.1 的 4-1 到 4-9。上一版（四个账号各起一个临时 Pod 真读）作废：那样的 Pod 带着平台账号或 applier 账号能做的一切。应用之前：一个新建的、什么权限都没有的探针账号真读一次，必须被拒（403，程序印拒绝、退出码 1），然后查它的 Pod 和账号都没有留下。应用之后 `kubectl auth can-i <动词> freezes.release.bifrost.io --as=…`，每一问的答案和退出码都留下，空的答案或别的退出码算没问成：`cicd` 的 12 个 ServiceAccount 逐个、两个平台账号、`bifrost-access:bifrost-agent`，对 `list` 都是 yes；对 `create`、`get`、`watch`、`update`、`patch`、`delete`、`deletecollection`，除下面 10 格之外都是 no——`argocd-application-controller` 这七个动词都是 yes，`argocd-server` 的 `get`、`patch`、`delete` 是 yes（实测 10-12，通配符规则，和附录一致；拦住它们改和删的是准入策略，已在步 3 对它们各试过）。原来要真读的四个身份——`cicd` 的 `bifrost-applier` 和 `default`，两个平台命名空间的 `bifrost-platform`——各问一次 `list`，四个答案都必须正好是 `yes`。新角色 `bifrost-release-freeze-list` 没有标签、没有 `aggregationRule`、规则只有 `list` 这一条（另一个新角色步 9 才应用，到那时查）；`admin`、`edit`、`view` 三个聚合角色都读到了，规则里搜不到 `release.bifrost.io`。然后真读一次：`freeze_gate.py` 的说明模式（3.2），Pod 在 `cicd`，身份是这一格新建的一个 ServiceAccount——它经 `rbac-list.yaml` 里给 `cicd` 全体账号的那条绑定得到 `list`，别的什么都没有。Pod 的名字每次不同；清单是 7.1 里的定文（一个容器、一条命令、没有额外的挂载、`restartPolicy: Never`、`activeDeadlineSeconds: 180`）；等待和送入都有期限；退出和被打断时都清理，只删这一格自己建出来的（按建的时候记下的 UID）；紧接着的一格查 Pod 和账号都不在了，也没有绑定点它的名。对象是新类型的空 LIST。这次读留下：命名空间、判定 `clear`、请求行 `HTTP/1.1`、证书链用的是该 Pod 的 CA 文件且签发者在里面、主机名是 `kubernetes.default.svc`。**这一步不再证明的**：读在每一个真实的工作负载里走得通。两个流水线账号的由步 5 的两次 run 证明；平台账号的，连同 Go 读函数自己的第一次真读，是 S3b 在 STG 上的验收（D10）。只核对 `kubectl` 印出的正文不算。集群升级之后、下一次发布之前重跑真读那一格 |
| 5 | `k8s/cicd/tekton/` 下的两个 Task 文件（它们的提交当天才进 `main`，见第 8 节 S2，不在 S1） | 「修订 2026-10-12」7.1 的 5-0 到 5-5；两个文件的写法和来路见 3.3。集群上 Task 的脚本和 `scripts/release/freeze_gate.py` 的 SHA-256 相同；一次 `plan_manifest`（账号 `bifrost-applier`）在 `freeze-check` 通过，日志第一行是「未冻结：0 条记录」；一次 STG 发布（账号 `default`）通过。「修订 2026-10-12 之二」那次 STG 发布点名是平台的 `bifrost-deliver-platform`；起之前先看它会带上去哪些提交。它的副作用（两个可变标签上的镜像被换掉，平台 STG 滚动重启）和两条退路写在 7.1 步 5 末尾：恢复两个 Task 是一条；平台 STG 是另一条，带了改动时只能前修。改过的 `bifrost-release-window` 这一步跑不到，它第一次真跑在此后的第一次插件或 research 构建（第 13 节的表） |
| | **——平台新版先后上 STG、PROD（S3）之后，第二次——**「修订 2026-10-12 之二」上了 STG、还没上 PROD 的时候有一次短的：Owner 手建一条记录、看 STG 拒绝、再删掉（D10 第 ③ 条） | |
| 6 | 不改东西：排空和版本 | `kubectl -n cicd get pods -o json` 里，挂着 ConfigMap `bifrost-release-freeze-check` 而 `status.phase` 不是 `Succeeded` / `Failed` 的，零个；`kubectl -n cicd get taskruns -o json` 里，没有 `status.completionTime` 而创建时间早于步 5 的，零个；两个环境的状态接口都报 `freeze_protocol: 3`；每个环境里 `platform-api` 和 `platform-workers` 的所有 Pod 的 `imageID` 相同（两个 Deployment 都是单副本、`Recreate`，实测）。这四项只读身份也能查 |
| 7 | 写墓碑（第 5 节的命令）。**动手前再看一遍：之后不能回滚到旧 Task 或 S3 之前的平台** | `jsonpath='{.immutable} {.data.frozen}'` 是 `true true`；Owner 对它 dry-run 改 `data`——拒（不可变）；`--as=system:serviceaccount:cnpg-system:cnpg-manager` 对它 dry-run 删除——被策略拒；存下来的旧检查程序读现网对象，退出码非 0、第一行是拒绝；一次新的 plan run 照常通过 |
| 8 | TD-314 和 TD-293 的收窄（清单和各自的验收在这两条里；可以更早做） | TD-314：`kubectl auth can-i patch deployment/argocd-server -n cicd --as=system:serviceaccount:bifrost-platform-prod:bifrost-platform` 是 no，平台的重启和缩放照常。TD-293：`kubectl auth can-i` 的 `update` 和 `patch`，对 `-n cicd` 的 `configmap/argocd-cm`、`configmap/argocd-rbac-cm`、`configmap/argocd-cmd-params-cm`，分别 `--as` 两个平台账号和 `system:serviceaccount:cicd:tekton-deliver`，都是 no；平台写发布记录和发布窗口、流水线写它该写的 ConfigMap 照常。只读身份能查其中一半：读这三个账号在 `cicd` 的角色，规则都带 `resourceNames`，里面没有这三个名字 |
| 9 | `rbac-create.yaml` | 两个平台账号 `can-i create` 是 yes，其余账号仍是 no；状态接口的 `freeze_can_create` 为真 |
| 10 | 演练（第 6 节八步），然后清理 | 八步全部符合；删掉 `cicd/bifrost-release-freeze-check` 和两个 `platform-state-release-policy-freeze`；墓碑留着 |

### 7.1 步 0–5：每一格的命令和预期（「修订 2026-10-12」；「修订 2026-10-12 之二」按复核 121 整节重写）

每一格落成三种之一。**命令**：整条命令和预期输出。**Owner 自己看**：看什么、记在哪。**并掉**：并到哪里、为什么。原表步 0–5 的每一格在这里都有着落，没有整格删掉的：绝大多数是命令；Owner 自己看的有三项（用户名和组；认证的来源；当天第一次拒绝的原文）。本节另加的格标着「新」。有一格挪走了大半：原来步 4 要在四个真实账号的身份下各真读一次，现在步 4 只做一次真读，身份是为这一次新建的探针账号（见步 4 开头）。

**先取结果，再判（之二）。** Owner 的查询都经下面的 `q` 发出：它把标准输出存进 `$DAY/<格>.out`，把错误输出存进 `.err`，把退出码存进 `.rc`，再把三样印出来。判的时候读的是这三个文件。空的答案、失败的查询、不是这一格写明的那个退出码，都算这一格不符，不算预期输出。每一格先看 `.rc`，再看别的。不经 `q` 的有三处，各自留结果：4-4、4-5 的循环把每一问的答案和退出码写成一行；`probe.sh` 自己记日志；统筹方跑的几格（0-7、5-4、5-5）用 `> 文件; echo "exit=$?"`，意思相同。上一版里的毛病是同一种：查询接在管道后面，查询失败时 `grep -c` 照样印出 `0`，看上去和「什么都没有」一样。

**怎么认一次拒绝（之二）。** 准入的拒绝：同一份 `.err` 里同时有策略名 `bifrost-release-records` 和那条规则自己的 `message`。RBAC 的拒绝：完整的 `User "…" cannot <动词> resource` 这一句。单凭 `is forbidden` 认不出来源——准入的拒绝也可能带这三个词。报文的样式是假定：当天见到的第一次拒绝（2-4 的 `d-ownerref`）先原样看一遍、留在文件里，和假定对得上才往下；对不上就停，先把下面几格里要找的字改对。

**试跑到哪一步。** 只读身份不能写、不能 `--as`、不能做服务端试算；工作区的守门脚本拒绝执行任何写着 Owner 凭证的命令行，也不许把 `KUBECONFIG` 指到只读身份那一份之外。所以带 `$BIFROST_OWNER_KUBECONFIG` 的命令没有任何人跑过。标「写法实测」的，是同一种写法在 10-12 用只读身份对现有对象、或在本地跑通过。`q` 在 zsh 里试过。`probe.sh` 用一个不碰集群的替身 `kubectl` 试过八条路：答 `clear`、被拒、答得不对、账号建不出、Pod 建不出、Pod 起不来、`attach` 卡住、中途被终止——清理都只删它自己建出来的东西。终端里的 Ctrl-C 没法在后台模拟，试的是同一个处理函数接到终止信号。

命令在 `bifrost-trade-infra` 的检出目录里执行，一行一条。`$DAY` 是仓库之外的目录，统筹方读里面的文件。

**先做，不碰集群**（写法实测）

```
export BIFROST_OWNER_KUBECONFIG=<Owner 自己填：他的管理员 kubeconfig 的路径>
export DAY=~/agent-work/td-310-s2/day
mkdir -p "$DAY/src" "$DAY/obj" "$DAY/src5" "$DAY/prev"
q() { f="$DAY/$1"; shift; "$@" > "$f.out" 2> "$f.err"; echo "exit=$?" > "$f.rc"; cat "$f.out" "$f.err" "$f.rc"; }
git fetch origin
git rev-parse origin/main | tee "$DAY/commit.txt"
git archive origin/main k8s/release-freeze scripts/release/freeze_gate.py scripts/release/freeze_lift.sh | tar -x -C "$DAY/src"
shasum -a 256 "$DAY/src/scripts/release/freeze_gate.py" | tee "$DAY/gate.sha"
```

`commit.txt` 里应当是统筹方事先报的那个提交（准备片已经合并，两个 Task 文件还没有进 `main`）；`gate.sha` 应当是统筹方事先报的那个摘要——送进探针 Pod 的就是这一份、复核过的程序。应用和运行的一律是 `$DAY/src` 里这份导出，不是工作树里的文件（工作树是多个会话共用的）。再生成步 2、步 3 要用的 11 个对象，和步 4 探针的两份清单：

```
python3 - "$DAY/obj" <<'PY'
import pathlib, sys
out = pathlib.Path(sys.argv[1])
SPEC = '  who: owner\n  reason: admission probe\n  at: "2026-01-01T00:00:00Z"\n'
OWNER = '  ownerReferences:\n  - {apiVersion: v1, kind: Namespace, name: cicd, uid: 00000000-0000-0000-0000-000000000001}\n'
def rec(name, meta="", spec=SPEC):
    return "apiVersion: release.bifrost.io/v1\nkind: Freeze\nmetadata:\n  name: " + name + "\n" + meta + ("spec:\n" + spec if spec else "")
one = "freeze-" + "1" * 32
files = {
    "probe": rec("freeze-" + "0" * 32, spec=SPEC + "  via: probe\n"),
    "c-compliant": rec(one),
    "d-ownerref": rec(one, OWNER),
    "e-finalizer": rec(one, "  finalizers: [release.bifrost.io/probe]\n"),
    "f-label": rec(one, "  labels: {probe: x}\n"),
    "g-annotation": rec(one, "  annotations: {probe: x}\n"),
    "h-generatename": rec(one, "  generateName: freeze-\n"),
    "i-badname": rec("freeze-xyz"),
    "j-nospec": rec(one, spec=""),
    "k-noreason": rec(one, spec='  who: owner\n  at: "2026-01-01T00:00:00Z"\n'),
    "l-ownerref-real": rec("freeze-" + "2" * 32, OWNER),
    "probe-sa": "apiVersion: v1\nkind: ServiceAccount\nmetadata:\n  name: NAME\n  namespace: cicd\nautomountServiceAccountToken: false\n",
    "probe-pod": ("apiVersion: v1\nkind: Pod\nmetadata:\n  name: NAME\n  namespace: cicd\nspec:\n  serviceAccountName: NAME\n"
                  "  automountServiceAccountToken: true\n  restartPolicy: Never\n  activeDeadlineSeconds: 180\n  containers:\n  - name: read\n"
                  "    image: python:3.11-slim-bookworm\n    command: [\"python3\", \"-\", \"--explain\"]\n    stdin: true\n    stdinOnce: true\n"),
}
for name, text in files.items():
    (out / (name + ".yaml")).write_text(text, encoding="utf-8")
print(len(files), "files written to", out.name)
PY
```

预期印 `13 files written to obj`。最后写下步 4 的探针脚本（定文；它做什么见步 4）：

```
cat > "$DAY/probe.sh" <<'EOF'
#!/bin/bash
# One real read by the strict gate, in a Pod under a ServiceAccount made for this run and removed by it.
# usage: KUBECONFIG=<the Owner's> DAY=<the day's directory> bash probe.sh refused|clear
set -u
trap '' PIPE
want="${1:-}"
case "$want" in refused|clear) ;; *) echo "probe: usage: probe.sh refused|clear"; exit 2 ;; esac
: "${KUBECONFIG:?probe: KUBECONFIG is not set}"
: "${DAY:?probe: DAY is not set}"
ns=cicd
name="freeze-probe-$(date -u +%H%M%S)-$$"
gate="$DAY/src/scripts/release/freeze_gate.py"
out="$DAY/$name.out"
log="$DAY/s4-probe-$want.txt"
say() { echo "$@" >> "$log"; echo "$@"; }
uid_re='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
sa_uid=""
pod_uid=""
attach_s="${PROBE_ATTACH_SECONDS:-45}"
[ -s "$gate" ] || { echo "probe: FAILED ($gate is missing)"; exit 2; }
[ -s "$DAY/obj/probe-sa.yaml" ] && [ -s "$DAY/obj/probe-pod.yaml" ] || { echo "probe: FAILED (the two manifests are missing)"; exit 2; }

remove() {  # remove <resource> <uid>: delete only the object this run created, by its UID
  printf '{"kind":"DeleteOptions","apiVersion":"v1","gracePeriodSeconds":0,"preconditions":{"uid":"%s"}}' "$2" \
    | kubectl --request-timeout=30s delete --raw "/api/v1/namespaces/$ns/$1/$name" -f - >/dev/null 2>>"$out.err"
}
cleanup() {
  trap - EXIT INT TERM
  if [ -n "$pod_uid" ]; then remove pods "$pod_uid"; say "probe: pod $name delete exit=$?"; fi
  if [ -n "$sa_uid" ]; then remove serviceaccounts "$sa_uid"; say "probe: serviceaccount $name delete exit=$?"; fi
}
trap cleanup EXIT
trap 'say "probe: interrupted"; exit 130' INT TERM

sa_uid=$(sed "s/NAME/$name/g" "$DAY/obj/probe-sa.yaml" | kubectl --request-timeout=30s create -f - -o jsonpath='{.metadata.uid}' 2>>"$out.err")
rc=$?
say "probe: serviceaccount $name create exit=$rc uid=[$sa_uid]"
if [ "$rc" -ne 0 ] || ! printf '%s' "$sa_uid" | grep -Eq "$uid_re"; then sa_uid=""; say "probe: FAILED (the ServiceAccount was not created; nothing else was attempted)"; exit 1; fi

pod_uid=$(sed "s/NAME/$name/g" "$DAY/obj/probe-pod.yaml" | kubectl --request-timeout=30s create -f - -o jsonpath='{.metadata.uid}' 2>>"$out.err")
rc=$?
say "probe: pod $name create exit=$rc uid=[$pod_uid]"
if [ "$rc" -ne 0 ] || ! printf '%s' "$pod_uid" | grep -Eq "$uid_re"; then pod_uid=""; say "probe: FAILED (the Pod was not created)"; exit 1; fi

kubectl --request-timeout=130s -n "$ns" wait --for=condition=Ready "pod/$name" --timeout=120s >>"$out.err" 2>&1
rc=$?
say "probe: wait exit=$rc"
if [ "$rc" -ne 0 ]; then say "probe: FAILED (the Pod did not become ready in 120 s)"; exit 1; fi

kubectl -n "$ns" attach -q -i "$name" -c read < "$gate" > "$out" 2>>"$out.err" &
apid=$!
( sleep "$attach_s"; kill "$apid" 2>/dev/null ) >/dev/null 2>&1 &
wpid=$!
wait "$apid"
rc=$?
kill "$wpid" 2>/dev/null
say "probe: attach exit=$rc"
cat "$out" >> "$log"
cat "$out"

code=""
i=0
while [ "$i" -lt 10 ]; do
  code=$(kubectl --request-timeout=20s -n "$ns" get pod "$name" -o jsonpath='{.status.containerStatuses[0].state.terminated.exitCode}' 2>>"$out.err")
  [ -n "$code" ] && break
  i=$((i + 1))
  sleep 2
done
say "probe: container exit=[$code]"

first=$(head -n 1 "$out")
verdict=$(grep -m1 '^explain: verdict=' "$out" | cut -d= -f2)
if [ "$want" = clear ]; then
  if [ "$code" = 0 ] && [ "$first" = "未冻结：0 条记录" ] && [ "$verdict" = clear ] \
     && grep -qx 'explain: request=GET /apis/release.bifrost.io/v1/freezes HTTP/1.1' "$out" \
     && grep -qx 'explain: host=kubernetes.default.svc' "$out" \
     && grep -qx 'explain: issuer_in_ca_file=yes' "$out"; then
    say "probe: ok (clear)"; exit 0
  fi
else
  case "$first" in "拒绝：读不到冻结状态（"*) refused=1 ;; *) refused=0 ;; esac
  if [ "$code" = 1 ] && [ "$refused" = 1 ] && [ "$verdict" = unreadable ]; then
    say "probe: ok (refused)"; exit 0
  fi
fi
say "probe: FAILED (wanted $want; first line [$first], verdict [$verdict], container exit [$code])"
exit 1
EOF
```

**步 0**

0-1　命令（原表步 1 的试算，挪到最前）。当天第一条集群命令：

```
q s0-1 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" apply --dry-run=server -f "$DAY/src/k8s/release-freeze/crd.yaml"
```

预期末行 `exit=0`，上面是 `customresourcedefinition.apiextensions.k8s.io/freezes.release.bifrost.io created (server dry run)`。被拒就是 schema 有问题：什么都没改，当天到此为止。

0-2　命令（写法实测，10-12 的输出就是预期）。旧对象的完整形状，不只看 `data`：

```
q s0-2 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" -n cicd get configmap bifrost-release-freeze -o json > /dev/null; cat "$DAY/s0-2.rc"
python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); print("data=%s immutable=%s other=%s" % (json.dumps(o.get("data"), sort_keys=True), o.get("immutable"), sorted(k for k in o if k not in ("apiVersion", "kind", "metadata", "data"))))' "$DAY/s0-2.out"
```

预期 `exit=0`，然后 `data={"frozen": "false"} immutable=None other=[]`。`immutable` 不是 `None`，或者 `other` 里有东西：停——不可变的旧对象之后写不成墓碑。

0-3　命令：

```
q s0-3 scripts/release/release.sh window
```

预期 `no release window open (ConfigMap cicd/bifrost-release-window)` 和 `exit=0`。

0-4　Owner 自己看。看的是第一条印出的 `Username` 和 `Groups` 两行（假定是 `system:admin` 和带 `system:masters` 的一组，以印出来的为准），末行应当是 `exit=0`；两行留在 `$DAY/s0-4.out`。用户名由他填进第二条：

```
q s0-4 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" auth whoami
export OWNER_NAME='<上一条 Username 那一行的值>'
printf '%s\n' "$OWNER_NAME" | grep -Ex '[A-Za-z0-9:._@-]+'
```

第三条原样印出这个名字。什么都不印，说明名字里有下一格的渲染处理不了的字符：停。

0-5　命令，新（写法实测，用 `system:admin` 试的）。渲染填好的副本，看差异：

```
sed "s/'OWNER_USERNAME'/'$OWNER_NAME'/" "$DAY/src/k8s/release-freeze/admission.yaml" > "$DAY/admission.filled.yaml"
q s0-5 diff "$DAY/src/k8s/release-freeze/admission.yaml" "$DAY/admission.filled.yaml"
grep -c '^[<>]' "$DAY/s0-5.out"
grep -c OWNER_USERNAME "$DAY/admission.filled.yaml"
```

预期第二条末行是 `exit=1`——`diff` 找到差异时的退出码就是 1；0 说明什么都没换，2 说明出错，都算不符。差异正好两处，`17c17` 和 `44c44`，每处一行换一行，变的只有引号里的名字。后两条依次印 `4` 和 `1`（剩下的那一处是第 2 行的注释）。副本只在 `$DAY` 里，不进仓库。

0-6　Owner 自己看。看的是：这台集群认哪些身份来源——控制面节点（实测 10-12 只有 `ubt-k3s-01` 一台）上 k3s 服务端的认证设置里，除了客户端证书还有没有别的（静态令牌文件、OIDC、认证 webhook）；他这张管理员 kubeconfig 还有哪些副本、在谁手里。本文给不出命令：这些设置在节点上，只读身份看不到，哪个文件或启动参数带着它们没有量过。记在 `$DAY/s0-owner.txt`，一项一行：看了什么，结论是什么。

0-7　命令（统筹方用只读身份跑；10-12 跑过，输出就是预期）：附录末尾重算的那三条。预期第一条印 `exit=0`，第二条印 13 行，第三条印 `13`，其中 `impersonate` 四行：`cicd/argocd-application-controller`、`group:system:masters`、`kube-system/helm-traefik`、`kube-system/helm-traefik-crd`。多出一行就停。

**步 1**

1-1　命令：

```
q s1-1 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" apply -f "$DAY/src/k8s/release-freeze/crd.yaml"
```

预期 `customresourcedefinition.apiextensions.k8s.io/freezes.release.bifrost.io created` 和 `exit=0`。

1-2　命令（写法实测）：

```
q s1-2 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get crd freezes.release.bifrost.io -o jsonpath='{.status.conditions[?(@.type=="Established")].status}{"\n"}'
```

预期 `True` 和 `exit=0`。空着不算。

1-3　命令，新（写法实测）：

```
q s1-3 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" api-resources --api-group=release.bifrost.io
grep -c -E '^freezes +release\.bifrost\.io/v1 +false +Freeze$' "$DAY/s1-3.out"
```

预期第一条末行 `exit=0`，第二条印 `1`：类型在，不分命名空间。

原表里「这一步不做空 LIST 的真读」不是一格检查，并进步 4。

**步 2**

2-1、2-2　命令。先试算，再应用，都是步 0 渲染的那份副本：

```
q s2-1 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" apply --dry-run=server -f "$DAY/admission.filled.yaml"
q s2-2 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" apply -f "$DAY/admission.filled.yaml"
grep -c 'created (server dry run)$' "$DAY/s2-1.out"
grep -c 'created$' "$DAY/s2-2.out"
```

预期前两条末行都是 `exit=0`，各印四行：两条 `validatingadmissionpolicy.admissionregistration.k8s.io/…` 和两条 `validatingadmissionpolicybinding.admissionregistration.k8s.io/…`，名字是 `bifrost-release-records` 和 `bifrost-release-freeze-tombstone`。后两条都印 `4`。

2-3　命令（写法实测，对现有 6 条策略跑过）：

```
q s2-3 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get validatingadmissionpolicy bifrost-release-records bifrost-release-freeze-tombstone -o jsonpath='{range .items[*]}{.metadata.name}{" generation="}{.metadata.generation}{" observed="}{.status.observedGeneration}{" warnings="}{.status.typeChecking.expressionWarnings}{"\n"}{end}'
```

预期 `exit=0` 和两行 `<名字> generation=1 observed=1 warnings=`。`observed=` 后面是空的就等几秒再跑。`warnings=` 后面有内容：照上表步 2 的修订办——警告的原文已经留在 `$DAY/s2-3.out`，记成一条待核实的事，继续做下面的探针，由探针判；事后由统筹方逐条说明它是动态类型的推断警告还是真错（第 13 节的表）。

2-4　命令。九次服务端试算，每次的结果各存一份：

```
for f in c-compliant d-ownerref e-finalizer f-label g-annotation h-generatename i-badname j-nospec k-noreason; do echo "== $f"; q "s2-4-$f" kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" create --dry-run=server -f "$DAY/obj/$f.yaml"; done
```

2-5　Owner 自己看（之二）。当天的第一次拒绝，先原样看：

```
cat "$DAY/s2-4-d-ownerref.err"
```

看的是这段报文里有没有策略名 `bifrost-release-records`，有没有 `a release record carries a name and no other metadata` 这一句。两样都在才往下。少一样就停：报文和假定的样式不一样，先照这份原文把 2-6 和 3-16 里要找的字改对，再继续。原文就留在这个文件里。

2-6　命令。判 2-4：

```
cat "$DAY"/s2-4-*.rc | sort | uniq -c
grep -c 'created (server dry run)' "$DAY/s2-4-c-compliant.out"
grep -l 'bifrost-release-records' "$DAY"/s2-4-{d-ownerref,e-finalizer,f-label,g-annotation,h-generatename}.err | wc -l
grep -l 'a release record carries a name and no other metadata' "$DAY"/s2-4-{d-ownerref,e-finalizer,f-label,g-annotation,h-generatename}.err | wc -l
grep -l 'bifrost-release-records' "$DAY"/s2-4-{i-badname,j-nospec,k-noreason}.err | wc -l
grep -l -E 'User ".*" cannot ' "$DAY"/s2-4-*.err | wc -l
grep -c 'name must match' "$DAY/s2-4-i-badname.err"
```

预期第一条印两行：`1 exit=0`（合规的那一次）和 `8 exit=1`——九份结果都在、退出码都对，先看这一条。然后依次是 `1`、`5`、`5`、`0`、`0`、`1`：五种多余的元数据各被记录那条策略拒；名字不合规、缺 `spec`、缺 `reason` 不是被策略拒的，也没有一次是 RBAC 拒的（没有 `User "…" cannot` 那一句）；名字不合规的那一次提到了 CRD 自己的规则。`j-nospec`、`k-noreason` 的报文各看一眼，应当分别提到 `spec` 和 `spec.reason`。

**步 3**

```
PROBE=freeze-00000000000000000000000000000000
ARGO=system:serviceaccount:cicd:argocd-application-controller
ARGOSRV=system:serviceaccount:cicd:argocd-server
GC=system:serviceaccount:kube-system:generic-garbage-collector
```

三个账号名是实测 10-12 的：前两个是 `cicd` 里的 ServiceAccount；第三个是 ClusterRoleBinding `system:controller:generic-garbage-collector` 的主体。垃圾回收器的请求实际用不用这个身份，只读身份量不到；这一格证明的是「以这个身份来的删，准入会拒」。

3-1　命令。真建探针。字段管理者写成平台的名字（实测 10-12：平台写的对象上是 `platform-api`），探针带 `via`，为的是让它的信封尽量像平台将来建的那一条：

```
q s3-1 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" create --field-manager=platform-api -f "$DAY/obj/probe.yaml"
```

预期 `freeze.release.bifrost.io/freeze-00000000000000000000000000000000 created` 和 `exit=0`。

3-2　命令，新。留一份探针刚建出来时的样子，记下 UID，量一次有一条记录的 LIST：

```
q s3-2 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get freeze "$PROBE" -o json > /dev/null; cat "$DAY/s3-2.rc"
python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); m=o["metadata"]; print(json.dumps({"uid": m.get("uid"), "resourceVersion": m.get("resourceVersion"), "generation": m.get("generation"), "labels": m.get("labels"), "annotations": m.get("annotations"), "finalizers": m.get("finalizers"), "ownerReferences": m.get("ownerReferences"), "deletionTimestamp": m.get("deletionTimestamp"), "spec": o.get("spec")}, sort_keys=True))' "$DAY/s3-2.out" | tee "$DAY/s3-2.snap"
PROBE_UID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["metadata"]["uid"])' "$DAY/s3-2.out"); echo "uid=$PROBE_UID"
q s3-2-list kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get --raw /apis/release.bifrost.io/v1/freezes > /dev/null; cat "$DAY/s3-2-list.rc"; wc -c < "$DAY/s3-2-list.out"
```

预期两处 `exit=0`；快照一行，里面 `labels`、`annotations`、`finalizers`、`ownerReferences`、`deletionTimestamp` 都是 `null`，`spec` 是探针的四个字段；UID 是 8-4-4-4-12 的小写十六进制；最后的字节数按信封算是 700 上下（未实测），记作 L1。

3-3 到 3-15　命令。十三次试算，都不改东西：

```
q s3-3 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" patch freeze "$PROBE" --type=merge -p '{"spec":{"reason":"changed"}}' --dry-run=server
q s3-4 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" label freeze "$PROBE" probe=x --dry-run=server
q s3-5 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete freeze "$PROBE" --dry-run=server --as="$ARGO"
q s3-6 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" patch freeze "$PROBE" --type=merge -p '{"spec":{"reason":"changed"}}' --dry-run=server --as="$ARGO"
q s3-7 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete freeze "$PROBE" --dry-run=server --as="$ARGOSRV"
q s3-8 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" patch freeze "$PROBE" --type=merge -p '{"spec":{"reason":"changed"}}' --dry-run=server --as="$ARGOSRV"
q s3-9 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete freeze "$PROBE" --dry-run=server --as="$GC"
q s3-10 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete --raw "/apis/release.bifrost.io/v1/freezes/$PROBE?dryRun=All" --as="$ARGO"
q s3-11 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete --raw '/apis/release.bifrost.io/v1/freezes?dryRun=All' --as="$ARGO"
q s3-12 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete freeze "$PROBE" --cascade=foreground --dry-run=server
q s3-13 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete freeze "$PROBE" --cascade=orphan --dry-run=server
q s3-14 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete freeze "$PROBE" --dry-run=server
q s3-15 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" delete --raw "/apis/release.bifrost.io/v1/freezes/$PROBE?dryRun=All"
```

预期，按行：3-3、3-4（Owner 改 `spec`、加标签）被记录那条策略拒，`a release record is never updated`；3-5（Argo 控制器删）拒，`only the Owner removes a release record, with a plain delete`；3-6（新，Argo 控制器改）拒，`never updated`；3-7、3-8（新，`argocd-server` 删、改）拒，同上两句；3-9（垃圾回收器删）拒；3-10（Argo 控制器不带请求体的原始 DELETE）拒；3-11（Argo 控制器对整类的原始 DELETE）拒；3-12、3-13（Owner 前台删除、孤儿式删除）拒；3-14（Owner 普通删除）放行，印 `freeze.release.bifrost.io "freeze-00000000000000000000000000000000" deleted (server dry run)`；3-15（Owner 不带请求体的原始 DELETE）放行，印一段 JSON——这一格证明规则里 `options` 缺省的那一支不是求值出错。被拒的十一行末尾是 `exit=1`，放行的两行是 `exit=0`。

3-16　命令，新。判上面十三行，并拿探针和 3-2 留的样子比：

```
cat "$DAY"/s3-{3,4,5,6,7,8,9,10,11,12,13}.rc | sort | uniq -c
cat "$DAY"/s3-{14,15}.rc | sort | uniq -c
grep -l 'bifrost-release-records' "$DAY"/s3-{3,4,5,6,7,8,9,10,11,12,13}.err | wc -l
grep -l 'a release record is never updated' "$DAY"/s3-{3,4,6,8}.err | wc -l
grep -l 'only the Owner removes a release record, with a plain delete' "$DAY"/s3-{5,7,9,10,11,12,13}.err | wc -l
grep -l -E 'User ".*" cannot ' "$DAY"/s3-{3,4,5,6,7,8,9,10,11,12,13}.err | wc -l
q s3-16 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get freeze "$PROBE" -o json > /dev/null; cat "$DAY/s3-16.rc"
python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); m=o["metadata"]; print(json.dumps({"uid": m.get("uid"), "resourceVersion": m.get("resourceVersion"), "generation": m.get("generation"), "labels": m.get("labels"), "annotations": m.get("annotations"), "finalizers": m.get("finalizers"), "ownerReferences": m.get("ownerReferences"), "deletionTimestamp": m.get("deletionTimestamp"), "spec": o.get("spec")}, sort_keys=True))' "$DAY/s3-16.out" > "$DAY/s3-16.snap"
cmp "$DAY/s3-2.snap" "$DAY/s3-16.snap" && echo same
```

预期依次是：`11 exit=1`；`2 exit=0`；`11`；`4`；`7`；`0`；`exit=0`；最后一条印 `same`——`resourceVersion`、`generation`、元数据和 `spec` 都和刚建出来时一样，探针没被动过。第六个数不是 0，说明有一次是被 RBAC 而不是被准入拒的：不算，停。

3-17　命令。真建一条带属主引用的，等两分钟，再列：

```
q s3-17 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" create -f "$DAY/obj/l-ownerref-real.yaml"
grep -c 'a release record carries a name and no other metadata' "$DAY/s3-17.err"
sleep 120
q s3-17-list kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get freezes.release.bifrost.io -o name
```

预期第一条末行 `exit=1`，第二条印 `1`；最后一条印一行 `freeze.release.bifrost.io/freeze-00000000000000000000000000000000` 和 `exit=0`，没有第二个名字。

3-18　命令，新。带一个错的 UID 去删。这是一次真的删除请求，预期被拒：

```
q s3-18 "$DAY/src/scripts/release/freeze_lift.sh" "$PROBE" 00000000-0000-0000-0000-000000000000
q s3-18-get kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get freeze "$PROBE" -o jsonpath='{.metadata.uid}{"\n"}'
```

预期第一条末行 `exit=1`，报文是冲突（409，`Conflict`）；第二条印出 3-2 记下的那个 UID 和 `exit=0`。第二条报 `NotFound`，说明 apiserver 没有认 UID 前置条件：停，3.4 的 `unfreeze` 要回设计。

3-19　命令。带对的 UID 真删，再读一次空的 LIST：

```
q s3-19 "$DAY/src/scripts/release/freeze_lift.sh" "$PROBE" "$PROBE_UID" > /dev/null; cat "$DAY/s3-19.rc"
q s3-19-list kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get --raw /apis/release.bifrost.io/v1/freezes
wc -c < "$DAY/s3-19-list.out"
```

预期第一条 `exit=0`；第二条印 `{"apiVersion":"release.bifrost.io/v1","items":[],"kind":"FreezeList","metadata":{"continue":"","resourceVersion":"<一串数字>"}}` 和 `exit=0`；第三条印 126（`resourceVersion` 是八位数字时），记作 L0。L0 不超过 150；L1 − L0 − 25 是这条探针除三个字段的内容之外占的字节数（25 是 `owner`、`admission probe`、`probe` 三段内容的长度），按信封算是 549，应当不超过 600。**这只是对 E 的一次估计，不是签收**：探针是 `kubectl` 发的，平台自己的请求第一次真实出现是步 10 演练里平台建的第一条记录，E 在那里量、在那里签收（3.4）。这里超过 600 就停，先把 E 调大。

**这一建一删通过之前，什么都不接线。**

**步 4**

之二，统筹方的裁定：步 4 不在平台账号或 applier 账号的身份下起 Pod——那样的 Pod 带着那个账号能做的一切，清单定文管得住程序做什么，管不住凭证能做什么。原来这一步要证的两件事拆开：

- **四个身份各自读得到新类型**：由 Owner 用 `kubectl auth can-i list … --as=…` 问四次，每次的答案必须正好是 `yes`（4-5）。
- **严格读的程序经集群里的 CA 从真实的 apiserver 读到一份属于 L 的应答**：只做一次真读（4-8），Pod 的身份是这一格自己新建的一个 ServiceAccount。它建在 `cicd`，建出来时什么权限都没有；`rbac-list.yaml` 应用之后，它和 `cicd` 里每个账号一样，经那份绑定里的组得到 `list`，别的什么都没有（实测 10-12：集群上没有一条绑定把权限给 ServiceAccount 的组，只有 `system:authenticated` 和 `system:serviceaccounts` 的那几条发现类的只读规则）。所以这个探针账号没有属于它自己的绑定：给它 `list` 的就是 `rbac-list.yaml` 那一条，读完删掉账号即可。这和裁定的字面差一处——裁定写的是给它单独绑一条、读完连绑定一起删；在 `cicd` 里那一条是多余的，不建它就少建、少删一个集群级的 RBAC 对象，而且这次读顺带证明了「`cicd` 里新来的账号不用另外授权就读得到」（3.1 那张表的本意）。统筹方要照字面办的话，改法是 `probe.sh` 在建账号之后多建一条指向 `bifrost-release-freeze-list` 的 ClusterRoleBinding，同样按 UID 删，4-9 的查法不变。账号自己关掉令牌的自动挂载，只有探针 Pod 的清单点名打开。

另有一次**预期被拒的读**（4-1），排在应用 `rbac-list.yaml` 之前，用的是同一套做法、另一个新建的探针账号，那时它什么权限都没有：读到 403，程序印拒绝、以 1 退出。它先把这套做法在什么都还没应用的时候走一遍，也是第 8 节 S2「都不放行」那半句落的四处之一。

探针的两份清单是定文（`$DAY/obj/probe-sa.yaml`、`probe-pod.yaml`，`NAME` 由脚本换成这一次生成的名字）：

```
apiVersion: v1
kind: ServiceAccount
metadata:
  name: NAME
  namespace: cicd
automountServiceAccountToken: false
---
apiVersion: v1
kind: Pod
metadata:
  name: NAME
  namespace: cicd
spec:
  serviceAccountName: NAME
  automountServiceAccountToken: true
  restartPolicy: Never
  activeDeadlineSeconds: 180
  containers:
  - name: read
    image: python:3.11-slim-bookworm
    command: ["python3", "-", "--explain"]
    stdin: true
    stdinOnce: true
```

`probe.sh`（「先做」那一段写下的定文）一次做这些事，每一步的退出码都印出来并记进 `$DAY/s4-probe-<refused 或 clear>.txt`：生成一个不重复的名字（`freeze-probe-<时分秒>-<进程号>`）；建账号，记下它的 UID，建不出来就立刻停，什么都不再做；建 Pod，记下 UID，建不出来就停并删掉刚建的账号；等 Pod 起来，最多 120 秒；把 `freeze_gate.py` 从标准输入送进去，最多 45 秒，到时间就掐断；取容器的退出码；判。不管从哪里退出——判完、出错、被 Ctrl-C 或终止信号打断——它都先带着记下的 UID 去删 Pod、再删账号：UID 对不上的同名对象它不碰，只删这一次自己建出来的。Pod 自己还有 180 秒的寿命上限，脚本没来得及删它也活不过这个数。镜像和检查任务用的一样，仍是可变标签；Pod 里的凭证只读得到这一个（此刻是空的）类型，所以这里不靠镜像摘要设防。

**这一步不再证明的（之二）：** 读在每一个真实的工作负载里走得通。两个流水线账号在真实的 Tekton 步骤 Pod 里读得通，改由步 5 的 5-4、5-5 证明（比原来晚：原来在换 Task 之前）；平台账号在平台 Pod 里、用 Go 读函数读得通，改由 S3b 在 STG 上的验收证明（D10）。

4-1　命令，新。应用 `rbac-list.yaml` 之前，预期被拒的一次读：

```
KUBECONFIG="$BIFROST_OWNER_KUBECONFIG" bash "$DAY/probe.sh" refused
```

预期印出的行里依次有：`probe: serviceaccount freeze-probe-… create exit=0 uid=[…]`；`probe: pod freeze-probe-… create exit=0 uid=[…]`；`probe: wait exit=0`；`probe: attach exit=0`；程序的输出，第一行 `拒绝：读不到冻结状态（HTTP 403），按冻结处理`；`probe: container exit=[1]`；`probe: ok (refused)`；`probe: pod freeze-probe-… delete exit=0`；`probe: serviceaccount freeze-probe-… delete exit=0`。出现 `probe: FAILED` 就停；两条 `delete exit=` 有一条不是 0，先做 4-2 看留下了什么。这一格只在 `rbac-list.yaml` 还没有应用时做得出「被拒」：当天是重做、而它上一次已经应用了的话，跳过 4-1 和 4-2，在 `$DAY/s0-owner.txt` 里记一行原因（第 8 节 S2「都不放行」落的四处那时只剩前三处）。

4-2　命令，新（写法实测，10-12 的输出就是预期）。查探针的 Pod 和账号都没有留下，也没有一条绑定点它的名：

```
q s4-2 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" -n cicd get pods,serviceaccounts -o name > /dev/null; cat "$DAY/s4-2.rc"
grep -c 'freeze-probe-' "$DAY/s4-2.out"
q s4-2b kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get clusterrolebindings,rolebindings -A -o json > /dev/null; cat "$DAY/s4-2b.rc"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))["items"]; print("bindings=%d naming-a-probe=%d" % (len(d), sum(1 for b in d for s in (b.get("subjects") or []) if s.get("name", "").startswith("freeze-probe-"))))' "$DAY/s4-2b.out"
```

预期两处 `exit=0`；第二条印 `0`；第四条印 `bindings=<两百来条> naming-a-probe=0`。`exit` 不是 0 时后面的数不算数：先把查询跑通。留下了东西，就照 `s4-probe-refused.txt` 里记的名字和 UID 手工删掉，再查一遍。手工删也只删这一格自己建的：先 `kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" -n cicd get pod <名字> -o jsonpath='{.metadata.uid}'`，印出的 UID 和记下的相同，才 `kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" -n cicd delete pod <名字>`；账号同样两条，把 `pod` 换成 `serviceaccount`。UID 不同就不删，停下来报给统筹方。

4-3　命令：

```
q s4-3a kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" apply --dry-run=server -f "$DAY/src/k8s/release-freeze/rbac-list.yaml"
q s4-3b kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" apply -f "$DAY/src/k8s/release-freeze/rbac-list.yaml"
```

预期各两行：`clusterrole.rbac.authorization.k8s.io/bifrost-release-freeze-list` 和 `clusterrolebinding.rbac.authorization.k8s.io/bifrost-release-freeze-list`，先 `created (server dry run)`，后 `created`；两条末行都是 `exit=0`。

4-4　命令。15 个身份 × 8 个动词，每一问的答案和退出码都留下：

```
for who in system:serviceaccount:cicd:argocd-application-controller system:serviceaccount:cicd:argocd-applicationset-controller system:serviceaccount:cicd:argocd-dex-server system:serviceaccount:cicd:argocd-notifications-controller system:serviceaccount:cicd:argocd-redis system:serviceaccount:cicd:argocd-repo-server system:serviceaccount:cicd:argocd-server system:serviceaccount:cicd:bifrost-applier system:serviceaccount:cicd:default system:serviceaccount:cicd:tekton-deliver system:serviceaccount:cicd:tekton-pipelinerun-ttl system:serviceaccount:cicd:tekton-trigger system:serviceaccount:bifrost-platform-prod:bifrost-platform system:serviceaccount:bifrost-platform-stg:bifrost-platform system:serviceaccount:bifrost-access:bifrost-agent; do for verb in list create get watch update patch delete deletecollection; do a=$(kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" auth can-i "$verb" freezes.release.bifrost.io --as="$who" 2>>"$DAY/s4-4.err"); echo "$who $verb answer=[$a] exit=$?"; done; done > "$DAY/s4-4.out"
wc -l < "$DAY/s4-4.out"
grep -c -E ' answer=\[yes\] exit=0$| answer=\[no\] exit=1$' "$DAY/s4-4.out"
grep -c ' list answer=\[yes\] exit=0$' "$DAY/s4-4.out"
grep -v ' list ' "$DAY/s4-4.out" | grep ' answer=\[yes\]'
```

`can-i` 答 `yes` 时退出码是 0，答 `no` 时是 1；别的组合——空的答案、别的退出码——都是这一问没问成。预期后四条依次是 `120`；`120`（每一行都是问成了的 `yes` 或 `no`）；`15`；和正好这 10 行：`system:serviceaccount:cicd:argocd-application-controller` 接 `create`、`get`、`watch`、`update`、`patch`、`delete`、`deletecollection` 各一行，`system:serviceaccount:cicd:argocd-server` 接 `get`、`patch`、`delete` 各一行，每行以 `answer=[yes] exit=0` 结尾。第二个数不是 120 就看 `s4-4.out` 里是哪一问、看 `s4-4.err` 里的原因，问成了再判。那 10 行多一行、少一行都停。循环的写法用替身试过。

4-5　命令，新（之二）。原来要真读的四个身份，各问一次能不能 `list`：

```
for who in system:serviceaccount:cicd:bifrost-applier system:serviceaccount:cicd:default system:serviceaccount:bifrost-platform-prod:bifrost-platform system:serviceaccount:bifrost-platform-stg:bifrost-platform; do a=$(kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" auth can-i list freezes.release.bifrost.io --as="$who" 2>>"$DAY/s4-5.err"); echo "$who answer=[$a] exit=$?"; done | tee "$DAY/s4-5.out"
grep -c ' answer=\[yes\] exit=0$' "$DAY/s4-5.out"
```

预期印四行，每行以 `answer=[yes] exit=0` 结尾；第二条印 `4`。

4-6　命令：

```
q s4-6 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get clusterrole bifrost-release-freeze-list -o json > /dev/null; cat "$DAY/s4-6.rc"
python3 -c 'import json,sys; o=json.load(open(sys.argv[1])); print("labels=%s aggregationRule=%s rules=%s" % (o["metadata"].get("labels"), o.get("aggregationRule"), json.dumps(o.get("rules"), sort_keys=True)))' "$DAY/s4-6.out"
```

预期 `exit=0`，然后 `labels=None aggregationRule=None rules=[{"apiGroups": ["release.bifrost.io"], "resources": ["freezes"], "verbs": ["list"]}]`。另一个新角色步 9 才有，到那时用同样的两条查。

4-7　命令（写法实测，10-12 的输出就是预期）：

```
q s4-7 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get clusterrole admin edit view -o yaml > /dev/null; cat "$DAY/s4-7.rc"
grep -c -E '^    name: (admin|edit|view)$' "$DAY/s4-7.out"
grep -c 'release.bifrost.io' "$DAY/s4-7.out"
```

预期 `exit=0`，然后 `3`（三个角色都读到了），然后 `0`。

4-8　命令。唯一的一次真读，身份是这一格新建的探针账号：

```
KUBECONFIG="$BIFROST_OWNER_KUBECONFIG" bash "$DAY/probe.sh" clear
```

预期印出的行里依次有：两条 `create exit=0`；`probe: wait exit=0`；`probe: attach exit=0`；程序的输出——第一行 `未冻结：0 条记录`，然后 `explain: namespace=cicd`、`explain: request=GET /apis/release.bifrost.io/v1/freezes HTTP/1.1`、`explain: host=kubernetes.default.svc`、`explain: ca_file=/var/run/secrets/kubernetes.io/serviceaccount/ca.crt`、一行或几行 `explain: ca_subject=…`、`explain: peer_issuer=…`（10-11 对 apiserver 握手量到的签发者是 `CN=k3s-server-ca@1781402855`）、`explain: issuer_in_ca_file=yes`、`explain: verdict=clear`；`probe: container exit=[0]`；`probe: ok (clear)`；两条 `delete exit=0`。出现 `probe: FAILED` 就停：真实的应答不在 3.2 收窄的语言里，或者 CA、主机名对不上，这不是现场能修的。

4-9　命令，新（写法实测）。和 4-2 一样的四条，文件名换成 `s4-9`、`s4-9b`：

```
q s4-9 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" -n cicd get pods,serviceaccounts -o name > /dev/null; cat "$DAY/s4-9.rc"
grep -c 'freeze-probe-' "$DAY/s4-9.out"
q s4-9b kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" get clusterrolebindings,rolebindings -A -o json > /dev/null; cat "$DAY/s4-9b.rc"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1]))["items"]; print("bindings=%d naming-a-probe=%d" % (len(d), sum(1 for b in d for s in (b.get("subjects") or []) if s.get("name", "").startswith("freeze-probe-"))))' "$DAY/s4-9b.out"
```

预期两处 `exit=0`、`0`、`naming-a-probe=0`：探针的 Pod 和账号都没了，也没有一条绑定点它的名。

集群升级之后、下一次发布之前，4-8 要重跑。只核对 `kubectl` 印出的正文不算。

**步 5**

5-0　命令，新（统筹方做，不是 Owner）。步 4 通过之后，把复核过的那个提交推上 `main`：

```
scripts/release/release.sh window && git push origin <复核过的 40 位提交>:refs/heads/main
```

5-1　命令，新（写法实测）。导出当天的 `main`：

```
git fetch origin
git rev-parse origin/main | tee "$DAY/commit5.txt"
git archive origin/main k8s/cicd/tekton/task-release-freeze-check.yaml k8s/cicd/tekton/task-release-window.yaml scripts/release/freeze_gate.py | tar -x -C "$DAY/src5"
cmp "$DAY/src/scripts/release/freeze_gate.py" "$DAY/src5/scripts/release/freeze_gate.py" && echo same
```

预期 `commit5.txt` 是统筹方刚推的那个提交；最后一条印 `same`（步 4 真读用的程序和要装进 Task 的是同一份）。

5-2　命令：

```
q s5-2a kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" apply --dry-run=server -f "$DAY/src5/k8s/cicd/tekton/task-release-freeze-check.yaml" -f "$DAY/src5/k8s/cicd/tekton/task-release-window.yaml"
q s5-2b kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" apply -f "$DAY/src5/k8s/cicd/tekton/task-release-freeze-check.yaml" -f "$DAY/src5/k8s/cicd/tekton/task-release-window.yaml"
```

预期各两行：`task.tekton.dev/bifrost-release-freeze-check configured` 和 `task.tekton.dev/bifrost-release-window configured`（试算那次后面带 `(server dry run)`）；两条末行都是 `exit=0`。

5-3　命令（`jsonpath` 写法实测，对现网的旧 Task 跑过）：

```
q s5-3 kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" -n cicd get task bifrost-release-freeze-check -o jsonpath='{.spec.steps[0].script}' > /dev/null; cat "$DAY/s5-3.rc"
shasum -a 256 < "$DAY/s5-3.out"
shasum -a 256 < "$DAY/src5/scripts/release/freeze_gate.py"
```

预期 `exit=0`，后两行的十六进制相同，也和 `$DAY/gate.sha` 里的相同。

5-4　命令（统筹方做）。发起一次试算 run：平台动作 `plan_manifest`，`repo` 填 `bifrost-trade-infra`，`path` 填 `k8s/cicd/tekton/task-release-freeze-check.yaml`，`commit` 填 `commit5.txt` 里的提交。它返回 run 的名字。然后用只读身份看（第二条的写法实测；只读身份在 `cicd` 有读日志的权限，实测 10-12，第三条本身没跑过）：

```
RUN=<plan_manifest 返回的名字>
kubectl -n cicd get taskruns -l "tekton.dev/pipelineRun=$RUN,tekton.dev/pipelineTask=freeze-check" -o jsonpath='{range .items[*]}{.metadata.name}{" succeeded="}{.status.conditions[?(@.type=="Succeeded")].status}{" passed_cut_at="}{.status.results[?(@.name=="passed_cut_at")].value}{" pod="}{.status.podName}{" sa="}{.spec.serviceAccountName}{"\n"}{end}' > "$DAY/s5-4.out"; echo "exit=$?"; cat "$DAY/s5-4.out"
kubectl -n cicd logs <上一条印出的 pod> -c step-check > "$DAY/s5-4.log"; echo "exit=$?"; head -n 1 "$DAY/s5-4.log"
```

预期第二条印 `exit=0` 和一行 `…-freeze-check succeeded=True passed_cut_at=<一个 UTC 时刻> pod=… sa=bifrost-applier`；第三条印 `exit=0` 和 `未冻结：0 条记录`。这是 `bifrost-applier` 的真实步骤 Pod 里的一次真读。

5-5　命令（统筹方做；之二）。用的是平台的 STG 发布：流水线 `bifrost-deliver-platform`，账号 `default`，`revision` 不填就是 `main`（`k8s/cicd/tekton/pipeline-deliver-platform.yaml:5–31`）。经平台动作 `start_pipeline_run` 起（B 级），窗口照 `docs/RELEASE.md`「发布窗口」一节先持有。选它的理由：留存的 run 里 `cicd` 的发布和构建流水线都跑在 `default` 下（实测 10-12），平台的 STG 是其中紧接着 S3 还要再发的那一条。起之前先看它会带上去什么（前两条的写法实测 10-12：最近一次成功的 run 克隆的是平台的 `17136ba`，平台的 `main` 当时在 `832fd90`，差 14 个提交）：

```
kubectl -n cicd get pipelineruns -l tekton.dev/pipeline=bifrost-deliver-platform --sort-by=.metadata.creationTimestamp -o jsonpath='{range .items[*]}{.metadata.name}{" "}{.status.conditions[?(@.type=="Succeeded")].status}{"\n"}{end}' > "$DAY/s5-5-runs.out"; echo "exit=$?"; grep ' True$' "$DAY/s5-5-runs.out" | tail -n 1
kubectl -n cicd get taskruns -l "tekton.dev/pipelineRun=<上一条印出的 run>,tekton.dev/pipelineTask=clone-platform" -o jsonpath='{.items[0].status.results[?(@.name=="commit")].value}{"\n"}' > "$DAY/s5-5-deployed.out"; echo "exit=$?"; cat "$DAY/s5-5-deployed.out"
git -C ../bifrost-platform ls-remote origin refs/heads/main
```

前两条各印一行 `exit=0`。后两条印出的提交相同：这次发布不带任何代码改动，只是把同一个提交重新构建、重新滚动一遍。不相同：它是一次真的平台 STG 发布，带上去的是这两个提交之间的全部改动——先把它们列出来（`git -C ../bifrost-platform fetch origin`，再 `git -C ../bifrost-platform log --oneline <前一个>..<后一个>`），按平常的平台 STG 验收看过，再起；或者等这些改动按平常的节奏先发上 STG，再做这一格。

这次发布的副作用（读流水线文件得出，第 34–147 行）：同步一次 Gitea 镜像；构建两个镜像并推到**可变标签** `…/bifrost-platform-api:stg` 和 `…/bifrost-platform-console:stg`，原来挂在这两个标签上的镜像从此没有标签；Argo 同步平台的 STG 应用；滚动重启 `bifrost-platform-stg` 里的 Deployment（等待上限 300 秒，这段时间 STG 的平台不可用）。它没有数据库步骤，滚动之后也没有校验任务。

判定用 5-4 的后两条，`RUN` 换成这次的 run：预期 `succeeded=True`、`sa=default`、日志第一行 `未冻结：0 条记录`，并且整条 run 成功。这是 `default` 账号的真实步骤 Pod 里的一次真读。

步 5 不符时有两条退路，是两件不同的事，不要当成一件。

**退路一：恢复两个 Task**（上表之前那一段说的退路）。它只把检查任务和窗口任务换回当天开头的样子，不动任何已经发出去的东西：

```
git archive "$(cat "$DAY/commit.txt")" k8s/cicd/tekton/task-release-freeze-check.yaml k8s/cicd/tekton/task-release-window.yaml | tar -x -C "$DAY/prev"
q s5-back kubectl --kubeconfig "$BIFROST_OWNER_KUBECONFIG" apply -f "$DAY/prev/k8s/cicd/tekton/task-release-freeze-check.yaml" -f "$DAY/prev/k8s/cicd/tekton/task-release-window.yaml"
```

`commit.txt` 是当天开头记下的提交，两个 Task 文件在那里还是旧的。预期两行 `configured` 和 `exit=0`。旧对象这时还是 `false`，旧的程序 ConfigMap 还在；CRD、策略、绑定留着无害。

**退路二：退回 5-5 发出去的平台 STG。** 这是另一步，退路一不包含它。5-5 的流水线在检查通过之后才构建和滚动，所以检查不过时没有东西要退。检查通过而后面出了问题时：这次发布不带代码改动（上面两个提交相同）的话，STG 上要跑的仍是同一个提交，重跑一次同一条流水线；带了改动的话，今天平台的 STG 没有不重建的回退——镜像在可变标签上，旧镜像已经没有标签，按提交号起平台的发布也走不通（`agent-config/WORK.md` 的 W-56「现在」一段；`TECH_DEBT.md` 的 TD-295）——**只能前修**：在平台的 `main` 上把那几个提交退掉，再跑一次 `bifrost-deliver-platform`。

**这一步没有跑到的：** 改过的 `bifrost-release-window`（去掉了 `freeze` 步骤）。5-4 和 5-5 的两条流水线都不含这个任务；含它的五条是插件和 research 的构建与发布（实测 10-12）。它第一次真跑是此后的第一次插件或 research 构建；它在那里失败的话，流水线停在它那里、后面什么都没做，退路一把它换回去（第 13 节的表）。

## 8. 分片

每一片单独复核。给复核方的问题和给实现方的目标是同一句话（LESSONS 第 86 行第 ② 条）：

> 不动用 L3 的权限，给出一个操作序列——第 6 节字母表里的事件，任意交错，任意一个门可以什么都没看过——使得一个新协议的门在还有一条没被 Owner 删掉的记录时答 `clear`，或者 `create` 打开之后一个还活着的旧程序答 `clear`，或者一个新协议的门在没有任何记录，且传输每一条都成立，且正文属于 L 时不答 `clear`。找不到，就回答找不到。

| 片 | 内容 | 谁 | 停止条件（可判定） |
|---|---|---|---|
| **S1　规则、两份实现、清单，全部离线** | 判定函数（Go）和 `freeze_gate.py`，按 3.2 的产生式实现 L，不经过通用 JSON；传输各行；二进制向量；带照产生式另写的识别器的生成器（种子 `310101`，678 条，Python 跑全部，不是抽样）；第 6 节的状态图（快照含旧对象和 `create` 开关，门调用真正的识别器）、两个阴性对照、随机序列（默认 2000，全量看 `FREEZE_MODEL_SEQUENCES`）；`k8s/release-freeze/` 的五个文件（`crd`、`admission`、`rbac-list`、`rbac-create`、`tombstone`）；`unfreeze` 命令的测试（路径、编码器生成的 `DeleteOptions`、`Background`、UID 前置条件、过期 UID 得 409、对象保留，以及引号、反斜杠、重复键注入）；410 处理函数只做单元测试，不接进路由。不含建记录的 POST，不含两个 Task 文件。不打开冻结：没有任何运行时改动 | 实现方；独立复核 | 通过 = 固定状态图上每条写明的断言都成立（零违例）、两个阴性对照各给出预期的违例、三个识别器对 678 条一致、252 条属于 L 的正文都是 `clear`、该识别器拒绝的没有被答成 `clear`、3.2 点名的手写全文都不是 `clear`、生成器与穷尽模型与整包三次计时分开且整包在 `GOMAXPROCS=2` 下低于 40 秒、3.2 的实现约束（含 HTTP/1.1 的三项）和 `unfreeze` 的命令各有测试、`grep` 不到从服务端接线到新包的调用。离线的零违例不代替第 7 节的现场验收；步 3 的探针真建真删通过之前，后面几片都不接线。**停线** = 一份不在 L 里的应答被答成 `clear`，或两份实现的二进制判定不同，或没有任何记录，且传输每一条都成立，且正文属于 L 时不答 `clear`；复核对上面那句话给出一个序列，同样停。出现这些就重写设计，不补规则。 |
| **「修订 2026-10-12」S2 之前　准备片和两个 Task 文件** | 准备片（infra 分支 `w31/td-310-s2prep`，只改三处，什么都不应用）：去掉 `crd.yaml` 里和 `properties` 并排的 `additionalProperties` 并加测试（3.1）；给 `freeze_gate.py` 加说明模式（3.2）；把检查任务的文件加进 `paths.json` 并加「路径表盖住每个文件」的测试（3.1）。「修订 2026-10-12 之二」第四处：`crd.yaml` 里 `reason` 的上限改成 350，`at` 写死成 20 个字符，加一条从 schema 重算「空清单上建的一条装得下」的测试，片 1 钉着旧上限的测试在同一个提交里改（3.1）。它合并之后，两个 Task 文件写在分支 `w31/td-310-s2task` 上（3.3），不进 `main` | 实现方；独立复核 | 准备片通过 = 三处（「修订 2026-10-12 之二」四处）各有测试、各有一处种错被点名的测试拦住；不带参数时 `freeze_gate.py` 的输出和退出码逐字节不变，两份共享向量和片 1 的种错清单照旧全过。Task 分支通过 = 3.3 列的测试都在，复核对第 8 节开头那句话答找不到。两者都不改集群 |
| **S2　Owner 的第一次** | 第 7 节步 0–5，含两个 Task 文件。它们当天进 `main`，不提前进 applier 能应用的前缀 `k8s/cicd/tekton/`。「修订 2026-10-12」每一格的命令在 7.1；两个文件的来路在 3.3 | Owner | 通过 = 每一格都符合；检查步骤无输出、非 0 退出、超时未退出、以及读函数的可恢复失败，都不放行。有一格不符 = 停；步 5 的问题按退路回到上一个 Task。「修订 2026-10-12」「都不放行」那半句落在四处：程序只在 `clear` 时以 0 退出（片 1 的测试）；新 Task 的第一步带 `timeout`、没有 `onError`（Task 文件的测试，3.3）；检查任务失败时流水线停在它那里——集群上留着的 run `plan-0cc8c195-1791741388` 就是这样，`freeze-check` 失败，排在它后面的 `run` 没有建（实测 10-12）；7.1 的 4-1：没有 `list` 的账号真读一次，印拒绝、退出码非 0。「修订 2026-10-12 之二」4-1 的账号换成新建的探针账号。步 4 的真读只有一次，身份也是探针账号，所以这一片不再证明读在每一个真实的工作负载里走得通：两个流水线账号的由 5-4、5-5 证明，平台账号的归 S3b（D10）。每一格先取结果和退出码、再判；空的答案和失败的查询算不符。E 不在这一片签收（3.4）。步 5 的退路只恢复两个 Task；5-5 那次平台 STG 发布带了改动时只能前修（7.1 步 5 末尾） |
| **S3　平台改读记录，删掉记忆** | 3.4 的平台部分，含建记录的 POST，先 STG 后 PROD。不打开冻结：没有 `create` 的绑定。410 在这一片接进路由 | 实现方；人工批准的发布（触及信任根的路径） | 通过 = 两个环境的状态都是 `freeze_protocol: 3`、`freeze_state: clear`、`freeze_can_create: false`；`unfreeze` 回 410；`memory.go` 不存在；一次 STG 发布通过；读失败、超时、无输出、可恢复故障时 `Decide`、`Evaluate` 和 B 级都不放行。B 级入口是 `FreezeSet` 读失败返回 false（`api/internal/releasepolicy/engine.go:238–245`）之后今天由 `server/release_policy_wire.go:146–166` 放行的那条，本片必须改成拒绝。PROD 发完后是 `unreadable` = 回滚平台（这时还没有墓碑，旧版读到的仍是从未冻结）。「修订 2026-10-12」这一片数下来有 16 条规则，分两片做。**S3a**：只做「建」这一个函数，就是 3.4 的四步（先读、再建、回读、一个期限），离线，没有任何东西调用它，合进主线不改任何环境的行为。**S3b**：接线和删除——`Status`、`Decide`、`Evaluate`、B 级改读记录，删掉记忆，410 进路由，状态接口换形状——它改行为，发版在 S2 之后；它自己还超过八条，开工前要再切一次。Go 读函数的第一次真读在 S3b 的 STG 验收里（D10）：STG 的状态必须是 `freeze_state: clear`，不是就停、不上 PROD。通过条件里「`memory.go` 不存在」这一条在主线上已经成立，该查的是什么见第 13 节的表。「修订 2026-10-12 之二」S3a 多三样：名字的随机性要经得住「从 0 起的进程内计数器」这种种错；`at` 的合法范围和范围之外怎么办；POST 只发往一个地址、不跟随重定向（3.4 第 2 步）。S3b 的 STG 验收是两样都看到才上 PROD：`freeze_state: clear`，和失败关闭——Owner 手建一条合规的记录，STG 报 `frozen` 并拒绝一次发布，Owner 删掉之后回到 `clear`（D10 第 ③ 条）。这期间不写墓碑、不开 `create`，平台可以回滚 |
| **S4　排空、墓碑、打开冻结、演练** | 第 7 节步 6–10；`release.sh` 的 `freeze` / `unfreeze` / `policy status`；在途 run 的清点 | Owner 在场 | 通过 = 步 6–9 每一格符合、演练八步全部符合，TD-310 的验收改写后重跑。步 6 有一格不符 = 不写墓碑。演练有一步不符 = Owner 删掉 `create` 的绑定和全部记录，冻结回到不可用（墓碑不动），TD-310 不进待签收。「修订 2026-10-12 之二」演练第 ② 步多一件事：平台建出第一条记录时量 E 并签收，超过 600 按不符处理（3.4） |
| **S5　策略改成只增的记录** | 第 4 节。在锚合并之前做完 | 实现方；Owner 应用第二个 CRD 和绑定 | 通过 = 第 4 节的四条向量在门和签名工具上都过；模型里只要有一条更新的、验得过的记录在，生效的就不是排序值更小的那条；重放此前的每一份签名都不改变生效的策略。复核给出反例 = 停线 |
| **S6　文档和台账** | `docs/RELEASE.md` 的四节重写；计划第 1 步里「解冻的独立授权」「冻结的串行边界」和 C 片的演练改写；TD-310 的修法和验收改写；登记只读防线（3.1） | 统筹方 | 文档里不再出现 `unfreeze.sig`、`freeze_id`；防线登记在 `RATCHETS.md` |

## 9. 决定

| | 决定 | 谁定 | 结论或推荐 | 一句话推翻 |
|---|---|---|---|---|
| D1 | 集群管理员一级（1.3 的 L3）不在这个协议的防范之内 | Owner，2026-10-11 **已定：按推荐** | 推荐：是。它本来就能直接发布；防它要集群外的见证，是另一件事。普通平台身份升上去的两条路（TD-314、TD-293）都是打开 `create` 的前置（步 8） | 「管理员一级也要防」 |
| D2 | 解冻靠签名（A），还是靠集群的授权（E） | Owner，2026-10-11 **已定：按推荐** | 推荐：集群的授权。复核 93 的理由：今天管理员身份删一下就已经能解开冻结，从签名换成集群凭证没有新增任何能力。它改的是 ADR §5「放宽要他签名」对冻结这一项的字面；策略仍然要签名 | 「解冻仍要签名」——那就在记录上加一类解冻记录，检查任务换成能验签的程序，代价见 2.2 的 A |
| D3 | 记录放在专用的集群级资源类型上 | 统筹方，2026-10-11 **已定：是** | 复核 93 认为成立，条件是补上属主引用的准入（已补，3.1） | 「不加 CRD」——回到 2.2 的 B：专用命名空间、哨兵、两处特判 |
| D4 | 用哪份凭证解冻 | Owner，2026-10-11 **已定：按推荐** | 推荐：先用他现有的管理员 kubeconfig。Agent 搬离他这台机器（W-67）时换成一个只能 `list` 和 `delete` 这类对象的专用身份，同时改策略里的用户名。用户名认的是凭证不是人：今天同一张管理员证书的持有者都被当作 Owner（都算 L3）；换成专用身份时按 3.1 把用户名、组、同名认证和 `impersonate` 重新核对一遍 | 「解冻不该动用管理员凭证」 |
| D5 | 策略也改成只建不改的记录，在第一份策略签出来之前 | 统筹方，2026-10-11 **已定：是** | 复核 93 认为成立，条件是签名的排序和记录的保留（已写，第 4 节） | 「策略先不动」——重放的界限仍是过期时间，那至少要先做 TD-293 |
| D6 | 读不到冻结状态时，B 级的发布也拒绝 | Owner，2026-10-11 **已定：按推荐** | 推荐：是。检查任务本来就会拒绝，平台放过去只是换个地方失败 | 「读不到时测试环境照发」 |
| D7 | 「修订 2026-10-12」一次冻结凭什么报「建成」 | 统筹方，2026-10-12 **已定** | 只凭 POST 之后经门的严格读回读到刚建的那个名字。POST 可以走平台现有的 Kubernetes 客户端，它的状态码只用来选报哪一种失败；POST 加回读共用一个 10 秒的绝对期限；丢失或含糊的 POST 报「没有确认建成，状态未知，请再读一次」（3.4）。「修订 2026-10-12 之二」「现有的 Kubernetes 客户端」读作同一份集群配置、令牌和 CA；HTTP 客户端为这一次另起，只发往一个地址，不跟随重定向，不重试（3.4 第 2 步） | 「POST 回 201 就算建成」 |
| D8 | 「修订 2026-10-12」清单的上限怎么算，和读不到时建不建 | 统筹方，2026-10-12 **已定**（当天改过一次：头一版是「上限按条数 N = 7，读不到就不建」，两句都撤回了） | 上限按字节：建之前读得到、而且已有记录时，读到的正文字节数加新记录的上界超过 4096 就不建，报「没有新增：清单满了」；零条时不看大小。读不到时照样建：冻结是急停，要偏向冻住；建完回读，回读也读不到就报「未知：只要还读不到，门就不放行；请再读一次」。原来的「满 20 条」经读函数数不到（3.2、3.4）。代价一句话：读不到的那段时间里的一次建（或者零条时一条单独就超限的记录）可能把清单撑过上限，之后门一直不放行、印的是读不到，直到 Owner 删掉一条——失败关闭，而且看得见。「修订 2026-10-12 之二」「单独一条装不装得下」定了：CRD 把字段收短（`reason` 至多 350，`at` 写死 20 个字符），空清单上建的一条之后总读得到，算术在 3.1（150 + 600 + 3,252 = 4,002，余 94 字节）；函数不在空清单上另做大小检查。代价那句话里括号中的那一种因此没有了，换成并发：几个调用同时建，每一条都装得下，合起来可以超过上限，结果一样——门不放行、印的是读不到、Owner 删掉几条。E = 600 在平台自己建出第一条记录时签收（3.4） | 「读不到的时候不许再往里加」——那就是头一版：读不到时没有人冻得上。「单独一条不必保证装得下」——那就把 `reason` 放回 500，回到只靠规则的形状 |
| D9 | 「修订 2026-10-12」Owner 的用户名填在哪里 | 统筹方，2026-10-12 **已定** | 仓库留着占位符，测试不动；当天在仓库之外渲染副本、看差异、应用副本，填好的文件不进 `main`（3.1、7.1 的 0-4、0-5） | 「把用户名写进仓库」——那就改片 1 钉着占位符的三处测试 |
| D10 | 「修订 2026-10-12」步 4 的真读用什么读 | 统筹方，2026-10-12 **已定** | 用 `freeze_gate.py` 的说明模式（3.2），四个账号各读一次。Go 读函数在 S2 没有可执行的入口，它的第一次真读是 S3b 在 STG 上的验收。**这比复核 103 第 3 条弱**：那一条要 Go 读函数在接线之前、在平台 Pod 里真读一次（第 12 节），现在它第一次面对真实的 apiserver 时已经接上线了。为什么可以接受：最坏的情形是 Go 读函数对真实的应答答不出 `clear`，STG 的状态是 `unreadable`，STG 上的发布全部被拒，平台回滚到上一版——一次回滚的 STG，不会有一次错放的发布；PROD 要等 STG 报 `freeze_state: clear` 才发（第 8 节 S3）。两份读法在片 1 的 180,843 份应答上判定一致，应答合不合 3.2 的语言由 Python 这四次先答。「修订 2026-10-12 之二」两处改动。一，「四个账号各读一次」作废：步 4 不在平台账号或 applier 账号下起 Pod，四个身份各问一次 `can-i`，真读只有一次，身份是探针账号（7.1 步 4）。二，按复核 121 的条件接受，四条都要成立：① Python 的真读先在 S2 通过（4-8），两个流水线账号在真实步骤 Pod 里的读在步 5 通过（5-4、5-5）；② S3b 只先上 STG；③ 在 STG 上看到两样之后才上 PROD——Go 读函数答 `clear`（状态接口报 `freeze_state: clear`），和它的失败关闭：Owner 手建一条合规的记录，STG 的状态变成 `frozen` 并列出这一条，经 STG 平台发起的一次发布被拒，Owner 带 UID 删掉它，STG 回到 `clear`；④ 这期间墓碑没有写、`create` 没有打开，平台可以回滚到上一版。这是把现场的风险挪到 STG，不是在接线之前验证了 Go。第 ③ 条要 Owner 多到场一次，两条命令，写法同 7.1 的 3-1 和 3-19，对象用合规的那一条；那几分钟里新 Task 的检查也读到这条记录，全集群的发布流水线都被拒——那就是一次真的冻结，事先说一声 | 「Go 读函数也要在接线之前真读一次」——那要先给它做一个能进平台镜像的入口，另算一片 |

## 10. 这份设计不保证的

- **L3。** 能改准入策略、它的绑定或 CRD 的身份，以及能冒充 Owner 的身份。CRD 被删的那段时间门是拒绝的（读不到）；重建之后是空的，也就是未冻结。
- **从备份恢复（etcd）。** 把集群状态恢复到一次冻结之前，那次冻结就没了，门发现不了。
- **平台账号自己的权限。** 见 1.3：量到的两条提升的路在步 8 封住；没有清点过的借用路径不在声称之内。
- **已经过了最后一次读的发布**（3.3 的窗口），以及根本不读冻结的入口：CI 流水线（有意不查）、内联规格的 run（TD-272）、推 `main` 之后 Argo 的自动同步、`gitops_sync_app`、重启和缩放。它们归计划第 1 步的 D、E、F 片。
- **可用性。** 任何有 operator 令牌的线程都能把发布全部停下，直到 Owner 来删。这是「收紧谁都可以」的本意。`who` 是调用方自己报的。解冻没有签名凭据，留痕是发布日志；apiserver 的审计日志开没开，未测。
- **检查任务本身。** 它的定义谁能改（applier 经一张 C 级的单，以及 L3）；它用的镜像标签是可变的（计划第 2 步改成摘要）。**策略**的部分见第 4 节「留着的」。

没量到的：webhook 准入配置（只读身份没有权限）；Owner 的用户名和组，以及还有什么能以这个用户名通过认证；发布密钥有没有口令；准入策略对 DELETE、`deletecollection`、集群级自定义资源、`request.options` 的实际表现（本集群没有先例，步 2–3 证明）；1.2 第 2、3 条那两条路实际走不走得通；`tekton-deliver` 下的任务能不能被参数带出一次写入；那 27 个内联 run 是谁建的；垃圾回收器的请求用的是哪个身份；LIST「最新读」在这个集群上的表现。

「修订 2026-10-12」实测 10-12 量掉的：`cicd` 的 12 个 ServiceAccount 的名字，和它们谁凭通配符够得着新类型（3.1）；`impersonate` 的授予方仍是四个；垃圾回收器在 RBAC 里的主体是 `kube-system/generic-garbage-collector`（它的请求实际用不用这个身份仍没量到）；控制面只有 `ubt-k3s-01` 一台；旧对象仍是 `{"frozen":"false"}`、没有 `immutable`；没有名字带 `bifrost` 的 CRD，`release.bifrost.io` 这个组不存在；准入策略仍是那 6 条，其中 5 条带着类型检查的警告；集群上的旧检查程序和 `239f100` 的 `freeze_decision.py` 逐字节相同（SHA-256 `8aaad4e5…`）；18 条流水线里 13 条以 `freeze-check` 为唯一的根任务；留存的 TaskRun 3,232 个，没有未完成的；只读身份读不到 webhook 配置（两类都是 Forbidden）；真实对象上 `managedFields` 的大小（3.2）；apiserver 把自定义资源里的 `<`、`>`、`&` 各写成 6 个字节（3.2）。仍然只有 Owner 的身份才量得到的：他的用户名和组；同名认证的来源（在控制面节点上）；`crd.yaml` 和 `admission.yaml` 过不过服务端试算；准入策略对 DELETE、整类删除、`request.options` 的实际表现和拒绝报文的样式；apiserver 认不认删除的 UID 前置条件；7.1 里 `fread` 那条起临时 Pod 的命令走不走得通；一条真实冻结记录在 LIST 里占多少字节。

「修订 2026-10-12 之二」`fread` 已经换成 `probe.sh`（7.1 步 4）。它用不碰集群的替身 `kubectl` 试过八条路，真的 `kubectl` 对真的集群没有跑过；集群上管 Pod 的两条准入策略（`bifrost-platform-job-sa`、`bifrost-applier-pod-spec`）只匹配平台账号和 applier 发起的创建，`cicd` 没有配额、只有 Argo 的入站网络策略（都是实测 10-12）；有没有 webhook 会拒掉这样一个 Pod，只读身份看不到；`attach` 把程序从标准输入送进去在这台集群上走不走得通，要到当天才知道。走不通时脚本自己停下并清理，步 4 不算通过。这一轮量掉的：`cicd` 的 18 条流水线里 13 条以 `freeze-check` 为第一个任务，含 `release-window` 任务的是五条（三条插件构建、research 的构建和发布）；留存的 run 里，发布和构建流水线都跑在 `default` 下，`bifrost-apply-manifest` 跑在 `bifrost-applier` 下；最近一次成功的平台 STG 发布克隆的是平台的 `17136ba`，当时平台的 `main` 在 `832fd90`。这一轮新增的不保证：几个调用同时冻结，合起来可以超过 4096 字节（3.1、D8）；平台 STG 的发布没有不重建的回退（7.1 步 5 末尾）。

## 11. 复核 95 逐条

1. P2　TD-293 也要先封：1.2 第 3 条、1.3 的声称、第 7 节顶上的清单和步 8、第 9 节 D1、第 10 节。
2. P2　使用前的检查补三样（带注解的建、孤儿式删除、不带请求体的原始 DELETE），拒绝要来自目标策略，策略「看着正常」不算数：3.1、第 7 节步 2–3。
3. P2　前台和孤儿式删除：去掉「不会出现」，写成「持续冻结」和 Owner 的恢复步骤；垃圾回收器被拒后重试也拿不到删除权：3.1、3.4 末段。
4. P2　有限模型的状态：内容等价类、建删历史、读的线性化点、两代 UID 用完之后、固定状态图和写明的断言：第 6 节、第 8 节 S1。
5. P2　删除命令：S1 测真的 `kubectl` 发出的东西和过期 UID 的 409；探针真建真删先过；410 的单元测试和 S3 的接线分开验收：3.4、第 7 节步 3、第 8 节 S1。
6. P2　Owner 的身份是凭证不是人：记下组，核对同名认证和 `impersonate` 的来源，今天的证书持有者算 L3，专用身份要重新核对：3.1、第 7 节步 0、第 9 节 D4。
7. P3　顺序是必要的偏序，不是唯一的排法；墓碑之后不能回滚的警告放在 Owner 动手之前读到的地方：第 5 节、第 7 节的开头和步 7。
8. P3　四个旧读者分开写：旧 `freeze` 步骤把 404 当未冻结，所以要点是墓碑留着、删它过准入；旧平台的 `Unfreeze` 写入失败并报错：第 0 节、第 5 节。

复核 93（`change first`，2 个 P1、7 个 P2、2 个 P3）：两个 P1 经复核 95 确认已关——带属主引用的记录被回收（3.1 的准入策略、第 7 节步 2–3），换 Task 换不掉已装载的旧程序（第 5 节的墓碑、步 6–7）。
它的 P2、P3 里，策略排序、批量解冻、读代码的事实、读法、最后一次读的窗口已采纳；提升路径、有限模型、使用前检查当时只采纳了一部分，余下的就是上面第 1、4、2 条；RBAC 证据仍只有汇总和重算的办法（附录），没有可以独立复算的原始导出——仓库是公开的，原始导出不进仓库。

## 12. 复核 103 逐条

复核 100：八条已写入第 3、6、7、8 节。
其中第 4 条当时只采纳了一部分；可恢复边界在 3.2，本轮没有放宽。
复核 101：六条都采纳。扫描器正文和正则已删，L 只留产生式。
101 的第 5 条里，HTTP/2 推送不再作为规则；协议改为 HTTP/1.1，见下面第 2 条。

1. P1　metadata 有两套说法：3.2，L 只剩那一组产生式；点名的全文进入不 `clear` 的手写向量。
2. P2　HTTP 版本没写死：3.2，两侧只使用 HTTP/1.1；1xx、帧结束、`Content-Encoding` 都在读函数里；去掉推送和流结束。
3. P2　现场读的身份和顺序：第 7 节步 4，`list` 之后、步 5 之前，在平台 Pod 和 Tekton 步骤 Pod 里读；CA 与主机名由这次读留下；升级后重跑。「修订 2026-10-12 之二」现在比这一条弱两处，都记在 D10：步 5 之前的真读只有一次，身份是探针账号，不是平台账号或流水线账号；Tekton 步骤 Pod 里的读是步 5 自己（接线之后的第一次 run），平台 Pod 里的读是 S3b 的 STG 验收。CA 与主机名仍由步 4 的那一次读留下，升级后仍重跑。
4. P3　活性漏了传输前提：第 6 节 L、第 8 节开头、S1 停线都是「传输每一条都成立，且正文属于 L」。

## 13. 「修订 2026-10-12」改了哪些段落；已知、延后的

这一轮由复核 121 看过，结论是「先改」；它之后的改动是下面的之二，还没有复核。改到的段落，按出现的先后：

1. 文首状态行之后：这一轮修订的说明。
2. 3.1 「类型」一段：schema 里不写 `additionalProperties`；片 1 文件里的那一行由准备片去掉。
3. 3.1 「规则里的 Owner 是谁」：用户名填在仓库之外的副本里（D9）；只读防线比的是换掉占位符之后的样子。
4. 3.1 末尾：检查任务的文件补进路径表；新增一段，`cicd` 的 12 个账号是谁、哪两个凭通配符够得着新类型（实测）。
5. 3.2 末尾新增两段：记录多到装不下的时候（含 apiserver 把 `<`、`>`、`&` 写成 6 个字节的实测，和「单独一条也可能超限」）；说明模式。
6. 3.3 第四条：两个 Task 文件怎么写、在哪条分支上复核、怎样当天进 `main`。
7. 3.4 平台一段之后：`Freeze` 改成四步——先读、再建、回读、一个期限（D7、D8）。第 1 步当天改过两次，现在是：读不到照样建；零条不看大小；已有记录时按字节算上限，并写明不变式。
8. 第 7 节开头清单第 4 条：四次真读；Go 读函数的第一次真读在 S3b。
9. 第 7 节表格步 0–5 六行：各指向 7.1；步 2 的 `expressionWarnings` 只记录；步 3 多六格；步 4 整格重写。
10. 新增 7.1：步 0–5 每一格的命令和预期，步 5 退路的命令。
11. 第 8 节：新增「S2 之前」一行；S2 行补上「都不放行」落在哪四处；S3 行补上分成 S3a、S3b。
12. 第 9 节：新增 D7–D10。D8 当天重写过一次（上限从条数改回字节，读不到从不建改回照样建）；D10 写明它比复核 103 第 3 条弱、以及最坏的情形是什么。
13. 第 10 节末尾：实测 10-12 量掉了什么，哪些仍只有 Owner 的身份量得到。
14. 新增本节。
15. 附录末尾：实测 10-12 的重算命令和它的输出。
16. 7.1 步 4 的临时 Pod，请复核方专门看：它以两个流水线账号和两个平台账号（含 PROD 平台的）的身份各存在几十秒。清单是定文（一个容器、一条命令、没有额外的挂载、`restartPolicy: Never`）；读的那一格自己删掉它（4-1、4-7）；紧接着的一格查没有留下（4-2、4-8）。「修订 2026-10-12 之二」这一条作废：复核 121 指出这样的 Pod 带着那个账号的全部权限，步 4 改掉了，见下面第 23 条。

「修订 2026-10-12 之二」改到的段落（复核 121 之后；这一轮也还没有复核），接着上面往下编号：

17. 文首：这一轮修订的说明。
18. 3.1 「类型」一段，和它后面新增的一段：`reason` 至多 350，`at` 写死 20 个字符；「空清单上建的一条装得下」的算术；这句话不管并发。
19. 3.2 「记录多到装不下的时候」：各种大小按收短后的上限重算；E 是估计。
20. 3.4 第 1 步：不变式那一段改写，新增「E 是估计」一段，「挡不住的」一段改写。第 2 步：POST 只发往一个地址、不跟随重定向；`at` 的范围。
21. 第 7 节开头清单第 4 条；表格之前那一段（两条退路是两件事；STG 和 PROD 之间多一次短的）。
22. 第 7 节表格：步 0（旧对象的完整形状）、步 2（多一格；警告是待核实的事；拒绝的认法）、步 3（探针的建法；和快照比；E 不签收）、步 4（整格再次重写）、步 5（点名发布、副作用、两条退路）、分隔行。
23. 7.1 整节重写：`q`（先取结果和退出码，再判）；拒绝的认法；`probe.sh` 和探针的两份清单；步 4 从八格变成九格，不在真实账号下起 Pod；步 5 点名发布、两条退路、「这一步没有跑到的」。
24. 第 8 节：「S2 之前」多第四处；S2、S3、S4 三行各补一段。
25. 第 9 节：D7（HTTP 客户端）、D8（字段收短；并发）、D10（复核 121 的四个条件）。
26. 第 10 节末尾新增一段。
27. 第 12 节第 3 条：现在比它弱在哪两处。
28. 本节：这张清单；上面第 16 条作废；下表改两行，加七行（标着之二）。
29. 附录：重算的命令改成先存结果、再算。

已知、延后的。这一轮不解决，各归各的片：

| 事 | 现在的样子 | 归哪一片 |
|---|---|---|
| Console 把 `unfreeze_command` 当必填字段读并显示，3.4 要删这个字段 | `console/src/api/releasePolicy.ts:18`、`:53` | S3b：状态接口换形状时一起改，或者这个字段多留一版 |
| `release_unfreeze` 在动作目录里；`mcp/` 下没有叫这个名字的工具，3.4 的「从 MCP 工具里去掉」没有对象 | `api/internal/actions/catalog.go:146`、`config/actions-catalog.json:26` | S3b |
| 第五条发起发布的路：审批执行器送来的已批准 C 级调用，在两道检查之前就过了 `guard`，平台不为它读冻结。3.4 只点了四个调用方 | `api/internal/server/actions_wire.go:58–61` | S3b：先定这条路要不要读 |
| 不在 Pod 里的平台进程（开发机上的 `platform-api`）没有 ServiceAccount 令牌，读到的是 `unreadable`；按 D6，它被要求发起的发布全部被拒。它的 POST 用的是本机 kubeconfig 里的身份 | `api/internal/releasefreeze/read.go:205–222`、`api/internal/cluster/client.go:118–159` | S3b |
| `release.sh policy status` 读 `frozen_at`，S3 删掉这个字段之后它印 `at ?` | `scripts/release/release.sh:615` | S4：`release.sh` 在那一片改 |
| 墓碑有两种做法并存：第 5 节的 `kubectl patch` 命令，和片 1 放的清单 `k8s/release-freeze/tombstone.yaml` | 第 5 节；该文件第 3–4 行 | S4：留一种 |
| 3.4 那几句报错的话（没打开、没写上、未知、清单满了）的原文、语言，和路由回的状态码 | 3.4 写的是意思 | S3b |
| `via` 里写什么 | 3.1 只说「哪一个平台实例写的」 | S3b |
| 「只有两个函数的包」对不上：包导出了五个入口，`Gate` 有九个能改地址、CA、令牌和期限的导出字段；接线的代码怎样构造 `Gate`，要一条规则 | `api/internal/releasefreeze/read.go:31–50`、`:53`，`decision.go:59`、`:67`，`lang.go:5`，`handler.go:12` | S3b |
| 第 8 节 S3 的通过条件「`memory.go` 不存在」在主线上已经成立：那个文件只在分支 `w31/td-310-anchor` 上，主线上的那份记忆在别处 | `api/internal/releasepolicy/engine.go:64`、`:73`、`:159–211` | S3b：通过条件改成点这几处 |
| `freeze_can_create` 的那次 SelfSubjectAccessReview 经哪个客户端发 | 3.4 没写 | S3b |
| S3b 自己还超过八条规则 | 第 8 节 S3 行 | S3b 的任务书：开工前再切 |
| 新记录上界里的 E = 600 是按实测的信封算出来的，不是量出来的。「修订 2026-10-12 之二」步 3 的探针是 `kubectl` 发的，量到的数不能签收 | 3.2、3.4 | S2 当天只核对它没有离谱（7.1 的 3-2、3-19）；S4 步 10 演练第 ② 步，平台自己建出第一条记录时量并签收 |
| 3.1 那条只读防线还没有做 | 3.1 | S6 |
| Go 读函数没有说明模式，接线之前不会真读 | D10 | S3b 的 STG 验收（「修订 2026-10-12 之二」`clear` 和失败关闭都看到才上 PROD）；要更早就另算一片 |
| 「修订 2026-10-12 之二」步 2 记下的 `expressionWarnings`，如果有 | 7.1 的 2-3；原文留在当天的文件里 | S2 之后由统筹方逐条说明：是对动态类型的推断警告，还是真错；连同步 2、步 3 的正反探针留档。说明之前不当作噪声 |
| 「修订 2026-10-12 之二」S3b 的 STG 验收里，Owner 手建一条记录再删掉的操作单 | D10 第 ③ 条只写了做什么 | S3b 发版前另写；命令的写法同 7.1 的 3-1、3-2、3-19 |
| 「修订 2026-10-12 之二」`probe.sh` 没有对真的集群跑过 | 7.1 步 4；用替身试过八条路 | S2 当天；走不通就停在步 4，不往下做 |
| 「修订 2026-10-12 之二」改过的 `bifrost-release-window` 在 S2 里没有一次真跑 | 7.1 步 5 末尾 | S2 之后的第一次插件或 research 构建；要在 S2 当天看到，就在 5-5 之后加一次含这个任务的构建，由统筹方定 |
| 「修订 2026-10-12 之二」平台 STG 的发布没有不重建的回退 | 7.1 步 5 末尾；`TECH_DEBT.md` 的 TD-295 | 不归这份设计；5-5 带了改动时只能前修 |
| 「修订 2026-10-12 之二」几个调用同时冻结，合起来可以超过 4096 字节 | 3.1、D8 | 接受：失败关闭，看得见，Owner 删掉几条就恢复；要防就得让「建」串行，另议 |
| 「修订 2026-10-12 之二」探针 Pod 的镜像是可变标签 | 7.1 步 4 | 和检查任务一样，归计划第 2 步改成摘要；探针的凭证只有 `list`，这里不靠它设防 |

## 附：RBAC 证据（实测 2026-10-11 17:19 CDT）

读到 126 个 ClusterRole、93 个 ClusterRoleBinding、50 个 Role、118 个 RoleBinding。原始导出不进仓库（仓库是公开的），这里是汇总。重算的办法：只读身份 `kubectl get clusterroles,clusterrolebindings -o json` 和 `kubectl get roles,rolebindings -A -o json`；一条规则算数的条件是 `apiGroups` 含 `*` 或该组、`resources` 含 `*` 或该资源、`verbs` 含 `*` 或该动词；再按绑定展开主体。新类型现在还不存在，「对新类型」一列是通配符规则给出的。

| 主体 | 经由 | 对新类型 | 写 CRD | 写准入策略和绑定 | `impersonate` |
|---|---|---|---|---|---|
| 组 `system:masters` | `cluster-admin` | 全部 | ✓ | ✓ | ✓ |
| `cicd/argocd-application-controller` | 同名绑定 → 同名角色（`*` / `*` / `*`） | 全部 | ✓ | ✓ | ✓ |
| `kube-system/helm-traefik`、`helm-traefik-crd` | → `cluster-admin` | 全部 | ✓ | ✓ | ✓ |
| `cicd/argocd-server` | 同名绑定 → 同名角色（`*` 的 `delete` / `get` / `patch`） | `patch`、`delete` | `patch`、`delete` | `patch`、`delete` | – |
| `kube-system/generic-garbage-collector` | `system:controller:generic-garbage-collector` | `list`、`update`、`patch`、`delete` | `update`、`patch`、`delete` | 同左 | – |
| `kube-system/namespace-controller` | `system:controller:namespace-controller` | `list`、`delete`、`deletecollection` | `delete` | `delete` | – |
| `tekton-pipelines/tekton-pipelines-webhook`；`kube-system/resourcequota-controller`、用户 `system:kube-controller-manager` | 各自的角色 | 前者没有；后两者 `list` | 前者 `update`、`patch`（限名字） | – | – |

除此之外没有主体对新类型有 `list` 或任何写动词。带 `aggregationRule` 的 ClusterRole 只有 `admin`、`edit`、`view`，各按自己的 `aggregate-to-*` 标签聚合；没有一个命名空间内的 Role 同时通配组和资源。准入策略到位之后，这张表决定的只是「谁是 L3」，不再决定「谁能删一条记录」。

「修订 2026-10-12」实测 10-12 重算，结果和上表一致，对象的个数也没变（126、93、50、118）。上表「对新类型」一列少写了几个只读的动词，以这次的输出为准：`argocd-server` 还有 `get`，垃圾回收器还有 `get`、`watch`，命名空间控制器还有 `get`、`watch`，`resourcequota-controller` 和 `system:kube-controller-manager` 是 `list`、`watch`。重算的命令（只读身份跑，新类型是集群级的，所以只看 ClusterRoleBinding）。「修订 2026-10-12 之二」改成两条，先把查询的结果和退出码留下、再算：上一版是一条管道，查询失败时后半截照样印出零行，看上去像「谁都够不着」。`$DAY` 是 7.1 的那个目录。第一条必须印 `exit=0`，否则第二条的输出不算数（10-12 重跑过，输出和下面的 13 行相同）：

```
kubectl get clusterroles,clusterrolebindings -o json > "$DAY/s0-7.json"; echo "exit=$?"
python3 -c '
import json, sys
items = json.load(open(sys.argv[1]))["items"]
roles = {i["metadata"]["name"]: i.get("rules") or [] for i in items if i["kind"] == "ClusterRole"}
def who(s):
    return (s.get("namespace", "") + "/" if s["kind"] == "ServiceAccount" else s["kind"].lower() + ":") + s["name"]
for b in sorted((i for i in items if i["kind"] == "ClusterRoleBinding"), key=lambda i: i["metadata"]["name"]):
    verbs, imp = set(), False
    for r in roles.get(b["roleRef"]["name"], []):
        groups, res, v = r.get("apiGroups") or [], r.get("resources") or [], set(r.get("verbs") or [])
        if ("*" in groups or "release.bifrost.io" in groups) and ("*" in res or "freezes" in res):
            verbs |= v
        if "impersonate" in v or ("*" in v and "*" in groups and "*" in res):
            imp = True
    for s in b.get("subjects") or []:
        if verbs:
            print("freezes", who(s), ",".join(sorted(verbs)))
        if imp:
            print("impersonate", who(s))
' "$DAY/s0-7.json" | sort | tee "$DAY/s0-7.out"
wc -l < "$DAY/s0-7.out"
```

10-12 的输出，13 行（应用 `rbac-list.yaml` 之前）：

```
freezes cicd/argocd-application-controller *
freezes cicd/argocd-server delete,get,patch
freezes group:system:masters *
freezes kube-system/generic-garbage-collector delete,get,list,patch,update,watch
freezes kube-system/helm-traefik *
freezes kube-system/helm-traefik-crd *
freezes kube-system/namespace-controller delete,deletecollection,get,list,watch
freezes kube-system/resourcequota-controller list,watch
freezes user:system:kube-controller-manager list,watch
impersonate cicd/argocd-application-controller
impersonate group:system:masters
impersonate kube-system/helm-traefik
impersonate kube-system/helm-traefik-crd
```

`cicd` 的 12 个 ServiceAccount 里，被 ClusterRoleBinding 点名的只有五个：`argocd-application-controller`、`argocd-applicationset-controller`、`argocd-server`、`bifrost-applier`（`bifrost-applier-namespaces`，只读 `namespaces`）、`tekton-trigger`（`tekton-trigger-resolve`）。应用 `rbac-list.yaml` 之后这条命令会多出四行 `list`（组 `system:serviceaccounts:cicd`、两个平台账号、只读身份）。
