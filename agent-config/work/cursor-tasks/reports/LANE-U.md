# LANE-U 报告 — @bifrost/ui 构建与版本、Redis 清单（Cursor，2026-10-06）

三项都只推了分支，没有推 main，没有起 PipelineRun，没有 `kubectl apply`，没有写数据库。worktree 已全部移除。
只读集群操作：`kubectl get`（读 PipelineRun / release record）与一次 `kubectl diff -k k8s/data/redis`（服务端 dry-run，不改集群）。

## TD-235
- Claim：成立。`bifrost-ui/package.json:8` 的 `build` 以 `rm -rf dist &&` 开头，`:11` `prepare` 是 `npm run build`；两个消费方都别名到 `bifrost-ui/dist`（`bifrost-trade-frontend/vite.config.ts:188`，`bifrost-platform/console/tsconfig.json:21`）。
- 改动：bifrost-ui · `cursor/td-ui-build`（起点 origin/main `2271260`）· `b65af130898f84be91c52c8f022ddf13ecc78696`
  - `build` 改为 `node scripts/build.mjs`：tsc `--outDir dist.tmp-<pid>`，拷 5 个样式文件，全部成功后才 `rename dist → dist.old-<pid>`、`rename dist.tmp-<pid> → dist`，再删旧目录。编译或拷贝失败时删掉临时目录、`dist/` 原样保留并 exit 1。临时目录带 pid，两个会话同时 build 不会互踩。
  - 新增 `npm test`（`node --test scripts/*.test.mjs`）；`.gitignore` 加 `dist.tmp-*/`、`dist.old-*/`。
  - 产物与旧脚本一致：新旧 `dist/` 文件清单逐项相同（对比共享 checkout 的 dist），source map 相对路径不变。
  - 说明：两次 rename 之间 `dist/` 缺席的时间是微秒级，不是严格原子；比原来「整个 tsc 期间都没有 dist」小几个数量级。
- 防线：`bifrost-ui/scripts/build.test.mjs`（`npm test`）
  - `package.json build does not delete dist before compiling` — build 脚本出现 `rm -rf dist` 即失败
  - `a tsc failure leaves the previous dist in place` — 用真实 tsc 编译一个编造的类型错误，断言旧 `dist/index.js` 原样、无残留临时目录
  - `a successful build replaces dist with the new output and styles`
- 门禁（bifrost-ui 没有 eslint / vitest，用它自己的脚本）：`npm run lint`（tsc --noEmit）→ exit 0 · `npm test` → 3 passed / 0 failed · `npm run build` → exit 0
- 验收：`git -C bifrost-ui fetch -q origin && git -C bifrost-ui show origin/cursor/td-ui-build:package.json | grep -c 'rm -rf dist &&'` → `0`（合并 main 后改成 `origin/main`）；可选 `git -C bifrost-ui worktree add --detach /tmp/v235 origin/cursor/td-ui-build && ln -s "$PWD/bifrost-ui/node_modules" /tmp/v235/node_modules && (cd /tmp/v235 && npm test)` → `pass 3`
- 要 Owner 批：没有部署动作；只需把分支合进 bifrost-ui main（合并后 `npm install` 自动走新 build）。
- 后续：没有 CI 跑 bifrost-ui 自己的 `npm test`：`pipeline-ci-frontend.yaml:99` 装 ui 时用 `--ignore-scripts`，`pipeline-ci-platform.yaml:141` 装 ui 时跑 `npm ci`（也就是 prepare → build），但都不跑 test。建议在 ci-platform 的 test-console 步骤里，装完 ui 后加一行 `npm test`（infra 改动，本道没做）。

## TD-234
- Claim：大部分成立，有一处已过时。
  - 成立：bifrost-ui 推送只触发 `frontend-ci-ui`（`bifrost-trade-infra/k8s/cicd/tekton/trigger-trade-ci.yaml:250`），platform CI 模板不接收 `uiRevision`（同文件 `:163-185`）；`pipeline-deliver-platform.yaml:59` 和 `pipeline-deliver-platform-prod.yaml:91` 的 clone-ui 都用 `$(params.revision)`；`bifrost-platform/console/package.json:22` 是 `file:../../bifrost-ui`。
  - 已过时：「nothing records the ui commit」不再成立。platform `f53713b`（2026-10-06，release records）已经为每次 platform deliver 记下 clone-ui 的提交，实测 `cm/release-bifrost-deliver-platform-prod-1791344349` 里 `bifrost-ui` 的来源是 `result`。真正缺的是**钉住** ui：PROD 只能拿到当时 ui main 的版本，回滚也选不了 ui。
- 改动：
  - bifrost-trade-infra · `cursor/td-ui-pin`（起点 origin/main `f5ea642`）· `ccd35df220f0d046026446eea4c2bd1fdeec1b49`
    - 所有 clone bifrost-ui 的 Pipeline（deliver-platform、deliver-platform-prod、deliver-stg、deliver-prod、build-frontend-stg）声明 `uiRevision`（默认 main），clone-ui 改用 `$(params.uiRevision)`。
    - `trigger-trade-ci.yaml`：platform CI 模板加 `uiRevision` 并传给 PipelineRun；新增 trigger `platform-ci-ui`（bifrost-ui 推 main → `bifrost-gitea-push-ui` 绑定 → platform 在 main、ui 在推送的 SHA）。
    - `scripts/release/platform-prod-pinned-from-stg.sh` + `release_tool.py platform-pinned-spec`：从一次成功的 `bifrost-deliver-platform` run 读 clone-platform / clone-ui 的提交，生成 `bifrost-deliver-platform-prod` run（`revision` 和 `uiRevision` 都是 40 位 SHA，标签 `bifrost.io/purpose=platform-prod-pinned`、`bifrost.io/from-stg-run`），**只生成 JSON，不创建**。用真实 STG run `bifrost-deliver-platform-1791344064` 试过：两个提交都读到；拿 prod run 去生成会 REFUSED，exit 1。
    - `run-deliver-{stg,prod,platform}.sh` 传 `UI_REVISION`（默认等于 `REVISION`），所以这些脚本起的 run 行为不变。
  - bifrost-platform · `cursor/td-ui-pin`（起点 origin/td-l6 `b066d99`）· `411d46113fc798ac94cb953c8797dbf052272736`
    - `StartPipelineRun` 的参数抽到 `pipelineRunParams`；对 clone 集合里有 bifrost-ui 的 pipeline 追加 `uiRevision = revision`，保持现在「一个 ref 用于所有 repo」的语义（RefPreflight 已经检查这个 ref 在每个 repo 都存在）。
    - `releases.buildRecord`：clone 没有 commit result 时，先用该 TaskRun 自己解析后的 `revision` 参数（是 40 位 SHA 才算），只有 TaskRun 没有 revision 参数时才退回用 run 的 `revision`。不改的话，一个 pin 住的 ui clone 如果缺 result，会被记成 platform 的 SHA。
  - 没做的部分（Fix 第 3 条）：(a) 把 ui SHA 写进镜像（build arg → OCI label / `/health`）：release record 已经把 run 对应的 ui 提交记下来了，所以没加，免得同一个事实有两个来源；(b) `UI_VERSION_NOW` 改成构建时取值：它在 `bifrost-trade-frontend/src/lib/design/uiVersion.ts:50`，那是 LANE-D 的仓库，不在本道范围，见「后续」。
- 防线：
  - `bifrost-trade-infra/scripts/check_ui_revision.py`（`make check-ui-revision`；`--self-test`；`run-deliver-{stg,prod,platform}.sh` 发布前也跑）。规则一：每个 clone bifrost-ui 的 Pipeline task 必须用 `$(params.uiRevision)`，且 Pipeline 声明了这个参数。规则二：每个 clone ui 的 `bifrost-ci-*` 都要有一个 EventListener trigger：filter 是 `'bifrost-ui'`，binding 设 `uiRevision=$(body.after)`，模板把 `$(tt.params.uiRevision)` 传给该 Pipeline。对 origin/main 报 11 处问题，对本分支报 0。
  - `bifrost-platform/api/internal/delivery/pipeline_run_params_test.go::TestPipelineRunParamsUIRevision`
  - `bifrost-platform/api/internal/releases/releases_test.go::TestParamSHAAndIncompleteRecordIsCompletedLater`（新增「clone 走自己的参数」用例：ui 记成 TaskRun 的 SHA；`revision=main` 的 clone 不会冒用 run 的 SHA，进 Missing）
- 门禁：
  - infra：`check_ui_revision.py --self-test` → self-test ok · `check_ui_revision.py`（k8s/cicd/tekton 和整个 k8s/）→ exit 0 · `ruff check` 两个 py 文件 → All checks passed · `bash -n` 三个 run-deliver 脚本 → ok · 所有 tekton YAML 能解析 → ok · `check_pg_wait.py` → exit 0。infra 没有 `make lint` / `make test` 目标；本机没有 shellcheck。
  - platform：`go build ./...` → exit 0 · `go vet ./...` → exit 0 · `go test ./...` → 51 个包 ok，0 FAIL · `golangci-lint run ./...` → 44 issues，与起点 origin/td-l6 完全相同（44，都是既有问题），本次改的文件没有新增。console 没改，没跑 TS 门禁。
- 验收：`git -C bifrost-trade-infra fetch -q origin && git -C bifrost-trade-infra worktree add --detach /tmp/v234 origin/cursor/td-ui-pin && /usr/bin/python3 /tmp/v234/scripts/check_ui_revision.py --self-test && /usr/bin/python3 /tmp/v234/scripts/check_ui_revision.py; echo $?` → `self-test ok` 加 `0`（用 `/usr/bin/python3` 是因为 homebrew python3 没装 PyYAML）。platform：`git -C bifrost-platform worktree add --detach /tmp/v234p origin/cursor/td-ui-pin && (cd /tmp/v234p/api && go test ./internal/delivery/ ./internal/releases/)` → 两个 ok。台账里的线上验收（ci-platform 出现 `uiRevision=<40hex>`）要等下面的上线动作做完、再推一次 ui 之后才会有结果。
- 要 Owner 批：
  1. 先合 infra `cursor/td-ui-pin` 进 main，并把 Tekton 对象应用到集群：`pipeline-deliver-{platform,platform-prod,stg,prod}.yaml`、`pipeline-build-frontend-stg.yaml`、`trigger-trade-ci.yaml`（infra 的 apply 目标，例如 `make k3s-install-ci-triggers` / `k3s-apply-cicd-platform-pipeline`）。
  2. **然后**才合 platform `cursor/td-ui-pin`（基于 td-l6），走 platform 发布。顺序必须是先 infra 后 platform：platform-api 会开始传 `uiRevision`，Pipeline 先声明了它，就不会遇到 Tekton 怎么处理多余参数的问题。
  3. 以后 PROD platform 发布用 `scripts/release/platform-prod-pinned-from-stg.sh <stg-run> -o f.json`，然后 `kubectl create -f f.json`。这一步就是 PROD 发布，每次都要 Owner 点头。
- 后续：
  - `bifrost-trade-frontend/src/lib/design/uiVersion.ts:50` `UI_VERSION_NOW` 仍是手写常量。应在 vite 构建时从 `bifrost-ui/package.json` 的 version 注入（LANE-D 的仓库）。
  - `bifrost-platform/agent/remediation/src/prompt.ts:202,205,304,373` 写着 deliver-platform「clone both repos at pipeline param `revision`」。经 platform-api 起的 run 仍然如此，但用 pinned 脚本起的 PROD run 里 ui 是单独钉的；等 pinned 流程接进 Console / agent 时要一起改。

## TD-238
- Claim：成立。`bifrost-trade-infra/k8s/data/redis/instances.yaml:29-34`（stg）、`:116-121`（prod）、`:203-208`（dev）都是 `--appendonly yes --appendfsync everysec --maxmemory-policy noeviction`，没有 volume，也没有 `--maxmemory`。另外没被部署的 `k8s/base/infra/redis.yaml:22` 也是 `--appendonly yes`：三个 overlay 都用 `redis-remove.patch.yaml` 把它删了。
- 改动：bifrost-trade-infra · `cursor/td-redis`（起点 origin/main `f5ea642`）· `ce91d8158e09c484e26556891d9695152bbbac80`
  - 三个实例按台账 Fix 的第一种做法声明为易失：`--appendonly no --save ""`，并设 `--maxmemory`：stg / dev 是 400mb（容器 limit 512Mi），prod 是 800mb（limit 1Gi）；`--maxmemory-policy noeviction` 保留。base redis 改成同样的参数（200mb，limit 256Mi），让检查能覆盖整个 `k8s/`。
  - 本机 `redis:7-alpine` 用这组参数起过：`CONFIG GET` 返回 appendonly `no`、save 为空、maxmemory 419430400（400 MiB）、policy noeviction。
  - `kubectl diff -k k8s/data/redis`：三个 Deployment 只有上述 args 变化。另有 3 个对象有既有漂移，与本改动无关：NetworkPolicy `redis-dev-ingress`、`redis-dev-lan-ingress` 和 Service `redis-dev-lan` 缺 kustomize 的 part-of / managed-by / component 三个标签，`redis-dev-lan` 的 `bifrost.io/purpose` 注解也和清单不同。
- 防线：`bifrost-trade-infra/scripts/check_redis_config.py`（`make check-redis-config`；`--self-test`）。规则一：没有 `/data` volumeMount 的 redis-server 不得 `--appendonly yes`，并且必须写 `--save ""`。规则二：每个 redis-server 都要有 `--maxmemory` 大于 0（noeviction 本来就是 redis 的默认策略），且小于容器的 memory limit。对 origin/main 报 12 处问题，对本分支报 0。
- 门禁：`check_redis_config.py --self-test` → self-test ok · `check_redis_config.py` → exit 0 · `make check-redis-config` → exit 0 · `ruff check` → All checks passed · `check_pg_wait.py` / `check_data_lan_exposure.py` → exit 0。（`check_overlay_configs.py` 在本机缺 `bifrost_core` 模块，起不来；origin/main 上一样，与本改动无关。）
- 验收：静态：`git -C bifrost-trade-infra worktree add --detach /tmp/v238 origin/cursor/td-redis && /usr/bin/python3 /tmp/v238/scripts/check_redis_config.py; echo $?` → `0`。上线后：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec deploy/redis-live-prod -c redis </dev/null -- redis-cli CONFIG GET appendonly maxmemory` → appendonly `no`，maxmemory `838860800`（stg / dev 是 `419430400`）。
- 要 Owner 批：合 `cursor/td-redis` 进 main 之后，`k8s/data/redis` 不归 Argo 管，要手工应用。先跑 `kubectl diff -k k8s/data/redis` 看一遍（预期只有上面列的那些），再 `kubectl apply -k k8s/data/redis`。这会**重启 redis-live-prod、redis-live-stg、redis-dev 三个 pod**，内存里的 key 会丢（都是带 TTL 的 IPC，PROD 实测只有 3 个 key）。另外 apply 还会顺带把上面 3 个对象的标签和注解漂移改回清单的样子，需要 Owner 知道。
- 后续：无后续。顺带提一句：`scripts/k3s/verify-data-layer-phase5-data.sh:19` 只校验 maxmemory-policy，可以考虑同时校验 `appendonly no` 和 `maxmemory > 0`，作为这条防线的线上版（可选，没做）。

## 合并注意
- infra 的两个分支都改了 `Makefile`，但改的位置不同（td-ui-pin 在 `check-pg-wait` 后面加目标并改 `.PHONY`；td-redis 在 `check-data-lan-exposure` 后面加目标、不碰 `.PHONY`），预计不会冲突。
- TD-234 的 infra 和 platform 两个分支有先后顺序：先 infra，后 platform（见 TD-234「要 Owner 批」）。
