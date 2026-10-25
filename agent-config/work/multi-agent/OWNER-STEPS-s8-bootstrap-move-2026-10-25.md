# TD-432 S8：仅搬迁剩余的管理员 Secret（Work 565）

仓库改动已准备；本文件的集群命令尚未执行。S0 §1–§6 的 CI、RBAC、三套 reader、
管理员令牌轮换、旧令牌吊销和旧 clone Secret 删除已由 Owner 完成，不重做。
本次只把 `cicd/gitea-bootstrap` 搬到 `gitea-admin/gitea-bootstrap`。
main 冻结仍成立；统筹复核此分支后，由 Owner 在干净的已复核 checkout 中执行。
每个代码块是一步；任何失败停下，不能把失败吞掉继续。不要开 `set -x`，不要 `get secret -o yaml`。

## 1. 边界与消费方

`gitea-admin` 不在 Argo 应用或 overlay 中，由 Owner 单独管理。没有 RoleBinding/ClusterRoleBinding；
RBAC 是累加授权，没有“deny Role”。平台和 CI 原来在 `cicd` 的权限不会跟随 Secret 搬迁。
`ResourceQuota/no-workloads` 把 Pod 及常用 workload 对象数量设成零；默认 SA 不自动挂令牌，
NetworkPolicy 全拒绝，PSA restricted。平台/CI 还必须不能改 quota、建绑定或建 workload。

已切换的消费方：

| 入口 | 新位置 | 验证 |
|---|---|---|
| `scripts/gitea/lib.sh` 及所有 source 它的 Owner 脚本 | `gitea-admin` | fake kubectl 只接受新 namespace；Owner `check-step1.sh` 只读核对 |
| `scripts/gitea/rotate-admin-token.sh` 的读取和 patch | `gitea-admin` | rotation 测试强制 namespace；Owner `check`，不再 rotate |
| `scripts/k3s/install-ci-webhooks.sh` | `gitea-admin`，服务仍在 `cicd` | 静态检查；不为验证重复改 webhook |
| Secret 样例 | admin 在 `gitea-admin`，CI reader 仍在 `cicd` | YAML 测试；不要用样例覆盖现有值 |
| Tekton Tasks、Pipelines、CronJobs、Deployment | 无 admin 消费方 | 全仓 `k8s/**/*.yaml` 防线，已有 reader 原位不变 |

历史 CUT、旧操作单和旧债证据保留原位置，不能当作今天的操作入口。以下全仓检索由 Owner 再核对一次：

```bash
git grep -n -E 'gitea-bootstrap|gitea_admin_token' -- scripts k8s
PATH=/opt/anaconda3/bin:$PATH python3 -m pytest -q scripts/gitea scripts/release
PATH=/opt/anaconda3/bin:$PATH python3 -m pytest -q scripts/test_platform_rbac_secrets.py
```

实际读/写 admin 的三个入口只能指向新 namespace。测试、迁移工具、拒绝名单和 `.example` 的命中是预期。
先停止其他 Owner 管理脚本与轮换操作，直到第 6 步完成；不需要停业务、CI 或 reader。

## 2. 建空 namespace，先安装隔离对象

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml create --dry-run=server -f k8s/gitea-admin/namespace.yaml
```

预期 server dry run。若 namespace 已存在，停下检查其来源和工作负载，不能直接接管。

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml create -f k8s/gitea-admin/namespace.yaml
```

namespace 存在后才能 dry-run namespace 内对象：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply --server-side --dry-run=server -f k8s/gitea-admin/isolation.yaml
```

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml apply --server-side -f k8s/gitea-admin/isolation.yaml
```

不使用 `--force-conflicts`。default SA 由 Kubernetes 创建，若字段冲突先调查。

```bash
KUBECONFIG=~/.bifrost-owner/kube/admin.yaml python3 scripts/gitea/check-bootstrap-isolation.py
```

只读元数据和 SubjectAccessReview，不读 Secret。预期 workload identities 全拒绝、0 workload、zero Pod quota。
新 CI SA 自动纳入检查；`cicd` 的 Argo 基础设施身份单独列出。任何 FAIL 都不能复制 Secret。

## 3. 在内存中复制，先 server dry-run

```bash
python3 scripts/gitea/move-bootstrap.py --kubeconfig ~/.bifrost-owner/kube/admin.yaml dry-run
```

预期 `PASS: dry-run (Secret values suppressed)`。工具只保留 type/data 和新 metadata，
不复制 uid、resourceVersion、managedFields、ownerReferences、last-applied；也不输出 kubectl 错误正文，
避免 admission 错误回显 Secret。真实写入用 create，不生成含凭证的 last-applied 注解。

```bash
python3 scripts/gitea/move-bootstrap.py --kubeconfig ~/.bifrost-owner/kube/admin.yaml copy
```

预期 `PASS: copy`，包含内存中逐字 data/type 读回比较。目标已存在即拒绝，不覆盖。

```bash
python3 scripts/gitea/move-bootstrap.py --kubeconfig ~/.bifrost-owner/kube/admin.yaml verify
```

预期两边完全相同。只复制已经轮换过的令牌，不创建另一枚，不重做 revoke。

## 4. 切换脚本并核对每一类消费方

现在才使用本片的新脚本；不要运行旧 checkout 的管理脚本。迁移没有 namespace 环境变量回退。

```bash
bash scripts/gitea/rotate-admin-token.sh check
bash scripts/gitea/check-step1.sh
```

上面两条逐条执行。`check` 应报告管理员是 `weitingzhao`、reader 是独立的 CI 身份、不是历史泄漏令牌；
它本身有些诊断只打印不使退出失败，所以必须看输出。`check-step1` 检查现有团队/分支保护等状态，
若出现与 S0 新保护规则相关的差异，调查而非运行修复命令。两者均不轮换令牌。
`install-ci-webhooks.sh` 的 API 写操作不是本次迁移验收所需，不运行。

Owner 在 Console 查看最近一次 reader 克隆、mirror-sync、GitHub sync/reconcile 成功记录，记录 run 名与时间。
若无最近成功记录，保留旧副本并由统筹另列所需验证动作；不能用“源代码已换”声称运行时消费方已验证。
检查线上 manifest 是否仍引用 admin 的命令（读取非 Secret 对象，不打印 env 内容）：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml get deployments,statefulsets,daemonsets,jobs,cronjobs,pods,serviceaccounts,tasks,pipelines,taskruns,pipelineruns -A -o json |
python3 -c 'import json,sys
items=json.load(sys.stdin)["items"]
bad=[x["kind"]+"/"+x["metadata"].get("namespace","")+"/"+x["metadata"]["name"] for x in items if "gitea-bootstrap" in json.dumps(x)]
print("\n".join(bad) if bad else "PASS: no workload object references bootstrap")
sys.exit(bool(bad))'
```

旧已完成 TaskRun 也会被报出。它不会被本包删除：先解释并保存只含名称的记录，确认它已结束；
任一仍可运行的对象引用 admin 都必须先修复。再次执行隔离检查后才进入删除步骤。

## 5. 集群级受信主体（不能说“只有 Owner 能读”）

2026-10-25 UTC 本片以 `bifrost-agent` 只读读取了 ClusterRole/ClusterRoleBinding，未读 Secret：

| 现有身份 | 为什么仍受信 | 防平台借用的边界 |
|---|---|---|
| `system:masters`；`helm-traefik`、`helm-traefik-crd` | Owner/K3s 安装恢复根，cluster-admin | 不能交给 Agent；平台不能改 RBAC 或 impersonate |
| `argocd-application-controller`、`argocd-applicationset-controller`、`argocd-server` @ cicd | GitOps 控制器，已有全局 Secret 权限 | S0 main Owner-only；此 namespace 不在 Argo 目标；S3b 禁止平台改 Argo ConfigMap，S3c 冻结 PodSpec |
| `tekton-pipelines-controller`、`tekton-pipelines-resolvers`、`tekton-triggers-core-interceptors` | Tekton 控制器读取凭证/解析对象；不能用 namespace RBAC 撤销集群授权 | workload SA 不继承控制器权限；S3d 限 TaskRun/PipelineRun，gitea-admin 零 Pod 配额，平台不能改控制器部署 |
| `cnpg-manager` @ cnpg-system | 数据库控制器 | 平台不能替换其代码/身份；本次没有新数据库对象 |
| `cluster-state-backup` @ kube-system | 集群恢复备份；备份仍含 Secret，应视同凭证 | 平台不能改其 CronJob、配置或读取备份；不将备份给 Agent |
| monitoring 的 `kube-prometheus-stack-operator`、`kube-prometheus-stack-grafana`、`kube-prometheus-stack-kube-state-metrics`、`loki` | 现有监控基础设施全局授权 | 平台不能改镜像/挂载；不把监控身份用于候选代码。收窄其全局权限属于独立后续工作 |
| `traefik` @ kube-system | Ingress/TLS 控制器 | 平台不能改控制器代码或其 SA/RBAC |
| `generic-garbage-collector`、`namespace-controller`、`resourcequota-controller`、`system:kube-controller-manager` | Kubernetes 生命周期控制器 | 集群控制面是恢复根，平台不能修改或模拟它们 |

`system:node` 绑定没有 subjects，不是一个已授予的 SA。节点/etcd/备份管理员仍是恢复信任根。
表中为既有信任边界，不宣称 namespace 能抵挡集群管理员或控制器失陷。
Owner 执行前核对在线绑定无新增，且现有 S3b/S3c/S3d 准入仍在；
本片没有执行服务器 dry-run、准入 live 探针、控制器借用攻击或集群写入。

## 6. 删除旧副本，读回

所有第 4、5 节检查通过且没有并行轮换才执行：

```bash
python3 scripts/gitea/move-bootstrap.py --kubeconfig ~/.bifrost-owner/kube/admin.yaml delete-old
```

先再次比较两边数据，再带旧副本 UID/resourceVersion 前提删除；旧副本中途变化会拒绝。
隔离脚本不验证 Secret 值，最终使用 `check` 验证新位置：

```bash
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n cicd get secret gitea-bootstrap --ignore-not-found -o name
kubectl --kubeconfig ~/.bifrost-owner/kube/admin.yaml -n gitea-admin get secret gitea-bootstrap -o name
KUBECONFIG=~/.bifrost-owner/kube/admin.yaml python3 scripts/gitea/check-bootstrap-isolation.py
bash scripts/gitea/rotate-admin-token.sh check
```

第一条无输出，第二条只打印名字，后两条无异常。记录时间、提交、隔离检查输出和消费方 run 证据。
只有这些实测通过才可称 S8 完成；源代码测试通过不代替上线验收。

## 回退

- 未删除旧副本：停止新脚本，使用迁移前的已复核版本；旧副本尚在。不要删 namespace。
- 已删除：仍用新脚本先 `rollback-dry-run` 再 `rollback-copy`（下列命令）。目标 cicd 已存在即拒绝，
  不能覆盖可能已轮换的 token。恢复后用 `verify` 比较，再切回旧版本；保留新副本直到问题解决。

```bash
python3 scripts/gitea/move-bootstrap.py --kubeconfig ~/.bifrost-owner/kube/admin.yaml rollback-dry-run
python3 scripts/gitea/move-bootstrap.py --kubeconfig ~/.bifrost-owner/kube/admin.yaml rollback-copy
python3 scripts/gitea/move-bootstrap.py --kubeconfig ~/.bifrost-owner/kube/admin.yaml verify
```

回退到 cicd 会重新暴露给该 namespace 的旧读取/挂载边界，是 Owner 的恢复动作，不能作为正常结束状态。
不回退 S0 分支保护，不复活旧 clone Secret 或被吊销的令牌，不自动删除隔离清单。

## 本机身份事件（TD-440）

Owner 报告：Mac 的 Gitea Keychain 在 2026-07-30 至 2026-10-25 存在管理员 `weitingzhao` 的缓存凭证，
2026-10-25 已删除，改用 `bifrost-mbp`（仅分支）。哪些推送实际使用该缓存，须从 Gitea activity 逐事件核定，不能由缓存存在推断。
已知反向证据（Work 567 BRIEF）：2026-10-25 03:36Z 的 platform main 推送及 03:40Z 的 infra main 推送者均为 `bifrost-mbp`。
这是 Owner 报告的事实，本片没有读取密码或另做真实推送。此时间窗的“推送者是 Owner”不能单独作为批准证据，也不能批量将这段历史标成 Owner 签收。
Owner 完整核对 admin 名单后，在真实 checkout 跑下列只读 metadata 检查；有其他 admin 则重复 `--admin`，
host 有别名则逐个指定 `--host`；每个真实 checkout 都须检查，可重复 `--checkout <path>`。检查覆盖全部实际 fetch/push URL、路径专属 username、helper 链、空值重置和配置来源。未知 helper 或来源返回 INCONCLUSIVE，必须另查账户元数据，不能放行。

```bash
python3 scripts/gitea/check-local-credential-identity.py --host 192.168.10.73:30300 --admin weitingzhao
```

后续服务端推送者证据、main 拒绝与历史授权回溯见 TD-440；本片不重新开放 main。
