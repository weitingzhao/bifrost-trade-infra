# LANE-R2 报告

六条 Claim 在各仓库 `origin/main` 的 worktree 上均成立（共享 checkout 落后于 origin，没有在共享 checkout 里改代码）。只推了分支，没有 push main，没有 apply / delete / rollout、PipelineRun、`release.sh stg|prod|dev`、数据库写入，也没有改 `TECH_DEBT.md` / `RATCHETS.md`。按道文件，research 版本号没有 bump（发版时由 Claude Code 定）。

因调用方而留下的路由：**没有**。下面 16 条在 frontend、platform、trade-api、research MCP 里都没有 HTTP 调用方，已删除。digest / weekly-policy / memory distill 没有 HTTP 调用方，但台账的修法是改成启动 Dagster job，所以这三条 HTTP 还在，进程里不再跑引擎。

## TD-120

- Claim：成立。`k8s/orchestration/dagster_instance.yaml` 是第二份实例配置，没有 `run_monitoring`，也没有任何引用。真正挂载的是 `dagster.yaml` 里的 ConfigMap `dagster-instance`（有 `run_monitoring`）。daemon / webserver 镜像是 `<pin>-dagster`，API 是 `<pin>`。`task-deliver-research.yaml` 的 verify 只对 research-api 做 `*:"${WANT}"`，对不上 `-dagster` 后缀
- 改动：
  - bifrost-research · `cursor/r2-research` · `aa5f76b6101b4e0fa245884ce37d89fc0d44a1b9`（与 TD-121 同一提交；分支头 `f798f33079ab173e427f6372856f4ffa2dd5c277`）
  - bifrost-trade-infra · `cursor/r2-infra` · `b7fe79cc4cf8a5bca93efbac8846d0a9e29324e8`
- 防线：`tests/orchestration/test_daemon_manifest.py` 的 `test_k8s_holds_one_dagster_instance_config`、`test_daemon_image_tag_is_the_api_pin_plus_dagster`。infra 侧是 `k8s/cicd/tekton/task-deliver-research.yaml` 的 image-assert：research-api 对上之后，再要求 `dagster-daemon` 的镜像以 `:${WANT}-dagster` 结尾，否则 exit 1。没有改 `pipeline-deliver-research.yaml` / `pipeline-build-research-dagster.yaml`（那是 LANE-R1 TD-95）
- 门禁：research `make lint` → exit 0。`make test` → exit 0，2129 passed，30 skipped（整分支，含后面的 TD-123 / TD-106）。infra 这次只改 Tekton shell，没有 Python 门禁
- 验收：在 `aa5f76b` 上 `PYTHONPATH=src pytest tests/orchestration/test_daemon_manifest.py -q`，预期 4 passed，且 `k8s/orchestration/dagster_instance.yaml` 不存在。在 `b7fe79c` 上 `rg 'WANT}-dagster' k8s/cicd/tekton/task-deliver-research.yaml` 应有命中
- 要 Owner 批：下一次按 pin 跑 deliver-research 时，verify 会失败，直到集群里 `dagster-daemon` 的镜像已经是 `<tag>-dagster`。`orchestration/**` 不在 Argo 里，这条流水线也不滚动它。本道没有 kubectl。需要有人在发版前把 daemon 镜像滚到与 pin 一致的 `-dagster` 标签
- 后续：code-health 预提交打印 research 超过 800 行的文件是 4，基线是 5，并要求把 `scripts/code-health/baselines.env` 的 `OVERSIZED_RESEARCH_BASELINE` 降到 4。本道没有改这个文件（infra 基线可能被别的道同时改）。钩子仍然 exit 0

## TD-121

- Claim：成立（只做 research 这一半）。`research-api`、`research-mcp`、`dagster-webserver`、`dagster-daemon` 四个 Deployment 的 `envFrom` 把整个 `bifrost-research-secrets` 标了 `optional: true`。`secretKeyRef` 上 market-data-write-token / flex-query-write-token 的 `optional: true` 按道文件保留。CronJob / Job 不在这条 Claim 里
- 改动：bifrost-research · `cursor/r2-research` · `aa5f76b6101b4e0fa245884ce37d89fc0d44a1b9`（与 TD-120 同一提交）。没有动 `sync_openai_secret.sh` 和 checksum 注解（LANE-R1）
- 防线：`tests/orchestration/test_daemon_manifest.py` 的 `test_deployments_do_not_mark_the_research_secret_optional`。它检查上述四个 Deployment 的 `envFrom` 名字 `bifrost-research-secrets` 后面不能紧跟 `optional: true`
- 门禁：同上，research `make lint` exit 0，`make test` 2129 passed / 30 skipped
- 验收：`pytest tests/orchestration/test_daemon_manifest.py::test_deployments_do_not_mark_the_research_secret_optional -q` 预期 passed。四个 Deployment 的 `envFrom` 块里不再有整份 Secret 的 `optional: true`
- 要 Owner 批：没有单独动作。k8s 改动留在分支上。LANE-R1 会在同一批 Deployment YAML 上加 checksum 注解，合并时要 rebase
- 后续：无后续

## TD-123

- Claim：成立。台账列出的 19 条里，16 条读/计算路由在 frontend、platform、trade-api、research MCP 中没有 HTTP 调用方，已删除。另外 3 条（digest、weekly-policy、memory distill）也没有 HTTP 调用方；按修法保留为 HTTP，改为 GraphQL `launchRun` 启动对应 Dagster job（`research_daily_digest_job`、`research_weekly_policy_review_job`、`research_memory_distill_job`）。请求体里的 force / dry_run / use_llm / days 被忽略，用调度默认值。失败回 502。`hypothesis/{id}/retire` 的 HTTP 已删；MCP 工具 `research.hypothesis.retire` 调的是 `repo.retire_hypothesis`，不是这条 HTTP，工具还在。没有 bump research 版本
- 改动：bifrost-research · `cursor/r2-research` · `c977c3184d5a4e639b75f1afd340765df057a730`（分支头 `f798f33079ab173e427f6372856f4ffa2dd5c277`）
- 防线：`tests/api/test_retired_routes.py`（`test_retired_routes_are_gone`、`test_their_neighbours_are_served`、`test_api_does_not_import_retired_engine_entries`）。邻居仍在：morning/eod、`POST /research/backtest/settle`、screens retire、假设的 refresh-trajectory，以及改成 launch 的三条。`tests/api/test_dagster_launch.py` 覆盖 GraphQL 成功、Dagster 错误、HTTP 错误。完整的跨仓库 callers manifest 没有做：research CI 没有兄弟仓库，退役表加 AST 禁令是本仓库能守住的防线
- 门禁：research `make lint` → exit 0。`make test` → exit 0，2129 passed，30 skipped。其中 `tests/api/test_retired_routes.py`、`test_dagster_launch.py`、`test_wave4_routes.py`、`test_wave4_compute_owner_auth.py`、`test_research_routes.py`、`test_hypothesis.py`、`test_hypothesis_owner_auth.py`、`test_agents_run_owner_auth.py` 在提交前单独跑过 47 passed
- 验收：`PYTHONPATH=src pytest tests/api/test_retired_routes.py tests/api/test_dagster_launch.py -q` 预期全部通过。`POST /research/agents/digest/run` 在有 research 用户时返回 202，body 里 `job_name` 为 `research_daily_digest_job`
- 要 Owner 批：没有。公开接口变更已在道文件里批准。版本号按道文件留给发版。下一次 research 发版会带上这些路由删除；调用方清单里没有 HTTP 客户端要改。Hermes / 手工 curl 不在 Measured 范围内
- 后续：无后续。删除的 16 条：
  - GET `/analytics/sepa/technical-filter`
  - GET `/analytics/sepa/screening-ranked`
  - GET `/research/sepa/candidates`（`/research/sepa/model/candidates` 仍在）
  - GET `/research/volatility/surface`（`/research/volatility/smile` 仍在）
  - GET `/research/forecast/hourly`
  - GET `/research/forecast/settlement`（`GET /research/backtest/settlement` 仍在）
  - GET `/research/forecast/backtest`
  - GET `/research/backtest/regime-stats`
  - GET `/research/canonical-pnl/coverage`（trajectory / structures 仍在）
  - POST `/research/forecast/terrain/compute`
  - POST `/research/forecast/sessions/compute`
  - POST `/research/forecast/settle`（`POST /research/backtest/settle` 仍在，仍在 API 进程里调用 `settle_forecast`）
  - POST `/research/event-radar/run`
  - POST `/research/events/ingest`
  - POST `/research/backtest/aggregate`
  - POST `/research/hypothesis/{hypothesis_id}/retire`

## TD-106

- Claim：成立。`POST /market/ingest/enqueue-slot` 对 `trim` 是同步跑完才返回；Dagster 的 `market_trim` 把这次 HTTP 当成结束。重试会再开一轮 trim。返回体里本来就有 `retention_archive`
- 改动：
  - bifrost-platform-plugin-market-data · `cursor/r2-md` · 行为在 `0bebcd1cbd8f7a85de025b5aaa80587aab4e328f`，路由的 `response_model=None` 修正在 `d042fed42efa43cd71134b6d09695efff7bdabe3`（分支头 `a68838a4c59ee8a461f0d7990f603b36deffdabc`）
  - bifrost-research · `cursor/r2-research` · `f798f33079ab173e427f6372856f4ffa2dd5c277`（Dagster 这一半）
- 防线：
  - `tests/test_trim_single_flight.py` 的 `test_two_concurrent_starts_run_trim_once`（两次并发只有一次 `run`，第二次 `already_running`）、`test_trim_budgets_finish_inside_the_client_timeout`（`budget_sec + 2×snapshot_budget_sec + 2×60` 的 dated 默认 < 1200）
  - research `tests/orchestration/test_market_trim_poll.py`：`already_running` 轮询同一个 job id；失败让 asset 失败；超过 `TRIM_CLIENT_TIMEOUT_SEC`（1200）则失败。两边 CI 不能互相 import，所以两边都断言这个数是 1200
  - 没有加 `STEP_UP_FOR_RETRY` 告警：single-flight 之后重试 POST 得到 `already_running` 并接着轮询同一行，重试是安全的。告警要 apply 到集群，本道不做
  - 没有改 LANE-D2 的 schema DDL
- 门禁：
  - research `make lint` exit 0；`make test` exit 0，2129 passed，30 skipped
  - market-data `make test` exit 0，1285 passed，9 skipped（见 TD-119 的登录接线修正之后重跑）
  - market-data `make lint` exit 2：ruff 0.16.9 报 788 条，含未改的 `src/bifrost_market_data/worker/loop.py`。这是这版 ruff 对整个仓库的已有红，不是本道新引入的规则违规。本道新文件 `trim_flight.py`、`test_trim_single_flight.py` 单独 ruff 通过
- 验收：`pytest tests/test_trim_single_flight.py tests/orchestration/test_market_trim_poll.py` 分别在两个仓库里预期通过。`POST /market/ingest/enqueue-slot` body `{"slot":"trim"}` 应是 202，`status` 为 `accepted` 或 `already_running`，并带 `job_id`。完整结果（含 `retention_archive`）写在 `ops_jobs.job_ingest` 的 `slot-trim` 行上，状态先 `running` 再 `done`/`failed`。锁是会话级 `pg_try_advisory_lock(hashtext('bifrost.market.trim'))`，由后台线程持有那条 `statement_timeout=1500s` 的连接
- 要 Owner 批：没有集群动作。合并后下一次夜间 `market_trim` 会改成「启动后轮询」，最长等 1200 秒。CLI `scheduler.daily --slot trim` 仍是同步的，不走这把锁
- 后续：无后续

## TD-119

- Claim：成立。`make deploy` 先 `kubectl apply -k k8s/base`（当时 base 含迁移 Job），再 rollout API，最后才 `wait` Job。新进程会在迁移完成前起来
- 改动：bifrost-platform-plugin-market-data · `cursor/r2-md` · Job 拆分在 `9385eee977a32e9fd0f6a40174d23ace2ac4751b`，登录接线测试跟着 Job 走在 `a68838a4c59ee8a461f0d7990f603b36deffdabc`（分支头）
- 防线：`tests/test_schema_migrate_order.py`：`kubectl kustomize k8s/base` 没有 `kind: Job`；`k8s/migrate` 恰好一个 Job 且没有 Deployment；两边 `images.newTag` 都是 `0.85.0`；Makefile 里 `apply -k k8s/migrate`、`wait --for=condition=complete` 出现在 `apply -k k8s/base` 之前。`tests/test_db_login_wiring.py` 同时扫 `k8s/base` 和 `k8s/migrate`，密码仍然配着 user。没有改 wave8 DDL
- 门禁：`make test` exit 0，1285 passed，9 skipped。`make lint` 与 TD-106 同一条已有红（exit 2，788）
- 验收：`pytest tests/test_schema_migrate_order.py -q` 预期 5 passed。`make deploy` 的顺序是：删旧 Job → `apply -k k8s/migrate` → wait complete → logs → `apply -k k8s/base` → rollout api
- 要 Owner 批：没有。本道没有执行 `make deploy`。下次有人部署 market-data 时会按这个顺序跑；迁移 kustomization 的 `newTag` 必须和 base 一起改
- 后续：无后续

## TD-102

- Claim：成立。插件 `GET /market/analytics/max-pain/compute` 与 `/compute/history`、`analytics/max_pain_math.py` 没有运行时调用方。frontend 的 `SymbolDealerHistory.tsx` 和 `researchPipeline.ts` 只在注释里提到 history 路径。`fetch_pcr_aggregate` 打的是插件 `GET /options/analytics/pcr`，SQL 对 `raw_market.option_open_interest` / `option_snapshot` 做 SUM，没有 adjusted-root 谓词。Research `GET /analytics/options/pcr` 读的是已经滤过的 `features.option_metric_pcr_daily`
- 改动：
  - bifrost-platform-plugin-market-data · `cursor/r2-md` · `2e22efed4c20c01339d0703cab6b3495fbba1108`（分支头 `a68838a4c59ee8a461f0d7990f603b36deffdabc`）
  - bifrost-trade-api · `cursor/r2-api` · `7063a8989d14b6be7ad0f71db975a0a01ea78af6`
- 防线：
  - `tests/test_max_pain.py`：`compute_max_pain_curve` 不在插件源码里，两条 compute 路由不在 OpenAPI，`GET /market/analytics/max-pain`（持久化）还在
  - `tests/test_adjusted_contract_aggregates.py`：`api/*.py` 里对 `raw_market.option_(open_interest|snapshot|daily)` 的 SUM / GROUP BY 必须含 `!~ '[0-9]$'`。`coverage.py` 在允许名单里（它统计完整度，不是一条曲线）。PCR 三条和 `chain_by_expiry.py` 两条已加上 `substr(ticker, 3, length(ticker) - 17) !~ '[0-9]$'`
  - `tests/research/test_fetch_pcr_aggregate.py`：Research 行映射成 `{trend:[{trade_date, put_value, call_value, ratio}], latest_ratio, type}`，按日期升序；lookback 夹到 365；404 / Research 不可用返回 `{ok: false, trend: []}`，`source` 为 `research_filtered_pcr`。函数签名没变，trade-api 没有 bump
  - 没有往 `scan.sh` 加跨仓库指标。第二份 `compute_max_pain_curve` 在另一个仓库里不会触发本仓库的重名计数，登记新指标还要改 infra 基线。插件测试「这个函数已不存在」是本道的防线
- 门禁：
  - market-data `make test` exit 0，1285 passed，9 skipped。`make lint` exit 2（同上，788 条已有红）
  - trade-api `make lint` exit 0
  - trade-api `make test` exit 2：收集阶段 11 个错误，都是 `ModuleNotFoundError: bifrost_core.portfolio.reader.keyset` 或 market-ingest 从共享 checkout 的 core 里 import 失败。那是 LANE-T 正在改的共享 core，不是本分支的文件。`pytest tests/research/test_fetch_pcr_aggregate.py` → 3 passed。`tests/test_market_data_client.py` 在排除这些收集错误之后的那一轮里通过
- 验收：`pytest tests/test_max_pain.py tests/test_adjusted_contract_aggregates.py tests/research/test_fetch_pcr_aggregate.py` 预期通过。`fetch_pcr_aggregate("SPY")` 打 Research `GET /analytics/options/pcr`，不再打插件 `/options/analytics/pcr`。插件 PCR 路由还在，给仍直接打它的客户端，SQL 已带 adjusted 谓词
- 要 Owner 批：没有。公开接口变更已批准。research 的 max-pain 计算没有删（那是已经滤过 adjusted 合约的那份）
- 后续：无后续

## 和别的道撞车的文件

- LANE-R1 会给 research 的 `k8s/api/deployment.yaml`、`k8s/mcp/deployment.yaml`、`k8s/orchestration/dagster.yaml` 加 checksum。本道已经在这三份里去掉了 `envFrom` 的 `optional: true`。合并时以两边都保留为准
- 没有改 LANE-R1 的 `pipeline-deliver-research.yaml`、`pipeline-build-research-dagster.yaml`、`sync_openai_secret.sh`
- 没有改 LANE-D2 的 market-data schema DDL
- 没有改 LANE-T 的 trade-api `market_ingest*`。trade-api 全量测试红是共享 checkout 里 core 缺 `keyset`，本道停在那，没有去改 core
