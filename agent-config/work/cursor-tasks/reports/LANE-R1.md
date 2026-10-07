# LANE-R1 报告

五条 Claim 在 `origin/main` 上均成立，已按「只推分支」落地。没有 push main，没有 apply / PipelineRun / `release.sh stg|prod|dev`。

## TD-162
- Claim：成立（`bifrost-trade-infra/scripts/release/release.sh` 开头只描述 Trade 的 stg/prod/dev；窗口文件只有这一处，research / 插件发布不打开也不检查它。platform-api `StartPipelineRun` 创建 PipelineRun 之前不读窗口）
- 改动：
  - bifrost-trade-infra · `cursor/r1-infra` · `8da5697f4371cb1411b152aff38e5ed77074429e`
  - bifrost-platform · `cursor/r1-platform` · `a4636693f1b883e4d73fdf89ee5620de2f2d3356`
  - bifrost-platform-plugin-flex-query · `cursor/r1-flex` · `b8c094c6f733a3e6846ac5fc569ccc1025a03688`
- 防线：`scripts/release/test_window_decision.py`（`WindowTests`，含「别人持有则拒绝」）；`scripts/check-release-chain.py` 断言 deliver-research / dagster / market-data / ib-gateway 的第一个任务是 `release-window`，并核对 Tekton 任务里内联的 `decide()` 与 `window_decision.py` 一致。platform `release_window_test.go` 同一张判定表。flex-query 流水线引用同一个 Task；判定表里有 `bifrost-build-flex-query`，YAML 本身在另一个仓库，infra 检查扫不到它。
- 门禁：
  - `python3 scripts/release/test_window_decision.py` → 18 passed
  - `python3 scripts/check-release-chain.py` → ok（7 个窗口用例）
  - `bash -n scripts/release/release.sh` → exit 0
  - platform `go build ./...` → exit 0；`go vet ./...` → exit 0；`go test ./internal/delivery/` → ok
  - platform `go test ./...` → 失败 2 个包，都不在本次 diff：`internal/safego` `TestNoUnguardedGoroutines`（`checklist/prober.go`）、`internal/tradevocab` `TestTradeVocabularyOnlyShrinks`（`probe/probe.go`）。这是 `origin/main` 上已有的红，本分支没改这两个文件
- 验收：`git -C bifrost-trade-infra show 8da5697f4371cb1411b152aff38e5ed77074429e:scripts/check-release-chain.py` 后在该提交上跑 `python3 scripts/check-release-chain.py`，预期打印 `check-release-chain: ok`。platform 上 `go test ./internal/delivery/ -count=1 -run 'TestResearch|TestSomeoneElse|TestPluginBuilds'` 预期全部通过
- 要 Owner 批：把本分支的 Tekton 对象 apply 进 `cicd`（`task-release-window.yaml`、`rbac-release-window.yaml`，以及 install 脚本里新增的那几条）。在此之前流水线的第一个 task 会因读不到 ConfigMap 而失败（这是故意的 fail-closed）。platform-api 的 ServiceAccount 若不能 `get` 这个 ConfigMap，research/插件构建会一律拒绝；RBAC 目录 `k8s/platform-rbac` 归 LANE-S2，本道没有加。用法：`release.sh hold --what <仓库>`，`start_pipeline_run` 的 JSON 带同一个 `who`
- 后续：无后续（窗口与 `who` 核对已写进 `CLAUDE.md` §5 与 `docs/RELEASE.md`，parity `workspace-v14`。合并前工作区根的 parity 脚本仍读共享 checkout，对不上 v14 是预期的）

## TD-155
- Claim：成立（CI 由 Gitea webhook 触发；`bootstrap-gitea-mirrors.sh` 只在手工执行时 `POST mirror-sync`。deliver 流水线虽有 mirror-sync，但是固定 sleep 8 秒，不等待目标 SHA，也不等该 SHA 的 CI）
- 改动：bifrost-trade-infra · `cursor/r1-infra` · `8da5697f4371cb1411b152aff38e5ed77074429e`（与 TD-162 同一提交）
- 防线：`scripts/release/test_window_decision.py` 的 `CiGateTests`（别的 SHA、失败、缺失、`--allow-red`）；`scripts/check-release-chain.py` 断言 `task-gitea-mirror-sync.yaml` 含 `expectSha` 与 `git/commits`，且 `release.sh` 调用 `bootstrap-gitea-mirrors.sh` 与 `ci_gate.py`
- 门禁：同上，`test_window_decision.py` 18 passed 里含 CI 用例；`check-release-chain.py` exit 0
- 验收：在 `8da5697` 上 `python3 scripts/release/test_window_decision.py CiGateTests` 预期通过。`task-gitea-mirror-sync.yaml` 里应能看到对 `/git/commits/${sha}` 的轮询，超时则 exit 1
- 要 Owner 批：没有单独的集群动作。`release.sh stg|prod` 会自己同步镜像再等 CI；这条要等窗口和发版批准之后才跑，本道没有跑
- 后续：没有做 GitHub → Gitea 的 push webhook。集群 Gitea 只在局域网 NodePort，GitHub 的 runner 够不到。选了台账里的另一条：发布脚本和 deliver 流水线先同步镜像，再等这个 SHA。GitHub 推上去之后、有人发版之前，CI 仍要等下一次 mirror-sync 或发版脚本

## TD-95
- Claim：成立（`pipeline-deliver-research.yaml` 的顺序是 mirror-sync → clone → build/pin-check，revision 默认 `main`，不读 `bifrost-ci-python`。`pipeline-build-research-dagster.yaml` 克隆后直接 Kaniko。`release.sh` 不查 CI）
- 改动：bifrost-trade-infra · `cursor/r1-infra` · `8da5697f4371cb1411b152aff38e5ed77074429e`；platform 对这两条流水线（外加 ib-gateway）拒绝非 40 位 revision，SHA 在 `a4636693f1b883e4d73fdf89ee5620de2f2d3356`
- 防线：`scripts/check-release-chain.py` 断言两条 research 流水线有 `validate-revision`、`lint-test` 在 build/kaniko 的 `runAfter` 里，且 revision 参数不再 `default: main`。`ci_gate.py` 是 `release.sh stg|prod` 的开关，`--allow-red <原因>` 放行并写进日志
- 门禁：`python3 scripts/check-release-chain.py` → exit 0。platform `go test ./internal/delivery/ -run TestFullSHA` → 含在 delivery 包 ok 里
- 验收：`python3 scripts/check-release-chain.py` 预期 exit 0。`pipeline-deliver-research.yaml` 与 `pipeline-build-research-dagster.yaml` 里 `build-research` / `kaniko` 的 `runAfter` 包含 `lint-test`
- 要 Owner 批：apply `task-validate-git-sha.yaml`、`task-research-lint-test.yaml` 以及改过的两条 Pipeline（install 脚本已列上）。lint-test 会在构建前跑 ruff、pytest `-m 'not ib and not db'`、sqlfluff 和 code-health，research 发版会变长
- 后续：台账原文的 `BifrostCIMainRed` 告警没有加。Measured 写明 Tekton controller 指标没有被抓取，告警不会响。真正挡住发布的是流水线里的 lint-test 和 `release.sh` 的 CI 门。Trade 的 deliver-stg/prod 没有内联 lint-test（道文件只要求 research 两条）；Trade 侧用 `release.sh` 查已有 `ci-*`

## TD-122
- Claim：成立（`bifrost-platform-plugin/k8s/ib-gateway/base/deployment.yaml` 使用 `bifrost-platform-plugin-ib-gateway:0.3.0` 且 `imagePullPolicy: IfNotPresent`；仓库里没有构建流水线。三个健康 hash 不写 git SHA）
- 改动：
  - bifrost-platform-plugin · `cursor/r1-plugin` · `1e7212a1103ec5f77c30233f3030dd6e665d209d`
  - 流水线副本也在 infra `cursor/r1-infra` · `8da5697f4371cb1411b152aff38e5ed77074429e`（`k8s/cicd/tekton/pipeline-build-ib-gateway.yaml`，与插件仓 `k8s/cicd/pipeline-build.yaml` 内容一致）
- 防线：`tests/test_health_git_sha.py`（三个 hash 带 `git_sha`，且没有 `updated_at`）；`tests/test_ib_gateway_image_pin.py`（镜像是 `192.168.10.73:30500/...`、`imagePullPolicy: Always`、流水线有 `--digest-file` 和 `GIT_SHA` build-arg、安装脚本的可执行行不再调用节点导入）
- 门禁：`PYTHONPATH=src BIFROST_SKIP_CORE_CONTRACT_SYNC=1 pytest -q` → 75 passed, 1 skipped。跳过的是 `test_manifest_is_core_copy`：worktree 不在 core 旁边，且当前 core checkout 里没有 `tests/contracts/redis_ib_keys.json`（`git ls-files` 为空），与本次改动无关。`ruff check` 改过的三个文件 → clean。全仓 `ruff check src tests` 有 2 个既有 F401（`ib_ops.py`、`tests/test_self_heal.py`），不在本次 diff
- 验收：在 `1e7212a` 上 `PYTHONPATH=src pytest -q tests/test_health_git_sha.py tests/test_ib_gateway_image_pin.py` 预期通过。`writer.py` 的 `_health_identity` 只追加 `git_sha`
- 要 Owner 批：apply `pipeline-build-ib-gateway`（以及它依赖的 release-window / validate-git-sha / mirror-sync 任务）后，用 40 位 SHA 跑一次构建。Kaniko 结果 `digest` 要写回 Deployment，把现在的 tag 换成 `192.168.10.73:30500/bifrost-platform-plugin-ib-gateway@sha256:…`，然后再 apply Deployment。本道没有构建，所以清单里还是 tag，不是伪造的 digest。`scripts/install-ib-gateway.sh` 现在直接拒绝，不再把笔记本镜像导入节点
- 后续：健康 hash 只加了 `git_sha`。`updated_at` 留给 LANE-T（TD-104）。开工时 `cursor/t-plugin` 相对 `origin/main` 没有提交；若该道改同一段 writer，合并点在 `_health_identity`。code-health「插件仓镜像缺 registry 或 digest = 0」没有加进 `scan.sh`：flex-query / market-data 的清单仍是 tag，这条指标一上就会红。ib-gateway 的 digest 钉进 git 要等第一次构建（上面的 Owner 步骤）。没有改 `preflight.js`（guard 文件）；安装脚本不再执行节点导入

## TD-121
- Claim：成立（`bifrost-research/scripts/sync_openai_secret.sh` 只 `rollout restart deployment/research-api`。research-api / mcp / dagster 的 envFrom 指向 `bifrost-research-secrets`。infra 的 `holder_deployments()` 会按 Secret 推导 Deployment，但不管这把 research Secret）
- 改动：bifrost-trade-infra · `cursor/r1-infra` · `8da5697f4371cb1411b152aff38e5ed77074429e`。research 清单（去掉 `optional: true`、checksum 注解进 kustomize）是 LANE-R2，本道没改 research 仓
- 防线：`scripts/test_research_secret_holders.py`（`HolderTests`：列出所有挂载该 Secret 的 Deployment，名字前缀不算，checksum 不含原值）。`scripts/check-release-chain.py` 断言 `research-secret-restart.sh` 不出现 `deployment/research-api`，并写入注解 `bifrost.io/secret-checksum`
- 门禁：`python3 scripts/test_research_secret_holders.py` → 3 passed。`bash -n scripts/research-secret-restart.sh` → exit 0
- 验收：`python3 scripts/test_research_secret_holders.py` 预期 3 passed。`grep -n deployment/research-api scripts/research-secret-restart.sh` 预期无匹配
- 要 Owner 批：轮换 Secret 之后由 Owner 跑 `scripts/research-secret-restart.sh`（可先 `--dry-run`）。脚本会 `kubectl patch` Deployment 注解，从而滚动重启。本道没有执行。注解打在运行中的对象上，不在 Git 清单里；清单侧的 checksum / 去掉 `optional: true` 等 R2
- 后续：无后续（research 侧仍由 LANE-R2 改 `optional: true`）
