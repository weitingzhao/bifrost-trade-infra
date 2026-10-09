# LANE-W33C 报告

W-33 第 2 步的第二道。发版链不再自己创建集群对象：窗口、镜像同步、钉死的 PROD run 都走平台。代码只在分支上，已推 origin，没有合 main。没有发版、没有 apply、没有写数据库、没有执行真跑清单。D10 仍是 BLOCKED。没有改 `api/internal/approvals/` 的审批语义，也没有碰 `scripts/agent-guard/`。

## 改动

- bifrost-platform · `cursor/w33c-platform` · `61d8595677162397d3df8c8c28cc1fdf38f76df7` · Change-Id `I5c3051586228338cfc3ae7cad29eee98b7f24cff` · 已推 origin
- bifrost-trade-infra · `cursor/w33c-infra` · `0c5845f4eccc57fe10e0638103ae8dfeb036e5af` · Change-Id `Ie4ab24803fd545fa49e689b45e59df138d4bfcb2` · 已推 origin

平台分支从 `origin/main` `e2d5137d3400d359d5b00c8917ad3b9fc2d76c3b` 开。infra 分支从 `cd8c19a4419068ef7e9fe4da82a7996dbef311c6` 开；写报告时 `origin/main` 已到 `4f7211cd94417ec1d68786d4fff4a204f18a9f6c`，`cd8c19a` 仍是其祖先。

〇节四件按 2026-10-09 的决定落地，没有另起方案。

## 一、发布窗口

`GET` / `PUT` / `DELETE /api/v1/delivery/release-window` 读写现有 ConfigMap `cicd/bifrost-release-window`（键 `window.json`）。字段是原来的超集：`who`、`what`、`env`、`pid`（0）、`host`（空）、`started_at`、`expires_at`、`reason`。流水线仍只读 `who` / `what`。ttl 默认 5 分钟，最大 60。同一 `who` 再 PUT 是续期：`started_at` 不动，`expires_at` 后移。别人持有且未过期返回 409。过期视为空，GET 会删掉这份 ConfigMap。DELETE 只有持有者能直接调；`?force=1` 是级别 C，直调 403，审批执行器才带上。并发用 resourceVersion：Create 遇到 AlreadyExists、Update 遇到 Conflict 都重试，测试里 8 个不同 `who` 只有 1 个成功。

`release.sh hold` 成功之后每 60 秒续期一次，退出时以持有者身份 DELETE。本机 `~/.bifrost-release/window.json` 只迁移一次：本机 pid 已死则改名为 `window.json.migrated`，不重新占锁；集群窗口已开则把文件留在原地。

过期同时写进 `scripts/release/window_decision.py` 和 `k8s/cicd/tekton/task-release-window.yaml` 里内联的 `decide()`。没有 `expires_at` 或解析不了的，仍视为开着（兼容旧窗口）。

防线：`api/internal/delivery/window_store_test.go`（`TestReleaseWindowOneHolderWins`、`TestReleaseWindowRenewAndForeignDelete`、`TestExpiredWindowIsEmptyAndReplaceable`）；`scripts/release/test_window_decision.py::WindowTests.test_expired_window_is_empty`；`scripts/check-release-chain.py` 对比两份 `decide()`。

门禁：`cd api && go test ./internal/delivery/` 通过。`python3 -m unittest discover scripts/release` 23 项通过（1 项原有跳过）。`BIFROST_WORKSPACE=/Users/vision-mac-trader/Desktop/stocks python3 scripts/check-release-chain.py` → `check-release-chain: ok (7 window cases)`。

验收：`go test ./internal/delivery/ -count=1 -run 'TestReleaseWindow|TestExpiredWindow'` → 全部通过，且 `TestReleaseWindowOneHolderWins` 的成功次数是 1。

要 Owner 批：窗口 task 不归 Argo 管。合 infra 之后、真跑之前：

```bash
kubectl apply -f k8s/cicd/tekton/task-release-window.yaml
```

未 apply 之前，Tekton 侧不认 `expires_at`，过期窗口仍会挡住 research / 插件构建。平台 API 自己的 `decideReleaseWindow` 会认。

后续：`api/internal/delivery/window_store.go` 的并发锁是 resourceVersion，不是进程内互斥。两副本平台都安全。`release.sh window --clear` 只提交 `release_window_release`（force）审批并打印 id，不轮询。

## 二、镜像同步

`POST /api/v1/delivery/mirrors/sync`，级别 B。仓库必须在 `actuation-policy.yaml` 的 `mirrors.repos` 里，名单与 `bootstrap-gitea-mirrors.sh` 的 `MIRROR_REPOS` 相同（不含 `bifrost-trade-socket`）。代码不写仓库名。未知仓库在发 HTTP 之前拒绝。对每个仓库 `POST` Gitea `mirror-sync`，再轮询 `git/commits/{sha}`，最多 90 秒。`plan_manifest` 在 `startRun` 之前对这一次的 repo+commit 做同样的同步；`Sync` 未接线时 Plan 直接失败（TD-273）。

`release.sh` 不再调用 `bootstrap-gitea-mirrors.sh`，也不再读 gitea-bootstrap Secret。令牌只进权限 600 的 curl 配置文件，用完即删，不进命令行，不打印。

防线：`api/internal/delivery/mirrors_test.go`；`api/internal/workactions/plan_sync_test.go`（先同步、同步失败则不建 run）；`api/internal/actuationpolicy/policy_test.go::TestGoSourcesDoNotNameAllowList` 把 `mirrors.repos` 和 `delivery/mirrors.go` 纳入扫描；`scripts/release/test_w33c_static.py` 断言 `release.sh` 不含引导脚本名。

门禁：`go test ./internal/delivery/ ./internal/workactions/ ./internal/actuationpolicy/` 通过。

验收：`go test ./internal/workactions/ -count=1 -run TestPlan` → `TestPlanSyncsBeforeTheRun` 与 `TestPlanDoesNotStartWhenSyncFails` 通过。

要 Owner 批：无单独命令。策略副本见第六节的顺序。空的 `mirrors.repos` 会让整份策略 `Validate` 失败。

后续：`api/internal/delivery/mirrors.go` 的轮询间隔是 2 秒。`lineage/mirrors.go` 仍是另一条全量刷新，没有复用。

## 三、钉死的 PROD 与流水线参数

`start_pipeline_run` 增加 `params`（object）。只接受该 Pipeline `spec.params` 里声明的名字。字符集 `^[A-Za-z0-9._:@/+-]{1,256}$`。调用方没传 `params` 时，旧的 revision/tag 映射还在，并且 `bifrost-deliver-prod` 会把同一个 revision 填进 `coreRevision`、`workerRevision`、`apiRevision`、`frontendRevision`、`infraRevision`。调用方与旧映射同名时，调用方赢。旧映射里线上 Pipeline 还没声明的名字会被丢掉，所以策略文件还没 apply 之前，不会给旧 Pipeline 送 `coreRevision`。

`bifrost-deliver-prod` 增加这五个参数（`uiRevision` 原来就有），六个 clone 各用各的。`revision` 仍在，给标签用。钉死的 run 请求级 `revision` 保持 `main`（RefPreflight 对每个被 clone 的仓库都要看得到），六个 SHA 只放在 `params` 里，并额外把 `params.revision` 设成 core 的 SHA，标签在 RefPreflight 之后才改写。

`prod-pinned-from-stg.sh` 只输出这六个键的 JSON，stderr 仍打印 `clone-* <sha>`。源文件和输出都没有 `pipelineSpec`。

超时和 amd64 不写死流水线名：Pipeline 注解 `bifrost.io/run-timeout`、`bifrost.io/run-arch=amd64`，`applyDeclaredRunExtras` 抄到 run 上。两条 deliver Pipeline 都加了 `1h0m0s` 和 `amd64`。注解要等 Pipeline 对象 apply 之后才生效。

防线：`api/internal/delivery/params_test.go`；`scripts/release/test_w33c_static.py::test_pinned_output_is_six_shas`。

门禁：`go test ./internal/delivery/ -count=1 -run 'TestMerge|TestDeclared'` 通过。`bash scripts/release/release.sh prod --dry-run --from-stg bifrost-deliver-stg-rtq5w` 退出 0，打印的是 `POST /api/v1/approvals`，body 里是六个 SHA，没有内联 spec。

验收：`python3 -m unittest scripts.release.test_w33c_static` → 通过，且钉死脚本源码不含 `pipelineSpec`。

要 Owner 批：两条 Pipeline 不归 Argo 管。真跑之前 apply（见上线顺序）：

```bash
kubectl apply -f k8s/cicd/tekton/pipeline-deliver-stg.yaml
kubectl apply -f k8s/cicd/tekton/pipeline-deliver-prod.yaml
```

后续：在 Pipeline 对象更新之前，用新 `release.sh` 发钉死 PROD 会被拒（`coreRevision` 等尚未声明）。只传一个 revision 的旧调用方在更新前仍然能发，六个 clone 继续用 `$(params.revision)`。

## 四、release.sh

`stg`：`POST /api/v1/delivery/pipelines/bifrost-deliver-stg/runs`，`revision=main`，级别 B，直接拿 `run.name`。

`prod`：`POST /api/v1/approvals`，action `start_pipeline_run`，然后用 viewer 令牌轮询 `GET /api/v1/approvals/<id>`，直到 executed / failed / rejected / expired，或超过 `--timeout`（退出 3）。run 名读 `result.run.name`，没有则读 `result.target` 的最后一段。

PROD 的 before DB 步骤：每一行 `commit:` 提交一条 `owner_run_command`（reason 是步骤 id），打印审批 id。创建失败则打印命令并退出 1；创建成功退出 3。平台不执行。dry-run 只打印 POST。

角色矩阵：`release-check.sh` 改为 `--via psql`，`PGHOST=192.168.10.73` `PGPORT=30432` `PGUSER=agent_reader`。没有 `~/.pgpass` 就退出，不再退回集群 exec。

`kubectl get` 还在（CI 门和 `release_tool`）。`kubectl create` / `apply` / `delete` / `exec` 不在 `release.sh` 里。

防线：`scripts/release/test_w33c_static.py::test_release_sh_does_not_create_objects_itself`；`scripts/check-release-chain.py` 改为要求两个平台路径，并禁止引导脚本和上述四条 kubectl 子命令。

门禁：

- `bash scripts/release/release.sh stg --dry-run` → 退出 0。打印 `PUT /api/v1/delivery/release-window`、`POST /api/v1/delivery/mirrors/sync`、`POST .../bifrost-deliver-stg/runs`。没有创建任何对象。
- `bash scripts/release/release.sh prod --dry-run --from-stg bifrost-deliver-stg-rtq5w` → 退出 0。该 STG run 的 release-check 记录是 passed。六个 clone SHA 写入 JSON。随后打印 PROD 审批 POST。
- worktree 里没有 `.env`，dry-run 的窗口 GET 只打印路径，没有发出去，也没有打印令牌。合进有 `.env` 的检出之后，dry-run 会真的 GET 一次（只读），窗口开着则以 2 退出。

验收：`bash scripts/release/release.sh stg --dry-run` → 退出 0，输出里有 `POST /api/v1/delivery/pipelines/bifrost-deliver-stg/runs`，且 `rg` 不到 `kubectl create`。

要 Owner 批：无（脚本随 infra main 生效，不 apply）。

后续：`scripts/release/release.sh` 的 `tag_core_release.sh` 在这个 worktree 里找不到兄弟目录 `bifrost-trade-core`，dry-run 把这一步记成失败提示，整次退出码仍是 0。在正常检出里兄弟目录存在。

## 五、文档与 parity

- `docs/RELEASE.md`：窗口、镜像、STG/PROD 起 run、PROD 的 DB 审批，改成平台路径。
- `research-release` 两侧 skill：`parity-id` `research-release-v3` → `research-release-v4`。窗口用 `PUT /api/v1/delivery/release-window`；镜像失败用 `POST /api/v1/delivery/mirrors/sync`；`k8s/orchestration/dagster.yaml` 用 `apply_manifest`（repo `bifrost-research`，级别 C）；ddl 用 `owner_run_command` 再 `scripts/owner/owner-run.sh`。
- `market-data-subscription-focus` 两侧 skill 同步改发布步骤：构建用 `start_pipeline_run` name=`bifrost-build-market-data`，部署用 `plan_manifest` / `apply_manifest`。没有新造 parity-id。
- `CLAUDE.md` 与 `cursor/rules/workspace.mdc` 的窗口段落同步，`workspace-v16` → `workspace-v17`。
- `RATCHETS.md` 增加「发版链不持管理员 kubeconfig（LANE-W33C）」。没有改 `TECH_DEBT.md`。TD-273 由 Plan 先同步覆盖；TD-262 不在本道。

防线：`scripts/release/test_w33c_static.py::test_release_docs_do_not_create_pipelineruns_by_hand`，范围是 `docs/RELEASE.md` 和 `agent-config/{claude,cursor}/skills/**/SKILL.md`。

门禁：`bash scripts/check-agent-config-parity.sh` 在工作区根退出 0（它比的是共享检出里的符号链接，不是这条分支）。分支内 `research-release` 与 `market-data-subscription-focus` 的两侧文件 `diff -q` 无差异。合进 main 之后同一条 parity 脚本会看到 `workspace-v17` 和 `research-release-v4`。

验收：在 infra 分支上 `diff -q agent-config/claude/skills/research-release/SKILL.md agent-config/cursor/skills/research-release/SKILL.md` → 无输出。

要 Owner 批：无。

后续：历史报告和道文件里仍有旧的 kubectl 句子。静态检查故意不扫 `agent-config/work/`。

## 六、pipelinerun-deliver-stg.json 逐项对照

对照文件：`scripts/release/pipelinerun-deliver-stg.json`。平台起 `bifrost-deliver-stg` 时已经会带上的，本道没有再写死一遍。

| 设置 | 平台现在 | 说明 |
|---|---|---|
| `pipelineRef.name=bifrost-deliver-stg` | 会带 | 准入要求 pipelineRef，禁止内联 spec |
| `params.revision=main` | 会带 | 另外，Pipeline 若声明了 `uiRevision`，兼容层会补上 |
| `taskRunSpecs` prepare / rollout / gitops-sync 用 `tekton-deliver` | 会带 | 仍是既有的兼容分支，没有为新功能再加流水线名开关 |
| workspace `build-context` 10Gi、`local-path`、ReadWriteOnce | 会带 | JSON 里的 `creationTimestamp: null` 和空 `status` 是 kubectl 噪声，不带 |
| `timeouts.pipeline=1h0m0s` | apply 注解之后会带 | 注解 `bifrost.io/run-timeout`。Tekton 默认本来就是 1 小时。未 apply 之前没有这层显式超时 |
| `taskRunTemplate`：`serviceAccountName=default`，`nodeSelector kubernetes.io/arch=amd64`，control-plane `Exists`/`NoSchedule` | apply 注解之后会带 | 注解 `bifrost.io/run-arch=amd64`。未 apply 之前这条没有 amd64 约束，这是行为上的缺口 |
| 标签 `bifrost.io/purpose=stg-deliver` | 不带 | 平台写 `bifrost.io/trigger=platform-api` 和 `bifrost.io/revision`。没有消费者读 purpose |
| `generateName` | 不带 | 平台用显式名 `<pipeline>-<unix>` |
| `metadata.namespace`、`creationTimestamp`、`status` | 不带 | 由 API 和集群填 |

`bifrost-deliver-prod` 的 taskRunSpecs 和 10Gi workspace 与 STG 相同，并加上第六节之前说的六个 revision 参数。

## 公开 API

- `PUT /api/v1/delivery/release-window`，action `release_window_hold`，级别 B。body：`what`、`who` 必填，`reason`、`ttl_minutes`、`env` 可选。
- `DELETE /api/v1/delivery/release-window`，action `release_window_release`，级别 B；`force=1` 时级别 C。
- `GET /api/v1/delivery/release-window`，viewer，不是动作。
- `POST /api/v1/delivery/mirrors/sync`，action `sync_mirrors`，级别 B。body：`repos` 必填，`commits` 可选。
- `start_pipeline_run` 增加可选 `params` object。MCP 工具和审批参数一并带上。审批卡片对嵌套的 pipeline params 逐项显示（英文字段名）。
- `config/actions-catalog.json` 增加上述三个 id。没有新的 stdio 工具（仍是 52）。

## Breaking changes

- 新平台进程若加载到没有 `mirrors.repos` 的策略文件，`Validate` 失败，通用写动作整批不加载（见上线顺序）。旧进程加载带这段的新文件不受影响（未知字段被忽略）。
- `release.sh` 合进 main 之后，窗口不再写本机文件；没有平台令牌就不能 hold。STG/PROD 不再接受 kubectl 创建 run。
- 钉死 PROD 的辅助脚本不再输出 PipelineRun。还在读它当 spec 的调用方会坏。`platform-prod-pinned-from-stg.sh` 没改。
- 直接 `DELETE /api/v1/delivery/release-window?force=1` 返回 403，要走审批。`asBool` 接受 `"1"` / `"0"`，避免 query 解析失败之后门禁被绕过。

## 门禁汇总

| 命令 | 结果 |
|---|---|
| platform `cd api && go build ./... && go vet ./... && go test ./...` | 通过 |
| `cd mcp/platform && npm test` | 20 通过 |
| `python3 -m unittest discover scripts/release` | 23 通过，1 跳过 |
| `bash scripts/release/release.sh stg --dry-run` | 退出 0 |
| `bash scripts/release/release.sh prod --dry-run --from-stg bifrost-deliver-stg-rtq5w` | 退出 0 |
| `kubectl kustomize` platform-stg / platform-prod | 通过（2830 / 3012 行） |
| `python3.12 scripts/check_admission_guards.py` | `ok: admission files match the actuation policy`。默认 `python3` 没有 PyYAML，会在 import 处失败 |
| `PLATFORM_ROOT=<platform worktree> python3 scripts/check_ops_context_parity.py` | `ok: 55 decisions`，D10=BLOCKED，三份策略副本一致 |
| `bash scripts/check-agent-config-parity.sh`（工作区根，共享检出） | 退出 0。共享检出仍是 `workspace-v16`；分支上的 v17 要合进 main 之后这条才会看见 |

## 上线顺序

不要先发平台镜像、后更新策略 ConfigMap。新二进制要求 `mirrors.repos` 非空，否则策略加载失败，`apply_manifest` / `plan_manifest` 全部拒绝。旧二进制忽略这段新 YAML。

1. 合 infra 分支（含三份 `actuation-policy.yaml`、两条 Pipeline、窗口 task、`release.sh`、文档）。等 Argo 把 STG/PROD overlay 的策略 ConfigMap 同步上去。此时新的 `release.sh` 已经在 main 上，但对应接口要等下一步的镜像。
2. 合 platform 分支。发 STG 平台镜像。
3. PROD 平台镜像（审批）。
4. Owner 批之后 apply 下面三份（不归 Argo）：

```bash
kubectl apply -f k8s/cicd/tekton/task-release-window.yaml
kubectl apply -f k8s/cicd/tekton/pipeline-deliver-stg.yaml
kubectl apply -f k8s/cicd/tekton/pipeline-deliver-prod.yaml
```

5. 真跑清单。钉死 PROD 必须在第 4 步之后，否则六个参数尚未声明。

这和道文件草稿里「先合 platform、再合 infra」的顺序不同，原因只是策略 `Validate`。Pipeline 的 apply 仍然在真跑之前，这一点与道文件一致。

## 真跑清单

由 Claude 上线时执行。本道没有执行。共 3 条。

1. 一次 STG Trade 发布：`scripts/release/release.sh stg`（先 `--dry-run`）。观察窗口 ConfigMap 在持有期间 `expires_at` 大约每分钟后移，进程退出后 ConfigMap 消失；run 由平台创建，名字来自响应的 `run.name`；镜像同步返回的每个 repo `present` 为 true。
2. 一次新形式的 PROD 钉死发布，等 Owner 批：`scripts/release/release.sh prod --from-stg <刚成功的 STG run>`。观察审批单里六个 SHA 都在，批准后 `result.run.name` 存在，且该 run 的六个 clone commit 与 STG 一致。第 4 步的 Pipeline apply 必须已经完成。
3. 一次插件构建加部署：选一个有改动的插件，或重发 market-data 的当前版本。构建走 `start_pipeline_run`（`bifrost-build-market-data`），部署走 `plan_manifest` 再 `apply_manifest`（级别 C）。观察 Plan 在建 run 之前先同步了镜像。

## 未做与偏离

- 真跑清单 3 条都没跑。没有 `release.sh stg/prod/dev` 真执行，没有 `start_pipeline_run`，没有 kubectl apply/create/delete，没有写数据库。
- 审批卡片的嵌套参数只改了代码，没有在浏览器里点开一张 PROD 审批单。dev console 不是这条 worktree。
- 平台仓库是 husky。新 worktree 不跑钩子，所以平台提交的 Change-Id / Work 是用 `scripts/git-hooks/lineage.sh` 补上的，没有 `--no-verify`，也没有改 git config。
- 道文件的上线顺序写的是先合 platform。报告第六节改成先让策略 ConfigMap 落地，再发平台镜像。这是为了避免 `Validate` 把通用写动作整批拒绝，不是新的产品决定。
- 没有新的架构级决策留着等拍板。仓库白名单在配置里，参数名从集群里的 Pipeline 读，代码不写死仓库名或流水线名。
