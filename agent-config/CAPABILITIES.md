# 能力目录：我要办一件事，找谁、怎么办、带什么

归工坊（11 Station）。2026-11-24 进仓库（原在共享笔记，Agent 在 mini 上读不到）。按事查：`python3 bifrost-trade-infra/scripts/station/howto.py find <关键词>`。

2026-11-24 v0，由 Station 从章程、身份卡、动作目录、MCP 工具清单、归属表汇编；每条线自己核对后改。
这页回答：系统里每条线能替别人做什么，怎么开口，要带什么。起因：Agent 不知道有什么能力、去哪拿，只好猜；11-23 夜里 06 回集群卡住，就是没人知道算力线能经执行口进集群节点（包括控制面 .73）、能开主机档的卡。
这页只照抄出处，不新定任何能力。【推】= 推断，没在出处里读到原句；【冲突】= 两处出处说法不一致。所有读数是 2026-11-24 读的 `origin/main`：infra `8064271c`，platform `7a017451e`。

缩写（下面的出处一栏用）：
- `infra:` = bifrost-trade-infra，`plat:` = bifrost-platform，都指 origin/main
- `CAT` = `plat:api/internal/actions/catalog.go`（动作 ID 和级别 B/C/D/X）
- `MCP` = `plat:mcp/platform/src/index.ts`（MCP 工具注册的行号）；`MSG` = 同目录 `registerMessages.ts`；`QST` = `registerQuestions.ts`；`PLI` = `registerPlanImport.ts`
- `DOM` = `plat:config/domain-ownership.json`（领域合约）
- `CH/` = `infra:agent-config/charters/`；`CARD/` = `infra:agent-config/charters/cards/`
- `OE` = `infra:agent-config/OWNER_EXEC.md`；`AF` = `infra:agent-config/AGENT_FACTS.md`；`CM` = `infra:agent-config/CLAUDE.md`
- `NOTES/` = 共享笔记目录 `side-session-notes/local_accccb4e…/`

级别怎么读（`CM:96` 起的表、`CAT`）：B 直接调；C、D 建卡，Owner 在 PROD Console（`ops.bifrost.lan`）批；X 提不了（D10）。签名规则覆盖的 C 级发布直接发。

## 0. 席位地址

不在这里抄（抄的会过期）：查 `infra:agent-config/charters/seats.yaml`，按 `id` 找 `session`。发信用 `send_message`，`to` 写 `thread:<会话号>`，或直接写 `roster:<席位 id>`（MCP 发信前按 infra origin/main 的名册换成现任会话，回执里 `resolved_to` 是寄到的会话、`roster_source` 是读的哪一份；`plat:mcp/platform/src/roster.ts`）。`session: null` 的席位空着，没人收信。

下表「归哪条线」一栏只写席位 id。

## 1. 我要办一件事，找谁

### 1a. 机器和集群

| 要办的事 | 归哪条线 | 怎么办 | 要带什么 / 前提 | 出处 |
|---|---|---|---|---|
| 要请一个 Agent 干活，该派到哪台机器、哪个账号、交给谁 | 11-station | `python3 infra:scripts/station/pick.py <claude\|codex\|opencode> [--skip <额度用完的账号>]`：打印账号标签、机器、那台机器上的常驻线程地址 | 额度用完的账号用 --skip 跳过；全跳完就是要 Owner 定账号 | `CH/seats.yaml` 的 accounts 表 |
| 在工坊值守那里问「找谁、怎么办」，或请它在 mini 上照任务书干一件活 | 11-station（mini-01 值守） | `send_message` 到 `thread:01a20bde-35a2-7600-8947-e24375a43229`，任务书放正文或 artifact | 它每封信醒一次，回信 reply_to 你的信 | `CH/seats.yaml` 的 station-desk-mini01 行 |
| 叫醒 4090（gpu-server） | 6-compute | `wake_compute_node`，B 级，直接调（MCP bifrost-platform 或 bifrost-kubernetes） | 节点名 `gpu-server`；它平时关着，NotReady 加封锁是常态 | `CAT:360`、`DOM:483`、`MCP:413`、`AF` 节点表 gpu-server 行 |
| 关 4090 | 6-compute | `poweroff_compute_node`，D 级：先排空再关机，建卡等批 | Owner 醒着；卡写清楚上面跑着什么 | `CAT:354`、`DOM:484`、`MCP:421` |
| 封锁 / 解封节点（cordon / uncordon） | 6-compute | `cordon_node`、`uncordon_node`，**C 级**，建卡 | 【冲突】06 回集群手续的回退一节写「cordon_node（B 级）」，动作目录是 C；以 `CAT` 为准 | `CAT:331,337`、`MCP:336,344`；`NOTES/compute/06-rejoin-runbook.md:58` |
| 排空节点（drain） | 6-compute | `drain_node`，D 级 | 同上 | `CAT:343`、`MCP:352` |
| 加一台节点进集群（重装后入群） | 6-compute 写手续和登记；装系统、取令牌、入群要 Owner 本人 | 按算力线的手续：Owner 在机器前装 Ubuntu；在 MacBook 上跑 `infra:scripts/k3s/fetch-join-token.sh`（要 SSH 到 .73 并输 sudo 密码）；再 `scp` 三个脚本、`ssh` 跑 `join-bifrost-agent.sh`；之后算力线只读核 Ready、建卡打标签、推 ready/ 改 topology 和 home_info | 入群令牌属 Secret，只在 Owner 的 Mac 和新机之间；手机办不了 | `NOTES/compute/06-rejoin-runbook.md:17-55`、`infra:scripts/k3s/fetch-join-token.sh:8-15`、`CARD/6-hw-upgrade.yaml:22` |
| 给节点打标签 | 6-compute | 建 `owner_run_command` 卡，命令写 `kubectl label node …`，执行口能写 Node | 命令原文一字不改；结果读 `get_request` | `NOTES/compute/06-rejoin-runbook.md:44-45`、`OE:28-29` |
| 在某台集群节点上跑一条命令（读盘、看主机状态，包括控制面 ubt-k3s-01 / .73） | 6-compute 用得最多【推】；工具人人可用 | `bash infra:scripts/owner-exec/node-run.sh render --tier device --node <节点> --recipe nvme-smart`（设备只读档）或 `--tier host --node <节点> --cmd '<写死的命令>' --pods-file <该节点存活 Pod 清单>`（主机档 = 节点的 root），把打印出来的整段文字放进 `owner_run_command` 卡 | 节点要 Ready；主机档必须带 `--pods-file`；能用设备档或平台动作就不用主机档；主机档 11-24 已在 .73 真跑通一次（卡 #715，00:57Z，加一行公钥，exit 0）；在 4090（gpu-server）上也跑通过：卡 #721 加 8082 转发、#728 停掉 harness 服务（11-24，exit 0）。4090 要先叫醒到 Ready | `OE:100-128`、`infra:scripts/owner-exec/node-run.sh:10-11,124-132`；.73 是集群节点 `AF` 节点表 ubt-k3s-01 行 |
| 集群管理员级命令（没有现成平台动作） | 5-approvals 管执行口；谁要谁建卡 | `request_action`，`action: owner_run_command`，`params.command` + `params.reason`，卡理由第一段写「批了会发生什么」，带 `rollback`、`work_id`、`requester_thread` | 命令要自带全部内容（执行口没有仓库检出）；只通集群 API、PROD platform-api、DNS；最长 30 分钟；卡上只留输出最后 2048 字节；不打印秘密；Owner 睡了不建 | `OE:13-35`、`CAT:591-593`、`MCP:874` |
| 重启 Deployment | 谁要谁调 | `rollout_restart_deployment`，B 级；`data`、`bifrost-prod`、`bifrost-platform-prod` 是 C | 命名空间、kind、name | `CAT:297-298,98`、`MCP:372` |
| 扩缩 Deployment | 谁要谁建卡 | `scale_deployment`，C 级；给 `daemon` 加副本是 X，提不了 | D10 | `CAT:310-311`、`MCP:386` |
| 删 Pod | 谁要谁调 | `delete_pod`，B 级 | — | `CAT:322`、`MCP:401` |
| 应用一份清单（原来的 kubectl apply） | 5-approvals（actuation 在它的合约里） | 先 `plan_manifest`（B，渲染 git 路径给 plan id），再 `apply_manifest`（按清单里最高的命名空间定级，起点 C） | 清单要在 git 里；不删对象（删走 D 级）；渲染出 daemon 是 X | `CAT:509-521`、`DOM:436-437`、`MCP:798,810` |
| 从 CronJob 起一次 Job | 谁要谁调 | `create_job_from_cronjob`，B 级；PROD 业务命名空间和 `data` 是 C | — | `CAT:529-530`、`MCP:821` |
| 删已结束的 Job / 探针 Pod | 谁要谁调 | `delete_finished_jobs`，B 级 | 给 names 或 label_selector | `CAT:539-540`、`MCP:832` |
| 起一个临时探针 Pod | 谁要谁调 | `run_probe_pod`，B 级；`data` 是 C | 镜像要在白名单里 | `CAT:549-550`、`MCP:850` |
| 建缺的命名空间 | 谁要谁建卡 | `ensure_bifrost_namespaces`，C 级 | 名字要在平台配置的 `bifrost_namespaces` 里 | `CAT:451-452`、`MCP:365` |
| 申请算力、问「这块活放哪、会不会挤业务」 | 6-compute | 按 `compute/resource-request-standard.md` 写申请，不挑机器；发算力线信箱 | 申请写对象、增量、验收条件 | `CH/6-compute.md:26`、`CARD/6-compute.yaml:13,21-23` |
| 看节点老家、疼痛线、库节点上的客人、盘的写延迟 | 6-compute（口径）；读口经 foundation | `GET /api/v1/telemetry/overview?group=compute`；Prometheus `bifrost_node:home_info`、`ALERTS{alertname=~"ComputePain.*"}` | — | `CH/6-compute.md:24-25`、`DOM:459-490` |
| 本机 dev 服务（platform-api、console、trade-ui 等）看状态、重启、读日志 | 6-compute（devsession 包） | MCP bifrost-local：`list_dev_sessions`、`restart_dev_session`、`get_dev_session_logs`；兜底 `bdev` | 不直接 kill 进程 | `DOM` compute 合约 request_response、`CM:122` 起 |

### 1b. 读东西

| 要办的事 | 归哪条线 | 怎么办 | 要带什么 / 前提 | 出处 |
|---|---|---|---|---|
| 读集群（节点、负载） | 0-foundation-decouple（cluster 这栋楼） | MCP `get_cluster_summary`、`get_cluster_nodes`；或 `kubectl --kubeconfig ~/.kube/bifrost-k3s.yaml get …`（路径原样写全，别在脚本里拼，否则 preflight 当成 Owner 凭证拦下） | 只读身份 `bifrost-agent`；exec 只在 research、两个插件命名空间 | `MCP:135,139`、`infra:scripts/station/README.md:16`、`AF` §8c「集群与节点」 |
| 读库 | 0-foundation-decouple【推：底座管库】 | `psql -h 192.168.10.73 -p 30432 -U agent_reader -d <库>`；或 MCP bifrost-postgres（viewer）的 `get_data_freshness`、`get_postgres_backup_status` 等 | 只用 `agent_reader` | `CM:118`、`AF` §8c「入口与 NodePort」数据层行 |
| 查 Prometheus | 8-3-metrics（规则和抓取）；读口在 foundation | MCP bifrost-prometheus：`query_prometheus`、`list_alerts`、`list_targets`；或 `get_telemetry_overview` / `get_telemetry_alerts` / `get_telemetry_targets` | port-forward 只准 `prometheus-kube-prometheus-stack-prometheus-0` | `DOM` foundation commands、`MCP:766,776,783`、`AF` §8c |
| 看系统存档的评估读数（CI 用时、发布成功率、Owner 动手次数等） | 8-3-metrics | `get_evaluation_readings` 或 `GET /api/v1/readings/evaluation?days=1..31&name=` | 只算已结束的芝加哥整天；每个数带 definition、samples、status | `CH/8-3-metrics.md:25`、`MCP:647` |
| 问「这个数是多少、从哪来」「这条告警保护什么、响了几次」 | 8-3-metrics | 发指标线信箱 | — | `CARD/8-3-metrics.yaml:15-17` |
| 查 Trade 各域健康（只读） | 7-payload（占位） | MCP bifrost-trade-api：`get_market_health`、`get_account_health` 等，`trade_mcp_capabilities` | 只读 | `AF` §8b MCP 表、`CH/7-payload.md:14` |
| 查自己是谁、能做什么 | 0-foundation-decouple（identity） | `whoami`；`get_auth_capabilities`；`get_trust_matrix` | — | `MCP:931,118,433`、`infra:docs/AGENT_WORK.md` §2 |
| 查连通性、环境列表 | 0-foundation-decouple | `get_connectivity_matrix`、`list_environments`、`get_ops_context` | — | `MCP:92,110,114` |

### 1c. 沟通

| 要办的事 | 归哪条线 | 怎么办 | 要带什么 / 前提 | 出处 |
|---|---|---|---|---|
| 给别的席位发信（问、求助、交回） | 8-2-comm-desk | `send_message`，`to` 写 `thread:<会话号>` 或 `roster:<席位 id>`，kind 填 `ask`、`help`、`handover` | 对方信箱要登记过（见第 0 节）；不要写共享笔记代替发信 | `MSG:18`、`CH/8-2-comm-desk.md:33`、`CARD/11-station.yaml`（原 9-crew 卡已删）、`infra:docs/AGENT_WORK.md` §2-3 |
| 收信、等信 | 8-2-comm-desk | `wait_for_messages`，读完 `ack_messages`；`read_message` 读一封；门铃 `doorbell.ts --minutes N`（来信就退出，打印发件人、种类、字节数），用 `run_in_background` 起 | — | `MSG:36,47,69`、`CH/8-2-comm-desk.md:33-34` |
| 叫醒一个闲着的会话 | 8-2-comm-desk | 给它发信；它挂着门铃就醒。按事件叫醒：订阅表 `bus/registry/subscriptions/<tenant>.yaml` 一行写交付方式 `wake` 和交给谁 | 对方得挂着门铃；订阅表只决定叫谁，不带授权 | `CH/8-2-comm-desk.md:4,28,34` |
| 等某类事件发生（窗口变了、CI 跑完） | 8-2-comm-desk | `wait_for_event`；或 `GET /api/v1/bus/events`（长轮询 ≤25 秒，游标续读） | — | `MCP:663`、`CH/8-2-comm-desk.md:31` |
| 登记一类新事件 | 8-2-comm-desk（规矩）；事件由各领域自己发 | 在 `bus/registry/<tenant>.yaml` 加一类（只加不改），推 ready/ | 字段改了要升 version | `CH/8-2-comm-desk.md:27,37,48` |
| 回一封「问题信」的判断 | 收信的席位做，格式归 8-2 | 给 `controller` 发 note，正文 `problem_verdict` 格式 | 格式不对算 Not counted | `CH/8-2-comm-desk.md:35` |
| 报自己状态 / 请一个会话停下 | 8-2-comm-desk | `report_status`；`request_stop` | — | `MSG:54`、`MCP:1062` |

### 1d. 找 Owner

| 要办的事 | 归哪条线 | 怎么办 | 要带什么 / 前提 | 出处 |
|---|---|---|---|---|
| 建审批卡让 Owner 批 | 5-approvals | `request_action`；看进度 `get_request`、`wait_for_request`、`list_requests`；撤 `withdraw_request` | 先过 skill `owner-decision-check`；只在 PROD 平台建；Owner 说「去睡了」之后不建；卡怎么写见 skill `owner-exec-cards` | `MCP:874,900,907,918,890`、`CM:231,233`、`CARD/5-approvals.yaml:13` |
| 问 Owner 一个问题 | 5-approvals | `ask_owner`；`wait_for_answer`；`ack_answer`；`withdraw_question` | 回答不是批准，不能转述成「他点头了」 | `QST:20,60,70,77`、`CM` §5「问题的回答不是批准」 |
| 查某个动作是几级 | 5-approvals | `GET /api/v1/actions`（以它为准） | — | `DOM` approvals request_response、`CM:116` 一带 |
| 记一次 Owner 特权使用 | 谁遇上谁记 | `record_privilege_use`，B 级 | 写推了什么、为什么卡住 | `CAT:251`、`MCP:688` |
| 两条线冲突要裁、要改标准规则边界、卡住且一张卡解决不了 | company-coordinator | 发主统筹信箱 | 只这三种事 | `CH/company-coordinator.md:13` |

### 1e. 合入、验证、发布

| 要办的事 | 归哪条线 | 怎么办 | 要带什么 / 前提 | 出处 |
|---|---|---|---|---|
| 把改动合进 infra 或 platform 的 main | 3-4-verify-release-ci | 从最新 origin/main 牵分支，单独一条 `git -C <绝对路径> push origin <40 位提交号>:refs/heads/ready/<名字>`；CI 绿了自动进 main。看结果：`wait_for_pipeline_run`（pipeline `bifrost-land`，revision 填全长提交号） | 四个尾注（缺 Change-Id 会被拒且推的人收不到信）；对齐最新 main；新包要有归属行；先跑 `python3 infra:scripts/station/precheck.py <检出目录>`；查要带什么 `python3 infra:scripts/station/howto.py land` | `infra:scripts/landing/admission.yaml:11-65`、`MCP:301` |
| 把改动合进别的仓库的 main | 3-4-verify-release-ci | `infra:scripts/release/push-main.sh <checkout> [<commit>]` | 窗口开着一律不推；只接受快进 | `CM:226` |
| 我的提交为什么红、哪个测试挂了 | 3-4-verify-release-ci | `get_unit_runs`、`get_commit_evidence` | — | `DOM` verification tasks（`DOM:229` 起）、`MCP:558,509` |
| CI 会给我的改动跑什么 | 3-4-verify-release-ci | `get_unit_scope`、`get_unit_plan`、`get_unit_config` | — | `MCP:542,520,550` |
| 每日全量过没过、覆盖哪些落地 | 3-4-verify-release-ci | `get_full_ci`、`check_full_ci_landings` | — | `MCP:732,739` |
| 让平台补跑一个提交的单元测试 | 3-4-verify-release-ci | `request_unit_evidence`，B 级 | 单元派发关着时拒 | `CAT:192`、`MCP:747` |
| 登记 / 关掉 main 上的已知回归 | 3-4-verify-release-ci | `report_regression`、`mark_regression_fixed`（B）；`list_regressions` | 40 位提交号；影响一行 ≤200 字 | `CAT:209,219`、`MCP:702,712,722` |
| 占 / 放 / 看发布窗口 | 8-2-comm-desk（排队、通知）+ 3-4（其余） | `hold_release_window`、`release_release_window`、`get_release_window`；脚本 `infra:scripts/release/release.sh window`、`release.sh hold --what <repo>` | `who` 用持有者打印的值；窗口开着就等；占窗口带席位名 | `MCP:978,992,971`、`CAT:121,133`、`CM:206-222`、`CH/8-2-comm-desk.md:18` |
| 发 STG（`bifrost-stg`、`bifrost-platform-stg`） | 3-4-verify-release-ci（谁的改动谁发） | `start_pipeline_run`（`bifrost-deliver-stg` / `bifrost-deliver-platform`，B）或 `release.sh stg`；清单改动推 ready/ 后 `gitops_sync_app` | 该提交 `ci-*` Succeeded；先持窗口；发完自己核 | `CM:249`、`CAT:96,103`、`MCP:265` |
| 这个提交能不能上 PROD、为什么不能 | 3-4-verify-release-ci | `check_release_policy` | — | `DOM` delivery tasks（`DOM:283` 起）、`MCP:288` |
| 发 platform PROD | 3-4-verify-release-ci | 持窗口，`start_pipeline_run` `bifrost-deliver-platform-prod`（C 级，签名规则覆盖时直接发；回「approval required」就建卡） | ci 绿；STG 跑的同一提交已核；同仓库没有未结发布单 | `CAT:96`、`CM` §5「platform 的 PROD」 |
| 发 Trade PROD | Owner 批 | `bifrost-deliver-prod` 是 C 级，走 Console 审批单 | 三条前提同上 | `CAT:96`、`CM` §5「走平台审批单的 PROD 发版」 |
| 发 Research | 谁发谁按 skill 走 | skill `research-release`；`bifrost-deliver-research` 是 C 级 | 窗口；先镜像后清单 | `CAT:96`、`infra:agent-config/claude/skills/research-release/SKILL.md` |
| Argo 同步 / 回滚 | 3-4-verify-release-ci | `gitops_sync_app`、`gitops_rollback_app`（B；PROD 应用 C） | — | `CAT:280,287`、`MCP:245,253` |
| 各环境跑的哪个版本、main 上有什么没上 PROD | 3-4-verify-release-ci / 8-2 | `get_delivery_revisions`、`get_release_context`、`get_delivery_run_logs` | — | `DOM` delivery tasks、`MCP:444,454,235` |
| 跑平台库（agentrt）的迁移 | 3-4-verify-release-ci（直跑）；落迁移文件归 foundation | `run_agentrt_migration`（C；只增不删、已在 STG 发过的由签名规则放行直跑） | 跑完核 `/health` 的 `agentrt_schema_applied` | `CAT:201`、`OE:95`、`MCP:757` |

### 1f. 计划、登记、血缘、地图

| 要办的事 | 归哪条线 | 怎么办 | 要带什么 / 前提 | 出处 |
|---|---|---|---|---|
| 看计划 | 1-plan（占位，信箱未登记） | `get_plan`、`get_plan_view` | 计划树不是领活入口 | `MCP:936,943`、`CH/1-plan.md:13`、`infra:docs/AGENT_WORK.md` §1 |
| 改计划、给计划记笔记、导入 | 1-plan | `propose_plan_change`、`post_plan_note`、`propose_plan_import`；签收只有 Owner | 计划变更会给 Owner 发决策卡 | `MCP:1000`、`PLI:13,24`、`CH/1-plan.md:12,19` |
| 登记一件外部工作（让人看得见谁在干什么） | 2-lineage | 先 `put_artifact` 传描述（9 个字段的 JSON），再 `register_external_work`；过程用 `record_external_work_event`（started / heartbeat / submitted…）。派 Codex 时 `dispatch.sh` 自动登记 | 登记不授权、submitted 不等于做完 | `MCP:948,957,1029`、`CH/2-lineage.md:12-13`、`infra:scripts/agent-host/dispatch.sh:2-4` |
| 查一个提交是谁改的、落地没有 | 2-lineage | `get_commit_lineage`；`git log --all --grep='Claude-Session: local_…'`；按 `Change-Id` 判落地，不按标题 | — | `MCP:480`、`CM` §5「提交血缘」、`CARD/2-lineage.yaml:17` |
| 「X 归谁」、新包要加归属行 | 0-2-catalog | `get_owner`（repo、path，可带 domain）或 `GET /api/v1/catalog/owner?repo=&path=`；没主的路径给出可粘贴的那一行 | 和改动放同一个提交 | `infra:scripts/landing/admission.yaml:41-45`、`CH/0-2-catalog.md:21-22` |
| 按事找该用哪个工具 | 0-2-catalog | `find_by_task`（`?task=`）；领域 `self` 指向的 admission.yaml 由它给出去 | 现在只有合入、领活两份自我说明 | `MCP:610`、`infra:scripts/station/README.md:23` |
| 某领域有什么、开放什么、健康吗；图外有什么；某包谁在用 | 0-2-catalog | `get_domain`、`get_domain_status`、`get_catalog_index`、`get_unperceived`、`get_package_users` | 读口不在请求时列集群 | `MCP:602,594,586,566,618`、`CARD/0-2-catalog.yaml:12` |
| 要加表、删表、写事件账本；能不能直接引用别的领域的包 | 0-foundation-decouple | 发底座信箱；新表由提出的领域设计，落迁移在底座；删有数据的走卡 | 加表先看 skill `database-design`；架构级先列选项 | `CARD/0-foundation-decouple.yaml:7,17-19`、`CH/0-foundation-decouple.md:8` |
| 记一次 preflight 拦截 | 0-foundation-decouple【推：拦截记录的生产方】 | `record_guard_block`，B 级（目录里有，MCP 没注册，直接调接口） | rule、session | `CAT:241`、`CARD/8-3-metrics.yaml:23` |

### 1g. Payload、数据

| 要办的事 | 归哪条线 | 怎么办 | 要带什么 / 前提 | 出处 |
|---|---|---|---|---|
| 行情插件诊断、按处方修 | 7-payload（占位） | `market_data_doctor`；`market_data_heal`（B） | — | `MCP:151,161`、`CAT:391` |
| 把 bifrost_prod 克隆到非 prod 库 | 7-payload | `trigger_data_clone`（C）；`get_data_clone_status`；改计划表 `update_data_clone_schedule`（C） | — | `CAT:378,484`、`MCP:195,219` |
| 看数据新鲜度 | 7-payload | `get_data_freshness` | — | `MCP:144`、`DOM` payload 合约 |
| IB 网关软重连 | 7-payload | `ib_reconnect`（B，只发 `reconnect_all`）；`ib_mode`、`ib_maintenance` 是 C | D10：Agent 不写 `ib:operator:cmd` 的其他 op | `CAT:400-413`、`CM` §3 |
| 数据库备份、修 WAL 存储 | 【推】0-foundation-decouple（「Postgres 实例和库的写入」归底座） | `trigger_cnpg_backup`（C）、`repair_cnpg_wal_store`（D）、`get_postgres_backup_status` | 删改即毁 PITR | `CAT:366,372`、`MCP:181,188,174`、`CARD/6-compute.yaml:28` |

### 1h. 人、台面、验收

| 要办的事 | 归哪条线 | 怎么办 | 要带什么 / 前提 | 出处 |
|---|---|---|---|---|
| 新来的 Agent：活从哪来、交到哪 | 11-station | 读 `infra:docs/AGENT_WORK.md`；活由主人席位给 `BRIEF.md`，做完写 `REPORT.md` 发 `reply_to`（kind `handover`） | 任务书头写 `invited_by`、`reply_to` | `infra:scripts/agent-host/admission.yaml:8-27` |
| 派 Codex 干一块活 | 请它的主人席位自己派；工具归 Station | `bash infra:scripts/agent-host/dispatch.sh <带 BRIEF.md 的目录> <计划节点> <任务> <repo> <branch>`；任务书从 `scripts/agent-host/BRIEF.template.md` 起；进门卡自动写成 `AGENTS.md` | 没写 `reply_to` 不起；命令原样写进任务书 | `infra:scripts/agent-host/dispatch.sh:1-25`、`infra:docs/AGENT_WORK.md` §1 |
| 办一件事前查要带什么、会被什么拒 | 11-station | `python3 infra:scripts/station/howto.py [<工具>]`；`precheck.py`；改治理文件时用 `workspace.sh <检出目录>` 拼临时工作区跑一致性检查 | — | `infra:scripts/station/README.md:5-7` |
| 改规矩文字（CLAUDE.md、OWNER_LAW.md、OWNER_EXEC.md、AGENTS.md） | 11-station | 把改后原文发 Station 落；或自己落但要过 `check-governance-consistency.sh` 第 8 节 | Agent 推 agent-config 会被 auto mode 拦，治理改动单独提交 | `CARD/win2-workshop.yaml:12-13`、`infra:scripts/landing/admission.yaml:61-65` |
| 进名册、换坐席的 Agent、交身份卡 | 11-station | 发工坊信箱；名册 `CH/seats.yaml`，对账 `agent-config/scripts/check-seats.py`，卡 `render-card.py <席位>` | 卡一屏以内、六栏 | `CH/11-station.md`（原 9-crew 章程已并入） |
| 问「某席位谁在坐、谁请来的」 | 11-station | 读 `seats.yaml` 或问工坊 | — | `CARD/11-station.yaml`（原 9-crew 卡已删） |
| 一块活做完了，要有人验 | 12-audit | 发 Audit 信箱；结论写在 `NOTES/domains/2-lineage/audit/<日期>-<块>.md`（落点是占位） | 验收人不能是写方案或做活的人；只认系统产的数 | `CH/12-audit.md:25`、`CARD/12-audit.yaml:11,29` |
| 问「某条规则拦过谁、几次」 | 12-audit | 发 Audit 信箱 | — | `CARD/12-audit.yaml:16-18` |
| 没达到，该动哪里（法、Agent、工具）；起草改法 | 1-plan（立法） | 发立法信箱（11-24 起法的原文、墙的单子、改法提议归立法，Audit 只给事实） | 改法一条一次 | `CH/1-plan.md`、`CH/12-audit.md` |
| 改 City / Console 页面、我的系统要进 City | 10-cockpit | 发 Cockpit 信箱；翻译层要交的合约：places、cards、trips、alerts、techTree | 用别的领域的数据只走它的读口；卡上写「推 bifrost-ui main 前先给 Owner 看」（该线有更新的说法以它为准） | `CARD/10-cockpit.yaml:16-17,26`、`CH/10-cockpit.md:125` |
| 存首页城市布局 | 10-cockpit | `PUT /api/v1/home/layout`（动作 `save_home_layout`，B）；写只给 Owner | base_version | `CH/10-cockpit.md:122`、`CAT:262` |

共 80 行。13 个领域每个至少一行；crew、audit、triage 三个只有「发信 + 文件」，没有机器接口。

## 2. 各领域：管什么、口子、能替别人做的事

### foundation（0-foundation-decouple + 0-2-catalog；总线由 8-2 维护）
- 管：底座包（eventlog、actor 等）、agentrt 迁移和 schema、包之间的墙（codeguard、repoguard）、platform 里没人认领的代码；地图线管归属表、总目录、无法感知池。`CARD/0-foundation-decouple.yaml:5-9`、`CH/0-2-catalog.md:6-15`
- 口子：包间函数 `eventlog.Append/InTx/Declare`、`actor.CheckWriter/IdempotentAs/Register*`；地图读口 `/api/v1/catalog/{unperceived,owner,index,status,domain,users}` 和对应 MCP；集群、网络、遥测、审计等读口（`DOM` foundation request_response）。底座线自己说「没有自己的路由和 MCP 工具」（`CH/0-foundation-decouple.md:17`），但 `DOM` 把集群、遥测、目录等读口登在 foundation 名下【冲突：登记表和章程口径不同】。
- 能为别人做的事：答「这个包归谁、能不能直接引用」「加表删表怎么落」；给新包一行归属（`get_owner` 给可粘贴的行）；按事找工具（`find_by_task`）；看领域健康；读集群、读 Prometheus、读审计日志（`get_audit_log`）。

### plan（1-plan，11-23 起是「立法」：法的名录、修法票、闭环、计划树）
- 管：计划树（`agentrt.plan_node` 等）、进展投影。`CH/1-plan.md:5-8`
- 口子：`GET /plan`、`/plan-view`、`/plan-pace`、`/progress`；`POST /plan/proposals`、`notes`、`imports`、`signoff`（签收只 Owner）；MCP `get_plan`、`get_plan_view`、`post_plan_note`、`propose_plan_change`、`propose_plan_import`。`CH/1-plan.md:12-13`
- 能为别人做的事：读计划、收计划变更提议、记笔记。没人值守：信箱未登记，「自己定」「必须答」两栏空着（`CARD/1-plan.yaml:12-15`）。

### lineage（2-lineage，占位，席位空着）
- 管：external-work 登记、线程心跳与在线、提交血缘。`CH/2-lineage.md:6-8`
- 口子：`POST /api/v1/agentrt/external-work`（及 events、GET）、`/agent/threads/heartbeat`、`GET /api/v1/lineage`；MCP `get_commit_lineage`、`register_external_work`、`record_external_work_event`；事件 `git.mirror.settled`、流 `git.main.advanced`。`CH/2-lineage.md:12-13`、`DOM:196` 起
- 能为别人做的事：登记你在干的活（让 Ops 看得见）；答「这个改动落地没」。

### verification（3-4-verify-release-ci）
- 管：CI、合入、证据账、单元计划。`CH/3-4-verify-release-ci.md:7-10`
- 口子：ready/ 合入；MCP `get_unit_runs`、`get_commit_evidence`、`get_unit_scope`、`get_unit_plan`、`get_unit_config`、`get_full_ci`、`check_full_ci_landings`、`request_unit_evidence`、`report_regression`、`mark_regression_fixed`；自我说明 `infra:scripts/landing/admission.yaml`；Ops Work > CI 页。
- 能为别人做的事：把你的改动合进 infra / platform main；答「为什么没进 main」（证据账 `pipeline_seen.refusal`）；给出 CI 红了怎么本地复现（`admission.yaml:91-96`）；补跑单元测试。

### delivery（3-4-verify-release-ci；窗口排队归 8-2）
- 管：STG、PROD 发布，发布窗口，签名规则的判定，发布记录。`DOM:283` 起
- 口子：`check_release_policy`、`start_pipeline_run`、`hold/release/get_release_window`、`get_delivery_revisions`、`get_release_context`、`get_delivery_run_logs`、`gitops_sync_app`、`gitops_rollback_app`、`run_agentrt_migration`、`delete_pipeline_run`、`get_stg_smoke`；脚本 `release.sh`、`push-main.sh`。
- 能为别人做的事：试判一个提交能不能上 PROD；发 STG、发 platform PROD（规则覆盖时）；告诉你各环境跑的哪个版本；跑只增不删的平台迁移。

### approvals（5-approvals）
- 管：审批单、`ask_owner` 问题、执行口（`owner_run_command`）、审批通知、规则批准。`CH/5-approvals.md:6-11`
- 口子：`/approvals/*`、`/questions/*`、`/release-policy`；MCP `request_action`、`get_request`、`list_requests`、`wait_for_request`、`withdraw_request`、`ask_owner`、`wait_for_answer`、`ack_answer`、`withdraw_question`、`get_question`、`list_questions`、`get_trust_matrix`；actuation 动作 `plan_manifest`、`apply_manifest`、`create_job_from_cronjob`、`delete_finished_jobs`、`run_probe_pod`。`DOM:370` 起、`DOM:436-440`
- 能为别人做的事：把要 Owner 批的事送到他手机上，批完由执行口在集群里跑；问他问题；替你在集群里 apply 清单、起 Job、起探针。执行卡退出码 75 =「现在不行、什么都没写」，会自动重排最多 30 分钟（`CH/5-approvals.md:52`）。

### compute（6-compute）
- 管：CPU、内存、GPU、集群外容量与调度；节点老家、借用、收回；Tekton 资源；dev-session；节点硬件读数；topology.yaml。`CARD/6-compute.yaml:5-11`
- 口子：`wake_compute_node`（B）、`poweroff_compute_node`（D）；dev-session 三条路由和三个 MCP 工具；事件 `cluster.node.changed` 等；Prometheus 存储 `bifrost_node:home_info`、ComputePain 告警；读数经 `/api/v1/telemetry/overview?group=compute`；申请格式 `compute/resource-request-standard.md`。`CH/6-compute.md:18-26`
- 能为别人做的事：开关 4090；决定活放哪台、要多少、会不会挤业务；越线时收回 CI 客人；写节点入群手续并做登记；用 node-run 卡进集群节点（包括 .73）读或做事【推：手续里用 `owner_run_command` 打标签，node-run 是通用工具，没写明是算力线的口子】；cordon / uncordon / drain 建卡。

### payload（7-payload，占位，信箱未登记）
- 管：平台接业务应用的包（marketdata、flexquery、research、tradeagent、ibgateway），`config/environments.yaml`、`topology.yaml` 里的租户声明。`CH/7-payload.md:5-9`
- 口子：插件状态读口、`/plugins/*/api/*` 代理、`watchlist/union`、数据克隆、数据新鲜度；动作 `trigger_data_clone`、`ib_reconnect`、`ib_mode`、`ib_maintenance`、`ib_self_heal`、`market_data_heal`、`market_data_delete`、`update_data_clone_schedule`。`DOM:493` 起、`DOM:531-537`
- 能为别人做的事：查 Trade / 插件健康；诊断并修行情插件；克隆 prod 库到非 prod；IB 软重连。没人值守。

### coordination（8-2-comm-desk 沟通线、8-3-metrics 指标线、8-1 值班由主统筹兼）
- 管：总线、事件、信箱、叫醒、窗口排队（8-2）；Prometheus 抓取、告警规则、评估读口（8-3）。`CH/8-2-comm-desk.md:13-19`、`CH/8-3-metrics.md:15-19`
- 口子：事件登记表、订阅表、CloudEvents 信封、`/bus/*` 读口、MCP `send_message`、`wait_for_messages`、`read_message`、`ack_messages`、`report_status`、`request_stop`、`wait_for_event`、窗口三件；门铃；`GET /api/v1/readings/evaluation`、记录规则 `bifrost_metrics:*`、告警规则。`CH/8-2-comm-desk.md:25-35`、`CH/8-3-metrics.md:23-27`
- 能为别人做的事：送信、叫醒别的会话；答「这件事在总线上有没有、为什么没送到」；登记新事件；告诉你一个数是多少、从哪来、哪天的窗口；加告警规则。

### station（11-station，工坊；11-24 和 Crew 合并）
- 管：Agent 这个员工的一切：名册 `seats.yaml`、身份卡、账号表（`seats.yaml` 的 `accounts`）、住处（两台 Mac mini）、外壳（Claude、Codex、OpenCode）；规矩文字、法和文字对得上的检查、Codex 席位配置和钩子、派活脚本、任务书和交单模板、身份卡递送、办事指南。`CARD/win2-workshop.yaml:5-10`
- 口子：`AGENTS.md → CLAUDE.md → 章程和身份卡` 的进门路；`docs/AGENT_WORK.md`；`scripts/agent-host/dispatch.sh`、`BRIEF.template.md`、`codex-card.py`；`scripts/station/howto.py`、`precheck.py`、`workspace.sh`；格式 `station.requires/v1`；自我说明 `scripts/agent-host/admission.yaml`；信箱。`DOM:591` 合约为空。
- 能为别人做的事：把你或你请来的临时 Agent 记进名册；答谁坐哪个席位、用哪个账号；在 mini 上起一个 Agent 接你的活（工坊有两台 mini 的 SSH）；告诉新来的人从哪进、活从哪来、交到哪；派 Codex；查办一件事要带什么、会被什么拒；替别的线落规矩文字；派活脚本或钩子坏了修。

### audit（12-audit；11-23 起 Triage 并入）
- 管：做完的活对着完成标准验一次；每条拦过人的规则的记数；特权三数。`CARD/12-audit.yaml:5-9`
- 口子：结论文件（占位落点）；读 `get_evaluation_readings`、`get_commit_lineage`。`CH/12-audit.md:25-26`。`DOM:598` 合约为空。
- 能为别人做的事：验你的活（只给 达到 / 部分 / 没达到 / 没核，不开药方）；答某条规则拦过谁几次。

### 不是领域、但常被找的
- company-coordinator（主统筹）：裁两条线冲突、改标准规则边界、一张卡解决不了的卡住。`CH/company-coordinator.md:13`
- 10-cockpit：City / Console 表现层、`/api/v1/home/layout`、UI 引擎（bifrost-ui `src/city`）。`CARD/10-cockpit.yaml:5-8`

## 3. 已知的坑 / 只有某台机器、某个人能做

- **执行口（owner-exec）够得着哪里**：命令跑在集群里一个 Pod，网络只通集群 API、PROD platform-api、DNS；`git clone`、外网、Gitea、数据库都不通；不能写三个 Trade 命名空间、名叫 `daemon` 的 Deployment、`redis-ib`、IB 网关。`OE:28-46`
- **node-run 够得着哪里**：只到集群节点（经 Pod 钉在节点上）。ubt-k3s-01（.73，唯一的控制面）是集群节点，所以【推】主机档能在 .73 上以 root 跑命令。集群外的机器（Mac mini .50/.52、NAS、ubt-k3s-06）够不着。主机档 11-24 已在 .73 真跑通一次（卡 #715，exit 0），所以「主机档能进 .73」不再是推断；设备档只在 05 上跑过一次（卡 #602）。`OE:127-128`、`AF` 节点表
- **SSH 钥匙谁有**：出处里只写到两件。06 回集群手续要求「导入 MacBook 的公钥」，所有 ssh / scp 都由 Owner 在 MacBook 上跑（`NOTES/compute/06-rejoin-runbook.md:20-38`）；取入群令牌的脚本 SSH 到 `vision@192.168.10.73` 并要输 sudo 密码（`infra:scripts/k3s/fetch-join-token.sh:8-15`）。11-24 起工坊能 SSH 进两台 Mac mini（用户 `vision`，钥匙在工坊所在的 Mac Pro 上）；06 已回集群，走 node-run；4090 的系统层走算力线的主机档卡。哪台机器的哪把钥匙能进哪台主机，没有任何出处列全。
- **入群令牌**：属 Secret，只在 Owner 的 Mac 和新机之间（`CARD/6-hw-upgrade.yaml:22`）。重装系统要人在机器前（手续第 1 步写明手机办不了）。
- **集群外机器上执行**：动作目录写着 `owner_run_command` 可以带 `runner: host` 和 `host`（如 `mac-pro`、`mini-1`），由那台机器自己的执行器认领，要 Owner 的一次性码换来的 ticket（`CAT:593`、`plat:api/internal/actions/runner.go:17`）。但 `OE:89` 写「在 Mac 上执行的那一种还没做（TD-578）」。【冲突】代码里有这个参数，文档说没做；哪台机器真装了执行器，出处没写。
- **只有 Owner 回电脑才能做的**（全仓库唯一清单，`OE:84-98`）：集群或 Console 自己挂了；命令要用他 Mac 上的文件、凭据或集群够不着的机器；解冻 `release.sh unfreeze`；重放验证器钥匙 `enroll.sh`；交易相关的一切；一次性库步骤；装进集群的自举清单；应用 auto mode 规则。另外：节点重装、入群令牌（上一条）。
- **六类始终是 Owner 的**：交易和钱、口令和 Secret、有数据的删改、Trade 的 PROD 发布、改签名规则和信任根、auto mode 规则（`CM` §5「放行规则只省复制到终端」）。
- **Owner 睡着时不建卡、不问问题**（`CM:233`）；人批的单只在 PROD 平台建（`CM:231`）。
- **preflight 只看命令原文**：推 ready/ 不能先 `cd`、不能写 `HEAD` 或变量；kubeconfig 路径别在脚本里拼；`git add -A` 被拦（`infra:scripts/station/README.md:13-17`）。
- **没有尾注的提交没人收得到拒信**，要自己 `wait_for_pipeline_run` 等（`infra:scripts/landing/admission.yaml:11`）。
- **信箱未登记的席位发不进**：1-plan、7-payload（`CH/seats.yaml:23,28`）。
- **cordon_node 级别对不上**：手续写 B，动作目录是 C（第 1a 节）。
- **章程里提到、MCP 里已没有的工具名**：`record_release_review`（`CH/3-4-verify-release-ci.md:14`）、`request_owner`（`CH/5-approvals.md:17`）在 platform main 的 MCP 注册里查不到。`record_guard_block`、`save_home_layout`、`record_acceptance_reading` 在动作目录里有，但没注册成 MCP 工具，要直接调接口。

## 4. 空白（没有出处说怎么办，等各线补）

1. **集群外主机（Mac mini .50/.52、ubt-k3s-06、NAS、4090 的系统层）上跑命令**：执行口和 node-run 都够不着；`runner: host` 文档说没做；SSH 谁能进哪台没有表。06 回集群这次只能等 Owner 在 MacBook 上做。→ 6-compute、5-approvals、Station
2. **SSH 钥匙和登录面的清单**：哪台机器、哪把钥匙、能进哪台主机、用什么用户，没有一处写全。→ 6-compute（节点）、Station（Agent 主机）
3. **节点入群的免人手路径**：取令牌、装系统、join 全靠 Owner；有没有可能用主机档在 .73 上读令牌、能不能这样做（令牌是 Secret，属六类），没人判过。→ 6-compute 提，Owner 定
4. **四个领域合约为空**：crew、station、audit、triage 在 `DOM:584-610` 都是 `{}`；只有 Station 写了一份自我说明（领活），合入那份 verification 和 delivery 共用。发布窗口、建卡、发信三份自我说明还没写（`infra:scripts/station/README.md:40`）。→ 各线
5. **占位领域没人值守**：7-payload 信箱没登记（1-plan 11-23 起是立法线，有人值守）、「自己定」「必须答」空着；2-lineage 席位空着。要用计划、插件、租户接入时找不到人答。→ 主统筹定先后
6. **Trade 和 Research 的业务改动找谁**：名册里没有 Trade 五仓、Research 的席位；章程只覆盖 Ops 一侧。→ 主统筹
7. **数据库备份、CNPG、UniFi 网络动作归谁**：`trigger_cnpg_backup`、`repair_cnpg_wal_store`、`sweep_failed_backups`、`unifi_*`、`ensure_metrics_server`、`sync_kubeconfig` 等在动作目录里，但归属表的合约没把它们登在任何领域下（只有 `unifi_firewall_apply` 在 foundation）。→ 地图线、Foundation
8. **preflight.js 归谁**：Crew 和 Foundation 的卡都说不是自己的、待裁（`CH/11-station.md`（原 9-crew 章程已并入）、`CARD/0-foundation-decouple.yaml:24`）。被它误拦时该找谁没有定。→ 主统筹
9. **4090 的 harness、agent-06 当执行机**：算力线说缺；装到 06 属阶段 B 现在不做（`CH/6-compute.md:61,74`）；06 已决定格式化回集群，Agent 主机这块谁收尾只在手续第 7 步一句话。→ 6-compute、Station
10. **叫醒没挂门铃的会话**（8-2 已补，2026-11-25）：平台信箱只留底，叫醒要对方挂着门铃。没挂门铃的 Claude 会话，用 harness 的会话消息直接发给它的 `local_…` 会话号（Claude Desktop 里的 SendMessage），会开启它的一个回合；回执写 delivered 和「turn has started」。Codex 坐席发给它在 Claude 一侧的联络会话。会话消息不留在平台的事件账里，要留底的话，同一件事再发一封平台信。席位空着（`session: null`）的，两种都叫不醒，找主统筹。→ 8-2-comm-desk
11. **谁把 submitted 变成做完、计划步怎么认领**：1 号计划没定（`infra:docs/AGENT_WORK.md` §4）。→ 1-plan
12. **算力线的口子里没写「能开 node-run 主机档的卡」**：这次卡住的那件能力，章程和身份卡都没列，只在 `OE` 里当通用工具写。→ 6-compute 核对后补进 §2
