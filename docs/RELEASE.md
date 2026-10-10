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

## 一次性 DB 步骤

```bash
scripts/release/release.sh db-steps            # 三个环境各步骤的状态
scripts/release/release.sh db-done prod <id>   # Owner 执行完后记录（本机 ~/.bifrost-release/db-steps.done）
```

记录后在下一次 infra 提交里把环境加进该步骤文件的 `done:` 行，别的机器和会话才看得到。
