# STG Deliver Pipeline (`bifrost-deliver-stg`)

正式 STG 交付路径：业务代码进镜像，ConfigMap 只承载 YAML 配置（不含 Python/TS 热补丁）。

## 架构

```
GitHub (upstream)
    ↓ mirror-sync (pipeline task prepare)
Gitea (cicd)  ← clone 7 repos (incl. bifrost-trade-infra)
    ↓ prepare: Dockerfile ConfigMaps from infra clone
    ↓ Kaniko
Registry :30500  →  bifrost-{api,frontend,worker,socket}:stg
    ↓ rollout restart
    ↓ verify-stg (in-cluster HTTP: gateway + 9 APIs)
bifrost-stg namespace  (+ Argo CD sync)
```

**Console Delivery → Run** 与 **`make k3s-deliver-stg`** 现在共用同一 Pipeline（含 prepare + verify）。CLI 额外步骤：可选 `sync-stg-config`、Gitea mirror（Pipeline 内 prepare 也会尝试 mirror-sync）。

| 组件 | 来源 | 说明 |
|------|------|------|
| 业务代码 | Gitea clone | api / worker / socket / frontend / ui / core |
| Dockerfiles | infra clone in pipeline | `prepare` task 写入 cicd ConfigMap |
| 运行时配置 | `config/config.stg.yaml` | ConfigMap `bifrost-config`，Secret 放密钥 |
| Overlay 策略 | `k8s/overlays/stg/` | celery-worker replicas=0、NodePort、amd64 调度 |
| 验收 | `verify-stg` task | 集群内 curl nginx + 9 API；Delivery Stg smoke 为外网视角 |

## 镜像内容（Dockerfile.api-stg）

共享 API 镜像包含：

- `bifrost-core` + `bifrost-worker` + `bifrost-socket` + `bifrost-api`（pip 安装）
- `/build/bifrost-trade-worker/scripts`（含 `run_celery.py`）
- `/build/bifrost-trade-socket/scripts`（含 `run_massive_ws.py`）
- `procps`（Celery pgrep）

9 个 API Deployment 共用同一 digest（crane copy），由 K8s command 区分 domain。

## 日常交付流程

### 1. 推送业务仓库到 GitHub

至少涉及 STG 近期改动的 repo：

- `bifrost-trade-api` — Ops Socket/Celery 修复
- `bifrost-trade-socket` — Massive delayed WS + 120s heartbeat
- `bifrost-trade-worker` — `run_celery.py`
- `bifrost-trade-frontend` — Socket 页 Stg pill / k8s_managed
- `bifrost-trade-infra` — overlay、config、Tekton、Dockerfile

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

等价于 `scripts/k3s/run-deliver-stg.sh`，默认：

1. Gitea mirror-sync（从 GitHub 拉最新）
2. `sync-stg-config`（若有 `.env`）
3. 更新 Tekton Dockerfile ConfigMaps
4. 创建 `bifrost-deliver-stg` PipelineRun
5. 等待完成（默认 2h 超时）

**环境变量：**

| 变量 | 默认 | 说明 |
|------|------|------|
| `SYNC_GITEA` | `1` | 跑 Gitea mirror-sync |
| `APPLY_OVERLAY` | `0` | deliver 时是否 `kubectl apply -k` |
| `RUN_DB_INIT` | `0` | 成功后重跑 `db-init-stg` Job |
| `REVISION` | `main` | Gitea clone 分支 |

```bash
# 已手动 sync 过 Gitea，只重建镜像
SYNC_GITEA=0 make k3s-deliver-stg

# 配置 + 镜像一起更新
APPLY_OVERLAY=1 make k3s-deliver-stg
```

### 4. 验证

```bash
make k3s-verify-phase-b-stg-v2
curl -s http://192.168.10.73:30880/api/monitor/status
```

Ops Console：**Delivery → bifrost-deliver-stg → Run**（Platform API 创建 PipelineRun）。

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

## Massive WS STG 要点

- Watchlist 种子：`scripts/k3s/seed-stg-watchlist.sh`（从 Dev PG 导入）
- **Options Starter**：`massive.features.ws_enabled: false` — `massive-ws` REST-only 待机（`ws_mode=rest_only`），期权 aggregates 走 Celery REST；**不要求** live Polygon WS quotes
- Options Developer+：设 `ws_enabled: true`（或 `tier: developer`）后启用 WS；Starter 可用 `wss://delayed.polygon.io/options`
- K8s 托管：Socket 页 Start/Stop 禁用；重启用 `kubectl rollout restart deployment/massive-ws -n bifrost-stg`

## 相关文件

```
k8s/cicd/tekton/pipeline-deliver-stg.yaml
k8s/cicd/tekton/task-deliver-stg.yaml
k8s/cicd/tekton/task-kaniko-*.yaml
k8s/cicd/docker/Dockerfile.*-stg
scripts/k3s/run-deliver-stg.sh
scripts/k3s/bootstrap-gitea-mirrors.sh
k8s/overlays/stg/
```

完整 Phase B 计划见 `docs/PHASE_B_STG_V2_PLAN.md`。
