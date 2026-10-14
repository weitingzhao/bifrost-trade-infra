# Owner 操作单：W-31 第 2 轮 2.1 数据层上线（O5–O10）

起草 2026-10-14（统筹线程）。依据：设计 v5 §5.1、§5.7；infra 分支 `w31/agentrt-21-infra`（含 db-step、库对象、redis-agents、迁移 Job）、
`w31/agentrt-21-infra-roles`（过渡矩阵）、`w31/agentrt-21-infra-after`（完整矩阵与逻辑备份目标）；平台代码已在主线 `b50d827`。

**前提（统筹方已查实）**：CNPG 主库是 `bifrost-postgres-1`（每次照下面的命令现查）；`max_connections` 200，过去 7 天峰值 125，
新六个角色的上限合计 32（owner 各 4，runtime PROD 10、STG/DEV 各 5），最坏 157；默认存储类 `local-path`。
**正式环境平台要先发 #18**（`b50d827`）：迁移 Job 用的是 `:prod` 镜像，里面要有 `agentrt-migrate` 子命令。

每一步的格式：做什么 → 在哪做 → 命令（原样可运行）→ 改了正式环境的什么 → 怎么回退 → 做完回什么。
命令都在**你自己的终端**跑（管理员身份 `~/.bifrost-owner/kube/admin.yaml`），统筹方读不到你的终端输出，回一句话即可。

---

## 第 1 步　生成 8 个密码，建 6 个 Secret，DEV 两行写进 `~/.pgpass`（O5）

密码只在你的机器上：文件放 `~/.bifrost-owner/agentrt/`（权限 600，无换行）。已存在的文件不会被覆盖。

```bash
umask 077; mkdir -p ~/.bifrost-owner/agentrt && cd ~/.bifrost-owner/agentrt && for n in redis-agents-prod redis-agents-stg owner-prod owner-stg owner-dev runtime-prod runtime-stg runtime-dev; do [ -s "$n" ] || printf %s "$(openssl rand -hex 24)" > "$n"; done; ls -l
```

```bash
( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; d="$HOME/.bifrost-owner/agentrt"; for e in prod stg; do kubectl -n bifrost-platform-$e create secret generic redis-agents --from-file=password="$d/redis-agents-$e" --dry-run=client -o yaml | kubectl apply -f - && kubectl -n bifrost-platform-$e create secret generic agentrt-db-owner --from-file=password="$d/owner-$e" --dry-run=client -o yaml | kubectl apply -f - && kubectl -n bifrost-platform-$e create secret generic agentrt-db-runtime --from-file=password="$d/runtime-$e" --dry-run=client -o yaml | kubectl apply -f - || break; done )
```

```bash
d="$HOME/.bifrost-owner/agentrt"; touch ~/.pgpass && chmod 600 ~/.pgpass && printf '192.168.10.73:30432:bifrost_platform_dev:agentrt_owner_dev:%s\n192.168.10.73:30432:bifrost_platform_dev:platform_agentrt_dev:%s\n' "$(cat "$d/owner-dev")" "$(cat "$d/runtime-dev")" >> ~/.pgpass
```

- 改了什么：两个平台命名空间各 3 个 Secret（`redis-agents`、`agentrt-db-owner`、`agentrt-db-runtime`）；本机 `~/.pgpass` 两行。不重启任何东西。
- 回退：`kubectl -n bifrost-platform-<env> delete secret <名字>`；删掉 `~/.pgpass` 里那两行。
- 做完回：「Secret 建好了」。

## 第 2 步　推 infra 分支 1：redis-agents 上线（O7）

**统筹方做**，你只要在线程里回「推 redis-agents」。统筹方：`release.sh window` → 把 `w31/agentrt-21-infra` 合进 infra 主线并推送。
Argo 自动同步：两个平台命名空间各新建 redis-agents（Deployment、1Gi `local-path` 卷、ClusterIP Service、只放行 platform-api/workers 的
NetworkPolicy）；平台 Pod 一个字段不变、不重启。db-step 文件和迁移 Job 清单也随之进主线（它们不会自己运行）。

- 统筹方随后核对：两个 redis-agents Pod Running、带密码能 PING、没有 NodePort；两个平台 App 仍 Healthy。
- 回退：统筹方回滚这次合并提交并推送，Argo 删掉 redis-agents（数据只是可重建的信号，丢了无妨）。

## 第 3 步　建六个登录角色 + 设密码 + 过渡矩阵（O6 前半；一个发布窗口里做完）

为什么要连着做：主线的角色矩阵检查器认识的登录角色里没有这六个，建好角色到矩阵更新之间，任何 Trade 发布前的检查都会失败。
所以**统筹方先占住发布窗口并推过渡矩阵**（`w31/agentrt-21-infra-roles`，六个角色写 `connect: []`），你接着做下面三块，做完统筹方放开窗口。
你在线程里回「开始建角色」，统筹方回「窗口占好了、过渡矩阵已推」之后再跑：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git pull -q --ff-only && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; p=$(kubectl -n data get pods -l cnpg.io/cluster=bifrost-postgres,cnpg.io/instanceRole=primary -o jsonpath='{.items[0].metadata.name}'); echo "primary=$p"; [ -n "$p" ] || exit 1; for e in dev stg prod; do kubectl -n data exec -i "$p" -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=$e -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles.sql && kubectl -n data exec -i "$p" -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -v env=$e -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-1-roles-verify.sql || { echo "STOP at $e"; break; }; done; kubectl apply -k k8s/data/role-matrix )
```

设六个密码（交互式，密码不进命令行、不进日志）：先进 psql——

```bash
( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; p=$(kubectl -n data get pods -l cnpg.io/cluster=bifrost-postgres,cnpg.io/instanceRole=primary -o jsonpath='{.items[0].metadata.name}'); kubectl -n data exec -it "$p" -c postgres -- psql -U postgres -d postgres -X )
```

然后对每个角色：在**另一个**终端窗口跑对应的 `pbcopy < ~/.bifrost-owner/agentrt/<文件>`，回到 psql 输入 `\password <角色>`，粘贴两次。
对照：`agentrt_owner_prod`←`owner-prod`、`platform_agentrt_prod`←`runtime-prod`、`agentrt_owner_stg`←`owner-stg`、
`platform_agentrt_stg`←`runtime-stg`、`agentrt_owner_dev`←`owner-dev`、`platform_agentrt_dev`←`runtime-dev`。完了 `\q`。

- 改了什么：共享 CNPG 集群里新增六个登录角色（无超级用户、无建库建角色权限、连接上限 4/10/5）；角色矩阵 ConfigMap 更新。
  这是 PROD 集群上的 DDL，你跑这条命令本身就是批准。
- 回退：`…-1-roles-rollback.sql`（把角色设为 NOLOGIN，不删）；矩阵回退由统筹方回滚过渡提交。
- 做完回：「角色和密码好了」（统筹方随即放开窗口）。

## 第 4 步　建三个库 + 收紧连接 + 放行迁移的入站策略（O6 后半）

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; kubectl apply -n data -f k8s/data/databases.yaml && p=$(kubectl -n data get pods -l cnpg.io/cluster=bifrost-postgres,cnpg.io/instanceRole=primary -o jsonpath='{.items[0].metadata.name}') && for i in $(seq 1 30); do n=$(kubectl -n data exec -i "$p" -c postgres -- psql -U postgres -d postgres -X -At -c "SELECT count(*) FROM pg_database d JOIN pg_roles r ON r.oid = d.datdba WHERE (d.datname, r.rolname) IN (('bifrost_platform','agentrt_owner_prod'),('bifrost_platform_stg','agentrt_owner_stg'),('bifrost_platform_dev','agentrt_owner_dev'))"); [ "$n" = 3 ] && break; sleep 5; done; echo "databases ready: $n/3"; [ "$n" = 3 ] || exit 1; for e in dev stg prod; do db=bifrost_platform_$e; [ $e = prod ] && db=bifrost_platform; kubectl -n data exec -i "$p" -c postgres -- psql -U postgres -d $db -X -v ON_ERROR_STOP=1 -v env=$e -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect.sql && kubectl -n data exec -i "$p" -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d $db -X -v ON_ERROR_STOP=1 -v env=$e -f - < scripts/release/db-steps.d/sql/2026-10-14-w31-agentrt-2-connect-verify.sql || { echo "STOP at $e"; exit 1; }; done; kubectl apply -n data -f k8s/data/postgres-ingress-network-policy.yaml )
```

- 改了什么：CNPG 上三个新库（属主各环境的 owner 角色；`databases.yaml` 里原有四个库的声明不变）；三个库收回 PUBLIC 的连接、
  只给本环境两个角色和 `agent_reader`、`role_matrix_reader`，PROD 库另给备份用的 `bifrost` 只读；`data` 里新增一条入站策略，
  只放行两个平台命名空间里 platform-api、platform-workers、agentrt-migrate 的 Pod 到 5432。
- 回退：`…-2-connect-rollback.sql`（收回授权，不删库）；删库要你另行决定（空库，无数据）。
- 做完回：「库好了」。

## 第 5 步　迁移：STG → PROD →（统筹方）DEV（O10）

统筹方先核对：`:stg` / `:prod` 镜像的 digest 等于正在跑的 platform-api（#18 发完之后）；把四个迁移文件里含 `drop|truncate` 的行列给你
（预计只有触发器名里的 `TRUNCATE` 守卫和 `dropped` 状态字样，不是删表语句）。你在线程里回「迁 STG」：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; kubectl create -f k8s/agentrt-migrate/stg/job.yaml )
```

统筹方核对 STG（只读）：库里 `agentrt` 的表、触发器、种子都在，`schema_migration` 四行。之后你看了 SQL 清单、在线程里回「迁 PROD」再跑：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; kubectl create -f k8s/agentrt-migrate/prod/job.yaml )
```

- 改了什么：PROD `bifrost_platform` 里建 `agentrt` schema、全部表和守卫、授权、种子（7 个身份、6 条能力事实）。PROD DDL，你跑这条就是批准。
- 回退：迁移只往前；回退 = 在 `bifrost_platform` 里 `DROP SCHEMA agentrt CASCADE`（库里没有别的东西），要你另行决定。
- DEV：统筹方用你写进 `~/.pgpass` 的 DEV owner 凭据在本机跑 `platform-api agentrt-migrate`（只碰 `bifrost_platform_dev`）。

## 第 6 步　完整角色矩阵与逻辑备份（三个库都迁完之后）

统筹方先用 `w31/agentrt-21-infra-after` 自己的检查器和矩阵、以只读身份跑一遍，0 差异才合并推送；然后请你：

```bash
cd ~/Desktop/stocks/bifrost-trade-infra && git pull -q --ff-only && ( export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml"; kubectl apply -k k8s/data/role-matrix && kubectl apply -k k8s/data/logical-backup )
```

- 改了什么：矩阵 ConfigMap 覆盖七个库；夜间逻辑备份多一个目标 `bifrost_platform:agentrt`。
- 之后统筹方手动起一次 `db-role-matrix`（要求 0 差异）和一次逻辑备份 + 演练。

## 不在这张单上的

- O8 / O9：CI 加 postgres、redis 两个 sidecar（要下载两个钉摘要的镜像、应用流水线定义）——单独一张单，2.2 开工前。
- O11：物理备份恢复到临时集群的演练——单独一张单。
- 设计 v5 §5.1.1 里写的「挂起的 CronJob」已改为 Argo 之外的 Job（Argo v3.4.3 会把挂起的 CronJob 报成 Suspended），v5 正文随后改。
