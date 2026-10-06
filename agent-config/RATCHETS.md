# Bifrost 防线登记（棘轮）

> 债还完之后真正留下来的是防线：让同一类问题不能再回来的机械检查（测试、CI、code-health 指标、preflight 规则、告警、数据库约束）。
> **规则**：每关掉 `TECH_DEBT.md` 里的一项，要么在这里加一条（或扩大已有一条的范围），要么在提交信息里写明为什么没有可行的防线。删掉或放宽一条防线要写理由。
> 强度：blocking＝不过就不能提交/发布；warning＝报出来但不拦；alert＝运行时告警；manual＝要人手跑。

更新：2026-10-06（第 2 轮扫描的防线盘点）

## 现有防线

| 防线 | 位置 | 挡什么 | 强度 | 范围与缺口 |
|---|---|---|---|---|
| preflight.js D10 闸门（ib:operator:cmd 写、monitor /control/* POST、daemon scale>0、guard 文件删除/Edit、MCP scale_deployment daemon） | `bifrost-trade-infra/agent-config/scripts/agent-guard/preflight.js（d10Rules / d10FileRule / d10McpRule）；挂在 agent-config/claude/settings.json PreToolUse matcher Bash/Edit/Write/MultiEdit/NotebookEdit 与 mcp__.*` | Agent 发出的实盘武装动作；运行时读 spine D10，fail-closed | blocking | 只管 Agent 工具调用（Claude/Cursor），且只认得 curl 的 -X/-d 写法、rm/mv/truncate 删 guard 文件。实测（MEASURED，本地把样例字符串喂给 preflight.js）：`sed -i … daemon-scale-zero.patch.yaml`、`python3 -c requests.post('…/api/monitor/control/arm')`、`wget --post-data … /control/arm` 三个都返回 ALLOW。人和 CI 不经过它 |
| preflight.js 共享工作树规则 + dev-services 规则 | `bifrost-trade-infra/agent-config/scripts/agent-guard/preflight.js sharedWorktreeRules / devServiceRules` | git add -A/-u/. 与 git commit -a 把别的会话的在制品卷进提交；裸跑 run_platform.py、kill bdev 托管服务、手动 port-forward 9090 | blocking | 只管 Agent 的 Bash 调用；git stash 不在内 |
| agent-guard 回归测试 test.js（42 例） | `bifrost-trade-infra/agent-config/scripts/agent-guard/test.js` | preflight 规则回退（误放 / 误拦） | manual | 没有 CI 跑它（infra repo 没有 CI trigger）；只靠 auto-mode 允许列表里的 `node scripts/agent-guard/test.js` 手动跑。MEASURED：在干净 worktree 上 42/42 通过 |
| check-agent-config-parity.sh（Cursor ↔ Claude parity-id） | `bifrost-trade-infra/agent-config/scripts/check-agent-config-parity.sh；Makefile check-agent-parity` | 两套规则之间漂移 | manual | 只在工作区根能跑（在干净 worktree 里报“找不到工作区根”）；不在 CI 里 |
| code-health scan.sh + baselines.env（重复函数名、超 800/500 行文件、无 schema 的 FE api 模块、平铺页面文件、research 镜像档数） | `bifrost-trade-infra/agent-config/scripts/code-health/scan.sh；Tekton task k8s/cicd/tekton/task-code-health.yaml` | 结构性腐化：同一概念的复制粘贴、巨型文件、FE 契约覆盖倒退、research 组件钉在旧版本 | warning | CI 只对 frontend、platform、research、trade-api/core/worker 跑（pipeline-ci-python.yaml 的 when 子句，外加 ci-frontend / ci-platform）。三个插件 repo 和 infra 有基线，但没有任何 CI 或 hook 跑它们。MEASURED（在 origin/main worktree 上跑 scan.sh）：market-data 重复函数 6/4、超大文件 11/5；infra 重复 shell 函数 4/3、超大文件 5/3，全部 OVER 而无人发现。只按名字计重复，换了名字的副本（TD-42 的 BS 三份）抓不到。CI 是 push 后跑，红了也不挡发布 |
| pre-commit hook：frontend .husky/pre-commit（check:legacy-css + check:code-health）、research .githooks/pre-commit（scan.sh） | `bifrost-trade-frontend/.husky/pre-commit；bifrost-research/.githooks/pre-commit` | 本地提交就把 code-health / legacy CSS 推过基线 | blocking | 每个 clone 要手动 opt-in（research 要 make install-hooks；husky 在新 worktree 不执行）；FE hook 不跑 vitest |
| check-legacy-css.sh（RAW_PNL_PALETTE 等基线） | `bifrost-trade-frontend/scripts/check-legacy-css.sh；ci-frontend lint-build 步骤` | 旧 CSS / 原始 PnL 色重新出现 | warning | CI 里写成 `// { echo WARN … }`（pipeline-ci-frontend.yaml，“Legacy CSS check”），不会挡；能挡的只有 pre-commit。MEASURED：当前 OK |
| FE 守卫测试：directFetchRatchet、failureContract、researchFailureContract、deadLinks、routeRegistry、contractKey 等 | `bifrost-trade-frontend/src/lib/directFetchRatchet.test.ts（BASELINE = 7）；src/api/failureContract.test.ts；src/layout/deadLinks.test.ts；src/layout/routeRegistry.test.ts` | 绕开共享 HTTP 客户端的 fetch（TD-50）、读不到失败信息（TD-16）、死链 / 退役路由回流（TD-60）、contract_key 格式漂移（TD-25） | manual | ci-frontend 只跑 `npm run lint`（非阻塞）和 `npm run build`，不跑 vitest；pre-commit 也不跑。这些棘轮只有 Agent 自检跑 test:run 时才生效。MEASURED：在 origin/main 导出副本上 523 个文件 / 3991 例全过，所以现在是绿的，只是没有强制 |
| FE eslint | `ci-frontend：`npm run lint // { echo "WARN: lint found issues (non-blocking for now)" }`` | lint 类回退 | warning | MEASURED：0 error / 65 warning，改成阻塞没有成本 |
| ci-python lint-test（ruff + pytest -m 'not ib and not db' + dbt 目录的 sqlfluff） | `bifrost-trade-infra/k8s/cicd/tekton/pipeline-ci-python.yaml；trigger-trade-ci.yaml 只对 core/api/worker/research 的 push 触发` | Python 回退；research 的 SQL 风格 | warning | push 到 main 之后才跑；release.sh 和 deliver pipeline 都不查 CI 结果，Tekton 指标也没被抓取（`tekton_pipelines_controller_pipelinerun*` 查询结果为空）。MEASURED：trade-api 在 main 头 0784017 上的 CI ci-python-bifrost-trade-api-j5d4v（10-04 14:53Z）失败，失败用例是 `FAILED tests/research/test_bs_core_switch.py::test_core_reproduces_the_recorded_research_math`。7 天保留窗口内 trade-api 共 28 次运行，14 次失败。按 expected.d/2026-10-04j-td-batch.allow，同一批 api 0.9.0 照常发布了（这一点是 CODE-READ） |
| core db-test：在 postgres sidecar 上跑 pytest -m db（含 test_brokerage_view_grants_db.py） | `pipeline-ci-python.yaml task db-test（只对 bifrost-trade-core）；bifrost-trade-core/tests/test_brokerage_view_grants_db.py` | db-init 重建 raw_broker 视图时丢掉不是它授的权限（TD-86）；DDL 回退 | warning | 只覆盖 raw_broker 的视图（saved_view_grants）。market.* 和 public.v_us_equity_universe 每次 db-init 也是 DROP 再重建（brokerage_ddl.py:630、:664；ddl.py:575），现在靠 bifrost/postgres 的 default ACL 兜住 trade_app_<env>。MEASURED：pg_default_acl 里有 trade_app_prod 在 market 上的 r 权限。没有测试守这条 |
| trade-api 路由与信封守卫：test_retired_routes、route_listing、test_account_serves_every_domain_router、test_envelopes / *_envelopes、test_write_guard、test_core_alias_imports、test_query_vocab、test_naming_alignment、test_naming_r4、test_deprecations、contract/*_parity | `bifrost-trade-api/tests/（origin/main）` | 退役路由复活（TD-40/64）、未部署的 app factory（TD-29）、200 {ok:false} 失败信封（TD-16/17）、未鉴权的写（TD-23）、core 别名导入（TD-80）、查询词表 / 命名漂移（TD-51/57/26） | warning | 在 ci-python 里跑，但只在 push 之后，也不挡发布（见上一条） |
| core 守卫测试：test_downstream_imports、test_import_fanout、test_golden_black_scholes、test_golden_contract_key、test_ddl_no_readiness_tables、test_execution_view_columns、test_ddl_schema | `bifrost-trade-core/tests/` | 跨 repo 接口导入下划线私有名（TD-20）、DDL↔reader 导入环（TD-47）、BS / contract_key 分叉（TD-42/25）、退役表复活 | warning | 在 ci-python 里跑，push 之后才跑 |
| research test_sargable_symbol_predicates（禁止谓词位置出现 UPPER(TRIM)）+ test_schema_names + test_copilot_writes | `bifrost-research/tests/test_sargable_symbol_predicates.py、test_schema_names.py、test_copilot_writes.py` | 破坏索引的 symbol 谓词；schema 名漂移；Copilot 写工具的范围 | warning | 只扫 Python 源码；DATE(timezone()) 这一类没覆盖（memory 有记） |
| platform CI：go test + console tsc + check_spine_catalog.sh + code-health | `bifrost-trade-infra/k8s/cicd/tekton/pipeline-ci-platform.yaml；bifrost-platform/scripts/ci/check_spine_catalog.sh` | Go 回退、类型错误、spine 与 catalog 漂移 | warning | 不跑 console 的 vitest；不比对 bifrost-trade-infra/k8s/overlays/platform-{stg,prod}/config/ops-context.yaml 这两份部署副本 |
| check_overlay_configs.py（listen 端口、daemon_scale_guard: freeze、platform_audit、reference_indices、重复键） | `bifrost-trade-infra/scripts/check_overlay_configs.py；Makefile check-overlay-configs` | overlay 配置丢键（TD-06/05/53）以及 D10 freeze 标志被去掉 | manual | 只有 Makefile 入口：没有 CI，release.sh 也不调它。MEASURED：dev/stg/prod 当前 ok |
| check_trade_gateway_routes.py（每个进程一个前缀、strip 恰好是自己的前缀、RETIRED 里的别名不得回来） | `bifrost-trade-infra/scripts/check_trade_gateway_routes.py；Makefile check-trade-gateway-routes` | 别名前缀复活：这正是 TD-07 绕过 D10 正则的那条路，也是 TD-55 | manual | 只有 Makefile 入口：没有 CI，不在 release.sh 里。MEASURED：三个 env 都 ok（各 4 个前缀） |
| check_entrypoint_paths.py | `bifrost-trade-infra/scripts/check_entrypoint_paths.py；Makefile check-entrypoint-paths` | Job / 部署指向不存在的脚本路径（db-init 08-24→09-26 那类） | manual | Makefile 入口 |
| release.sh：发布窗口锁、2 分钟内 deliver 去重、PROD 只能钉一个 release-check 通过的 STG run、未执行的 db-steps 拦住发布 | `bifrost-trade-infra/scripts/release/release.sh` | 两个会话同时发布（09-27 / 09-28）；PROD 拿未验证的 STG 构建；跳过 Owner 的 DB 步骤 | blocking | 只管 Trade 走 release.sh 的发布；不查 CI 是否绿，也不跑 overlay / gateway 检查 |
| release-check.sh before/after 快照 diff + probes.json + expected.d/*.allow | `bifrost-trade-infra/scripts/release/release-check.sh、release_checks.py、probes.json、expected.d/` | 发布前后 API 出现意料之外的形状变化；/health 的 core_sha 对不上；每个进程一个前缀的探针（TD-55） | blocking | 只检查 Trade 网关；Research 和插件不在内 |
| loki_gate.py / naming_r4_gate.py（删兼容名之前要求零命中） | `bifrost-trade-infra/scripts/release/loki_gate.py、naming_r4_gate.py` | 在调用方还在用的时候删掉旧名 / 路由（半截改名的反方向） | manual | 每个计划一次性使用，Owner / Agent 手动跑 |
| tag_core_release.sh | `bifrost-trade-infra/scripts/release/tag_core_release.sh` | core 的 tag 标到没上 PROD 的提交（TD-37） | manual | 发布手册的一步 |
| Prometheus 告警：bifrost-trade / infrastructure / flex-ingest / market-data / platform-plugins / logging / gateway（Traefik 404/503）/ postgres 备份 / WAL / 容量 | `bifrost-trade-infra/k8s/monitoring/bifrost-alerting-rules.yaml` | 运行时静默失败：Flex 漏跑或数据陈旧、doctor 陈旧、插件不可达、路由 404 / 空后端 503、备份缺失 | alert | BifrostAPIHighErrorRate 只匹配 `namespace=~"bifrost-.*"` 的 http_requests_total。MEASURED：这个指标只存在于 bifrost-dev/stg/prod，research-api 和插件的 5xx 不会触发任何错误率告警。CI 失败也没有告警 |
| Dagster run_failure_sensor → BifrostDagsterRunFailed | `bifrost-research/src/bifrost_research/orchestration/failure_alerts.py` | Research 定时作业静默失败 | alert | 只报 FAILURE 状态；“成功但写了 0 行”看不见。MEASURED：7 天 539 次 SUCCESS、1 次 FAILURE（research_memory_distill_job，即 TD-86） |
| auto-mode 分类器规则 + release-permissions 放行规则 | `bifrost-trade-infra/agent-config/claude/auto-mode/project.autoMode.json（由 Owner 应用到 ~/.claude/settings.json）` | Agent 越权（PROD DDL、force push、动 guard）；放行已批准的发布步骤 | blocking | 只管 Claude 会话，由 LLM 分类器判断而不是确定性规则；生效与否以 `claude auto-mode config` 为准 |
| permissions.deny：禁止 Edit/Write 已归档的 bifrost-analytics | `bifrost-trade-infra/agent-config/claude/settings.json` | 改动已归档的 repo | blocking | 只管 Claude |

## 各类债现在挡没挡住

| 债的类别 | 挡住了吗 | 靠什么 | 缺口怎么补 |
|---|---|---|---|
| Failure-as-success（读失败变成 200 空列表、{ok:false} 200、保存报成功却什么都没存）：TD-08/16/27/61/83 | partial | trade-api 的 test_envelopes / test_*_envelopes / test_research_failures / contract/test_strategy_list_read_failure（在 CI 里，但 push 之后才跑、不挡发布）；FE 的 failureContract.test.ts、researchFailureContract.test.ts、directFetchRatchet.test.ts（BASELINE 7）不在任何 CI 里；运行时有 BifrostDagsterRunFailed，以及只看 bifrost-* namespace 的 5xx 告警 | (1) ci-frontend 加阻塞的 `npm run test:run`（MEASURED：origin/main 上 3991 例全绿，可以直接开）；(2) release.sh 在 stg 之前查要发的 SHA 对应的 ci-* PipelineRun 必须 Succeeded，不是就 refuse；(3) 告警 BifrostAPIHighErrorRate 去掉 namespace 限制，或给 research / plugin-* 加同类规则（MEASURED：research 和插件没有 http_requests_total）；(4) 插件 / research 的“成功但写了 0 行”加行数断言或 freshness 告警（按表） |
| 别名前缀 / D10 guard 绕过（TD-07、TD-55） | partial | preflight.js 按路径尾部匹配 /control/*（Agent 侧阻塞，test.js 42 例）；check_trade_gateway_routes.py 断言别名前缀不得回来（手动）；probes.json 每个进程一个前缀 | (1) 给 bifrost-trade-infra 建 ci-infra pipeline（trigger-trade-ci.yaml 加 infra），阻塞运行 node agent-guard/test.js、check_trade_gateway_routes.py、check_overlay_configs.py、scan.sh --repo bifrost-trade-infra；(2) preflight 的 D10 规则补上非 curl 的写法：requests/httpx 的 .post/.put/.delete、wget --post-data、sed -i / tee / cp 写 guard 文件、kubectl patch/edit/apply 改 daemon replicas（MEASURED：前三种现在都放行）。每种绕过写法在 test.js 里补一条 DENY 用例 |
| 半截改名（TD-13/19/26/75/81/82；按标签当键的表静默失配） | partial | trade-api 的 test_naming_alignment、test_naming_r4、test_query_vocab、test_deprecations；release 前跑 naming_r4_gate.py / loki_gate.py 零命中门（手动）；release-check 的 diff 必须配 expected.d/*.allow | FE 加一条 vitest：从真实 NAV_GROUPS / route registry 派生键，断言 LIFECYCLE / NAV_ORDERS 这类按标签当键的表覆盖了每个标签（memory「改名会弄坏按名字查的表」）；然后把 vitest 接进 CI（见上）。改名计划的 gate 用 loki_gate 之后，把被删的名字写进 test_retired_routes 的 RETIRED 列表，防止回来 |
| 把共享 Golden Source 当成按环境分开的存储（TD-09、TD-74） | no | 没有机械检查。TD-09 / TD-74 是改代码修的，没有约束或测试阻止下一张 GS 表带上 env 维度的 id，或者存三份 per-env 副本 | GS 的 schema 测试（core 的 db-test 或 research 的 test_schema_names）：GS 表上出现 env / environment 列或 *_env 后缀就失败，除非在白名单里写明理由；database-design skill 写一条规则，DDL 审查时 grep |
| 配置两个来源 / 部署副本漂移（TD-06/52/53/54/69） | partial | check_overlay_configs.py（手动，当前 ok）；TD-52 环境身份在 /health 由 release-check 验证 | MEASURED 新缺口：bifrost-trade-infra/k8s/overlays/platform-prod/config/ops-context.yaml（PROD 的 platform-api 和 platform-workers 挂载的 ConfigMap bifrost-platform-config）只有 17 个 decision id，bifrost-platform origin/main 的 config/ops-context.yaml 有 50 个，缺 D-Journal-Stores、D-Ops-Split、D-Wave-10..13 等 33 个；该副本最后同步在 2026-08-24（0170331），diff 502 / 538 行。集群上 Ops Console 读到的 spine 已经陈旧 6 周。加一条 CI 检查（放 ci-infra 或 ci-platform）：部署副本与 platform main 的 spine decision 集合必须相同（或改由构建时从 platform repo 生成 ConfigMap，消掉这份副本）；check_overlay_configs.py 进 CI |
| 死重（TD-22/29/40/58/59/60/67） | partial | trade-api 的 test_retired_routes、test_account_serves_every_domain_router、test_account_sync_retired；FE 的 deadLinks.test.ts、routeRegistry.test.ts（不在 CI）；code-health 的 FLAT_PAGES / UNVALIDATED_API；core 的 test_ddl_no_readiness_tables | 没有查未使用代码的工具。Python 加 vulture（基线计数进 baselines.env），TS 加 knip（未用的 export / 文件数做棘轮）；FE vitest 进 CI |
| 漂移的副本（TD-04/30/42/46/78，以及 sync 脚本 heredoc） | partial | code-health 重复函数名棘轮（按名字计；CI 只覆盖 7 个 repo）；core 的 golden oracle 测试（BS、contract_key） | (1) 让三个插件 repo 也进 CI（trigger-trade-ci.yaml 的 python-ci 过滤加上 bifrost-platform-plugin*，pipeline-ci-python 的 code-health when 子句也加上）。MEASURED：market-data 重复 6/4、超大 11/5，infra 4/3、5/3，现在都在基线之上而没人知道；(2) oversized 指标排除 tests/，与 dup 指标的定义一致（现在 market-data 的 tests/test_daily.py 3078 行也被计入）；(3) 改名的副本抓不到：补一个按函数体指纹（AST hash）计的重复指标 |
| TD-85 DB 角色（一个密码通吃；Research D13 边界在权限层没落地） | no | 只有一次性的 db-steps.d/sql/*verify*.sql（手动）。MEASURED：bifrost 登录角色仍能 CONNECT dev/stg/prod/GS 四个库；analytics_writer 在 raw_market（属主 data_writer）和 raw_broker（属主 bifrost）上都有 schema CREATE 权限（nspacl 里 `analytics_writer=UC`），与 D13 的“Research 只写 dw_stock/features/research/journal”在权限层冲突 | 做一个只读的 role-matrix 检查（脚本 + 期望矩阵 YAML，放在 infra）：对每个登录角色断言可 CONNECT 的库集合，以及各 schema 上的 CREATE/INSERT/UPDATE/DELETE 集合，和期望矩阵逐格比对；作为 CronJob 每日跑，以 BifrostDbPrivilegeDrift 告警上报，并在 release-check before 里跑。TD-85 关闭时期望矩阵就是验收标准 |
| TD-86 视图重建丢掉授权 | partial | core 的 saved_view_grants 加 tests/test_brokerage_view_grants_db.py（在 CI db-test 里，只覆盖 raw_broker） | 把这个测试推广：遍历 db-init 会 DROP 再重建的所有视图（MARKET_LOCAL_VIEWS、public.v_us_equity_universe 等），断言重建前后 has_table_privilege 对所有非属主角色不变；上面的 role-matrix 检查放进 release-check after，db-init 跑完立刻能发现掉了权限 |
| 闸门本身失效（CI 是红的但没人看；有基线的 repo 没进 CI） | no | 没有。MEASURED：Tekton 指标没被抓取；trade-api main 从 10-04 起 CI 红着；plugin 三个 repo 自 09-29 起 32 次提交、0 次 CI 运行；infra 120 次提交、0 次 CI 运行 | (1) 抓取 tekton controller 指标，加 BifrostCIMainRed 告警：任一 repo 的 main 最近一次 ci-* 运行 Failed 超过 2 小时就报；(2) release.sh 在 stg/prod 之前 refuse，除非要发的 SHA 的 CI 是 Succeeded（`--allow-red <reason>` 留给 Owner）；(3) scan.sh 的 KNOWN_REPOS 加一个反向检查：baselines.env 里有基线的 repo，必须出现在某条 CI 的 when 子句里 |

## 待建防线（第 2 轮提议，按覆盖面排序）

### CI gates release (one switch that makes every test ratchet real)

- **做什么**：(a) deliver-research / build-research-dagster run ruff+pytest+code-health on the cloned SHA before build, reject non-SHA revisions; (b) release.sh refuses stg/prod unless the SHA's ci-* PipelineRun Succeeded (--allow-red <reason> for Owner); (c) trigger-trade-ci adds the three plugin repos and infra (new ci-infra: node agent-guard/test.js, check_overlay_configs.py, check_trade_gateway_routes.py, ops-context spine parity, scan.sh --repo infra); (d) ci-frontend runs vitest blocking; (e) scrape Tekton metrics + BifrostCIMainRed.
- **放哪**：bifrost-trade-infra/k8s/cicd/tekton (pipeline-deliver-research.yaml, trigger-trade-ci.yaml, new pipeline-ci-infra.yaml), scripts/release/release.sh, k8s/monitoring/bifrost-alerting-rules.yaml
- **强度**：blocking
- **覆盖**：TD-95, TD-96, TD-109, class: gate itself fails, class: failure-as-success (FE tests not in CI), class: drifting copies (plugins/infra had baselines but no CI), all test-based ratchets in TD-87..TD-125

### Every asset has an output check (Dagster asset-check contract)

- **做什么**：Test enumerating ENGINE_ASSETS + RESEARCH_AUX_ASSETS + market slot assets: each has a registered asset check or an explicit opt-out with reason. Shared check helpers: rows_written vs trailing median, failure share past onboarding window, mode!=skipped twice, judged as_of == latest NY session, held-pins-vs-zero-legs, gate session == expected, input mount present (no 'idle' green). Failures route through failure_alerts.
- **放哪**：bifrost-research/src/bifrost_research/orchestration (asset_checks.py) + tests/orchestration/test_asset_check_coverage.py
- **强度**：blocking
- **覆盖**：TD-92, TD-89, TD-94, TD-97, TD-100, TD-106, class: failure-as-success (green on zero rows)

### Session-date invariant

- **做什么**：(1) Nightly SQL sweep over every features/research/dw_stock/journal table with a trade_date: no weekend/holiday/future-of-newest-SPY-bar dates (asset check + Prometheus gauge). (2) dbt tests tying eval_date/trade_date to is_trading_day and max(bar_date). (3) ruff DTZ005/DTZ011 on research src with falling baseline; grep fails on new _today/_today_ny outside db/calendar.py.
- **放哪**：bifrost-research (dbt tests/generic, pyproject ruff select, orchestration asset check); alert rule in bifrost-trade-infra monitoring
- **强度**：blocking
- **覆盖**：TD-87, TD-98, TD-111, TD-93 (calendar part), TD-97

### Silent-swallow and silent-success metric in code-health

- **做什么**：AST metric across all Python repos: broad `except` with no logger and no raise (research baseline 99), persistence writers that `return 0/False/[]` from except (core accounts.py), bare `failed += 1` with no reason, handler results carrying truncated=true without a continuation allowlist; falling baselines in baselines.env.
- **放哪**：bifrost-trade-infra/agent-config/scripts/code-health/scan.sh + baselines.env; worker-level truncated guard in bifrost-platform-plugin-market-data worker
- **强度**：blocking
- **覆盖**：TD-91, TD-93, TD-113, TD-90, TD-92, TD-116, class: failure-as-success

### Liveness and freshness as timestamps, alerted

- **做什么**：Exporter metrics + rules: bifrost_dagster_schedule_last_success_seconds (cadence from roster) → BifrostDagsterScheduleOverdue; daemon_heartbeats → BifrostDagsterDaemonHeartbeatStale; per-table last_nonzero_write for features/research/raw_broker → stale rules (event_radar, option_pinned, transactions); bifrost_flex_coverage_gap_months == 0; freshness keyed by (dimension, slot) with last_nonzero_at; extend 5xx/crashloop rules beyond bifrost-* to research and plugin-*; gateway health hashes carry updated_at (required-field contract).
- **放哪**：bifrost-research /metrics (or small exporter), bifrost-platform-plugin-market-data freshness.py, bifrost-trade-infra/k8s/monitoring/bifrost-alerting-rules.yaml, tests/contracts/redis_ib_keys.json
- **强度**：warning
- **覆盖**：TD-99, TD-100, TD-101, TD-88, TD-104, TD-106, class: failure-as-success (runtime)

### Cross-repo contracts from one source

- **做什么**：Consumers test against producer-owned fixtures instead of hand-written dicts or literal copies: trade-api envelope fixture/OpenAPI for research readers (grep bans .get("attributions"|"executions") outside the shared helper); research schedule roster served by /research/orchestration/status and consumed by Console (literal maps removed); redis-ib hash required fields; operator ops classified exhaustively into READ_ONLY/PROD_ONLY; plugin aggregate OI reads must carry the adjusted-root predicate; route-caller manifest for research (port TD-40).
- **放哪**：bifrost-research tests/contracts, bifrost-platform console tests, bifrost-platform-plugin tests/test_operator_streams.py, bifrost-platform-plugin-market-data tests, bifrost-trade-api contract fixtures export
- **强度**：blocking
- **覆盖**：TD-89, TD-104, TD-105, TD-108, TD-102, TD-123, class: half-done renames, class: drifting copies

### Declared schema and grants equal live (catalog snapshot + role matrix)

- **做什么**：CI applies each repo's DDL to an empty Postgres and snapshots indexes, constraints and grants; a weekly read-only CronJob (and release-check after db-init) diffs against live GS/Trade DBs and an expected role-matrix YAML (CONNECT per db, CREATE/INSERT/UPDATE/DELETE per schema), alerting BifrostDbSchemaDrift / BifrostDbPrivilegeDrift. Also asserts no GS table carries an env column.
- **放哪**：bifrost-trade-infra/scripts/db-catalog-check (+ CronJob in k8s/monitoring), hooked into release-check.sh after
- **强度**：warning
- **覆盖**：TD-107, TD-103 (constraint after backfill), class: TD-85 DB roles, class: TD-86 view rebuild grants, class: shared GS as per-env store

### Manifest hygiene check

- **做什么**：kustomize-build assertions per repo: no kind: CronJob / Job in base unless allowlisted with reason; every image has a registry host (and digest for plugins); no RESEARCH_WATCHLIST literal; exactly one Dagster instance config; Deployments that envFrom secrets carry a checksum annotation and do not mark required keys optional; deployed config copies (ops-context.yaml) match their source or are generated.
- **放哪**：bifrost-trade-infra/scripts/check_manifests.py run in ci-infra and per-repo CI
- **强度**：blocking
- **覆盖**：TD-124, TD-119, TD-122, TD-120, TD-121, TD-109, TD-125, class: dead weight, class: config two sources

