# 台账清理：129 条「未开始」里 63 条离开台账（2026-11-05）

状态：已执行。属于还债方案 D5 台账止涨（`DESIGN-r5-debt-paydown-2026-11-05.md` §2 D5），统筹线程 11-05 11:0x CST 按清单执行。
核对基线：台账取自 infra `ae24104`；代码按各仓 Gitea `origin/main` 核对（platform `8920724c`、research `badd5d6`、trade-frontend `ac431ff5` 等），只读。

| 去向 | 条数 | 台账里怎么处理 | 原文在哪 |
|---|---|---|---|
| 已修好（DROP_FIXED） | 12 | 删除 | git 历史 |
| 已退役（DROP_STALE） | 2 | 删除 | git 历史 |
| 合并（MERGE_INTO） | 10 | 删除，目标条目加一行「合并自」 | git 历史 |
| 挂到 R5 的步骤（ATTACH） | 15 | 删除，由对应步骤负责 | 本文 §3 |
| 降级（DEMOTE） | 24 | 删除，够不上登记门槛 | `CUT-r5-ledger-demoted-2026-11-05.md` |

登记门槛（D5）：只登记挡住业务、出过事故、有明确修法的三类；其余写进对应设计稿的风险。保留 66 条。另外改写了 TD-266（原因换了、症状还在），TD-285 并入 TD-309 时标出两者修法冲突、待定。

## 1. 已修好、已退役（直接删除）

防线：每条的修复提交自带测试或检查，见证据列；没有单列新防线。

| TD | 级 | 领域 | 标题 | 核对结论 | 证据 |
|---|---|---|---|---|---|
| TD-308 | P2 | ops-platform | the progress document is published by a script that never says whether it was accepted; th | Progress 看板已从所有页面退役，AgentWorkBoard 只被测试引用；进度改看 Console 计划视图 | bifrost-platform 242db7f4（board retired from every page）；console/src/pages/shell/progress/AgentWorkBoard.tsx:218 无路由引用 |
| TD-346 | P2 | release | push-main.sh pushes a commit whose tests it never saw: twice on 2026-10-14 a red gate and  | push-main 第 6 步已在干净 worktree 跑仓库快测试，红即拒推（TD-413 待签收） | bifrost-trade-infra/scripts/release/push-main.sh:31-39@ae24104；修复随 TD-413（待你签收） |
| TD-348 | P3 | observability | the API latency alert counts agentd's long-poll claim, so a healthy STG platform-api pages | 延迟告警回退直方图已排除 agentrt claim/messages 与 approvals/claim 长轮询，含规则测试 | bifrost-trade-infra/k8s/monitoring/bifrost-alerting-rules.yaml:89@ae24104 (8a360da); rule-tests/alerts-1024.test.yaml |
| TD-350 | P2 | agentrt | checks of a task with no pushed commit run their commands in an empty directory | 检查任务 BaseCommit 缺 commit 时取主任务 base，agentd 有 repo+base 即 checkout；事故真因可能是任务本身无 repo（未核实） | bifrost-platform/api/internal/agentrt/store/accept.go:161; api/internal/agentd/run.go:341@8920724c |
| TD-363 | P3 | release | push-main.sh pushes a Go repository's main without running its tests, so a session that sk | push-main 现要求该提交 ci-* Succeeded（CI 跑全量 go test），并跑 go vet 与改动包测试（TD-413） | bifrost-trade-infra/scripts/release/push-main.sh:14-24,36,401-421@ae24104 |
| TD-385 | P2 | console | after every Console release a browser keeps the old index.html and loses its stylesheet: t | Console nginx 已加 /assets 404 + immutable、index no-cache；frontend 也有 no-cache 且静态缺失走 404 | bifrost-platform 6f76a8c8；console/nginx.conf:26-39@8920724c；bifrost-trade-frontend/nginx.conf:7-20@ac431ff5 |
| TD-398 | P2 | ci | the platform CI gives the whole `go test ./...` 120 seconds per package, and the agentrt s | 包超时已从 120s 提到 900s 并已应用到集群；与 TD-374 重复（store 包现约 230s，见 NOTE） | bifrost-trade-infra/k8s/cicd/tekton/task-ci-platform-test-api.yaml:263@ae24104；kubectl get task bifrost-ci-platform-test-api 显示 900s |
| TD-420 | P2 | approvals | a pipeline-run approval is created without checking that its revision exists, so the Owner | 建单时即核对所签提交，缺失不写审批行 | bifrost-platform de9087ab/8dab6fb7/2c406dd0；api/internal/delivery/request_refs.go:15；server/approval_create_check.go:15 |
| TD-421 | P2 | runtime | a branch task without `base_commit` is accepted, and agentd runs it in an empty directory | 提议时拒无 repo/base_commit 的 branch 任务；agentd 不在空目录起执行者 | bifrost-platform e166e519；api/internal/agentrt/store/propose.go:486@8920724c；agentd/run.go:349 |
| TD-423 | P3 | gitea | batch D's step 5 copied back 12 attempt branches that agentd had deleted on purpose | 照着跑的脚本已删；12 条分支中只剩 t_01M50 的 3 条 ref，无人引用，纯清理 | infra 27076df 删 copy-agent-branches.sh；git ls-remote origin refs/heads/agent/* 2026-11-05 只见 3 条 t_01M50* |
| TD-425 | P3 | ops-console | the sign-off list shows a step whose work has not started as if it were ready to sign | 选项 A 已落地：未开始的步骤移出签收计数，另列 Not started | 82b3e9d7（+8920724c 后续）；console/src/api/agentRuntimePlan.ts:370-375@8920724c |
| TD-426 | P3 | agentrt | tests · TestExamVoidRefusals fails about once in 256 runs: its "no such paper" id can be a | 用例已改为翻转首位十六进制，永不等于真 id | 596048b8；api/internal/agentrt/store/examvoid_test.go:101-105@8920724c |
| TD-455 | P3 | Console / 平台 MCP | 落地卡不在问题列表里 | list_questions 默认 inbox 只列本线程（设计如此），status=open 会列全部 open 卡含 agentrt 的；按代码核对、未实测 | bifrost-platform/mcp/platform/src/questionTools.ts:108; api/internal/questions/transition.go:308@8920724c |
| TD-460 | P2 | platform B5 | 首次 STG 自动发布 canary 缺「创建样本 / 收尾」的操作入口 | 已加 Tier C 动作 stg_release_sample_create/finalize 与 canary 文档动作名测试（即防线） | bifrost-platform 3ddb155d; api/internal/actions/catalog.go:492,507@8920724c; api/cmd/stg-release-probe/canary_doc_test.go:99 |

## 2. 合并

| TD | 并入 | 标题 | 理由 |
|---|---|---|---|
| TD-285 | TD-309 | The applier cannot take over a field that `kubectl-client-side-apply` owns: plan and apply | 同一机制：client-side-apply 字段归属与 applier SSA 冲突（TD-309 在做，限 Tekton；本条是通用对象）；11-01 TD-473 又撞 |
| TD-361 | TD-394 | a failure before an attempt starts (checkout, a sibling clone, the setup wrapper) is never | 修法已随 TD-394（在做）落地：准备失败以 prepare_failed 结束并上报，三次即出卡 |
| TD-369 | TD-344 | the platform MCP package's type check is red, and no CI task runs it | 与 TD-344 同一机制同一行（writeGate.test.ts:85）；类型错已修，剩 CI 步骤 |
| TD-375 | TD-370 | security · threads that share one token can still act as each other, and the question rout | TD-370（观察中）的余项：其修法第二选项「每线程自有令牌」就是本条修法；questions 路由仍只校验头格式 |
| TD-377 | TD-359 | security · an executor still reads what its user can read: token files and other attempts' | 同一机制：执行者与 agentd 同用户可读令牌文件；读规则未管（confine.go 明写） |
| TD-388 | TD-403 | a codex review of Go work cannot build Go or run database tests, so it fails work it could | 修法即 TD-403（每次尝试含复核都起临时库，"for a check, the subject's repository"）+ TD-404 Go 缓存；待 TD-403 的 STG 验收 |
| TD-406 | TD-354 | a ready task that no executor ever could take (empty route, every candidate retired or exc | 与 TD-354 同一机制（ready 任务无人可领却不出卡、needs_you 为 0）；TD-354 的修法覆盖 TD-406 的空路由/全排除情形（原 chunk3 判 DEMOTE，按跨块核对改并入） |
| TD-412 | TD-344 | the platform's MCP server is never type-checked in CI, and main has carried a type error s | 与 TD-344/TD-369 同一件：mcp/platform 无 CI 类型检查；类型错已由 e98b1487 修，剩 CI 步骤 |
| TD-494 | TD-514 | PROD 的 agentrt-landing-requests 一轮大约每 10 分钟超时一次，每轮都重读同一批旧审批 | 与 TD-514（在做，分支 td/514-456-handin）同一循环 agentrt-landing-requests 重读已执行旧单；11-05 PROD 仍 24h 85 次超时，作 TD-514 上线验收基线 |
| TD-506 | TD-497 | 重提的任务不挂到它替代的那个，旧的一直 ready；预算卡不看同 mission 里已接受的同步骤、同任务书的实现，写「No recommendation」（卡 #99） | 同一机制：被替代/没用上的交付任务一直 ready；②即 TD-497 修法，①卡片规则一并带入 |

## 3. 挂到 R5 的步骤（原文）

这些债的修法正是对应步骤要做的事，由步骤负责，步骤完成时一并验收。

### → R5:5.13 (5.13-1…5.13-12)

#### TD-444（原文，挂到 R5:5.13 (5.13-1…5.13-12)）

**P2 · NAS 存储 · 两块 SSD 镜像放常写数据和每日备份，机械盘每周汇总一次；第二块 SSD 11-03 到货后直接按此做**

- **状态**：未开始（2026-11-02 统筹线程 12:0x CST：Owner 定按最终方案一次做：第二块 SSD 11-03 到货、当天装上后，不再分期。Time Machine 已于当天停用，本机改为 restic 每周白名单备份到 NAS `TimeMachine` 共享（加密、只留最新一份、约 3.7 GB），NAS 用量 1.42 TB → 0.41 TB，原推荐 A 的前提已不在。TD-489（同日重复登记）并入此条。）此前：未开始（2026-10-26 设计已出，等 Owner 选 A / B / C）。
- **证据**：`agent-config/work/multi-agent/CUT-w68-nas-tiering-2026-10-26.md` 第 2 节。10-24 16:30 至 10-26 21:50 CDT：52 次突发、每小时 0.97 次、每次约 15 分钟、中位收 3.5 GB；占 md1 全部写入 82%、盘忙时间 79%；突发间盘忙 4.7%。突发时 md1 写等待中位 1216 ms（空闲 107 ms），`NodeDiskIOSaturation` 每晚 pending。本机 Time Machine 目标是 NAS `TimeMachine` 共享，间隔 3600 秒，家目录每小时约 1.1 GB 改动（`~/.codex`、Chrome、Codex 应用数据等未排除）。
- **证据（2026-11-02）**：`smartctl_device_bytes_written{host="nas",device="nvme0"}` 一生 12.8 MB、24 小时增量 0（SSD 闲置）；三块机械盘 `Start_Stop_Count` 24 小时增量 0；仍在常写机械盘的：Postgres WAL 归档到 NAS 上的 MinIO（`cnpg_pg_stat_archiver_archived_count` 现 0.8 段/分钟、24 小时最高 6 段/分钟）、04 上 Prometheus 的 NFS（Write 0.39/s、Commit 0.33/s）。NAS 卷 0.41 TB：MinIO 328 GB、Prometheus 约 12 GB、其余约 74 GB。
- **影响**：Owner 每小时听到机械盘响一阵；Prometheus WAL、MinIO WAL 归档、registry 拉镜像每小时有约 15 分钟每次写要等一秒多；三块盘常年承受不必要的随机写。
- **修法**（Owner 2026-11-02 定）：两块同款 SSD 组成 RAID1（`/volume2`），放常写的热数据：Prometheus 与 Alertmanager 的卷（新 StorageClass，如 `nfs-fast`）、registry；也放每日备份：MinIO（WAL 与每晚基础备份）、逻辑备份、Gitea / 集群状态 / Finance 备份、行情归档的每晚副本。RAID5 机械盘放行情归档主份、本机 restic 备份，并每周从 SSD 汇总一次所有备份作长期存档，机械盘平时空闲。当天先前定的「单盘先放热数据」的第一期取消。CUT 文档第 5 节的 A（Time Machine 换 SSD）作废。
- **第二块 SSD 到货后（Owner 2026-11-02 下单，11-03 到货当天装）**，按顺序，一步做完核对再做下一步：
  1. （统筹）装之前：`release.sh window` 没有窗口、cicd 里没有在跑的 PipelineRun；避开每晚 21:00–23:45 CST 的备份和 22:00 起的 backup-retry。NAS 一关机，registry、Prometheus、Alertmanager、MinIO（WAL 归档）、行情归档都会断，hard 挂载的 Pod 会卡住，NAS 回来后自己恢复。
  2. （Owner）UGOS 里正常关机 → 装进第二个 M.2 槽（同款 Kingston SNV3S1000G，装散热片）→ 开机。
  3. （统筹）开机后核对：NAS 能 ping 通；04 上的 Prometheus、registry、market-data-api 与 02 上的 Alertmanager 都 Ready；`up{job="smartctl",host="nas"}` 为 1 且出现 nvme1，`critical_warning` 和 `media_errors` 为 0；`minio_cluster_usage_total_bytes` 有数；CNPG 的 WAL 归档追上（`cnpg_pg_stat_archiver_failed_count` 不再增长）；本机 restic 的共享能重新挂上（`last-success` 下次照常更新）。
  4. （Owner，UGOS）先看 `/volume2` 里那约 2.2 GB 是什么、要不要留；再把 pool2 改成两块 SSD 的 RAID1：UGOS 能「加盘改 RAID1」就原地改，不能就删掉 pool2、用两块 SSD 新建 RAID1 池。做完在 UGOS 里对两块 SSD 各跑一次磁盘检测。
  5. （统筹）RAID1 建好后核对两块盘 SMART 正常、池状态健康，再按上面「修法」搬迁：先热数据（Prometheus、Alertmanager、registry），再把每日备份改成先落 SSD、并建每周汇总到 RAID5 的任务；每一类搬之前写好怎么停、怎么回退，集群清单改动走 C 级单。
  6. （统筹）验收：机械盘一周里只有每周汇总那一阵在忙；SSD 两块健康；从 SSD 和 RAID5 各恢复一次数据库备份和行情归档做演练。
- **防线**：做完后加一条告警「NAS 一天里盘忙超 30% 的 5 分钟窗口超过 20 个」（`count_over_time((rate(node_disk_io_time_seconds_total{host="nas",device="sda"}[5m]) > 0.3)[1d:5m]) > 20`，warning），让「有人又往 RAID5 上放了热写」当天能看到；归档副本由 CronJob 的最近成功时间告警兜住。
- **验收**：首次全量完成后 24 小时，CUT 第 7 节五项：盘忙超 30% 的窗口 ≤ 5/天、md1 最差写等待 < 0.3 秒、nvme0n1 每小时有写、SSD 健康 1、`NodeDiskIOSaturation` 不再 pending。
- 审批：NAS 关机装盘、RAID1 与共享由 Owner 在 UGOS 做；集群清单改动按 C 级单；MinIO 搬家前先确认 WAL 归档不断档的切法。

### → R5:5.2-6

#### TD-429（原文，挂到 R5:5.2-6）

**P1 · delivery · release window · the holder is a machine, not a session, and approved PROD runs start without holding the window**

- **状态**：未开始（2026-10-24 统筹线程记；修法并进 4.3「每个会话一个持有凭据」）
- **Claim**: ① `release.sh` sets the holder to `${USER}@$(hostname -s)` (`bifrost-trade-infra` `scripts/release/release.sh:746,772`), and the window store treats a second hold by the same holder as a renewal that may change `what` (`bifrost-platform` `api/internal/delivery/window_store.go:155-163`): every session on one machine is the same holder, so the window does not keep two sessions on one machine apart. ② A PROD approval executes `start_pipeline_run` for the requester without the runner holding the window; on 2026-10-23 four platform PROD runs started while nobody held it (the coordinator's watcher takes the window only after the run appears).
- **Evidence**: ① code read by the coordinator 2026-10-24; ② `DESIGN-release-lanes-2026-10-24.md` §1.3 (audit of 2026-10-23), not re-measured by the coordinator.
- **Impact**: the two incidents the window exists for (2026-09-27 core 0.24.0 released twice, 2026-09-28 a plugin tag overwritten) can recur between sessions on the same machine, or between a PROD run and anything else.
- **Fix**: a per-session holder credential issued by the platform; the PROD runner takes the application's lane before it starts the run and releases it when the run ends (4.3).
- **Ratchet**: a test where two sessions on one host hold the same application: the second is refused; an audit check that every PROD run started inside a held lane.
- 验收: both checks pass on PROD for a week of releases.
- 审批 要（4.3 的设计由 Owner 定）· 代价 M · 风险 medium · repos: bifrost-platform, bifrost-trade-infra

#### TD-431（原文，挂到 R5:5.2-6）

**P2 · delivery · release window · the window's decision table is hard-coded three times with Trade's repository and pipeline names**

- **状态**：未开始（2026-10-24 统筹线程记；4.3 设计稿实读，修法并进 4.3「应用登记」）
- **Claim**: which pipelines must hold the window, which pass without it and which are refused is decided by three copies of one table, each naming Trade's five repositories and four deliver pipelines: Go `bifrost-platform` `api/internal/delivery/release_window.go:21-39,141-183`, Python `bifrost-trade-infra` `scripts/release/window_decision.py:12-33,75-126`, Tekton inline `k8s/cicd/tekton/task-release-window.yaml:39-134`. A pipeline not in the table (`bifrost-build-stg`, `build-frontend-stg`, `build-research-pine`, `ci-finance`) is refused whenever any window is open.
- **Evidence**: `work/multi-agent/DESIGN-release-lanes-2026-10-24.md` §1.1 (branch w31/r4-release-lanes 836b6508); copies to be re-read by the fix.
- **Impact**: the platform knows Trade by name (CLAUDE.md §1 verification test fails); adding an application means editing three files in two repositories that can drift apart.
- **Fix**: one application registry the three readers load (4.3 §2.1), or one reader the others call.
- **Ratchet**: a test that fails when a repository or pipeline name appears in a decision copy instead of the registry.
- 验收: a new application registered in one place is decided the same by all three readers.
- 审批 不要 · 代价 M · 风险 low · repos: bifrost-platform, bifrost-trade-infra

### → R5:5.3-14

#### TD-272（原文，挂到 R5:5.3-14）

**P3 · ops-platform · tekton-trigger can create any PipelineRun in cicd, and no admission policy matches it, so its token is still a path to the cluster-admin Argo controller account**

- **状态**：未开始
- **Claim**: TD-271's policies match only the platform identities and tekton-deliver. Role `cicd/tekton-trigger-runs` grants `tekton-trigger` create on PipelineRuns and TaskRuns (and get/list/watch on Secrets in cicd). A run it creates may inline a spec, use a resolver, bind a secret workspace or name `argocd-application-controller`. The EventListener only renders fixed TriggerTemplates, so the exposure is the SA token or the EventListener pod, not an anonymous webhook.
- **Measured**: MEASURED 2026-10-09 (Claude, read-only). Role rules: `pipelineruns, taskruns` create/get/list; `secrets` get/list/watch. `40-admission.yaml` matchConditions list `bifrost-platform` (STG, PROD) and `tekton-deliver` only.
- **Evidence**:
  - `bifrost-trade-infra/k8s/platform-rbac/40-admission.yaml` — `matchConditions` of `bifrost-platform-pipelinerun` / `bifrost-platform-taskrun`
  - live: `role/tekton-trigger-runs` in cicd
- **Impact**: Whoever holds the tekton-trigger token is cluster-admin through the Argo account, the same way the platform was before TD-271.
- **Fix**: Add `system:serviceaccount:cicd:tekton-trigger` to the two run policies' matchConditions, after measuring that its TriggerTemplates only use `pipelineRef` names, volumeClaimTemplate workspaces and the `default` account. Drop the Secrets list/watch from its role if the interceptors do not need it.
- **Ratchet**: `check_admission_guards.py --live` gains the same inline / resolver / secret-workspace cases as tekton-trigger, plus a normal templated run allowed.
- 验收: `python3 scripts/check_admission_guards.py --live`（tekton-trigger 的反例被拒、正常 run 放行）
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-trade-infra

### → R5:5.3-16

#### TD-330（原文，挂到 R5:5.3-16）

**P2 · ops-platform · a push to infra main that touches the production platform's manifests is deployed by Argo at once, with no approval and no release check**

- **状态**：未开始（2026-10-13 11:34 护栏 ⑤ 选路时记下：Owner 选了走标签，钉住清单的做法留到第 3 轮和全自动发布一起看）
- **Claim**: the Application `bifrost-platform-prod` follows `main` of the infra repository with automated sync, prune and selfHeal. Any session that pushes a change under `k8s/overlays/platform-prod` or `k8s/base-platform` changes production; the approval request, the release window and the source check of the delivery pipeline are not on that path. Twelve repositories and several agent sessions push to that branch every day.
- **Measured**: MEASURED 2026-10-12 22:45 read-only: `targetRevision=main`, `automated={prune:true,selfHeal:true}`, no `ignoreDifferences`. About 20 commits touched those two directories in the month before (counted for the design, `agent-work` notes; NOT re-counted here).
- **Evidence**: `k8s/cicd/applications/bifrost-platform-prod.yaml:12-22`; `bifrost-trade-infra/CLAUDE.md` ("推 main 即改运行时"); the three design drafts and reviews 141, 143, 148 of guardrail 5 (pinning the Application to a commit advanced by the delivery pipeline closes this, and was not chosen now: three drafts still had wrong-answer paths).
- **Impact**: the one production surface an agent can change without the Owner seeing a request. A wrong edit to a ConfigMap generator there rolls the API and the workers.
- **Fix**: either pin the Application to a commit that only the delivery pipeline advances (the design exists, unfinished), or a smaller guard first: the agent guard and CI refuse a push that touches those two directories unless it carries an approved request's id; decide when round 3 is planned.
- **Ratchet**: a read-only check that the live `targetRevision` and sync policy are what the ledger says, and whichever guard is chosen.
- 验收: a change under `k8s/overlays/platform-prod` reaches production only through an approved request
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-trade-infra, bifrost-platform

### → R5:5.3-26

#### TD-337（原文，挂到 R5:5.3-26）

**P2 · ops-platform · routine platform releases still wait for the Owner's approval, and one pending request freezes the platform's STG: on 2026-10-13 three chained requests left the line idle for about nine hours**

- **状态**：未开始（2026-10-13 19:22 Owner 定：不做通知静默时段，也不做「撤回待批单」这类机制；该调整的是哪些单子需要人批，那是 W-56 的规则，等它的门槛做完由他签；现在不强求。统筹方先改排法：他不在时不建单，做完的攒着，他在时合成一张）
- **Claim**: by the architecture's definition of the human's role (goals, rules, irreversible things) the three requests of 2026-10-13 (#13, #14, #15: reversible code releases of the platform, with green CI, the same commit on STG and an independent review) did not need a human decision. They reached the Owner because the release policy does not list the production pipelines until W-56's thresholds are accepted (his decision of 2026-10-10). While a request is pending, the source gate of a production delivery (the newest successful STG delivery must be the requested commit) keeps anything else off the platform's STG, so requests made one by one form a chain: #13 waited 10 h 51 min, #14 1 h 2 min, #15 4 h 49 min.
- **Measured**: MEASURED 2026-10-13 from the request records and from the coordinator's commit and event log (no activity 06:08–11:34 and 14:29–18:13 CDT; the second gap was a stalled thread, LESSONS row 120).
- **Evidence**: `scripts/release/platform_prod_gate.py:165-187`; `agent-config/WORK.md` W-56 (thresholds, and the Owner's notes of 2026-10-10, 2026-10-12 and 2026-10-13); `agent-config/work/multi-agent/LESSONS-from-practice.md` row 121.
- **Impact**: every routine release costs the Owner an approval and stalls the platform line while he is away.
- **Fix**: finish W-56's thresholds (rollback without rebuild, failure detection, the drills) and have the Owner sign a release policy that lists the platform's production pipeline; after that only three kinds of release reach him: outside the policy, a failed or stuck check, during a freeze. Until then the coordinator batches: no request while he is away, one request for everything verified on STG when he is back.
- **Ratchet**: the policy template's own test (production pipelines stay out of the policy until the thresholds are accepted) is the line to move, with his signature.
- 验收: a routine platform release reaches production with no approval request, and a release outside the policy still produces one
- 审批 Owner 签规则（放宽）· 代价 L（W-56 的剩余门槛）· 风险 med · repos: bifrost-platform, bifrost-trade-infra

### → R5:5.4-2

#### TD-471（原文，挂到 R5:5.4-2）

**P2 · S5 · 检查器镜像里没有清单绑定的依赖声明文件，启用后每次检查都会报 S5_TYPE，且构建期发现不了**

- **状态**：未开始（2026-10-31）。修法待 Owner 选（A / B / C）。
- **证据**：检查器从 `/opt/s5/node_modules` 解析依赖（platform `api/internal/agentrt/rules/s5check/ts/compiler.cjs:11-13,170-178`），实读的每个声明文件 sha256 进 toolchain，与 `policies/manifest.json` 不等即拒：`ts/contracts.cjs:270`（S5_TYPE）、`:298`（S5_IMPORT_UNKNOWN）。manifest 的 toolchain 共 324 项，其中 `dependencies/*` 263 个文件 / 78 个包（`@bifrost/ui` 71 个：`dist/**/*.d.ts`、`package.json`、嵌套的 clsx / class-variance-authority；其余是 console 的 `@types/react`、radix、vitest、tanstack 等）。镜像只装 go、node、typescript（infra `docker/s5-checker/TOOLS.lock.json`、`fetch_tools.py:21-23`、`Dockerfile:6-11,19-21`），runner 只把 UI 当 bare 仓库绑 SHA、不构建 dist（`runner.py:176-195,340-341,379`）。镜像构建期的 `verify_materials.py` 与 `--ci-materials`（`materials.go:257-276`）只校 manifest、脚本、TOOLS.lock、UI pin，不校 toolchain 里的依赖文件，所以镜像会「绿着」构建出来。2026-10-31 实测：本机 `console/node_modules` + bifrost-ui c83f40b 构建产物与 263 项逐一相等，修法可行。
- **影响**：S5 启用后没有一件落地能过检查；而规则一登记 S5 路径，platform 所有 `.ts/.tsx` 落地都要 S5 证据（`landing/s5.go:106,114`），展示类 TSX 落地会一起卡住。
- **修法（三选一）**：A（推荐）镜像内按 `platform/console/package-lock.json` 做 `npm ci --ignore-scripts`，流水线加 `clone-ui`（`uiRevision` = `policies/ui-revision.json` 的 pin，validate-sources 一并校验）并构出 dist，组装 `/opt/s5/node_modules`；B 检查时由 fetch Task 现装（扩大联网面，违背 README:96-97「不在检查时安装」）；C 把 263 个文件 vendor 进 `rules/s5check/vendor/`，Dockerfile 直接 COPY（离线，但每次 enroll 要重新 vendor）。
- **防线**：`docker/s5-checker/verify_materials.py` 构建期逐项比对 manifest.toolchain 的全部哈希，不等即构建失败；platform 的 `--ci-materials` 同样覆盖。
- **验收**：S5 启用演练中一次真实检查 `passed:true`、`findings:[]`，且 toolchain 无 S5_TYPE。

### → R5:5.4-3

#### TD-472（原文，挂到 R5:5.4-3）

**P2 · S5 · 准入策略文件里的 S5 段在 Kubernetes 1.35 上 CEL 编译不过，从未装上；main 与线上不一致**

- **状态**：未开始（2026-10-31）。
- **证据**：2026-10-31 11:17 #233（owner_run_command）对 infra main f871bc4 的 `k8s/platform-rbac/40-admission.yaml` 做服务端 dry-run 被拒：S5 模板比较处 `expected type 'string' but found 'map(string, dyn)'`、`expected type 'bool' but found 'map(string, string)'` 等类型错误，来自 10-30 的 6a9bf12、f416ea7、25d7b23（`variables.s5`）。线上 `bifrost-platform-pipelinerun` 一直是 e889aa6（10-24）版；B5 改用安装快照 971956d（分支 `install/b5-admission-2026-10-31`：e889aa6 + B5 repo-url 一条规则）装上（#234）。
- **影响**：main 上的准入文件装不上去；S5 启用前必须修；在修好之前，任何人按 main 重装都会在 dry-run 失败（失败即不改，安全）。
- **修法**：把 S5 段里的列表 / map 字面量改成同构（`dyn()` 包裹或逐字段比较），每次改动在集群上做服务端 dry-run；装上后 main 与线上一致，删安装快照分支。
- **防线**：infra CI 的 statics 阶段对 `40-admission.yaml` 做与集群版本一致的 CEL 编译检查，编不过就红。
- **验收**：`git show origin/main:k8s/platform-rbac/40-admission.yaml | kubectl apply --dry-run=server -f -` 通过。

### → R5:5.5-16

#### TD-480（原文，挂到 R5:5.5-16）

**P3 · Console 计划树 · PlanTree 把「边不在 waiting_on」推断成「Milestone verified」**

- **状态**：未开始（2026-11-01；模块详情已在 R5:5.5-3 改，PlanTree 没改）。
- **证据**：`console/src/pages/shell/agents/PlanTree.tsx:20-25`：阻塞边在 `waiting_on` 里找不到就显示 `Milestone verified`。plan-view 没有逐边 / 逐里程碑的「已验证」字段；`moduleDetailModel.tsx:546,562` 已改成 `No wait recorded`。
- **影响**：Whole plan 折叠视图对没有等待记录的边宣称里程碑已验证，可能与事实相反。
- **修法**：PlanTree 用与模块详情相同的说法（`No wait recorded`）；或 plan-view 给出直接字段后再显示「verified」。
- **防线**：PlanTree 测试：边不在 `waiting_on` 时文字不含 `verified`。
- **验收**：测试通过；Whole plan 上没有等待记录的阻塞边显示 `No wait recorded`。

#### TD-483（原文，挂到 R5:5.5-16）

**P3 · Console 指挥页 · Now、Open goals、Crew 卡和页头结论只在报错或离线时作废，不看读数年龄**

- **状态**：未开始（2026-11-01，R5:5.5-4 复核时发现）。
- **证据**：`console/src/pages/shell/owner/useOwnerYours.ts:19-21` `current()` 只在 `isError || isPaused` 时丢掉数据；`useOwnerConsole.ts:131` `runtimeError` 同样只看这两项；`OwnerConsolePage.tsx:31-45` `VerdictBanner` 显示「as of …」但结论的颜色和文字不受读数年龄影响。刷新卡住（请求一直不回、也不报错）时，旧数被当成现状。
- **影响**：Command 页和整页结论可能说「一切正常」而读数已是很久以前的。
- **修法**：在 `current()` 或外壳层统一加读数年龄判定（超过轮询间隔的若干倍就当未读，结论降为 Unknown 并说明多久没读到）；建议单独立项（影响 Command 与整页结论）。
- **防线**：owner 模型单测：`dataUpdatedAt` 超过门槛时卡片与结论都显示未知。
- **验收**：单测通过；在 DEV 上让运行时读挂起 2 分钟，页头结论变为 Unknown。

### → R5:5.6-2

#### TD-464（原文，挂到 R5:5.6-2）

**P3 · handin · 报告过大被拒后 key 绑死，新 key 要等 15 分钟宽限**

- **状态**：未开始（2026-10-30）。
- **证据**：2026-10-30 15:4x S6 quick（`t_01M6796F06X57VF6T36PNFCQWV`）：`handin.sh run` 在 claim 之后上传 13 KB 报告得 HTTP 422；该 key 随即绑定到这份报告（再用同 key 报 `key is bound to a different report`），换新 key 又报 `leased, not ready`，要等旧尝试过 Grace（15 分钟，`api/internal/agentrt/store/kernel.go:44`）。
- **第二例**（2026-11-01，统筹记）：报告里写了家目录形式的本机路径，平台按 H8 拒收（`bifrost-platform` `api/internal/agentrt/store/localpath.go:15-23`：`report` 类工件要扫描，规则与 agentd 共用）。`agent-config/scripts/landing/handin.sh:380-388` 在 claim 之前就把 key 绑定到这份报告的哈希，`:418-419` 在 claim 之后才上传，所以同样卡住：要先删掉本地绑定（`git rev-parse --git-path handin/runs/<binding>.json`）再用同一个 key 重交。修法加一条：claim 之前按平台同一规则查本机路径，命中就拒绝、不 claim。
- **影响**：一次报告超长就白等 15 分钟以上，且要人工判断换 key。
- **修法**：`handin.sh run` 在 claim 之前按 API 给出的上限检查报告大小，超限直接拒绝、不 claim；脚本说明里写明宽限等待。
- **防线**：handin 的 shell 测试：超长报告在 claim 之前失败、不产生任何尝试。
- **验收**：用一份超限报告跑 `handin.sh run`，返回大小错误且平台上没有新尝试。

#### TD-485（原文，挂到 R5:5.6-2）

**P3 · infra handin · propose 不核对 --base 是否存在，错的基点照样建出任务**

- **状态**：未开始（2026-11-01）。
- **证据**：2026-11-01 统筹凭记忆写 infra main 的全 SHA：`handin.sh propose --base e4eaf08b6f30…`（实际是 `e4eaf0816b4d…`），任务 `t_01M6BTX2ST0H58JBJ4V15NYD39` 照建（proposed，`base_commit` 就是错值），统筹 `request_stop` 后重建。`agent-config/scripts/landing/handin.sh:189-224` `cmd_propose` 只要求 `--base` 非空；平台 `api/internal/agentrt/store/propose.go:481-482`、`:490-498` 只查 repo 与 base_commit 有没有填，不查提交在不在。
- **影响**：错基点的任务要到 run 或落地时才失败，白占一次任务和一次停止。
- **修法**：propose 前在 `--repo` 的 Gitea 远端核对 base 存在且是 main 的祖先（`git ls-remote` / `git cat-file -e`，或平台 propose 时校验 base 可达）；不通过就拒并说明。
- **防线**：`test_handin.sh` 加「不存在的 base → 拒绝，平台上没有新任务」用例。
- **验收**：用一个不存在的 SHA 跑 `handin.sh propose`，非 0 退出且平台上没有新任务。

### → R5:5.7-6

#### TD-466（原文，挂到 R5:5.7-6）

**P2 · infra 落地 · 平台侧发现把单词 work 也当信号，平台任何一处新 token 都让 infra 落地整条变红**

- **状态**：未开始（2026-10-30）；修法要 Owner 定。
- **证据**：`scripts/landing/doc_consumers.py:12` 的 S1 含 `["']work["']` 和 `/work/`，`:69` 对平台检出也用 S1。平台 9997c113 有 89 个命中文件，其中 64 个登记为 `token`（JSON 键、路由 id、夹具目录名，与 infra 文档无关）。S5 落地（9997c113）一次就新增 3 个这样的文件（`api/internal/agentrt/rules/s5check/ci_test.go`、`landing_contract_test.go`、`policies/manifest.json`），每一个都会让 infra 落地红在 `unregistered_consumer`，直到 Owner 手推更新登记（登记表在硬底线）。
- **第二例**（2026-11-01，只读 `kubectl -n cicd` 读检查 Pod 日志）：平台 R5:5.5 的 Console 改动一落地，infra 的检查就红在 consumers：`ci-infra-tjhl8`（17:26Z）`unregistered_consumer console/src/pages/shell/agents/planRoundModel.ts:45`（`formatShellHash('work', …)`，S1 的 `["']work["']` 命中路由名）；`ci-infra-djgcv`（18:59Z）`unregistered_consumer …/__tests__/workPage.test.tsx:50`；infra `fb8142e`（11-01 11:33 CST）登记了五个 Console 文件后，`landing-ci-infra-49ddb38d415c3faa5fd8d335-1`（21:04Z）又红在 `consumer_changed console/src/pages/shell/agents/workViewModel.ts`（5.5-2 与 5.5-4 之间命中行变了）；21:30Z 之后转绿。平台自己的落地不跑这项检查，红只在下一次 infra CI 才出现。
- **影响**：平台的日常开发会不断关掉 infra 文档落地，每次都要 Owner 手推一个只为登记 token 的提交，抵消了 S6 让 Owner 不再手推 infra 的目的。
- **修法**（二选一，先问 Owner）：A. 平台侧只认目录信号 `multi-agent|agent-config/work|work/multi`，单独的 `"work"` 与 `/work/` 不再算（平台读 infra 只经三条 Gitea 读取路径，都指向硬底线文件，§12）；B. 规则不变，但平台侧只命中 token 型信号的新增文件降为告警，不变红。推荐 A：规则简单，降级判断不依赖分类。C（2026-11-01 统筹补，可与 A 并用）：平台落地 CI 也按 infra 的登记表跑 discover / verify，红在平台交付时就出现，而不是留给下一次 infra CI。
- **防线**：`scripts/landing/test_doc_policy.py` 加用例：平台新增一行 `"work"` → 绿（A）或告警（B）；平台新增 `agent-config/work/multi-agent/...` 引用 → 仍红 `unregistered_consumer`。
- **验收**：在平台夹具里加一个只含 `"work"` 键的新文件，`doc_consumers.py` 不红；加一个含文档目录路径的新文件，红。

#### TD-490（原文，挂到 R5:5.7-6）

**P2 · 落地 · platform 的落地不查 infra 的文档消费者登记表，下一件 infra 落地才红**

- **状态**：未开始（2026-11-02 夜，R5:5.11-1 落地 CI 红时记）。
- **证据**：infra 的 `scripts/landing/doc_consumers.py:69` 在 infra 的落地 CI 里也扫 platform main（`--platform-revision`），platform 文件只按 S1 字样匹配（`:26`）。platform 自己的落地 CI 不跑这一步。11-02 白天 platform 落了两件（`0865f2c0` R5:5.8-3a、`277363a4` R5:5.5-10），带进四处没登记的消费者：`api/internal/agentrt/migrations/0011_debts.sql:2`、`api/internal/agentrt/rules/debt.go:14`、`api/internal/agentrt/store/debts.go:22` 是注释引用设计文档；`console/src/pages/shell/agents/planModuleModel.tsx:367`、`:433` 是界面文字里的英文名词。当晚 R5:5.11-1（只加一份设计文档）的落地 CI `landing-ci-infra-bcd298e0…` 在 consumers 阶段红：`unregistered_consumer api/internal/agentrt/migrations/0011_debts.sql:2`。之后每一件 infra 落地都会同样红，直到登记行上 main。登记表是硬底线，只能你推。
- **第三例**（2026-11-04）：P-a（platform `749823ef`，11:28 CST 落地）带进 `api/internal/agentthreads/collector_test.go:258`（`"work":"W-765"`，夹具里的工作号）。本机按 infra 的落地检查核对时先发现，那时还没有 infra CI 跑到它。同时核对了排队中的 platform 版本：P-c1 还会带进 `console/src/api/__fixtures__/plan-view-collector.generated.json:26`，P-c2 还会带进 `console/src/api/__tests__/pc2MixedVersions.test.ts:18`。三处都只是单词 `work`（TD-466），一次登记，没等它们落地。已经交上去的 R5:5.7-6 设计稿那件交付先停了，免得落地失败出卡。
- **影响**：platform 一落地，infra 的落地就被挡住，要等你推登记行；挡住的是与之无关的改动；登记表只能在事后补。
- **修法**（架构级，先问你）：A. platform 的落地检查对候选提交跑同一个 `verify`，用 infra main 的登记表，有没登记或指纹变了的消费者就拒，并说清要先登记哪一行；B. infra 的 consumers 阶段对 platform 文件只警告、不拒，由每日巡检出单；C. 维持现状，每次事后补登记。推荐 A：在 platform main 前进之前就挡住，和「先登记、再出现消费者」的设计一致。
- **防线**：platform 落地检查的测试：候选提交加一行带 S1 字样的注释，落地被拒，拒绝原因写明文件和行；登记后放行。
- **验收**：一件 platform 改动带进新的 S1 字样时，它自己的落地被拒；登记后落地，随后一件 infra 文档落地 CI 绿。

#### TD-513（原文，挂到 R5:5.7-6）

**P2 · 发布 · push-main 推 infra 时不跑文档消费者检查和 code-health，也不等 ci-infra，main 红了没人知道**

- **状态**：未开始（2026-11-04 记）。
- **证据**：推 infra 时 push-main 打印「bifrost-trade-infra has no CI of its own; no CI checked」，可每次推 infra main 都会跑 `ci-infra` 流水线。11-03 晚从 80a8a4a 起它在 consumers 段连续失败（`unregistered_consumer k8s/storage/nfs-fast/render.py:96`，TD-444 第 5 步带上 11 个未登记的消费者），约 6 小时没人发现；期间在它之上的 infra 落地（R5:5.5-12 设计稿补充）落地 CI 也失败。consumers 段读的是推送前 main 上的登记表（`scripts/landing/doc_consumers.py` 的 `main`），所以登记行必须比消费者先上 main。
- **再现**（2026-11-04）：R5:5.5-12 S1-5 那一推（0c841a4）push-main 测试 83/83 通过、打印「has no code-health task in CI; not scanned」后推上 main，ci-infra 在 code-health 段失败：`code.duplication.rocket.infra-py 40→42`。新加的测试辅助函数 `world`（`scripts/agent-host/tests/` 又多两份，共 5 份）和 `calls`（`agent-config/scripts/landing/test_handin_sessions.py`，共 4 份）超过「同名定义不超过 3 处」。推之前在本机只对 TD-444 那几推跑过 ci-infra 各段，没对 S1-4、S1-5 的提交跑。改名后回到 40（td/513-dup-names）。
- **影响**：infra main 的 CI 一直红，所有 infra 落地都过不去，而推的人以为是绿的。
- **修法**：push-main 推 infra 之前，和 ci-infra 一样以推送前的 main 作基点、候选作修订跑 `doc_consumers.py --purpose push`；有未登记的消费者就拒推，并提示先单独推登记行（登记行必须比消费者先上 main：检查只信基点的登记表）。基点 main 本身已经不一致时（例如 11-03 晚那 11 个），要有一个写明原因的放行开关，否则修复它的那一推也推不上去。code-health 同理：以推送前的 main 作基点跑 `coverage_infra.py` 的 code-health 比较，指标涨了就拒推。推完像 CI_REPOS 一样等 `ci-infra` 的结果并打印出来。
- **防线**：push-main 的测试：一个提交新加一个带 `rglob(` 的文件，不登记就被拒推。
- **验收**：`bash scripts/release/test_push_main.sh` 通过，新用例在本条修复前失败。
