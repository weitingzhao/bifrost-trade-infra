# LANE-W33D 报告

W-33 第 3 步。Mac 上的 Agent 不再持有管理员凭证。〇节四件按 Owner 2026-10-09 的决定落地（A、A、推荐那一组、A），没有另起方案。代码只在分支上，已推 origin，没有合 main。没有 apply，没有改 `~/.kube`、`~/.ssh`、`.env`，没有连节点，没有生成密钥，没有发版，没有写数据库。D10 仍是 BLOCKED。没有改 `api/internal/approvals/` 的审批语义，也没有改 `scripts/agent-guard/`（只提交补丁）。

## 改动

- bifrost-trade-infra · `cursor/w33d-infra` · `5c50c203ff4fcfcef7436eea2f1d138153691d9e` · Change-Id `If27d0a61140ce421d052d6e415498cba5cc49110` · 已推 origin
- bifrost-platform · `cursor/w33d-platform` · `b87b6a2f3f38d6ddf116d2c6d3b6b5e3f15a4727` · Change-Id `Iab3ddbfba277d2f6abd8b0cc58b619a41d6f3cf0` · 已推 origin
- bifrost-platform-plugin · 未改，未建分支。`origin/main` 仍是 `e335bd69f7b987ad4d091027adca99d69802ce81`

infra 分支从 `origin/main` `db899323eb9a1579f2e17f38c39e94b0b3a09a33` 开。platform 分支从 `origin/main` `dcc2d2144dc607d53a38b1dcdb36e8fe4685c6ef` 开。

## 一、只读身份

命名空间 `bifrost-access`，ServiceAccount `bifrost-agent`，空的 `kubernetes.io/service-account-token` Secret `bifrost-agent-token`（git 里没有 `data` / `stringData`）。不归 Argo。`ClusterRoleBinding bifrost-agent-view` 指向内置 `view`。`ClusterRole bifrost-agent-read` 补 view 没覆盖的日常 CRD，动词只有 `get` / `list` / `watch`。`pods/exec` 加 `pods get` 只在 research、plugin-market-data、plugin-flex-query。`pods/portforward` 只在 monitoring，`resourceNames` 只有 `prometheus-kube-prometheus-stack-prometheus-0`。没有 Secret 读，没有写动词。

2026-10-09 对照集群里的 `clusterrole/view`：已含 pods、pods/log、metrics.k8s.io 的 nodes 和 pods、tekton.dev 的 pipelines / pipelineruns / tasks / taskruns。不含 argoproj.io、postgresql.cnpg.io、traefik.io、monitoring.coreos.com。额外角色把这些和 metrics 又写了一遍，避免依赖聚合。未加 imagecatalogs、failoverquorums、publications、subscriptions、thanosrulers、prometheusagents、probes、applicationsets、verificationpolicies。

防线：`scripts/check_agent_access.py`（静态拒绝 Secret 读、写动词、越界 exec / port-forward）；`scripts/check-no-k8s-secrets.sh` 排除这一份空令牌清单，仍拒绝 `data` / `stringData`。

门禁：`python3 scripts/check_agent_access.py` → `static: 14 objects, 0 problems` / `ok`。`kubectl kustomize k8s/agent-access` → 281 行。`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl apply --dry-run=server -k k8s/agent-access` 退出 1，输出原样：

```
namespace/bifrost-access created (server dry run)
role.rbac.authorization.k8s.io/bifrost-agent-portforward created (server dry run)
role.rbac.authorization.k8s.io/bifrost-agent-exec created (server dry run)
role.rbac.authorization.k8s.io/bifrost-agent-exec created (server dry run)
role.rbac.authorization.k8s.io/bifrost-agent-exec created (server dry run)
clusterrole.rbac.authorization.k8s.io/bifrost-agent-read created (server dry run)
rolebinding.rbac.authorization.k8s.io/bifrost-agent-portforward created (server dry run)
rolebinding.rbac.authorization.k8s.io/bifrost-agent-exec created (server dry run)
rolebinding.rbac.authorization.k8s.io/bifrost-agent-exec created (server dry run)
rolebinding.rbac.authorization.k8s.io/bifrost-agent-exec created (server dry run)
clusterrolebinding.rbac.authorization.k8s.io/bifrost-agent-read created (server dry run)
clusterrolebinding.rbac.authorization.k8s.io/bifrost-agent-view created (server dry run)
Error from server (NotFound): error when creating "k8s/agent-access": namespaces "bifrost-access" not found
Error from server (NotFound): error when creating "k8s/agent-access": namespaces "bifrost-access" not found
```

两条 NotFound 分开核对过：`serviceaccount.yaml` 和 `token-secret.yaml`。命名空间还不存在，server dry-run 不会先把它留下，这是预期。没有真的 apply。

验收：合入并 apply 之后，`KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_agent_access.py --live` 退出 0。whoami 是 `system:serviceaccount:bifrost-access:bifrost-agent`，`get secrets -A` 是 no，三个命名空间的 `create pods/exec` 是 yes，data 与 bifrost-prod 是 no，Prometheus 那一个 Pod 的 port-forward 是 yes，别的名字是 no。

要 Owner 批：见文末清单第 1 步。本道没有 apply。

后续：`bifrost-platform/scripts/run_prometheus_pf.sh:39` 转发的是 Service `svc/kube-prometheus-stack-prometheus`，新 Role 只允许那一个 Pod。交换 kubeconfig 之后，bdev 的 `prometheus-pf` 会被拒绝。三个选项：A（推荐）把这条改成 `pod/prometheus-kube-prometheus-stack-prometheus-0`，正好落在已经写好的 `resourceNames` 里；B 让这个 session 改用 Owner 目录里的管理员 kubeconfig，等于把管理员凭证又放回 Agent 会跑的进程；C 先停这个 session，等另开一道再改。本道没有改这个脚本。

## 二、Owner 脚本

`scripts/owner/` 文件头都写明只给 Owner 用。`owner-env.sh` 只供 source：环境变量优先，否则读 `~/.bifrost-owner/owner.env`。`make-agent-kubeconfig.sh <输出> [管理员 kubeconfig]` 用管理员文件读令牌和 CA，令牌不进命令行，标准输出只有 `wrote <path> mode 600`。交换之前第二参数必须是 `~/.kube/bifrost-k3s.yaml`，因为默认路径 `~/.bifrost-owner/kube/admin.yaml` 那时还不存在。`move-owner-secrets.sh` 可重复执行，`--undo` 撤回；值不同则拒绝并且不打印值。`owner-run.sh` 的 `OWNER_KUBECONFIG` 默认改到 Owner 目录里的管理员文件。

防线：`scripts/owner/move-owner-secrets_test.sh`、`make-agent-kubeconfig_test.sh`、`owner-env_test.sh`。假值不出现在标准输出或标准错误。

门禁：三个测试都打印 `ok`。`bash scripts/owner/owner-run_test.sh` → `ok: owner-run refuses wrong status, expired approvals, a hash mismatch, and a piped yes`。`python3 scripts/k3s/test_rolling_reboot_plan.py` → 15 通过。`python3 -m unittest discover scripts/release` → 24 项，1 项原有跳过，OK。

验收：`bash scripts/owner/move-owner-secrets_test.sh && bash scripts/owner/make-agent-kubeconfig_test.sh && bash scripts/owner/owner-env_test.sh` 三条都是 `ok`，且输出里没有假值。

要 Owner 批：见清单第 2、3、4、5 步。本道没有执行。

后续：无。

## 三、读凭证的位置

搬走的键：infra `.env` 的 `OPS_ADMIN_TOKEN`、`REDIS_IB_PASSWORD`、`BIFROST_PG_PASSWORD_PREVIOUS`、`BIFROST_PG_PASSWORD_NEXT`；platform `.env` 的 `UNIFI_HOST`、`UNIFI_USER`、`UNIFI_PASS`、`UNIFI_API_KEY`；`k8s/base/secrets/` 里非 example 文件。`POSTGRES_PASSWORD` / `PGPASSWORD`、`REDIS_IB_PLATFORM_PASS`、平台管理员令牌不搬。

platform 用本仓库的 `scripts/unifi_owner_env.py` 和 `unifi_owner_env.sh`，不跨仓 source infra。八个会读 `UNIFI_*` 的脚本在读之前先填。`unifi_check_ports.py` 只读 `/tmp` 里的 JSON，没改。

`materialize_k8s_trade_secrets.py` 把 Secret 写到 `~/.bifrost-owner/secrets`，两个管理员键回写 owner.env。`trade-operator-tokens.sh` 优先读 Owner 目录里的 yaml，没有才回退仓库。`bifrost-password-rotate.sh` 的环境文件默认改成 owner.env。`sync_redis_ib_trade_config.sh` 仍读插件仓库自己的 `REDIS_IB_TRADE_*_PASS`，写出目录改到 Owner secrets。`rolling-reboot.sh` 的默认密钥改成 `~/.bifrost-owner/ssh/node`。

防线：platform `scripts/unifi_owner_env_test.py`。

门禁：`python3 scripts/unifi_owner_env_test.py` → `ok`。改过的 shell `bash -n` 通过。platform 没有改 Go，没跑 `go test`。

验收：`python3 scripts/unifi_owner_env_test.py` 打印 `ok`，且输出里没有假值。

要 Owner 批：见清单第 5 步。

后续：`bifrost-platform-plugin/scripts/redis-ib-env-users.sh:132` 会把密码写回 `TRADE_INFRA/k8s/base/secrets/bifrost-$env-secrets.yaml`。它 source 的是插件自己的 `.env`（同文件第 18 行 `ENV_FILE`），不读 infra `.env`，所以本道按道文件不改它。搬家之后再跑这个脚本，会在 Agent 能读的目录里把 Secret 文件造回来。

## 四、preflight 补丁

`agent-config/work/ops-arch/preflight-w33d.patch`。Bash、Read、Grep、Glob 的路径或文本里出现 Owner 目录或 `owner.env` 就拒绝。`KUBECONFIG=` 和 `--kubeconfig` 指向 `~/.kube/bifrost-k3s.yaml` 以外也拒绝，`~`、`$HOME`、`${HOME}` 和绝对路径都认。未设置 `KUBECONFIG` 的 `kubectl get pods` 放行。Edit 文档正文提到这些名字放行。拦截信息含「这是 Owner 的凭证，写操作走平台动作或 owner_run_command」。补丁注明 Cursor 与 Claude 共用这一份，Cursor 不用另改。`scripts/agent-guard/` 没有改。

防线：补丁里的 test.js 用例（16 条，DENY 必须含上面那句）。

门禁：在副本上 `patch --dry-run -p1` 与 `patch -p1` 都成功，`node scripts/agent-guard/test.js` → `101 通过 / 0 失败`。仓库里的 `preflight.js` 和 `test.js` `git diff` 为空。

验收：Owner 应用补丁之后，在工作区根 `node scripts/agent-guard/test.js` → 101 通过 / 0 失败。

要 Owner 批：见清单第 6 步。第 6 步必须在第 3 步之后：补丁会拦 `~/.kube/bifrost-agent.yaml`，第 2 步还要用这个路径。

后续：补丁应用前闸门还是旧的。

## 五、文档

`AGENT_FACTS.md` §8c、`CLAUDE.md` §3 与 §5、`cursor/rules/workspace.mdc` §3 写了同一张对照：apply → `plan_manifest` / `apply_manifest`，`create job --from` → `create_job_from_cronjob`，删 Job → `delete_finished_jobs`，删 Pod → `delete_pod`，rollout restart → `rollout_restart_deployment`，临时 Pod → `run_probe_pod`，起 run → `start_pipeline_run`，其余 → `owner_run_command`。查库用 `agent_reader`。exec 只在三个命名空间。port-forward 只有 Prometheus 那一个 Pod。parity-id `workspace-v17` → `workspace-v18`，两侧一致。

ADR §5 加了三条接受风险：同一 macOS 用户下 Owner 目录只靠 preflight 文本拦截；DB 属主密码四个库共用，等 TD-85；推 GitHub main 触发 Argo 自动同步，归 W-31。

`RATCHETS.md` 加了「Agent 只读身份（LANE-W33D）」。ops-arch README 的节点那一句改成 Agent 不能登录节点。

skill：两侧 `SKILL.md` 里没有 `kubectl apply` / `create` / `delete` / `exec` / `port-forward`。剩下的是 `kubectl get`、`logs`、`wait`（research-release、market-data-subscription-focus、research-loop-automation）。没有改 skill，没有 bump skill parity。

门禁：分支内两侧都是 `workspace-v18`。从工作区根跑 `bash scripts/check-agent-config-parity.sh` 退出 0，但它看的是符号链接指向的共享检出（仍是 main 的 `workspace-v17`），合进 main 之后才会看到 v18。

验收：合进 main 之后再跑 `bash scripts/check-agent-config-parity.sh`，`[workspace]` 仍是一致，且 `CLAUDE.md` 与 `workspace.mdc` 都是 `workspace-v18`。

要 Owner 批：无单独命令。文档随 infra 分支合入。

后续：本机 bdev 的 platform-api 仍把 `PLATFORM_KUBECONFIG` 指到 `~/.kube/bifrost-k3s.yaml`。交换之后这份文件是 `bifrost-agent`，本机 api 变成只读，相当于 STG 的观测角色。

## 六、plugin 未改

`bifrost-platform-plugin/scripts/redis-ib-env-users.sh` 第 18 行 `ENV_FILE="${ENV_FILE:-$ROOT/.env}"`，第 40 行 `source "$ENV_FILE"`。`TRADE_INFRA` 只用来拼 `k8s/base/secrets` 的写出路径（第 132 行），不 source infra `.env`。道文件说不读 infra `.env` 就不改。没有建 `cursor/w33d-plugin`。

## 七、CRD can-i

当前身份 `system:admin`（`kubectl auth whoami`）。Role 没有 apply，所以 `--as=system:serviceaccount:bifrost-access:bifrost-agent --as-group=system:serviceaccounts` 全部是 no，不能代表新 Role。admin 一列说明这些资源在集群里存在。上线后的核对在清单第 2 步和第 1 步之后的 `--live`。

| 命令 | admin | as bifrost-agent（未 apply） |
|---|---|---|
| list pods -A | yes | no |
| get pods --subresource=log -n research | yes | no |
| list applications.argoproj.io -A | yes | no |
| list appprojects.argoproj.io -A | yes | no |
| list clusters.postgresql.cnpg.io -A | yes | no |
| list backups.postgresql.cnpg.io -A | yes | no |
| list scheduledbackups.postgresql.cnpg.io -A | yes | no |
| list poolers.postgresql.cnpg.io -A | yes | no |
| list pipelineruns.tekton.dev -A | yes | no |
| list taskruns.tekton.dev -A | yes | no |
| list pipelines.tekton.dev -A | yes | no |
| list tasks.tekton.dev -A | yes | no |
| list ingressroutes.traefik.io -A | yes | no |
| list middlewares.traefik.io -A | yes | no |
| list prometheusrules.monitoring.coreos.com -A | yes | no |
| list servicemonitors.monitoring.coreos.com -A | yes | no |
| list podmonitors.monitoring.coreos.com -A | yes | no |
| list scrapeconfigs.monitoring.coreos.com -A | yes | no |
| list prometheuses.monitoring.coreos.com -A | yes | no |
| list alertmanagers.monitoring.coreos.com -A | yes | no |
| list pods.metrics.k8s.io -A | yes | no |
| list nodes.metrics.k8s.io -A | yes | no |
| get secrets -A | yes | no |
| create pods/exec -n research | yes | no |
| create pods/exec -n plugin-market-data | yes | no |
| create pods/exec -n plugin-flex-query | yes | no |
| create pods/exec -n data | yes | no |
| create pods/portforward/prometheus-kube-prometheus-stack-prometheus-0 -n monitoring | yes | no |
| create pods/portforward/not-prometheus -n monitoring | yes | no |

## 公开 API 变更

无。没有新 RPC，没有新外部依赖，没有改公开接口，没有新表或列。

## Breaking Changes

无代码破坏。Owner 按清单交换 kubeconfig、换节点密钥、搬走明文之后，Agent 的 kubectl 写、节点 SSH、以及读 Owner 目录会失败。这是这一步的目的。

## Owner 执行清单

本道没有执行下面任何一步。顺序不要换：第 6 步（preflight）必须在第 3 步（kubeconfig 已经换成只读文件）之后。换节点密钥必须先确认新密钥能登录，再删旧的。

命令在含 `k8s/agent-access` 的 infra 检出里跑（`cursor/w33d-infra`，或该提交合进 main 之后）。不要在共享检出里为了这一步切分支。

### 1. apply 只读身份

```bash
KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl apply -k k8s/agent-access
```

Claude 核对：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n bifrost-access get sa bifrost-agent` 能看到 ServiceAccount；`kubectl auth can-i list applications.argoproj.io --as=system:serviceaccount:bifrost-access:bifrost-agent -A` 为 yes；`kubectl auth can-i get secrets --as=system:serviceaccount:bifrost-access:bifrost-agent -A` 为 no。

回滚：

```bash
KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl delete -k k8s/agent-access
```

### 2. 写出只读 kubeconfig

这一步在交换之前，管理员文件还在 `~/.kube/bifrost-k3s.yaml`，所以要显式传入。默认路径此时还不存在。

```bash
bash scripts/owner/make-agent-kubeconfig.sh ~/.kube/bifrost-agent.yaml ~/.kube/bifrost-k3s.yaml
```

标准输出只应有一行 `wrote … mode 600`。

Claude 核对：`KUBECONFIG=~/.kube/bifrost-agent.yaml kubectl auth whoami` 的用户名是 `system:serviceaccount:bifrost-access:bifrost-agent`。然后 `KUBECONFIG=~/.kube/bifrost-agent.yaml python3 scripts/check_agent_access.py --live`。这时节点密钥和 `.env` 还没搬，ssh 与键名检查失败是预期；whoami 和 can-i 必须符合脚本里的 yes/no。不要打印令牌。

回滚：`rm -f ~/.kube/bifrost-agent.yaml`。集群里的 Role 还在，清单第 1 步的回滚才删它。

### 3. 交换两份 kubeconfig

```bash
mkdir -p ~/.bifrost-owner/kube ~/.bifrost-owner/ssh ~/.bifrost-owner/secrets
chmod 700 ~/.bifrost-owner ~/.bifrost-owner/kube ~/.bifrost-owner/ssh ~/.bifrost-owner/secrets
mv ~/.kube/bifrost-k3s.yaml ~/.bifrost-owner/kube/admin.yaml
mv ~/.kube/bifrost-agent.yaml ~/.kube/bifrost-k3s.yaml
chmod 600 ~/.kube/bifrost-k3s.yaml ~/.bifrost-owner/kube/admin.yaml
```

Claude 核对：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl auth whoami` 仍是 `bifrost-agent`，不是 `system:admin`。`test -f ~/.bifrost-owner/kube/admin.yaml` 为真。不要 `cat` 这两份文件。

回滚：

```bash
mv ~/.kube/bifrost-k3s.yaml ~/.kube/bifrost-agent.yaml
mv ~/.bifrost-owner/kube/admin.yaml ~/.kube/bifrost-k3s.yaml
```

### 4. 换节点密钥

先登录，再删旧的。六台：`192.168.10.73`、`192.168.10.70`、`192.168.10.75`、`192.168.10.77`、`192.168.10.79`、`192.168.10.60`。`ssh-keygen` 会要口令。不要把新私钥加进 ssh-agent，不要把私钥打出来。

```bash
ssh-keygen -t ed25519 -f ~/.bifrost-owner/ssh/node -C bifrost-owner-node
chmod 700 ~/.bifrost-owner/ssh
chmod 600 ~/.bifrost-owner/ssh/node
for host in 192.168.10.73 192.168.10.70 192.168.10.75 192.168.10.77 192.168.10.79 192.168.10.60; do
  ssh -F /dev/null -o IdentitiesOnly=yes -i ~/.ssh/id_rsa "vision@${host}" 'cat >> ~/.ssh/authorized_keys' < ~/.bifrost-owner/ssh/node.pub
done
for host in 192.168.10.73 192.168.10.70 192.168.10.75 192.168.10.77 192.168.10.79 192.168.10.60; do
  ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node "vision@${host}" true
done
```

上面第二轮全部成功之后，才删旧行，并用新密钥再确认一次，然后才删本机没在用的 `bifrost_deploy`：

```bash
for host in 192.168.10.73 192.168.10.70 192.168.10.75 192.168.10.77 192.168.10.79 192.168.10.60; do
  ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node "vision@${host}" "grep -v 'gh:weitingzhao' ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.w33d && mv ~/.ssh/authorized_keys.w33d ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
done
for host in 192.168.10.73 192.168.10.70 192.168.10.75 192.168.10.77 192.168.10.79 192.168.10.60; do
  ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node "vision@${host}" true
done
rm -f ~/.ssh/bifrost_deploy ~/.ssh/bifrost_deploy.pub
```

Claude 核对：六台 `ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -i ~/.bifrost-owner/ssh/node vision@<host> true` 都是退出 0。`ssh -F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes -i ~/.ssh/id_rsa vision@<host> true` 应失败。不要打印私钥。

回滚：第二轮 `true` 有任何一台失败，就停，不要跑 `grep -v`。用旧密钥把刚加上的公钥行删掉：

```bash
for host in 192.168.10.73 192.168.10.70 192.168.10.75 192.168.10.77 192.168.10.79 192.168.10.60; do
  ssh -F /dev/null -o IdentitiesOnly=yes -i ~/.ssh/id_rsa "vision@${host}" "grep -v 'bifrost-owner-node' ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.w33d && mv ~/.ssh/authorized_keys.w33d ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
done
```

旧行已经删掉、又想恢复时，用还在本机的 `~/.ssh/id_rsa.pub` 按同样的重定向加回去。不要在新密钥失败之后删除 `gh:weitingzhao`。

### 5. 搬走明文

```bash
bash scripts/owner/move-owner-secrets.sh
```

Claude 核对：只看键名。`OPS_ADMIN_TOKEN`、`REDIS_IB_PASSWORD`、`BIFROST_PG_PASSWORD_PREVIOUS`、`BIFROST_PG_PASSWORD_NEXT` 不在 infra `.env`，在 `~/.bifrost-owner/owner.env`。`UNIFI_HOST`、`UNIFI_USER`、`UNIFI_PASS`、`UNIFI_API_KEY` 不在 platform `.env`，在同一份 owner.env。`k8s/base/secrets/` 只剩 example。`POSTGRES_PASSWORD` 仍在 infra `.env`。用 `awk -F= '/^[A-Z0-9_]+=/{print $1}'`，不要打印值。

回滚：

```bash
bash scripts/owner/move-owner-secrets.sh --undo
```

### 6. 应用 preflight 补丁

补丁路径相对 infra 仓库。工作区根的 `scripts/agent-guard` 是同一份文件的符号链接。

```bash
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra
patch -p1 < agent-config/work/ops-arch/preflight-w33d.patch
cd /Users/vision-mac-trader/Desktop/stocks
node scripts/agent-guard/test.js
```

Claude 核对：最后一行是 `101 通过 / 0 失败`。`cat ~/.bifrost-owner/owner.env` 会被闸门拒绝，拒绝文本里有「这是 Owner 的凭证，写操作走平台动作或 owner_run_command」。`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl get pods` 放行。

回滚：

```bash
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra
patch -R -p1 < agent-config/work/ops-arch/preflight-w33d.patch
```

### 7. （可选）收发布放行

auto mode 的发布放行在 `.claude/auto-mode/`。本道没有改它。要不要收，由 Owner 定。Claude 核对：`claude auto-mode config` 里还能不能直接放行 `release.sh stg` / `prod`。回滚是把改之前的 payload 再应用一次。

### 上线后 Claude 再跑

清单 1–6 都做完之后：

```bash
KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_agent_access.py --live
```

预期退出 0。另外按道文件：`release.sh window` 与一次 dry-run、一次 B 级 `delete_finished_jobs`、对账漂移 0。这些本道都没跑。

## 本道没有做的

- 没有 apply，没有改本机 kubeconfig、ssh、`.env`，没有连节点，没有生成密钥。
- 没有跑 `check_agent_access.py --live`（上线前 whoami 仍是管理员，按设计会失败）。
- 没有改 skill。
- 没有改 plugin。
- 没有改 `prometheus-pf` 的 Service 转发。见第一节后续，等 Owner 在 A/B/C 里选。
- 没有需要道文件以外再拍板的架构决定。上面 prometheus-pf 是后续，不是本道擅自改 Role。

## Claude 验收（2026-10-09）

结论：**通过**。Claude 补了几笔（infra `32c48e4`，plugin `cursor/w33d-plugin` `6c1c9d7`），Owner 执行清单按下面两处调整执行。

1. **复核**：
   - `k8s/agent-access`：只有 `view`（实测聚合后 15 条规则全是只读，不含 Secret，Tekton 由 `tekton-aggregate-view` 聚合进来）、几类 CRD 的只读、三个命名空间的 exec，以及 Prometheus 那一个 Pod 的 port-forward；
   - 集群里没有别的东西绑着 `view`；
   - 6 台主机的 root 都不能经 ssh-agent 登录，节点上只有 `vision` 一个账号授权了密钥，所以删掉 `gh:weitingzhao` 那一行就够了；
   - Owner 脚本的 4 个测试、检查脚本、发版测试、滚动重启测试、kustomize 都过；分支没有改 `preflight.js`。
2. **补：插件 `.env` 里可写 `ib:*` 的两个 redis-ib 用户**：
   - `REDIS_IB_GATEWAY_PASS`、`REDIS_IB_TRADE_PROD_PASS` 按 ACL 能写 `ib:operator:cmd`（D10）。`move-owner-secrets.sh` 把它们一并挪进 `owner.env`，`REDIS_IB_PLATFORM_PASS` 留着；测试和 `check_agent_access.py` 跟着加；
   - 插件的 `render-redis-ib-acl.sh` 和 `redis-ib-env-users.sh` 也读 `owner.env`。缺任何一个密码时，渲染照旧拒绝，不会生成带空密码的 ACL（实测）；`switch` 更新 Owner 目录里那份 Secret 文件。Cursor 担心的「写回 Agent 能读的目录」不会发生：原脚本只在文件已经存在时才写。
3. **补：preflight 拦截「只给 Owner 运行的脚本」**：
   - 闸门只看命令文本，Agent 一运行这些脚本就能读到 Owner 凭证，比如 `render-redis-ib-acl.sh` 会把全部 redis-ib 密码打到标准输出；
   - 补丁现在也拦截：`scripts/owner/` 下的四个脚本、Secret 物化、属主密码轮换、redis-ib 的两个脚本、UniFi 脚本；`*_test` 照常放行；
   - 在打了补丁的副本上，`test.js` **112 通过 / 0 失败**（清单第 6 步的预期改成 112）。
4. **清单第 5 步的核对加一项**：插件 `.env` 不再有 `REDIS_IB_GATEWAY_PASS`、`REDIS_IB_TRADE_PROD_PASS`，仍有 `REDIS_IB_PLATFORM_PASS`。
5. **`prometheus-pf`**：`kubectl port-forward svc/…` 会先解析到 Pod，再对那个 Pod 做 port-forward，按理也在 resourceNames 范围内。第 2 步之后，用只读 kubeconfig 实测 svc 写法；不行再把 `run_prometheus_pf.sh` 改成 `pod/prometheus-kube-prometheus-stack-prometheus-0`。
6. **合并顺序**：
   - 先合：代码、清单、补丁文件，以及 platform、plugin 两条分支。脚本在 Owner 目录不存在时照旧读原来的位置；
   - 后合：AGENT_FACTS、CLAUDE.md、workspace.mdc（parity v18）、ADR。等 Owner 执行完、Claude 验收通过再合，以免 Agent 在凭证还没换时就按新规则行事。
