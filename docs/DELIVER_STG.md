# STG Deliver Pipeline (`bifrost-deliver-stg`)

正式 STG 交付路径：业务代码进镜像，ConfigMap 只承载 YAML 配置（不含 Python/TS 热补丁）。

## 架构

```
push-main.sh → Gitea (cicd) main   ← the primary of every repository; GitHub only follows (see below)
    ↓ mirror-sync: each repo is Gitea's own, so nothing is fetched; fails if Gitea or a repo is missing
    ↓ clone 7 repos from Gitea (incl. bifrost-trade-infra)
    ↓ prepare: Dockerfile ConfigMaps from infra clone
    ↓ Kaniko
Registry :30500  →  bifrost-{api,frontend,worker,socket}:stg
    ↓ rollout restart
    ↓ verify-stg (in-cluster Traefik: follow redirects / accept 301|302|200|503)
bifrost-stg namespace  (+ Argo CD sync)
```

**代码在哪（Gitea 做主，2026-10-17/18 起）：** 11 个仓库（`agent-config/gitea-primary.txt`）都以集群内 Gitea
`bifrost/<repo>` 为主仓库，不再是 GitHub 的拉取镜像；建拉取镜像的脚本和它的两个 make 目标在第 D 批（2026-10-23）
删除，`scripts/release/test_w33c_static.py` 守着不让它回来。人和 Agent 都推 Gitea；GitHub `weitingzhao/<repo>`
只收 `main` 和标签，由集群快进推过去（`k8s/cicd/github-sync`），见 [RELEASE.md](RELEASE.md)「代码在哪」。

**约束：** `clone-*` 仍 `runAfter: [mirror-sync]`。这个 Task（`bifrost-gitea-mirror-sync`）先问 Gitea 每个仓库是不是拉取镜像：
是才请求同步，不是就打一行 `… is Gitea's primary: nothing to fetch`；给了 `expectSha` 就等到这个提交在 Gitea 上。
今天 11 个仓库都是主仓库，所以它只核对 Gitea 在、仓库在（和提交在）。prepare 只写 Dockerfile ConfigMap。
`bifrost-trade-infra` 必须在 mirrorRepos 里。

| 组件 | 来源 | 说明 |
|------|------|------|
| 业务代码 | Gitea clone | api / worker / socket / frontend / ui / core |
| Dockerfiles | infra clone in pipeline | `prepare` task 写入 cicd ConfigMap |
| 运行时配置 | `config/config.stg.yaml` | ConfigMap `bifrost-config`，Secret 放密钥 |
| Overlay 策略 | `k8s/overlays/stg/` | celery-worker replicas=0、NodePort、amd64 调度 |
| 验收 | `verify-stg` task | 集群内 curl Traefik（`-L -k`，接受 200/301/302/503）+ 9 API；外网视角用 Delivery `get_stg_smoke`（NodePort） |

## 镜像内容（Dockerfile.api-stg）

共享 API 镜像包含：

- `bifrost-core` + `bifrost-worker` + `bifrost-socket` + `bifrost-api`（pip 安装）
- `/build/bifrost-trade-worker/scripts`（含 `run_celery.py`）
- `/build/bifrost-trade-socket/scripts`（含 `run_massive_ws.py`）
- `procps`（Celery pgrep）

9 个 API Deployment 共用同一 digest（crane copy），由 K8s command 区分 domain。

## 日常交付流程

### 1. 把改动推到 Gitea 的 main

经 `scripts/release/push-main.sh <checkout> <sha>` 推（见 [RELEASE.md](RELEASE.md)「发布窗口」）：各检出的 `origin`
是 Gitea（`http://192.168.10.73:30300/bifrost/<repo>.git`），`github` 远端只读。deliver 克隆的是 Gitea 上的提交；
推到 Gitea 后 CI 由 Gitea 的推送钩子直接起，不用等任何同步。直接推 GitHub 被 `preflight.js` 和 `push-main.sh` 拒绝。

### 2. 同步配置（可选）

```bash
cd bifrost-trade-infra
cp .env.example .env   # 填 IB / POSTGRES 等
make sync-stg-config
kubectl apply -k k8s/overlays/stg   # 配置变更时
```

### 3. 运行 deliver

```bash
export KUBECONFIG=~/.kube/bifrost-k3s.yaml
make k3s-deliver-stg
```

等价于 `scripts/k3s/run-deliver-stg.sh`（它用 `kubectl apply`，只有 Owner 的管理员 kubeconfig 能跑；Agent 发 STG 用
`release.sh stg`，经平台起 run），默认：

1. 本地检查 overlay 配置、Postgres 等待、`uiRevision` 接线
2. 更新 Tekton Dockerfile ConfigMaps
3. 创建 `bifrost-deliver-stg` PipelineRun
4. 等待完成（默认 2h 超时）

不再有「先同步 Gitea 镜像」这一步：Gitea 是主仓库，推上去的就是 deliver 克隆的。

**环境变量：**

| 变量 | 默认 | 说明 |
|------|------|------|
| `APPLY_OVERLAY` | `0` | deliver 时是否 `kubectl apply -k` |
| `RUN_DB_INIT` | `0` | 成功后重跑 `db-init-stg` Job |
| `REVISION` | `main` | Gitea clone 分支 |

```bash
# 配置 + 镜像一起更新
APPLY_OVERLAY=1 make k3s-deliver-stg
```

### 4. 验证

```bash
make k3s-verify-phase-b-stg-v2
curl -s http://192.168.10.73:30880/api/monitor/status
```

Ops Console：**Delivery → bifrost-deliver-stg → Run**（Platform API 创建 PipelineRun）。

## core 版本身份与 PROD tag（TD-37）

- core 随 api / worker 同一次克隆构建，发布身份是 **clone-core 的 SHA**：`bifrost-git-clone-gitea` 把 `git rev-parse HEAD` 写进
  结果 `commit`（日志仍打印 `=== HEAD <sha> ===`），两条 deliver 流水线把 `$(tasks.clone-core.results.commit)` 作为 `coreSha`
  传给 `bifrost-kaniko-all-apis-stg` 与 `bifrost-kaniko-worker-stg`，Kaniko 以 build-arg `BIFROST_CORE_SHA` /
  `BIFROST_CORE_VERSION`（读克隆里的 `pyproject.toml`）写进镜像：env `BIFROST_CORE_SHA`、label `io.bifrost.core.sha` /
  `io.bifrost.core.version`。不传 `coreSha` 的旧 run 得到 `unknown`。
- 核对：`curl -s http://192.168.10.73:30880/api/monitor/health`（PROD `:30881`；account 进程走 `/api/account/health`（TD-55 B1 起；
  之前是别名 `/api/trading/health`），market / research 走 `/api/<domain>/health`）看 `core_sha` / `core_version`。
- PROD 的钉版本内联 run（`bifrost-deliver-prod-pinned-*`）复制的是 `pipeline/bifrost-deliver-prod` 的 spec：本改动上线后，
  要从新的 pipeline spec 重新生成 JSON，旧 JSON 构建出的镜像 `core_sha` 是 `unknown`。
- PROD 发布成功后打 tag：`scripts/release/tag_core_release.sh <core_sha>` 先 dry-run，确认后加 `--push`。
  `v<version>` 已指向别的提交时拒绝（一个版本号装了两份内容）。

## 发布脚本（TD-84）

STG → PROD → DEV 的整套步骤（窗口锁、并发检查、钉版本 spec、before/after 核对、DB 步骤闸门、计时）见
[RELEASE.md](RELEASE.md)：`scripts/release/release.sh stg|prod|dev [--dry-run]`。推 Trade 仓库的 `main` 或起任何
`bifrost-deliver-*` run 之前先跑 `scripts/release/release.sh window`（exit 0 = 没有发布在进行）。

## 已退役的热补丁

以下 ConfigMap / patch **已从 overlay 移除**，改由镜像承载：

| 旧机制 | 替代 |
|--------|------|
| `api-ops-code-patch` ConfigMap | `bifrost-api-ops:stg` 镜像内 `bifrost_api.ops.*` |
| `celery-run-script` ConfigMap + initContainer | 镜像 `/build/bifrost-trade-worker/scripts` |
| `socket-massive-code-patch` | `bifrost-socket:stg` 镜像内 massive 模块 |
| api-ops 启动时 `apt-get procps` / `sed pgrep` | Dockerfile.api-stg 已含 procps；源码已用 `pgrep -af` |

**保留的 overlay 补丁：**

- `api-ops-celery.patch.yaml` — `celery-worker` replicas=0 + api-ops 可写 logs emptyDir
- `config.stg.yaml` — `massive.ws_url: delayed.polygon.io`（Starter tier）

## Massive WS STG 要点 [RETIRED]

> **Trade `massive-ws` Deployment retired (P7).** 其 Plugin 继任者 `polygon-ws-ingestor` 与 `redis-massive`
> 亦于 2026-09-27 退役（Owner 决策：Options Starter 无实时 WS）。Polygon WS ingest 已不存在，勿再做任何 WS rollout / restart。

- Watchlist 种子：`scripts/k3s/seed-stg-watchlist.sh`（从 Dev PG 导入）
- **Options Starter**（历史）：`massive.features.ws_enabled: false` — 原 `massive-ws` REST-only 待机

## 相关文件

```
k8s/cicd/tekton/pipeline-deliver-stg.yaml
k8s/cicd/tekton/task-gitea-mirror-sync.yaml   # 主仓库不拉取，只核对仓库和提交在 Gitea 上
k8s/cicd/tekton/task-prepare-deliver-stg.yaml
k8s/cicd/tekton/task-deliver-stg.yaml
k8s/cicd/tekton/task-kaniko-*.yaml
k8s/cicd/docker/Dockerfile.*-stg
scripts/k3s/run-deliver-stg.sh
scripts/release/push-main.sh                  # 推 Gitea main 的唯一入口
k8s/cicd/github-sync/                         # GitHub 跟随 Gitea：main 和标签，只快进
agent-config/gitea-primary.txt                # 以 Gitea 为主的仓库名单
k8s/overlays/stg/
```

完整 Phase B 计划见 `docs/PHASE_B_STG_V2_PLAN.md`。
