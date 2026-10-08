# Trade 发布（`scripts/release/`，TD-84）

一次 Trade 发布 = STG（从 `main`）→ 核对 → PROD（钉在那次 STG 克隆的提交上）→ 核对 → core tag → DEV 跟上。
2026-10-03 这些步骤是手工一条条做的；现在由 `scripts/release/` 的脚本做。auto mode 的「Approved Release Runbook」规则
（`agent-config/claude/auto-mode/project.autoMode.json`，Owner 用 `apply-auto-mode.sh` 应用后生效）按这些脚本路径放行 c–f、i 项。
流水线本身见 [DELIVER_STG](DELIVER_STG.md)。

| 脚本 | 做什么 | 写什么 |
|------|--------|--------|
| `release.sh stg\|prod\|dev [--dry-run]` | 一个入口：窗口锁 → 并发检查 → DB 步骤闸门 → before 快照 → 建 run → 等待 → after 核对 → 汇总 | 建 PipelineRun（stg/prod）、改 `:dev` 镜像并重启 DEV（dev） |
| `prod-pinned-from-stg.sh <stg-run> [-o f]` | 生成 PROD 钉版本 spec（不创建） | 只写本地文件 |
| `release-check.sh <env> before\|after\|probes` / `diff a b` | 快照、diff、`/health` core 身份、探针 | 只读（GET、`kubectl get`） |
| `tag_core_release.sh <sha> [--push]` | 给到达 PROD 的 core 提交打 `v<version>` | 只在 `--push` 时 |

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

`--dry-run` 跑所有只读检查（窗口、并发、STG run 状态、核对记录、生成 spec、DB 步骤），其余命令只打印；
任何一项不满足时打印 `WOULD REFUSE` 并以 2 退出。

### release.sh 每一步

1. **窗口锁** `~/.bifrost-release/window.json`（who / what / env / pid / host / started_at）。已存在就拒绝；
   脚本无论怎么退出都会删掉自己的锁（trap）。
2. **并发**：任何 `bifrost-deliver-*` run 处于 Unknown，或 2 分钟内刚建过，就拒绝（09-27 两个会话相隔 16 秒发同一版的教训）。
   建 run 前会再查一次。
3. **PROD 专有**：`--from-stg <run>` 必须是 `bifrost-deliver-stg` 的 run、Succeeded，且
   `~/.bifrost-release/checks/<run>.json` 写着 `passed: true`（由 `release-check.sh stg after --run <run>` 写，
   `release.sh stg` 会自动做）。然后生成钉版本 spec：线上 `pipeline/bifrost-deliver-prod` 的 spec，6 个
   `clone-<repo>` 的 `revision` 换成 STG run 对应 TaskRun 的结果 `commit`（40 位，缺一个就拒绝）。
4. **一次性 DB 步骤**：`db-steps.d/` 里对本环境 `when: before` 且未完成的步骤 → 打印给 Owner 的命令并**停下**（exit 3）。
   脚本永远不对 stg / prod / golden_source 跑 `psql`。格式见 `scripts/release/db-steps.d/README.md`。
5. **before 快照** → `${BIFROST_RELEASE_DIR:-/tmp/claude-501/release}/<date>/<env>-<HHMMSS>/`。
6. **建 run**：STG `kubectl create -f scripts/release/pipelinerun-deliver-stg.json`（revision main）；
   PROD 先 `--dry-run=server` 再 create；DEV 是 `RESTART=1 make dev-sync-backend-images`：worker、四个 API 和前端的 `:dev` 一起跟 `:stg`（前端镜像不分环境；2026-10-05 前前端不在内，DEV 前端曾停在 10-02）。
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
或**起任何 `bifrost-deliver-*` run** 之前都先跑它：窗口开着就等它关，或者问 Owner。持有进程已不在
（同一台机器上 pid 不存在）时它会提示是残留锁，由 Owner 决定 `release.sh window --clear`；进程还在时 `--clear` 拒绝。

窗口只在 `release.sh` 运行期间存在（`hold` 一直占到进程退出）。Research 与插件用同一个文件，
`what` 写仓库名；`hold` 把它镜像到 ConfigMap `cicd/bifrost-release-window`。对应流水线的第一个 task
和 platform-api 的 `start_pipeline_run` 在窗口被别人持有时拒绝。`stg` / `prod` 在创建 run 之前同步
Gitea 镜像，并要求所发 SHA 有 Succeeded 的 `ci-*`，`--allow-red <原因>` 才放行。
STG 与 PROD 之间（等 Owner 看 STG）没有锁——这段时间推 main 不影响 PROD，
因为 PROD 钉的是 STG 克隆的提交，不是 `main`。

### 正常结束 `hold`

`hold` 占着窗口直到**该 shell 进程退出**；退出时 trap 会删掉本地 `window.json` 并 unpublish ConfigMap。

- **推荐**：对 `release.sh hold` 进程发 `kill -TERM <pid>`，或在前台按 Ctrl-C（SIGINT）。几秒内应看到进程结束，`release.sh window` 恢复 exit 0。
- **不要**对 holder 发 `kill -9`：会跳过 EXIT trap，窗口文件和 ConfigMap 会留成残留锁。
- **残留锁**（`window` 提示 pid 已不在、或你误用了 `kill -9`）：只有 Owner 可跑 `release.sh window --clear`（规则见上文）；不要用 `--clear` 去杀还在跑的 holder。

旧版实现用前台 `sleep 3600`，`kill -TERM` 可能要等一小时才生效；若你仍看到这种现象，升级到含 TD-269 修复的 `release.sh`。

## 一次性 DB 步骤

```bash
scripts/release/release.sh db-steps            # 三个环境各步骤的状态
scripts/release/release.sh db-done prod <id>   # Owner 执行完后记录（本机 ~/.bifrost-release/db-steps.done）
```

记录后在下一次 infra 提交里把环境加进该步骤文件的 `done:` 行，别的机器和会话才看得到。
