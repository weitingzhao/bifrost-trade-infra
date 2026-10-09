# LANE-W33D — W-33 第 3 步：Mac 上的 Agent 不再持有管理员凭证

登记：`agent-config/WORK.md` 的 W-33（匹配 LANE-W33D）。依据：同目录 `W33-step3-2026-10-09.md`，Owner 2026-10-09 定「〇」节四件，全部按推荐。

这是瘦身计划的最后一道。本道只写清单、脚本、检查、补丁和文档；**集群和本机的改动全部由 Owner 执行**，顺序和命令写进报告。

仓库与分支（从最新 origin/main 开独立 worktree）：

- bifrost-trade-infra · `cursor/w33d-infra`
- bifrost-platform · `cursor/w33d-platform`（只改 UniFi 脚本读凭证的位置）
- bifrost-platform-plugin · `cursor/w33d-plugin`（只改 `scripts/redis-ib-env-users.sh` 读凭证的位置，前提是它确实从 infra `.env` 读）

先读：

- `W33-step3-2026-10-09.md`（实测与决定）；
- `README.md` 的「Cursor 共用规则」；
- `scripts/agent-guard/README.md` 和 `preflight.js` 现有的拦截方式（只读，不改）。

## 事实（2026-10-09 实测，只看键名和指纹）

- **节点 root**：
  - 6 台主机（`.73 .70 .75 .77 .79` 和 `gpu-server .60`）的 `vision` 账号都只授权了一把 `ssh-rsa`，注释 `gh:weitingzhao`，指纹 `SHA256:RXvH+heBvTbD3pMSpyJjWEkPlfRNtrU2rxM4Sryel7c`，也就是本机的 `~/.ssh/id_rsa`（同时是 GitHub 密钥）；
  - 这把密钥已在 ssh-agent 里解锁；节点上免密 sudo；
  - `~/.ssh/bifrost_deploy` 没有授权到任何节点，也没有口令；
  - `~/.ssh/config` 的 `Host *` 带 `IdentityFile ~/.ssh/id_rsa`。
- **kubeconfig**：
  - `~/.kube/bifrost-k3s.yaml` 是集群管理员；
  - 本机 bdev 的 platform-api 用 `PLATFORM_KUBECONFIG` 指向它；`prometheus-pf` 用它做 port-forward；
  - Prometheus 的 Pod 是 `monitoring/prometheus-kube-prometheus-stack-prometheus-0`。
- **管理员级明文**（Agent 能读）：
  - infra `k8s/base/secrets/` 下的 `bifrost-{dev,stg,prod}-secrets.yaml` 和 `bifrost-{dev,stg,prod}-db-owner.yaml`（gitignore，没进 git）；
  - infra `.env`：`OPS_ADMIN_TOKEN`、`REDIS_IB_PASSWORD`、`BIFROST_PG_PASSWORD_PREVIOUS`、`BIFROST_PG_PASSWORD_NEXT`；
  - platform `.env`：`UNIFI_HOST`、`UNIFI_USER`、`UNIFI_PASS`、`UNIFI_API_KEY`。
- **不在本道**：
  - DB 日常密码 `POSTGRES_PASSWORD` / `PGPASSWORD`（`bifrost` 属主，四个库共用）：TD-85；
  - 平台管理员令牌：ADR §5，保留；
  - `REDIS_IB_PLATFORM_PASS`：ACL 受限，本机 platform-api 要用；
  - 推 GitHub main 触发 Argo 自动同步：W-31。
- 工作区根目录下有一批旧 worktree 目录（`*-a6r-report`、`*-d1`、`*-e1`、`*-phase3-*`），里面有脚本副本。**本道只改正式检出对应的仓库**，不碰这些目录。

## 要做

### 一、只读身份（infra `k8s/agent-access/`，不归 Argo，手工 apply）

- 命名空间 `bifrost-access`，ServiceAccount `bifrost-agent`，`kubernetes.io/service-account-token` 类型的长期令牌 Secret。
- ClusterRoleBinding：
  - `bifrost-agent` → `view`；
  - 另加只读角色：metrics.k8s.io 的 nodes、pods，以及 `view` 没覆盖、但 Agent 日常要读的 CRD。逐个实测：`kubectl auth can-i list <资源> --as=…` 对 Tekton、Argo、CNPG、Traefik、monitoring.coreos.com 给 yes。
- `pods/exec` 和 `pods get`：只在 research、plugin-market-data、plugin-flex-query 绑定（Role + RoleBinding）。
- `pods/portforward`：只在 monitoring，`resourceNames: [prometheus-kube-prometheus-stack-prometheus-0]`。
- **绝对不能有**：Secret 的读、任何写、其他命名空间的 exec 和 port-forward、集群级写。

### 二、Owner 用的脚本（infra `scripts/owner/`，文件头写明「只给 Owner 用，Agent 不运行」）

1. `make-agent-kubeconfig.sh <输出路径>`：
   - 用 `OWNER_KUBECONFIG`（默认 `~/.bifrost-owner/kube/admin.yaml`；交换文件之前用 `~/.kube/bifrost-k3s.yaml`，由参数指定）读取 `bifrost-access` 的令牌和集群 CA；
   - 写出只用这个令牌的 kubeconfig，服务器地址与管理员那份相同，权限 600；
   - 令牌不打印，也不进命令行。
2. `move-owner-secrets.sh [--undo]`：
   - 把上面「管理员级明文」清单里的键，从对应的 `.env` 挪进 `~/.bifrost-owner/owner.env`（600）；
   - 把 `k8s/base/secrets/` 下的非 `.example` 文件挪进 `~/.bifrost-owner/secrets/`；
   - 全程不打印值，可重复执行；
   - `--undo` 原样放回。
3. `owner-env.sh`：一个可以 `source` 的小函数，给下面这些脚本取凭证用。优先用环境变量，其次读 `~/.bifrost-owner/owner.env`。
4. 改成从 Owner 目录取凭证的脚本（先 grep 确认每个脚本现在读的是哪个文件，没用到的不改）：
   - infra：`materialize_k8s_trade_secrets.py`、`trade-operator-tokens.sh`、`bifrost-password-rotate.sh`、`sync_redis_ib_trade_config.sh`；
   - infra：`scripts/k3s/rolling-reboot.sh`，`BIFROST_SSH_KEY` 默认改成 `~/.bifrost-owner/ssh/node`；
   - infra：`scripts/owner/owner-run.sh`，`OWNER_KUBECONFIG` 默认改成 `~/.bifrost-owner/kube/admin.yaml`；
   - platform：`scripts/unifi_*`；
   - plugin：`scripts/redis-ib-env-users.sh`。

### 三、检查（infra `scripts/check_agent_access.py`，加 `--live`）

- **静态**：
  - `k8s/agent-access` 能渲染；
  - 没有 Secret 的读，没有写 verbs；exec 和 port-forward 的范围与上面一致。
- **`--live`**，用当前的 `~/.kube/bifrost-k3s.yaml`：
  - `kubectl auth whoami` 是 `system:serviceaccount:bifrost-access:bifrost-agent`；
  - can-i 矩阵（每行写清楚期望值）：
    - 能：list pods、get pods/log、research 的 exec、Prometheus 那个 Pod 的 port-forward；
    - 不能：get secrets、cicd 里 create pipelineruns、data 和 bifrost-prod 的 exec、其他 Pod 的 port-forward、delete pods、patch deployments、create namespaces；
  - `ssh -F /dev/null -o BatchMode=yes vision@<6 台>` 只走 ssh-agent，**全部失败**；
  - Agent 能读到的 `.env`（infra、platform）里没有清单上的键；`k8s/base/secrets/` 下只剩 `.example`。

### 四、preflight 补丁（只写补丁文件，不改 `scripts/agent-guard/`）

`agent-config/work/ops-arch/preflight-w33d.patch`，对 `scripts/agent-guard/preflight.js` 和 `test.js` 的 diff，由 Owner 应用：

- 拦截：Bash 命令、Read、Grep、Glob 的路径或文本里出现 `.bifrost-owner`、`owner.env`；
- 拦截：`KUBECONFIG=` 或 `--kubeconfig` 指向 `~/.kube/bifrost-k3s.yaml` 以外的文件。`$HOME`、`~` 和绝对路径三种写法都要认；
- 拦截信息写清楚：「这是 Owner 的凭证，写操作走平台动作或 `owner_run_command`」；
- `test.js` 加对应用例：上面每一种写法都被拦，正常的 `KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl get pods` 放行；
- Claude 和 Cursor 共用这一份闸门，补丁里注明 Cursor 侧不用另改。

### 五、文档

- AGENT_FACTS §8c：
  - kubeconfig 是只读的（`bifrost-agent`）；
  - 写操作和平台动作的对照表：apply → `plan_manifest` / `apply_manifest`，`create job --from` → `create_job_from_cronjob`，删 Job → `delete_finished_jobs`，删 Pod → `delete_pod`，rollout restart → `rollout_restart_deployment`，临时 Pod → `run_probe_pod`，起 run → `start_pipeline_run`，其余 → `owner_run_command`；
  - 查库用 `agent_reader`；
  - exec 只在三个命名空间；
  - port-forward 只有 Prometheus。
- CLAUDE.md 与 `cursor/rules/workspace.mdc` 同步（bump parity-id）：§3 / §5 里所有「kubectl 写」的说法改成上面的对照。
- skill：凡是写着 `kubectl apply`、`create`、`delete`、`exec`（三个命名空间以外）、`port-forward` 的，改成对应的动作。两侧同步。
- ADR §5「已知的接受风险」加三条：
  - 同一个 macOS 用户下，Owner 目录只靠 preflight 文本拦截；
  - DB 属主密码四个库共用，等 TD-85；
  - 推 GitHub main 会触发 Argo 自动同步（platform overlay、research），归 W-31。
- RATCHETS.md 登记 `check_agent_access.py` 和 preflight 的新测试。

## 防线

- `check_agent_access.py`：静态，加 `--live`。
- preflight `test.js` 的新用例（随补丁）。
- `move-owner-secrets.sh` 的测试：用临时目录和假的 `.env`，挪走、撤回、重复执行都要对，输出里不出现任何值。
- `make-agent-kubeconfig.sh` 的测试：用假的 kubectl，输出文件权限 600，标准输出里不出现令牌。

## 门禁

- infra：
  - `python3 scripts/check_agent_access.py`（静态）；
  - `kubectl kustomize k8s/agent-access`；
  - `kubectl apply --dry-run=server -k k8s/agent-access`（只读的 dry-run）。`bifrost-access` 命名空间还不存在，dry-run 里这个命名空间下的对象会报 NotFound，属于预期；集群级对象和其他命名空间里的 Role、RoleBinding 应该都被接受。结果原样写进报告；
  - 新测试；
  - `python3 -m unittest discover scripts/release`；
  - `bash agent-config/scripts/check-agent-config-parity.sh`；
- platform 和 plugin：改过的脚本 `bash -n`，以及它们现有的测试。

## 报告

写 `agent-config/work/ops-arch/reports/LANE-W33D.md`，格式照 README，另附「**Owner 执行清单**」。每一步写原样命令、执行后 Claude 怎么核对、怎么回滚：

1. `kubectl apply -k k8s/agent-access`；
2. `bash scripts/owner/make-agent-kubeconfig.sh ~/.kube/bifrost-agent.yaml`。Claude 用 `KUBECONFIG=~/.kube/bifrost-agent.yaml` 跑 `check_agent_access.py --live` 里 kubeconfig 相关的部分；
3. 建 `~/.bifrost-owner/{kube,ssh,secrets}`（700），交换两份 kubeconfig；
4. 节点密钥：
   - `ssh-keygen -t ed25519 -f ~/.bifrost-owner/ssh/node`（设口令，不加进 ssh-agent）；
   - 用现有的访问把公钥加到 6 台主机；
   - `ssh -F /dev/null -o IdentityAgent=none -i ~/.bifrost-owner/ssh/node vision@<每台> true` 全部成功之后，再删各主机上 `gh:weitingzhao` 那一行；
   - `rm ~/.ssh/bifrost_deploy ~/.ssh/bifrost_deploy.pub`；
   - **先确认新密钥能登录，再删旧的**，避免把自己锁在外面；
5. `bash scripts/owner/move-owner-secrets.sh`；
6. 在工作区根应用 preflight 补丁，跑 `node scripts/agent-guard/test.js`；
7. （可选）收一收 auto mode 里那组发布放行规则。

上线后由 Claude 跑完整的 `check_agent_access.py --live`、release.sh 的 window 检查和 dry-run、一次 B 级动作，以及对账。

报告从 origin/main 另开 worktree 提交，推 main 用同一条命令：
`bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`

## 不做

- 多 Agent 运行时：任务与租约、Agent 主机守护进程、交互总线、推理网关、额度账本；
- 发布队列；
- RP 发版策略（`cursor/rp-*` 两条分支不合）；
- 认领与待办箱；
- 工作项编号规则；
- Grok Bot 相关的任何事（它暂停中：不验收 LANE-N / LANE-M2，不收尾它的台账）。
- 不改 `api/internal/approvals/` 的审批语义。
- **不改 `scripts/agent-guard/`**：只写补丁文件。
- **不执行任何 Owner 步骤**：不 apply，不动 `~/.kube`、`~/.ssh`、`.env`，不连节点改 `authorized_keys`，不生成密钥。
- 不读任何凭证的值。需要确认「某个键在不在」时，只看键名。
- 不碰工作区根目录下的旧 worktree 目录。
- 暂缓、不在瘦身范围：TWS 自动重启、交易区迁移、网络分区。
