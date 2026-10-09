# LANE-W33BR 报告

W-33 返工。代码只在既有分支上，已推送。没有发版、没有 apply、没有写数据库、没有推代码到 main。TD-271 仍是「在做」。

## 改动

- bifrost-platform · `cursor/w33b-platform` · `e2d5137d3400d359d5b00c8917ad3b9fc2d76c3b` · Change-Id `I2796e085116aee1494c869753e4815bd89b7ab86` · 已推送
- bifrost-trade-infra · `cursor/w33b-infra` · 第 1 部分 `918ee55e449953008f2d5bdf28c60a32604a8f2c` · Change-Id `I4c3c8efbf31991b6be395062a528cb76cec42f01` · 已推送
- bifrost-trade-infra · `cursor/w33b-infra` · **PROD overlay 单独提交** `e8e42dd97a498401b8e56fa5ac256a14084a8679` · Change-Id `I5bca43640972f46c0e8f9b939b949f625fdb4f19` · 已推送（分支 HEAD）

第 1 部分含 STG overlay、Tekton 副本、流水线、准入、owner-run、role-matrix、DB 步骤文件、AGENT_FACTS、RATCHETS。第 2 部分只有 `k8s/overlays/platform-prod/config/actuation-policy.yaml`。

## 一、参数注入

流水线脚本里不再出现 `$(params.`。`MODE`、`REPO`、`PATH_IN_REPO`、`COMMIT`、`GITEA_BASE`、`GITEA_ORG`、`REQUIRE_ON_MAIN` 经 step env 传入，脚本只读环境变量，并再查一遍同一套字符集：repo `^[A-Za-z0-9._-]+$`，path `^[A-Za-z0-9._/-]+$` 且不能以 `/` 开头、不能有空段、`.`、`..`，mode 只能是 `plan` 或 `apply`。

防线：`apply-manifest-check_test.sh` 抽出 script 块，断言没有 `$(params.`；Go `TestRepoAndPathRejectShellMetacharacters` 拒绝 `$`、反引号、引号、空格、`;`、换行。

验收：`bash k8s/cicd/tekton/apply-manifest/apply-manifest-check_test.sh` → 通过（含 script 块断言）。

要 Owner 批：无（本段不单独上线；随第四节流水线 apply）。

后续：无。

## 二、检查与 apply 同一份 JSON

渲染之后 `kubectl create --dry-run=client -o json`，再 `jq -s` 收成一个 List，写到 `/tmp/normalized.json`。检查、diff、apply 都用这个文件。检查展开嵌套 List，缺 kind、缺 name、缺 namespace 即失败；对每个活对象读 `argocd.argoproj.io/tracking-id`，NotFound 跳过，有 tracking-id 拒绝。

夹具（同一份规范化）拒绝：flow 文档、JSON 文档、没有 namespace、flow 藏着的 daemon Deployment、List 藏着的 daemon、带 tracking-id 的 ConfigMap。`bifrost-dev` 的普通 ConfigMap 通过，级别 B。

防线：`k8s/cicd/tekton/apply-manifest/apply-manifest-check_test.sh`。RATCHETS 新增「apply 参数与规范化清单（LANE-W33BR）」。

验收：同上一条命令，预期打印 `ok: normalized manifests reject flow, json, missing namespace, hidden daemon, List, and Argo tracking`。

要 Owner 批：无（本段不单独上线）。

后续：无。

## 三、实测（2026-10-09，只读 kubectl）

集群只读。没有 apply、helm、写库。

- cicd PipelineRun 581 个。`taskRunTemplate.podTemplate` 只有 `nodeSelector` 和 `tolerations`（保留）。workspace 字段只有 `volumeClaimTemplate`。
- Task 25 个、Pipeline 17 个：`hostPath` 0，`privileged` 0。所以 applier 写入的 Task/Pipeline 拒绝这两样。
- Tekton resolver（git / bundles / cluster / hub）按道文件记为已开启。PipelineRun 必须有 `pipelineRef.name`，禁止 `resolver`、`params`、`bundle`、`pipelineSpec`。`taskRef` 同样禁止 resolver。
- workspace 只允许 `volumeClaimTemplate` 和 `emptyDir`。`taskRunTemplate.podTemplate` 和 `taskRunSpecs[].podTemplate` 禁止 `volumes` 和 `hostNetwork`。

各命名空间现有 ServiceAccount（不是全部进入白名单）：

| 命名空间 | 现有账号 |
|---|---|
| bifrost-dev | api-ops, daemon-worker, default |
| bifrost-stg | api-ops, daemon-worker, default |
| bifrost-platform-stg | bifrost-platform, default |
| bifrost-prod | api-ops, daemon-worker, default |
| bifrost-platform-prod | bifrost-platform, default |
| research | default |
| plugin-market-data | default |
| plugin-flex-query | default |
| data | backup-retry, bifrost-postgres, default |
| monitoring | default, kube-prometheus-stack-alertmanager, kube-prometheus-stack-grafana, kube-prometheus-stack-kube-state-metrics, kube-prometheus-stack-operator, kube-prometheus-stack-prometheus, kube-prometheus-stack-prometheus-node-exporter, loki, maintainer-reconcile, promtail |
| cicd | argocd-application-controller, argocd-applicationset-controller, argocd-dex-server, argocd-notifications-controller, argocd-redis, argocd-repo-server, argocd-server, default, tekton-deliver, tekton-pipelinerun-ttl, tekton-trigger |

能读 Secret 的账号不进 applier Pod 白名单（argocd-*、grafana、kube-state-metrics、operator、loki、tekton-trigger）。`bifrost-postgres` 也不进。写入策略的 applier Pod 白名单只覆盖仍允许 apply 的路径渲染出来、且不读 Secret 的账号：

- bifrost-dev：default, api-ops, daemon-worker
- monitoring：default, maintainer-reconcile
- cicd：default, tekton-pipelinerun-ttl
- data：default
- research：default
- 其余命名空间只允许空或 `default`

`backup-retry` 仍留在原有 Job 账号列表（CronJob 复制活对象的 ServiceAccount），不进 applier Pod 列表。平台身份 Job/Pod（`bifrost-platform-job-sa`）加上与 applier 相同的 host/privileged/capabilities 限制，monitoring 命名空间除外。

Argo Application（命名空间 cicd，project 仍是 default）：

| 应用 | 路径 | 仓库 |
|---|---|---|
| bifrost-platform-prod | k8s/overlays/platform-prod | bifrost-trade-infra |
| bifrost-platform-stg | k8s/overlays/platform-stg | bifrost-trade-infra |
| bifrost-prod | k8s/overlays/prod | bifrost-trade-infra |
| bifrost-stg | k8s/overlays/stg | bifrost-trade-infra |
| bifrost-research | k8s | bifrost-research |

没有 bifrost-dev Application，所以 `k8s/overlays/dev` 留在白名单。

research 命名空间里没有 tracking-id 的工作负载：Deployment `dagster-daemon`、`dagster-webserver`，Service `dagster-webserver`，ConfigMap `dagster-instance`、`dagster-workspace`。`research-api`、`research-mcp`、`research-pine` 和 CronJob `research-harness` 有 tracking-id。

白名单路径对照：

| 路径 | 去向 |
|---|---|
| k8s/overlays/stg、prod、platform-stg、platform-prod | 拿掉。归 Argo，改用 `gitops_sync_app` |
| k8s/platform-rbac | 拿掉。RBAC/准入，applier 写不了，走 `owner_run_command` |
| bifrost-research `k8s`（除 orchestration） | 拿掉。Argo 应用路径就是 `k8s` |
| bifrost-research `k8s/orchestration` | 留下。`k8s/orchestration/dagster.yaml`，活对象没有 tracking-id |
| infra `k8s/ib-gateway` | 拿掉。这条路径在 infra 里不存在；插件仓 `k8s` 已覆盖 `bifrost-platform-plugin/k8s/ib-gateway` |
| k8s/overlays/dev | 留下。没有对应 Application |
| k8s/monitoring、k8s/cicd/tekton、k8s/cicd/gitea、k8s/data/logical-backup | 留下 |
| 三个插件仓的 `k8s` | 留下 |

Application 规则：`spec.sources` 必须与 oldObject 同在且相等；`source.kustomize`、`source.helm`、`source.plugin`、`source.directory` 的有无和内容都要相等。

防线：`scripts/check_admission_guards.py`（无 `--live`）检查策略文件里有 resolver、hostPath、sources、kustomize/helm/plugin/directory、volumeClaimTemplate、emptyDir，以及策略名 `bifrost-applier-pod-spec`、`bifrost-applier-tekton-spec`。没有跑 `--live`（策略还没 apply）。

验收：`python3 scripts/check_admission_guards.py` → `ok: admission files match the actuation policy`。

要 Owner 批：见「上线顺序」第 2 步 `kubectl apply -k k8s/platform-rbac`。通过之后才能跑 `--live`。

后续：TD-271 维持「在做」，等 `--live` 通过再谈签收。`tekton-trigger` 仍能读 Secret，不在本道白名单里，同类能力以后另看。

## 四、其余

镜像前缀改成完整 registry，只 `HasPrefix`。短名在代码里补 `docker.io/`。`evil.example/x/bifrost-research:1` 不过。探针 `bifrost-stg` 和 `bifrost-prod` 改为 C（收紧；Monitor `/control/*` 在这两个命名空间）。`Summarize` 核对流水线名、`bifrost.io/trigger=platform-api`、`bifrost.io/mode=plan`、参数 `mode=plan`，且没有 resolver/params/bundle，否则 ready 为假。`owner-run.sh` 在校验哈希之后、`read` 之前要求 `[ -t 0 ]`。

防线：`TestImagePrefixMatchesOnlyAtTheStart`、`plan_identity_test.go`、`scripts/owner/owner-run_test.sh`。RATCHETS 新增「owner-run 必须是终端（LANE-W33BR）」。code-health 提示 platform 超长文件 12，低于基线 13，exit 0。没有改 `OVERSIZED_PLATFORM_BASELINE`。

验收：`bash scripts/owner/owner-run_test.sh` → `ok: owner-run refuses wrong status, expired approvals, a hash mismatch, and a piped yes`。

要 Owner 批：无（本段随分支合并；PROD overlay 见下）。

后续：无。

## 五、数据库

Owner 已回「数据库照做」。文件已写，DDL 没有执行，密码不在 git、不在集群。

- `scripts/release/db-steps.d/2026-10-09-w33-agent-reader.md`
- `scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader.sql`
- `scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader-verify.sql`
- `scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader-rollback.sql`
- `k8s/data/role-matrix/expected.yaml`：`agent_reader` 对四个库只有 connect，没有 grants
- `AGENT_FACTS.md` §8c：数据库只读查询用 `agent_reader`，经 `192.168.10.73:30432` 用 psql 连接，不再 `kubectl exec psql`

角色是 LOGIN INHERIT，不是超级用户，`CONNECTION LIMIT 8`，加入 `pg_read_all_data`，三个 ALTER ROLE 设置只读、语句超时、空闲事务超时。四个库只 GRANT CONNECT。回滚只 REVOKE CONNECT 并 NOLOGIN，不 DROP，不收回成员资格。

上一轮停下的 `research.copilot_bridge_event.input_tokens` / `output_tokens` 按道文件是用量计数，不是凭证。本道没有再改授权方式。

防线：`(cd k8s/data/role-matrix && python3 -m unittest test_check_role_matrix.py)` → 11 passed。

验收：文件在分支上；`SELECT rolname FROM pg_roles WHERE rolname = 'agent_reader'` 在执行 DDL 之前应为空。

要 Owner 批：见「上线顺序」第 9–11 步。

后续：无。

## 门禁

测的是 worktree：platform `/tmp/cursor-w33b/w33b-platform`，infra `/tmp/cursor-w33b/w33b-infra`。parity 临时根 `/tmp/cursor-w33b/parity-root`（`bifrost-platform` 指向 platform worktree，`.cursor` / `.claude` / `CLAUDE.md` / `AGENT_FACTS.md` / `scripts` 指向工作区根）。没有改共享 checkout。

| 命令 | 结果 |
|---|---|
| platform `go build ./... && go vet ./... && go test ./...` | 通过 |
| platform `mcp/platform` `npm test` | 20 passed |
| `bash k8s/cicd/tekton/apply-manifest/apply-manifest-check_test.sh` | 通过 |
| `bash scripts/owner/owner-run_test.sh` | 通过 |
| `python3 scripts/check_admission_guards.py`（无 `--live`） | 通过 |
| `python3 scripts/check_platform_rbac.py` / `make check-platform-rbac` | 138 permission answers match |
| `kubectl kustomize` platform-rbac、platform-stg、platform-prod、apply-manifest | 通过 |
| `(cd k8s/data/role-matrix && python3 -m unittest test_check_role_matrix.py)` | 11 passed |
| `PLATFORM_ROOT=/tmp/cursor-w33b/w33b-platform make check-ops-context-parity` | self-test ok；55 decisions，D10=BLOCKED |
| 临时根 `bash agent-config/scripts/check-agent-config-parity.sh` | exit 0。新鲜度警告：platform「从未 fetch」（worktree 的 `.git` 是文件，`FETCH_HEAD` 路径不存在，不算失败）；infra 落后 origin/main 4 个提交（分支未 rebase，按道文件保持，不算失败） |

console 本道没改，没有跑 `npm run lint/test/build`。没有跑 `check_admission_guards.py --live` 或 `check_platform_rbac.py --live`。

## 上线顺序

PROD overlay 是单独提交 `e8e42dd97a498401b8e56fa5ac256a14084a8679`。合进 main 会改 platform-prod 的 configMapGenerator，滚动 PROD 平台 Pod。STG 与其余改动在 `918ee55e449953008f2d5bdf28c60a32604a8f2c`。两笔都还在 `cursor/w33b-infra`，没有合 main。

1. 合并 platform `e2d5137d3400d359d5b00c8917ad3b9fc2d76c3b`，以及 infra 第 1 部分 `918ee55e449953008f2d5bdf28c60a32604a8f2c`。先不要合 PROD overlay 那一笔。
2. Owner 批：`kubectl apply -k k8s/platform-rbac`
3. Owner 批：迁 AppProject（先同步 Application，再 `kubectl apply -f k8s/cicd/appprojects/default-empty.yaml`）
4. `KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_platform_rbac.py --live` 和 `python3 scripts/check_admission_guards.py --live`
5. Owner 批：`kubectl apply -k k8s/cicd/tekton/apply-manifest`
6. STG 发布，Owner 过目。STG 只观测。
7. Owner 批 PROD 之后，再合并 infra PROD overlay `e8e42dd97a498401b8e56fa5ac256a14084a8679`，然后 PROD 发布。
8. PROD 冒烟：bifrost-dev 无害 ConfigMap 的计划与执行；从 `monitoring/maintainer-reconcile` 起一次 Job；起一个 curl 探针；清理；提一张 `owner_run_command` 然后驳回。
9. Owner 批 DB 步骤（未执行）：
   - dry-run：`kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -At -c "SELECT rolname FROM pg_roles WHERE rolname = 'agent_reader'"`
   - commit：`kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader.sql`
   - verify：`kubectl -n data exec -i bifrost-postgres-1 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader-verify.sql`
   - rollback：`kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d postgres -X -v ON_ERROR_STOP=1 -f - < scripts/release/db-steps.d/sql/2026-10-09-w33-agent-reader-rollback.sql`
10. Owner 设密码（密码不进 git、不进集群、不进 Secret），两条命令：
    - `psql -h 192.168.10.73 -p 30432 -U postgres -d postgres -c "ALTER ROLE agent_reader PASSWORD '<由 Owner 填写>'"`
    - `umask 077 && touch ~/.pgpass && chmod 600 ~/.pgpass`，然后只追加一行 `192.168.10.73:30432:*:agent_reader:<同一密码>`
11. 只读应成功、写入应失败：`psql -h 192.168.10.73 -p 30432 -U agent_reader -d bifrost_dev -c 'SELECT 1'`；再试一次写入，预期被拒。

## 要 Owner 批

上面第 2、3、5、6、7、9、10 步。本道没有替 Owner 执行其中任何一条。

## 后续

- TD-271 维持「在做」。
- 不开始下一条道。
- D10 仍是 BLOCKED。
