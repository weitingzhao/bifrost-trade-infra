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

## 发布窗口：推 main 或起 deliver 之前先看

```bash
scripts/release/release.sh window && git push origin <sha>:refs/heads/main
```

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
| 冻结 | ConfigMap `cicd/bifrost-release-freeze` | `POST …/freeze`（任何人）、`POST …/unfreeze`（Owner 签名） |
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
- **到期提醒**：PROD platform-workers 每小时查一次，到期前 14 天、3 天、1 天推送 Owner，过期后有发布在等再推一次
  （STG 设 `PLATFORM_RELEASE_POLICY_REMINDERS=off`）。存活由 maintainer `platform/prod/release-policy-expiry` 记。
- **首次落地**（一次）：apply `k8s/cicd/release-policy/configmaps.yaml`、`k8s/cicd/tekton/rbac-release-window.yaml`、
  `k8s/cicd/tekton/task-release-window.yaml`（都不在 Argo 下，走平台 `apply_manifest` 审批；先 ConfigMap 和 RBAC，再 task）。

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

### 恢复（只有 Owner，带外）

下面都不能走 apply 流水线。

冻结对象缺失或畸形时，先分清它当时是不是冻结的，再写回同一种形状。当时是冻结的，就不要建成 `frozen: "false"`。对象已经没了之后再跑 `release.sh policy status`，平台把缺失读成没冻结，这次输出不能当依据。看两处：对象还可读时的最后一次 `scripts/release/release.sh policy status`（冻结时这一行是 `frozen    True  (<reason>, at <frozen_at>)`，否则是 `frozen    False`）；平台审计 `GET /api/v1/audit` 里结果为 ok 的最后一条 `release_policy.freeze`（target 是 `who: reason`）或 `release_policy.unfreeze`（target 是签过名的原文 `unfreeze frozen_at=<那次 frozen_at> ...`）。签名不在审计里。`release.sh unfreeze` 写完就删掉本机临时文件，`unfreeze.sig` 只在 ConfigMap 里。对象还在就先 `kubectl -n cicd get configmap bifrost-release-freeze -o json`，只保留该形状的键。对象已经没了、最后一条是冻结：用审计里的 who、reason 和当时 status 行里的 `frozen_at`。对象已经没了、最后一条是解冻、签名也没了：不要编 `unfreeze.sig`，也不要写成从未冻结。用解冻原文里的 `frozen_at` 和它对应的那条 `release_policy.freeze` 把对象写成冻结形状，发布保持停止，然后 Owner 再跑 `release.sh unfreeze`。

`kubectl apply` 会按键合并 ConfigMap 的 `data`，多余键会留下。删掉再创建，只写这一个对象。删和建之间对象是缺失的，这段时间不要有发布在跑：旧的 release-window 把 404 当成没冻结，新检查把 404 当成拒绝。冻结时：

```bash
kubectl -n cicd delete configmap bifrost-release-freeze --ignore-not-found
kubectl -n cicd create -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: bifrost-release-freeze
  namespace: cicd
  labels:
    bifrost.io/purpose: release-policy
data:
  frozen: "true"
  frozen_at: "${FROZEN_AT}"
  who: "${WHO}"
  reason: "${REASON}"
EOF
```

先从上面两处导出 `FROZEN_AT`、`WHO`、`REASON`，再跑这条命令。从未冻结把 `data` 换成只有 `frozen: "false"`。解冻用带引号的 heredoc（`<<'EOF'`），把取出来的 `frozen_at`、`unfreeze.txt`、`unfreeze.sig` 原样贴进去，避免 shell 展开签名。

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

现有 Role `tekton-release-window` 已经允许 `default` 和 `tekton-deliver` 对 `bifrost-release-freeze` 做 `get`，这一片不新写 RBAC。

冻结期间 apply 流水线也不跑，包括它的 plan 模式（plan 和 apply 是同一个任务）。解冻不走这条流水线：`release.sh unfreeze` 把 Owner 签名交给平台 `POST /api/v1/release-policy/unfreeze`。这一片不给任何流水线豁免。若以后有一条流水线必须在冻结期间跑，先停下来写进报告，而不是加豁免。

兄弟仓库 `bifrost-platform-plugin-flex-query` 的 `bifrost-build-flex-query` 今天仍以 `release-window` 开头，内联的 `kaniko` 推镜像不被冻结检查支配。棘轮报 `bifrost-platform-plugin-flex-query/bifrost-build-flex-query: kaniko is not dominated by the freeze check`。这条记在 `scripts/release/freeze_known_gaps.json`，绑的是仓库、流水线、任务名、该内联 `taskSpec` 的 sha256，以及解析过的日期 `2026-10-11`。把这个 `kaniko` 换成同名、脚本里跑 `git push` 的任务，报文不变，摘要变了，是新缺口。`--allow-known-gaps` 只放过仓库、流水线、任务名、摘要都对上、并且日期不早于 30 天的条目。30 天是留给那个仓库改完的一个发布周期；过了就不再匹配，免得后来改过的任务一直顶着旧报文。放过的每一条都打印日龄，例如 `(age 0 days)`，并有 `known gaps: 1`。默认退出码非 0。

没有 CI 任务、没有 make 目标、也没有发布脚本调用 `scripts/check-release-chain.py`。`agent-config/RATCHETS.md` 把这条 TD-263 检查标成 manual（infra 没有 CI）。合进之后，手工跑这个检查会因为 flex-query 这条缺口默认失败。它不会让任何自动检查变红。

要消掉缺口，那个仓库得把 `bifrost-release-freeze-check` 加成立即的根，并让 `release-window` 在它之后。这一片不改那个仓库。那个仓库改完之后，这里 TD-263 对 flex-query「第一个任务必须是 `release-window`」的特例也要改成和本仓库一样（第一个是 `freeze-check`）。

旧 PROD 链 `bifrost-deliver-platform-prod` 只有这一次检查，放在两条推镜像之前。过了它的 run（TaskRun 结果 `passed_cut_at`）会把构建和滚动走完，滚动前不再查第二次。还没到检查的 run，跑到检查时被拒。检查自己超时或被取消，任务失败，run 被拒。一条镜像推成、另一条失败，按 run 当时的记录留下，这一片不补救。在途 run 的名字在冻结回执里：看 `tekton.dev/pipelineTask=freeze-check` 的 TaskRun，结果里有 `passed_cut_at`，再用标签 `tekton.dev/pipelineRun` 对上仍在跑的 PipelineRun。列出这件事这一片不做。`scripts/release/freeze_inflight.py` 的测试是一张行为表，不是一次 Tekton 调度演练。

这一片不声称已经挡住自动同步、可变镜像标签，或有人直接改这份 ConfigMap。那是 C 片、E 片和第 4 步的事。

## 一次性 DB 步骤

```bash
scripts/release/release.sh db-steps            # 三个环境各步骤的状态
scripts/release/release.sh db-done prod <id>   # Owner 执行完后记录（本机 ~/.bifrost-release/db-steps.done）
```

记录后在下一次 infra 提交里把环境加进该步骤文件的 `done:` 行，别的机器和会话才看得到。
