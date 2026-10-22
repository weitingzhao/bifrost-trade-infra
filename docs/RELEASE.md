# Trade 发布（`scripts/release/`，TD-84）

一次 Trade 发布 = STG（从 `main`）→ 核对 → PROD（钉在那次 STG 克隆的提交上）→ 核对 → core tag → DEV 跟上。
2026-10-03 这些步骤是手工一条条做的；现在由 `scripts/release/` 的脚本做。auto mode 的「Approved Release Runbook」规则
（`agent-config/claude/auto-mode/project.autoMode.json`，Owner 用 `apply-auto-mode.sh` 应用后生效）按这些脚本路径放行 c–f、i 项。
流水线本身见 [DELIVER_STG](DELIVER_STG.md)。

| 脚本 | 做什么 | 写什么 |
|------|--------|--------|
| `release.sh stg\|prod\|dev [--dry-run]` | 一个入口：窗口锁 → 并发检查 → DB 步骤闸门 → before 快照 → 经平台起 run → 等待 → after 核对 → 汇总 | STG 直接 `start_pipeline_run`；PROD 走审批；DEV 改 `:dev` 镜像并重启 |
| `prod-pinned-from-stg.sh <stg-run> [-o f]` | 读出 STG run 的 6 个 clone SHA（不创建 run） | 只写 JSON |
| `release-check.sh <env> before\|after\|probes` / `diff a b` | 快照、diff、`/health` core 身份、探针 | 只读（GET、`kubectl get`） |
| `tag_core_release.sh <sha> [--push]` | 给到达 PROD 的 core 提交打 `v<version>` | 只在 `--push` 时 |
| `release.sh policy status\|sign\|install`、`freeze`、`unfreeze` | 发布策略与冻结（见「发布策略」） | 只经 platform-api 写 |

## 一次完整发布

```bash
cd bifrost-trade-infra
export KUBECONFIG=~/.kube/bifrost-k3s.yaml

scripts/release/release.sh window                       # exit 0 = 没人在发
scripts/release/release.sh stg --dry-run --allow scripts/release/expected.d/<date>-<name>.allow
scripts/release/release.sh stg --allow scripts/release/expected.d/<date>-<name>.allow
#   → 结尾打印 next: release.sh prod --from-stg bifrost-deliver-stg-xxxxx …
scripts/release/release.sh prod --from-stg bifrost-deliver-stg-xxxxx --allow scripts/release/expected.d/<date>-<name>.allow
#   → 结尾打印 tag_core_release.sh 的 dry-run 和下一条命令（--push 不自动执行）
bash scripts/release/tag_core_release.sh --push <core_sha>
scripts/release/release.sh dev                          # make dev-sync-backend-images RESTART=1（后端 + 前端）+ 核对
```

`--dry-run` 跑所有只读检查（窗口、并发、STG run 状态、核对记录、读出 6 个 SHA、DB 步骤），其余平台调用只打印方法和路径；
任何一项不满足时打印 `WOULD REFUSE` 并以 2 退出。令牌不出现在命令行，也不打印。

### release.sh 每一步

1. **窗口** ConfigMap `cicd/bifrost-release-window`（who / what / env / started_at / expires_at）。
   `PUT /api/v1/delivery/release-window`，ttl 5 分钟，持有期间每分钟续期；别人持有就拒绝。
   脚本退出时以持有者身份释放。过期的窗口视为空。
2. **并发**：任何 `bifrost-deliver-*` run 处于 Unknown，或 2 分钟内刚建过，就拒绝（09-27 两个会话相隔 16 秒发同一版的教训）。
   起 run 前会再查一次。
3. **PROD 专有**：`--from-stg <run>` 必须是 `bifrost-deliver-stg` 的 run、Succeeded，且
   `~/.bifrost-release/checks/<run>.json` 写着 `passed: true`（由 `release-check.sh stg after --run <run>` 写，
   `release.sh stg` 会自动做）。然后读出 6 个 clone SHA（40 位，缺一个就拒绝），作为
   `coreRevision` / `workerRevision` / `apiRevision` / `frontendRevision` / `uiRevision` / `infraRevision`。
   请求本身的 `revision` 仍是 `main`（每个仓库都有），6 个 SHA 放在 `params` 里。
4. **一次性 DB 步骤**：`db-steps.d/` 里对本环境 `when: before` 且未完成的步骤 → 打印给 Owner 的命令并**停下**（exit 3）。
   PROD 的 before 步骤会为每一行 `commit:` 提交 `owner_run_command` 审批（reason 是步骤 id），打印审批 id；
   Owner 批准后自己跑 `scripts/owner/owner-run.sh <id>`。脚本永远不对 stg / prod / golden_source 跑 `psql`。
   格式见 `scripts/release/db-steps.d/README.md`。
5. **before 快照** → `${BIFROST_RELEASE_DIR:-/tmp/claude-501/release}/<date>/<env>-<HHMMSS>/`。
   角色矩阵走 `psql`（`PGHOST=192.168.10.73` `PGPORT=30432` `PGUSER=agent_reader`，口令在 `~/.pgpass`）。
6. **起 run**：STG `POST /api/v1/delivery/pipelines/bifrost-deliver-stg/runs`（revision main，直接调用，级别 B）。
   PROD `POST /api/v1/approvals`（action `start_pipeline_run`，name `bifrost-deliver-prod`，级别 C），然后用 viewer 令牌轮询到 executed，读出 `result.run.name`。
   平台若回 400 `call directly` 且带 `auto_approved_by`（签名策略覆盖这次发布），脚本改为直接 `POST /api/v1/delivery/pipelines/bifrost-deliver-prod/runs`，平台在 guard 里再判一次并写审计。
   DEV 是 `RESTART=1 make dev-sync-backend-images`：worker、四个 API 和前端的 `:dev` 一起跟 `:stg`（前端镜像不分环境；2026-10-05 前前端不在内，DEV 前端曾停在 10-02）。
7. **等待**：每 15 秒看一次，直到离开 Unknown，打印每个 TaskRun 的耗时（10-03 实测 STG 约 4 分钟、PROD 约 5 分钟）。
   超过 `--timeout`（默认 3600 秒）以 3 退出——run 仍在跑，不要再起一个。
8. **after 核对**（见下）；PROD 另外核对它克隆的 6 个提交与 STG 完全一致。
9. **汇总**：各步耗时、产物目录、下一条命令；`when: after` 的 DB 步骤也在这里列出。

## release-check.sh

```bash
scripts/release/release-check.sh prod before                       # 只读，随时可跑
scripts/release/release-check.sh prod after --run bifrost-deliver-prod-pinned-xxxxx --allow <file>
scripts/release/release-check.sh dev after --expect-core-sha <sha> --no-diff
scripts/release/release-check.sh diff old.json new.json --allow <file>
```

- **快照**：`GET /api/account/executions?limit=0`（每个 `account_executions_id` 的 contract_key / side / quantity）、
  `/api/account/performance`、每个账户的 `/api/account/portfolio/model-analysis?account_id=`（TD-55：一个进程一个前缀；
  网关还没有 `/api/account` 路由时自动退回别名 `/api/trading` 并在 stderr 说明，B2 删别名时一并删掉退回）。账户从 API 取
  （executions 的 account_id ∪ `/api/monitor/status` 的 portfolio.accounts），repo 里不写账户号。
  快照含账户内容：只放在本机 /tmp，**不进任何 repo**。
- **diff**：每段给出 `identical` / `only added keys` / `changed values`。列表按行的标识字段（最具体的 `*_id`，否则
  period / symbol）对齐，顺序变化不算变化。新增的键和新成交永远放行；改值、删除、长度变化要在 `--allow` 文件里列出
  （每行一个 glob，`*` 任意，`[*]` 表示列表行，例：`perf.summary.win_rate`、`execs.*.q`），否则 exit 1。
  每次发布的预期变化放 `scripts/release/expected.d/<date>-<name>.allow`（示例：`2026-10-03-td-batch.allow`）；
  `expected.d/always.allow` 每次都带上（Owner 2026-10-06：里面只放盘中随实时权益移动的字段——按 capital_base /
  current_equity 算的各组 return_pct、capital_base / start_equity / current_equity、IB 透传的 total_cash /
  buying_power / net_liquidation；未实现盈亏金额不在里面，它们不随实时报价动）。
- **/health**：monitor / trading / market / research 的 `core_sha` 必须等于 `--run` 的 clone-core 提交，
  `core_version` 必须等于该提交 `pyproject.toml` 的版本（从 `BIFROST_CORE_REPO`，默认 `../bifrost-trade-core` 读；
  本地没有这个提交时只要求四个域一致且不是 unknown，并提示没交叉核对）。
- **探针**：`scripts/release/probes.json`（8 个 api 的 /health 返回 JSON、前端首页）加每个 `--probes` 文件。
  请求带 `User-Agent: bifrost-release-check/1`。探测已标 Deprecation 的路由会进 TD-40 的调用者日志，所以这类探针默认 `enabled: false`。

## Platform PROD source check（W-56 guardrail 2）

> 状态：**已应用到集群**（Owner 2026-10-12 21:13，文件取自提交 `79c8088`；应用前在集群里试跑过一正一反）。平台那一半随 `26a10b5` 在正式环境上。
> 2026-10-13 18:32 起线上的 PROD 流水线取自提交 `b9ec378`：源检查与上面相同，只有 `rollout` 改成重启后按摘要核对 Pod（护栏 ⑤ 收口片；同日 18:25 STG 流水线也取自这个提交）。要退回到只有源检查、不核对摘要的那一版，用 `0e3d33b`（与 `79c8088` 逐字节相同），见 `agent-config/work/multi-agent/OWNER-STEPS-digest-s2-s3.md` 的「撤回」。

`bifrost-deliver-platform-prod` 在 mirror-sync 后、clone 前拒绝两种情况：平台提交没有整 SHA 匹配的 Succeeded `bifrost-ci-platform`，或无法证明 STG 克隆了同一整 SHA。STG 只取 `bifrost-deliver-platform` 中创建时间最新的一条（同时间拒绝），它必须成功，且其它每条都必须在它**创建之前**就已结束（completionTime 严格早于它的 creationTimestamp，即不许交叠）；在途、缺失或不能解析的时间、和它交叠过的 run 都拒绝，并在拒绝行里点名。含义：验证过的那次之后，只要又起过一次 STG 发布（哪怕它没碰到 STG 就失败），PROD 就被拒，直到再成功发一次 STG。查询失败或证据畸形也拒绝。

没有 allow-red。覆盖检查的途径是 Owner 应用此前版本的 Pipeline 定义。上线顺序是先把包含 check-source 身份接线的 platform 发到 PROD 并核对，再由 Owner 在没有平台发布在途、没有未结 PROD 发布单时应用 `k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml`；反过来会拒绝每次平台 PROD 发布。回退由 Owner 重新应用此前版本的同一 Pipeline 文件。

**正式环境不再构建，按 STG 核对过的摘要部署**（TD-335，W-31 3.4 ①，Owner 2026-10-21「D3 A」；切法 `agent-config/work/multi-agent/CUT-release-speedup-2026-10-22.md`）。`check-source` 认定的那条 STG run，它的 `rollout` 核对过的 api、console 两个摘要（只在 Pod 真跑着之后才写），就是 PROD 发布的那一对；同一条 run 的 `clone-ui` 提交必须等于这张单子的 uiRevision。`agentrt-schema` 按这对里的 api 摘要查迁移，`promote-images` 把 `:prod` 挪到这一对（给 tag 的读者：Owner 的迁移 Job、registry 的保留集），`gitops-sync`（任务 `bifrost-argocd-pin-sync-platform`）在同一次 patch 里把应用 `bifrost-platform-prod` 的 `spec.source.kustomize.images` 钉到这两个摘要并发出同步、等这一次同步完成，`rollout` 以 `requireSpecDigest=true` 核对：三个 Deployment 的 spec 写着这个摘要，Pod 的 imageID 也是它（workers 用 API 摘要）。读取不是原子快照，不保证读完之后的状态。之后成立的是：Deployment 写的是摘要，Pod 重启拉的还是这一对，`:prod` 被谁改写都不改变 PROD 跑什么（TD-331）。STG 同样按本次构建的摘要钉住（TD-419）。

**回滚不重建**：把上一次成功发布的那一对再钉回去。要么再成功发一次旧提交的 STG、再提升；要么 Owner 直接钉（两个摘要取自那次 PROD run 的 `check-source` 结果或台账）：

```bash
kubectl -n cicd patch application bifrost-platform-prod --type merge -p '{"spec":{"source":{"kustomize":{"images":["registry.cicd.svc.cluster.local:5000/bifrost-platform-api=192.168.10.73:30500/bifrost-platform-api@sha256:<api>","registry.cicd.svc.cluster.local:5000/bifrost-platform-console=192.168.10.73:30500/bifrost-platform-console@sha256:<console>"]}}},"operation":{"initiatedBy":{"username":"owner-rollback"},"sync":{"revision":"HEAD"}}}'
```

钉子只在应用对象里：`kubectl apply` 重新应用 git 里的应用定义不会删它（那个字段不在定义里）；`kubectl replace` 整个对象会删掉它，Deployment 回到写 `:prod`，跑 `:prod` 那一刻指着的东西。那**不一定**是刚才钉着的一对：回滚钉回旧的一对不挪 `:prod`，一次 PROD 发布挪了 `:prod` 却钉失败，也会让两者不一致（复核 513 C1）。钉子丢了，就从最后一次成功 PROD run 的 `check-source` 结果（或台账）取那两个摘要，用上面的命令钉回去，再看三个 Deployment 写着 `@sha256:<摘要>`、Pod 的 imageID 也是它；不靠 `:prod`。

钉住路径 `scripts/release/platform-prod-pinned-from-stg.sh <stg-run> -o <file>` 读取线上 PROD Pipeline：有 check-source 就设置该任务使用 tekton-deliver，保留其它 override；没有就不添加，读不到或 tasks 不是列表就拒绝生成。它只生成 JSON，创建发布仍由 Owner 批准。指定旧 STG run 不会绕过最新 STG 判定。

应用前，`python3 scripts/release/platform_prod_gate_trial.py <revision> [--ui-revision main] > <file>` 只打印一条 trial PipelineRun，内联任务与正式 check-source 完全相同、身份是 tekton-deliver；Owner 可对当前 STG 提交与没有 CI 的提交分别试跑。它不构建、不克隆、不发布，生成器从不调用 kubectl。ui commit 会解析为固定 SHA 并交给后续 clone，但不与 STG 比较。

### Owner 应用这道检查时（一次）

次序：含 check-source 身份接线的 platform 已在 PROD → 试跑一正一反 → 应用。三条命令都在 infra 主线的检出目录里、Owner 自己的终端跑；没有平台发布在途、没有未结的 PROD 发布单时再做。

摘要核对第 3 片另须先确认第 1 片的两个 kaniko Task 已应用（声明 digest result 并写 --digest-file），再应用 PROD Role 的只读权限 → 支持 STG/PROD 的核对 Task → 对 PROD 只核对试跑一正一反 → PROD Pipeline。试跑用 `python3 scripts/release/platform_digest_verify_trial.py <api-digest> <console-digest> --namespace bifrost-platform-prod`；默认仍为 STG，只接受两个完整名字，不重启、不记录 Application。若先应用 PROD Pipeline 而 kaniko Task 仍是旧版，构建没有 digest 结果，下游结果引用不能满足，run 会失败，不能算发布成功；构建可能已推镜像。新 Task 或 Role 未就绪同样不能应用流水线。撤回第 3 片：先把 PROD Pipeline 恢复成 `0e3d33b` 的文件（与 `79c8088` 逐字节相同）：`git show 0e3d33b:k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml | kubectl apply -f -`。不是下面第 3 条的 `27e4467`——那一条连 check-source 一起撤掉。之后再处理共享核对 Task 和新增权限；STG 或 PROD 的流水线仍引用核对 Task 时保留它和两处只读权限。

```bash
# 1. 试跑（不构建、不发布；只为解析提交，把两个仓库各浅拉一次到临时目录）。在将要应用的那个提交上生成；给镜像上已有的整 SHA。
python3 scripts/release/platform_prod_gate_trial.py <STG 当前的平台提交> > /tmp/trial-pass.yaml
python3 scripts/release/platform_prod_gate_trial.py <一个没有 CI 的提交> > /tmp/trial-refuse.yaml
# 这两个文件各创建一次。创建命令在脚本自带的说明里（Owner 自己的身份才建得了）：
#   python3 scripts/release/platform_prod_gate_trial.py --help
# 2. 应用
kubectl apply --dry-run=server -f k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml \
  && kubectl apply -f k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml
# 3. 回退（要越过这道检查也是这一条：没有 allow-red）
git show 27e4467:k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml | kubectl apply -f -
```

试跑应看到（`kubectl -n cicd get pipelinerun -l bifrost.io/purpose=check-source-trial`，日志在它唯一的 TaskRun 里）：第一条 Succeeded，结果 `commit` 是那个提交；第二条 Failed，日志一行 `REFUSED: CI cannot be shown for <sha>: no exact-SHA Succeeded CI`。第一条如果起不来（镜像里没有 python3 或 git）或报 `identity cannot read…`，不要应用。

拒绝行各自怎么办：

| 拒绝行里有 | 意思 | 怎么办 |
|---|---|---|
| `identity cannot read PipelineRuns/TaskRuns in cicd` | 检查没跑在 tekton-deliver 下 | platform 那一半还没到 PROD，或这条 run 是手建的、没给 check-source 指身份 |
| `no exact-SHA Succeeded CI` | 这个提交没有成功的 `bifrost-ci-platform` | 等 CI；CI 没起就先同步镜像再起一次 |
| `no STG delivery` | 集群里一条 `bifrost-deliver-platform` 的 run 都没有（run 只留 7 天） | 发一次 STG |
| `STG clone commit differs or is ambiguous` | STG 最新一次成功发布的不是这个提交 | 先把这个提交发到 STG |
| `STG run X is False`、`is Unknown`、`is running/no Succeeded condition` | 最新一次 STG 发布失败或还在跑 | 等它结束；失败就重发 STG |
| `STG run X had not finished before the newest run started` | 两次 STG 发布交叠过，说不清 STG 上是哪一次的 | 再发一次 STG |
| `STG run X has missing or unparsable completionTime`（或 `creationTimestamp`） | 有一条 STG run 还没结束，或它的时间字段坏了 | 等它结束；一直不结束或字段坏了，就删掉那条 run（`delete_pipeline_run`） |
| `ambiguous latest STG delivery` | 两条 STG run 的创建时间在同一秒 | 再发一次 STG |
| `missing or ambiguous clone-platform TaskRun`、`clone TaskRun identity/status mismatch` | 那次 STG 发布的拉代码记录不在了，或和 run 对不上 | 再发一次 STG |
| `missing or ambiguous clone-ui TaskRun`、`UI clone TaskRun identity/status mismatch`、`STG UI clone commit differs from uiRevision` | PROD 部署的是那次 STG 构建出的 console（TD-335），它不是这张单子写的 UI 提交，或它的拉代码记录不在了 | 用那次 STG 发布的 UI 提交建单（`release.sh prod` 自己会取），或把这个 UI 提交先发到 STG |
| `missing or ambiguous rollout TaskRun`、`rollout TaskRun identity/status mismatch`、`missing or ambiguous api-digest result`（或 `console-digest`）、`STG rollout digests are malformed` | 那次 STG 发布没有核对过的一对摘要可提升（TD-335：PROD 只部署 STG 核对过的摘要） | 再发一次 STG |
| `empty or ambiguous mirror revision` | 镜像上没有这个分支或标签，或者同名的分支和标签都在 | 同步镜像；改给 40 位整 SHA |
| `invalid revision`、`mirror returned another SHA`、`invalid mirror SHA`、`invalid resolved SHA` | 给的修订号不合法，或镜像回的不是它 | 只给分支名、标签名或 40 位整 SHA；再出现就停下查镜像 |
| `query failed: <原因>`、`CalledProcessError: <原因>`（原因是几句固定的话之一，例如 `cannot reach the API server`、`mirror authentication failed`、`timed out`；认不出的写 `unrecognised error output`。工具自己的报错原文不进日志，因为这一步拿着镜像的凭证）、`malformed or incomplete PipelineRun list`、`PipelineRun does not match selector …`、`malformed run`、`malformed spec`、`malformed params`、`ambiguous params`、`ambiguous status`、`duplicate JSON key`、`timezone missing` | 读集群失败，或读回来的记录形状不对。关着失败 | 重试一次；仍然出现就不要绕过，把这一行原样交给统筹线程 |
| 行尾是一个异常类名（`CalledProcessError`、`TimeoutExpired`、`KeyError` 等） | git 或 kubectl 子进程失败，或超过 20 秒 | 同上 |

钉住路径生成的 JSON 在应用或回退这条 Pipeline 之后要重新生成（它在生成那一刻读线上的定义）。

**这道检查生效之后怎么把平台退回旧提交**：直接再发旧提交会被拒，因为 STG 上已经不是它了。两条路：① Owner 先把 Pipeline 恢复成不含检查的定义（上面第 3 条命令），再发旧提交；退回到不含 check-source 身份接线的平台（`2726c47` 之前）之后，检查要一直保持撤回。② 先把旧提交成功发到 STG、让它成为最新的一次，再发 PROD；只适用于含身份接线的平台提交。Owner 动手时用的清单见 `agent-config/work/multi-agent/OWNER-STEPS-2026-10-13.md`。

## Platform STG / PROD running-image verification（guardrail 5，slices 2–3）

STG 的 `rollout` 引用 `bifrost-rollout-verify-platform`，先重启并等待三个 Deployment，再核对 API/worker 与 console 的 `imageID` 是否分别等于本次两个构建结果。三个 Deployment 的副本状态必须全齐；按它们自己的 matchLabels 选 Pod，忽略终止中以及 status.phase 为 Succeeded 或 Failed 的 Pod，剩余数量必须恰好等于期望副本数。每个 Pod 经控制器 UID 链归属当前 Deployment 和当前 revision，并且只有预期的一个容器、正在 Running、running 且 ready。不支持 init/ephemeral 容器以及非空 matchExpressions；不支持的形状拒绝，不放宽检查。

参数没有默认值，STG 和 PROD 都明确给 `requireSpecDigest=false`、`recordApplication=none`。核对最多 3 次，每次重读整套对象，间隔 3 秒，总预算 55 秒，每个 kubectl 子进程最多 5 秒；任意一次整套通过才写 `api-digest`、`console-digest`、`verified-at` 三个结果（摘要没有换行）。这证明读取时的运行状态，顺序读取不是原子快照，也不固定以后移动标签拉到的镜像。

应用前由统筹方只读量好第 1 片三个摘要相等、STG/PROD 的 imageID、容器名和 UID/revision 归属链的真实形状。Owner 的次序：STG Role → 新 Task → 两条只核对的试跑（正例成功且结果相符、反例拒绝）→ STG Pipeline。`scripts/release/platform_digest_verify_trial.py <api-digest> <console-digest>` 只打印试跑清单，唯一内联步骤直接取新 Task 的核对脚本，身份 `tekton-deliver`、amd64；创建命令只在生成器 `--help` 中。自动应用脚本仍会整批应用，首次应用时应按上述分步次序执行，试跑未通过不应用 Pipeline。撤回先恢复 STG Pipeline，再撤新 Task（也可留着；PROD Pipeline 还引着它时不能撤），最后撤 STG Role 的新增只读权限。共享旧 Task 保持不变。正式环境第 3 片的应用次序见上一节「Owner 应用这道检查时」里以「摘要核对第 3 片」开头的那一段。

拒绝日志前缀 `REFUSED: platform digest verification:` 后面只使用下列固定句；工具输出和对象字段不进入日志。把拒绝句交给统筹方查证，失败不算发布成功。

| 拒绝句 | 意思及处理 |
|---|---|
| `invalid expected digest` | 两个期望摘要必须为 sha256 加 64 位小写十六进制，且无换行；查构建结果。 |
| `only STG or PROD verification without recording is supported` | 只允许 bifrost-platform-stg、bifrost-platform-prod 和 none；查任务接线。 |
| `invalid spec digest mode` | 核对模式必须明确为 true 或 false；STG 和 PROD 接 false。 |
| `verification deadline exceeded` | 总预算耗尽；查滚动和集群读取耗时，不放宽判定。 |
| `cluster read timed out` | kubectl 子进程超过预算；查 API 可达性。 |
| `identity cannot read Deployments/Pods/ReplicaSets` | 身份或目标环境 Role 不符；查 tekton-deliver 接线和新增权限。 |
| `cluster read failed` | 读取失败（含对象不存在）；查 API 与对象，工具原文不进日志。 |
| `malformed cluster JSON` | JSON 无法解析；查 API 返回值。 |
| `duplicate JSON key` | JSON 有重复键；查返回证据。 |
| `malformed cluster object` | 返回的不是对象；查返回形状。 |
| `invalid controller reference` | 属主引用不是列表；查实际归属链。 |
| `missing or ambiguous controller reference` | 真控制器必须恰好一条；查 Pod 或 ReplicaSet。 |
| `wrong controller kind or API version` | 必须为 apps/v1 的 ReplicaSet 或 Deployment；查实际控制器。 |
| `invalid controller identity` | 控制器名字或 UID 缺失/无效；查对象。 |
| `invalid ReplicaSet name` | ReplicaSet 名字必须符合 DNS 子域名格式且不超过 253 字符；拒绝后不查询该名字。 |
| `cluster object identity mismatch` | 返回对象名字、命名空间或 UID 不符；查对象。 |
| `Deployment has no positive replica count` | 副本数必须为正整数；查 Deployment。 |
| `Deployment generation is not observed` | 最新 generation 尚未被观察；等滚动完成。 |
| `Deployment replicas are not fully rolled out` | 四个副本状态不齐；查滚动结果。 |
| `unsupported Deployment selector` | matchLabels 缺失/非法或带 matchExpressions；先核对真实形状再修设计。 |
| `malformed or incomplete Pod list` | Pod 列表形状不符或分页未完整；查返回证据。 |
| `active Pod count differs from replicas` | 无 Pod、只有终止中或终态 Pod、数量不足或多出 Pod；查滚动时序。 |
| `Pod list identity or selector mismatch` | Pod UID 重复或标签与选择器不符；查返回证据。 |
| `Pod ReplicaSet UID mismatch` | Pod 引用的 ReplicaSet 已重建或不符；查 UID 链。 |
| `ReplicaSet Deployment identity mismatch` | ReplicaSet 属于别的 Deployment 或同名旧 UID；查 UID 链。 |
| `ReplicaSet is not the current revision` | 两边 revision 不同或无效；等旧 Pod 退出再核对。 |
| `Pod is not Running` | Pod Pending 或退出；查容器启动。 |
| `unexpected Pod containers` | 容器集合不符合预期；先核对实际容器名。 |
| `init or ephemeral containers are not supported` | 存在额外容器或其状态；查实际形状。 |
| `missing or ambiguous container status` | 状态数量或名字不符；查 Pod。 |
| `container is not running and ready` | 等待、退出、未 ready 或状态矛盾；查启动/探针。 |
| `container imageID digest differs or is invalid` | 摘要缺失、格式不符或与构建结果不同；查当前镜像，workers 应跑 API 摘要。 |
| `Deployment spec image is not the expected digest` | 显式打开 spec 摘要核对时声明镜像不符；STG 和 PROD 不打开此项。 |
| `missing or malformed verification evidence` | 缺字段、错误类型或其它内部异常；查证据形状，未写结果。 |
| `REFUSED: invalid STG or PROD rollout parameters` | 重启前拒绝错误环境、摘要、记录或模式参数；查流水线接线。 |
| `REFUSED: platform rollout failed or timed out` | 重启/等待失败；查滚动状态，工具原文不进日志。 |

## 发布窗口：推 main 或起 deliver 之前先看

```bash
scripts/release/push-main.sh <checkout> <sha>
```

`push-main.sh`（TD-341）先跑 `release.sh window`；对有自己 CI 的仓库（platform、trade-frontend、trade-core / api / worker、research），要求 `<sha>` 有一次成功的 ci-* 运行（W-31 3.4 ②：CI 在每次推分支时就跑，所以先把分支推到 Gitea，绿了再合；没跑完的最多等 `PUSH_MAIN_CI_WAIT` 秒，失败或一直没有就拒推；`--allow-red <理由>` 照推并打印理由，和 `release.sh --allow-red` 同义；只改 Markdown 的不查）；再在 `<sha>` 的干净 worktree 上跑和 CI 同一份 code-health 扫描（只对 CI 有 code-health 任务的仓库：platform、trade-frontend、research、trade-api / core / worker），过了才 `git push origin <sha>:refs/heads/main`，只接受快进，推之前再查一次窗口。直接 `git push` 到 main 由 `preflight.js` 拦截。

- **血缘（TD-400）**：扫描之前先查 `origin/main..<sha>` 里的每个提交，必须同时带 `Change-Id` 和 `Claude-Session` 两个尾注。缺的会逐个点名，然后拒推。husky 仓库新开的 worktree 不跑钩子，在那里提交要自己补 `--trailer`。cherry-pick 和 rebase 保留原尾注。不在 Claude 会话里做的提交（比如 Owner 自己的），用 `push-main.sh --no-lineage <理由> <checkout> <sha>` 推，理由和这些提交会打在输出里。
- **快测试（TD-413）**：在扫描用的那个干净 worktree 里接着跑这个仓库的快测试，失败就拒推。worktree 旁边会链接工作区里的其他仓库，因为测试会读它们。
  - infra：`python3 -m pytest -q scripts/release scripts/agentrt scripts/agent-host`，实测约 5 分钟。
  - platform：`go vet ./...`，再加 `origin/main..<sha>` 改过的包的 `go test`。没设 `AGENTRT_TEST_PG` 时，数据库测试会跳过。
  - 其他仓库暂时不跑。
  - 只改了 Markdown：`origin/main..<sha>` 里改到的文件全是 `.md`（改名按一删一增算，`.py` 改名成 `.md` 不算只改文档）。这时输出「only documentation changed: …」，不用写理由。整套不跑，只跑管文档内容的防线：infra 的考题要点扫描 `scripts/agentrt/test_no_exam_keys.py`，约 7 秒；platform 什么都不跑。只要有一个非 `.md` 文件，就照常全跑。
  - 剩下的漏洞：只改文档时不会核对 `docs/RELEASE.md` 里拒绝原因那张表（在 `test_platform_prod_gate.py` 里），要等下一次完整推送才会发现。
  - 退出码按原样读，不经过管道。真跑不了时用 `--skip-tests <理由>`，理由会打在输出里。
- **共用检出跟上 main（TD-408）**：推成功后，或者 main 已经是这个提交时，工作区里这个仓库的共用检出（`<工作区>/<repo>`；各会话的 MCP 和本机构建都从它跑）同时满足下面几条，就快进到刚推的提交：在 main 上、没有已跟踪的改动、origin 相同、不是推送来源本身、能快进。有一条不满足就不动它，在输出里说明原因（`push-main: shared checkout …: …`）。这一步不会让推送失败。工作区是 infra 主 worktree 的上一级目录，可以用 `PUSH_MAIN_SHARED_ROOT` 指定别处。

`release.sh window` 没有窗口时 exit 0，有窗口时打印持有者并 exit 1。任何会话在**推 Trade 任一仓库的 main**
或**起任何 `bifrost-deliver-*` run** 之前都先跑它：窗口开着就等它关，或者问 Owner。窗口 ttl 5 分钟，
持有期间每分钟续期；进程退出或到期后自然放开。`release.sh window --clear` 提交
`release_window_release`（force）审批，由 Owner 批准后才清掉别人的窗口。

窗口在 `release.sh` 运行期间存在（`hold` 一直占到进程退出，并续期）。Research 与插件用同一个
ConfigMap `cicd/bifrost-release-window`，`what` 写仓库名。对应流水线的第一个 task
和 platform-api 的 `start_pipeline_run` 在窗口被别人持有时拒绝。`stg` / `prod` 在起 run 之前
`POST /api/v1/delivery/mirrors/sync`，并要求所发 SHA 有 Succeeded 的 `ci-*`，`--allow-red <原因>` 才放行。
STG 与 PROD 之间（等 Owner 看 STG）没有锁——这段时间推 main 不影响 PROD，
因为 PROD 钉的是 STG 克隆的提交，不是 `main`。

## 发布策略（W-42，卡 2 = B）

**platform-api 是唯一的裁判**；`release.sh` 只签名、只调平台，自己不判。没有生效的策略时一切照旧：
PROD / platform-prod / research 的发布（级别 C）等 Owner 批，STG 与构建（级别 B）直接跑。

| 对象 | 位置 | 谁写 |
|------|------|------|
| 策略 | ConfigMap `cicd/bifrost-release-policy`（`policy.yaml` 规范 JSON + `policy.sig`） | `PUT /api/v1/release-policy`（`release.sh policy sign`） |
| 冻结 | ConfigMap `cicd/bifrost-release-freeze` | `POST …/freeze`（操作员；没有信任锚则拒绝）、`POST …/unfreeze`（Owner 签名） |
| 信任根 | platform 编译进去的 `releasepolicy.OwnerKeyFingerprint`（`api/internal/releasepolicy/anchor.go`） | 改它是信任根变更，Owner 手动发 PROD |
| 模板与路径表 | `agent-config/release-policy/template.json`、`paths.json` | 改它们在下一次签名时生效 |

- **签名**：`release.sh policy sign [--days N]` 用 `~/.ssh/bifrost_release_owner`（`BIFROST_RELEASE_KEY` 可改）
  `ssh-keygen -Y sign -n bifrost-release-policy`，再 PUT 给平台；平台按编译进去的指纹验签，拒绝过期的、
  早于已装策略的。签好的文件留在 `~/.bifrost-release/policy/<policy_id>/`，平台不在线时用 `policy install <dir>` 补装。默认 90 天。
- **判定**（全部满足才不等人）：签名有效且未过期；未冻结；pipeline 在 `allow`；申请方持有发布窗口；
  该环境没有未完成的 before DB 步骤（读 Gitea main 上 `scripts/release/db-steps.d/` 的 `done:` 行，本机 `db-done` 不算）；
  revision 是 main 头或 tag——PROD 与 platform-prod 改为「钉住的提交 = 最新一条 STG / platform STG 发布记录发的提交」；
  每个 SHA 有 Succeeded 的 `ci-*`；diff（上次发布记录 → 这次）不碰 D10 路径、不碰信任根，碰 DDL 时必须只增不改
  （`additive_ddl`：只加行；无 DROP / RENAME / ALTER COLUMN / 不带 CONCURRENTLY 的 CREATE INDEX / 无默认值的 NOT NULL 列等）。
  **2026-10-10 起模板的 `allow` 不含 `bifrost-deliver-prod` 和 `bifrost-deliver-platform-prod`**（Owner 定，Codex 审查 R02）：W-56 的六条门槛（逐仓固定 SHA、按镜像摘要部署、回滚不重建等）验收之前，PROD 发布仍由 Owner 批。
  **2026-10-10 起模板里 `additive_ddl` 是 `false`**：现有分类器按行匹配禁止词、默认放行，换行或没列进清单的语句会被放过（Codex 审查 R01，已复现）。W-55 把它重做成允许清单并经独立复核之前，命中 DDL 路径的发版一律等 Owner。
- **级别 B**（STG、构建）：设了冻结就 409 拒绝；有生效策略时照常起 run，并写审计 `release_policy.check`（covered / not covered + 条款），
  这是 PROD 依赖这些事实之前的影子演练。
- **级别 C**：覆盖 → `POST /api/v1/approvals` 回 400 `call directly` + `auto_approved_by`，直接调用时 guard 写审计
  `release_policy.auto_approve`（policy_id、请求方、SHA、条款）；不覆盖 → 照旧建审批单推给 Owner，理由写在单里。
- **冻结**：`release.sh freeze --reason <原因>` 立即拒绝所有新发布（平台的级别 B / C，以及 research / 插件流水线的
  release-window task 的 `freeze` 步骤）。`release.sh unfreeze` 由 Owner 对 `unfreeze frozen_at=<那次冻结> …` 签名，
  平台只接受针对当前这次冻结的签名。ConfigMap 不存在不算冻结（向后兼容），但级别 C 的自动放行要求它存在且为 false。
  没有编译进去的信任锚时，平台和 `release.sh freeze` 都拒绝设置冻结，见「The release owner key」。已经冻上、又签不了字时，见「Lifting a freeze without a signature (break-glass)」。
- **到期提醒**：PROD platform-workers 每小时查一次，到期前 14 天、3 天、1 天推送 Owner，过期后有发布在等再推一次
  （STG 设 `PLATFORM_RELEASE_POLICY_REMINDERS=off`）。存活由 maintainer `platform/prod/release-policy-expiry` 记。
- **首次落地**（一次）：apply `k8s/cicd/release-policy/configmaps.yaml`、`k8s/cicd/tekton/rbac-release-window.yaml`、
  `k8s/cicd/tekton/task-release-window.yaml`（都不在 Argo 下，走平台 `apply_manifest` 审批；先 ConfigMap 和 RBAC，再 task）。

## The release owner key

冻结和级别 C 的自动放行用的是同一把 Owner 钥匙。平台不读磁盘上的私钥，只验编译进 `releasepolicy.OwnerKeyFingerprint` 的指纹（`bifrost-platform/api/internal/releasepolicy/anchor.go`）。指纹为空时，策略签名和解冻签名都不被接受，`policy status` 的 anchor 一行是 `none compiled in: nothing auto-approves, and freeze is refused (nobody could lift it)`，自动放行不会发生。这时 `freeze` 也不提供：平台和 `release.sh freeze` 都拒绝，因为设下去没有签名解得开。

钥匙路径和 `policy sign` 的签法见上面「签名」。钥匙文件还不在时，`policy sign` 打印的生成命令是：

```bash
ssh-keygen -t ed25519 -C bifrost-release-owner -f ~/.ssh/bifrost_release_owner
```

`BIFROST_RELEASE_KEY` 改的是同一条路径。策略签名的命名空间是 `bifrost-release-policy`，解冻签名的命名空间是 `bifrost-release-unfreeze`，两处都用这一把私钥。

指纹是 `ssh-keygen -lf ~/.ssh/bifrost_release_owner.pub` 里的 `SHA256:…` 字段，写进 `OwnerKeyFingerprint`。同一把公钥记在 `agent-config/release-policy/allowed_signers`。两处必须是同一把钥匙。改指纹或改这个文件都是信任根变更（见上表「信任根」；`paths.json` 的 `no_trust_anchor_change` 盖住 `api/internal/releasepolicy/**` 和 `agent-config/release-policy/**`），由 Owner 审，不会自动放行。指纹在二进制里，要一次平台发版之后，正在跑的 platform-api 才带上它。发版之前 `freeze` 仍被拒绝。

## Lifting a freeze without a signature (break-glass)

只有 Owner，并且用 cluster-admin 的 kubeconfig。用在冻结已经写上、签名又解不开的时候：没有钥匙，或者正在跑的 platform-api 里没有信任锚。日常解开用 `release.sh unfreeze`。

按这个顺序改三个对象。kubeconfig 写占位符，不写某一台机器上的路径。不要 `kubectl apply -f k8s/cicd/release-policy/configmaps.yaml`：那个文件同时带着已签名的策略（见下面 Freeze check 一节）。

平台另存着见过的最新一次 `frozen_at`。冻结对象回到从未冻结之后，这份记忆还在的话，`policy status` 仍报冻结（`a freeze from … was seen and its record is gone`）。所以先改冻结对象，再把 PROD 和 STG 两边的记忆写成 `{"frozen_at":""}`。Tekton 的 freeze-check 只读冻结对象；平台的门读两边。

```bash
# 1. cicd/bifrost-release-freeze 回到从未冻结的形状：只有 frozen: "false"
kubectl --kubeconfig <admin-kubeconfig> -n cicd patch configmap bifrost-release-freeze --type=json \
  -p '[{"op":"replace","path":"/data","value":{"frozen":"false"}}]'

# 2. PROD 平台记住的最近一次冻结（键 state.json）
kubectl --kubeconfig <admin-kubeconfig> -n bifrost-platform-prod patch configmap platform-state-release-policy-freeze --type=json \
  -p '[{"op":"replace","path":"/data/state.json","value":"{\"frozen_at\":\"\"}"}]'

# 3. STG 平台的同一份记忆（两个命名空间各一份）
kubectl --kubeconfig <admin-kubeconfig> -n bifrost-platform-stg patch configmap platform-state-release-policy-freeze --type=json \
  -p '[{"op":"replace","path":"/data/state.json","value":"{\"frozen_at\":\"\"}"}]'
```

然后 `release.sh policy status` 应显示未冻结，再跑一次 STG 发布，确认发布走得通（步骤见「一次完整发布」）。

这一节在 2026-10-11 用过一次。再需要它，是缺陷，要记下来。

## Freeze check (W-56 step 1, slice B — not applied yet)

新 Task `bifrost-release-freeze-check` 读一次 ConfigMap `cicd/bifrost-release-freeze` 的 `data`，故障即拒。
只有读成功、`data` 恰好是下面三种之一、并且 `frozen` 是字符串 `"false"` 才放行。每种形状的键是闭的：多一个、少一个、空字符串，或 `frozen_at` 不是 RFC 3339，都是畸形。

| 形状 | 键 | 结果 |
| --- | --- | --- |
| 从未冻结 | 只有 `frozen="false"` | 放行：`未冻结：<checked_at>` |
| 冻结 | `frozen="true"`、`frozen_at`（RFC 3339）、`who`、`reason` | `拒绝：发布已冻结（<reason>，<frozen_at>）；解冻要 Owner 签名` |
| Owner 解冻之后 | `frozen="false"`、`frozen_at`（那次冻结的）、`unfreeze.txt`、`unfreeze.sig` | 放行，第二行 `note: un-freeze signature not verified (slice C)` |

序号和对解冻签名的核验一起在 C 片到来，随平台改写入。这一片按形状接受解冻对象，不验签名。

今天集群里的对象就是「从未冻结」：`k8s/cicd/release-policy/configmaps.yaml` 的 `data` 只有 `frozen: "false"`。Owner 在应用这个 Task 之前不用创建或改它。不要 `kubectl apply -f k8s/cicd/release-policy/configmaps.yaml`：那个文件同时带着策略 ConfigMap，盖上去会动已签名的策略；对象当时若是冻结的，还会被写成没冻结。

读不到或形状不对（404、其它 API 错误、超时、解析不了、缺字段、多余字段、`frozen` 不是 `"true"` / `"false"`、布尔值而不是字符串、`frozen_at` 不是 RFC 3339）：`拒绝：读不到冻结状态（<what>），按冻结处理`。

上线不靠流水线豁免。对象缺失或畸形时检查会拒绝，坏掉的对象不能靠 `bifrost-apply-manifest` 修，因为这条流水线自己也被同一道检查挡住。谁做哪一步：

1. 不动冻结对象。今天的 `frozen: "false"` 已经能过检查。
2. Owner 自己 `kubectl apply -f k8s/cicd/tekton/task-release-freeze-check.yaml`。这一个文件里是 Task 和装着程序的 ConfigMap。不走 `bifrost-apply-manifest`。
3. 然后十一条会推镜像或滚动的 Pipeline，按文件逐个 apply。
4. 最后才是 `bifrost-apply-manifest`。`freeze-check` 是根，`run`（里面的 `kubectl apply`）在它之后。

从第 2 步动手到第 4 步做完，不要开始任何发布。

中途停下来并不安全：

- 只做完第 2 步：新 Task 在，还没有流水线跑它。集群里现有的流水线仍不经过这道检查。apply 也还没被挡住。
- 十一条里只换了一部分：已经换上的被检查支配；还没换的那条仍不跑这道检查。apply 留到最后，所以这时 apply 仍不检查。
- 十一条都换了、apply 还没有：这十一条被挡住。旧的 apply 流水线仍能写入。
- 第 4 步做完：apply 的 `run` 也在检查之后。这是这一片接上的流水线第一次全部被挡住。

续装从还没 apply 的下一个文件接着做，顺序不变。不要先换 apply，也不要靠发起一次发布把安装做完。

### 恢复（只有 Owner）

下面都不能走 apply 流水线：它被同一个检查挡着。

**冻结对象缺失或畸形**：新检查读不到合法的对象就拒绝全部流水线，这是期望的状态，不用抢着解除。恢复只用两条现成的、有测试的命令，不手写对象，不用 `kubectl` 编辑或重建。这两步要信任锚已经编进正在跑的 platform-api；没有锚时 `freeze` 被拒绝，见「The release owner key」。对象已经是冻结、签名又解不开时，走「Lifting a freeze without a signature (break-glass)」，不要再冻一次：

1. `scripts/release/release.sh freeze --reason "<写明是恢复时建的冻结>"`。平台的写入在对象缺失时创建它、在对象存在时整体替换 `data`（`bifrost-platform/api/internal/delivery/release_policy_facts.go` 的 `WriteConfigMap`；`Freeze` 对原有内容没有前置条件），所以不管原来是缺失还是畸形，写完都是一个合法的「已冻结」对象。用 `release.sh policy status` 确认显示已冻结。
2. Owner 运行 `scripts/release/release.sh unfreeze`，对这一次冻结签名解冻。写完是合法的「已解冻」对象，流水线恢复放行。

**不去推断它原来是不是冻结的**（复核 45）：旧的 `policy status` 输出没有保证被留着，平台的审计只保留最近 500 条，也不一定对得上最新那次冻结。上面两步对「原来冻结」和「原来没冻结」是同一个做法：先冻结，再由 Owner 签名解冻；原来确实该冻结的，就停在第 1 步不解冻。多冻一次的代价是一次签名。

**平台不可用时**：不恢复，等平台回来再做上面两步。这段时间对象缺失或畸形，新检查把所有流水线拒掉。平台不可用而又必须发布，是 Owner 的带外应急，这一片不提供工具，也不给手写对象的示例（复核 46 指出过那样的示例会出的错）；带签名的冻结对象和它的恢复工具在 C 片一起做、一起测。

**还没换上新检查的流水线**（安装中断在半路，见上一节）：旧的 release-window 任务把缺失的对象读成没冻结。所以对象缺失期间，不要启动任何还没换上新检查的流水线，直到第 1 步写回对象。

冻结检查的 Task 或程序 ConfigMap 坏了：Owner 自己再 apply 这两个对象所在的那一个文件，不走 apply 流水线：

```bash
kubectl apply -f k8s/cicd/tekton/task-release-freeze-check.yaml
```

事后核对。在 `bifrost-trade-infra` 仓库根目录把决定程序对着活对象跑，退出码 0 才是放行：

```bash
kubectl -n cicd get configmap bifrost-release-freeze -o json \
  | python3 -c 'import json,sys; sys.path.insert(0,"scripts/release"); import freeze_decision as fd; doc=json.load(sys.stdin); code,text=fd.render(fd.data_from_envelope(doc)); sys.stdout.write(text); raise SystemExit(code)'
```

再干跑一条流水线：平台 `plan_manifest`（`bifrost-apply-manifest`，`mode=plan`）。它会跑 `freeze-check`，然后 `kubectl diff`，不会 `kubectl apply`。恢复出来的状态若是冻结，这一跑会在检查处被拒，这是预期。

Role `tekton-release-window` 允许三个身份对 `bifrost-release-freeze` 做 `get`：`default`、`tekton-deliver`，和 apply 流水线的 `bifrost-applier`（`k8s/cicd/tekton/rbac-release-window.yaml`）。第三个是 2026-10-11 安装当天补的：这一片原先写「不新写 RBAC」，没有核对 apply 流水线跑在哪个身份下；装完之后它的第一次干跑在检查处得到 403，按故障即拒被拒，`plan_manifest` 和 `apply_manifest` 因此全部不可用，直到 Owner 应用这条绑定。应用前要核对的身份是**每一条**接上检查的流水线各自的运行身份，不只是构建类的。

冻结期间 apply 流水线也不跑，包括它的 plan 模式（plan 和 apply 是同一个任务）。解冻不走这条流水线：`release.sh unfreeze` 把 Owner 签名交给平台 `POST /api/v1/release-policy/unfreeze`。这一片不给任何流水线豁免。若以后有一条流水线必须在冻结期间跑，先停下来写进报告，而不是加豁免。

兄弟仓库 `bifrost-platform-plugin-flex-query` 的 `bifrost-build-flex-query` 在仓库里已经和本仓库同一条规则：`freeze-check`（`taskRef` 为 `bifrost-release-freeze-check`）是立即的根，`release-window` 在它之后，内联的 `kaniko` 推镜像被这道检查支配。`scripts/release/freeze_known_gaps.json` 的 `gaps` 是空的（`max_age_days` 与 `max_age_reason` 仍在）。检查器不再对 flex-query 单独要求第一个任务是 `release-window`。两个检出并排放着时，`scripts/check-release-chain.py` 不带 `--allow-known-gaps` 退出码是 0。

这些清单还没进集群。本变更不 apply。集群里的 `bifrost-build-flex-query` 仍是旧图，直到有人按上面的顺序自己 apply：先是冻结检查的 Task 和程序 ConfigMap（第 2 步），然后才是这条流水线（和那十一条一样，按文件 apply，不走 `bifrost-apply-manifest`）。只改仓库、不 apply，集群里的推镜像仍不被检查支配。

应用前要核对的一件事（只读实测 2026-10-11）：冻结检查用 PipelineRun 的 ServiceAccount 去读 `cicd/bifrost-release-freeze`，读不到就按冻结处理、拒绝构建。授权名单是 `cicd/default` 和 `cicd/tekton-deliver`（`k8s/cicd/tekton/rbac-release-window.yaml`）。集群里最近一次 `bifrost-build-flex-query`（2026-10-10）跑在 `default` 下，在名单里；别的构建流水线最近一次也都是 `default`。以后有人给这条流水线换身份，要先把新身份加进名单。集群里此刻还没有 `bifrost-release-freeze-check` 这个 Task，也没有任何 Argo 应用同步插件仓库，所以推插件仓库的主线不改变集群。

已经在跑的 PipelineRun 不受影响。改的是 Pipeline 对象；在途的那一次仍按启动时的任务图走完，不会中途插上 `freeze-check`。

旧 PROD 链 `bifrost-deliver-platform-prod` 只有这一次检查，放在两条推镜像之前。过了它的 run（TaskRun 结果 `passed_cut_at`）会把构建和滚动走完，滚动前不再查第二次。还没到检查的 run，跑到检查时被拒。检查自己超时或被取消，任务失败，run 被拒。一条镜像推成、另一条失败，按 run 当时的记录留下，这一片不补救。在途 run 的名字在冻结回执里：看 `tekton.dev/pipelineTask=freeze-check` 的 TaskRun，结果里有 `passed_cut_at`，再用标签 `tekton.dev/pipelineRun` 对上仍在跑的 PipelineRun。列出这件事这一片不做。`scripts/release/freeze_inflight.py` 的测试是一张行为表，不是一次 Tekton 调度演练。

这一片不声称已经挡住自动同步、可变镜像标签，或有人直接改这份 ConfigMap。那是 C 片、E 片和第 4 步的事。

## 一次性 DB 步骤

```bash
scripts/release/release.sh db-steps            # 三个环境各步骤的状态
scripts/release/release.sh db-done prod <id>   # Owner 执行完后记录（本机 ~/.bifrost-release/db-steps.done）
```

记录后在下一次 infra 提交里把环境加进该步骤文件的 `done:` 行，别的机器和会话才看得到。
